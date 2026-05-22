from scripts.check_warning_taxonomy_drift import warning_taxonomy_drift_messages


def test_warning_taxonomy_drift_messages_empty_when_counts_match():
    report = {
        "warning_taxonomy": {
            "counts": {
                "strict": 0,
                "heuristic": 0,
                "informational": 1,
                "total": 1,
            }
        }
    }
    expected = {"strict": 0, "heuristic": 0, "informational": 1, "total": 1}

    assert warning_taxonomy_drift_messages(report, expected) == []


def test_warning_taxonomy_drift_messages_reports_mismatch():
    report = {
        "warning_taxonomy": {
            "counts": {
                "strict": 0,
                "heuristic": 2,
                "informational": 1,
                "total": 3,
            }
        }
    }
    expected = {"strict": 0, "heuristic": 0, "informational": 1, "total": 1}

    issues = warning_taxonomy_drift_messages(report, expected)
    assert any("warning_taxonomy.heuristic drift" in issue for issue in issues)
    assert any("warning_taxonomy.total drift" in issue for issue in issues)
