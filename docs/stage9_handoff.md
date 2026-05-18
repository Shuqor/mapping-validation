# Stage 9 Handoff Notes

Stage 9 starts from a stable Stage 8 baseline with global semantic behavior.

## Baseline You Inherit

- Semantic profile resolution is global-only.
- Family overrides are intentionally not used.
- Semantic summary and skipped-rule guidance are available in backend and browser validation flows.
- Real-world semantic corpus coverage is expanded and enforced by tests.

## Non-Negotiable Constraints

- Do not reintroduce family-level semantic profile overrides.
- Keep deterministic semantic scoring and explainability payloads.
- Preserve report schema compatibility for Stage 8 frozen fields.
- Keep browser-local processing as the default path (no mandatory server upload flow).

## Where To Extend

- Add adapter interfaces and normalization stages without coupling format logic into validator rules.
- Keep semantic matching independent from format adapters.
- Grow curated phrase corpus when adding new partners or mapping idioms.

## CI Gates To Keep

- Semantic regression suites
- Web/backend parity suites
- Structure contract fixture suite
- Semantic performance guardrail suite

## Performance Guardrail Policy

- Keep medium and large corpus semantic scoring under configured thresholds.
- Thresholds can be tuned via environment variables in CI when hardware profile changes.
- Any threshold increase requires evidence and notes in PR description.

## Practical Next Steps

1. Define adapter interface for parser/normalizer pipeline.
2. Add one pilot adapter (for example JSON) to validate integration seam.
3. Add format-agnostic integration tests against the Stage 8 frozen report contract.
4. Keep semantic corpus additions in small, reviewable batches.

## Stage 9 Skeleton Added

- Adapter models and interface scaffold under `core/adapters/`
- Registry and pipeline seam under `core/adapters/registry.py` and `core/adapters/pipeline.py`
- Pilot JSON adapter under `core/adapters/json_adapter.py`
- Stage 9 adapter tests under `tests/test_stage9_adapters.py`
- Non-invasive payload bridge entrypoint in `core/validate.py`:
	- `validate_mapping_from_payload_bytes(...)`
	- Supports matching `.xml` payloads (passthrough) and matching `.json` payloads (canonical adapter bridge)
	- Supports cross-format EDI bridge flows for `x12_segment` specs: X12/EDIFACT input + JSON/XML output
	- Loop-aware GROUP_* fallback is applied during XPath lookup for EDI-derived paths
	- Returns the same report contract shape used by existing validation flow
- Browser-local Stage 9 JSON pilot in `web/index.html`:
	- Input/output payloads now support matching `.xml`, `.json`, `.x12`, `.edifact`, or `.edi`
	- Non-XML payloads are normalized locally in Stage 9 bridge mode
	- Browser parity supports cross-format EDI flows for `x12_segment` specs (X12/EDIFACT input + JSON/XML output)
	- Browser xpath lookup includes GROUP_* loop-token fallback for EDI-derived paths
	- `.edi` payloads are flavor-detected as X12 or EDIFACT using deterministic signatures
	- No API/server upload is required for this path
- Stage 9 JSON bridge baseline snapshot:
	- Artifact: `results/stage9_json_bridge_baseline.json`
	- Test: `tests/test_stage9_json_bridge_baseline_snapshot.py`
	- Regeneration helper: `scripts/regenerate_stage9_json_baseline.py`
- Stage 9 X12 bridge baseline snapshot:
	- Artifact: `results/stage9_x12_bridge_baseline.json`
	- Test: `tests/test_stage9_x12_bridge_baseline_snapshot.py`
	- Regeneration helper: `scripts/regenerate_stage9_x12_baseline.py`
- Stage 9 EDIFACT bridge baseline snapshot:
	- Artifact: `results/stage9_edifact_bridge_baseline.json`
	- Test: `tests/test_stage9_edifact_bridge_baseline_snapshot.py`
	- Regeneration helper: `scripts/regenerate_stage9_edifact_baseline.py`
- Spec-reader EDI layout extension:
	- EDIFACT-style source paths (`/EDIFACT/...`) and UNB/UNH segment hints map to the shared `x12_segment` extraction layout.
	- Source/target disambiguation now uses value-signature heuristics so duplicate xpath-style columns prefer EDI paths (`/X12/...`, `/EDIFACT/...`) as `source_xpath` and document paths (`/root/...`) as `target_xpath`.
	- Workbook-style EDIFACT mapping sheet coverage is included in parser tests (header-offset + duplicate xpath columns + rule extraction assertions).
