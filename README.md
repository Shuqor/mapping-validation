# Mapping Validation Program

CLI validator for mapping rules between source and target payloads across XML, JSON, X12, and EDIFACT formats.

## Current Stage

Stage 9 complete — multi-format adapter pipeline shipping. Stage 10 in planning.

- Completed: Phase 1 through Phase 9
- Completed: Browser-side validation flow with no API requirement
- Live at: https://shuqor.github.io/mapping-validation/
- Completed: Stage 9 pluggable format adapter pipeline (XML, JSON, X12, EDIFACT, cross-format bridge)

## Deployment Status

✅ **GitHub Pages enabled** – https://shuqor.github.io/mapping-validation/  
✅ **Client-side validation enabled** – Files are processed in browser memory  
✅ **No backend required for sharing** – GitHub Pages link is enough

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
- Optional result display modes (`strict` or `lenient` under the hood)

### Phase 5 – Simple Web UI ✅
- Minimal HTML/JS frontend:
  - Upload files
  - Show validation results
  - Choose how results are shown (`Highlight all issues` or `Show issues, but keep the result usable`)
  - Download validation result as JSON
  - Process files locally in browser (no server upload)
- Functionality and correctness over appearance

### Phase 6 – Validation Core Contract ✅
- Define and freeze canonical internal validation model
- Lock strict/lenient behavior and report schema compatibility
- Add baseline golden test set for regression safety

### Phase 7 – CSV/Excel Parser Robustness ✅
- Support variable sheet names and sheet selection fallback
- Improve header row detection and column alias matching
- Preserve duplicate headers safely and map source/target columns reliably
- Handle sparse/merged/offset headers with clear parser diagnostics
- Keep parser behavior deterministic across mixed Excel layouts
- Surface parser diagnostics and confidence in validation output
- Report ambiguous/fallback parser decisions explicitly
- Track parsed-only vs enforced rule support in validation results
- Lock important real workbook families into regression coverage

Phase 7 exit criteria (stability-focused):

- All key workbook families in `rules/` parse without runtime failures.
- Parser diagnostics are visible in CLI/API/UI output.
- Fallback and ambiguity decisions are reported instead of hidden.
- Validation output separates enforced rules from parsed-only/unsupported rules.
- Real workbook regression coverage exists for representative families (JABIL, P&G, TMSLSP, Inttra).

Stage 7 local status:

- Local parser regression checks currently show no `low_confidence` specs in `rules/`.
- Parser diagnostics are available in CLI/API/UI and JSON report payloads.
- Remaining parser warnings are explicit and actionable (for example, offset headers or sheet fallback), not hidden heuristics.
- Workbook-family stability is tracked with regression tests for previously unstable files.

Stage 7 baseline snapshot:

- Baseline artifact: `results/stage7_parser_baseline.json`
- Contains parser status counts and workbook-level diagnostic inventory for regression comparison.

Parser operations runbook:

1. Run parser regression checks
- `python -m pytest tests/test_phase6_spec_reader.py`

2. Interpret parser status
- `clean`: deterministic parse, no blocking parser concerns.
- `parsed_with_warnings`: parse succeeded, but workbook should be reviewed for non-fatal parser caveats.
- `parsed_with_fallbacks`: parse succeeded using fallback sheet or fallback heuristics.
- `low_confidence`: parse succeeded but ambiguity/unsupported patterns make output unreliable; investigate before relying on the results.

3. Interpret confidence
- `high`: deterministic extraction with no unresolved ambiguity.
- `medium`: successful extraction with explicit warnings/fallbacks.
- `low`: unresolved ambiguity or extraction concerns; investigate before relying on output.

4. Triage parser notes
- `warnings`: actionable issues that require workbook-specific review.
- `info`: non-blocking notes (for example duplicate header normalization).

5. Stage 7 local debug policy
- Keep `low_confidence` count at `0` during local parser sweeps.
- Review any increase in `parsed_with_warnings` against the baseline snapshot.
- Use parser diagnostics (`warnings` and `info`) to decide whether a workbook needs parser-rule updates.

