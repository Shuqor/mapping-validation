from scripts.check_global_parser_quality import evaluate_parser_diagnostics


def test_evaluate_parser_diagnostics_accepts_allowed_confidence_and_no_ambiguity():
    diagnostics = {"confidence": "high", "extraction": {"ambiguities": []}}
    issues = evaluate_parser_diagnostics(diagnostics, allowed_confidence=("high", "medium"), max_ambiguities=0)
    assert issues == []


def test_evaluate_parser_diagnostics_reports_confidence_and_ambiguity_drift():
    diagnostics = {"confidence": "low", "extraction": {"ambiguities": [{"header": "Condition"}]}}
    issues = evaluate_parser_diagnostics(diagnostics, allowed_confidence=("high", "medium"), max_ambiguities=0)
    assert any("confidence=low" in issue for issue in issues)
    assert any("ambiguities=1" in issue for issue in issues)
