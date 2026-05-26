import json
from pathlib import Path

import core.validate as validate_module


def _web_source() -> str:
    web_path = Path(__file__).resolve().parents[1] / "web" / "index.html"
    return web_path.read_text(encoding="utf-8")


def test_backend_and_browser_expose_decision_contract_fields():
    report = validate_module.validate_spec_coverage(
        "rules/Inttra-Contivo_X12_300_5030_to_JSON_BOOKINGINBOUND 1 Update.xlsx"
    )

    decisions = report.get("rule_decisions", [])
    assert decisions
    required_backend_keys = {"row", "status", "family", "reason", "reason_code", "confidence", "remediation_hint"}
    assert required_backend_keys.issubset(set(decisions[0].keys()))

    source = _web_source()
    assert "rule_decisions: ruleDecisions" in source
    assert "reason_code: toReasonCode(decisionReason)," in source
    assert "remediation_hint: decisionRemediationHint(decisionStatus, decisionReason, decisionFamily)," in source


def test_backend_report_contains_warning_taxonomy_contract_for_browser_consumers():
    report = validate_module.validate_spec_coverage(
        "rules/Inttra-Contivo_X12_300_5030_to_JSON_BOOKINGINBOUND 1 Update.xlsx"
    )

    taxonomy = report.get("warning_taxonomy", {})
    assert isinstance(taxonomy, dict)
    assert "counts" in taxonomy
    assert taxonomy["counts"]["total"] == len(report.get("warnings", []))


def test_browser_source_contains_warning_taxonomy_and_ai_review_summary_contract():
    source = _web_source()
    assert "function buildWarningTaxonomy(warnings)" in source
    assert "function buildAiReviewSummary(ruleDecisions, supportSummary)" in source
    assert "warning_taxonomy: warningTaxonomy," in source
    assert "ai_review_summary: aiReviewSummary," in source
