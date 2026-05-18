from pathlib import Path

import pytest

from core.validate import validate_mapping_from_payload_bytes


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

    adapter_pipeline = result.get("adapter_pipeline") or {"enabled": False}
    if expects_adapter:
        assert adapter_pipeline.get("enabled") is True
        assert adapter_pipeline.get("input_format") in {"x12", "edifact", "json", "xml"}
    else:
        assert adapter_pipeline.get("enabled") in {False, None}