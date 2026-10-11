from noa_data.collectors import seoul_citydata
from noa_data.db.connection import connect
from noa_data.loaders import citydata, citydata_transport, service
from noa_data.ml.predict import refresh_congestion
from noa_data.ml.hourly_predict import publish as publish_hourly


def main() -> None:
    """
    15분 주기 실시간 파이프라인.

    CityData 수집
      -> DB 적재
      -> 서비스 테이블 동기화
      -> actual / predicted 최신 혼잡도 갱신
    """

    print("===== CityData 수집 =====")
    seoul_citydata.collect()

    print("\n===== CityData 적재 =====")

    with connect() as conn:
        citydata.load_snapshots(conn)
        citydata_transport.load_snapshots(conn)

        print("\n===== 서비스 테이블 동기화 =====")
        service.sync_all(conn)

        print("\n===== 혼잡도 최신화 =====")
        actual, predicted = refresh_congestion(conn)

        print("\\n===== 검증된 지역별 시간대 혼잡도 예측 =====")
        hourly = publish_hourly(conn)

    print(f"actual={actual:,}, predicted={predicted:,}, hourly_verified={hourly:,}")


if __name__ == "__main__":
    main()
