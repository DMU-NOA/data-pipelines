-- TourAPI에는 좌표가 없는 장소도 존재한다.
-- 원본 행은 보존하고 location_valid=false로 서비스/공간 분석 대상에서 제외한다.
ALTER TABLE tour_place
    ALTER COLUMN location DROP NOT NULL;
