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

    return df
