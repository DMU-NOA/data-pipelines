import csv
import io
from datetime import datetime

import pandas as pd
import psycopg

from noa_data.collectors.common import KST, load_raw
from noa_data.loaders.common import integer, kst, pending_files, point, record_loaded, text, upsert


OBSERVATION_COLUMNS = [
    "sensor_code", "observed_at", "serial_no", "model_name", "visitor_count",
    "region", "district", "administrative_dong", "registered_at", "source_api", "collected_at",
]

SENSING_TIME_FORMAT = "%Y-%m-%d_%H:%M:%S"

# 서울 열린데이터광장 주간 파일 헤더. 파일에 따라 이름만 조금 다르고 순서와 뜻은 같다.
# (2024~ 141개 파일 조사: 138개는 첫 번째, 2개는 두 번째 형태)
FILE_HEADERS = [
    ["모델번호", "시리얼", "측정시간", "지역", "자치구", "행정동", "방문자수", "등록일"],
    ["모델명", "시리얼", "측정시간", "지역", "자치구", "행정동", "방문자수", "등록 일시"],
]


def sensor_code(serial: str) -> int | None:
    """
    원본 시리얼(00000002993)을 위치정보의 센서코드(2993)로 바꾼다.
    """

    serial = (serial or "").strip()

    return int(serial) if serial.isdigit() else None


def registered_time(value: str | None):
    """
    등록 시각 형식이 소스마다, 파일마다 다르다.
    2026-09-23 23:58:04 / 2026-09-27 13:58:01.0 / 2024-06-03 00:01 / 2024-06-03 0:01
    """

    if not value:
        return None

    value = str(value).split(".")[0].strip()

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return kst(value, fmt)
        except ValueError:
            continue

    return None


def upsert_observations(conn: psycopg.Connection, rows: list[tuple]) -> int:
    # 같은 (센서, 측정시각) 이 다시 등록되면 더 늦게 등록된 값을 쓴다.
    rows = [row for row in rows if row[0] is not None and row[1] is not None]
    rows.sort(key=lambda row: row[8] or kst("2000-01-01 00:00:00", "%Y-%m-%d %H:%M:%S"))

    return upsert(
        conn, "sdot_observation", OBSERVATION_COLUMNS, rows,
        key=["sensor_code", "observed_at"],
        update_where="sdot_observation.registered_at IS NULL "
                     "OR EXCLUDED.registered_at >= sdot_observation.registered_at",
    )


def load_sensors(conn: psycopg.Connection) -> int:
    """
    S-DoT 설치 위치정보 엑셀 (OA-15964) → sdot_sensor

    파일 이름 순서대로 적재하므로 날짜가 붙은 최신 파일(_251113)이 마지막에 반영된다.
    """

    files = pending_files(conn, "seoul_files/OA-15964/*위치정보*.xlsx")
    total = 0

    for path in files:
        sensors = pd.read_excel(path).dropna(subset=["방문자 센서코드"])

        rows = [
            (
                int(row["방문자 센서코드"]),
                text(row.get("시리얼번호")),
                text(row.get("주소")),
                point(row.get("경도"), row.get("위도")),
            )
            for _, row in sensors.iterrows()
        ]

        with conn.transaction():
            count = upsert(
                conn, "sdot_sensor",
                ["sensor_code", "device_serial", "address", "location"],
                rows, key=["sensor_code"],
            )
            conn.execute("UPDATE sdot_sensor SET updated_at = now()")
            record_loaded(conn, path, "sdot_sensor", count)

        total += count
        print(f"  sdot_sensor ← {path.name}: {count}")

    return total


def load_api_observations(conn: psycopg.Connection) -> int:
    """
    S-DoT API 수집 파일 (recent: IotVdata018, realtime: sDoTPeople) → sdot_observation
    """

    files = pending_files(conn, "sdot_*/*/*.json.gz")
    total = 0

    for path in files:
        record = load_raw(path)
        payload = record["payload"]
        service = payload["service"]

        rows = [
            (
                sensor_code(row.get("SERIAL_NO") or row.get("SERIAL")),
                kst(row.get("SENSING_TIME"), SENSING_TIME_FORMAT),
                text(row.get("SERIAL_NO") or row.get("SERIAL")),
                text(row.get("MODEL_NM") or row.get("MODELNAME")),
                integer(row.get("VISITOR_COUNT")),
                text(row.get("REGION")),
                text(row.get("AUTONOMOUS_DISTRICT")),
                text(row.get("ADMINISTRATIVE_DISTRICT")),
                registered_time(row.get("REG_DTTM") or row.get("DATE")),
                service,
                record["collected_at"],
            )
            for row in payload["rows"]
        ]

        with conn.transaction():
            count = upsert_observations(conn, rows)
            record_loaded(conn, path, "sdot_api", count)

        total += count

    print(f"  sdot_observation ← API 파일 {len(files)}개")

    return total


def load_file_observations(conn: psycopg.Connection) -> int:
    """
    S-DoT 주간 파일 (서울 열린데이터광장 OA-15964, CP949 CSV) → sdot_observation
    """

    files = pending_files(conn, "seoul_files/OA-15964/S-DoT_WALK_*.csv")
    total = 0

    for path in files:
        raw = path.read_bytes()

        try:
            content = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            content = raw.decode("cp949")

        reader = csv.reader(io.StringIO(content))
        header = [column.strip() for column in next(reader)]
        first_rows = []

        # 헤더 끝에 줄바꿈이 빠져 첫 행이 붙어 있는 파일이 있다 (2024.05.06-05.12).
        # 예: [..., '방문자수', '등록일"SDOT001"', '00000004014', ...]
        if len(header) > 8 and header[7].startswith("등록일"):
            first_rows = [[header[7][len("등록일"):].strip('"')] + header[8:]]
            header = header[:7] + ["등록일"]

        if header not in FILE_HEADERS:
            raise RuntimeError(f"{path.name} 헤더가 예상과 다릅니다: {header}")

        downloaded_at = datetime.fromtimestamp(path.stat().st_mtime, tz=KST)

        rows = [
            (
                sensor_code(row[1]),
                kst(row[2], SENSING_TIME_FORMAT),
                text(row[1]),
                text(row[0]),
                integer(row[6]),
                text(row[3]),
                text(row[4]),
                text(row[5]),
                registered_time(row[7]),
                "file",
                downloaded_at,
            )
            for row in [*first_rows, *reader]
            if len(row) >= 8
        ]

        with conn.transaction():
            count = upsert_observations(conn, rows)
            record_loaded(conn, path, "sdot_file", count)

        total += count
        print(f"  sdot_observation ← {path.name}: {count:,}")

    return total
