import json
from pathlib import Path

from scripts.check_global_validator_health import build_global_validator_health_projection


BASELINE_PATH = Path(__file__).resolve().parent.parent / "results" / "ci" / "global_validator_health_baseline.json"


def _stable_projection_view(payload: dict) -> dict:
    projection = dict(payload)
    runtime = dict(projection.get("curated_runtime") or {})
    performance = dict(runtime.get("performance") or {})
    # Runtime durations vary per run/machine; keep threshold only for stable snapshot intent.
    performance.pop("p95_runtime_seconds", None)
    performance.pop("max_runtime_seconds", None)
    runtime["performance"] = performance

    normalized_runs = []
    for run in runtime.get("runs") or []:
        run_copy = dict(run)
        run_copy.pop("runtime_seconds", None)
        normalized_runs.append(run_copy)
    runtime["runs"] = normalized_runs

    projection["curated_runtime"] = runtime
    return projection


def test_global_validator_health_snapshot_matches_known_projection():
    baseline_payload = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    projection = build_global_validator_health_projection(rules_dir="rules")

    assert _stable_projection_view(projection) == _stable_projection_view(baseline_payload["projection"]), (
        "Global validator health baseline drift detected. If this change is intentional, "
        "update results/ci/global_validator_health_baseline.json with the new projection."
    )
