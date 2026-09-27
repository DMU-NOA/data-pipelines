-- 한국관광공사 관광 빅데이터 (T맵 내비게이션, 통신 데이터)
--
-- 네이버 블로그 대신 쓰는 "장소의 기본 인지도" 재료 (내비게이션 목적지 순위, 함께 찾는 관광지).
-- 파이프라인은 원본 값과 관광지 연결표까지만 만든다. 인기도 점수 계산은 분석/모델 쪽에서 한다.
-- 한국관광공사 장소 코드(tats_cd, 해시 문자열)는 TourAPI content_id 와 다르므로
-- kto_place_match 로 연결한다.


-- 기초지자체 중심 관광지 (구마다 내비게이션 목적지 상위 100곳, 월 단위)
CREATE TABLE kto_hub_place (
    base_ym          date NOT NULL,             -- 그 달 1일
    signgu_cd        text NOT NULL,             -- 11110 (종로구)
    hub_tats_cd      text NOT NULL,
    hub_tats_nm      text NOT NULL,
    lcls_nm          text,                      -- 관광지, 숙박 ...
    mcls_nm          text,                      -- 역사관광 ...
    hub_rank         smallint NOT NULL,
    location         geography(Point, 4326),
    PRIMARY KEY (base_ym, signgu_cd, hub_tats_cd)
);


-- 관광지별 연관 관광지 (중심 관광지와 함께 찾는 곳, 최대 50위, 월 단위)
CREATE TABLE kto_related_place (
    base_ym          date NOT NULL,
    signgu_cd        text NOT NULL,
    tats_cd          text NOT NULL,             -- 중심 관광지
    tats_nm          text NOT NULL,
    rlte_tats_cd     text NOT NULL,             -- 연관 관광지
    rlte_tats_nm     text NOT NULL,
    rlte_signgu_cd   text,
    rlte_lcls_nm     text,
    rlte_mcls_nm     text,
    rlte_scls_nm     text,
    rlte_rank        smallint NOT NULL,
    PRIMARY KEY (base_ym, tats_cd, rlte_tats_cd)
);


-- 기초지자체별 일별 방문자 수 (통신 데이터, 서울만 넣는다)
CREATE TABLE kto_region_visitor (
    base_date        date NOT NULL,
    signgu_cd        text NOT NULL,
    signgu_nm        text,
    tou_div_cd       text NOT NULL,             -- 1 현지인, 2 외지인, 3 외국인
    tou_div_nm       text,
    daywk_div_cd     text,
    tou_num          double precision,
    PRIMARY KEY (base_date, signgu_cd, tou_div_cd)
);


-- 한국관광공사 장소 코드 → TourAPI 관광지
-- match_method: hub_location (중심 관광지 좌표 + 이름), name_signgu (같은 구 안에서 이름)
CREATE TABLE kto_place_match (
    tats_cd          text PRIMARY KEY,
    tats_nm          text NOT NULL,
    content_id       text NOT NULL,
    match_method     text NOT NULL,
    distance_m       double precision
);

