import argparse

from noa_data.collectors import tourapi_details
from noa_data.collectors.tourapi_places import LANGUAGE_SERVICES


def main() -> None:
    parser = argparse.ArgumentParser(
        description="TourAPI 상세정보(개요, 운영시간, 휴무일) 수집. 이미 받은 곳은 건너뛴다.",
    )
    parser.add_argument("--lang", default="ko", choices=list(LANGUAGE_SERVICES))
    parser.add_argument(
        "--max",
        type=int,
        default=tourapi_details.DEFAULT_MAX_PLACES,
        help="이번 실행에서 받을 최대 장소 수 (하루 호출 한도 고려)",
    )
    args = parser.parse_args()

    tourapi_details.collect(args.lang, args.max)


if __name__ == "__main__":
    main()
