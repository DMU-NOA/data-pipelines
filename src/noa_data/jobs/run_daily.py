import subprocess
import sys
import time


# 매일 새벽 한 번 실행하는 작업 (순서대로)
# 각 단계는 새로 나온 것만 받는다. 한 단계가 실패해도 다음 단계는 계속 실행한다.
# 15분마다 도는 실시간 파이프라인(run_realtime)은 작업 스케줄러에 따로 등록한다.
STEPS: list[tuple[str, list[str]]] = [
    # ── 기준 정보 ──────────────────────────────────────────────
    # 공휴일: 임시공휴일이 새로 지정될 수 있어 올해와 내년을 다시 받는다.
    ("공휴일", ["collect_holidays"]),
    # 관광지 목록 (한국어, 영어, 일본어, 중국어. 활용신청 안 된 언어는 건너뜀)
    ("관광지 목록", ["collect_tourapi_places"]),
    ("관광지 분류 코드", ["collect_tourapi_codes"]),
    # 운영시간, 휴무일. 하루 한도 안에서 이어서 받고, 다 받으면 아무것도 하지 않는다.
    ("관광지 상세정보", ["collect_tourapi_details"]),
    ("축제·행사", ["collect_tourapi_festivals"]),
    # 위치 기준 (새 버전/파일이 있을 때만 받는다)
    ("행정동 경계", ["collect_admdong_boundary"]),
    ("121장소 목록·영역", ["collect_seoul_files", "citydata_area"]),
    ("S-DoT 센서 위치", ["collect_seoul_files", "sdot_sensor"]),
    ("지하철역 위치", ["collect_seoul_subway_stations"]),
    ("버스정류장 위치", ["collect_seoul_bus_stops"]),

    # ── 인지도 재료 (네이버 리뷰 대신: 한국관광공사 T맵 내비게이션 빅데이터, 월 단위) ──
    ("중심 관광지 순위", ["collect_kto_bigdata", "hub"]),
    ("연관 관광지", ["collect_kto_bigdata", "related"]),

    # ── 관광지 주변 신호 ───────────────────────────────────────
    # 날씨 관측: 전날까지 제공된다. 최근 7일을 다시 받아 빠진 날과 보정값을 채운다.
    ("날씨 관측 (ASOS)", ["collect_kma_weather"]),
    # 관광지 집중률 30일 예측 (과거 이력을 주지 않아 매일 받아야 한다)
    ("관광지 집중률", ["collect_kto_concentration"]),
    # S-DoT: API 는 최근 약 16일 / 한 달만 보관하므로 빠진 날짜를 채운다.
    ("S-DoT 실시간 API", ["collect_sdot", "--api", "realtime", "--days", "14", "--skip-complete"]),
    ("S-DoT 기존 API", ["collect_sdot", "--api", "recent", "--days", "28", "--skip-complete"]),
    ("S-DoT 주간 파일", ["collect_seoul_files", "sdot_history", "--since", "20240101"]),
    # 월 단위로 1~2달 늦게 공개된다. 새 달만 받는다.
    ("생활인구 (행정동)", ["collect_seoul_files", "living_population", "--since", "20240101"]),
    ("단기체류 외국인 (행정동)", ["collect_seoul_files", "foreigner_dong", "--since", "20240101"]),
    # 집계구 단위는 원본만 받아 둔다 (집계구 경계 확보 후 적재).
    ("단기체류 외국인 (집계구, 원본만)", ["collect_seoul_files", "foreigner_block", "--since", "20240101"]),
    ("구별 방문자수 (통신 데이터)", ["collect_kto_bigdata", "visitor"]),
    ("지하철 승하차", ["collect_seoul_ridership", "subway"]),
    ("버스 승하차", ["collect_seoul_ridership", "bus"]),

    # ── DB 적재 + 서비스 최신화 ───────────────────────────────
    # 위에서 받은 원본을 DB에 넣고, 마지막 loader에서 backend 서비스 테이블까지 동기화한다.
    ("DB 적재", ["load_db"]),

    # 기존 모델이 있으면 predicted까지 갱신한다.
    # 모델이 아직 없으면 actual만 갱신하고 predicted는 안전하게 건너뛴다.
    ("혼잡도 최신화", ["refresh_congestion"]),
]


def main() -> None:
    results: list[tuple[str, bool, float]] = []

    for name, command in STEPS:
        print(f"\n===== {name}: {' '.join(command)}", flush=True)
        started = time.monotonic()

        completed = subprocess.run(
            [sys.executable, "-m", f"noa_data.jobs.{command[0]}", *command[1:]],
        )

        results.append((name, completed.returncode == 0, time.monotonic() - started))

    print("\n===== 요약")

    for name, ok, seconds in results:
        print(f"{'성공' if ok else '실패'}  {name} ({seconds:.0f}초)")

    if not all(ok for _, ok, _ in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
