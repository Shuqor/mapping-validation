import json
from pathlib import Path

import core.validate as validate_module


FIXTURES_PATH = Path(__file__).resolve().parent / "fixtures" / "structure_contract_fixtures.json"


def _patch_rules(monkeypatch, rules):
    monkeypatch.setattr(validate_module, "read_mapping_table", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(validate_module, "extract_rules", lambda _df: rules)
    monkeypatch.setattr(
        validate_module,
        "get_parser_diagnostics",
        lambda _df: {
            "status": "clean",
            "confidence": "high",
            "warnings": [],
            "sheet_name": "Mapping",
            "header_row": 0,
            "layout": rules[0].get("layout", "xpath_target") if rules else "xpath_target",
            "rule_count": len(rules),
            "extraction": {"ambiguities": []},
        },
    )


def test_structure_contract_fixtures(monkeypatch, tmp_path):
    fixtures = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))

    for fixture in fixtures:
        input_xml = tmp_path / f"{fixture['name']}_input.xml"
        output_xml = tmp_path / f"{fixture['name']}_output.xml"
        input_xml.write_text(fixture["input_xml"], encoding="utf-8")
        output_xml.write_text(fixture["output_xml"], encoding="utf-8")

        _patch_rules(monkeypatch, fixture["rules"])

        result = validate_module.validate_mapping(
            fixture["spec_path"],
            str(input_xml),
            str(output_xml),
            validation_mode=fixture.get("validation_mode", "structure_strict"),
        )

        expected = fixture["expected"]
        assert result["summary"]["status"] == expected["status"], fixture["name"]

        for key, value in expected.get("grouped_error_counts", {}).items():
            assert result["summary"]["grouped_error_counts"].get(key) == value, fixture["name"]

        categories = {finding.get("category") for finding in result.get("structure_findings", [])}
        for category in expected.get("structure_categories", []):
            assert category in categories, fixture["name"]

        coverage = result["structure_summary"].get("coverage", {})
        assert "coverage_percent" in coverage, fixture["name"]
        assert "missing_allowed_paths" in coverage, fixture["name"]
