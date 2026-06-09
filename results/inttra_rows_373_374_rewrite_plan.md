# Inttra Row 373/374 Deterministic Rewrite Plan

## Goal
Convert the two remaining procedural rows into deterministic, parser-friendly rules without changing current runtime-safe behavior.

- Current safe runtime status remains PASS.
- These rewrites are for future promotion from parsed_only to enforced.

## Scope
- Row 373
- Row 374
- Target: /equipments.haulage.points.dates
- Source fields:
  - /X12/TS_300/GROUP_4/DTM/DTM01
  - /X12/TS_300/GROUP_4/DTM/DTM02
  - /X12/TS_300/GROUP_4/DTM/DTM03

## Problem Summary
Both rows are compound procedural sentences mixing:
- location guard logic (N101 code)
- date qualifier logic (DTM01/DTM02 checks)
- mapping action (direct map / concatenate)
- date-format token mapping

This mixed phrasing is currently classified as procedural and kept parsed_only.

## Rewrite Strategy
Split into explicit deterministic families already supported by the validator:
- Family A: if_expression_chain_map (or equivalent explicit if/elseif clauses)
- Family B: field_concat_mapping (for DTM02 + DTM03)
- Family C: date_format_mapping (for CCYYMMDD / CCYYMMDDHHMM)

## Row 373 (Recommended Canonical Rewrite)
Use a single explicit conditional mapping statement where each branch maps the same deterministic expression.

Canonical shape:
- If N101 = "LL" and (DTM01 = "144" or DTM01 = "087") then map DTM02 + DTM03 to Target
- Elseif N101 = "SF" and (DTM01 = "118" or DTM01 = "996") then map DTM02 + DTM03 to Target
- Elseif N101 = "ST" and DTM01 = "002" then map DTM02 + DTM03 to Target
- Elseif N101 = "CL" and DTM01 = "992" then map DTM02 + DTM03 to Target

Notes:
- Keep one normalized qualifier field per comparison branch where possible.
- Avoid "Direct Map" prose in same sentence as concatenation action.

## Row 374 (Recommended Canonical Rewrite)
Split into two deterministic rules to remove ambiguity between date-only and date+time outcomes.

Rule 374A (date+time):
- If N101 in {LL,SF,ST,CL} and DTM02 exists and DTM03 exists then map "CCYYMMDDHHMM" to Target

Rule 374B (date only fallback):
- If N101 in {LL,SF,ST,CL} and DTM02 exists and DTM03 not exists then map "CCYYMMDD" to Target

Notes:
- Do not keep free text such as "then"/blank pipes between fragments.
- Keep each rule to one action family only.

## Acceptance Checks
After rewriting rows 373/374 in the workbook:
1. Run the exact strict pair used in reliability runs.
2. Expect parsed_only to reduce by up to 2 more rows.
3. Expect unsupported to remain 0.
4. Expect status to remain PASS (no new hard failures).

## Validation Command
C:/Users/mohdshuqor.nordin/AppData/Local/Python/pythoncore-3.14-64/python.exe main.py --spec "rules/Inttra-Contivo_X12_300_5030_to_JSON_BOOKINGINBOUND 1 Update.xlsx" --input "samples/SampleforV1 - Copy.edi" --output "samples/BOOKINGINBOUND_1 1.json" --mode structure_strict --report "results/debug_inttra_reliability_after_373_374_rewrite.json"
