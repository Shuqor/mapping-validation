from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

_REASON_CODE_PATTERN = re.compile(r"^[a-z0-9_]{1,80}$")


def check_decision_explanations(report: dict) -> list[str]:
    issues: list[str] = []
    decisions = report.get("rule_decisions") if isinstance(report.get("rule_decisions"), list) else []

    for index, decision in enumerate(decisions):
        if not isinstance(decision, dict):
            issues.append(f"rule_decisions[{index}] must be an object")
            continue

        status = str(decision.get("status", "") or "").strip().lower()
        reason = str(decision.get("reason", "") or "").strip()
        reason_code = str(decision.get("reason_code", "") or "").strip()
        hint = str(decision.get("remediation_hint", "") or "").strip()

        if not reason:
            issues.append(f"rule_decisions[{index}].reason is required")
        if not reason_code:
            issues.append(f"rule_decisions[{index}].reason_code is required")
        elif not _REASON_CODE_PATTERN.fullmatch(reason_code):
            issues.append(f"rule_decisions[{index}].reason_code must match ^[a-z0-9_]{{1,80}}$")

        if status in {"parsed_only", "unsupported"} and not hint:
            issues.append(
                f"rule_decisions[{index}].remediation_hint is required when status is {status}"
            )

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Check decision explanation quality contract in report JSON")
    parser.add_argument("--report", required=True, help="Path to validation report JSON")
    args = parser.parse_args()

    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    issues = check_decision_explanations(report)
    if issues:
        print("Decision explanation check failed:")
        for issue in issues:
            print(f"- {issue}")
        return 1

    print("Decision explanation check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
