import json

import core.validate as validate_module


def _write_xml(path, body: str) -> None:
    path.write_text(body, encoding="utf-8")


def _patch_rules(monkeypatch, rules):
    monkeypatch.setattr(validate_module, "read_mapping_table", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(validate_module, "extract_rules", lambda _df: rules)
    monkeypatch.setattr(validate_module, "get_parser_diagnostics", lambda _df: {
        "status": "clean",
        "confidence": "high",
        "warnings": [],
        "sheet_name": "Mapping",
        "header_row": 0,
        "layout": rules[0].get("layout", "xpath_target") if rules else "xpath_target",
        "rule_count": len(rules),
        "extraction": {"ambiguities": []},
    })


def test_report_format_pass(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"
    report = tmp_path / "report_pass.json"

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction1>STATUS</ediFunction1>\n'
        '</status>\n'
    )
    _write_xml(src_xml, xml)
    _write_xml(tgt_xml, xml)

    rules = [
        {
            "target_xpath": "/status/ediFunction1",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "1..1",
            "condition": 'If Source !="" then map Source to Target',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))
    validate_module.write_report(result, str(report))

    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["summary"]["status"] == "PASS"
    assert payload["summary"]["parser_status"] == "clean"
    assert payload["summary"]["parser_confidence"] == "high"
    assert payload["summary"]["error_count"] == 0
    assert payload["summary"]["top_critical_errors"] == []
    assert payload["summary"]["grouped_error_counts"]["source_target_missing"] == 0
    assert payload["human_summary"]["headline"] == "No mapping issues found"
    assert payload["human_summary"]["what_to_fix_first"] == []
    assert payload["valid"] is True
    assert payload["validation_mode"] == "strict"
    assert payload["error_count"] == 0
    assert isinstance(payload["warnings"], list)
    assert payload["parser_diagnostics"]["sheet_name"] == "Mapping"
    assert payload["rule_support_summary"]["enforced_rules"] >= 1
    assert isinstance(payload["rule_stats"], dict)
    assert isinstance(payload["error_sections"], dict)
    assert isinstance(payload["errors"], list)
    assert payload["report_id"]
    assert payload["generated_at_utc"]


def test_report_format_fail(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"
    report = tmp_path / "report_fail.json"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction1>STATUS</ediFunction1>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/ediFunction1",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "1..1",
            "condition": 'If Source !="" then map Source to Target',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))
    validate_module.write_report(result, str(report))

    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["summary"]["status"] == "FAIL"
    assert payload["summary"]["parser_status"] == "clean"
    assert payload["summary"]["error_count"] > 0
    assert payload["summary"]["top_critical_errors"]
    assert payload["summary"]["grouped_error_counts"]["source_target_missing"] > 0
    assert payload["human_summary"]["what_to_fix_first"]
    assert payload["human_summary"]["what_to_fix_first"][0].startswith("Add the missing target field")
    assert "Target:" not in payload["human_summary"]["what_to_fix_first"][0]
    assert "Row " not in payload["human_summary"]["what_to_fix_first"][0]
    assert payload["human_summary"]["issue_breakdown"]
    assert payload["valid"] is False
    assert payload["strict_would_fail"] is True
    assert payload["error_count"] > 0
    assert payload["errors"]


