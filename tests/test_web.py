from pathlib import Path


def _web_source() -> str:
    web_path = Path(__file__).resolve().parents[1] / "web" / "index.html"
    return web_path.read_text(encoding="utf-8")


def test_web_structure_strict_has_conditional_structure_guard():
    source = _web_source()
    assert "function structureConditionApplies(conditionText, sourceValues)" in source
    assert "if (normalized.includes('if source') || normalized.includes('source exists'))" in source


def test_web_structure_strict_has_per_parent_cardinality_check():
    source = _web_source()
    assert "structureParentCardinalityRules" in source
    assert "Per-parent cardinality violation under" in source
    assert "child_cardinality_violations" in source


def test_web_structure_strict_has_required_attribute_check():
    source = _web_source()
    assert "structureRequiredAttributeRules" in source
    assert "Required target attribute is missing" in source
    assert "required_target_attributes_missing" in source


def test_web_structure_strict_has_choice_and_order_checks():
    source = _web_source()
    assert "choice_group_violations" in source
    assert "ordered_sibling_groups" in source
    assert "Sibling order violation: children are not in the expected sequence" in source


def test_web_structure_strict_has_namespace_mismatch_check():
    source = _web_source()
    assert "parseXmlFileWithNamespaces" in source
    assert "Namespace mismatch: target node uses a different namespace than expected" in source
    assert "namespace_mismatches" in source


def test_web_structure_summary_includes_new_categories():
    source = _web_source()
    assert "Required details missing" in source
    assert "Repeated child items have too many or too few values" in source
    assert "Either/or choice rules not satisfied" in source
    assert "Items appear in the wrong order" in source
    assert "Namespace format does not match expected" in source
    assert "Repeat count problems" in source
    assert "if (value > 0)" in source


def test_web_structure_mode_collapses_unexpected_node_rows_for_display():
    source = _web_source()
    assert "function filterUnexpectedNodeErrorsToTopLevel(errors)" in source
    assert "unexpected_target_nodes: filterUnexpectedNodeErrorsToTopLevel(visibleErrorSections.unexpected_target_nodes || [])" in source
    assert "const seenNormalizedPaths = new Set();" in source
    assert "if (seenNormalizedPaths.has(normalizedTarget)) return false;" in source
    assert "Unexpected extra sections (all paths):" in source


def test_web_semantic_suggestion_payload_parity_fields_present():
    source = _web_source()
    assert "const SEMANTIC_PROFILE_CONFIG = {" in source
    assert "function getSemanticProfile(specFileName)" in source
    assert "profileKey: 'global'" in source
    assert "function canonicalizeSemanticConditionWithTrace(conditionText, semanticProfile = null)" in source
    assert "function suggestPatternFamilies(conditionText, topN = 3, semanticProfile = null)" in source
    assert "function extractSemanticParts(conditionText, fieldAliases)" in source
    assert "function analyzeSemanticAmbiguity(suggestions, thresholds)" in source
    assert "function buildSuggestedCanonicalRewrite(familyName, semanticParts, ambiguity)" in source
    assert "unsupported_rule_suggestions_provided" in source
    assert "high_similarity_unsupported_rules" in source
    assert "condition_transform_applied_rules" in source
    assert "ambiguous_unsupported_rules" in source
    assert "auto_promote_candidate_rules" in source
    assert "field_alias_normalized_rules" in source
    assert "normalized_condition" in source
    assert "nearest_family" in source
    assert "similarity_score" in source
    assert "similarity_confidence" in source
    assert "nearest_patterns" in source
    assert "why_not_enforced" in source
    assert "try_normalized_form" in source
    assert "semantic_parts" in source
    assert "ambiguous_families" in source
    assert "ambiguity_reason" in source
    assert "suggested_canonical_rewrite" in source
    assert "future_auto_promotion_eligible" in source
    assert "semantic_profile" in source
    assert "semantic_summary" in source
    assert "promote_to_generic_candidates" in source
    assert "Semantic rule coverage:" in source


def test_web_supports_local_multi_format_payload_bridge_without_api():
    source = _web_source()
    assert "Input Payload (XML, JSON, X12, EDIFACT)" in source
    assert "Output Payload (XML, JSON, X12, EDIFACT)" in source
    assert "accept=\".xml,.json,.x12,.edifact,.edi\"" in source
    assert "async function parsePayloadForValidation(payloadFile)" in source
    assert "function canonicalJsonToXml(jsonValue)" in source
    assert "function canonicalX12ToXml(x12Text)" in source
    assert "function canonicalEdifactToXml(edifactText)" in source
    assert "function detectEdiFlavor(rawText)" in source
    assert "Input and output payload formats must match, or provide X12/EDIFACT input with JSON/XML output when the spec layout is x12_segment." in source
    assert "crossFormatBridge" in source
    assert "stripGroupTokens" in source
    assert "mode: crossFormatBridge ? 'cross_format' : 'homogeneous'" in source
    assert "adapter_pipeline" in source
    assert "payload_format" in source


