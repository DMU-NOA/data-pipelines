-- 행정동 단위 단기체류 외국인 생활인구 (1시간)
--
-- 집계구 단위는 한 달 약 700만 행 이상이라,
-- 집계구 경계(SGIS)로 관광지 주변 집계구만 고를 수 있을 때까지 DB 에는 행정동 단위를 쓴다.
-- 집계구 원본 파일은 data/raw/seoul_files/OA-14980 에 계속 받아 둔다.
CREATE TABLE foreigner_population_dong (
    base_date     date NOT NULL,
    hour          smallint NOT NULL,
    adm_code      text NOT NULL,            -- 행정동 코드 8자리
    total         double precision,
    chinese       double precision,
    non_chinese   double precision,
    PRIMARY KEY (adm_code, base_date, hour)
);

CREATE INDEX foreigner_population_dong_date_idx ON foreigner_population_dong (base_date, hour);
