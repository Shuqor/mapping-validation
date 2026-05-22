# Stage 10 Sync Gate Expansion Policy

This policy keeps parser-validator synchronization strict while expanding coverage safely.

## Rules

1. Expand the sync fixture list in small batches.
2. Add broad format/workbook family coverage before depth in one family.
3. Keep each added spec deterministic and repeatable.
4. If any new fixture fails, pause expansion and fix root cause first.

## Batch Procedure

1. Add one to three new representative specs to `tests/test_parser_validator_sync_gate.py`.
2. Run only the sync gate locally.
3. If green, merge and observe CI trend.
4. Repeat after previous batch remains stable.

## Coverage Priority

1. Global/foundational sample (`rules/spec.xlsx`).
2. INTTRA X12 and EDIFACT specs.
3. JABIL and DHL custom layouts.
4. P&G cXML/CDM family.
