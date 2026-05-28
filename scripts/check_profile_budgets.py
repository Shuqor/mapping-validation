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


def _budget_for(budgets: dict, fallback: dict, key: str) -> dict:
    budget = budgets.get(key)
    if isinstance(budget, dict):
        return budget
    return fallback if isinstance(fallback, dict) else {}


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
    family_budgets = budgets.get("families") if isinstance(budgets.get("families"), dict) else {}

    specs = sorted(Path(args.rules_dir).glob("*.xlsx"))
    stats: dict[str, dict[str, int]] = defaultdict(lambda: {"checked": 0, "parsed_only": 0, "unsupported": 0, "spec_count": 0})
    family_stats: dict[str, dict[str, dict[str, int]]] = defaultdict(lambda: defaultdict(lambda: {"decision_count": 0, "parsed_only": 0, "unsupported": 0}))

    for spec_path in specs:
        profile = str(validate_module._get_semantic_profile(str(spec_path)).get("profile_key", "generic"))
        report = validate_module.validate_spec_coverage(str(spec_path))
        support = report.get("rule_support_summary") if isinstance(report.get("rule_support_summary"), dict) else {}
        decisions = report.get("rule_decisions") if isinstance(report.get("rule_decisions"), list) else []

        stats[profile]["checked"] += int(report.get("checked_rules", 0) or 0)
        stats[profile]["parsed_only"] += int(support.get("parsed_only_rules", 0) or 0)
        stats[profile]["unsupported"] += int(support.get("unsupported_rules", 0) or 0)
        stats[profile]["spec_count"] += 1

        for decision in decisions:
            if not isinstance(decision, dict):
                continue
            family = str(decision.get("family") or "unspecified").strip() or "unspecified"
            status = str(decision.get("status") or "").strip()
            family_stats[profile][family]["decision_count"] += 1
            if status == "parsed_only":
                family_stats[profile][family]["parsed_only"] += 1
            elif status == "unsupported":
                family_stats[profile][family]["unsupported"] += 1

    findings: list[str] = []
    profile_report: dict[str, dict] = {}
    for profile, agg in sorted(stats.items()):
        checked = int(agg["checked"])
        parsed_only = int(agg["parsed_only"])
        unsupported = int(agg["unsupported"])

        parsed_only_rate = (parsed_only / checked) if checked else 0.0
        unsupported_rate = (unsupported / checked) if checked else 0.0

        budget = _budget_for(profile_budgets, default_budget, profile)
        max_parsed_only_rate = float(budget.get("max_parsed_only_rate", 1.0) or 1.0)
        max_unsupported_rate = float(budget.get("max_unsupported_rate", 1.0) or 1.0)
        profile_family_report: dict[str, dict] = {}
        profile_findings: list[str] = []

        for family, fam_agg in sorted(family_stats.get(profile, {}).items()):
            family_decisions = int(fam_agg["decision_count"])
            family_parsed_only = int(fam_agg["parsed_only"])
            family_unsupported = int(fam_agg["unsupported"])
            family_parsed_only_rate = (family_parsed_only / family_decisions) if family_decisions else 0.0
            family_unsupported_rate = (family_unsupported / family_decisions) if family_decisions else 0.0
            family_budget = family_budgets.get(family) if isinstance(family_budgets.get(family), dict) else {}
            # Family-specific gates are opt-in: only families explicitly configured in
            # budgets["families"] should enforce per-family parsed-only/unsupported rates.
            if family_budget:
                max_family_parsed_only_rate = float(
                    family_budget.get("max_parsed_only_rate", max_parsed_only_rate) or max_parsed_only_rate
                )
                max_family_unsupported_rate = float(
                    family_budget.get("max_unsupported_rate", max_unsupported_rate) or max_unsupported_rate
                )
            else:
                max_family_parsed_only_rate = 1.0
                max_family_unsupported_rate = 1.0
            family_findings: list[str] = []

            if family_parsed_only_rate > max_family_parsed_only_rate:
                finding = (
                    f"{profile}/{family}: parsed_only_rate={family_parsed_only_rate:.4f} "
                    f"exceeds max_parsed_only_rate={max_family_parsed_only_rate:.4f}"
                )
                findings.append(finding)
                family_findings.append(finding)
                profile_findings.append(finding)
            if family_unsupported_rate > max_family_unsupported_rate:
                finding = (
                    f"{profile}/{family}: unsupported_rate={family_unsupported_rate:.4f} "
                    f"exceeds max_unsupported_rate={max_family_unsupported_rate:.4f}"
                )
                findings.append(finding)
                family_findings.append(finding)
                profile_findings.append(finding)

            profile_family_report[family] = {
                "decision_count": family_decisions,
                "parsed_only_rules": family_parsed_only,
                "unsupported_rules": family_unsupported,
                "parsed_only_rate": round(family_parsed_only_rate, 6),
                "unsupported_rate": round(family_unsupported_rate, 6),
                "budget": {
                    "max_parsed_only_rate": max_family_parsed_only_rate,
                    "max_unsupported_rate": max_family_unsupported_rate,
                },
                "finding_count": len(family_findings),
                "findings": family_findings,
            }

        if parsed_only_rate > max_parsed_only_rate:
            finding = f"{profile}: parsed_only_rate={parsed_only_rate:.4f} exceeds max_parsed_only_rate={max_parsed_only_rate:.4f}"
            findings.append(finding)
            profile_findings.append(finding)
        if unsupported_rate > max_unsupported_rate:
            finding = f"{profile}: unsupported_rate={unsupported_rate:.4f} exceeds max_unsupported_rate={max_unsupported_rate:.4f}"
            findings.append(finding)
            profile_findings.append(finding)

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
            "finding_count": len(profile_findings),
            "findings": profile_findings,
            "families": profile_family_report,
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
