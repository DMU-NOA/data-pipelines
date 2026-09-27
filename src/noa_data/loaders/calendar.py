import psycopg

from noa_data.collectors.common import load_raw
from noa_data.collectors.tourapi_places import extract_items
from noa_data.loaders.common import kst, pending_files, record_loaded, text, upsert


def load_holidays(conn: psycopg.Connection) -> int:
    """
    한국천문연구원 공휴일 (연도별 파일) → holiday

    임시공휴일이 추가되거나 취소될 수 있으므로, 연도 파일을 적재할 때
    그 해의 행을 모두 지우고 새로 넣는다. 파일을 수집 순서대로 적재하므로
    마지막에는 가장 최근 파일의 내용이 남는다.
    """

    files = pending_files(conn, "holidays/*/rest_days_*.json.gz")
    total = 0

    for path in files:
        record = load_raw(path)
        year = int(path.name.split("_")[2])
        items = extract_items(record["payload"])

        rows = [
            (
                kst(item["locdate"], "%Y%m%d").date(),
                text(item.get("dateName")),
                text(item.get("dateKind")),
                item.get("isHoliday") == "Y",
                record["collected_at"],
            )
            for item in items
        ]

        with conn.transaction():
            conn.execute(
                "DELETE FROM holiday WHERE extract(year FROM holiday_date) = %s",
                (year,),
            )
            count = upsert(
                conn,
                "holiday",
                ["holiday_date", "holiday_name", "date_kind", "is_holiday", "collected_at"],
                rows,
                key=["holiday_date", "holiday_name"],
            )
            record_loaded(conn, path, "holidays", count)

        total += count
        print(f"  holiday ← {path.name}: {year}년 {count}일")

    return total
