import json
from pathlib import Path

from core.validate import validate_mapping_from_payload_bytes
from scripts.build_rule_decision_diff import build_decision_diff
from scripts.build_shadow_delta import build_shadow_delta
from scripts.check_parser_uncertainty_budget import check_uncertainty_budget


def _load_inttra_report() -> dict:
    report_path = Path(__file__).resolve().parents[1] / "results" / "stage10_spec_coverage_inttra.json"
    return json.loads(report_path.read_text(encoding="utf-8"))


def test_reason_code_contract_is_stable_for_real_report_fixture():
    root = Path(__file__).resolve().parents[1]
    spec = "rules/Inttra-Contivo_X12_300_5030_to_JSON_BOOKINGINBOUND 1 Update.xlsx"
    input_bytes = (root / "samples" / "BOOKINGINBOUND_1.json").read_bytes()
    output_bytes = (root / "samples" / "output INTTRA.json").read_bytes()

    report = validate_mapping_from_payload_bytes(
        spec,
        input_bytes,
        "BOOKINGINBOUND_1.json",
        output_bytes,
        "output INTTRA.json",
        validation_mode="strict",
    )
    decisions = report.get("rule_decisions", [])

    assert decisions, "Expected non-empty rule_decisions in stage10_spec_coverage_inttra.json"
    for decision in decisions:
        code = str(decision.get("reason_code") or "")
        assert code
        assert len(code) <= 80
        assert code == code.lower()
        assert all(ch.isalnum() or ch == "_" for ch in code)


def test_shadow_delta_projection_computes_grouped_error_deltas():
    strict_report = {
        "report_id": "strict",
        "summary": {"status": "FAIL", "grouped_error_counts": {"constant_mismatches": 4, "value_mismatches": 1}},
        "error_count": 5,
    }
    shadow_report = {
        "report_id": "shadow",
        "summary": {"status": "FAIL", "grouped_error_counts": {"constant_mismatches": 2, "value_mismatches": 3}},
        "error_count": 5,
    }

    delta = build_shadow_delta(strict_report, shadow_report)
    by_type = {item["type"]: item for item in delta["grouped_error_deltas"]}

    assert by_type["constant_mismatches"]["delta"] == -2
    assert by_type["value_mismatches"]["delta"] == 2


def test_parser_uncertainty_budget_passes_for_current_inttra_fixture():
    report = _load_inttra_report()
    issues = check_uncertainty_budget(report, max_ambiguities=0, allowed_confidence=("high", "medium"))
    assert issues == []


def test_same_inputs_produce_stable_fingerprint_and_reason_codes():
    root = Path(__file__).resolve().parents[1]
    spec = "rules/Inttra-Contivo_X12_300_5030_to_JSON_BOOKINGINBOUND 1 Update.xlsx"
    input_bytes = (root / "samples" / "BOOKINGINBOUND_1.json").read_bytes()
    output_bytes = (root / "samples" / "output INTTRA.json").read_bytes()

    report_a = validate_mapping_from_payload_bytes(
        spec,
        input_bytes,
        "BOOKINGINBOUND_1.json",
        output_bytes,
        "output INTTRA.json",
        validation_mode="strict",
    )
    report_b = validate_mapping_from_payload_bytes(
        spec,
        input_bytes,
        "BOOKINGINBOUND_1.json",
        output_bytes,
        "output INTTRA.json",
        validation_mode="strict",
    )

    assert report_a["validation_fingerprint"] == report_b["validation_fingerprint"]
    assert [d.get("reason_code") for d in report_a.get("rule_decisions", [])] == [
        d.get("reason_code") for d in report_b.get("rule_decisions", [])
    ]


def test_rule_decision_diff_projection_captures_changed_rows_and_transitions():
    baseline = {
        "report_id": "baseline",
        "summary": {"status": "PASS"},
        "checked_rules": 3,
        "rule_decisions": [
            {"row": 1, "target_xpath": "/a", "status": "parsed_only", "family": "manual_review", "reason_code": "parsed_only_a", "reason": "A"},
            {"row": 2, "target_xpath": "/b", "status": "unsupported", "family": "field_concat_mapping", "reason_code": "unsupported_b", "reason": "B"},
            {"row": 3, "target_xpath": "/c", "status": "enforced", "family": "direct_map", "reason_code": "enforced_c", "reason": "C"},
        ],
    }
    current = {
        "report_id": "current",
        "summary": {"status": "PASS"},
        "checked_rules": 3,
        "rule_decisions": [
            {"row": 1, "target_xpath": "/a", "status": "enforced", "family": "direct_map", "reason_code": "enforced_a", "reason": "A2"},
            {"row": 2, "target_xpath": "/b", "status": "unsupported", "family": "field_concat_mapping", "reason_code": "unsupported_b", "reason": "B"},
            {"row": 3, "target_xpath": "/c", "status": "parsed_only", "family": "manual_review", "reason_code": "parsed_only_c", "reason": "C2"},
        ],
    }

    diff = build_decision_diff(baseline, current)

    assert diff["decision_changes"]["changed_rows"] == 2
    assert diff["decision_changes"]["status_transitions"]
    assert diff["decision_changes"]["family_transitions"]
    assert diff["decision_changes"]["reason_code_transitions"]
    assert len(diff["decision_changes"]["changed_rules"]) == 2