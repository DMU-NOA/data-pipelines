import subprocess
import sys


STEPS = [
    ("DB migration", ["-m", "noa_data.db.migrate"]),
    ("전체 데이터 수집/적재", ["-m", "noa_data.jobs.run_daily"]),
    ("ML 학습/예측", ["-m", "noa_data.jobs.run_training"]),
]


def main() -> None:
    for name, args in STEPS:
        print(f"\n===== {name} =====", flush=True)

        result = subprocess.run(
            [sys.executable, *args],
            check=False,
        )

        if result.returncode != 0:
            raise SystemExit(
                f"{name} 단계 실패 (exit={result.returncode})"
            )

    print("\n===== NOA pipeline fresh setup 완료 =====")


if __name__ == "__main__":
    main()
