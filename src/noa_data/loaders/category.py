import csv
from pathlib import Path

import psycopg

from noa_data.collectors.common import PROJECT_ROOT


CONFIG_DIR = PROJECT_ROOT / "config"

CATEGORY_FILE = CONFIG_DIR / "noa_category.csv"
RULE_FILE = CONFIG_DIR / "noa_category_rules.csv"
OVERRIDE_FILE = CONFIG_DIR / "noa_category_overrides.csv"


def read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as file:
        return [
            {key: (value or "").strip() for key, value in row.items()}
            for row in csv.DictReader(file)
        ]


def sync_and_assign(conn: psycopg.Connection) -> int:
    """
    config/*.csv 의 카테고리, 규칙, 수동 지정을 DB 에 그대로 반영하고
    tour_place 전체의 noa_category 를 다시 계산한다.

    CSV 가 원본이다. DB 에서 직접 바꾼 값은 다음 적재 때 CSV 내용으로 되돌아간다.
    그래서 새 DB 에 처음부터 적재해도 항상 같은 결과가 나온다.
    """

    categories = read_csv(CATEGORY_FILE)
    rules = read_csv(RULE_FILE)
    overrides = read_csv(OVERRIDE_FILE)

    codes = {row["code"] for row in categories}

    for row in rules + overrides:
        if row["noa_category"] not in codes:
            raise ValueError(f"config 에 없는 카테고리: {row}")

    with conn.transaction():
        # 1. 카테고리 (추가, 수정)
        for row in categories:
            conn.execute(
                """
                INSERT INTO noa_category (code, name, environment, sort_order)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (code) DO UPDATE
                SET name = EXCLUDED.name,
                    environment = EXCLUDED.environment,
                    sort_order = EXCLUDED.sort_order
                """,
                (row["code"], row["name"], row["environment"], int(row["sort_order"])),
            )

        # 2. 규칙 (통째로 교체)
        conn.execute("DELETE FROM noa_category_rule")

        for row in rules:
            conn.execute(
                "INSERT INTO noa_category_rule (lcls_prefix, noa_category, note) VALUES (%s, %s, %s)",
                (row["lcls_prefix"], row["noa_category"], row["note"] or None),
            )

        # 3. 수동 지정 (통째로 교체)
        conn.execute(
            "UPDATE tour_place SET noa_category_manual = NULL WHERE noa_category_manual IS NOT NULL"
        )

        missing = []

        for row in overrides:
            result = conn.execute(
                """
                UPDATE tour_place SET noa_category_manual = %s
                WHERE lang = %s AND content_id = %s
                """,
                (row["noa_category"], row["lang"], row["content_id"]),
            )

            if result.rowcount == 0:
                missing.append(f"{row['lang']}/{row['content_id']}")

        # 4. 카테고리 다시 계산: 수동 지정 > 가장 긴 규칙 > 없음
        changed = conn.execute(
            """
            WITH target AS (
                SELECT
                    place.lang,
                    place.content_id,
                    COALESCE(
                        place.noa_category_manual,
                        (
                            SELECT rule.noa_category
                            FROM noa_category_rule AS rule
                            WHERE place.lcls_systm3 LIKE rule.lcls_prefix || '%'
                            ORDER BY length(rule.lcls_prefix) DESC
                            LIMIT 1
                        )
                    ) AS noa_category
                FROM tour_place AS place
            )
            UPDATE tour_place AS place
            SET noa_category = target.noa_category
            FROM target
            WHERE place.lang = target.lang
              AND place.content_id = target.content_id
              AND place.noa_category IS DISTINCT FROM target.noa_category
            """
        ).rowcount

        # 5. CSV 에서 빠진 카테고리 삭제 (이제 아무도 참조하지 않는다)
        conn.execute(
            "DELETE FROM noa_category WHERE NOT (code = ANY(%s))",
            (sorted(codes),),
        )

    print(
        f"  noa_category: 카테고리 {len(categories)}, 규칙 {len(rules)}, "
        f"수동 지정 {len(overrides) - len(missing)} → {changed}곳 변경"
    )

    if missing:
        print(f"  ! 수동 지정했지만 DB 에 없는 장소: {', '.join(missing)}")

    return changed