def test_web_normalize_xpath_supports_dot_notation_targets():
    source = _web_source()
    assert "function normalizeXpath(xpath, rootName)" in source
    assert ".flatMap((segment) => segment.split('.'))" in source
    assert "if (normalizedRoot && expanded[0].toLowerCase() === normalizedRoot.toLowerCase())" in source


def test_web_value_mismatch_comparison_normalizes_scalars():
    source = _web_source()
    assert "function normalizeComparableValue(value)" in source
    assert "function comparableValuesEqual(left, right)" in source
    assert "function hasComparableValueOverlap(leftValues, rightValues)" in source
    assert "!hasComparableValueOverlap(srcVals, tgtVals)" in source
    assert "!hasDerivedSourceOverlap(srcVals, tgtVals)" in source
    assert "function looksLikeConditionCell(value)" in source
    assert "function resolveConditionText(row, primaryCol, columns, excludedColumns)" in source


def test_web_if_source_rule_excludes_multiline_conversion():
    """isIfSourceMapRule must not fire for multi-branch conversion conditions."""
    source = _web_source()
    assert "normalized.includes('elseif')" in source or "normalized.includes(\"elseif\")" in source
    assert "normalized.startsWith('conversion:')" in source or 'normalized.startsWith("conversion:")' in source


def test_web_direct_map_inline_filter_is_supported():
    source = _web_source()
    assert "function extractDirectMapInlineFilter(condText)" in source
    assert "const directMapFilter = extractDirectMapInlineFilter(condTextRaw || condText);" in source
    assert "inlineFilterApplies && srcHasValue && !tgtHasValue" in source


def test_web_supports_additional_condition_families_for_manual_review_reduction():
    source = _web_source()
    assert "function extractStandaloneDirectMapGuard(condText)" in source
    assert "function extractGuardOnlyCondition(condText)" in source
    assert "function extractMultiConditionAndMap(condText)" in source
    assert "function extractIfExpressionChainMap(condText)" in source
    assert "function evaluateBooleanExpr(expr, baseXpath, srcDoc)" in source
    assert "function extractStartsWithReplaceMapping(condText)" in source
    assert "function extractStartsWithReplaceAppendMapping(condText)" in source
    assert "function extractStartsWithSubstringMapping(condText)" in source
    assert "function extractTokenExistsTargetMapping(condText)" in source
    assert "function extractIfInListMapToTarget(condText)" in source
    assert "function extractExistsThenDirectMap(condText)" in source
    assert "function extractStartsWithTargetConstant(condText)" in source
    assert "function extractFieldConcatMapping(condText)" in source
    assert "function extractMultiBranchDirectConcatMapping(condText)" in source
    assert "function extractDateFormatMapping(condText)" in source
    assert "function dateFormatToRegex(format)" in source
    assert "function extractDirectSubstringConcatSourceMapping(condText)" in source
    assert "function extractComputeStatement(condText)" in source
    assert "function extractInstructionOnlyCondition(condText)" in source
    assert "function resolveExpectedFromTargetSpec(baseXpath, srcVals, srcDoc, targetLiteral, targetToken, targetFromSource)" in source
    assert "const directGuard = extractStandaloneDirectMapGuard(condText);" in source
    assert "const multiAnd = extractMultiConditionAndMap(condText);" in source
    assert "if (!handledCondition && ifExpressionChainMap !== null)" in source
    assert "if (!handledCondition && guardOnlyCondition !== null && Boolean(src))" in source
    assert "if (!handledCondition && tokenExistsTarget !== null)" in source
    assert "if (!handledCondition && inListMapToTarget !== null)" in source
    assert "if (!handledCondition && startsWithSubstring !== null)" in source
    assert "if (!handledCondition && existsThenDirectMap !== null)" in source
    assert "if (!handledCondition && startsWithTargetConstant !== null)" in source
    assert "if (!handledCondition && fieldConcatMapping !== null)" in source
    assert "if (!handledCondition && multiBranchDirectConcat !== null)" in source
    assert "if (!handledCondition && dateFormatMapping !== null)" in source
    assert "if (!handledCondition && directSubstringConcat !== null)" in source


