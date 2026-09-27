from datetime import datetime

import psycopg

from noa_data.collectors.common import load_raw
from noa_data.collectors.tourapi_places import extract_items
from noa_data.loaders.common import number, pending_files, record_loaded, text, upsert


COLUMNS = [
    "collected_date", "signgu_cd", "t_ats_nm", "base_ymd",
    "area_cd", "area_nm", "signgu_nm", "cnctr_rate",
]


def load_concentration(conn: psycopg.Connection) -> int:
    """
    한국관광공사 관광지 집중률 (하루 1회 수집) → kto_concentration

    수집일을 키에 넣어, 같은 날짜에 대한 예측이 날마다 어떻게 바뀌는지 남긴다.
    같은 날 여러 번 수집하면 마지막 값으로 덮어쓴다.
    """

    files = pending_files(conn, "kto_concentration/*/concentration_*.json.gz")
    total = 0

    for path in files:
        record = load_raw(path)
        collected_date = datetime.fromisoformat(record["collected_at"]).date()

        rows = [
            (
                collected_date,
                text(item.get("signguCd")),
                text(item.get("tAtsNm")),
                datetime.strptime(str(item["baseYmd"]), "%Y%m%d").date(),
                text(item.get("areaCd")),
                text(item.get("areaNm")),
                text(item.get("signguNm")),
                number(item.get("cnctrRate")),
            )
            for payload in record["payload"]["signgu"].values()
            for item in extract_items(payload)
        ]

        with conn.transaction():
            count = upsert(
                conn, "kto_concentration", COLUMNS, rows,
                key=["collected_date", "signgu_cd", "t_ats_nm", "base_ymd"],
            )
            record_loaded(conn, path, "kto_concentration", count)

        total += count
        print(f"  kto_concentration ← {path.parent.name}/{path.name}: {count}")

    return total
