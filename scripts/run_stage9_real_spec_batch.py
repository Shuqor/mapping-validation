from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
RULES_DIR = ROOT_DIR / "rules"
SAMPLES_DIR = ROOT_DIR / "samples"

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.validate import validate_mapping_from_payload_bytes


@dataclass
class BatchCase:
    spec_name: str
    input_name: str
    output_name: str
    expects_adapter: bool


@dataclass
class CaseResult:
    case: BatchCase
    status: str
    parser_status: str
    checked_rules: int
    adapter_enabled: bool
    message: str


REAL_SPEC_CASES = [
    BatchCase(
        "JABIL_X12_214_4010_to_JSON_TMSCARRIERTENDERRESPONSE_v1.4.xlsx",
        "input.x12",
        "output.json",
        True,
    ),
    BatchCase(
        "Inttra-Contivo_X12_300_5030_to_JSON_BOOKINGINBOUND.xlsx",
        "input.x12",
        "output.json",
        True,
    ),
    BatchCase(
        "P&G_CDM_ReceiptDownload_1.0_to_cXML_ReceiptRequest_1.2.051.xlsx",
        "input.xml",
        "output.xml",
        False,
    ),
    BatchCase(
        "TMSLSP-DHLLINK_Common_CUSTOMXML_Status_1.0_to_CUSTOMXML_Status_1.0.xlsx",
        "input.xml",
        "output.xml",
        False,
    ),
]


def run_case(case: BatchCase, mode: str) -> CaseResult:
    spec_path = RULES_DIR / case.spec_name
    input_path = SAMPLES_DIR / case.input_name
    output_path = SAMPLES_DIR / case.output_name

    if not spec_path.exists():
        return CaseResult(case, "SKIP", "unknown", 0, False, f"Missing workbook: {case.spec_name}")
    if not input_path.exists() or not output_path.exists():
        return CaseResult(case, "SKIP", "unknown", 0, False, "Missing input/output sample payload")

    try:
        result = validate_mapping_from_payload_bytes(
            str(spec_path),
            input_path.read_bytes(),
            input_path.name,
            output_path.read_bytes(),
            output_path.name,
            validation_mode=mode,
        )
    except Exception as exc:
        return CaseResult(case, "FAIL", "unknown", 0, False, f"Runtime error: {type(exc).__name__}: {exc}")

    summary = result.get("summary", {})
    parser_status = str(summary.get("parser_status") or "unknown")
    checked_rules = int(result.get("checked_rules") or 0)
    adapter_enabled = bool((result.get("adapter_pipeline") or {}).get("enabled"))

    issues = []
    if parser_status == "low_confidence":
        issues.append("parser status is low_confidence")
    if checked_rules <= 0:
        issues.append("no rules were checked")
    if case.expects_adapter and not adapter_enabled:
        issues.append("adapter pipeline was expected but not enabled")
    if (not case.expects_adapter) and adapter_enabled:
        issues.append("adapter pipeline was not expected but is enabled")

    if issues:
        return CaseResult(
            case,
            "FAIL",
            parser_status,
            checked_rules,
            adapter_enabled,
            "; ".join(issues),
        )

    report_status = str(summary.get("status") or "unknown")
    return CaseResult(
        case,
        "PASS",
        parser_status,
        checked_rules,
        adapter_enabled,
        f"validation status={report_status}",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Stage 9 real-workbook smoke batch")
    parser.add_argument(
        "--mode",
        choices=["strict", "lenient", "structure_strict"],
        default="lenient",
        help="Validation mode used for each case",
    )
    parser.add_argument(
        "--json-out",
        default="",
        help="Optional path to write batch JSON results",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    results = [run_case(case, args.mode) for case in REAL_SPEC_CASES]
    pass_count = sum(1 for item in results if item.status == "PASS")
    fail_count = sum(1 for item in results if item.status == "FAIL")
    skip_count = sum(1 for item in results if item.status == "SKIP")

    print("Stage 9 real workbook batch")
    print(f"Mode: {args.mode}")
    print("-" * 72)
    for item in results:
        print(
            f"[{item.status}] {item.case.spec_name} | "
            f"in={item.case.input_name} out={item.case.output_name} | "
            f"parser={item.parser_status} checked={item.checked_rules} "
            f"adapter={item.adapter_enabled} | {item.message}"
        )
    print("-" * 72)
    print(f"Summary: pass={pass_count} fail={fail_count} skip={skip_count} total={len(results)}")

    if args.json_out:
        out_path = Path(args.json_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_payload = {
            "mode": args.mode,
            "summary": {
                "pass": pass_count,
                "fail": fail_count,
                "skip": skip_count,
                "total": len(results),
            },
            "results": [
                {
                    "case": asdict(item.case),
                    "status": item.status,
                    "parser_status": item.parser_status,
                    "checked_rules": item.checked_rules,
                    "adapter_enabled": item.adapter_enabled,
                    "message": item.message,
                }
                for item in results
            ],
        }
        out_path.write_text(json.dumps(out_payload, indent=2), encoding="utf-8")
        print(f"Wrote JSON report to {out_path}")

    return 1 if fail_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
