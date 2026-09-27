-- 관광지 단위 혼잡도를 위한 주변 신호와 공간 관계
--
-- 121장소(넓은 지역)보다 자세하게 보기 위해, 관광지 바로 주변의
-- 점 단위 데이터(지하철역, 버스정류장, S-DoT 센서)와 작은 구역 단위 데이터
-- (행정동)를 관광지와 연결한다.


-- ==================================================
-- 공간 기준
-- ==================================================

-- 행정동 경계 (vuski/admdongkor, 서울만)
-- adm_code 는 생활인구와 같은 8자리 (adm_cd2 10자리의 앞 8자리)
CREATE TABLE admin_dong (
    adm_code      text PRIMARY KEY,
    adm_cd2       text NOT NULL,
    adm_nm        text NOT NULL,
    sgg_code      text NOT NULL,
    sgg_nm        text,
    boundary      geography(MultiPolygon, 4326) NOT NULL,
    version       text NOT NULL             -- 경계 파일 버전 (예: ver20260701)
);

CREATE INDEX admin_dong_boundary_idx ON admin_dong USING gist (boundary);


-- 121장소 영역
ALTER TABLE citydata_area ADD COLUMN boundary geography(MultiPolygon, 4326);
CREATE INDEX citydata_area_boundary_idx ON citydata_area USING gist (boundary);


-- ==================================================
-- 지하철
-- ==================================================

-- 역 위치 (서울시 역사마스터). 호선이 다르면 다른 행이다.
CREATE TABLE subway_station (
    station_id    text PRIMARY KEY,         -- BLDN_ID
    station_nm    text NOT NULL,
    line          text NOT NULL,
    location      geography(Point, 4326) NOT NULL
);

CREATE INDEX subway_station_location_idx ON subway_station USING gist (location);
CREATE INDEX subway_station_name_idx ON subway_station (station_nm);


-- 호선별 역별 시간대별 승하차 (월 합계)
-- 역 위치와는 역 이름으로 연결한다 (승하차 데이터에 역 ID 가 없다).
CREATE TABLE subway_ridership (
    use_month     date NOT NULL,            -- 그 달 1일
    line          text NOT NULL,
    station_nm    text NOT NULL,
    hour          smallint NOT NULL,        -- 0 ~ 23
    get_on        double precision,
    get_off       double precision,
    PRIMARY KEY (use_month, line, station_nm, hour)
);


-- ==================================================
-- 버스
-- ==================================================

-- 정류장 위치
CREATE TABLE bus_stop (
    stop_id       text PRIMARY KEY,         -- STOPS_NO (승하차 데이터의 STOPS_ID 와 같다)
    stop_nm       text NOT NULL,
    stop_type     text,
    node_id       text,
    location      geography(Point, 4326) NOT NULL
);

CREATE INDEX bus_stop_location_idx ON bus_stop USING gist (location);


-- 정류장별 시간대별 승하차 (월 합계, 노선을 합친 값)
-- 원본은 노선 x 정류장 단위라 너무 크므로 정류장 단위로 합쳐 넣는다.
-- 노선별 값은 원본 파일에 그대로 있다.
CREATE TABLE bus_ridership (
    use_month     date NOT NULL,
    stop_id       text NOT NULL,
    hour          smallint NOT NULL,
    get_on        double precision,
    get_off       double precision,
    route_count   smallint NOT NULL,        -- 합친 노선 수
    PRIMARY KEY (use_month, stop_id, hour)
);


-- ==================================================
-- 실시간 도시데이터의 날씨 (121장소별)
-- ==================================================

CREATE TABLE citydata_weather (
    area_cd          text NOT NULL,
    weather_time     timestamptz NOT NULL,
    temperature      double precision,
    humidity         double precision,
    wind_speed       double precision,
    precipitation    text,                  -- 원본 그대로 ('-', '1mm미만', '2.5' 등)
    precpt_type      text,                  -- 없음, 비, 눈 ...
    pm10             double precision,
    pm25             double precision,
    air_idx          text,
    collected_at     timestamptz NOT NULL,
    PRIMARY KEY (area_cd, weather_time)
);


-- 발표 시점(weather_time) 별 24시간 예보
CREATE TABLE citydata_weather_forecast (
    area_cd          text NOT NULL,
    weather_time     timestamptz NOT NULL,
    fcst_time        timestamptz NOT NULL,
    temperature      double precision,
    precipitation    text,
    precpt_type      text,
    rain_chance      double precision,
    sky_stts         text,
    collected_at     timestamptz NOT NULL,
    PRIMARY KEY (area_cd, weather_time, fcst_time)
);


-- ==================================================
-- 관광지 ↔ 주변 신호 관계
-- ==================================================

-- 관광지(tour_place, 한국어) 마다 주변의 신호 후보를 거리와 함께 모두 남긴다.
-- 가장 가까운 하나로 고정하지 않고, ML 에서 가장 가까운 N개, 반경, 거리 가중치를 실험한다.
--
-- target_type
--   admin_dong      : 관광지가 속한 행정동 (distance_m = 0)
--   citydata_area   : 관광지가 속하거나 가까운 121장소 영역 (속하면 0)
--   sdot_sensor     : 반경 안의 S-DoT 센서
--   subway_station  : 반경 안의 지하철역
--   bus_stop        : 반경 안의 버스정류장
-- 반경은 config/place_nearby.csv 에서 정한다.
CREATE TABLE place_nearby (
    content_id     text NOT NULL,
    target_type    text NOT NULL,
    target_id      text NOT NULL,
    distance_m     double precision NOT NULL,
    rank           smallint NOT NULL,       -- 같은 종류 안에서 가까운 순서 (1부터)
    PRIMARY KEY (content_id, target_type, target_id)
);

CREATE INDEX place_nearby_target_idx ON place_nearby (target_type, target_id);
