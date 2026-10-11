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
    CSV에서 누락된 매핑만 추가한다.

    운영 DB에는 spot_mapping(area_cd)의 UNIQUE 제약이 없을 수도 있다.
    따라서 ON CONFLICT (area_cd)에 의존하거나 전체 DELETE 하지 않는다.
    기존 매핑이 CSV와 다르면 API 참조/좋아요가 영향을 받을 수 있으므로
    조용히 변경하지 않고 경고로 남긴다.
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

    # 같은 키의 상충 설정이 있으면 부분 동기화하지 않고 중단한다.
    areas = {}
    contents = {}
    for area_cd, content_id in valid:
        if area_cd in areas and areas[area_cd] != content_id:
            raise ValueError(f"CSV 중복 area_cd 매핑 충돌: {area_cd}")
        if content_id in contents and contents[content_id] != area_cd:
            raise ValueError(f"CSV 중복 content_id 매핑 충돌: {content_id}")
        areas[area_cd] = content_id
        contents[content_id] = area_cd

    inserted = 0
    unchanged = 0
    skipped = 0
    with conn.transaction():
        for area_cd, content_id in dict.fromkeys(valid):
            # 실제 backend 스키마에 UNIQUE(area_cd)가 없어도 중복을 만들지 않는다.
            existing = conn.execute(
                """
                SELECT area_cd, content_id
                FROM spot_mapping
                WHERE area_cd = %s OR content_id = %s
                """,
                (area_cd, content_id),
            ).fetchall()
            if existing:
                if len(existing) == 1 and existing[0] == (area_cd, content_id):
                    unchanged += 1
                else:
                    skipped += 1
                    print(f"  spot_mapping 충돌 유지: {area_cd} → {content_id} (기존 매핑 보존)")
                continue

            result = conn.execute(
                """
                INSERT INTO spot_mapping (area_cd, content_id)
                SELECT %s, %s
                WHERE EXISTS (SELECT 1 FROM seoul_spots WHERE area_cd = %s)
                  AND EXISTS (SELECT 1 FROM tour_spots WHERE content_id = %s)
                  AND NOT EXISTS (
                      SELECT 1 FROM spot_mapping
                      WHERE area_cd = %s OR content_id = %s
                  )
                ON CONFLICT DO NOTHING
                """,
                (area_cd, content_id, area_cd, content_id, area_cd, content_id),
            )
            inserted += result.rowcount
            if result.rowcount == 0:
                skipped += 1

    print(
        f"  spot_mapping: 신규 {inserted:,}, 기존 {unchanged:,}, "
        f"건너뜀 {skipped:,} / config {len(valid):,}"
    )
    return inserted


def sync_all(conn: psycopg.Connection) -> int:
    """
    pipeline 테이블 -> 기존 backend 서비스용 테이블 전체 동기화.
    """
    total = 0
    total += sync_seoul_spots(conn)
    total += sync_tour_spots(conn)
    total += sync_mapping(conn)
    return total
