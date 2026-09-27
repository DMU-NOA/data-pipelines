from pathlib import Path

from noa_data.collectors.common import (
    RAW_DATA_DIR,
    get_env,
    load_raw,
    now_kst,
    save_raw,
)
from noa_data.collectors.tourapi_places import (
    call,
    extract_items,
    latest_raw_file,
)
from noa_data.loaders.category import RULE_FILE, read_csv


SOURCE = "tourapi_details"

# 개발계정은 오퍼레이션별로 하루 호출 수가 제한되어 있다.
# 한 곳당 detailCommon2 + detailIntro2 두 번을 호출한다.
DEFAULT_MAX_PLACES = 450


def collected_ids(lang: str) -> set[str]:
    """
    이미 상세정보를 받은 content_id 목록.
    여러 날에 나눠 실행할 때 이어서 수집하는 데 쓴다.
    """

    ids: set[str] = set()

    for path in (RAW_DATA_DIR / SOURCE).glob(f"*/details_{lang}_*.json.gz"):
        ids.update(load_raw(path)["payload"]["details"])

    return ids


def target_places(lang: str) -> dict[str, dict]:
    """
    상세정보를 받을 장소: NOA 카테고리가 붙는 곳 (config/noa_category_rules.csv 와 같은 규칙).
    관광지, 문화시설, 음식점, 시장·백화점·쇼핑몰 등. 면세점(개별 매장), 숙박은 제외된다.
    """

    prefixes = [row["lcls_prefix"] for row in read_csv(RULE_FILE)]
    places: dict[str, dict] = {}

    for payload in load_raw(latest_raw_file(lang))["payload"]["pages"]:
        for item in extract_items(payload):
            code = str(item.get("lclsSystm3") or "")

            if any(code.startswith(prefix) for prefix in prefixes):
                places[str(item["contentid"])] = item

    return places


def fetch_detail(lang: str, content_id: str, content_type: str) -> dict:
    """
    한 곳의 공통정보(개요, 홈페이지 등)와 소개정보(운영시간, 휴무일, 주차 등)를 조회한다.
    """

    common = call(lang, "detailCommon2", {"contentId": content_id})
    intro = call(
        lang,
        "detailIntro2",
        {"contentId": content_id, "contentTypeId": content_type},
    )

    return {
        "common": extract_items(common),
        "intro": extract_items(intro),
    }


def collect(
    lang: str = "ko",
    max_places: int = DEFAULT_MAX_PLACES,
) -> Path | None:
    """
    목록에 있는 장소의 상세정보를 받는다.

    이미 받은 장소는 건너뛰므로, 하루 한도 안에서 매일 실행하면
    전체 목록을 며칠에 걸쳐 채운다.
    """

    get_env("DATA_GO_KR_API_KEY")

    collected_at = now_kst()

    places = target_places(lang)
    done = collected_ids(lang)
    todo = [
        (content_id, str(item["contenttypeid"]))
        for content_id, item in places.items()
        if content_id not in done
    ][:max_places]

    print(f"{lang}: 전체 {len(places):,} / 완료 {len(done & set(places)):,} / 이번 실행 {len(todo):,}")

    if not todo:
        return None

    details: dict[str, dict] = {}
    errors: dict[str, str] = {}

    for index, (content_id, content_type) in enumerate(todo, start=1):
        try:
            details[content_id] = fetch_detail(lang, content_id, content_type)

        except RuntimeError as error:
            errors[content_id] = str(error).splitlines()[0]

            # 하루 한도 초과는 이후 요청도 모두 실패하므로 멈춘다.
            if "LIMITED" in errors[content_id].upper():
                print("호출 한도에 걸려 중단합니다.")
                break

        if index % 50 == 0:
            print(f"[{index:>4}/{len(todo)}] 성공 {len(details)} / 실패 {len(errors)}")

    if not details:
        raise RuntimeError(f"모든 요청이 실패했습니다. 첫 오류: {next(iter(errors.values()))}")

    path = save_raw(
        SOURCE,
        f"details_{lang}",
        {"lang": lang, "details": details, "errors": errors},
        collected_at,
    )

    print(f"성공 {len(details)} / 실패 {len(errors)} → {path}")

    return path
