from scripts.check_decision_explanations import check_decision_explanations


def test_decision_explanation_contract_accepts_valid_report():
    report = {
        "rule_decisions": [
            {
                "status": "enforced",
                "reason": "Rule was evaluated with deterministic parser support",
                "reason_code": "rule_was_evaluated_with_deterministic_parser_support",
                "remediation_hint": "No action required.",
            },
            {
                "status": "parsed_only",
                "reason": "Condition recognized as procedural/instruction-only",
                "reason_code": "condition_recognized_as_procedural_instruction_only",
                "remediation_hint": "Keep as parsed_only or rewrite condition into a deterministic mapping expression.",
            },
        ]
    }

    assert check_decision_explanations(report) == []


def test_decision_explanation_contract_flags_missing_hint_for_parsed_only():
    report = {
        "rule_decisions": [
            {
                "status": "parsed_only",
                "reason": "Condition recognized as procedural/instruction-only",
                "reason_code": "condition_recognized_as_procedural_instruction_only",
            }
        ]
    }

    issues = check_decision_explanations(report)
    assert any("remediation_hint" in issue for issue in issues)
