from pathlib import Path

import pandas as pd
import psycopg

from noa_data.collectors.common import PROJECT_ROOT


ARTIFACT_DIR = PROJECT_ROOT / "artifacts"
DATASET_PATH = ARTIFACT_DIR / "congestion_training_dataset.csv"

LABELS = {
    "여유": 0,
    "보통": 1,
    "약간 붐빔": 2,
    "붐빔": 3,
}


def build_dataset(conn: psycopg.Connection) -> pd.DataFrame:
    """
    CityData의 실제 혼잡도를 정답(label)으로 사용해 V1 학습 데이터셋을 만든다.

    현재 V1 feature:
    - category
    - mapx / mapy
    - hour
    - day_of_week

    추후 V2에서는 이 함수에서 S-DoT, 지하철/버스, 생활인구,
    외국인, 날씨, 공휴일, KTO 집중률을 같은 시각 기준으로 추가한다.
    """

    query = """
        SELECT
            c.area_cd,
            m.content_id,
            t.name,
            t.category,
            t.mapx,
            t.mapy,
            c.ppltn_time AS collected_at,
            EXTRACT(
                HOUR FROM (
                    c.ppltn_time AT TIME ZONE 'Asia/Seoul'
                )
            )::INTEGER AS hour,
            (
                EXTRACT(
                    ISODOW FROM (
                        c.ppltn_time AT TIME ZONE 'Asia/Seoul'
                    )
                )::INTEGER - 1
            ) AS day_of_week,
            c.congest_lvl AS congestion_level
        FROM citydata_population c
        JOIN spot_mapping m
          ON m.area_cd = c.area_cd
        JOIN tour_spots t
          ON t.content_id = m.content_id
        WHERE
            c.congest_lvl IN ('여유', '보통', '약간 붐빔', '붐빔')
            AND t.category IS NOT NULL
            AND t.mapx IS NOT NULL
            AND t.mapy IS NOT NULL
        ORDER BY c.ppltn_time, c.area_cd
    """

    # 서비스 실제 혼잡도(117곳)와 ML 학습가능 장소(68곳)의 차이를 원인별로 계측한다.
    # 임의 좌표나 카테고리를 채워서 학습행을 부풀리지 않는다.
    diagnostics = conn.execute("""
        SELECT
            COUNT(*) AS actual_rows,
            COUNT(*) FILTER (WHERE m.content_id IS NULL) AS no_mapping,
            COUNT(*) FILTER (WHERE t.content_id IS NULL) AS no_tour_spot,
            COUNT(*) FILTER (WHERE t.category IS NULL) AS no_category,
            COUNT(*) FILTER (WHERE t.mapx IS NULL OR t.mapy IS NULL) AS no_coordinates,
            COUNT(*) FILTER (
                WHERE t.content_id IS NOT NULL
                  AND t.category IS NOT NULL
                  AND t.mapx IS NOT NULL AND t.mapy IS NOT NULL
            ) AS eligible
        FROM citydata_population c
        LEFT JOIN spot_mapping m ON m.area_cd = c.area_cd
        LEFT JOIN tour_spots t ON t.content_id = m.content_id
        WHERE c.congest_lvl IN ('여유', '보통', '약간 붐빔', '붐빔')
    """).fetchone()
    print(
        "ML 데이터 누락 진단: "
        f"실제라벨={diagnostics[0]}, 매핑없음={diagnostics[1]}, "
        f"관광지없음={diagnostics[2]}, 카테고리없음={diagnostics[3]}, "
        f"좌표없음={diagnostics[4]}, 학습가능={diagnostics[5]}"
    )
    rows = conn.execute(query).fetchall()

    columns = [
        "area_cd",
        "content_id",
        "name",
        "category",
        "mapx",
        "mapy",
        "collected_at",
        "hour",
        "day_of_week",
        "congestion_level",
    ]

    df = pd.DataFrame(rows, columns=columns)

    if df.empty:
        raise RuntimeError(
            "학습 가능한 CityData가 없습니다. "
            "먼저 CityData 수집/적재와 service sync를 실행하세요."
        )

    df["congestion_label"] = df["congestion_level"].map(LABELS)

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(DATASET_PATH, index=False, encoding="utf-8-sig")

    print(f"학습 데이터셋: {len(df):,}행 → {DATASET_PATH}")
    print(df["congestion_label"].value_counts().sort_index())
    print(
        f"관측 장소 {df['area_cd'].nunique()}곳, "
        f"서로 다른 수집 시점 {df['collected_at'].nunique()}개"
    )
    print("참고: 원본 CityData 121곳과 매핑 117곳은 학습 가능한 라벨 행 수와 같지 않습니다.")

    return df
