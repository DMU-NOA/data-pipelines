-- 장소 이름 비교용 키: 괄호 안 설명, 공백, 기호를 지우고 소문자로 바꾼다.
-- 예: '국립현대미술관/서울관' → '국립현대미술관서울관', '창덕궁과 후원 [유네스코 세계유산]' → '창덕궁과후원'
-- 한국관광공사 빅데이터(장소 코드가 TourAPI 와 다름)를 관광지에 연결할 때 쓴다.
CREATE FUNCTION noa_name_key(name text) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE
RETURN lower(
    regexp_replace(
        regexp_replace(coalesce(name, ''), '\(.*?\)|\[.*?\]', '', 'g'),
        '[\s/·\-_,.&''"]', '', 'g'
    )
);

CREATE INDEX tour_place_name_key_idx ON tour_place (lang, noa_name_key(title));