### Phase 8 – Validation Rule Expansion (Completed)
- Broaden supported condition patterns
- Expand cardinality/value/constant/concat rule coverage
- Improve rule-level traceability and severity ordering
- Add regression tests from real mapping specs
- Freeze Stage 8 acceptance criteria and CI regression gates

### Phase 9 – Pluggable Format Adapter Pipeline ✅
- Introduce parser/normalizer adapter interface
- Convert all input/output formats into one canonical model before validation
- Keep validator core format-agnostic
- API and CLI wired to Stage 9 `validate_mapping_from_payload_bytes` entrypoint
- Browser runtime diagnostics card (spec layout, payload route, adapter path)
- Cross-format bridge: X12/EDIFACT input + JSON/XML output for `x12_segment` specs
- Real-workbook smoke batch runner (`scripts/run_stage9_real_spec_batch.py`)
- Plain-English structure summary and issue breakdown labels

Stage 8 contract and Stage 9 handoff docs:

- `docs/stage8_acceptance_criteria.md`
- `docs/stage9_handoff.md`

Stage 8 baseline artifact:

- `results/stage8_validation_baseline.json`
- enforced by `tests/test_stage8_baseline_snapshot.py`
- regenerate intentionally with `python scripts/regenerate_stage8_baseline.py`

Stage 9 JSON bridge baseline artifact:

- `results/stage9_json_bridge_baseline.json`
- enforced by `tests/test_stage9_json_bridge_baseline_snapshot.py`
- regenerate intentionally with `python scripts/regenerate_stage9_json_baseline.py`

### Stage 10 – UI Cleanup, Parser Upgrade, Semantic Rule Engine, and Mapper Productivity (Planned)

**10.1 – UI Cleanup and Wording Upgrade**
- Redesign the result panel: visual severity cards (error / warning / info), collapsible issue groups
- Replace raw JSON download with a clean human-readable summary view
- Improve pass / warn / fail color coding with clear call-to-action wording
- Polish the runtime diagnostics card (spec layout, adapter path, format badges)
- Rewrite all remaining technical labels to plain mapper-friendly English
- Add inline guidance text explaining what each issue type means and what action to take

**10.2 – Spec Reader Parser Upgrade (All Formats)**
- Increase column detection coverage for non-standard header names and merged/offset layouts across all spec types (XML, JSON, X12, EDIFACT)
- Support EDIFACT segment notation in source/target columns (`edifact_segment` layout type) alongside existing `xpath_target`, `cdm_target`, and `x12_segment`
- Improve multi-sheet workbook handling: better fallback order, sheet scoring, and ambiguity reporting
- Handle more real-world layout variations: blank leading rows, mixed column ordering, inline cardinality notation
- Surface per-rule parser confidence alongside validation results
- Expand real-workbook regression coverage as new spec files are added across all supported formats

**10.3 – Semantic Condition and Pattern Recognition Engine**
- Replace brittle regex condition matching with a semantic normalizer pipeline
- Canonicalize free-text conditions (varying capitalization, phrasing, symbols) before matching
- Expand recognized pattern families: value translation, conditional copy, existence guard, concat, format transform, substring slice, date remap
- Track unrecognized conditions explicitly and report them as `unsupported_rule` gaps rather than silently skipping
- Expose pattern match trace in the validation report so mappers can see why a rule was or was not enforced

**10.4 – Rule Gap Reporting and Actionable Fix Suggestions**
- Add a `rule_gap_summary` section to the validation report: enforced vs parsed-only vs unsupported rule counts per spec
- Show which conditions are not yet enforced and why, so mappers know what the tool cannot check
- Generate per-issue fix suggestions in plain English (for example: "Add `/status/code` to the output — the spec requires it when source `ST01` is present")
- Add a confidence score per rule so mappers can prioritize which issues are definite failures vs likely mismatches

**10.5 – Side-by-Side Diff View**
- Show source fields vs target fields in two columns with color-coded match / mismatch / missing status
- Let mappers visually scan what mapped correctly, what is wrong, and what is absent — without reading a raw issue list
- Highlight the exact field pair that caused each issue directly on the diff row

**10.6 – Spec Coverage Read-Out (Dry Run Mode)**
- Upload only the spec (no payload) and get back a full coverage report: total rules parsed, enforced count, parsed-only count, unrecognized count
- Show which fields have no cardinality defined and which conditions the tool cannot currently enforce
- Lets mappers audit a new spec before they even have payloads to test against

