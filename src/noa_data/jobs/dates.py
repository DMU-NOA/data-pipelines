from datetime import datetime, timedelta

from noa_data.collectors.common import now_kst


DATE_FORMAT = "%Y%m%d"


def days_ago(days: int) -> str:
    return (now_kst() - timedelta(days=days)).strftime(DATE_FORMAT)


def date_range(start: str, end: str) -> list[str]:
    """
    start ~ end (둘 다 포함) 날짜 목록을 YYYYMMDD로 반환한다.
    """

    current = datetime.strptime(start, DATE_FORMAT)
    last = datetime.strptime(end, DATE_FORMAT)

    if current > last:
        raise ValueError(f"start({start})가 end({end})보다 늦습니다.")

    dates = []

    while current <= last:
        dates.append(current.strftime(DATE_FORMAT))
        current += timedelta(days=1)

    return dates
