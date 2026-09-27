import argparse

from noa_data.collectors import tourapi_festivals
from noa_data.collectors.tourapi_places import LANGUAGE_SERVICES


def main() -> None:
    parser = argparse.ArgumentParser(
        description="TourAPI 서울 축제/공연/행사 수집 (행사 기간 포함, 언어별 저장)",
    )
    parser.add_argument("--since", default="20240101", help="행사 시작일 YYYYMMDD (기본값: 20240101)")
    parser.add_argument("--lang", nargs="*", choices=list(LANGUAGE_SERVICES), help="언어 (생략하면 전체)")
    args = parser.parse_args()

    tourapi_festivals.collect(args.since, args.lang)


if __name__ == "__main__":
    main()
