import pandas as pd

from core.spec_reader import extract_rules
from core.validate import _resolve_condition_from_rule_ir, _resolve_rule_row


def _sample_df() -> pd.DataFrame:
    df = pd.DataFrame(
        {
            "target xpath": ["/root/a", "/root/b"],
            "source xpath": ["/root/srcA", "/root/srcB"],
            "cardinality": ["0..N", "1..1"],
            "condition": ["If source exists then map to target", "No Mapping"],
            "note": ["note a", "note b"],
            "m/o": ["O", "M"],
        }
    )
    df.attrs["parser_diagnostics"] = {
        "spec_name": "unit_test_spec.xlsx",
        "sheet_name": "Mapping",
        "workbook_family": "generic",
        "file_format": "excel",
        "header_row": 0,
    }
    return df


def test_rule_ir_identity_is_stable_for_same_input():
    rules_one = extract_rules(_sample_df())
    rules_two = extract_rules(_sample_df())

    assert [r["rule_id"] for r in rules_one] == [r["rule_id"] for r in rules_two]
    assert [r["rule_fingerprint"] for r in rules_one] == [r["rule_fingerprint"] for r in rules_two]


def test_rule_ir_constraints_include_normalized_occurs_semantics():
    rules = extract_rules(_sample_df())

    first_constraints = rules[0]["rule_ir"]["constraints"]
    second_constraints = rules[1]["rule_ir"]["constraints"]

    assert first_constraints["min_occurs"] == 0
    assert first_constraints["max_occurs"] is None
    assert first_constraints["required"] is False
    assert first_constraints["nullable"] is True

    assert second_constraints["min_occurs"] == 1
    assert second_constraints["max_occurs"] == 1
    assert second_constraints["required"] is True
    assert second_constraints["nullable"] is False


def test_validator_prefers_rule_ir_condition_and_row_when_available():
    rule = {
        "condition": "legacy condition",
        "rule_ir": {
            "condition": {
                "raw": "If SOURCE exists then map to Target",
                "normalized": "If SOURCE exists then map to Target",
            },
            "provenance": {
                "row": 77,
            },
        },
    }

    assert _resolve_condition_from_rule_ir(rule) == "If SOURCE exists then map to Target"
    assert _resolve_rule_row(rule, fallback_row=12) == 77
