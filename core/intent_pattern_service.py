from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


_SEMANTIC_PROFILES_CONFIG_PATH = Path(__file__).resolve().parents[1] / "rules" / "semantic_profiles.json"


def _normalize_pattern_key(pattern: str) -> str:
    return re.sub(r"\s+", "", str(pattern or "").strip().lower())


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path.as_posix()}")
    return payload


def _ensure_semantic_schema(config: dict[str, Any]) -> tuple[list[str], list[str]]:
    notes: list[str] = []
    if not isinstance(config.get("profiles"), dict):
        config["profiles"] = {}
        notes.append("Created missing top-level profiles object")

    profiles = config["profiles"]
    if not isinstance(profiles.get("generic"), dict):
        profiles["generic"] = {}
        notes.append("Created missing profiles.generic object")

    generic = profiles["generic"]
    if not isinstance(generic.get("intent_patterns"), dict):
        generic["intent_patterns"] = {}
        notes.append("Created missing profiles.generic.intent_patterns object")

    intent_patterns = generic["intent_patterns"]
    if not isinstance(intent_patterns.get("direct_map_comment_patterns"), list):
        intent_patterns["direct_map_comment_patterns"] = []
        notes.append("Created missing direct_map_comment_patterns list")

    patterns = [
        str(item).strip()
        for item in intent_patterns.get("direct_map_comment_patterns", [])
        if str(item).strip()
    ]
    return patterns, notes


def _coerce_approved_entries(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    approved_raw = manifest.get("approved_patterns")
    if not isinstance(approved_raw, list):
        return []

    approved: list[dict[str, Any]] = []
    for item in approved_raw:
        if isinstance(item, dict):
            approved.append(dict(item))
        else:
            approved.append({"proposed_regex": str(item or "")})
    return approved


def apply_approved_intent_patterns(
    *,
    manifest: dict[str, Any],
    dry_run: bool = True,
    actor: str | None = None,
    semantic_config_path: Path | None = None,
) -> dict[str, Any]:
    if not isinstance(manifest, dict):
        raise ValueError("manifest must be a JSON object")

    config_path = semantic_config_path or _SEMANTIC_PROFILES_CONFIG_PATH
    config_payload = _load_json_object(config_path)
    existing_patterns, schema_notes = _ensure_semantic_schema(config_payload)
    existing_keys = {_normalize_pattern_key(pattern) for pattern in existing_patterns}

    accepted: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for item in _coerce_approved_entries(manifest):
        proposed_regex = str(item.get("proposed_regex") or "").strip()
        normalized_key = _normalize_pattern_key(proposed_regex)

        if not proposed_regex:
            skipped.append({
                "row": item.get("row"),
                "target_xpath": str(item.get("target_xpath") or "").strip(),
                "proposed_regex": proposed_regex,
                "reason": "missing_proposed_regex",
            })
            continue

        try:
            re.compile(proposed_regex)
        except re.error as exc:
            skipped.append({
                "row": item.get("row"),
                "target_xpath": str(item.get("target_xpath") or "").strip(),
                "proposed_regex": proposed_regex,
                "reason": "invalid_regex",
                "details": str(exc),
            })
            continue

        if normalized_key in existing_keys:
            skipped.append({
                "row": item.get("row"),
                "target_xpath": str(item.get("target_xpath") or "").strip(),
                "proposed_regex": proposed_regex,
                "reason": "already_exists",
            })
            continue

        accepted.append({
            "row": item.get("row"),
            "target_xpath": str(item.get("target_xpath") or "").strip(),
            "condition": str(item.get("condition") or "").strip(),
            "family": str(item.get("family") or "").strip(),
            "confidence": str(item.get("confidence") or "").strip().lower(),
            "proposed_regex": proposed_regex,
        })
        existing_keys.add(normalized_key)

    accepted_patterns = [entry["proposed_regex"] for entry in accepted]
    final_patterns = list(dict.fromkeys([*existing_patterns, *accepted_patterns]))

    applied = False
    if not dry_run and (accepted_patterns or schema_notes):
        config_payload["profiles"]["generic"]["intent_patterns"]["direct_map_comment_patterns"] = final_patterns
        config_path.write_text(json.dumps(config_payload, indent=2) + "\n", encoding="utf-8")
        applied = True

    return {
        "status": "preview" if dry_run else "applied",
        "dry_run": bool(dry_run),
        "report_id": str(manifest.get("report_id") or "").strip(),
        "updated_by": str(actor or "").strip() or "anonymous",
        "semantic_config_path": config_path.as_posix(),
        "schema_notes": schema_notes,
        "existing_pattern_count": len(existing_patterns),
        "accepted_count": len(accepted),
        "skipped_count": len(skipped),
        "final_pattern_count": len(final_patterns),
        "applied": applied,
        "accepted": accepted,
        "skipped": skipped,
        "scope_note": "Applies to the shared semantic profile file on this deployment environment.",
    }
