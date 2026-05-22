from scripts.check_warning_taxonomy import check_warning_taxonomy


def test_warning_taxonomy_contract_accepts_consistent_report():
    report = {
        "warnings": ["a", "b", "c"],
        "warning_taxonomy": {
            "strict_warnings": ["a"],
            "heuristic_warnings": ["b"],
            "informational_warnings": ["c"],
            "counts": {
                "strict": 1,
                "heuristic": 1,
                "informational": 1,
                "total": 3,
            },
        },
    }

    assert check_warning_taxonomy(report) == []


def test_warning_taxonomy_contract_rejects_total_mismatch():
    report = {
        "warnings": ["a", "b"],
        "warning_taxonomy": {
            "strict_warnings": ["a"],
            "heuristic_warnings": [],
            "informational_warnings": ["b"],
            "counts": {
                "strict": 1,
                "heuristic": 0,
                "informational": 1,
                "total": 3,
            },
        },
    }

    issues = check_warning_taxonomy(report)
    assert any("counts.total" in issue for issue in issues)
