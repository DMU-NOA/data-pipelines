from pathlib import Path
from noa_data.jobs.reset_tourism import TOUR_TABLES, TOUR_SOURCES


def test_tourism_reset_only_targets_tourism_tables():
    assert "citydata_population" not in TOUR_TABLES
    assert "sdot_observation" not in TOUR_TABLES
    assert "users" not in TOUR_TABLES
    assert "seoul_spots" not in TOUR_TABLES
    assert {"tour_place", "tour_spots", "latest_congestion", "spot_mapping"}.issubset(TOUR_TABLES)


def test_fresh_raw_only_tourapi():
    assert TOUR_SOURCES == ("tourapi_places", "tourapi_details", "tourapi_festivals")
