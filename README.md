# NOA Data Pipeline

서울 관광지의 혼잡도를 **관광지 단위로** 예측하기 위한 데이터 수집·적재 파이프라인.

서울시 실시간 도시데이터(121장소)는 "광화문·덕수궁" 처럼 넓은 지역 단위라 관광지 하나하나의
혼잡도를 나타내지 못한다. 그래서 관광지마다 **바로 주변의 신호**(지하철역, 버스정류장,
S-DoT 센서, 행정동/집계구 인구)를 모으고 관광지와 공간으로 연결한다.
121장소는 넓은 지역의 추세와 예측 검증에 쓴다.

```
외부 API / 파일
   │  collectors (원본 그대로 저장)
   ▼
data/raw/<소스>/<수집일>/*.json.gz, data/raw/seoul_files/<데이터셋>/<원본 파일>
   │  loaders (정제, 중복 제거, 공간 변환)      ← config/*.csv (카테고리, 반경)
   ▼
PostgreSQL + PostGIS (public 스키마, 백엔드와 같은 DB 를 쓴다)
   │
   ▼
예측 (예정) → FastAPI 백엔드
```

## 수집하는 데이터

### 관광지 (예측 대상)

| 데이터 | 출처 | 테이블 |
|---|---|---|
| 관광지 목록 (전체 분류, 한/영/일/중) | TourAPI `areaBasedList2` (법정동 11) | `tour_place` |
| NOA 카테고리 5개 (역사·명소, 전시·문화, 자연·공원, 쇼핑·놀거리, 맛집) | `config/*.csv` 규칙 | `noa_category`, `tour_place.noa_category` |
| 분류 코드 이름 | TourAPI `lclsSystmCode2` | `tour_lcls_code` |
| 상세정보 (운영시간, 휴무일, 주차) | TourAPI `detailCommon2`, `detailIntro2` | 원본 파일 (적재 예정) |
| 축제·행사 (기간, 위치) | TourAPI `searchFestival2` | `tour_festival` |

### 관광지 주변 신호 (관광지 단위 혼잡도)

| 데이터 | 공간 단위 | 시간 단위 | 과거 | 출처 | 테이블 |
|---|---|---|---|---|---|
| S-DoT 유동인구 | 센서 지점 (약 110개) | 10분 | 2024-01~ | 서울 열린데이터광장 API + 주간 파일 | `sdot_observation`, `sdot_sensor` |
| 지하철 승하차 | 역 | 1시간 (월 합계) | 2024-01~ | `CardSubwayTime` | `subway_ridership`, `subway_station` |
| 버스 승하차 | 정류장 | 1시간 (월 합계) | 2024-01~ | `CardBusTimeNew` | `bus_ridership`, `bus_stop` |
| 단기체류 외국인 (관광객) | 행정동 (집계구는 원본만) | 1시간 | 2024-01~ | OA-14993 / OA-14980 월별 파일 | `foreigner_population_dong` |
| 생활인구 (내국인) | 행정동 | 1시간 | 2024-01~ | OA-14991 월별 파일 | `living_population` |
| 관광지 집중률 30일 예측 | 관광지 | 1일 | **없음 (매일 쌓음)** | 한국관광공사 | `kto_concentration` |

### 넓은 지역 추세, 외부 요인

| 데이터 | 과거 | 테이블 |
|---|---|---|
| 실시간 도시데이터 121장소 (인구, 12시간 예측, 날씨, 24시간 예보) | **없음 (15분마다 쌓음)** | `citydata_population`, `citydata_forecast`, `citydata_weather`, `citydata_weather_forecast` |
| 날씨 관측 (서울 ASOS, 시간별) | 2024-01~ | `weather_observation` |
| 공휴일 (대체·임시공휴일 포함) | 연도별 | `holiday` |

### 공간 기준과 관계