def test_web_supports_if_in_list_length_and_char_offset_mappings():
    source = _web_source()
    assert "function extractIfInListSubstringSourceMapping(condText)" in source
    assert "function extractIfEqualsSubstringFromTokenMapping(condText)" in source
    assert "function extractCharOffsetMapping(condText)" in source
    assert "function extractLengthBasedMapping(condText)" in source
    assert "function resolveLengthMapAction(baseXpath, srcVals, srcDoc, action)" in source
    assert "const normalizedExpected = cleanCell(expectedVal);" in source
    assert "if (normalizedExpected) {" in source
    assert "const inListSubstring = extractIfInListSubstringSourceMapping(condText);" in source
    assert "const ifEqualsSubstringFromToken = extractIfEqualsSubstringFromTokenMapping(condText);" in source
    assert "const charOffset = extractCharOffsetMapping(condText);" in source
    assert "const lengthBased = extractLengthBasedMapping(condText);" in source


def test_web_xpath_values_supports_json_array_item_fallback():
    source = _web_source()
    assert "if (/\\[\\*\\]/.test(candidate))" in source
    assert "candidate.replace(/\\[\\*\\]/g, '/item')" in source


def test_web_xpath_values_supports_target_alias_fallbacks():
    source = _web_source()
    assert "function buildAliasXpathCandidates(xpath)" in source
    assert "{ pattern: /\\/partyName$/i, replacements: ['/partyName1'] }" in source
    assert "{ pattern: /\\/postal_code$/i, replacements: ['/postalCode'] }" in source
    assert "{ pattern: /\\/SizeCodeType$/i, replacements: ['/sizeCodeType'] }" in source
    assert "{ pattern: /\\/SizeCodeValue$/i, replacements: ['/sizeCodeValue'] }" in source


def test_web_direct_map_prefers_full_condition_sentence_when_present():
    source = _web_source()
    assert "const directMapHasAdditionalDirectives = Boolean(" in source
    assert "function looksLikeAmbiguousComplexCondition(condText)" in source
    assert "if (isDirectMappingRule && srcHasValue && (isIfSourceRule || (!specializedConditionDetected && !looksLikeAmbiguousComplexCondition(condText))))" in source
    assert "if (!handledCondition && isDirectMapRuleCondition(condText) && !specializedConditionDetected)" in source


def test_web_extract_rules_filters_non_rule_rows():
    source = _web_source()
    assert "let skippedNonRuleRows = 0;" in source
    assert "skipped_non_rule_rows: skippedNonRuleRows" in source
    assert "if (!hasAnyRuleSignal || (!sourceXpath && isNarrativeOnlyCondition(resolvedCondition)))" in source


def test_web_emits_rule_decision_diagnostics_payload():
    source = _web_source()
    assert "const ruleDecisions = [];" in source
    assert "const errorDiagnostics = [];" in source
    assert "function estimateRuleConfidence(status, hasCondition, isDirectMap, similarityScore = 0)" in source
    assert "if (status === 'parsed_only') return 0.55;" in source
    assert "if (status === 'unsupported') {" in source
    assert "Math.max(0.05, Math.min(0.45, Number(similarityScore || 0)))" in source
    assert "rule_decisions: ruleDecisions" in source
    assert "error_diagnostics: errorDiagnostics" in source


def test_web_bridge_shows_preview_label_and_warning():
    source = _web_source()
    assert "adapter-preview-badge" in source
    assert "runtime-summary-card" in source
    assert "attention-note" in source
    assert "What \"too many or too few values\" means" in source
    assert "Stage 9 bridge mode (cross-format):" in source
    assert "Stage 9 bridge mode:" in source
    assert "Cross-format bridge mode:" in source
    assert "Adapter pipeline mode:" in source
    assert "Spec layout:" in source
    assert "Payload route:" in source
    assert "Adapter path:" in source
    assert "runtime_summary" in source


def test_web_supports_spec_coverage_mode_without_payload_files():
    source = _web_source()
    assert '<option value="spec_coverage">Spec coverage only (no payloads)</option>' in source
    assert "function validateSpecCoverageOnly(specFile)" in source
    assert "inputPayloadInput.required = !isSpecCoverage;" in source
    assert "outputPayloadInput.required = !isSpecCoverage;" in source
    assert "isSpecCoverage" in source
    assert "await validateSpecCoverageOnly(specFile)" in source
    assert "payload_format: 'spec_only'" in source
    assert "Mandatory pre-flight:" in source
    assert "Reverse validation:" in source
    assert "Completeness:" in source
    assert "Priority check - Rule-gap:" in source
    assert "Priority check - Reverse validation:" in source
    assert "Priority check - Completeness:" in source
    assert "Action: fix failed items first, then rerun validation." in source


