import psycopg

from noa_data.loaders.category import CONFIG_DIR, read_csv


NEARBY_FILE = CONFIG_DIR / "place_nearby.csv"

# 대상 관광지: 한국어, NOA 카테고리가 있고, 좌표가 서울 안
TARGET_PLACES = """
    SELECT content_id, location
    FROM tour_place
    WHERE lang = 'ko' AND noa_category IS NOT NULL AND location_valid
"""

# target_type 별로 후보를 찾는 SQL. %(radius)s, %(max_count)s 를 config 에서 채운다.
QUERIES = {
    # 관광지가 속한 행정동
    "admin_dong": """
        SELECT place.content_id, dong.adm_code, 0.0
        FROM ({places}) AS place
        JOIN admin_dong AS dong ON ST_Covers(dong.boundary, place.location)
    """,

    # 관광지가 속하거나 반경 안에 있는 121장소 영역 (영역 안이면 거리 0)
    "citydata_area": """
        SELECT place.content_id, area.area_cd, ST_Distance(area.boundary, place.location)
        FROM ({places}) AS place
        JOIN citydata_area AS area
          ON area.boundary IS NOT NULL
         AND ST_DWithin(area.boundary, place.location, %(radius)s)
    """,

    "sdot_sensor": """
        SELECT place.content_id, sensor.sensor_code::text, ST_Distance(sensor.location, place.location)
        FROM ({places}) AS place
        JOIN sdot_sensor AS sensor
          ON sensor.location IS NOT NULL
         AND ST_DWithin(sensor.location, place.location, %(radius)s)
    """,

    "subway_station": """
        SELECT place.content_id, station.station_id, ST_Distance(station.location, place.location)
        FROM ({places}) AS place
        JOIN subway_station AS station ON ST_DWithin(station.location, place.location, %(radius)s)
    """,

    "bus_stop": """
        SELECT place.content_id, stop.stop_id, ST_Distance(stop.location, place.location)
        FROM ({places}) AS place
        JOIN bus_stop AS stop ON ST_DWithin(stop.location, place.location, %(radius)s)
    """,
}


def build(conn: psycopg.Connection) -> int:
    """
    관광지 ↔ 주변 신호 후보 관계(place_nearby) 를 처음부터 다시 만든다.

    관광지, 센서, 역, 정류장이 바뀌면 관계도 바뀌므로 매번 전체를 다시 계산한다.
    반경과 개수는 config/place_nearby.csv 에서 정한다.
    """

    settings = {row["target_type"]: row for row in read_csv(NEARBY_FILE)}
    unknown = set(settings) - set(QUERIES)

    if unknown:
        raise ValueError(f"place_nearby.csv 에 알 수 없는 target_type: {unknown}")

    total = 0

    with conn.transaction():
        conn.execute("DELETE FROM place_nearby")

        for target_type, setting in settings.items():
            candidates = QUERIES[target_type].format(places=TARGET_PLACES)

            result = conn.execute(
                f"""
                INSERT INTO place_nearby (content_id, target_type, target_id, distance_m, rank)
                SELECT content_id, %(target_type)s, target_id, distance_m, rank
                FROM (
                    SELECT
                        candidate.content_id,
                        candidate.target_id,
                        candidate.distance_m,
                        row_number() OVER (
                            PARTITION BY candidate.content_id
                            ORDER BY candidate.distance_m, candidate.target_id
                        ) AS rank
                    FROM ({candidates}) AS candidate (content_id, target_id, distance_m)
                ) AS ranked
                WHERE rank <= %(max_count)s
                """,
                {
                    "target_type": target_type,
                    "radius": float(setting["radius_m"]),
                    "max_count": int(setting["max_count"]),
                },
            )

            total += result.rowcount
            print(f"  place_nearby: {target_type} {result.rowcount:,}")

    return total
