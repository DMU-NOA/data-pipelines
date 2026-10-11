"""ML 학습과 추론에 동일하게 사용하는 카테고리 규칙."""

UNKNOWN_CATEGORY = "기타"


def normalize_category(value):
    """원본 카테고리가 없거나 공백인 경우 공통 미분류 카테고리를 사용한다."""
    if value is None:
        return UNKNOWN_CATEGORY
    value = str(value).strip()
    return value if value else UNKNOWN_CATEGORY
