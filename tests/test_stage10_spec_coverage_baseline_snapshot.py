import json
from pathlib import Path

import core.validate as validate_module
from scripts.regenerate_stage10_spec_coverage_baseline import project_stage10_spec_coverage


BASELINE_PATH = Path(__file__).resolve().parent.parent / "results" / "stage10_spec_coverage_baseline.json"


def test_stage10_spec_coverage_baseline_snapshot_matches_known_projection():
    baseline_payload = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))

    report = validate_module.validate_spec_coverage(
        "rules/Inttra-Contivo_X12_300_5030_to_JSON_BOOKINGINBOUND 1 Update.xlsx"
    )
    projection = project_stage10_spec_coverage(report)

    assert projection == baseline_payload["projection"], (
        "Stage 10 spec coverage baseline drift detected. If this change is intentional, "
        "update results/stage10_spec_coverage_baseline.json with the new projection."
    )
