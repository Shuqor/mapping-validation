from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _calibration_error(calibration: dict) -> float:
    buckets = calibration.get("buckets") if isinstance(calibration.get("buckets"), list) else []
    weighted_error = 0.0
    weighted_count = 0
    for row in buckets:
        if not isinstance(row, dict):
            continue
        bucket = str(row.get("bucket") or "")
        accuracy = float(row.get("accuracy", 0.0) or 0.0)
        count = int(row.get("count", 0) or 0)
        try:
            left, right = bucket.split("-")
            midpoint = (float(left) + float(right)) / 2.0
        except Exception:
            midpoint = 0.5
        weighted_error += abs(accuracy - midpoint) * count
        weighted_count += count
    return (weighted_error / weighted_count) if weighted_count else 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description="Append latest quality metrics into trend history artifact")
    parser.add_argument("--runtime-report", default="results/ci/stage10_spec_coverage_runtime.json")
    parser.add_argument("--calibration", default="results/ci/confidence_calibration.json")
    parser.add_argument("--history", default="results/ci/quality_trend_history.json")
    args = parser.parse_args()

    runtime = _load_json(Path(args.runtime_report))
    calibration = _load_json(Path(args.calibration))
    history_path = Path(args.history)
    history_payload = _load_json(history_path)

    support = runtime.get("rule_support_summary") if isinstance(runtime.get("rule_support_summary"), dict) else {}
    ai_summary = runtime.get("ai_review_summary") if isinstance(runtime.get("ai_review_summary"), dict) else {}
    checked_rules = int(runtime.get("checked_rules", 0) or 0)
    parsed_only_rules = int(support.get("parsed_only_rules", 0) or 0)

    overall = calibration.get("overall") if isinstance(calibration.get("overall"), dict) else {}
    latest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "false_positive_rate": float(overall.get("false_positive_rate", 0.0) or 0.0),
        "parsed_only_rate": (parsed_only_rules / checked_rules) if checked_rules else 0.0,
        "contradiction_demotions": int(ai_summary.get("demoted_rules", 0) or 0),
        "calibration_error": _calibration_error(calibration),
    }

    rows = history_payload.get("history") if isinstance(history_payload.get("history"), list) else []
    rows.append(latest)
    rows = rows[-60:]

    out_payload = {
        "history": rows,
        "latest": latest,
    }
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(json.dumps(out_payload, indent=2) + "\n", encoding="utf-8")

    print(f"Quality trend history updated: {history_path.as_posix()}")
    print(json.dumps(latest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
