from datetime import date

from noa_data.collectors.seoul_files import RemoteFile
from noa_data.loaders.sdot import registered_time, sensor_code
from noa_data.loaders.transit import hourly_values


def test_hourly_values_handles_inconsistent_column_names():
    # 버스 원본은 시간대마다 컬럼 이름이 다르다 (TNOPE / NOPE)
    row = {
        "STOPS_ID": "110000327",
        "HR_0_GET_ON_TNOPE": 5.0,
        "HR_0_GET_OFF_TNOPE": 13.0,
        "HR_1_GET_ON_NOPE": 0.0,
        "HR_1_GET_OFF_NOPE": 3.0,
    }

    assert hourly_values(row) == {0: {"on": 5.0, "off": 13.0}, 1: {"on": 0.0, "off": 3.0}}


def test_sensor_code_keeps_raw_and_normalizes():
    assert sensor_code("00000002993") == 2993
    assert sensor_code("") is None
    assert sensor_code("ABC") is None


def test_registered_time_accepts_both_formats():
    assert registered_time("2026-09-23 23:58:04").hour == 23
    assert registered_time("2026-09-27 13:58:01.0").minute == 58
    assert registered_time("2024-06-03 0:01").hour == 0
    assert registered_time("2024-06-03 00:01").minute == 1
    assert registered_time(None) is None


def test_remote_file_date_from_name():
    def file(name):
        return RemoteFile(name=name, seq="1", size_mb=1.0, modified="2026.01.01")

    assert file("S-DoT_WALK_2026.09.07-09.13.csv").data_date == date(2026, 9, 7)
    assert file("S-DoT_WALK_2022년(2022.01.03~2023.01.01).zip").data_date == date(2022, 1, 3)
    assert file("LOCAL_PEOPLE_DONG_202607.zip").data_date == date(2026, 7, 1)
    assert file("TEMP_FOREIGNER_202401.zip").data_date == date(2024, 1, 1)
