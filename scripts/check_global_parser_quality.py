import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import core.validate as validate_module


def evaluate_parser_diagnostics(
    diagnostics: dict,
    *,
    allowed_confidence: tuple[str, ...] = ("high", "medium"),
    max_ambiguities: int = 0,
) -> list[str]:
    issues: list[str] = []
    confidence = str(diagnostics.get("confidence") or "unknown").strip().lower()
    allowed = {item.lower() for item in allowed_confidence if item}
    if confidence not in allowed:
        issues.append(f"confidence={confidence} not in allowed={sorted(allowed)}")

    extraction = diagnostics.get("extraction") if isinstance(diagnostics.get("extraction"), dict) else {}
    ambiguities = extraction.get("ambiguities") if isinstance(extraction.get("ambiguities"), list) else []
    if len(ambiguities) > max_ambiguities:
        issues.append(f"ambiguities={len(ambiguities)} exceed max={max_ambiguities}")

    return issues


def scan_global_parser_quality(
    *,
    rules_dir: Path,
    allowed_confidence: tuple[str, ...],
    max_ambiguities: int,
) -> list[dict]:
    findings: list[dict] = []
    for spec_path in sorted(rules_dir.glob("*.xlsx")):
        try:
            df = validate_module.read_mapping_table(str(spec_path))
            diagnostics = validate_module.get_parser_diagnostics(df)
            issues = evaluate_parser_diagnostics(
                diagnostics,
                allowed_confidence=allowed_confidence,
                max_ambiguities=max_ambiguities,
            )
            if issues:
                findings.append(
                    {
                        "spec": str(spec_path.as_posix()),
                        "confidence": diagnostics.get("confidence", "unknown"),
                        "ambiguity_count": len((diagnostics.get("extraction") or {}).get("ambiguities", [])),
                        "issues": issues,
                    }
                )
        except Exception as exc:  # noqa: BLE001
            findings.append(
                {
                    "spec": str(spec_path.as_posix()),
                    "confidence": "unknown",
                    "ambiguity_count": -1,
                    "issues": [f"parser_exception: {exc}"],
                }
            )

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Global parser quality visibility checker across all rules/*.xlsx")
    parser.add_argument("--rules-dir", default="rules", help="Directory containing .xlsx mapping specs")
    parser.add_argument("--allowed-confidence", default="high,medium", help="Comma-separated allowed parser confidence values")
    parser.add_argument("--max-ambiguities", type=int, default=0, help="Maximum allowed parser ambiguities per spec")
    parser.add_argument("--output", default="results/ci/global_parser_quality.json", help="Where to write summary artifact")
    parser.add_argument(
        "--fail-on-findings",
        action="store_true",
        help="Fail with non-zero exit code when findings are present",
    )
    args = parser.parse_args()

    allowed = tuple(part.strip().lower() for part in args.allowed_confidence.split(",") if part.strip())
    findings = scan_global_parser_quality(
        rules_dir=Path(args.rules_dir),
        allowed_confidence=allowed,
        max_ambiguities=args.max_ambiguities,
    )

    payload = {
        "rules_dir": str(Path(args.rules_dir).as_posix()),
        "allowed_confidence": list(allowed),
        "max_ambiguities": int(args.max_ambiguities),
        "spec_count": len(list(Path(args.rules_dir).glob("*.xlsx"))),
        "finding_count": len(findings),
        "findings": findings,
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if findings:
        mode = "blocking" if args.fail_on_findings else "non-blocking"
        print(f"Global parser quality drift detected ({mode}): {len(findings)} spec(s)")
        for finding in findings[:20]:
            print(f"::warning::{finding['spec']} -> {'; '.join(finding['issues'])}")
    else:
        print("Global parser quality check: no drift detected")

    print(f"Artifact written: {out_path}")
    if findings and args.fail_on_findings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
