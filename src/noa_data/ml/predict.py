from datetime import datetime
from zoneinfo import ZoneInfo

import joblib
import pandas as pd
import psycopg

from noa_data.collectors.common import PROJECT_ROOT
from noa_data.ml.category import normalize_category


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
    최신 CityData 실측을 지역(area_cd) 기준으로 1건씩 저장한다.
    TourAPI content_id 매핑 여부와 무관하게 실제 관측은 보존해야 한다.
    매핑 실패 시 content_id는 NULL (FK 허용); 실측 장소는 별도 API로 조회한다.
    """
    with conn.transaction():
        conn.execute(
            """
            DELETE FROM latest_congestion l
            WHERE l.source = 'actual'
              AND NOT EXISTS (
                  SELECT 1 FROM seoul_spots s WHERE s.area_cd = l.area_cd
              )
            """
        )
        result = conn.execute(
            """
            WITH latest AS (
                SELECT DISTINCT ON (c.area_cd)
                    c.area_cd, c.congest_lvl, c.ppltn_time
                FROM citydata_population c
                WHERE c.congest_lvl IN ('여유', '보통', '약간 붐빔', '붐빔')
                ORDER BY c.area_cd, c.ppltn_time DESC
            )
            INSERT INTO latest_congestion (
                area_cd, content_id, congestion_level,
                congestion_label, source, updated_at
            )
            SELECT
                latest.area_cd, m.content_id,
                latest.congest_lvl,
                CASE latest.congest_lvl
                    WHEN '여유' THEN 0
                    WHEN '보통' THEN 1
                    WHEN '약간 붐빔' THEN 2
                    WHEN '붐빔' THEN 3
                END,
                'actual', latest.ppltn_time
            FROM latest
            JOIN seoul_spots s ON s.area_cd = latest.area_cd
            LEFT JOIN spot_mapping m ON m.area_cd = latest.area_cd
            ON CONFLICT (area_cd) WHERE source = 'actual'
            DO UPDATE SET
                content_id = EXCLUDED.content_id,
                congestion_level = EXCLUDED.congestion_level,
                congestion_label = EXCLUDED.congestion_label,
                updated_at = EXCLUDED.updated_at
            """
        )
        coverage = conn.execute(
            """
            SELECT COUNT(*) FILTER (WHERE content_id IS NOT NULL),
                   COUNT(*) FILTER (WHERE content_id IS NULL)
            FROM latest_congestion WHERE source = 'actual'
            """
        ).fetchone()
    print(
        f"actual 혼잡도 동기화: {result.rowcount:,} "
        f"(TourAPI 매핑 {coverage[0]:,}, 미매핑 지역 {coverage[1]:,})"
    )
    return result.rowcount


def _geo_features(rows):
    """서울 위경도를 근사 미터 좌표로 바꾼다 (KNN 거리용)."""
    import numpy as np

    return np.asarray(
        [[float(lon) * 88400.0, float(lat) * 111000.0] for lon, lat in rows],
        dtype=float,
    )


def _spatial_knn_estimates(reference, targets):
    """
    관측 장소를 공간상 최근접 이웃으로 학습하는 KNN 시범 모델.
    신뢰도 검증된 시간/장소 일반화 모델이 아니므로 별도 플래그로 저장한다.
    데이터 불균형 때문에 존재하지 않은 혼잡 클래스를 만들어내지 않는다.
    """
    from sklearn.neighbors import KNeighborsClassifier

    if len(reference) < 2 or len({int(r[2]) for r in reference}) < 2:
        raise ValueError("시범 KNN 학습에 서로 다른 혼잡도 2단계 이상의 실제 관측이 필요합니다.")

    x_ref = _geo_features([(r[0], r[1]) for r in reference])
    y_ref = [int(r[2]) for r in reference]
    x_target = _geo_features(targets)
    n = min(3, len(reference))
    model = KNeighborsClassifier(n_neighbors=n, weights="distance")
    model.fit(x_ref, y_ref)
    labels = model.predict(x_target)
    distances, _ = model.kneighbors(x_target, n_neighbors=1)
    return [int(v) for v in labels], [round(float(row[0]), 1) for row in distances]


def _prediction_targets(conn: psycopg.Connection):
    return conn.execute(
        """
        SELECT t.content_id, t.category, t.mapx, t.mapy
        FROM tour_spots t
        LEFT JOIN spot_mapping m ON m.content_id = t.content_id
        WHERE m.content_id IS NULL
          AND t.mapx IS NOT NULL
          AND t.mapy IS NOT NULL
        ORDER BY t.content_id
        """
    ).fetchall()


def _publish_predictions(conn, rows, labels, *, verified, method, distances=None):
    """시범/검증 모델 모두 같은 서비스 테이블에 예측 출처를 기록한다."""
    with conn.transaction():
        # 매핑된 실제 관측 장소 및 사라진 관광지의 오래된 예측 정리.
        conn.execute(
            """
            DELETE FROM latest_congestion p
            WHERE p.source = 'predicted'
              AND (NOT EXISTS (
                  SELECT 1 FROM tour_spots t WHERE t.content_id = p.content_id
              ) OR EXISTS (
                  SELECT 1 FROM spot_mapping m WHERE m.content_id = p.content_id
              ))
            """
        )
        count = 0
        for i, (content_id, _category, _mapx, _mapy) in enumerate(rows):
            label = int(labels[i])
            if label not in LABEL_NAMES:
                raise ValueError(f"허용하지 않는 혼잡도 예측 클래스: {label}")
            distance = distances[i] if distances is not None else None
            result = conn.execute(
                """
                INSERT INTO latest_congestion (
                    area_cd, content_id, congestion_level, congestion_label,
                    source, updated_at, prediction_verified, prediction_method,
                    reference_distance_m
                )
                VALUES (NULL, %s, %s, %s, 'predicted', CURRENT_TIMESTAMP, %s, %s, %s)
                ON CONFLICT (content_id) WHERE source = 'predicted'
                DO UPDATE SET
                    congestion_level = EXCLUDED.congestion_level,
                    congestion_label = EXCLUDED.congestion_label,
                    updated_at = EXCLUDED.updated_at,
                    prediction_verified = EXCLUDED.prediction_verified,
                    prediction_method = EXCLUDED.prediction_method,
                    reference_distance_m = EXCLUDED.reference_distance_m
                """,
                (content_id, LABEL_NAMES[label], label, verified, method, distance),
            )
            count += result.rowcount
    return count


def _experimental_predictions(conn):
    rows = _prediction_targets(conn)
    if not rows:
        print("시범 ML 예측 대상 관광지가 없습니다.")
        return 0

    # 지역 자체의 경계를 우선 사용한다. 매핑된 TourAPI 장소가 없어도
    # 실측 관측 지역을 공간 KNN의 학습 기준점으로 사용할 수 있다.
    reference = conn.execute(
        """
        SELECT
            COALESCE(
                ST_X(ST_PointOnSurface(c.boundary::geometry)), t.mapx
            ) AS longitude,
            COALESCE(
                ST_Y(ST_PointOnSurface(c.boundary::geometry)), t.mapy
            ) AS latitude,
            a.congestion_label
        FROM latest_congestion a
        JOIN citydata_area c ON c.area_cd = a.area_cd
        LEFT JOIN spot_mapping m ON m.area_cd = a.area_cd
        LEFT JOIN tour_spots t ON t.content_id = m.content_id
        WHERE a.source = 'actual'
          AND a.congestion_label BETWEEN 0 AND 3
          AND (
              c.boundary IS NOT NULL
              OR (t.mapx IS NOT NULL AND t.mapy IS NOT NULL)
          )
        ORDER BY a.area_cd
        """
    ).fetchall()
    print(f"KNN 공간 좌표 확보한 실측 지역: {len(reference):,}곳")
    try:
        labels, distances = _spatial_knn_estimates(
            reference, [(r[2], r[3]) for r in rows],
        )
    except ValueError as exc:
        print(f"시범 KNN 보류: {exc}")
        return 0

    count = _publish_predictions(
        conn, rows, labels, verified=False,
        method="spatial_knn_experimental", distances=distances,
    )
    print(
        f"시범 공간 KNN 예측: {count:,}건 "
        f"(실측 {len(reference)}곳 참조, 미검증 참고 추정)"
    )
    return count


def sync_predicted(conn: psycopg.Connection) -> int:
    """검증된 RF가 있으면 사용하고, 없으면 실측 기반 KNN 시범 추정을 제공한다."""
    if MODEL_PATH.exists():
        artifact = joblib.load(MODEL_PATH)
    else:
        artifact = None

    if (
        isinstance(artifact, dict)
        and artifact.get("validated") is True
        and artifact.get("feature_columns")
        == ["category", "mapx", "mapy", "hour", "day_of_week"]
    ):
        model = artifact["model"]
        rows = _prediction_targets(conn)
        if not rows:
            return 0
        now = datetime.now(KST)
        features = pd.DataFrame(
            [
                {
                    "category": normalize_category(category),
                    "mapx": float(mapx),
                    "mapy": float(mapy),
                    "hour": now.hour,
                    "day_of_week": now.weekday(),
                }
                for _cid, category, mapx, mapy in rows
            ]
        )
        labels = model.predict(features)
        count = _publish_predictions(
            conn, rows, labels, verified=True, method="validated_random_forest",
        )
        print(f"검증된 RandomForest 예측: {count:,}건")
        return count

    print("검증된 RF 모델 부족 → 실제 관측에 기반한 미검증 KNN 시범 예측 실행")
    return _experimental_predictions(conn)


def refresh_congestion(conn: psycopg.Connection) -> tuple[int, int]:
    actual = sync_actual(conn)
    predicted = sync_predicted(conn)
    return actual, predicted
