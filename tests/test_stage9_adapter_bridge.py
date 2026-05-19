from pathlib import Path

import pytest

import core.validate as validate_module


def _stub_report(validation_mode: str = "strict") -> dict:
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
            "parser_status": "clean",
            "parser_confidence": "high",
        },
        "human_summary": {
            "headline": "No mapping issues found",
            "what_to_fix_first": [],
            "issue_breakdown": [],
            "checked_rules": 1,
            "skipped_rules": 0,
            "semantic_summary": {
                "headline": "All rule conditions matched supported semantic patterns",
                "coverage_percent": 100.0,
                "top_suggested_families": [],
            },
            "support_confidence": {
                "parser": "high",
                "enforcement": "high",
            },
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
        "structure_summary": {"status": "PASS", "counts": {}},
        "semantic_summary": {
            "profile": "global",
            "coverage": {
                "total_condition_rules": 0,
                "supported_condition_rules": 0,
                "unsupported_condition_rules": 0,
                "coverage_percent": 100.0,
            },
            "top_unsupported_conditions": [],
            "promote_to_generic_candidates": [],
            "top_suggested_families": [],
        },
        "structure_findings": [],
        "parser_diagnostics": {
            "status": "clean",
            "confidence": "high",
        },
        "rule_support_summary": {
            "total_rules": 1,
            "enforced_rules": 1,
            "parsed_only_rules": 0,
            "unsupported_rules": 0,
            "target_path_heuristic_rules": 0,
            "condition_based_rules": 0,
        },
        "skipped_rules": [],
        "error_sections": {
            "cardinality_violations": [],
            "source_target_missing": [],
            "value_mismatches": [],
            "constant_mismatches": [],
            "concat_mismatches": [],
            "other": [],
        },
        "top_critical_errors": [],
        "error_count": 0,
        "inputs": {
            "spec_path": "rules/spec.xlsx",
            "input_xml_path": "input.xml",
            "output_xml_path": "output.xml",
        },
        "errors": [],
    }


def test_validate_mapping_from_payload_bytes_xml_passthrough(monkeypatch):
    calls = {}

    def _stub_validate(spec_path: str, input_path: str, output_path: str, validation_mode: str = "strict") -> dict:
        calls["spec_path"] = spec_path
        calls["input_xml"] = Path(input_path).read_text(encoding="utf-8")
        calls["output_xml"] = Path(output_path).read_text(encoding="utf-8")
        return _stub_report(validation_mode=validation_mode)

    monkeypatch.setattr(validate_module, "validate_mapping", _stub_validate)

    result = validate_module.validate_mapping_from_payload_bytes(
        spec_path="rules/spec.xlsx",
        input_payload=b"<status><a>1</a></status>",
        input_filename="input.xml",
        output_payload=b"<status><a>1</a></status>",
        output_filename="output.xml",
        validation_mode="lenient",
    )

    assert result["validation_mode"] == "lenient"
    assert "adapter_pipeline" not in result
    assert calls["spec_path"] == "rules/spec.xlsx"
    assert "<status><a>1</a></status>" in calls["input_xml"]
    assert "<status><a>1</a></status>" in calls["output_xml"]


