## Summary

- What changed:
- Why it changed:
- Risk level (low/medium/high):

## Validation

- [ ] Local tests run
- [ ] CI checks pass
- [ ] Backward compatibility considered

## Stage 10.20 Release Readiness Checklist

Use this checklist for release-impacting changes.

- [ ] Stage 8 frozen regression gate is green (`tests/test_semantic_similarity.py`, `tests/test_web.py`, `tests/test_report_format.py`, `tests/test_structure_contract_fixtures.py`, `tests/test_semantic_performance_guardrail.py`, `tests/test_stage8_baseline_snapshot.py`)
- [ ] Stage 9 bridge/parity regression gate is green (`tests/test_stage9_adapter_bridge.py`, `tests/test_stage9_adapters.py`, `tests/test_stage9_real_spec_smoke.py`, `tests/test_stage9_edi_performance_guardrail.py`)
- [ ] Browser parity workflow job is stable on `main` for at least 7 consecutive runs (pass or explicit runtime-unavailable skip)
- [ ] Diagnostics contract fields are unchanged, or schema deltas are documented and validated (`rule_decisions`, `error_diagnostics`, `parser_diagnostics.token_resolution_diagnostics`, `parser_diagnostics.rollout_guardrails`)
- [ ] Any `MVP_SHADOW_RULE_FAMILIES` rollout promotion includes real-spec evidence (before/after unsupported, parsed-only, enforced distributions and false-positive impact)
- [ ] False-positive rate on curated real-spec set is at or below target (<2% by default), with non-worsening trend over last 2 release candidates
- [ ] If Stage 10 behavior, thresholds, or evidence assumptions changed, `results/ci/stage10_release_evidence.json` was reviewed/updated with current false-positive trend data
- [ ] Large X12/EDIFACT performance guardrails pass; any threshold increase includes rationale in PR notes
- [ ] Triage runbook classification is applied for active validation bugs (`parser_gap`, `rule_ambiguity`, `data_mismatch`)

## Notes for Reviewers

- Any known limitations:
- Follow-up tasks (if any):
