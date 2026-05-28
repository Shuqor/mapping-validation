from scripts.export_uncertain_rule_reviews import collect_uncertain_rule_reviews


def test_collect_uncertain_rule_reviews_includes_abstain_and_low_confidence_rows():
    report = {
        "report_id": "rpt-1",
        "inputs": {"spec_path": "rules/spec.xlsx"},
        "rule_decisions": [
            {
                "row": 1,
                "target_xpath": "/a",
                "status": "enforced",
                "decision_outcome": "PASS",
                "confidence": 0.92,
                "reason_code": "ok",
            },
            {
                "row": 2,
                "target_xpath": "/b",
                "status": "parsed_only",
                "decision_outcome": "ABSTAIN",
                "confidence": 0.66,
                "reason_code": "manual_review",
                "guardrail_failed_checks": ["evidence_complete"],
            },
            {
                "row": 3,
                "target_xpath": "/c",
                "status": "enforced",
                "decision_outcome": "PASS",
                "confidence": 0.45,
                "reason_code": "low_conf",
            },
        ],
    }

    rows = collect_uncertain_rule_reviews(report, confidence_floor=0.8)

    assert len(rows) == 2
    assert rows[0]["row"] == 2
    assert rows[0]["decision_outcome"] == "ABSTAIN"
    assert rows[1]["row"] == 3
    assert rows[1]["decision_outcome"] == "PASS"
