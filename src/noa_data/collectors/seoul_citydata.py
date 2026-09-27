from pathlib import Path

import pandas as pd

from noa_data.collectors.common import (
    RAW_DATA_DIR,
    get_env,
    now_kst,
    save_raw,
)
from noa_data.collectors.seoul_open_api import fetch_page


SOURCE = "seoul_citydata"

# 서울 열린데이터광장 OA-21285 에서 내려받은 파일
# python -m noa_data.jobs.collect_seoul_files citydata_area
PLACE_LIST_FILE = RAW_DATA_DIR / "seoul_files" / "OA-21285" / "서울시 주요 121장소 목록.xlsx"


def load_area_codes() -> list[str]:
    """
    서울시 주요 121장소의 AREA_CD 목록을 읽는다.
    """

    places = pd.read_excel(PLACE_LIST_FILE)

    return places["AREA_CD"].dropna().astype(str).tolist()


def fetch_place(area_cd: str) -> dict:
    """
    한 장소의 실시간 도시데이터를 조회한다.

    citydata는 장소 1곳당 1건만 반환한다.
    응답에는 실시간 인구, 12시간 인구 예측, 지하철/버스 승하차,
    주차, 날씨, 행사, 상권 결제 정보가 함께 들어 있다.
    """

    payload = fetch_page("citydata", 1, 5, area_cd)

    result = payload.get("RESULT", {})
    code = result.get("RESULT.CODE") or result.get("CODE")

    if "CITYDATA" not in payload:
        raise RuntimeError(
            f"citydata 응답 오류: {area_cd} {code} "
            f"{result.get('RESULT.MESSAGE') or result.get('MESSAGE')}"
        )

    # sample 키는 요청한 장소와 관계없이 고정된 장소를 돌려준다.
    returned_area_cd = payload["CITYDATA"].get("AREA_CD")

    if returned_area_cd != area_cd:
        raise RuntimeError(
            f"요청한 장소({area_cd})와 응답 장소({returned_area_cd})가 다릅니다."
        )

    return payload


def collect(area_codes: list[str] | None = None) -> Path:
    """
    모든 장소의 실시간 도시데이터를 조회해서 원본 그대로 저장한다.

    한 장소가 실패해도 나머지 장소는 계속 수집하고,
    실패한 장소는 errors에 기록한다.
    """

    # 키가 없으면 121번 실패하기 전에 바로 알린다.
    get_env("SEOUL_API_KEY")

    collected_at = now_kst()
    area_codes = area_codes or load_area_codes()

    places: dict[str, dict] = {}
    errors: dict[str, str] = {}

    for index, area_cd in enumerate(area_codes, start=1):
        try:
            places[area_cd] = fetch_place(area_cd)
            status = "ok"

        except RuntimeError as error:
            errors[area_cd] = str(error)
            status = "error"

        print(f"[{index:>3}/{len(area_codes)}] {area_cd} {status}")

    if not places:
        raise RuntimeError(
            f"모든 요청이 실패해서 저장하지 않습니다. 첫 오류: {next(iter(errors.values()))}"
        )

    path = save_raw(
        SOURCE,
        "citydata",
        {"places": places, "errors": errors},
        collected_at,
    )

    print(
        f"\n성공 {len(places)} / 실패 {len(errors)} → {path}"
    )

    return path
