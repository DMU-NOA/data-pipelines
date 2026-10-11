import pandas as pd
import pytest

from noa_data.ml.train import validate_training_data, train_model


def test_single_snapshot_is_not_training_ready():
    df = pd.DataFrame({
        "area_cd": ["POI001"] * 68,
        "category": ["역사·명소"] * 68,
        "mapx": [126.98] * 68,
        "mapy": [37.56] * 68,
        "hour": [20] * 68,
        "day_of_week": [0] * 68,
        "collected_at": ["2026-10-05T20:00:00+09:00"] * 68,
        "congestion_label": [0] * 66 + [1] * 2,
    })
    issues = validate_training_data(df)
    assert issues
    assert any("클래스 2" in issue for issue in issues)
    with pytest.raises(ValueError, match="학습 보류"):
        train_model(df)


def test_missing_features_reported():
    issues = validate_training_data(pd.DataFrame({"congestion_label": [0]}))
    assert any("컬럼 누락" in issue for issue in issues)
