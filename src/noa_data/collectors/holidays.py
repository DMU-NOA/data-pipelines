from pathlib import Path

from noa_data.collectors.common import get_env, get_json, now_kst, save_raw


SOURCE = "holidays"

# 한국천문연구원_특일 정보 - 공휴일 정보 조회
# 대체공휴일, 선거일 같은 임시공휴일도 지정되면 반영된다.
URL = "https://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/getRestDeInfo"


def collect(year: int) -> Path:
    """
    한 해의 공휴일 목록을 원본 그대로 저장한다.

    임시공휴일은 연중에 새로 지정될 수 있으므로 올해와 내년은 주기적으로 다시 받는다.
    """

    collected_at = now_kst()

    payload = get_json(
        URL,
        params={
            "serviceKey": get_env("DATA_GO_KR_API_KEY"),
            "solYear": str(year),
            "numOfRows": 100,
            "_type": "json",
        },
    )

    header = payload.get("response", {}).get("header", {})

    if header.get("resultCode") != "00":
        raise RuntimeError(f"특일정보 응답 오류: {year} {header or payload}")

    body = payload["response"]["body"]
    path = save_raw(SOURCE, f"rest_days_{year}", payload, collected_at)

    print(f"{year}: 공휴일 {body.get('totalCount', 0)}일 → {path}")

    return path
