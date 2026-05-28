import json
from pathlib import Path

from scripts.regenerate_rules_extraction_baseline import project_rules_extraction_baseline


BASELINE_PATH = Path(__file__).resolve().parent.parent / "results" / "rules_extraction_baseline.json"


def _stable_projection(projection: dict) -> dict:
    specs = projection.get("specs") if isinstance(projection.get("specs"), list) else []
    stable_specs: list[dict] = []
    for spec in specs:
        if not isinstance(spec, dict):
            continue
        stable_specs.append(
            {
                "spec": spec.get("spec"),
                "layout": spec.get("layout"),
                "status": spec.get("status"),
                "confidence": spec.get("confidence"),
                "rule_count": spec.get("rule_count"),
                "ambiguity_count": spec.get("ambiguity_count"),
            }
        )

    stable_specs.sort(key=lambda item: str(item.get("spec") or ""))
    return {
        "rules_dir": projection.get("rules_dir"),
        "spec_count": projection.get("spec_count"),
        "failure_count": projection.get("failure_count"),
        "failures": projection.get("failures"),
        "specs": stable_specs,
    }


def test_rules_extraction_baseline_snapshot_matches_known_projection():
    baseline_payload = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    projection = project_rules_extraction_baseline(rules_dir="rules")

    assert _stable_projection(projection) == _stable_projection(baseline_payload["projection"]), (
        "Rules extraction baseline drift detected. If this change is intentional, "
        "update results/rules_extraction_baseline.json with the new projection."
    )