**10.7 – Export to Excel**
- Download validation results as a formatted `.xlsx` file with columns for rule row, field path, issue type, issue description, and suggested fix
- Mappers can filter, sort, and share results directly in Excel without interpreting JSON
- Include a summary tab with pass/warn/fail counts and spec coverage metrics

**10.8 – Condition Suggestion on Unrecognized Rules**
- When a condition does not match any known pattern, show the closest recognized pattern and what it would enforce
- Example: "Did you mean: `If Source != '' then map to Target`? This would check that the target field is populated whenever the source is not empty."
- Helps mappers fix ambiguous condition wording in the spec before rerunning validation

**10.9 – Batch / Multi-Payload Validation Mode**
- Upload one spec and multiple input/output payload pairs in a single session
- Get a consolidated pass/fail summary across all pairs with per-pair drill-down
- Useful for regression testing after a spec change or validating a full transaction set at once

**10.10 – Spec Diff / Change Detection**
- Upload two versions of the same spec and get a diff: rules added, rules removed, rules changed (cardinality, condition, target path)
- Flag high-risk changes that are likely to break existing mappings
- Helps mappers assess the impact of a spec revision before running a full validation sweep

**10.11 – Interactive Rule Inspector**
- Click any issue in the result panel to expand a detail view: raw condition text from the spec, which pattern it matched, what value was checked, what was expected vs found
- Replaces the need to cross-reference the spec workbook manually for every issue
- Show the full rule row context (source path, target path, cardinality, condition, note) inline

**10.12 – Mandatory Field Pre-Flight Checklist**
- Before running full validation, show a simple tick-list of every mandatory (M / 1..1) field in the spec and whether it exists in the output at all
- Catches the most obvious omissions immediately without wading through a detailed issue list
- Lets mappers fix the basics first before investigating conditional or value-level failures

**10.13 – Reverse Validation (Unmapped Required Fields)**
- Identify required fields where no source field could have populated the output — not "wrong value" but "no mapping attempt was made at all"
- Surfaces gaps that are not yet errors in the payload but will fail in production
- Complements forward validation by showing what was skipped, not just what was wrong

**10.14 – Mapping Completeness Score**
- Calculate a percentage score: what fraction of mandatory spec rules are fully satisfied
- Display as a single headline metric (for example "Completeness: 74%") so mappers and team leads can track progress across a project
- Teams can set a go-live threshold (for example must reach 90% before sign-off)

**10.15 – Issue Annotation and Triage**
- Let mappers mark individual issues as `accepted`, `needs fix`, or `won't fix` and save that state across sessions
- When sharing results with a partner or team lead, they can see what has been acknowledged vs what still requires action
- Prevents the same known-acceptable deviations from cluttering every subsequent validation run

**10.16 – Shareable Result Link**
- Generate a shareable URL for a validation result so the whole team can review it without re-uploading files
- Could be encoded as a URL-safe payload or posted to a GitHub Gist automatically
- Removes the need to email JSON files back and forth for team review

**10.17 – Payload Template Generator**
- Given a spec, auto-generate a skeleton output file (XML or JSON) with all mandatory fields present as clearly labelled placeholders
- Mappers start a new implementation from a valid skeleton rather than a blank file
- Reduces the time to first successful validation on a new mapping project

**10.18 – Sample Payload Generator**
- Given a spec, generate the minimal valid input and output payload pair that satisfies all mandatory rules with realistic placeholder values
- Invaluable for testing a new spec implementation end-to-end without needing real transaction data
- Can also serve as a documentation artifact showing what a correct mapping looks like

**10.19 – Full-Field Payload Generator (Input and Output)**
- Generate a complete input payload and a matching complete output payload covering every field defined in the spec — not just mandatory fields but all optional and conditional fields too
- Each field is populated with a realistic placeholder value based on its data type, cardinality, and any format hints in the spec (for example dates, codes, numeric ranges)
- Useful for exhaustive integration testing: validates that the mapping engine handles every possible field combination, not just the happy path
- Output covers all supported formats: XML, JSON, X12 segment, and EDIFACT segment layouts
- Can be used as a golden reference pair for regression baseline generation



