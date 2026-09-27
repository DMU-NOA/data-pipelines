import argparse

from noa_data.collectors import tourapi_places


def main() -> None:
    parser = argparse.ArgumentParser(
        description="TourAPI 서울 장소 목록 전체 분류 수집 (언어별 저장)",
    )
    parser.add_argument(
        "--lang",
        nargs="*",
        choices=list(tourapi_places.LANGUAGE_SERVICES),
        help="언어 (생략하면 한국어, 영어, 일본어, 중국어 간체/번체)",
    )
    args = parser.parse_args()

    tourapi_places.collect(args.lang)


if __name__ == "__main__":
    main()
