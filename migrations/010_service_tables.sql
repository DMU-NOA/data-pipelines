-- Backend 서비스 호환용 테이블
-- data-pipelines가 원본/분석 테이블을 관리하고,
-- 현재 noa-backend가 읽는 서비스용 read model을 이 테이블들에 동기화한다.

CREATE TABLE IF NOT EXISTS users (
    id          serial PRIMARY KEY,
    social_id   varchar(255) NOT NULL,
    provider    varchar(20) NOT NULL,
    email       varchar(255),
    name        varchar(100),
    created_at  timestamp DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (social_id, provider)
);

CREATE TABLE IF NOT EXISTS seoul_spots (
    area_cd      varchar(50) PRIMARY KEY,
    name         varchar(255),
    category     varchar(50),
    name_en      varchar(255),
    category_en  varchar(100)
);

CREATE TABLE IF NOT EXISTS tour_spots (
    content_id        varchar(50) PRIMARY KEY,
    name              varchar(255),
    name_en           varchar(255),
    content_type_id   varchar(20),
    category          varchar(50),
    image_url         text,
    image_url2        text,
    description       text,
    description_en    text,
    address           text,
    address_en        text,
    mapx              numeric(11, 7),
    mapy              numeric(10, 7),
    event_start_date  date,
    event_end_date    date,
    updated_at        timestamp DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS spot_mapping (
    id          bigserial PRIMARY KEY,
    area_cd     varchar(50) UNIQUE NOT NULL
                REFERENCES seoul_spots(area_cd) ON DELETE CASCADE,
    content_id  varchar(50) UNIQUE NOT NULL
                REFERENCES tour_spots(content_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS likes (
    id          bigserial PRIMARY KEY,
    social_id   varchar(255) NOT NULL,
    provider    varchar(20) NOT NULL,
    area_cd     varchar(50)
                REFERENCES seoul_spots(area_cd) ON DELETE CASCADE,
    content_id  varchar(50)
                REFERENCES tour_spots(content_id) ON DELETE CASCADE,
    created_at  timestamp DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_likes_user_content
ON likes (social_id, provider, content_id);

CREATE TABLE IF NOT EXISTS latest_congestion (
    id                bigserial PRIMARY KEY,
    area_cd           varchar(50)
                      REFERENCES seoul_spots(area_cd) ON DELETE CASCADE,
    content_id        varchar(50)
                      REFERENCES tour_spots(content_id) ON DELETE CASCADE,
    congestion_level  varchar(20) NOT NULL,
    congestion_label  smallint NOT NULL CHECK (congestion_label BETWEEN 0 AND 3),
    source             varchar(20) NOT NULL CHECK (source IN ('actual', 'predicted')),
    updated_at         timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_latest_actual
ON latest_congestion(area_cd)
WHERE source = 'actual';

CREATE UNIQUE INDEX IF NOT EXISTS uq_latest_predicted
ON latest_congestion(content_id)
WHERE source = 'predicted';
