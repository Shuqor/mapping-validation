from scripts.check_parser_uncertainty_profiles import profile_budget_issues, select_profile


def test_select_profile_matches_spec_contains_marker():
    report = {
        "inputs": {
            "spec_path": "rules/Inttra-Contivo_EDIFACT_IFTMBF_D99B_to_JSON_BOOKINGINBOUND.xlsx",
        }
    }
    config = {
        "default": {"max_ambiguities": 0, "allowed_confidence": ["high", "medium"]},
        "profiles": [
            {
                "id": "inttra_edifact_bookinginbound",
                "spec_path_contains": "Inttra-Contivo_EDIFACT_IFTMBF_D99B_to_JSON_BOOKINGINBOUND.xlsx",
                "max_ambiguities": 0,
                "allowed_confidence": ["high", "medium"],
            }
        ],
    }

    profile_name, profile = select_profile(report, config)

    assert profile_name == "inttra_edifact_bookinginbound"
    assert profile["max_ambiguities"] == 0


def test_profile_budget_issues_reports_confidence_drift():
    report = {
        "summary": {"parser_confidence": "low"},
        "parser_diagnostics": {"confidence": "low", "extraction": {"ambiguities": []}},
        "inputs": {"spec_path": "rules/spec.xlsx"},
    }
    config = {
        "default": {"max_ambiguities": 0, "allowed_confidence": ["high", "medium"]},
        "profiles": [],
    }

    profile_name, issues = profile_budget_issues(report, config)

    assert profile_name == "default"
    assert any("parser confidence" in issue for issue in issues)
