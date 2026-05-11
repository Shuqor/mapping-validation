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
    _input_path: str,
    _output_path: str,
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
    monkeypatch.setattr(api, "validate_mapping", _stub_validate_mapping)

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
    monkeypatch.setattr(api, "validate_mapping", _stub_validate_mapping)

    response = client.post("/validate", files=_files(spec_bytes=b""))

    assert response.status_code == 422
    assert response.json()["detail"] == "mapping_spec file is empty"


def test_validate_rejects_unsupported_spec_extension(monkeypatch):
    api.RATE_LIMIT_STATE.clear()
    monkeypatch.setattr(api, "validate_mapping", _stub_validate_mapping)

    response = client.post("/validate", files=_files(spec_name="rules.txt"))

    assert response.status_code == 422
    assert "Invalid mapping_spec file type" in response.json()["detail"]


def test_validate_timeout_returns_408(monkeypatch):
    api.RATE_LIMIT_STATE.clear()

    def _slow_validate(
        _spec_path: str,
        _input_path: str,
        _output_path: str,
        validation_mode: str = "strict",
    ) -> dict:
        time.sleep(0.05)
        return _stub_validate_mapping(_spec_path, _input_path, _output_path, validation_mode)

    monkeypatch.setattr(api, "validate_mapping", _slow_validate)
    monkeypatch.setattr(api, "VALIDATION_TIMEOUT_SECONDS", 0.001)

    response = client.post("/validate", files=_files())

    assert response.status_code == 408
    assert "Validation timed out" in response.json()["detail"]


def test_validate_rate_limit_returns_429(monkeypatch):
    api.RATE_LIMIT_STATE.clear()
    monkeypatch.setattr(api, "validate_mapping", _stub_validate_mapping)
    monkeypatch.setattr(api, "RATE_LIMIT_MAX_REQUESTS", 1)
    monkeypatch.setattr(api, "RATE_LIMIT_WINDOW_SECONDS", 60)

    first = client.post("/validate", files=_files())
    second = client.post("/validate", files=_files())

    assert first.status_code == 200
    assert second.status_code == 429
    assert "Too many validation requests" in second.json()["detail"]


def test_validate_lenient_mode_is_forwarded(monkeypatch):
    api.RATE_LIMIT_STATE.clear()
    monkeypatch.setattr(api, "validate_mapping", _stub_validate_mapping)

    response = client.post("/validate?validation_mode=lenient", files=_files())

    assert response.status_code == 200
    payload = response.json()
    assert payload["validation_mode"] == "lenient"
