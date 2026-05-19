# Inttra BOOKINGINBOUND Patch Plan (Fix-First)

- Source report id: 3080472b-02bc-4e0d-ab84-5ddbb8778c40
- Status: FAIL
- Total errors: 158

## Priority Order

### 1. /packageDetails.dangerousGoods (14 issues)

- Rows to update in workbook: 143, 144, 145, 146, 148, 149, 150, 151, 152, 158, 159, 161
- Failure mix: source_target_missing: 8; if_equals_mismatches: 4; constant_mismatches: 1; translated_value_mismatches: 1
- Suggested edits:
  - Add or correct target node creation mapping so the target path is emitted when source is present.
  - Review IF_EQUALS condition literals and branch mapping; align expected output value/path with true-condition branch.
  - Update translation/code-list table for the listed source values or map to the correct normalized output codes.
  - Verify hardcoded constant values and move constant to the active branch where target path is generated.
- Example failure: Row 143 | Target: /packageDetails.dangerousGoods | Source exists but target is missing

### 2. /parties.contacts.emails (10 issues)

- Rows to update in workbook: 89, 90, 114, 115
- Failure mix: if_equals_mismatches: 8; source_target_missing: 2
- Suggested edits:
  - Add or correct target node creation mapping so the target path is emitted when source is present.
  - Review IF_EQUALS condition literals and branch mapping; align expected output value/path with true-condition branch.
- Example failure: Row 89 | Target: /parties.contacts.emails | Source exists but target is missing

### 3. /parties.contacts.faxes (10 issues)

- Rows to update in workbook: 92, 93, 117, 118
- Failure mix: if_equals_mismatches: 8; source_target_missing: 2
- Suggested edits:
  - Add or correct target node creation mapping so the target path is emitted when source is present.
  - Review IF_EQUALS condition literals and branch mapping; align expected output value/path with true-condition branch.
- Example failure: Row 92 | Target: /parties.contacts.faxes | Source exists but target is missing

### 4. /equipments.equipmentSizeCode (7 issues)

- Rows to update in workbook: 182, 183, 184, 237, 238
- Failure mix: if_equals_mismatches: 4; source_exists_mismatches: 2; translated_value_mismatches: 1
- Suggested edits:
  - Review IF_EQUALS condition literals and branch mapping; align expected output value/path with true-condition branch.
  - Check SOURCE_EXISTS guard and ensure target assignment occurs whenever guarded source token exists.
  - Update translation/code-list table for the listed source values or map to the correct normalized output codes.
- Example failure: Row 184 | Target: /equipments.equipmentSizeCode | Translated target is missing for source value 2

### 5. /equipments.atmosphere (6 issues)

- Rows to update in workbook: 191, 192, 193, 241, 242, 243
- Failure mix: source_exists_mismatches: 4; source_target_missing: 2
- Suggested edits:
  - Add or correct target node creation mapping so the target path is emitted when source is present.
  - Check SOURCE_EXISTS guard and ensure target assignment occurs whenever guarded source token exists.
- Example failure: Row 193 | Target: /equipments.atmosphere | Source exists but target is missing

### 6. /equipments.haulage.haulage (6 issues)

- Rows to update in workbook: 218, 250
- Failure mix: if_equals_mismatches: 4; translated_value_mismatches: 2
- Suggested edits:
  - Review IF_EQUALS condition literals and branch mapping; align expected output value/path with true-condition branch.
  - Update translation/code-list table for the listed source values or map to the correct normalized output codes.
- Example failure: Row 218 | Target: /equipments.haulage.haulage | Translated target is missing for source value PP

### 7. /equipments.haulage.points.haulageparty.address (6 issues)

- Rows to update in workbook: 224, 225, 226, 256, 257, 258
- Failure mix: source_target_missing: 6
- Suggested edits:
  - Add or correct target node creation mapping so the target path is emitted when source is present.
