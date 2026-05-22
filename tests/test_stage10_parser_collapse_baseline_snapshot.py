import json
from pathlib import Path

from scripts.regenerate_stage10_parser_collapse_baseline import build_parser_collapse_projection


BASELINE_PATH = Path(__file__).resolve().parent.parent / "results" / "stage10_parser_collapse_baseline.json"


def test_stage10_parser_collapse_baseline_snapshot_matches_known_projection():
    baseline_payload = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    spec_paths = list(baseline_payload.get("inputs", {}).get("spec_paths", []))

    projection = build_parser_collapse_projection(spec_paths)

    assert projection == baseline_payload["projection"], (
        "Stage 10 parser collapse baseline drift detected. If intentional, update "
        "results/stage10_parser_collapse_baseline.json using "
        "scripts/regenerate_stage10_parser_collapse_baseline.py"
    )
