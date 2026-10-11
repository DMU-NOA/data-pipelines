"""Read-only inventory of collected NOA data and congestion prediction readiness.

Run via: python -m noa_data.jobs.run_setup --audit-only
Writes artifacts/data_audit.json (gitignored). No API calls or DB mutations.
"""
import json
from datetime import datetime, timedelta, timezone

from noa_data.collectors.common import PROJECT_ROOT
from noa_data.db.connection import connect


# Display name / source table / relevant latest observation or reference date.
# These are data tables only: no accounts, likes or user-generated information.
TABLES = (
    ("관광지 원본", "tour_place", "collected_at"),
    ("관광지 상세", "tour_place_detail", "collected_at"),
    ("축제·행사", "tour_festival", "collected_at"),
    ("관광지 분류코드", "tour_lcls_code", "collected_at"),
    ("NOA 카테고리", "noa_category", None),
    ("서비스 관광지", "tour_spots", "updated_at"),
    ("서울시 관측 지역", "seoul_spots", None),
    ("관광지 직접 매핑", "spot_mapping", None),
    ("주변 신호 연결", "place_nearby", None),
    ("CityData 지역", "citydata_area", None),
    ("CityData 인구", "citydata_population", "ppltn_time"),
    ("CityData 인구 예보", "citydata_forecast", "ppltn_time"),
    ("CityData 날씨·미세먼지", "citydata_weather", "weather_time"),
    ("CityData 시간별 날씨 예보", "citydata_weather_forecast", "weather_time"),
    ("CityData 도로 소통", "citydata_road_traffic", "observed_at"),
    ("CityData 실시간 주차", "citydata_parking", "observed_at"),
    ("S-DoT 센서 위치", "sdot_sensor", None),
    ("S-DoT 유동인구", "sdot_observation", "observed_at"),
    ("기상청 ASOS", "weather_observation", "observed_at"),
    ("공휴일", "holiday", "holiday_date"),
    ("행정동 경계", "admin_dong", None),
    ("지하철역 위치", "subway_station", None),
    ("지하철 월별 승하차", "subway_ridership", "use_month"),
    ("버스정류장 위치", "bus_stop", None),
    ("버스 월별 승하차", "bus_ridership", "use_month"),
    ("행정동 생활인구", "living_population", "base_date"),
    ("외국인 체류인구", "foreigner_population_dong", "base_date"),
    ("관광지 집중률", "kto_concentration", "collected_date"),
    ("한국관광공사 중심 관광지", "kto_hub_place", "base_ym"),
    ("한국관광공사 연관 관광지", "kto_related_place", "base_ym"),
    ("한국관광공사 방문자", "kto_region_visitor", "base_date"),
    ("한국관광공사 장소 연결", "kto_place_match", None),
    ("혼잡도 서비스", "latest_congestion", "updated_at"),
    ("검증된 지역 시간별 예측", "area_hourly_forecast", "issued_at"),
)
# Without these, the fundamental tourism service or its observed congestion
# cannot work; other feeds may be optional, limited or lagging by publication.
REQUIRED = frozenset({
    "tour_place", "tour_spots", "citydata_population",
    "latest_congestion", "place_nearby",
})