def test_validate_mapping_from_payload_bytes_json_bridge(monkeypatch):
    calls = {}

    def _stub_validate(spec_path: str, input_path: str, output_path: str, validation_mode: str = "strict") -> dict:
        calls["input_xml"] = Path(input_path).read_text(encoding="utf-8")
        calls["output_xml"] = Path(output_path).read_text(encoding="utf-8")
        return _stub_report(validation_mode=validation_mode)

    monkeypatch.setattr(validate_module, "validate_mapping", _stub_validate)

    result = validate_module.validate_mapping_from_payload_bytes(
        spec_path="rules/spec.xlsx",
        input_payload=b'{"status": {"a": 1, "items": ["x"]}}',
        input_filename="input.json",
        output_payload=b'{"status": {"a": 1, "items": ["x"]}}',
        output_filename="output.json",
        validation_mode="strict",
    )

    assert result["summary"]["status"] == "PASS"
    assert result["adapter_pipeline"]["enabled"] is True
    assert result["adapter_pipeline"]["input_format"] == "json"
    assert result["adapter_pipeline"]["output_format"] == "json"
    assert result["inputs"]["input_payload_name"] == "input.json"
    assert result["inputs"]["output_payload_name"] == "output.json"
    assert any("Adapter pipeline mode" in warning for warning in result["warnings"])
    assert "<root>" in calls["input_xml"]
    assert "<status>" in calls["input_xml"]
    assert "<item>x</item>" in calls["input_xml"]
    assert calls["input_xml"] == calls["output_xml"]
    assert result["output_population"]["total_scalar_fields"] >= 2
    assert result["output_population"]["non_empty_scalar_fields"] >= 2


def test_validate_mapping_from_payload_bytes_json_bridge_flags_empty_output_population(monkeypatch):
    def _stub_validate(spec_path: str, input_path: str, output_path: str, validation_mode: str = "strict") -> dict:
        return _stub_report(validation_mode=validation_mode)

    monkeypatch.setattr(validate_module, "validate_mapping", _stub_validate)

    result = validate_module.validate_mapping_from_payload_bytes(
        spec_path="rules/spec.xlsx",
        input_payload=b'{"status": {"a": 1}}',
        input_filename="input.json",
        output_payload=b"{}",
        output_filename="output.json",
        validation_mode="strict",
    )

    assert result["output_population"]["non_empty_scalar_fields"] == 0
    assert any("Output generation check" in warning for warning in result.get("warnings", []))


def test_validate_mapping_from_payload_bytes_x12_bridge(monkeypatch):
    calls = {}

    def _stub_validate(spec_path: str, input_path: str, output_path: str, validation_mode: str = "strict") -> dict:
        calls["input_xml"] = Path(input_path).read_text(encoding="utf-8")
        calls["output_xml"] = Path(output_path).read_text(encoding="utf-8")
        return _stub_report(validation_mode=validation_mode)

    monkeypatch.setattr(validate_module, "validate_mapping", _stub_validate)

    x12_payload = (
        b"ISA*00*          *00*          *ZZ*SENDER         *ZZ*RECEIVER       *240101*0101*U*00401*000000001*0*T*:~"
        b"GS*PO*SENDER*RECEIVER*20240101*0101*1*X*004010~"
    )

    result = validate_module.validate_mapping_from_payload_bytes(
        spec_path="rules/spec.xlsx",
        input_payload=x12_payload,
        input_filename="input.x12",
        output_payload=x12_payload,
        output_filename="output.x12",
        validation_mode="strict",
    )

    assert result["adapter_pipeline"]["enabled"] is True
    assert result["adapter_pipeline"]["input_format"] == "x12"
    assert "<X12>" in calls["input_xml"]
    assert "<ISA>" in calls["input_xml"]


def test_validate_mapping_from_payload_bytes_edifact_bridge(monkeypatch):
    calls = {}

    def _stub_validate(spec_path: str, input_path: str, output_path: str, validation_mode: str = "strict") -> dict:
        calls["input_xml"] = Path(input_path).read_text(encoding="utf-8")
        return _stub_report(validation_mode=validation_mode)

    monkeypatch.setattr(validate_module, "validate_mapping", _stub_validate)

    edi_payload = b"UNB+UNOA:1+SENDER+RECEIVER+240101:0101+000000001'UNH+1+INVOIC:D:96A:UN'"

    result = validate_module.validate_mapping_from_payload_bytes(
        spec_path="rules/spec.xlsx",
        input_payload=edi_payload,
        input_filename="input.edifact",
        output_payload=edi_payload,
        output_filename="output.edifact",
        validation_mode="strict",
    )

    assert result["adapter_pipeline"]["enabled"] is True
    assert result["adapter_pipeline"]["input_format"] == "edifact"
    assert "UNB" in calls["input_xml"]


