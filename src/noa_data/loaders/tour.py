import psycopg
from psycopg.types.json import Jsonb

from noa_data.collectors.common import load_raw
from noa_data.collectors.tourapi_places import extract_items
from noa_data.loaders.common import (
    in_seoul,
    kst,
    pending_files,
    point,
    record_loaded,
    text,
    upsert,
)


TOURAPI_TIME_FORMAT = "%Y%m%d%H%M%S"

PLACE_COLUMNS = [
    "lang", "content_id", "content_type_id", "title", "addr1", "addr2", "zipcode", "tel",
    "ldong_regn_cd", "ldong_signgu_cd", "lcls_systm1", "lcls_systm2", "lcls_systm3",
    "cat1", "cat2", "cat3", "first_image", "first_image2", "cpyrht_div_cd",
    "location", "location_valid", "created_time", "modified_time", "collected_at",
]


def load_places(conn: psycopg.Connection) -> int:
    """
    TourAPI 장소 목록 (언어별 파일) → tour_place

    나중에 수집한 파일의 값으로 덮어쓴다.
    좌표가 서울 범위 밖이면 location_valid = false 로 표시하고 행은 그대로 둔다.
    """

    files = pending_files(conn, "tourapi_places/*/places_*.json.gz")
    total = 0

    for path in files:
        record = load_raw(path)
        lang = record["payload"]["lang"]
        collected_at = record["collected_at"]

        rows = [
            (
                lang,
                str(item["contentid"]),
                str(item["contenttypeid"]),
                text(item.get("title")),
                text(item.get("addr1")),
                text(item.get("addr2")),
                text(item.get("zipcode")),
                text(item.get("tel")),
                text(item.get("lDongRegnCd")),
                text(item.get("lDongSignguCd")),
                text(item.get("lclsSystm1")),
                text(item.get("lclsSystm2")),
                text(item.get("lclsSystm3")),
                text(item.get("cat1")),
                text(item.get("cat2")),
                text(item.get("cat3")),
                text(item.get("firstimage")),
                text(item.get("firstimage2")),
                text(item.get("cpyrhtDivCd")),
                point(item.get("mapx"), item.get("mapy")),
                in_seoul(item.get("mapx"), item.get("mapy")),
                kst(item.get("createdtime"), TOURAPI_TIME_FORMAT),
                kst(item.get("modifiedtime"), TOURAPI_TIME_FORMAT),
                collected_at,
            )
            for payload in record["payload"]["pages"]
            for item in extract_items(payload)
        ]

        with conn.transaction():
            count = upsert(conn, "tour_place", PLACE_COLUMNS, rows, key=["lang", "content_id"])
            record_loaded(conn, path, "tourapi_places", count)

        total += count
        invalid = sum(not row[PLACE_COLUMNS.index("location_valid")] for row in rows)
        print(f"  tour_place ← {path.name}: {count} (좌표 이상 {invalid})")

    return total


def load_lcls_codes(conn: psycopg.Connection) -> int:
    """
    TourAPI 신분류체계 코드와 이름 → tour_lcls_code
    """

    files = pending_files(conn, "tourapi_codes/*/lcls_codes_*.json.gz")
    total = 0

    for path in files:
        record = load_raw(path)

        rows = [
            (
                item["lclsSystm3Cd"], item["lclsSystm3Nm"],
                item["lclsSystm2Cd"], item["lclsSystm2Nm"],
                item["lclsSystm1Cd"], item["lclsSystm1Nm"],
                record["collected_at"],
            )
            for item in extract_items(record["payload"])
        ]

        with conn.transaction():
            count = upsert(
                conn,
                "tour_lcls_code",
                ["lcls_systm3", "lcls_systm3_nm", "lcls_systm2", "lcls_systm2_nm",
                 "lcls_systm1", "lcls_systm1_nm", "collected_at"],
                rows,
                key=["lcls_systm3"],
            )
            record_loaded(conn, path, "tourapi_codes", count)

        total += count
        print(f"  tour_lcls_code ← {path.name}: {count}")

    return total



