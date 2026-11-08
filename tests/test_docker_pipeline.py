"""Pure unit tests: no live API, DB or Docker daemon required."""
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from noa_data.engine import citydata
from noa_data.pipeline_service import _slot_key


def test_citydata_process_rejects_missing_raw(tmp_path):
    with patch.object(citydata, "RAW_DATA_DIR", tmp_path):
        with pytest.raises(ValueError):
            citydata.process("../invalid.json.gz")


def test_citydata_process_uses_stage_loaders(tmp_path):
    file = tmp_path / "seoul_citydata" / "20261108" / "citydata_140000.json.gz"
    file.parent.mkdir(parents=True)
    file.write_bytes(b"test")
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


def test_collection_slot_uses_quarter_hour():
    with patch("noa_data.pipeline_service.datetime") as clock:
        clock.now.return_value = datetime(2026, 11, 8, 14, 28, 53, tzinfo=citydata.seoul_citydata.now_kst().tzinfo)
        assert _slot_key().endswith("14:15:00+09:00")
