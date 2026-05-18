from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parent.parent


def run_step(script_name: str) -> None:
    script_path = REPO_ROOT / "scripts" / script_name
    print(f"[stage9-baselines] running {script_name}")
    subprocess.run([sys.executable, str(script_path)], cwd=str(REPO_ROOT), check=True)


def main() -> None:
    steps = [
        "regenerate_stage9_json_baseline.py",
        "regenerate_stage9_x12_baseline.py",
        "regenerate_stage9_edifact_baseline.py",
        "regenerate_stage9_edifact_parser_baseline.py",
    ]
    for step in steps:
        run_step(step)
    print("[stage9-baselines] all Stage 9 baseline artifacts regenerated")


if __name__ == "__main__":
    main()
