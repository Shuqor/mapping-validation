import argparse
import json
from pathlib import Path


def _lookup_warning_count(report: dict) -> int:
    warnings = report.get("warnings") if isinstance(report, dict) else []
    if not isinstance(warnings, list):
        return 0
    count = 0
    for item in warnings:
        text = str(item or "").strip().lower()
        if not text:
            continue
        if "lookup ambiguity finding(s) were downgraded" in text or "lookup conflict finding(s) were downgraded" in text:
            count += 1
    return count


def check_lookup_warning_budget(report: dict, max_lookup_downgrade_warnings: int) -> list[str]:
    observed = _lookup_warning_count(report)
    limit = max(int(max_lookup_downgrade_warnings), 0)
    if observed > limit:
        return [
            "lookup_warning_budget exceeded: "
            f"observed={observed}, max_allowed={limit}. "
            "Investigate lookup-table ambiguity/conflict suppression drift."
        ]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Blocking budget check for lookup ambiguity/conflict downgrade warnings"
    )
    parser.add_argument("--report", required=True, help="Path to validation report JSON")
    parser.add_argument(
        "--max-lookup-downgrade-warnings",
        type=int,
        default=0,
        help="Maximum allowed number of lookup downgrade warnings",
    )
    args = parser.parse_args()

    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    issues = check_lookup_warning_budget(report, args.max_lookup_downgrade_warnings)
    if issues:
        print("Lookup warning budget check failed:")
        for issue in issues:
            print(f"- {issue}")
        return 1

    print("Lookup warning budget check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
