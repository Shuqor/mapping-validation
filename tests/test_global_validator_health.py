from scripts.check_global_validator_health import evaluate_global_validator_health


def test_evaluate_global_validator_health_accepts_clean_projection():
    projection = {
        "rules_folder": {
            "spec_count": 2,
            "failure_count": 0,
            "total_ambiguities": 0,
            "status_counts": {"clean": 2},
            "confidence_counts": {"high": 2},
        },
        "curated_runtime": {
            "run_count": 2,
            "success_count": 2,
            "failure_count": 0,
            "failures": [],
            "status_counts": {"PASS_WITH_WARNINGS": 2},
            "total_errors": 8,
            "total_unsupported_rules": 0,
            "total_checked_rules": 84,
            "performance": {
                "p95_runtime_seconds": 0.42,
                "max_runtime_seconds": 0.44,
                "max_p95_runtime_seconds": 1.0,
            },
            "runs": [
                {"id": "xml_lenient", "status": "PASS_WITH_WARNINGS", "runtime_seconds": 0.44},
                {"id": "x12_lenient", "status": "PASS_WITH_WARNINGS", "runtime_seconds": 0.41},
            ],
        },
    }

    assert evaluate_global_validator_health(projection) == []


def test_evaluate_global_validator_health_reports_failures_and_ambiguities():
    projection = {
        "rules_folder": {
            "spec_count": 2,
            "failure_count": 1,
            "total_ambiguities": 3,
        },
        "curated_runtime": {
            "run_count": 2,
            "success_count": 1,
            "failure_count": 1,
            "runs": [{"id": "xml", "status": "FAIL", "runtime_seconds": 1.2}],
            "performance": {
                "p95_runtime_seconds": 2.2,
                "max_runtime_seconds": 2.2,
                "max_p95_runtime_seconds": 1.0,
            },
        },
    }

    issues = evaluate_global_validator_health(projection)
    assert any("rules_folder.failure_count=1" in issue for issue in issues)
    assert any("rules_folder.total_ambiguities=3" in issue for issue in issues)
    assert any("curated_runtime.failure_count=1" in issue for issue in issues)
    assert any("disallowed statuses" in issue for issue in issues)
    assert any("p95_runtime_seconds=" in issue for issue in issues)
