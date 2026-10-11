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


class _FakeResult:
    def __init__(self, rowcount=0):
        self.rowcount = rowcount

    def fetchone(self):
        return (5,)


class _FakeConnection:
    def __init__(self):
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        return _FakeResult()

    def transaction(self):
        from contextlib import nullcontext
        return nullcontext()


def test_reset_uses_bound_like_patterns_and_allows_explicit_like_delete():
    from noa_data.jobs.reset_tourism import reset

    conn = _FakeConnection()
    result = reset(conn, allow_delete_likes=True)
    assert result["likes"] == 5

    statements = [(sql, params) for sql, params in conn.executed
                  if "DELETE FROM pipeline_load_history" in sql]
    assert len(statements) == 1
    sql, params = statements[0]
    assert sql.count("%s") == 2
    assert "LIKE ANY(%s)" in sql
    assert params == (list(TOUR_SOURCES), [f"{source}/%" for source in TOUR_SOURCES])
