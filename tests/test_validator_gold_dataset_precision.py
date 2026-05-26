from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from core.validate import validate_mapping_from_payload_bytes


FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "validator_gold_dataset.json"


def _row_error_counts(report: dict) -> dict[int, int]:
    counts: dict[int, int] = defaultdict(int)
    diagnostics = report.get("error_diagnostics") if isinstance(report.get("error_diagnostics"), list) else []
    for diag in diagnostics:
        if not isinstance(diag, dict):
            continue
        row = int(diag.get("row", 0) or 0)
        if row > 0:
            counts[row] += 1
    return counts


def test_validator_gold_dataset_precision_and_false_positive_budget() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    runs = fixture.get("runs") if isinstance(fixture.get("runs"), list) else []

    decision_count = 0
    correct_count = 0
    enforced_count = 0
    false_positive_count = 0

    for run_cfg in runs:
        report = validate_mapping_from_payload_bytes(
            spec_path=str(run_cfg["spec"]),
            input_payload=Path(str(run_cfg["input"])).read_bytes(),
            input_filename=Path(str(run_cfg["input"])).name,
            output_payload=Path(str(run_cfg["output"])).read_bytes(),
            output_filename=Path(str(run_cfg["output"])).name,
            validation_mode=str(run_cfg.get("mode") or "lenient"),
        )

        row_counts = _row_error_counts(report)
        decisions = report.get("rule_decisions") if isinstance(report.get("rule_decisions"), list) else []
        for decision in decisions:
            if not isinstance(decision, dict):
                continue
            row = int(decision.get("row", 0) or 0)
            status = str(decision.get("status", "") or "").strip().lower()
            row_errors = int(row_counts.get(row, 0))

            decision_count += 1
            if row_errors == 0:
                correct_count += 1

            if status == "enforced":
                enforced_count += 1
                if row_errors > 0:
                    false_positive_count += 1

    precision = (correct_count / decision_count) if decision_count else 0.0
    false_positive_rate = (false_positive_count / enforced_count) if enforced_count else 0.0

    min_precision = float(fixture.get("min_precision", 0.85) or 0.85)
    max_false_positive_rate = float(fixture.get("max_false_positive_rate", 0.08) or 0.08)
    max_false_positive_count = int(fixture.get("max_false_positive_count", 25) or 25)

    assert precision >= min_precision, (
        f"Gold dataset precision too low: precision={precision:.4f}, required={min_precision:.4f}, "
        f"decision_count={decision_count}"
    )
    assert false_positive_rate <= max_false_positive_rate, (
        "Gold dataset false-positive rate too high: "
        f"false_positive_rate={false_positive_rate:.4f}, limit={max_false_positive_rate:.4f}, "
        f"enforced_count={enforced_count}"
    )
    assert false_positive_count <= max_false_positive_count, (
        "Gold dataset false-positive count too high: "
        f"false_positive_count={false_positive_count}, limit={max_false_positive_count}"
    )
