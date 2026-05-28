from __future__ import annotations

import json
from pathlib import Path

from core.intent_pattern_service import apply_approved_intent_patterns


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
    )

    assert result["dry_run"] is True
    assert result["applied"] is False
    assert result["accepted_count"] == 1
    assert result["final_pattern_count"] == 2

    config_after = json.loads(config_path.read_text(encoding="utf-8"))
    patterns = config_after["profiles"]["generic"]["intent_patterns"]["direct_map_comment_patterns"]
    assert patterns == ["\\bmust\\s+match\\b"]


def test_apply_approved_intent_patterns_apply_writes_new_entries_and_skips_duplicates(tmp_path: Path) -> None:
    config_path = tmp_path / "semantic_profiles.json"
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
        semantic_config_path=config_path,
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
