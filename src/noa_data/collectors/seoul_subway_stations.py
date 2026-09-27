from pathlib import Path

from noa_data.collectors.common import get_env, now_kst, save_raw
from noa_data.collectors.seoul_open_api import fetch_all_rows


SOURCE = "seoul_subway_stations"

# 서울시 역사마스터 정보: 역 코드, 역 이름, 호선, 위도(LAT), 경도(LOT)
# 지하철 승하차 데이터를 관광지 좌표와 연결하는 데 쓴다.
SERVICE = "subwayStationMaster"


def collect() -> Path:
    get_env("SEOUL_API_KEY")

    collected_at = now_kst()
    rows, total = fetch_all_rows(SERVICE)

    path = save_raw(
        SOURCE,
        "stations",
        {"service": SERVICE, "list_total_count": total, "rows": rows},
        collected_at,
    )

    print(f"역 {len(rows):,} / {total:,} → {path}")

    return path
