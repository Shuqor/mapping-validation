from __future__ import annotations

from core.validate import (
    _DECISION_OUTCOME_ABSTAIN,
    _DECISION_OUTCOME_FAIL,
    _DECISION_OUTCOME_PASS,
    _build_agent_action_plan,
    _confidence_guardrail_thresholds,
    _decision_outcome_from_evidence,
)


def test_decision_outcome_enforced_with_errors_is_fail_when_high_confidence() -> None:
    thresholds = _confidence_guardrail_thresholds({"high": 0.8, "medium": 0.55})

    outcome = _decision_outcome_from_evidence(
        status="enforced",
        row_error_count=2,
        decision_confidence=0.92,
        parser_confidence="high",
        requires_abstain=False,
        thresholds=thresholds,
    )

    assert outcome == _DECISION_OUTCOME_FAIL


def test_decision_outcome_enforced_with_errors_is_abstain_when_low_confidence() -> None:
    thresholds = _confidence_guardrail_thresholds({"high": 0.8, "medium": 0.55})

    outcome = _decision_outcome_from_evidence(
        status="enforced",
        row_error_count=1,
        decision_confidence=0.51,
        parser_confidence="high",
        requires_abstain=False,
        thresholds=thresholds,
    )

    assert outcome == _DECISION_OUTCOME_ABSTAIN


def test_decision_outcome_without_errors_is_pass_for_enforced() -> None:
    thresholds = _confidence_guardrail_thresholds({"high": 0.8, "medium": 0.55})

    outcome = _decision_outcome_from_evidence(
        status="enforced",
        row_error_count=0,
        decision_confidence=0.4,
        parser_confidence="low",
        requires_abstain=True,
        thresholds=thresholds,
    )

    assert outcome == _DECISION_OUTCOME_PASS


def test_backend_action_plan_prioritizes_fix_now_then_review() -> None:
    thresholds = _confidence_guardrail_thresholds({"high": 0.8, "medium": 0.55})
    rule_decisions = [
        {
            "row": 10,
            "target_xpath": "/root/a",
            "status": "enforced",
            "decision_outcome": "FAIL",
            "confidence": 0.93,
            "reason": "mismatch",
            "remediation_hint": "fix",
        },
        {
            "row": 20,
            "target_xpath": "/root/b",
            "status": "unsupported",
            "decision_outcome": "ABSTAIN",
            "confidence": 0.42,
            "reason": "unsupported",
            "remediation_hint": "review",
        },
        {
            "row": 30,
            "target_xpath": "/root/c",
            "status": "enforced",
            "decision_outcome": "PASS",
            "confidence": 0.9,
            "reason": "ok",
            "remediation_hint": "none",
        },
    ]
    error_diagnostics = [
        {"row": 10},
        {"row": 10},
        {"row": 20},
    ]

    plan = _build_agent_action_plan(rule_decisions, error_diagnostics, thresholds)

    assert plan["counts"]["fix_now"] == 1
    assert plan["counts"]["needs_review"] == 1
    assert plan["counts"]["ignore"] == 1
    assert plan["items"][0]["row"] == 10
    assert plan["items"][0]["action"] == "fix_now"
