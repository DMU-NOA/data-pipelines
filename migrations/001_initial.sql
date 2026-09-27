-- NOA data-pipeline 초기 스키마
--
-- 원칙
-- - 원본 값은 최대한 그대로 보존한다 (0을 NULL로 바꾸지 않는다, 행을 삭제하지 않는다).
-- - 모든 테이블은 자연키를 PK로 두고 ON CONFLICT 로 적재한다 (여러 번 적재해도 결과가 같다).
-- - 좌표는 geography(Point, 4326) 로 저장해 거리를 미터 단위로 계산한다.
-- - 시각은 timestamptz 로 저장한다 (원본은 모두 KST).
-- - 백엔드와 같은 DB 의 public 스키마를 함께 쓴다. 백엔드 테이블과 이름이 겹치지 않게 한다.

CREATE EXTENSION IF NOT EXISTS postgis;


-- ==================================================
-- 파이프라인 운영: 원본 파일 적재 기록
-- ==================================================

CREATE TABLE pipeline_load_history (
    file_path   text PRIMARY KEY,           -- data/raw 기준 상대 경로
    source      text NOT NULL,
    row_count   integer NOT NULL,
    loaded_at   timestamptz NOT NULL DEFAULT now()
);


-- ==================================================
-- 관광 정보
-- ==================================================

-- TourAPI 장소 목록 (전체 분류, 언어별)
-- 외국어 서비스는 content_id 와 content_type_id 체계가 국문과 다르다.
CREATE TABLE tour_place (
    lang              text NOT NULL,         -- ko, en, ja, zh-CN, zh-TW
    content_id        text NOT NULL,
    content_type_id   text NOT NULL,         -- 국문 12 관광지, 14 문화시설 ... / 외국어 76 관광지, 78 문화시설 ...
    title             text NOT NULL,
    addr1             text,
    addr2             text,
    zipcode           text,
    tel               text,
    ldong_regn_cd     text,                  -- 법정동 시도 (서울 11)
    ldong_signgu_cd   text,                  -- 법정동 시군구 (예: 110 종로구)
    lcls_systm1       text,                  -- 신분류체계
    lcls_systm2       text,
    lcls_systm3       text,
    cat1              text,                  -- 구분류체계
    cat2              text,
    cat3              text,
    first_image       text,
    first_image2      text,
    cpyrht_div_cd     text,
    location          geography(Point, 4326) NOT NULL,
    created_time      timestamptz,
    modified_time     timestamptz,
    collected_at      timestamptz NOT NULL,
    PRIMARY KEY (lang, content_id)
);

CREATE INDEX tour_place_location_idx ON tour_place USING gist (location);
CREATE INDEX tour_place_type_idx ON tour_place (lang, content_type_id);


-- TourAPI 상세정보 (공통정보 + 소개정보)
-- 소개정보는 분류마다 필드 이름이 달라 원본을 intro 에 보존하고,
-- 운영시간과 휴무일만 공통 컬럼으로 뽑는다.
CREATE TABLE tour_place_detail (
    lang              text NOT NULL,
    content_id        text NOT NULL,
    content_type_id   text,
    overview          text,
    homepage          text,
    use_time          text,
    rest_date         text,
    parking           text,
    info_center       text,
    intro             jsonb,
    collected_at      timestamptz NOT NULL,
    PRIMARY KEY (lang, content_id)
);


-- TourAPI 축제/공연/행사 (행사 기간 포함)
CREATE TABLE tour_festival (
    lang              text NOT NULL,
    content_id        text NOT NULL,
    title             text NOT NULL,
    event_start_date  date,
    event_end_date    date,
    addr1             text,
    addr2             text,
    tel               text,
    ldong_regn_cd     text,
    ldong_signgu_cd   text,
    first_image       text,
    location          geography(Point, 4326),
    modified_time     timestamptz,
    collected_at      timestamptz NOT NULL,
    PRIMARY KEY (lang, content_id)
);

CREATE INDEX tour_festival_period_idx ON tour_festival (event_start_date, event_end_date);
CREATE INDEX tour_festival_location_idx ON tour_festival USING gist (location);


-- ==================================================
-- S-DoT 유동인구 센서
-- ==================================================

