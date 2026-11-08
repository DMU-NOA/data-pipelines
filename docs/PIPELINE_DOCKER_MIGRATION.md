# Docker 상주형 NOA 데이터 파이프라인 전환 설계 (test 브랜치)

작성 기준: 2026-11-08, `test` HEAD `218f1b8bdabc4f6e162dcd9ee4d0833bba44c557`.

> **상태: 설계 문서만 추가. 실행 동작, DB 구조, Windows 스케줄러는 아직 변경하지 않음.**
> 본 문서는 변경 범위와 검증 기준을 먼저 확정하기 위한 것이다.

## 목표
- Docker 이미지 빌드 후 `docker compose up -d --build` 1회로 상주형 파이프라인 자동 시작.
- **단일 애플리케이션 컨테이너, 단일 상주 Python 프로세스**에서 수집(collector), 가공(processor), 서비스 적재(serving loader)를 독립적인 작업으로 실행.
- Windows Task Scheduler 미사용. 데이터 소스별 수집 주기와 후속 작업 의존성은 컨테이너 내부 스케줄러/DB 작업 큐로 관리.
- 외부 API 원본은 `data/raw/`의 영속 볼륨에 보존. 정제·시계열 이력은 PostgreSQL 저장. 백엔드 직접 조회용 결과만 서비스 테이블에 적재.
- 현재 FastAPI 스키마 및 API 동작을 깨지 않는 단계적 전환.

## 확인한 기존 구현
- `jobs/run_daily.py`: 공휴일/TourAPI/위치 기준/KTO/ASOS/S-DoT/생활인구/교통 등 수집 → `load_db` → `refresh_congestion`.
- `jobs/run_realtime.py`: CityData 수집 → CityData/교통 적재 → `service.sync_all()` → `refresh_congestion()` → `hourly_predict.publish()`.
- `jobs/load_db.py`: 기준·관광지·공간·시계열 로더와 `service.sync_all()`가 한 작업에 결합.
- `ml/predict.py`: 실측 동기화/검증 RF 또는 미검증 KNN 추론/서비스 테이블 INSERT 결합.
- `ml/hourly_predict.py`: 검증 V2 추론/서비스 테이블 INSERT 결합.
- `pyproject.toml`: Python >=3.13, scikit-learn 및 psycopg 의존성 존재; 현재 Dockerfile/compose.yaml 없음.
- `main`, `test`가 같은 HEAD인 시점에서 **test 브랜치만 수정**.

## 제안하는 운영 구조

```text
Docker ENTRYPOINT => python -m noa_data.pipeline_service
  ├─ startup: configuration / DB reachability / migrations / recovery
  ├─ scheduler: source-specific collection schedules (Asia/Seoul)
  ├─ durable job coordinator: collect -> process -> serve
  └─ bounded worker: stages run independently, no concurrent duplicate batch
External data -> collectors -> durable raw files + batch metadata
                -> processors -> normalized history + spatial/ML artifacts
                -> serving loader -> backend-facing tables
PostgreSQL/PostGIS: same instance, logical boundaries first
FastAPI: reads backend-facing tables
```

### 작업 단위
- `collect(source, window)`: 원본 파일 저장 + 배치 메타데이터 기록. API 실패시 다른 소스 수집은 계속.
- `process(batch_id)`: 로더의 원천 정제/이력 적재, 공간 관계 구성, 필요한 경우 ML 특징 생성·추론. 원본 파일을 반복 다운로드하지 않음.
- `serve(batch_id)`: 완료된 가공 결과를 `tour_spots`, `seoul_spots`, `spot_mapping`, `latest_congestion`, 공식/ML 시간별 예보 등에 갱신. 더 오래된 자료가 최신 자료를 덮어쓰지 못함.
- `train(model)`: 별도 주기·품질 게이트. 추론과 재학습은 구분. 검증된 모델이 없으면 CityData 실측/공식 예보는 그대로 서비스, V1 KNN은 미검증 출처 표시.

