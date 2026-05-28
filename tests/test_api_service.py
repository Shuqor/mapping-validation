from __future__ import annotations

from pathlib import Path

import pytest

from core.api_service import validate_uploaded_payloads


ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize(
    ("field", "spec_bytes", "input_bytes", "output_bytes", "expected"),
    [
        ("mapping_spec", b"", b"x", b"y", "mapping_spec is empty"),
        ("input_payload", b"x", b"", b"y", "input_payload is empty"),
        ("output_payload", b"x", b"y", b"", "output_payload is empty"),
    ],
)
def test_validate_uploaded_payloads_requires_non_empty_payloads(
    field: str,
    spec_bytes: bytes,
    input_bytes: bytes,
    output_bytes: bytes,
    expected: str,
) -> None:
    with pytest.raises(ValueError, match=expected):
        validate_uploaded_payloads(
            mapping_spec_name="spec.xlsx",
            mapping_spec_bytes=spec_bytes,
            input_payload_name="input.xml",
            input_payload_bytes=input_bytes,
            output_payload_name="output.xml",
            output_payload_bytes=output_bytes,
        )


def test_validate_uploaded_payloads_happy_path_returns_summary() -> None:
    result = validate_uploaded_payloads(
        mapping_spec_name="spec.xlsx",
        mapping_spec_bytes=(ROOT / "rules" / "spec.xlsx").read_bytes(),
        input_payload_name="input.xml",
        input_payload_bytes=(ROOT / "samples" / "input.xml").read_bytes(),
        output_payload_name="output.xml",
        output_payload_bytes=(ROOT / "samples" / "output.xml").read_bytes(),
    )

    assert "summary" in result
    assert "status" in result["summary"]
