"""
Phase 6 — Smoke tests for robust spec reading across all sample files.
Verifies that every xlsx in the rules/ folder can be parsed without error
and yields at least one valid rule.
"""
import json
import pytest
import pandas as pd
from pathlib import Path
from jsonschema import validate as jsonschema_validate

from core.spec_reader import (
    read_mapping_table,
    extract_rules,
    _find_mapping_sheet,
    get_parser_diagnostics,
)

RULES_DIR = Path(__file__).parent.parent / "rules"
ALL_SPECS = sorted(RULES_DIR.glob("*.xlsx"))
RULE_IR_SCHEMA_PATH = Path(__file__).parent.parent / "schemas" / "rule_ir.schema.json"


@pytest.mark.parametrize("spec_path", ALL_SPECS, ids=lambda p: p.name)
def test_spec_can_be_read(spec_path):
    """read_mapping_table must succeed and return a non-empty DataFrame."""
    df = read_mapping_table(str(spec_path))
    assert not df.empty, f"{spec_path.name}: DataFrame is empty"


@pytest.mark.parametrize("spec_path", ALL_SPECS, ids=lambda p: p.name)
def test_spec_yields_rules(spec_path):
    """extract_rules must return at least one rule with a non-empty target or source."""
    df = read_mapping_table(str(spec_path))
    rules = extract_rules(df)
    assert len(rules) > 0, f"{spec_path.name}: no rules extracted"
    # Every rule must have the expected keys
    required_keys = {
        "target_xpath",
        "source_xpath",
        "cardinality",
        "condition",
        "note",
        "m_o",
        "layout",
        "parser_confidence",
        "rule_ir",
    }
    for rule in rules:
        assert required_keys.issubset(rule.keys()), (
            f"{spec_path.name}: rule missing keys: {required_keys - rule.keys()}"
        )
        assert rule["parser_confidence"] in {"high", "medium", "low"}
        assert rule["rule_ir"]["node_type"] == "mapping_rule"
        assert rule["rule_ir"]["provenance"]["row"] >= 1
        assert rule["rule_id"] == rule["rule_ir"]["identity"]["rule_id"]
        assert rule["rule_fingerprint"] == rule["rule_ir"]["identity"]["rule_fingerprint"]
        assert rule["rule_ir"]["provenance"]["workbook_fingerprint"]


@pytest.mark.parametrize("spec_path", ALL_SPECS, ids=lambda p: p.name)
def test_rule_ir_schema_contract(spec_path):
    schema = json.loads(RULE_IR_SCHEMA_PATH.read_text(encoding="utf-8"))
    df = read_mapping_table(str(spec_path))
    rules = extract_rules(df)
    assert rules, f"{spec_path.name}: no rules to validate against IR schema"

    for rule in rules:
        jsonschema_validate(instance=rule["rule_ir"], schema=schema)


@pytest.mark.parametrize("spec_path", ALL_SPECS, ids=lambda p: p.name)
def test_sheet_detection(spec_path):
    """_find_mapping_sheet must return a non-empty string for every spec file."""
    sheet = _find_mapping_sheet(spec_path)
    assert sheet, f"{spec_path.name}: no mapping sheet detected"


def test_cdm_target_layout_detected():
    """cXML-to-CDM files (P&G_cXML_*) must be detected as cdm_target layout."""
    from core.spec_reader import _detect_layout

    # Files named P&G_cXML_* have cXML as the SOURCE and CDM as the TARGET
    cdm_files = [p for p in ALL_SPECS if p.name.startswith("P&G_cXML_")]
    assert cdm_files, "No cXML-to-CDM spec files found for layout detection test"

    for spec_path in cdm_files:
        df = read_mapping_table(str(spec_path))
        layout = _detect_layout(df)
        assert layout == "cdm_target", (
            f"{spec_path.name}: expected 'cdm_target', got '{layout}'"
        )


