# Stage 10 Operational Governance

This note captures the minimum governance policy for Stage 10 delivery.

## Contract Freeze

The following report fields are treated as contract fields:

- rule_decisions
- error_diagnostics
- parser_diagnostics.token_resolution_diagnostics
- parser_diagnostics.rollout_guardrails

Schema updates to these fields must include release notes and test updates.

## Rollout Policy

Rule family rollout follows:

1. shadow
2. observe
3. enforce

Promotion from one stage to the next requires real-spec evidence, including false-positive impact.

## Quality Target

- False-positive rate target: less than 2 percent on curated real-spec runs.
- Trend requirement: non-worsening over the previous two release candidates.

## Performance Guardrails

Large X12 and EDIFACT fixtures must continue to pass performance guardrail tests.
Threshold increases require rationale in pull request notes.

## Release Gate

A Stage 10 release candidate requires all of the following:

- Stage 8 frozen regression gate passing.
- Stage 9 bridge/parity gate passing.
- Browser parity workflow stable for seven consecutive main runs (pass or explicit runtime-unavailable skip).
- Diagnostics contract unchanged, or deltas documented and validated.
