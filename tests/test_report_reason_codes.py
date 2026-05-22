from scripts.check_report_reason_codes import check_report_reason_codes


def test_report_reason_code_checker_accepts_valid_report_shape():
    report = {
        "rule_decisions": [
            {"reason": "Rule was evaluated with deterministic parser support", "reason_code": "rule_was_evaluated_with_deterministic_parser_support"},
            {"reason": "Rule parsed but not fully enforceable with deterministic evidence", "reason_code": "rule_parsed_but_not_fully_enforceable_with_deterministic_evidence"},
        ],
        "error_diagnostics": [
            {
                "decision_reason": "Rule was evaluated with deterministic parser support",
                "decision_reason_code": "rule_was_evaluated_with_deterministic_parser_support",
            }
        ],
    }

    assert check_report_reason_codes(report) == []


def test_report_reason_code_checker_flags_missing_reason_code():
    report = {
        "rule_decisions": [
            {"reason": "Rule was evaluated with deterministic parser support", "reason_code": ""},
        ],
        "error_diagnostics": [],
    }

    issues = check_report_reason_codes(report)

    assert issues == ["rule_decisions[0].reason_code is required"]