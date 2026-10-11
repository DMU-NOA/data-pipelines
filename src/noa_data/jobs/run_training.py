"""Refresh observed congestion, retrain V1 and V2 only when each gate passes."""
from datetime import timedelta
from noa_data.db.connection import connect
from noa_data.ml.features import build_dataset
from noa_data.ml.predict import sync_actual, sync_predicted
from noa_data.ml.train import train_model
from noa_data.ml.hourly_features import make_features, expand_forecast
from noa_data.ml.hourly_train import train as train_hourly
from noa_data.ml.hourly_predict import publish as publish_hourly


def main():
    print("===== 실제 혼잡도 동기화 =====")
    with connect() as conn:
        actual = sync_actual(conn)
    print(f"actual={actual:,}")

    print("\n===== 기존 V1 모델 학습/검증 =====")
    try:
        with connect() as conn:
            df = build_dataset(conn)
        train_model(df)
    except (ValueError, RuntimeError) as exc:
        print(f"V1 학습 보류: {exc}")

    # Historical/experimental KNN is labelled unverified, separate from V2.
    with connect() as conn:
        predicted = sync_predicted(conn)
    print(f"V1/시범 관광지 예상: {predicted:,}건")

    print("\n===== V2: 시점별 다중 데이터 결합 =====")
    try:
        with connect() as conn:
            # Avoid expensive 12-horizon expansion until enough *real*
            # observation history exists. A one-day data reset must not
            # trigger a model fit or a huge unnecessary source join.
            dates = conn.execute(
                """SELECT MIN(ppltn_time), MAX(ppltn_time),
                          COUNT(DISTINCT date_trunc('hour', ppltn_time))
                   FROM citydata_population
                   WHERE ppltn_time >= now() - interval '30 days'
                     AND congest_lvl IN ('여유','보통','약간 붐빔','붐빔')"""
            ).fetchone()
            if (dates[0] is None or dates[1]-dates[0] < timedelta(days=14)
                    or dates[2] < 7 * 24):
                raise ValueError(
                    f"현재 CityData 이력 부족: 관측 시작={dates[0]}, 마지막={dates[1]}, "
                    f"서로 다른 관측 시간={dates[2]}. V2는 최소 14일 필요."
                )
            features = make_features(conn)
            hourly_df = expand_forecast(features, conn, with_labels=True)
        print(f"V2 후보: {len(hourly_df):,}행")
        artifact = train_hourly(hourly_df)
    except ValueError as exc:
        print(f"V2 학습 보류: {exc}")
        print("기존 검증 모델이 있으면 유지하고, 데이터가 부족하면 자체 시간별 예측은 생성하지 않습니다.")
        return

    print("\n===== 검증된 V2 1~12시간 예측 적재 =====")
    with connect() as conn:
        count = publish_hourly(conn)
    print(f"hourly_verified={count:,}")


if __name__ == "__main__":
    main()
