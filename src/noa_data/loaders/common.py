from collections.abc import Iterable, Sequence
from datetime import datetime
from pathlib import Path

import psycopg

from noa_data.collectors.common import KST, RAW_DATA_DIR


# 원본 좌표가 이 범위 밖이면 서울이 아닌 것으로 본다.
SEOUL_LAT = (37.41, 37.72)
SEOUL_LNG = (126.73, 127.27)


def relative_key(path: Path) -> str:
    """
    적재 기록에 남길 파일 키 (data/raw 기준 상대 경로).
    """

    return path.resolve().relative_to(RAW_DATA_DIR.resolve()).as_posix()


def pending_files(conn: psycopg.Connection, pattern: str) -> list[Path]:
    """
    data/raw 아래에서 pattern 에 맞고 아직 적재하지 않은 파일을
    수집 순서(수집일 폴더, 파일 이름)대로 돌려준다.

    나중에 수집한 파일이 먼저 수집한 값을 덮어써야 하므로 순서가 중요하다.
    """

    loaded = {
        row[0]
        for row in conn.execute("SELECT file_path FROM pipeline_load_history")
    }

    files = sorted(
        RAW_DATA_DIR.glob(pattern),
        key=lambda path: (path.parent.name, path.name),
    )

    return [path for path in files if relative_key(path) not in loaded]


def record_loaded(
    conn: psycopg.Connection,
    path: Path,
    source: str,
    row_count: int,
) -> None:
    conn.execute(
        """
        INSERT INTO pipeline_load_history (file_path, source, row_count)
        VALUES (%s, %s, %s)
        ON CONFLICT (file_path) DO UPDATE
        SET row_count = EXCLUDED.row_count, loaded_at = now()
        """,
        (relative_key(path), source, row_count),
    )


def upsert(
    conn: psycopg.Connection,
    table: str,
    columns: Sequence[str],
    rows: Iterable[Sequence],
    key: Sequence[str],
    update: bool = True,
    update_where: str | None = None,
) -> int:
    """
    rows 를 임시 테이블에 COPY 로 넣은 뒤 table 에 INSERT ... ON CONFLICT 한다.

    update=True 면 키가 같은 행을 새 값으로 바꾸고, False 면 기존 행을 유지한다.
    update_where 로 바꿀 조건을 줄 수 있다 (예: 더 늦게 등록된 값만).
    rows 안에 키가 같은 행이 있으면 마지막 행만 남긴다.
    """

    key_index = [columns.index(column) for column in key]
    unique: dict[tuple, Sequence] = {}

    for row in rows:
        unique[tuple(row[index] for index in key_index)] = row

    if not unique:
        return 0

    column_list = ", ".join(columns)
    temp = f"tmp_{table}"

    conn.execute(
        f"CREATE TEMP TABLE {temp} (LIKE {table} INCLUDING DEFAULTS) ON COMMIT DROP"
    )

    with conn.cursor().copy(f"COPY {temp} ({column_list}) FROM STDIN") as copy:
        for row in unique.values():
            copy.write_row(row)

    if update:
        assignments = ", ".join(
            f"{column} = EXCLUDED.{column}"
            for column in columns
            if column not in key
        )
        conflict = f"DO UPDATE SET {assignments}"

        if update_where:
            conflict += f" WHERE {update_where}"
    else:
        conflict = "DO NOTHING"

    conn.execute(
        f"""
        INSERT INTO {table} ({column_list})
        SELECT {column_list} FROM {temp}
        ON CONFLICT ({", ".join(key)}) {conflict}
        """
    )

    conn.execute(f"DROP TABLE {temp}")

    return len(unique)


def point(lng: float | str | None, lat: float | str | None) -> str | None:
    """
    경도, 위도를 PostGIS geography 입력 형식(EWKT)으로 바꾼다.
    """

    if lng in (None, "") or lat in (None, ""):
        return None

    return f"SRID=4326;POINT({float(lng)} {float(lat)})"


def in_seoul(lng: float | str | None, lat: float | str | None) -> bool:
    try:
        lng, lat = float(lng), float(lat)
    except (TypeError, ValueError):
        return False

    return SEOUL_LAT[0] <= lat <= SEOUL_LAT[1] and SEOUL_LNG[0] <= lng <= SEOUL_LNG[1]


def kst(value: str | int | None, fmt: str) -> datetime | None:
    """
    원본의 한국 시간 문자열을 timezone 이 있는 datetime 으로 바꾼다.
    """

    if value is None:
        return None

    value = str(value).strip()  # 원본 끝에 공백이 붙은 경우가 있다 (S-DoT 주간 파일)

    if not value:
        return None

    return datetime.strptime(value, fmt).replace(tzinfo=KST)


def text(value) -> str | None:
    """
    빈 문자열은 NULL 로 바꾼다. (원본 API 가 값이 없을 때 "" 를 준다)
    """

    if value is None:
        return None

    value = str(value).strip()

    return value or None


def number(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def integer(value) -> int | None:
    number_value = number(value)

    return None if number_value is None else int(number_value)
