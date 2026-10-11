"""Run the existing collection/load/realtime/training stages and audit their results.

Do not install a scheduler unless --schedule was explicitly requested.
"""
import argparse
import subprocess
import sys
from pathlib import Path

STEPS = [
    ("DB migration", ["-m", "noa_data.db.migrate"]),
    ("전체 데이터 수집/적재", ["-m", "noa_data.jobs.run_daily"]),
    ("실시간 CityData 수집/적재", ["-m", "noa_data.jobs.run_realtime"]),
    ("ML 학습/예측", ["-m", "noa_data.jobs.run_training"]),
]
AUDIT = ["-m", "noa_data.jobs.audit_data"]


def run(command: list[str], name: str) -> int:
    print(f"\n===== {name} =====", flush=True)
    try:
        return subprocess.run(command, check=False).returncode
    except OSError as exc:
        print(f"{name} 실행 불가: {exc}", flush=True)
        return 1


def main() -> None:
    parser = argparse.ArgumentParser(description="NOA 전체 수집·적재·학습·예측 및 DB 점검")
    parser.add_argument(
        "--schedule", action="store_true",
        help="전체 실행 성공 후 Windows 작업 스케줄러에 realtime/daily/training 등록",
    )
    parser.add_argument(
        "--audit-only", action="store_true",
        help="새 수집·적재·예측 없이 현재 DB 테이블 수량/시각/모델 상태만 점검",
    )
    args = parser.parse_args()
    if args.audit_only and args.schedule:
        parser.error("--audit-only와 --schedule은 함께 사용할 수 없습니다.")

    if args.audit_only:
        raise SystemExit(run([sys.executable, *AUDIT], "현재 DB 데이터 현황"))

    results = []
    for name, subcommand in STEPS:
        status = run([sys.executable, *subcommand], name)
        results.append((name, status))
        # No DB schema means all subsequent stages would fail with misleading errors.
        if subcommand == STEPS[0][1] and status:
            print("DB migration 실패: 나머지 변경 작업을 중단하고 읽기 전용 진단을 실행합니다.")
            break

    # Always attempt an audit even when a public source/API failed. The report
    # differentiates existing DB rows from failures in this particular run.
    status = run([sys.executable, *AUDIT], "수집·적재·예측 후 데이터 현황")
    results.append(("최종 데이터 현황", status))
    failures = [name for name, code in results if code]
    if args.schedule:
        if failures:
            print("일부 작업 실패: 스케줄러를 등록하지 않습니다.")
        elif sys.platform != "win32":
            failures.append("Windows 이외 환경의 스케줄 등록")
            print("--schedule은 Windows 작업 스케줄러에서만 지원합니다.")
        else:
            script = Path(__file__).resolve().parents[3] / "scripts" / "register_tasks.ps1"
            status = run(
                ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                "자동 스케줄 등록",
            )
            results.append(("자동 스케줄 등록", status))
            if status:
                failures.append("자동 스케줄 등록")

    print("\n===== 통합 실행 결과 =====")
    for name, code in results:
        print(f"{'성공' if code == 0 else '실패'} | {name} (exit={code})")
    if failures:
        print("확인 필요한 단계:", ", ".join(failures))
        raise SystemExit(1)
    print("모든 실행 단계 정상 종료. 각 데이터 소스의 실제 보유량과 모델 검증 상태는 위 보고서를 확인하세요.")


if __name__ == "__main__":
    main()
