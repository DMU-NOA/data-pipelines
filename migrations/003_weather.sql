-- 기상청 ASOS 시간별 관측 (서울 관측소 108)
-- 원본에서 값이 비어 있으면 NULL 로 둔다.
-- 강수량(rn)과 적설(dsnw)은 비/눈이 없을 때 비어 있으므로 NULL 은 대부분 "없음"을 뜻한다.
CREATE TABLE weather_observation (
    station_id       text NOT NULL,
    observed_at      timestamptz NOT NULL,
    temperature      double precision,     -- 기온 (°C)
    precipitation    double precision,     -- 강수량 (mm)
    humidity         double precision,     -- 습도 (%)
    wind_speed       double precision,     -- 풍속 (m/s)
    wind_direction   double precision,     -- 풍향 (16방위, 도)
    snow_depth       double precision,     -- 적설 (cm)
    cloud_amount     double precision,     -- 전운량 (10분위)
    visibility       double precision,     -- 시정 (10m)
    sunshine         double precision,     -- 일조 (hr)
    collected_at     timestamptz NOT NULL,
    PRIMARY KEY (station_id, observed_at)
);