- Cross-format EDI bridge coverage:
	- X12 input + JSON output and EDIFACT input + JSON output are covered in bridge tests when spec layout is `x12_segment`.
- Guided EDIFACT sample spec fixture:
	- Sample workbook: `samples/spec_edifact_guided.xlsx`
	- Sample workbook: `samples/spec_edifact_orders_guided.xlsx`
	- Header style mirrors JABIL X12 mapping sheets to keep parser expectations realistic.
- Stage 9 EDIFACT parser baseline snapshot:
	- Artifact: `results/stage9_edifact_parser_baseline.json`
	- Test: `tests/test_stage9_edifact_parser_baseline_snapshot.py`
	- Regeneration helper: `scripts/regenerate_stage9_edifact_parser_baseline.py`
	- Baseline projection compares both guided fixtures (`INVOIC` and `ORDERS`) in one snapshot payload.
- Stage 9 one-command baseline regeneration:
	- Helper: `scripts/regenerate_stage9_all_baselines.py`
	- Regenerates JSON/X12/EDIFACT bridge baselines and EDIFACT parser baseline in one pass.

## Stage 9 Performance Guardrails

- Large EDI payload fixtures:
	- `samples/input_large.x12`, `samples/output_large.x12`
	- `samples/input_large.edifact`, `samples/output_large.edifact`
- Guardrail test suite: `tests/test_stage9_edi_performance_guardrail.py`
	- `STAGE9_PERF_X12_MAX_SECONDS` (default `8.0`)
	- `STAGE9_PERF_EDIFACT_MAX_SECONDS` (default `8.0`)

## Stage 9 Exit Checklist

- Payload combinations verified:
	- XML↔XML, JSON↔JSON, X12↔X12, EDIFACT↔EDIFACT, `.edi` flavor autodetect
	- Cross-format EDI flows (`x12_segment` specs only): X12/EDIFACT input + JSON/XML output
- Baseline suites green:
	- `tests/test_stage9_json_bridge_baseline_snapshot.py`
	- `tests/test_stage9_x12_bridge_baseline_snapshot.py`
	- `tests/test_stage9_edifact_bridge_baseline_snapshot.py`
	- `tests/test_stage9_edifact_parser_baseline_snapshot.py`
- Performance guardrails green:
	- `tests/test_stage9_edi_performance_guardrail.py`
- Regression suites green:
	- `tests/test_stage9_adapter_bridge.py`
	- `tests/test_stage9_adapters.py`
	- `tests/test_web.py`
- Regeneration helpers verified:
	- Individual scripts under `scripts/regenerate_stage9_*`
	- Consolidated script: `scripts/regenerate_stage9_all_baselines.py`

## Stage 9 Sign-off Evidence (2026-05-18)

- Baselines relocked after final browser parity fix:
	- Command: `.venv/Scripts/python.exe scripts/regenerate_stage9_all_baselines.py`
	- Artifacts updated: `results/stage9_json_bridge_baseline.json`, `results/stage9_x12_bridge_baseline.json`, `results/stage9_edifact_bridge_baseline.json`, `results/stage9_edifact_parser_baseline.json`
- Stage 9 closure suites:
	- Command: `.venv/Scripts/python.exe -m pytest tests/test_stage9_edi_performance_guardrail.py tests/test_stage9_json_bridge_baseline_snapshot.py tests/test_stage9_x12_bridge_baseline_snapshot.py tests/test_stage9_edifact_bridge_baseline_snapshot.py tests/test_stage9_edifact_parser_baseline_snapshot.py tests/test_stage9_adapter_bridge.py tests/test_web.py tests/test_stage9_group_fallback.py -q`
	- Result: `33 passed`
- Full repository regression:
	- Command: `.venv/Scripts/python.exe -m pytest -q`
	- Result: `369 passed`
- Browser-local UAT (cross-format EDI bridge):
	- Scenario: `samples/spec_edifact_guided.xlsx` + `samples/input.edifact` + `samples/output.json`
	- Result: validation succeeded in browser-local mode; result panel rendered with Stage 9 bridge badge and no format-gate error.
