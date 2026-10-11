-- 013: 예측된 혼잡도와 실제 측정, 검증된 예측을 구분한다.
-- 이미 적용한 010 마이그레이션은 수정하지 않는다.
ALTER TABLE latest_congestion
    ADD COLUMN IF NOT EXISTS prediction_verified boolean NOT NULL DEFAULT false;

ALTER TABLE latest_congestion
    ADD COLUMN IF NOT EXISTS prediction_method text;

ALTER TABLE latest_congestion
    ADD COLUMN IF NOT EXISTS reference_distance_m double precision;

-- 종전 모델의 예측 기록은 신뢰 불가: 기본 false로 구분한다.
-- 실제(actual)는 해당 예측 메타데이터를 사용하지 않는다.
