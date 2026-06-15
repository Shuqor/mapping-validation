from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


_AUDIT_LOG_PATH = Path(__file__).resolve().parents[1] / "results" / "ai_agent_audit_events.jsonl"
_LEARNING_SUMMARY_PATH = Path(__file__).resolve().parents[1] / "results" / "ai_agent_learning_summary.json"
_POLICY_RULES_PATH = Path(__file__).resolve().parents[1] / "rules" / "agent_policy_rules.json"

_DEFAULT_POLICY_RULES = {
    "min_requests_before_enforce": 3,
    "precision_block_threshold": 0.6,
    "precision_warn_threshold": 0.75,
    "default_min_confidence": "medium",
    "block_min_confidence": "high",
}


def _stable_json(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _event_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()


def _load_json_dict(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _last_record_hash(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return str(payload.get("record_hash") or "").strip()
    return ""


def _policy_rules() -> dict[str, Any]:
    payload = _load_json_dict(_POLICY_RULES_PATH)
    candidate = payload.get("learning_policy") if isinstance(payload.get("learning_policy"), dict) else {}
    merged = dict(_DEFAULT_POLICY_RULES)
    merged.update(candidate)
    return merged


def _as_float(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _as_int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _normalize_confidence(value: Any, fallback: str = "medium") -> str:
    normalized = str(value or fallback).strip().lower()
    if normalized not in {"low", "medium", "high"}:
        return fallback
    return normalized


def _policy_decision(*, suggestion_precision: float, request_count: int) -> dict[str, Any]:
    rules = _policy_rules()
    min_requests = max(_as_int(rules.get("min_requests_before_enforce"), 3), 0)
    block_threshold = _as_float(rules.get("precision_block_threshold"), 0.6)
    warn_threshold = _as_float(rules.get("precision_warn_threshold"), 0.75)
    default_min_confidence = _normalize_confidence(rules.get("default_min_confidence"), "medium")
    block_min_confidence = _normalize_confidence(rules.get("block_min_confidence"), "high")

    if request_count < min_requests:
        return {
            "apply_allowed": True,
            "recommended_min_confidence": default_min_confidence,
            "reason": f"Warm-up mode: collected {request_count}/{min_requests} requests before strict apply gating.",
            "state": "warmup",
            "rules": {
                "min_requests_before_enforce": min_requests,
                "precision_block_threshold": block_threshold,
                "precision_warn_threshold": warn_threshold,
            },
        }

    if suggestion_precision < block_threshold:
        return {
            "apply_allowed": False,
            "recommended_min_confidence": block_min_confidence,
            "reason": "Apply is temporarily restricted because recent suggestion precision is below policy threshold.",
            "state": "blocked",
            "rules": {
                "min_requests_before_enforce": min_requests,
                "precision_block_threshold": block_threshold,
                "precision_warn_threshold": warn_threshold,
            },
        }

    if suggestion_precision < warn_threshold:
        return {
            "apply_allowed": True,
            "recommended_min_confidence": "high",
            "reason": "Apply is enabled with elevated confidence guard because precision is in warning range.",
            "state": "warning",
            "rules": {
                "min_requests_before_enforce": min_requests,
                "precision_block_threshold": block_threshold,
                "precision_warn_threshold": warn_threshold,
            },
        }

    return {
        "apply_allowed": True,
        "recommended_min_confidence": default_min_confidence,
        "reason": "Apply is enabled under current learning policy.",
        "state": "healthy",
        "rules": {
            "min_requests_before_enforce": min_requests,
            "precision_block_threshold": block_threshold,
            "precision_warn_threshold": warn_threshold,
        },
    }


def append_immutable_audit_event(
    *,
    event_type: str,
    actor: str,
    payload: dict[str, Any],
    log_path: Path | None = None,
) -> dict[str, Any]:
    target_path = log_path or _AUDIT_LOG_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)

    core_event = {
        "event_id": str(uuid4()),
        "event_type": str(event_type or "unspecified"),
        "actor": str(actor or "anonymous"),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "payload": payload if isinstance(payload, dict) else {},
        "prev_hash": _last_record_hash(target_path),
    }
    core_event["record_hash"] = _event_hash(core_event)

    with target_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(core_event, ensure_ascii=True) + "\n")

    return {
        "event_id": core_event["event_id"],
        "record_hash": core_event["record_hash"],
        "log_path": target_path.as_posix(),
    }


def update_learning_summary_from_apply_result(
    *,
    apply_result: dict[str, Any],
    actor: str,
    summary_path: Path | None = None,
) -> dict[str, Any]:
    target_path = summary_path or _LEARNING_SUMMARY_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)

    summary = _load_json_dict(target_path)
    totals = summary.get("totals") if isinstance(summary.get("totals"), dict) else {}
    actors = summary.get("actors") if isinstance(summary.get("actors"), dict) else {}
    skipped_reasons = summary.get("skipped_reasons") if isinstance(summary.get("skipped_reasons"), dict) else {}

    accepted_count = int(apply_result.get("accepted_count", 0) or 0)
    skipped_count = int(apply_result.get("skipped_count", 0) or 0)
    dry_run = bool(apply_result.get("dry_run", True))

    totals["requests"] = int(totals.get("requests", 0) or 0) + 1
    totals["dry_run_requests"] = int(totals.get("dry_run_requests", 0) or 0) + (1 if dry_run else 0)
    totals["apply_requests"] = int(totals.get("apply_requests", 0) or 0) + (0 if dry_run else 1)
    totals["accepted_patterns"] = int(totals.get("accepted_patterns", 0) or 0) + accepted_count
    totals["skipped_patterns"] = int(totals.get("skipped_patterns", 0) or 0) + skipped_count

    actor_key = str(actor or "anonymous").strip() or "anonymous"
    actors[actor_key] = int(actors.get(actor_key, 0) or 0) + 1

    skipped_entries = apply_result.get("skipped") if isinstance(apply_result.get("skipped"), list) else []
    for row in skipped_entries:
        if not isinstance(row, dict):
            continue
        reason = str(row.get("reason") or "unspecified")
        skipped_reasons[reason] = int(skipped_reasons.get(reason, 0) or 0) + 1

    accepted_total = int(totals.get("accepted_patterns", 0) or 0)
    rejected_total = max(int(totals.get("skipped_patterns", 0) or 0) - int(skipped_reasons.get("already_exists", 0) or 0), 0)
    suggestion_precision = (
        round(accepted_total / (accepted_total + rejected_total), 4)
        if (accepted_total + rejected_total) > 0
        else 1.0
    )

    policy = _policy_decision(
        suggestion_precision=suggestion_precision,
        request_count=int(totals.get("requests", 0) or 0),
    )
    recommended_min_confidence = policy["recommended_min_confidence"]

    summary_payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "totals": totals,
        "actors": actors,
        "skipped_reasons": skipped_reasons,
        "quality": {
            "suggestion_precision": suggestion_precision,
            "recommended_min_confidence": recommended_min_confidence,
        },
        "apply_guard": {
            "apply_allowed": bool(policy["apply_allowed"]),
            "reason": str(policy["reason"]),
            "recommended_min_confidence": recommended_min_confidence,
            "state": str(policy["state"]),
            "rules": dict(policy["rules"]),
        },
    }
    target_path.write_text(json.dumps(summary_payload, indent=2) + "\n", encoding="utf-8")

    return {
        "summary_path": target_path.as_posix(),
        "quality": dict(summary_payload["quality"]),
        "totals": dict(totals),
    }


