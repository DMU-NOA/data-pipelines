"""Persist verified 12-hour area-level ML forecasts, if a validated model exists."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from noa_data.ml.hourly_features import HORIZONS, INPUT_COLUMNS, expand_forecast, make_features
from noa_data.ml.hourly_train import load_verified, _matrix

KST = ZoneInfo("Asia/Seoul")
LABELS = ("여유", "보통", "약간 붐빔", "붐빔")


def publish(conn, now=None):
    model_info = load_verified()
    if not model_info:
        print("검증 V2 모델 없음: 시간별 자체 ML 예측 보류 (서울시 공식 예보는 별도)")
        return 0
    now = now or datetime.now(KST)
    df = make_features(conn, now=now, days=3)
    if df.empty:
        print("V2 예측 기준 실측 데이터 없음")
        return 0
    df = df.sort_values(["area_cd", "slot"]).drop_duplicates("area_cd", keep="last")
    # Ignore stale observations so a missing CityData collector cannot keep
    # publishing seemingly fresh hourly forecasts.
    df = df[df["issue_time"] >= pd.Timestamp(now) - pd.Timedelta(hours=2)]
    if df.empty:
        print("V2 최신 실측 데이터 없음 (2시간 기준)")
        return 0
    features = expand_forecast(df, conn, with_labels=False)
    now_utc = pd.Timestamp(now).tz_convert("UTC")
    features = features[(features["forecast_at"] > now_utc)
                        & (features["forecast_at"] <= now_utc + pd.Timedelta(hours=12))]
    if features.empty:
        return 0
    model = model_info["model"]
    labels = model.predict(_matrix(features))
    issued = now
    rows = []
    for (area, horizon, target), label in zip(
        features[["area_cd", "horizon", "forecast_at"]].itertuples(index=False, name=None),
        labels
    ):
        rows.append((area, target.to_pydatetime(), issued, int(label),
                     LABELS[int(label)], int(horizon),
                     model_info["version"],
                     model_info["balanced_accuracy"],
                     model_info["baseline_balanced_accuracy"]))
    with conn.transaction():
        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO area_hourly_forecast
                    (area_cd, forecast_at, issued_at, congestion_label,
                     congestion_level, horizon_hours, model_version,
                     validation_balanced_accuracy, validation_baseline_accuracy)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (area_cd, forecast_at) DO UPDATE SET
                     issued_at=EXCLUDED.issued_at,
                     congestion_label=EXCLUDED.congestion_label,
                     congestion_level=EXCLUDED.congestion_level,
                     horizon_hours=EXCLUDED.horizon_hours,
                     model_version=EXCLUDED.model_version,
                     validation_balanced_accuracy=EXCLUDED.validation_balanced_accuracy,
                     validation_baseline_accuracy=EXCLUDED.validation_baseline_accuracy""",
                rows
            )
        conn.execute("DELETE FROM area_hourly_forecast WHERE forecast_at < %s",
                     (now - timedelta(days=2),))
    print(f"검증 V2 혼잡도 1~12시간 예측: {len(rows):,}행 / {df['area_cd'].nunique()}개 관측지역")
    return len(rows)
