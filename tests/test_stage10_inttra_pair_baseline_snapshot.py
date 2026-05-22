import json
from pathlib import Path

import core.validate as validate_module
from scripts.regenerate_stage10_inttra_pair_baseline import project_stage10_inttra_pair


BASELINE_PATH = Path(__file__).resolve().parent.parent / "results" / "stage10_inttra_pair_baseline.json"


def test_stage10_inttra_pair_baseline_snapshot_matches_known_projection():
    baseline_payload = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))

    report = validate_module.validate_mapping_from_payload_bytes(
        "rules/Inttra-Contivo_X12_300_5030_to_JSON_BOOKINGINBOUND 1 Update.xlsx",
        (Path(__file__).resolve().parent.parent / "samples" / "BOOKINGINBOUND_1.json").read_bytes(),
        "BOOKINGINBOUND_1.json",
        (Path(__file__).resolve().parent.parent / "samples" / "output INTTRA.json").read_bytes(),
        "output INTTRA.json",
        validation_mode="strict",
    )
    projection = project_stage10_inttra_pair(report)

    assert projection == baseline_payload["projection"], (
        "Stage 10 INTTRA pair baseline drift detected. If intentional, update "
        "results/stage10_inttra_pair_baseline.json with the new projection."
    )
