"""Validated area-level 1..12-hour pooled-horizon ML classifier.

Only labeled CityData *area* hours are eligible for validation.
No claimed individual-tourist congestion accuracy.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import balanced_accuracy_score

from noa_data.collectors.common import PROJECT_ROOT
from noa_data.ml.hourly_features import INPUT_COLUMNS, HORIZONS, OPTIONAL, PROVENANCE

MODEL_PATH = PROJECT_ROOT / "artifacts" / "area_hourly_v2.pkl"
MIN_DAYS = 14
MIN_AREAS = 20
MIN_SLOTS = 7 * 24
MIN_ROWS = 2000
MIN_PER_CLASS = 40
MIN_BALANCED = 0.40
MIN_IMPROVEMENT = 0.025
VERSION = "area_hourly_v2"


def evaluate_readiness(frame):
    """Quality gate before ML fit; report *why* an empty/biased corpus fails."""
    reasons = []
    required = {"issue_time", "forecast_at", "area_cd", "congestion_label",
                "last_level"} | set(INPUT_COLUMNS)
    missing = required - set(frame.columns)
    if missing:
        return [f"필수 컬럼 누락: {', '.join(sorted(missing))}"]
    if len(frame) < MIN_ROWS:
        reasons.append(f"학습 후보 {len(frame):,}행 (최소 {MIN_ROWS:,}행)")
    if frame["area_cd"].nunique() < MIN_AREAS:
        reasons.append(f"관측 지역 {frame['area_cd'].nunique()}곳 (최소 {MIN_AREAS}곳)")
    times = pd.to_datetime(frame["issue_time"], utc=True)
    if times.nunique() < MIN_SLOTS:
        reasons.append(f"기준 시각 {times.nunique()}개 (최소 {MIN_SLOTS}개)")
    if times.empty or times.max() - times.min() < pd.Timedelta(days=MIN_DAYS):
        reasons.append(f"관측 이력 최소 {MIN_DAYS}일 필요")
    count = frame["congestion_label"].value_counts()
    for label in range(4):
        if int(count.get(label, 0)) < MIN_PER_CLASS:
            reasons.append(f"혼잡 클래스 {label}: {int(count.get(label,0))}행")
    return reasons


def _matrix(data):
    # HistGradientBoosting safely handles absent sensor values as NaN.
    x = data.reindex(columns=INPUT_COLUMNS).copy()
    for column in INPUT_COLUMNS:
        x[column] = pd.to_numeric(x[column], errors="coerce")
        x[column] = x[column].replace([np.inf, -np.inf], np.nan)
    return x


def train(frame):
    """Strict chronological holdout; persistence baseline must be beaten."""
    failures = evaluate_readiness(frame)
    if failures:
        raise ValueError("V2 학습 보류:\n- " + "\n- ".join(failures))
    df = frame.copy()
    df["issue_time"] = pd.to_datetime(df["issue_time"], utc=True)
    df["forecast_at"] = pd.to_datetime(df["forecast_at"], utc=True)
    times = sorted(df["issue_time"].unique())
    split_time = times[int(len(times) * .8)]
    # Train targets must not cross validation issue boundary.
    training = df[df["forecast_at"] < split_time]
    validation = df[df["issue_time"] >= split_time]
    if len(training) < 1000 or len(validation) < 250:
        raise ValueError("V2 시간순 훈련/검증 표본 부족")
    if set(range(4)) - set(training["congestion_label"].unique()):
        raise ValueError("V2 훈련 구간에 모든 혼잡 클래스가 존재해야 함")
    if set(range(4)) - set(validation["congestion_label"].unique()):
        raise ValueError("V2 검증 구간에 모든 혼잡 클래스가 존재해야 함")

    model = HistGradientBoostingClassifier(
        max_iter=150, learning_rate=0.06, max_leaf_nodes=24,
        min_samples_leaf=40, l2_regularization=2, random_state=42,
    )
    model.fit(_matrix(training), training["congestion_label"].astype(int))
    truth = validation["congestion_label"].astype(int)
    predicted = model.predict(_matrix(validation))
    score = balanced_accuracy_score(truth, predicted)
    baseline = balanced_accuracy_score(truth, validation["last_level"].astype(int))
    # An acceptable pooled score can hide a severely poor 12-hour horizon.
    # Track every horizon separately so it is visible in the model artifact.
    horizon_scores = {}
    for horizon in range(1, 13):
        mask = validation["horizon"].to_numpy() == horizon
        if int(mask.sum()) < 20:
            raise ValueError(f"V2 {horizon}시간 검증 자료 부족 ({int(mask.sum())}개)")
        horizon_scores[horizon] = round(
            float(balanced_accuracy_score(truth[mask], predicted[mask])), 4
        )
    if score < MIN_BALANCED or score < baseline + MIN_IMPROVEMENT or horizon_scores[12] < 0.30:
        raise ValueError(
            f"V2 검증 미달: balanced_accuracy={score:.3f}, "
            f"현재 혼잡도 유지 기준선={baseline:.3f}; "
            f"필요: {MIN_BALANCED:.2f} 이상 및 기준선 + {MIN_IMPROVEMENT:.3f}; "
            f"12시간 score={horizon_scores[12]:.3f} (최소 0.30)"
        )

    coverage = {}
    for source, names in OPTIONAL.items():
        coverage[source] = round(float(training[names].notna().any(axis=1).mean()), 4)
    artifact = {
        "model": model, "validated": True,
        "version": VERSION, "feature_columns": INPUT_COLUMNS,
        "prediction_unit": "CityData area",
        "horizons": HORIZONS, "balanced_accuracy": float(score),
        "baseline_balanced_accuracy": float(baseline),
        "training_rows": len(training), "validation_rows": len(validation),
        "feature_coverage": coverage, "sources": PROVENANCE,
        "horizon_balanced_accuracy": horizon_scores,
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, MODEL_PATH)
    print(f"V2 검증 통과: model={VERSION} score={score:.3f} baseline={baseline:.3f}")
    print(f"훈련 {len(training):,}행 / 검증 {len(validation):,}행 / 출처 커버리지 {coverage}")
    print(f"시차별 balanced accuracy: {horizon_scores}")
    return artifact


def load_verified():
    if not MODEL_PATH.is_file():
        return None
    artifact = joblib.load(MODEL_PATH)
    if not (isinstance(artifact, dict) and artifact.get("validated") is True
            and artifact.get("version") == VERSION
            and artifact.get("feature_columns") == INPUT_COLUMNS):
        return None
    return artifact
