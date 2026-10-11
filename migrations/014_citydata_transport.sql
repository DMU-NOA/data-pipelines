-- CityData road conditions and live parking are parsed by data-pipelines,
-- stored as history, and queried read-only by FastAPI.
-- Keep area_cd and observed_at so a stored snapshot is never treated as timeless live data.
CREATE TABLE IF NOT EXISTS citydata_road_traffic (
    area_cd text NOT NULL,
    observed_at timestamptz NOT NULL,
    avg_speed double precision,
    road_msg text,
    collected_at timestamptz NOT NULL,
    PRIMARY KEY (area_cd, observed_at)
);
CREATE INDEX IF NOT EXISTS citydata_road_latest_idx
    ON citydata_road_traffic(area_cd, observed_at DESC);

CREATE TABLE IF NOT EXISTS citydata_parking (
    area_cd text NOT NULL,
    parking_key text NOT NULL,
    parking_name text NOT NULL,
    observed_at timestamptz NOT NULL,
    available_count integer NOT NULL CHECK (available_count >= 0),
    capacity integer NOT NULL CHECK (capacity >= 0),
    base_fee integer,
    location geography(Point, 4326) NOT NULL,
    collected_at timestamptz NOT NULL,
    PRIMARY KEY (area_cd, parking_key, observed_at)
);
CREATE INDEX IF NOT EXISTS citydata_parking_latest_idx
    ON citydata_parking(area_cd, parking_key, observed_at DESC);
CREATE INDEX IF NOT EXISTS citydata_parking_location_idx
    ON citydata_parking USING gist(location);
