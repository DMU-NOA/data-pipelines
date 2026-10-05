import joblib
import pandas as pd

from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from noa_data.collectors.common import PROJECT_ROOT
from noa_data.ml.features import DATASET_PATH


MODEL_PATH = PROJECT_ROOT / "artifacts" / "congestion_model.pkl"


def train_model(df: pd.DataFrame | None = None):
    """
    기존 noa-backend ML V1과 같은 RandomForest 모델을 학습한다.
    """

    if df is None:
        if not DATASET_PATH.exists():
            raise FileNotFoundError(
                f"학습 데이터셋이 없습니다: {DATASET_PATH}"
            )
        df = pd.read_csv(DATASET_PATH)

    feature_columns = [
        "category",
        "mapx",
        "mapy",
        "hour",
        "day_of_week",
    ]
    target_column = "congestion_label"

    X = df[feature_columns]
    y = df[target_column]

    if y.nunique() < 2:
        raise RuntimeError("혼잡도 클래스가 2개 미만이라 학습할 수 없습니다.")

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.25,
        random_state=42,
        stratify=y,
    )

    preprocessor = ColumnTransformer(
        transformers=[
            (
                "category",
                OneHotEncoder(handle_unknown="ignore"),
                ["category"],
            ),
            (
                "numeric",
                "passthrough",
                ["mapx", "mapy", "hour", "day_of_week"],
            ),
        ]
    )

    model = RandomForestClassifier(
        n_estimators=300,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
    )

    pipeline = Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            ("model", model),
        ]
    )

    pipeline.fit(X_train, y_train)

    y_pred = pipeline.predict(X_test)

    print(f"Accuracy: {accuracy_score(y_test, y_pred):.4f}")
    print(
        classification_report(
            y_test,
            y_pred,
            labels=[0, 1, 2, 3],
            target_names=["여유", "보통", "약간 붐빔", "붐빔"],
            zero_division=0,
        )
    )
    print(confusion_matrix(y_test, y_pred, labels=[0, 1, 2, 3]))

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, MODEL_PATH)

    print(f"모델 저장: {MODEL_PATH}")

    return pipeline
