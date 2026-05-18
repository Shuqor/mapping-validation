import json
from pathlib import Path

import core.validate as validate_module


FIXTURES_PATH = Path(__file__).resolve().parent / "fixtures" / "semantic_similarity_fixtures.json"
REGRESSION_CORPUS_PATH = Path(__file__).resolve().parent / "fixtures" / "semantic_regression_corpus.json"
REAL_WORLD_CORPUS_PATH = Path(__file__).resolve().parent / "fixtures" / "semantic_real_world_corpus.json"


def _write_xml(path, body: str) -> None:
    path.write_text(body, encoding="utf-8")


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
            "layout": "xpath_target",
            "rule_count": len(rules),
            "extraction": {"ambiguities": []},
        },
    )


def test_semantic_similarity_fixtures_rank_expected_top_family():
    fixtures = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))

    for fixture in fixtures:
        suggestions = validate_module._suggest_pattern_families(fixture["condition"], top_n=3)
        assert suggestions, fixture["name"]
        assert suggestions[0]["family"] == fixture["expected_top_family"], fixture["name"]
        assert suggestions[0]["confidence"] in {"high", "medium", "low"}, fixture["name"]


def test_unsupported_rule_contains_similarity_suggestions(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status">\n'
        '  <ediFunction1>ABC</ediFunction1>\n'
        '</status>\n'
    )
    _write_xml(src_xml, xml)
    _write_xml(tgt_xml, xml)

    rules = [
        {
            "target_xpath": "/status/ediFunction1",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "0..1",
            "condition": "Use external codebook match policy before deciding final target mapping",
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping("unused.xlsx", str(src_xml), str(tgt_xml))

    assert result["skipped_rules"]
    skipped = result["skipped_rules"][0]
    assert skipped["reason"] == "Unsupported condition pattern"
    assert skipped["normalized_condition"]
    assert isinstance(skipped["applied_transforms"], list)
    assert skipped["nearest_family"]
    assert isinstance(skipped["similarity_score"], float)
    assert skipped["similarity_confidence"] in {"high", "medium", "low"}
    assert isinstance(skipped["nearest_patterns"], list)
    assert skipped["why_not_enforced"]
    assert skipped["try_normalized_form"]
    assert result["rule_support_summary"]["unsupported_rule_suggestions_provided"] >= 1


def test_semantic_regression_corpus_extracts_expected_parts_and_rewrites():
    fixtures = json.loads(REGRESSION_CORPUS_PATH.read_text(encoding="utf-8"))

    for fixture in fixtures:
        profile = validate_module._get_semantic_profile(fixture["spec_path"])
        normalized, _trace = validate_module._canonicalize_semantic_condition_with_trace(
            fixture["condition"],
            semantic_profile=profile,
        )
        parts = validate_module._extract_semantic_parts(normalized, profile["field_aliases"])

        assert parts["operator"] == fixture["expected_operator"], fixture["name"]
        assert parts["action"] == fixture["expected_action"], fixture["name"]

        expected_field = fixture.get("expected_field_reference")
        if expected_field:
            assert expected_field in parts["field_references"], fixture["name"]

        expected_family = fixture.get("expected_top_family")
        if expected_family:
            suggestions = validate_module._suggest_pattern_families(
                normalized,
                top_n=3,
                semantic_profile=profile,
            )
            assert suggestions[0]["family"] == expected_family, fixture["name"]
            rewrite = validate_module._build_suggested_canonical_rewrite(expected_family, parts, {"is_ambiguous": False})
            expected_rewrite = fixture.get("expected_rewrite_contains")
            if expected_rewrite:
                assert expected_rewrite in rewrite, fixture["name"]


def test_semantic_ambiguity_helper_flags_close_matches():
    ambiguity = validate_module._analyze_semantic_ambiguity(
        [
            {"family": "if_equals_then_map", "score": 0.79},
            {"family": "source_exists_target_constant", "score": 0.75},
        ],
        {"high": 0.75, "medium": 0.45, "auto_promote": 0.9, "ambiguity_gap": 0.08},
    )

    assert ambiguity["is_ambiguous"] is True
    assert ambiguity["candidate_families"] == ["if_equals_then_map", "source_exists_target_constant"]


def test_unsupported_rule_includes_semantic_summary_and_guidance(tmp_path, monkeypatch):
    src_xml = tmp_path / "input.xml"
    tgt_xml = tmp_path / "output.xml"

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<status xmlns="http://tms-lsp.blujaysolutions.net/api/status">\n'
        '  <ediFunction1>ABC</ediFunction1>\n'
        '</status>\n'
    )
    _write_xml(src_xml, xml)
    _write_xml(tgt_xml, xml)

    rules = [
        {
            "target_xpath": "/status/ediFunction1",
            "source_xpath": "/status/ediFunction1",
            "cardinality": "0..1",
            "condition": "Whenever TrackingNumber equals 'ABC' then write source into target using external lookup",
            "note": "",
        }
    ]
    _patch_rules(monkeypatch, rules)

    result = validate_module.validate_mapping(
        "rules/JABIL_X12_214_4010_to_IDM_NotifyShipment-10.2_v1.2.xlsx",
        str(src_xml),
        str(tgt_xml),
    )

    skipped = result["skipped_rules"][0]
    semantic_summary = result["semantic_summary"]

    assert skipped["semantic_parts"]["field_references"]
    assert skipped["semantic_profile"] == "global"
    assert "suggested_canonical_rewrite" in skipped
    assert "future_auto_promotion_eligible" in skipped
    assert "ambiguity_reason" in skipped
    assert semantic_summary["profile"] == "global"
    assert semantic_summary["coverage"]["total_condition_rules"] == 1
    assert semantic_summary["coverage"]["unsupported_condition_rules"] == 1
    assert isinstance(semantic_summary["top_unsupported_conditions"], list)
    assert isinstance(semantic_summary["promote_to_generic_candidates"], list)
    assert isinstance(semantic_summary["top_suggested_families"], list)
    assert result["human_summary"]["semantic_summary"]["headline"]


def test_real_world_semantic_corpus_matches_expected_families_and_parts():
    fixtures = json.loads(REAL_WORLD_CORPUS_PATH.read_text(encoding="utf-8"))

    assert len(fixtures) >= 25

    for fixture in fixtures:
        profile = validate_module._get_semantic_profile(fixture["spec_path"])
        normalized, _trace = validate_module._canonicalize_semantic_condition_with_trace(
            fixture["condition"],
            semantic_profile=profile,
        )
        parts = validate_module._extract_semantic_parts(normalized, profile["field_aliases"])
        suggestions = validate_module._suggest_pattern_families(
            normalized,
            top_n=3,
            semantic_profile=profile,
        )

        assert suggestions, fixture["name"]
        expected_top_family = fixture.get("expected_top_family")
        if expected_top_family:
            assert suggestions[0]["family"] == expected_top_family, fixture["name"]
        expected_candidates = fixture.get("expected_candidate_families")
        if expected_candidates:
            suggested_families = [item["family"] for item in suggestions]
            assert any(candidate in suggested_families for candidate in expected_candidates), fixture["name"]
        assert parts["operator"] == fixture["expected_operator"], fixture["name"]
        assert parts["action"] == fixture["expected_action"], fixture["name"]
        assert suggestions[0]["confidence"] in {"high", "medium", "low"}, fixture["name"]
