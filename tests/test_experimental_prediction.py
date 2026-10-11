import pytest
from noa_data.ml.predict import _spatial_knn_estimates


def test_knn_learns_actual_local_patterns():
    reference = [
        (127.000, 37.500, 0),
        (127.005, 37.500, 0),
        (127.100, 37.500, 2),
        (127.105, 37.500, 2),
    ]
    labels, distances = _spatial_knn_estimates(
        reference, [(127.0001, 37.5001), (127.1001, 37.5001)],
    )
    assert labels == [0, 2]
    assert all(0 <= x < 100 for x in distances)


def test_knn_does_not_fabricate_missing_classes():
    reference = [(127.0, 37.5, 0), (127.1, 37.5, 1)]
    labels, _ = _spatial_knn_estimates(reference, [(127.09, 37.5)])
    assert set(labels).issubset({0, 1})


def test_knn_requires_actual_label_diversity():
    with pytest.raises(ValueError, match="서로 다른 혼잡도"):
        _spatial_knn_estimates(
            [(127, 37.5, 0), (127.1, 37.5, 0)],
            [(127.2, 37.5)],
        )
