# Stage 10 Exit Criteria

This document defines the minimum sign-off criteria for Stage 10 parser-validator stabilization.

## Blocking Criteria

1. Parser-validator sync gate is green.
- Test: `tests/test_parser_validator_sync_gate.py`
- Requirement: all selected representative specs pass row/family/status alignment checks.

2. Deterministic precedence gate is green.
- Test: `tests/test_pattern_family_precedence.py`
- Requirement: overlapping condition texts resolve to stable expected families.

3. Collapse-determinism snapshot gate is green.
- Test: `tests/test_stage10_parser_collapse_baseline_snapshot.py`
- Requirement: parser diagnostics projection remains consistent with approved baseline.

4. Existing Stage 10 baseline gates are green.
- Tests:
  - `tests/test_stage10_spec_coverage_baseline_snapshot.py`
  - `tests/test_stage10_inttra_pair_baseline_snapshot.py`

5. Contract gates are green.
- Tests/scripts:
  - `tests/test_report_reason_codes.py`
  - `scripts/check_report_reason_codes.py`
  - `tests/test_warning_taxonomy_contract.py`
  - `scripts/check_warning_taxonomy.py`

## Visibility (Soak/Trend) Criteria

1. Global parser quality check runs every CI run.
- Script: `scripts/check_global_parser_quality.py`
- Mode: blocking (`--fail-on-findings`).

2. Warning taxonomy drift check runs every CI run.
- Script: `scripts/check_warning_taxonomy_drift.py`
- Initial mode: non-blocking (warning only).

3. Parser uncertainty profile check runs every CI run.
- Script: `scripts/check_parser_uncertainty_profiles.py`
- Initial mode: non-blocking (warning only).

## Promotion Rules

- Global parser quality has been promoted to blocking after soak stabilization.
- Promote drift checks to blocking only after expected-value baselines are reviewed and approved.
- Any intentional baseline update must include rationale in PR notes.
