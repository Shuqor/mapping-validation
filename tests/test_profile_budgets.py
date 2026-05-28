import json

from scripts import check_profile_budgets


def test_check_profile_budgets_reports_family_breakdown(tmp_path, monkeypatch):
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()
    spec_path = rules_dir / "sample.xlsx"
    spec_path.write_bytes(b"fake-xlsx")

    budgets_path = tmp_path / "budgets.json"
    budgets_path.write_text(
        json.dumps(
            {
                "default": {"max_parsed_only_rate": 0.5, "max_unsupported_rate": 0.5},
                "profiles": {"generic": {"max_parsed_only_rate": 0.5, "max_unsupported_rate": 0.5}},
                "families": {"direct_map": {"max_parsed_only_rate": 0.5, "max_unsupported_rate": 0.5}},
            }
        ),
        encoding="utf-8",
    )

    output_path = tmp_path / "report.json"

    monkeypatch.setattr(check_profile_budgets.validate_module, "_get_semantic_profile", lambda path: {"profile_key": "generic"})
    monkeypatch.setattr(
        check_profile_budgets.validate_module,
        "validate_spec_coverage",
        lambda path: {
            "checked_rules": 4,
            "rule_support_summary": {"parsed_only_rules": 1, "unsupported_rules": 1},
            "rule_decisions": [
                {"family": "direct_map", "status": "enforced"},
                {"family": "direct_map", "status": "parsed_only"},
                {"family": "manual_review", "status": "unsupported"},
                {"family": "manual_review", "status": "enforced"},
            ],
        },
    )

    monkeypatch.setattr(
        check_profile_budgets.sys,
        "argv",
        [
            "check_profile_budgets.py",
            "--rules-dir",
            str(rules_dir),
            "--budgets",
            str(budgets_path),
            "--output",
            str(output_path),
        ],
    )

    assert check_profile_budgets.main() == 0

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["finding_count"] == 0
    assert payload["profiles"]["generic"]["finding_count"] == 0
    assert payload["profiles"]["generic"]["families"]["direct_map"]["decision_count"] == 2
    assert payload["profiles"]["generic"]["families"]["manual_review"]["unsupported_rules"] == 1
    assert payload["profiles"]["generic"]["families"]["manual_review"]["finding_count"] == 0


def test_check_profile_budgets_emits_family_finding_counts_when_threshold_exceeded(tmp_path, monkeypatch):
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()
    spec_path = rules_dir / "sample.xlsx"
    spec_path.write_bytes(b"fake-xlsx")

    budgets_path = tmp_path / "budgets.json"
    budgets_path.write_text(
        json.dumps(
            {
                "default": {"max_parsed_only_rate": 0.1, "max_unsupported_rate": 0.1},
                "profiles": {"generic": {"max_parsed_only_rate": 0.1, "max_unsupported_rate": 0.1}},
                "families": {"manual_review": {"max_parsed_only_rate": 0.1, "max_unsupported_rate": 0.1}},
            }
        ),
        encoding="utf-8",
    )

    output_path = tmp_path / "report.json"

    monkeypatch.setattr(check_profile_budgets.validate_module, "_get_semantic_profile", lambda path: {"profile_key": "generic"})
    monkeypatch.setattr(
        check_profile_budgets.validate_module,
        "validate_spec_coverage",
        lambda path: {
            "checked_rules": 4,
            "rule_support_summary": {"parsed_only_rules": 2, "unsupported_rules": 1},
            "rule_decisions": [
                {"family": "manual_review", "status": "parsed_only"},
                {"family": "manual_review", "status": "parsed_only"},
                {"family": "manual_review", "status": "unsupported"},
                {"family": "manual_review", "status": "enforced"},
            ],
        },
    )

    monkeypatch.setattr(
        check_profile_budgets.sys,
        "argv",
        [
            "check_profile_budgets.py",
            "--rules-dir",
            str(rules_dir),
            "--budgets",
            str(budgets_path),
            "--output",
            str(output_path),
        ],
    )

    assert check_profile_budgets.main() == 0

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    family_payload = payload["profiles"]["generic"]["families"]["manual_review"]
    assert payload["finding_count"] > 0
    assert payload["profiles"]["generic"]["finding_count"] > 0
    assert family_payload["finding_count"] == 2
    assert len(family_payload["findings"]) == 2