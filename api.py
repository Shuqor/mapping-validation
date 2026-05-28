from __future__ import annotations

from fastapi import FastAPI, File, HTTPException, Query, UploadFile

from core.validate import validate_mapping_from_payload_bytes


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
        spec_bytes = await mapping_spec.read()
        input_bytes = await input_payload.read()
        output_bytes = await output_payload.read()

        if not spec_bytes:
            raise HTTPException(status_code=400, detail="mapping_spec is empty")
        if not input_bytes:
            raise HTTPException(status_code=400, detail="input_payload is empty")
        if not output_bytes:
            raise HTTPException(status_code=400, detail="output_payload is empty")

        from pathlib import Path
        from tempfile import NamedTemporaryFile

        suffix = ".xlsx"
        if mapping_spec.filename:
            lower_name = mapping_spec.filename.lower()
            if lower_name.endswith(".xls"):
                suffix = ".xls"
            elif lower_name.endswith(".xlsx"):
                suffix = ".xlsx"

        spec_path = ""
        with NamedTemporaryFile(suffix=suffix, delete=False) as spec_tmp:
            spec_tmp.write(spec_bytes)
            spec_tmp.flush()
            spec_path = spec_tmp.name

        try:
            return validate_mapping_from_payload_bytes(
                spec_path,
                input_bytes,
                input_payload.filename or "input.xml",
                output_bytes,
                output_payload.filename or "output.xml",
                validation_mode=validation_mode,
            )
        finally:
            if spec_path:
                try:
                    Path(spec_path).unlink(missing_ok=True)
                except PermissionError:
                    # Best-effort cleanup on Windows where file handles can linger briefly.
                    pass
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Validation failed: {exc}") from exc
