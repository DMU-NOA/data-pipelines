"""Persist the road/parking sections of saved Seoul CityData snapshots.

Historical raw files have already been ingested by citydata.load_snapshots for
population and weather. A separate history key enables one-time backfill
without rerunning or duplicating those tables.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

import psycopg

from noa_data.collectors.common import RAW_DATA_DIR, load_raw
from noa_data.loaders.common import in_seoul, number, point, relative_key, upsert

KST = ZoneInfo("Asia/Seoul")
SOURCE = "seoul_citydata_transport"
ROAD_COLUMNS = ["area_cd", "observed_at", "avg_speed", "road_msg", "collected_at"]
PARKING_COLUMNS = ["area_cd", "parking_key", "parking_name", "observed_at",
                   "available_count", "capacity", "base_fee", "location", "collected_at"]


def _list(value):
    if isinstance(value, list):
        return [x for x in value if isinstance(x, dict)]
    return [value] if isinstance(value, dict) else []


def _time(value):
    if value is None:
        return None
    raw = str(value).strip()
    if not raw or raw == "-":
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S",
                "%Y%m%d%H%M", "%Y%m%d%H%M%S"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=KST)
        except ValueError:
            pass
    try:
        parsed = datetime.fromisoformat(raw)
        return parsed.replace(tzinfo=KST) if parsed.tzinfo is None else parsed
    except ValueError:
        return None


def _nonnegative_int(value):
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if num < 0 or not num.is_integer():
        return None
    return int(num)


def transport_rows(area_cd, payload, collected_at):
    """Validate road and parking observations without inventing missing timestamps."""
    data = payload.get("CITYDATA") or {}
    road_rows, parking_rows = [], []

    raw_road = data.get("ROAD_TRAFFIC_STTS") or {}
    roads = _list(raw_road)
    if roads:
        road = roads[0]
        avg_list = _list(road.get("AVG_ROAD_DATA"))
        avg = avg_list[0] if avg_list else {}
        timestamp = _time(road.get("ROAD_TRAFFIC_TIME") or avg.get("ROAD_TRAFFIC_TIME"))
        speed = number(avg.get("ROAD_TRAFFIC_SPD", road.get("ROAD_TRAFFIC_SPD")))
        if (timestamp is not None and speed is not None and 0 <= speed <= 200):
            msg = avg.get("ROAD_MSG") or road.get("ROAD_MSG") or None
            road_rows.append((area_cd, timestamp, speed, msg, collected_at))

    for item in _list(data.get("PRK_STTS")):
        if not item.get("PRK_NM") or str(item.get("CUR_PRK_YN") or "").upper() != "Y":
            continue
        stamp = _time(item.get("CUR_PRK_TIME"))
        avail = _nonnegative_int(item.get("CUR_PRK_CNT"))
        capacity = _nonnegative_int(item.get("CPCTY"))
        lon, lat = item.get("LNG"), item.get("LAT")
        if (stamp is None or avail is None or capacity is None
                or avail > capacity or not in_seoul(lon, lat)):
            continue
        name = str(item["PRK_NM"]).strip()
        key = str(item.get("PRK_CD") or "").strip() or f"{name}|{lon}|{lat}"
        fee = _nonnegative_int(item.get("RATES"))
        parking_rows.append(
            (area_cd, key, name, stamp, avail, capacity, fee,
             point(lon, lat), collected_at)
        )
    return road_rows, parking_rows


def load_snapshots(conn: psycopg.Connection) -> int:
    """Backfill older raw files and ingest new files incrementally."""
    loaded = {
        row[0] for row in conn.execute(
            "SELECT file_path FROM pipeline_load_history WHERE source = %s", (SOURCE,)
        ).fetchall()
    }
    files = sorted(RAW_DATA_DIR.glob("seoul_citydata/*/citydata_*.json.gz"))
    pending = [(path, f"transport/{relative_key(path)}") for path in files
               if f"transport/{relative_key(path)}" not in loaded]
    total = 0
    for path, history_key in pending:
        record = load_raw(path)
        road_rows, parking_rows = [], []
        for area_cd, payload in record["payload"]["places"].items():
            road, parking = transport_rows(area_cd, payload, record["collected_at"])
            road_rows.extend(road)
            parking_rows.extend(parking)
        with conn.transaction():
            road_count = upsert(conn, "citydata_road_traffic", ROAD_COLUMNS, road_rows,
                                key=["area_cd", "observed_at"], update=False)
            parking_count = upsert(conn, "citydata_parking", PARKING_COLUMNS,
                                   parking_rows, key=["area_cd", "parking_key", "observed_at"],
                                   update=False)
            conn.execute(
                """INSERT INTO pipeline_load_history(file_path, source, row_count)
                   VALUES (%s, %s, %s) ON CONFLICT (file_path) DO NOTHING""",
                (history_key, SOURCE, road_count + parking_count),
            )
        total += road_count + parking_count
    print(f"  CityData 교통·주차: 파일 {len(pending):,}개 / 적재 {total:,}건")
    return total
