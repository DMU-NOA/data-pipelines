from pathlib import Path
from noa_data.ml import predict


def test_actual_sync_independent_of_tour_mapping():
    import inspect
    source = inspect.getsource(predict.sync_actual)
    assert "JOIN seoul_spots s ON s.area_cd = latest.area_cd" in source
    assert "LEFT JOIN spot_mapping m ON m.area_cd = latest.area_cd" in source
    assert "JOIN spot_mapping m" not in source.replace("LEFT JOIN spot_mapping m", "")


def test_prototype_uses_citydata_area_geometry():
    import inspect
    source = inspect.getsource(predict._experimental_predictions)
    assert "ST_PointOnSurface(c.boundary::geometry)" in source
    assert "LEFT JOIN spot_mapping" in source
