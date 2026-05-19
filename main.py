
import argparse
from pathlib import Path

from core.validate import validate_mapping_from_payload_bytes, write_report


def _print_human_summary(result: dict, max_items: int | None = None) -> None:
    human = result.get("human_summary", {})
    headline = human.get("headline")
    if headline:
        print(headline)

    parser_status = result.get("summary", {}).get("parser_status")
    parser_confidence = result.get("summary", {}).get("parser_confidence")
    if parser_status and parser_confidence:
        print(f"Parser status: {parser_status} (confidence: {parser_confidence})")

    support = result.get("rule_support_summary", {})
    parsed_only = support.get("parsed_only_rules", 0)
    unsupported = support.get("unsupported_rules", 0)
    if parsed_only or unsupported:
        print(
            "Rule support: "
            f"enforced={support.get('enforced_rules', 0)}, "
            f"parsed_only={parsed_only}, unsupported={unsupported}"
        )

    adapter_pipeline = result.get("adapter_pipeline") or {}
    if adapter_pipeline.get("enabled"):
        mode = str(adapter_pipeline.get("mode") or "homogeneous")
        input_format = str(adapter_pipeline.get("input_format") or "payload").upper()
        output_format = str(adapter_pipeline.get("output_format") or input_format).upper()
        if mode == "cross_format":
            print(f"Adapter pipeline: {input_format} -> {output_format} (cross-format bridge)")
        else:
            print(f"Adapter pipeline: {input_format} (homogeneous bridge)")

    issue_breakdown = human.get("issue_breakdown", [])
    if issue_breakdown:
        print("Issue breakdown:")
        for item in issue_breakdown:
            issue = item.get("issue", "Issue")
            count = item.get("count", 0)
            print(f"- {issue}: {count}")

    top_issues = human.get("what_to_fix_first") or result.get("top_critical_errors", [])
    if top_issues:
        print(f"Issue(s) to fix: {len(top_issues)}")
        visible_issues = top_issues if max_items is None else top_issues[:max_items]
        for issue in visible_issues:
            print("-", issue)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mapping Validation Program")
    parser.add_argument("--spec", default="rules/spec.xlsx", help="Path to mapping spec Excel file")
    parser.add_argument("--input", default="samples/input.xml", help="Path to source input payload (.xml, .json, .x12, .edifact, .edi)")
    parser.add_argument("--output", default="samples/output.xml", help="Path to target output payload (.xml, .json, .x12, .edifact, .edi)")
    parser.add_argument("--report", default="results/report.json", help="Path to write JSON report")
    parser.add_argument(
        "--mode",
        default="strict",
        choices=["strict", "lenient", "structure_strict"],
        help="Validation mode: strict fails on errors, lenient reports warnings, structure_strict also enforces target structure checks",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    result = validate_mapping_from_payload_bytes(
        args.spec,
        input_path.read_bytes(),
        input_path.name,
        output_path.read_bytes(),
        output_path.name,
        validation_mode=args.mode,
    )
    report_path = write_report(result, args.report)

    status = result.get("summary", {}).get("status")
    if status == "PASS_WITH_WARNINGS":
        print("VALIDATION COMPLETED WITH WARNINGS")
        _print_human_summary(result)
    elif result["errors"]:
        print("VALIDATION FAILED")
        _print_human_summary(result)
    else:
        print("VALIDATION PASSED")
        _print_human_summary(result)

    print(f"Report written to {report_path}")
    return 0 if result.get("valid", False) else 1

if __name__ == "__main__":
    raise SystemExit(main())
