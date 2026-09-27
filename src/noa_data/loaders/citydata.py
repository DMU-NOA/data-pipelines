import pandas as pd
import psycopg

from noa_data.collectors.common import load_raw
from noa_data.loaders.common import (
    integer,
    kst,
    number,
    pending_files,
    record_loaded,
    text,
    upsert,
)


PPLTN_TIME_FORMAT = "%Y-%m-%d %H:%M"

POPULATION_COLUMNS = [
    "area_cd", "ppltn_time", "congest_lvl", "congest_msg", "ppltn_min", "ppltn_max",
    "male_rate", "female_rate",
    "rate_0", "rate_10", "rate_20", "rate_30", "rate_40", "rate_50", "rate_60", "rate_70",
    "resnt_rate", "non_resnt_rate", "replace_yn", "collected_at",
]

FORECAST_COLUMNS = [
    "area_cd", "ppltn_time", "fcst_time", "congest_lvl", "ppltn_min", "ppltn_max", "collected_at",
]

WEATHER_COLUMNS = [
    "area_cd", "weather_time", "temperature", "humidity", "wind_speed", "precipitation",
    "precpt_type", "pm10", "pm25", "air_idx", "collected_at",
]

WEATHER_FORECAST_COLUMNS = [
    "area_cd", "weather_time", "fcst_time", "temperature", "precipitation", "precpt_type",
    "rain_chance", "sky_stts", "collected_at",
]


def as_list(value) -> list:
    # 원본은 값이 하나면 list 대신 dict 로 주기도 한다.
    if not value:
        return []

    return [value] if isinstance(value, dict) else value


def weather_rows(area_cd: str, payload: dict, collected_at: str) -> tuple[list, list]:
    """
    실시간 도시데이터의 날씨(WEATHER_STTS) 와 24시간 예보(FCST24HOURS) 를 행으로 바꾼다.
    """

    current_rows = []
    forecast_rows = []

    for weather in as_list(payload["CITYDATA"].get("WEATHER_STTS")):
        weather_time = kst(weather.get("WEATHER_TIME"), PPLTN_TIME_FORMAT)

        if weather_time is None:
            continue

        current_rows.append((
            area_cd,
            weather_time,
            number(weather.get("TEMP")),
            number(weather.get("HUMIDITY")),
            number(weather.get("WIND_SPD")),
            text(weather.get("PRECIPITATION")),
            text(weather.get("PRECPT_TYPE")),
            number(weather.get("PM10")),
            number(weather.get("PM25")),
            text(weather.get("AIR_IDX")),
            collected_at,
        ))

        for forecast in as_list(weather.get("FCST24HOURS")):
            fcst_time = kst(forecast.get("FCST_DT"), "%Y%m%d%H%M")

            if fcst_time is None:
                continue

            forecast_rows.append((
                area_cd,
                weather_time,
                fcst_time,
                number(forecast.get("TEMP")),
                text(forecast.get("PRECIPITATION")),
                text(forecast.get("PRECPT_TYPE")),
                number(forecast.get("RAIN_CHANCE")),
                text(forecast.get("SKY_STTS")),
                collected_at,
            ))

    return current_rows, forecast_rows


def load_areas(conn: psycopg.Connection) -> int:
    """
    121장소 목록 (서울 열린데이터광장 OA-21285 엑셀) → citydata_area
    """

    files = pending_files(conn, "seoul_files/OA-21285/*121장소 목록*.xlsx")
    total = 0

    for path in files:
        places = pd.read_excel(path).dropna(subset=["AREA_CD"])

        rows = [
            (
                text(row.AREA_CD),
                text(row.AREA_NM),
                text(row.ENG_NM),
                text(row.CATEGORY),
            )
            for row in places.itertuples()
        ]

        with conn.transaction():
            count = upsert(
                conn,
                "citydata_area",
                ["area_cd", "area_nm", "eng_nm", "category"],
                rows,
                key=["area_cd"],
            )
            record_loaded(conn, path, "citydata_area", count)

        total += count
        print(f"  citydata_area ← {path.name}: {count}")

    return total


