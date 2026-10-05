import csv
from pathlib import Path

import psycopg

from noa_data.collectors.common import PROJECT_ROOT


MAPPING_FILE = PROJECT_ROOT / "config" / "citydata_tour_mapping.csv"

CATEGORY_EN = {
    "관광특구": "Tourist Zone",
    "고궁·문화유산": "Palace & Heritage",
    "인구밀집지역": "Populated Area",
    "발달상권": "Commercial District",
    "공원": "Park",
    "골목상권": "Alley District",
    "전통시장": "Traditional Market",
    "산·자연": "Mountain & Nature",
}


def sync_seoul_spots(conn: psycopg.Connection) -> int:
    """
    pipeline의 citydata_area를 현재 noa-backend가 읽는 seoul_spots로 동기화한다.
    """
    with conn.transaction():
        result = conn.execute(
            """
            INSERT INTO seoul_spots (
                area_cd,
                name,
                category,
                name_en,
                category_en
            )
            SELECT
                area_cd,
                area_nm,
                category,
                eng_nm,
                CASE category
                    WHEN '관광특구' THEN 'Tourist Zone'
                    WHEN '고궁·문화유산' THEN 'Palace & Heritage'
                    WHEN '인구밀집지역' THEN 'Populated Area'
                    WHEN '발달상권' THEN 'Commercial District'
                    WHEN '공원' THEN 'Park'
                    WHEN '골목상권' THEN 'Alley District'
                    WHEN '전통시장' THEN 'Traditional Market'
                    WHEN '산·자연' THEN 'Mountain & Nature'
                    ELSE category
                END
            FROM citydata_area
            ON CONFLICT (area_cd) DO UPDATE
            SET
                name = EXCLUDED.name,
                category = EXCLUDED.category,
                name_en = EXCLUDED.name_en,
                category_en = EXCLUDED.category_en
            """
        )

    print(f"  seoul_spots: {result.rowcount:,}")
    return result.rowcount


def sync_tour_spots(conn: psycopg.Connection) -> int:
    """
    pipeline의 한국어 TourAPI 장소/상세정보를 noa-backend용 tour_spots로 동기화한다.

    data-pipelines의 tour_place가 원본이며 tour_spots는 서비스 호환용 read model이다.
    """
    with conn.transaction():
        result = conn.execute(
            """
            INSERT INTO tour_spots (
                content_id,
                name,
                content_type_id,
                category,
                image_url,
                image_url2,
                description,
                address,
                mapx,
                mapy,
                event_start_date,
                event_end_date,
                updated_at
            )
            SELECT
                p.content_id,
                p.title,
                p.content_type_id,
                COALESCE(c.name, p.noa_category),
                p.first_image,
                p.first_image2,
                d.overview,
                CONCAT_WS(' ', p.addr1, p.addr2),
                ST_X(p.location::geometry),
                ST_Y(p.location::geometry),
                f.event_start_date,
                f.event_end_date,
                CURRENT_TIMESTAMP
            FROM tour_place p
            LEFT JOIN noa_category c
                ON p.noa_category = c.code
            LEFT JOIN tour_place_detail d
                ON d.lang = p.lang
               AND d.content_id = p.content_id
            LEFT JOIN tour_festival f
                ON f.lang = p.lang
               AND f.content_id = p.content_id
            WHERE
                p.lang = 'ko'
                AND p.location_valid
                AND p.noa_category IS NOT NULL
            ON CONFLICT (content_id) DO UPDATE
            SET
                name = EXCLUDED.name,
                content_type_id = EXCLUDED.content_type_id,
                category = EXCLUDED.category,
                image_url = COALESCE(EXCLUDED.image_url, tour_spots.image_url),
                image_url2 = COALESCE(EXCLUDED.image_url2, tour_spots.image_url2),
                description = COALESCE(EXCLUDED.description, tour_spots.description),
                address = COALESCE(EXCLUDED.address, tour_spots.address),
                mapx = EXCLUDED.mapx,
                mapy = EXCLUDED.mapy,
                event_start_date = EXCLUDED.event_start_date,
                event_end_date = EXCLUDED.event_end_date,
                updated_at = CURRENT_TIMESTAMP
            """
        )

    print(f"  tour_spots: {result.rowcount:,}")
    return result.rowcount


def sync_mapping(conn: psycopg.Connection) -> int:
    """
    config/citydata_tour_mapping.csv를 spot_mapping에 반영한다.

    CSV를 단일 원본으로 사용한다. DB에 직접 넣은 임시 매핑은 다음 동기화 때 제거된다.
    """
    if not MAPPING_FILE.exists():
        raise FileNotFoundError(f"매핑 설정 파일이 없습니다: {MAPPING_FILE}")

    with MAPPING_FILE.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))

    valid = []

    for row in rows:
        area_cd = (row.get("area_cd") or "").strip()
        content_id = (row.get("content_id") or "").strip()

        if area_cd and content_id:
            valid.append((area_cd, content_id))

    with conn.transaction():
        conn.execute("DELETE FROM spot_mapping")

        count = 0

        for area_cd, content_id in valid:
            result = conn.execute(
                """
                INSERT INTO spot_mapping (area_cd, content_id)
                SELECT %s, %s
                WHERE EXISTS (
                    SELECT 1 FROM seoul_spots WHERE area_cd = %s
                )
                AND EXISTS (
                    SELECT 1 FROM tour_spots WHERE content_id = %s
                )
                ON CONFLICT DO NOTHING
                """,
                (area_cd, content_id, area_cd, content_id),
            )
            count += result.rowcount

    print(f"  spot_mapping: {count:,} / config {len(valid):,}")
    return count


def sync_all(conn: psycopg.Connection) -> int:
    """
    pipeline 테이블 -> 기존 backend 서비스용 테이블 전체 동기화.
    """
    total = 0
    total += sync_seoul_spots(conn)
    total += sync_tour_spots(conn)
    total += sync_mapping(conn)
    return total