- Example failure: Row 224 | Target: /equipments.haulage.points.haulageparty.address | Source exists but target is missing

### 8. /equipments.haulage.points.haulageparty.address.country (6 issues)

- Rows to update in workbook: 227, 228, 259, 260
- Failure mix: constant_mismatches: 2; source_exists_mismatches: 2; source_target_missing: 2
- Suggested edits:
  - Add or correct target node creation mapping so the target path is emitted when source is present.
  - Check SOURCE_EXISTS guard and ensure target assignment occurs whenever guarded source token exists.
  - Verify hardcoded constant values and move constant to the active branch where target path is generated.
- Example failure: Row 228 | Target: /equipments.haulage.points.haulageparty.address.country | Source exists but target is missing

### 9. /parties.address (6 issues)

- Rows to update in workbook: 82, 83, 84, 107, 108, 109
- Failure mix: source_target_missing: 6
- Suggested edits:
  - Add or correct target node creation mapping so the target path is emitted when source is present.
- Example failure: Row 82 | Target: /parties.address | Source exists but target is missing

### 10. /parties.address.Country (6 issues)

- Rows to update in workbook: 85, 86, 110, 111
- Failure mix: constant_mismatches: 2; source_exists_mismatches: 2; source_target_missing: 2
- Suggested edits:
  - Add or correct target node creation mapping so the target path is emitted when source is present.
  - Check SOURCE_EXISTS guard and ensure target assignment occurs whenever guarded source token exists.
  - Verify hardcoded constant values and move constant to the active branch where target path is generated.
- Example failure: Row 86 | Target: /parties.address.Country | Source exists but target is missing

### 11. /parties.contacts.phones (6 issues)

- Rows to update in workbook: 95, 120
- Failure mix: if_equals_mismatches: 4; source_target_missing: 2
- Suggested edits:
  - Add or correct target node creation mapping so the target path is emitted when source is present.
  - Review IF_EQUALS condition literals and branch mapping; align expected output value/path with true-condition branch.
- Example failure: Row 95 | Target: /parties.contacts.phones | Source exists but target is missing

### 12. /transactionContact.emails (6 issues)

- Rows to update in workbook: 3, 7, 8
- Failure mix: if_equals_mismatches: 3; translated_value_mismatches: 2; source_target_missing: 1
- Suggested edits:
  - Add or correct target node creation mapping so the target path is emitted when source is present.
  - Review IF_EQUALS condition literals and branch mapping; align expected output value/path with true-condition branch.
  - Update translation/code-list table for the listed source values or map to the correct normalized output codes.
- Example failure: Row 3 | Target: /transactionContact.emails | Source exists but target is missing

### 13. /transactionLocations.locationDates (6 issues)

- Rows to update in workbook: 68, 70, 71, 72
- Failure mix: if_equals_mismatches: 2; source_target_missing: 2; concat_mismatches: 1; field_concat_mismatches: 1
- Suggested edits:
  - Add or correct target node creation mapping so the target path is emitted when source is present.
  - Review IF_EQUALS condition literals and branch mapping; align expected output value/path with true-condition branch.
  - Rebuild CONCAT expression order/delimiter to match expected output format for the target path.
- Example failure: Row 71 | Target: /transactionLocations.locationDates | Source exists but target is missing

### 14. /equipments.airFlow (4 issues)

- Rows to update in workbook: 189, 190, 239, 240
- Failure mix: source_exists_mismatches: 2; source_target_missing: 2
- Suggested edits:
  - Add or correct target node creation mapping so the target path is emitted when source is present.
  - Check SOURCE_EXISTS guard and ensure target assignment occurs whenever guarded source token exists.
- Example failure: Row 190 | Target: /equipments.airFlow | Source exists but target is missing

### 15. /equipments.reeferHandling (4 issues)

