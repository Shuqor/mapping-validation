from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from core.agent_learning_service import get_audit_event_snapshot, get_audit_health_snapshot, get_learning_policy_snapshot
from core.api_service import validate_uploaded_payloads
from core.idempotency_service import get_idempotent_response, store_idempotent_response
from core.intent_pattern_service import apply_approved_intent_patterns, rollback_intent_patterns_from_audit_event


app = FastAPI(title="Mapping Validation API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


_CONFIDENCE_RANK = {"low": 1, "medium": 2, "high": 3}


def _normalize_confidence(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in _CONFIDENCE_RANK:
        return normalized
    return "medium"


def _as_report_payload(payload: dict) -> dict:
    report = payload.get("report")
    if isinstance(report, dict):
        return report
    return payload


def _skipped_rules_by_row(report: dict) -> dict[int, dict]:
    index: dict[int, dict] = {}
    for item in report.get("skipped_rules") or []:
        if not isinstance(item, dict):
            continue
        row = int(item.get("row") or 0)
        if row > 0:
            index[row] = item
    return index


def _build_agent_recommendations(report: dict, limit: int = 50) -> dict:
    recommendations: list[dict] = []
    skipped_index = _skipped_rules_by_row(report)

    for entry in report.get("rule_decisions") or []:
        if not isinstance(entry, dict):
            continue
        status = str(entry.get("decision_status") or "").strip().lower()
        if status not in {"parsed_only", "unsupported"}:
            continue

        row = int(entry.get("row") or 0)
        skipped = skipped_index.get(row, {})
        family = str(entry.get("rule_family") or skipped.get("nearest_family") or skipped.get("family") or "").strip()
        confidence = _normalize_confidence(entry.get("decision_confidence") or skipped.get("similarity_confidence"))
        alternatives = skipped.get("ambiguous_families") if isinstance(skipped.get("ambiguous_families"), list) else []
        remediation = str(entry.get("remediation_hint") or "").strip() or str(skipped.get("suggested_canonical_rewrite") or "").strip()
        reason = str(entry.get("decision_reason") or "").strip()

        action = "rewrite_to_supported_family"
        if alternatives and len(alternatives) > 1:
            action = "clarify_family_then_apply"
        elif status == "parsed_only" and _CONFIDENCE_RANK.get(confidence, 2) >= _CONFIDENCE_RANK["high"]:
            action = "promote_with_guarded_apply"

        priority = 90 if status == "unsupported" else 70
        if "ambig" in reason.lower():
            priority += 5
        if _CONFIDENCE_RANK.get(confidence, 2) == _CONFIDENCE_RANK["high"]:
            priority -= 5

        recommendations.append(
            {
                "row": row,
                "target_xpath": str(entry.get("target_xpath") or skipped.get("target_xpath") or "").strip(),
                "rule_family": family,
                "status": status,
                "reason": reason,
                "recommended_action": action,
                "confidence": confidence,
                "priority": max(1, min(100, priority)),
                "alternatives": [str(v).strip() for v in alternatives if str(v).strip()][:5],
                "guided_fix": remediation,
            }
        )

    recommendations.sort(key=lambda item: (-int(item.get("priority") or 0), int(item.get("row") or 0)))
    sliced = recommendations[: max(1, min(limit, 200))]
    return {
        "report_id": str(report.get("report_id") or "").strip(),
        "total_recommendations": len(sliced),
        "recommendations": sliced,
    }


def _build_multi_hypothesis(report: dict, limit: int = 25) -> dict:
    hypotheses: list[dict] = []
    for skipped in report.get("skipped_rules") or []:
        if not isinstance(skipped, dict):
            continue
        row = int(skipped.get("row") or 0)
        nearest_family = str(skipped.get("nearest_family") or skipped.get("family") or "").strip()
        ambiguous = skipped.get("ambiguous_families") if isinstance(skipped.get("ambiguous_families"), list) else []
        similarity_score = float(skipped.get("similarity_score") or 0.0)

        row_hypotheses = []
        if nearest_family:
            row_hypotheses.append({"family": nearest_family, "score": round(max(0.0, min(1.0, similarity_score or 0.65)), 4), "source": "nearest_family"})
        for family in ambiguous[:4]:
            fam = str(family).strip()
            if not fam or fam == nearest_family:
                continue
            row_hypotheses.append({"family": fam, "score": round(max(0.0, min(1.0, (similarity_score or 0.65) - 0.08)), 4), "source": "ambiguous_family"})

        rewrite = str(skipped.get("suggested_canonical_rewrite") or "").strip()
        hypotheses.append(
            {
                "row": row,
                "target_xpath": str(skipped.get("target_xpath") or "").strip(),
                "condition": str(skipped.get("condition") or skipped.get("normalized_condition") or "").strip(),
                "hypotheses": row_hypotheses[:3],
                "suggested_rewrite": rewrite,
            }
        )

    return {
        "report_id": str(report.get("report_id") or "").strip(),
        "total_items": len(hypotheses[: max(1, min(limit, 200))]),
        "items": hypotheses[: max(1, min(limit, 200))],
    }


def _build_evidence_graph(report: dict, limit: int = 250) -> dict:
    nodes: list[dict] = []
    edges: list[dict] = []
    node_ids: set[str] = set()

    def add_node(node_id: str, node_type: str, label: str) -> None:
        if not node_id or node_id in node_ids:
            return
        node_ids.add(node_id)
        nodes.append({"id": node_id, "type": node_type, "label": label})

    def add_edge(source: str, target: str, relation: str) -> None:
        if not source or not target:
            return
        edges.append({"source": source, "target": target, "relation": relation})

    skipped_index = _skipped_rules_by_row(report)
    for entry in report.get("rule_decisions") or []:
        if not isinstance(entry, dict):
            continue
        row = int(entry.get("row") or 0)
        decision_id = f"decision:{row or len(nodes) + 1}"
        status = str(entry.get("decision_status") or "").strip().lower() or "unknown"
        add_node(decision_id, "decision", f"Row {row} {status}")

        family = str(entry.get("rule_family") or "").strip()
        if family:
            family_id = f"family:{family}"
            add_node(family_id, "family", family)
            add_edge(decision_id, family_id, "classified_as")

        reason = str(entry.get("decision_reason") or "").strip()
        if reason:
            reason_id = f"reason:{reason[:80]}"
            add_node(reason_id, "reason", reason)
            add_edge(decision_id, reason_id, "because")

        skipped = skipped_index.get(row, {})
        for pattern in (skipped.get("nearest_patterns") or [])[:2]:
            if not isinstance(pattern, dict):
                continue
            regex = str(pattern.get("pattern") or "").strip()
            if not regex:
                continue
            pattern_id = f"pattern:{regex[:90]}"
            add_node(pattern_id, "pattern", regex)
            add_edge(decision_id, pattern_id, "nearest_pattern")

        if len(nodes) >= limit or len(edges) >= limit * 2:
            break

    return {
        "report_id": str(report.get("report_id") or "").strip(),
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": nodes,
        "edges": edges,
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/health/audit")
def health_audit(log_path: str | None = Query(default=None)) -> dict:
    return get_audit_health_snapshot(log_path=Path(log_path) if log_path else None)


@app.post("/validate")
async def validate(
    mapping_spec: UploadFile = File(...),
    input_payload: UploadFile = File(...),
    output_payload: UploadFile = File(...),
    validation_mode: str = Query("strict"),
) -> dict:
    try:
        return validate_uploaded_payloads(
            mapping_spec_name=mapping_spec.filename,
            mapping_spec_bytes=await mapping_spec.read(),
            input_payload_name=input_payload.filename,
            input_payload_bytes=await input_payload.read(),
            output_payload_name=output_payload.filename,
            output_payload_bytes=await output_payload.read(),
            validation_mode=validation_mode,
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Validation failed: {exc}") from exc


@app.post("/intent-patterns/apply-approved")
async def apply_approved_patterns(request: Request, payload: dict = Body(...)) -> dict:
    try:
        manifest = payload.get("manifest")
        if manifest is None:
            manifest = {
                "report_id": payload.get("report_id"),
                "approved_patterns": payload.get("approved_patterns", []),
            }

        dry_run = bool(payload.get("dry_run", True))
        actor = str(payload.get("actor") or "").strip() or None
        actor_context = payload.get("actor_context") if isinstance(payload.get("actor_context"), dict) else {}
        semantic_config_path = Path(str(payload.get("semantic_config_path") or "").strip()) if payload.get("semantic_config_path") else None
        audit_log_path = Path(str(payload.get("audit_log_path") or "").strip()) if payload.get("audit_log_path") else None
        learning_summary_path = Path(str(payload.get("learning_summary_path") or "").strip()) if payload.get("learning_summary_path") else None
        idempotency_cache_path = Path(str(payload.get("idempotency_cache_path") or "").strip()) if payload.get("idempotency_cache_path") else None
        idempotency_key = str(payload.get("idempotency_key") or "").strip()

        normalized_actor_context = {
            "source": str(actor_context.get("source") or "api_client").strip(),
            "environment": str(actor_context.get("environment") or "server").strip(),
            "session_id": str(actor_context.get("session_id") or "").strip(),
            "pipeline_run_id": str(actor_context.get("pipeline_run_id") or "").strip(),
            "client_version": str(actor_context.get("client_version") or "").strip(),
            "page_origin": str(actor_context.get("page_origin") or "").strip(),
            "validation_mode": str(actor_context.get("validation_mode") or "").strip(),
            "policy_confidence": str(actor_context.get("policy_confidence") or "").strip().lower(),
        }
        if request is not None and not normalized_actor_context["client_version"]:
            normalized_actor_context["client_version"] = str(request.headers.get("user-agent") or "").strip()
        normalized_actor_context = {key: value for key, value in normalized_actor_context.items() if value}

        if not dry_run:
            policy = get_learning_policy_snapshot(summary_path=learning_summary_path)
            apply_allowed = bool((policy.get("apply_guard") or {}).get("apply_allowed", True))
            if not apply_allowed:
                raise HTTPException(
                    status_code=409,
                    detail=str((policy.get("apply_guard") or {}).get("reason") or "Apply is currently blocked by learning policy."),
                )

        request_fingerprint = {
            "manifest": manifest,
            "dry_run": bool(dry_run),
            "actor": str(actor or "").strip(),
            "actor_context": normalized_actor_context,
            "semantic_config_path": semantic_config_path.as_posix() if semantic_config_path else "",
        }
        replay = get_idempotent_response(
            idempotency_key=idempotency_key,
            request_payload=request_fingerprint,
            cache_path=idempotency_cache_path,
        )
        if replay is not None:
            return replay

        result = apply_approved_intent_patterns(
            manifest=manifest,
            dry_run=dry_run,
            actor=actor,
            request_context=normalized_actor_context,
            semantic_config_path=semantic_config_path,
            audit_log_path=audit_log_path,
            learning_summary_path=learning_summary_path,
        )
        result["idempotency_replay"] = False
        if idempotency_key:
            result["idempotency_key"] = idempotency_key
            store_idempotent_response(
                idempotency_key=idempotency_key,
                request_payload=request_fingerprint,
                response_payload=result,
                cache_path=idempotency_cache_path,
            )
        return result
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Intent pattern apply failed: {exc}") from exc


@app.post("/intent-patterns/rollback-audit-event")
async def rollback_audit_event(payload: dict = Body(...)) -> dict:
    try:
        event_id = str(payload.get("event_id") or "").strip()
        if not event_id:
            raise ValueError("event_id is required")

        dry_run = bool(payload.get("dry_run", True))
        actor = str(payload.get("actor") or "").strip() or None
        semantic_config_path = Path(str(payload.get("semantic_config_path") or "").strip()) if payload.get("semantic_config_path") else None
        audit_log_path = Path(str(payload.get("audit_log_path") or "").strip()) if payload.get("audit_log_path") else None

        return rollback_intent_patterns_from_audit_event(
            event_id=event_id,
            dry_run=dry_run,
            actor=actor,
            semantic_config_path=semantic_config_path,
            audit_log_path=audit_log_path,
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Intent pattern rollback failed: {exc}") from exc


@app.get("/intent-patterns/learning-policy")
async def intent_patterns_learning_policy(summary_path: str | None = Query(default=None)) -> dict:
    try:
        return get_learning_policy_snapshot(summary_path=Path(summary_path) if summary_path else None)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Learning policy read failed: {exc}") from exc


@app.get("/intent-patterns/audit-events")
async def intent_patterns_audit_events(
    limit: int = Query(default=20, ge=1, le=200),
    log_path: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
    actor_contains: str | None = Query(default=None),
) -> dict:
    try:
        return get_audit_event_snapshot(
            limit=limit,
            log_path=Path(log_path) if log_path else None,
            event_type=event_type,
            actor_contains=actor_contains,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Audit event read failed: {exc}") from exc


@app.post("/agent/recommend-actions")
async def recommend_actions(payload: dict = Body(...), limit: int = Query(default=50, ge=1, le=200)) -> dict:
    try:
        report = _as_report_payload(payload)
        return _build_agent_recommendations(report, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Recommendation generation failed: {exc}") from exc


@app.post("/agent/multi-hypothesis")
async def multi_hypothesis(payload: dict = Body(...), limit: int = Query(default=25, ge=1, le=200)) -> dict:
    try:
        report = _as_report_payload(payload)
        return _build_multi_hypothesis(report, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Hypothesis generation failed: {exc}") from exc


@app.post("/agent/evidence-graph")
async def evidence_graph(payload: dict = Body(...), limit: int = Query(default=250, ge=10, le=1000)) -> dict:
    try:
        report = _as_report_payload(payload)
        return _build_evidence_graph(report, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Evidence graph generation failed: {exc}") from exc
