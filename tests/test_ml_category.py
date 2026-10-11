from noa_data.ml.category import UNKNOWN_CATEGORY, normalize_category


def test_missing_category_is_normalized_for_training_and_prediction():
    assert normalize_category(None) == UNKNOWN_CATEGORY
    assert normalize_category("") == UNKNOWN_CATEGORY
    assert normalize_category("   ") == UNKNOWN_CATEGORY


def test_category_kept_consistently():
    assert normalize_category(" 공원 ") == "공원"
    assert normalize_category("Tourist Zone") == "Tourist Zone"
