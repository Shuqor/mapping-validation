# Mapping Validation Program

CLI validator for mapping rules between source and target XML payloads.

## Current Stage

Phase 5 - Simple Web UI (next in progress)

- Completed: Phase 1, Phase 2, Phase 3, Phase 4
- Next: Add a minimal frontend to upload files and display results
- First UI milestone: add `strict` / `lenient` mode toggle

## Deployment Status

✅ **GitHub Pages enabled** – Public repository, workflow configured  
🔄 **Render backend** – `render.yaml` ready for connection  
📋 **Next step** – Connect Render dashboard to activate backend deployment

## Roadmap

### Phase 1 – Stabilize Local Validator ✅
- Improve validation logic:
  - Support cardinality: `1..1`, `0..1`, `0..N`
  - Handle conditions:
    - `"If Source != '' then map Source to Target"`
    - `"Value of source 'X'"`
  - Produce clear, human-readable error messages:
    - Include mapping row number
    - Include target XPath
- CLI-based only (`python main.py`)

### Phase 2 – Validation Report Output ✅
- Structured JSON validation report
- Summary: PASS / FAIL, error count

### Phase 3 – Minimal Web API (FastAPI) ✅
- `POST /validate` endpoint
- Accepts multipart: `mapping_spec` (Excel), `input_payload` (XML), `output_payload` (XML)
- Returns validation report JSON
- No frontend, no authentication

### Phase 4 – Shareable API Access ✅
- Stateless API endpoint
- Anyone with the API URL can use the program
- Users upload files for each validation request
- Upload guardrails (file type, empty-file checks, max size)
- Request timeout and basic rate limiting
- Grouped validation summary for mapper-friendly troubleshooting
- Top 10 critical errors in each validation response
- Optional strict/lenient validation mode

### Phase 5 – Simple Web UI
- Minimal HTML/JS frontend:
  - Upload files
  - Show validation results
  - Choose validation mode (`strict` or `lenient`)
  - Download validation result as JSON
- Functionality and correctness over appearance



## Run

```bash
python main.py
```

Optional arguments:

```bash
python main.py --spec rules/spec.xlsx --input samples/input.xml --output samples/output.xml --report results/report.json
```

Example CLI output (human-readable):

```text
VALIDATION FAILED
Found 3 mapping issue(s); fix the top items first
Issue breakdown:
- Missing target when source has value: 1
- Cardinality mismatches: 1
- Source and target value mismatches: 1
Top 3 issue(s) to fix first:
- Row 12 | Target: /status/ediFunction1 | Source exists but target is missing
- Row 12 | Target: /status/ediFunction1 | Cardinality violation: expected 1..1, got 0
- Row 4 | Target: /status/ediFunction2 | Value mismatch from source /status/ediFunction2: OK != BAD
Report written to results/report.json
```

## API (Phase 4)

Install dependencies:

```bash
pip install -r requirements.txt
```

Run API:

```bash
uvicorn api:app --reload
```

Web UI (Phase 5 entrypoint):

- Open `http://127.0.0.1:8000/`
- Upload `mapping_spec`, `input_payload`, and `output_payload`
- Select `strict` or `lenient` mode
- Set `API Base URL` when UI is not hosted on the same server as the API
- Review human-readable headline, issue breakdown, and top fixes
- Download JSON report from the UI button

## Public Sharing Setup (One URL for Coworkers)

To share like a public link (similar to GitHub Pages sites), deploy frontend and backend separately:

1. Deploy backend (FastAPI) on Render
- Connect this repository in Render
- Use `render.yaml` from repo root
- Render will run:
  - Build: `pip install -r requirements.txt`
  - Start: `uvicorn api:app --host 0.0.0.0 --port $PORT`
- Copy deployed API URL, e.g. `https://mapping-validation-api.onrender.com`

2. Deploy frontend (web UI) on GitHub Pages
- Push to `main`
- Enable Pages in repository settings (`GitHub Actions` source)
- Workflow `.github/workflows/deploy-pages.yml` publishes `web/`
- Your UI URL will look like `https://<org-or-user>.github.io/<repo>/`

3. Connect frontend to backend
- Open the GitHub Pages URL
- In `API Base URL`, paste your Render API URL
- Run validation from the same page

Notes:
- API CORS is already enabled for cross-origin frontend calls.
- The browser remembers `API Base URL` in local storage after you set it once.

Endpoints:

- `POST /validate`
- Query parameter:
  - `validation_mode` = `strict` (default) or `lenient`
- Multipart form fields:
  - `mapping_spec` (`.xlsx`, `.xls`, or `.csv`)
  - `input_payload` (XML file)
  - `output_payload` (XML file)
- Returns validation report JSON for that request
- Stateless behavior: no temporary result storage
- To revalidate, users upload files again

Validation mode behavior:

