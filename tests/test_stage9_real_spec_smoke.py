from pathlib import Path

import pytest

from core.validate import _looks_like_ambiguous_complex_condition, validate_mapping_from_payload_bytes


ROOT_DIR = Path(__file__).resolve().parents[1]
RULES_DIR = ROOT_DIR / "rules"
SAMPLES_DIR = ROOT_DIR / "samples"


REAL_SPEC_CASES = [
    (
        "JABIL_X12_214_4010_to_JSON_TMSCARRIERTENDERRESPONSE_v1.4.xlsx",
        "input.x12",
        "output.json",
        True,
    ),
    (
        "Inttra-Contivo_X12_300_5030_to_JSON_BOOKINGINBOUND.xlsx",
        "input.x12",
        "output.json",
        True,
    ),
    (
        "Inttra-Contivo_X12_300_5030_to_JSON_BOOKINGINBOUND 1 Update.xlsx",
        "SampleforV1 - Copy.edi",
        "BOOKINGINBOUND_1.json",
        True,
    ),
    (
        "P&G_CDM_ReceiptDownload_1.0_to_cXML_ReceiptRequest_1.2.051.xlsx",
        "input.xml",
        "output.xml",
        False,
    ),
    (
        "TMSLSP-DHLLINK_Common_CUSTOMXML_Status_1.0_to_CUSTOMXML_Status_1.0.xlsx",
        "input.xml",
        "output.xml",
        False,
    ),
]


@pytest.mark.parametrize("spec_name,input_name,output_name,expects_adapter", REAL_SPEC_CASES)
def test_stage9_real_spec_smoke(spec_name, input_name, output_name, expects_adapter):
    spec_path = RULES_DIR / spec_name
    input_path = SAMPLES_DIR / input_name
    output_path = SAMPLES_DIR / output_name

    if not spec_path.exists():
        pytest.skip(f"Real workbook not present: {spec_name}")

    result = validate_mapping_from_payload_bytes(
        str(spec_path),
        input_path.read_bytes(),
        input_path.name,
        output_path.read_bytes(),
        output_path.name,
        validation_mode="lenient",
    )

    assert result["summary"]["status"] in {"PASS", "PASS_WITH_WARNINGS", "FAIL"}
    assert result["summary"].get("parser_status") != "low_confidence"
    assert result["checked_rules"] > 0
    assert isinstance(result.get("errors", []), list)
    assert "rule_support_summary" in result
    assert "rule_decisions" in result
    assert isinstance(result.get("rule_decisions", []), list)
    parser_diag = result.get("parser_diagnostics", {})
    assert "token_resolution_diagnostics" in parser_diag
    assert "rollout_guardrails" in parser_diag
    assert "shadow_rule_families" in parser_diag.get("rollout_guardrails", {})

    adapter_pipeline = result.get("adapter_pipeline") or {"enabled": False}
    if expects_adapter:
        assert adapter_pipeline.get("enabled") is True
        assert adapter_pipeline.get("input_format") in {"x12", "edifact", "json", "xml"}
    else:
        assert adapter_pipeline.get("enabled") in {False, None}


def test_looks_like_ambiguous_complex_condition_is_conservative():
    assert _looks_like_ambiguous_complex_condition('Conversion: If Source="AO" then hardcode Target as "EquipmentContact" Else Direct Map')
    assert _looks_like_ambiguous_complex_condition('If /EDIFACT/IFTMBF/GROUP_16/GROUP_27/FTX/FTX01 = "HAN" and /EDIFACT/IFTMBF/GROUP_16/GROUP_27/FTX/FTX0301 = "4" then hardcode "true" to Target')
    assert not _looks_like_ambiguous_complex_condition('Direct Map | /X12/TS_300/N9/N901 = "ZZZ"')
    assert not _looks_like_ambiguous_complex_condition('')


def test_rule_decisions_distribution_matches_support_summary():
    # Use the first available real-spec case to validate decision/support parity.
    for spec_name, input_name, output_name, _expects_adapter in REAL_SPEC_CASES:
        spec_path = RULES_DIR / spec_name
        input_path = SAMPLES_DIR / input_name
        output_path = SAMPLES_DIR / output_name
        if not spec_path.exists():
            continue

        result = validate_mapping_from_payload_bytes(
            str(spec_path),
            input_path.read_bytes(),
            input_path.name,
            output_path.read_bytes(),
            output_path.name,
            validation_mode="lenient",
        )

        decisions = result.get("rule_decisions", [])
        support = result.get("rule_support_summary", {})

        assert isinstance(decisions, list)
        assert decisions, "rule_decisions should be populated"

        statuses = [d.get("status") for d in decisions]
        assert all(s in {"enforced", "parsed_only", "unsupported"} for s in statuses)
        assert all(0.0 <= float(d.get("confidence", 0.0)) <= 1.0 for d in decisions)

        enforced_count = sum(1 for s in statuses if s == "enforced")
        parsed_only_count = sum(1 for s in statuses if s == "parsed_only")
        unsupported_count = sum(1 for s in statuses if s == "unsupported")

        assert enforced_count == int(support.get("enforced_rules", 0))
        assert parsed_only_count == int(support.get("parsed_only_rules", 0))
        assert unsupported_count == int(support.get("unsupported_rules", 0))
        assert enforced_count + parsed_only_count + unsupported_count == int(result.get("checked_rules", 0))
        return

    pytest.skip("No real workbook present for parity distribution test")