-- 센서 마스터 (설치 위치정보 엑셀 134개)
-- 특정 기간에 측정값이 없어도 삭제하지 않는다.
CREATE TABLE sdot_sensor (
    sensor_code       integer PRIMARY KEY,   -- 방문자 센서코드 (예: 2993)
    device_serial     text,                  -- 엑셀 시리얼번호 (예: V02Q1940889). 측정값의 시리얼과 다르다
    address           text,
    location          geography(Point, 4326),
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX sdot_sensor_location_idx ON sdot_sensor USING gist (location);


-- 측정값
-- 위치정보에 없는 센서가 새로 나타나도 측정값은 버리지 않도록 FK 는 두지 않는다.
-- 같은 (센서, 측정시각) 이 재등록되면 가장 늦게 등록된 값을 쓴다.
CREATE TABLE sdot_observation (
    sensor_code          integer NOT NULL,   -- 정규화 코드 (00000002993 -> 2993)
    observed_at          timestamptz NOT NULL,
    serial_no            text NOT NULL,      -- 원본 그대로 (00000002993)
    model_name           text,
    visitor_count        integer NOT NULL,   -- 0 은 0 그대로 저장
    region               text,               -- traditional_markets, main_street ...
    district             text,
    administrative_dong  text,
    registered_at        timestamptz,
    source_api           text NOT NULL,      -- IotVdata018, sDoTPeople
    collected_at         timestamptz NOT NULL,
    PRIMARY KEY (sensor_code, observed_at)
);

CREATE INDEX sdot_observation_time_idx ON sdot_observation (observed_at);


-- ==================================================
-- 혼잡 관련 (실시간 인구, 외부 예측)
-- ==================================================

-- 서울시 주요 121장소
CREATE TABLE citydata_area (
    area_cd           text PRIMARY KEY,      -- POI001 ...
    area_nm           text NOT NULL,
    eng_nm            text,
    category          text
);


-- 실시간 인구 (정답 데이터)
-- 같은 인구 집계 시각을 여러 번 수집해도 한 행만 남는다.
CREATE TABLE citydata_population (
    area_cd              text NOT NULL,
    ppltn_time           timestamptz NOT NULL,
    congest_lvl          text,
    congest_msg          text,
    ppltn_min            integer,
    ppltn_max            integer,
    male_rate            numeric,
    female_rate          numeric,
    rate_0               numeric,
    rate_10              numeric,
    rate_20              numeric,
    rate_30              numeric,
    rate_40              numeric,
    rate_50              numeric,
    rate_60              numeric,
    rate_70              numeric,
    resnt_rate           numeric,            -- 상주인구 비율
    non_resnt_rate       numeric,            -- 비상주인구 비율
    replace_yn           text,               -- 대체 데이터 여부
    collected_at         timestamptz NOT NULL,
    PRIMARY KEY (area_cd, ppltn_time)
);

CREATE INDEX citydata_population_time_idx ON citydata_population (ppltn_time);


-- 서울시 12시간 인구 예측
-- 어느 시점(ppltn_time)에 한 예측인지 남겨 나중에 실제값과 비교한다.
CREATE TABLE citydata_forecast (
    area_cd              text NOT NULL,
    ppltn_time           timestamptz NOT NULL,
    fcst_time            timestamptz NOT NULL,
    congest_lvl          text,
    ppltn_min            integer,
    ppltn_max            integer,
    collected_at         timestamptz NOT NULL,
    PRIMARY KEY (area_cd, ppltn_time, fcst_time)
);


-- 한국관광공사 관광지 집중률 30일 예측
-- 수집일을 키에 넣어, 같은 날짜에 대한 예측이 어떻게 바뀌는지와
-- 나중에 실제값과 맞았는지를 비교할 수 있게 한다.
CREATE TABLE kto_concentration (
    collected_date       date NOT NULL,
    signgu_cd            text NOT NULL,
    t_ats_nm             text NOT NULL,      -- 관광지명 (ID 없음)
    base_ymd             date NOT NULL,      -- 예측 대상 날짜
    area_cd              text,
    area_nm              text,
    signgu_nm            text,
    cnctr_rate           numeric NOT NULL,
    PRIMARY KEY (collected_date, signgu_cd, t_ats_nm, base_ymd)
);

CREATE INDEX kto_concentration_target_idx ON kto_concentration (t_ats_nm, base_ymd);