## Run

```bash
python main.py
```

Optional arguments:

```bash
python main.py --spec rules/spec.xlsx --input samples/input.xml --output samples/output.xml --report results/report.json
```

Stage 9 CLI examples:

```bash
python main.py --spec rules/JABIL_X12_214_4010_to_JSON_TMSCARRIERTENDERRESPONSE_v1.4.xlsx --input samples/input.x12 --output samples/output.json
python main.py --spec samples/spec_edifact_guided.xlsx --input samples/input.edifact --output samples/output.json --mode lenient
```

Validation modes:

- `strict`: fail when any validation issue is found
- `lenient`: keep the result usable while still reporting issues
- `structure_strict`: run the normal validation checks and also add expected-root, missing-branch, unexpected-attribute, and unexpected-node checks

Example CLI output (human-readable):

```text
VALIDATION FAILED
Found 3 mapping issue(s); fix the top items first
What needs attention:
- Missing target fields: 1
- Wrong number of values: 1
- Source and target values do not match: 1
What to fix first:
- Add the missing target field /status/ediFunction1 so it receives the source value.
- Adjust /status/ediFunction1 so the number of values matches the expected rule (1..1 expected, 0 found).
- Review the mapping from /status/ediFunction2 to /status/ediFunction2: the source and target values do not match.
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
- Upload `mapping_spec` plus matching `input_payload` and `output_payload` (`.xml`, `.json`, `.x12`, `.edifact`, or `.edi`)
- Choose `Highlight all issues`, `Show issues, but keep the result usable`, or `Enforce output structure from spec`
- Validation runs locally in browser memory
- Non-XML payloads (`.json`, `.x12`, `.edifact`, `.edi`) run in Stage 9 bridge mode (normalized locally, no server upload)
- Review the headline, what needs attention, and what to fix first
- Download JSON report from the UI button

Supported local payload combinations:

- XML + XML
- JSON + JSON
- X12 (`.x12`) + X12 (`.x12`)
- EDIFACT (`.edifact`) + EDIFACT (`.edifact`)
- EDI autodetect (`.edi`) + EDI autodetect (`.edi`) for either X12 or EDIFACT flavor
- Cross-format Stage 9 bridge: X12/EDIFACT input + JSON/XML output for specs detected as `x12_segment`

Stage 9 baseline regeneration (all bridge/parser artifacts):

```bash
python scripts/regenerate_stage9_all_baselines.py
```

Stage 9 real-workbook smoke batch:

```bash
python scripts/run_stage9_real_spec_batch.py --mode lenient
```

Local-first policy:

- Recommended usage is browser-local validation with no backend uploads.
- API usage is optional and intended only for controlled internal environments.

## Public Sharing Setup (One URL for Coworkers)

To share publicly with one URL, use GitHub Pages only:

1. Deploy frontend (web UI) on GitHub Pages
- Push to `main`
- Enable Pages in repository settings (`GitHub Actions` source)
- Workflow `.github/workflows/deploy-pages.yml` publishes `web/`
- Your UI URL will look like `https://<org-or-user>.github.io/<repo>/`

2. Use the shared URL directly
- Open the GitHub Pages URL
- Upload files and validate directly in the browser

Notes:
- Uploaded files are processed locally in browser memory.
- No API endpoint is required for the GitHub Pages flow.

Endpoints:

- `POST /validate`
- Query parameter:
  - `validation_mode` = `strict` (default), `lenient`, or `structure_strict`
- Multipart form fields:
  - `mapping_spec` (`.xlsx`, `.xls`, or `.csv`)
  - `input_payload` (`.xml`, `.json`, `.x12`, `.edifact`, or `.edi`)
  - `output_payload` (`.xml`, `.json`, `.x12`, `.edifact`, or `.edi`)
- Returns validation report JSON for that request
- Stateless behavior: no temporary result storage
- To revalidate, users upload files again

API payload combinations:

- Matching formats: XML, JSON, X12, EDIFACT, or `.edi` autodetect
- Cross-format Stage 9 bridge: X12/EDIFACT input with JSON/XML output when the spec layout resolves to `x12_segment`
- API responses include `adapter_pipeline` metadata when Stage 9 normalization is used