def test_direct_mapping_without_condition_flags_missing_target(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction1>STATUS</ediFunction1>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/ediFunction1",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "",
            "condition": "",
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "FAIL"
    assert result["summary"]["grouped_error_counts"]["source_target_missing"] == 1
    assert any("Source exists but target is missing" in item for item in result["errors"])


def test_direct_mapping_to_container_path_counts_node_presence(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status>\n'
        '  <inputVal>A</inputVal>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status>\n'
        '  <items><item><value>A</value></item></items>\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/items",
            "source_xpath": "/status/inputVal",
            "cardinality": "",
            "condition": "",
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["summary"]["grouped_error_counts"]["source_target_missing"] == 0
    assert result["summary"]["grouped_error_counts"]["value_mismatches"] == 0


def test_guard_only_if_equals_condition_filters_mapping(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status>\n'
        '  <srcVal>HELLO</srcVal>\n'
        '  <G6103>TE</G6103>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status>\n'
        '  <outVal>WRONG</outVal>\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/outVal",
            "source_xpath": "/status/srcVal",
            "cardinality": "0..1",
            "condition": "if G6103='TE'",
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "FAIL"
    assert result["summary"]["grouped_error_counts"]["if_equals_mismatches"] == 1
    assert any("expected HELLO, got WRONG" in item for item in result["errors"])


def test_guard_only_if_equals_condition_skips_when_false(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status>\n'
        '  <srcVal>HELLO</srcVal>\n'
        '  <G6103>ZZ</G6103>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status>\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/outVal",
            "source_xpath": "/status/srcVal",
            "cardinality": "0..1",
            "condition": "if G6103='TE'",
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["summary"]["grouped_error_counts"]["source_target_missing"] == 0
    assert result["summary"]["grouped_error_counts"]["if_equals_mismatches"] == 0


def test_empty_target_value_is_treated_as_missing(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction1>STATUS</ediFunction1>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction1></ediFunction1>\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/ediFunction1",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "1..1",
            "condition": 'If Source !="" then map Source to Target',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "FAIL"
    assert result["summary"]["grouped_error_counts"]["source_target_missing"] == 1
    assert any("Source exists but target is missing" in item for item in result["errors"])


def test_structure_strict_flags_missing_branch_and_unexpected_node(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <detail>\n'
        '    <ediFunction1>STATUS</ediFunction1>\n'
        '  </detail>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <extraNode>noise</extraNode>\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/detail/ediFunction1",
            "source_xpath": "/status/detail/ediFunction1",
            "cardinality": "1..1",
            "condition": 'If Source !="" then map Source to Target',
            "note": "",
            "m_o": "M",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping(
        "unused.xlsx",
        str(src_xml),
        str(tgt_xml),
        validation_mode="structure_strict",
    )

    assert result["summary"]["status"] == "FAIL"
    assert result["validation_mode"] == "structure_strict"
    assert result["summary"]["grouped_error_counts"]["missing_target_branches"] == 1
    assert result["summary"]["grouped_error_counts"]["unexpected_target_nodes"] == 1
    assert result["summary"]["grouped_error_counts"]["source_target_missing"] == 1
    assert result["summary"]["grouped_error_counts"]["cardinality_violations"] == 1
    assert result["rule_stats"]["missing_target_branches"] == 1
    assert result["rule_stats"]["unexpected_target_nodes"] == 1
    assert result["rule_stats"]["source_target_missing"] == 1
    assert result["rule_stats"]["cardinality_violations"] == 1
    assert any("Required target branch is missing" in item for item in result["errors"])
    assert any("Unexpected target node not described by the spec" in item for item in result["errors"])
    assert result["human_summary"]["what_to_fix_first"][0].startswith("Add the required target branch")
    assert any("Structure-strict mode enabled" in item for item in result["warnings"])


def test_strict_mode_does_not_flag_unexpected_target_nodes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction1>STATUS</ediFunction1>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction1>STATUS</ediFunction1>\n'
        '  <extraNode>noise</extraNode>\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/ediFunction1",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "1..1",
            "condition": 'If Source !="" then map Source to Target',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["summary"]["grouped_error_counts"]["unexpected_target_nodes"] == 0
    assert result["summary"]["grouped_error_counts"]["missing_target_branches"] == 0


def test_structure_strict_flags_root_mismatch(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status">\n'
        '  <ediFunction1>STATUS</ediFunction1>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<shipment xmlns="http://tms-lsp.blujaysolutions.net/api/status">\n'
        '  <ediFunction1>STATUS</ediFunction1>\n'
        '</shipment>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/ediFunction1",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "1..1",
            "condition": 'If Source !="" then map Source to Target',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping(
        "unused.xlsx",
        str(src_xml),
        str(tgt_xml),
        validation_mode="structure_strict",
    )

    assert result["summary"]["grouped_error_counts"]["root_mismatches"] == 1
    assert any("Target root does not match spec" in item for item in result["errors"])


def test_structure_strict_flags_unexpected_target_attribute(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    xml_src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction1>STATUS</ediFunction1>\n'
        '</status>\n'
    )
    xml_tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status" extraFlag="1">\n'
        '  <ediFunction1>STATUS</ediFunction1>\n'
        '</status>\n'
    )
    _write_xml(src_xml, xml_src)
    _write_xml(tgt_xml, xml_tgt)

    rules = [
        {
            "target_xpath": "/status/@type",
            "source_xpath": "/status/@type",
            "cardinality": "1..1",
            "condition": 'If Source !="" then map Source to Target',
            "note": "",
        },
        {
            "target_xpath": "/status/ediFunction1",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "1..1",
            "condition": 'If Source !="" then map Source to Target',
            "note": "",
        },
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping(
        "unused.xlsx",
        str(src_xml),
        str(tgt_xml),
        validation_mode="structure_strict",
    )

    assert result["summary"]["grouped_error_counts"]["unexpected_target_attributes"] == 1
    assert any("Unexpected target attribute not described by the spec" in item for item in result["errors"])


def test_structure_strict_uses_parsed_only_rule_parent_branches(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status">\n'
        '  <detail>\n'
        '    <ediFunction1>STATUS</ediFunction1>\n'
        '  </detail>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status">\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/detail/ediFunction1",
            "source_xpath": "/status/detail/ediFunction1",
            "cardinality": "",
            "condition": "current datetime",
            "note": "",
            "m_o": "M",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping(
        "unused.xlsx",
        str(src_xml),
        str(tgt_xml),
        validation_mode="structure_strict",
    )

    assert result["summary"]["grouped_error_counts"]["missing_target_branches"] == 1
    assert any("Target: /status/detail | Required target branch is missing" in item for item in result["errors"])


def test_structure_strict_ignores_allowlisted_noise_nodes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status">\n'
        '  <ediFunction1>STATUS</ediFunction1>\n'
        '  <debug>noise</debug>\n'
        '</status>\n'
    )
    _write_xml(src_xml, xml)
    _write_xml(tgt_xml, xml)

    rules = [
        {
            "target_xpath": "/status/ediFunction1",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "1..1",
            "condition": 'If Source !="" then map Source to Target',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping(
        "unused.xlsx",
        str(src_xml),
        str(tgt_xml),
        validation_mode="structure_strict",
    )

    assert result["summary"]["status"] == "PASS"
    assert result["summary"]["grouped_error_counts"]["unexpected_target_nodes"] == 0


def test_structure_summary_reports_repeat_count_violation(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status">\n'
        '  <detail>one</detail>\n'
        '  <detail>two</detail>\n'
        '</status>\n'
    )
    _write_xml(src_xml, xml)
    _write_xml(tgt_xml, xml)

    rules = [
        {
            "target_xpath": "/status/detail",
            "source_xpath": "/status/detail",
            "cardinality": "0..1",
            "condition": 'If Source !="" then map Source to Target',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping(
        "unused.xlsx",
        str(src_xml),
        str(tgt_xml),
        validation_mode="structure_strict",
    )

    assert result["structure_summary"]["counts"]["repeat_count_violations"] == 1
    assert any("Repeat count violation" in item for item in result["structure_summary"]["repeat_count_examples"])


def test_spec_scoped_structure_exception_ignores_known_required_path(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status">\n'
        '  <ediFunction1>STATUS</ediFunction1>\n'
        '</status>\n'
    )
    _write_xml(src_xml, xml)
    _write_xml(tgt_xml, xml)

    rules = [
        {
            "target_xpath": "interchange/message/status/fileHeader/trackingAndTracing/details/detail",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "0..1",
            "condition": 'If Source !="" then map Source to Target',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping(
        "spec.xlsx",
        str(src_xml),
        str(tgt_xml),
        validation_mode="structure_strict",
    )

    assert result["summary"]["grouped_error_counts"]["missing_target_branches"] == 0
    assert "/interchange" in result["structure_summary"]["applied_exceptions"]["ignore_required_paths"]
    assert "structure_exceptions.json" in result["structure_summary"]["applied_exceptions"]["config_source"]


def test_structure_summary_includes_coverage_and_findings(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status">\n'
        '  <detail><ediFunction1>STATUS</ediFunction1></detail>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status">\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/detail/ediFunction1",
            "source_xpath": "/status/detail/ediFunction1",
            "cardinality": "1..1",
            "condition": 'If Source !="" then map Source to Target',
            "note": "",
            "m_o": "M",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping(
        "unused.xlsx",
        str(src_xml),
        str(tgt_xml),
        validation_mode="structure_strict",
    )

    coverage = result["structure_summary"].get("coverage", {})
    assert coverage["allowed_paths"] >= 1
    assert coverage["missing_allowed_paths"] >= 1
    assert isinstance(coverage["coverage_percent"], float)

    assert result["structure_summary"]["finding_count"] >= 1
    assert result["structure_findings"]
    assert any(item["category"] == "missing_target_branches" for item in result["structure_findings"])


def test_structure_conditional_requirement_not_enforced_when_source_is_empty(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status">\n'
        '</status>\n'
    )
    _write_xml(src_xml, xml)
    _write_xml(tgt_xml, xml)

    rules = [
        {
            "target_xpath": "/status/detail/ediFunction1",
            "source_xpath": "/status/detail/ediFunction1",
            "cardinality": "1..1",
            "condition": 'If Source !="" then map Source to Target',
            "note": "",
            "m_o": "M",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping(
        "unused.xlsx",
        str(src_xml),
        str(tgt_xml),
        validation_mode="structure_strict",
    )

    assert result["summary"]["grouped_error_counts"]["missing_target_branches"] == 0


def test_structure_per_parent_cardinality_violation_is_reported(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status">\n'
        '  <detail><lineItem>A</lineItem></detail>\n'
        '  <detail></detail>\n'
        '</status>\n'
    )
    _write_xml(src_xml, xml)
    _write_xml(tgt_xml, xml)

    rules = [
        {
            "target_xpath": "/status/detail/lineItem",
            "source_xpath": "/status/detail/lineItem",
            "cardinality": "1..1",
            "condition": 'If Source !="" then map Source to Target',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping(
        "unused.xlsx",
        str(src_xml),
        str(tgt_xml),
        validation_mode="structure_strict",
    )

    assert result["summary"]["grouped_error_counts"]["child_cardinality_violations"] >= 1


def test_structure_required_attribute_missing_is_reported(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status">\n'
        '  <detail>abc</detail>\n'
        '</status>\n'
    )
    _write_xml(src_xml, xml)
    _write_xml(tgt_xml, xml)

    rules = [
        {
            "target_xpath": "/status/detail/@code",
            "source_xpath": "/status/detail",
            "cardinality": "1..1",
            "condition": "",
            "note": "",
            "m_o": "M",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping(
        "unused.xlsx",
        str(src_xml),
        str(tgt_xml),
        validation_mode="structure_strict",
    )

    assert result["summary"]["grouped_error_counts"]["required_target_attributes_missing"] == 1


def test_structure_choice_group_violation_is_reported(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status">\n'
        '  <detail><optionA>A</optionA><optionB>B</optionB></detail>\n'
        '</status>\n'
    )
    _write_xml(src_xml, xml)
    _write_xml(tgt_xml, xml)

    rules = [
        {
            "target_xpath": "/status/detail/optionA",
            "source_xpath": "/status/detail/optionA",
            "cardinality": "0..1",
            "condition": 'If Source !="" then map Source to Target',
            "note": "",
        },
        {
            "target_xpath": "/status/detail/optionB",
            "source_xpath": "/status/detail/optionB",
            "cardinality": "0..1",
            "condition": 'If Source !="" then map Source to Target',
            "note": "",
        },
    ]
    _patch_rules(monkeypatch, rules)
    monkeypatch.setitem(
        validate_module._STRUCTURE_SPEC_EXCEPTIONS,
        "unused.xlsx",
        {
            "ignore_required_paths": set(),
            "allow_nodes": set(),
            "allow_attributes": set(),
            "ordered_sibling_groups": [],
            "choice_groups": [
                {
                    "parent_path": "/status/detail",
                    "options": ["/status/detail/optionA", "/status/detail/optionB"],
                    "min": 1,
                    "max": 1,
                }
            ],
        },
    )

    result = validate_module.validate_mapping(
        "unused.xlsx",
        str(src_xml),
        str(tgt_xml),
        validation_mode="structure_strict",
    )

    assert result["summary"]["grouped_error_counts"]["choice_group_violations"] == 1


def test_structure_sibling_order_violation_is_reported(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status">\n'
        '  <detail><second>B</second><first>A</first></detail>\n'
        '</status>\n'
    )
    _write_xml(src_xml, xml)
    _write_xml(tgt_xml, xml)

    rules = [
        {
            "target_xpath": "/status/detail/first",
            "source_xpath": "/status/detail/first",
            "cardinality": "0..1",
            "condition": 'If Source !="" then map Source to Target',
            "note": "",
        },
        {
            "target_xpath": "/status/detail/second",
            "source_xpath": "/status/detail/second",
            "cardinality": "0..1",
            "condition": 'If Source !="" then map Source to Target',
            "note": "",
        },
    ]
    _patch_rules(monkeypatch, rules)
    monkeypatch.setitem(
        validate_module._STRUCTURE_SPEC_EXCEPTIONS,
        "unused.xlsx",
        {
            "ignore_required_paths": set(),
            "allow_nodes": set(),
            "allow_attributes": set(),
            "ordered_sibling_groups": [
                {
                    "parent_path": "/status/detail",
                    "children": ["/status/detail/first", "/status/detail/second"],
                }
            ],
            "choice_groups": [],
        },
    )

    result = validate_module.validate_mapping(
        "unused.xlsx",
        str(src_xml),
        str(tgt_xml),
        validation_mode="structure_strict",
    )

    assert result["summary"]["grouped_error_counts"]["sibling_order_violations"] == 1


def test_structure_namespace_mismatch_is_reported(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status">\n'
        '  <detail>ok</detail>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" xmlns:alt="http://alt.example/ns">\n'
        '  <alt:detail>ok</alt:detail>\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/detail",
            "source_xpath": "/status/detail",
            "cardinality": "1..1",
            "condition": 'If Source !="" then map Source to Target',
            "note": "",
            "m_o": "M",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping(
        "unused.xlsx",
        str(src_xml),
        str(tgt_xml),
        validation_mode="structure_strict",
    )

    assert result["summary"]["grouped_error_counts"]["namespace_mismatches"] == 1


def test_optional_rule_allows_missing_target(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction1>STATUS</ediFunction1>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/ediFunction1",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "",
            "condition": "",
            "note": "",
            "m_o": "O",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["summary"]["grouped_error_counts"]["source_target_missing"] == 0
    assert result["error_count"] == 0


def test_mandatory_rule_requires_target_when_source_has_value(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction1>STATUS</ediFunction1>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/ediFunction1",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "",
            "condition": "",
            "note": "",
            "m_o": "M",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "FAIL"
    assert result["summary"]["grouped_error_counts"]["source_target_missing"] == 1
    assert any("Mandatory target is missing" in item for item in result["errors"])


def test_report_format_lenient_mode(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction1>STATUS</ediFunction1>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/ediFunction1",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "1..1",
            "condition": 'If Source !="" then map Source to Target',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping(
        "unused.xlsx",
        str(src_xml),
        str(tgt_xml),
        validation_mode="lenient",
    )

    assert result["summary"]["status"] == "PASS_WITH_WARNINGS"
    assert result["valid"] is True
    assert result["strict_would_fail"] is True
    assert result["warnings"]


def test_multi_condition_and_hardcode_target_as_supported(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <R401>L</R401>\n'
        '  <DTM01>369</DTM01>\n'
        '  <DTM02>20260518</DTM02>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <eventType>EstimatedDepartureDate</eventType>\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/eventType",
            "source_xpath": "/status/R401",
            "cardinality": "",
            "condition": 'if R401 = "L" and DTM01 = "369" and DTM02 exists then Hardcode Target as "EstimatedDepartureDate"',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["error_count"] == 0
    assert result["rule_support_summary"]["multi_condition_and_rules"] == 1


def test_multi_condition_and_concat_map_supported(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <R401>L</R401>\n'
        '  <DTM01>369</DTM01>\n'
        '  <DTM02>20260518</DTM02>\n'
        '  <DTM03>1215</DTM03>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <eventDateTime>202605181215</eventDateTime>\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/eventDateTime",
            "source_xpath": "/status/R401",
            "cardinality": "",
            "condition": 'if R401 = "L" and DTM01 = "369" then map DTM02 + DTM03 to Target',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["error_count"] == 0
    assert result["rule_support_summary"]["multi_condition_and_rules"] == 1


def test_multi_condition_and_concat_map_mismatch(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <R401>L</R401>\n'
        '  <DTM01>369</DTM01>\n'
        '  <DTM02>20260518</DTM02>\n'
        '  <DTM03>1215</DTM03>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <eventDateTime>202605180000</eventDateTime>\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/eventDateTime",
            "source_xpath": "/status/R401",
            "cardinality": "",
            "condition": 'if R401 = "L" and DTM01 = "369" then map DTM02 + DTM03 to Target',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "FAIL"
    assert result["summary"]["grouped_error_counts"]["if_equals_mismatches"] == 1
    assert any("Multi-condition mapping mismatch" in item for item in result["errors"])


def test_multi_condition_and_not_equals_operator_supported(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <N101>CP</N101>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <partyType>Customer</partyType>\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/partyType",
            "source_xpath": "/status/N101",
            "cardinality": "",
            "condition": 'if N101 <> "LL" and N101 <> "SF" then map "Customer" to Target',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["error_count"] == 0
    assert result["rule_support_summary"]["multi_condition_and_rules"] == 1


def test_multi_condition_and_not_equals_bang_operator_supported(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <N101>CP</N101>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <partyType>Customer</partyType>\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/partyType",
            "source_xpath": "/status/N101",
            "cardinality": "",
            "condition": 'if N101 != "LL" and N101 != "SF" then map "Customer" to Target',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["error_count"] == 0
    assert result["rule_support_summary"]["multi_condition_and_rules"] == 1


def test_concat_condition_spelling_tolerance(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction1>STATUS</ediFunction1>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction1>ID-STATUS</ediFunction1>\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/ediFunction1",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "1..1",
            "condition": 'Concatenate("ID-", <ediFunction1>)',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["error_count"] == 0


def test_unsupported_condition_is_tracked_as_skipped(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction1>STATUS</ediFunction1>\n'
        '</status>\n'
    )
    _write_xml(src_xml, xml)
    _write_xml(tgt_xml, xml)

    rules = [
        {
            "target_xpath": "/status/ediFunction1",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "",
            "condition": "Apply custom transform rule",
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["error_count"] == 0
    assert len(result["skipped_rules"]) == 1
    assert result["skipped_rules"][0]["reason"] == "Unsupported condition pattern"
    assert any("Skipped 1 rule(s)" in warning for warning in result["warnings"])
    assert result["rule_support_summary"]["unsupported_rules"] == 1
    assert result["rule_support_summary"]["parsed_only_rules"] >= 1


def test_source_value_translation_condition_passes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction1>DD</ediFunction1>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction1>DoorToDoor</ediFunction1>\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/ediFunction1",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "",
            "condition": 'Conversion: If Source = "DD" then map Target as "DoorToDoor"',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["error_count"] == 0
    assert result["rule_support_summary"]["translated_condition_rules"] == 1
    assert result["rule_support_summary"]["unsupported_rules"] == 0


def test_guard_only_condition_is_parsed_only_not_unsupported(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction1>STATUS</ediFunction1>\n'
        '</status>\n'
    )
    _write_xml(src_xml, xml)
    _write_xml(tgt_xml, xml)

    rules = [
        {
            "target_xpath": "/status/ediFunction1",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "",
            "condition": 'If /status/ediFunction1 = "STATUS"',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert len(result["skipped_rules"]) == 0
    assert result["rule_support_summary"]["unsupported_rules"] == 0
    assert result["rule_support_summary"]["parsed_only_rules"] >= 1
    assert result["rule_support_summary"]["guard_only_condition_rules"] == 1


def test_guard_only_not_equals_chain_is_parsed_only(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <N101>CP</N101>\n'
        '</status>\n'
    )
    _write_xml(src_xml, xml)
    _write_xml(tgt_xml, xml)

    rules = [
        {
            "target_xpath": "/status/N101",
            "source_xpath": "/status/N101",
            "cardinality": "",
            "condition": 'N101 <> "LL" and N101 <> "SF"',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert len(result["skipped_rules"]) == 0
    assert result["rule_support_summary"]["unsupported_rules"] == 0
    assert result["rule_support_summary"]["parsed_only_rules"] >= 1
    assert result["rule_support_summary"]["guard_only_condition_rules"] == 1


def test_source_value_translation_mismatch_is_reported(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction1>DD</ediFunction1>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction1>PortToPort</ediFunction1>\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/ediFunction1",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "",
            "condition": 'If Source = "DD" then map Target as "DoorToDoor"',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "FAIL"
    assert result["summary"]["grouped_error_counts"]["translated_value_mismatches"] == 1
    assert result["human_summary"]["issue_breakdown"][0]["issue"] == "Mapped values need correction"
    assert result["human_summary"]["what_to_fix_first"][0] == "Update /status/ediFunction1 so it uses the expected mapped value."


def test_source_value_translation_with_else_maps_source(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction1>X</ediFunction1>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction1>X</ediFunction1>\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/ediFunction1",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "",
            "condition": (
                'Conversion:\n\n'
                'if Source = "U" then map "AMEND" to Target\n'
                'elseif Source = "N" then map "REQUEST" to Target\n'
                'else then map Source to Target\n'
                'endIf'
            ),
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["error_count"] == 0
    assert result["rule_support_summary"]["translated_condition_rules"] == 1


def test_source_exists_target_constant_condition_passes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction1>anything</ediFunction1>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction1>ISO</ediFunction1>\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/ediFunction1",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "",
            "condition": 'If Source exists then map Target as "ISO"',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["error_count"] == 0
    assert result["rule_support_summary"]["source_exists_condition_rules"] == 1


def test_source_exists_target_constant_mismatch_is_reported(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction1>anything</ediFunction1>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction1>BAD</ediFunction1>\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/ediFunction1",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "",
            "condition": 'If Source exists then map Target as "ISO"',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "FAIL"
    assert result["summary"]["grouped_error_counts"]["source_exists_mismatches"] == 1
    assert result["human_summary"]["issue_breakdown"][0]["issue"] == "Source-exists mapping needs correction"


def test_startswith_replace_mapping_passes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction1>NVO-12345</ediFunction1>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction1>12345</ediFunction1>\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/ediFunction1",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "",
            "condition": (
                'if Source startsWith "NVO-" then '
                'replace Characters "NVO-" with "" in K101 and map to Target'
            ),
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["error_count"] == 0
    assert result["rule_support_summary"]["startswith_replace_rules"] == 1


def test_startswith_replace_mapping_mismatch_is_reported(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction1>NVO-12345</ediFunction1>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction1>BAD</ediFunction1>\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/ediFunction1",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "",
            "condition": (
                'if Source startsWith "NVO-" then '
                'replace Characters "NVO-" with "" in K101 and map to Target'
            ),
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "FAIL"
    assert result["summary"]["grouped_error_counts"]["startswith_transform_mismatches"] == 1
    assert result["human_summary"]["issue_breakdown"][0]["issue"] == "Starts-with transformation needs correction"


def test_startswith_replace_append_with_sibling_field_passes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction1>GEN-123</ediFunction1>\n'
        '  <ediFunction2>ABC</ediFunction2>\n'
        '  <ediFunction3>123ABC</ediFunction3>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction3>123ABC</ediFunction3>\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/ediFunction3",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "",
            "condition": (
                'if Source startsWith "GEN-" then '
                'replace Characters "GEN-" with "" in ediFunction1 and append with ediFunction2 and map to Target'
            ),
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["error_count"] == 0
    assert result["rule_support_summary"]["startswith_replace_append_rules"] == 1


def test_startswith_replace_append_with_sibling_field_mismatch_is_reported(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction1>GEN-123</ediFunction1>\n'
        '  <ediFunction2>ABC</ediFunction2>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction3>BAD</ediFunction3>\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/ediFunction3",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "",
            "condition": (
                'if Source startsWith "GEN-" then '
                'replace Characters "GEN-" with "" in ediFunction1 and append with ediFunction2 and map to Target'
            ),
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "FAIL"
    assert result["summary"]["grouped_error_counts"]["startswith_append_mismatches"] == 1
    assert result["human_summary"]["issue_breakdown"][0]["issue"] == "Starts-with + append transformation needs correction"


def test_startswith_replace_append_with_literal_passes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction1>PRE-77</ediFunction1>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction3>77-A</ediFunction3>\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/ediFunction3",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "",
            "condition": (
                'if Source startsWith "PRE-" then '
                'replace Characters "PRE-" with "" in ediFunction1 and append with "-A" and map to Target'
            ),
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["error_count"] == 0
    assert result["rule_support_summary"]["startswith_replace_append_rules"] == 1


def test_if_equals_then_map_literal_passes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction1>PPOL</ediFunction1>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction3>PlaceOfLoad</ediFunction3>\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/ediFunction3",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "",
            "condition": 'if ediFunction1 = "PPOL" then map "PlaceOfLoad" to Target',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["error_count"] == 0
    assert result["rule_support_summary"]["if_equals_map_rules"] == 1


def test_if_equals_then_map_field_token_passes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction1>PETD-</ediFunction1>\n'
        '  <ediFunction2>20260515</ediFunction2>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction3>20260515</ediFunction3>\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/ediFunction3",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "",
            "condition": 'if ediFunction1 = "PETD-" then map ediFunction2 to Target',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["error_count"] == 0
    assert result["rule_support_summary"]["if_equals_map_rules"] == 1


def test_if_equals_then_map_mismatch_is_reported(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction1>PPOL</ediFunction1>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction3>BAD</ediFunction3>\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/ediFunction3",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "",
            "condition": 'if ediFunction1 = "PPOL" then map "PlaceOfLoad" to Target',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "FAIL"
    assert result["summary"]["grouped_error_counts"]["if_equals_mismatches"] == 1
    assert result["human_summary"]["issue_breakdown"][0]["issue"] == "Conditional mapping needs correction"


def test_if_elseif_chain_literal_clause_passes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction1>CN</ediFunction1>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction3>Consignee</ediFunction3>\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/ediFunction3",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "",
            "condition": (
                'if ediFunction1 = "CA" then map "Carrier" to Target '
                'elseif ediFunction1 = "CN" then map "Consignee" to Target '
                'else then map ediFunction1 to Target'
            ),
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["error_count"] == 0
    assert result["rule_support_summary"]["if_equals_chain_rules"] == 1


def test_if_elseif_chain_else_token_passes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction1>ZZ</ediFunction1>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction3>ZZ</ediFunction3>\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/ediFunction3",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "",
            "condition": (
                'if ediFunction1 = "CA" then map "Carrier" to Target '
                'elseif ediFunction1 = "CN" then map "Consignee" to Target '
                'else then map ediFunction1 to Target'
            ),
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["error_count"] == 0
    assert result["rule_support_summary"]["if_equals_chain_rules"] == 1


def test_if_elseif_chain_mismatch_is_reported(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction1>CA</ediFunction1>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction3>BAD</ediFunction3>\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/ediFunction3",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "",
            "condition": (
                'if ediFunction1 = "CA" then map "Carrier" to Target '
                'elseif ediFunction1 = "CN" then map "Consignee" to Target '
                'else then map ediFunction1 to Target'
            ),
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "FAIL"
    assert result["summary"]["grouped_error_counts"]["if_equals_mismatches"] == 1
    assert result["human_summary"]["issue_breakdown"][0]["issue"] == "Conditional mapping needs correction"


def test_if_expression_chain_and_or_passes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction1>L</ediFunction1>\n'
        '  <ediFunction2>Y</ediFunction2>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction3>MainCarriage</ediFunction3>\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/ediFunction3",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "",
            "condition": (
                'if (ediFunction1 = "L" and (ediFunction2 exists or ediFunction4 exists)) then map "MainCarriage" to Target '
                'elseif (ediFunction1 = "D" and (ediFunction2 exists or ediFunction3 exists)) then map "MainCarriage" to Target '
                'else then map "Other" to Target'
            ),
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["error_count"] == 0
    assert result["rule_support_summary"]["if_expression_chain_rules"] == 1


def test_if_expression_chain_else_token_passes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction1>Z</ediFunction1>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction3>Z</ediFunction3>\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/ediFunction3",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "",
            "condition": (
                'if (ediFunction1 = "L" and ediFunction2 exists) then map "MainCarriage" to Target '
                'elseif (ediFunction1 = "D" and ediFunction3 exists) then map "MainCarriage" to Target '
                'else then map ediFunction1 to Target'
            ),
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["error_count"] == 0
    assert result["rule_support_summary"]["if_expression_chain_rules"] == 1


def test_if_expression_chain_mismatch_is_reported(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction1>D</ediFunction1>\n'
        '  <ediFunction3>Y</ediFunction3>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction3>BAD</ediFunction3>\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/ediFunction3",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "",
            "condition": (
                'if (ediFunction1 = "L" and ediFunction2 exists) then map "MainCarriage" to Target '
                'elseif (ediFunction1 = "D" and (ediFunction2 exists or ediFunction3 exists)) then map "MainCarriage" to Target '
                'else then map "Other" to Target'
            ),
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "FAIL"


def test_if_expression_chain_with_angle_not_equals_passes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction1>CP</ediFunction1>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction3>Customer</ediFunction3>\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/ediFunction3",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "",
            "condition": (
                'if (ediFunction1 <> "LL" and ediFunction1 <> "SF") then map "Customer" to Target '
                'else then map "Other" to Target'
            ),
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["error_count"] == 0
    assert result["rule_support_summary"]["if_expression_chain_rules"] == 1


def test_if_expression_chain_with_angle_not_equals_else_branch(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction1>LL</ediFunction1>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction3>Other</ediFunction3>\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/ediFunction3",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "",
            "condition": (
                'if (ediFunction1 <> "LL" and ediFunction1 <> "SF") then map "Customer" to Target '
                'else then map "Other" to Target'
            ),
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["error_count"] == 0
    assert result["rule_support_summary"]["if_expression_chain_rules"] == 1


def test_hardcoded_date_format_token_passes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction1>anything</ediFunction1>\n'
        '  <ediFunction3>CCYYMMDD</ediFunction3>\n'
        '</status>\n'
    )
    _write_xml(src_xml, xml)
    _write_xml(tgt_xml, xml)

    rules = [
        {
            "target_xpath": "/status/ediFunction3",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "",
            "condition": 'Hardcode "CCYYMMDD" to Target',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["error_count"] == 0
    assert result["rule_support_summary"]["date_format_rules"] == 1


def test_dtm_date_time_format_token_passes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction1>20260515</ediFunction1>\n'
        '  <ediFunction2>1345</ediFunction2>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction3>CCYYMMDDHHMM</ediFunction3>\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/ediFunction3",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "",
            "condition": (
                'if ediFunction1 exists then map Target "CCYYMMDD" '
                'if ediFunction2 exists then Append to the Target as below based on the length of ediFunction2 '
                'if length(ediFunction2) = 4 then Append "HHMM" to Target '
                'else if length(ediFunction2) = 6 then Append "HHMMSS" to Target '
                'else if length(ediFunction2) = 7 then Append "HHMMSSD" to Target '
                'else if length(ediFunction2) = 8 then Append "HHMMSSDD" to Target'
            ),
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["error_count"] == 0
    assert result["rule_support_summary"]["date_format_rules"] == 1


def test_date_format_token_mismatch_is_reported(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction1>20260515</ediFunction1>\n'
        '  <ediFunction2>134500</ediFunction2>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction3>BAD</ediFunction3>\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/ediFunction3",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "",
            "condition": (
                'if ediFunction1 exists then map Target "CCYYMMDD" '
                'if ediFunction2 exists then Append to the Target as below based on the length of ediFunction2 '
                'if length(ediFunction2) = 4 then Append "HHMM" to Target '
                'else if length(ediFunction2) = 6 then Append "HHMMSS" to Target'
            ),
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "FAIL"
    assert result["summary"]["grouped_error_counts"]["date_format_mismatches"] == 1
    assert result["human_summary"]["issue_breakdown"][0]["issue"] == "Date or time format token needs correction"


def test_top_critical_errors_are_deterministic_and_human_readable(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction1>STATUS</ediFunction1>\n'
        '  <ediFunction2>OK</ediFunction2>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction2>BAD</ediFunction2>\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/ediFunction2",
            "source_xpath": "/status/ediFunction2",
            "cardinality": "1..1",
            "condition": 'If Source !="" then map Source to Target',
            "note": "",
        },
        {
            "target_xpath": "/status/ediFunction1",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "1..1",
            "condition": 'If Source !="" then map Source to Target',
            "note": "",
        },
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "FAIL"
    # Source-target missing has higher severity and should be listed first.
    assert "Row 2" in result["summary"]["top_critical_errors"][0]
    assert "Source exists but target is missing" in result["summary"]["top_critical_errors"][0]
    # Cardinality is next highest severity before value mismatch.
    assert "Row 2" in result["summary"]["top_critical_errors"][1]
    assert "Cardinality violation" in result["summary"]["top_critical_errors"][1]
    assert "Row 1" in result["summary"]["top_critical_errors"][2]
    assert "Value mismatch" in result["summary"]["top_critical_errors"][2]
    assert result["human_summary"]["what_to_fix_first"][0].startswith("Add the missing target field")
    assert "Target:" not in result["human_summary"]["what_to_fix_first"][0]
    assert "Row " not in result["human_summary"]["what_to_fix_first"][0]


def test_field_concat_two_fields_passes(tmp_path, monkeypatch):
    """Concatenate DTM02 + DTM03 then map to Target — values match."""
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns">\n'
        '  <DTM02>20260515</DTM02>\n'
        '  <DTM03>1430</DTM03>\n'
        '</msg>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns">\n'
        '  <departureDateTime>202605151430</departureDateTime>\n'
        '</msg>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/msg/departureDateTime",
            "source_xpath": "/msg/DTM02",
            "cardinality": "",
            "condition": "Concatenate DTM02 + DTM03 then map to Target",
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["rule_support_summary"]["field_concat_rules"] == 1
    assert result["summary"]["grouped_error_counts"].get("field_concat_mismatches", 0) == 0


def test_field_concat_literal_prefix_passes(tmp_path, monkeypatch):
    """Concatenate "20" + /msg/year + /msg/rest then map to Target — literal + fields."""
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns">\n'
        '  <year>26</year>\n'
        '  <rest>0515</rest>\n'
        '</msg>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns">\n'
        '  <fullDate>20260515</fullDate>\n'
        '</msg>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/msg/fullDate",
            "source_xpath": "/msg/year",
            "cardinality": "",
            "condition": 'Concatenate "20" + year + rest then map to Target',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["rule_support_summary"]["field_concat_rules"] == 1
    assert result["summary"]["grouped_error_counts"].get("field_concat_mismatches", 0) == 0


def test_field_concat_mismatch_is_reported(tmp_path, monkeypatch):
    """Concatenate DTM02 + DTM03 — target has wrong value, mismatch is reported."""
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns">\n'
        '  <DTM02>20260515</DTM02>\n'
        '  <DTM03>1430</DTM03>\n'
        '</msg>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns">\n'
        '  <departureDateTime>WRONG</departureDateTime>\n'
        '</msg>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/msg/departureDateTime",
            "source_xpath": "/msg/DTM02",
            "cardinality": "",
            "condition": "Concatenate DTM02 + DTM03 then map to Target",
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "FAIL"
    assert result["summary"]["grouped_error_counts"]["field_concat_mismatches"] == 1
    fc_issue = next(
        (item for item in result["human_summary"]["issue_breakdown"]
         if "Concatenated" in item["issue"]),
        None,
    )
    assert fc_issue is not None
    assert fc_issue["count"] == 1


# ---------------------------------------------------------------------------
# Direct Map slice
# ---------------------------------------------------------------------------

def test_direct_map_plain_passes(tmp_path, monkeypatch):
    """'Direct Map' condition: source value must equal target value."""
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><bookingRef>BK123</bookingRef></msg>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><bookingId>BK123</bookingId></msg>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/msg/bookingId",
            "source_xpath": "/msg/bookingRef",
            "cardinality": "",
            "condition": "Direct Map",
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["rule_support_summary"]["direct_map_rules"] == 1
    assert result["summary"]["grouped_error_counts"].get("value_mismatches", 0) == 0


def test_direct_map_with_inline_filter_passes(tmp_path, monkeypatch):
    """'Direct Map | N901 = \"ZZZ\"' condition is recognised and handled."""
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><refNum>REF42</refNum></msg>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><refOut>REF42</refOut></msg>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/msg/refOut",
            "source_xpath": "/msg/refNum",
            "cardinality": "",
            "condition": 'Direct Map | /msg/refNum != ""',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["rule_support_summary"]["direct_map_rules"] == 1


def test_direct_map_mismatch_is_reported(tmp_path, monkeypatch):
    """'Direct Map' condition: value mismatch is caught by direct-map enforcement."""
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><bookingRef>BK999</bookingRef></msg>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><bookingId>WRONG</bookingId></msg>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/msg/bookingId",
            "source_xpath": "/msg/bookingRef",
            "cardinality": "",
            "condition": "Direct Map",
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "FAIL"
    assert result["rule_support_summary"]["direct_map_rules"] == 1
    assert result["summary"]["grouped_error_counts"]["value_mismatches"] == 1


# ---------------------------------------------------------------------------
# startsWith + substring extraction slice
# ---------------------------------------------------------------------------

def test_startswith_substring_single_field_passes(tmp_path, monkeypatch):
    """startsWith + skip N chars from single field — value matches."""
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><H201>GEN-CARGO123</H201></msg>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><CargoRef>CARGO123</CargoRef></msg>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/msg/CargoRef",
            "source_xpath": "/msg/H201",
            "cardinality": "",
            "condition": (
                'if H201 startsWith "GEN-" | '
                "Get the substring after the first 4 characters from the left from H201 and map to Target"
            ),
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["rule_support_summary"]["startswith_substring_rules"] == 1
    assert result["summary"]["grouped_error_counts"].get("startswith_substring_mismatches", 0) == 0


def test_startswith_substring_with_sibling_passes(tmp_path, monkeypatch):
    """startsWith + skip N chars + append sibling field — concatenated value matches."""
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns">\n'
        '  <H201>GEN-CARGO</H201>\n'
        '  <H202>123</H202>\n'
        '</msg>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><CargoRef>CARGO123</CargoRef></msg>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/msg/CargoRef",
            "source_xpath": "/msg/H201",
            "cardinality": "",
            "condition": (
                'if H201 startsWith "GEN-" | '
                "Get the substring after the first 4 characters from the left from H201 + H202 and map to Target"
            ),
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["rule_support_summary"]["startswith_substring_rules"] == 1
    assert result["summary"]["grouped_error_counts"].get("startswith_substring_mismatches", 0) == 0


def test_startswith_substring_mismatch_is_reported(tmp_path, monkeypatch):
    """startsWith + skip N chars — wrong target value is caught."""
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><H201>GEN-CARGO123</H201></msg>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><CargoRef>WRONG</CargoRef></msg>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/msg/CargoRef",
            "source_xpath": "/msg/H201",
            "cardinality": "",
            "condition": (
                'if H201 startsWith "GEN-" | '
                "Get the substring after the first 4 characters from the left from H201 and map to Target"
            ),
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "FAIL"
    assert result["rule_support_summary"]["startswith_substring_rules"] == 1
    assert result["summary"]["grouped_error_counts"]["startswith_substring_mismatches"] == 1
    sub_issue = next(
        (item for item in result["human_summary"]["issue_breakdown"]
         if "substring" in item["issue"].lower()),
        None,
    )
    assert sub_issue is not None
    assert sub_issue["count"] == 1


# ---------------------------------------------------------------------------
# Character-offset extraction slice
# ---------------------------------------------------------------------------

def test_char_offset_left_chars_passes(tmp_path, monkeypatch):
    """Map left N characters — value matches."""
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><data>ABCDE-12345</data></msg>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><prefix>ABCDE</prefix></msg>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/msg/prefix",
            "source_xpath": "/msg/data",
            "cardinality": "",
            "condition": "Map left 5 Characters to Target",
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["rule_support_summary"]["char_offset_rules"] == 1
    assert result["summary"]["grouped_error_counts"].get("char_offset_mismatches", 0) == 0


def test_char_offset_next_chars_from_position_passes(tmp_path, monkeypatch):
    """Map next N characters starting from position M — value matches."""
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><data>ABCDE-12345</data></msg>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><middle>12345</middle></msg>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/msg/middle",
            "source_xpath": "/msg/data",
            "cardinality": "",
            "condition": "Map next 5 characters to Target (starting from 7th chr)",
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["rule_support_summary"]["char_offset_rules"] == 1
    assert result["summary"]["grouped_error_counts"].get("char_offset_mismatches", 0) == 0


def test_char_offset_mismatch_is_reported(tmp_path, monkeypatch):
    """Map left N characters — wrong target value is caught."""
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><data>ABCDE-12345</data></msg>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><prefix>WRONG</prefix></msg>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/msg/prefix",
            "source_xpath": "/msg/data",
            "cardinality": "",
            "condition": "Map left 5 Characters to Target",
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "FAIL"
    assert result["rule_support_summary"]["char_offset_rules"] == 1
    assert result["summary"]["grouped_error_counts"]["char_offset_mismatches"] == 1
    offset_issue = next(
        (item for item in result["human_summary"]["issue_breakdown"]
         if "Character-offset" in item["issue"]),
        None,
    )
    assert offset_issue is not None
    assert offset_issue["count"] == 1


# ---------------------------------------------------------------------------
# Relaxed startsWith replace slice
# ---------------------------------------------------------------------------

def test_startswith_replace_relaxed_passes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><H201>GEN-CARGO123</H201></msg>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><CargoRef>CARGO123</CargoRef></msg>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/msg/CargoRef",
            "source_xpath": "/msg/H201",
            "cardinality": "",
            "condition": 'if H201 starts with "GEN-" replace "GEN-" with "" map Target',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["rule_support_summary"]["startswith_replace_rules"] == 1
    assert result["summary"]["grouped_error_counts"].get("startswith_transform_mismatches", 0) == 0


def test_startswith_replace_append_relaxed_passes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns">\n'
        '  <H201>GEN-CARGO</H201>\n'
        '  <H202>123</H202>\n'
        '</msg>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><CargoRef>CARGO123</CargoRef></msg>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/msg/CargoRef",
            "source_xpath": "/msg/H201",
            "cardinality": "",
            "condition": 'if H201 starts with "GEN-" replace "GEN-" with "" append with H202 map Target',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["rule_support_summary"]["startswith_replace_append_rules"] == 1
    assert result["summary"]["grouped_error_counts"].get("startswith_append_mismatches", 0) == 0


def test_startswith_replace_relaxed_mismatch_is_reported(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><H201>GEN-CARGO123</H201></msg>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><CargoRef>WRONG</CargoRef></msg>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/msg/CargoRef",
            "source_xpath": "/msg/H201",
            "cardinality": "",
            "condition": 'if H201 starts with "GEN-" replace "GEN-" with "" map Target',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "FAIL"
    assert result["rule_support_summary"]["startswith_replace_rules"] == 1
    assert result["summary"]["grouped_error_counts"]["startswith_transform_mismatches"] == 1


# ---------------------------------------------------------------------------
# Simplified character-offset slice
# ---------------------------------------------------------------------------

def test_char_offset_next_chars_without_position_passes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><data>ABCDE-12345</data></msg>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><prefix>ABCDE</prefix></msg>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/msg/prefix",
            "source_xpath": "/msg/data",
            "cardinality": "",
            "condition": "Map next 5 characters to Target",
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["rule_support_summary"]["char_offset_rules"] == 1
    assert result["summary"]["grouped_error_counts"].get("char_offset_mismatches", 0) == 0


def test_char_offset_next_chars_without_position_case_variant_passes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><data>ABCDE-12345</data></msg>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><prefix>ABCD</prefix></msg>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/msg/prefix",
            "source_xpath": "/msg/data",
            "cardinality": "",
            "condition": "Map next 4 chars to Target",
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["rule_support_summary"]["char_offset_rules"] == 1
    assert result["summary"]["grouped_error_counts"].get("char_offset_mismatches", 0) == 0


def test_char_offset_next_chars_without_position_mismatch_is_reported(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><data>ABCDE-12345</data></msg>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><prefix>WRONG</prefix></msg>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/msg/prefix",
            "source_xpath": "/msg/data",
            "cardinality": "",
            "condition": "Map next 5 characters to Target",
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "FAIL"
    assert result["rule_support_summary"]["char_offset_rules"] == 1
    assert result["summary"]["grouped_error_counts"]["char_offset_mismatches"] == 1


# ---------------------------------------------------------------------------
# Compact if-equals mapping slice
# ---------------------------------------------------------------------------

def test_source_translation_without_to_target_passes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><code>02</code></msg>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><flag>true</flag></msg>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/msg/flag",
            "source_xpath": "/msg/code",
            "cardinality": "",
            "condition": 'If Source="02" map Target "true"',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["rule_support_summary"]["translated_condition_rules"] == 1
    assert result["summary"]["grouped_error_counts"].get("translated_value_mismatches", 0) == 0


def test_if_equals_without_then_and_to_target_passes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><K101>PPOL</K101></msg>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><LocationType>PlaceOfLoad</LocationType></msg>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/msg/LocationType",
            "source_xpath": "/msg/K101",
            "cardinality": "",
            "condition": 'if K101="PPOL" map "PlaceOfLoad"',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["rule_support_summary"]["if_equals_map_rules"] == 1
    assert result["summary"]["grouped_error_counts"].get("if_equals_mismatches", 0) == 0


def test_if_equals_without_then_and_to_target_mismatch_is_reported(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><K101>PPOL</K101></msg>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><LocationType>WRONG</LocationType></msg>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/msg/LocationType",
            "source_xpath": "/msg/K101",
            "cardinality": "",
            "condition": 'if K101="PPOL" map "PlaceOfLoad"',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "FAIL"
    assert result["rule_support_summary"]["if_equals_map_rules"] == 1
    assert result["summary"]["grouped_error_counts"]["if_equals_mismatches"] == 1


# ---------------------------------------------------------------------------
# Length-based mapping slice
# ---------------------------------------------------------------------------

def test_length_based_map_then_branch_passes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><name>ABCD</name></msg>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><shortName>ABCD</shortName></msg>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/msg/shortName",
            "source_xpath": "/msg/name",
            "cardinality": "",
            "condition": "if length(name) <= 5 then map name to Target | else | map name left (name,5) to Target",
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["rule_support_summary"]["length_based_rules"] == 1
    assert result["summary"]["grouped_error_counts"].get("length_based_mismatches", 0) == 0


def test_length_based_map_else_left_branch_passes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><name>ABCDEFGHI</name></msg>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><shortName>ABCDE</shortName></msg>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/msg/shortName",
            "source_xpath": "/msg/name",
            "cardinality": "",
            "condition": "if length(name) <= 5 then map name to Target | else | map name left (name,5) to Target",
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["rule_support_summary"]["length_based_rules"] == 1
    assert result["summary"]["grouped_error_counts"].get("length_based_mismatches", 0) == 0


def test_length_based_map_mismatch_is_reported(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><name>ABCDEFGHI</name></msg>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><shortName>WRONG</shortName></msg>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/msg/shortName",
            "source_xpath": "/msg/name",
            "cardinality": "",
            "condition": "if length(name) <= 5 then map name to Target | else | map name left (name,5) to Target",
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "FAIL"
    assert result["rule_support_summary"]["length_based_rules"] == 1
    assert result["summary"]["grouped_error_counts"]["length_based_mismatches"] == 1


# ---------------------------------------------------------------------------
# Outer-guarded length mapping slice
# ---------------------------------------------------------------------------

def test_length_based_with_outer_guard_passes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns">\n'
        '  <K101>PETD-</K101>\n'
        '  <K102>20260515</K102>\n'
        '</msg>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><format>CCYYMMDD</format></msg>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/msg/format",
            "source_xpath": "/msg/K101",
            "cardinality": "",
            "condition": (
                'if K101 = "PETD-" then map as below '
                'if length (K102) = 8 then map "CCYYMMDD" to Target '
                'if length (K102) = 12 then "CCYYMMDDHHMM" to Target'
            ),
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["rule_support_summary"]["date_format_rules"] == 1
    assert result["summary"]["grouped_error_counts"].get("date_format_mismatches", 0) == 0


def test_length_based_outer_guard_not_met_skips_enforcement(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns">\n'
        '  <K101>OTHER</K101>\n'
        '  <K102>202605151230</K102>\n'
        '</msg>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><format>WRONG-BUT-IGNORED</format></msg>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/msg/format",
            "source_xpath": "/msg/K101",
            "cardinality": "",
            "condition": (
                'if K101 = "PETD-" then map as below '
                'if length (K102) = 8 then map "CCYYMMDD" to Target '
                'if length (K102) = 12 then "CCYYMMDDHHMM" to Target'
            ),
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["rule_support_summary"]["date_format_rules"] == 1
    assert result["summary"]["grouped_error_counts"].get("date_format_mismatches", 0) == 0


def test_length_based_with_outer_guard_mismatch_is_reported(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns">\n'
        '  <K101>PETD-</K101>\n'
        '  <K102>202605151230</K102>\n'
        '</msg>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><format>WRONG</format></msg>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/msg/format",
            "source_xpath": "/msg/K101",
            "cardinality": "",
            "condition": (
                'if K101 = "PETD-" then map as below '
                'if length (K102) = 8 then map "CCYYMMDD" to Target '
                'if length (K102) = 12 then "CCYYMMDDHHMM" to Target'
            ),
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "FAIL"
    assert result["rule_support_summary"]["date_format_rules"] == 1
    assert result["summary"]["grouped_error_counts"]["date_format_mismatches"] == 1


# ---------------------------------------------------------------------------
# Loose conversion-chain syntax slice
# ---------------------------------------------------------------------------

def test_if_expression_chain_without_then_and_else_if_passes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns">\n'
        '  <kind>L</kind>\n'
        '  <marker>Y</marker>\n'
        '</msg>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><leg>MainCarriage</leg></msg>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/msg/leg",
            "source_xpath": "/msg/kind",
            "cardinality": "",
            "condition": (
                'Conversion: if (kind = "L" and marker exists) map "MainCarriage" toTarget '
                'else if marker exists map "Secondary" to Target endIf'
            ),
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["rule_support_summary"]["if_expression_chain_rules"] == 1
    assert result["summary"]["grouped_error_counts"].get("if_equals_mismatches", 0) == 0


def test_if_expression_chain_else_if_branch_passes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns">\n'
        '  <kind>X</kind>\n'
        '  <marker>Y</marker>\n'
        '</msg>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><leg>Secondary</leg></msg>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/msg/leg",
            "source_xpath": "/msg/kind",
            "cardinality": "",
            "condition": (
                'Conversion: if (kind = "L" and marker exists) map "MainCarriage" toTarget '
                'else if marker exists map "Secondary" to Target endIf'
            ),
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["rule_support_summary"]["if_expression_chain_rules"] == 1
    assert result["summary"]["grouped_error_counts"].get("if_equals_mismatches", 0) == 0


def test_if_expression_chain_without_then_mismatch_is_reported(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns">\n'
        '  <kind>L</kind>\n'
        '  <marker>Y</marker>\n'
        '</msg>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><leg>WRONG</leg></msg>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/msg/leg",
            "source_xpath": "/msg/kind",
            "cardinality": "",
            "condition": (
                'Conversion: if (kind = "L" and marker exists) map "MainCarriage" toTarget '
                'else if marker exists map "Secondary" to Target endIf'
            ),
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "FAIL"
    assert result["rule_support_summary"]["if_expression_chain_rules"] == 1
    assert result["summary"]["grouped_error_counts"]["if_equals_mismatches"] == 1


# ---------------------------------------------------------------------------
# Sequential endIf conversion chain slice
# ---------------------------------------------------------------------------

def test_sequential_endif_chain_first_clause_passes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns">\n'
        '  <K101>AMS</K101>\n'
        '</msg>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><category>Customer</category></msg>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/msg/category",
            "source_xpath": "/msg/K101",
            "cardinality": "",
            "condition": (
                'if K101 = "AMS" then map "Customer" to Target endIf '
                'if K101 startsWith "NVO-" then map "Carrier_NVO" toTarget endIf '
                'if K101 startsWith "NVO" then map "Carrier_NVO" to Target endIf'
            ),
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["rule_support_summary"]["if_expression_chain_rules"] == 1
    assert result["summary"]["grouped_error_counts"].get("if_equals_mismatches", 0) == 0


def test_sequential_endif_chain_later_clause_passes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns">\n'
        '  <K101>NVO-123</K101>\n'
        '</msg>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><category>Carrier_NVO</category></msg>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/msg/category",
            "source_xpath": "/msg/K101",
            "cardinality": "",
            "condition": (
                'if K101 = "AMS" then map "Customer" to Target endIf '
                'if K101 startsWith "NVO-" then map "Carrier_NVO" toTarget endIf '
                'if K101 startsWith "NVO" then map "Carrier_NVO" to Target endIf'
            ),
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["rule_support_summary"]["if_expression_chain_rules"] == 1
    assert result["summary"]["grouped_error_counts"].get("if_equals_mismatches", 0) == 0


def test_sequential_endif_chain_mismatch_is_reported(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns">\n'
        '  <K101>NVO-123</K101>\n'
        '</msg>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><category>WRONG</category></msg>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/msg/category",
            "source_xpath": "/msg/K101",
            "cardinality": "",
            "condition": (
                'if K101 = "AMS" then map "Customer" to Target endIf '
                'if K101 startsWith "NVO-" then map "Carrier_NVO" toTarget endIf '
                'if K101 startsWith "NVO" then map "Carrier_NVO" to Target endIf'
            ),
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "FAIL"
    assert result["rule_support_summary"]["if_expression_chain_rules"] == 1
    assert result["summary"]["grouped_error_counts"]["if_equals_mismatches"] == 1


def test_if_source_not_empty_map_to_target_without_then_passes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction1>STATUS</ediFunction1>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction1>STATUS</ediFunction1>\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/ediFunction1",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "",
            "condition": 'If Source !="" map to Target',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["error_count"] == 0
    assert result["rule_support_summary"]["unsupported_rules"] == 0


def test_if_expression_chain_move_alias_passes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction1>L</ediFunction1>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction3>MainCarriage</ediFunction3>\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/ediFunction3",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "",
            "condition": (
                'if (ediFunction1 = "L") then move "MainCarriage" to Target '
                'else then move "Other" to Target'
            ),
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["error_count"] == 0
    assert result["rule_support_summary"]["if_expression_chain_rules"] == 1


def test_char_offset_map_substring_source_passes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction1>ABCDEFGHIJ</ediFunction1>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status" type="shipment-status">\n'
        '  <ediFunction3>ABCDE</ediFunction3>\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/ediFunction3",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "",
            "condition": 'Map substring(source, 1, 5) to Target',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["error_count"] == 0
    assert result["rule_support_summary"]["char_offset_rules"] == 1


def test_if_equals_get_substring_line_broken_passes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns">\n'
        '  <H201>IHL-ABC123</H201>\n'
        '</msg>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><code>ABC123</code></msg>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/msg/code",
            "source_xpath": "/msg/H201",
            "cardinality": "",
            "condition": (
                'if H201 = "IHL"\n'
                'Get the substring after the first 4 characters from the left from H201 and map to Target'
            ),
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["error_count"] == 0
    assert result["rule_support_summary"]["if_equals_get_substring_rules"] == 1


def test_if_in_list_substring_source_passes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns">\n'
        '  <N101>SF</N101>\n'
        '  <refNum>ABCDEFGHIJ</refNum>\n'
        '</msg>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><shortRef>ABCDE</shortRef></msg>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/msg/shortRef",
            "source_xpath": "/msg/refNum",
            "cardinality": "",
            "condition": 'If N101 = "LL" | "SF" | "ST" then Direct Map Map substring(source, 1,5) to Target',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["error_count"] == 0
    assert result["rule_support_summary"]["if_in_list_substring_rules"] == 1


def test_if_in_list_substring_source_mismatch_reported(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns">\n'
        '  <N101>SF</N101>\n'
        '  <refNum>ABCDEFGHIJ</refNum>\n'
        '</msg>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><shortRef>ZZZZZ</shortRef></msg>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/msg/shortRef",
            "source_xpath": "/msg/refNum",
            "cardinality": "",
            "condition": 'If N101 = "LL" | "SF" | "ST" then Direct Map Map substring(source, 1,5) to Target',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "FAIL"
    assert result["summary"]["grouped_error_counts"]["char_offset_mismatches"] >= 1
    assert any("In-list substring mismatch" in item for item in result["errors"])


def test_source_substring_date_part_ccyy_passes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status">\n'
        '  <dateTime>202606181230</dateTime>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status">\n'
        '  <year>2026</year>\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/year",
            "source_xpath": "/status/dateTime",
            "cardinality": "",
            "condition": 'if Source !="" then substring the CCYY then map to Target',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["error_count"] == 0
    assert result["rule_support_summary"]["date_part_substring_rules"] == 1


def test_source_substring_date_part_dd_passes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status">\n'
        '  <dateTime>202606181230</dateTime>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status">\n'
        '  <day>18</day>\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/day",
            "source_xpath": "/status/dateTime",
            "cardinality": "",
            "condition": 'if Source !="" then substring the DD then map to Target',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["error_count"] == 0
    assert result["rule_support_summary"]["date_part_substring_rules"] == 1


def test_source_substring_date_part_mm_month_passes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status">\n'
        '  <dateTime>202606181230</dateTime>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status">\n'
        '  <month>06</month>\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/month",
            "source_xpath": "/status/dateTime",
            "cardinality": "",
            "condition": 'if Source !="" then substring the MM then map to Target',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["error_count"] == 0
    assert result["rule_support_summary"]["date_part_substring_rules"] == 1


def test_source_substring_date_part_mm_minute_passes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status">\n'
        '  <dateTime>202606181230</dateTime>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status">\n'
        '  <minute>30</minute>\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/minute",
            "source_xpath": "/status/dateTime",
            "cardinality": "",
            "condition": 'if Source !="" then substring the MM then map to Target',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["error_count"] == 0
    assert result["rule_support_summary"]["date_part_substring_rules"] == 1


def test_if_source_map_without_then_with_trailing_text_passes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status">\n'
        '  <ediFunction1>ABC123</ediFunction1>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status">\n'
        '  <ediFunction1>ABC123</ediFunction1>\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/ediFunction1",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "",
            "condition": 'If Source !="" map to Target Convert to cXML date time format',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["error_count"] == 0
    assert result["rule_support_summary"]["unsupported_rules"] == 0


def test_conversion_if_chain_with_outer_exists_passes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns">\n'
        '  <L004>1</L004>\n'
        '  <L011>K</L011>\n'
        '</msg>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><unit>KGM</unit></msg>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/msg/unit",
            "source_xpath": "/msg/L011",
            "cardinality": "",
            "condition": (
                "if L004 exists then Conversion: "
                "if L011 = 'K' then map 'KGM' to Target "
                "if L011 = 'L' then map 'LBR' to Target"
            ),
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["error_count"] == 0
    assert result["rule_support_summary"]["conversion_if_chain_rules"] == 1


def test_conversion_if_chain_source_parentheses_passes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns">\n'
        '  <H201>GAS</H201>\n'
        '</msg>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><kind>Gas</kind></msg>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/msg/kind",
            "source_xpath": "/msg/H201",
            "cardinality": "",
            "condition": (
                "Conversion: "
                "If source (H201)= \"GAS\" then map Target as \"Gas\" "
                "If source (H201)= \"LQD\" then map Target as \"Liquid\""
            ),
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["error_count"] == 0
    assert result["rule_support_summary"]["conversion_if_chain_rules"] == 1


def test_instruction_only_no_mapping_is_parsed_only(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status">\n'
        '  <ediFunction1>STATUS</ediFunction1>\n'
        '</status>\n'
    )
    _write_xml(src_xml, xml)
    _write_xml(tgt_xml, xml)

    rules = [
        {
            "target_xpath": "/status/ediFunction1",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "",
            "condition": "No mapping",
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["rule_support_summary"]["unsupported_rules"] == 0
    assert result["rule_support_summary"]["instruction_only_rules"] == 1
    assert len(result["skipped_rules"]) == 0


def test_directmap_variant_is_recognized(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status">\n'
        '  <ediFunction1>STATUS</ediFunction1>\n'
        '</status>\n'
    )
    _write_xml(src_xml, xml)
    _write_xml(tgt_xml, xml)

    rules = [
        {
            "target_xpath": "/status/ediFunction1",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "",
            "condition": "DirectMap",
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["rule_support_summary"]["unsupported_rules"] == 0


def test_multi_condition_map_to_target_uses_source_value(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status">\n'
        '  <bespokeCode>custXref1</bespokeCode>\n'
        '  <ediFunction1>REF123</ediFunction1>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status">\n'
        '  <ediFunction2>REF123</ediFunction2>\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/ediFunction2",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "",
            "condition": 'If bespokeCode = "custXref1" and Source !="" then map to Target',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["error_count"] == 0
    assert result["rule_support_summary"]["multi_condition_and_rules"] == 1


def test_if_equals_map_to_target_uses_source_value(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status">\n'
        '  <N101>SH</N101>\n'
        '  <ediFunction1>VAL001</ediFunction1>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status">\n'
        '  <ediFunction2>VAL001</ediFunction2>\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/ediFunction2",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "",
            "condition": 'If N101="SH" then map to Target',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["error_count"] == 0
    assert result["rule_support_summary"]["if_equals_map_rules"] == 1


def test_hardcode_to_literal_variant_passes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status">\n'
        '  <ediFunction1>anything</ediFunction1>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status">\n'
        '  <ediFunction2>Not Available</ediFunction2>\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/ediFunction2",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "",
            "condition": 'Hardcode to "Not Available"',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["error_count"] == 0
    assert result["rule_support_summary"]["hardcode_literal_rules"] == 1


def test_expression_map_to_target_shorthand_passes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status">\n'
        '  <ediCustomerDepartment>ABC</ediCustomerDepartment>\n'
        '  <ediFunction1>ABC</ediFunction1>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status">\n'
        '  <ediFunction2>ABC</ediFunction2>\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/ediFunction2",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "",
            "condition": 'if ediCustomerDepartment !="" map to Target',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["error_count"] == 0
    assert result["rule_support_summary"]["expression_map_to_target_rules"] == 1


def test_hardcoded_as_literal_variant_passes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status">\n'
        '  <ediFunction1>anything</ediFunction1>\n'
        '</status>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status">\n'
        '  <ediFunction2>SYSTEM_ID</ediFunction2>\n'
        '</status>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/status/ediFunction2",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "",
            "condition": 'Hardcoded as "SYSTEM_ID"',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["error_count"] == 0
    assert result["rule_support_summary"]["hardcode_literal_rules"] == 1


def test_token_exists_map_literal_to_target_passes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns">\n'
        '  <N722>YES</N722>\n'
        '</msg>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><code>1</code></msg>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/msg/code",
            "source_xpath": "/msg/N722",
            "cardinality": "",
            "condition": 'if N722 exists then map "1" to Target',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["error_count"] == 0
    assert result["rule_support_summary"]["token_exists_condition_rules"] == 1


def test_token_exists_map_target_as_literal_passes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns">\n'
        '  <N722>YES</N722>\n'
        '</msg>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><uom>ISO</uom></msg>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/msg/uom",
            "source_xpath": "/msg/N722",
            "cardinality": "",
            "condition": 'If N722 exists then map Target as "ISO"',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["error_count"] == 0
    assert result["rule_support_summary"]["token_exists_condition_rules"] == 1


def test_conversion_if_chain_single_clause_with_else_and_outer_exists_passes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns">\n'
        '  <N702>Y</N702>\n'
        '  <N701>ABC</N701>\n'
        '</msg>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><flag>true</flag></msg>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/msg/flag",
            "source_xpath": "/msg/N701",
            "cardinality": "",
            "condition": (
                'If N702 exists then Conversion: '
                'If N701 <> "" then map Target as "true" '
                'else mapTarget as "false"'
            ),
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["error_count"] == 0
    assert result["rule_support_summary"]["conversion_if_chain_rules"] == 1


def test_startswith_constant_target_as_literal_passes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns">\n'
        '  <W0906>ECA-123</W0906>\n'
        '</msg>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><haz>true</haz></msg>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/msg/haz",
            "source_xpath": "/msg/W0906",
            "cardinality": "",
            "condition": 'if source startsWith "ECA" then map Target as "true"',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["error_count"] == 0
    assert result["rule_support_summary"]["startswith_constant_rules"] == 1


def test_startswith_constant_typo_and_target_to_literal_passes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns">\n'
        '  <W0906>ICT-555</W0906>\n'
        '</msg>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><flag>true</flag></msg>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/msg/flag",
            "source_xpath": "/msg/W0906",
            "cardinality": "",
            "condition": 'If source strats with "ICT" then map target to "true"',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["error_count"] == 0
    assert result["rule_support_summary"]["startswith_constant_rules"] == 1



def test_if_exists_else_map_simple_tokens_passes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns">\n'
        '  <A>YES</A>\n'
        '  <B>T</B>\n'
        '  <C>F</C>\n'
        '</msg>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><out>T</out></msg>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/msg/out",
            "source_xpath": "/msg/A",
            "cardinality": "",
            "condition": 'If A then map B to Target else map C to Target',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["error_count"] == 0
    assert result["rule_support_summary"]["if_exists_else_map_rules"] == 1



def test_if_replace_map_to_target_passes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns">\n'
        '  <Source>TmValue</Source>\n'
        '</msg>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><out>IcValue</out></msg>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/msg/out",
            "source_xpath": "/msg/Source",
            "cardinality": "",
            "condition": 'If Source != "" then replace "Tm" with "Ic" and map to Target',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["error_count"] == 0
    assert result["rule_support_summary"]["if_replace_map_rules"] == 1


def test_stage85_semantic_present_variant_passes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns">\n'
        '  <N722>YES</N722>\n'
        '</msg>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><uom>ISO</uom></msg>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/msg/uom",
            "source_xpath": "/msg/N722",
            "cardinality": "",
            "condition": 'If N722 is present then map Target as "ISO"',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["error_count"] == 0
    assert result["rule_support_summary"]["token_exists_condition_rules"] == 1
    assert result["rule_support_summary"]["stage_8_5_canonicalized_rules"] >= 1


def test_stage85_semantic_begins_with_variant_passes(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns">\n'
        '  <W0906>ECA-123</W0906>\n'
        '</msg>\n'
    )
    tgt = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<msg xmlns="http://example.com/ns"><haz>true</haz></msg>\n'
    )
    _write_xml(src_xml, src)
    _write_xml(tgt_xml, tgt)

    rules = [
        {
            "target_xpath": "/msg/haz",
            "source_xpath": "/msg/W0906",
            "cardinality": "",
            "condition": 'If source begins with "ECA" then map "true" into Target',
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["summary"]["status"] == "PASS"
    assert result["error_count"] == 0
    assert result["rule_support_summary"]["startswith_constant_rules"] == 1
    assert result["rule_support_summary"]["stage_8_5_canonicalized_rules"] >= 1

