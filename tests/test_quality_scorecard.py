import json
from pathlib import Path

from scripts.build_quality_scorecard import main as build_quality_scorecard_main


def test_build_quality_scorecard_includes_family_budget_summary(tmp_path, monkeypatch):
    global_parser = tmp_path / "global_parser.json"
    global_parser.write_text(json.dumps({"projection": {"status": "PASS"}}), encoding="utf-8")

    global_validator = tmp_path / "global_validator.json"
    global_validator.write_text(json.dumps({"projection": {"status": "PASS"}}), encoding="utf-8")

    calibration = tmp_path / "calibration.json"
    calibration.write_text(json.dumps({"overall": {"precision": 0.9}}), encoding="utf-8")

    profile_budget = tmp_path / "profile_budget.json"
    profile_budget.write_text(
        json.dumps(
            {
                "finding_count": 1,
                "profiles": {
                    "generic": {
                        "finding_count": 1,
                        "families": {
                            "direct_map": {"finding_count": 2},
                            "manual_review": {"finding_count": 3},
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    trend = tmp_path / "trend.json"
    trend.write_text(json.dumps({"history": [{"report_id": "r1"}]}), encoding="utf-8")

    output = tmp_path / "scorecard.json"

    monkeypatch.setattr(
        "sys.argv",
        [
            "build_quality_scorecard.py",
            "--global-parser",
            str(global_parser),
            "--global-validator",
            str(global_validator),
            "--calibration",
            str(calibration),
            "--profile-budget",
            str(profile_budget),
            "--trend",
            str(trend),
            "--output",
            str(output),
        ],
    )

    assert build_quality_scorecard_main() == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["profile_budgets"]["finding_count"] == 1
    assert payload["profile_budgets"]["family_finding_count"] == 5
    assert payload["profile_budgets"]["families"]["generic"]["direct_map"]["finding_count"] == 2


def test_build_quality_scorecard_infers_family_findings_when_missing_counts(tmp_path, monkeypatch):
    global_parser = tmp_path / "global_parser.json"
    global_parser.write_text(json.dumps({"projection": {"status": "PASS"}}), encoding="utf-8")

    global_validator = tmp_path / "global_validator.json"
    global_validator.write_text(json.dumps({"projection": {"status": "PASS"}}), encoding="utf-8")

    calibration = tmp_path / "calibration.json"
    calibration.write_text(json.dumps({"overall": {"precision": 0.9}}), encoding="utf-8")

    profile_budget = tmp_path / "profile_budget.json"
    profile_budget.write_text(
        json.dumps(
            {
                "finding_count": 1,
                "profiles": {
                    "generic": {
                        "families": {
                            "manual_review": {
                                "parsed_only_rate": 1.0,
                                "unsupported_rate": 0.0,
                                "budget": {"max_parsed_only_rate": 0.35, "max_unsupported_rate": 1.0},
                            },
                            "source_value_translation": {
                                "parsed_only_rate": 0.0,
                                "unsupported_rate": 0.2,
                                "budget": {"max_parsed_only_rate": 0.35, "max_unsupported_rate": 0.1},
                            },
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    trend = tmp_path / "trend.json"
    trend.write_text(json.dumps({"history": [{"report_id": "r1"}]}), encoding="utf-8")

    output = tmp_path / "scorecard.json"

    monkeypatch.setattr(
        "sys.argv",
        [
            "build_quality_scorecard.py",
            "--global-parser",
            str(global_parser),
            "--global-validator",
            str(global_validator),
            "--calibration",
            str(calibration),
            "--profile-budget",
            str(profile_budget),
            "--trend",
            str(trend),
            "--output",
            str(output),
        ],
    )

    assert build_quality_scorecard_main() == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["profile_budgets"]["family_finding_count"] == 2
    assert payload["profile_budgets"]["families"]["generic"]["manual_review"]["finding_count"] == 1
    assert payload["profile_budgets"]["families"]["generic"]["source_value_translation"]["finding_count"] == 1