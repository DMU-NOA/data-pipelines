from pathlib import Path

from noa_data.collectors.common import RAW_DATA_DIR, get_env, now_kst, save_raw
from noa_data.collectors.seoul_open_api import fetch_all_rows


# 서울 열린데이터광장 월 단위 시간대별 승하차 (다음 달 초에 전월이 공개된다)
DATASETS = {
    "subway": {
        "service": "CardSubwayTime",
        "source": "seoul_subway_hourly",
        "name": "지하철 호선별 역별 시간대별 승하차",
    },
    "bus": {
        "service": "CardBusTimeNew",
        "source": "seoul_bus_hourly",
        "name": "버스 노선별 정류장별 시간대별 승하차",
    },
}


def is_collected(dataset: str, use_month: str) -> bool:
    source = DATASETS[dataset]["source"]

    return any((RAW_DATA_DIR / source).glob(f"*/{dataset}_{use_month}_*.json.gz"))


def collect(dataset: str, use_month: str) -> Path | None:
    """
    한 달치 시간대별 승하차를 원본 그대로 저장한다.

    use_month: YYYYMM
    """

    get_env("SEOUL_API_KEY")

    config = DATASETS[dataset]
    collected_at = now_kst()
    rows, total = fetch_all_rows(config["service"], use_month)

    if not rows:
        print(f"{config['name']} {use_month}: 아직 공개되지 않음")
        return None

    path = save_raw(
        config["source"],
        f"{dataset}_{use_month}",
        {"use_month": use_month, "list_total_count": total, "rows": rows},
        collected_at,
    )

    print(f"{config['name']} {use_month}: {len(rows):,} / {total:,} → {path}")

    return path