def test_xpath_target_layout_detected():
    """CDM-to-cXML and X12 files must be detected as xpath_target layout."""
    from core.spec_reader import _detect_layout

    # Files named P&G_CDM_*, JABIL_* (excluding X12), and spec.xlsx have xpath targets
    xpath_files = [
        p for p in ALL_SPECS
        if (p.name.startswith("P&G_CDM_")
            or (p.name.lower().startswith("jabil") and "x12" not in p.name.lower())
            or p.name.lower() == "spec.xlsx")
    ]
    assert xpath_files, "No xpath_target spec files found"

    for spec_path in xpath_files:
        df = read_mapping_table(str(spec_path))
        layout = _detect_layout(df)
        assert layout == "xpath_target", (
            f"{spec_path.name}: expected 'xpath_target', got '{layout}'"
        )


def test_x12_segment_layout_detected():
    """X12 spec files (e.g., JABIL_*X12*) must be detected as x12_segment layout."""
    from core.spec_reader import _detect_layout

    # Files with X12 in the name have x12 segment sources
    x12_files = [p for p in ALL_SPECS if "x12" in p.name.lower()]
    
    if not x12_files:
        pytest.skip("No X12 spec files found for layout detection test")

    for spec_path in x12_files:
        df = read_mapping_table(str(spec_path))
        layout = _detect_layout(df)
        assert layout == "x12_segment", (
            f"{spec_path.name}: expected 'x12_segment', got '{layout}'"
        )


def test_edifact_segment_layout_detected_from_xpath_values():
    """EDIFACT-style source paths should be detected as x12_segment (generic EDI segment layout)."""
    from core.spec_reader import _detect_layout

    df = pd.DataFrame(
        {
            "segment / field xpath": [
                "/root/invoiceNumber",
                "/root/messageType",
            ],
            "source xpath": [
                "/EDIFACT/MSG_INVOIC/BGM/BGM02",
                "/EDIFACT/MSG_INVOIC/UNH/UNH02",
            ],
        }
    )

    layout = _detect_layout(df)
    assert layout == "x12_segment"


def test_edifact_segment_layout_detected_from_segment_payload_hints():
    """UNB/UNH style hints in source columns should map to x12_segment EDI layout."""
    from core.spec_reader import _detect_layout

    df = pd.DataFrame(
        {
            "target xpath": ["/root/id"],
            "source segment": ["UNH+1+INVOIC:D:96A:UN"],
        }
    )

    layout = _detect_layout(df)
    assert layout == "x12_segment"


def test_edifact_source_column_disambiguation_supports_slash_segment_notation():
    """Slash notation (for example UNH/UNH02) should be treated as EDI source paths."""
    df = pd.DataFrame(
        {
            "segment / field xpath": [
                "/root/message/type",
                "/root/message/id",
            ],
            "segment / field xpath__dup2": [
                "UNH/UNH02",
                "BGM/BGM02",
            ],
            "condition": ["", ""],
        }
    )
    df.attrs["parser_diagnostics"] = {"workbook_family": "generic"}

    rules = extract_rules(df)

    assert rules
    assert all(rule["layout"] == "x12_segment" for rule in rules)
    assert all(rule["source_xpath"] in {"UNH/UNH02", "BGM/BGM02"} for rule in rules)


def test_edifact_source_column_disambiguation_supports_composite_segment_notation():
    """Composite EDIFACT notation (for example BGM+220+INV001) should be recognized as EDI source values."""
    df = pd.DataFrame(
        {
            "xpath": [
                "/root/invoice/id",
            ],
            "xpath__dup2": [
                "BGM+220+INV001",
            ],
            "condition": [""],
        }
    )
    df.attrs["parser_diagnostics"] = {"workbook_family": "generic"}

    rules = extract_rules(df)

    assert rules
    assert rules[0]["source_xpath"] == "BGM+220+INV001"
    assert rules[0]["layout"] == "x12_segment"