def test_validate_mapping_from_payload_bytes_detects_edi_flavor(monkeypatch):
    def _stub_validate(spec_path: str, input_path: str, output_path: str, validation_mode: str = "strict") -> dict:
        return _stub_report(validation_mode=validation_mode)

    monkeypatch.setattr(validate_module, "validate_mapping", _stub_validate)

    x12_payload = b"ISA*00*          *00*          *ZZ*SENDER*ZZ*RECEIVER*240101*0101*U*00401*000000001*0*T*:~"
    result_x12 = validate_module.validate_mapping_from_payload_bytes(
        spec_path="rules/spec.xlsx",
        input_payload=x12_payload,
        input_filename="input.edi",
        output_payload=x12_payload,
        output_filename="output.edi",
        validation_mode="strict",
    )
    assert result_x12["adapter_pipeline"]["input_format"] == "x12"

    edifact_payload = b"UNB+UNOA:1+SENDER+RECEIVER+240101:0101+000000001'"
    result_edi = validate_module.validate_mapping_from_payload_bytes(
        spec_path="rules/spec.xlsx",
        input_payload=edifact_payload,
        input_filename="input.edi",
        output_payload=edifact_payload,
        output_filename="output.edi",
        validation_mode="strict",
    )
    assert result_edi["adapter_pipeline"]["input_format"] == "edifact"


def test_validate_mapping_from_payload_bytes_requires_matching_payload_formats():
    with pytest.raises(ValueError):
        validate_module.validate_mapping_from_payload_bytes(
            spec_path="rules/spec.xlsx",
            input_payload=b"<root/>",
            input_filename="input.xml",
            output_payload=b"{}",
            output_filename="output.json",
            validation_mode="strict",
        )


# ── X12 canonical XML converter ───────────────────────────────────────────────


def test_x12_bytes_to_segment_xml_basic_structure():
    """ISA+GS envelope segments appear under <X12>, ST/SE body under <TS_214>."""
    from core.validate import _x12_bytes_to_segment_xml
    from lxml import etree

    x12 = (
        b"ISA*00*          *00*          *ZZ*SENDER         *ZZ*RECEIVER       *240101*0101*U*00401*000000001*0*T*:~"
        b"GS*QM*SENDER*RECEIVER*20240101*0101*1*X*004010~"
        b"ST*214*0001~"
        b"B10*PRO001*PO12345*UPSN~"
        b"L11*TDR99*OQ~"
        b"SE*4*0001~"
        b"GE*1*1~"
        b"IEA*1*000000001~"
    )
    xml_bytes = _x12_bytes_to_segment_xml(x12)
    root = etree.fromstring(xml_bytes)
    assert root.tag == "X12"
    assert root.find("ISA") is not None
    assert root.find("GS") is not None
    ts = root.find("TS_214")
    assert ts is not None
    assert ts.find("B10") is not None


def test_x12_bytes_to_segment_xml_xpath_resolution():
    """/X12/TS_214/B10/B1002 and /X12/GS/GS03 must resolve to the correct values."""
    from core.validate import _x12_bytes_to_segment_xml
    from lxml import etree

    x12 = (
        b"ISA*00*          *00*          *ZZ*JABILINC        *ZZ*E2NETSUPPLY    *240101*0101*U*00401*000000001*0*T*:~"
        b"GS*QM*JABILINC*E2NETSUPPLY*20240101*0101*1*X*004010~"
        b"ST*214*0001~"
        b"B10*PRO123456*PO9876543*UPSN~"
        b"L11*TDR88776*OQ~"
        b"L11*EQ112233*EQ~"
        b"SE*6*0001~"
        b"GE*1*1~"
        b"IEA*1*000000001~"
    )
    xml_bytes = _x12_bytes_to_segment_xml(x12)
    tree = etree.fromstring(xml_bytes)

    assert tree.xpath("/X12/TS_214/B10/B1002")[0].text == "PO9876543"
    assert tree.xpath("/X12/TS_214/B10/B1001")[0].text == "PRO123456"
    assert tree.xpath("/X12/TS_214/B10/B1003")[0].text == "UPSN"
    assert tree.xpath("/X12/GS/GS03")[0].text == "E2NETSUPPLY"
    # L11 with L1102="OQ" - first occurrence
    l11_nodes = tree.xpath("/X12/TS_214/L11")
    assert len(l11_nodes) == 2
    assert l11_nodes[0].find("L1101").text == "TDR88776"
    assert l11_nodes[0].find("L1102").text == "OQ"


