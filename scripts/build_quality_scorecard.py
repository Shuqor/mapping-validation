from __future__ import annotations

import argparse
import json
from pathlib import Path


def _load(path: Path) -> dict:
    if not path.exists():
        return {"_missing": path.as_posix()}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"_invalid": path.as_posix()}
    return payload if isinstance(payload, dict) else {"_invalid": path.as_posix()}


def _family_budget_summary(profile_budgets: dict) -> tuple[int, dict]:
    family_finding_count = 0
    families: dict = {}

    for profile_name, profile_payload in profile_budgets.items():
        if not isinstance(profile_payload, dict):
            continue
        family_map = profile_payload.get("families")
        if not isinstance(family_map, dict):
            continue

        normalized_family_map: dict[str, dict] = {}
        for family_name, family_payload in family_map.items():
            if isinstance(family_payload, dict):
                finding_count = int(family_payload.get("finding_count", 0) or 0)
                # Backward compatibility: infer findings from rates and budget when explicit counts are absent.
                if finding_count == 0 and "finding_count" not in family_payload:
                    budget = family_payload.get("budget") if isinstance(family_payload.get("budget"), dict) else {}
                    parsed_only_rate = float(family_payload.get("parsed_only_rate", 0.0) or 0.0)
                    unsupported_rate = float(family_payload.get("unsupported_rate", 0.0) or 0.0)
                    max_parsed_only_rate = float(budget.get("max_parsed_only_rate", 1.0) or 1.0)
                    max_unsupported_rate = float(budget.get("max_unsupported_rate", 1.0) or 1.0)
                    if parsed_only_rate > max_parsed_only_rate:
                        finding_count += 1
                    if unsupported_rate > max_unsupported_rate:
                        finding_count += 1

                normalized_payload = dict(family_payload)
                normalized_payload["finding_count"] = finding_count
                normalized_family_map[str(family_name)] = normalized_payload
                family_finding_count += finding_count

        families[profile_name] = normalized_family_map

    return family_finding_count, families


def main() -> int:
    parser = argparse.ArgumentParser(description="Build consolidated quality scorecard artifact")
    parser.add_argument("--global-parser", default="results/ci/global_parser_quality.json")
    parser.add_argument("--global-validator", default="results/ci/global_validator_health.json")
    parser.add_argument("--calibration", default="results/ci/confidence_calibration.json")
    parser.add_argument("--profile-budget", default="results/ci/profile_budget_report.json")
    parser.add_argument("--trend", default="results/ci/quality_trend_history.json")
    parser.add_argument("--unknown-triage", default="results/ci/unknown_rule_triage.json")
    parser.add_argument("--output", default="results/ci/quality_scorecard.json")
    args = parser.parse_args()

    gp = _load(Path(args.global_parser))
    gv = _load(Path(args.global_validator))
    cal = _load(Path(args.calibration))
    pb = _load(Path(args.profile_budget))
    tr = _load(Path(args.trend))
    ut = _load(Path(args.unknown_triage))
    family_finding_count, family_map = _family_budget_summary(pb.get("profiles", {}))

    scorecard = {
        "global_parser_quality": gp.get("projection", gp),
        "global_validator_health": gv.get("projection", gv),
        "confidence_calibration": cal.get("overall", cal),
        "profile_budgets": {
            "finding_count": int(pb.get("finding_count", 0) or 0),
            "profiles": pb.get("profiles", {}),
            "family_finding_count": family_finding_count,
            "families": family_map,
        },
        "trend": {
            "latest": tr.get("latest", {}),
            "points": len(tr.get("history", [])) if isinstance(tr.get("history"), list) else 0,
        },
        "unknown_rule_triage": {
            "summary": ut.get("summary", ut),
            "top_cluster_count": len(ut.get("clusters", [])) if isinstance(ut.get("clusters"), list) else 0,
        },
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(scorecard, indent=2) + "\n", encoding="utf-8")

    print(f"Quality scorecard written: {out_path.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
