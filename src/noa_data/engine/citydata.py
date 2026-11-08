"""CityData stage functions. Import existing collection/loader/ML implementations."""
from pathlib import Path

from noa_data.collectors import seoul_citydata, seoul_files
from noa_data.collectors.common import RAW_DATA_DIR
from noa_data.db.connection import connect
from noa_data.loaders import citydata, citydata_transport, service
from noa_data.loaders.common import relative_key
from noa_data.ml.predict import refresh_congestion
from noa_data.ml.hourly_predict import publish


def _area_codes() -> list[str]:
    with connect() as conn:
        codes = [r[0] for r in conn.execute(
            "SELECT area_cd FROM citydata_area ORDER BY area_cd"
        ).fetchall()]
        if codes:
            return codes
        # A fresh DB does not contain the 121-area reference list. Recover it
        # from persisted raw files or fetch it before collecting live CityData.
        citydata.load_areas(conn)
        codes = [r[0] for r in conn.execute(
            "SELECT area_cd FROM citydata_area ORDER BY area_cd"
        ).fetchall()]
        if codes:
            return codes
    seoul_files.collect("citydata_area")
    with connect() as conn:
        citydata.load_areas(conn)
        codes = [r[0] for r in conn.execute(
            "SELECT area_cd FROM citydata_area ORDER BY area_cd"
        ).fetchall()]
    if not codes:
        raise RuntimeError("121개 권역 기준 파일 적재 실패: CityData 수집을 보류합니다")
    return codes


def collect() -> str:
    path = seoul_citydata.collect(area_codes=_area_codes())
    if not Path(path).is_file():
        raise RuntimeError("CityData 원본 파일이 생성되지 않았습니다")
    return relative_key(Path(path))


def process(batch_key: str) -> None:
    path = RAW_DATA_DIR / batch_key
    if not path.is_file() or not path.resolve().is_relative_to(RAW_DATA_DIR.resolve()):
        raise ValueError(f"수집 원본이 없거나 허용되지 않는 경로: {batch_key}")
    with connect() as conn:
        citydata.load_snapshots(conn)
        citydata_transport.load_snapshots(conn)
        rows = conn.execute(
            "SELECT 1 FROM pipeline_load_history WHERE file_path = %s", (batch_key,)
        ).fetchone()
        if rows is None:
            raise RuntimeError(f"CityData 가공 완료 기록을 찾을 수 없음: {batch_key}")


def serve() -> tuple[int, int, int]:
    with connect() as conn:
        service.sync_all(conn)
        actual, predicted = refresh_congestion(conn)
        hourly = publish(conn)
    return actual, predicted, hourly
