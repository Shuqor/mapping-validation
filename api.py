import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from time import time
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from core.validate import validate_mapping_from_payload_bytes


app = FastAPI(title="Mapping Validation Program API", version="0.1.0")
WEB_UI_PATH = Path(__file__).parent / "web" / "index.html"

def _env_int(name: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default

    try:
        value = int(raw)
    except ValueError:
        return default

    return value if value >= minimum else default


MAX_UPLOAD_BYTES = _env_int("MAX_UPLOAD_BYTES", 5 * 1024 * 1024)
VALIDATION_TIMEOUT_SECONDS = _env_int("VALIDATION_TIMEOUT_SECONDS", 30)
RATE_LIMIT_WINDOW_SECONDS = _env_int("RATE_LIMIT_WINDOW_SECONDS", 60)
RATE_LIMIT_MAX_REQUESTS = _env_int("RATE_LIMIT_MAX_REQUESTS", 30)

ALLOWED_SPEC_EXTENSIONS = {".xlsx", ".xls", ".csv"}
ALLOWED_PAYLOAD_EXTENSIONS = {".xml", ".json", ".x12", ".edifact", ".edi"}

RATE_LIMIT_STATE: dict[str, list[float]] = {}

# Enable CORS for shareable links - allow any origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _suffix_of(filename: str | None) -> str:
    return Path(filename or "").suffix.lower()


def _friendly_parse_error(exc: Exception) -> str:
    message = str(exc)
    lowered = message.lower()

    if "worksheet named 'mapping' not found" in lowered:
        return "Spec worksheet not found. Add a sheet named 'Mapping' or align the spec format."
    if "could not detect header row" in lowered:
        return (
            "Mapping header row not detected. Include header fields like xpath/cardinality/condition, "
            "or check whether the workbook has offset preamble rows or merged headers."
        )
    if "segment / field xpath" in lowered:
        return "Required mapping columns are missing. Ensure target/source XPath columns exist."
    if "mapping table is empty after header detection" in lowered:
        return (
            "Mapping sheet was found but no data rows remained after header detection. "
            "Check the selected sheet, header row, and sparse rows around the mapping table."
        )
    if "target column could be resolved" in lowered or "anchor column could be resolved" in lowered:
        return (
            "Unable to resolve required mapping columns from the spec. "
            "Review target/source column names and parser diagnostics."
        )
    if "xml" in lowered and ("syntax" in lowered or "not well-formed" in lowered):
        return "Invalid XML file. Please upload well-formed XML input and output payloads."
    if "unsupported payload format" in lowered or "payload formats must match" in lowered:
        return (
            "Unsupported payload combination. Use matching XML/JSON/X12/EDIFACT payloads, "
            "or provide X12/EDIFACT input with JSON/XML output when the spec layout is x12_segment."
        )
    if "unable to detect .edi payload flavor" in lowered:
        return "Unable to detect whether the .edi payload is X12 or EDIFACT. Use .x12 or .edifact for clarity."

    return f"File parse error: {type(exc).__name__}: {exc}"


def _enforce_rate_limit(client_id: str) -> None:
    now = time()
    window_start = now - RATE_LIMIT_WINDOW_SECONDS
    calls = RATE_LIMIT_STATE.get(client_id, [])
    calls = [ts for ts in calls if ts >= window_start]

    if len(calls) >= RATE_LIMIT_MAX_REQUESTS:
        raise HTTPException(
            status_code=429,
            detail=(
                "Too many validation requests. "
                f"Limit is {RATE_LIMIT_MAX_REQUESTS} requests per {RATE_LIMIT_WINDOW_SECONDS} seconds."
            ),
        )

    calls.append(now)
    RATE_LIMIT_STATE[client_id] = calls


async def _read_and_validate_upload(
    upload: UploadFile,
    label: str,
    allowed_extensions: set[str],
) -> tuple[bytes, str]:
    ext = _suffix_of(upload.filename)
    if ext not in allowed_extensions:
        allowed = ", ".join(sorted(allowed_extensions))
        raise HTTPException(
            status_code=422,
            detail=f"Invalid {label} file type '{ext or 'unknown'}'. Allowed extensions: {allowed}",
        )

    content = await upload.read()
    if not content:
        raise HTTPException(status_code=422, detail=f"{label} file is empty")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"{label} file is too large. Max size is {MAX_UPLOAD_BYTES} bytes",
        )

    return content, ext


@app.get("/health")
async def health() -> dict:
    """Health check endpoint for readiness/liveness probes."""
    return {"status": "ok"}


@app.get("/")
async def web_ui() -> FileResponse:
    """Serve minimal Phase 5 web UI."""
    return FileResponse(WEB_UI_PATH)


@app.post("/validate")
async def validate(
    request: Request,
    validation_mode: Literal["strict", "lenient", "structure_strict"] = "strict",
    mapping_spec: UploadFile = File(...),
    input_payload: UploadFile = File(...),
    output_payload: UploadFile = File(...),
) -> dict:
    client_id = request.client.host if request.client and request.client.host else "unknown"
    _enforce_rate_limit(client_id)

    spec_bytes, spec_ext = await _read_and_validate_upload(
        mapping_spec,
        "mapping_spec",
        ALLOWED_SPEC_EXTENSIONS,
    )
    input_bytes, _ = await _read_and_validate_upload(
        input_payload,
        "input_payload",
        ALLOWED_PAYLOAD_EXTENSIONS,
    )
    output_bytes, _ = await _read_and_validate_upload(
        output_payload,
        "output_payload",
        ALLOWED_PAYLOAD_EXTENSIONS,
    )

    with TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        spec_path = tmp_path / f"mapping_spec{spec_ext}"

        spec_path.write_bytes(spec_bytes)

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    validate_mapping_from_payload_bytes,
                    str(spec_path),
                    input_bytes,
                    input_payload.filename or "input_payload",
                    output_bytes,
                    output_payload.filename or "output_payload",
                    validation_mode,
                ),
                timeout=VALIDATION_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError as exc:
            raise HTTPException(
                status_code=408,
                detail=(
                    f"Validation timed out after {VALIDATION_TIMEOUT_SECONDS} seconds. "
                    "Try smaller files or simplify the mapping scope."
                ),
            ) from exc
        except (ValueError, KeyError, OSError) as exc:
            raise HTTPException(status_code=422, detail=_friendly_parse_error(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Validation error: {type(exc).__name__}: {exc}",
            ) from exc

    return {
        "report_version": "1.1",
        "report_id": str(uuid4()),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "spec_filename": mapping_spec.filename,
            "input_filename": input_payload.filename,
            "output_filename": output_payload.filename,
        },
        **result,
    }