| 데이터 | 출처 | 테이블 |
|---|---|---|
| 행정동 경계 | [vuski/admdongkor](https://github.com/vuski/admdongkor) | `admin_dong` |
| 121장소 목록·영역 | OA-21285 | `citydata_area` |
| **관광지 ↔ 주변 신호 후보** (거리, 순위) | PostGIS 계산, 반경은 `config/place_nearby.csv` | `place_nearby` |

`place_nearby` 는 관광지마다 속한 행정동, 가까운 121장소 영역, 반경 안의 S-DoT 센서·지하철역·버스정류장을
거리순으로 모두 남긴다. 가장 가까운 하나로 고정하지 않는다.

### 수집하지 않는 것

- 네이버 지도 / 카카오맵 리뷰: robots.txt 에서 모든 봇 접근을 금지(`Disallow: /`)하므로 크롤링하지 않는다.
- 집계구 단위 내국인 생활인구 (OA-14979): 한 달 약 1.2GB 라 보류. 집계구 경계(SGIS)를 확보한 뒤 관광지 주변 집계구만 받는다.

## 처음 설치하고 실행하는 순서

팀원이 새로 받아도 같은 데이터가 만들어지도록, 설정은 모두 저장소 파일(`migrations/`, `config/`)에 있다.

### 1. 준비

```powershell
cd data-pipeline
python -m venv .venv
.venv\Scripts\activate
python -m pip install -e ".[dev]"
copy .env.example .env      # 키와 DB 비밀번호 입력 (.env.example 의 활용신청 목록 참고)
```

### 2. DB (로컬 개발용 Docker)

```powershell
docker run -d --name noa-postgis --restart unless-stopped `
  -e POSTGRES_DB=noa -e POSTGRES_USER=noa -e POSTGRES_PASSWORD=<.env 의 DB_PASSWORD> `
  -p 5432:5432 -v noa_pgdata:/var/lib/postgresql/data postgis/postgis:17-3.5

python -m noa_data.db.migrate          # migrations/*.sql 중 아직 적용하지 않은 것만 적용
```

### 3. 과거 데이터 수집 (처음 한 번, 약 6GB, 1시간 이상)

`run_daily` 한 번이 전부 받는다. 모든 단계가 이미 받은 것은 건너뛰므로 여러 번 실행해도 된다.

```powershell
python -m noa_data.jobs.run_daily
```

단계별로 따로 실행하려면 (위와 같은 순서):

```powershell
# 기준 정보
python -m noa_data.jobs.collect_holidays --years 2024 2025 2026 2027
python -m noa_data.jobs.collect_tourapi_places
python -m noa_data.jobs.collect_tourapi_codes
python -m noa_data.jobs.collect_tourapi_details          # 하루 450곳씩. 며칠 반복
python -m noa_data.jobs.collect_tourapi_festivals
python -m noa_data.jobs.collect_admdong_boundary
python -m noa_data.jobs.collect_seoul_files citydata_area
python -m noa_data.jobs.collect_seoul_files sdot_sensor
python -m noa_data.jobs.collect_seoul_subway_stations
python -m noa_data.jobs.collect_seoul_bus_stops

# 관광지 주변 신호 (2024-01 부터)
python -m noa_data.jobs.collect_kma_weather --start 20240101
python -m noa_data.jobs.collect_kto_concentration
python -m noa_data.jobs.collect_sdot --api recent --days 28 --skip-complete
python -m noa_data.jobs.collect_sdot --api realtime --days 14 --skip-complete
python -m noa_data.jobs.collect_seoul_files sdot_history --since 20240101
python -m noa_data.jobs.collect_seoul_files living_population --since 20240101
python -m noa_data.jobs.collect_seoul_files foreigner_block --since 20240101
python -m noa_data.jobs.collect_seoul_ridership subway
python -m noa_data.jobs.collect_seoul_ridership bus
python -m noa_data.jobs.collect_seoul_citydata          # 실시간 도시데이터 (지금 시점 1회)

# DB 적재 (이미 적재한 파일은 건너뜀)
python -m noa_data.jobs.load_db
```

`--dry-run` 을 붙이면 `collect_seoul_files` 는 받지 않고 받을 파일과 용량만 보여준다.
`load_db --only <이름>` 으로 일부만 적재할 수 있다 (순서는 `jobs/load_db.py` 의 `LOADERS`).

### 4. 정기 실행 등록 (Windows 작업 스케줄러)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\register_tasks.ps1
schtasks /Query /TN "\NOA\" /FO TABLE
```

| 작업 | 주기 | 내용 |
|---|---|---|
| `\NOA\realtime` | 15분 | 실시간 도시데이터 수집 (파일로만 저장) |
| `\NOA\daily` | 매일 01:10 | `run_daily`: 새로 나온 데이터 수집 → DB 적재 |

로그인되어 있고 PC 가 켜져 있을 때만 실행된다. 로그: `data/logs/<job>.log`. 서버가 정해지면 Kubernetes CronJob 으로 옮긴다.

## 운영 참고

### 다시 수집할 수 없는 데이터

아래는 API 가 과거 이력을 주지 않는다. 새로 설치한 사람이 다시 수집해도 **받기 시작한 날부터만** 생긴다.
이력이 필요하면 `data/raw/` 의 해당 폴더를 복사해 받아야 한다.

| 폴더 | 이유 |
|---|---|
| `data/raw/seoul_citydata` | 실시간 도시데이터는 현재 값만 제공 |
| `data/raw/kto_concentration` | 앞으로 30일 예측만 제공 |
| `data/raw/sdot_realtime`, `sdot_recent` | 최근 약 16일 / 한 달만 보관 (그 이전은 주간 파일로 대체 가능) |

### 원본 데이터의 알려진 문제

- 생활인구 월별 파일은 인코딩이 섞여 있다 (`202509` 만 CP949). 적재 코드가 파일마다 판단한다.
- 생활인구 원본에 `2025-07-08`, `07-09` 이틀이 없고 `2025-09-18` 은 일부만 있다.
- TourAPI 좌표 일부가 서울 밖이다 (기본값 `19.69, 117.99` 등). 행은 두고 `tour_place.location_valid = false` 로 표시한다.
- 지하철 승하차 역 이름에 괄호 부제가 붙어 있다. `station_key` (괄호 제거) 로 역 위치와 연결한다 (536개 중 532개 일치).
- TourAPI 는 `areaCode=1` 로 조회하면 서울 관광지가 절반 이상 빠진다. `lDongRegnCd=11` 을 쓴다.

### 키

- 현재 백엔드와 같은 키를 쓴다. 호출 한도를 나눠 쓰므로 파이프라인 전용 키를 권장한다.
- `SEOUL_API_KEY=sample` 로 두면 소스별 최대 5건만 받아 구조를 확인할 수 있다.

## 폴더 구조

```
data-pipeline/
├── config/            카테고리, 분류 규칙, 수동 지정, 주변 신호 반경 (DB 에 그대로 반영)
├── migrations/        테이블 구조 (001 ~)
├── scripts/           작업 스케줄러 등록
├── src/noa_data/
│   ├── collectors/    API 호출, 원본 저장
│   ├── loaders/       원본 → DB
│   ├── jobs/          실행 진입점 (python -m noa_data.jobs.<이름>)
│   └── db/            DB 접속, 마이그레이션
├── data/raw/          원본 (git 제외)
├── data/logs/         실행 로그 (git 제외)
└── tests/
```
