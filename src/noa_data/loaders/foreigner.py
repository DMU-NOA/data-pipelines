import csv
import io
import re
import zipfile
from datetime import date

import psycopg

from noa_data.loaders.common import pending_files, record_loaded


# 단기체류 외국인 생활인구
# - 행정동 단위 (OA-14993): DB 에 적재한다.
# - 집계구 단위 (OA-14980): 원본만 받아 둔다. 한 달 약 700만 행 이상이라,
#   집계구 경계(SGIS)로 관광지 주변 집계구만 고를 수 있게 되면 적재를 추가한다.


def number(value: str) -> float | None:
    # '*' 는 표본이 적어 가린 값이다. NULL 로 둔다.
    value = value.strip()

    if value in ("", "*"):
        return None

    return float(value)


def open_csv(archive: zipfile.ZipFile, name: str):
    with archive.open(name) as raw:
        data = raw.read()

    try:
        content = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        content = data.decode("cp949")

    return csv.reader(io.StringIO(content))


DONG_COLUMNS = ["base_date", "hour", "adm_code", "total", "chinese", "non_chinese"]

DONG_HEADER = ["기준일ID", "시간대구분", "행정동코드", "총생활인구수", "중국인체류인구수", "중국외외국인체류인구수"]


def load_dong_files(conn: psycopg.Connection) -> int:
    """
    행정동 단위 단기체류 외국인 생활인구 월별 ZIP (OA-14993) → foreigner_population_dong

    파일 하나가 한 달이다. 그 달의 행을 지우고 COPY 로 통째로 넣는다.
    """

    files = pending_files(conn, "seoul_files/OA-14993/TEMP_FOREIGNER_DONG_*.zip")
    total = 0

    for path in files:
        month = re.search(r"_(\d{4})(\d{2})\.zip$", path.name)
        first_day = date(int(month.group(1)), int(month.group(2)), 1)
        count = 0

        with zipfile.ZipFile(path) as archive, conn.transaction():
            conn.execute(
                """
                DELETE FROM foreigner_population_dong
                WHERE base_date >= %s AND base_date < %s::date + interval '1 month'
                """,
                (first_day, first_day),
            )

            with conn.cursor().copy(
                f"COPY foreigner_population_dong ({', '.join(DONG_COLUMNS)}) FROM STDIN"
            ) as copy:
                for name in sorted(archive.namelist()):
                    if not name.lower().endswith(".csv"):
                        continue

                    reader = open_csv(archive, name)
                    header = [column.strip('﻿?"') for column in next(reader)]

                    if header[:6] != DONG_HEADER:
                        raise RuntimeError(f"{path.name}/{name} 헤더가 예상과 다릅니다: {header}")

                    for row in reader:
                        if len(row) < 6:
                            continue

                        copy.write_row((
                            date(int(row[0][:4]), int(row[0][4:6]), int(row[0][6:8])),
                            int(row[1]),
                            row[2],
                            number(row[3]),
                            number(row[4]),
                            number(row[5]),
                        ))
                        count += 1

            record_loaded(conn, path, "foreigner_dong", count)

        total += count
        print(f"  foreigner_population_dong ← {path.name}: {count:,}")

    return total
