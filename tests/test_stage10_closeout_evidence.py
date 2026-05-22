from scripts.check_stage10_closeout_evidence import check_closeout_evidence


def test_stage10_closeout_evidence_passes_for_non_worsening_trend():
    payload = {
        "generated_at_utc": "2026-05-22T00:00:00+00:00",
        "browser_parity_consecutive_main_runs": 7,
        "diagnostics_contract_changed": False,
        "schema_deltas_documented_and_validated": False,
        "shadow_promotion_evidence_present": True,
        "triage_runbook_applied": True,
        "false_positive_target_percent": 2.0,
        "false_positive_rates_percent": [1.9, 1.8, 1.7],
    }

    assert check_closeout_evidence(payload) == []


def test_stage10_closeout_evidence_fails_for_worsening_or_over_target_trend():
    payload = {
        "generated_at_utc": "2026-05-22T00:00:00+00:00",
        "browser_parity_consecutive_main_runs": 8,
        "diagnostics_contract_changed": False,
        "schema_deltas_documented_and_validated": False,
        "shadow_promotion_evidence_present": True,
        "triage_runbook_applied": True,
        "false_positive_target_percent": 2.0,
        "false_positive_rates_percent": [1.7, 1.8, 2.1],
    }

    issues = check_closeout_evidence(payload)
    joined = " | ".join(issues)
    assert "exceeds target" in joined
    assert "trend worsened" in joined


def test_stage10_closeout_evidence_fails_when_timestamp_is_stale():
    payload = {
        "generated_at_utc": "2025-01-01T00:00:00+00:00",
        "browser_parity_consecutive_main_runs": 8,
        "diagnostics_contract_changed": False,
        "schema_deltas_documented_and_validated": False,
        "shadow_promotion_evidence_present": True,
        "triage_runbook_applied": True,
        "false_positive_target_percent": 2.0,
        "false_positive_rates_percent": [1.8, 1.7, 1.6],
    }

    issues = check_closeout_evidence(payload, max_evidence_age_days=30)
    assert any("evidence is stale" in issue for issue in issues)
