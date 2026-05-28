import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def build_dashboard(report: dict) -> dict:
    summary = report.get("summary", {}) if isinstance(report, dict) else {}
    fingerprint = report.get("validation_fingerprint", {}) if isinstance(report, dict) else {}
    decisions = report.get("rule_decisions", []) if isinstance(report, dict) else []

    reason_codes = Counter()
    parsed_only_reasons = Counter()
    unsupported_reasons = Counter()
    status_counts = Counter()
    family_counts = Counter()
    for decision in decisions:
        if not isinstance(decision, dict):
            continue
        status = str(decision.get("status") or "unspecified").strip()
        family = str(decision.get("family") or "unspecified").strip()
        code = str(decision.get("reason_code") or "unspecified").strip()
        if code:
            reason_codes[code] += 1
        if status:
            status_counts[status] += 1
        if family:
            family_counts[family] += 1
        if status == "parsed_only" and code:
            parsed_only_reasons[code] += 1
        elif status == "unsupported" and code:
            unsupported_reasons[code] += 1

    grouped = summary.get("grouped_error_counts")
    if not isinstance(grouped, dict):
        grouped = {}

    warnings = report.get("warnings") if isinstance(report, dict) else []
    if not isinstance(warnings, list):
        warnings = []

    warning_taxonomy = report.get("warning_taxonomy") if isinstance(report, dict) else {}
    if not isinstance(warning_taxonomy, dict):
        warning_taxonomy = {}

    parser_diag = report.get("parser_diagnostics") if isinstance(report, dict) else {}
    if not isinstance(parser_diag, dict):
        parser_diag = {}

    counts = warning_taxonomy.get("counts") if isinstance(warning_taxonomy.get("counts"), dict) else {}
    if counts:
        strict_warning_count = int(counts.get("strict", 0) or 0)
        heuristic_warning_count = int(counts.get("heuristic", 0) or 0)
        informational_warning_count = int(counts.get("informational", 0) or 0)
        total_warning_count = int(counts.get("total", len(warnings)) or 0)
    else:
        heuristic_warning_count = 0
        strict_warning_count = 0
        informational_warning_count = 0
        for warning in warnings:
            text = str(warning or "").lower()
            if "parser confidence" in text or "ambiguous" in text or "heuristic" in text:
                heuristic_warning_count += 1
            else:
                strict_warning_count += 1
        total_warning_count = len(warnings)

    extraction = parser_diag.get("extraction") if isinstance(parser_diag.get("extraction"), dict) else {}
    ambiguities = extraction.get("ambiguities") if isinstance(extraction.get("ambiguities"), list) else []

    return {
        "snapshot_name": "stability_dashboard",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "report_id": report.get("report_id", ""),
        "validation_mode": report.get("validation_mode", ""),
        "summary": {
            "status": summary.get("status", "unknown"),
            "error_count": int(report.get("error_count", summary.get("error_count", 0)) or 0),
            "checked_rules": int(report.get("checked_rules", 0) or 0),
        },
        "fingerprint": {
            "validator_version": fingerprint.get("validator_version", ""),
            "parser_version": fingerprint.get("parser_version", ""),
            "mode": fingerprint.get("mode", ""),
            "exception_profile": fingerprint.get("exception_profile", ""),
            "exception_count": int(fingerprint.get("exception_count", 0) or 0),
            "exception_profile_hash": fingerprint.get("exception_profile_hash", ""),
        },
        "top_grouped_errors": sorted(
            [{"type": str(key), "count": int(value)} for key, value in grouped.items() if int(value) > 0],
            key=lambda item: item["count"],
            reverse=True,
        )[:10],
        "reason_code_histogram": [
            {"reason_code": code, "count": count}
            for code, count in reason_codes.most_common(20)
        ],
        "decision_status_histogram": [
            {"status": status, "count": count}
            for status, count in status_counts.most_common()
        ],
        "decision_family_histogram": [
            {"family": family, "count": count}
            for family, count in family_counts.most_common()
        ],
        "decision_reason_histograms": {
            "parsed_only": [
                {"reason_code": code, "count": count}
                for code, count in parsed_only_reasons.most_common(20)
            ],
            "unsupported": [
                {"reason_code": code, "count": count}
                for code, count in unsupported_reasons.most_common(20)
            ],
        },
        "warning_split": {
            "strict_warning_count": strict_warning_count,
            "heuristic_warning_count": heuristic_warning_count,
            "informational_warning_count": informational_warning_count,
            "total_warnings": total_warning_count,
        },
        "parser_uncertainty": {
            "parser_confidence": summary.get("parser_confidence", parser_diag.get("confidence", "unknown")),
            "ambiguity_count": len(ambiguities),
        },
    }


def write_dashboard(report: dict, output_path: Path) -> Path:
    payload = build_dashboard(report)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Build compact stabilization dashboard artifact from a report JSON")
    parser.add_argument("--report", required=True, help="Path to validation report JSON")
    parser.add_argument("--output", required=True, help="Path to write dashboard JSON")
    args = parser.parse_args()

    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    output = write_dashboard(report, Path(args.output))
    print(f"Stability dashboard written to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
