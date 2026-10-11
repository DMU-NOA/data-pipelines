"""Non-destructive CityData road / parking coverage report.

Usage:
    python -m noa_data.jobs.diagnose_citydata_transport
Prints raw snapshot coverage, DB load counts, freshness and tourist matching.
Never calls the external CityData API or modifies database rows.
"""
from datetime import datetime, timedelta

from noa_data.collectors.common import RAW_DATA_DIR, load_raw, now_kst
from noa_data.db.connection import connect
from noa_data.loaders.citydata_transport import transport_rows

AGE = timedelta(minutes=90)


def _print_db_stats(conn, table):
    exists = conn.execute("SELECT to_regclass(%s)", (f"public.{table}",)).fetchone()[0]
    if not exists:
        print(f"  {table}: 테이블 없음 → 마이그레이션 미실행")
        return False
    row = conn.execute(
        f"""
        SELECT COUNT(*), COUNT(DISTINCT area_cd), MAX(observed_at),
               COUNT(*) FILTER (
                   WHERE observed_at >= now() - interval '90 minutes'
                     AND observed_at <= now() + interval '5 minutes'
               ),
               COUNT(DISTINCT area_cd) FILTER (
                   WHERE observed_at >= now() - interval '90 minutes'
                     AND observed_at <= now() + interval '5 minutes'
               )
        FROM {table}
        """
    ).fetchone()
    print(f"  {table}: 전체 {row[0]:,}행 / 전체 지역 {row[1]:,}곳"
          f" / 최근 90분 {row[3]:,}행({row[4]:,}곳)"
          f" / 최종 관측 {row[2]}")
    return True


def _raw_stats():
    files = sorted(RAW_DATA_DIR.glob("seoul_citydata/*/citydata_*.json.gz"))
    print(f"\n[1] 수집 원본 파일 수: {len(files):,}")
    if not files:
        print("  저장된 CityData 원본 파일 없음.")
        return
    path = files[-1]
    record = load_raw(path)
    places = record.get("payload", {}).get("places") or {}
    raw_road, raw_parking, eligible_road, eligible_parking = 0, 0, 0, 0
    raw_parking_places, valid_parking_places = set(), set()
    road_shapes, parking_shapes = {}, {}
    example_road = example_parking = None
    for area_cd, place in places.items():
        data = place.get("CITYDATA") or {}
        road = data.get("ROAD_TRAFFIC_STTS")
        park = data.get("PRK_STTS")
        rs = type(road).__name__
        ps = type(park).__name__
        road_shapes[rs] = road_shapes.get(rs, 0) + 1
        parking_shapes[ps] = parking_shapes.get(ps, 0) + 1
        if road:
            raw_road += 1
            if example_road is None and isinstance(road, (dict, list)):
                example_road = list(road.keys()) if isinstance(road, dict) else (
                    list(road[0].keys()) if road and isinstance(road[0], dict) else []
                )
        items = park if isinstance(park, list) else [park] if isinstance(park, dict) else []
        raw_parking += len(items)
        if items:
            raw_parking_places.add(area_cd)
            if example_parking is None and isinstance(items[0], dict):
                example_parking = list(items[0].keys())
        roads, parking = transport_rows(area_cd, place, record.get("collected_at"))
        eligible_road += len(roads)
        eligible_parking += len(parking)
        if parking:
            valid_parking_places.add(area_cd)
    print(f"  최신 파일: {path.relative_to(RAW_DATA_DIR)}")
    print(f"  최신 파일에 포함된 CityData 장소: {len(places):,}곳")
    print(f"  원본 ROAD_TRAFFIC_STTS 비어 있지 않은 장소: {raw_road:,}곳")
    print(f"  원본 PRK_STTS 항목 수: {raw_parking:,}건 / {len(raw_parking_places)}개 지역")
    print(f"  정제 후 적재 가능한 도로: {eligible_road:,}건")
    print(f"  정제 후 적재 가능한 주차장: {eligible_parking:,}건 / {len(valid_parking_places)}개 지역")
    print(f"  원본 자료형: 도로 {road_shapes} / 주차 {parking_shapes}")
    print(f"  도로 필드 이름 예시: {example_road}")
    print(f"  주차 필드 이름 예시: {example_parking}")