def test_ambiguity_reporting_is_deterministic_for_duplicate_resolution():
    """Ambiguity diagnostics should remain stable across repeated extractions."""
    df_one = pd.DataFrame(
        {
            "segment / field xpath": ["/root/a", "/root/b"],
            "x12 segment path": ["/X12/TS_214/B10/B1001", "/X12/TS_214/B10/B1002"],
            "x12 segment value": ["/X12/TS_214/L11/L1101", "/X12/TS_214/L11/L1102"],
            "condition": ["", ""],
        }
    )
    df_two = df_one.copy()

    df_one.attrs["parser_diagnostics"] = {"workbook_family": "generic"}
    df_two.attrs["parser_diagnostics"] = {"workbook_family": "generic"}

    extract_rules(df_one)
    extract_rules(df_two)

    diag_one = get_parser_diagnostics(df_one)
    diag_two = get_parser_diagnostics(df_two)
    amb_one = diag_one.get("extraction", {}).get("ambiguities", [])
    amb_two = diag_two.get("extraction", {}).get("ambiguities", [])

    assert amb_one == amb_two
    assert amb_one
    assert any(item.get("role") == "source" for item in amb_one)
    assert all(item.get("reason") == "multiple_distinct_candidate_bases" for item in amb_one)


def test_rule_level_parser_confidence_for_guided_edifact_samples():
    """Guided EDIFACT fixtures should emit stable rule-level parser confidence labels."""
    spec_path = Path(__file__).parent.parent / "samples" / "spec_edifact_guided.xlsx"
    if not spec_path.exists():
        pytest.skip("Guided EDIFACT sample spec not present")

    df = read_mapping_table(str(spec_path))
    rules = extract_rules(df)

    assert rules
    assert all(rule.get("parser_confidence") in {"high", "medium", "low"} for rule in rules)
    assert all(rule.get("parser_confidence") == "high" for rule in rules)


def test_csv_comma_delimited():
    """CSV with comma delimiter must be read correctly."""
    csv_path = Path(__file__).parent.parent / "samples" / "spec_comma.csv"
    df = read_mapping_table(str(csv_path))
    
    assert not df.empty, "CSV DataFrame is empty"
    assert "segment / field xpath" in df.columns, "Missing expected column"
    assert len(df) >= 4, "Should have at least 4 data rows"
    
    rules = extract_rules(df)
    assert len(rules) > 0, "Should extract at least one rule"


def test_csv_semicolon_delimited():
    """CSV with semicolon delimiter must be read correctly."""
    csv_path = Path(__file__).parent.parent / "samples" / "spec_semicolon.csv"
    df = read_mapping_table(str(csv_path))
    
    assert not df.empty, "CSV DataFrame is empty"
    assert "segment / field xpath" in df.columns, "Missing expected column"
    assert len(df) >= 4, "Should have at least 4 data rows"
    
    rules = extract_rules(df)
    assert len(rules) > 0, "Should extract at least one rule"


def test_csv_tab_delimited():
    """TSV with tab delimiter must be read correctly."""
    tsv_path = Path(__file__).parent.parent / "samples" / "spec_tab.tsv"
    df = read_mapping_table(str(tsv_path))
    
    assert not df.empty, "TSV DataFrame is empty"
    assert "segment / field xpath" in df.columns, "Missing expected column"
    assert len(df) >= 4, "Should have at least 4 data rows"
    
    rules = extract_rules(df)
    assert len(rules) > 0, "Should extract at least one rule"


def test_csv_pipe_delimited():
    """CSV with pipe delimiter must be read correctly."""
    csv_path = Path(__file__).parent.parent / "samples" / "spec_pipe.csv"
    df = read_mapping_table(str(csv_path))
    
    assert not df.empty, "CSV DataFrame is empty"
    assert "segment / field xpath" in df.columns, "Missing expected column"
    assert len(df) >= 4, "Should have at least 4 data rows"
    
    rules = extract_rules(df)
    assert len(rules) > 0, "Should extract at least one rule"


