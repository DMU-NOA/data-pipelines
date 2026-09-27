import argparse

from noa_data.collectors import kto_bigdata
from noa_data.jobs.collect_seoul_ridership import months, previous_month


# 데이터가 시작되는 달
DEFAULT_SINCE = {"hub": "202405", "related": "202405", "visitor": "202401"}

# 방문자수는 한 달이 다 차기 전에 일부만 공개되므로 최근 몇 달은 다시 받는다.
REFRESH_RECENT_MONTHS = {"hub": 0, "related": 0, "visitor": 3}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="한국관광공사 관광 빅데이터 수집 (월 단위, 이미 받은 달은 건너뜀)",
    )
    parser.add_argument("dataset", choices=list(kto_bigdata.DATASETS))
    parser.add_argument("--since", help="YYYYMM (기본값: 데이터 시작 달)")
    parser.add_argument("--until", default=previous_month(), help="YYYYMM (기본값: 전월)")
    args = parser.parse_args()

    targets = months(args.since or DEFAULT_SINCE[args.dataset], args.until)
    refresh = set(targets[-REFRESH_RECENT_MONTHS[args.dataset]:]) if REFRESH_RECENT_MONTHS[args.dataset] else set()
    collected = kto_bigdata.collected_months(args.dataset)

    for use_month in targets:
        if use_month in collected and use_month not in refresh:
            continue

        kto_bigdata.collect(args.dataset, use_month)


if __name__ == "__main__":
    main()
