import argparse
import json
import re
from pathlib import Path


_REASON_CODE_PATTERN = re.compile(r"^[a-z0-9_]{1,80}$")


def check_report_reason_codes(report: dict) -> list[str]:
    issues: list[str] = []
    decisions = report.get("rule_decisions") if isinstance(report, dict) else None
    if not isinstance(decisions, list):
        return ["rule_decisions must be a list"]

    for index, decision in enumerate(decisions):
        prefix = f"rule_decisions[{index}]"
        if not isinstance(decision, dict):
            issues.append(f"{prefix} must be an object")
            continue

        reason = str(decision.get("reason") or "").strip()
        reason_code = str(decision.get("reason_code") or "").strip()
        if not reason:
            issues.append(f"{prefix}.reason is required")
        if not reason_code:
            issues.append(f"{prefix}.reason_code is required")
        elif not _REASON_CODE_PATTERN.fullmatch(reason_code):
            issues.append(f"{prefix}.reason_code must match ^[a-z0-9_]{{1,80}}$")

    diagnostics = report.get("error_diagnostics")
    if isinstance(diagnostics, list):
        for index, diagnostic in enumerate(diagnostics):
            prefix = f"error_diagnostics[{index}]"
            if not isinstance(diagnostic, dict):
                issues.append(f"{prefix} must be an object")
                continue
            decision_reason = str(diagnostic.get("decision_reason") or "").strip()
            decision_reason_code = str(diagnostic.get("decision_reason_code") or "").strip()
            if decision_reason and not decision_reason_code:
                issues.append(f"{prefix}.decision_reason_code is required when decision_reason exists")
            elif decision_reason_code and not _REASON_CODE_PATTERN.fullmatch(decision_reason_code):
                issues.append(f"{prefix}.decision_reason_code must match ^[a-z0-9_]{{1,80}}$")

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Check reason_code contract in a validation report JSON")
    parser.add_argument("--report", required=True, help="Path to validation report JSON")
    args = parser.parse_args()

    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    issues = check_report_reason_codes(report)
    if issues:
        print("Report reason-code contract check failed:")
        for issue in issues:
            print(f"- {issue}")
        return 1

    print("Report reason-code contract check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())