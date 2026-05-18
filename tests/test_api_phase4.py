from fastapi.testclient import TestClient
import time

import api


client = TestClient(api.app)


def _files(
    spec_name: str = "any-name.xlsx",
    spec_bytes: bytes = b"fake spec bytes",
    input_name: str = "input.xml",
    input_bytes: bytes = b"<root/>",
    output_name: str = "output.xml",
    output_bytes: bytes = b"<root/>",
):
    return {
        "mapping_spec": (
            spec_name,
            spec_bytes,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
        "input_payload": (input_name, input_bytes, "application/xml"),
        "output_payload": (output_name, output_bytes, "application/xml"),
    }


def _stub_validate_mapping(
    _spec_path: str,
    _input_payload: bytes,
    _input_filename: str,
    _output_payload: bytes,
    _output_filename: str,
    validation_mode: str = "strict",
) -> dict:
    return {
        "summary": {
            "status": "PASS",
            "error_count": 0,
            "grouped_error_counts": {
                "cardinality_violations": 0,
                "source_target_missing": 0,
                "value_mismatches": 0,
                "constant_mismatches": 0,
                "concat_mismatches": 0,
                "other": 0,
            },
            "top_critical_errors": [],
        },
        "valid": True,
        "validation_mode": validation_mode,
        "strict_would_fail": False,
        "checked_rules": 1,
        "warnings": [],
        "rule_stats": {
            "cardinality_violations": 0,
            "source_target_missing": 0,
            "value_mismatches": 0,
            "constant_mismatches": 0,
            "concat_mismatches": 0,
        },
        "error_count": 0,
        "inputs": {
            "spec_path": "unused",
            "input_xml_path": "unused",
            "output_xml_path": "unused",
        },
        "error_sections": {
            "cardinality_violations": [],
            "source_target_missing": [],
            "value_mismatches": [],
            "constant_mismatches": [],
            "concat_mismatches": [],
            "other": [],
        },
        "top_critical_errors": [],
        "errors": [],
    }


def test_validate_returns_shareable_link_and_get_result(monkeypatch):
    api.RATE_LIMIT_STATE.clear()
    monkeypatch.setattr(api, "validate_mapping_from_payload_bytes", _stub_validate_mapping)

    post_response = client.post("/validate", files=_files())
    assert post_response.status_code == 200
    payload = post_response.json()

    assert payload["report_id"]
    assert "result_url" not in payload
    assert payload["summary"]["status"] == "PASS"
    assert payload["summary"]["top_critical_errors"] == []
    assert payload["error_count"] == 0
    assert payload["validation_mode"] == "strict"


def test_get_result_endpoint_not_available_returns_404():
    api.RATE_LIMIT_STATE.clear()
    response = client.get("/result/non-existent-id")

    assert response.status_code == 404


def test_web_ui_root_is_available():
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")


def test_validate_rejects_empty_upload(monkeypatch):
    api.RATE_LIMIT_STATE.clear()
    monkeypatch.setattr(api, "validate_mapping_from_payload_bytes", _stub_validate_mapping)

    response = client.post("/validate", files=_files(spec_bytes=b""))

    assert response.status_code == 422
    assert response.json()["detail"] == "mapping_spec file is empty"


def test_validate_rejects_unsupported_spec_extension(monkeypatch):
    api.RATE_LIMIT_STATE.clear()
    monkeypatch.setattr(api, "validate_mapping_from_payload_bytes", _stub_validate_mapping)

    response = client.post("/validate", files=_files(spec_name="rules.txt"))

    assert response.status_code == 422
    assert "Invalid mapping_spec file type" in response.json()["detail"]


def test_validate_timeout_returns_408(monkeypatch):
    api.RATE_LIMIT_STATE.clear()

    def _slow_validate(
        _spec_path: str,
        _input_payload: bytes,
        _input_filename: str,
        _output_payload: bytes,
        _output_filename: str,
        validation_mode: str = "strict",
    ) -> dict:
        time.sleep(0.05)
        return _stub_validate_mapping(
            _spec_path,
            _input_payload,
            _input_filename,
            _output_payload,
            _output_filename,
            validation_mode,
        )

    monkeypatch.setattr(api, "validate_mapping_from_payload_bytes", _slow_validate)
    monkeypatch.setattr(api, "VALIDATION_TIMEOUT_SECONDS", 0.001)

    response = client.post("/validate", files=_files())

    assert response.status_code == 408
    assert "Validation timed out" in response.json()["detail"]


def test_validate_rate_limit_returns_429(monkeypatch):
    api.RATE_LIMIT_STATE.clear()
    monkeypatch.setattr(api, "validate_mapping_from_payload_bytes", _stub_validate_mapping)
    monkeypatch.setattr(api, "RATE_LIMIT_MAX_REQUESTS", 1)
    monkeypatch.setattr(api, "RATE_LIMIT_WINDOW_SECONDS", 60)

    first = client.post("/validate", files=_files())
    second = client.post("/validate", files=_files())

    assert first.status_code == 200
    assert second.status_code == 429
    assert "Too many validation requests" in second.json()["detail"]


def test_validate_lenient_mode_is_forwarded(monkeypatch):
    api.RATE_LIMIT_STATE.clear()
    monkeypatch.setattr(api, "validate_mapping_from_payload_bytes", _stub_validate_mapping)

    response = client.post("/validate?validation_mode=lenient", files=_files())

    assert response.status_code == 200
    payload = response.json()
    assert payload["validation_mode"] == "lenient"


def test_validate_structure_strict_mode_is_forwarded(monkeypatch):
    api.RATE_LIMIT_STATE.clear()
    monkeypatch.setattr(api, "validate_mapping_from_payload_bytes", _stub_validate_mapping)

    response = client.post("/validate?validation_mode=structure_strict", files=_files())

    assert response.status_code == 200
    payload = response.json()
    assert payload["validation_mode"] == "structure_strict"


def test_validate_parse_error_mentions_offset_or_header_guidance(monkeypatch):
    api.RATE_LIMIT_STATE.clear()

    def _broken_validate(*_args, **_kwargs):
        raise ValueError("Could not detect header row in mapping spec (file=x.xlsx, sheet=Mapping)")

    monkeypatch.setattr(api, "validate_mapping_from_payload_bytes", _broken_validate)

    response = client.post("/validate", files=_files())

    assert response.status_code == 422
    assert "header row not detected" in response.json()["detail"].lower()
    assert "offset preamble rows" in response.json()["detail"].lower()


def test_validate_parse_error_mentions_mapping_columns(monkeypatch):
    api.RATE_LIMIT_STATE.clear()

    def _broken_validate(*_args, **_kwargs):
        raise ValueError("No target column could be resolved for xpath_target layout")

    monkeypatch.setattr(api, "validate_mapping_from_payload_bytes", _broken_validate)

    response = client.post("/validate", files=_files())

    assert response.status_code == 422
    assert "unable to resolve required mapping columns" in response.json()["detail"].lower()


def test_validate_accepts_json_payloads(monkeypatch):
    captured = {}

    def _stub_validate(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return _stub_validate_mapping(*args, **kwargs)

    api.RATE_LIMIT_STATE.clear()
    monkeypatch.setattr(api, "validate_mapping_from_payload_bytes", _stub_validate)

    response = client.post(
        "/validate?validation_mode=lenient",
        files=_files(
            input_name="input.json",
            input_bytes=b'{"status": {"a": 1}}',
            output_name="output.json",
            output_bytes=b'{"status": {"a": 1}}',
        ),
    )

    assert response.status_code == 200
    assert captured["args"][2] == "input.json"
    assert captured["args"][4] == "output.json"
    assert captured["args"][5] == "lenient"


def test_validate_accepts_cross_format_edi_payloads(monkeypatch):
    captured = {}

    def _stub_validate(*args, **kwargs):
        captured["args"] = args
        return _stub_validate_mapping(*args, **kwargs)

    api.RATE_LIMIT_STATE.clear()
    monkeypatch.setattr(api, "validate_mapping_from_payload_bytes", _stub_validate)

    response = client.post(
        "/validate",
        files=_files(
            input_name="input.edifact",
            input_bytes=b"UNB+UNOA:1+SENDER+RECEIVER+240101:0101+000000001'",
            output_name="output.json",
            output_bytes=b'{"invoice": {"id": "1"}}',
        ),
    )

    assert response.status_code == 200
    assert captured["args"][2] == "input.edifact"
    assert captured["args"][4] == "output.json"


def test_validate_rejects_unknown_payload_extension(monkeypatch):
    api.RATE_LIMIT_STATE.clear()
    monkeypatch.setattr(api, "validate_mapping_from_payload_bytes", _stub_validate_mapping)

    response = client.post(
        "/validate",
        files=_files(input_name="input.txt", output_name="output.xml"),
    )

    assert response.status_code == 422
    assert "Invalid input_payload file type" in response.json()["detail"]


def test_validate_cross_format_error_is_humanized(monkeypatch):
    api.RATE_LIMIT_STATE.clear()

    def _broken_validate(*_args, **_kwargs):
        raise ValueError(
            "Input (edifact) and output (json) payload formats must match, or supply an X12/EDIFACT input with a JSON/XML output for a cross-format spec."
        )

    monkeypatch.setattr(api, "validate_mapping_from_payload_bytes", _broken_validate)

    response = client.post(
        "/validate",
        files=_files(input_name="input.edifact", output_name="output.json"),
    )

    assert response.status_code == 422
    assert "unsupported payload combination" in response.json()["detail"].lower()


def test_validate_edi_flavor_error_is_humanized(monkeypatch):
    api.RATE_LIMIT_STATE.clear()

    def _broken_validate(*_args, **_kwargs):
        raise ValueError("Unable to detect .edi payload flavor. Use .x12 or .edifact extension for clarity.")

    monkeypatch.setattr(api, "validate_mapping_from_payload_bytes", _broken_validate)

    response = client.post(
        "/validate",
        files=_files(input_name="input.edi", output_name="output.edi"),
    )

    assert response.status_code == 422
    assert "use .x12 or .edifact for clarity" in response.json()["detail"].lower()
