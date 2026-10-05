-- Backend likes 테이블의 기존 제약과 동일하게 사용자별 area_cd 찜 중복을 막는다.
CREATE UNIQUE INDEX IF NOT EXISTS uq_likes_user_area
ON likes (social_id, provider, area_cd);