def test_csv_quoted_values():
    """CSV with quoted values containing delimiters must be read correctly."""
    csv_path = Path(__file__).parent.parent / "samples" / "spec_quoted.csv"
    df = read_mapping_table(str(csv_path))
    
    assert not df.empty, "CSV DataFrame is empty"
    assert "segment / field xpath" in df.columns, "Missing expected column"
    assert len(df) >= 4, "Should have at least 4 data rows"
    
    rules = extract_rules(df)
    assert len(rules) > 0, "Should extract at least one rule"
    
    # Verify that quoted values were parsed correctly (no extra quotes)
    # Check that condition was parsed without surrounding quotes
    conditions = [r.get("condition", "") for r in rules if r.get("condition")]
    assert any("'NEW'" in c for c in conditions), "Should parse quoted mapping rules"


def test_sheet_name_fallback_when_requested_sheet_missing(tmp_path):
    """Excel parsing should fall back deterministically when requested sheet is absent."""
    xlsx_path = tmp_path / "fallback_sheet.xlsx"
    df = pd.DataFrame(
        [
            ["meta", "", "", ""],
            ["Segment / Field XPath", "Cardinality", "Condition", "XPath"],
            ["/target/status", "1..1", "", "/source/status"],
        ]
    )
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        pd.DataFrame([["intro"]]).to_excel(writer, sheet_name="Readme", index=False, header=False)
        df.to_excel(writer, sheet_name="Mapping-UnitStatus", index=False, header=False)

    parsed = read_mapping_table(str(xlsx_path), sheet_name="NotARealSheet")
    diagnostics = get_parser_diagnostics(parsed)

    assert not parsed.empty
    assert diagnostics.get("sheet_name") == "Mapping-UnitStatus"
    assert diagnostics.get("sheet_fallback_used") is True


def test_duplicate_headers_are_preserved_deterministically(tmp_path):
    """Duplicate headers should be preserved with suffixes and still extract rules."""
    csv_path = tmp_path / "dup_headers.csv"
    csv_path.write_text(
        "Segment / Field XPath,XPath,XPath,Condition\n"
        "/target/a,/source/a,/source/b,\n",
        encoding="utf-8",
    )

    parsed = read_mapping_table(str(csv_path))
    diagnostics = get_parser_diagnostics(parsed)
    rules = extract_rules(parsed)

    assert "xpath" in parsed.columns
    assert "xpath__dup2" in parsed.columns
    assert diagnostics.get("duplicate_columns")
    assert rules and rules[0]["source_xpath"] == "/source/b"


def test_edifact_source_column_disambiguation_with_duplicate_xpath_columns():
    """When xpath-like columns are duplicated, EDIFACT-like values must be selected as source paths."""
    df = pd.DataFrame(
        {
            "segment / field xpath": [
                "/root/invoice/id",
                "/root/invoice/messageType",
            ],
            "segment / field xpath__dup2": [
                "/EDIFACT/MSG_INVOIC/BGM/BGM02",
                "/EDIFACT/MSG_INVOIC/UNH/UNH02",
            ],
            "condition": ["", ""],
        }
    )
    df.attrs["parser_diagnostics"] = {"workbook_family": "generic"}

    rules = extract_rules(df)
    assert rules, "Expected rules to be extracted"
    assert all(rule["layout"] == "x12_segment" for rule in rules)
    assert any(rule["source_xpath"].startswith("/EDIFACT/") for rule in rules)
    assert any(rule["target_xpath"].startswith("/root/") for rule in rules)


