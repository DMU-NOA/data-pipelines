from noa_data.db.connection import connect
from noa_data.ml.features import build_dataset
from noa_data.ml.predict import sync_actual, sync_predicted
from noa_data.ml.train import train_model


def main() -> None:
    print("===== 실제 혼잡도 동기화 =====")
    with connect() as conn:
        actual = sync_actual(conn)
    print(f"actual={actual:,}")

    print("\n===== ML 학습 데이터 생성 =====")
    with connect() as conn:
        df = build_dataset(conn)

    print("\n===== RandomForest 학습/검증 =====")
    try:
        train_model(df)
    except ValueError as exc:
        # 초기 수집 직후 표본과 클래스가 부족한 것은 예상 가능한 상태.
        # 실제 데이터가 충분히 쌓일 때까지 임의 예측은 생성하지 않는다.
        print(exc)
        print("검증 모델 보류: KNN 시범 추정으로 관광지 예측을 제공합니다.")
        with connect() as conn:
            predicted = sync_predicted(conn)
        print(f"actual={actual:,}, experimental_predicted={predicted:,}")
        return

    print("\n===== 검증된 모델로 혼잡도 예측 =====")
    with connect() as conn:
        predicted = sync_predicted(conn)
    print(f"actual={actual:,}, predicted={predicted:,}")


if __name__ == "__main__":
    main()