def test_x12_bytes_to_segment_xml_empty_payload():
    """Empty payload returns minimal <X12/> document without error."""
    from core.validate import _x12_bytes_to_segment_xml

    result = _x12_bytes_to_segment_xml(b"")
    assert b"<X12" in result


# ── EDIFACT canonical XML converter ──────────────────────────────────────────


def test_edifact_bytes_to_segment_xml_basic_structure():
    """UNB appears under <EDIFACT>; UNH/UNT body under <MSG_INVOIC>."""
    from core.validate import _edifact_bytes_to_segment_xml
    from lxml import etree

    edi = b"UNB+UNOA:1+SENDER+RECEIVER+240101:0101+000000001'UNH+1+INVOIC:D:96A:UN'BGM+380+342459+9'UNT+3+1'UNZ+1+000000001'"
    xml_bytes = _edifact_bytes_to_segment_xml(edi)
    root = etree.fromstring(xml_bytes)
    assert root.tag == "EDIFACT"
    assert root.find("UNB") is not None
    msg = root.find("MSG_INVOIC")
    assert msg is not None
    assert msg.find("BGM") is not None


def test_edifact_bytes_to_segment_xml_xpath_resolution():
    """/EDIFACT/MSG_INVOIC/BGM/BGM01 must resolve to the correct value."""
    from core.validate import _edifact_bytes_to_segment_xml
    from lxml import etree

    edi = b"UNB+UNOA:1+SENDER+RECEIVER+240101:0101+000000001'UNH+1+INVOIC:D:96A:UN'BGM+380+342459+9'UNT+3+1'UNZ+1+000000001'"
    xml_bytes = _edifact_bytes_to_segment_xml(edi)
    tree = etree.fromstring(xml_bytes)

    assert tree.xpath("/EDIFACT/MSG_INVOIC/BGM/BGM01")[0].text == "380"
    assert tree.xpath("/EDIFACT/MSG_INVOIC/BGM/BGM02")[0].text == "342459"
    assert tree.xpath("/EDIFACT/UNB/UNB02")[0].text == "SENDER"


# ── Cross-format bridge: X12 input + JSON/XML output ─────────────────────────


def test_validate_mapping_cross_format_x12_input_json_output(monkeypatch, tmp_path):
    """X12 input + JSON output is accepted when spec has x12_segment layout."""
    calls = {}

    def _stub_validate(spec_path, input_path, output_path, validation_mode="strict"):
        calls["input_xml"] = Path(input_path).read_text(encoding="utf-8")
        calls["output_xml"] = Path(output_path).read_text(encoding="utf-8")
        return _stub_report(validation_mode=validation_mode)

    monkeypatch.setattr(validate_module, "validate_mapping", _stub_validate)
    monkeypatch.setattr(validate_module, "_get_spec_layout", lambda _: "x12_segment")

    x12_payload = (
        b"ISA*00*          *00*          *ZZ*JABILINC        *ZZ*E2NETSUPPLY    *240101*0101*U*00401*000000001*0*T*:~"
        b"GS*QM*JABILINC*E2NETSUPPLY*20240101*0101*1*X*004010~"
        b"ST*214*0001~"
        b"B10*PRO001*PO12345*UPSN~"
        b"SE*3*0001~"
        b"GE*1*1~"
        b"IEA*1*000000001~"
    )
    json_payload = b'{"upserts": {"loadStatus": {"loadId": "PO12345"}}}'

    result = validate_module.validate_mapping_from_payload_bytes(
        spec_path="rules/spec.xlsx",
        input_payload=x12_payload,
        input_filename="input.x12",
        output_payload=json_payload,
        output_filename="output.json",
        validation_mode="strict",
    )

    assert result["adapter_pipeline"]["enabled"] is True
    assert result["adapter_pipeline"]["mode"] == "cross_format"
    assert result["adapter_pipeline"]["input_format"] == "x12"
    assert result["adapter_pipeline"]["output_format"] == "json"
    # Input XML must contain X12 segment structure
    assert "<X12>" in calls["input_xml"]
    assert "<TS_214>" in calls["input_xml"]
    assert "<B10>" in calls["input_xml"]
    # Output XML must reflect the JSON path structure
    assert "<loadId>" in calls["output_xml"]
    # Warning about GROUP_* paths must be present
    assert any("Cross-format bridge" in w for w in result["warnings"])


