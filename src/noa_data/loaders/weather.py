import psycopg

from noa_data.collectors.common import load_raw
from noa_data.collectors.tourapi_places import extract_items
from noa_data.loaders.common import kst, number, pending_files, record_loaded, upsert


COLUMNS = [
    "station_id", "observed_at", "temperature", "precipitation", "humidity",
    "wind_speed", "wind_direction", "snow_depth", "cloud_amount", "visibility",
    "sunshine", "collected_at",
]


def load_observations(conn: psycopg.Connection) -> int:
    """
    기상청 ASOS 시간별 관측 → weather_observation

    최근 며칠을 매일 다시 받으므로 같은 시각이 여러 번 들어온다.
    나중에 받은 값으로 덮어쓴다 (기상청이 값을 보정하는 경우가 있다).
    """

    files = pending_files(conn, "kma_asos_hourly/*/asos_*.json.gz")
    total = 0

    for path in files:
        record = load_raw(path)

        rows = [
            (
                item["stnId"],
                kst(item["tm"], "%Y-%m-%d %H:%M"),
                number(item.get("ta")),
                number(item.get("rn")),
                number(item.get("hm")),
                number(item.get("ws")),
                number(item.get("wd")),
                number(item.get("dsnw")),
                number(item.get("dc10Tca")),
                number(item.get("vs")),
                number(item.get("ss")),
                record["collected_at"],
            )
            for item in extract_items(record["payload"])
        ]

        with conn.transaction():
            count = upsert(
                conn, "weather_observation", COLUMNS, rows,
                key=["station_id", "observed_at"],
            )
            record_loaded(conn, path, "kma_asos_hourly", count)

        total += count

    print(f"  weather_observation ← 파일 {len(files)}개")

    return total
