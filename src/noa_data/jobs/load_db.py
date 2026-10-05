import argparse
import time

from noa_data.db.connection import connect
from noa_data.loaders import (
    calendar,
    category,
    citydata,
    foreigner,
    kto,
    living_population,
    kto_bigdata,
    nearby,
    sdot,
    service,
    spatial,
    tour,
    transit,
    weather,
)


# 적재 순서. 뒤 단계가 앞 단계의 결과를 쓰므로 순서가 중요하다.
# 원본 파일은 아직 적재하지 않은 것만 넣는다 (pipeline_load_history 기준).
LOADERS = {
    # 1. 기준 정보
    "holiday": calendar.load_holidays,
    "weather": weather.load_observations,
    "citydata_area": citydata.load_areas,
    "citydata_area_boundary": spatial.load_citydata_area_boundary,
    "admin_dong": spatial.load_admin_dong,
    "sdot_sensor": sdot.load_sensors,
    "subway_station": transit.load_subway_stations,
    "bus_stop": transit.load_bus_stops,

    # 2. 관광지와 카테고리 (config/*.csv 반영)
    "tour_lcls_code": tour.load_lcls_codes,
    "tour_place": tour.load_places,
    "noa_category": category.sync_and_assign,
    "tour_festival": tour.load_festivals,
    "tour_place_detail": tour.load_details,

    # 3. 관광지 ↔ 주변 신호 관계
    "place_nearby": nearby.build,

    # 4. 한국관광공사 빅데이터
    "kto_hub": kto_bigdata.load_hub,
    "kto_related": kto_bigdata.load_related,
    "kto_place_match": kto_bigdata.build_match,

    # 5. 시계열 신호
    "kto_concentration": kto.load_concentration,
    "citydata": citydata.load_snapshots,
    "sdot_api": sdot.load_api_observations,
    "sdot_file": sdot.load_file_observations,
    "subway_ridership": transit.load_subway_ridership,
    "bus_ridership": transit.load_bus_ridership,
    "living_population": living_population.load_monthly_files,
    "foreigner_dong": foreigner.load_dong_files,
    "kto_visitor": kto_bigdata.load_visitor,

    # 6. 현재 noa-backend가 읽는 서비스용 read model
    "service": service.sync_all,
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="data/raw 원본 파일을 DB에 적재하고 서비스 테이블까지 동기화",
    )
    parser.add_argument(
        "--only",
        nargs="*",
        choices=list(LOADERS),
        help="이 적재만 실행 (생략하면 전부, 위 순서대로)",
    )
    args = parser.parse_args()

    names = args.only or list(LOADERS)

    with connect() as conn:
        for name in names:
            started = time.monotonic()
            print(f"== {name}", flush=True)
            count = LOADERS[name](conn)
            print(f"   {count:,}행, {time.monotonic() - started:.0f}초", flush=True)


if __name__ == "__main__":
    main()