def test_validate_mapping_cross_format_rejected_without_x12_segment_spec(monkeypatch):
    """X12 input + JSON output must be rejected when spec is not x12_segment layout."""
    monkeypatch.setattr(validate_module, "_get_spec_layout", lambda _: "xpath_target")

    with pytest.raises(ValueError, match="must match"):
        validate_module.validate_mapping_from_payload_bytes(
            spec_path="rules/spec.xlsx",
            input_payload=b"ISA*00*~",
            input_filename="input.x12",
            output_payload=b"{}",
            output_filename="output.json",
        )


def test_validate_mapping_cross_format_edifact_input_json_output(monkeypatch):
    """EDIFACT input + JSON output is accepted when spec has x12_segment layout."""
    calls = {}

    def _stub_validate(spec_path, input_path, output_path, validation_mode="strict"):
        calls["input_xml"] = Path(input_path).read_text(encoding="utf-8")
        calls["output_xml"] = Path(output_path).read_text(encoding="utf-8")
        return _stub_report(validation_mode=validation_mode)

    monkeypatch.setattr(validate_module, "validate_mapping", _stub_validate)
    monkeypatch.setattr(validate_module, "_get_spec_layout", lambda _: "x12_segment")

    edifact_payload = (
        b"UNB+UNOA:1+SENDER+RECEIVER+240101:0101+000000001'"
        b"UNH+1+INVOIC:D:96A:UN'"
        b"BGM+380+342459+9'"
        b"UNT+3+1'"
        b"UNZ+1+000000001'"
    )
    json_payload = b'{"invoice": {"id": "342459", "type": "380"}}'

    result = validate_module.validate_mapping_from_payload_bytes(
        spec_path="rules/spec.xlsx",
        input_payload=edifact_payload,
        input_filename="input.edifact",
        output_payload=json_payload,
        output_filename="output.json",
        validation_mode="strict",
    )

    assert result["adapter_pipeline"]["enabled"] is True
    assert result["adapter_pipeline"]["mode"] == "cross_format"
    assert result["adapter_pipeline"]["input_format"] == "edifact"
    assert result["adapter_pipeline"]["output_format"] == "json"
    assert "<EDIFACT>" in calls["input_xml"]
    assert "<MSG_INVOIC>" in calls["input_xml"]
    assert "<BGM>" in calls["input_xml"]
    assert "<invoice>" in calls["output_xml"]
    assert any("Cross-format bridge" in warning for warning in result.get("warnings", []))


def test_x12_canonical_xml_from_sample_file():
    """Sample input.x12 must parse to valid segment-addressable XML."""
    from core.validate import _x12_bytes_to_segment_xml
    from lxml import etree

    sample = Path("samples/input.x12").read_bytes()
    xml_bytes = _x12_bytes_to_segment_xml(sample)
    root = etree.fromstring(xml_bytes)
    assert root.tag == "X12"
    assert root.xpath("/X12/TS_214/B10/B1002")[0].text == "PO9876543"
    assert root.xpath("/X12/GS/GS03")[0].text == "E2NETSUPPLY"

