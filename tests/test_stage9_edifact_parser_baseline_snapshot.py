import json
from pathlib import Path

from core.spec_reader import extract_rules, get_parser_diagnostics, read_mapping_table
from scripts.regenerate_stage9_edifact_parser_baseline import project_stage9_edifact_parser

BASELINE_PATH = Path(__file__).resolve().parent.parent / "results" / "stage9_edifact_parser_baseline.json"


def test_stage9_edifact_parser_baseline_snapshot_matches_known_projection():
    baseline_payload = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))

    fixture_paths = [
        "samples/spec_edifact_guided.xlsx",
        "samples/spec_edifact_orders_guided.xlsx",
    ]
    projection = {"fixtures": {}}
    for fixture in fixture_paths:
        df = read_mapping_table(fixture)
        rules = extract_rules(df)
        diagnostics = get_parser_diagnostics(df)
        projection["fixtures"][Path(fixture).name] = project_stage9_edifact_parser(df, rules, diagnostics)

    assert projection == baseline_payload["projection"], (
        "Stage 9 EDIFACT parser baseline drift detected. If this change is intentional, "
        "update results/stage9_edifact_parser_baseline.json with the new projection."
    )
