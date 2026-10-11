from noa_data.jobs import run_setup
from noa_data.jobs.audit_data import TABLES, REQUIRED, _training_readiness


def test_setup_contains_collection_realtime_training_and_audit():
    module_names = [cmd[-1] for _, cmd in run_setup.STEPS]
    assert module_names == [
        "noa_data.db.migrate",
        "noa_data.jobs.run_daily",
        "noa_data.jobs.run_realtime",
        "noa_data.jobs.run_training",
    ]
    assert run_setup.AUDIT[-1] == "noa_data.jobs.audit_data"
    assert all(name in {table for _, table, _ in TABLES} for name in REQUIRED)


def test_inventory_covers_all_operational_sources():
    tables = {table for _, table, _ in TABLES}
    assert {
        "tour_festival", "citydata_population", "citydata_weather",
        "citydata_road_traffic", "citydata_parking",
        "subway_ridership", "bus_ridership",
        "living_population", "foreigner_population_dong",
        "sdot_observation", "weather_observation",
        "kto_concentration", "latest_congestion",
        "place_nearby",
    } <= tables


def test_training_readiness_does_not_claim_v2_usage():
    class NoTableConnection:
        def execute(self, *args):
            raise AssertionError("no DB should be queried when training tables missing")
    r = _training_readiness(NoTableConnection(), set())
    assert r["ready_for_training_gate"] is False
    assert r["uses_sdot_subway_bus_weather_foreigner"] is False
    assert "테이블" in r["reasons"][0]
