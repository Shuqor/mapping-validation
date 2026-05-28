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
    status_counts = {item["status"]: item["count"] for item in dashboard["decision_status_histogram"]}
    family_counts = {item["family"]: item["count"] for item in dashboard["decision_family_histogram"]}
    assert status_counts["unspecified"] == 3
    assert family_counts["unspecified"] == 3
    assert dashboard["decision_reason_histograms"]["unsupported"] == []
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


def test_build_rule_decision_diff_captures_transition_counts():
    from scripts.build_rule_decision_diff import build_decision_diff

    baseline = {
        "report_id": "baseline",
        "summary": {"status": "PASS"},
        "checked_rules": 2,
        "rule_decisions": [
            {"row": 1, "target_xpath": "/a", "status": "parsed_only", "family": "manual_review", "reason_code": "parsed_only_a", "reason": "A"},
            {"row": 2, "target_xpath": "/b", "status": "unsupported", "family": "field_concat_mapping", "reason_code": "unsupported_b", "reason": "B"},
        ],
    }
    current = {
        "report_id": "current",
        "summary": {"status": "PASS"},
        "checked_rules": 2,
        "rule_decisions": [
            {"row": 1, "target_xpath": "/a", "status": "enforced", "family": "direct_map", "reason_code": "enforced_a", "reason": "A2"},
            {"row": 2, "target_xpath": "/b", "status": "unsupported", "family": "field_concat_mapping", "reason_code": "unsupported_b", "reason": "B"},
        ],
    }

    diff = build_decision_diff(baseline, current)

    assert diff["decision_changes"]["changed_rows"] == 1
    assert diff["decision_changes"]["status_transitions"][0]["transition"] == "parsed_only->enforced"
    assert diff["decision_changes"]["family_transitions"][0]["transition"] == "manual_review->direct_map"
    assert diff["decision_changes"]["top_changed_rows"][0]["row"] == 1
    assert diff["decision_changes"]["top_changed_rows"][0]["severity_score"] > 0
