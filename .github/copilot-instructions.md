# Repository Copilot Instructions

## Dual-Path Parity Policy

- For feature and validation-rule changes, implement parity in both paths when available:
  - Python backend validator logic.
  - Browser validator logic.
- Do not ship one-sided behavior unless explicitly requested by the user.
- If one side cannot be safely updated in the same change, report:
  - What was updated.
  - What parity gap remains.
  - The concrete follow-up change required to close the gap.

## Validation Expectations

- Add or update tests for both sides where practical.
- Prefer focused regression tests for new condition families and mismatch categories.
- Preserve existing report contracts unless a contract change is explicitly requested.
