import joblib
import pandas as pd

from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import balanced_accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from noa_data.collectors.common import PROJECT_ROOT
from noa_data.ml.features import DATASET_PATH


MODEL_PATH = PROJECT_ROOT / "artifacts" / "congestion_model.pkl"
FEATURE_COLUMNS = ["category", "mapx", "mapy", "hour", "day_of_week"]
LABELS = [0, 1, 2, 3]

# 한 번 수집한 실시간 스냅샷만으로 만든 모델을 실서비스에 내보내지 않는다.
MIN_ROWS = 500
MIN_PER_CLASS = 20
MIN_DAYS = 7
MIN_DISTINCT_TIMES = 24


def validate_training_data(df: pd.DataFrame) -> list[str]:
    problems = []
    required = FEATURE_COLUMNS + ["congestion_label", "collected_at", "area_cd"]
    missing = sorted(set(required) - set(df.columns))
    if missing:
        return [f"필수 학습 컬럼 누락: {', '.join(missing)}"]

    valid = df.dropna(subset=FEATURE_COLUMNS + ["congestion_label", "collected_at"])
    counts = valid["congestion_label"].value_counts()
    if len(valid) < MIN_ROWS:
        problems.append(f"표본 부족: {len(valid)}/{MIN_ROWS}행")
    for label in LABELS:
        count = int(counts.get(label, 0))
        if count < MIN_PER_CLASS:
            problems.append(f"혼잡도 클래스 {label} 부족: {count}/{MIN_PER_CLASS}행")

    times = pd.to_datetime(valid["collected_at"], errors="coerce", utc=True).dropna()
    if times.nunique() < MIN_DISTINCT_TIMES:
        problems.append(f"서로 다른 수집 시점 부족: {times.nunique()}/{MIN_DISTINCT_TIMES}")
    if times.empty or (times.max() - times.min()).total_seconds() < MIN_DAYS * 86400:
        problems.append(f"기간 부족: 최소 {MIN_DAYS}일의 관측 필요")
    if valid["area_cd"].nunique() < 20:
        problems.append("관측 장소 부족: 최소 20곳 필요")
    return problems


def train_model(df: pd.DataFrame | None = None):
    if df is None:
        if not DATASET_PATH.exists():
            raise FileNotFoundError(f"학습 데이터셋이 없습니다: {DATASET_PATH}")
        df = pd.read_csv(DATASET_PATH)

    problems = validate_training_data(df)
    if problems:
        raise ValueError("학습 보류 (잘못된 모델 생성 방지):\n- " + "\n- ".join(problems))

    data = df.dropna(subset=FEATURE_COLUMNS + ["congestion_label", "collected_at"]).copy()
    # 시간 순서 검증: 같은 시각/장소의 값이 학습과 검증에 섞이지 않도록
    # 최신 20% 시점을 검증용으로 고정한다.
    data["_time"] = pd.to_datetime(data["collected_at"], utc=True)
    unique_times = sorted(data["_time"].unique())
    split_at = unique_times[max(1, int(len(unique_times) * 0.8))]
    train = data[data["_time"] < split_at]
    test = data[data["_time"] >= split_at]
    if train.empty or test.empty or set(LABELS) - set(train["congestion_label"].unique()):
        raise ValueError("시간순 분할 후 학습 데이터에 4개 클래스가 모두 존재하지 않습니다. 학습 보류.")
    if set(LABELS) - set(test["congestion_label"].unique()):
        raise ValueError("시간순 검증 데이터에 4개 클래스가 모두 존재하지 않습니다. 학습 보류.")

    preprocessor = ColumnTransformer(
        transformers=[
            ("category", OneHotEncoder(handle_unknown="ignore"), ["category"]),
            ("numeric", "passthrough", ["mapx", "mapy", "hour", "day_of_week"]),
        ]
    )
    pipeline = Pipeline(steps=[
        ("preprocessor", preprocessor),
        ("model", RandomForestClassifier(
            n_estimators=300,
            class_weight="balanced",
            random_state=42,
            n_jobs=-1,
        )),
    ])
    pipeline.fit(train[FEATURE_COLUMNS], train["congestion_label"])
    pred = pipeline.predict(test[FEATURE_COLUMNS])
    balanced = balanced_accuracy_score(test["congestion_label"], pred)
    print(f"시간순 검증 balanced accuracy: {balanced:.4f}")
    print(classification_report(test["congestion_label"], pred, labels=LABELS, zero_division=0))
    print(confusion_matrix(test["congestion_label"], pred, labels=LABELS))

    # 일정 기준 아래의 모델을 저장/배포하지 않는다.
    if balanced < 0.45:
        raise ValueError(f"검증 점수 미달 ({balanced:.4f} < 0.45). 기존 모델은 변경하지 않습니다.")

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    # 기존의 단순 Pipeline pickle은 검증 여부를 알 수 없으므로 사용하지 않는다.
    joblib.dump({
        "model": pipeline,
        "validated": True,
        "feature_columns": FEATURE_COLUMNS,
        "balanced_accuracy": float(balanced),
        "training_rows": len(train),
        "validation_rows": len(test),
    }, MODEL_PATH)
    print(f"검증된 모델 저장: {MODEL_PATH}")
    return pipeline
