from __future__ import annotations

import argparse
import json
from pathlib import Path


METRICS = {
    "false_positive_rate": {"direction": "up", "max_delta": 0.02},
    "parsed_only_rate": {"direction": "up", "max_delta": 0.05},
    "contradiction_demotions": {"direction": "up", "max_delta": 15},
    "calibration_error": {"direction": "up", "max_delta": 0.05},
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Check trend drift over recent quality history")
    parser.add_argument("--history", default="results/ci/quality_trend_history.json")
    parser.add_argument("--window", type=int, default=5)
    parser.add_argument("--fail-on-findings", action="store_true")
    args = parser.parse_args()

    payload = json.loads(Path(args.history).read_text(encoding="utf-8"))
    rows = payload.get("history") if isinstance(payload.get("history"), list) else []

    if len(rows) < 2:
        print("Quality trend drift check skipped: insufficient history")
        return 0

    window = max(2, int(args.window))
    sample = rows[-window:]
    latest = sample[-1]
    baseline = sample[0]

    findings: list[str] = []
    for metric, policy in METRICS.items():
        latest_value = float(latest.get(metric, 0.0) or 0.0)
        baseline_value = float(baseline.get(metric, 0.0) or 0.0)
        delta = latest_value - baseline_value

        if policy["direction"] == "up" and delta > float(policy["max_delta"]):
            findings.append(
                f"{metric} drifted upward by {delta:.4f} over {len(sample)} points (limit={float(policy['max_delta']):.4f})"
            )

    if findings:
        mode = "blocking" if args.fail_on_findings else "non-blocking"
        print(f"Quality trend drift findings ({mode}): {len(findings)}")
        for finding in findings:
            print(f"::warning::{finding}")
    else:
        print("Quality trend drift check passed")

    if findings and args.fail_on_findings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
