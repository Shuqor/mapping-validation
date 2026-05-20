import pytest

from core.validate import _detect_pattern_family, _normalize_condition_text_with_trace


@pytest.mark.parametrize(
    "variants",
    [
        [
            'if FTX01 = "CCI" & FTX0301 = "AMS" then hardcode "NotCarrier" to Target',
            'IF   FTX01="CCI" and FTX0301 = "AMS" THEN hardcode "NotCarrier" to target',
            'if FTX01 = "CCI" && FTX0301 = "AMS" then hardcode "NotCarrier" to Target',
        ],
        [
            "Conversion:\nIf Source='AO' then hardcode Target as \"EquipmentContact\"\nElse Direct Map",
            "conversion: if source = 'AO' then hardcode target as \"EquipmentContact\" else direct map",
            "Conversion: IF Source='AO' THEN hardcode Target as \"EquipmentContact\" ELSE Direct Map",
        ],
    ],
)
def test_condition_normalization_fuzz_stable(variants):
    families = []
    traces = []
    for text in variants:
        normalized, trace = _normalize_condition_text_with_trace(text)
        families.append(_detect_pattern_family(normalized))
        traces.append(trace)

    assert all(family == families[0] for family in families)
    assert all(isinstance(trace, list) for trace in traces)