def test_edifact_source_column_disambiguation_when_same_xpath_bucket():
    """If source and target initially resolve to the same xpath bucket, parser should pick an alternate source column."""
    df = pd.DataFrame(
        {
            "xpath": [
                "/root/order/id",
                "/root/order/date",
            ],
            "xpath__dup2": [
                "/EDIFACT/MSG_ORDERS/BGM/BGM02",
                "/EDIFACT/MSG_ORDERS/DTM/DTM01",
            ],
            "note": ["", ""],
        }
    )
    df.attrs["parser_diagnostics"] = {"workbook_family": "generic"}

    rules = extract_rules(df)
    assert rules, "Expected rules to be extracted"
    assert any(rule["source_xpath"].startswith("/EDIFACT/") for rule in rules)
    assert all(rule["source_xpath"] != rule["target_xpath"] for rule in rules)


def test_offset_header_rows_emit_diagnostics(tmp_path):
    """Sparse/offset sheets should parse with a clear offset diagnostic."""
    xlsx_path = tmp_path / "offset_header.xlsx"
    df = pd.DataFrame(
        [
            ["Document Title", "", "", ""],
            ["Generated on", "", "", ""],
            ["Notes", "", "", ""],
            ["", "", "", ""],
            ["Segment / Field XPath", "Cardinality", "Condition", "XPath"],
            ["/target/b", "0..1", "", "/source/b"],
        ]
    )
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Mapping 001", index=False, header=False)

    parsed = read_mapping_table(str(xlsx_path))
    diagnostics = get_parser_diagnostics(parsed)

    assert not parsed.empty
    warnings = diagnostics.get("warnings", [])
    info = diagnostics.get("info", [])
    combined = [*warnings, *info]
    assert any("preamble" in message.lower() for message in combined)


def test_edifact_workbook_like_mapping_sheet_parses_and_extracts_rules(tmp_path):
    """Workbook-like EDIFACT mapping sheets should parse and produce x12_segment EDI rules."""
    xlsx_path = tmp_path / "edifact_mapping.xlsx"
    rows = [
        ["Change History", "", "", ""],
        ["Final TARGET INVOICE", "", "SOURCE EDIFACT", ""],
        ["LEVEL", "SEGMENT / FIELD XPATH", "SEGMENT / FIELD XPATH", "CONDITION"],
        ["Header", "/root/invoice/id", "/EDIFACT/MSG_INVOIC/BGM/BGM02", ""],
        ["Header", "/root/invoice/type", "/EDIFACT/MSG_INVOIC/BGM/BGM01", ""],
    ]
    mapping_df = pd.DataFrame(rows)

    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        pd.DataFrame([["meta"]]).to_excel(writer, sheet_name="Change History", index=False, header=False)
        mapping_df.to_excel(writer, sheet_name="Mapping", index=False, header=False)

    parsed = read_mapping_table(str(xlsx_path))
    diagnostics = get_parser_diagnostics(parsed)
    rules = extract_rules(parsed)

    assert not parsed.empty
    assert diagnostics.get("layout") == "x12_segment"
    assert len(rules) >= 2
    assert any(rule["source_xpath"].startswith("/EDIFACT/") for rule in rules)
    assert any(rule["target_xpath"].startswith("/root/") for rule in rules)


def test_inttra_contivo_spec_can_be_parsed_and_extract_rules():
    """Named coverage for the Inttra-Contivo workbook added during Stage 7."""
    spec_path = RULES_DIR / "Inttra-Contivo_X12_300_5030_to_JSON_BOOKINGINBOUND.xlsx"
    if not spec_path.exists():
        pytest.skip("Inttra-Contivo workbook not present")

    df = read_mapping_table(str(spec_path))
    diagnostics = get_parser_diagnostics(df)
    rules = extract_rules(df)

    assert not df.empty
    assert diagnostics.get("sheet_name") == "Mapping"
    assert diagnostics.get("layout") == "x12_segment"
    assert diagnostics.get("rule_count", 0) > 0
    assert diagnostics.get("confidence") in {"high", "medium", "low"}
    assert len(rules) > 0


