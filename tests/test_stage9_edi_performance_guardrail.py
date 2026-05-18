import os
import time
from pathlib import Path

import core.validate as validate_module


SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def test_stage9_large_x12_fixture_smoke_bridge_runs():
    report = validate_module.validate_mapping_from_payload_bytes(
        spec_path="rules/spec.xlsx",
        input_payload=(SAMPLES / "input_large.x12").read_bytes(),
        input_filename="input_large.x12",
        output_payload=(SAMPLES / "output_large.x12").read_bytes(),
        output_filename="output_large.x12",
        validation_mode="strict",
    )

    assert report.get("adapter_pipeline", {}).get("enabled") is True
    assert report.get("adapter_pipeline", {}).get("input_format") == "x12"
    assert report.get("adapter_pipeline", {}).get("output_format") == "x12"


def test_stage9_large_edifact_fixture_smoke_bridge_runs():
    report = validate_module.validate_mapping_from_payload_bytes(
        spec_path="rules/spec.xlsx",
        input_payload=(SAMPLES / "input_large.edifact").read_bytes(),
        input_filename="input_large.edifact",
        output_payload=(SAMPLES / "output_large.edifact").read_bytes(),
        output_filename="output_large.edifact",
        validation_mode="strict",
    )

    assert report.get("adapter_pipeline", {}).get("enabled") is True
    assert report.get("adapter_pipeline", {}).get("input_format") == "edifact"
    assert report.get("adapter_pipeline", {}).get("output_format") == "edifact"


def _time_stage9_bridge_roundtrip(input_name: str, output_name: str) -> float:
    start = time.perf_counter()
    validate_module.validate_mapping_from_payload_bytes(
        spec_path="rules/spec.xlsx",
        input_payload=(SAMPLES / input_name).read_bytes(),
        input_filename=input_name,
        output_payload=(SAMPLES / output_name).read_bytes(),
        output_filename=output_name,
        validation_mode="strict",
    )
    return time.perf_counter() - start


def test_stage9_runtime_large_x12_guardrail():
    max_seconds = float(os.getenv("STAGE9_PERF_X12_MAX_SECONDS", "8.0"))
    duration = _time_stage9_bridge_roundtrip("input_large.x12", "output_large.x12")
    assert duration <= max_seconds, (
        f"Stage 9 X12 bridge runtime exceeded guardrail: "
        f"duration={duration:.4f}s max={max_seconds:.4f}s"
    )


def test_stage9_runtime_large_edifact_guardrail():
    max_seconds = float(os.getenv("STAGE9_PERF_EDIFACT_MAX_SECONDS", "8.0"))
    duration = _time_stage9_bridge_roundtrip("input_large.edifact", "output_large.edifact")
    assert duration <= max_seconds, (
        f"Stage 9 EDIFACT bridge runtime exceeded guardrail: "
        f"duration={duration:.4f}s max={max_seconds:.4f}s"
    )
