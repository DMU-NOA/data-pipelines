import argparse
from datetime import date, timedelta

from noa_data.collectors.common import now_kst

from noa_data.collectors import tourapi_festivals
from noa_data.collectors.tourapi_places import LANGUAGE_SERVICES


def rolling_since(today: date | None = None) -> str:
    """Keep long-running festivals discoverable; the feed is checked daily."""
    today = today or now_kst().date()
    return (today - timedelta(days=365)).strftime("%Y%m%d")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="TourAPI 서울 축제/공연/행사 수집 (행사 기간 포함, 언어별 저장)",
    )
    parser.add_argument(
        "--since", default=None,
        help="행사 검색 시작일 YYYYMMDD (기본값: 서울 기준 오늘로부터 365일 전)",
    )
    parser.add_argument("--lang", nargs="*", choices=list(LANGUAGE_SERVICES), help="언어 (생략하면 전체)")
    args = parser.parse_args()

    since = args.since or rolling_since()
    print(f"축제 검색 시작일: {since} (종료·예정 여부는 상세 API에서 날짜 검증)")
    tourapi_festivals.collect(since, args.lang)


if __name__ == "__main__":
    main()
