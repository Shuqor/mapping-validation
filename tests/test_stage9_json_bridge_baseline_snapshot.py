import json
from pathlib import Path

import core.validate as validate_module


BASELINE_PATH = Path(__file__).resolve().parent.parent / "results" / "stage9_json_bridge_baseline.json"


def project_stage9_json_bridge_report(report: dict) -> dict:
    grouped = report["summary"]["grouped_error_counts"]
    adapter = report.get("adapter_pipeline", {})

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
        "adapter_pipeline": {
            "enabled": bool(adapter.get("enabled", False)),
            "input_format": adapter.get("input_format", ""),
            "output_format": adapter.get("output_format", ""),
            "input_diag_status": adapter.get("input_diagnostics", {}).get("status", ""),
            "output_diag_status": adapter.get("output_diagnostics", {}).get("status", ""),
        },
        "warnings_count": len(report.get("warnings", [])),
        "has_semantic_summary": "semantic_summary" in report,
        "has_skipped_rules": bool(report.get("skipped_rules")),
    }


def test_stage9_json_bridge_baseline_snapshot_matches_known_projection():
    baseline_payload = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))

    report = validate_module.validate_mapping_from_payload_bytes(
        spec_path="rules/spec.xlsx",
        input_payload=Path("samples/input.json").read_bytes(),
        input_filename="input.json",
        output_payload=Path("samples/output.json").read_bytes(),
        output_filename="output.json",
        validation_mode="strict",
    )

    projection = project_stage9_json_bridge_report(report)
    assert projection == baseline_payload["projection"], (
        "Stage 9 JSON bridge baseline drift detected. If this change is intentional, "
        "update results/stage9_json_bridge_baseline.json with the new projection."
    )
