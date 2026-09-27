-- NOA 서비스 카테고리
--
-- 원본 분류(tour_place.lcls_systm1~3)는 그대로 두고, 적재할 때 대응표(noa_category_rule)로
-- noa_category 를 붙인다. 규칙을 바꾸면 다음 적재 때 전체가 다시 분류된다 (재수집 불필요).
--
-- 카테고리, 규칙, 수동 지정의 내용은 config/*.csv 가 원본이다.
-- 이 마이그레이션은 테이블 구조만 만들고, 적재할 때 CSV 내용으로 채운다.


-- TourAPI 신분류체계 코드와 이름 (3단계, 246개)
CREATE TABLE tour_lcls_code (
    lcls_systm3     text PRIMARY KEY,
    lcls_systm3_nm  text NOT NULL,
    lcls_systm2     text NOT NULL,
    lcls_systm2_nm  text NOT NULL,
    lcls_systm1     text NOT NULL,
    lcls_systm1_nm  text NOT NULL,
    collected_at    timestamptz NOT NULL
);


-- NOA 카테고리 5가지
CREATE TABLE noa_category (
    code          text PRIMARY KEY,
    name          text NOT NULL,
    environment   text NOT NULL CHECK (environment IN ('indoor', 'outdoor', 'mixed')),  -- 날씨 보정에 사용
    sort_order    smallint NOT NULL
);


-- TourAPI 분류 코드 → NOA 카테고리 대응표
-- lcls_prefix 는 1단계(HS), 2단계(VE01), 3단계(EX070200) 어느 것이든 된다.
-- 여러 규칙이 맞으면 가장 긴(구체적인) 규칙을 쓴다.
-- 규칙이 없는 분류(면세점 SH04, 숙박 AC, 축제 EV 등)는 카테고리를 붙이지 않는다.
CREATE TABLE noa_category_rule (
    lcls_prefix   text PRIMARY KEY,
    noa_category  text NOT NULL REFERENCES noa_category (code),
    note          text
);


-- 장소별 NOA 카테고리
-- noa_category_manual 을 채우면 규칙 대신 그 값을 쓴다 (잘못 분류된 곳을 고칠 때).
-- 값은 config/noa_category_overrides.csv 에서 적재할 때마다 다시 채운다.
ALTER TABLE tour_place
    ADD COLUMN noa_category         text REFERENCES noa_category (code),
    ADD COLUMN noa_category_manual  text REFERENCES noa_category (code);

CREATE INDEX tour_place_noa_category_idx ON tour_place (lang, noa_category);
