import json

import core.validate as validate_module


def _write_xml(path, body: str) -> None:
    path.write_text(body, encoding="utf-8")


def _patch_rules(monkeypatch, rules):
    monkeypatch.setattr(validate_module, "read_mapping_table", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(validate_module, "extract_rules", lambda _df: rules)


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
    assert payload["summary"]["error_count"] == 0
    assert payload["summary"]["top_critical_errors"] == []
    assert payload["summary"]["grouped_error_counts"]["source_target_missing"] == 0
    assert payload["human_summary"]["headline"] == "No mapping issues found"
    assert payload["human_summary"]["what_to_fix_first"] == []
    assert payload["valid"] is True
    assert payload["validation_mode"] == "strict"
    assert payload["error_count"] == 0
    assert isinstance(payload["warnings"], list)
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
    assert payload["summary"]["error_count"] > 0
    assert payload["summary"]["top_critical_errors"]
    assert payload["summary"]["grouped_error_counts"]["source_target_missing"] > 0
    assert payload["human_summary"]["what_to_fix_first"]
    assert payload["human_summary"]["what_to_fix_first"][0].startswith("Create target")
    assert "Target:" not in payload["human_summary"]["what_to_fix_first"][0]
    assert "Row " not in payload["human_summary"]["what_to_fix_first"][0]
    assert payload["human_summary"]["issue_breakdown"]
    assert payload["valid"] is False
    assert payload["strict_would_fail"] is True
    assert payload["error_count"] > 0
    assert payload["errors"]


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
    assert result["human_summary"]["what_to_fix_first"][0].startswith("Create target")
    assert "Target:" not in result["human_summary"]["what_to_fix_first"][0]
    assert "Row " not in result["human_summary"]["what_to_fix_first"][0]