FESTIVAL_COLUMNS = [
    "lang", "content_id", "title", "event_start_date", "event_end_date", "addr1", "addr2",
    "tel", "ldong_regn_cd", "ldong_signgu_cd", "first_image", "location", "modified_time",
    "collected_at",
]


def load_festivals(conn: psycopg.Connection) -> int:
    """
    TourAPI 축제/공연/행사 (언어별, 행사 기간 포함) → tour_festival
    """

    files = pending_files(conn, "tourapi_festivals/*/festivals_*.json.gz")
    total = 0

    for path in files:
        record = load_raw(path)
        lang = record["payload"]["lang"]

        rows = [
            (
                lang,
                str(item["contentid"]),
                text(item.get("title")),
                kst(item.get("eventstartdate"), "%Y%m%d").date() if item.get("eventstartdate") else None,
                kst(item.get("eventenddate"), "%Y%m%d").date() if item.get("eventenddate") else None,
                text(item.get("addr1")),
                text(item.get("addr2")),
                text(item.get("tel")),
                text(item.get("lDongRegnCd")),
                text(item.get("lDongSignguCd")),
                text(item.get("firstimage")),
                point(item.get("mapx"), item.get("mapy")),
                kst(item.get("modifiedtime"), TOURAPI_TIME_FORMAT),
                record["collected_at"],
            )
            for payload in record["payload"]["pages"]
            for item in extract_items(payload)
        ]

        with conn.transaction():
            count = upsert(conn, "tour_festival", FESTIVAL_COLUMNS, rows, key=["lang", "content_id"])
            record_loaded(conn, path, "tourapi_festivals", count)

        total += count
        print(f"  tour_festival ← {path.name}: {count}")

    return total


# 소개정보(detailIntro2)는 분류마다 필드 이름이 다르다.
# 관광지 usetime, 문화시설 usetimeculture, 음식점 opentimefood, 쇼핑 opentime ...
# 앞부분이 같은 필드 중 값이 있는 첫 번째를 쓴다.
INTRO_FIELDS = {
    "use_time": ("usetime", "opentime"),
    "rest_date": ("restdate",),
    "parking": ("parking",),
    "info_center": ("infocenter",),
}

INTRO_EXCLUDE = ("parkingfee",)


def intro_value(intro: dict, prefixes: tuple[str, ...]) -> str | None:
    for key, value in intro.items():
        if key.startswith(prefixes) and not key.startswith(INTRO_EXCLUDE) and text(value):
            return text(value)

    return None


DETAIL_COLUMNS = [
    "lang", "content_id", "content_type_id", "overview", "homepage",
    "use_time", "rest_date", "parking", "info_center", "intro", "collected_at",
]


def load_details(conn: psycopg.Connection) -> int:
    """
    TourAPI 상세정보 (개요, 운영시간, 휴무일, 주차) → tour_place_detail

    운영시간과 휴무일은 원본 문장 그대로 둔다 (예: "매주 화요일 ※ 단, 공휴일과 겹치면 개방").
    해석은 분석/모델 쪽에서 한다. 분류별 원본 필드는 intro(jsonb)에 모두 남긴다.
    """

    files = pending_files(conn, "tourapi_details/*/details_*.json.gz")
    total = 0

    for path in files:
        record = load_raw(path)
        lang = record["payload"]["lang"]
        rows = []

        for content_id, detail in record["payload"]["details"].items():
            common = detail["common"][0] if detail["common"] else {}
            intro = detail["intro"][0] if detail["intro"] else {}

            rows.append((
                lang,
                content_id,
                text(common.get("contenttypeid") or intro.get("contenttypeid")),
                text(common.get("overview")),
                text(common.get("homepage")),
                *(intro_value(intro, prefixes) for prefixes in INTRO_FIELDS.values()),
                Jsonb(intro),
                record["collected_at"],
            ))

        with conn.transaction():
            count = upsert(conn, "tour_place_detail", DETAIL_COLUMNS, rows, key=["lang", "content_id"])
            record_loaded(conn, path, "tourapi_details", count)

        total += count
        print(f"  tour_place_detail ← {path.name}: {count}")

    return total
