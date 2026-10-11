"""Verify collected hourly data, published predictions and scheduled tasks.

Does not launch a scheduler, modify DB data or call external Seoul APIs.
Exit status: zero only when the *operational scheduler and endpoint* are
available. Missing validated ML is reported but doesn't falsify official data.
"""
import argparse
import subprocess
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from noa_data.db.connection import connect

KST = ZoneInfo("Asia/Seoul")
TASKS = ("realtime", "daily", "training")


def _counts(conn):
    info = {}
    for name, table, date_column in (
        ("citydata_observations", "citydata_population", "ppltn_time"),
        ("official_hourly_forecasts", "citydata_forecast", "ppltn_time"),
        ("hourly_ml_predictions", "area_hourly_forecast", "issued_at"),
        ("verified_spot_ml", "latest_congestion", "updated_at"),
    ):
        extra = " WHERE prediction_verified IS TRUE AND source = 'predicted'" if name == "verified_spot_ml" else ""
        row = conn.execute(f"SELECT COUNT(*), MAX({date_column}) FROM {table}{extra}").fetchone()
        info[name] = {"rows": row[0], "latest": row[1]}
    return info


def _scheduler():
    if sys.platform != "win32":
        return {"supported": False, "reason": "Windows 스케줄러 확인은 Windows에서만 지원"}
    results = {}
    for name in TASKS:
        command = ["schtasks", "/Query", "/TN", f"\\NOA\\{name}", "/FO", "LIST", "/V"]
        completed = subprocess.run(command, capture_output=True, text=True, errors="replace")
        results[name] = {
            "registered": completed.returncode == 0,
            "detail": (completed.stdout if completed.returncode == 0 else completed.stderr)[-1500:],
        }
    return results


def _api(api_base, spot_id):
    try:
        response = requests.get(
            f"{api_base.rstrip('/')}/api/spots/{spot_id}/forecast",
            params={"lang": "ko"}, timeout=8
        )
        response.raise_for_status()
        body = response.json()
        return {
            "ok": isinstance(body.get("forecast"), list),
            "source": body.get("source"),
            "count": len(body.get("forecast") or []),
            "regional_reference": body.get("regional_reference"),
        }
    except (requests.RequestException, ValueError) as exc:
        return {"ok": False, "error": str(exc)}


def main():
    parser = argparse.ArgumentParser(description="NOA 시간별 예측/스케줄러 점검")
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--spot", default="POI001",
                        help="백엔드 예보 endpoint에 전달할 관광지 ID 또는 CityData AREA_CD")
    args = parser.parse_args()

    with connect() as conn:
        data = _counts(conn)
    print("===== 시간별 예측 DB 상태 =====")
    for k, v in data.items():
        print(f"{k}: {v['rows']:,}행 / 최근 {v['latest']}")
    ml = data["hourly_ml_predictions"]["rows"]
    official = data["official_hourly_forecasts"]["rows"]
    if not ml and official:
        print("검증 ML 시간별 예측 없음 → 서울시 공식 시간별 예보를 보여주는 것이 정상")
    elif not ml and not official:
        print("공식 및 자체 시간별 예측 모두 없음 → 수집 상태 확인 필요")

    print("\n===== Windows 작업 스케줄러 =====")
    scheduled = _scheduler()
    if not scheduled.get("supported", True):
        print(scheduled["reason"])
    else:
        for k, v in scheduled.items():
            print(f"{k}: {'등록됨' if v['registered'] else '등록되지 않음'}")
        print("등록과 실제 실행 성공은 다릅니다. 작업 결과/로그·다음날 DB 관측 시각까지 확인해야 합니다.")

    print("\n===== 백엔드 시간별 예보 API =====")
    endpoint = _api(args.api, args.spot)
    print(endpoint)
    failures = []
    if not official and not ml:
        failures.append("시간별 예보 자료 없음")
    if not endpoint["ok"]:
        failures.append("백엔드 API 응답 확인 실패")
    if scheduled.get("supported", False):
        failures.extend(f"\\NOA\\{t} 등록 안 됨" for t, v in scheduled.items()
                        if not v["registered"])
    if failures:
        print("검증 미완료:", "; ".join(failures))
        raise SystemExit(1)
    print("기본 연결 점검 통과. 실제 주기 실행 성공·ML 정확도는 별도 검증 필요.")


if __name__ == "__main__":
    main()