Local artifact hygiene:

- Default CLI reports in `results/report.json` are local scratch output and should not be treated as baseline artifacts.
- Use the tracked Stage 8/Stage 9 baseline files in `results/` only when intentionally regenerating snapshots.

Validation mode behavior:

- `strict`: status becomes `FAIL` when errors exist and `valid=false`
- `lenient`: status becomes `PASS_WITH_WARNINGS` when errors exist and `valid=true`
- `structure_strict`: status becomes `FAIL` when normal validation or added structure checks find issues, including wrong root, missing branches, unexpected attributes, unexpected nodes, per-parent cardinality violations, missing required attributes, configured choice/order violations, and namespace mismatches; conditional target requirements are only enforced when the rule guard applies
- Both modes still return full error details

Mapper-friendly response fields:

- `summary.grouped_error_counts`: counts by error type
- `summary.top_critical_errors`: top 10 prioritized errors
- `summary.parser_status`: parser status (`clean`, `parsed_with_warnings`, `parsed_with_fallbacks`, `low_confidence`)
- `summary.parser_confidence`: parser confidence (`high`, `medium`, `low`)
- `structure_summary`: structure-only status, counts for root/branch/attribute/node issues, repeat-count examples, and applied spec exceptions
- `structure_summary.coverage`: allowed-vs-present structure coverage with missing allowed path counts/examples
- `structure_findings`: structured explainability payload per structure finding (category, row, target path, expected/actual metadata when available)
- `error_sections`: grouped lists of detailed errors
- `strict_would_fail`: indicates if strict mode would fail this validation
- `parser_diagnostics`: selected sheet/header row, duplicate headers, fallbacks, ambiguities
- `rule_support_summary`: enforced vs parsed-only vs unsupported rule counts, plus deterministic semantic telemetry (`condition_transform_applied_rules`, `unsupported_rule_suggestions_provided`, high/medium/low similarity buckets, ambiguity counters, field-alias normalization counters, and future auto-promotion candidate counts)
- `semantic_summary`: global semantic coverage, top unsupported phrasings, top suggested rule families, ambiguity counts, semantic thresholds in effect, and `promote_to_generic_candidates` for phrase promotion into the global profile

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

- Workflow first runs pinned parity tests for structure validation:
  - `python -m pytest tests/test_web.py tests/test_report_format.py -q`
- Workflow also runs contract fixtures for partner/spec structure regression via `tests/test_structure_contract_fixtures.py`
- Workflow runs a frozen Stage 8 semantic gate:
  - `python -m pytest tests/test_semantic_similarity.py tests/test_web.py tests/test_report_format.py tests/test_structure_contract_fixtures.py -q`
- Workflow runs semantic performance guardrails:
  - `python -m pytest tests/test_semantic_performance_guardrail.py -q`
- Workflow runs a baseline snapshot regression:
  - `python -m pytest tests/test_stage8_baseline_snapshot.py -q`
- Workflow runs `pytest`
- Then starts the API and performs a multipart `/validate` smoke request using sample files
- See `.github/workflows/ci.yml`

Structure exceptions configuration:

- File: `rules/structure_exceptions.json`
- Non-technical how-to: `rules/structure_exceptions_guide.md`
- Supports per-spec overrides for:
  - `ignore_required_paths`
  - `allow_nodes`
  - `allow_attributes`
  - `ordered_sibling_groups`
  - `choice_groups`

Semantic profile configuration:

- File: `rules/semantic_profiles.json`
- Supports global phrase replacements, field aliases, and thresholds for:
  - `high`
  - `medium`
  - `auto_promote`
  - `ambiguity_gap`
- Semantic matching now runs one global profile for all specs (no family overrides)

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
- `skipped_rules`: list of rules skipped due to unsupported conditions, including deterministic suggestion hints (`nearest_family`, `similarity_score`, `similarity_confidence`, `nearest_patterns`, `normalized_condition`, `applied_transforms`, `why_not_enforced`, `try_normalized_form`, `semantic_parts`, `ambiguous_families`, `ambiguity_reason`, `suggested_canonical_rewrite`, `future_auto_promotion_eligible`, and semantic profile/workbook family tags)
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