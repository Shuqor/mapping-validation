# AGENTS Policy

## Dual-Path Lookup Parity (Required)

- For lookup-table validation changes, update both implementations when available:
  - Python backend logic in core/validate.py.
  - Browser validator logic in web/index.html.
- Treat one-sided lookup changes as incomplete unless explicitly requested.

## Change Checklist for Lookup Features

- Update extraction/parsing behavior on both sides.
- Update resolution/scoring behavior on both sides.
- Update mismatch categories and support counters on both sides.
- Add or update tests that verify backend-browser parity behavior.

## If Parity Cannot Be Completed Safely

- Document what was changed.
- Document the exact remaining parity gap.
- Provide the concrete follow-up patch scope to close the gap.
