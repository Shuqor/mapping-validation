import argparse
import json
from pathlib import Path


def check_uncertainty_budget(report: dict, max_ambiguities: int = 0, allowed_confidence: tuple[str, ...] = ("high",)) -> list[str]:
    issues: list[str] = []
    parser_diag = report.get("parser_diagnostics") if isinstance(report, dict) else {}
    if not isinstance(parser_diag, dict):
        return ["parser_diagnostics must be an object"]

    confidence = str(parser_diag.get("confidence") or report.get("summary", {}).get("parser_confidence") or "unknown").strip().lower()
    if confidence not in {c.lower() for c in allowed_confidence}:
        issues.append(f"parser confidence '{confidence}' exceeds allowed set: {allowed_confidence}")

    extraction = parser_diag.get("extraction") if isinstance(parser_diag.get("extraction"), dict) else {}
    ambiguities = extraction.get("ambiguities") if isinstance(extraction.get("ambiguities"), list) else []
    if len(ambiguities) > max_ambiguities:
        issues.append(f"ambiguity count {len(ambiguities)} exceeds budget {max_ambiguities}")

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Check parser uncertainty budget from report JSON")
    parser.add_argument("--report", required=True, help="Path to validation report JSON")
    parser.add_argument("--max-ambiguities", type=int, default=0, help="Maximum allowed parser ambiguities")
    parser.add_argument(
        "--allowed-confidence",
        default="high",
        help="Comma-separated allowed confidence values (default: high)",
    )
    args = parser.parse_args()

    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    allowed = tuple(part.strip().lower() for part in args.allowed_confidence.split(",") if part.strip())
    issues = check_uncertainty_budget(report, max_ambiguities=args.max_ambiguities, allowed_confidence=allowed)
    if issues:
        print("Parser uncertainty budget check failed:")
        for issue in issues:
            print(f"- {issue}")
        return 1

    print("Parser uncertainty budget check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())