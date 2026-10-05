from datetime import datetime
from zoneinfo import ZoneInfo

import joblib
import pandas as pd
import psycopg

from noa_data.collectors.common import PROJECT_ROOT


KST = ZoneInfo("Asia/Seoul")
MODEL_PATH = PROJECT_ROOT / "artifacts" / "congestion_model.pkl"

LABELS = {
    "여유": 0,
    "보통": 1,
    "약간 붐빔": 2,
    "붐빔": 3,
}

LABEL_NAMES = {
    0: "여유",
    1: "보통",
    2: "약간 붐빔",
    3: "붐빔",
}


def sync_actual(conn: psycopg.Connection) -> int:
    """
    citydata_population의 장소별 최신 실제 혼잡도를 latest_congestion에 반영한다.
    """
    with conn.transaction():
        conn.execute(
            """
            DELETE FROM latest_congestion l
            WHERE l.source = 'actual'
              AND NOT EXISTS (
                  SELECT 1
                  FROM spot_mapping m
                  WHERE m.area_cd = l.area_cd
              )
            """
        )

        result = conn.execute(
            """
            WITH latest AS (
                SELECT DISTINCT ON (c.area_cd)
                    c.area_cd,
                    c.congest_lvl,
                    c.ppltn_time
                FROM citydata_population c
                WHERE c.congest_lvl IN ('여유', '보통', '약간 붐빔', '붐빔')
                ORDER BY c.area_cd, c.ppltn_time DESC
            )
            INSERT INTO latest_congestion (
                area_cd,
                content_id,
                congestion_level,
                congestion_label,
                source,
                updated_at
            )
            SELECT
                latest.area_cd,
                m.content_id,
                latest.congest_lvl,
                CASE latest.congest_lvl
                    WHEN '여유' THEN 0
                    WHEN '보통' THEN 1
                    WHEN '약간 붐빔' THEN 2
                    WHEN '붐빔' THEN 3
                END,
                'actual',
                latest.ppltn_time
            FROM latest
            JOIN spot_mapping m
              ON m.area_cd = latest.area_cd
            ON CONFLICT (area_cd)
            WHERE source = 'actual'
            DO UPDATE SET
                content_id = EXCLUDED.content_id,
                congestion_level = EXCLUDED.congestion_level,
                congestion_label = EXCLUDED.congestion_label,
                updated_at = EXCLUDED.updated_at
            """
        )

    print(f"actual 혼잡도 동기화: {result.rowcount:,}")
    return result.rowcount


def sync_predicted(conn: psycopg.Connection) -> int:
    """
    CityData와 직접 매핑되지 않은 TourAPI 관광지의 현재 혼잡도를 ML로 예측한다.
    """
    if not MODEL_PATH.exists():
        print(f"예측 모델 없음 - predicted 생략: {MODEL_PATH}")
        return 0

    model = joblib.load(MODEL_PATH)

    rows = conn.execute(
        """
        SELECT
            t.content_id,
            t.name,
            t.category,
            t.mapx,
            t.mapy
        FROM tour_spots t
        LEFT JOIN spot_mapping m
          ON m.content_id = t.content_id
        WHERE
            m.content_id IS NULL
            AND t.category IS NOT NULL
            AND t.mapx IS NOT NULL
            AND t.mapy IS NOT NULL
        ORDER BY t.content_id
        """
    ).fetchall()

    if not rows:
        print("predicted 대상 관광지가 없습니다.")
        return 0

    now = datetime.now(KST)

    features = pd.DataFrame(
        [
            {
                "category": category,
                "mapx": float(mapx),
                "mapy": float(mapy),
                "hour": now.hour,
                "day_of_week": now.weekday(),
            }
            for _, _, category, mapx, mapy in rows
        ]
    )

    predictions = model.predict(features)

    with conn.transaction():
        # actual로 전환된 관광지에는 predicted 행을 남기지 않는다.
        conn.execute(
            """
            DELETE FROM latest_congestion l
            WHERE l.source = 'predicted'
              AND EXISTS (
                  SELECT 1
                  FROM spot_mapping m
                  WHERE m.content_id = l.content_id
              )
            """
        )

        count = 0

        for (content_id, _name, _category, _mapx, _mapy), prediction in zip(
            rows,
            predictions,
        ):
            label = int(prediction)
            level = LABEL_NAMES[label]

            result = conn.execute(
                """
                INSERT INTO latest_congestion (
                    area_cd,
                    content_id,
                    congestion_level,
                    congestion_label,
                    source,
                    updated_at
                )
                VALUES (
                    NULL,
                    %s,
                    %s,
                    %s,
                    'predicted',
                    CURRENT_TIMESTAMP
                )
                ON CONFLICT (content_id)
                WHERE source = 'predicted'
                DO UPDATE SET
                    congestion_level = EXCLUDED.congestion_level,
                    congestion_label = EXCLUDED.congestion_label,
                    updated_at = EXCLUDED.updated_at
                """,
                (content_id, level, label),
            )
            count += result.rowcount

    print(f"predicted 혼잡도 동기화: {count:,}")
    return count


def refresh_congestion(conn: psycopg.Connection) -> tuple[int, int]:
    actual = sync_actual(conn)
    predicted = sync_predicted(conn)
    return actual, predicted