- Rows to update in workbook: 197, 207, 247, 249
- Failure mix: if_equals_mismatches: 2; source_target_missing: 1; startswith_substring_mismatches: 1
- Suggested edits:
  - Add or correct target node creation mapping so the target path is emitted when source is present.
  - Review IF_EQUALS condition literals and branch mapping; align expected output value/path with true-condition branch.
  - Validate substring STARTSWITH extraction indices and ensure source token exists before slicing.
- Example failure: Row 247 | Target: /equipments.reeferHandling | Source exists but target is missing

### 16. /equipments.temperature (4 issues)

- Rows to update in workbook: 195, 246
- Failure mix: if_equals_mismatches: 2; source_target_missing: 2
- Suggested edits:
  - Add or correct target node creation mapping so the target path is emitted when source is present.
  - Review IF_EQUALS condition literals and branch mapping; align expected output value/path with true-condition branch.
- Example failure: Row 195 | Target: /equipments.temperature | Source exists but target is missing

### 17. /parties.contacts (4 issues)

- Rows to update in workbook: 87, 112
- Failure mix: if_equals_mismatches: 4
- Suggested edits:
  - Review IF_EQUALS condition literals and branch mapping; align expected output value/path with true-condition branch.
- Example failure: Row 87 | Target: /parties.contacts | Conditional mapped target is missing

### 18. /transportLegs.vesselFlagCountry (4 issues)

- Rows to update in workbook: 21, 22, 23
- Failure mix: source_target_missing: 2; constant_mismatches: 1; source_exists_mismatches: 1
- Suggested edits:
  - Add or correct target node creation mapping so the target path is emitted when source is present.
  - Check SOURCE_EXISTS guard and ensure target assignment occurs whenever guarded source token exists.
  - Verify hardcoded constant values and move constant to the active branch where target path is generated.
- Example failure: Row 22 | Target: /transportLegs.vesselFlagCountry | Source exists but target is missing

### 19. /equipments.haulage.points.haulageparty (3 issues)

- Rows to update in workbook: 221, 253, 254
- Failure mix: if_equals_mismatches: 2; char_offset_mismatches: 1
- Suggested edits:
  - Review IF_EQUALS condition literals and branch mapping; align expected output value/path with true-condition branch.
  - Adjust character-offset extraction positions and confirm source field length assumptions.
- Example failure: Row 221 | Target: /equipments.haulage.points.haulageparty | Conditional mapped target is missing

### 20. /equipments.netVolume (3 issues)

- Rows to update in workbook: 187, 188
- Failure mix: if_equals_mismatches: 2; source_target_missing: 1
- Suggested edits:
  - Add or correct target node creation mapping so the target path is emitted when source is present.
  - Review IF_EQUALS condition literals and branch mapping; align expected output value/path with true-condition branch.
- Example failure: Row 188 | Target: /equipments.netVolume | Source exists but target is missing

### 21. /equipments.netWeight (3 issues)

- Rows to update in workbook: 185, 186
- Failure mix: if_equals_mismatches: 2; source_target_missing: 1
- Suggested edits:
  - Add or correct target node creation mapping so the target path is emitted when source is present.
  - Review IF_EQUALS condition literals and branch mapping; align expected output value/path with true-condition branch.
- Example failure: Row 186 | Target: /equipments.netWeight | Source exists but target is missing

### 22. /packageDetails.outOfGaugeDetails.height (3 issues)

- Rows to update in workbook: 134, 135
- Failure mix: if_equals_mismatches: 2; source_target_missing: 1
- Suggested edits:
  - Add or correct target node creation mapping so the target path is emitted when source is present.
  - Review IF_EQUALS condition literals and branch mapping; align expected output value/path with true-condition branch.
- Example failure: Row 135 | Target: /packageDetails.outOfGaugeDetails.height | Source exists but target is missing

### 23. /packageDetails.outOfGaugeDetails.width (3 issues)

- Rows to update in workbook: 132, 133
- Failure mix: if_equals_mismatches: 2; source_target_missing: 1
- Suggested edits:
  - Add or correct target node creation mapping so the target path is emitted when source is present.
  - Review IF_EQUALS condition literals and branch mapping; align expected output value/path with true-condition branch.
