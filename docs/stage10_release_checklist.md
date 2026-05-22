# Stage 10 Release Checklist

Use this checklist before sign-off for Stage 10 stabilization changes.

## Mandatory Gates

- Parser-validator sync gate passes.
- Deterministic precedence gate passes.
- Stage 10 spec coverage baseline snapshot gate passes.
- Stage 10 strict pair baseline snapshot gate passes.
- Parser collapse baseline snapshot gate passes.
- Reason-code contract gate passes.
- Warning taxonomy contract gate passes.
- Rule-intent golden pack gate passes.
- Backend-browser decision parity contract gate passes.

## Visibility Gates

- Global parser quality artifact is generated.
- Warning taxonomy drift check is reviewed.
- Parser uncertainty profile check is reviewed.

## Command

Run the consolidated checklist:

`python scripts/run_stage10_readiness_check.py`

If all commands pass, Stage 10 readiness is green for the selected gates.
