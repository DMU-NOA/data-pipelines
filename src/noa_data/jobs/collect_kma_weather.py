import argparse
from datetime import datetime

from noa_data.collectors import kma_weather
from noa_data.jobs.dates import days_ago


def to_date(value: str):
    return datetime.strptime(value, "%Y%m%d").date()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="기상청 ASOS 서울(108) 시간별 관측 수집 (전날까지 제공)",
    )
    parser.add_argument("--start", default=days_ago(7), help="YYYYMMDD (기본값: 7일 전)")
    parser.add_argument("--end", default=days_ago(1), help="YYYYMMDD (기본값: 어제)")
    args = parser.parse_args()

    kma_weather.collect(to_date(args.start), to_date(args.end))


if __name__ == "__main__":
    main()