### 바로 서비스 가능한 데이터의 빠른 경로
- CityData 실제 혼잡도/공식 예보: 원본 저장 후 **최소 스키마·시각·중복 검증**을 거쳐 서비스 적재를 우선 예약. 같은 배치는 원천 관측 이력에도 저장.
- 이 빠른 경로도 **serving loader가 단독으로 DB write**; collector가 서비스 테이블에 직접 쓰지 않음.
- 관광지 정보/축제는 일반 정제 경로; S-DoT·교통·생활인구 등은 시계열과 ML 특징 저장 후 필요한 서비스 집계만 반영.

### 실행과 복구
- 단일 Python 프로세스: APScheduler(또는 동급)로 기동 후 계속 대기. 실제 작업은 내부 제한된 worker로 실행하며 CPU 부하 높은 학습 작업은 동시성 제한.
- PostgreSQL에 `pipeline_runs`/`pipeline_jobs` 이력: source, window, stage, input batch, state, retries, last_error, timestamps.
- 고유키/UPSERT/lock으로 중복 실행 방지. 컨테이너 재시작시 running 상태 복구.
- 작업 실패 시 해당 batch 후속 stage 정지. 기존 정상 serving 값 유지.
- `data/raw`, `artifacts`는 영속 볼륨; `.env`는 이미지에 복사하지 않음. `TZ=Asia/Seoul` 및 시각 UTC 저장/표시 변환.

## 변경 예정 파일 (설계 → 구현 순서)
1. **기반**: `Dockerfile`, `.dockerignore`, `compose.yaml`, `pyproject.toml`, `src/noa_data/pipeline_service.py`, `src/noa_data/engine/`.
2. **수집 분리**: `jobs/run_daily.py`, `jobs/run_realtime.py`의 수집 단계만 재사용하는 소스별 registry; 기존 `collectors/` 유지.
3. **원천 적재/가공 분리**: `jobs/load_db.py`의 `LOADERS`에서 `service.sync_all` 제거한 정제 단계 + spatial/nearby 가공 단계. 기존 로더 내부 SQL은 최대 재사용.
4. **서비스 적재**: `loaders/service.py`와 `ml/predict.py`, `ml/hourly_predict.py`에서 계산/DB write 책임 분리.
5. **학습**: 기존 `jobs/run_training.py`의 모델 유효성 검증 유지, 스케줄 이벤트로 호출.
6. **운영**: README 최신화, `scripts/register_tasks.ps1`은 최종 전환 검증 이후에만 deprecated 처리.

## 구현 검증 순서
1. `docker compose config`, Docker 이미지 빌드 및 상주 프로세스 정상 기동.
2. 빈 DB 환경: 마이그레이션 → 누락된 기준자료 수집 → 독립 process/serve.
3. CityData 1회 수집 → 원본 및 실측 history → `latest_congestion` (actual) 확인.
4. 동일 batch 재실행 시 중복 없음, 실패/재시작 후 회복.
5. 관광지/축제와 S-DoT·교통·인구 확장, 주변 공간 관계 및 서비스 API 호환 확인.
6. 검증 모델 없을 때 실측/공식 예보 유지, KNN 출처 보존. 검증 모델 있으면 V1/V2 추론·적재.
7. API 429/비정상 응답, DB 연결 단절, batch 시간 역행, 15분 실행 겹침 테스트.
8. 신규 엔진으로 안정 운영 검증한 뒤에만 Windows 작업 스케줄러 중단.

## 배포 제약 및 주의
- 외부 PostgreSQL(RDS)이 기존처럼 준비되어 있으면 **파이프라인 컨테이너 하나**로 동작한다.
- 완전히 비어 있는 서버에서 DB와 FastAPI까지 모두 실행하려면 별도 DB/API 컨테이너나 관리형 서비스가 필요하다. 애플리케이션 프로세스 1개 요구와 DB 서버 1개 요구는 서로 다르다.
- Docker 이미지에는 공공데이터/모델/비밀키를 내장하지 않는다. 특히 CityData 과거 이력은 최초 설치만으로 복구되지 않으며 기존 raw 백업 또는 지속 수집이 필요하다.
- 초기 단계에서 Dockerfile만 만들어도 end-to-end 자동화가 완성된 것은 아니다. 각 단계 완료 조건 및 서비스 DB write 분리가 완료되어야 운영 가능 상태로 판단한다.
