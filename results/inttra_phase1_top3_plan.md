# Inttra Phase 1 Plan (Top 3 Targets)

Goal: reduce the highest-volume mapping failures first while keeping validator behavior stable.

## Scope

- Spec: rules/Inttra-Contivo_X12_300_5030_to_JSON_BOOKINGINBOUND 1 Update.xlsx
- Input: samples/SampleforV1 - Copy.edi
- Output: samples/BOOKINGINBOUND_1.json
- Baseline report: results/inttra_bookinginbound_sample_report.json

## Target 1: /packageDetails.dangerousGoods (14 issues)

- Workbook rows: 143, 144, 145, 146, 148, 149, 150, 151, 152, 158, 159, 161
- Failure mix:
  - source_target_missing: 8
  - if_equals_mismatches: 4
  - constant_mismatches: 1
  - translated_value_mismatches: 1
- Suggested edits:
  - Ensure target node creation is attached to the active branch when source token exists.
  - Verify IF_EQUALS literals and branch routing for DG related values.
  - Verify translation/code-list output for DG values.
  - Confirm hardcoded constants are applied in the same branch that writes the target path.

## Target 2: /parties.contacts.emails (10 issues)

- Workbook rows: 89, 90, 114, 115
- Failure mix:
  - if_equals_mismatches: 8
  - source_target_missing: 2
- Suggested edits:
  - Ensure contacts/emails target node is created in true-condition branches.
  - Align IF_EQUALS conditions to the actual source values in SampleforV1 - Copy.edi.

## Target 3: /parties.contacts.faxes (10 issues)

- Workbook rows: 92, 93, 117, 118
- Failure mix:
  - if_equals_mismatches: 8
  - source_target_missing: 2
- Suggested edits:
  - Ensure contacts/faxes target node is created in true-condition branches.
  - Align IF_EQUALS conditions to the actual source values in SampleforV1 - Copy.edi.

## Phase 1 Validation Loop

1. Update only the rows listed above.
2. Re-run validation with the same spec/input/output trio.
3. Confirm these three target paths drop in issue count before moving to next targets.

## Re-run Command

```powershell
Set-Location -LiteralPath "c:\Users\mohdshuqor.nordin\OneDrive - WiseTech Global\Documents\Mapping Validation Program"
& "C:/Users/mohdshuqor.nordin/AppData/Local/Python/pythoncore-3.14-64/python.exe" main.py --spec "rules/Inttra-Contivo_X12_300_5030_to_JSON_BOOKINGINBOUND 1 Update.xlsx" --input "samples/SampleforV1 - Copy.edi" --output "samples/BOOKINGINBOUND_1.json" --report "results/inttra_bookinginbound_sample_report.json"
```