import argparse
from datetime import date

from noa_data.collectors import seoul_ridership
from noa_data.collectors.common import now_kst


def months(since: str, until: str) -> list[str]:
    year, month = int(since[:4]), int(since[4:])
    result = []

    while f"{year:04d}{month:02d}" <= until:
        result.append(f"{year:04d}{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)

    return result


def previous_month() -> str:
    today = now_kst().date()
    first = date(today.year, today.month, 1)
    return (date(first.year - 1, 12, 1) if first.month == 1 else date(first.year, first.month - 1, 1)).strftime("%Y%m")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="지하철/버스 시간대별 승하차 수집 (월 단위, 이미 받은 달은 건너뜀)",
    )
    parser.add_argument("dataset", choices=list(seoul_ridership.DATASETS))
    parser.add_argument("--since", default="202401", help="YYYYMM (기본값: 202401)")
    parser.add_argument("--until", default=previous_month(), help="YYYYMM (기본값: 전월)")
    args = parser.parse_args()

    for use_month in months(args.since, args.until):
        if seoul_ridership.is_collected(args.dataset, use_month):
            continue

        seoul_ridership.collect(args.dataset, use_month)


if __name__ == "__main__":
    main()
