from datetime import date, timedelta
from pathlib import Path

from noa_data.collectors.common import get_env, get_json, now_kst, save_raw


SOURCE = "kma_asos_hourly"

# 기상청_지상(종관, ASOS) 시간자료 조회서비스
URL = "https://apis.data.go.kr/1360000/AsosHourlyInfoService/getWthrDataList"

# 108 = 서울 관측소
SEOUL_STATION_ID = "108"

# 한 번에 최대 999행. 40일(960시간)씩 나눠 받는다.
CHUNK_DAYS = 40


def fetch(start: date, end: date) -> dict:
    params = {
        "serviceKey": get_env("DATA_GO_KR_API_KEY"),
        "pageNo": 1,
        "numOfRows": 999,
        "dataType": "JSON",
        "dataCd": "ASOS",
        "dateCd": "HR",
        "startDt": start.strftime("%Y%m%d"),
        "startHh": "00",
        "endDt": end.strftime("%Y%m%d"),
        "endHh": "23",
        "stnIds": SEOUL_STATION_ID,
    }

    payload = get_json(URL, params=params, timeout=60)

    header = payload.get("response", {}).get("header", {})

    if header.get("resultCode") != "00":
        raise RuntimeError(f"ASOS 응답 오류: {start}~{end} {header or payload}")

    return payload


def collect(start: date, end: date) -> list[Path]:
    """
    start ~ end (둘 다 포함) 서울 관측소 시간별 관측값을 원본 그대로 저장한다.

    ASOS 시간자료는 전날까지만 제공된다.
    실시간 날씨와 예보는 seoul_citydata 에도 들어 있지만,
    과거 날씨의 영향을 배우는 데는 이 관측 자료를 쓴다.
    """

    get_env("DATA_GO_KR_API_KEY")

    paths: list[Path] = []
    chunk_start = start

    while chunk_start <= end:
        chunk_end = min(chunk_start + timedelta(days=CHUNK_DAYS - 1), end)
        collected_at = now_kst()

        payload = fetch(chunk_start, chunk_end)
        count = int(payload["response"]["body"].get("totalCount", 0))

        path = save_raw(
            SOURCE,
            f"asos_{chunk_start:%Y%m%d}_{chunk_end:%Y%m%d}",
            payload,
            collected_at,
        )
        paths.append(path)

        print(f"{chunk_start} ~ {chunk_end}: {count}시간 → {path}")

        chunk_start = chunk_end + timedelta(days=1)

    return paths
