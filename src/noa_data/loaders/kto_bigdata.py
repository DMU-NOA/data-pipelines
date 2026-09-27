from datetime import date

import psycopg

from noa_data.collectors.common import load_raw
from noa_data.collectors.tourapi_places import extract_items
from noa_data.loaders.common import integer, number, pending_files, point, record_loaded, text, upsert


# 한국관광공사 중심 관광지를 TourAPI 관광지에 좌표로 연결할 때의 최대 거리
HUB_MATCH_RADIUS_M = 300


def month_start(base_ym: str) -> date:
    return date(int(base_ym[:4]), int(base_ym[4:6]), 1)


def signgu_items(payload: dict):
    """
    수집 파일의 {구 코드: [페이지...]} 에서 item 을 꺼낸다.
    """

    for pages in payload["pages"].values():
        for page in pages:
            yield from extract_items(page)


def load_hub(conn: psycopg.Connection) -> int:
    """
    기초지자체 중심 관광지 (월) → kto_hub_place
    """

    files = pending_files(conn, "kto_hub_place/*/hub_*.json.gz")
    total = 0

    for path in files:
        payload = load_raw(path)["payload"]

        rows = [
            (
                month_start(item["baseYm"]),
                item["signguCd"],
                item["hubTatsCd"],
                text(item["hubTatsNm"]),
                text(item.get("hubCtgryLclsNm")),
                text(item.get("hubCtgryMclsNm")),
                integer(item["hubRank"]),
                point(item.get("mapX"), item.get("mapY")),
            )
            for item in signgu_items(payload)
        ]

        with conn.transaction():
            count = upsert(
                conn, "kto_hub_place",
                ["base_ym", "signgu_cd", "hub_tats_cd", "hub_tats_nm", "lcls_nm", "mcls_nm", "hub_rank", "location"],
                rows, key=["base_ym", "signgu_cd", "hub_tats_cd"],
            )
            record_loaded(conn, path, "kto_hub_place", count)

        total += count

    print(f"  kto_hub_place ← 파일 {len(files)}개")

    return total


def load_related(conn: psycopg.Connection) -> int:
    """
    관광지별 연관 관광지 (월) → kto_related_place
    """

    files = pending_files(conn, "kto_related_place/*/related_*.json.gz")
    total = 0

    for path in files:
        payload = load_raw(path)["payload"]

        rows = [
            (
                month_start(item["baseYm"]),
                item["signguCd"],
                item["tAtsCd"],
                text(item["tAtsNm"]),
                item["rlteTatsCd"],
                text(item["rlteTatsNm"]),
                text(item.get("rlteSignguCd")),
                text(item.get("rlteCtgryLclsNm")),
                text(item.get("rlteCtgryMclsNm")),
                text(item.get("rlteCtgrySclsNm")),
                integer(item["rlteRank"]),
            )
            for item in signgu_items(payload)
        ]

        with conn.transaction():
            count = upsert(
                conn, "kto_related_place",
                ["base_ym", "signgu_cd", "tats_cd", "tats_nm", "rlte_tats_cd", "rlte_tats_nm",
                 "rlte_signgu_cd", "rlte_lcls_nm", "rlte_mcls_nm", "rlte_scls_nm", "rlte_rank"],
                rows, key=["base_ym", "tats_cd", "rlte_tats_cd"],
            )
            record_loaded(conn, path, "kto_related_place", count)

        total += count

    print(f"  kto_related_place ← 파일 {len(files)}개")

    return total


def load_visitor(conn: psycopg.Connection) -> int:
    """
    기초지자체 일별 방문자수 (월, 전국) → kto_region_visitor (서울만)

    최근 달은 다시 받으므로 나중에 받은 값으로 덮어쓴다.
    """

    files = pending_files(conn, "kto_region_visitor/*/visitor_*.json.gz")
    total = 0

    for path in files:
        payload = load_raw(path)["payload"]

        rows = [
            (
                date(int(item["baseYmd"][:4]), int(item["baseYmd"][4:6]), int(item["baseYmd"][6:8])),
                item["signguCode"],
                text(item.get("signguNm")),
                item["touDivCd"],
                text(item.get("touDivNm")),
                text(item.get("daywkDivCd")),
                number(item.get("touNum")),
            )
            for item in signgu_items(payload)
            if str(item.get("signguCode", "")).startswith("11")
        ]

        with conn.transaction():
            count = upsert(
                conn, "kto_region_visitor",
                ["base_date", "signgu_cd", "signgu_nm", "tou_div_cd", "tou_div_nm", "daywk_div_cd", "tou_num"],
                rows, key=["base_date", "signgu_cd", "tou_div_cd"],
            )
            record_loaded(conn, path, "kto_region_visitor", count)

        total += count

    print(f"  kto_region_visitor ← 파일 {len(files)}개")

    return total


