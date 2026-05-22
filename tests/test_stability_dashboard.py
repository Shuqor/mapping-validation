import json
from pathlib import Path

from scripts.build_stability_dashboard import build_dashboard


def test_build_stability_dashboard_includes_fingerprint_and_reason_histogram():
    sample_report = {
        "report_id": "r1",
        "validation_mode": "strict",
        "summary": {
            "status": "PASS_WITH_WARNINGS",
            "error_count": 2,
            "parser_confidence": "medium",
            "grouped_error_counts": {"constant_mismatches": 2, "value_mismatches": 0},
        },
        "checked_rules": 10,
        "error_count": 2,
        "validation_fingerprint": {
            "validator_version": "v1",
            "parser_version": "p1",
            "mode": "strict",
            "exception_profile": "default",
            "exception_count": 1,
            "exception_profile_hash": "abcd1234",
        },
        "rule_decisions": [
            {"reason_code": "rule_was_evaluated"},
            {"reason_code": "rule_was_evaluated"},
            {"reason_code": "unsupported_condition_pattern"},
        ],
        "warnings": [
            "Parser confidence is medium; review parser_diagnostics for fallbacks or ambiguities",
            "Skipped 1 rule(s) due to unsupported conditions",
        ],
        "warning_taxonomy": {
            "strict_warnings": ["Skipped 1 rule(s) due to unsupported conditions"],
            "heuristic_warnings": [
                "Parser confidence is medium; review parser_diagnostics for fallbacks or ambiguities"
            ],
            "informational_warnings": [],
            "counts": {"strict": 1, "heuristic": 1, "informational": 0, "total": 2},
        },
        "parser_diagnostics": {
            "confidence": "medium",
            "extraction": {"ambiguities": [{"header": "Condition"}]},
        },
    }

    dashboard = build_dashboard(sample_report)

    assert dashboard["summary"]["status"] == "PASS_WITH_WARNINGS"
    assert dashboard["summary"]["error_count"] == 2
    assert dashboard["fingerprint"]["exception_count"] == 1
    assert dashboard["reason_code_histogram"][0]["reason_code"] == "rule_was_evaluated"
    assert dashboard["reason_code_histogram"][0]["count"] == 2
    assert dashboard["top_grouped_errors"][0]["type"] == "constant_mismatches"
    assert dashboard["warning_split"]["heuristic_warning_count"] == 1
    assert dashboard["warning_split"]["strict_warning_count"] == 1
    assert dashboard["warning_split"]["informational_warning_count"] == 0
    assert dashboard["parser_uncertainty"]["parser_confidence"] == "medium"
    assert dashboard["parser_uncertainty"]["ambiguity_count"] == 1


def test_stage10_spec_coverage_report_can_be_projected_to_stability_dashboard():
    report_path = Path(__file__).resolve().parents[1] / "results" / "stage10_spec_coverage_inttra.json"
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    dashboard = build_dashboard(payload)

    assert dashboard["report_id"]
    assert dashboard["summary"]["status"]