def load_snapshots(conn: psycopg.Connection) -> int:
    """
    실시간 도시데이터 수집 파일
    → citydata_population, citydata_forecast (인구, 서울시 12시간 예측)
    → citydata_weather, citydata_weather_forecast (날씨, 24시간 예보)

    같은 인구 집계 시각(ppltn_time)을 여러 번 받아도 한 행만 남는다.
    """

    files = pending_files(conn, "seoul_citydata/*/citydata_*.json.gz")
    total = 0

    for path in files:
        record = load_raw(path)
        collected_at = record["collected_at"]
        population_rows = []
        forecast_rows = []
        weather_current_rows = []
        weather_forecast_rows = []

        for area_cd, payload in record["payload"]["places"].items():
            current, forecast = weather_rows(area_cd, payload, collected_at)
            weather_current_rows.extend(current)
            weather_forecast_rows.extend(forecast)

            statuses = payload["CITYDATA"].get("LIVE_PPLTN_STTS") or []

            if isinstance(statuses, dict):
                statuses = [statuses]

            for status in statuses:
                ppltn_time = kst(status.get("PPLTN_TIME"), PPLTN_TIME_FORMAT)

                if ppltn_time is None:
                    continue

                population_rows.append((
                    area_cd,
                    ppltn_time,
                    text(status.get("AREA_CONGEST_LVL")),
                    text(status.get("AREA_CONGEST_MSG")),
                    integer(status.get("AREA_PPLTN_MIN")),
                    integer(status.get("AREA_PPLTN_MAX")),
                    number(status.get("MALE_PPLTN_RATE")),
                    number(status.get("FEMALE_PPLTN_RATE")),
                    *(number(status.get(f"PPLTN_RATE_{age}")) for age in range(0, 80, 10)),
                    number(status.get("RESNT_PPLTN_RATE")),
                    number(status.get("NON_RESNT_PPLTN_RATE")),
                    text(status.get("REPLACE_YN")),
                    collected_at,
                ))

                forecasts = status.get("FCST_PPLTN") or []

                if isinstance(forecasts, dict):
                    forecasts = [forecasts]

                for forecast in forecasts:
                    fcst_time = kst(forecast.get("FCST_TIME"), PPLTN_TIME_FORMAT)

                    if fcst_time is None:
                        continue

                    forecast_rows.append((
                        area_cd,
                        ppltn_time,
                        fcst_time,
                        text(forecast.get("FCST_CONGEST_LVL")),
                        integer(forecast.get("FCST_PPLTN_MIN")),
                        integer(forecast.get("FCST_PPLTN_MAX")),
                        collected_at,
                    ))

        with conn.transaction():
            # 같은 집계 시각이면 값도 같으므로 처음 받은 행을 유지한다.
            population = upsert(
                conn, "citydata_population", POPULATION_COLUMNS, population_rows,
                key=["area_cd", "ppltn_time"], update=False,
            )
            forecast = upsert(
                conn, "citydata_forecast", FORECAST_COLUMNS, forecast_rows,
                key=["area_cd", "ppltn_time", "fcst_time"], update=False,
            )
            weather = upsert(
                conn, "citydata_weather", WEATHER_COLUMNS, weather_current_rows,
                key=["area_cd", "weather_time"], update=False,
            )
            weather_forecast = upsert(
                conn, "citydata_weather_forecast", WEATHER_FORECAST_COLUMNS, weather_forecast_rows,
                key=["area_cd", "weather_time", "fcst_time"], update=False,
            )
            record_loaded(conn, path, "seoul_citydata", population + forecast + weather + weather_forecast)

        total += population

    print(f"  citydata ← 파일 {len(files)}개")

    return total