def test_web_spec_coverage_renders_unsupported_rule_details():
    source = _web_source()
    assert "function renderSpecCoverageUnsupportedRules(payload)" in source
    assert "Row ${row} | Target: ${target} | Condition: ${condition}" in source
    assert "renderSpecCoverageUnsupportedRules(payload);" in source


def test_web_renders_side_by_side_diff_table_for_validation_errors():
    source = _web_source()
    assert "Side-by-Side Field Diff" in source
    assert "diff-table-body" in source
    assert "function renderSideBySideDiff(payload)" in source
    assert "function parseValidationErrorForDiff(errorText)" in source
    assert "function buildDiffFailureExplanation(row)" in source
    assert "Why it failed:" in source
    assert "top-fixes-wrap" in source
    assert "payload.validation_mode !== 'spec_coverage'" in source


def test_web_date_format_validation_handles_container_and_dateformat_nodes():
    source = _web_source()
    assert "function evaluateDateFormatTarget(tgtDoc, tgtXpath, tgtValues, formatTokens)" in source
    assert "targetPathLower.endsWith('/dateformat')" in source
    assert "const childDateValues = xpathValues(tgtDoc, `${tgtXpath}/dateValue`);" in source
    assert "const dateEval = evaluateDateFormatTarget(tgtDoc, tgt, tgtVals, allowedFormats);" in source


def test_web_date_format_validation_supports_multiple_allowed_formats():
    source = _web_source()
    assert "const formatPattern = /\\b(CCYYMMDDHHMMSS|CCYYMMDDHHMM|CCYYMMDD|YYYYMMDDHHMMSS|YYYYMMDDHHMM|YYYYMMDD|HHMMSS|HHMM)\\b/ig;" in source
    assert "formats.push('CCYYMMDDHHMM');" in source
    assert "const allowedFormats = Array.isArray(dateFormatMapping.formats) && dateFormatMapping.formats.length" in source
    assert "const expectedLabel = allowedFormats.join(' or ');" in source
    assert "function isCompatibleDateValueForFormat(rawValue, formatToken)" in source
    assert "if ((format === 'CCYYMMDD' || format === 'YYYYMMDD') && /^\\d{10}$/.test(value))" in source
    assert "let RULE_VALUE_EXCEPTIONS = [];" in source
    assert "async function ensureValidatorExceptionRegistryLoaded()" in source
    assert "../rules/validator_exceptions.json" in source
    assert "function isRuleValueException(rowNum, tgtXpath, expectedValue, foundValue, kind)" in source
    assert "&& !isRuleValueException(rowNum, tgt, hardcodeLit, foundValue, 'hardcode')" in source
    assert "function buildValidationFingerprint(mode)" in source
    assert "validation_fingerprint: buildValidationFingerprint(mode)," in source
    assert "exception_profile_version: VALIDATOR_EXCEPTION_PROFILE_VERSION," in source
    assert "reason_code: toReasonCode(decisionReason)," in source


def test_web_resolve_token_value_supports_multi_line_base_xpaths():
    source = _web_source()
    assert "function splitCandidateXpaths(baseXpath)" in source
    assert ".split(/\\r?\\n|\\|/)" in source
    assert "for (const candidate of baseCandidates)" in source
    assert "if (candidate.endsWith(`/${raw}`))" in source


def test_web_normalize_xpath_preserves_multi_path_inputs():
    source = _web_source()
    assert "const multiParts = String(trimmed)" in source
    assert ".split(/\\r?\\n|\\|/)" in source
    assert "return normalizedParts.join('\\n');" in source


def test_web_multi_condition_and_map_skips_conversion_multi_if_blocks():
    source = _web_source()
    assert "if (/\\bconversion\\s*:/i.test(text)) return null;" in source
    assert "if ((text.match(/\\bif\\b/ig) || []).length > 1) return null;" in source