def build_match(conn: psycopg.Connection) -> int:
    """
    한국관광공사 장소 코드(중심 관광지, 연관 관광지)를 TourAPI 관광지에 연결한다 → kto_place_match

    대상: 한국어 관광지 중 NOA 카테고리가 있고 좌표가 정상인 곳
      1. 중심 관광지: 좌표 300m 안에서 이름 키가 같거나 한쪽이 다른 쪽을 포함하는 가장 가까운 곳
      2. 나머지: 같은 구 안에서 이름 키가 같은 곳이 딱 하나일 때

    인기도 점수 같은 계산은 하지 않는다. 순위와 연결표만 두고 분석/모델 쪽에서 쓴다.
    관광지나 원본이 바뀌면 연결도 바뀌므로 매번 전체를 다시 만든다.
    """

    with conn.transaction():
        conn.execute("DELETE FROM kto_place_match")

        # 1. 중심 관광지: 좌표 + 이름
        hub_matched = conn.execute(
            f"""
            INSERT INTO kto_place_match (tats_cd, tats_nm, content_id, match_method, distance_m)
            SELECT DISTINCT ON (hub.hub_tats_cd)
                hub.hub_tats_cd, hub.hub_tats_nm, place.content_id, 'hub_location',
                ST_Distance(hub.location, place.location)
            FROM (
                SELECT DISTINCT ON (hub_tats_cd) hub_tats_cd, hub_tats_nm, location
                FROM kto_hub_place
                WHERE location IS NOT NULL
                ORDER BY hub_tats_cd, base_ym DESC
            ) AS hub
            JOIN tour_place AS place
              ON place.lang = 'ko'
             AND place.noa_category IS NOT NULL
             AND place.location_valid
             AND ST_DWithin(hub.location, place.location, {HUB_MATCH_RADIUS_M})
             AND length(noa_name_key(hub.hub_tats_nm)) >= 2
             AND (
                   noa_name_key(place.title) = noa_name_key(hub.hub_tats_nm)
                OR noa_name_key(place.title) LIKE '%%' || noa_name_key(hub.hub_tats_nm) || '%%'
                OR noa_name_key(hub.hub_tats_nm) LIKE '%%' || noa_name_key(place.title) || '%%'
             )
            ORDER BY hub.hub_tats_cd, ST_Distance(hub.location, place.location)
            """
        ).rowcount

        # 2. 나머지 (연관 관광지 등): 같은 구 + 같은 이름, 후보가 하나일 때만
        name_matched = conn.execute(
            """
            INSERT INTO kto_place_match (tats_cd, tats_nm, content_id, match_method, distance_m)
            SELECT code.tats_cd, code.tats_nm, min(place.content_id), 'name_signgu', NULL
            FROM (
                SELECT DISTINCT ON (tats_cd) tats_cd, tats_nm, signgu_cd
                FROM (
                    SELECT hub_tats_cd AS tats_cd, hub_tats_nm AS tats_nm, signgu_cd, base_ym FROM kto_hub_place
                    UNION ALL
                    SELECT tats_cd, tats_nm, signgu_cd, base_ym FROM kto_related_place
                    UNION ALL
                    SELECT rlte_tats_cd, rlte_tats_nm, rlte_signgu_cd, base_ym FROM kto_related_place
                ) AS all_codes
                WHERE signgu_cd LIKE '11%%'
                ORDER BY tats_cd, base_ym DESC
            ) AS code
            JOIN tour_place AS place
              ON place.lang = 'ko'
             AND place.noa_category IS NOT NULL
             AND place.location_valid
             AND '11' || place.ldong_signgu_cd = code.signgu_cd
             AND noa_name_key(place.title) = noa_name_key(code.tats_nm)
            WHERE NOT EXISTS (SELECT 1 FROM kto_place_match AS done WHERE done.tats_cd = code.tats_cd)
            GROUP BY code.tats_cd, code.tats_nm
            HAVING count(*) = 1
            """
        ).rowcount

    print(f"  kto_place_match: 좌표 연결 {hub_matched}, 이름 연결 {name_matched}")

    return hub_matched + name_matched
