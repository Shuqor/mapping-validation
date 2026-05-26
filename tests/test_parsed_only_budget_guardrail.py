from __future__ import annotations

import os
from pathlib import Path

from core.validate import validate_spec_coverage


def test_parsed_only_budget_guardrail_for_standard_specs() -> None:
    """Guardrail: keep parsed-only drift bounded across the STANDARD workbook pack."""
    repo_root = Path(__file__).resolve().parents[1]
    specs = sorted((repo_root / "rules").glob("STANDARD_*.xlsx"))

    if not specs:
        raise AssertionError("No STANDARD_*.xlsx specs found for parsed-only budget guardrail")

    parsed_only_total = 0
    unsupported_total = 0
    checked_total = 0

    for spec in specs:
        report = validate_spec_coverage(str(spec))
        support = report.get("rule_support_summary", {}) if isinstance(report.get("rule_support_summary"), dict) else {}
        gap = report.get("rule_gap_summary", {}) if isinstance(report.get("rule_gap_summary"), dict) else {}

        parsed_only_total += int(support.get("parsed_only_rules", 0) or 0)
        unsupported_total += int(gap.get("unsupported_rules", support.get("unsupported_rules", 0)) or 0)
        checked_total += int(report.get("checked_rules", 0) or 0)

    parsed_only_budget = int(os.getenv("MVP_PARSED_ONLY_BUDGET", "150"))

    assert unsupported_total == 0, (
        f"Unsupported rules must remain zero for STANDARD specs, got unsupported_total={unsupported_total}"
    )
    assert parsed_only_total <= parsed_only_budget, (
        "Parsed-only budget exceeded for STANDARD specs: "
        f"parsed_only_total={parsed_only_total}, budget={parsed_only_budget}, checked_total={checked_total}"
    )
