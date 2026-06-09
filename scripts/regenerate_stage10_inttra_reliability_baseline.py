import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import core.validate as validate_module


DEFAULT_BASELINE_PATH = Path("results/stage10_inttra_reliability_baseline.json")
DEFAULT_SPEC = "rules/Inttra-Contivo_X12_300_5030_to_JSON_BOOKINGINBOUND 1 Update.xlsx"
DEFAULT_INPUT = "samples/SampleforV1 - Copy.edi"
DEFAULT_OUTPUT = "samples/BOOKINGINBOUND_1 1.json"


def project_stage10_inttra_reliability(report: dict) -> dict:
    summary = report.get("summary", {}) if isinstance(report.get("summary"), dict) else {}
    support = report.get("rule_support_summary", {}) if isinstance(report.get("rule_support_summary"), dict) else {}
    gap = report.get("rule_gap_summary", {}) if isinstance(report.get("rule_gap_summary"), dict) else {}
    structure = report.get("structure_summary", {}) if isinstance(report.get("structure_summary"), dict) else {}
    structure_counts = structure.get("counts", {}) if isinstance(structure.get("counts"), dict) else {}
    fingerprint = report.get("validation_fingerprint", {}) if isinstance(report.get("validation_fingerprint"), dict) else {}

    return {
        "validation_mode": report.get("validation_mode"),
        "status": summary.get("status"),
        "error_count": int(report.get("error_count", 0) or 0),
        "checked_rules": int(report.get("checked_rules", 0) or 0),
        "rule_support": {
            "enforced_rules": int(support.get("enforced_rules", 0) or 0),
            "parsed_only_rules": int(support.get("parsed_only_rules", 0) or 0),
            "unsupported_rules": int(support.get("unsupported_rules", 0) or 0),
        },
        "semantic_condition_coverage_percent": float(gap.get("semantic_condition_coverage_percent", 0.0) or 0.0),
        "structure": {
            "unexpected_target_nodes": int(structure_counts.get("unexpected_target_nodes", 0) or 0),
            "unexpected_target_nodes_suppressed": int(structure_counts.get("unexpected_target_nodes_suppressed", 0) or 0),
        },
        "fingerprint": {
            "validator_version": fingerprint.get("validator_version"),
            "parser_version": fingerprint.get("parser_version"),
            "mode": fingerprint.get("mode"),
            "exception_profile": fingerprint.get("exception_profile"),
            "exception_count": int(fingerprint.get("exception_count", 0) or 0),
            "exception_profile_hash": fingerprint.get("exception_profile_hash"),
        },
    }


def regenerate_stage10_inttra_reliability_baseline(
    output_path: Path,
    spec_path: str,
    input_path: str,
    output_payload_path: str,
) -> dict:
    result = validate_module.validate_mapping_from_payload_bytes(
        spec_path,
        Path(input_path).read_bytes(),
        Path(input_path).name,
        Path(output_payload_path).read_bytes(),
        Path(output_payload_path).name,
        validation_mode="structure_strict",
    )

    payload = {
        "snapshot_name": "stage10_inttra_reliability_baseline",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "spec_path": spec_path,
            "input_path": input_path,
            "output_path": output_payload_path,
        },
        "projection": project_stage10_inttra_reliability(result),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Regenerate structure_strict INTTRA reliability baseline snapshot artifact")
    parser.add_argument("--spec", default=DEFAULT_SPEC, help="Spec file path")
    parser.add_argument("--input", default=DEFAULT_INPUT, help="Input payload path")
    parser.add_argument("--output-payload", default=DEFAULT_OUTPUT, help="Output payload path")
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE_PATH), help="Baseline artifact path")
    args = parser.parse_args()

    payload = regenerate_stage10_inttra_reliability_baseline(
        output_path=Path(args.baseline),
        spec_path=args.spec,
        input_path=args.input,
        output_payload_path=args.output_payload,
    )

    projection = payload["projection"]
    print(
        f"Updated baseline: {args.baseline} | "
        f"status={projection['status']} errors={projection['error_count']} checked_rules={projection['checked_rules']} "
        f"unsupported={projection['rule_support']['unsupported_rules']}"
    )


if __name__ == "__main__":
    main()
