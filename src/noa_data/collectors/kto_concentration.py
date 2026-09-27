from pathlib import Path

from noa_data.collectors.common import get_env, get_json, now_kst, save_raw


SOURCE = "kto_concentration"

# 한국관광공사_관광지 집중률 방문자 추이 예측 정보
# 관광지별 향후 30일 일별 집중률(0~100) 예측
URL = "https://apis.data.go.kr/B551011/TatsCnctrRateService/tatsCnctrRatedList"

SEOUL_AREA_CD = "11"

# 법정동 기준 서울 25개 자치구 코드
SEOUL_SIGNGU_CODES = {
    "11110": "종로구",
    "11140": "중구",
    "11170": "용산구",
    "11200": "성동구",
    "11215": "광진구",
    "11230": "동대문구",
    "11260": "중랑구",
    "11290": "성북구",
    "11305": "강북구",
    "11320": "도봉구",
    "11350": "노원구",
    "11380": "은평구",
    "11410": "서대문구",
    "11440": "마포구",
    "11470": "양천구",
    "11500": "강서구",
    "11530": "구로구",
    "11545": "금천구",
    "11560": "영등포구",
    "11590": "동작구",
    "11620": "관악구",
    "11650": "서초구",
    "11680": "강남구",
    "11710": "송파구",
    "11740": "강동구",
}


def fetch_signgu(signgu_cd: str) -> dict:
    """
    자치구 하나의 관광지 집중률 예측 전체를 조회한다.
    """

    params = {
        "serviceKey": get_env("DATA_GO_KR_API_KEY"),
        "MobileOS": "ETC",
        "MobileApp": "NOA",
        "_type": "json",
        "areaCd": SEOUL_AREA_CD,
        "signguCd": signgu_cd,
        "numOfRows": 9999,
        "pageNo": 1,
    }

    payload = get_json(URL, params=params)

    header = payload.get("response", {}).get("header", {})

    if header.get("resultCode") not in ("0000", "00"):
        raise RuntimeError(
            f"집중률 응답 오류: {signgu_cd} {header or payload}"
        )

    return payload


def collect() -> Path:
    """
    서울 25개 자치구의 관광지 집중률 예측을 원본 그대로 저장한다.

    예측값은 매일 갱신되므로 하루 1회 수집하면 된다.
    """

    # 키가 없으면 25번 실패하기 전에 바로 알린다.
    get_env("DATA_GO_KR_API_KEY")

    collected_at = now_kst()

    signgu: dict[str, dict] = {}
    errors: dict[str, str] = {}

    for signgu_cd, name in SEOUL_SIGNGU_CODES.items():
        try:
            signgu[signgu_cd] = fetch_signgu(signgu_cd)
            status = "ok"

        except RuntimeError as error:
            errors[signgu_cd] = str(error)
            status = "error"

        print(f"{signgu_cd} {name} {status}")

    if not signgu:
        raise RuntimeError(
            f"모든 요청이 실패해서 저장하지 않습니다. 첫 오류: {next(iter(errors.values()))}"
        )

    path = save_raw(
        SOURCE,
        "concentration",
        {"signgu": signgu, "errors": errors},
        collected_at,
    )

    print(f"\n성공 {len(signgu)} / 실패 {len(errors)} → {path}")

    return path
