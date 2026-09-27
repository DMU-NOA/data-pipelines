import argparse
from datetime import datetime

from noa_data.collectors import seoul_files


def main() -> None:
    parser = argparse.ArgumentParser(
        description="서울 열린데이터광장 파일 데이터셋 내려받기 (이미 받은 파일은 건너뜀)",
    )
    parser.add_argument("dataset", choices=list(seoul_files.DATASETS))
    parser.add_argument("--since", help="YYYYMMDD. 파일 이름의 날짜가 이 날짜 이후인 파일만")
    parser.add_argument("--dry-run", action="store_true", help="받지 않고 목록과 용량만 출력")
    args = parser.parse_args()

    since = datetime.strptime(args.since, "%Y%m%d").date() if args.since else None
    seoul_files.collect(args.dataset, since, args.dry_run)


if __name__ == "__main__":
    main()
