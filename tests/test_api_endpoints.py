from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from api import app
from core.agent_learning_service import append_immutable_audit_event
from core.intent_pattern_service import apply_approved_intent_patterns


client = TestClient(app)


def _agent_sample_report() -> dict:
    return {
        "report_id": "agent-rpt-1",
        "rule_decisions": [
            {
                "row": 5,
                "target_xpath": "/shipment/id",
                "rule_family": "if_then_condition",
                "decision_status": "unsupported",
                "decision_reason": "ambiguous condition family",
                "decision_confidence": "medium",
                "remediation_hint": "Use explicit if <cond> then map <target>",
            },
            {
                "row": 6,
                "target_xpath": "/shipment/date",
                "rule_family": "direct_map_comment",
                "decision_status": "parsed_only",
                "decision_reason": "no canonical pattern matched",
                "decision_confidence": "high",
            },
        ],
        "skipped_rules": [
            {
                "row": 5,
                "target_xpath": "/shipment/id",
                "condition": "if segment A then map B",
                "nearest_family": "if_then_condition",
                "ambiguous_families": ["if_then_condition", "segment_scope"],
                "suggested_canonical_rewrite": "If SEG=A then map /shipment/id from B",
                "similarity_score": 0.71,
                "nearest_patterns": [{"pattern": "^if\\s+.+then\\s+map", "confidence": "medium"}],
            }
        ],
    }