- Example failure: Row 133 | Target: /packageDetails.outOfGaugeDetails.width | Source exists but target is missing

### 24. /transportLegs.endLocation.locationDates (3 issues)

- Rows to update in workbook: 37, 39, 40
- Failure mix: source_target_missing: 2; constant_mismatches: 1
- Suggested edits:
  - Add or correct target node creation mapping so the target path is emitted when source is present.
  - Verify hardcoded constant values and move constant to the active branch where target path is generated.
- Example failure: Row 39 | Target: /transportLegs.endLocation.locationDates | Source exists but target is missing

### 25. /transportLegs.startLocation.locationDates (3 issues)

- Rows to update in workbook: 27, 29, 30
- Failure mix: source_target_missing: 2; constant_mismatches: 1
- Suggested edits:
  - Add or correct target node creation mapping so the target path is emitted when source is present.
  - Verify hardcoded constant values and move constant to the active branch where target path is generated.
- Example failure: Row 29 | Target: /transportLegs.startLocation.locationDates | Source exists but target is missing

### 26. /packageDetails.dangerousGoods.contacts (2 issues)

- Rows to update in workbook: 165, 166
- Failure mix: source_exists_mismatches: 1; source_target_missing: 1
- Suggested edits:
  - Add or correct target node creation mapping so the target path is emitted when source is present.
  - Check SOURCE_EXISTS guard and ensure target assignment occurs whenever guarded source token exists.
- Example failure: Row 165 | Target: /packageDetails.dangerousGoods.contacts | Source exists but target is missing

### 27. /packageDetails.dangerousGoods.contacts.phones (2 issues)

- Rows to update in workbook: 167, 171
- Failure mix: if_equals_mismatches: 1; source_target_missing: 1
- Suggested edits:
  - Add or correct target node creation mapping so the target path is emitted when source is present.
  - Review IF_EQUALS condition literals and branch mapping; align expected output value/path with true-condition branch.
- Example failure: Row 167 | Target: /packageDetails.dangerousGoods.contacts.phones | Source exists but target is missing

### 28. /packageDetails.outOfGaugeDetails.length (2 issues)

- Rows to update in workbook: 130, 131
- Failure mix: if_equals_mismatches: 1; source_target_missing: 1
- Suggested edits:
  - Add or correct target node creation mapping so the target path is emitted when source is present.
  - Review IF_EQUALS condition literals and branch mapping; align expected output value/path with true-condition branch.
- Example failure: Row 131 | Target: /packageDetails.outOfGaugeDetails.length | Source exists but target is missing

### 29. /packageDetails.splitGoodsDetailsList (2 issues)

- Rows to update in workbook: 138
- Failure mix: source_exists_mismatches: 1; source_target_missing: 1
- Suggested edits:
  - Add or correct target node creation mapping so the target path is emitted when source is present.
  - Check SOURCE_EXISTS guard and ensure target assignment occurs whenever guarded source token exists.
- Example failure: Row 138 | Target: /packageDetails.splitGoodsDetailsList | Source exists but target is missing

### 30. /packageDetails.splitGoodsDetailsList.grossVolume (2 issues)

- Rows to update in workbook: 142
- Failure mix: source_exists_mismatches: 1; source_target_missing: 1
- Suggested edits:
  - Add or correct target node creation mapping so the target path is emitted when source is present.
  - Check SOURCE_EXISTS guard and ensure target assignment occurs whenever guarded source token exists.
- Example failure: Row 142 | Target: /packageDetails.splitGoodsDetailsList.grossVolume | Source exists but target is missing

### 31. /packageDetails.splitGoodsDetailsList.grossWeight (2 issues)

