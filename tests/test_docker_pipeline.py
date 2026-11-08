"""Pure unit tests: no live API, DB or Docker daemon required."""
from datetime import datetime
from unittest.mock import patch

from noa_data.engine import citydata


def test_citydata_process_rejects_missing_raw(tmp_path):
    with patch.object(citydata, "RAW_DATA_DIR", tmp_path):
        try:
            citydata.process("../invalid.json.gz")
        except ValueError:
            pass
        else:
            raise AssertionError("missing or escaping path must be rejected")


def test_citydata_process_uses_stage_loaders(tmp_path):
    file = tmp_path / "seoul_citydata" / "20261108" / "citydata_140000.json.gz"
    file.parent.mkdir(parents=True)
    file.write_bytes(b"test")
    from unittest.mock import MagicMock
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = (1,)
    ctx = MagicMock()
    ctx.__enter__.return_value = conn
    with patch.object(citydata, "RAW_DATA_DIR", tmp_path), \
         patch.object(citydata, "connect", return_value=ctx), \
         patch.object(citydata.citydata, "load_snapshots") as pop, \
         patch.object(citydata.citydata_transport, "load_snapshots") as transport:
        citydata.process(file.relative_to(tmp_path).as_posix())
        pop.assert_called_once_with(conn)
        transport.assert_called_once_with(conn)