def _serial(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def _one(conn, query, params=()):
    return conn.execute(query, params).fetchone()


def _table_info(conn, title, table, latest_col):
    exists = _one(conn, "SELECT to_regclass(%s)", (f"public.{table}",))[0]
    entry = {"name": title, "table": table, "status": "missing",
             "rows": None, "count_is_estimate": False, "latest": None}
    if exists is None:
        return entry

    try:
        # Count exact for small tables; use a clearly marked PostgreSQL estimate
        # for very large historical tables to avoid expensive RDS full-table scans.
        estimate = _one(conn, """SELECT n_live_tup FROM pg_stat_user_tables
                                 WHERE relid = to_regclass(%s)""",
                        (f"public.{table}",))
        estimate = int(estimate[0]) if estimate and estimate[0] is not None else -1
        if estimate >= 500_000:
            entry["rows"] = estimate
            entry["count_is_estimate"] = True
        else:
            entry["rows"] = int(_one(conn, f"SELECT COUNT(*) FROM public.{table}")[0])
        entry["status"] = "present" if entry["rows"] else "empty"
    except Exception as exc:
        entry["status"] = "error"
        entry["error"] = f"행 수 조회 실패: {type(exc).__name__}"
        return entry

    if latest_col and entry["rows"]:
        try:
            latest = _one(conn, f"SELECT MAX({latest_col}) FROM public.{table}")[0]
            entry["latest"] = _serial(latest)
        except Exception as exc:
            entry["latest_error"] = type(exc).__name__
    return entry


def _prediction_summary(conn, has_table):
    result = {
        "actual": 0, "verified": 0, "experimental": 0,
        "methods": {}, "note": "시범 KNN은 검증 완료 ML이 아닙니다.",
    }
    if not has_table:
        return result
    for source, method, verified, count in conn.execute(
        """SELECT source, COALESCE(prediction_method, '-'),
                  COALESCE(prediction_verified, FALSE), COUNT(*)
           FROM latest_congestion
           GROUP BY source, prediction_method, prediction_verified"""
    ):
        if source == "actual":
            result["actual"] += count
        elif verified:
            result["verified"] += count
        else:
            result["experimental"] += count
        result["methods"][f"{source}/{method}/{bool(verified)}"] = count
    return result


def _training_readiness(conn, table_names):
    result = {
        "feature_version": "V1",
        "features": ["category", "mapx", "mapy", "hour", "day_of_week"],
        "uses_sdot_subway_bus_weather_foreigner": False,
        "requirements": {
            "minimum_rows": 500,
            "minimum_per_class": 20,
            "minimum_days": 7,
            "minimum_times": 24,
            "minimum_areas": 20,
        },
        "ready_for_training_gate": False,
        "reasons": [],
    }
    needed = {"citydata_population", "spot_mapping", "tour_spots"}
    if not needed.issubset(table_names):
        result["reasons"].append("필수 학습 테이블이 없음")
        return result
    rows, areas, times, first, last, c0, c1, c2, c3 = _one(
        conn, """
        WITH eligible AS (
            SELECT c.area_cd, c.ppltn_time, c.congest_lvl
            FROM citydata_population c
            JOIN spot_mapping m ON m.area_cd = c.area_cd
            JOIN tour_spots t ON t.content_id = m.content_id
            WHERE c.congest_lvl IN ('여유', '보통', '약간 붐빔', '붐빔')
              AND t.mapx IS NOT NULL AND t.mapy IS NOT NULL
        )
        SELECT COUNT(*), COUNT(DISTINCT area_cd), COUNT(DISTINCT ppltn_time),
               MIN(ppltn_time), MAX(ppltn_time),
               COUNT(*) FILTER (WHERE congest_lvl='여유'),
               COUNT(*) FILTER (WHERE congest_lvl='보통'),
               COUNT(*) FILTER (WHERE congest_lvl='약간 붐빔'),
               COUNT(*) FILTER (WHERE congest_lvl='붐빔')
        FROM eligible
        """
    )
    result.update({
        "rows": rows, "areas": areas, "times": times,
        "first_observation": _serial(first), "last_observation": _serial(last),
        "class_counts": {
            "여유": c0, "보통": c1, "약간 붐빔": c2, "붐빔": c3,
        },
    })
    limits = result["requirements"]
    if rows < limits["minimum_rows"]:
        result["reasons"].append(f"학습행 부족 ({rows}/500)")
    if areas < limits["minimum_areas"]:
        result["reasons"].append(f"관측지역 부족 ({areas}/20)")
    if times < limits["minimum_times"]:
        result["reasons"].append(f"관측시각 부족 ({times}/24)")
    if first is None or last is None or last-first < timedelta(days=7):
        result["reasons"].append("최소 7일 실측 이력 부족")
    for name, count in result["class_counts"].items():
        if count < limits["minimum_per_class"]:
            result["reasons"].append(f"{name} 클래스 부족 ({count}/20)")
    result["ready_for_training_gate"] = not result["reasons"]
    result["note"] = (
        "기초 자료 조건만 점검했습니다. 실제 시간순 분할 및 검증 점수는 "
        "run_training 결과로 확인해야 합니다."
    )
    return result


def audit(conn):
    """Create a structured report without changing the database."""
    # Avoid blocking a production/RDS instance indefinitely on large reports.
    conn.execute("SET statement_timeout = '20s'")
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "tables": [],
        "missing_required": [],
        "warnings": [],
    }
    for title, table, latest in TABLES:
        row = _table_info(conn, title, table, latest)
        report["tables"].append(row)
        if table in REQUIRED and row["status"] != "present":
            report["missing_required"].append(table)
        elif row["status"] != "present":
            report["warnings"].append(f"{table}: {row['status']}")
    available = {r["table"] for r in report["tables"] if r["status"] == "present"}

    # Staleness is evaluated from the *source observation time*, never the
    # pipeline load time. For other feeds (monthly releases, holidays, etc.)
    # publication lag is expected, so only report the timestamp.
    expected_recent = {
        "citydata_population": timedelta(hours=3),
        "citydata_weather": timedelta(hours=3),
        "citydata_road_traffic": timedelta(minutes=90),
        "citydata_parking": timedelta(minutes=90),
    }
    now = datetime.now(timezone.utc)
    for row in report["tables"]:
        threshold = expected_recent.get(row["table"])
        if not threshold or not row.get("latest"):
            continue
        try:
            observed = datetime.fromisoformat(row["latest"])
            if observed.tzinfo is None:
                # Date without timezone is not proof of a fresh live reading.
                row["fresh"] = None
            else:
                row["fresh"] = -timedelta(minutes=5) <= now - observed <= threshold
                if row["fresh"] is False:
                    report["warnings"].append(f"{row['table']}: 관측 시각 오래됨")
        except ValueError:
            row["fresh"] = None

    # Source-level ingestion history complements current table counts.
    if "pipeline_load_history" in {
        x[0] for x in conn.execute(
            """SELECT tablename FROM pg_tables WHERE schemaname = 'public'"""
        ).fetchall()
    }:
        try:
            report["load_history"] = [
                {"source": source, "files": files,
                 "loaded_rows_recorded": recorded, "last_loaded": _serial(latest)}
                for source, files, recorded, latest in conn.execute(
                    """SELECT source, COUNT(*), COALESCE(SUM(row_count), 0),
                              MAX(loaded_at)
                       FROM pipeline_load_history GROUP BY source ORDER BY source"""
                ).fetchall()
            ]
        except Exception as exc:
            report["warnings"].append(f"적재 이력 집계 실패: {type(exc).__name__}")
    try:
        from noa_data.ml.hourly_train import load_verified
        verified = load_verified()
        report["hourly_v2"] = (
            {"model_validated": True,
             "balanced_accuracy": verified["balanced_accuracy"],
             "baseline_accuracy": verified["baseline_balanced_accuracy"],
             "per_horizon_scores": verified.get("horizon_balanced_accuracy", {}),
             "feature_coverage": verified.get("feature_coverage", {}),
             "trained_at_utc": verified.get("trained_at_utc"),
             "prediction_unit": verified.get("prediction_unit")}
            if verified else {"model_validated": False}
        )
    except Exception as exc:
        report["hourly_v2"] = {"model_validated": False, "error": type(exc).__name__}
        report["warnings"].append("V2 모델 로드 실패")
    try:
        report["predictions"] = _prediction_summary(conn, "latest_congestion" in available)
    except Exception as exc:
        report["predictions"] = {"error": type(exc).__name__}
        report["warnings"].append("예측 출처 통계 조회 실패")
    try:
        report["ml_training"] = _training_readiness(conn, available)
    except Exception as exc:
        report["ml_training"] = {"error": type(exc).__name__}
        report["warnings"].append("학습 자료 조건 점검 실패")
    return report