- `strict`: status becomes `FAIL` when errors exist and `valid=false`
- `lenient`: status becomes `PASS_WITH_WARNINGS` when errors exist and `valid=true`
- Both modes still return full error details

Mapper-friendly response fields:

- `summary.grouped_error_counts`: counts by error type
- `summary.top_critical_errors`: top 10 prioritized errors
- `error_sections`: grouped lists of detailed errors
- `strict_would_fail`: indicates if strict mode would fail this validation

Guardrails:

- Max upload size per file: `5 MB`
- Timeout per validation request: `30 seconds`
- Rate limit: `30 requests per 60 seconds` per client
- Common response codes:
  - `200`: validation completed
  - `408`: validation timed out
  - `413`: uploaded file too large
  - `422`: invalid file type/empty file/parse error
  - `429`: too many requests

Environment variables (optional):

- `MAX_UPLOAD_BYTES` (default: `5242880`)
- `VALIDATION_TIMEOUT_SECONDS` (default: `30`)
- `RATE_LIMIT_WINDOW_SECONDS` (default: `60`)
- `RATE_LIMIT_MAX_REQUESTS` (default: `30`)

PowerShell example (set custom limits before starting API):

```powershell
$env:MAX_UPLOAD_BYTES = "10485760"
$env:VALIDATION_TIMEOUT_SECONDS = "45"
$env:RATE_LIMIT_WINDOW_SECONDS = "60"
$env:RATE_LIMIT_MAX_REQUESTS = "100"
uvicorn api:app --reload
```

Example request (`curl`):

```bash
curl -X POST "http://127.0.0.1:8000/validate" \
  -F "mapping_spec=@rules/spec.xlsx" \
  -F "input_payload=@samples/input.xml" \
  -F "output_payload=@samples/output.xml"
```

Lenient mode example (`curl`):

```bash
curl -X POST "http://127.0.0.1:8000/validate?validation_mode=lenient" \
  -F "mapping_spec=@rules/spec.xlsx" \
  -F "input_payload=@samples/input.xml" \
  -F "output_payload=@samples/output.xml"
```

Example request (PowerShell):

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/validate" -Form @{
  mapping_spec = Get-Item "rules/spec.xlsx"
  input_payload = Get-Item "samples/input.xml"
  output_payload = Get-Item "samples/output.xml"
}
```

Smoke test script:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/smoke_validate.ps1 -BaseUrl "http://127.0.0.1:8000"
```

CI smoke step:

- Workflow runs `pytest`
- Then starts the API and performs a multipart `/validate` smoke request using sample files
- See `.github/workflows/ci.yml`

Returns the same validation report JSON structure as CLI output.

## Validation Report JSON Schema

The report file (default: `results/report.json`) includes:

- `report_version`: report schema version
- `report_id`: unique UUID for this run
- `generated_at_utc`: ISO8601 UTC timestamp
- `summary.status`: `PASS`, `FAIL`, or `PASS_WITH_WARNINGS`
- `summary.error_count`: number of validation errors
- `summary.grouped_error_counts`: issue counts by category
- `summary.top_critical_errors`: top prioritized issues (up to 10)
- `human_summary.headline`: plain-language mapper summary
- `human_summary.what_to_fix_first`: fix-first issue list
- `human_summary.issue_breakdown`: human-readable category/count pairs
- `human_summary.checked_rules`: number of evaluated rules
- `human_summary.skipped_rules`: number of skipped unsupported rules
- `valid`: boolean equivalent of status
- `validation_mode`: `strict` or `lenient`
- `strict_would_fail`: indicates whether strict mode would fail
- `checked_rules`: number of evaluated mapping rows
- `warnings`: non-fatal warnings
- `rule_stats`: per-check counters
- `skipped_rules`: list of rules skipped due to unsupported conditions
- `error_sections`: grouped lists of detailed errors
- `top_critical_errors`: top prioritized issues (same content as `summary.top_critical_errors`)
- `error_count`: total error count
- `inputs`: spec/input/output paths used for this run
- `errors`: list of human-readable errors

Example (PASS):

```json
{
  "report_version": "1.1",
  "report_id": "f2f13af9-127f-4955-8a53-2a5cf4f4bbf3",
  "generated_at_utc": "2026-05-08T08:22:47.073055+00:00",
  "summary": {
    "status": "PASS",
    "error_count": 0
  },
  "valid": true,
  "checked_rules": 42,
  "warnings": [],
  "rule_stats": {
    "cardinality_violations": 0,
    "source_target_missing": 0,
    "value_mismatches": 0,
    "constant_mismatches": 0,
    "concat_mismatches": 0
  },
  "error_count": 0,
  "inputs": {
    "spec_path": "rules/spec.xlsx",
    "input_xml_path": "samples/input.xml",
    "output_xml_path": "samples/output.xml"
  },
  "errors": []
}
```