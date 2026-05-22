# Parser + Validator Stabilization Plan

This plan captures the 10-point stabilization strategy and maps each item to concrete repo deliverables.

## 1) Canonical Validation Engine Path
- Goal: Remove logic drift between browser and backend validation.
- Action:
  - Define a single canonical rule-evaluation contract in `core/validate.py`.
  - Keep UI-specific behavior in `web/index.html` presentation only.
- Deliverable:
  - Shared deterministic reason-code taxonomy for both CLI and browser reports.

## 2) Deterministic Rule Evaluation
- Goal: Ensure each rule follows a stable precedence and traceable branch selection.
- Action:
  - Add explicit reason codes to every `rule_decisions` entry.
  - Keep branch ordering fixed and tested.
- Deliverable:
  - `reason_code` populated in report decisions.

## 3) Validation Fingerprint in Reports
- Goal: Make report changes explainable when behavior changes.
- Action:
  - Emit a `validation_fingerprint` object with engine version, mode, and exception profile info.
- Deliverable:
  - Fingerprint fields in CLI and browser JSON reports.

## 4) Hard Fail vs Heuristic Warning Separation
- Goal: Reduce false positives while preserving strict correctness.
- Action:
  - Keep deterministic spec mismatches as errors.
  - Shift low-confidence heuristics to warnings in strict mode only when confidence is low.
- Deliverable:
  - Severity policy table and coverage tests by pattern family.

## 5) Central Exception Governance
- Goal: Avoid hidden one-off logic and track exception ownership.
- Action:
  - Maintain exceptions in `rules/validator_exceptions.json` with owner/reason/review date.
- Deliverable:
  - Structured exception registry with lifecycle metadata.

## 6) Golden Baseline Regression Gate
- Goal: Prevent unnoticed behavior regressions for key partner pairs.
- Action:
  - Store frozen outputs for known critical mappings and diff in CI.
- Deliverable:
  - Baseline snapshots under `results/` and tests that enforce compatibility.

## 7) Pattern-Family Test Matrix
- Goal: Isolate regressions by semantic pattern family.
- Action:
  - Maintain explicit tests for hardcode, if/else, date-format, length-based, concat, char-offset, and substring rules.
- Deliverable:
  - Expanded tests in `tests/test_report_format.py`, `tests/test_web.py`, and `tests/test_main_cli.py`.

## 8) Unresolved-Input Guardrails
- Goal: Avoid false mismatches when expected values cannot be resolved.
- Action:
  - Short-circuit to skip-with-reason when expected value derivation fails.
- Deliverable:
  - Deterministic skip reason in `rule_decisions` and diagnostics.

## 9) Shadow Mode Rollout
- Goal: Safely ship stricter logic.
- Action:
  - Run candidate logic in shadow mode and compare with current output before promotion.
- Deliverable:
  - Shadow delta report for selected partner datasets.

## 10) Parser Confidence + Uncertainty Surfacing
- Goal: Expose confidence and avoid over-asserting uncertain parses.
- Action:
  - Attach parse confidence and uncertainty reason to unsupported or ambiguous conditions.
- Deliverable:
  - Confidence and ambiguity metadata in diagnostics and inspector context.

## Current Phase Seeded in Code
- Exception registry file added: `rules/validator_exceptions.json`.
- Reason-code and fingerprint plumbing is now being added to core and web report payloads.
