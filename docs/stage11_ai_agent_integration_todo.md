# Stage 11 - AI Agent Integration for Undetected Rules (No API)

Stage 11 defines a local-first workflow where the browser validator remains the primary engine, and AI is used only as a fallback for undetected rules.

## Stage Goal

- Keep validation fully usable without any hosted API/server.
- Call AI only when new/unknown rule patterns are detected.
- Reduce token usage over time by continuously expanding local validator coverage.

## Recommended Architecture (Best Approach)

- Primary runtime: browser-local validator (`web/index.html`).
- AI usage model: human-triggered review in VS Code Copilot (no custom API endpoint).
- Detection gate: AI is invoked only when `unsupported` or `needs_review` rules exist.
- Artifact-driven loop: unknown rules are exported, reviewed, implemented, and regression-locked.

## Stage 11 To-Do List

### 11.1 Add Unknown Rule Gate in Browser Flow

- [ ] Ensure every validation run computes:
  - total parsed rules
  - enforced rules
  - unsupported/needs-review rules
- [ ] Add a strict AI gate condition:
  - if unsupported count = `0`, do not trigger AI workflow.
- [ ] Display a plain-English status card:
  - "All rules recognized" or "X rules need review".

### 11.2 Add Compact Undetected-Rule Export

- [ ] Add `Export Unknown Rules` button in browser UI.
- [ ] Export `results/unknown_rules_review.json`-compatible structure containing only minimal fields:
  - rule row ID
  - normalized rule text
  - source field/path
  - target field/path
  - parser/semantic confidence
  - reason code (`unsupported_pattern`, `ambiguous_condition`, etc.)
- [ ] Exclude full payload bodies and unrelated report sections from this export.

### 11.3 Add Stable Rule Fingerprint and Diff

- [ ] Compute deterministic fingerprint per rule (for example hash of normalized condition + source + target).
- [ ] Persist prior fingerprints as local baseline artifact.
- [ ] Classify rules on each run as:
  - unchanged
  - new
  - modified
- [ ] Restrict AI review set to `new + modified + unsupported` only.

### 11.4 Create a Token Budget Policy

- [ ] Define a maximum rule batch size per AI review request (example: 20-40 rules).
- [ ] Send only compact unknown-rule JSON, never full workbook when avoidable.
- [ ] Add prompt template for AI review with fixed fields and short outputs.
- [ ] Track per-run counts:
  - unknown rules sent to AI
  - accepted implementations
  - remaining unsupported rules

### 11.5 Add AI Review SOP (No API)

- [ ] Define team workflow:
  1. Run browser validator locally.
  2. Export unknown rules if count > 0.
  3. Open export in VS Code and request AI review.
  4. Implement suggested pattern handler.
  5. Re-run validation and confirm unsupported count drops.
- [ ] Keep this SOP in docs for non-technical users.

### 11.6 Add Safe Pattern-Handler Extension Path

- [ ] Centralize pattern recognition/normalization in one section of browser validator logic.
- [ ] Add one handler per new pattern family (avoid patching unrelated logic).
- [ ] Require deterministic behavior:
  - explicit match criteria
  - explicit fail reason when not matched

### 11.7 Add Regression Locks for New Patterns

- [ ] For every newly supported pattern, add at least:
  - one positive case
  - one negative case
  - one ambiguity case (if applicable)
- [ ] Update or add snapshot artifact showing coverage drift.
- [ ] Fail regression if previously supported pattern becomes unsupported.

### 11.8 Add Coverage Trend Metrics

- [ ] Track trend per run:
  - unsupported rule count
  - parsed-only count
  - enforced count
- [ ] Add simple trend view in report summary (current run vs previous baseline).
- [ ] Declare Stage 11 success target (example):
  - unsupported ratio < 2% on active partner specs.

### 11.9 Add Operations Policy for Offline Mode

- [ ] Document expected behavior when laptop/VS Code is offline:
  - known rules still validate locally.
  - unknown-rule AI interpretation is deferred.
- [ ] Add queue artifact for pending AI review tasks (`results/pending_ai_review.json`).

### 11.10 Stage 11 Exit Criteria

- [ ] No-API workflow is documented and repeatable by non-technical users.
- [ ] AI gate works (no AI requests when unsupported count is `0`).
- [ ] Unknown-rule export is compact and stable.
- [ ] Rule fingerprint diff is active and tested.
- [ ] Regression coverage prevents pattern-support regressions.
- [ ] Trend metrics show decreasing unknown-rule rate across recent specs.

## Why This Is the Best Approach for Current Constraints

- No server dependency: compatible with strict infrastructure limits.
- Lowest operational cost: AI used only on novel gaps.
- Scales gradually: each new handler reduces future AI usage.
- Maintains trust: validator remains deterministic and test-backed.

## Expected Token Usage Behavior

- Short term: small AI usage for currently unknown patterns.
- Medium term: usage declines as pattern coverage increases.
- Long term: mostly steady low usage, with occasional spikes for truly new partner phrasing.

This means: yes, as validator coverage improves, token usage should generally decrease because fewer undetected rules need AI review.