@pytest.mark.parametrize(
    "fixture_name,expected_rule_count,expected_message_segment,expected_target_prefix",
    [
        ("spec_edifact_guided.xlsx", 4, "MSG_INVOIC", "/root/invoice/"),
        ("spec_edifact_orders_guided.xlsx", 5, "MSG_ORDERS", "/root/order/"),
    ],
)
def test_guided_edifact_sample_specs_parse_with_expected_columns_and_rules(
    fixture_name: str,
    expected_rule_count: int,
    expected_message_segment: str,
    expected_target_prefix: str,
):
    """Reusable EDIFACT sample workbooks (guided from JABIL X12 header style) should parse deterministically."""
    spec_path = Path(__file__).parent.parent / "samples" / fixture_name
    if not spec_path.exists():
        pytest.skip(f"Guided EDIFACT sample spec not present: {fixture_name}")

    df = read_mapping_table(str(spec_path))
    rules = extract_rules(df)
    diagnostics = get_parser_diagnostics(df)
    selected = diagnostics.get("extraction", {}).get("selected_columns", {})

    assert not df.empty
    assert diagnostics.get("sheet_name") == "Mapping"
    assert diagnostics.get("layout") == "x12_segment"
    assert diagnostics.get("header_row") == 2
    assert diagnostics.get("rule_count") == expected_rule_count
    assert selected.get("target") == "segment / field xpath"
    assert selected.get("source") == "segment / field xpath__dup2"
    assert len(rules) == expected_rule_count
    assert all(rule.get("source_xpath", "").startswith("/EDIFACT/") for rule in rules)
    assert any(expected_message_segment in rule.get("source_xpath", "") for rule in rules)
    assert all(rule.get("target_xpath", "").startswith(expected_target_prefix) for rule in rules)


@pytest.mark.parametrize(
    "spec_name",
    [
        "JABIL_X12_214_4010_to_JSON_TMSCARRIERTENDERRESPONSE_v1.4.xlsx",
        "JABIL_X12_315_4010_to_JSON_TMSCARRIERTENDERRESPONSE_v1.4.xlsx",
        "P&G_CDM_OrderForecastDownload_1.0_to_cXML_ProductActivityForecast_1.2.051.xlsx",
        "P&G_CDM_PurchasedForecastDownload_1.0_to_cXML_ProductActivityForecast_1.2.051.xlsx",
        "P&G_CDM_PurchasedItemsInventoryDownload_1.0_to_cXML_ProductActivityInventory_1.2.051.xlsx",
        "spec.xlsx",
        "TMSLSP-DHLLINK_Common_CUSTOMXML_Status_1.0_to_CUSTOMXML_Status_1.0.xlsx",
        "TMSLSP-DHLLINK_SAP_CUSTOMXML_Status-out_1.0_to_CUSTOMXML_Status-out_1.0.xlsx",
    ],
)
def test_previously_low_confidence_specs_are_stable(spec_name):
    """Regression guard: previously low-confidence files should stay non-low."""
    spec_path = RULES_DIR / spec_name
    if not spec_path.exists():
        pytest.skip(f"Spec not present: {spec_name}")

    df = read_mapping_table(str(spec_path))
    rules = extract_rules(df)
    diagnostics = get_parser_diagnostics(df)

    assert len(rules) > 0
    assert diagnostics.get("status") in {"clean", "parsed_with_warnings", "parsed_with_fallbacks"}
    assert diagnostics.get("status") != "low_confidence"


def test_stage7_quality_gate_no_low_confidence_specs():
    """Stage 7 quality gate: no workbook in rules/ should remain low-confidence."""
    low_confidence_specs = []
    for spec_path in ALL_SPECS:
        df = read_mapping_table(str(spec_path))
        extract_rules(df)
        diagnostics = get_parser_diagnostics(df)
        if diagnostics.get("status") == "low_confidence":
            low_confidence_specs.append(spec_path.name)

    assert not low_confidence_specs, f"Low-confidence specs remain: {low_confidence_specs}"
