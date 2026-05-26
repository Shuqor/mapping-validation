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


def main() -> int:
    parser = argparse.ArgumentParser(description="Build consolidated quality scorecard artifact")
    parser.add_argument("--global-parser", default="results/ci/global_parser_quality.json")
    parser.add_argument("--global-validator", default="results/ci/global_validator_health.json")
    parser.add_argument("--calibration", default="results/ci/confidence_calibration.json")
    parser.add_argument("--profile-budget", default="results/ci/profile_budget_report.json")
    parser.add_argument("--trend", default="results/ci/quality_trend_history.json")
    parser.add_argument("--output", default="results/ci/quality_scorecard.json")
    args = parser.parse_args()

    gp = _load(Path(args.global_parser))
    gv = _load(Path(args.global_validator))
    cal = _load(Path(args.calibration))
    pb = _load(Path(args.profile_budget))
    tr = _load(Path(args.trend))

    scorecard = {
        "global_parser_quality": gp.get("projection", gp),
        "global_validator_health": gv.get("projection", gv),
        "confidence_calibration": cal.get("overall", cal),
        "profile_budgets": {
            "finding_count": int(pb.get("finding_count", 0) or 0),
            "profiles": pb.get("profiles", {}),
        },
        "trend": {
            "latest": tr.get("latest", {}),
            "points": len(tr.get("history", [])) if isinstance(tr.get("history"), list) else 0,
        },
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(scorecard, indent=2) + "\n", encoding="utf-8")

    print(f"Quality scorecard written: {out_path.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
