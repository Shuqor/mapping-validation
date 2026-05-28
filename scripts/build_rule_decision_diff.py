from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def _index_decisions(report: dict) -> dict[int, dict]:
    decisions = report.get("rule_decisions") if isinstance(report.get("rule_decisions"), list) else []
    indexed: dict[int, dict] = {}
    for fallback_row, decision in enumerate(decisions, start=1):
        if not isinstance(decision, dict):
            continue
        try:
            row = int(decision.get("row", fallback_row) or fallback_row)
        except (TypeError, ValueError):
            row = fallback_row
        indexed[row] = decision
    return indexed


def _transition_severity(baseline: dict, current: dict) -> int:
    baseline_status = str(baseline.get("status", "") or "").strip()
    current_status = str(current.get("status", "") or "").strip()
    baseline_family = str(baseline.get("family", "") or "").strip()
    current_family = str(current.get("family", "") or "").strip()
    baseline_reason_code = str(baseline.get("reason_code", "") or "").strip()
    current_reason_code = str(current.get("reason_code", "") or "").strip()

    score = 0
    if baseline_status != current_status:
        score += 30
        if current_status == "unsupported":
            score += 80
        elif current_status == "parsed_only":
            score += 45
        elif current_status == "enforced":
            score += 10
        if baseline_status == "enforced" and current_status != "enforced":
            score += 35
    if baseline_family != current_family:
        score += 12
    if baseline_reason_code != current_reason_code:
        score += 5
    return score


def build_decision_diff(baseline_report: dict, current_report: dict) -> dict:
    baseline_index = _index_decisions(baseline_report)
    current_index = _index_decisions(current_report)
    rows = sorted(set(baseline_index) | set(current_index))

    status_transitions: Counter[str] = Counter()
    family_transitions: Counter[str] = Counter()
    reason_code_transitions: Counter[str] = Counter()
    changes: list[dict[str, object]] = []

    for row in rows:
        baseline = baseline_index.get(row, {})
        current = current_index.get(row, {})

        baseline_status = str(baseline.get("status", "missing") or "missing")
        current_status = str(current.get("status", "missing") or "missing")
        baseline_family = str(baseline.get("family", "") or "")
        current_family = str(current.get("family", "") or "")
        baseline_reason_code = str(baseline.get("reason_code", "") or "")
        current_reason_code = str(current.get("reason_code", "") or "")

        if baseline_status != current_status:
            status_transitions[f"{baseline_status}->{current_status}"] += 1
        if baseline_family != current_family:
            family_transitions[f"{baseline_family}->{current_family}"] += 1
        if baseline_reason_code != current_reason_code:
            reason_code_transitions[f"{baseline_reason_code}->{current_reason_code}"] += 1

        if (
            baseline_status != current_status
            or baseline_family != current_family
            or baseline_reason_code != current_reason_code
            or baseline.get("reason", "") != current.get("reason", "")
        ):
            changes.append(
                {
                    "row": row,
                    "target_xpath": current.get("target_xpath", baseline.get("target_xpath", "")),
                    "severity_score": _transition_severity(baseline, current),
                    "baseline": {
                        "status": baseline_status,
                        "family": baseline_family,
                        "reason_code": baseline_reason_code,
                        "reason": baseline.get("reason", ""),
                    },
                    "current": {
                        "status": current_status,
                        "family": current_family,
                        "reason_code": current_reason_code,
                        "reason": current.get("reason", ""),
                    },
                }
            )

    top_changed_rows = sorted(
        changes,
        key=lambda item: (-int(item.get("severity_score", 0) or 0), int(item.get("row", 0) or 0)),
    )[:25]

    baseline_summary = baseline_report.get("summary") if isinstance(baseline_report.get("summary"), dict) else {}
    current_summary = current_report.get("summary") if isinstance(current_report.get("summary"), dict) else {}

    return {
        "snapshot_name": "rule_decision_diff",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "baseline": {
            "report_id": baseline_report.get("report_id", ""),
            "status": baseline_summary.get("status", "unknown"),
            "checked_rules": int(baseline_report.get("checked_rules", 0) or 0),
        },
        "current": {
            "report_id": current_report.get("report_id", ""),
            "status": current_summary.get("status", "unknown"),
            "checked_rules": int(current_report.get("checked_rules", 0) or 0),
        },
        "decision_changes": {
            "changed_rows": len(changes),
            "status_transitions": [
                {"transition": transition, "count": count}
                for transition, count in status_transitions.most_common()
            ],
            "family_transitions": [
                {"transition": transition, "count": count}
                for transition, count in family_transitions.most_common()
            ],
            "reason_code_transitions": [
                {"transition": transition, "count": count}
                for transition, count in reason_code_transitions.most_common()
            ],
            "changed_rules": changes[:100],
            "top_changed_rows": top_changed_rows,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build rule decision diff artifact from two report JSON files")
    parser.add_argument("--baseline", required=True, help="Path to baseline report JSON")
    parser.add_argument("--current", required=True, help="Path to current report JSON")
    parser.add_argument("--output", required=True, help="Path to write diff JSON")
    args = parser.parse_args()

    baseline_payload = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    current_payload = json.loads(Path(args.current).read_text(encoding="utf-8"))
    diff = build_decision_diff(baseline_payload, current_payload)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(diff, indent=2) + "\n", encoding="utf-8")
    print(f"Rule decision diff written to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())