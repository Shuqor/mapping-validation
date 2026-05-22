import json
from pathlib import Path

import core.validate as validate_module


FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "rule_intent_golden.json"


def test_rule_intent_golden_pack_matches_expected_families_and_reason_codes():
    fixtures = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    for item in fixtures:
        cond = str(item["condition"])
        expected_family = str(item["expected_family"])
        expected_reason_code = str(item["expected_reason_code"])

        normalized, _trace = validate_module._canonicalize_semantic_condition_with_trace(
            cond,
            semantic_profile=validate_module._get_semantic_profile("rules/spec.xlsx"),
        )
        family = validate_module._detect_pattern_family(normalized)
        enforceable, parsed_only = validate_module._is_condition_supported_for_dry_run(normalized)

        if enforceable:
            reason_code = validate_module._reason_code("Condition pattern is supported in deterministic mode")
        elif parsed_only:
            reason_code = validate_module._reason_code("Condition recognized as procedural/instruction-only")
        else:
            reason_code = validate_module._reason_code("Unsupported condition pattern")

        assert family == expected_family, f"{item['id']}: expected family {expected_family}, got {family}"
        assert reason_code == expected_reason_code, f"{item['id']}: expected reason_code {expected_reason_code}, got {reason_code}"
