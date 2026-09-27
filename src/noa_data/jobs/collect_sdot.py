import argparse
from datetime import datetime

from noa_data.collectors import sdot
from noa_data.collectors.common import RAW_DATA_DIR
from noa_data.jobs.dates import date_range, days_ago


def to_dash(date: str) -> str:
    return datetime.strptime(date, "%Y%m%d").strftime("%Y-%m-%d")


def is_complete(api: str, date: str) -> bool:
    """
    그 날짜가 끝난 뒤에 수집한 파일이 있으면 완료된 날짜로 본다.

    파일 경로: data/raw/<source>/<수집일 YYYYMMDD>/<service>_<YYYY-MM-DD>_*.json.gz
    """

    config = sdot.APIS[api]
    pattern = f"*/{config['service']}_{to_dash(date)}_*.json.gz"

    return any(
        path.parent.name > date
        for path in (RAW_DATA_DIR / config["source"]).glob(pattern)
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="S-DoT 유동인구 측정값 수집 (하루 단위 저장)",
    )
    parser.add_argument(
        "--api",
        choices=list(sdot.APIS),
        default="realtime",
        help="realtime: 최근 약 16일, 10~20분 지연 / recent: 최근 약 한 달, 약 4일 지연",
    )
    parser.add_argument("--start", default=days_ago(1), help="YYYYMMDD (기본값: 어제)")
    parser.add_argument("--end", default=days_ago(0), help="YYYYMMDD (기본값: 오늘)")
    parser.add_argument(
        "--days",
        type=int,
        help="최근 N일 ~ 어제 (지정하면 --start, --end 대신 사용. 정기 실행용)",
    )
    parser.add_argument(
        "--skip-complete",
        action="store_true",
        help="이미 완료된 날짜는 건너뛴다 (정기 실행용. PC가 꺼졌던 날을 다음 실행에서 메운다)",
    )
    args = parser.parse_args()

    if args.days:
        args.start, args.end = days_ago(args.days), days_ago(1)

    for date in date_range(args.start, args.end):
        if args.skip_complete and is_complete(args.api, date):
            continue

        sdot.collect(args.api, to_dash(date))


if __name__ == "__main__":
    main()
