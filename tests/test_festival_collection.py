from datetime import date

from noa_data.jobs.collect_tourapi_festivals import rolling_since


def test_festival_collect_rolling_window_changes_with_date():
    assert rolling_since(date(2026, 10, 11)) == "20251011"
    assert rolling_since(date(2026, 10, 12)) == "20251012"


def test_daily_job_collects_korean_festivals():
    from noa_data.jobs.run_daily import STEPS
    matches = [args for name, args in STEPS if name == "축제·행사"]
    assert matches == [["collect_tourapi_festivals", "--lang", "ko"]]
