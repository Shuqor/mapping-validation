import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.check_parser_uncertainty_budget import check_uncertainty_budget


def select_profile(report: dict, config: dict) -> tuple[str, dict]:
    default_profile = config.get("default") if isinstance(config.get("default"), dict) else {}
    spec_path = str((report.get("inputs") or {}).get("spec_path") or "")

    profiles = config.get("profiles") if isinstance(config.get("profiles"), list) else []
    for profile in profiles:
        if not isinstance(profile, dict):
            continue
        marker = str(profile.get("spec_path_contains") or "").strip()
        if marker and marker in spec_path:
            profile_name = str(profile.get("id") or marker)
            return profile_name, profile

    return "default", default_profile


def profile_budget_issues(report: dict, config: dict) -> tuple[str, list[str]]:
    profile_name, profile = select_profile(report, config)
    max_ambiguities = int(profile.get("max_ambiguities", 0) or 0)
    allowed_confidence = tuple(str(item).strip().lower() for item in profile.get("allowed_confidence", ["high"]) if str(item).strip())
    issues = check_uncertainty_budget(
        report,
        max_ambiguities=max_ambiguities,
        allowed_confidence=allowed_confidence or ("high",),
    )
    return profile_name, issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Warn-only parser uncertainty profile checker")
    parser.add_argument("--report", required=True, help="Path to validation report JSON")
    parser.add_argument(
        "--config",
        default="rules/parser_uncertainty_budgets.json",
        help="Path to parser uncertainty profile configuration",
    )
    args = parser.parse_args()

    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))

    profile_name, issues = profile_budget_issues(report, config)
    print(f"Parser uncertainty profile: {profile_name}")

    if issues:
        print("Parser uncertainty profile drift detected (non-blocking):")
        for issue in issues:
            print(f"::warning::{issue}")
    else:
        print("Parser uncertainty profile check: no drift detected")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
