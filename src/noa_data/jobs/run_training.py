from noa_data.db.connection import connect
from noa_data.ml.features import build_dataset
from noa_data.ml.predict import refresh_congestion
from noa_data.ml.train import train_model


def main() -> None:
    print("===== ML 학습 데이터 생성 =====")

    with connect() as conn:
        df = build_dataset(conn)

    print("\n===== RandomForest 학습 =====")
    train_model(df)

    print("\n===== 전체 혼잡도 재계산 =====")

    with connect() as conn:
        actual, predicted = refresh_congestion(conn)

    print("\n===== 완료 =====")
    print(f"actual={actual:,}, predicted={predicted:,}")


if __name__ == "__main__":
    main()
