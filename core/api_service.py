from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile

from core.validate import validate_mapping_from_payload_bytes


def _require_payload(value: bytes, field_name: str) -> None:
    if not value:
        raise ValueError(f"{field_name} is empty")


def _spec_suffix(spec_name: str | None) -> str:
    lower_name = (spec_name or "").lower()
    if lower_name.endswith(".xls"):
        return ".xls"
    if lower_name.endswith(".xlsx"):
        return ".xlsx"
    return ".xlsx"


def validate_uploaded_payloads(
    *,
    mapping_spec_name: str | None,
    mapping_spec_bytes: bytes,
    input_payload_name: str | None,
    input_payload_bytes: bytes,
    output_payload_name: str | None,
    output_payload_bytes: bytes,
    validation_mode: str = "strict",
) -> dict:
    _require_payload(mapping_spec_bytes, "mapping_spec")
    _require_payload(input_payload_bytes, "input_payload")
    _require_payload(output_payload_bytes, "output_payload")

    spec_path = ""
    with NamedTemporaryFile(suffix=_spec_suffix(mapping_spec_name), delete=False) as spec_tmp:
        spec_tmp.write(mapping_spec_bytes)
        spec_tmp.flush()
        spec_path = spec_tmp.name

    try:
        return validate_mapping_from_payload_bytes(
            spec_path,
            input_payload_bytes,
            input_payload_name or "input.xml",
            output_payload_bytes,
            output_payload_name or "output.xml",
            validation_mode=validation_mode,
        )
    finally:
        if spec_path:
            try:
                Path(spec_path).unlink(missing_ok=True)
            except PermissionError:
                # Best-effort cleanup on Windows where file handles can linger briefly.
                pass
