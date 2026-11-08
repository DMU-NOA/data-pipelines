# NOA 단일 컨테이너 자동 파이프라인 — 1차 CityData 단계

> 2026-11-08 `test` 브랜치 실험 기능. 기존 `run_daily`/`run_realtime` 및 Windows 스케줄러는 **아직 삭제하지 않았음**. 두 스케줄러를 같은 DB에 동시에 연결하지 말 것.

## 실행 조건
- Docker Engine + Docker Compose 플러그인
- 이미 준비된 PostgreSQL/PostGIS DB. 외부 RDS 또는 별도 DB 컨테이너가 필요함.
- 서울 열린데이터광장 `SEOUL_API_KEY`, `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`가 들어 있는 프로젝트 `.env`
- **중요:** `DB_HOST=localhost`는 컨테이너 자신을 뜻함. 호스트 DB는 Docker Desktop에서 `host.docker.internal`, Linux에서는 도커 네트워크 내 서비스 이름 또는 접근 가능한 외부 IP/DNS를 사용.

```bash
git switch test
git pull --ff-only origin test
cp .env.example .env
# .env를 실제 API 키와 접속 가능한 DB 정보로 작성
docker compose up -d --build
docker compose logs -f pipeline
docker compose ps
```

컨테이너가 기동할 때 `python -m noa_data.pipeline_service`가 자동으로 실행되며, 사람이 수집 스크립트를 호출하지 않아도 다음 흐름이 시작된다.

```text
DB 준비 확인 및 SQL migration 016 → 재시작된 작업 복구
  → 최초 CityData 수집 작업 1회 등록
  → 매 00/15/30/45분 수집 일정 등록
  → DB durable queue를 10초마다 확인
  → collect: CityData API → 원본 파일 저장
  → process: 원본 검증, CityData/교통/주차 시계열 적재
  → serve: service.sync_all → actual / 검증 RF or KNN → 검증 V2 예측 발행
```

## 처음 시작하는 빈 DB
- SQL migrations가 자동 실행된다.
- `citydata_area`가 비어 있으면 로컬 원본 또는 서울시 OA-21285 121개 권역 파일을 확보해 적재한 뒤 실시간 수집을 시도한다.
- **관광지 전체·S-DoT·교통 월간 자료를 최초부터 모두 수집하는 기능은 이 1차 단계에 포함되지 않음.** 현재는 CityData 경로만 Docker 상주 서비스로 전환했다. 해당 자료는 이후 소스별로 이 구조에 이전할 예정.
- 외부 사이트 다운로드 또는 권한 실패 시 수집 작업은 최대 5회 지수 백오프 재시도되며, 원인은 `pipeline_jobs.last_error`에 남는다.
- `data/raw`와 모델은 Docker 이름 있는 볼륨 `noa_raw`, `noa_models`에 보존된다. 컨테이너 재생성 시 유지되지만 `docker compose down -v`는 데이터 볼륨을 삭제하므로 사용하지 않는다.
- 기존 Windows의 `data/raw`, `artifacts`와 **자동으로 동기화되지 않는다.** 과거 원본·모델을 재사용하려면 볼륨으로 별도 이관해야 한다.

## 작업 상태 확인
```sql
SELECT id, source, stage, state, attempts, batch_key, started_at,
       finished_at, last_error
FROM pipeline_jobs ORDER BY id DESC LIMIT 30;
```

`stage`: `collect`, `process`, `serve`.

`state`: `pending`, `running`, `succeeded`, `failed`.

컨테이너 비정상 종료 시 `running` 작업은 다음 시작에 `pending`으로 복구한다. 동일 배치 중복 등록은 unique constraint로 방지하며 SQL 적재는 기존 `pipeline_load_history`와 UPSERT 기반이다.

## 운영상 주의사항
- 모델 학습은 이 1차 컨테이너 스케줄에 아직 포함하지 않았다. 기존 모델이 없으면 공간 KNN의 **미검증 참고 추정**을 사용하며, 검증 V2 없으면 자체 시간별 예측을 생성하지 않는다. CityData 공식 시간별 예보는 별도 시계열 테이블에 적재된다.
- 현단계에서는 `process`가 CityData 이력 테이블(기존 백엔드가 직접 참고할 수 있음)에 저장하고, `serve`가 `latest_congestion` 등 서비스용 테이블을 갱신한다. 최종 목표인 완전한 raw/processed/serving 스키마 격리는 다음 단계다.
- 121개 API 호출은 시간이 걸리므로 15분 작업이 겹칠 수 있다. 단일 `stage_runner`가 작업을 순차 처리하여 동시에 같은 데이터를 덮어쓰지 않으며 큐에 대기한다.
- Docker만으로 PostgreSQL, 공공데이터 API 인증, 기존 모델 및 과거 CityData 이력이 자동 생성되지는 않는다.
- 이 변경은 GitHub 소스 반영까지만 확인했다. 실제 Docker 빌드, 공공 API, RDS 연결 및 엔드투엔드 실행은 사용 가능한 실행 환경에서 별도 검증해야 한다.

## 다음 단계
1. 투입 가능한 모의 CityData 파일로 큐 복구·재시도·중복 처리 통합 시험.
2. TourAPI/ASOS/S-DoT/교통/인구 수집 주기 등록 및 수집기 함수 직접 호출 지원.
3. `load_db`를 raw-staging / processing / serving 단계로 완전히 분리.
4. 모델 학습 별도 내부 예약 작업 및 모델 산출물 검증·교체 절차.
5. 정상 운영 이후 Windows 스케줄러 비활성화.
