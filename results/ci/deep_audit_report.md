# Deep Audit Report - Validator Rule Coverage and False-Positive Risk

Generated: 2026-05-26

## Scope
- Full all-rules coverage across rules workbook set
- Curated precision and false-positive checks
- Parser-validator sync consistency checks
- Profile budget checks for parsed-only and unsupported rates

## Executive Summary
- Full rule parsing/coverage run completed successfully across 90 specs.
- Precision/false-positive gates are currently healthy on the curated gold dataset.
- A blocking sync issue exists in parser-validator family labeling consistency tests.
- No low-confidence parser outcomes were observed in all-rules coverage.

## Key Metrics
From integrator browser regression summary:
- spec_count: 90
- success_count: 90
- failure_count: 0
- status_counts: PASS=81, PASS_WITH_WARNINGS=9
- confidence_counts: high=88, medium=2
- total_checked_rules: 17039
- total_enforced_rules: 16318
- total_parsed_only_rules: 645
- total_unsupported_rules: 76
- low_confidence_count: 0

From calibration deep audit artifact:
- decision_count: 126
- accuracy: 0.9127
- enforced_count: 110
- false_positive_count: 0
- false_positive_rate: 0.0000

## Findings (ordered by severity)

### 1) Blocking: Parser-validator sync gate failures on rule family mapping
- Test file: tests/test_parser_validator_sync_gate.py
- Result: 7 failed, 9 passed
- Primary pattern: enforceable rules are labeled as direct_map instead of detected semantic family.
- Example mismatches:
  - expected if_expression_chain_map, actual direct_map
  - expected if_equals_then_map, actual direct_map
  - expected field_concat_mapping, actual direct_map
- Additional observed mismatch class:
  - parsed_only rows carry family=unknown instead of manual_review expectation in custom diagnostic probe.

Impact:
- Increases diagnostic ambiguity for operators and weakens explainability consistency.
- May increase triage friction and perceived false positives, even when status classification is correct.

### 2) Non-blocking quality: PASS_WITH_WARNINGS concentration in specific specs
- 9 specs reported PASS_WITH_WARNINGS in full coverage.
- Higher unsupported and/or parsed-only clusters remain in selected JABIL/INTTRA/TMSLSP workbooks.

Impact:
- Not a parser stability failure, but a semantic enforcement gap concentration that should be reduced over time.

### 3) Healthy signal: False-positive budget and profile budget checks passed
- false_positive_rate: 0.0000 (calibration sample)
- false_positive_count: 0
- Profile budget check: passed

Impact:
- No immediate evidence of false-positive inflation in curated calibration path.

## Recommended Fix-First Plan

1. Fix semantic family labeling consistency in validate_spec_coverage rule decision assembly.
- Ensure enforceable conditions preserve detected semantic family instead of falling back to direct_map when a known family is detected.
- Keep direct_map only for truly empty/no-condition direct mapping rows.

2. Normalize parsed_only/unsupported family labels.
- parsed_only should consistently map to manual_review family label for decision output.
- unsupported should consistently map to unsupported_rule family label.

3. Add targeted regression assertions.
- Extend sync-gate tests with explicit fixtures for if_expression_chain_map, if_equals_then_map, field_concat_mapping.
- Add one fixture to assert parsed_only -> manual_review family mapping.

4. Continue reducing unsupported clusters in the 9 PASS_WITH_WARNINGS specs.
- Prioritize by unsupported_rules count from all-rules coverage artifact.
- Convert recurring parsed_only procedural patterns into deterministic enforceable patterns where possible.

## Artifacts
- results/ci/integrator_browser_regression.json
- results/ci/integrator_browser_all_rules_coverage.json
- results/ci/integrator_browser_batch_allpass.json
- results/ci/confidence_calibration_deep_audit.json
- results/ci/profile_budget_report_deep_audit.json

## Commands Used
- python scripts/run_integrator_browser_regression.py --mode lenient ...
- pytest tests/test_validator_gold_dataset_precision.py tests/test_parsed_only_budget_guardrail.py tests/test_parser_validator_sync_gate.py tests/test_stage9_real_spec_smoke.py -q
- python scripts/generate_confidence_calibration.py --output results/ci/confidence_calibration_deep_audit.json
- python scripts/check_false_positive_budget.py --calibration results/ci/confidence_calibration_deep_audit.json --max-false-positive-rate 0.08 --max-false-positive-count 25
- python scripts/check_profile_budgets.py --rules-dir rules --budgets rules/profile_budgets.json --output results/ci/profile_budget_report_deep_audit.json