def main():
    with connect() as conn:
        report = audit(conn)

    print("\n===== NOA 전체 DB 데이터 현황 =====", flush=True)
    for item in report["tables"]:
        rows = item["rows"]
        count = (("약 " if item["count_is_estimate"] else "") + f"{rows:,}")
                 if rows is not None else "-"
        latest = f" | 최신 기준 {item['latest']}" if item.get("latest") is not None else ""
        print(f"[{item['status']:7}] {item['name']:<21} {count:>12}건{latest}")
    pred = report.get("predictions", {})
    print("\n===== 혼잡도 출처 구분 =====")
    print(f"실측 {pred.get('actual', '-')} / 검증 예측 {pred.get('verified', '-')} "
          f"/ 미검증 시범 예측 {pred.get('experimental', '-')}")
    h2 = report.get("hourly_v2", {})
    print(f"지역별 시간별 V2 모델 검증 여부: {h2.get('model_validated', False)}")
    if h2.get("model_validated"):
        print(f"V2 balanced accuracy: {h2['balanced_accuracy']:.3f}, "
              f"persistence 기준선: {h2['baseline_accuracy']:.3f}")
        print(f"V2 학습 특성 제공률: {h2['feature_coverage']}")
    ml = report.get("ml_training", {})
    print("\n===== 현재 ML V1 학습 준비도 =====")
    print("특징: category, mapx, mapy, hour, day_of_week")
    print("V2 다중 소스 학습 코드 구현됨: 현재 소스 커버리지 및 품질 기준 충족 시에만 발표")
    print("주의: V2 혼잡도 정답은 서울시 지역 단위입니다. 관광지 자체 실측이 아닙니다.")
    print("기초 자료 조건 충족:", "예 (추가 검증 필요)" if ml.get("ready_for_training_gate")
          else "아니요")
    for problem in ml.get("reasons", []):
        print(" -", problem)
    print(f"필수 테이블 미준비: {report['missing_required'] or '없음'}")
    freshness = [
        f"{r['table']}: {'최신' if r['fresh'] else '오래됨'}"
        for r in report["tables"] if r.get("fresh") is not None
    ]
    print("실시간 계열 관측 최신성:", ", ".join(freshness) or "확인 불가")
    print(f"선택/원본 테이블 확인 필요: {len(report['warnings'])}건")
    for message in report["warnings"][:15]:
        print(" -", message)
    if len(report["warnings"]) > 15:
        print(f" - 그 외 {len(report['warnings'])-15}건 (JSON 참조)")

    path = PROJECT_ROOT / "artifacts" / "data_audit.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str),
                    encoding="utf-8")
    print(f"\n진단 보고서 저장: {path}")
    if report["missing_required"]:
        raise SystemExit("기본 서비스 데이터가 부족합니다. 위 테이블 상태를 확인하세요.")


if __name__ == "__main__":
    main()
