-- 공휴일, 생활인구, 관광지 좌표 품질 표시


-- 원본 좌표가 서울 범위 밖이면 false (예: 좌표가 없을 때 들어간 기본값 19.69, 117.99)
-- 원본은 그대로 두고, 공간 검색과 예측에서 이 값으로 거른다.
ALTER TABLE tour_place ADD COLUMN location_valid boolean NOT NULL DEFAULT true;


-- 한국천문연구원 특일정보: 공휴일 (대체공휴일, 선거일, 임시공휴일 포함)
-- 같은 날짜에 공휴일이 둘 이상일 수 있다 (예: 어린이날 + 부처님오신날).
CREATE TABLE holiday (
    holiday_date    date NOT NULL,
    holiday_name    text NOT NULL,
    date_kind       text,
    is_holiday      boolean NOT NULL,
    collected_at    timestamptz NOT NULL,
    PRIMARY KEY (holiday_date, holiday_name)
);


-- 행정동 단위 서울 생활인구 (내국인), 1시간 단위
-- adm_code 는 행정동 코드 8자리 (행정동 경계 adm_cd2 10자리의 앞 8자리)
-- 월별 파일 단위로 한 달을 통째로 바꿔 넣는다.
CREATE TABLE living_population (
    base_date          date NOT NULL,
    hour               smallint NOT NULL,     -- 0 ~ 23
    adm_code           text NOT NULL,
    total              double precision NOT NULL,
    male_0_9           double precision,
    male_10_14         double precision,
    male_15_19         double precision,
    male_20_24         double precision,
    male_25_29         double precision,
    male_30_34         double precision,
    male_35_39         double precision,
    male_40_44         double precision,
    male_45_49         double precision,
    male_50_54         double precision,
    male_55_59         double precision,
    male_60_64         double precision,
    male_65_69         double precision,
    male_70_plus       double precision,
    female_0_9         double precision,
    female_10_14       double precision,
    female_15_19       double precision,
    female_20_24       double precision,
    female_25_29       double precision,
    female_30_34       double precision,
    female_35_39       double precision,
    female_40_44       double precision,
    female_45_49       double precision,
    female_50_54       double precision,
    female_55_59       double precision,
    female_60_64       double precision,
    female_65_69       double precision,
    female_70_plus     double precision,
    PRIMARY KEY (adm_code, base_date, hour)
);

CREATE INDEX living_population_date_idx ON living_population (base_date, hour);