def test_web_conditional_expected_checks_use_target_overlap():
    source = _web_source()
    assert "function targetValuesContainExpected(targetValues, expectedValue)" in source
    assert "function targetValuesContainAnyExpected(targetValues, expectedCandidates)" in source
    assert "function hasTemperatureTypeValueSwapMatch(tgtDoc, tgtXpath, expectedValue, targetValues)" in source
    assert "function resolveExpectedCandidatesFromTargetSpec(baseXpath, srcVals, srcDoc, targetLiteral, targetToken, targetFromSource)" in source
    assert "const targetMatchesAny = (expectedCandidates) => targetValuesContainAnyExpectedForRule(tgtDoc, tgt, tgtVals, expectedCandidates);" in source
    assert "function hasEquipmentSizeCodeValueConflictSatisfied(tgtXpath, srcDoc, targetValues)" in source
    assert "const targetMismatchesExpected = (expected) => !targetMatchesExpected(expected) && !shouldIgnoreSizeCodeConflict([expected]);" in source
    assert "const targetMismatchesAny = (expectedCandidates) => !targetMatchesAny(expectedCandidates) && !shouldIgnoreSizeCodeConflict(expectedCandidates);" in source
    assert "targetMismatchesExpected(seConst)" in source
    assert "expectedVal && targetMismatchesExpected(expectedVal)" in source
    assert "targetMismatchesAny(matchedExpectedCandidates.length ? matchedExpectedCandidates : [matchedExpected])" in source


def test_web_decimal_direct_map_values_are_compared_numerically_when_needed():
    source = _web_source()
    assert "const numericPattern = /^[+-]?\\d+(?:\\.\\d+)?$/;" in source
    assert "&& (normalizedLeft.includes('.') || normalizedRight.includes('.'))" in source
    assert "function hasDerivedSourceOverlap(sourceValues, targetValues)" in source
    assert "!hasDerivedSourceOverlap(srcVals, tgtVals)" in source


def test_web_concat_rules_build_aligned_candidates_for_dtm_date_pairs():
    source = _web_source()
    assert "function resolveConcatExpectedCandidates(baseXpath, parts, srcDoc)" in source
    assert "function hasEquipmentCountConflictSatisfied(tgtXpath, srcDoc, targetValues)" in source
    assert "function hasPartyAddressUnstructuredOverlap(tgtDoc, tgtXpath, expectedCandidates)" in source
    assert "const expectedCandidates = resolveConcatExpectedCandidates(src, fieldConcatMapping.parts || [], srcDoc);" in source
    assert "const expectedCandidates = resolveConcatExpectedCandidates(src, multiBranchDirectConcat.parts || [], srcDoc);" in source
    assert "expectedCandidates = resolveConcatExpectedCandidates(src, multiAnd.target_tokens, srcDoc);" in source
    assert "&& !hasEquipmentCountConflictSatisfied(tgt, srcDoc, tgtVals)" in source
    assert "targetMismatchesAny(expectedCandidates) && !hasPartyAddressUnstructuredOverlap(tgtDoc, tgt, expectedCandidates)" in source
    assert "concatenate\\s+2\\s+iterations\\s+of\\s+n3" in source


def test_web_conversion_if_chain_allows_empty_string_compare_literal():
    source = _web_source()
    assert "([^'\"]*)" in source


def test_web_supports_excel_export_and_share_link_actions():
    source = _web_source()
    assert "Download Excel Report" in source
    assert "Create Share Link" in source
    assert "function downloadExcelReport(payload)" in source
    assert "function encodeSharePayload(payload)" in source
    assert "function decodeSharePayload(encoded)" in source
    assert "applySharedPayloadIfPresent()" in source


def test_web_supports_spec_diff_change_detection_controls():
    source = _web_source()
    assert "Compare Against Spec" in source
    assert "Compare Specs" in source
    assert "Spec Diff / Change Detection" in source
    assert "function summarizeSpecDiff(baseRules, compareRules)" in source


def test_web_supports_issue_annotation_and_interactive_rule_inspector():
    source = _web_source()
    assert "Interactive Rule Inspector" in source
    assert "function renderIssueInspector(payload)" in source
    assert "diag.rule_row || diag.row" in source
    assert "function parseIssueTargetPath(issueText)" in source
    assert "function buildInspectorContext(payload, issueText)" in source
    assert "function getDiffRowsForInspector(payload)" in source
    assert "condition_text: condTextRaw || condText || ''" in source
    assert "pattern_family: detectedPatternFamily" in source
    assert "needs_fix" in source
    assert "accepted" in source
    assert "wont_fix" in source
    assert "TRIAGE_STORAGE_KEY" in source


def test_web_supports_payload_template_sample_and_full_generators():
    source = _web_source()
    assert "Payload Generator" in source
    assert "Template output (mandatory placeholders)" in source
    assert "Sample pair (minimal valid projection)" in source
    assert "Full-field pair (broad projection)" in source
    assert "Generate Payload Pair" in source
    assert "function buildGeneratedPayloads(rules, mode)" in source