def get_learning_policy_snapshot(*, summary_path: Path | None = None) -> dict[str, Any]:
    target_path = summary_path or _LEARNING_SUMMARY_PATH
    payload = _load_json_dict(target_path)

    totals_raw = payload.get("totals") if isinstance(payload.get("totals"), dict) else {}
    quality_raw = payload.get("quality") if isinstance(payload.get("quality"), dict) else {}
    actors_raw = payload.get("actors") if isinstance(payload.get("actors"), dict) else {}
    skipped_reasons_raw = payload.get("skipped_reasons") if isinstance(payload.get("skipped_reasons"), dict) else {}

    totals = {
        "requests": int(totals_raw.get("requests", 0) or 0),
        "dry_run_requests": int(totals_raw.get("dry_run_requests", 0) or 0),
        "apply_requests": int(totals_raw.get("apply_requests", 0) or 0),
        "accepted_patterns": int(totals_raw.get("accepted_patterns", 0) or 0),
        "skipped_patterns": int(totals_raw.get("skipped_patterns", 0) or 0),
    }
    request_count = int(totals.get("requests", 0) or 0)

    suggestion_precision = quality_raw.get("suggestion_precision", 1.0)
    try:
        normalized_precision = float(suggestion_precision)
    except (TypeError, ValueError):
        normalized_precision = 1.0

    policy = _policy_decision(suggestion_precision=normalized_precision, request_count=request_count)
    recommended_min_confidence = _normalize_confidence(
        quality_raw.get("recommended_min_confidence") or policy["recommended_min_confidence"],
        policy["recommended_min_confidence"],
    )

    return {
        "summary_path": target_path.as_posix(),
        "summary_exists": target_path.exists(),
        "generated_at_utc": str(payload.get("generated_at_utc") or ""),
        "quality": {
            "suggestion_precision": normalized_precision,
            "recommended_min_confidence": recommended_min_confidence,
        },
        "totals": totals,
        "apply_guard": {
            "apply_allowed": bool(policy["apply_allowed"]),
            "reason": str(policy["reason"]),
            "recommended_min_confidence": recommended_min_confidence,
            "state": str(policy["state"]),
            "rules": dict(policy["rules"]),
        },
        "actors_count": len(actors_raw),
        "skipped_reasons_count": len(skipped_reasons_raw),
    }


