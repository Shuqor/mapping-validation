from __future__ import annotations

import json
import re
import hashlib
from pathlib import Path
from typing import Any

from core.agent_learning_service import append_immutable_audit_event, update_learning_summary_from_apply_result


_SEMANTIC_PROFILES_CONFIG_PATH = Path(__file__).resolve().parents[1] / "rules" / "semantic_profiles.json"


def _normalize_pattern_key(pattern: str) -> str:
    return re.sub(r"\s+", "", str(pattern or "").strip().lower())


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path.as_posix()}")
    return payload


def _file_checksum(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise ValueError(f"Unable to read {path.as_posix()}: {exc}") from exc


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
    request_context: dict[str, Any] | None = None,
    semantic_config_path: Path | None = None,
    audit_log_path: Path | None = None,
    learning_summary_path: Path | None = None,
) -> dict[str, Any]:
    if not isinstance(manifest, dict):
        raise ValueError("manifest must be a JSON object")

    config_path = semantic_config_path or _SEMANTIC_PROFILES_CONFIG_PATH
    initial_checksum = _file_checksum(config_path)
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
        current_checksum = _file_checksum(config_path)
        if current_checksum != initial_checksum:
            raise ValueError(
                "Semantic profile changed during apply request. Retry with a fresh request to avoid overwriting concurrent updates."
            )
        config_payload["profiles"]["generic"]["intent_patterns"]["direct_map_comment_patterns"] = final_patterns
        config_path.write_text(json.dumps(config_payload, indent=2) + "\n", encoding="utf-8")
        applied = True

    updated_by = str(actor or "").strip() or "anonymous"
    context = request_context if isinstance(request_context, dict) else {}
    safe_request_context = {
        "source": str(context.get("source") or "").strip(),
        "environment": str(context.get("environment") or "").strip(),
        "session_id": str(context.get("session_id") or "").strip(),
        "pipeline_run_id": str(context.get("pipeline_run_id") or "").strip(),
        "client_version": str(context.get("client_version") or "").strip(),
        "page_origin": str(context.get("page_origin") or "").strip(),
        "validation_mode": str(context.get("validation_mode") or "").strip(),
        "policy_confidence": str(context.get("policy_confidence") or "").strip().lower(),
    }
    safe_request_context = {key: value for key, value in safe_request_context.items() if value}

    result_payload = {
        "status": "preview" if dry_run else "applied",
        "dry_run": bool(dry_run),
        "report_id": str(manifest.get("report_id") or "").strip(),
        "updated_by": updated_by,
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

    audit_event = append_immutable_audit_event(
        event_type="intent_pattern_apply",
        actor=updated_by,
        payload={
            "dry_run": bool(dry_run),
            "report_id": result_payload["report_id"],
            "accepted_count": len(accepted),
            "skipped_count": len(skipped),
            "applied": bool(applied),
            "accepted_patterns": accepted_patterns,
            "skipped_reasons": [str(item.get("reason") or "unspecified") for item in skipped],
            "request_context": safe_request_context,
        },
        log_path=audit_log_path,
    )
    learning_summary = update_learning_summary_from_apply_result(
        apply_result=result_payload,
        actor=updated_by,
        summary_path=learning_summary_path,
    )

    result_payload["audit_event"] = audit_event
    result_payload["learning_summary"] = learning_summary
    return result_payload


def rollback_intent_patterns_from_audit_event(
    *,
    event_id: str,
    dry_run: bool = True,
    actor: str | None = None,
    semantic_config_path: Path | None = None,
    audit_log_path: Path | None = None,
) -> dict[str, Any]:
    target_event_id = str(event_id or "").strip()
    if not target_event_id:
        raise ValueError("event_id is required")

    config_path = semantic_config_path or _SEMANTIC_PROFILES_CONFIG_PATH
    audit_path = audit_log_path or (Path(__file__).resolve().parents[1] / "results" / "ai_agent_audit_events.jsonl")
    if not audit_path.exists():
        raise ValueError(f"Audit log not found at {audit_path.as_posix()}")

    selected_event: dict[str, Any] | None = None
    for line in audit_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        if str(payload.get("event_id") or "").strip() == target_event_id:
            selected_event = payload
            break

    if selected_event is None:
        raise ValueError(f"event_id not found in audit log: {target_event_id}")

    selected_event_type = str(selected_event.get("event_type") or "").strip().lower()
    if selected_event_type != "intent_pattern_apply":
        raise ValueError("rollback requires an intent_pattern_apply event_id")

    event_payload = selected_event.get("payload") if isinstance(selected_event.get("payload"), dict) else {}
    accepted_patterns = [
        str(item).strip()
        for item in (event_payload.get("accepted_patterns") if isinstance(event_payload.get("accepted_patterns"), list) else [])
        if str(item).strip()
    ]
    if not accepted_patterns:
        return {
            "status": "preview" if dry_run else "applied",
            "dry_run": bool(dry_run),
            "event_id": target_event_id,
            "updated_by": str(actor or "").strip() or "anonymous",
            "semantic_config_path": config_path.as_posix(),
            "removed_count": 0,
            "removed_patterns": [],
            "applied": False,
        }

    initial_checksum = _file_checksum(config_path)
    config_payload = _load_json_object(config_path)
    existing_patterns, schema_notes = _ensure_semantic_schema(config_payload)
    removal_keys = {_normalize_pattern_key(item) for item in accepted_patterns}

    kept_patterns: list[str] = []
    removed_patterns: list[str] = []
    for pattern in existing_patterns:
        if _normalize_pattern_key(pattern) in removal_keys:
            removed_patterns.append(pattern)
        else:
            kept_patterns.append(pattern)

    applied = False
    if not dry_run and (removed_patterns or schema_notes):
        current_checksum = _file_checksum(config_path)
        if current_checksum != initial_checksum:
            raise ValueError(
                "Semantic profile changed during rollback request. Retry with a fresh request to avoid overwriting concurrent updates."
            )
        config_payload["profiles"]["generic"]["intent_patterns"]["direct_map_comment_patterns"] = kept_patterns
        config_path.write_text(json.dumps(config_payload, indent=2) + "\n", encoding="utf-8")
        applied = True

    updated_by = str(actor or "").strip() or "anonymous"
    result_payload = {
        "status": "preview" if dry_run else "applied",
        "dry_run": bool(dry_run),
        "event_id": target_event_id,
        "updated_by": updated_by,
        "semantic_config_path": config_path.as_posix(),
        "removed_count": len(removed_patterns),
        "removed_patterns": removed_patterns,
        "applied": applied,
    }

    append_immutable_audit_event(
        event_type="intent_pattern_rollback",
        actor=updated_by,
        payload={
            "source_event_id": target_event_id,
            "dry_run": bool(dry_run),
            "removed_count": len(removed_patterns),
            "removed_patterns": removed_patterns,
            "applied": bool(applied),
        },
        log_path=audit_log_path,
    )

    return result_payload
