from pathlib import Path

from noa_data.collectors.common import (
    RAW_DATA_DIR,
    get_env,
    get_json,
    load_raw,
    now_kst,
    save_raw,
)


SOURCE = "tourapi_places"

BASE_URL = "https://apis.data.go.kr/B551011"

# 언어별 TourAPI 서비스 (언어마다 data.go.kr 활용신청이 따로 필요하다)
# 외국어 서비스는 content_id와 contentTypeId 체계가 국문과 다르다.
# 수집 언어는 한국어, 영어, 일본어, 중국어(간체/번체)로 한정한다.
LANGUAGE_SERVICES = {
    "ko": "KorService2",
    "en": "EngService2",
    "ja": "JpnService2",
    "zh-CN": "ChsService2",
    "zh-TW": "ChtService2",
}

# 법정동 시도코드 11 = 서울
# 구버전 areaCode=1 로 조회하면 관광지가 절반 이상 빠진다 (375 vs 778, 2026-09 확인)
SEOUL_LDONG_REGN_CD = "11"

# 국문 contentTypeId
# 12 관광지, 14 문화시설, 15 축제공연행사, 25 여행코스, 28 레포츠, 32 숙박, 38 쇼핑, 39 음식점
# 외국어 contentTypeId
# 75 레포츠, 76 관광지, 77 교통, 78 문화시설, 79 쇼핑, 80 숙박, 82 음식점, 85 축제공연행사

PAGE_SIZE = 1000


def extract_items(payload: dict) -> list[dict]:
    """
    TourAPI 응답에서 item 목록을 꺼낸다.

    결과가 없으면 items가 빈 문자열로, 1건이면 item이 dict로 온다.
    """

    items = payload.get("response", {}).get("body", {}).get("items")

    if not items:
        return []

    item = items.get("item", [])

    if isinstance(item, dict):
        return [item]

    return item


def call(lang: str, operation: str, params: dict) -> dict:
    """
    TourAPI 한 번 호출하고 응답 코드를 확인한다.
    """

    url = f"{BASE_URL}/{LANGUAGE_SERVICES[lang]}/{operation}"

    payload = get_json(
        url,
        params={
            "serviceKey": get_env("DATA_GO_KR_API_KEY"),
            "MobileOS": "ETC",
            "MobileApp": "NOA",
            "_type": "json",
            **params,
        },
    )

    header = payload.get("response", {}).get("header", {})

    if header.get("resultCode") != "0000":
        raise RuntimeError(
            f"TourAPI 응답 오류: {lang} {operation} {params} {header or payload}"
        )

    return payload


def fetch_all_pages(lang: str, operation: str, params: dict) -> list[dict]:
    """
    목록형 오퍼레이션의 모든 페이지를 원본 그대로 모은다.
    """

    pages: list[dict] = []
    page_no = 1
    fetched = 0

    while True:
        payload = call(
            lang,
            operation,
            {**params, "numOfRows": PAGE_SIZE, "pageNo": page_no},
        )
        pages.append(payload)

        items = extract_items(payload)
        total = int(payload["response"]["body"].get("totalCount", 0))
        fetched += len(items)

        if fetched >= total or not items:
            break

        page_no += 1

    return pages


def collect(languages: list[str] | None = None) -> list[Path]:
    """
    서울의 모든 분류(관광지, 문화시설, 축제, 레포츠, 숙박, 쇼핑, 음식점)
    TourAPI 목록을 언어별로 나눠 원본 그대로 저장한다.

    저장: data/raw/tourapi_places/<수집일>/places_<lang>_<시각>.json.gz
    활용신청이 안 된 언어는 건너뛰고 오류만 출력한다.
    """

    get_env("DATA_GO_KR_API_KEY")

    languages = languages or list(LANGUAGE_SERVICES)
    paths: list[Path] = []
    errors: dict[str, str] = {}

    for lang in languages:
        collected_at = now_kst()

        try:
            pages = fetch_all_pages(
                lang,
                "areaBasedList2",
                {"lDongRegnCd": SEOUL_LDONG_REGN_CD, "arrange": "C"},
            )

        except RuntimeError as error:
            errors[lang] = str(error).splitlines()[0]
            print(f"{lang:5} 실패: {errors[lang]}")
            continue

        count = sum(len(extract_items(page)) for page in pages)

        path = save_raw(
            SOURCE,
            f"places_{lang}",
            {"lang": lang, "service": LANGUAGE_SERVICES[lang], "pages": pages},
            collected_at,
        )
        paths.append(path)

        print(f"{lang:5} {count:>6,} → {path}")

    if not paths:
        raise RuntimeError(f"모든 언어가 실패했습니다: {errors}")

    return paths


def latest_raw_file(lang: str) -> Path:
    files = sorted(
        (RAW_DATA_DIR / SOURCE).glob(f"*/places_{lang}_*.json.gz"),
        key=lambda path: (path.parent.name, path.name),
    )

    if not files:
        raise FileNotFoundError(
            f"{lang} 관광지 목록이 없습니다. 먼저 실행하세요: "
            "python -m noa_data.jobs.collect_tourapi_places"
        )

    return files[-1]

