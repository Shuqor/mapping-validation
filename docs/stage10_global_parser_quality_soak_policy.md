# Stage 10 Global Parser Quality Soak Policy

This policy defines when the global parser quality check should remain warning-only and when it can be promoted to blocking.

## Scope

- Check script: `scripts/check_global_parser_quality.py`
- Artifact: `results/ci/global_parser_quality.json`
- Coverage: all `rules/*.xlsx` specs

## Soak Phase

- Run in non-blocking mode during stabilization.
- Collect findings every CI run and review trend, not one-off noise.
- Treat parser exceptions as highest-priority issues.

## Promotion Gate

Promote to blocking mode only when all are true:

1. No parser exceptions reported across recent runs.
2. No confidence violations outside allowed set.
3. Ambiguity counts stay within configured threshold.
4. Findings are either fixed or explicitly approved as temporary exceptions.

## Blocking Mode

- Enable script fail mode: `--fail-on-findings`.
- In CI, this mode is now enabled as the default Stage 10 gate.
- Any new finding fails the gate and requires remediation or rollback.

## Closeout Evidence

- Stage 10 closeout evidence is checked by `scripts/check_stage10_closeout_evidence.py`.
- Evidence file: `results/ci/stage10_release_evidence.json`.
