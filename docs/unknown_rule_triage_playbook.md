# Unknown Rule Triage Playbook

This playbook is the pre-agent path to near AI-level behavior for unexpected rules.

## Objectives

- Keep deterministic quality high for known patterns.
- Convert unknown rules into a managed backlog with evidence.
- Reduce unsupported/parsed-only rates each week.

## 1) Unknown Rule Triage Pipeline

- Generate `results/ci/unknown_rule_triage.json` from runtime report:
  - clusters unknown decisions (`unsupported`, `parsed_only`, abstain-like)
  - groups by semantic token similarity
  - computes review priority

Command:

```bash
python scripts/build_unknown_rule_triage.py \
  --report results/ci/stage10_spec_coverage_runtime.json \
  --calibration results/ci/confidence_calibration.json \
  --output results/ci/unknown_rule_triage.json
```

## 2) Retrieval Layer (nearest known evidence)

- Each unknown row stores `nearest_known` examples from supported rows using token similarity.
- Use those examples to decide whether to patch parser logic or semantic intent rules.

## 3) Confidence Calibration + Abstain Guidance

- Calibration artifact contributes an abstain floor used in triage.
- Treat low-confidence rows as unknown backlog unless evidence supports enforcement.

## 4) Counterfactual Validation

- Triage emits conflict flags (for example direct-map-like rows marked unsupported).
- Prioritize clusters with counterfactual flags to reduce false negatives/positives.

## 5) Canonicalization Improvements

- Use normalized condition text and tokenized semantics in triage grouping.
- Feed recurring variants back into parser normalization and semantic profiles.

## 6) Rule IR-Centered Operations

- Continue using `rule_ir` and provenance for deterministic debugging.
- Keep parser/validator alignment through shared condition normalization semantics.

## 7) Deterministic Patch Suggestions

- Triage emits `suggested_parser_patches` as candidate regex entries.
- Apply only after review; keep approvals explicit.

## 8) Closed-Loop Quality Program

Weekly loop:

1. Review top unknown clusters by `review_priority`.
2. Approve parser or semantic pattern updates.
3. Add focused tests for promoted patterns.
4. Re-run CI gates and refresh baselines intentionally.

Key KPIs:

- `unknown_ratio`
- `unsupported` count
- cluster backlog size
- oldest unresolved cluster age
