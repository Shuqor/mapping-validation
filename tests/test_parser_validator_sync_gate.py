from pathlib import Path

import pytest

import core.validate as validate_module


SYNC_SPECS = [
    "rules/Inttra-Contivo_X12_300_5030_to_JSON_BOOKINGINBOUND 1 Update.xlsx",
    "rules/Inttra-Contivo_EDIFACT_IFTMBF_D99B_to_JSON_BOOKINGINBOUND.xlsx",
    "rules/spec.xlsx",
    "rules/JABIL_X12_214_4010_to_JSON_TMSCARRIERTENDERRESPONSE_v1.4.xlsx",
    "rules/JABIL_X12_315_4010_to_JSON_TMSCARRIERTENDERRESPONSE_v1.4.xlsx",
    "rules/TMSLSP-DHLLINK_Common_CUSTOMXML_Status_1.0_to_CUSTOMXML_Status_1.0.xlsx",
    "rules/P&G_CDM_DiscreteOrderDownload_1.0_to_cXML_PurchaseOrder_1.2.051.xlsx",
]


@pytest.mark.parametrize("spec_path", SYNC_SPECS)
def test_parser_validator_sync_gate_on_real_specs(spec_path):
    root = Path(__file__).resolve().parents[1]
    assert (root / spec_path).exists(), f"Missing sync-gate fixture: {spec_path}"

    report = validate_module.validate_spec_coverage(spec_path)
    decisions = report.get("rule_decisions", [])
    parser_diag = report.get("parser_diagnostics", {})
    checked_rules = int(report.get("checked_rules", 0) or 0)

    assert parser_diag.get("rule_count") == checked_rules
    assert len(decisions) == checked_rules

    rows = [int(item.get("row", 0) or 0) for item in decisions]
    assert rows == list(range(1, checked_rules + 1))

    rules = validate_module.extract_rules(validate_module.read_mapping_table(spec_path))
    assert len(rules) == checked_rules

    by_row = {int(item["row"]): item for item in decisions}
    for row_index, rule in enumerate(rules, start=1):
        decision = by_row[row_index]
        cond_raw = str(rule.get("condition", "") or "").strip()

        if not cond_raw:
            assert decision.get("status") == "enforced"
            assert decision.get("family") == "direct_map"
            continue

        cond_norm, _trace = validate_module._canonicalize_semantic_condition_with_trace(
            cond_raw,
            semantic_profile=validate_module._get_semantic_profile(spec_path),
        )
        enforceable, parsed_only = validate_module._is_condition_supported_for_dry_run(cond_norm)

        if enforceable:
            assert decision.get("status") == "enforced"
            detected = validate_module._detect_pattern_family(cond_norm)
            expected_family = detected if detected != "unknown" else "direct_map"
            assert decision.get("family") == expected_family
        elif parsed_only:
            assert decision.get("status") == "parsed_only"
        else:
            assert decision.get("status") == "unsupported"

        reason_code = str(decision.get("reason_code") or "")
        assert reason_code
        assert len(reason_code) <= 80
