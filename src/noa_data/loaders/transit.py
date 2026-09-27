import re
from collections import defaultdict
from datetime import date

import psycopg

from noa_data.collectors.common import load_raw
from noa_data.loaders.common import number, pending_files, point, record_loaded, text, upsert


# 승하차 컬럼 이름이 일정하지 않다 (예: HR_0_GET_ON_TNOPE, HR_1_GET_ON_NOPE)
HOUR_COLUMN = re.compile(r"^HR_(\d{1,2})_GET_(ON|OFF)_T?NOPE$")


def hourly_values(row: dict) -> dict[int, dict[str, float | None]]:
    """
    가로로 펼쳐진 시간대 컬럼을 {시각: {"on": 승차, "off": 하차}} 로 바꾼다.
    """

    hours: dict[int, dict[str, float | None]] = defaultdict(dict)

    for key, value in row.items():
        match = HOUR_COLUMN.match(key)

        if match:
            hours[int(match.group(1))][match.group(2).lower()] = number(value)

    return hours


def month_start(use_month: str) -> date:
    return date(int(use_month[:4]), int(use_month[4:6]), 1)


def load_subway_stations(conn: psycopg.Connection) -> int:
    """
    서울시 역사마스터 → subway_station
    """

    files = pending_files(conn, "seoul_subway_stations/*/stations_*.json.gz")
    total = 0

    for path in files:
        rows = [
            (
                row["BLDN_ID"],
                text(row["BLDN_NM"]),
                text(row["ROUTE"]),
                point(row["LOT"], row["LAT"]),
            )
            for row in load_raw(path)["payload"]["rows"]
            if row.get("LAT") and row.get("LOT")
        ]

        with conn.transaction():
            count = upsert(
                conn, "subway_station",
                ["station_id", "station_nm", "line", "location"],
                rows, key=["station_id"],
            )
            record_loaded(conn, path, "seoul_subway_stations", count)

        total += count
        print(f"  subway_station ← {path.name}: {count}")

    return total


def load_subway_ridership(conn: psycopg.Connection) -> int:
    """
    지하철 호선별 역별 시간대별 승하차 (월) → subway_ridership (세로로 펼침)
    """

    files = pending_files(conn, "seoul_subway_hourly/*/subway_*.json.gz")
    total = 0

    for path in files:
        payload = load_raw(path)["payload"]
        use_month = month_start(payload["use_month"])

        rows = [
            (use_month, text(row["SBWY_ROUT_LN_NM"]), text(row["STTN"]), hour, values.get("on"), values.get("off"))
            for row in payload["rows"]
            for hour, values in hourly_values(row).items()
        ]

        with conn.transaction():
            count = upsert(
                conn, "subway_ridership",
                ["use_month", "line", "station_nm", "hour", "get_on", "get_off"],
                rows, key=["use_month", "line", "station_nm", "hour"],
            )
            record_loaded(conn, path, "seoul_subway_hourly", count)

        total += count
        print(f"  subway_ridership ← {path.name}: {count:,}")

    return total


def load_bus_stops(conn: psycopg.Connection) -> int:
    """
    서울시 버스정류소 위치 → bus_stop
    """

    files = pending_files(conn, "seoul_bus_stops/*/bus_stops_*.json.gz")
    total = 0

    for path in files:
        rows = [
            (
                row["STOPS_NO"],
                text(row["STOPS_NM"]),
                text(row.get("STOPS_TYPE")),
                text(row.get("NODE_ID")),
                point(row["XCRD"], row["YCRD"]),
            )
            for row in load_raw(path)["payload"]["rows"]
            if row.get("XCRD") and row.get("YCRD")
        ]

        with conn.transaction():
            count = upsert(
                conn, "bus_stop",
                ["stop_id", "stop_nm", "stop_type", "node_id", "location"],
                rows, key=["stop_id"],
            )
            record_loaded(conn, path, "seoul_bus_stops", count)

        total += count
        print(f"  bus_stop ← {path.name}: {count:,}")

    return total


def load_bus_ridership(conn: psycopg.Connection) -> int:
    """
    버스 노선별 정류장별 시간대별 승하차 (월) → bus_ridership

    노선별로 나뉜 값을 정류장 단위로 합친다. 노선별 원본은 원본 파일에 있다.
    """

    files = pending_files(conn, "seoul_bus_hourly/*/bus_*.json.gz")
    total = 0

    for path in files:
        payload = load_raw(path)["payload"]
        use_month = month_start(payload["use_month"])

        sums: dict[tuple[str, int], list] = {}

        for row in payload["rows"]:
            stop_id = text(row.get("STOPS_ID"))

            if not stop_id:
                continue

            for hour, values in hourly_values(row).items():
                current = sums.setdefault((stop_id, hour), [0.0, 0.0, 0])
                current[0] += values.get("on") or 0
                current[1] += values.get("off") or 0
                current[2] += 1

        rows = [
            (use_month, stop_id, hour, get_on, get_off, routes)
            for (stop_id, hour), (get_on, get_off, routes) in sums.items()
        ]

        with conn.transaction():
            count = upsert(
                conn, "bus_ridership",
                ["use_month", "stop_id", "hour", "get_on", "get_off", "route_count"],
                rows, key=["use_month", "stop_id", "hour"],
            )
            record_loaded(conn, path, "seoul_bus_hourly", count)

        total += count
        print(f"  bus_ridership ← {path.name}: {count:,}")

    return total
