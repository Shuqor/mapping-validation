# Stage 10 Triage Runbook

Use this runbook to classify validation mismatches consistently.

## Categories

- parser_gap: Spec could not be parsed deterministically or parser confidence is low.
- rule_ambiguity: Rule text is parsed but condition is not deterministic enough to enforce.
- data_mismatch: Rule is enforceable and payload output does not satisfy expected mapping behavior.

## Decision Flow

1. Check parser diagnostics.
- If parser status is low_confidence or parsed_with_fallbacks and issue references structural extraction behavior, classify as parser_gap.

2. Check rule decisions.
- If issue maps to parsed_only or unsupported status, classify as rule_ambiguity.

3. Check enforceable rule failures.
- If issue is from an enforceable rule and expected vs found values differ, classify as data_mismatch.

## Ownership

- parser_gap: parser maintainers
- rule_ambiguity: semantic rule owners + mapper who authored condition text
- data_mismatch: mapping implementation team

## Required Evidence in Bug Report

- spec file name and row number
- target path and source path
- parser status and confidence
- rule decision status (enforced/parsed_only/unsupported)
- expected vs found payload values
- proposed next action
