import json
from pathlib import Path

from scripts.build_unknown_rule_triage import build_unknown_rule_triage


def test_unknown_rule_triage_clusters_unknown_rows_and_retrieves_known_examples():
    report = {
        "rule_decisions": [
            {
                "row": 1,
                "status": "unsupported",
                "confidence": 0.41,
                "family": "unknown",
                "condition": "If H201 startsWith GEN- then map to target",
                "target_xpath": "/a",
                "source_xpath": "/X12/TS_300/H2/H201",
                "reason": "unsupported",
            },
            {
                "row": 2,
                "status": "parsed_only",
                "confidence": 0.52,
                "family": "manual_review",
                "condition": "If H201 startsWith GEN- then map to target",
                "target_xpath": "/b",
                "source_xpath": "/X12/TS_300/H2/H201",
                "reason": "parsed only",
            },
            {
                "row": 3,
                "status": "enforced",
                "confidence": 0.96,
                "family": "startswith_replace_mapping",
                "condition": "If H201 startsWith ABC then map to target",
                "target_xpath": "/c",
                "source_xpath": "/X12/TS_300/H2/H201",
                "reason": "supported",
            },
        ]
    }

    calibration = {
        "buckets": [
            {
                "bucket": "0.8-0.9",
                "false_positive_rate": 0.03,
            }
        ]
    }

    payload = build_unknown_rule_triage(report, calibration=calibration, similarity_threshold=0.5)

    summary = payload.get("summary", {})
    assert summary.get("unknown_count") == 2
    assert summary.get("cluster_count") >= 1

    clusters = payload.get("clusters", [])
    assert clusters
    first_cluster = clusters[0]
    assert first_cluster.get("size", 0) >= 2

    rows = first_cluster.get("rows", [])
    assert rows
    assert any(row.get("nearest_known") for row in rows)
    assert isinstance(first_cluster.get("suggested_parser_patches"), list)


def test_unknown_rule_triage_payload_is_json_serializable(tmp_path: Path):
    report = {
        "rule_decisions": [
            {
                "row": 7,
                "status": "unsupported",
                "confidence": 0.2,
                "family": "unknown",
                "condition": "No Mapping",
                "target_xpath": "/x",
                "source_xpath": "",
                "reason": "instruction only",
            }
        ]
    }

    payload = build_unknown_rule_triage(report, calibration={}, similarity_threshold=0.5)
    out_path = tmp_path / "unknown_rule_triage.json"
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    loaded = json.loads(out_path.read_text(encoding="utf-8"))
    assert loaded.get("summary", {}).get("unknown_count") == 1
