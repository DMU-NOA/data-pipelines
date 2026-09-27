import argparse

from noa_data.collectors import holidays
from noa_data.collectors.common import now_kst


def main() -> None:
    this_year = now_kst().year

    parser = argparse.ArgumentParser(description="한국천문연구원 공휴일 정보 수집")
    parser.add_argument(
        "--years",
        nargs="*",
        type=int,
        default=[this_year, this_year + 1],
        help="연도 (기본값: 올해, 내년)",
    )
    args = parser.parse_args()

    for year in args.years:
        holidays.collect(year)


if __name__ == "__main__":
    main()