def _db_stats():
    print("\n[2] PostgreSQL 데이터 적재 및 신선도")
    with connect() as conn:
        road_ok = _print_db_stats(conn, "citydata_road_traffic")
        parking_ok = _print_db_stats(conn, "citydata_parking")
        mapped = conn.execute("SELECT COUNT(*) FROM spot_mapping").fetchone()[0]
        total = conn.execute("SELECT COUNT(*) FROM tour_spots").fetchone()[0]
        print(f"  관광지 전체: {total:,}곳 / 직접 CityData 매핑: {mapped:,}개")
        if road_ok:
            row = conn.execute(
                """
                SELECT COUNT(DISTINCT m.content_id), COUNT(DISTINCT m.area_cd)
                FROM spot_mapping m
                JOIN citydata_road_traffic road ON road.area_cd = m.area_cd
                WHERE road.observed_at >= now() - interval '90 minutes'
                  AND road.observed_at <= now() + interval '5 minutes'
                """
            ).fetchone()
            print(f"  현재 조건으로 도로 데이터가 조회 가능한 매핑 관광지: "
                  f"{row[0]:,}곳 ({row[1]:,}개 지역)")
        if parking_ok:
            row = conn.execute(
                """
                SELECT COUNT(DISTINCT m.content_id)
                FROM spot_mapping m
                JOIN tour_spots t ON t.content_id = m.content_id
                JOIN citydata_parking p ON p.area_cd = m.area_cd
                WHERE p.observed_at >= now() - interval '90 minutes'
                  AND p.observed_at <= now() + interval '5 minutes'
                  AND t.mapx IS NOT NULL AND t.mapy IS NOT NULL
                  AND ST_DWithin(
                      p.location,
                      ST_SetSRID(ST_MakePoint(t.mapx::double precision,
                                              t.mapy::double precision), 4326)::geography,
                      2000
                  )
                """
            ).fetchone()
            print(f"  현재 조건으로 반경 2km 주차장 조회 가능한 매핑 관광지: {row[0]:,}곳")
        # Coverage expected under the new backend read-only queries.
        if road_ok:
            coverage = """
                WITH eligible AS (
                    SELECT m.content_id
                    FROM spot_mapping m
                    JOIN citydata_road_traffic r ON r.area_cd = m.area_cd
                    WHERE r.observed_at BETWEEN now() - interval '90 minutes'
                                            AND now() + interval '5 minutes'
                    UNION
                    SELECT n.content_id
                    FROM place_nearby n
                    JOIN citydata_road_traffic r ON r.area_cd = n.target_id
                    WHERE n.target_type = 'citydata_area'
                      AND n.distance_m <= 1000
                      AND r.observed_at BETWEEN now() - interval '90 minutes'
                                            AND now() + interval '5 minutes'
                )
                SELECT t.content_id, t.name FROM eligible e
                JOIN tour_spots t ON t.content_id = e.content_id
            """
            row = conn.execute(f"SELECT COUNT(*) FROM ({coverage}) possible").fetchone()
            sample = conn.execute(
                f"SELECT content_id, name FROM ({coverage}) possible "
                "ORDER BY name, content_id LIMIT 5"
            ).fetchall()
            print(f"  개선한 조회 기준(직접 매핑 또는 1km 이내 관측 지역) 도로 정보 가능: {row[0]:,}곳")
            print(f"  도로 테스트용 관광지: {sample}")
        if parking_ok:
            parking_condition = """
                t.mapx IS NOT NULL AND t.mapy IS NOT NULL
                AND EXISTS (
                    SELECT 1 FROM citydata_parking p
                    WHERE p.observed_at BETWEEN now() - interval '90 minutes'
                                            AND now() + interval '5 minutes'
                      AND ST_DWithin(
                          p.location,
                          ST_SetSRID(
                              ST_MakePoint(t.mapx::double precision, t.mapy::double precision),
                              4326
                          )::geography, 2000
                      )
                )
            """
            available = conn.execute(
                f"SELECT COUNT(*) FROM tour_spots t WHERE {parking_condition}"
            ).fetchone()[0]
            sample = conn.execute(
                f"SELECT t.content_id, t.name FROM tour_spots t "
                f"WHERE {parking_condition} ORDER BY t.name, t.content_id LIMIT 5"
            ).fetchall()
            print(f"  개선한 조회 기준(지역 구분 없이 직선 2km) 주차장 잔여 정보 가능: {available:,}곳")
            print(f"  주차장 테스트용 관광지: {sample}")
        history_exists = conn.execute(
            "SELECT to_regclass('public.pipeline_load_history')"
        ).fetchone()[0]
        if history_exists:
            done = conn.execute(
                """SELECT COUNT(*), MAX(loaded_at), COALESCE(SUM(row_count), 0)
                   FROM pipeline_load_history WHERE source = 'seoul_citydata_transport'"""
            ).fetchone()
            print(f"  교통 적재 이력: {done[0]:,}개 파일 / 마지막 적재 {done[1]} /"
                  f" 기록상 행 수 {done[2]:,}")


def main():
    print(f"CityData 교통·주차 진단 (서울 시간: {now_kst().isoformat(timespec='seconds')})")
    _raw_stats()
    _db_stats()
    print("\n해석:")
    print("  원본 존재 + 정제 0건 => 파서 조건/누락 필드/실제 제공 범위 확인")
    print("  정제 양수 + DB 0건 => 마이그레이션/적재 이력/적재 실패 확인")
    print("  DB 양수 + 최근90분 0건 => 최근 수집 미실행 또는 시간 필터 초과")
    print("  최근90분 양수 + 매핑 가능 0건 => 관광지 직접 매핑 또는 거리 제한 문제")


if __name__ == "__main__":
    main()
