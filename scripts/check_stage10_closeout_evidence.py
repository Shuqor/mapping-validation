import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _validate_false_positive_trend(payload: dict, issues: list[str]) -> None:
    target = float(payload.get("false_positive_target_percent", 2.0) or 2.0)
    rates = payload.get("false_positive_rates_percent", [])
    if not isinstance(rates, list) or len(rates) < 3:
        issues.append("false_positive_rates_percent must include at least 3 release-candidate values")
        return

    values = [float(item) for item in rates]
    current = values[-1]
    prev1 = values[-2]
    prev2 = values[-3]

    if current > target:
        issues.append(f"false-positive current={current:.3f}% exceeds target={target:.3f}%")

    # Non-worsening across the most recent two transitions.
    if current > prev1 or prev1 > prev2:
        issues.append(
            "false-positive trend worsened over the last two release-candidate transitions "
            f"(prev2={prev2:.3f}%, prev1={prev1:.3f}%, current={current:.3f}%)"
        )


def _parse_iso8601_utc(value: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise ValueError("empty timestamp")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _validate_evidence_freshness(payload: dict, max_age_days: int, issues: list[str]) -> None:
    generated_at = payload.get("generated_at_utc")
    if not generated_at:
        issues.append("generated_at_utc is required")
        return

    try:
        generated_dt = _parse_iso8601_utc(str(generated_at))
    except Exception as exc:  # noqa: BLE001
        issues.append(f"generated_at_utc is invalid: {exc}")
        return

    now_utc = datetime.now(timezone.utc)
    age_days = (now_utc - generated_dt).total_seconds() / 86400.0
    if age_days > float(max_age_days):
        issues.append(
            f"evidence is stale: age_days={age_days:.2f} exceeds max_age_days={int(max_age_days)}"
        )


def check_closeout_evidence(payload: dict, *, max_evidence_age_days: int = 30) -> list[str]:
    issues: list[str] = []

    _validate_evidence_freshness(payload, int(max_evidence_age_days), issues)

    if int(payload.get("browser_parity_consecutive_main_runs", 0) or 0) < 7:
        issues.append("browser_parity_consecutive_main_runs must be at least 7")

    diagnostics_contract_changed = _as_bool(payload.get("diagnostics_contract_changed", False))
    schema_deltas_documented = _as_bool(payload.get("schema_deltas_documented_and_validated", False))
    if diagnostics_contract_changed and not schema_deltas_documented:
        issues.append("diagnostics contract changed but schema_deltas_documented_and_validated is false")

    if not _as_bool(payload.get("shadow_promotion_evidence_present", False)):
        issues.append("shadow_promotion_evidence_present must be true")

    if not _as_bool(payload.get("triage_runbook_applied", False)):
        issues.append("triage_runbook_applied must be true")

    _validate_false_positive_trend(payload, issues)
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Stage 10 closeout evidence and trend gates")
    parser.add_argument(
        "--evidence",
        default="results/ci/stage10_release_evidence.json",
        help="Path to Stage 10 release evidence JSON",
    )
    parser.add_argument(
        "--max-evidence-age-days",
        type=int,
        default=30,
        help="Maximum allowed age of evidence timestamp (generated_at_utc)",
    )
    args = parser.parse_args()

    evidence_path = Path(args.evidence)
    if not evidence_path.exists():
        print(f"Missing evidence file: {evidence_path}")
        return 1

    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    issues = check_closeout_evidence(payload, max_evidence_age_days=args.max_evidence_age_days)

    if issues:
        print("Stage 10 closeout evidence check FAILED")
        for issue in issues:
            print(f"- {issue}")
        return 1

    print("Stage 10 closeout evidence check PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
