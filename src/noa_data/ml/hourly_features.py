"""Leakage-aware multi-source *area-level* hourly congestion features.

Sources: hourly CityData labels, weather/PM, traffic, parking, S-DoT, published
monthly subway/bus, living/foreigner population, ASOS and festivals/holidays.
Source timestamps determine what would have been known when each prediction
was made. If no safe matching observation exists, keep NaN (no synthetic data).

NOT tourist-site-specific ground truth. Historical CityData area congestion
is the only observed target, and nearby signals are proxies.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

KST = ZoneInfo("Asia/Seoul")
LABELS = {"여유": 0, "보통": 1, "약간 붐빔": 2, "붐빔": 3}
HORIZONS = tuple(range(1, 13))
MAX_DAYS = 30

INPUT_COLUMNS = [
    "horizon", "hour", "day_of_week", "month", "is_weekend", "is_holiday",
    "longitude", "latitude", "last_level", "level_3h_ago",
    "temp", "humidity", "pm10", "pm25", "road_speed", "parking_availability",
    "sdot_people", "subway_board", "subway_alight", "bus_board", "bus_alight",
    "living_population", "foreign_population", "asos_temp_yesterday",
    "festival_count",
]
OPTIONAL = {
    "weather": ["temp", "humidity", "pm10", "pm25"],
    "traffic": ["road_speed"],
    "parking": ["parking_availability"],
    "sdot": ["sdot_people"],
    "subway_monthly": ["subway_board", "subway_alight"],
    "bus_monthly": ["bus_board", "bus_alight"],
    "living_monthly": ["living_population"],
    "foreigner_monthly": ["foreign_population"],
    "asos_yesterday": ["asos_temp_yesterday"],
    "festivals": ["festival_count"],
}
# Known-upcoming features only; no future weather/road observations.
PROVENANCE = {
    "citydata_population": "area-level label + last observed class; never target-hour class",
    "citydata_forecast": "official forecasts are kept separate from supervised target labels",
    "citydata_weather": "as-of observed AND collected timestamps; max age 3h",
    "citydata_road_traffic": "as-of observed AND collected timestamps; max age 90m",
    "citydata_parking": "as-of observed AND collected timestamps; max age 90m",
    "sdot_observation": "mapped-nearby sensors as-of observed AND collected; max age 2h",
    "subway_ridership": "monthly hourly sums; conservative 3-month publication lag",
    "bus_ridership": "monthly hourly sums; conservative 3-month publication lag",
    "living_population": "monthly hourly historical proxy; conservative 3-month publication lag",
    "foreigner_population_dong": "monthly hourly proxy; conservative 3-month publication lag",
    "weather_observation": "24h-old ASOS reference, never target-time weather",
    "tour_festival": "known at issue time + geographically close and target-date active",
    "holiday": "target-day holiday only when collected before issue time",
    "kto_concentration": "not included without robust tourist/area linkage and publish-time auditing",
    "kto_region_visitor": "not included without reliable publication date",
    "kto_hub_place": "static metadata only; not a time-varying population signal",
    "kto_related_place": "tourist relationship metadata; not a validated area hourly signal",
    "admin_dong": "static location link in place_nearby, not a time-series label",
    "tour_place": "static tourism locations; CityData area labels are not site-specific",
}


def _fetch(conn, sql, params=(), columns=None):
    rows = conn.execute(sql, params).fetchall()
    return pd.DataFrame(rows, columns=columns)


def _utc(series):
    return pd.to_datetime(series, utc=True, errors="coerce")


def _base(conn, now, days):
    df = _fetch(conn, """
        SELECT p.area_cd, p.ppltn_time, p.collected_at, p.congest_lvl,
               COALESCE(ST_X(ST_PointOnSurface(a.boundary::geometry)), t.mapx::float)
                 AS longitude,
               COALESCE(ST_Y(ST_PointOnSurface(a.boundary::geometry)), t.mapy::float)
                 AS latitude
        FROM citydata_population p
        JOIN citydata_area a ON a.area_cd = p.area_cd
        LEFT JOIN spot_mapping m ON m.area_cd = p.area_cd
        LEFT JOIN tour_spots t ON t.content_id = m.content_id
        WHERE p.ppltn_time BETWEEN %s AND %s
          AND p.congest_lvl IN ('여유','보통','약간 붐빔','붐빔')
        ORDER BY p.area_cd, p.ppltn_time
    """, (now - timedelta(days=days), now),
        ["area_cd", "observation", "collected", "label", "longitude", "latitude"])
    if df.empty:
        return df
    df["observation"] = _utc(df["observation"])
    df["collected"] = _utc(df["collected"])
    df["slot"] = df["observation"].dt.floor("h")
    # A 15:50 observation is not usable at 15:00. Use its actual
    # collector timestamp as the prediction issue time, rounded UP to
    # the next hour. Future labels are strictly later than this time.
    df["issue_time"] = df["collected"].dt.ceil("h")
    # Some feeds claim a past observation but become available later.
    df = df[(df["observation"] <= df["issue_time"]) & df["longitude"].notna()
            & df["latitude"].notna()].copy()
    df = df.sort_values(["area_cd", "slot", "observation"])
    df = df.drop_duplicates(["area_cd", "slot"], keep="last")
    df["last_level"] = df["label"].map(LABELS).astype(int)
    # Do not accidentally use the prior *row* as a prior-hour label across gaps.
    previous = df.groupby("area_cd", sort=False)
    df["level_3h_ago"] = previous["last_level"].shift(3)
    old_slot = previous["slot"].shift(3)
    df.loc[df["slot"] - old_slot != pd.Timedelta(hours=3), "level_3h_ago"] = np.nan
    return df


def _observed_feature(base, conn, sql, columns, max_age):
    """Left-as-of by area and *availability time*, not target timestamp."""
    out = base.copy()
    features = columns[3:]
    raw = _fetch(conn, sql, (), columns)
    if raw.empty:
        for feature in features:
            out[feature] = np.nan
        return out
    raw["observed"] = _utc(raw["observed"])
    raw["collected"] = _utc(raw["collected"])
    raw["available"] = raw[["observed", "collected"]].max(axis=1)
    raw = raw.dropna(subset=["area_cd", "observed", "available"])
    if raw.empty:
        for feature in features:
            out[feature] = np.nan
        return out
    # Pandas merge_asof requires time-key sort globally, even with 'by'.
    out = out.sort_values(["issue_time", "area_cd"])
    raw = raw.sort_values(["available", "area_cd"])
    out = pd.merge_asof(
        out, raw[["area_cd", "observed", "available", *features]],
        left_on="issue_time", right_on="available", by="area_cd",
        direction="backward",
    )
    expired = out["issue_time"] - out["observed"] > pd.Timedelta(max_age)
    for feature in features:
        out.loc[expired, feature] = np.nan
    return out.drop(columns=["observed", "available"])


def _optional_sources(df, conn, now, days):
    from_ts = now - timedelta(days=days + 2)
    sources = [
        ("""SELECT area_cd, weather_time, collected_at, temperature,
                   humidity, pm10, pm25 FROM citydata_weather
            WHERE weather_time >= TIMESTAMPTZ '""" + from_ts.isoformat() + """'""",
         ["area_cd", "observed", "collected", "temp", "humidity", "pm10", "pm25"], "3h"),
        ("""SELECT area_cd, observed_at, collected_at, avg_speed
            FROM citydata_road_traffic
            WHERE observed_at >= TIMESTAMPTZ '""" + from_ts.isoformat() + """'""",
         ["area_cd", "observed", "collected", "road_speed"], "90min"),
        ("""SELECT area_cd, date_trunc('hour', observed_at), MAX(collected_at),
                   AVG(available_count::float / NULLIF(capacity,0))
            FROM citydata_parking
            WHERE observed_at >= TIMESTAMPTZ '""" + from_ts.isoformat() + """'
            GROUP BY area_cd, date_trunc('hour', observed_at)""",
         ["area_cd", "observed", "collected", "parking_availability"], "90min"),
        ("""SELECT m.area_cd, date_trunc('hour', o.observed_at),
                   MAX(o.collected_at), AVG(o.visitor_count)::float
            FROM sdot_observation o
            JOIN place_nearby n ON n.target_type='sdot_sensor'
                             AND n.target_id = o.sensor_code::text
            JOIN spot_mapping m ON m.content_id = n.content_id
            WHERE o.observed_at >= TIMESTAMPTZ '""" + from_ts.isoformat() + """'
              AND n.distance_m <= 1000
            GROUP BY m.area_cd, date_trunc('hour', o.observed_at)""",
         ["area_cd", "observed", "collected", "sdot_people"], "2h"),
    ]
    for sql, cols, max_age in sources:
        df = _observed_feature(df, conn, sql, cols, max_age)
    return df


def _monthly_proxies(df, conn, now):
    """Only historical data released 3+ months before prediction issuance."""
    queries = [
        ("subway_board", "subway_alight", """
            SELECT m.area_cd, r.use_month, r.hour,
                   AVG(r.get_on)::float, AVG(r.get_off)::float
            FROM subway_ridership r
            JOIN subway_station s ON s.station_key = r.station_key
            JOIN place_nearby n ON n.target_type='subway_station'
                              AND n.target_id=s.station_id
            JOIN spot_mapping m ON m.content_id=n.content_id
            WHERE r.use_month >= %s
            GROUP BY m.area_cd,r.use_month,r.hour
        """),
        ("bus_board", "bus_alight", """
            SELECT m.area_cd, r.use_month, r.hour,
                   AVG(r.get_on)::float, AVG(r.get_off)::float
            FROM bus_ridership r
            JOIN place_nearby n ON n.target_type='bus_stop'
                              AND n.target_id=r.stop_id
            JOIN spot_mapping m ON m.content_id=n.content_id
            WHERE r.use_month >= %s
            GROUP BY m.area_cd,r.use_month,r.hour
        """),
        ("living_population", None, """
            SELECT m.area_cd, date_trunc('month', d.base_date)::date, d.hour,
                   AVG(d.total)::float, NULL::float
            FROM living_population d
            JOIN place_nearby n ON n.target_type='admin_dong'
                              AND n.target_id=d.adm_code
            JOIN spot_mapping m ON m.content_id=n.content_id
            WHERE d.base_date >= %s
            GROUP BY m.area_cd,date_trunc('month',d.base_date),d.hour
        """),
        ("foreign_population", None, """
            SELECT m.area_cd, date_trunc('month',d.base_date)::date,d.hour,
                   AVG(d.total)::float,NULL::float
            FROM foreigner_population_dong d
            JOIN place_nearby n ON n.target_type='admin_dong'
                              AND n.target_id=d.adm_code
            JOIN spot_mapping m ON m.content_id=n.content_id
            WHERE d.base_date >= %s
            GROUP BY m.area_cd,date_trunc('month',d.base_date),d.hour
        """),
    ]
    # Published monthly datasets do not require scanning years of historical
    # records at every 15-minute realtime inference call.
    oldest = (now - timedelta(days=220)).date()
    for name, second, sql in queries:
        raw = _fetch(conn, sql, (oldest,),
                     ["area_cd","use_month","hour","first","second"])
        if raw.empty:
            df[name] = np.nan
            if second: df[second] = np.nan
            continue
        raw["available"] = _utc(pd.to_datetime(raw["use_month"])) + pd.DateOffset(months=3)
        raw["available"] = _utc(raw["available"])
        raw = raw.sort_values(["available", "area_cd", "hour"])
        left = df[["area_cd", "issue_time", "hour"]].copy()
        left["_original_position"] = np.arange(len(df))
        # Hour-of-day of intended target is known; use target-hour historical profile.
        left = left.sort_values(["issue_time", "area_cd", "hour"])
        joined = pd.merge_asof(
            left, raw[["area_cd","hour","available","first","second"]],
            left_on="issue_time", right_on="available",
            by=["area_cd","hour"], direction="backward")
        joined = joined.sort_values("_original_position")
        df[name] = joined["first"].to_numpy()
        if second:
            df[second] = joined["second"].to_numpy()
    return df


def _known_future(df, conn):
    target = df["forecast_at"].dt.tz_convert(KST)
    df["hour"] = target.dt.hour.astype(int)
    df["day_of_week"] = target.dt.weekday.astype(int)
    df["month"] = target.dt.month.astype(int)
    df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)
    days = target.dt.date.tolist()
    # Temporary holidays announced later must not leak to earlier training.
    holiday_rows = conn.execute(
        """SELECT holiday_date, MIN(collected_at)
           FROM holiday WHERE is_holiday IS TRUE
           GROUP BY holiday_date""").fetchall()
    known_holidays = {
        day: pd.Timestamp(first_known).tz_convert("UTC")
        for day, first_known in holiday_rows
    }
    df["is_holiday"] = [
        int(day in known_holidays and known_holidays[day] <= issue)
        for day, issue in zip(days, df["issue_time"])
    ]

    festival_rows = conn.execute("""
        SELECT a.area_cd, f.event_start_date, f.event_end_date, f.collected_at
        FROM citydata_area a
        JOIN tour_festival f ON f.lang='ko'
            AND f.location IS NOT NULL
            AND a.boundary IS NOT NULL
            AND ST_DWithin(a.boundary, f.location, 3000)
        WHERE f.event_start_date IS NOT NULL AND f.event_end_date IS NOT NULL
    """).fetchall()
    grouped = {}
    for area, start, end, collected in festival_rows:
        grouped.setdefault(area, []).append((start, end, collected))
    df["festival_count"] = [
        sum(start <= target_date <= end and pd.Timestamp(collected).tz_convert("UTC") <= issue
            for start, end, collected in grouped.get(area, ()))
        for area, target_date, issue in zip(df["area_cd"], days, df["issue_time"])
    ]
    return df


def make_features(conn, now=None, days=MAX_DAYS, sample_step=1):
    """Construct historical origin-hour features once; used for train and inference.

    Training can subsample every second hourly origin to bound RAM on small
    servers without altering the real-time inference path.
    """
    now = now or datetime.now(KST)
    base = _base(conn, now, days)
    if base.empty:
        return base
    if sample_step > 1:
        base = base[
            base.groupby("area_cd", sort=False).cumcount() % sample_step == 0
        ].copy()
    base = _optional_sources(base, conn, now, days)
    return base


def expand_forecast(base, conn, horizons=HORIZONS, with_labels=True):
    """Pooled direct horizon model; all labels strictly after issue-hour evidence."""
    if base.empty:
        return base
    # The source labels are un-sampled hourly observations. Predictions
    # must always target future hours relative to the issue timestamp.
    # Training origin rows may be sampled (every 2h). Target labels must
    # NOT be sampled, or odd horizons vanish and 12h evaluation is biased.
    if with_labels:
        labels_raw = _fetch(
            conn,
            """SELECT DISTINCT ON (area_cd, date_trunc('hour', ppltn_time))
                      area_cd, date_trunc('hour', ppltn_time), congest_lvl
               FROM citydata_population
               WHERE ppltn_time >= %s AND ppltn_time <= %s
                 AND congest_lvl IN ('여유','보통','약간 붐빔','붐빔')
               ORDER BY area_cd, date_trunc('hour', ppltn_time),
                        ppltn_time DESC""",
            (base["issue_time"].min().to_pydatetime(),
             (base["issue_time"].max() + pd.Timedelta(hours=max(horizons))).to_pydatetime()),
            ["area_cd", "forecast_at", "label"],
        )
        labels_raw["forecast_at"] = _utc(labels_raw["forecast_at"])
        labels_raw["congestion_label"] = labels_raw["label"].map(LABELS)
        hourly_labels = labels_raw[["area_cd", "forecast_at", "congestion_label"]]
    else:
        hourly_labels = None
    frames = []
    for h in horizons:
        part = base.copy()
        part["horizon"] = h
        part["forecast_at"] = part["issue_time"] + pd.Timedelta(hours=h)
        frames.append(part)
    df = pd.concat(frames, ignore_index=True)
    df = _known_future(df, conn)
    df = _monthly_proxies(df, conn, datetime.now(KST))
    # ASOS observation is published later than its measurement; when an exact
    # publication timestamp isn't recorded use yesterday's hourly city mean
    # rather than target-hour future weather.
    city_weather = _fetch(conn, """
        SELECT date_trunc('hour', observed_at), AVG(temperature)::float
        FROM weather_observation
        WHERE observed_at >= now() - interval '34 days'
          AND temperature BETWEEN -50 AND 55
        GROUP BY date_trunc('hour', observed_at)
        ORDER BY date_trunc('hour', observed_at)
    """, (), ["observed", "temperature"])
    df["asos_temp_yesterday"] = np.nan
    if not city_weather.empty:
        city_weather["available"] = _utc(city_weather["observed"]) + pd.Timedelta(days=1)
        l = df[["issue_time"]].copy()
        l["_position"] = np.arange(len(l))
        joined = pd.merge_asof(
            l.sort_values("issue_time"),
            city_weather[["available","temperature"]].sort_values("available"),
            left_on="issue_time",right_on="available",direction="backward",
            tolerance=pd.Timedelta(hours=3))
        df["asos_temp_yesterday"] = joined.sort_values("_position")["temperature"].to_numpy()
    # Future label is joined only AFTER all feature sources are assembled.
    if with_labels:
        df = df.merge(hourly_labels, on=["area_cd", "forecast_at"], how="inner",
                      validate="many_to_one")
        # A target hour at or before issuance would be label leakage.
        df = df[df["forecast_at"] > df["issue_time"]]
        df = df[df["congestion_label"].notna()]
    return df
