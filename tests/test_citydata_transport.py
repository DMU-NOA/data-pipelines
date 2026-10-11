from datetime import datetime
from zoneinfo import ZoneInfo

from noa_data.loaders.citydata_transport import transport_rows, _time, _nonnegative_int


def test_citydata_transport_parses_valid_road_and_parking():
    payload = {"CITYDATA": {
        "ROAD_TRAFFIC_STTS": {
            "ROAD_TRAFFIC_TIME": "2026-10-11 15:00",
            "AVG_ROAD_DATA": {"ROAD_TRAFFIC_SPD": "24.2", "ROAD_MSG": "서행"},
        },
        "PRK_STTS": [
            {"PRK_NM": "주차장A", "PRK_CD": "101", "CUR_PRK_YN": "Y",
             "CUR_PRK_TIME": "2026-10-11 15:00", "CUR_PRK_CNT": "9",
             "CPCTY": "50", "LNG": "127.01", "LAT": "37.55", "RATES": "1000"},
        ],
    }}
    road, park = transport_rows("POI001", payload, "2026-10-11T15:05:00+09:00")
    assert len(road) == len(park) == 1
    assert road[0][2] == 24.2
    assert park[0][1] == "101"
    assert park[0][4:6] == (9, 50)
    assert park[0][7] == "SRID=4326;POINT(127.01 37.55)"


def test_transport_rejects_unverifiable_or_impossible_live_readings():
    data = {"CITYDATA": {
        "ROAD_TRAFFIC_STTS": {"AVG_ROAD_DATA": {"ROAD_TRAFFIC_SPD": "22"}},
        "PRK_STTS": [
            {"PRK_NM": "날짜누락", "CUR_PRK_YN": "Y", "CUR_PRK_CNT": 6,
             "CPCTY": 30, "LNG": 127.01, "LAT": 37.55},
            {"PRK_NM": "숫자오류", "CUR_PRK_YN": "Y", "CUR_PRK_TIME": "2026-10-11 15:00",
             "CUR_PRK_CNT": 31, "CPCTY": 30, "LNG": 127.01, "LAT": 37.55},
        ],
    }}
    road, park = transport_rows("POI001", data, "2026-10-11T15:05:00+09:00")
    assert road == []
    assert park == []


def test_transport_timestamp_parsing():
    assert _time("2026-10-11 15:00") == datetime(2026, 10, 11, 15, 0,
                                                   tzinfo=ZoneInfo("Asia/Seoul"))
    assert _time("-") is None
    assert _nonnegative_int("2.5") is None


def test_load_db_registers_transport_loader():
    from noa_data.jobs.load_db import LOADERS
    assert "citydata_transport" in LOADERS
    assert list(LOADERS).index("citydata") < list(LOADERS).index("citydata_transport")
