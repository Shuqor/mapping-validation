
import argparse

from core.validate import validate_mapping, write_report


def _print_human_summary(result: dict, max_items: int = 3) -> None:
    human = result.get("human_summary", {})
    headline = human.get("headline")
    if headline:
        print(headline)

    issue_breakdown = human.get("issue_breakdown", [])
    if issue_breakdown:
        print("Issue breakdown:")
        for item in issue_breakdown:
            issue = item.get("issue", "Issue")
            count = item.get("count", 0)
            print(f"- {issue}: {count}")

    top_issues = human.get("what_to_fix_first") or result.get("top_critical_errors", [])
    if top_issues:
        print(f"Top {min(max_items, len(top_issues))} issue(s) to fix first:")
        for issue in top_issues[:max_items]:
            print("-", issue)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mapping Validation Program")
    parser.add_argument("--spec", default="rules/spec.xlsx", help="Path to mapping spec Excel file")
    parser.add_argument("--input", default="samples/input.xml", help="Path to source input XML")
    parser.add_argument("--output", default="samples/output.xml", help="Path to target output XML")
    parser.add_argument("--report", default="results/report.json", help="Path to write JSON report")
    parser.add_argument(
        "--mode",
        default="strict",
        choices=["strict", "lenient"],
        help="Validation mode: strict fails on errors, lenient reports warnings",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = validate_mapping(args.spec, args.input, args.output, validation_mode=args.mode)
    report_path = write_report(result, args.report)

    status = result.get("summary", {}).get("status")
    if status == "PASS_WITH_WARNINGS":
        print("VALIDATION COMPLETED WITH WARNINGS")
        _print_human_summary(result, max_items=3)
    elif result["errors"]:
        print("VALIDATION FAILED")
        _print_human_summary(result, max_items=3)
    else:
        print("VALIDATION PASSED")
        _print_human_summary(result, max_items=3)

    print(f"Report written to {report_path}")
    return 0 if result.get("valid", False) else 1

if __name__ == "__main__":
    raise SystemExit(main())
