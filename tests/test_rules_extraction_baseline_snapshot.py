import json
from pathlib import Path

from scripts.regenerate_rules_extraction_baseline import project_rules_extraction_baseline


BASELINE_PATH = Path(__file__).resolve().parent.parent / "results" / "rules_extraction_baseline.json"


def test_rules_extraction_baseline_snapshot_matches_known_projection():
    baseline_payload = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    projection = project_rules_extraction_baseline(rules_dir="rules")

    assert projection == baseline_payload["projection"], (
        "Rules extraction baseline drift detected. If this change is intentional, "
        "update results/rules_extraction_baseline.json with the new projection."
    )
