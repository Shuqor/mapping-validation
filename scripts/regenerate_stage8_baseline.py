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


DEFAULT_BASELINE_PATH = Path("results/stage8_validation_baseline.json")


def project_stage8_report(report: dict) -> dict:
    grouped = report["summary"]["grouped_error_counts"]
    parser = report["parser_diagnostics"]

    return {
        "validation_mode": report["validation_mode"],
        "summary": {
            "status": report["summary"]["status"],
            "error_count": report["summary"]["error_count"],
            "grouped_error_counts": {
                "cardinality_violations": grouped.get("cardinality_violations", 0),
                "source_target_missing": grouped.get("source_target_missing", 0),
                "value_mismatches": grouped.get("value_mismatches", 0),
                "constant_mismatches": grouped.get("constant_mismatches", 0),
                "concat_mismatches": grouped.get("concat_mismatches", 0),
            },
            "parser_status": report["summary"]["parser_status"],
            "parser_confidence": report["summary"]["parser_confidence"],
        },
        "checked_rules": report["checked_rules"],
        "rule_support_summary": {
            "total_rules": report["rule_support_summary"]["total_rules"],
            "enforced_rules": report["rule_support_summary"]["enforced_rules"],
            "parsed_only_rules": report["rule_support_summary"]["parsed_only_rules"],
            "unsupported_rules": report["rule_support_summary"]["unsupported_rules"],
            "target_path_heuristic_rules": report["rule_support_summary"]["target_path_heuristic_rules"],
            "condition_based_rules": report["rule_support_summary"]["condition_based_rules"],
        },
        "parser": {
            "sheet_name": parser.get("sheet_name"),
            "header_row": parser.get("header_row"),
            "layout": parser.get("layout"),
            "rule_count": parser.get("rule_count"),
        },
        "warnings_count": len(report.get("warnings", [])),
        "has_skipped_rules": bool(report.get("skipped_rules")),
        "has_semantic_summary": "semantic_summary" in report,
    }


def regenerate_stage8_baseline(output_path: Path, spec_path: str, input_path: str, output_xml_path: str) -> dict:
    report = validate_module.validate_mapping(
        spec_path,
        input_path,
        output_xml_path,
        validation_mode="strict",
    )

    payload = {
        "snapshot_name": "stage8_validation_baseline",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "spec_path": spec_path,
            "input_xml_path": input_path,
            "output_xml_path": output_xml_path,
        },
        "projection": project_stage8_report(report),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Regenerate Stage 8 baseline snapshot artifact.")
    parser.add_argument("--spec", default="rules/spec.xlsx", help="Mapping spec path")
    parser.add_argument("--input", default="samples/input.xml", help="Input payload XML path")
    parser.add_argument("--output-xml", default="samples/output.xml", help="Output payload XML path")
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE_PATH), help="Baseline artifact path")
    args = parser.parse_args()

    baseline_path = Path(args.baseline)
    payload = regenerate_stage8_baseline(
        output_path=baseline_path,
        spec_path=args.spec,
        input_path=args.input,
        output_xml_path=args.output_xml,
    )

    print(
        f"Updated baseline: {baseline_path} | "
        f"status={payload['projection']['summary']['status']} "
        f"errors={payload['projection']['summary']['error_count']}"
    )


if __name__ == "__main__":
    main()
