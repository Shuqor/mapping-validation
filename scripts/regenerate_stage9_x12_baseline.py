import json
from datetime import datetime, timezone
from pathlib import Path

import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import core.validate as validate_module
from tests.test_stage9_x12_bridge_baseline_snapshot import project_stage9_x12_bridge_report


BASELINE_PATH = Path("results/stage9_x12_bridge_baseline.json")


def main() -> None:
    report = validate_module.validate_mapping_from_payload_bytes(
        spec_path="rules/spec.xlsx",
        input_payload=Path("samples/input.x12").read_bytes(),
        input_filename="input.x12",
        output_payload=Path("samples/output.x12").read_bytes(),
        output_filename="output.x12",
        validation_mode="strict",
    )

    payload = {
        "snapshot_name": "stage9_x12_bridge_baseline",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "spec_path": "rules/spec.xlsx",
            "input_payload_path": "samples/input.x12",
            "output_payload_path": "samples/output.x12",
        },
        "projection": project_stage9_x12_bridge_report(report),
    }

    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        f"Updated Stage 9 X12 baseline: {BASELINE_PATH} | "
        f"status={payload['projection']['summary']['status']} "
        f"errors={payload['projection']['summary']['error_count']}"
    )


if __name__ == "__main__":
    main()
