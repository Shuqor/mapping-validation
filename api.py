from __future__ import annotations

from fastapi import FastAPI, File, HTTPException, Query, UploadFile

from core.api_service import validate_uploaded_payloads


app = FastAPI(title="Mapping Validation API")


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
