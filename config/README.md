# config

데이터를 만드는 기준이 되는 설정 파일. **DB 에서 직접 고치지 말고 이 파일을 고친 뒤 커밋한다.**
적재(`python -m noa_data.jobs.load_db`) 할 때마다 DB 에 그대로 반영되므로,
누가 새 DB 에 처음부터 적재해도 같은 결과가 나온다.

| 파일 | 내용 | 반영되는 테이블 |
|---|---|---|
| `noa_category.csv` | NOA 카테고리 5가지 (code, 이름, 실내/야외, 순서) | `noa_category` |
| `noa_category_rules.csv` | TourAPI 분류 코드(앞부분) → NOA 카테고리. 여러 규칙이 맞으면 가장 긴 규칙 | `noa_category_rule` |
| `noa_category_overrides.csv` | 규칙과 다르게 분류할 장소 (lang, content_id). 이유를 적는다 | `tour_place.noa_category_manual` |
| `place_nearby.csv` | 관광지마다 주변 신호(행정동, 121장소, S-DoT, 지하철역, 버스정류장)를 찾는 반경과 개수 | `place_nearby` |

- 분류 코드 이름은 DB 의 `tour_lcls_code` 테이블에서 확인할 수 있다 (예: `HS010100` = 고궁).
- `noa_category_rules.csv` 는 관광지 상세정보를 받을 대상을 정할 때도 쓴다 (카테고리가 붙는 곳만 받는다).
- `place_nearby` 는 한국어 관광지 중 NOA 카테고리가 있고 좌표가 정상인 곳만 대상으로 한다.
