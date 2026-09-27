import gzip
import json
import os
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[3]
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"

KST = ZoneInfo("Asia/Seoul")

load_dotenv(PROJECT_ROOT / ".env")


def get_env(name: str) -> str:
    """
    필수 환경변수를 읽는다.

    값이 없으면 어떤 키가 필요한지 바로 알 수 있도록 에러를 낸다.
    """

    value = os.getenv(name)

    if not value:
        raise RuntimeError(
            f"환경변수 {name} 가 없습니다. "
            f"data-pipeline/.env 에 추가하세요. (.env.example 참고)"
        )

    return value


def now_kst() -> datetime:
    return datetime.now(KST)


def get_json(
    url: str,
    params: dict | None = None,
    headers: dict | None = None,
    json_body: dict | None = None,
    retries: int = 3,
    timeout: int = 20,
) -> dict:
    """
    JSON API를 호출한다.

    json_body가 있으면 POST, 없으면 GET으로 요청한다.
    일시적인 네트워크 오류나 5xx 응답은 재시도한다.
    """

    last_error: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            response = requests.request(
                "POST" if json_body is not None else "GET",
                url,
                params=params,
                headers=headers,
                json=json_body,
                timeout=timeout,
            )

            # 인증 오류, 파라미터 오류 같은 4xx는 재시도해도 같으므로 바로 알린다.
            if 400 <= response.status_code < 500:
                raise RuntimeError(
                    f"요청 오류 {response.status_code}: {url}\n"
                    f"{response.text[:500]}"
                )

            response.raise_for_status()

        except requests.RequestException as error:
            last_error = error

            if attempt < retries:
                time.sleep(2 ** attempt)

            continue

        # 인증키 오류 등은 JSON 요청에도 XML로 오는 경우가 있다.
        # 재시도해도 결과가 같으므로 응답 본문을 그대로 보여준다.
        try:
            return response.json()

        except ValueError:
            raise RuntimeError(
                f"JSON이 아닌 응답: {url}\n{response.text[:500]}"
            ) from None

    raise RuntimeError(
        f"API 호출 실패: {url} ({last_error})"
    )


def save_raw(
    source: str,
    name: str,
    payload: dict,
    collected_at: datetime,
) -> Path:
    """
    API 원본 응답을 가공하지 않고 gzip JSON으로 저장한다.

    저장 위치:
    data/raw/<source>/<YYYYMMDD>/<name>_<HHMMSS>.json.gz
    """

    directory = (
        RAW_DATA_DIR
        / source
        / collected_at.strftime("%Y%m%d")
    )

    directory.mkdir(parents=True, exist_ok=True)

    path = directory / (
        f"{name}_{collected_at.strftime('%H%M%S')}.json.gz"
    )

    record = {
        "source": source,
        "collected_at": collected_at.isoformat(),
        "payload": payload,
    }

    with gzip.open(path, "wt", encoding="utf-8") as file:
        json.dump(record, file, ensure_ascii=False)

    return path


def load_raw(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as file:
        return json.load(file)
