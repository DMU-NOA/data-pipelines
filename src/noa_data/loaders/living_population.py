import csv
import io
import re
import zipfile
from datetime import date

import psycopg

from noa_data.loaders.common import pending_files, record_loaded


# 월별 파일의 컬럼 순서 (원본 헤더)
# 기준일ID, 시간대구분, 행정동코드, 총생활인구수,
# 남자 0-9, 10-14, ..., 65-69, 70세이상 (14개), 여자 같은 순서 (14개)
AGE_GROUPS = [
    "0_9", "10_14", "15_19", "20_24", "25_29", "30_34", "35_39",
    "40_44", "45_49", "50_54", "55_59", "60_64", "65_69", "70_plus",
]

COLUMNS = [
    "base_date", "hour", "adm_code", "total",
    *(f"male_{age}" for age in AGE_GROUPS),
    *(f"female_{age}" for age in AGE_GROUPS),
]

EXPECTED_HEADER_PREFIX = ["기준일ID", "시간대구분", "행정동코드", "총생활인구수"]


def detect_encoding(archive: zipfile.ZipFile, name: str) -> str:
    """
    월별 파일마다 인코딩이 다르다 (대부분 UTF-8, 202509 는 CP949).
    첫 줄(헤더)을 UTF-8 로 읽어 보고 안 되면 CP949 로 본다.
    """

    with archive.open(name) as raw:
        header = raw.readline()

    try:
        header.decode("utf-8-sig")
        return "utf-8-sig"
    except UnicodeDecodeError:
        return "cp949"


def number(value: str) -> float | None:
    # 원본의 빈 값과 '*' (표본 부족으로 가린 값) 은 NULL 로 둔다.
    value = value.strip()

    if value in ("", "*"):
        return None

    return float(value)


def load_monthly_files(conn: psycopg.Connection) -> int:
    """
    행정동 단위 생활인구 월별 ZIP → living_population

    파일 하나가 한 달이다. 그 달의 행을 지우고 COPY 로 통째로 넣는다.
    (한 달 약 31만 행이라 행 단위 upsert 보다 훨씬 빠르다)
    """

    files = pending_files(conn, "seoul_files/OA-14991/LOCAL_PEOPLE_DONG_*.zip")
    total = 0

    for path in files:
        month = re.search(r"_(\d{4})(\d{2})\.zip$", path.name)
        first_day = date(int(month.group(1)), int(month.group(2)), 1)

        with zipfile.ZipFile(path) as archive:
            name = next(item for item in archive.namelist() if item.lower().endswith(".csv"))

            encoding = detect_encoding(archive, name)

            with archive.open(name) as raw:
                reader = csv.reader(io.TextIOWrapper(raw, encoding=encoding))
                # CP949 파일 맨 앞에 BOM 이 '?' 로 남아 있는 경우가 있다 (202509).
                header = [column.strip('﻿?"') for column in next(reader)]

                if header[:4] != EXPECTED_HEADER_PREFIX:
                    raise RuntimeError(f"{path.name} 헤더가 예상과 다릅니다: {header[:4]}")

                with conn.transaction():
                    conn.execute(
                        """
                        DELETE FROM living_population
                        WHERE base_date >= %s AND base_date < %s::date + interval '1 month'
                        """,
                        (first_day, first_day),
                    )

                    count = 0

                    with conn.cursor().copy(
                        f"COPY living_population ({', '.join(COLUMNS)}) FROM STDIN"
                    ) as copy:
                        for row in reader:
                            if not row:
                                continue

                            copy.write_row((
                                date(int(row[0][:4]), int(row[0][4:6]), int(row[0][6:8])),
                                int(row[1]),
                                row[2],
                                float(row[3]),
                                *(number(value) for value in row[4:32]),
                            ))
                            count += 1

                    record_loaded(conn, path, "living_population", count)

        total += count
        print(f"  living_population ← {path.name}: {count:,}")

    return total
