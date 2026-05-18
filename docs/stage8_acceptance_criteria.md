# Stage 8 Acceptance Criteria (Frozen)

This document freezes the Stage 8 contract for semantic rule expansion.

## Status

- Stage 8 is complete and contract-frozen.
- Any change that alters the criteria below must be treated as a planned contract update.

## Functional Scope (Frozen)

- Semantic condition matching uses one global profile for all specs.
- Family-specific semantic overrides are disabled.
- Unsupported condition handling includes deterministic similarity guidance.
- Browser validator and backend validator expose equivalent semantic summary payloads.

## Contract Fields (Frozen)

The following report payload sections are Stage 8 contract surfaces:

- `rule_support_summary`
- `semantic_summary`
- `skipped_rules[*]` semantic guidance fields

Minimum required semantic telemetry includes:

- coverage counts for total vs unsupported condition rules
- top unsupported condition phrases
- top suggested pattern families
- ambiguity counters
- semantic thresholds in effect
- promote-to-generic candidates

## Regression Gates (Frozen)

The Stage 8 gate is considered passing only when all of the following pass:

1. `tests/test_semantic_similarity.py`
2. `tests/test_web.py`
3. `tests/test_report_format.py`
4. `tests/test_structure_contract_fixtures.py`
5. `tests/test_semantic_performance_guardrail.py`
6. `tests/test_stage8_baseline_snapshot.py`

## Baseline Snapshot Artifact (Frozen)

- Baseline file: `results/stage8_validation_baseline.json`
- Snapshot test: `tests/test_stage8_baseline_snapshot.py`
- Regeneration helper: `scripts/regenerate_stage8_baseline.py`
- Snapshot projection intentionally excludes volatile fields such as report ID and timestamps.

Intentional baseline update workflow:

1. Regenerate the baseline artifact:
	- `python scripts/regenerate_stage8_baseline.py`
2. Validate the snapshot gate:
	- `python -m pytest tests/test_stage8_baseline_snapshot.py -q`
3. Validate the frozen Stage 8 gate set:
	- `python -m pytest tests/test_semantic_similarity.py tests/test_web.py tests/test_report_format.py tests/test_structure_contract_fixtures.py tests/test_semantic_performance_guardrail.py tests/test_stage8_baseline_snapshot.py -q`
4. Include rationale for baseline drift in the PR description.

## Real-World Corpus Requirement (Frozen)

- `tests/fixtures/semantic_real_world_corpus.json` must retain at least 25 curated entries.
- New entries should prefer realistic partner phrases and include expected semantic behavior.

## Change Control

Before changing frozen behavior:

1. Update this document with rationale.
2. Update Stage 9 handoff notes for migration impact.
3. Update regression fixtures/tests in the same PR.
