import argparse
import subprocess
import sys
from pathlib import Path


STEPS = [
    ("DB migration", ["-m", "noa_data.db.migrate"]),
    ("전체 데이터 수집/적재", ["-m", "noa_data.jobs.run_daily"]),
    ("실시간 CityData 초기 수집/적재", ["-m", "noa_data.jobs.run_realtime"]),
    ("ML 학습/예측", ["-m", "noa_data.jobs.run_training"]),
]


def run(command: list[str], name: str) -> None:
    print(f"\n===== {name} =====", flush=True)
    result = subprocess.run(command, check=False)
    if result.returncode:
        raise SystemExit(f"{name} 실패 (exit={result.returncode})")


def main() -> None:
    parser = argparse.ArgumentParser(description="NOA 최초 구축 및 자동 운영 설정")
    parser.add_argument(
        "--schedule", action="store_true",
        help="최초 실행 후 Windows 작업 스케줄러에 realtime/daily/training 등록",
    )
    args = parser.parse_args()

    for name, subcommand in STEPS:
        run([sys.executable, *subcommand], name)

    if args.schedule:
        if sys.platform != "win32":
            raise SystemExit("--schedule은 Windows 작업 스케줄러에서만 지원합니다.")
        script = Path(__file__).resolve().parents[3] / "scripts" / "register_tasks.ps1"
        run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(script)],
            "자동 스케줄 등록",
        )

    print("\n===== NOA pipeline fresh setup 완료 =====")
    if not args.schedule:
        print("15분 주기 자동 수집이 필요하면 run_setup --schedule로 설정하세요.")


if __name__ == "__main__":
    main()
