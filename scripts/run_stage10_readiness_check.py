import argparse
import subprocess
import sys
from pathlib import Path


DEFAULT_COMMANDS = [
    [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_parser_validator_sync_gate.py",
        "tests/test_pattern_family_precedence.py",
        "tests/test_stage10_parser_collapse_baseline_snapshot.py",
        "-q",
    ],
    [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_stage10_spec_coverage_baseline_snapshot.py",
        "tests/test_stage10_inttra_pair_baseline_snapshot.py",
        "tests/test_rule_intent_golden_pack.py",
        "tests/test_backend_browser_decision_parity_contract.py",
        "tests/test_report_reason_codes.py",
        "tests/test_warning_taxonomy_contract.py",
        "-q",
    ],
]


def run_command(command: list[str], cwd: Path) -> int:
    print("Running:", " ".join(command))
    completed = subprocess.run(command, cwd=str(cwd), check=False)
    return int(completed.returncode)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Stage 10 readiness checklist gates")
    parser.add_argument("--workspace", default=".", help="Workspace root path")
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    failures = 0
    for command in DEFAULT_COMMANDS:
        rc = run_command(command, workspace)
        if rc != 0:
            failures += 1

    if failures:
        print(f"Stage 10 readiness check FAILED: {failures} command(s) failed")
        return 1

    print("Stage 10 readiness check PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
