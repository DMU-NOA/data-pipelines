import argparse

from noa_data.collectors import admdong_boundary


def main() -> None:
    parser = argparse.ArgumentParser(description="행정동 경계 GeoJSON 내려받기 (vuski/admdongkor)")
    parser.add_argument("--version", help="예: ver20260701 (생략하면 최신)")
    args = parser.parse_args()

    admdong_boundary.collect(args.version)


if __name__ == "__main__":
    main()
