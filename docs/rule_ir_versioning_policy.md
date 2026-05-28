# Rule IR Versioning Policy

This policy governs evolution of `rule_ir` payloads emitted by the parser.

## Version Model

- `ir_version` uses `major.minor`.
- `major` changes indicate breaking schema changes.
- `minor` changes indicate backward-compatible additions.

## Compatibility Rules

- Current producer emits `ir_version=1.1`.
- Consumers must accept all `1.x` payloads and ignore unknown fields.
- New fields in `1.x` are additive only.
- Existing required fields cannot be renamed or removed inside `1.x`.

## Deprecation Window

- A breaking change requires a `2.0` cut.
- Prior major (`1.x`) remains supported for at least 2 release cycles.
- During deprecation, CI must validate both current and previous-major payload examples.

## Change Process

- Any IR schema update must include:
  - schema update in `schemas/rule_ir.schema.json`
  - contract test updates
  - release note entry describing migration impact
- Breaking changes require explicit migration guidance for validator/report consumers.

## Consumer Guidance

- Prefer `identity.rule_id` and `identity.rule_fingerprint` for stable tracking.
- Prefer `condition.normalized` and `provenance.row` for deterministic reasoning.
- Treat `semantic.*` as best-effort hints, not strict enforcement input unless validated.
