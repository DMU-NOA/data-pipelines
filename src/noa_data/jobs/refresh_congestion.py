from noa_data.db.connection import connect
from noa_data.ml.predict import refresh_congestion


def main() -> None:
    with connect() as conn:
        actual, predicted = refresh_congestion(conn)

    print(f"actual={actual:,}, predicted={predicted:,}")


if __name__ == "__main__":
    main()
