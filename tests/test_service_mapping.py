import csv
from contextlib import nullcontext

from noa_data.loaders import service


class _Result:
    def __init__(self, rows=(), rowcount=0):
        self._rows = rows
        self.rowcount = rowcount

    def fetchall(self):
        return list(self._rows)


class _Connection:
    def __init__(self, mappings):
        self.mappings = list(mappings)
        self.writes = 0

    def transaction(self):
        return nullcontext()

    def execute(self, sql, params):
        if "SELECT area_cd, content_id" in sql:
            area, content = params
            return _Result([(a, c) for a, c in self.mappings if a == area or c == content])
        if "INSERT INTO spot_mapping" in sql:
            area, content = params[:2]
            if not any(a == area or c == content for a, c in self.mappings):
                self.mappings.append((area, content))
                self.writes += 1
                return _Result(rowcount=1)
            return _Result(rowcount=0)
        raise AssertionError(sql)


def test_sync_mapping_keeps_existing_and_is_idempotent(tmp_path, monkeypatch):
    path = tmp_path / "mapping.csv"
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["area_cd", "content_id"])
        writer.writerow(["POI001", "1"])
        writer.writerow(["POI002", "2"])
    monkeypatch.setattr(service, "MAPPING_FILE", path)
    conn = _Connection([("POI001", "1")])
    assert service.sync_mapping(conn) == 1
    assert service.sync_mapping(conn) == 0
    assert conn.mappings == [("POI001", "1"), ("POI002", "2")]


def test_sync_mapping_preserves_conflicting_record(tmp_path, monkeypatch):
    path = tmp_path / "mapping.csv"
    path.write_text("area_cd,content_id\\nPOI001,2\\n", encoding="utf-8")
    monkeypatch.setattr(service, "MAPPING_FILE", path)
    conn = _Connection([("POI001", "1")])
    assert service.sync_mapping(conn) == 0
    assert conn.mappings == [("POI001", "1")]