def get_audit_event_snapshot(
    *,
    limit: int = 20,
    log_path: Path | None = None,
    event_type: str | None = None,
    actor_contains: str | None = None,
) -> dict[str, Any]:
    target_path = log_path or _AUDIT_LOG_PATH
    safe_limit = max(1, min(int(limit or 20), 200))
    raw_lines: list[str] = []

    if target_path.exists():
        try:
            raw_lines = [line for line in target_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        except OSError:
            raw_lines = []

    events: list[dict[str, Any]] = []
    invalid_rows = 0
    for line in raw_lines:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            invalid_rows += 1
            continue
        if isinstance(payload, dict):
            events.append(payload)
        else:
            invalid_rows += 1

    hash_chain_valid = True
    chain_break_index = -1
    previous_hash = ""

    for idx, event in enumerate(events):
        expected_prev = str(event.get("prev_hash") or "")
        if expected_prev != previous_hash:
            hash_chain_valid = False
            chain_break_index = idx
            break

        recompute_payload = {
            "event_id": str(event.get("event_id") or ""),
            "event_type": str(event.get("event_type") or ""),
            "actor": str(event.get("actor") or ""),
            "generated_at_utc": str(event.get("generated_at_utc") or ""),
            "payload": event.get("payload") if isinstance(event.get("payload"), dict) else {},
            "prev_hash": expected_prev,
        }
        expected_hash = _event_hash(recompute_payload)
        actual_hash = str(event.get("record_hash") or "")
        if actual_hash != expected_hash:
            hash_chain_valid = False
            chain_break_index = idx
            break

        previous_hash = actual_hash

    normalized_event_type = str(event_type or "").strip().lower()
    normalized_actor_contains = str(actor_contains or "").strip().lower()

    filtered_events = events
    if normalized_event_type:
        filtered_events = [
            item
            for item in filtered_events
            if str(item.get("event_type") or "").strip().lower() == normalized_event_type
        ]
    if normalized_actor_contains:
        filtered_events = [
            item
            for item in filtered_events
            if normalized_actor_contains in str(item.get("actor") or "").strip().lower()
        ]

    recent_events = filtered_events[-safe_limit:]
    compact = [
        {
            "event_id": str(item.get("event_id") or ""),
            "event_type": str(item.get("event_type") or ""),
            "actor": str(item.get("actor") or ""),
            "generated_at_utc": str(item.get("generated_at_utc") or ""),
            "record_hash": str(item.get("record_hash") or ""),
        }
        for item in recent_events
    ]

    return {
        "log_path": target_path.as_posix(),
        "log_exists": target_path.exists(),
        "total_events": len(events),
        "matched_events": len(filtered_events),
        "filter": {
            "event_type": normalized_event_type,
            "actor_contains": normalized_actor_contains,
        },
        "invalid_rows": invalid_rows,
        "hash_chain_valid": hash_chain_valid,
        "chain_break_index": chain_break_index,
        "latest_record_hash": previous_hash if hash_chain_valid else "",
        "events": compact,
    }


def get_audit_health_snapshot(*, log_path: Path | None = None) -> dict[str, Any]:
    snapshot = get_audit_event_snapshot(limit=1, log_path=log_path)
    return {
        "status": "ok" if snapshot.get("hash_chain_valid") else "degraded",
        "log_exists": bool(snapshot.get("log_exists")),
        "total_events": int(snapshot.get("total_events", 0) or 0),
        "invalid_rows": int(snapshot.get("invalid_rows", 0) or 0),
        "hash_chain_valid": bool(snapshot.get("hash_chain_valid")),
        "chain_break_index": int(snapshot.get("chain_break_index", -1) or -1),
        "latest_record_hash": str(snapshot.get("latest_record_hash") or ""),
    }
