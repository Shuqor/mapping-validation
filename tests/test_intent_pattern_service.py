from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.intent_pattern_service import apply_approved_intent_patterns, rollback_intent_patterns_from_audit_event


def _write_semantic_config(path: Path) -> None:
    payload = {
        "profiles": {
            "generic": {
                "intent_patterns": {
                    "direct_map_comment_patterns": [
                        "\\bmust\\s+match\\b",
                    ]
                }
            }
        }
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_apply_approved_intent_patterns_dry_run_does_not_modify_file(tmp_path: Path) -> None:
    config_path = tmp_path / "semantic_profiles.json"
    audit_path = tmp_path / "ai_agent_audit_events.jsonl"
    summary_path = tmp_path / "ai_agent_learning_summary.json"
    _write_semantic_config(config_path)

    manifest = {
        "report_id": "rpt-1",
        "approved_patterns": [
            {
                "row": 12,
                "target_xpath": "/root/a",
                "proposed_regex": "\\bnew\\s+intent\\b",
                "confidence": "low",
            }
        ],
    }

    result = apply_approved_intent_patterns(
        manifest=manifest,
        dry_run=True,
        actor="qa-user",
        semantic_config_path=config_path,
        audit_log_path=audit_path,
        learning_summary_path=summary_path,
    )

    assert result["dry_run"] is True
    assert result["applied"] is False
    assert result["accepted_count"] == 1
    assert result["final_pattern_count"] == 2
    assert result["audit_event"]["event_id"]
    assert result["learning_summary"]["summary_path"].endswith("ai_agent_learning_summary.json")

    config_after = json.loads(config_path.read_text(encoding="utf-8"))
    patterns = config_after["profiles"]["generic"]["intent_patterns"]["direct_map_comment_patterns"]
    assert patterns == ["\\bmust\\s+match\\b"]
    assert audit_path.exists()
    assert summary_path.exists()


def test_apply_approved_intent_patterns_apply_writes_new_entries_and_skips_duplicates(tmp_path: Path) -> None:
    config_path = tmp_path / "semantic_profiles.json"
    audit_path = tmp_path / "ai_agent_audit_events.jsonl"
    summary_path = tmp_path / "ai_agent_learning_summary.json"
    _write_semantic_config(config_path)

    manifest = {
        "report_id": "rpt-2",
        "approved_patterns": [
            {"proposed_regex": "\\bmust\\s+match\\b"},
            {"proposed_regex": "\\b(?:"},
            {"proposed_regex": "\\bbrand\\s+new\\b"},
        ],
    }

    result = apply_approved_intent_patterns(
        manifest=manifest,
        dry_run=False,
        actor="ops-user",
        request_context={
            "source": "browser_flow",
            "session_id": "sess_demo",
            "page_origin": "http://localhost:8000",
            "validation_mode": "strict",
        },
        semantic_config_path=config_path,
        audit_log_path=audit_path,
        learning_summary_path=summary_path,
    )

    assert result["dry_run"] is False
    assert result["applied"] is True
    assert result["updated_by"] == "ops-user"
    assert result["accepted_count"] == 1
    assert result["skipped_count"] == 2
    assert result["final_pattern_count"] == 2

    reasons = {entry["reason"] for entry in result["skipped"]}
    assert "already_exists" in reasons
    assert "invalid_regex" in reasons

    config_after = json.loads(config_path.read_text(encoding="utf-8"))
    patterns = config_after["profiles"]["generic"]["intent_patterns"]["direct_map_comment_patterns"]
    assert patterns == ["\\bmust\\s+match\\b", "\\bbrand\\s+new\\b"]

    audit_lines = [line for line in audit_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(audit_lines) == 1
    audit_event = json.loads(audit_lines[0])
    assert audit_event["payload"]["request_context"]["source"] == "browser_flow"
    assert audit_event["payload"]["request_context"]["session_id"] == "sess_demo"
    summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary_payload["totals"]["requests"] == 1
    assert summary_payload["totals"]["accepted_patterns"] == 1


def test_apply_approved_intent_patterns_audit_log_is_append_only(tmp_path: Path) -> None:
    config_path = tmp_path / "semantic_profiles.json"
    audit_path = tmp_path / "ai_agent_audit_events.jsonl"
    summary_path = tmp_path / "ai_agent_learning_summary.json"
    _write_semantic_config(config_path)

    first = {
        "report_id": "rpt-3",
        "approved_patterns": [{"proposed_regex": "\\balpha\\b"}],
    }
    second = {
        "report_id": "rpt-4",
        "approved_patterns": [{"proposed_regex": "\\bbeta\\b"}],
    }

    apply_approved_intent_patterns(
        manifest=first,
        dry_run=True,
        actor="ops-user",
        semantic_config_path=config_path,
        audit_log_path=audit_path,
        learning_summary_path=summary_path,
    )
    apply_approved_intent_patterns(
        manifest=second,
        dry_run=True,
        actor="ops-user",
        semantic_config_path=config_path,
        audit_log_path=audit_path,
        learning_summary_path=summary_path,
    )

    lines = [line for line in audit_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 2
    first_event = json.loads(lines[0])
    second_event = json.loads(lines[1])
    assert second_event["prev_hash"] == first_event["record_hash"]


def test_rollback_intent_patterns_from_audit_event_removes_patterns(tmp_path: Path) -> None:
    config_path = tmp_path / "semantic_profiles.json"
    audit_path = tmp_path / "ai_agent_audit_events.jsonl"
    summary_path = tmp_path / "ai_agent_learning_summary.json"
    _write_semantic_config(config_path)

    apply_result = apply_approved_intent_patterns(
        manifest={
            "report_id": "rpt-rollback-1",
            "approved_patterns": [{"proposed_regex": "\\bto\\s+remove\\b"}],
        },
        dry_run=False,
        actor="ops-user",
        semantic_config_path=config_path,
        audit_log_path=audit_path,
        learning_summary_path=summary_path,
    )

    event_id = apply_result["audit_event"]["event_id"]
    rollback_result = rollback_intent_patterns_from_audit_event(
        event_id=event_id,
        dry_run=False,
        actor="ops-user",
        semantic_config_path=config_path,
        audit_log_path=audit_path,
    )

    assert rollback_result["applied"] is True
    assert rollback_result["removed_count"] == 1
    assert "\\bto\\s+remove\\b" in rollback_result["removed_patterns"]

    config_after = json.loads(config_path.read_text(encoding="utf-8"))
    patterns = config_after["profiles"]["generic"]["intent_patterns"]["direct_map_comment_patterns"]
    assert patterns == ["\\bmust\\s+match\\b"]


def test_rollback_intent_patterns_requires_apply_event_id(tmp_path: Path) -> None:
    config_path = tmp_path / "semantic_profiles.json"
    audit_path = tmp_path / "ai_agent_audit_events.jsonl"
    summary_path = tmp_path / "ai_agent_learning_summary.json"
    _write_semantic_config(config_path)

    apply_result = apply_approved_intent_patterns(
        manifest={
            "report_id": "rpt-rollback-2",
            "approved_patterns": [{"proposed_regex": "\\balpha\\b"}],
        },
        dry_run=True,
        actor="ops-user",
        semantic_config_path=config_path,
        audit_log_path=audit_path,
        learning_summary_path=summary_path,
    )
    source_event_id = apply_result["audit_event"]["event_id"]

    rollback_intent_patterns_from_audit_event(
        event_id=source_event_id,
        dry_run=False,
        actor="ops-user",
        semantic_config_path=config_path,
        audit_log_path=audit_path,
    )

    lines = [line for line in audit_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    rollback_event_id = json.loads(lines[-1])["event_id"]

    with pytest.raises(ValueError, match="requires an intent_pattern_apply"):
        rollback_intent_patterns_from_audit_event(
            event_id=rollback_event_id,
            dry_run=False,
            actor="ops-user",
            semantic_config_path=config_path,
            audit_log_path=audit_path,
        )
