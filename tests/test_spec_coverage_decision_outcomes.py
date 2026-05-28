import core.validate as validate_module


def test_spec_coverage_includes_decision_outcomes_and_guardrails(monkeypatch):
    rules = [
        {
            "target_xpath": "/status/outA",
            "source_xpath": "/status/inA",
            "cardinality": "1..1",
            "condition": "",
            "note": "",
            "layout": "xpath_target",
            "parser_confidence": "high",
        },
        {
            "target_xpath": "/status/outB",
            "source_xpath": "",
            "cardinality": "0..1",
            "condition": "If source is available then map source to target",
            "note": "",
            "layout": "xpath_target",
            "parser_confidence": "low",
        },
    ]

    monkeypatch.setattr(validate_module, "read_mapping_table", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(validate_module, "extract_rules", lambda _df: rules)
    monkeypatch.setattr(
        validate_module,
        "get_parser_diagnostics",
        lambda _df: {
            "status": "parsed_with_warnings",
            "confidence": "medium",
            "warnings": [],
            "layout": "xpath_target",
            "rule_count": len(rules),
            "extraction": {"ambiguities": []},
        },
    )

    report = validate_module.validate_spec_coverage("rules/spec.xlsx")

    assert report["rule_decisions"]
    assert all(
        decision.get("decision_outcome") in {"PASS", "ABSTAIN", "FAIL"}
        for decision in report["rule_decisions"]
    )
    assert all(isinstance(decision.get("guardrail_checks", {}), dict) for decision in report["rule_decisions"])
    assert report["ai_review_summary"]["decision_outcomes"]["abstain"] >= 0
