from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import core.validate as validate_module


def _load_budgets(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Budget file must be a JSON object")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Check profile-specific parsed-only/unsupported budgets")
    parser.add_argument("--rules-dir", default="rules", help="Rules directory containing .xlsx specs")
    parser.add_argument("--budgets", default="rules/profile_budgets.json", help="Profile budget JSON path")
    parser.add_argument("--output", default="results/ci/profile_budget_report.json", help="Output report path")
    parser.add_argument("--fail-on-findings", action="store_true", help="Fail when budget findings are present")
    args = parser.parse_args()

    budgets = _load_budgets(Path(args.budgets))
    default_budget = budgets.get("default") if isinstance(budgets.get("default"), dict) else {}
    profile_budgets = budgets.get("profiles") if isinstance(budgets.get("profiles"), dict) else {}

    specs = sorted(Path(args.rules_dir).glob("*.xlsx"))
    stats: dict[str, dict[str, int]] = defaultdict(lambda: {"checked": 0, "parsed_only": 0, "unsupported": 0, "spec_count": 0})

    for spec_path in specs:
        profile = str(validate_module._get_semantic_profile(str(spec_path)).get("profile_key", "generic"))
        report = validate_module.validate_spec_coverage(str(spec_path))
        support = report.get("rule_support_summary") if isinstance(report.get("rule_support_summary"), dict) else {}

        stats[profile]["checked"] += int(report.get("checked_rules", 0) or 0)
        stats[profile]["parsed_only"] += int(support.get("parsed_only_rules", 0) or 0)
        stats[profile]["unsupported"] += int(support.get("unsupported_rules", 0) or 0)
        stats[profile]["spec_count"] += 1

    findings: list[str] = []
    profile_report: dict[str, dict] = {}
    for profile, agg in sorted(stats.items()):
        checked = int(agg["checked"])
        parsed_only = int(agg["parsed_only"])
        unsupported = int(agg["unsupported"])

        parsed_only_rate = (parsed_only / checked) if checked else 0.0
        unsupported_rate = (unsupported / checked) if checked else 0.0

        budget = profile_budgets.get(profile) if isinstance(profile_budgets.get(profile), dict) else default_budget
        max_parsed_only_rate = float(budget.get("max_parsed_only_rate", 1.0) or 1.0)
        max_unsupported_rate = float(budget.get("max_unsupported_rate", 1.0) or 1.0)

        if parsed_only_rate > max_parsed_only_rate:
            findings.append(
                f"{profile}: parsed_only_rate={parsed_only_rate:.4f} exceeds max_parsed_only_rate={max_parsed_only_rate:.4f}"
            )
        if unsupported_rate > max_unsupported_rate:
            findings.append(
                f"{profile}: unsupported_rate={unsupported_rate:.4f} exceeds max_unsupported_rate={max_unsupported_rate:.4f}"
            )

        profile_report[profile] = {
            "spec_count": int(agg["spec_count"]),
            "checked_rules": checked,
            "parsed_only_rules": parsed_only,
            "unsupported_rules": unsupported,
            "parsed_only_rate": round(parsed_only_rate, 6),
            "unsupported_rate": round(unsupported_rate, 6),
            "budget": {
                "max_parsed_only_rate": max_parsed_only_rate,
                "max_unsupported_rate": max_unsupported_rate,
            },
        }

    out_payload = {
        "rules_dir": str(Path(args.rules_dir).as_posix()),
        "budgets": budgets,
        "profiles": profile_report,
        "finding_count": len(findings),
        "findings": findings,
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out_payload, indent=2) + "\n", encoding="utf-8")

    if findings:
        mode = "blocking" if args.fail_on_findings else "non-blocking"
        print(f"Profile budget findings ({mode}): {len(findings)}")
        for finding in findings:
            print(f"::warning::{finding}")
    else:
        print("Profile budget check passed")

    print(f"Artifact written: {out_path.as_posix()}")
    if findings and args.fail_on_findings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
