import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow direct script execution from repository root without package install.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import core.validate as validate_module


DEFAULT_BASELINE_PATH = Path("results/stage10_spec_coverage_baseline.json")


def project_stage10_spec_coverage(report: dict) -> dict:
    support = report.get("rule_support_summary", {})
    semantic = report.get("semantic_summary", {})
    coverage = semantic.get("coverage", {})
    parser = report.get("parser_diagnostics", {})
    gap = report.get("rule_gap_summary", {})
    reverse = report.get("reverse_validation_summary", {})
    completeness = report.get("mapping_completeness", {})

    return {
        "validation_mode": report.get("validation_mode"),
        "summary": {
            "status": report.get("summary", {}).get("status"),
            "parser_status": report.get("summary", {}).get("parser_status"),
            "parser_confidence": report.get("summary", {}).get("parser_confidence"),
        },
        "checked_rules": int(report.get("checked_rules", 0)),
        "support": {
            "total_rules": int(support.get("total_rules", 0)),
            "enforced_rules": int(support.get("enforced_rules", 0)),
            "parsed_only_rules": int(support.get("parsed_only_rules", 0)),
            "unsupported_rules": int(support.get("unsupported_rules", 0)),
        },
        "semantic": {
            "profile": semantic.get("profile"),
            "coverage_percent": float(coverage.get("coverage_percent", 0.0)),
            "unsupported_condition_rules": int(coverage.get("unsupported_condition_rules", 0)),
            "top_unsupported_conditions": semantic.get("top_unsupported_conditions", [])[:10],
            "top_suggested_families": semantic.get("top_suggested_families", [])[:10],
        },
        "rule_gap_summary": {
            "enforceable_coverage_percent": float(gap.get("enforceable_coverage_percent", 0.0)),
            "semantic_condition_coverage_percent": float(gap.get("semantic_condition_coverage_percent", 0.0)),
            "missing_cardinality_rules": int(gap.get("missing_cardinality_rules", 0)),
            "ai_review_needed": bool(gap.get("ai_review_needed", False)),
        },
        "reverse_validation_summary": {
            "status": reverse.get("status", "PASS"),
            "required_rules": int(reverse.get("required_rules", 0)),
            "mapped_required_rules": int(reverse.get("mapped_required_rules", 0)),
            "unmapped_required_rules": int(reverse.get("unmapped_required_rules", 0)),
            "coverage_percent": float(reverse.get("coverage_percent", 100.0)),
        },
        "mapping_completeness": {
            "status": completeness.get("status", "PASS"),
            "basis": completeness.get("basis", "spec_projection"),
            "score_percent": float(completeness.get("score_percent", 100.0)),
            "satisfied_mandatory_rules": int(completeness.get("satisfied_mandatory_rules", 0)),
            "total_mandatory_rules": int(completeness.get("total_mandatory_rules", 0)),
        },
        "parser": {
            "sheet_name": parser.get("sheet_name"),
            "header_row": parser.get("header_row"),
            "layout": parser.get("layout"),
            "rule_count": parser.get("rule_count"),
        },
    }


def regenerate_stage10_spec_coverage_baseline(output_path: Path, spec_path: str) -> dict:
    report = validate_module.validate_spec_coverage(spec_path)

    payload = {
        "snapshot_name": "stage10_spec_coverage_baseline",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "spec_path": spec_path,
        },
        "projection": project_stage10_spec_coverage(report),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Regenerate Stage 10 spec coverage baseline snapshot artifact.")
    parser.add_argument(
        "--spec",
        default="rules/Inttra-Contivo_X12_300_5030_to_JSON_BOOKINGINBOUND 1 Update.xlsx",
        help="Mapping spec path for Stage 10 dry-run baseline",
    )
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE_PATH), help="Baseline artifact path")
    args = parser.parse_args()

    baseline_path = Path(args.baseline)
    payload = regenerate_stage10_spec_coverage_baseline(
        output_path=baseline_path,
        spec_path=args.spec,
    )

    print(
        f"Updated baseline: {baseline_path} | "
        f"coverage={payload['projection']['semantic']['coverage_percent']}% "
        f"unsupported={payload['projection']['support']['unsupported_rules']}"
    )


if __name__ == "__main__":
    main()
