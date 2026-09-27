from pathlib import Path

from noa_data.collectors.common import get_env, now_kst, save_raw
from noa_data.collectors.tourapi_places import call, extract_items


SOURCE = "tourapi_codes"


def collect() -> Path:
    """
    TourAPI 신분류체계 코드와 이름 전체 (1~3단계) 를 원본 그대로 저장한다.
    """

    get_env("DATA_GO_KR_API_KEY")

    collected_at = now_kst()

    payload = call(
        "ko",
        "lclsSystmCode2",
        {"lclsSystmListYn": "Y", "numOfRows": 1000, "pageNo": 1},
    )

    path = save_raw(SOURCE, "lcls_codes", payload, collected_at)

    print(f"분류 코드 {len(extract_items(payload))}개 → {path}")

    return path