def test_learning_policy_endpoint_returns_defaults_when_summary_missing(tmp_path) -> None:
    summary_path = tmp_path / "missing_summary.json"

    response = client.get(
        "/intent-patterns/learning-policy",
        params={"summary_path": str(summary_path)},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary_exists"] is False
    assert payload["quality"]["recommended_min_confidence"] == "medium"
    assert payload["apply_guard"]["apply_allowed"] is True
    assert payload["apply_guard"]["state"] == "warmup"
    assert payload["apply_guard"]["rules"]["min_requests_before_enforce"] == 3
    assert payload["totals"]["requests"] == 0


def test_learning_policy_endpoint_reads_existing_summary(tmp_path) -> None:
    summary_path = tmp_path / "learning_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "generated_at_utc": "2026-01-01T00:00:00+00:00",
                "totals": {
                    "requests": 3,
                    "dry_run_requests": 2,
                    "apply_requests": 1,
                    "accepted_patterns": 5,
                    "skipped_patterns": 4,
                },
                "actors": {"ops-user": 3},
                "skipped_reasons": {"invalid_regex": 1},
                "quality": {
                    "suggestion_precision": 0.55,
                    "recommended_min_confidence": "high",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    response = client.get(
        "/intent-patterns/learning-policy",
        params={"summary_path": str(summary_path)},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary_exists"] is True
    assert payload["quality"]["suggestion_precision"] == 0.55
    assert payload["quality"]["recommended_min_confidence"] == "high"
    assert payload["apply_guard"]["apply_allowed"] is False
    assert payload["apply_guard"]["recommended_min_confidence"] == "high"
    assert payload["apply_guard"]["state"] == "blocked"
    assert payload["totals"]["accepted_patterns"] == 5
    assert payload["actors_count"] == 1
    assert payload["skipped_reasons_count"] == 1


def test_audit_health_endpoint_reports_ok_when_hash_chain_valid(tmp_path: Path) -> None:
    audit_path = tmp_path / "audit_health_ok.jsonl"
    append_immutable_audit_event(
        event_type="intent_pattern_apply",
        actor="ops",
        payload={"accepted_count": 1},
        log_path=audit_path,
    )

    response = client.get("/health/audit", params={"log_path": str(audit_path)})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["hash_chain_valid"] is True
    assert payload["total_events"] == 1


def test_audit_events_endpoint_returns_hash_chain_snapshot(tmp_path: Path) -> None:
    audit_path = tmp_path / "audit.jsonl"
    append_immutable_audit_event(
        event_type="intent_pattern_apply",
        actor="ops",
        payload={"accepted_count": 1},
        log_path=audit_path,
    )
    append_immutable_audit_event(
        event_type="intent_pattern_apply",
        actor="ops",
        payload={"accepted_count": 2},
        log_path=audit_path,
    )

    response = client.get(
        "/intent-patterns/audit-events",
        params={"log_path": str(audit_path), "limit": 1},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["log_exists"] is True
    assert payload["total_events"] == 2
    assert payload["matched_events"] == 2
    assert payload["hash_chain_valid"] is True
    assert len(payload["events"]) == 1
    assert payload["events"][0]["event_type"] == "intent_pattern_apply"


def test_audit_events_endpoint_supports_event_type_and_actor_filters(tmp_path: Path) -> None:
    audit_path = tmp_path / "audit_filtered.jsonl"
    append_immutable_audit_event(
        event_type="intent_pattern_apply",
        actor="web-ui:sess_a",
        payload={"accepted_count": 1},
        log_path=audit_path,
    )
    append_immutable_audit_event(
        event_type="intent_pattern_apply",
        actor="ops-user",
        payload={"accepted_count": 2},
        log_path=audit_path,
    )
    append_immutable_audit_event(
        event_type="intent_pattern_review",
        actor="web-ui:sess_b",
        payload={"accepted_count": 0},
        log_path=audit_path,
    )

    response = client.get(
        "/intent-patterns/audit-events",
        params={
            "log_path": str(audit_path),
            "event_type": "intent_pattern_apply",
            "actor_contains": "web-ui",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_events"] == 3
    assert payload["matched_events"] == 1
    assert payload["filter"]["event_type"] == "intent_pattern_apply"
    assert payload["filter"]["actor_contains"] == "web-ui"
    assert len(payload["events"]) == 1
    assert payload["events"][0]["actor"].startswith("web-ui:")


def test_audit_events_endpoint_reports_chain_break(tmp_path: Path) -> None:
    audit_path = tmp_path / "audit_broken.jsonl"
    append_immutable_audit_event(
        event_type="intent_pattern_apply",
        actor="ops",
        payload={"accepted_count": 1},
        log_path=audit_path,
    )
    lines = [line for line in audit_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    event = json.loads(lines[0])
    event["prev_hash"] = "tampered"
    audit_path.write_text(json.dumps(event) + "\n", encoding="utf-8")

    response = client.get(
        "/intent-patterns/audit-events",
        params={"log_path": str(audit_path)},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["hash_chain_valid"] is False
    assert payload["chain_break_index"] == 0

    health_response = client.get("/health/audit", params={"log_path": str(audit_path)})
    assert health_response.status_code == 200
    assert health_response.json()["status"] == "degraded"


def test_apply_endpoint_blocks_apply_when_policy_guard_is_disabled(tmp_path: Path) -> None:
    summary_path = tmp_path / "learning_summary_blocked.json"
    summary_path.write_text(
        json.dumps(
            {
                "totals": {
                    "requests": 5,
                    "dry_run_requests": 2,
                    "apply_requests": 3,
                    "accepted_patterns": 2,
                    "skipped_patterns": 10,
                },
                "quality": {
                    "suggestion_precision": 0.2,
                    "recommended_min_confidence": "high",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    config_path = tmp_path / "semantic_profiles.json"
    config_path.write_text(
        json.dumps(
            {
                "profiles": {
                    "generic": {
                        "intent_patterns": {
                            "direct_map_comment_patterns": ["\\bmust\\s+match\\b"]
                        }
                    }
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    response = client.post(
        "/intent-patterns/apply-approved",
        json={
            "manifest": {
                "report_id": "blocked-rpt",
                "approved_patterns": [{"proposed_regex": "\\bnew\\b"}],
            },
            "dry_run": False,
            "semantic_config_path": str(config_path),
            "learning_summary_path": str(summary_path),
        },
    )

    assert response.status_code == 409
    assert "temporarily restricted" in response.json()["detail"].lower()


def test_apply_endpoint_idempotency_replays_without_second_apply(tmp_path: Path) -> None:
    config_path = tmp_path / "semantic_profiles_idempotent.json"
    config_path.write_text(
        json.dumps(
            {
                "profiles": {
                    "generic": {
                        "intent_patterns": {
                            "direct_map_comment_patterns": ["\\bmust\\s+match\\b"]
                        }
                    }
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    audit_path = tmp_path / "audit_idempotent.jsonl"
    summary_path = tmp_path / "summary_idempotent.json"
    cache_path = tmp_path / "idempotency_cache.json"

    payload = {
        "manifest": {
            "report_id": "idem-rpt",
            "approved_patterns": [{"proposed_regex": "\\bnew\\b"}],
        },
        "dry_run": True,
        "idempotency_key": "idem-123",
        "semantic_config_path": str(config_path),
        "audit_log_path": str(audit_path),
        "learning_summary_path": str(summary_path),
        "idempotency_cache_path": str(cache_path),
    }

    first = client.post("/intent-patterns/apply-approved", json=payload)
    second = client.post("/intent-patterns/apply-approved", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["idempotency_replay"] is False
    assert second.json()["idempotency_replay"] is True

    lines = [line for line in audit_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 1


def test_rollback_endpoint_removes_patterns_from_selected_apply_event(tmp_path: Path) -> None:
    config_path = tmp_path / "semantic_profiles_rollback.json"
    config_path.write_text(
        json.dumps(
            {
                "profiles": {
                    "generic": {
                        "intent_patterns": {
                            "direct_map_comment_patterns": ["\\bmust\\s+match\\b"]
                        }
                    }
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    audit_path = tmp_path / "audit_rollback.jsonl"
    summary_path = tmp_path / "summary_rollback.json"

    apply_result = apply_approved_intent_patterns(
        manifest={
            "report_id": "rpt-rollback",
            "approved_patterns": [{"proposed_regex": "\\brollback\\b"}],
        },
        dry_run=False,
        actor="ops-user",
        semantic_config_path=config_path,
        audit_log_path=audit_path,
        learning_summary_path=summary_path,
    )
    event_id = apply_result["audit_event"]["event_id"]

    response = client.post(
        "/intent-patterns/rollback-audit-event",
        json={
            "event_id": event_id,
            "dry_run": False,
            "actor": "ops-user",
            "semantic_config_path": str(config_path),
            "audit_log_path": str(audit_path),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["applied"] is True
    assert payload["removed_count"] == 1

    config_after = json.loads(config_path.read_text(encoding="utf-8"))
    patterns = config_after["profiles"]["generic"]["intent_patterns"]["direct_map_comment_patterns"]
    assert patterns == ["\\bmust\\s+match\\b"]


def test_agent_recommend_actions_endpoint_returns_ranked_actions() -> None:
    response = client.post("/agent/recommend-actions", json=_agent_sample_report())

    assert response.status_code == 200
    payload = response.json()
    assert payload["report_id"] == "agent-rpt-1"
    assert payload["total_recommendations"] >= 1
    first = payload["recommendations"][0]
    assert first["recommended_action"] in {
        "clarify_family_then_apply",
        "rewrite_to_supported_family",
        "promote_with_guarded_apply",
    }
    assert "guided_fix" in first


def test_agent_multi_hypothesis_endpoint_returns_alternatives() -> None:
    response = client.post("/agent/multi-hypothesis", json=_agent_sample_report())

    assert response.status_code == 200
    payload = response.json()
    assert payload["report_id"] == "agent-rpt-1"
    assert payload["total_items"] >= 1
    item = payload["items"][0]
    assert "hypotheses" in item
    assert isinstance(item["hypotheses"], list)


def test_agent_evidence_graph_endpoint_returns_nodes_and_edges() -> None:
    response = client.post("/agent/evidence-graph", json=_agent_sample_report())

    assert response.status_code == 200
    payload = response.json()
    assert payload["report_id"] == "agent-rpt-1"
    assert payload["node_count"] >= 1
    assert payload["edge_count"] >= 1
    assert isinstance(payload["nodes"], list)
    assert isinstance(payload["edges"], list)
