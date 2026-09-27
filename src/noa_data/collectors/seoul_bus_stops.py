from pathlib import Path

from noa_data.collectors.common import get_env, now_kst, save_raw
from noa_data.collectors.seoul_open_api import fetch_all_rows


SOURCE = "seoul_bus_stops"

# 서울시 버스정류소 위치정보: STOPS_NO, STOPS_NM, XCRD(경도), YCRD(위도), NODE_ID, STOPS_TYPE
SERVICE = "busStopLocationXyInfo"


def collect() -> Path:
    get_env("SEOUL_API_KEY")

    collected_at = now_kst()
    rows, total = fetch_all_rows(SERVICE)

    path = save_raw(
        SOURCE,
        "bus_stops",
        {"service": SERVICE, "list_total_count": total, "rows": rows},
        collected_at,
    )

    print(f"버스정류장 {len(rows):,} / {total:,} → {path}")

    return path
