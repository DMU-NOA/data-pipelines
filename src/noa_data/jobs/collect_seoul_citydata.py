import argparse

from noa_data.collectors import seoul_citydata


def main() -> None:
    parser = argparse.ArgumentParser(
        description="서울 실시간 도시데이터(121장소) 스냅샷 수집",
    )
    parser.add_argument(
        "--area",
        nargs="*",
        help="수집할 AREA_CD (생략하면 121장소 전체). 예: POI009",
    )
    args = parser.parse_args()

    seoul_citydata.collect(args.area)


if __name__ == "__main__":
    main()
