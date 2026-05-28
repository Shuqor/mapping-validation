from __future__ import annotations

from fastapi import Body, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from core.api_service import validate_uploaded_payloads
from core.intent_pattern_service import apply_approved_intent_patterns


app = FastAPI(title="Mapping Validation API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


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
async def apply_approved_patterns(payload: dict = Body(...)) -> dict:
    try:
        manifest = payload.get("manifest")
        if manifest is None:
            manifest = {
                "report_id": payload.get("report_id"),
                "approved_patterns": payload.get("approved_patterns", []),
            }

        dry_run = bool(payload.get("dry_run", True))
        actor = str(payload.get("actor") or "").strip() or None
        return apply_approved_intent_patterns(
            manifest=manifest,
            dry_run=dry_run,
            actor=actor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Intent pattern apply failed: {exc}") from exc
