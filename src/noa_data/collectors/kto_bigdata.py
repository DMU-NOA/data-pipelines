from datetime import date, timedelta
from pathlib import Path

from noa_data.collectors.common import RAW_DATA_DIR, get_env, get_json, now_kst, save_raw
from noa_data.collectors.kto_concentration import SEOUL_AREA_CD, SEOUL_SIGNGU_CODES
from noa_data.collectors.tourapi_places import extract_items


BASE_URL = "https://apis.data.go.kr/B551011"

# 한국관광공사 관광 빅데이터 (월 단위로 공개)
DATASETS = {
    # 기초지자체 중심 관광지: 구마다 T맵 내비게이션 목적지 상위 100곳. 2024-05~
    "hub": {
        "operation": "LocgoHubTarService1/areaBasedList1",
        "source": "kto_hub_place",
        "name": "기초지자체 중심 관광지",
        "per_signgu": True,
    },
    # 관광지별 연관 관광지: 중심 관광지와 함께 찾는 곳 최대 50위. 2024-05~
    "related": {
        "operation": "TarRlteTarService1/areaBasedList1",
        "source": "kto_related_place",
        "name": "관광지별 연관 관광지",
        "per_signgu": True,
    },
    # 지역별 방문자수: 기초지자체별 일별 현지인/외지인/외국인. 전국이 한 번에 온다.
    "visitor": {
        "operation": "DataLabService/locgoRegnVisitrDDList",
        "source": "kto_region_visitor",
        "name": "기초지자체 일별 방문자수",
        "per_signgu": False,
    },
}

# 한 달치가 한 번에 오도록 크게 잡는다 (방문자수 한 달 약 2.5만 행, 연관 관광지 구당 약 1,600행)
PAGE_SIZE = 30000


def call(operation: str, params: dict) -> dict:
    payload = get_json(
        f"{BASE_URL}/{operation}",
        params={
            "serviceKey": get_env("DATA_GO_KR_API_KEY"),
            "MobileOS": "ETC",
            "MobileApp": "NOA",
            "_type": "json",
            **params,
        },
        timeout=60,
    )

    header = payload.get("response", {}).get("header", {})

    if header.get("resultCode") != "0000":
        raise RuntimeError(f"한국관광공사 빅데이터 응답 오류: {operation} {params} {header or payload}")

    return payload


def fetch_all(operation: str, params: dict) -> list[dict]:
    pages = []
    page_no = 1
    fetched = 0

    while True:
        payload = call(operation, {**params, "numOfRows": PAGE_SIZE, "pageNo": page_no})
        pages.append(payload)

        items = extract_items(payload)
        total = int(payload["response"]["body"].get("totalCount", 0))
        fetched += len(items)

        if fetched >= total or not items:
            return pages

        page_no += 1


def month_range(use_month: str) -> tuple[str, str]:
    year, month = int(use_month[:4]), int(use_month[4:])
    next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)
    last_day = (date(next_year, next_month, 1) - timedelta(days=1)).day

    return f"{use_month}01", f"{use_month}{last_day:02d}"


def collected_months(dataset: str) -> set[str]:
    source = DATASETS[dataset]["source"]

    return {
        path.name.split("_")[1]
        for path in (RAW_DATA_DIR / source).glob(f"*/{dataset}_*.json.gz")
    }


def collect(dataset: str, use_month: str) -> Path | None:
    """
    한 달치를 원본 그대로 저장한다. 데이터가 아직 없으면 저장하지 않는다.

    hub, related: 서울 25개 구를 구마다 조회한다.
    visitor: 그 달 1일 ~ 말일을 한 번에 조회한다 (전국).
    """

    get_env("DATA_GO_KR_API_KEY")

    config = DATASETS[dataset]
    collected_at = now_kst()

    if config["per_signgu"]:
        pages = {
            signgu_cd: fetch_all(
                config["operation"],
                {"baseYm": use_month, "areaCd": SEOUL_AREA_CD, "signguCd": signgu_cd},
            )
            for signgu_cd in SEOUL_SIGNGU_CODES
        }
        count = sum(len(extract_items(page)) for signgu in pages.values() for page in signgu)
    else:
        start, end = month_range(use_month)
        pages = {"all": fetch_all(config["operation"], {"startYmd": start, "endYmd": end})}
        count = sum(len(extract_items(page)) for page in pages["all"])

    if count == 0:
        print(f"{config['name']} {use_month}: 아직 공개되지 않음")
        return None

    path = save_raw(
        config["source"],
        f"{dataset}_{use_month}",
        {"dataset": dataset, "use_month": use_month, "pages": pages},
        collected_at,
    )

    print(f"{config['name']} {use_month}: {count:,} → {path}")

    return path
