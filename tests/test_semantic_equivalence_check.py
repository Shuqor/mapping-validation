from scripts.check_semantic_equivalence import find_semantic_equivalence_issues


def test_semantic_equivalence_check_flags_family_drift_for_equivalent_condition():
    report = {
        "skipped_rules": [
            {
                "condition": "If source is present then map source to target",
                "normalized_condition": "if source exists then map source to target",
                "nearest_family": "if_source_map",
            },
            {
                "condition": "If source available then map source to target",
                "normalized_condition": "if source exists then map source to target",
                "nearest_family": "translation",
            },
        ]
    }

    issues = find_semantic_equivalence_issues(report)

    assert issues
    assert "multiple families" in issues[0]


def test_semantic_equivalence_check_passes_when_family_is_consistent():
    report = {
        "skipped_rules": [
            {
                "condition": "If source is present then map source to target",
                "normalized_condition": "if source exists then map source to target",
                "nearest_family": "if_source_map",
            },
            {
                "condition": "If source available then map source to target",
                "normalized_condition": "if source exists then map source to target",
                "nearest_family": "if_source_map",
            },
        ]
    }

    issues = find_semantic_equivalence_issues(report)

    assert issues == []
