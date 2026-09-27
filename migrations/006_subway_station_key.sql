-- 지하철 승하차와 역 위치를 역 이름으로 연결하기 위한 키
-- 승하차 데이터에는 '삼각지(전쟁기념관)' 처럼 괄호 부제가 붙어 있고, 역 위치에는 '삼각지' 로 되어 있다.
-- 괄호 부분을 뗀 이름을 station_key 로 두 테이블에 같은 규칙으로 만든다.

ALTER TABLE subway_station
    ADD COLUMN station_key text GENERATED ALWAYS AS (btrim(regexp_replace(station_nm, '\(.*\)$', ''))) STORED;

ALTER TABLE subway_ridership
    ADD COLUMN station_key text GENERATED ALWAYS AS (btrim(regexp_replace(station_nm, '\(.*\)$', ''))) STORED;

CREATE INDEX subway_station_key_idx ON subway_station (station_key);
CREATE INDEX subway_ridership_key_idx ON subway_ridership (station_key, use_month);
