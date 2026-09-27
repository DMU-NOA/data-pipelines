from pathlib import Path

import requests

from noa_data.collectors.common import RAW_DATA_DIR


SOURCE = "admdong_boundary"

# 대한민국 행정동 경계 (통계청 경계를 GeoJSON 으로 가공해 버전별로 공개하는 저장소)
# https://github.com/vuski/admdongkor
#
# 생활인구의 행정동 코드(8자리, 예: 11110530)는 이 파일 adm_cd2(10자리)의 앞 8자리와 같다.
REPO_API = "https://api.github.com/repos/vuski/admdongkor/contents"
RAW_URL = "https://raw.githubusercontent.com/vuski/admdongkor/master/{version}/HangJeongDong_{version}.geojson"


def latest_version() -> str:
    response = requests.get(REPO_API, timeout=30)
    response.raise_for_status()

    versions = [
        item["name"]
        for item in response.json()
        if item["type"] == "dir" and item["name"].startswith("ver")
    ]

    return max(versions)


def collect(version: str | None = None) -> Path | None:
    """
    행정동 경계 GeoJSON (전국) 을 원본 그대로 받는다.

    저장: data/raw/admdong_boundary/<version>/HangJeongDong_<version>.geojson
    이미 받은 버전은 건너뛴다. 행정동은 분리/통합으로 바뀌므로
    생활인구 기간에 맞는 버전을 골라 쓸 수 있도록 버전별로 보관한다.
    """

    version = version or latest_version()
    path = RAW_DATA_DIR / SOURCE / version / f"HangJeongDong_{version}.geojson"

    if path.exists():
        print(f"{version}: 이미 있음 → {path}")
        return None

    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".part")

    with requests.get(RAW_URL.format(version=version), stream=True, timeout=120) as response:
        response.raise_for_status()

        with open(partial, "wb") as output:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                output.write(chunk)

    partial.replace(path)

    print(f"{version}: {path.stat().st_size / 1024 / 1024:,.1f}MB → {path}")

    return path
