import json
from pathlib import Path

import core.validate as validate_module
from scripts.regenerate_stage8_baseline import project_stage8_report


BASELINE_PATH = Path(__file__).resolve().parent.parent / "results" / "stage8_validation_baseline.json"


def test_stage8_baseline_snapshot_matches_known_projection():
    baseline_payload = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))

    report = validate_module.validate_mapping(
        "rules/spec.xlsx",
        "samples/input.xml",
        "samples/output.xml",
        validation_mode="strict",
    )
    projection = project_stage8_report(report)

    assert projection == baseline_payload["projection"], (
        "Stage 8 baseline drift detected. If this change is intentional, "
        "update results/stage8_validation_baseline.json with the new projection."
    )
