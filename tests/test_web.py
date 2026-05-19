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
    assert "Required details missing:" in source
    assert "Repeated child items have too many or too few values:" in source
    assert "Either/or choice rules not satisfied:" in source
    assert "Items appear in the wrong order:" in source
    assert "Namespace format does not match expected:" in source
    assert "Repeat count problems:" in source


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
    assert "if (!hasComparableValueOverlap(srcVals, tgtVals))" in source
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
    assert "function extractMultiConditionAndMap(condText)" in source
    assert "function resolveExpectedFromTargetSpec(baseXpath, srcVals, srcDoc, targetLiteral, targetToken, targetFromSource)" in source
    assert "const directGuard = extractStandaloneDirectMapGuard(condText);" in source
    assert "const multiAnd = extractMultiConditionAndMap(condText);" in source


def test_web_supports_if_in_list_length_and_char_offset_mappings():
    source = _web_source()
    assert "function extractIfInListSubstringSourceMapping(condText)" in source
    assert "function extractCharOffsetMapping(condText)" in source
    assert "function extractLengthBasedMapping(condText)" in source
    assert "function resolveLengthMapAction(baseXpath, srcVals, srcDoc, action)" in source
    assert "const inListSubstring = extractIfInListSubstringSourceMapping(condText);" in source
    assert "const charOffset = extractCharOffsetMapping(condText);" in source
    assert "const lengthBased = extractLengthBasedMapping(condText);" in source


def test_web_xpath_values_supports_json_array_item_fallback():
    source = _web_source()
    assert "if (values.length === 0 && /\\[\\*\\]/.test(xpath))" in source
    assert "const arrayFallbackXpath = xpath.replace(/\\[\\*\\]/g, '/item');" in source


def test_web_direct_map_prefers_full_condition_sentence_when_present():
    source = _web_source()
    assert "const directMapHasAdditionalDirectives = Boolean(" in source
    assert "if (isDirectMappingRule && srcHasValue && (isIfSourceRule || !specializedConditionDetected))" in source
    assert "if (!handledCondition && isDirectMapRuleCondition(condText) && !specializedConditionDetected)" in source


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
