from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.check_global_validator_health import DEFAULT_CURATED_RUNS
from core.validate import validate_mapping_from_payload_bytes


def _bucket_label(score: float) -> str:
    left = math.floor(max(0.0, min(0.9999, score)) * 10) / 10
    right = left + 0.1
    return f"{left:.1f}-{right:.1f}"


def _build_row_error_counts(report: dict) -> dict[int, int]:
    counts: dict[int, int] = defaultdict(int)
    diagnostics = report.get("error_diagnostics") if isinstance(report.get("error_diagnostics"), list) else []
    for diag in diagnostics:
        if not isinstance(diag, dict):
            continue
        row = int(diag.get("row", 0) or 0)
        if row > 0:
            counts[row] += 1
    return counts


def generate_calibration() -> dict:
    bucket_totals: dict[str, int] = defaultdict(int)
    bucket_correct: dict[str, int] = defaultdict(int)
    bucket_enforced: dict[str, int] = defaultdict(int)
    bucket_false_positive: dict[str, int] = defaultdict(int)

    run_summaries: list[dict] = []
    total_decisions = 0
    total_correct = 0
    total_enforced = 0
    total_false_positive = 0

    for run_cfg in DEFAULT_CURATED_RUNS:
        report = validate_mapping_from_payload_bytes(
            spec_path=str(run_cfg["spec"]),
            input_payload=Path(str(run_cfg["input"])).read_bytes(),
            input_filename=Path(str(run_cfg["input"])).name,
            output_payload=Path(str(run_cfg["output"])).read_bytes(),
            output_filename=Path(str(run_cfg["output"])).name,
            validation_mode=str(run_cfg.get("mode") or "lenient"),
        )

        row_error_counts = _build_row_error_counts(report)
        run_decisions = report.get("rule_decisions") if isinstance(report.get("rule_decisions"), list) else []

        run_total = 0
        run_correct = 0
        run_enforced = 0
        run_false_positive = 0

        for decision in run_decisions:
            if not isinstance(decision, dict):
                continue
            score = float(decision.get("confidence", 0.0) or 0.0)
            row = int(decision.get("row", 0) or 0)
            status = str(decision.get("status", "") or "").strip().lower()
            row_errors = int(row_error_counts.get(row, 0))
            is_correct = row_errors == 0
            is_enforced = status == "enforced"
            is_false_positive = is_enforced and row_errors > 0

            label = _bucket_label(score)
            bucket_totals[label] += 1
            if is_correct:
                bucket_correct[label] += 1
            if is_enforced:
                bucket_enforced[label] += 1
            if is_false_positive:
                bucket_false_positive[label] += 1

            run_total += 1
            run_correct += 1 if is_correct else 0
            run_enforced += 1 if is_enforced else 0
            run_false_positive += 1 if is_false_positive else 0

        total_decisions += run_total
        total_correct += run_correct
        total_enforced += run_enforced
        total_false_positive += run_false_positive

        run_summaries.append(
            {
                "id": str(run_cfg.get("id") or "unnamed"),
                "spec": str(run_cfg.get("spec") or ""),
                "mode": str(run_cfg.get("mode") or ""),
                "decisions": run_total,
                "accuracy": round((run_correct / run_total), 4) if run_total else 0.0,
                "enforced": run_enforced,
                "false_positive_count": run_false_positive,
                "false_positive_rate": round((run_false_positive / run_enforced), 4) if run_enforced else 0.0,
            }
        )

    bucket_labels = sorted(bucket_totals.keys())
    bucket_rows = []
    for label in bucket_labels:
        total = bucket_totals[label]
        correct = bucket_correct[label]
        enforced = bucket_enforced[label]
        false_positive = bucket_false_positive[label]
        bucket_rows.append(
            {
                "bucket": label,
                "count": total,
                "accuracy": round((correct / total), 4) if total else 0.0,
                "enforced_count": enforced,
                "false_positive_count": false_positive,
                "false_positive_rate": round((false_positive / enforced), 4) if enforced else 0.0,
            }
        )

    return {
        "curated_runs": run_summaries,
        "overall": {
            "decision_count": total_decisions,
            "accuracy": round((total_correct / total_decisions), 4) if total_decisions else 0.0,
            "enforced_count": total_enforced,
            "false_positive_count": total_false_positive,
            "false_positive_rate": round((total_false_positive / total_enforced), 4) if total_enforced else 0.0,
        },
        "buckets": bucket_rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate confidence calibration artifact from curated validator runs")
    parser.add_argument(
        "--output",
        default="results/ci/confidence_calibration.json",
        help="Where to write calibration artifact",
    )
    args = parser.parse_args()

    payload = generate_calibration()
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    overall = payload.get("overall", {})
    print(
        "Calibration generated: "
        f"decisions={overall.get('decision_count', 0)} "
        f"accuracy={overall.get('accuracy', 0.0)} "
        f"false_positive_rate={overall.get('false_positive_rate', 0.0)}"
    )
    print(f"Artifact written: {out_path.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