- Rows to update in workbook: 140
- Failure mix: source_exists_mismatches: 1; source_target_missing: 1
- Suggested edits:
  - Add or correct target node creation mapping so the target path is emitted when source is present.
  - Check SOURCE_EXISTS guard and ensure target assignment occurs whenever guarded source token exists.
- Example failure: Row 140 | Target: /packageDetails.splitGoodsDetailsList.grossWeight | Source exists but target is missing

### 32. /transactionLocations.Country (2 issues)

- Rows to update in workbook: 74, 75
- Failure mix: source_exists_mismatches: 1; source_target_missing: 1
- Suggested edits:
  - Add or correct target node creation mapping so the target path is emitted when source is present.
  - Check SOURCE_EXISTS guard and ensure target assignment occurs whenever guarded source token exists.
- Example failure: Row 75 | Target: /transactionLocations.Country | Source exists but target is missing

### 33. /transportLegs.endLocation.Country (2 issues)

- Rows to update in workbook: 42, 43
- Failure mix: source_exists_mismatches: 1; source_target_missing: 1
- Suggested edits:
  - Add or correct target node creation mapping so the target path is emitted when source is present.
  - Check SOURCE_EXISTS guard and ensure target assignment occurs whenever guarded source token exists.
- Example failure: Row 43 | Target: /transportLegs.endLocation.Country | Source exists but target is missing

### 34. /transportLegs.startLocation.Country (2 issues)

- Rows to update in workbook: 32, 33
- Failure mix: source_exists_mismatches: 1; source_target_missing: 1
- Suggested edits:
  - Add or correct target node creation mapping so the target path is emitted when source is present.
  - Check SOURCE_EXISTS guard and ensure target assignment occurs whenever guarded source token exists.
- Example failure: Row 33 | Target: /transportLegs.startLocation.Country | Source exists but target is missing

### 35. /packageDetails.goodsGrossVolume (1 issues)

- Rows to update in workbook: 129
- Failure mix: source_target_missing: 1
- Suggested edits:
  - Add or correct target node creation mapping so the target path is emitted when source is present.
- Example failure: Row 129 | Target: /packageDetails.goodsGrossVolume | Source exists but target is missing

### 36. /packageDetails.goodsGrossWeight (1 issues)

- Rows to update in workbook: 127
- Failure mix: source_target_missing: 1
- Suggested edits:
  - Add or correct target node creation mapping so the target path is emitted when source is present.
- Example failure: Row 127 | Target: /packageDetails.goodsGrossWeight | Source exists but target is missing

### 37. /transactionContact.faxes (1 issues)

- Rows to update in workbook: 2
- Failure mix: source_target_missing: 1
- Suggested edits:
  - Add or correct target node creation mapping so the target path is emitted when source is present.
- Example failure: Row 2 | Target: /transactionContact.faxes | Source exists but target is missing

### 38. /transactionContact.phones (1 issues)

- Rows to update in workbook: 1
- Failure mix: source_target_missing: 1
- Suggested edits:
  - Add or correct target node creation mapping so the target path is emitted when source is present.
- Example failure: Row 1 | Target: /transactionContact.phones | Source exists but target is missing

## Execution Loop

- Update workbook rows for top 3 target paths first, then re-run validation for the same spec/input/output trio.
- Confirm reduction in source_target_missing and if_equals_mismatches counts before proceeding to next 3 paths.
- Keep each round small to isolate behavioral impact and prevent collateral mapping regressions.

## Re-run Command

```powershell
Set-Location -LiteralPath "c:\Users\mohdshuqor.nordin\OneDrive - WiseTech Global\Documents\Mapping Validation Program"
& "C:/Users/mohdshuqor.nordin/AppData/Local/Python/pythoncore-3.14-64/python.exe" main.py --spec "rules/Inttra-Contivo_X12_300_5030_to_JSON_BOOKINGINBOUND 1 Update.xlsx" --input "samples/SampleforV1 - Copy.edi" --output "samples/BOOKINGINBOUND_1.json" --report "results/inttra_bookinginbound_sample_report.json"
```