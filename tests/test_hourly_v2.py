from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from noa_data.ml import hourly_features as hf
from noa_data.ml.hourly_train import evaluate_readiness, _matrix


TZ = ZoneInfo("Asia/Seoul")
NOW = datetime(2026,10,11,16,0,tzinfo=TZ)


def test_future_collected_weather_does_not_leak(monkeypatch):
    base = pd.DataFrame({
        "area_cd": ["POI001"],
        "issue_time": pd.to_datetime(["2026-10-11T16:00:00+09:00"], utc=True),
    })
    weather = pd.DataFrame({
        "area_cd": ["POI001", "POI001"],
        "observed": [NOW-timedelta(minutes=30), NOW-timedelta(minutes=10)],
        "collected": [NOW-timedelta(minutes=20), NOW+timedelta(minutes=20)],
        "temp": [17, 24],
    })
    monkeypatch.setattr(hf, "_fetch", lambda *a,**kw: weather)
    result = hf._observed_feature(
        base, object(), "SELECT ...",
        ["area_cd", "observed", "collected", "temp"], "3h",
    )
    assert result.iloc[0]["temp"] == 17


def test_stale_weather_is_missing_instead_of_fabricated(monkeypatch):
    base = pd.DataFrame({
        "area_cd": ["POI001"],
        "issue_time": pd.to_datetime(["2026-10-11T16:00:00+09:00"], utc=True),
    })
    old = pd.DataFrame({
        "area_cd": ["POI001"],
        "observed": [NOW-timedelta(hours=4)],
        "collected": [NOW-timedelta(hours=3)],
        "temp": [14],
    })
    monkeypatch.setattr(hf, "_fetch", lambda *a,**kw: old)
    result = hf._observed_feature(
        base, object(), "SELECT ...",
        ["area_cd","observed","collected","temp"], "3h")
    assert pd.isna(result.iloc[0]["temp"])


def test_gap_is_not_a_three_hour_lag(monkeypatch):
    times = [NOW - timedelta(hours=6),
             NOW - timedelta(hours=4), NOW - timedelta(hours=1)]
    def fake_fetch(*a, **kw):
        return pd.DataFrame([
            ("POI001", t, t+timedelta(minutes=5), "여유",
             127.0,37.5) for t in times
        ], columns=["area_cd","observation","collected","label",
                     "longitude","latitude"])
    monkeypatch.setattr(hf, "_fetch", fake_fetch)
    out = hf._base(object(), NOW, 10)
    assert len(out) == 3
    assert pd.isna(out.iloc[2]["level_3h_ago"])


def test_training_gate_requires_real_history_and_all_classes():
    frame = pd.DataFrame({
        "issue_time": [pd.Timestamp(NOW)] * 40,
        "forecast_at": [pd.Timestamp(NOW+timedelta(hours=1))] * 40,
        "area_cd": ["POI001"] * 40,
        "congestion_label": [0] * 40,
        "last_level": [0] * 40,
    })
    for column in hf.INPUT_COLUMNS:
        frame[column] = 0
    failure = evaluate_readiness(frame)
    assert any("관측 이력" in reason for reason in failure)
    assert any("클래스" in reason for reason in failure)


def test_numeric_model_matrix_does_not_turn_missing_into_zero():
    frame = pd.DataFrame({"temp": [np.nan], "hour": [16]})
    x = _matrix(frame)
    assert pd.isna(x.iloc[0]["temp"])
    assert x.iloc[0]["hour"] == 16


def test_feature_source_contracts_explicitly_exclude_unverifiable_kto():
    assert "citydata_road_traffic" in hf.PROVENANCE
    assert "published" not in hf.PROVENANCE["kto_concentration"]
    assert hf.HORIZONS == tuple(range(1,13))
    assert "sdot_people" in hf.INPUT_COLUMNS
    assert "subway_board" in hf.INPUT_COLUMNS
    assert "is_holiday" in hf.INPUT_COLUMNS
