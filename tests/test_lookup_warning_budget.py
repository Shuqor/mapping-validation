from scripts.check_lookup_warning_budget import check_lookup_warning_budget


def test_lookup_warning_budget_passes_when_within_limit():
    report = {
        "warnings": [
            "Adapter pipeline mode: JSON payloads were normalized via the Stage 9 adapter bridge.",
            "0 lookup ambiguity finding(s) were downgraded under conservative low-confidence policy.",
        ]
    }
    assert check_lookup_warning_budget(report, 1) == []


def test_lookup_warning_budget_fails_when_over_limit():
    report = {
        "warnings": [
            "1 lookup ambiguity finding(s) were downgraded under conservative low-confidence policy.",
            "1 lookup conflict finding(s) were downgraded under conservative low-confidence policy.",
        ]
    }
    issues = check_lookup_warning_budget(report, 1)
    assert issues
    assert "lookup_warning_budget exceeded" in issues[0]
