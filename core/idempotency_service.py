from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_CACHE_PATH = Path(__file__).resolve().parents[1] / "results" / "intent_apply_idempotency_cache.json"
_MAX_ENTRIES = 500


def _load_cache(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"entries": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"entries": {}}
    if not isinstance(payload, dict):
        return {"entries": {}}
    entries = payload.get("entries") if isinstance(payload.get("entries"), dict) else {}
    return {"entries": entries}


def _save_cache(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _fingerprint(value: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def _trim_entries(entries: dict[str, Any], max_entries: int) -> dict[str, Any]:
    if len(entries) <= max_entries:
        return entries
    sortable: list[tuple[str, str]] = []
    for key, row in entries.items():
        stamp = ""
        if isinstance(row, dict):
            stamp = str(row.get("created_at_utc") or "")
        sortable.append((key, stamp))
    sortable.sort(key=lambda item: item[1])
    drop = len(entries) - max_entries
    for idx in range(drop):
        entries.pop(sortable[idx][0], None)
    return entries


def get_idempotent_response(
    *,
    idempotency_key: str,
    request_payload: dict[str, Any],
    cache_path: Path | None = None,
) -> dict[str, Any] | None:
    key = str(idempotency_key or "").strip()
    if not key:
        return None

    path = cache_path or _CACHE_PATH
    cache = _load_cache(path)
    entry = cache["entries"].get(key)
    if not isinstance(entry, dict):
        return None

    request_hash = _fingerprint(request_payload if isinstance(request_payload, dict) else {})
    stored_hash = str(entry.get("request_hash") or "")
    if stored_hash != request_hash:
        raise ValueError("idempotency_key was already used with a different request payload")

    response = entry.get("response") if isinstance(entry.get("response"), dict) else None
    if not response:
        return None

    replay = dict(response)
    replay["idempotency_replay"] = True
    replay["idempotency_key"] = key
    return replay


def store_idempotent_response(
    *,
    idempotency_key: str,
    request_payload: dict[str, Any],
    response_payload: dict[str, Any],
    cache_path: Path | None = None,
) -> None:
    key = str(idempotency_key or "").strip()
    if not key:
        return

    path = cache_path or _CACHE_PATH
    cache = _load_cache(path)
    entries = cache.get("entries") if isinstance(cache.get("entries"), dict) else {}

    entries[key] = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "request_hash": _fingerprint(request_payload if isinstance(request_payload, dict) else {}),
        "response": response_payload if isinstance(response_payload, dict) else {},
    }
    cache["entries"] = _trim_entries(entries, _MAX_ENTRIES)
    _save_cache(path, cache)
