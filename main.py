
import argparse
import json
from pathlib import Path

from core.validate import validate_mapping_from_payload_bytes, validate_spec_coverage, write_report
from core.stage10_tools import (
    diff_specs,
    generate_payload_bundle,
    write_excel_report,
    write_generated_payload_files,
)


def _run_batch_validation(spec_path: str, batch_manifest_path: str, validation_mode: str) -> dict:
    manifest_path = Path(batch_manifest_path)
    entries = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(entries, list):
        raise ValueError("Batch manifest must be a JSON array of {input, output[, id]} objects")

    runs: list[dict] = []
    status_counts = {"PASS": 0, "PASS_WITH_WARNINGS": 0, "FAIL": 0}
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise ValueError(f"Batch manifest entry at index {index - 1} must be an object")
        input_path = Path(str(entry.get("input", "") or ""))
        output_path = Path(str(entry.get("output", "") or ""))
        run_id = str(entry.get("id", "") or f"pair_{index}")
        if not input_path.exists() or not output_path.exists():
            raise ValueError(f"Batch entry '{run_id}' has missing file path(s)")

        result = validate_mapping_from_payload_bytes(
            spec_path,
            input_path.read_bytes(),
            input_path.name,
            output_path.read_bytes(),
            output_path.name,
            validation_mode=validation_mode,
        )
        status = str(result.get("summary", {}).get("status", "FAIL"))
        if status not in status_counts:
            status_counts["FAIL"] += 1
        else:
            status_counts[status] += 1

        runs.append(
            {
                "id": run_id,
                "input": str(input_path),
                "output": str(output_path),
                "summary": result.get("summary", {}),
                "valid": bool(result.get("valid", False)),
                "error_count": int(result.get("error_count", 0) or 0),
                "rule_gap_summary": result.get("rule_gap_summary", {}),
                "mapping_completeness": result.get("mapping_completeness", {}),
                "reverse_validation_summary": result.get("reverse_validation_summary", {}),
            }
        )

    total_runs = len(runs)
    fail_count = int(status_counts.get("FAIL", 0))
    warn_count = int(status_counts.get("PASS_WITH_WARNINGS", 0))
    pass_count = int(status_counts.get("PASS", 0))
    batch_status = "FAIL" if fail_count > 0 else ("PASS_WITH_WARNINGS" if warn_count > 0 else "PASS")

    return {
        "summary": {
            "status": batch_status,
            "error_count": sum(int(run.get("error_count", 0)) for run in runs),
            "grouped_error_counts": {},
            "top_critical_errors": [],
            "parser_status": "batch",
            "parser_confidence": "mixed",
        },
        "human_summary": {
            "headline": f"Batch validation completed: {pass_count} pass, {warn_count} warning, {fail_count} fail",
            "issue_breakdown": [
                {"issue": "Passed", "count": pass_count},
                {"issue": "Passed with warnings", "count": warn_count},
                {"issue": "Failed", "count": fail_count},
            ],
            "what_to_fix_first": [
                f"{run['id']}: status={run.get('summary', {}).get('status', 'FAIL')} errors={run.get('error_count', 0)}"
                for run in runs
                if str(run.get("summary", {}).get("status", "")) != "PASS"
            ][:20],
            "checked_rules": total_runs,
            "skipped_rules": 0,
        },
        "valid": fail_count == 0,
        "validation_mode": f"batch_{validation_mode}",
        "strict_would_fail": fail_count > 0,
        "checked_rules": total_runs,
        "warnings": [],
        "rule_stats": {},
        "structure_summary": None,
        "semantic_summary": {},
        "rule_gap_summary": {},
        "mandatory_preflight": {},
        "reverse_validation_summary": {},
        "mapping_completeness": {},
        "structure_findings": [],
        "parser_diagnostics": {"status": "batch", "confidence": "mixed", "warnings": []},
        "rule_support_summary": {},
        "rule_decisions": [],
        "error_diagnostics": [],
        "skipped_rules": [],
        "unsupported_rule_suggestions": [],
        "error_sections": {},
        "top_critical_errors": [],
        "error_count": sum(int(run.get("error_count", 0)) for run in runs),
        "inputs": {"spec_path": spec_path, "batch_manifest": str(manifest_path)},
        "batch_summary": {
            "total_runs": total_runs,
            "passed": pass_count,
            "warnings": warn_count,
            "failed": fail_count,
            "status_counts": status_counts,
        },
        "batch_runs": runs,
        "errors": [],
    }


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

    rule_gap = result.get("rule_gap_summary") or {}
    if rule_gap:
        print(
            "Rule-gap summary: "
            f"coverage={rule_gap.get('enforceable_coverage_percent', 100.0)}%, "
            f"semantic={rule_gap.get('semantic_condition_coverage_percent', 100.0)}%, "
            f"missing_cardinality={rule_gap.get('missing_cardinality_rules', 0)}"
        )
        if rule_gap.get("next_action"):
            print(f"Next action: {rule_gap.get('next_action')}")

    mandatory_preflight = result.get("mandatory_preflight") or {}
    if mandatory_preflight:
        status = mandatory_preflight.get("status", "unknown")
        total = mandatory_preflight.get("total_mandatory_fields", 0)
        present = mandatory_preflight.get("present_count", 0)
        missing = mandatory_preflight.get("missing_count", 0)
        coverage = mandatory_preflight.get("coverage_percent", 0.0)
        print(
            "Mandatory pre-flight: "
            f"status={status}, coverage={coverage}%, present={present}/{total}, missing={missing}"
        )
        if mandatory_preflight.get("note"):
            print(f"Pre-flight note: {mandatory_preflight.get('note')}")

    reverse_summary = result.get("reverse_validation_summary") or {}
    if reverse_summary:
        print(
            "Reverse validation: "
            f"status={reverse_summary.get('status', 'unknown')}, "
            f"coverage={reverse_summary.get('coverage_percent', 0.0)}%, "
            f"mapped_required={reverse_summary.get('mapped_required_rules', 0)}/{reverse_summary.get('required_rules', 0)}, "
            f"unmapped_required={reverse_summary.get('unmapped_required_rules', 0)}"
        )
        if reverse_summary.get("note"):
            print(f"Reverse-validation note: {reverse_summary.get('note')}")

    completeness = result.get("mapping_completeness") or {}
    if completeness:
        print(
            "Completeness: "
            f"status={completeness.get('status', 'unknown')}, "
            f"score={completeness.get('score_percent', 0.0)}%, "
            f"satisfied={completeness.get('satisfied_mandatory_rules', 0)}/{completeness.get('total_mandatory_rules', 0)}, "
            f"basis={completeness.get('basis', 'unknown')}"
        )
        if completeness.get("note"):
            print(f"Completeness note: {completeness.get('note')}")

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
    parser.add_argument("--spec-compare", default="", help="Optional second spec file for spec diff mode")
    parser.add_argument("--input", default="samples/input.xml", help="Path to source input payload (.xml, .json, .x12, .edifact, .edi)")
    parser.add_argument("--output", default="samples/output.xml", help="Path to target output payload (.xml, .json, .x12, .edifact, .edi)")
    parser.add_argument("--batch-manifest", default="", help="Optional JSON file with [{\"input\":..., \"output\":..., \"id\":...}] for batch validation")
    parser.add_argument("--report", default="results/report.json", help="Path to write JSON report")
    parser.add_argument("--report-xlsx", default="", help="Optional path to write Excel report (.xlsx)")
    parser.add_argument(
        "--generate-payload",
        default="",
        choices=["", "template", "sample", "full"],
        help="Generate payloads from spec only: template, sample, or full",
    )
    parser.add_argument(
        "--generated-prefix",
        default="results/generated_payload",
        help="Output prefix for generated payload files (without _input/_output suffix)",
    )
    parser.add_argument(
        "--mode",
        default="strict",
        choices=["strict", "lenient", "structure_strict", "completion_status", "spec_coverage"],
        help="Validation mode: strict fails on errors, lenient reports warnings, structure_strict enforces target structure checks, completion_status tracks completion metrics, spec_coverage runs parser/semantic dry-run without payload files",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    spec_compare = getattr(args, "spec_compare", "")
    generate_payload = getattr(args, "generate_payload", "")
    report_xlsx = getattr(args, "report_xlsx", "")

    if spec_compare:
        result = diff_specs(args.spec, spec_compare)
    elif generate_payload:
        result = generate_payload_bundle(args.spec, generate_payload)
        output_files = write_generated_payload_files(result, getattr(args, "generated_prefix", "results/generated_payload"))
        print(f"Generated payload files: input={output_files['input']} output={output_files['output']}")
    elif args.batch_manifest:
        if args.mode == "spec_coverage":
            raise SystemExit("--batch-manifest cannot be combined with --mode spec_coverage")
        result = _run_batch_validation(args.spec, args.batch_manifest, args.mode)
    elif args.mode == "spec_coverage":
        result = validate_spec_coverage(args.spec)
    else:
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
    if report_xlsx:
        xlsx_path = write_excel_report(result, report_xlsx)
        print(f"Excel report written to {xlsx_path}")

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
