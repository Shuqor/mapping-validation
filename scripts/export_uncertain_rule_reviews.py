import argparse
import json
from pathlib import Path


def collect_uncertain_rule_reviews(report: dict, confidence_floor: float = 0.8) -> list[dict]:
    decisions = report.get("rule_decisions") if isinstance(report.get("rule_decisions"), list) else []
    report_id = str(report.get("report_id") or "")
    spec_path = str((report.get("inputs") or {}).get("spec_path") or "")

    rows: list[dict] = []
    for item in decisions:
        if not isinstance(item, dict):
            continue

        status = str(item.get("status") or "").strip().lower()
        outcome = str(item.get("decision_outcome") or "").strip().upper()
        confidence = float(item.get("confidence", 0.0) or 0.0)
        uncertain = (
            outcome == "ABSTAIN"
            or status in {"parsed_only", "unsupported"}
            or confidence < confidence_floor
        )
        if not uncertain:
            continue

        rows.append(
            {
                "report_id": report_id,
                "spec_path": spec_path,
                "row": int(item.get("row", 0) or 0),
                "target_xpath": str(item.get("target_xpath") or ""),
                "source_xpath": str(item.get("source_xpath") or ""),
                "status": status,
                "decision_outcome": outcome or "ABSTAIN",
                "confidence": confidence,
                "family": str(item.get("family") or ""),
                "reason_code": str(item.get("reason_code") or ""),
                "reason": str(item.get("reason") or ""),
                "guardrail_failed_checks": list(item.get("guardrail_failed_checks") or []),
                "remediation_hint": str(item.get("remediation_hint") or ""),
            }
        )

    return sorted(rows, key=lambda row: (row["row"], row["target_xpath"], row["reason_code"]))


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(json.dumps(row, ensure_ascii=True) for row in rows)
    if payload:
        payload += "\n"
    path.write_text(payload, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Export uncertain/abstained rule decisions for human review")
    parser.add_argument("--report", required=True, help="Path to validation report JSON")
    parser.add_argument(
        "--output",
        default="results/ci/uncertain_rule_reviews.jsonl",
        help="Output JSONL path",
    )
    parser.add_argument(
        "--confidence-floor",
        type=float,
        default=0.8,
        help="Treat decisions below this confidence as uncertain",
    )
    args = parser.parse_args()

    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    rows = collect_uncertain_rule_reviews(report, confidence_floor=float(args.confidence_floor))
    output_path = Path(args.output)
    write_jsonl(output_path, rows)
    print(f"Exported {len(rows)} uncertain decision row(s) to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
