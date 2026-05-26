from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Check false-positive budget from confidence calibration artifact")
    parser.add_argument(
        "--calibration",
        default="results/ci/confidence_calibration.json",
        help="Calibration artifact path",
    )
    parser.add_argument(
        "--max-false-positive-rate",
        type=float,
        default=0.08,
        help="Maximum allowed false positive rate",
    )
    parser.add_argument(
        "--max-false-positive-count",
        type=int,
        default=25,
        help="Maximum allowed false positive count",
    )
    parser.add_argument(
        "--fail-on-findings",
        action="store_true",
        help="Exit non-zero when budget findings are present",
    )
    args = parser.parse_args()

    calibration_path = Path(args.calibration)
    payload = json.loads(calibration_path.read_text(encoding="utf-8"))
    overall = payload.get("overall") if isinstance(payload.get("overall"), dict) else {}

    false_positive_rate = float(overall.get("false_positive_rate", 0.0) or 0.0)
    false_positive_count = int(overall.get("false_positive_count", 0) or 0)
    enforced_count = int(overall.get("enforced_count", 0) or 0)

    findings: list[str] = []
    if false_positive_rate > float(args.max_false_positive_rate):
        findings.append(
            "false_positive_rate="
            f"{false_positive_rate:.4f} exceeds max_false_positive_rate={float(args.max_false_positive_rate):.4f}"
        )
    if false_positive_count > int(args.max_false_positive_count):
        findings.append(
            "false_positive_count="
            f"{false_positive_count} exceeds max_false_positive_count={int(args.max_false_positive_count)}"
        )

    if findings:
        mode = "blocking" if args.fail_on_findings else "non-blocking"
        print(f"False-positive budget findings ({mode}): {len(findings)}")
        for finding in findings:
            print(f"::warning::{finding}")
    else:
        print(
            "False-positive budget check passed: "
            f"enforced={enforced_count} false_positive_count={false_positive_count} false_positive_rate={false_positive_rate:.4f}"
        )

    if findings and args.fail_on_findings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
