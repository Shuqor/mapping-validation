import json

import pytest

from core.adapters import build_default_registry, parse_with_registry
from core.adapters.edifact_adapter import EdifactFormatAdapter
from core.adapters.json_adapter import JsonFormatAdapter
from core.adapters.registry import AdapterRegistry
from core.adapters.x12_adapter import X12FormatAdapter


def test_default_registry_contains_json_adapter():
    registry = build_default_registry()
    assert "json" in registry.names()
    assert "x12" in registry.names()
    assert "edifact" in registry.names()


def test_registry_resolves_adapter_by_source_extension():
    registry = AdapterRegistry()
    registry.register(JsonFormatAdapter())
    registry.register(X12FormatAdapter())
    registry.register(EdifactFormatAdapter())

    adapter = registry.resolve_for_source("payload.json")
    assert adapter.name == "json"
    assert registry.resolve_for_source("payload.x12").name == "x12"
    assert registry.resolve_for_source("payload.edifact").name == "edifact"


def test_registry_raises_for_unknown_extension():
    registry = build_default_registry()

    with pytest.raises(ValueError):
        registry.resolve_for_source("payload.xml")


def test_parse_with_registry_normalizes_json_tree_deterministically():
    registry = build_default_registry()
    raw = json.dumps({"z": 1, "a": {"b": True, "c": None}, "items": ["x", 2]}).encode("utf-8")

    doc = parse_with_registry(raw_payload=raw, source_name="sample.json", registry=registry)

    assert doc.source_format == "json"
    assert doc.source_name == "sample.json"
    assert doc.diagnostics.status == "ok"
    assert "normalized_json_tree" in doc.diagnostics.info

    root = doc.content["root"]
    assert root["type"] == "object"
    assert list(root["fields"].keys()) == ["a", "items", "z"]
    assert root["fields"]["a"]["fields"]["b"] == {"type": "boolean", "value": True}
    assert root["fields"]["a"]["fields"]["c"] == {"type": "null", "value": None}
    assert root["fields"]["items"]["type"] == "array"
    assert root["fields"]["items"]["items"][0] == {"type": "string", "value": "x"}
    assert root["fields"]["items"]["items"][1] == {"type": "number", "value": 2}


def test_json_adapter_raises_on_invalid_json():
    adapter = JsonFormatAdapter()

    with pytest.raises(json.JSONDecodeError):
        adapter.parse(raw_payload=b"{bad json}", source_name="broken.json")


def test_x12_adapter_parses_segments_into_canonical_document():
    adapter = X12FormatAdapter()
    payload = b"ISA*00*          *00*          *ZZ*SENDER         *ZZ*RECEIVER       *240101*0101*U*00401*000000001*0*T*:~GS*PO*SENDER*RECEIVER*20240101*0101*1*X*004010~"

    doc = adapter.parse(raw_payload=payload, source_name="sample.x12")

    assert doc.source_format == "x12"
    assert doc.content["root"]["fields"]["interchange_type"] == {"type": "string", "value": "x12"}
    assert doc.content["root"]["fields"]["segments"]["type"] == "array"
    assert "normalized_x12_segments" in " ".join(doc.diagnostics.info)


def test_edifact_adapter_parses_segments_into_canonical_document():
    adapter = EdifactFormatAdapter()
    payload = b"UNB+UNOA:1+SENDER+RECEIVER+240101:0101+000000001'UNH+1+INVOIC:D:96A:UN'BGM+380+342459+9'"

    doc = adapter.parse(raw_payload=payload, source_name="sample.edifact")

    assert doc.source_format == "edifact"
    assert doc.content["root"]["fields"]["interchange_type"] == {"type": "string", "value": "edifact"}
    assert doc.content["root"]["fields"]["segments"]["type"] == "array"
    assert "normalized_edifact_segments" in " ".join(doc.diagnostics.info)
