import json
import hashlib
import os
import re
from collections import Counter
from difflib import SequenceMatcher
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
from xml.sax.saxutils import escape

from core.spec_reader import extract_rules, get_parser_diagnostics, read_mapping_table
from core.xml_tools import parse_xml, xpath_values, rewrite_xpath_for_default_ns


_STRUCTURE_ALLOWLIST_LOCAL_NAMES = {
    "audit",
    "debug",
    "metadata",
    "trace",
}

_STRUCTURE_ALLOWLIST_PATH_SUFFIXES = {
    "/audit",
    "/debug",
    "/metadata",
    "/trace",
}

_STRUCTURE_SPEC_EXCEPTIONS = {
    "spec.xlsx": {
        "ignore_required_paths": {"/interchange"},
        "allow_nodes": set(),
        "allow_attributes": set(),
        "ordered_sibling_groups": [],
        "choice_groups": [],
    },
}

_STRUCTURE_EXCEPTIONS_CONFIG_PATH = Path(__file__).resolve().parents[1] / "rules" / "structure_exceptions.json"
_SEMANTIC_PROFILES_CONFIG_PATH = Path(__file__).resolve().parents[1] / "rules" / "semantic_profiles.json"
_VALIDATOR_EXCEPTIONS_CONFIG_PATH = Path(__file__).resolve().parents[1] / "rules" / "validator_exceptions.json"
_VALIDATOR_ENGINE_VERSION = "2026.05.21-stabilization-seed"
_PARSER_ENGINE_VERSION = "stage10-parser"
_DECISION_OUTCOME_PASS = "PASS"
_DECISION_OUTCOME_FAIL = "FAIL"
_DECISION_OUTCOME_ABSTAIN = "ABSTAIN"
_CONFIDENCE_HIGH_DEFAULT = 0.8
_CONFIDENCE_MEDIUM_DEFAULT = 0.55

_SEMANTIC_STOPWORDS = {
    "if",
    "then",
    "map",
    "to",
    "as",
    "the",
    "a",
    "an",
    "is",
    "are",
    "of",
    "and",
    "or",
    "into",
    "when",
    "where",
    "with",
    "from",
    "use",
    "using",
    "set",
    "write",
    "populate",
    "copy",
    "derive",
}

_DEFAULT_DIRECT_MAP_COMMENT_PATTERNS = [
    r"\bmust\s+match\b",
    r"\bmust\s+be\s+identical\b",
    r"\bthis\s+number\s+is\s+assigned\s+by\s+sender\b",
    r"\bcontrol\s+number\b.*\bidentical\b",
    r"\binterchange\s+control\s+number\b",
    r"\binterchange\s+control\s+count\b",
    r"\bgroup\s+control\s+number\b",
    r"\btransaction\s+set\s+control\s+number\b",
    r"\bnumber\s+of\s+line\s+item\s+segments\s+in\s+this\s+transaction\s+set\b",
    r"\bmessage\s+reference\s+number\b",
    r"\binterchange\s+control\s+reference\b",
    r"\bnumber\s+of\s+included\s+functional\s+groups\b",
    r"\bnumber\s+of\s+transaction\s+sets\s+included\b",
    r"\bnumber\s+of\s+included\s+segments\b",
    r"\bnumber\s+of\s+segments\s+in\s+the\s+message\b",
    r"\ba\s+count\s+of\s+the\s+number\s+of\s+functional\s+groups\b",
    r"\btotal\s+number\s+of\s+transaction\s+sets\s+included\b",
    r"\btotal\s+number\s+of\s+all\s+segments\b",
]

_DEFAULT_SEMANTIC_PROFILE_CONFIG = {
    "thresholds": {
        "high": 0.75,
        "medium": 0.45,
        "auto_promote": 0.9,
        "ambiguity_gap": 0.08,
    },
    "profiles": {
        "generic": {
            "phrase_replacements": {
                "populate": "map",
                "copy": "map",
                "write": "map",
                "derive": "map",
                "set": "map",
                "using": "map",
                "provided that": "if",
                "whenever": "if",
                "provided source is available": "if source exists",
            },
            "field_aliases": {
                "scac": "carrier_scac",
                "scaccode": "carrier_scac",
                "carriercode": "carrier_scac",
                "shipmentstatus": "shipment_status",
                "bookingnumber": "booking_number",
                "bol": "bill_of_lading",
                "bolnumber": "bill_of_lading",
                "containernumber": "container_number",
            },
            "intent_patterns": {
                "direct_map_comment_patterns": list(_DEFAULT_DIRECT_MAP_COMMENT_PATTERNS),
            },
        },
        "jabil": {
            "phrase_replacements": {
                "milestone batch": "milestonebatch",
                "notify shipment": "notifyshipment",
            },
            "field_aliases": {
                "trackingnumber": "tracking_number",
                "pro": "pro_number",
            },
        },
        "inttra": {
            "phrase_replacements": {
                "booking inbound": "bookinginbound",
            },
            "field_aliases": {
                "bookingref": "booking_reference",
            },
        },
        "tmslsp": {
            "phrase_replacements": {
                "dhllink": "tmslsp",
                "connected view": "connectedview",
                "delivery connect": "deliveryconnect",
            },
            "field_aliases": {
                "legid": "transport_leg_id",
                "tripid": "trip_id",
            },
        },
        "p_and_g": {
            "phrase_replacements": {
                "p&g": "p_and_g",
                "product activity": "productactivity",
            },
            "field_aliases": {
                "supplierinventory": "supplier_inventory",
                "purchasedcommit": "purchased_commit",
            },
        },
    },
}


def _reason_code(text: str) -> str:
    normalized = (text or "").strip().lower()
    if not normalized:
        return "unspecified"
    code = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
    return (code or "unspecified")[:80]


def _decision_fix_hint(status: str, reason: str, family: str) -> str:
    normalized_status = str(status or "").strip().lower()
    normalized_reason = str(reason or "").strip().lower()
    normalized_family = str(family or "").strip().lower()

    if normalized_status == "enforced":
        return "No action required."
    if "procedural/instruction-only" in normalized_reason:
        return "Keep as parsed_only or rewrite condition into a deterministic mapping expression."
    if "unsupported condition pattern" in normalized_reason:
        return "Normalize wording and add a deterministic handler or intent pattern for this condition family."
    if "conditional rule has no resolvable source path" in normalized_reason:
        return "Add/repair source XPath for this condition or downgrade it to procedural guidance."
    if "runtime output evidence contradicts deterministic enforcement" in normalized_reason:
        return "Review source/target mapping for this row and resolve output mismatches before enforcing."
    if "cross-rule contradiction" in normalized_reason:
        return "Unify target intent for this field: choose one strategy (source-map, fixed value, or transform)."
    if normalized_family in {"direct_map", "token_exists", "source_is_not_null"}:
        return "Ensure source and target paths are resolvable and values align for deterministic enforcement."
    return "Review this rule decision and add deterministic intent evidence or keep as parsed_only."


def _decision_outcome_from_status(status: str) -> str:
    normalized = str(status or "").strip().lower()
    if normalized == "enforced":
        return _DECISION_OUTCOME_PASS
    if normalized in {"parsed_only", "unsupported"}:
        return _DECISION_OUTCOME_ABSTAIN
    return _DECISION_OUTCOME_FAIL


def _confidence_guardrail_thresholds(thresholds: dict | None = None) -> dict[str, float]:
    thresholds = thresholds or {}
    high = float(thresholds.get("high", _CONFIDENCE_HIGH_DEFAULT) or _CONFIDENCE_HIGH_DEFAULT)
    medium = float(thresholds.get("medium", _CONFIDENCE_MEDIUM_DEFAULT) or _CONFIDENCE_MEDIUM_DEFAULT)
    high = _clamp_score(high)
    medium = _clamp_score(medium)
    if medium > high:
        medium = min(high, _CONFIDENCE_MEDIUM_DEFAULT)
    return {
        "high": high,
        "medium": medium,
    }


def _confidence_band_and_policy(score: float, thresholds: dict[str, float]) -> dict[str, str]:
    value = _clamp_score(score)
    high = float(thresholds.get("high", _CONFIDENCE_HIGH_DEFAULT))
    medium = float(thresholds.get("medium", _CONFIDENCE_MEDIUM_DEFAULT))
    if value >= high:
        return {
            "confidence_band": "high",
            "apply_policy": "auto_apply_candidate",
        }
    if value >= medium:
        return {
            "confidence_band": "medium",
            "apply_policy": "preview_only",
        }
    return {
        "confidence_band": "low",
        "apply_policy": "never_auto_apply",
    }


def _decision_outcome_from_evidence(
    *,
    status: str,
    row_error_count: int,
    decision_confidence: float,
    parser_confidence: str,
    requires_abstain: bool,
    thresholds: dict[str, float],
) -> str:
    normalized = str(status or "").strip().lower()
    if normalized in {"parsed_only", "unsupported"}:
        return _DECISION_OUTCOME_ABSTAIN
    if normalized != "enforced":
        return _DECISION_OUTCOME_FAIL
    if int(row_error_count or 0) <= 0:
        return _DECISION_OUTCOME_PASS

    parser_ok = str(parser_confidence or "").strip().lower() in {"high", "medium"}
    high_confidence = float(decision_confidence or 0.0) >= float(thresholds.get("high", _CONFIDENCE_HIGH_DEFAULT))
    if not requires_abstain and parser_ok and high_confidence:
        return _DECISION_OUTCOME_FAIL
    return _DECISION_OUTCOME_ABSTAIN


def _build_agent_action_plan(
    rule_decisions: list[dict[str, object]],
    error_diagnostics: list[dict[str, object]],
    thresholds: dict[str, float],
) -> dict[str, object]:
    row_error_counts: Counter[int] = Counter()
    for diag in error_diagnostics:
        row = int(diag.get("row", 0) or 0)
        if row > 0:
            row_error_counts[row] += 1

    ranked_items: list[dict[str, object]] = []
    for decision in rule_decisions:
        row = int(decision.get("row", 0) or 0)
        outcome = str(decision.get("decision_outcome", _DECISION_OUTCOME_FAIL) or _DECISION_OUTCOME_FAIL)
        status = str(decision.get("status", "") or "")
        confidence = float(decision.get("confidence", 0.0) or 0.0)
        confidence_policy = _confidence_band_and_policy(confidence, thresholds)
        row_errors = int(row_error_counts.get(row, 0))

        if outcome == _DECISION_OUTCOME_FAIL:
            action = "fix_now"
            priority = 300 + (row_errors * 20) + int(confidence * 10)
        elif outcome == _DECISION_OUTCOME_ABSTAIN and status in {"unsupported", "parsed_only"}:
            action = "needs_review"
            priority = 200 + (row_errors * 10) + int((1.0 - confidence) * 10)
        else:
            action = "ignore"
            priority = 100 + (row_errors * 5)

        ranked_items.append(
            {
                "row": row,
                "target_xpath": str(decision.get("target_xpath", "") or ""),
                "status": status,
                "decision_outcome": outcome,
                "action": action,
                "priority": int(priority),
                "confidence": round(confidence, 4),
                "confidence_band": confidence_policy["confidence_band"],
                "apply_policy": confidence_policy["apply_policy"],
                "row_error_count": row_errors,
                "reason": str(decision.get("reason", "") or ""),
                "remediation_hint": str(decision.get("remediation_hint", "") or ""),
            }
        )

    ranked_items.sort(key=lambda item: int(item.get("priority", 0)), reverse=True)
    counts = Counter(str(item.get("action", "ignore") or "ignore") for item in ranked_items)
    return {
        "history_context": {
            "source": "runtime_report",
            "available": False,
        },
        "thresholds": {
            "high": round(float(thresholds.get("high", _CONFIDENCE_HIGH_DEFAULT)), 4),
            "medium": round(float(thresholds.get("medium", _CONFIDENCE_MEDIUM_DEFAULT)), 4),
        },
        "counts": {
            "fix_now": int(counts.get("fix_now", 0)),
            "needs_review": int(counts.get("needs_review", 0)),
            "ignore": int(counts.get("ignore", 0)),
        },
        "items": ranked_items[:30],
    }


def _build_parser_validator_calibration(
    rule_decisions: list[dict[str, object]],
    thresholds: dict[str, float],
) -> dict[str, object]:
    outcome_counts = Counter(str(item.get("decision_outcome", _DECISION_OUTCOME_FAIL)) for item in rule_decisions)
    total = max(len(rule_decisions), 1)
    high_threshold = float(thresholds.get("high", _CONFIDENCE_HIGH_DEFAULT))
    low_threshold = float(thresholds.get("medium", _CONFIDENCE_MEDIUM_DEFAULT))

    high_confidence_fails = sum(
        1
        for item in rule_decisions
        if str(item.get("decision_outcome", "")) == _DECISION_OUTCOME_FAIL
        and float(item.get("confidence", 0.0) or 0.0) >= high_threshold
    )
    low_confidence_abstains = sum(
        1
        for item in rule_decisions
        if str(item.get("decision_outcome", "")) == _DECISION_OUTCOME_ABSTAIN
        and float(item.get("confidence", 0.0) or 0.0) < low_threshold
    )

    return {
        "decision_outcomes": {
            "pass": int(outcome_counts.get(_DECISION_OUTCOME_PASS, 0)),
            "abstain": int(outcome_counts.get(_DECISION_OUTCOME_ABSTAIN, 0)),
            "fail": int(outcome_counts.get(_DECISION_OUTCOME_FAIL, 0)),
        },
        "high_confidence_fail_candidates": int(high_confidence_fails),
        "low_confidence_abstains": int(low_confidence_abstains),
        "abstain_rate": round(int(outcome_counts.get(_DECISION_OUTCOME_ABSTAIN, 0)) / total, 4),
        "fail_rate": round(int(outcome_counts.get(_DECISION_OUTCOME_FAIL, 0)) / total, 4),
    }


def _build_pre_fail_guardrails(
    *,
    status: str,
    has_condition: bool,
    source_xpath: str,
    target_xpath: str,
    parser_confidence: str,
    decision_confidence: float,
) -> dict[str, object]:
    checks = {
        "evidence_complete": bool(str(target_xpath or "").strip()) and (bool(str(source_xpath or "").strip()) or not has_condition),
        "mapping_path_resolved": bool(str(target_xpath or "").strip()) and (
            bool(str(source_xpath or "").strip()) or str(status or "").strip().lower() in {"parsed_only", "unsupported"}
        ),
        "normalization_ready": bool(str(target_xpath or "").strip()),
        "uncertainty_within_budget": str(parser_confidence or "").strip().lower() in {"high", "medium"},
        "decision_confidence_ok": float(decision_confidence) >= 0.55,
    }
    failed_checks = [name for name, passed in checks.items() if not passed]
    return {
        "checks": checks,
        "failed_checks": failed_checks,
        "requires_abstain": len(failed_checks) > 0,
    }


def _build_warning_taxonomy(warnings: list[str]) -> dict:
    heuristic_markers = (
        "parser confidence",
        "ambigu",
        "heuristic",
        "parsed but not fully enforced",
        "parsed_only",
    )
    informational_markers = (
        "spec coverage mode",
        "cross-format bridge",
        "adapter pipeline mode",
        "output generation check",
        "structure-strict mode enabled",
        "lenient mode enabled",
    )

    strict_warnings: list[str] = []
    heuristic_warnings: list[str] = []
    informational_warnings: list[str] = []

    for warning in [str(item) for item in warnings if str(item).strip()]:
        normalized = warning.lower()
        if any(marker in normalized for marker in heuristic_markers):
            heuristic_warnings.append(warning)
        elif any(marker in normalized for marker in informational_markers):
            informational_warnings.append(warning)
        else:
            strict_warnings.append(warning)

    return {
        "strict_warnings": strict_warnings,
        "heuristic_warnings": heuristic_warnings,
        "informational_warnings": informational_warnings,
        "counts": {
            "strict": len(strict_warnings),
            "heuristic": len(heuristic_warnings),
            "informational": len(informational_warnings),
            "total": len(warnings),
        },
    }


def _load_validator_exception_registry() -> dict:
    try:
        raw = json.loads(_VALIDATOR_EXCEPTIONS_CONFIG_PATH.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return raw
    except (OSError, json.JSONDecodeError):
        pass
    return {"profile": "default", "version": "missing", "entries": []}


def _build_validation_fingerprint(mode: str) -> dict:
    registry = _load_validator_exception_registry()
    profile = str(registry.get("profile") or "default")
    version = str(registry.get("version") or "unknown")
    entries = registry.get("entries") if isinstance(registry.get("entries"), list) else []
    signature_parts = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        signature_parts.append(
            ":".join(
                [
                    str(entry.get("kind") or ""),
                    str(entry.get("row") or ""),
                    str(entry.get("target_xpath") or ""),
                    "|".join(str(v) for v in (entry.get("expected_values") or [])),
                    "|".join(str(v) for v in (entry.get("allowed_found_values") or [])),
                ]
            )
        )
    signature = ";".join(signature_parts)
    checksum = hashlib.sha1(signature.encode("utf-8")).hexdigest()[:8]
    return {
        "validator_version": _VALIDATOR_ENGINE_VERSION,
        "parser_version": _PARSER_ENGINE_VERSION,
        "mode": str(mode or ""),
        "exception_profile": profile,
        "exception_profile_version": version,
        "exception_count": len(entries),
        "exception_profile_hash": checksum,
    }


def _normalized_validator_exception_entries() -> list[dict]:
    registry = _load_validator_exception_registry()
    raw_entries = registry.get("entries") if isinstance(registry.get("entries"), list) else []
    normalized: list[dict] = []
    for entry in raw_entries:
        if not isinstance(entry, dict):
            continue
        status = str(entry.get("status") or "active").strip().lower()
        if status == "inactive":
            continue
        normalized.append(
            {
                "kind": str(entry.get("kind") or "").strip().lower(),
                "row": int(entry.get("row") or 0),
                "target_xpath": str(entry.get("target_xpath") or "").strip().lower(),
                "expected_values": [str(v).strip().upper() for v in (entry.get("expected_values") or []) if str(v).strip()],
                "allowed_found_values": [str(v).strip().upper() for v in (entry.get("allowed_found_values") or []) if str(v).strip()],
            }
        )
    return normalized


def _is_rule_value_exception(
    entries: list[dict],
    row_num: int,
    target_xpath: str,
    expected_value: str,
    found_value: str,
    kind: str,
) -> bool:
    target = str(target_xpath or "").strip().lower()
    expected = str(expected_value or "").strip().upper()
    found = str(found_value or "").strip().upper()
    kind_norm = str(kind or "").strip().lower()
    for entry in entries:
        if str(entry.get("kind") or "") != kind_norm:
            continue
        if int(entry.get("row") or 0) != int(row_num or 0):
            continue
        if str(entry.get("target_xpath") or "") != target:
            continue
        expected_values = entry.get("expected_values") or []
        if expected_values and expected not in expected_values:
            continue
        allowed_found_values = entry.get("allowed_found_values") or []
        if found in allowed_found_values:
            return True
    return False

_RULE_PATTERN_DICTIONARY = {
    "source_value_translation": {
        "keywords": {"source", "target", "translation", "map", "else"},
        "aliases": ["if source=", "map target as", "translate source value"],
        "synonyms": ["translate", "convert", "convert value"],
        "example": "If Source='02' then map Target as 'true' else map Source to Target",
        "expected_parts": {"operator": "equals", "action": "map_literal_to_target", "transforms": ["conditional", "translation"]},
    },
    "source_exists_target_constant": {
        "keywords": {"source", "exists", "target", "constant", "map"},
        "aliases": ["if source exists", "map target as", "if source is present"],
        "synonyms": ["present", "available", "found"],
        "example": "If Source exists then map Target as 'ISO'",
        "expected_parts": {"operator": "exists", "action": "map_literal_to_target", "transforms": ["conditional"]},
    },
    "if_equals_then_map": {
        "keywords": {"if", "equals", "map", "target", "source"},
        "aliases": ["if x =", "then map", "if token equals"],
        "synonyms": ["equals", "equal to", "same as"],
        "example": "If X101='Y' then map Source to Target",
        "expected_parts": {"operator": "equals", "action": "map_source_to_target", "transforms": ["conditional"]},
    },
    "if_equals_chain_map": {
        "keywords": {"if", "elseif", "else", "map", "target"},
        "aliases": ["elseif", "else map"],
        "synonyms": ["otherwise", "else if"],
        "example": "If A='1' then map 'X' to Target elseif A='2' then map 'Y' to Target else map Source to Target",
        "expected_parts": {"operator": "equals", "action": "map_literal_to_target", "control_flow": ["elseif", "else"]},
    },
    "if_expression_chain_map": {
        "keywords": {"if", "expression", "boolean", "map", "target"},
        "aliases": ["if (", "then map"],
        "synonyms": ["and", "or", "expression"],
        "example": "If (A exists and B='X') then map 'Y' to Target",
        "expected_parts": {"operator": "expression", "action": "map_literal_to_target", "control_flow": ["and", "or"]},
    },
    "date_format_mapping": {
        "keywords": {"date", "format", "token", "map", "target"},
        "aliases": ["ccyy", "yyyy", "mm", "dd", "hh"],
        "synonyms": ["format", "date token", "time token"],
        "example": "If Source != '' then substring the CCYY then map to Target",
        "expected_parts": {"operator": "not_equals", "action": "map_source_to_target", "transforms": ["date_format", "substring"]},
    },
    "field_concat_mapping": {
        "keywords": {"concat", "field", "map", "target"},
        "aliases": ["map DTM02 + DTM03", "concatenate"],
        "synonyms": ["concat", "concatenate", "append"],
        "example": "If condition then map DTM02 + DTM03 to Target",
        "expected_parts": {"operator": "expression", "action": "map_expression_to_target", "transforms": ["concat"]},
    },
    "startswith_substring_mapping": {
        "keywords": {"starts", "with", "substring", "map", "target"},
        "aliases": ["starts with", "substring"],
        "synonyms": ["begins with", "has prefix"],
        "example": "If Source starts with 'ABC' then map substring to Target",
        "expected_parts": {"operator": "starts_with", "action": "map_substring_to_target", "transforms": ["substring"]},
    },
    "if_in_list_substring_source_mapping": {
        "keywords": {"if", "in", "list", "substring", "source"},
        "aliases": ["in (", "substring"],
        "synonyms": ["one of", "member of"],
        "example": "If token in ('A','B') then map substring of Source to Target",
        "expected_parts": {"operator": "in_list", "action": "map_substring_to_target", "transforms": ["substring"]},
    },
    "char_offset_mapping": {
        "keywords": {"character", "offset", "substring", "target"},
        "aliases": ["char", "offset"],
        "synonyms": ["position", "slice"],
        "example": "Map characters at offset 2 length 4 to Target",
        "expected_parts": {"operator": "offset", "action": "map_substring_to_target", "transforms": ["char_offset"]},
    },
    "length_based_mapping": {
        "keywords": {"length", "if", "then", "map", "target"},
        "aliases": ["len(", "length"],
        "synonyms": ["strlen", "size"],
        "example": "If length(Source) = 10 then map X else map Y to Target",
        "expected_parts": {"operator": "length", "action": "map_literal_to_target", "transforms": ["length"]},
    },
}

_STRUCTURE_SECTION_KEYS = {
    "root_mismatches",
    "missing_target_branches",
    "unexpected_target_attributes",
    "unexpected_target_nodes",
    "child_cardinality_violations",
    "required_target_attributes_missing",
    "sibling_order_violations",
    "choice_group_violations",
    "namespace_mismatches",
    "repeat_count_violations",
}


def _normalize_structure_exception_entry(raw: dict | None) -> dict[str, object]:
    raw = raw or {}
    return {
        "ignore_required_paths": {str(item) for item in raw.get("ignore_required_paths", []) if str(item).strip()},
        "allow_nodes": {str(item) for item in raw.get("allow_nodes", []) if str(item).strip()},
        "allow_attributes": {str(item) for item in raw.get("allow_attributes", []) if str(item).strip()},
        "ordered_sibling_groups": list(raw.get("ordered_sibling_groups", [])),
        "choice_groups": list(raw.get("choice_groups", [])),
    }


def _load_structure_exceptions_file() -> dict[str, dict[str, object]]:
    path = _STRUCTURE_EXCEPTIONS_CONFIG_PATH
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    if isinstance(payload, dict) and isinstance(payload.get("specs"), dict):
        specs = payload.get("specs", {})
    elif isinstance(payload, dict):
        specs = payload
    else:
        return {}

    normalized: dict[str, dict[str, object]] = {}
    for spec_name, entry in specs.items():
        if not isinstance(spec_name, str) or not isinstance(entry, dict):
            continue
        normalized[spec_name.lower()] = _normalize_structure_exception_entry(entry)
    return normalized


def _normalize_semantic_profile_entry(raw: dict | None) -> dict[str, object]:
    raw = raw or {}
    intent_patterns_raw = dict(raw.get("intent_patterns", {})) if isinstance(raw.get("intent_patterns", {}), dict) else {}
    direct_map_comment_patterns = [
        str(pattern).strip()
        for pattern in intent_patterns_raw.get("direct_map_comment_patterns", [])
        if str(pattern).strip()
    ]
    return {
        "phrase_replacements": {
            str(key).strip().lower(): str(value).strip()
            for key, value in dict(raw.get("phrase_replacements", {})).items()
            if str(key).strip() and str(value).strip()
        },
        "field_aliases": {
            re.sub(r"[^a-z0-9]+", "", str(key).strip().lower()): str(value).strip()
            for key, value in dict(raw.get("field_aliases", {})).items()
            if str(key).strip() and str(value).strip()
        },
        "intent_patterns": {
            "direct_map_comment_patterns": direct_map_comment_patterns,
        },
    }


def _merge_semantic_profile_entry(base: dict[str, object], override: dict[str, object]) -> dict[str, object]:
    merged_direct_map_patterns = list(dict.fromkeys([
        *list(dict(base.get("intent_patterns", {})).get("direct_map_comment_patterns", [])),
        *list(dict(override.get("intent_patterns", {})).get("direct_map_comment_patterns", [])),
    ]))
    return {
        "phrase_replacements": {
            **dict(base.get("phrase_replacements", {})),
            **dict(override.get("phrase_replacements", {})),
        },
        "field_aliases": {
            **dict(base.get("field_aliases", {})),
            **dict(override.get("field_aliases", {})),
        },
        "intent_patterns": {
            "direct_map_comment_patterns": merged_direct_map_patterns,
        },
    }


def _load_semantic_profiles_file() -> dict[str, object]:
    path = _SEMANTIC_PROFILES_CONFIG_PATH
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _get_semantic_profile(spec_path: str) -> dict[str, object]:
    profile_key = "global"
    payload = _load_semantic_profiles_file()
    thresholds = dict(_DEFAULT_SEMANTIC_PROFILE_CONFIG.get("thresholds", {}))
    thresholds.update(dict(payload.get("thresholds", {})))

    default_profiles = dict(_DEFAULT_SEMANTIC_PROFILE_CONFIG.get("profiles", {}))
    config_profiles = payload.get("profiles", {}) if isinstance(payload.get("profiles", {}), dict) else {}
    generic_profile = _normalize_semantic_profile_entry(default_profiles.get("generic", {}))
    generic_profile = _merge_semantic_profile_entry(
        generic_profile,
        _normalize_semantic_profile_entry(config_profiles.get("generic", {})),
    )
    merged = generic_profile
    merged["profile_key"] = profile_key
    merged["config_source"] = str(_SEMANTIC_PROFILES_CONFIG_PATH) if payload else "built-in"
    merged["thresholds"] = thresholds
    return merged


def _normalize_semantic_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").strip().lower())


def _normalize_field_reference(value: str, field_aliases: dict[str, str]) -> tuple[str, str | None]:
    raw = (value or "").strip()
    if not raw:
        return "", None
    simplified = _simplify_xpath(raw, include_attributes=True) if raw.startswith("/") else raw
    canonical = simplified.strip("<>")
    lookup_key = _normalize_semantic_key(canonical.rsplit("/", 1)[-1].lstrip("@"))
    alias = field_aliases.get(lookup_key)
    if alias:
        return alias, canonical
    return canonical, None


def _extract_semantic_field_references(condition: str, field_aliases: dict[str, str]) -> tuple[list[str], list[dict[str, str]]]:
    references: list[str] = []
    alias_hits: list[dict[str, str]] = []
    candidates = re.findall(
        r"<[^>]+>|/[A-Za-z0-9_@/\.\-\[\]:]+|\b[A-Za-z][A-Za-z0-9_]{2,}\b",
        condition or "",
        flags=re.IGNORECASE,
    )
    for candidate in candidates:
        lookup_key = _normalize_semantic_key(candidate.strip("<>"))
        is_field_like = bool(
            candidate.startswith("<")
            or candidate.startswith("/")
            or candidate.lower() in {"source", "target"}
            or any(char.isdigit() for char in candidate)
            or "_" in candidate
            or lookup_key in field_aliases
            or (not candidate.islower() and not candidate.isupper())
        )
        if not is_field_like:
            continue
        normalized, original = _normalize_field_reference(candidate, field_aliases)
        if not normalized:
            continue
        references.append(normalized)
        if original:
            alias_hits.append({"original": original, "normalized": normalized})
    return _dedupe_preserve_order(references), alias_hits


def _extract_semantic_parts(condition: str, field_aliases: dict[str, str]) -> dict[str, object]:
    normalized = _normalize_condition_text(condition)
    fields, alias_hits = _extract_semantic_field_references(normalized, field_aliases)
    lower = normalized.lower()
    quoted_values = [match[0] or match[1] for match in re.findall(r'"([^"]*)"|\'([^\']*)\'', normalized)]

    operator = "unknown"
    if " starts with " in lower:
        operator = "starts_with"
    elif re.search(r"\bin\s*\(", lower):
        operator = "in_list"
    elif " exists" in lower or " present" in lower or " available" in lower:
        operator = "exists"
    elif "!=" in normalized:
        operator = "not_equals"
    elif re.search(r"(^|\s)=\s*['\"]", normalized):
        operator = "equals"
    elif "length(" in lower or " length(" in lower:
        operator = "length"
    elif "offset" in lower:
        operator = "offset"
    elif any(token in lower for token in (" and ", " or ", "(", ")")):
        operator = "expression"

    action = "unknown"
    if re.search(r"map\s+(?:the\s+)?target\s+as\s+['\"]", lower) or re.search(r"map\s+['\"][^'\"]+['\"]\s+to\s+target", lower):
        action = "map_literal_to_target"
    elif "substring" in lower and "map" in lower:
        action = "map_substring_to_target"
    elif any(token in lower for token in ("concat", "concatenate", "+", "compute", "expression")):
        action = "map_expression_to_target"
    elif re.search(r"map\s+source\s+to\s+target", lower):
        action = "map_source_to_target"
    elif "source" in lower and re.search(r"map\s+to\s+target", lower):
        action = "map_source_to_target"

    transforms: list[str] = []
    if any(token in lower for token in ("substring", "substr")):
        transforms.append("substring")
    if any(token in lower for token in ("concat", "concatenate", "append")):
        transforms.append("concat")
    if "replace" in lower:
        transforms.append("replace")
    if any(token in lower for token in ("ccyy", "yyyy", "mm", "dd", "date", "time", "format")):
        transforms.append("date_format")
    if "offset" in lower or "position" in lower:
        transforms.append("char_offset")
    if "length" in lower:
        transforms.append("length")
    if lower.startswith("if ") or " then " in lower:
        transforms.append("conditional")
    if "translate" in lower or "convert" in lower:
        transforms.append("translation")

    control_flow = [token for token in ("elseif", "else", "and", "or") if token in lower]
    return {
        "trigger": "if" if lower.startswith("if ") else "always",
        "operator": operator,
        "action": action,
        "comparison_values": quoted_values,
        "field_references": fields,
        "field_alias_normalizations": alias_hits,
        "transforms": _dedupe_preserve_order(transforms),
        "control_flow": _dedupe_preserve_order(control_flow),
        "raw": condition,
        "normalized": normalized,
    }


def _family_part_score(semantic_parts: dict[str, object], definition: dict[str, object]) -> float:
    expected = dict(definition.get("expected_parts", {}))
    if not expected:
        return 0.0

    score = 0.0
    transform_overlap_ratio = 1.0
    if expected.get("operator") and semantic_parts.get("operator") == expected.get("operator"):
        score += 0.4
    if expected.get("action") and semantic_parts.get("action") == expected.get("action"):
        score += 0.3
        if expected.get("action") == "map_expression_to_target" and "concat" in set(semantic_parts.get("transforms", [])):
            score += 0.1
    expected_transforms = set(expected.get("transforms", []))
    actual_transforms = set(semantic_parts.get("transforms", []))
    if expected_transforms:
        transform_overlap_ratio = len(expected_transforms & actual_transforms) / len(expected_transforms)
        score += 0.2 * transform_overlap_ratio
    expected_control = set(expected.get("control_flow", []))
    actual_control = set(semantic_parts.get("control_flow", []))
    if expected_control:
        score += 0.1 * (len(expected_control & actual_control) / len(expected_control))
    if expected_transforms and transform_overlap_ratio == 0.0:
        score = min(score, 0.45)
    return min(score, 1.0)


def _pattern_similarity_score(
    normalized_condition: str,
    family_name: str,
    definition: dict,
    semantic_parts: dict[str, object] | None = None,
) -> float:
    condition_tokens = _tokenize_condition_text(normalized_condition)
    keyword_tokens = {token.lower() for token in definition.get("keywords", set())}
    synonym_tokens = {token.lower() for token in definition.get("synonyms", [])}
    keyword_pool = keyword_tokens | synonym_tokens

    keyword_overlap = 0.0
    if keyword_pool:
        keyword_overlap = len(condition_tokens & keyword_pool) / len(keyword_pool)

    alias_hits = 0.0
    aliases = [alias.lower() for alias in definition.get("aliases", [])]
    if aliases:
        alias_hits = max((1.0 if alias in normalized_condition.lower() else 0.0) for alias in aliases)

    example = str(definition.get("example", "")).lower()
    char_similarity = SequenceMatcher(None, normalized_condition.lower(), example).ratio() if example else 0.0
    part_similarity = _family_part_score(semantic_parts or {}, definition)

    score = (0.3 * keyword_overlap) + (0.15 * alias_hits) + (0.15 * char_similarity) + (0.4 * part_similarity)
    return round(min(score, 1.0), 4)


def _similarity_confidence(score: float, thresholds: dict[str, float] | None = None) -> str:
    thresholds = thresholds or {}
    if score >= float(thresholds.get("high", 0.75)):
        return "high"
    if score >= float(thresholds.get("medium", 0.45)):
        return "medium"
    return "low"


def _analyze_semantic_ambiguity(suggestions: list[dict[str, object]], thresholds: dict[str, float]) -> dict[str, object]:
    if len(suggestions) < 2:
        return {"is_ambiguous": False, "candidate_families": [], "reason": ""}
    top = float(suggestions[0].get("score", 0.0))
    second = float(suggestions[1].get("score", 0.0))
    gap = top - second
    if second < float(thresholds.get("medium", 0.45)) or gap > float(thresholds.get("ambiguity_gap", 0.08)):
        return {"is_ambiguous": False, "candidate_families": [], "reason": ""}
    candidate_families = [str(item.get("family", "")) for item in suggestions[:2] if str(item.get("family", ""))]
    return {
        "is_ambiguous": True,
        "candidate_families": candidate_families,
        "reason": f"Top semantic matches are too close to separate confidently ({top:.2f} vs {second:.2f})",
    }


def _build_suggested_canonical_rewrite(
    family_name: str,
    semantic_parts: dict[str, object],
    ambiguity: dict[str, object],
) -> str:
    if ambiguity.get("is_ambiguous"):
        families = ", ".join(ambiguity.get("candidate_families", []))
        return f"Rewrite this rule using one supported family explicitly: {families}"

    fields = list(semantic_parts.get("field_references", []))
    values = list(semantic_parts.get("comparison_values", []))
    left = fields[0] if fields else "Source"
    literal = values[0] if values else "VALUE"

    templates = {
        "source_exists_target_constant": f"If Source exists then map Target as \"{literal}\"",
        "if_equals_then_map": f"If {left} = \"{literal}\" then map Source to Target",
        "startswith_substring_mapping": f"If {left} starts with \"{literal}\" then map substring to Target",
        "field_concat_mapping": f"If condition then map {left} + Source to Target",
        "length_based_mapping": f"If length({left}) = N then map \"{literal}\" to Target",
        "char_offset_mapping": f"Map characters at offset N length M from {left} to Target",
    }
    return templates.get(family_name, f"Rewrite this condition to match supported family: {family_name}")


def _build_semantic_explanation(
    top_suggestion: dict[str, object] | None,
    ambiguity: dict[str, object],
    semantic_parts: dict[str, object],
) -> str:
    if ambiguity.get("is_ambiguous"):
        return str(ambiguity.get("reason", "Semantic intent is ambiguous"))
    if not top_suggestion:
        return "The condition wording does not look close to any supported deterministic rule family yet"

    operator = semantic_parts.get("operator", "unknown")
    action = semantic_parts.get("action", "unknown")
    return (
        f"This looks closest to {top_suggestion.get('family', 'a supported family')}, "
        f"but the rule could not be enforced because the detected operator/action combination ({operator}/{action}) "
        "did not fully match a supported deterministic parser pattern"
    )


def _suggest_pattern_families(
    condition_text: str,
    top_n: int = 3,
    semantic_profile: dict[str, object] | None = None,
) -> list[dict[str, object]]:
    normalized = _normalize_condition_text(condition_text)
    if not normalized:
        return []

    thresholds = dict((semantic_profile or {}).get("thresholds", {}))
    semantic_parts = _extract_semantic_parts(
        normalized,
        dict((semantic_profile or {}).get("field_aliases", {})),
    )

    scored: list[dict[str, object]] = []
    for family_name, definition in _RULE_PATTERN_DICTIONARY.items():
        score = _pattern_similarity_score(normalized, family_name, definition, semantic_parts=semantic_parts)
        scored.append(
            {
                "family": family_name,
                "score": score,
                "confidence": _similarity_confidence(score, thresholds),
                "semantic_parts_match": round(_family_part_score(semantic_parts, definition), 4),
            }
        )

    scored.sort(key=lambda item: float(item["score"]), reverse=True)
    return scored[:top_n]


def _merge_structure_exception_entries(base: dict[str, object], override: dict[str, object]) -> dict[str, object]:
    return {
        "ignore_required_paths": set(override.get("ignore_required_paths", base.get("ignore_required_paths", set()))),
        "allow_nodes": set(override.get("allow_nodes", base.get("allow_nodes", set()))),
        "allow_attributes": set(override.get("allow_attributes", base.get("allow_attributes", set()))),
        "ordered_sibling_groups": list(override.get("ordered_sibling_groups", base.get("ordered_sibling_groups", []))),
        "choice_groups": list(override.get("choice_groups", base.get("choice_groups", []))),
    }


def is_supported_xpath(xpath: str) -> bool:
    return bool(xpath) and xpath.startswith("/")


def _local_name(tag: str) -> str:
    if tag.startswith("{") and "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _normalize_xpath(xpath: str, root_name: str) -> str:
    xpath = (xpath or "").strip()
    if not xpath:
        return ""
    if xpath.startswith("/"):
        return xpath

    if "/" not in xpath and root_name:
        return f"/{root_name}/{xpath}"

    return f"/{xpath}"


def _simplify_xpath(xpath: str, include_attributes: bool = False) -> str:
    xpath = (xpath or "").strip()
    if not xpath or not xpath.startswith("/"):
        return ""

    parts: list[str] = []
    for token in xpath.split("/"):
        token = token.strip()
        if not token:
            continue
        if token.startswith("@"):
            if include_attributes:
                attr_name = token[1:]
                if ":" in attr_name:
                    attr_name = attr_name.split(":", 1)[1]
                parts.append(f"@{attr_name}")
            continue
        token = re.sub(r"\[.*?\]", "", token).strip()
        if not token or token in {"*", "text()"}:
            continue
        if ":" in token:
            token = token.split(":", 1)[1]
        parts.append(token)

    return "/" + "/".join(parts) if parts else ""


def _path_ancestors(xpath: str) -> list[str]:
    simplified = _simplify_xpath(xpath)
    if not simplified:
        return []

    tokens = [token for token in simplified.split("/") if token]
    return ["/" + "/".join(tokens[:index]) for index in range(1, len(tokens) + 1)]


def _build_target_element_paths(tree) -> list[str]:
    root = tree.getroot()
    root_name = _local_name(root.tag)
    paths: list[str] = []

    def visit(element, current_path: str) -> None:
        paths.append(current_path)
        for child in element:
            if not isinstance(child.tag, str):
                continue
            visit(child, f"{current_path}/{_local_name(child.tag)}")

    visit(root, f"/{root_name}")
    return paths


def _build_target_attribute_paths(tree) -> list[str]:
    root = tree.getroot()
    root_name = _local_name(root.tag)
    paths: list[str] = []

    def visit(element, current_path: str) -> None:
        for attr_name in element.attrib:
            paths.append(f"{current_path}/@{_local_name(attr_name)}")
        for child in element:
            if not isinstance(child.tag, str):
                continue
            visit(child, f"{current_path}/{_local_name(child.tag)}")

    visit(root, f"/{root_name}")
    return paths


def _parsed_only_parent_branches(xpath: str) -> list[str]:
    ancestors = _path_ancestors(xpath)
    if len(ancestors) <= 1:
        return []
    return ancestors[:-1]


def _is_allowlisted_structure_path(path: str) -> bool:
    normalized = (path or "").strip()
    if not normalized:
        return False
    if normalized in _STRUCTURE_ALLOWLIST_PATH_SUFFIXES:
        return True
    if any(normalized.endswith(suffix) for suffix in _STRUCTURE_ALLOWLIST_PATH_SUFFIXES):
        return True

    last_token = normalized.rsplit("/", 1)[-1].lstrip("@")
    return last_token in _STRUCTURE_ALLOWLIST_LOCAL_NAMES


def _get_structure_spec_exceptions(spec_path: str) -> dict[str, object]:
    spec_name = Path(spec_path).name.lower()
    fallback = _normalize_structure_exception_entry(_STRUCTURE_SPEC_EXCEPTIONS.get(spec_name, {}))
    from_file = _load_structure_exceptions_file().get(spec_name, {})
    merged = _merge_structure_exception_entries(fallback, from_file)
    merged["config_source"] = str(_STRUCTURE_EXCEPTIONS_CONFIG_PATH) if from_file else "built-in"
    return merged


def _is_repeat_count_structure_rule(
    simplified_target_path: str,
    simplified_attribute_path: str,
    min_count: int,
    max_count: int | None,
    target_count: int,
) -> bool:
    if not simplified_target_path or "/@" in simplified_attribute_path:
        return False
    return max_count is None or max_count > 1 or min_count > 1 or target_count > 1


def _structure_condition_applies(condition_text: str, source_values: list[str]) -> bool:
    normalized = _normalize_condition_text(condition_text).lower()
    if not normalized:
        return True
    if "if source" in normalized or "source exists" in normalized:
        return _has_non_empty_value(source_values)
    return True


def _elements_for_simplified_path(tree, simplified_path: str) -> list:
    tokens = [token for token in (simplified_path or "").split("/") if token and not token.startswith("@")]
    if not tokens:
        return []
    root = tree.getroot()
    if _local_name(root.tag) != tokens[0]:
        return []
    current = [root]
    for token in tokens[1:]:
        next_nodes = []
        for element in current:
            for child in element:
                if isinstance(child.tag, str) and _local_name(child.tag) == token:
                    next_nodes.append(child)
        current = next_nodes
        if not current:
            break
    return current


def _namespace_uri(tag: str) -> str:
    if tag.startswith("{") and "}" in tag:
        return tag[1:].split("}", 1)[0]
    return ""


def _required_target_path(rule: dict, target_xpath: str) -> bool:
    parsed_cardinality = _parse_cardinality(rule.get("cardinality", ""))
    if parsed_cardinality is not None and parsed_cardinality[0] > 0:
        return True
    return _normalize_mo(str(rule.get("m_o", ""))) == "mandatory" and bool(target_xpath)


def _find_missing_branch_path(tree, nsmap: dict, target_xpath: str) -> str | None:
    for branch_path in _path_ancestors(target_xpath):
        if not xpath_values(tree, nsmap, branch_path):
            return branch_path
    return None


def _parse_cardinality(cardinality: str) -> tuple[int, int | None] | None:
    """Parse cardinality like 1..1, 0..1, 0..N into (min_count, max_count)."""
    if not cardinality:
        return None

    match = re.fullmatch(r"\s*(\d+)\s*\.\.\s*(\d+|N)\s*", cardinality, flags=re.IGNORECASE)
    if not match:
        return None

    min_count = int(match.group(1))
    max_token = match.group(2)
    max_count = None if max_token.upper() == "N" else int(max_token)
    return min_count, max_count


def _normalize_mo(raw_mo: str) -> str:
    """Normalize M/O style values into 'mandatory', 'optional', or ''."""
    token = (raw_mo or "").strip().lower()
    if token in {"m", "mandatory", "required", "req"}:
        return "mandatory"
    if token in {"o", "optional"}:
        return "optional"
    return ""


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output


def _apply_regex_transform(text: str, pattern: str, replacement: str, flags: int = 0) -> tuple[str, bool]:
    updated = re.sub(pattern, replacement, text, flags=flags)
    return updated, updated != text


def _normalize_condition_text_with_trace(condition: str) -> tuple[str, list[str]]:
    normalized = " ".join((condition or "").split())
    trace: list[str] = []
    if normalized != (condition or ""):
        trace.append("normalize_whitespace")
    if not normalized:
        return "", trace

    # Normalize smart quotes/dashes seen in Excel-authored rule text.
    smart_char_map = str.maketrans(
        {
            "\u2018": "'",
            "\u2019": "'",
            "\u201c": '"',
            "\u201d": '"',
            "\u2013": "-",
            "\u2014": "-",
        }
    )
    normalized_smart = normalized.translate(smart_char_map)
    if normalized_smart != normalized:
        normalized = normalized_smart
        trace.append("normalize_smart_punctuation")

    transforms = [
        (r"\bmaptarget\b", "map target", "fix_maptarget_typo"),
        (r"\bdirectmap\b", "direct map", "fix_directmap_typo"),
        (r"\bdirect\s+mapping\b", "direct map", "normalize_direct_mapping"),
        (r"\bhardocde\b", "hardcode", "fix_hardcode_typo"),
        (r"\bhardode\b", "hardcode", "fix_hardcode_typo_variant"),
        (r"\bpaylaod\b", "payload", "fix_payload_typo"),
        (r"\bfomat\b", "format", "fix_format_typo"),
        (r"\bavaialable\b", "available", "fix_available_typo"),
        (r"\bstrats\s+with\b", "starts with", "fix_startswith_typo"),
        (r"\bconcate\s*\(", "concatenate(", "fix_concatenate_typo"),
        (r"\belse\s+if\b", "elseif", "normalize_else_if"),
        (r"\bend\s+if\b", "endif", "normalize_end_if"),
        (r"\bto\s*target\w*\b", "to target", "normalize_to_target"),
        (r"\btehn\b", "then", "fix_then_typo"),
        (r"\bif(?=\(|[A-Za-z_\[/])", "if ", "normalize_if_spacing"),
    ]
    for pattern, replacement, label in transforms:
        normalized, changed = _apply_regex_transform(normalized, pattern, replacement, flags=re.IGNORECASE)
        if changed:
            trace.append(label)

    return normalized, trace


def _normalize_condition_text(condition: str) -> str:
    normalized, _ = _normalize_condition_text_with_trace(condition)
    return normalized


def _extract_rule_ir(rule: dict) -> dict:
    candidate = rule.get("rule_ir")
    return candidate if isinstance(candidate, dict) else {}


def _resolve_condition_from_rule_ir(rule: dict) -> str:
    rule_ir = _extract_rule_ir(rule)
    condition = rule_ir.get("condition") if isinstance(rule_ir.get("condition"), dict) else {}
    raw = str(condition.get("raw") or "").strip()
    if raw:
        return raw
    normalized = str(condition.get("normalized") or "").strip()
    if normalized:
        return normalized
    return str(rule.get("condition", "") or "").strip()


def _resolve_rule_row(rule: dict, fallback_row: int) -> int:
    rule_ir = _extract_rule_ir(rule)
    provenance = rule_ir.get("provenance") if isinstance(rule_ir.get("provenance"), dict) else {}
    row_value = provenance.get("row")
    try:
        row_number = int(row_value)
        if row_number > 0:
            return row_number
    except (TypeError, ValueError):
        pass
    return fallback_row


def _is_empty_condition_placeholder(condition: str) -> bool:
    normalized = _normalize_condition_text(condition).strip().lower()
    return normalized in {"", "none", "null", "nan", "n/a", "na", "-"}


def _is_label_like_condition(condition: str) -> bool:
    normalized = _normalize_condition_text(condition).strip()
    if not normalized:
        return False

    lowered = normalized.lower()
    if re.search(r"[=<>+*/()\[\]{}|]", lowered):
        return False

    if re.search(
        r"\b(if|then|else|elseif|map|hardcod(?:e|ed)|concat(?:enate)?|replace|format|exists|present|available|lookup|generate|compute|populate|substring|starts?|ends?|equals?|matches?|check|validate)\b",
        lowered,
    ):
        return False

    token_count = len(re.findall(r"[a-z0-9_]+", lowered))
    return 1 <= token_count <= 10


def _tokenize_condition_text(text: str) -> set[str]:
    tokens = set(re.findall(r"[a-z0-9_]+", (text or "").lower()))
    return {token for token in tokens if token and token not in _SEMANTIC_STOPWORDS}


def _canonicalize_semantic_condition_with_trace(
    condition: str,
    semantic_profile: dict[str, object] | None = None,
) -> tuple[str, list[str]]:
    text, trace = _normalize_condition_text_with_trace(condition)
    if not text:
        return "", trace

    semantic_transforms = [
        (r"\bbegins?\s+with\b", "starts with", "semantic_begins_with"),
        (r"\bhas\s+prefix\b", "starts with", "semantic_has_prefix"),
        (r"\binto\s+target\b", "to target", "semantic_into_target"),
        (r"\botherwise\s+map\b", "else map", "semantic_otherwise_map"),
        (r"\bif\s+([^\s\(\)]+)\s+(?:is\s+)?(?:present|available)\b", r"if \1 exists", "semantic_present_available"),
        (r"\bis\s+not\s+equal\s+to\b", "!=", "semantic_not_equal"),
        (r"\bdoes\s+not\s+equal\b", "!=", "semantic_not_equal"),
        (r"\bnot\s+equals?\b", "!=", "semantic_not_equal"),
        (r"\bis\s+equal\s+to\b", "=", "semantic_is_equal"),
        (r"\bis\s+not\s+(?:blank|empty)\b", "!= \"\"", "semantic_not_blank"),
        (r"\bis\s+(?:blank|empty)\b", "= \"\"", "semantic_blank"),
        (r"\b([A-Za-z0-9_\[/\]\.\-]+)\s+equals\s+(['\"][^'\"]*['\"])", r"\1 = \2", "semantic_equals_operator"),
    ]
    for pattern, replacement, label in semantic_transforms:
        text, changed = _apply_regex_transform(text, pattern, replacement, flags=re.IGNORECASE)
        if changed:
            trace.append(label)

    phrase_replacements = dict((semantic_profile or {}).get("phrase_replacements", {}))
    for phrase, replacement in phrase_replacements.items():
        updated = re.sub(rf"\b{re.escape(phrase)}\b", replacement, text, flags=re.IGNORECASE)
        if updated != text:
            text = updated
            trace.append(f"profile_phrase:{phrase}")

    normalized_final, final_trace = _normalize_condition_text_with_trace(text)
    trace.extend(final_trace)
    return normalized_final, _dedupe_preserve_order(trace)


def _canonicalize_semantic_condition(condition: str, semantic_profile: dict[str, object] | None = None) -> str:
    text, _ = _canonicalize_semantic_condition_with_trace(condition, semantic_profile=semantic_profile)
    return text


def _consolidate_multiline_condition(condition: str) -> str:
    """Consolidate multi-line conditions by joining lines split across cells.
    
    When a condition ends with incomplete keywords (then, and, or), attempt to 
    complete by joining with content on next lines. Normalize whitespace and line breaks.
    """
    if not condition or '\n' not in condition:
        return condition
    
    # Split by newline and process each line
    lines = condition.split('\n')
    consolidated = []
    
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        
        consolidated.append(line)
    
    # Join lines with space, maintaining logical structure
    result = ' '.join(consolidated)
    
    # Clean up multiple spaces
    result = re.sub(r'\s+', ' ', result).strip()
    
    # Common pattern: line ends with 'then' - join continuation
    # Pattern: "if X101 = \"Y\" \n then map Z" -> "if X101 = \"Y\" then map Z"
    result = re.sub(r'\bthen\s+', 'then ', result, flags=re.IGNORECASE)
    result = re.sub(r'\band\s+', 'and ', result, flags=re.IGNORECASE)
    result = re.sub(r'\bor\s+', 'or ', result, flags=re.IGNORECASE)
    
    return result


def _concat_expected(condition: str, source_values: list[str]) -> str | None:
    """Build expected target value for rules like Concatinate("prefix", <source>)."""
    if not source_values:
        return None

    match = re.search(
        r'concat(?:inate|enate)?\s*\(\s*"([^"]*)"\s*,\s*<[^>]+>\s*\)',
        condition,
        flags=re.IGNORECASE,
    )
    if not match:
        return None

    return f"{match.group(1)}{source_values[0]}"


def _extract_source_value_translation(condition: str) -> dict | None:
    """Parse simple Source=X => Target=Y translation blocks.

    Supported examples:
    - If Source="02" then map Target as "true"
    - If Source = "DD" then map Target as "DoorToDoor"
    - Conversion: If Source = "U" then map "AMEND" to Target elseif ... else then map Source to Target
    """
    normalized = _normalize_condition_text(condition)
    if not normalized:
        return None

    clause_pattern = re.compile(
        r"(?:^|\bif\b|\belseif\b)\s*"
        r"source\s*=\s*['\"]([^'\"]+)['\"]\s*"
        r"(?:then\s*)?map\s*"
        r"(?:target\s+(?:as\s*)?['\"]([^'\"]+)['\"]|['\"]([^'\"]+)['\"](?:\s+to\s+target)?)",
        flags=re.IGNORECASE,
    )
    clauses = []
    for match in clause_pattern.finditer(normalized):
        clauses.append(
            {
                "source": match.group(1),
                "target": match.group(2) or match.group(3),
            }
        )

    if not clauses:
        return None

    else_maps_source = bool(
        re.search(r"\belse\b\s*(?:then\s*)?map\s+source\s+to\s+target", normalized, flags=re.IGNORECASE)
    )
    return {
        "clauses": clauses,
        "else_maps_source": else_maps_source,
        "raw": condition,
    }


def _extract_source_exists_target_constant(condition: str) -> str | None:
    """Parse rules like 'If Source exists then map Target as "ISO"'."""
    normalized = _normalize_condition_text(condition)
    if not normalized:
        return None

    target_as_match = re.search(
        r"if\s+source\s+exists\s+then\s+map\s+(?:the\s+)?target\s+as\s*['\"]([^'\"]+)['\"]",
        normalized,
        flags=re.IGNORECASE,
    )
    if target_as_match:
        return target_as_match.group(1)

    to_target_match = re.search(
        r"if\s+source\s+exists\s+then\s+map\s*['\"]([^'\"]+)['\"]\s+to\s+target",
        normalized,
        flags=re.IGNORECASE,
    )
    if to_target_match:
        return to_target_match.group(1)

    return None


def _extract_token_exists_target_mapping(condition: str) -> dict | None:
    """Parse token-exists conditional mappings.

    Examples:
    - If N722 exists then map "1" to Target
    - If N722 exists then map Target as "ISO"
    - if H105 exists move "EmergencyDangerousGoodsContact" to Target
    """
    normalized = _normalize_condition_text(condition)
    if not normalized:
        return None

    # Keep generic source-exists constant rules handled by the dedicated extractor.
    if _extract_source_exists_target_constant(normalized) is not None:
        return None

    match = re.search(
        r"\bif\b\s+([^\s\(\)]+)\s+exists\s+(?:then\s*)?(?:map|move)\s+(.+?)\s*(?=\belseif\b|\belse\b|\bendif\b|$)",
        normalized,
        flags=re.IGNORECASE,
    )
    if not match:
        return None

    token = match.group(1)
    fragment = match.group(2).strip()
    map_source = fragment.lower() in {"to", "target", "to target"}
    target_literal, target_token = (None, None)
    if not map_source:
        target_literal, target_token = _parse_map_target_fragment(fragment)
        if target_literal is None and target_token is None:
            return None

    return {
        "token": token,
        "target_literal": target_literal,
        "target_token": target_token,
        "target_from_source": map_source,
        "raw": condition,
    }


def _extract_source_is_not_null_mapping(condition: str) -> dict | None:
    """Parse rules like 'If source is not null then hardcode "ISO" to Target'.
    
    Examples:
    - If source is not null then hardcode "ISO" to Target
    - If /xpath is not null then map "value" to Target
    - If source is not null then map source to Target
    """
    normalized = _normalize_condition_text(condition)
    if not normalized:
        return None
    
    lowered = normalized.lower()
    # Must have "is not null" (check for both "is not null" and variations)
    if not re.search(r"\bis\s+not\s+null\b", lowered):
        return None
    
    # Pattern 1: hardcode action
    hardcode_match = re.search(
        r"if\s+(?:source|/[^\s]+)\s+is\s+not\s+null\s+(?:then\s+)?hardcode\s+['\"]([^'\"]*)['\"](?:\s+(?:to|as)\s+target)?",
        normalized,
        flags=re.IGNORECASE
    )
    if hardcode_match:
        return {
            "action_type": "hardcode",
            "value": hardcode_match.group(1),
            "raw": condition,
        }
    
    # Pattern 2: map action - "map X to Target"
    map_match = re.search(
        r"if\s+(?:source|/[^\s]+)\s+is\s+not\s+null\s+(?:then\s+)?map\s+(?:the\s+)?(?:target\s+)?as\s*['\"]([^'\"]+)['\"]",
        normalized,
        flags=re.IGNORECASE
    )
    if map_match:
        return {
            "action_type": "map",
            "target_literal": map_match.group(1),
            "target_token": None,
            "raw": condition,
        }
    
    # Pattern 3: map literal to target
    map_literal_match = re.search(
        r"if\s+(?:source|/[^\s]+)\s+is\s+not\s+null\s+(?:then\s+)?map\s+['\"]([^'\"]+)['\"]\s+to\s+target",
        normalized,
        flags=re.IGNORECASE
    )
    if map_literal_match:
        return {
            "action_type": "map",
            "target_literal": map_literal_match.group(1),
            "target_token": None,
            "raw": condition,
        }
    
    # Pattern 4: map source to target (source is the value)
    map_source_match = re.search(
        r"if\s+source\s+is\s+not\s+null\s+(?:then\s+)?map\s+source\s+to\s+target",
        normalized,
        flags=re.IGNORECASE
    )
    if map_source_match:
        return {
            "action_type": "map_source",
            "raw": condition,
        }
    
    return None


def _extract_compute_statement(condition: str) -> dict | None:
    """Parse compute/counter statements like 'compute field = field + 1'.
    
    These are procedural rules, not declarative mappings. They're recognized
    but not enforceable as mapping validations.
    
    Examples:
    - compute mainCarriageMapCount = mainCarriageMapCount + 1
    - compute preCarriageMapCount = preCarriageMapCount + 1
    - if K101='MAIN' compute mainCarriageMapCount = mainCarriageMapCount + 1
    """
    normalized = _normalize_condition_text(condition)
    if not normalized:
        return None
    
    lowered = normalized.lower()
    # Must have "compute" keyword
    if "compute" not in lowered:
        return None
    
    # Pattern: [if condition] compute fieldName = fieldName + expr
    # We just need to detect the compute keyword and basic structure
    compute_match = re.search(
        r"\bcompute\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*([+\-*/])\s*(\d+)",
        normalized,
        flags=re.IGNORECASE
    )
    if compute_match:
        return {
            "type": "compute",
            "field": compute_match.group(1),
            "operand_field": compute_match.group(2),
            "operator": compute_match.group(3),
            "operand_value": compute_match.group(4),
            "raw": condition,
        }
    
    # Alternative pattern: just detect the word "compute" with field assignment
    simple_compute_match = re.search(
        r"\bcompute\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*=",
        normalized,
        flags=re.IGNORECASE
    )
    if simple_compute_match:
        return {
            "type": "compute",
            "field": simple_compute_match.group(1),
            "raw": condition,
        }
    
    return None


def _extract_hardcode_literal(condition: str) -> str | None:
    """Parse hardcode literal rules like 'Hardcode "CCYYMMDD" to Target'.
    
    Examples:
    - Hardcode "CCYYMMDD" to Target
    - Hardcode "ISO" to Target
    """
    normalized = _normalize_condition_text(condition)
    if not normalized:
        return None

    quote_literal_match = re.search(
        r"hardcode\s+[\"']\'[\"']\s+to\s+target",
        normalized,
        flags=re.IGNORECASE,
    )
    if quote_literal_match:
        return "'"

    quote_literal_standalone_match = re.search(
        r"hardcode\s+[\"']\'[\"']\s*$",
        normalized,
        flags=re.IGNORECASE,
    )
    if quote_literal_standalone_match:
        return "'"
    
    patterns = [
        r"hardcode\s*['\"]([^'\"]+)['\"]\s+to\s+target",
        r"hardcode\s*['\"]([^'\"]+)['\"]",
        r"hardcode\s+['\"]([^'\"]+)['\"]\s+to\s+target",
        r"hardcode\s+([A-Za-z0-9_\-]+)\s+to\s+target",
        r"hardcode\s+to\s+['\"]([^'\"]+)['\"]",
        r"hardcode\s+target\s+as\s+['\"]([^'\"]+)['\"]",
        r"hardcode(?:d)?\s+as\s+['\"]([^'\"]+)['\"]",
        r"hardcode\s+['\"]([^'\"]+)['\"]",
        r"^\s*hardcode\s+([A-Za-z0-9_\-]+)\s*$",
        r"^\s*hardcode\s+['\"]([^'\"]+)['\"]\s*$",
    ]
    for pat in patterns:
        match = re.search(pat, normalized, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    
    return None


def _extract_concatenate_fields(condition: str) -> dict | None:
    """Parse concatenation rules like 'Concatenate "20" + /X12/ISA/ISA09 + /X12/ISA/ISA10'.
    
    Returns:
    {
        "parts": [
            {"kind": "literal", "value": "20"},
            {"kind": "xpath", "value": "/X12/ISA/ISA09"},
            {"kind": "xpath", "value": "/X12/ISA/ISA10"},
        ]
    }
    """
    normalized = _normalize_condition_text(condition)
    if not normalized:
        return None
    
    # Check if this is a concatenate rule
    if not re.search(r"\bconcat(?:enate|inate)?\b", normalized, flags=re.IGNORECASE):
        return None
    
    # Extract all parts separated by +
    # Parts can be: "literal", /xpath, or token
    parts_pattern = r"""
        (?:concat(?:enate|inate)?\s*)?
        (
            ['\"]([^'\"]+)['\"]   # Literal strings
            |
            /[\w/\-\.]+           # XPaths
            |
            [\w]+                 # Simple tokens
        )
    """
    
    matches = re.findall(r"""['\"]([^'\"]+)['\"]|(/[\w/\-\.]+)|(\w+)""", normalized)
    if not matches or len(matches) < 2:
        return None
    
    parts = []
    for literal, xpath, token in matches:
        if literal:
            parts.append({"kind": "literal", "value": literal})
        elif xpath:
            parts.append({"kind": "xpath", "value": xpath})
        elif token:
            if token.lower() not in {"to", "target", "and", "then", "map"}:
                parts.append({"kind": "token", "value": token})
    
    if len(parts) >= 2:
        return {"parts": parts, "raw": condition}
    
    return None


def _extract_startswith_replace_mapping(condition: str) -> dict | None:
    """Parse starts-with + replace + map patterns.

    Supported example:
    if Source startsWith 'NVO-' then replace Characters 'NVO-' with '' in K101 and map to Target
    """
    normalized = _normalize_condition_text(condition)
    if not normalized:
        return None

    starts_with = re.search(
        r"\bif\b\s+(?:source|[\w/\.\-]+)\s+starts(?:\s*with|with)\s*['\"]([^'\"]+)['\"]",
        normalized,
        flags=re.IGNORECASE,
    )
    replace_match = re.search(
        r"replace(?:\s+characters?)?\s*['\"]([^'\"]+)['\"]\s*with\s*['\"]([^'\"]*)['\"](?:\s+in\s+[\w/\.\-]+)?\s*(?:and\s+)?map(?:\s+to\s+target|\s+target)?",
        normalized,
        flags=re.IGNORECASE,
    )
    if not starts_with or not replace_match:
        return None

    prefix = starts_with.group(1)
    replace_from = replace_match.group(1)
    replace_to = replace_match.group(2)
    if prefix != replace_from:
        return None

    return {
        "prefix": prefix,
        "replace_to": replace_to,
        "raw": condition,
    }


def _extract_startswith_replace_append_mapping(condition: str) -> dict | None:
    """Parse starts-with + replace + append + map patterns.

    Supported examples:
    - if Source startsWith 'GEN-' then replace Characters 'GEN-' with '' in K101 and append with K102 and map to Target
    - if Source startsWith 'PRE-' then replace Characters 'PRE-' with '' in K101 and append with "-A" and map to Target
    """
    normalized = _normalize_condition_text(condition)
    if not normalized:
        return None

    starts_with = re.search(
        r"\bif\b\s+(?:source|[\w/\.\-]+)\s+starts(?:\s*with|with)\s*['\"]([^'\"]+)['\"]",
        normalized,
        flags=re.IGNORECASE,
    )
    replace_match = re.search(
        r"replace(?:\s+characters?)?\s*['\"]([^'\"]+)['\"]\s*with\s*['\"]([^'\"]*)['\"](?:\s+in\s+[\w/\.\-]+)?\s*(?:and\s+)?append\s+with\s+([^\s]+)\s*(?:and\s+)?map(?:\s+to\s+target|\s+target)?",
        normalized,
        flags=re.IGNORECASE,
    )
    if not starts_with or not replace_match:
        return None

    prefix = starts_with.group(1)
    replace_from = replace_match.group(1)
    replace_to = replace_match.group(2)
    append_token = replace_match.group(3).strip().strip(",")
    if prefix != replace_from:
        return None

    append_literal = None
    append_field = None
    if (append_token.startswith('"') and append_token.endswith('"')) or (
        append_token.startswith("'") and append_token.endswith("'")
    ):
        append_literal = append_token[1:-1]
    else:
        append_field = append_token

    return {
        "prefix": prefix,
        "replace_to": replace_to,
        "append_literal": append_literal,
        "append_field": append_field,
        "raw": condition,
    }


def _extract_if_equals_then_map(condition: str) -> dict | None:
    """Parse simple conditional mapping rules.

    Supported examples:
    - if K101 = "PPOL" then map "PlaceOfLoad" to Target
    - if /X12/TS_300/K1/K101 = "AMS" then map "Customer" to Target
    - if K101 = "PETD-" then map K102 to Target
    """
    normalized = _normalize_condition_text(condition)
    if not normalized:
        return None
    lowered = normalized.lower()
    if "elseif" in lowered or " else " in f" {lowered} ":
        return None

    match = re.search(
        r"\bif\b\s+([^\s\(\)]+)\s*(=|==|!=|<>)\s*['\"]([^'\"]*)['\"]\s+(?:then\s*)?(?:map|move)\s+(.+?)\s*(?=\belseif\b|\belse\b|\bendif\b|$)",
        normalized,
        flags=re.IGNORECASE,
    )
    if not match:
        return None

    map_fragment = match.group(4).strip()
    target_from_source = map_fragment.lower() in {"to", "target", "to target"}
    target_literal, target_token = (None, None)
    if not target_from_source:
        target_literal, target_token = _parse_map_target_fragment(map_fragment)
        if target_literal is None and target_token is None:
            return None

    return {
        "lhs_token": match.group(1),
        "operator": match.group(2),
        "compare_value": match.group(3),
        "target_literal": target_literal,
        "target_token": target_token,
        "target_from_source": target_from_source,
        "raw": condition,
    }


def _extract_if_equals_chain_map(condition: str) -> dict | None:
    """Parse multi-clause conditional mapping rules (if/elseif[/else])."""
    normalized = _normalize_condition_text(condition)
    if not normalized:
        return None
    lowered = normalized.lower()
    if "elseif" not in lowered and " else " not in f" {lowered} ":
        return None

    map_fragment_pattern = (
        r"(?:target\s+(?:as\s*)?['\"][^'\"]+['\"]|['\"][^'\"]+['\"](?:\s+to\s+target)?|[^\s|]+(?:\s+to\s+target)?)"
    )
    clause_pattern = re.compile(
        r"(?:\bif\b|\belseif\b)\s+([^\s\(\)]+)\s*(=|==|!=|<>)\s*['\"]([^'\"]*)['\"]\s+(?:then\s*)?(?:map|move)\s*("
        + map_fragment_pattern
        + r")\s*(?=\belseif\b|\belse\b|\bendif\b|$)",
        flags=re.IGNORECASE,
    )
    clauses = []
    for match in clause_pattern.finditer(normalized):
        map_fragment = match.group(4).strip()
        target_from_source = map_fragment.lower() in {"to", "target", "to target"}
        target_literal, target_token = (None, None)
        if not target_from_source:
            target_literal, target_token = _parse_map_target_fragment(map_fragment)
            if target_literal is None and target_token is None:
                continue
        clauses.append(
            {
                "lhs_token": match.group(1),
                "operator": match.group(2),
                "compare_value": match.group(3),
                "target_literal": target_literal,
                "target_token": target_token,
                "target_from_source": target_from_source,
            }
        )
    if not clauses:
        return None

    else_map_pattern = re.search(
        r"\belse\b\s*(?:then\s*)?(?:map|move)\s*("
        + map_fragment_pattern
        + r")\s*(?=\bendif\b|$)",
        normalized,
        flags=re.IGNORECASE,
    )
    else_map = None
    if else_map_pattern:
        map_fragment = else_map_pattern.group(1).strip()
        target_from_source = map_fragment.lower() in {"to", "target", "to target"}
        target_literal, target_token = (None, None)
        if not target_from_source:
            target_literal, target_token = _parse_map_target_fragment(map_fragment)
        else_map = {
            "target_literal": target_literal,
            "target_token": target_token,
            "target_from_source": target_from_source,
        }

    return {
        "clauses": clauses,
        "else_map": else_map,
        "raw": condition,
    }


def _parse_map_target_fragment(fragment: str) -> tuple[str | None, str | None]:
    text = _normalize_condition_text(fragment)
    if not text:
        return None, None

    target_as = re.fullmatch(r"target\s+as\s*['\"]([^'\"]+)['\"]", text, flags=re.IGNORECASE)
    if target_as:
        return target_as.group(1), None

    target_literal = re.fullmatch(r"target\s+['\"]([^'\"]+)['\"]", text, flags=re.IGNORECASE)
    if target_literal:
        return target_literal.group(1), None

    literal_to_target = re.fullmatch(r"['\"]([^'\"]+)['\"]\s+to\s+target", text, flags=re.IGNORECASE)
    if literal_to_target:
        return literal_to_target.group(1), None

    literal_to_field = re.fullmatch(r"['\"]([^'\"]+)['\"]\s+to\s+([^\s]+)", text, flags=re.IGNORECASE)
    if literal_to_field:
        return literal_to_field.group(1), None

    target_to_literal = re.fullmatch(r"target\s+to\s+['\"]([^'\"]+)['\"]", text, flags=re.IGNORECASE)
    if target_to_literal:
        return target_to_literal.group(1), None

    bare_literal = re.fullmatch(r"['\"]([^'\"]+)['\"]", text, flags=re.IGNORECASE)
    if bare_literal:
        return bare_literal.group(1), None

    token_to_target = re.fullmatch(r"([^\s]+)\s+to\s+target", text, flags=re.IGNORECASE)
    if token_to_target:
        return None, token_to_target.group(1)

    bare_token = re.fullmatch(r"([^\s|]+)", text, flags=re.IGNORECASE)
    if bare_token:
        return None, bare_token.group(1)

    return None, None


def _parse_length_map_fragment(fragment: str) -> dict | None:
    text = _normalize_condition_text(fragment).strip().strip("|").strip()
    if not text:
        return None

    target_literal, target_token = _parse_map_target_fragment(text)
    if target_literal is not None:
        return {"kind": "literal", "literal": target_literal}
    if target_token is not None:
        return {"kind": "token", "token": target_token}

    left_match = re.fullmatch(
        r"(?:map\s+)?(?:[^\s|]+\s+)?left\s*\(\s*([^\s,|]+)\s*,\s*(\d+)\s*\)\s*(?:to\s+target)?",
        text,
        flags=re.IGNORECASE,
    )
    if left_match:
        return {
            "kind": "left",
            "token": left_match.group(1),
            "length": int(left_match.group(2)),
        }

    return None


def _extract_length_based_mapping(condition: str) -> dict | None:
    """Parse simple length-based conditional mapping rules."""
    normalized = _normalize_condition_text(condition)
    if not normalized or "length" not in normalized.lower():
        return None

    outer_guard_expr = None
    first_length_match = re.search(r"\bif\b\s+length\s*\(?", normalized, flags=re.IGNORECASE)
    if first_length_match:
        prefix = normalized[: first_length_match.start()].strip()
        guard_match = re.search(
            r"\bif\b\s+(.*?)\s+then\s+map\s+as\s+below\s*$",
            prefix,
            flags=re.IGNORECASE,
        )
        if guard_match:
            outer_guard_expr = guard_match.group(1).strip()

    clause_pattern = re.compile(
        r"(?:\bif\b|\belseif\b)\s+length\s*\(?\s*([^\)\s]+)\s*\)?\s*(<=|>=|==|=|!=|<|>)\s*(\d+)\s+then\s+(?:map\s+)?(.*?)\s*(?=\bif\b\s+length\s*\(?|\belseif\b|\belse\b|\bendif\b|$)",
        flags=re.IGNORECASE,
    )
    clauses = []
    for match in clause_pattern.finditer(normalized):
        action = _parse_length_map_fragment(match.group(4))
        if action is None:
            continue
        clauses.append(
            {
                "token": match.group(1),
                "operator": match.group(2),
                "threshold": int(match.group(3)),
                "action": action,
            }
        )
    if not clauses:
        return None

    else_match = re.search(
        r"\belse\b\s*(?:\|\s*)?(?:then\s*)?(?:map\s+)?(.*?)\s*(?=\bendif\b|$)",
        normalized,
        flags=re.IGNORECASE,
    )
    else_action = _parse_length_map_fragment(else_match.group(1)) if else_match else None

    return {
        "clauses": clauses,
        "else_action": else_action,
        "outer_guard_expr": outer_guard_expr,
        "raw": condition,
    }


def _extract_if_expression_chain_map(condition: str) -> dict | None:
    """Parse if/elseif[/else] rules that use logical expressions in conditions."""
    normalized = _normalize_condition_text(condition)
    if not normalized:
        return None
    has_logical_ops = bool(re.search(r"\b(?:and|or)\b|&&|\|\|", normalized, flags=re.IGNORECASE))
    has_parenthesized_predicate = bool(
        re.search(r"\(\s*[^()]+\s*(?:=|==|!=|<>)\s*[^()]+\s*\)", normalized, flags=re.IGNORECASE)
    )
    if not (has_logical_ops or has_parenthesized_predicate):
        return None

    map_fragment_pattern = (
        r"(?:target\s+(?:as\s*)?['\"][^'\"]+['\"]|['\"][^'\"]+['\"](?:\s+to\s+target)?|[^\s|]+(?:\s+to\s+target)?)"
    )
    clause_pattern = re.compile(
        r"(?:\bif\b|\belseif\b)\s+(.*?)\s+(?:then\s*)?(?:map|move)\s*("
        + map_fragment_pattern
        + r")\s*(?=\belseif\b|\belse\b|\bendif\b|$)",
        flags=re.IGNORECASE,
    )
    clauses = []
    for match in clause_pattern.finditer(normalized):
        target_literal, target_token = _parse_map_target_fragment(match.group(2))
        if target_literal is None and target_token is None:
            continue
        clauses.append(
            {
                "expr": match.group(1),
                "target_literal": target_literal,
                "target_token": target_token,
            }
        )
    if not clauses:
        return None

    else_match = re.search(
        r"\belse\b\s*(?:then\s*)?(?:map|move)\s*("
        + map_fragment_pattern
        + r")\s*(?=\bendif\b|$)",
        normalized,
        flags=re.IGNORECASE,
    )
    else_map = None
    if else_match:
        target_literal, target_token = _parse_map_target_fragment(else_match.group(1))
        if target_literal is not None or target_token is not None:
            else_map = {"target_literal": target_literal, "target_token": target_token}

    return {
        "clauses": clauses,
        "else_map": else_map,
        "raw": condition,
    }


def _extract_multi_condition_and_map(condition: str) -> dict | None:
    """Parse multi-condition AND rules (all conditions must be true).
    
    Supported examples:
    - if R401 = "L" and DTM01 = "369" then map DTM02 + DTM03 to Target
    - if K101 = "X" and K102 = "Y" then hardcode "Z" to Target
    - if /X12/TS_300/K1/K101 = "AMS" and K102 exists then map "Customer" to Target
    """
    normalized = _normalize_condition_text(condition)
    if not normalized:
        return None
    
    lowered = normalized.lower()
    # Must have "and" but not "elseif" or else/endif (those are chain rules)
    if " and " not in lowered and " && " not in lowered:
        return None
    if "elseif" in lowered or " else " in f" {lowered} " or "endif" in lowered:
        return None
    
    # Extract all equality conditions joined by "and"
    # Pattern: token = "value" and token = "value" and ... then action
    condition_part_pattern = re.compile(
        r"([^\s\(\)]+)\s*={1,2}\s*['\"]([^'\"]*)['\"]",
        flags=re.IGNORECASE
    )
    
    # Split by "and" to get individual conditions
    and_pattern = re.compile(r"\s+(?:and|&&)\s+", flags=re.IGNORECASE)
    
    # Find the part before "then"
    then_match = re.search(r"\bthen\b", normalized, flags=re.IGNORECASE)
    if not then_match:
        return None
    
    conditions_text = normalized[:then_match.start()].strip()
    action_text = normalized[then_match.end():].strip()
    
    # Remove leading "if" if present
    if_match = re.match(r"^\s*\bif\b\s+", conditions_text, flags=re.IGNORECASE)
    if if_match:
        conditions_text = conditions_text[if_match.end():].strip()
    
    # Split conditions by "and"
    condition_parts = and_pattern.split(conditions_text)
    if not condition_parts:
        return None
    
    conditions = []
    for part in condition_parts:
        part = part.strip()
        if not part:
            continue
        
        # Check for "exists" condition
        exists_match = re.match(r"^\s*([^\s\(\)]+)\s+exists\s*$", part, flags=re.IGNORECASE)
        if exists_match:
            conditions.append({
                "type": "exists",
                "token": exists_match.group(1),
                "raw": part
            })
            continue

        # Check for not-equals condition
        neq_match = re.match(
            r"^\s*([^\s\(\)]+)\s*(?:<>|!=)\s*['\"]([^'\"]*)['\"]",
            part,
            flags=re.IGNORECASE,
        )
        if neq_match:
            conditions.append({
                "type": "not_equals",
                "token": neq_match.group(1),
                "value": neq_match.group(2),
                "raw": part,
            })
            continue
        
        # Check for equality condition
        eq_match = re.match(r"^\s*([^\s\(\)]+)\s*={1,2}\s*['\"]([^'\"]*)['\"]", part, flags=re.IGNORECASE)
        if eq_match:
            conditions.append({
                "type": "equals",
                "token": eq_match.group(1),
                "value": eq_match.group(2),
                "raw": part
            })
            continue
    
    if not conditions or len(conditions) < 2:
        # Need at least 2 conditions for "and"
        return None
    
    # Parse the action part
    # Can be: map ..., hardcode ..., etc.
    target_literal = None
    target_token = None
    target_tokens = None
    action_type = None
    
    # Try to parse as map action
    map_match = re.search(
        r"\b(?:map|move)\s+(.+?)(?:\s+to\s+target)?$",
        action_text,
        flags=re.IGNORECASE
    )
    if map_match:
        action_type = "map"
        map_fragment = map_match.group(1).strip()
        if map_fragment.lower() in {"to", "target", "to target"}:
            action_type = "map_source"
            map_fragment = ""
        if re.search(r"\s*\+\s*|\s+and\s+", map_fragment, flags=re.IGNORECASE):
            raw_parts = re.split(r"\s*\+\s*|\s+and\s+", map_fragment, flags=re.IGNORECASE)
            parsed_parts = []
            for part in raw_parts:
                token = part.strip()
                if not token:
                    continue
                if (token.startswith('"') and token.endswith('"')) or (token.startswith("'") and token.endswith("'")):
                    parsed_parts.append({"kind": "literal", "value": token[1:-1]})
                else:
                    parsed_parts.append({"kind": "token", "value": token})
            if len(parsed_parts) >= 2:
                target_tokens = parsed_parts
            else:
                target_literal, target_token = _parse_map_target_fragment(map_fragment)
        else:
            target_literal, target_token = _parse_map_target_fragment(map_fragment)
    
    # Try to parse as hardcode action
    if not action_type:
        hardcode_match = re.search(
            r"\bhardcode\s+(?:target\s+(?:as\s*)?['\"]([^'\"]*)['\"]|['\"]([^'\"]*)['\"](?:\s+(?:to|as)\s+target)?)",
            action_text,
            flags=re.IGNORECASE
        )
        if hardcode_match:
            action_type = "hardcode"
            target_literal = hardcode_match.group(1) or hardcode_match.group(2)
    
    if not action_type or (
        action_type != "map_source"
        and target_literal is None
        and target_token is None
        and target_tokens is None
    ):
        return None
    
    return {
        "conditions": conditions,
        "action_type": action_type,
        "target_literal": target_literal,
        "target_token": target_token,
        "target_tokens": target_tokens,
        "raw": condition,
    }


def _extract_guard_only_condition(condition: str) -> dict | None:
    """Recognize condition-only guard rows without a mapping action.

    These rows are useful parser output but are not directly enforceable as
    value-mapping rules, so they should be tracked as parsed-only.
    """
    normalized = _normalize_condition_text(condition)
    if not normalized:
        return None

    lowered = normalized.lower()
    if re.search(
        r"\b(?:map|hardcode|compute|concat|append)\b|\bto\s+target\b|\btarget\s+as\b",
        lowered,
        flags=re.IGNORECASE,
    ):
        return None

    expr = normalized
    if lowered.startswith("if "):
        expr = normalized[3:].strip()
    expr = re.sub(r"\bthen\b.*$", "", expr, flags=re.IGNORECASE).strip()
    if not expr:
        return None

    if not re.search(
        r"(?:<>|!=|==|=|\bexists\b|\bis\s+not\s+null\b|\bstarts\s*with\b)",
        expr,
        flags=re.IGNORECASE,
    ):
        return None

    return {"expr": expr, "raw": condition}


def _extract_instruction_only_condition(condition: str) -> dict | None:
    """Recognize prose/instruction rows that are not enforceable mapping rules."""
    normalized = _normalize_condition_text(condition)
    if not normalized:
        return None

    lowered = normalized.lower()
    instruction_prefixes = (
        "no mapping",
        "not in ",
        "loop based",
        "leave blank",
        "this is mandatory field",
        "for future use",
        "total number of",
        "the total number of",
        "a count of the number",
        "number of line item segments",
        "the control number",
        "the data interchange control number",
        "this number is assigned by sender",
        "number of included functional groups",
        "number of included segments",
        "number of segments in the message",
        "number of transaction sets included",
        "transaction set control number",
        "interchange control reference",
        "interchange control number",
        "interchange control count",
        "message reference number",
        "group control number",
        "continuous sequential number",
        "sequential number per",
        "value of source",
        "value of ",
        "convert to cdm date time format",
        "convert to cxml date time format",
        "use uuid",
        "system date & time",
    )
    if lowered.startswith(instruction_prefixes):
        return {"kind": "instruction", "raw": condition}

    if lowered in {"conversion:", "conversion"}:
        return {"kind": "instruction", "raw": condition}

    if re.fullmatch(r"map\s+\w+", lowered):
        return {"kind": "instruction", "raw": condition}

    if lowered.startswith("map value of ") or lowered == "display empty tag":
        return {"kind": "instruction", "raw": condition}

    if lowered.startswith("map the ") and " in each " in lowered and " to target" not in lowered:
        return {"kind": "instruction", "raw": condition}

    if lowered in {"direct mapping", "direct map"}:
        return {"kind": "instruction", "raw": condition}

    if lowered in {"map source to target", "true or false", "current datetime"}:
        return {"kind": "instruction", "raw": condition}

    if any(
        lowered.startswith(prefix)
        for prefix in [
            "cumulative of ",
            "map parent ",
            "hardcoded as below",
            "hardcode to ",
            "check lookup-conversion tab",
            "check lookup conversion tab",
            "tbc",
            "<sender id>",
            "<receiver id>",
            "unique sequential number",
            "has to be multiples",
            "unitofmeasure from ",
            "if only n1*sf or n1*st is present",
            "if errorcode",
            "generate each ",
            "ten empty spaces",
        ]
    ):
        return {"kind": "instruction", "raw": condition}

    if "yyyy-mm-dd" in lowered and "hh:mm:ss" in lowered:
        return {"kind": "instruction", "raw": condition}

    if any(
        phrase in lowered
        for phrase in [
            "do the logic below",
            "map the first occurence of",
            "trim \"data:image/png;base64,\" at the beginning of input",
            "if ${hostname}",
            "substring the first three character",
            "if /x12/ts_300/group_2/n1/n101 = \"ll\" and (dtm01",
            "if bespokehook[bespokecode=\"tmspostcode\"]/bespokevalue then map bespokehook[bespokecode=\"tmspostcode\"]/bespokevalue else map address[addresstype=\"3\"]/addressdetails/postalcode",
        ]
    ):
        return {"kind": "instruction", "raw": condition}

    if "->" in lowered and "if " not in lowered and " then " not in lowered:
        return {"kind": "instruction", "raw": condition}

    if "mapping from" in lowered and "if " not in lowered:
        return {"kind": "instruction", "raw": condition}

    if "lookup table" in lowered and "to target" in lowered:
        return {"kind": "instruction", "raw": condition}

    if any(token in lowered for token in ["uuid.randomuuid", "map current date time", "$toduns", "$hostname"]):
        return {"kind": "instruction", "raw": condition}

    if "with format mm/dd/yyyy" in lowered or "sample:" in lowered:
        return {"kind": "instruction", "raw": condition}

    if lowered.startswith("/x12/"):
        return {"kind": "instruction", "raw": condition}

    if "hardcode \"tag\"" in lowered:
        return {"kind": "instruction", "raw": condition}

    if re.search(r"\brefer\b", lowered) and not re.search(r"\bif\b|\bmap\b|\bhardcode\b", lowered):
        return {"kind": "instruction", "raw": condition}

    return None


def _extract_expression_map_to_target(condition: str) -> dict | None:
    """Parse expression guards that directly map source value to target.

    Example:
    - if the attribute or ediCustomerDepartment !="" map to Target
    """
    normalized = _normalize_condition_text(condition)
    if not normalized:
        return None

    lowered = normalized.lower()
    if any(
        token in lowered
        for token in [
            "substring",
            "startswith",
            "replace",
            "append",
            "concat",
            "hardcode",
            "format",
            "date",
        ]
    ):
        return None

    direct_map_match = re.search(
        r"^\s*(?:if\s+)?(.+?)\s+(?:then\s*)?direct\s+map\b",
        normalized,
        flags=re.IGNORECASE,
    )
    map_to_target_match = re.search(
        r"^\s*(?:if\s+)?(.+?)\s+(?:then\s*)?map\s+to\s+target\b",
        normalized,
        flags=re.IGNORECASE,
    )

    match = direct_map_match or map_to_target_match
    if not match:
        return None

    expr = match.group(1).strip()
    if not expr or expr.lower() in {"source", "value", "the value"}:
        return None

    return {"expr": expr, "raw": condition}


def _tokenize_boolean_expr(expr: str) -> list[str]:
    tokens: list[str] = []
    i = 0
    n = len(expr)
    while i < n:
        c = expr[i]
        if c.isspace():
            i += 1
            continue
        if c in "()":
            tokens.append(c)
            i += 1
            continue
        if c in {'"', "'"}:
            quote = c
            j = i + 1
            while j < n and expr[j] != quote:
                j += 1
            if j < n:
                j += 1
            tokens.append(expr[i:j])
            i = j
            continue
        if i + 1 < n and expr[i : i + 2] in {"&&", "||", "==", "!=", "<>"}:
            tokens.append(expr[i : i + 2])
            i += 2
            continue
        if c in {"=", "!", "<", ">"}:
            tokens.append(c)
            i += 1
            continue

        j = i
        while j < n and (not expr[j].isspace()) and expr[j] not in "()":
            if j + 1 < n and expr[j : j + 2] in {"&&", "||", "==", "!=", "<>"}:
                break
            if expr[j] in {"=", "!", "<", ">"}:
                break
            j += 1
        tokens.append(expr[i:j])
        i = j
    return tokens


def _unquote(text: str) -> str:
    raw = (text or "").strip()
    if len(raw) >= 2 and ((raw[0] == '"' and raw[-1] == '"') or (raw[0] == "'" and raw[-1] == "'")):
        return raw[1:-1]
    return raw


class _BooleanExprParser:
    def __init__(self, tokens: list[str], resolver):
        self.tokens = tokens
        self.pos = 0
        self.resolver = resolver

    def _peek(self) -> str | None:
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def _consume(self) -> str | None:
        token = self._peek()
        if token is not None:
            self.pos += 1
        return token

    def parse(self) -> bool:
        value = self._parse_or()
        return bool(value)

    def _parse_or(self) -> bool:
        value = self._parse_and()
        while True:
            tok = self._peek()
            if tok is None or tok.lower() not in {"or", "||"}:
                break
            self._consume()
            rhs = self._parse_and()
            value = value or rhs
        return value

    def _parse_and(self) -> bool:
        value = self._parse_factor()
        while True:
            tok = self._peek()
            if tok is None or tok.lower() not in {"and", "&&"}:
                break
            self._consume()
            rhs = self._parse_factor()
            value = value and rhs
        return value

    def _parse_factor(self) -> bool:
        tok = self._peek()
        if tok == "(":
            self._consume()
            inner = self._parse_or()
            if self._peek() == ")":
                self._consume()
            return inner
        return self._parse_predicate()

    def _parse_predicate(self) -> bool:
        lhs = self._consume()
        if lhs is None:
            return False
        op = self._peek()
        if op is None:
            return bool(self.resolver(lhs))

        op_lower = op.lower()
        if op_lower == "exists":
            self._consume()
            return bool(self.resolver(lhs))

        if op in {"=", "==", "!=", "<>"}:
            self._consume()
            rhs = self._consume()
            if rhs is None:
                return False
            lhs_val = self.resolver(lhs)
            rhs_val = _unquote(rhs)
            if op in {"!=", "<>"}:
                return lhs_val != rhs_val
            return lhs_val == rhs_val

        return bool(self.resolver(lhs))


def _evaluate_boolean_expr(
    expr: str,
    base_source_xpath: str,
    src_tree,
    src_ns: dict,
    src_root_name: str,
) -> bool:
    tokens = _tokenize_boolean_expr(expr)
    if not tokens:
        return False

    def _resolver(token: str) -> str:
        return _resolve_source_token_value(base_source_xpath, token, src_tree, src_ns, src_root_name)

    parser = _BooleanExprParser(tokens, _resolver)
    try:
        return parser.parse()
    except Exception:
        return False


def _evaluate_condition_expr(
    expr: str,
    base_source_xpath: str,
    src_tree,
    src_ns: dict,
    src_root_name: str,
) -> bool:
    text = _normalize_condition_text(expr)
    if not text:
        return False

    starts_with = re.fullmatch(
        r"([\w/\.\-]+)\s+starts(?:\s*with|with)\s*['\"]([^'\"]+)['\"]",
        text,
        flags=re.IGNORECASE,
    )
    if starts_with:
        actual = _resolve_source_token_value(base_source_xpath, starts_with.group(1), src_tree, src_ns, src_root_name)
        return bool(actual) and actual.startswith(starts_with.group(2))

    return _evaluate_boolean_expr(text, base_source_xpath, src_tree, src_ns, src_root_name)


def _extract_sequential_if_chain_map(condition: str) -> dict | None:
    """Parse sequential if...map...endIf blocks into a chain-like mapping."""
    normalized = _normalize_condition_text(condition)
    if not normalized:
        return None
    lowered = normalized.lower()
    if lowered.count("if ") < 2:
        return None

    map_fragment_pattern = (
        r"(?:target\s+(?:as\s*)?['\"][^'\"]+['\"]|['\"][^'\"]+['\"](?:\s+to\s+target)?|[^\s|]+(?:\s+to\s+target)?)"
    )
    block_pattern = re.compile(
        r"\bif\b\s+(.*?)\s+(?:then\s*)?(?:map|move)\s*("
        + map_fragment_pattern
        + r")\s*\bendif\b",
        flags=re.IGNORECASE,
    )
    clauses = []
    for match in block_pattern.finditer(normalized):
        target_literal, target_token = _parse_map_target_fragment(match.group(2))
        if target_literal is None and target_token is None:
            continue
        clauses.append(
            {
                "expr": match.group(1).strip(),
                "target_literal": target_literal,
                "target_token": target_token,
            }
        )

    if len(clauses) < 2:
        chain_pattern = re.compile(
            r"\bif\b\s+(.*?)\s+(?:then\s*)?(?:map|move)\s*("
            + map_fragment_pattern
            + r")\s*(?=\bif\b|$)",
            flags=re.IGNORECASE,
        )
        clauses = []
        for match in chain_pattern.finditer(normalized):
            target_literal, target_token = _parse_map_target_fragment(match.group(2))
            if target_literal is None and target_token is None:
                continue
            clauses.append(
                {
                    "expr": match.group(1).strip(),
                    "target_literal": target_literal,
                    "target_token": target_token,
                }
            )

    if len(clauses) < 2:
        return None

    return {
        "clauses": clauses,
        "raw": condition,
    }


def _extract_constant_expected(condition: str) -> str | None:
    """Extract expected constant from expressions like Value of source 'X'."""
    quoted = re.search(r'value\s+of\s+source\s*[\(:]?\s*"([^"]+)"', condition, flags=re.IGNORECASE)
    if quoted:
        return quoted.group(1)

    quoted = re.search(r"value\s+of\s+source\s*[\(:]?\s*'([^']+)'", condition, flags=re.IGNORECASE)
    if quoted:
        return quoted.group(1)

    plain = re.search(r"value\s+of\s+source\s*[:=]\s*([^\s\)]+)", condition, flags=re.IGNORECASE)
    if plain:
        return plain.group(1).strip('"\'')

    return None


def _extract_date_format_mapping(condition: str) -> dict | None:
    """Parse date-format token mapping rules.

    Supported examples:
    - if DTM02 exists then map Target "CCYYMMDD"
    - if DTM03 exists then Append to the Target as below based on the length of DTM03 | if length(DTM03) = 4 then Append "HHMM" to Target | else if length(DTM03) = 6 then Append "HHMMSS" to Target
    - concate Date and Time - CCYYMMDDHHMM
    """
    normalized = _normalize_condition_text(condition)
    if not normalized:
        return None

    # Support terse spec wording such as:
    # - Current Date CCYYMMDD format
    # - Current Time HHMMSS format
    current_token = re.search(
        r"\bcurrent\s+(?:date(?:\s*time)?|time)\s+(CCYYMMDD(?:HHMM(?:SS(?:DD?)?)?)?|YYYYMMDD(?:HHMM(?:SS(?:DD?)?)?)?|YYMMDD|HHMMSS|HHMM)\s+format\b",
        normalized,
        flags=re.IGNORECASE,
    )
    if current_token:
        return {
            "base_token": current_token.group(1),
            "time_source": None,
            "length_map": {},
            "raw": condition,
        }

    # Support short descriptive forms like "CCYYMMDD format".
    bare_format_token = re.search(
        r"\b(CCYYMMDD(?:HHMM(?:SS(?:DD?)?)?)?|YYYYMMDD(?:HHMM(?:SS(?:DD?)?)?)?|YYMMDD|HHMMSS|HHMM)\b.*\bformat\b",
        normalized,
        flags=re.IGNORECASE,
    )
    if bare_format_token:
        return {
            "base_token": bare_format_token.group(1),
            "time_source": None,
            "length_map": {},
            "raw": condition,
        }

    map_with_format = re.search(
        r"\bif\b\s+([^\s\(\)]+)\s*(?:!=|<>)\s*['\"]?\s*['\"]?\s+then\s+map\s+to\s+target\s+with\s+format\s+(CCYYMMDD|YYYYMMDD|YYMMDD|HHMMSS|HHMM)\b",
        normalized,
        flags=re.IGNORECASE,
    )
    if map_with_format:
        return {
            "base_source": map_with_format.group(1),
            "base_token": map_with_format.group(2),
            "time_source": None,
            "length_map": {},
            "guard_expr": None,
            "raw": condition,
        }

    source_map_with_format = re.search(
        r"\bif\s+source\s*(?:!=|<>)\s*['\"]?\s*['\"]?\s+map\s+(?:date|time|hour\s*,\s*minute\s*&\s*second)\s+to\s+target\s+with\s+format\s+(CCYYMMDD|YYYYMMDD|YYMMDD|HHMMSS|HHMM)\b",
        normalized,
        flags=re.IGNORECASE,
    )
    if source_map_with_format:
        return {
            "base_source": "Source",
            "base_token": source_map_with_format.group(1),
            "time_source": None,
            "length_map": {},
            "guard_expr": None,
            "raw": condition,
        }

    source_then_map_with_format = re.search(
        r"\bif\s+source\s*(?:!=|<>)\s*['\"]?\s*['\"]?\s+then\s+map\s+(?:date|time|hour\s*,\s*minute\s*&\s*second)\s+to\s+target\s+with\s+format\s+(CCYYMMDD|YYYYMMDD|YYMMDD|HHMMSS|HHMM)\b",
        normalized,
        flags=re.IGNORECASE,
    )
    if source_then_map_with_format:
        return {
            "base_source": "Source",
            "base_token": source_then_map_with_format.group(1),
            "time_source": None,
            "length_map": {},
            "guard_expr": None,
            "raw": condition,
        }

    if re.search(r"\bmap\s+current\s+date\b", normalized, flags=re.IGNORECASE):
        return {
            "base_token": "CCYYMMDD",
            "time_source": None,
            "length_map": {},
            "raw": condition,
        }

    hardcode = re.search(
        r'hardcode\s*["\'](CCYYMMDD(?:HHMM(?:SS(?:DD?)?)?)?|YYYYMMDD(?:HHMM(?:SS(?:DD?)?)?)?)["\']\s+to\s+target',
        normalized,
        flags=re.IGNORECASE,
    )
    if hardcode:
        return {"base_token": hardcode.group(1), "time_source": None, "length_map": {}, "raw": condition}

    bare_token = re.fullmatch(
        r"(CCYYMMDD(?:HHMM(?:SS(?:DD?)?)?)?|YYYYMMDD(?:HHMM(?:SS(?:DD?)?)?)?)",
        normalized,
        flags=re.IGNORECASE,
    )
    if bare_token:
        return {"base_token": bare_token.group(1), "time_source": None, "length_map": {}, "raw": condition}

    concat_token = re.search(
        r"conc(?:at|ate|enate|inate).*?(CCYYMMDD(?:HHMM(?:SS(?:DD?)?)?)?|YYYYMMDD(?:HHMM(?:SS(?:DD?)?)?)?)",
        normalized,
        flags=re.IGNORECASE,
    )
    if concat_token:
        return {"base_token": concat_token.group(1), "time_source": None, "length_map": {}, "raw": condition}

    guarded_length = re.search(
        r"\bif\b\s+(.*?)\s+then\s+map\s+as\s+below",
        normalized,
        flags=re.IGNORECASE,
    )
    if guarded_length:
        guarded_map: dict[int, str] = {}
        guarded_source = None
        for match in re.finditer(
            r"(?:\bif\b|\belseif\b)\s+length\s*\(\s*([^\)]+)\s*\)\s*=\s*(\d+)\s+then\s+(?:map\s+)?[\"'](CCYYMMDD(?:HHMM(?:SS(?:DD?)?)?)?|YYYYMMDD(?:HHMM(?:SS(?:DD?)?)?)?)[\"'](?:\s+to\s+target)?",
            normalized,
            flags=re.IGNORECASE,
        ):
            guarded_source = match.group(1).strip()
            guarded_map[int(match.group(2))] = match.group(3)

        if guarded_map and guarded_source:
            return {
                "base_source": None,
                "base_token": None,
                "time_source": guarded_source,
                "length_map": guarded_map,
                "guard_expr": guarded_length.group(1).strip(),
                "raw": condition,
            }

    base_match = re.search(
        r"if\s+([^\s]+)\s+exists\s+then\s+map\s+(?:target\s+)?(?:as\s+)?[\"'](CCYYMMDD|YYYYMMDD)[\"']",
        normalized,
        flags=re.IGNORECASE,
    )
    if not base_match:
        return None

    base_token = base_match.group(2)
    base_source = base_match.group(1)
    length_map: dict[int, str] = {}
    time_source = None
    for match in re.finditer(
        r"if\s+length\s*\(\s*([^\)]+)\s*\)\s*=\s*(\d+)\s+then\s+append\s+[\"']([^\"']+)[\"']\s+to\s+target",
        normalized,
        flags=re.IGNORECASE,
    ):
        time_source = match.group(1).strip()
        length_map[int(match.group(2))] = match.group(3)

    return {
        "base_source": base_source,
        "base_token": base_token,
        "time_source": time_source,
        "length_map": length_map,
        "guard_expr": None,
        "raw": condition,
    }


def _extract_field_concat_mapping(condition: str) -> dict | None:
    """Parse multi-field concatenation rules.

    Supported examples:
    - Concatenate DTM02 + DTM03 then map to Target
    - Concatenate "20" + /X12/ISA/ISA09 + /X12/ISA/ISA10
    - Concatenate DTM02 and DTM03 then map to Target
    """
    normalized = " ".join((condition or "").split())
    if not normalized:
        return None
    # Must look like a concatenation instruction, not the prefix-source style already handled
    if not re.search(r"\bconcat\w*\b", normalized, re.IGNORECASE):
        return None
    # Already handled by _concat_expected (prefix + <source>)
    if re.search(r'concat(?:\w*)\s*\(\s*"[^"]*"\s*,\s*<[^>]+>\s*\)', normalized, re.IGNORECASE):
        return None
    # Already handled by _extract_date_format_mapping (CCYYMMDD tokens)
    if re.search(r"CCYYMMDD|YYYYMMDD", normalized, re.IGNORECASE):
        return None

    # Extract the token list from: Concatenate A + B + C [then map to Target]
    # Strip optional leading keyword and trailing "then map to target"
    body = re.sub(r"^.*?\bconcat\w*\b\s*", "", normalized, count=1, flags=re.IGNORECASE)
    body = re.sub(r"\s*then\s+map\s+to\s+target.*$", "", body, flags=re.IGNORECASE)
    body = re.sub(r"\s*map\s+to\s+target.*$", "", body, flags=re.IGNORECASE)
    body = body.strip()

    # Split by + or keyword 'and' (but not inside quotes)
    raw_tokens = re.split(r"\s*\+\s*|\s+and\s+", body, flags=re.IGNORECASE)
    tokens = []
    for tok in raw_tokens:
        tok = tok.strip()
        if not tok:
            continue
        # Quoted literal
        if (tok.startswith('"') and tok.endswith('"')) or (tok.startswith("'") and tok.endswith("'")):
            tokens.append({"kind": "literal", "value": tok[1:-1]})
        elif tok:
            tokens.append({"kind": "field", "value": tok})

    if len(tokens) < 2:
        return None

    return {"tokens": tokens, "raw": condition}


def _is_direct_map_rule(condition: str) -> bool:
    """Return True for 'Direct Map' conditions (plain or with an inline filter).

    Examples:
    - Direct Map
    - Direct Map | /X12/TS_300/N9/N901 = "ZZZ"
    """
    normalized = " ".join((condition or "").split())
    return bool(re.match(r"^direct\s*map\b", normalized, re.IGNORECASE))


def _looks_like_ambiguous_complex_condition(condition: str) -> bool:
    """Return True when a condition still looks too complex for generic direct-map fallback.

    This is a conservative guard: if the parser did not already recognize the condition as a
    supported semantic family, do not let a direct-map fallback guess through transformations,
    conversions, hardcodes, or other branching logic.
    """
    normalized = " ".join((condition or "").split())
    if not normalized:
        return False
    if re.match(r"^direct\s*map\b", normalized, re.IGNORECASE):
        return False
    return bool(
        re.search(
            r"\b(if|elseif|else|conversion|concat|append|substring|replace|hardcode|compute|length\s*\(|starts?\s*with|source\s+exists|source\s+is\s+not\s+null)\b",
            normalized,
            flags=re.IGNORECASE,
        )
    )


def _extract_startswith_substring_mapping(condition: str) -> dict | None:
    """Parse startsWith + skip-N-chars + optional-append patterns.

    Examples:
    - if H201 startsWith "GEN-" | Get the substring after the first 4 characters from the left from H201 and map to Target
    - if H201 startsWith "GEN-" | Get the substring after the first 4 characters from the left from H201 + H202 and map to Target
    """
    normalized = " ".join((condition or "").split())
    if not normalized:
        return None

    starts_with = re.search(
        r"\bif\b\s+([\w/\.\-]+)\s+starts(?:\s*with|with)\s*['\"]([^'\"]+)['\"]",
        normalized,
        flags=re.IGNORECASE,
    )
    if not starts_with:
        return None

    # Must contain a 'substring after first N characters' instruction
    skip_match = re.search(
        r"substring\s+after\s+the\s+first\s+(\d+)\s+char",
        normalized,
        flags=re.IGNORECASE,
    )
    if not skip_match:
        return None

    source_field = starts_with.group(1)
    prefix = starts_with.group(2)
    skip_chars = int(skip_match.group(1))

    # Optional: source field + sibling before "and map to target"
    # e.g. "from H201 + H202 and map"
    append_field: str | None = None
    append_match = re.search(
        r"from\s+" + re.escape(source_field) + r"\s*\+\s*([\w/\.\-]+)\s+and\s+map",
        normalized,
        flags=re.IGNORECASE,
    )
    if append_match:
        append_field = append_match.group(1)

    return {
        "source_field": source_field,
        "prefix": prefix,
        "skip_chars": skip_chars,
        "append_field": append_field,
        "raw": condition,
    }


def _extract_startswith_constant_mapping(condition: str) -> dict | None:
    """Parse startsWith guard with literal target mapping.

    Examples:
    - if source startsWith 'ECA' then map Target as "true"
    - If source starts with "FRZ" then map "true" to Target
    - If source starts with "ICT" then map target to "true"
    """
    normalized = _normalize_condition_text(condition)
    if not normalized:
        return None

    match = re.search(
        r"\bif\b\s+(?:source|[\w/\.\-]+)\s+starts(?:\s*with|with)\s*['\"]([^'\"]+)['\"]\s+(?:then\s*)?(?:map|move)\s+(.+?)\s*(?=\belseif\b|\belse\b|\bendif\b|$)",
        normalized,
        flags=re.IGNORECASE,
    )
    if not match:
        return None

    target_literal, target_token = _parse_map_target_fragment(match.group(2))
    if target_literal is None or target_token is not None:
        return None

    return {"prefix": match.group(1), "target_literal": target_literal, "raw": condition}


def _extract_if_exists_else_map(condition: str) -> dict | None:
    """Parse 'if expr then map X else map Y' patterns where expr may be existence-like."""
    normalized = _normalize_condition_text(condition)
    if not normalized:
        return None

    # Keep bracket-predicate expressions out of this lightweight parser.
    if "[" in normalized or "]" in normalized:
        return None

    match = re.search(
        r"\bif\b\s+(.+?)\s+(?:then\s*)?(?:map|move)\s+(.+?)\s+\belse\b\s*(?:then\s*)?(?:map|move)\s+(.+?)\s*(?=\bendif\b|$)",
        normalized,
        flags=re.IGNORECASE,
    )
    if not match:
        return None

    true_fragment = match.group(2).strip()
    false_fragment = match.group(3).strip()

    true_from_source = true_fragment.lower() in {"to", "target", "to target"}
    false_from_source = false_fragment.lower() in {"to", "target", "to target"}

    true_literal, true_token = (None, None)
    if not true_from_source:
        true_literal, true_token = _parse_map_target_fragment(true_fragment)
        if true_literal is None and true_token is None:
            return None

    false_literal, false_token = (None, None)
    if not false_from_source:
        false_literal, false_token = _parse_map_target_fragment(false_fragment)
        if false_literal is None and false_token is None:
            return None

    return {
        "expr": match.group(1).strip(),
        "true_target_literal": true_literal,
        "true_target_token": true_token,
        "true_target_from_source": true_from_source,
        "false_target_literal": false_literal,
        "false_target_token": false_token,
        "false_target_from_source": false_from_source,
        "raw": condition,
    }


def _extract_if_replace_map_to_target(condition: str) -> dict | None:
    """Parse conditional replace-then-map patterns.

    Example:
    - If Source != "" then replace "Tm" with "Ic" and map to Target
    """
    normalized = _normalize_condition_text(condition)
    if not normalized:
        return None

    match = re.search(
        r"\bif\b\s+([^\s\(\)]+)\s*(=|==|!=|<>)\s*['\"]([^'\"]*)['\"]\s+(?:then\s*)?replace\s+['\"]([^'\"]+)['\"]\s+with\s+['\"]([^'\"]*)['\"]\s+and\s+(?:map|move)\s+to\s+target\b",
        normalized,
        flags=re.IGNORECASE,
    )
    if not match:
        return None

    return {
        "lhs_token": match.group(1),
        "operator": match.group(2),
        "compare_value": match.group(3),
        "replace_from": match.group(4),
        "replace_to": match.group(5),
        "raw": condition,
    }


def _extract_if_equals_get_substring_mapping(condition: str) -> dict | None:
    """Parse if-equals guard plus get-substring mapping patterns.

    Example:
    - if H201 = "IHL" Get the substring after the first 4 characters from the left from H201 and map to Target
    """
    normalized = " ".join((condition or "").split())
    if not normalized:
        return None

    guard_match = re.search(
        r"\bif\b\s+([\w/\.\-]+)\s*={1,2}\s*['\"]([^'\"]+)['\"]",
        normalized,
        flags=re.IGNORECASE,
    )
    if not guard_match:
        return None

    substring_match = re.search(
        r"get\s+the\s+substring\s+after\s+the\s+first\s+(\d+)\s+characters?\s+from\s+the\s+left\s+from\s+([\w/\.\-]+)(?:\s*\+\s*([\w/\.\-]+))?\s+and\s+map\s+to\s+target",
        normalized,
        flags=re.IGNORECASE,
    )
    if not substring_match:
        return None

    return {
        "lhs_token": guard_match.group(1),
        "equals_value": guard_match.group(2),
        "skip_chars": int(substring_match.group(1)),
        "source_field": substring_match.group(2),
        "append_field": substring_match.group(3),
        "raw": condition,
    }


def _extract_if_in_list_substring_source_mapping(condition: str) -> dict | None:
    """Parse in-list guards with substring(source,start,len) map action.

    Example:
    - If N101 = "LL" | "SF" | "ST" then Direct Map Map substring(source, 1,35) to Target
    """
    normalized = " ".join((condition or "").split())
    if not normalized:
        return None

    match = re.search(
        r"\bif\b\s+([^\s\(\)]+)\s*={1,2}\s*(.+?)\s+(?:then\s*)?(?:direct\s+map\s+)?map\s+substring\s*\(\s*source\s*,\s*(\d+)\s*,\s*(\d+)\s*\)\s+to\s+target",
        normalized,
        flags=re.IGNORECASE,
    )
    if not match:
        return None

    values_blob = match.group(2)
    values = re.findall(r"['\"]([^'\"]+)['\"]", values_blob)
    if not values:
        return None

    return {
        "lhs_token": match.group(1),
        "values": values,
        "start_offset": max(int(match.group(3)) - 1, 0),
        "length": int(match.group(4)),
        "raw": condition,
    }


def _extract_char_offset_mapping(condition: str) -> dict | None:
    """Parse fixed character-offset extraction rules.

    Examples:
    - Map left 35 Characters to Target
    - Map next 35 characters to Target (starting from 36th chr)
    """
    normalized = " ".join((condition or "").split())
    if not normalized:
        return None

    # "Map left N characters" pattern
    left_match = re.search(
        r"\bmap\s+left\s+(\d+)\s+char",
        normalized,
        flags=re.IGNORECASE,
    )
    if left_match:
        length = int(left_match.group(1))
        return {
            "extraction_type": "left",
            "length": length,
            "start_offset": 0,
            "raw": condition,
        }

    # "Map next N characters (starting from Mth chr)" pattern
    next_match = re.search(
        r"\bmap\s+next\s+(\d+)\s+char.*?(?:starting\s+from\s+(\d+)(?:st|nd|rd|th)?\s+chr|starting\s+from\s+position\s+(\d+))",
        normalized,
        flags=re.IGNORECASE,
    )
    if next_match:
        length = int(next_match.group(1))
        start_1indexed = int(next_match.group(2) or next_match.group(3))
        start_offset = start_1indexed - 1  # Convert 1-indexed to 0-indexed
        return {
            "extraction_type": "next",
            "length": length,
            "start_offset": start_offset,
            "raw": condition,
        }

    bare_next_match = re.search(
        r"\bmap\s+next\s+(\d+)\s+char(?:acters?|s)?\s+to\s+target\b",
        normalized,
        flags=re.IGNORECASE,
    )
    if bare_next_match:
        return {
            "extraction_type": "next",
            "length": int(bare_next_match.group(1)),
            "start_offset": 0,
            "raw": condition,
        }

    substring_match = re.search(
        r"\bmap\s+substring\s*\(\s*source\s*,\s*(\d+)\s*,\s*(\d+)\s*\)\s+to\s+target\b",
        normalized,
        flags=re.IGNORECASE,
    )
    if substring_match:
        start_1indexed = int(substring_match.group(1))
        length = int(substring_match.group(2))
        return {
            "extraction_type": "substring_source",
            "length": length,
            "start_offset": max(start_1indexed - 1, 0),
            "raw": condition,
        }

    return None


def _extract_source_substring_date_part_mapping(condition: str) -> dict | None:
    """Parse date-part substring rules from Source.

    Example:
    - if Source !="" then substring the CCYY then map to Target
    """
    normalized = _normalize_condition_text(condition)
    if not normalized:
        return None

    match = re.search(
        r"\bif\b\s+(?:source|[^\s\(\)]+)\s*(?:!=|<>)\s*['\"]?\s*['\"]?\s*(?:then\s*)?substring\s+the\s+(CCYY|YYYY|MM|DD|HH|DATE|TIME)\s+then\s+map\s+to\s+target",
        normalized,
        flags=re.IGNORECASE,
    )
    if not match:
        return None

    return {
        "part": match.group(1).upper(),
        "raw": condition,
    }


def _extract_conversion_if_chain_map(condition: str) -> dict | None:
    """Parse conversion-style multi-if chains, with optional outer exists guard.

    Examples:
    - if L004 exists then Conversion: if L011 = 'K' then map 'KGM' to Target if L011 = 'L' then map 'LBR' to Target
    - Conversion: If source (H201)= "GAS" then map Target as "Gas" If source (H201)= "LQD" then map Target as "Liquid"
    """
    normalized = _normalize_condition_text(condition)
    if not normalized:
        return None

    working = normalized
    outer_exists_token = None
    outer_match = re.match(r"^\s*if\s+([^\s\(\)]+)\s+exists\s+then\s*(.*)$", working, flags=re.IGNORECASE)
    if outer_match:
        outer_exists_token = outer_match.group(1)
        working = outer_match.group(2).strip()

    # Only handle explicit conversion rules to avoid overlapping generic if/elseif parsers.
    if not re.search(r"\bconversion\b", working, flags=re.IGNORECASE):
        return None

    working = re.sub(r"^\s*conversion\s*:\s*", "", working, flags=re.IGNORECASE)

    map_fragment_pattern = (
        r"(?:target\s+(?:as\s*)?['\"][^'\"]+['\"]|['\"][^'\"]+['\"](?:\s+to\s+target)?|[^\s|]+(?:\s+to\s+target)?)"
    )
    clause_pattern = re.compile(
        r"\bif\b\s+(?:source\s*\(\s*([^\)]+)\s*\)|([^\s\(\)]+))\s*(?:(=|==|!=|<>)\s*['\"]([^'\"]*)['\"]|starts(?:\s*with|with)\s*['\"]([^'\"]+)['\"])\s+(?:then\s*)?(?:map|move)\s*("
        + map_fragment_pattern
        + r")\s*(?=\bif\b|\belse\b|\bendif\b|$)",
        flags=re.IGNORECASE,
    )

    clauses = []
    for match in clause_pattern.finditer(working):
        lhs_token = (match.group(1) or match.group(2) or "").strip()
        target_literal, target_token = _parse_map_target_fragment(match.group(6))
        if not lhs_token or (target_literal is None and target_token is None):
            continue
        clauses.append(
            {
                "lhs_token": lhs_token,
                "operator": "startswith" if match.group(5) is not None else match.group(3),
                "compare_value": match.group(5) if match.group(5) is not None else match.group(4),
                "target_literal": target_literal,
                "target_token": target_token,
            }
        )

    else_match = re.search(
        r"\belse\b\s*(?:then\s*)?(?:map|move)\s*(target\s+(?:as\s*)?['\"][^'\"]+['\"]|['\"][^'\"]+['\"](?:\s+to\s+target)?|[^\s|]+(?:\s+to\s+target)?)\s*(?=\bendif\b|$)",
        working,
        flags=re.IGNORECASE,
    )
    else_map = None
    if else_match:
        target_literal, target_token = _parse_map_target_fragment(else_match.group(1))
        if target_literal is not None or target_token is not None:
            else_map = {"target_literal": target_literal, "target_token": target_token}

    if len(clauses) < 2 and else_map is None:
        return None

    return {
        "outer_exists_token": outer_exists_token,
        "clauses": clauses,
        "else_map": else_map,
        "raw": condition,
    }


def _extract_date_part_value(source_value: str, part: str, target_xpath: str) -> str:
    """Extract date-part token from compact datetime-like source strings."""
    value = (source_value or "").strip()
    token = (part or "").upper()
    tgt_lower = (target_xpath or "").lower()

    if token in {"CCYY", "YYYY"}:
        return value[0:4] if len(value) >= 4 else ""
    if token == "DATE":
        return value[0:8] if len(value) >= 8 else ""
    if token == "TIME":
        if len(value) >= 14:
            return value[8:14]
        if len(value) >= 12:
            return value[8:12]
        return value[8:] if len(value) > 8 else ""
    if token == "DD":
        return value[6:8] if len(value) >= 8 else ""
    if token == "HH":
        return value[8:10] if len(value) >= 10 else ""
    if token == "MM":
        is_minute_target = any(k in tgt_lower for k in ["minute", "min", "hhmm", "time"]) and "month" not in tgt_lower
        if is_minute_target and len(value) >= 12:
            return value[10:12]
        return value[4:6] if len(value) >= 6 else ""
    return ""


def _length_compare(actual: int, operator: str, threshold: int) -> bool:
    if operator in {"=", "=="}:
        return actual == threshold
    if operator == "!=":
        return actual != threshold
    if operator == "<":
        return actual < threshold
    if operator == "<=":
        return actual <= threshold
    if operator == ">":
        return actual > threshold
    if operator == ">=":
        return actual >= threshold
    return False


def _resolve_length_map_action(
    base_source_xpath: str,
    action: dict | None,
    src_tree,
    src_ns: dict,
    src_root_name: str,
) -> str | None:
    if action is None:
        return None
    kind = action.get("kind")
    if kind == "literal":
        return action.get("literal", "")
    if kind == "token":
        return _resolve_source_token_value(base_source_xpath, action.get("token", ""), src_tree, src_ns, src_root_name)
    if kind == "left":
        value = _resolve_source_token_value(base_source_xpath, action.get("token", ""), src_tree, src_ns, src_root_name)
        return (value or "")[: action.get("length", 0)]
    return None


def _evaluate_optional_guard_expr(
    expr: str | None,
    base_source_xpath: str,
    src_tree,
    src_ns: dict,
    src_root_name: str,
) -> bool:
    if not expr:
        return True
    return _evaluate_boolean_expr(expr, base_source_xpath, src_tree, src_ns, src_root_name)


def _is_if_source_map_rule(condition: str) -> bool:
    normalized = _normalize_condition_text(condition).lower()
    if "if source" not in normalized:
        return False
    if "map source to target" in normalized:
        return True
    return bool(
        re.search(
            r"\bif\s+source\s*(?:!=|<>)\s*['\"]?\s*['\"]?\s*(?:then\s*)?map\s+to\s+target(?:\b|\s+)",
            normalized,
            flags=re.IGNORECASE,
        )
    )


def _is_semantic_direct_map_comment(condition: str, semantic_profile: dict[str, object] | None = None) -> bool:
    """Detect prose rules that still mean source value should map directly to target."""
    normalized = _normalize_condition_text(condition).lower()
    if not normalized:
        return False

    direct_match_patterns = list(_DEFAULT_DIRECT_MAP_COMMENT_PATTERNS)
    if semantic_profile:
        intent_patterns = dict(semantic_profile.get("intent_patterns", {}))
        profile_patterns = intent_patterns.get("direct_map_comment_patterns", [])
        direct_match_patterns = [
            str(pattern).strip()
            for pattern in profile_patterns
            if str(pattern).strip()
        ] or direct_match_patterns

    for pattern in direct_match_patterns:
        try:
            if re.search(pattern, normalized, flags=re.IGNORECASE):
                return True
        except re.error:
            continue
    return False


def _infer_sibling_xpath(base_source_xpath: str, field_name: str) -> str | None:
    """Infer sibling element XPath, e.g. /A/B/C101 + C102 => /A/B/C102."""
    if not base_source_xpath or not field_name:
        return None
    cleaned = field_name.strip().strip("\"'")
    if not cleaned or "/" in cleaned:
        return None
    if "/" not in base_source_xpath:
        return None
    parent = base_source_xpath.rsplit("/", 1)[0]
    return f"{parent}/{cleaned}"


def _resolve_source_token_value(
    base_source_xpath: str,
    token: str,
    src_tree,
    src_ns: dict,
    src_root_name: str,
) -> str:
    """Resolve a source token to a concrete value from input XML.

    Token can be:
    - Source (uses base source xpath)
    - absolute/relative xpath
    - sibling field token (e.g. K102)
    """
    raw = (token or "").strip().strip("\"'")
    if not raw:
        if _ACTIVE_TOKEN_RESOLUTION_STATS is not None:
            _ACTIVE_TOKEN_RESOLUTION_STATS["empty_token"] = _ACTIVE_TOKEN_RESOLUTION_STATS.get("empty_token", 0) + 1
        return ""

    resolved_xpath = ""
    mode = ""
    if raw.lower() == "source":
        mode = "base_source"
        resolved_xpath = _normalize_xpath(base_source_xpath, src_root_name)
    elif raw.startswith("/"):
        mode = "absolute_xpath"
        resolved_xpath = _normalize_xpath(raw, src_root_name)
    elif "/" in raw:
        mode = "explicit_path"
        resolved_xpath = _normalize_xpath(raw, src_root_name)
    else:
        mode = "inferred_sibling"
        resolved_xpath = _infer_sibling_xpath(base_source_xpath, raw) or ""

    if not resolved_xpath:
        if _ACTIVE_TOKEN_RESOLUTION_STATS is not None:
            _ACTIVE_TOKEN_RESOLUTION_STATS["unresolved_xpath"] = _ACTIVE_TOKEN_RESOLUTION_STATS.get("unresolved_xpath", 0) + 1
        return ""
    vals = xpath_values(src_tree, src_ns, resolved_xpath)
    value = _first_non_empty_value(vals)
    if _ACTIVE_TOKEN_RESOLUTION_STATS is not None:
        _ACTIVE_TOKEN_RESOLUTION_STATS[mode] = _ACTIVE_TOKEN_RESOLUTION_STATS.get(mode, 0) + 1
        if value:
            _ACTIVE_TOKEN_RESOLUTION_STATS["resolved_value"] = _ACTIVE_TOKEN_RESOLUTION_STATS.get("resolved_value", 0) + 1
        else:
            _ACTIVE_TOKEN_RESOLUTION_STATS["unresolved_value"] = _ACTIVE_TOKEN_RESOLUTION_STATS.get("unresolved_value", 0) + 1
    return value


def _resolve_condition_target_value(
    base_source_xpath: str,
    target_literal: str | None,
    target_token: str | None,
    src_tree,
    src_ns: dict,
    src_root_name: str,
) -> str:
    if target_literal is not None:
        return target_literal
    if target_token:
        return _resolve_source_token_value(base_source_xpath, target_token, src_tree, src_ns, src_root_name)
    return ""


def _format_error(row: int, target_xpath: str, message: str) -> str:
    return f"Row {row} | Target: {target_xpath} | {message}"


def _has_non_empty_value(values: list[str]) -> bool:
    return any(str(v).strip() for v in values)


def _first_non_empty_value(values: list[str]) -> str:
    for value in values:
        candidate = str(value).strip()
        if candidate:
            return candidate
    return ""


def _is_actionable_expected(value: str | None) -> bool:
    """Return True when an expected value is resolved enough for strict comparison."""
    if value is None:
        return False
    return bool(str(value).strip())


def _estimate_rule_confidence(status: str, has_condition: bool, is_direct_map: bool, similarity_score: float = 0.0) -> float:
    """Estimate per-rule confidence for diagnostics and future gating."""
    if status == "unsupported":
        return max(0.05, min(0.45, float(similarity_score)))
    if status == "parsed_only":
        return 0.55
    if is_direct_map and not has_condition:
        return 0.95
    return 0.85


def _clamp_score(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _confidence_label(score: float) -> str:
    if score >= 0.8:
        return "high"
    if score >= 0.55:
        return "medium"
    return "low"


def _build_ai_review_evidence(
    *,
    status: str,
    has_condition: bool,
    source_xpath: str,
    target_xpath: str,
    family: str,
    semantic_action: str,
    similarity_score: float,
    row_error_count: int,
    source_has_value: bool | None = None,
    target_has_value: bool | None = None,
) -> dict[str, object]:
    syntax_evidence = 1.0 if status in {"enforced", "parsed_only"} else 0.35
    semantic_evidence = 0.9 if family and family != "unknown" else (0.65 if semantic_action != "unknown" else 0.4)
    source_path_evidence = 1.0 if str(source_xpath or "").strip() else 0.2
    target_path_evidence = 1.0 if str(target_xpath or "").strip().startswith("/") else 0.25

    contradiction_penalty = 0.0
    if row_error_count > 0:
        contradiction_penalty += min(0.6, 0.15 * row_error_count)
    if source_has_value is False and status == "enforced":
        contradiction_penalty += 0.15
    if target_has_value is False and status == "enforced":
        contradiction_penalty += 0.2
    cross_field_evidence = _clamp_score(1.0 - contradiction_penalty)

    historical_evidence = _clamp_score(
        0.45
        if status == "unsupported"
        else (0.7 if has_condition else 0.9)
        if similarity_score <= 0
        else similarity_score
    )

    weights = {
        "syntax": 0.2,
        "semantic": 0.2,
        "source_path": 0.15,
        "target_path": 0.1,
        "cross_field": 0.25,
        "historical": 0.1,
    }
    score = _clamp_score(
        (syntax_evidence * weights["syntax"])
        + (semantic_evidence * weights["semantic"])
        + (source_path_evidence * weights["source_path"])
        + (target_path_evidence * weights["target_path"])
        + (cross_field_evidence * weights["cross_field"])
        + (historical_evidence * weights["historical"])
    )
    return {
        "score": round(score, 4),
        "confidence": _confidence_label(score),
        "components": {
            "syntax_evidence": round(syntax_evidence, 4),
            "semantic_evidence": round(semantic_evidence, 4),
            "source_path_evidence": round(source_path_evidence, 4),
            "target_path_evidence": round(target_path_evidence, 4),
            "cross_field_evidence": round(cross_field_evidence, 4),
            "historical_evidence": round(historical_evidence, 4),
        },
    }


def _rebalance_support_summary_status(
    support_summary: dict[str, object],
    from_status: str,
    to_status: str,
) -> None:
    if from_status == to_status:
        return
    from_key = f"{from_status}_rules"
    to_key = f"{to_status}_rules"
    if from_key in support_summary:
        support_summary[from_key] = max(0, int(support_summary.get(from_key, 0)) - 1)
    if to_key in support_summary:
        support_summary[to_key] = int(support_summary.get(to_key, 0)) + 1


def _ai_review_conflicts(
    *,
    status: str,
    has_condition: bool,
    source_xpath: str,
    family: str,
    semantic_action: str,
    row_error_count: int,
    enforce_source_path_guardrail: bool = True,
) -> list[str]:
    issues: list[str] = []
    if status != "enforced":
        return issues
    if row_error_count > 0:
        issues.append("runtime output evidence contradicts deterministic enforcement")
    source_required_actions = {"map", "map_source", "copy", "derive"}
    source_required_families = {
        "direct_map",
        "if_source_map",
        "translation",
        "source_exists_constant",
        "token_exists",
        "source_is_not_null",
    }
    if (
        enforce_source_path_guardrail
        and has_condition
        and not str(source_xpath or "").strip()
        and (
            str(semantic_action or "").strip().lower() in source_required_actions
            or str(family or "").strip().lower() in source_required_families
        )
    ):
        issues.append("conditional rule has no resolvable source path")
    return issues


def _decision_intent_class(decision: dict[str, object]) -> str:
    family = str(decision.get("family", "") or "").strip().lower()
    reason = str(decision.get("reason", "") or "").strip().lower()
    source_xpath = str(decision.get("source_xpath", "") or "").strip()

    if family in {"hardcode", "source_exists_constant"} or "constant" in reason or "hardcode" in reason:
        return "fixed_value"
    if family in {
        "translation",
        "if_equals",
        "if_equals_chain",
        "if_expression_chain",
        "if_exists_else",
        "if_replace",
        "startswith_replace",
        "startswith_replace_append",
        "startswith_constant",
        "date_format",
        "length_based",
        "field_concat",
        "concatenate",
    }:
        return "conditional_transform"
    if source_xpath and family in {"direct_map", "token_exists", "source_is_not_null", "", "unknown"}:
        return "source_map"
    if source_xpath:
        return "source_map"
    return "unknown"


def _detect_enforced_target_intent_conflicts(rule_decisions: list[dict[str, object]]) -> list[dict[str, object]]:
    """Find targets where enforced rules disagree on primary intent class."""
    by_target: dict[str, list[dict[str, object]]] = {}
    for decision in rule_decisions:
        if str(decision.get("status", "")) != "enforced":
            continue
        target_xpath = str(decision.get("target_xpath", "") or "").strip()
        if not target_xpath:
            continue
        by_target.setdefault(target_xpath, []).append(decision)

    conflicts: list[dict[str, object]] = []
    for target_xpath, decisions in by_target.items():
        if len(decisions) < 2:
            continue
        intent_classes = {
            _decision_intent_class(item)
            for item in decisions
            if _decision_intent_class(item) != "unknown"
        }
        if len(intent_classes) < 2:
            continue

        high_risk_conflict = (
            ("fixed_value" in intent_classes and "source_map" in intent_classes)
            or ("fixed_value" in intent_classes and "conditional_transform" in intent_classes)
        )
        if not high_risk_conflict:
            continue

        rows = sorted({int(item.get("row", 0) or 0) for item in decisions if int(item.get("row", 0) or 0) > 0})
        conflicts.append(
            {
                "target_xpath": target_xpath,
                "rows": rows,
                "intent_classes": sorted(intent_classes),
                "reason": (
                    "Cross-rule contradiction: enforced rules disagree on whether target should be "
                    "source-derived or fixed/transformed"
                ),
            }
        )
    return conflicts


_ACTIVE_TOKEN_RESOLUTION_STATS: dict[str, int] | None = None


def _get_shadow_rule_families() -> set[str]:
    raw = os.getenv("MVP_SHADOW_RULE_FAMILIES", "").strip()
    if not raw:
        return set()
    return {part.strip().lower() for part in raw.split(",") if part.strip()}


def _xpath_match_count(tree, nsmap: dict, xpath: str) -> int:
    """Return the number of XPath matches (elements/attributes/scalars), not just text values."""
    if not xpath:
        return 0

    xp = rewrite_xpath_for_default_ns(xpath, nsmap)
    try:
        result = tree.xpath(xp, namespaces=nsmap)
    except Exception:
        result = []

    if isinstance(result, list):
        if result:
            return len(result)
    elif result is not None:
        return 1

    # EDI loop-aware fallback for GROUP_* tokens, mirroring xpath_values behavior.
    if "GROUP_" in xpath.upper():
        fallback_xpath = re.sub(r"/GROUP_\d+", "", xpath, flags=re.IGNORECASE)
        if fallback_xpath and fallback_xpath != xpath:
            fallback_xp = rewrite_xpath_for_default_ns(fallback_xpath, nsmap)
            try:
                fallback_result = tree.xpath(fallback_xp, namespaces=nsmap)
            except Exception:
                fallback_result = []
            if isinstance(fallback_result, list):
                return len(fallback_result)
            return 1 if fallback_result is not None else 0
    return 0


def _target_path_has_nodes(tree, nsmap: dict, target_xpath: str) -> bool:
    return _xpath_match_count(tree, nsmap, target_xpath) > 0


def _collect_container_target_paths(simplified_targets: set[str]) -> set[str]:
    """Return target paths that are containers (appear as ancestors of other target paths)."""
    ancestor_paths: set[str] = set()
    for path in simplified_targets:
        for ancestor in _path_ancestors(path)[:-1]:
            ancestor_paths.add(ancestor)
    return simplified_targets & ancestor_paths


def _count_canonical_non_empty_scalars(node: dict[str, object] | None) -> tuple[int, int]:
    if not isinstance(node, dict):
        return 0, 0

    node_type = str(node.get("type", "string"))
    if node_type == "object":
        total = 0
        non_empty = 0
        for child in dict(node.get("fields", {})).values():
            child_total, child_non_empty = _count_canonical_non_empty_scalars(child if isinstance(child, dict) else None)
            total += child_total
            non_empty += child_non_empty
        return total, non_empty

    if node_type == "array":
        total = 0
        non_empty = 0
        for child in list(node.get("items", [])):
            child_total, child_non_empty = _count_canonical_non_empty_scalars(child if isinstance(child, dict) else None)
            total += child_total
            non_empty += child_non_empty
        return total, non_empty

    if node_type == "null":
        return 1, 0

    value = node.get("value", "")
    text = "" if value is None else str(value).strip()
    return 1, 1 if text else 0


def _canonical_output_population_summary(content: dict[str, object]) -> dict[str, int]:
    total, non_empty = _count_canonical_non_empty_scalars(dict(content.get("root", {})))
    return {
        "total_scalar_fields": int(total),
        "non_empty_scalar_fields": int(non_empty),
    }


def _error_row(error_text: str) -> int:
    match = re.search(r"Row\s+(\d+)", error_text)
    return int(match.group(1)) if match else 999999


def _sorted_errors(errors: list[str]) -> list[str]:
    return sorted(errors, key=lambda e: (_error_row(e), e.lower()))


def _humanize_issue_text(error_text: str) -> str:
    sanitized = re.sub(r"^Row\s+\d+\s*\|\s*", "", error_text).strip()
    parts = [p.strip() for p in sanitized.split("|")]
    if len(parts) < 2:
        return sanitized

    target_part = parts[0]
    message = parts[-1]
    target = target_part.removeprefix("Target:").strip()

    root_match = re.search(r"Target root does not match spec: expected\s*(.*?),\s*got\s*(.*)", message)
    if root_match:
        return f"Use the expected target root {root_match.group(1).strip()} instead of {root_match.group(2).strip()}."

    if message == "Required target branch is missing":
        return f"Add the required target branch {target} so the output matches the spec structure."

    if message == "Unexpected target attribute not described by the spec":
        return f"Review {target} because this attribute appears in the output but is not described by the spec."

    if message == "Unexpected target node not described by the spec":
        return f"Review {target} because it appears in the output but is not described by the spec."

    if message == "Required target attribute is missing":
        return f"Add the required attribute {target} so the output matches the spec structure."

    if message == "Sibling order violation: children are not in the expected sequence":
        return f"Reorder children under {target} so they follow the expected sequence."

    if message == "Namespace mismatch: target node uses a different namespace than expected":
        return f"Use the expected namespace for {target} so structure validation can match the spec."

    if message.startswith("Choice group violation:"):
        return f"Adjust branches under {target} so the expected one-of choice rule is satisfied."

    if message.startswith("Per-parent cardinality violation under"):
        return f"Adjust repeated child counts for {target} so each parent instance satisfies the cardinality rule."

    if message == "Source exists but target is missing":
        return f"Add the missing target field {target} so it receives the source value."

    card_match = re.search(r"Cardinality violation: expected\s+([^,]+),\s*got\s*(\d+)", message)
    if card_match:
        return (
            f"Adjust {target} so the number of values matches the expected rule "
            f"({card_match.group(1)} expected, {card_match.group(2)} found)."
        )

    value_match = re.search(r"Value mismatch from source\s+([^:]+):\s*(.*?)\s*!=\s*(.*)", message)
    if value_match:
        return (
            f"Review the mapping from {value_match.group(1).strip()} to {target}: "
            "the source and target values do not match."
        )

    translated_match = re.search(r"Translated value mismatch: expected\s*(.*?),\s*got\s*(.*)", message)
    if translated_match:
        return f"Update {target} so it uses the expected mapped value."

    source_exists_match = re.search(r"Source-exists mapped mismatch: expected\s*(.*?),\s*got\s*(.*)", message)
    if source_exists_match:
        return f"Update {target} so it uses the expected value when source data exists."

    startswith_match = re.search(r"Starts-with transform mismatch: expected\s*(.*?),\s*got\s*(.*)", message)
    if startswith_match:
        return f"Update {target} so the starts-with transformation output is correct."

    startswith_append_match = re.search(
        r"Starts-with append transform mismatch: expected\s*(.*?),\s*got\s*(.*)",
        message,
    )
    if startswith_append_match:
        return f"Update {target} so the starts-with + append transformation output is correct."

    if_equals_match = re.search(r"If-equals mapping mismatch: expected\s*(.*?),\s*got\s*(.*)", message)
    if if_equals_match:
        return f"Update {target} so the conditional mapping output is correct."

    if message == "Conditional mapped target is missing":
        return f"Add {target} because it is required when the condition is met."

    date_format_match = re.search(r"Date-format mapping mismatch: expected\s*(.*?),\s*got\s*(.*)", message)
    if date_format_match:
        return f"Update {target} so it uses the expected date or time format token."

    if message == "Date-format target is missing":
        return f"Add {target} because this field should carry the required date or time format token."

    constant_match = re.search(r"Constant mismatch: expected\s*(.*?),\s*got\s*(.*)", message)
    if constant_match:
        return f"Update {target} so it uses the expected fixed value."

    if message == "Required constant target is missing":
        return f"Add {target} because this field should always contain a fixed value."

    concat_match = re.search(r"Concat mismatch: expected\s*(.*?),\s*got\s*(.*)", message)
    if concat_match:
        return (
            f"Review how {target} is being built because the combined value "
            "is not coming out as expected."
        )

    if message == "Concat target is missing":
        return f"Add {target} because this field should contain a combined value."

    field_concat_match = re.search(r"Field-concat mapping mismatch: expected\s*(.*?),\s*got\s*(.*)", message)
    if field_concat_match:
        return (
            f"Review how {target} is being built from multiple source fields: "
            "the concatenated value does not match."
        )

    if message == "Field-concat target is missing":
        return f"Add {target} because it should be populated by concatenating source fields."

    startswith_sub_match = re.search(r"Starts-with substring mismatch: expected\s*(.*?),\s*got\s*(.*)", message)
    if startswith_sub_match:
        return f"Update {target} so the starts-with substring extraction output is correct."

    if message == "Starts-with substring target is missing":
        return f"Add {target} because it should contain the extracted substring when source matches the prefix."

    char_offset_match = re.search(r"Character-offset extraction mismatch: expected\s*(.*?),\s*got\s*(.*)", message)
    if char_offset_match:
        return f"Update {target} so the character-offset extraction output is correct."

    if message == "Character-offset extraction target is missing":
        return f"Add {target} because it should contain the extracted character substring."

    length_based_match = re.search(r"Length-based mapping mismatch: expected\s*(.*?),\s*got\s*(.*)", message)
    if length_based_match:
        return f"Update {target} so the length-based mapping output is correct."

    if message == "Length-based mapped target is missing":
        return f"Add {target} because it should be populated when the length-based condition is met."

    return f"Review {target}: {message}."


def _build_top_critical_errors(error_sections: dict[str, list[str]], limit: int | None = None) -> list[str]:
    priority = [
        "root_mismatches",
        "missing_target_branches",
        "required_target_attributes_missing",
        "child_cardinality_violations",
        "choice_group_violations",
        "sibling_order_violations",
        "namespace_mismatches",
        "unexpected_target_attributes",
        "unexpected_target_nodes",
        "source_target_missing",
        "cardinality_violations",
        "value_mismatches",
        "translated_value_mismatches",
        "source_exists_mismatches",
        "startswith_transform_mismatches",
        "startswith_append_mismatches",
        "if_equals_mismatches",
        "date_format_mismatches",
        "field_concat_mismatches",
        "length_based_mismatches",
        "constant_mismatches",
        "concat_mismatches",
        "other",
    ]
    top: list[str] = []
    for key in priority:
        for err in _sorted_errors(error_sections.get(key, [])):
            top.append(err)
            if limit is not None and len(top) >= limit:
                return top
    return top


def _human_issue_breakdown(grouped_error_counts: dict[str, int]) -> list[dict[str, int | str]]:
    labels = {
        "root_mismatches": "Top section name is incorrect",
        "missing_target_branches": "Required sections are missing",
        "required_target_attributes_missing": "Required details are missing",
        "child_cardinality_violations": "Repeated child items are out of range",
        "choice_group_violations": "Either/or rules are not satisfied",
        "sibling_order_violations": "Items are in the wrong order",
        "namespace_mismatches": "Namespace format does not match",
        "unexpected_target_attributes": "Unexpected extra details",
        "unexpected_target_nodes": "Unexpected extra sections",
        "source_target_missing": "Missing fields in output",
        "cardinality_violations": "Fields with too many or too few values",
        "value_mismatches": "Source and output values do not match",
        "translated_value_mismatches": "Mapped values need correction",
        "source_exists_mismatches": "Source-exists mapping needs correction",
        "startswith_transform_mismatches": "Starts-with transformation needs correction",
        "startswith_append_mismatches": "Starts-with + append transformation needs correction",
        "if_equals_mismatches": "Conditional mapping needs correction",
        "date_format_mismatches": "Date or time format token needs correction",
        "field_concat_mismatches": "Concatenated field values need correction",
        "startswith_substring_mismatches": "Starts-with substring extraction needs correction",
        "char_offset_mismatches": "Character-offset extraction needs correction",
        "length_based_mismatches": "Length-based mapping needs correction",
        "constant_mismatches": "Fixed values need correction",
        "concat_mismatches": "Combined values need correction",
        "other": "Other items to review",
    }
    ordered_keys = [
        "root_mismatches",
        "missing_target_branches",
        "required_target_attributes_missing",
        "child_cardinality_violations",
        "choice_group_violations",
        "sibling_order_violations",
        "namespace_mismatches",
        "unexpected_target_attributes",
        "unexpected_target_nodes",
        "source_target_missing",
        "cardinality_violations",
        "value_mismatches",
        "translated_value_mismatches",
        "source_exists_mismatches",
        "startswith_transform_mismatches",
        "startswith_append_mismatches",
        "if_equals_mismatches",
        "date_format_mismatches",
        "field_concat_mismatches",
        "startswith_substring_mismatches",
        "char_offset_mismatches",
        "length_based_mismatches",
        "constant_mismatches",
        "concat_mismatches",
        "other",
    ]
    items: list[dict[str, int | str]] = []
    for key in ordered_keys:
        count = grouped_error_counts.get(key, 0)
        if count > 0:
            items.append({"issue": labels[key], "count": count})
    return items


def _detect_pattern_family(condition_text: str) -> str:
    if _extract_source_value_translation(condition_text):
        return "source_value_translation"
    if _extract_source_exists_target_constant(condition_text):
        return "source_exists_target_constant"
    if _extract_token_exists_target_mapping(condition_text):
        return "token_exists_target_mapping"
    if _extract_startswith_replace_mapping(condition_text):
        return "startswith_replace"
    if _extract_startswith_replace_append_mapping(condition_text):
        return "startswith_replace_append"
    if _extract_startswith_constant_mapping(condition_text):
        return "startswith_constant_mapping"
    if _extract_if_exists_else_map(condition_text):
        return "if_exists_else_map"
    if _extract_if_replace_map_to_target(condition_text):
        return "if_replace_map_to_target"
    if _extract_if_equals_then_map(condition_text):
        return "if_equals_then_map"
    if _extract_if_equals_chain_map(condition_text):
        return "if_equals_chain_map"
    if _extract_if_expression_chain_map(condition_text):
        return "if_expression_chain_map"
    if _extract_sequential_if_chain_map(condition_text):
        return "sequential_if_chain_map"
    if _extract_date_format_mapping(condition_text):
        return "date_format_mapping"
    if _extract_field_concat_mapping(condition_text):
        return "field_concat_mapping"
    if _extract_startswith_substring_mapping(condition_text):
        return "startswith_substring_mapping"
    if _extract_if_equals_get_substring_mapping(condition_text):
        return "if_equals_get_substring_mapping"
    if _extract_if_in_list_substring_source_mapping(condition_text):
        return "if_in_list_substring_source_mapping"
    if _extract_source_substring_date_part_mapping(condition_text):
        return "source_substring_date_part_mapping"
    if _extract_conversion_if_chain_map(condition_text):
        return "conversion_if_chain_mapping"
    if _extract_expression_map_to_target(condition_text):
        return "expression_map_to_target"
    if _extract_char_offset_mapping(condition_text):
        return "char_offset_mapping"
    if _extract_length_based_mapping(condition_text):
        return "length_based_mapping"
    return "unknown"


def _x12_bytes_to_segment_xml(raw: bytes) -> bytes:
    """Convert raw X12 EDI bytes to canonical XML addressable via /X12/TS_{id}/SEG/SEGnn XPaths.

    Transaction-set segments (between ST and SE) are wrapped in <TS_{ST01}>.
    Envelope segments (ISA, GS, GE, IEA) appear directly under <X12>.
    Elements are named {SegID}{position:02d}, e.g. B10 element 2 → B1002.
    Paths referencing GROUP_* loop qualifiers cannot be resolved from flat EDI data
    and will naturally return no match in XPath lookups (treated as not-checked).
    """
    from xml.sax.saxutils import escape as _xml_escape

    text = raw.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n").lstrip()
    if not text:
        return b'<?xml version="1.0" encoding="UTF-8"?>\n<X12/>\n'

    # Detect separators from ISA header
    # ISA uses a fixed split: elem_sep is text[3]; then split on elem_sep up to 16 times
    # to get parts[0..16] where parts[16] starts with ISA16 (1 char) then seg_term (1 char)
    elem_sep = "*"
    comp_sep = ":"
    seg_term = "~"

    if text.startswith("ISA") and len(text) > 4:
        elem_sep = text[3]
        isa_parts = text.split(elem_sep, 16)
        if len(isa_parts) == 17:
            tail = isa_parts[16]  # ":<seg_term>GS..." or ":~\nGS..."
            if len(tail) >= 1:
                comp_sep = tail[0]
            if len(tail) >= 2:
                seg_term = tail[1]

    def _split_segments(payload: str) -> list[str]:
        return [s.strip() for s in payload.split(seg_term) if s.strip()]

    def _safe_tag(name: str) -> str:
        tag = re.sub(r"[^A-Za-z0-9_]", "_", name or "UNK")
        return ("_" + tag) if tag and tag[0].isdigit() else (tag or "UNK")

    def _seg_to_xml_lines(seg_id: str, elements: list[str], indent: str) -> list[str]:
        safe_id = _safe_tag(seg_id)
        lines = [f"{indent}<{safe_id}>"]
        for idx, val in enumerate(elements, start=1):
            elem_name = f"{safe_id}{idx:02d}"
            lines.append(f"{indent}  <{elem_name}>{_xml_escape(val)}</{elem_name}>")
        lines.append(f"{indent}</{safe_id}>")
        return lines

    segments = _split_segments(text)
    root_lines: list[str] = []
    ts_lines: list[str] = []
    current_ts_tag: str | None = None

    def flush_ts() -> None:
        nonlocal current_ts_tag, ts_lines
        if current_ts_tag and ts_lines:
            root_lines.append(f"  <{current_ts_tag}>")
            root_lines.extend(ts_lines)
            root_lines.append(f"  </{current_ts_tag}>")
        current_ts_tag = None
        ts_lines = []

    for segment in segments:
        parts = segment.split(elem_sep)
        seg_id = (parts[0] or "").strip()
        if not seg_id:
            continue
        elements = [p for p in parts[1:]]

        if seg_id == "ST":
            flush_ts()
            ts_type = elements[0].lstrip("0") if elements else "UNK"
            current_ts_tag = f"TS_{ts_type or 'UNK'}"
            ts_lines.extend(_seg_to_xml_lines(seg_id, elements, "    "))
        elif seg_id == "SE":
            ts_lines.extend(_seg_to_xml_lines(seg_id, elements, "    "))
            flush_ts()
        elif current_ts_tag is not None:
            ts_lines.extend(_seg_to_xml_lines(seg_id, elements, "    "))
        else:
            root_lines.extend(_seg_to_xml_lines(seg_id, elements, "  "))

    flush_ts()
    body = "\n".join(root_lines)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<X12>\n{body}\n</X12>\n'.encode("utf-8")


def _edifact_bytes_to_segment_xml(raw: bytes) -> bytes:
    """Convert raw EDIFACT EDI bytes to canonical XML addressable via /EDIFACT/MSG_{type}/SEG/SEGnn XPaths.

    Message segments (between UNH and UNT) are wrapped in <MSG_{message_type}>.
    Envelope segments appear directly under <EDIFACT>.
    Elements are named {SegID}{position:02d}.
    """
    from xml.sax.saxutils import escape as _xml_escape

    text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        return b'<?xml version="1.0" encoding="UTF-8"?>\n<EDIFACT/>\n'

    # Defaults; override from UNA service string advice if present
    comp_sep = ":"
    elem_sep = "+"
    seg_term = "'"

    if text.startswith("UNA") and len(text) >= 9:
        comp_sep = text[3]
        elem_sep = text[4]
        seg_term = text[8]
        text = text[9:].lstrip("\r\n")

    def _split_segments(payload: str) -> list[str]:
        return [s.strip() for s in payload.split(seg_term) if s.strip()]

    def _seg_to_xml_lines(seg_id: str, elements: list[str], indent: str) -> list[str]:
        safe_id = re.sub(r"[^A-Za-z0-9_]", "_", seg_id) if seg_id else "UNK"
        if safe_id and safe_id[0].isdigit():
            safe_id = "_" + safe_id
        lines = [f"{indent}<{safe_id}>"]
        for idx, val in enumerate(elements, start=1):
            elem_name = f"{safe_id}{idx:02d}"
            # Keep composite as flat string (joined with /)
            flat_val = val.replace(comp_sep, "/") if comp_sep in val else val
            lines.append(f"{indent}  <{elem_name}>{_xml_escape(flat_val)}</{elem_name}>")
        lines.append(f"{indent}</{safe_id}>")
        return lines

    segments = _split_segments(text)

    root_lines: list[str] = []
    msg_lines: list[str] = []
    current_msg_tag: str | None = None

    def flush_msg() -> None:
        nonlocal current_msg_tag, msg_lines
        if current_msg_tag and msg_lines:
            root_lines.append(f"  <{current_msg_tag}>")
            root_lines.extend(msg_lines)
            root_lines.append(f"  </{current_msg_tag}>")
        current_msg_tag = None
        msg_lines = []

    for segment in segments:
        parts = segment.split(elem_sep)
        seg_id = parts[0].strip() if parts else ""
        if not seg_id:
            continue
        elements = [p for p in parts[1:]]

        if seg_id == "UNH":
            flush_msg()
            # UNH02 is composite: message type is first component e.g. "INVOIC:D:96A:UN"
            msg_ref = elements[1].split(comp_sep)[0] if len(elements) > 1 else "UNK"
            current_msg_tag = f"MSG_{msg_ref}"
            msg_lines.extend(_seg_to_xml_lines(seg_id, elements, "    "))
        elif seg_id == "UNT":
            msg_lines.extend(_seg_to_xml_lines(seg_id, elements, "    "))
            flush_msg()
        elif current_msg_tag is not None:
            msg_lines.extend(_seg_to_xml_lines(seg_id, elements, "    "))
        else:
            root_lines.extend(_seg_to_xml_lines(seg_id, elements, "  "))

    flush_msg()

    body = "\n".join(root_lines)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<EDIFACT>\n{body}\n</EDIFACT>\n'.encode("utf-8")


def _get_spec_layout(spec_path: str) -> str:
    """Return detected layout type for the spec ('xpath_target', 'cdm_target', or 'x12_segment').
    Falls back to 'xpath_target' if the spec cannot be read."""
    try:
        from core.spec_reader import read_mapping_table, _detect_layout
        df = read_mapping_table(spec_path)
        return _detect_layout(df)
    except Exception:
        return "xpath_target"


def _canonical_node_to_xml(tag: str, node: dict[str, object]) -> str:
    node_type = str(node.get("type", "string"))
    if node_type == "object":
        fields = dict(node.get("fields", {}))
        children = "".join(
            _canonical_node_to_xml(str(key), dict(value))
            for key, value in fields.items()
        )
        return f"<{tag}>{children}</{tag}>"

    if node_type == "array":
        items = list(node.get("items", []))
        children = "".join(_canonical_node_to_xml("item", dict(item)) for item in items)
        return f"<{tag}>{children}</{tag}>"

    if node_type == "null":
        return f"<{tag}></{tag}>"

    value = node.get("value", "")
    return f"<{tag}>{escape(str(value))}</{tag}>"


def _canonical_content_to_xml_bytes(content: dict[str, object]) -> bytes:
    root_node = dict(content.get("root", {"type": "object", "fields": {}}))
    xml_body = _canonical_node_to_xml("root", root_node)
    return ("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n" + xml_body + "\n").encode("utf-8")


def _infer_payload_format(filename: str, raw_payload: bytes) -> str:
    ext = Path(filename or "").suffix.lower()
    if ext in {".xml", ".json", ".x12", ".edifact"}:
        return ext.lstrip(".")
    if ext == ".edi":
        preview = raw_payload.decode("utf-8", errors="ignore").strip().upper()[:300]
        if preview.startswith("UNA") or "UNB+" in preview:
            return "edifact"
        if preview.startswith("ISA") or "ISA*" in preview:
            return "x12"
        raise ValueError("Unable to detect .edi payload flavor. Use .x12 or .edifact extension for clarity.")
    raise ValueError("Unsupported payload format. Use matching .xml, .json, .x12, or .edifact payloads")


def _build_rule_gap_summary(
    support_summary: dict,
    parser_diagnostics: dict,
    semantic_summary: dict,
    missing_cardinality_rules: int,
) -> dict:
    total_rules = int(support_summary.get("total_rules", 0))
    enforced = int(support_summary.get("enforced_rules", 0))
    parsed_only = int(support_summary.get("parsed_only_rules", 0))
    unsupported = int(support_summary.get("unsupported_rules", 0))

    enforceable_coverage_percent = round((enforced / total_rules) * 100, 2) if total_rules else 100.0
    semantic_coverage_percent = float(
        semantic_summary.get("coverage", {}).get("coverage_percent", 100.0)
    )

    next_action = "All parsed rules are currently covered."
    if unsupported > 0:
        next_action = (
            "Review unsupported condition wording and add deterministic pattern handlers for remaining gaps."
        )
    elif parsed_only > 0:
        next_action = (
            "Review parsed-only procedural rules and decide whether to enforce or keep as informational checks."
        )

    return {
        "total_rules": total_rules,
        "enforced_rules": enforced,
        "parsed_only_rules": parsed_only,
        "unsupported_rules": unsupported,
        "missing_cardinality_rules": int(missing_cardinality_rules),
        "enforceable_coverage_percent": enforceable_coverage_percent,
        "semantic_condition_coverage_percent": semantic_coverage_percent,
        "parser_status": parser_diagnostics.get("status", "unknown"),
        "parser_confidence": parser_diagnostics.get("confidence", "unknown"),
        "ai_review_needed": unsupported > 0,
        "next_action": next_action,
    }


def _build_mandatory_preflight_checklist(
    rules: list[dict],
    tgt_tree=None,
    tgt_ns: dict | None = None,
) -> dict:
    checklist: list[dict] = []

    for index, rule in enumerate(rules, start=1):
        target_xpath = str(rule.get("target_xpath", "") or "").strip()
        if not target_xpath:
            continue

        mo_policy = _normalize_mo(str(rule.get("m_o", "")))
        cardinality_raw = str(rule.get("cardinality", "") or "").strip()
        parsed_cardinality = _parse_cardinality(cardinality_raw)

        is_mandatory = mo_policy == "mandatory" or (
            parsed_cardinality is not None and parsed_cardinality[0] > 0
        )
        if not is_mandatory:
            continue

        present: bool | None = None
        if tgt_tree is not None and tgt_ns is not None:
            target_values = xpath_values(tgt_tree, tgt_ns, target_xpath)
            present = _has_non_empty_value(target_values) or _target_path_has_nodes(
                tgt_tree,
                tgt_ns,
                target_xpath,
            )

        checklist.append(
            {
                "row": index,
                "target_xpath": target_xpath,
                "requirement": cardinality_raw or ("M" if mo_policy == "mandatory" else "required"),
                "present": present,
            }
        )

    total = len(checklist)
    if total == 0:
        return {
            "status": "PASS",
            "total_mandatory_fields": 0,
            "present_count": 0,
            "missing_count": 0,
            "coverage_percent": 100.0,
            "missing_examples": [],
            "checklist": [],
            "note": "No mandatory target rules were detected in the parsed spec.",
        }

    unresolved = [item for item in checklist if item.get("present") is None]
    missing = [item for item in checklist if item.get("present") is False]
    present_count = total - len(missing) - len(unresolved)

    if unresolved:
        status = "NOT_EVALUATED"
        coverage_percent = 0.0
        note = "Spec-only mode: mandatory targets were listed but output presence was not evaluated."
    else:
        status = "PASS" if not missing else "FAIL"
        coverage_percent = round((present_count / total) * 100, 2)
        note = ""

    return {
        "status": status,
        "total_mandatory_fields": total,
        "present_count": present_count,
        "missing_count": len(missing),
        "coverage_percent": coverage_percent,
        "missing_examples": missing[:20],
        "checklist": checklist,
        "note": note,
    }


def _build_unsupported_suggestion_summary(skipped_rules: list[dict], limit: int = 20) -> list[dict]:
    suggestions: list[dict] = []
    for raw in skipped_rules[:limit]:
        nearest_patterns = list(raw.get("nearest_patterns", []) or [])
        top_patterns = [item for item in nearest_patterns[:3] if isinstance(item, dict)]
        suggestions.append(
            {
                "row": int(raw.get("row", 0) or 0),
                "target_xpath": str(raw.get("target_xpath", "") or ""),
                "confidence": str(raw.get("similarity_confidence", "low") or "low"),
                "rewrite": str(raw.get("suggested_canonical_rewrite", "") or ""),
                "why": str(raw.get("why_not_enforced", "") or ""),
                "top_patterns": top_patterns,
            }
        )
    return suggestions


def _source_path_looks_viable(source_xpath: str) -> bool:
    token = (source_xpath or "").strip()
    if not token:
        return False
    lowered = token.lower()
    if lowered in {
        "na",
        "n/a",
        "not available",
        "not mapped",
        "unmapped",
        "none",
        "null",
        "-",
        "tbd",
        "future use",
    }:
        return False
    return True


def _build_reverse_validation_summary(rules: list[dict]) -> dict:
    required_rules: list[dict] = []
    unmapped_required_rules: list[dict] = []

    for index, rule in enumerate(rules, start=1):
        target_xpath = str(rule.get("target_xpath", "") or "").strip()
        if not target_xpath:
            continue

        mo_policy = _normalize_mo(str(rule.get("m_o", "")))
        cardinality_raw = str(rule.get("cardinality", "") or "").strip()
        parsed_cardinality = _parse_cardinality(cardinality_raw)
        is_required = mo_policy == "mandatory" or (
            parsed_cardinality is not None and parsed_cardinality[0] > 0
        )
        if not is_required:
            continue

        source_xpath = str(rule.get("source_xpath", "") or "").strip()
        condition_text = str(rule.get("condition", "") or "").strip()
        source_viable = _source_path_looks_viable(source_xpath)
        if source_viable and _extract_instruction_only_condition(condition_text) is not None:
            source_viable = False

        entry = {
            "row": index,
            "target_xpath": target_xpath,
            "source_xpath": source_xpath,
            "requirement": cardinality_raw or ("M" if mo_policy == "mandatory" else "required"),
            "reason": "Required target has no actionable source mapping rule" if not source_viable else "",
        }
        required_rules.append(entry)
        if not source_viable:
            unmapped_required_rules.append(entry)

    required_count = len(required_rules)
    unmapped_count = len(unmapped_required_rules)
    mapped_count = required_count - unmapped_count
    coverage_percent = round((mapped_count / required_count) * 100, 2) if required_count else 100.0

    return {
        "status": "PASS" if unmapped_count == 0 else "FAIL",
        "required_rules": required_count,
        "mapped_required_rules": mapped_count,
        "unmapped_required_rules": unmapped_count,
        "coverage_percent": coverage_percent,
        "examples": unmapped_required_rules[:20],
        "note": (
            "All required target rules include a source mapping path."
            if unmapped_count == 0
            else "Some required targets have no source mapping path in the spec and should be mapped before sign-off."
        ),
    }


def _build_mapping_completeness_summary(
    mandatory_preflight: dict,
    reverse_validation_summary: dict,
) -> dict:
    preflight_status = str(mandatory_preflight.get("status", "")).upper()
    preflight_total = int(mandatory_preflight.get("total_mandatory_fields", 0))
    preflight_present = int(mandatory_preflight.get("present_count", 0))

    reverse_total = int(reverse_validation_summary.get("required_rules", 0))
    reverse_mapped = int(reverse_validation_summary.get("mapped_required_rules", 0))

    if preflight_status != "NOT_EVALUATED" and preflight_total > 0:
        basis = "output_validated"
        satisfied = preflight_present
        total = preflight_total
        note = "Score is based on mandatory targets present in the output payload."
    else:
        basis = "spec_projection"
        satisfied = reverse_mapped
        total = reverse_total
        note = "Score is based on required spec rules that include source mapping paths."

    score_percent = round((satisfied / total) * 100, 2) if total > 0 else 100.0

    if score_percent >= 95.0:
        status = "PASS"
    elif score_percent >= 80.0:
        status = "WARN"
    else:
        status = "FAIL"

    return {
        "status": status,
        "basis": basis,
        "score_percent": score_percent,
        "satisfied_mandatory_rules": satisfied,
        "total_mandatory_rules": total,
        "headline": f"Completeness: {score_percent}% ({satisfied}/{total})",
        "note": note,
    }


def _build_completion_status_summary(
    rules: list[dict],
    mandatory_preflight: dict,
    reverse_validation_summary: dict,
    tgt_tree=None,
    tgt_ns: dict | None = None,
) -> dict:
    mandatory_weight = 0.8
    optional_weight = 0.2
    mandatory_total = 0
    mandatory_completed = 0
    optional_total = 0
    optional_completed = 0
    pending_examples: list[dict[str, object]] = []

    if tgt_tree is not None and tgt_ns is not None:
        for index, rule in enumerate(rules, start=1):
            row_number = _resolve_rule_row(rule, index)
            target_xpath = str(rule.get("target_xpath", "") or "").strip()
            if not target_xpath:
                continue

            mo_policy = _normalize_mo(str(rule.get("m_o", "")))
            parsed_cardinality = _parse_cardinality(str(rule.get("cardinality", "") or "").strip())
            is_mandatory = mo_policy == "mandatory" or (
                parsed_cardinality is not None and parsed_cardinality[0] > 0
            )
            target_values = xpath_values(tgt_tree, tgt_ns, target_xpath)
            is_present = _has_non_empty_value(target_values) or _target_path_has_nodes(tgt_tree, tgt_ns, target_xpath)

            if is_mandatory:
                mandatory_total += 1
                if is_present:
                    mandatory_completed += 1
                else:
                    pending_examples.append(
                        {
                            "row": row_number,
                            "target_xpath": target_xpath,
                            "source_xpath": str(rule.get("source_xpath", "") or "").strip(),
                            "condition": str(rule.get("condition", "") or "").strip(),
                            "requirement": "mandatory",
                        }
                    )
            else:
                optional_total += 1
                if is_present:
                    optional_completed += 1
                else:
                    pending_examples.append(
                        {
                            "row": row_number,
                            "target_xpath": target_xpath,
                            "source_xpath": str(rule.get("source_xpath", "") or "").strip(),
                            "condition": str(rule.get("condition", "") or "").strip(),
                            "requirement": "optional",
                        }
                    )

        basis = "output_validated"
    else:
        mandatory_total = int(mandatory_preflight.get("total_mandatory_fields", 0))
        mandatory_completed = int(reverse_validation_summary.get("mapped_required_rules", 0))
        optional_total = 0
        optional_completed = 0
        basis = "spec_projection"

    total_lines = mandatory_total + optional_total
    completed_lines = mandatory_completed + optional_completed
    lines_left = max(total_lines - completed_lines, 0)
    overall_completion_percent = round((completed_lines / total_lines) * 100, 2) if total_lines > 0 else 100.0
    mandatory_coverage = (mandatory_completed / mandatory_total) if mandatory_total > 0 else 1.0
    optional_coverage = (optional_completed / optional_total) if optional_total > 0 else 1.0
    effective_weight = 0.0
    weighted_score = 0.0
    if mandatory_total > 0:
        weighted_score += mandatory_coverage * mandatory_weight
        effective_weight += mandatory_weight
    if optional_total > 0:
        weighted_score += optional_coverage * optional_weight
        effective_weight += optional_weight
    if effective_weight > 0:
        weighted_completion_percent = round((weighted_score / effective_weight) * 100, 2)
    else:
        weighted_completion_percent = 100.0
    completion_status = "COMPLETE" if lines_left == 0 else "IN_PROGRESS"

    return {
        "overall_completion_percent": overall_completion_percent,
        "weighted_completion_percent": weighted_completion_percent,
        "mandatory_lines_completed": mandatory_completed,
        "mandatory_lines_total": mandatory_total,
        "optional_lines_completed": optional_completed,
        "optional_lines_total": optional_total,
        "lines_completed": completed_lines,
        "lines_total": total_lines,
        "lines_left": lines_left,
        "mandatory_lines_left": max(mandatory_total - mandatory_completed, 0),
        "optional_lines_left": max(optional_total - optional_completed, 0),
        "basis": basis,
        "weighting": {
            "mandatory_weight": mandatory_weight,
            "optional_weight": optional_weight,
        },
        "completion_status": completion_status,
        "pending_examples": pending_examples[:50],
    }


def _is_condition_supported_for_dry_run(condition_text: str) -> tuple[bool, bool]:
    """Return (enforceable, parsed_only) classification for dry-run coverage mode."""
    if not condition_text:
        return True, False

    enforceable_extractors = (
        _is_if_source_map_rule,
        _is_direct_map_rule,
        _is_semantic_direct_map_comment,
        _extract_source_value_translation,
        _extract_source_exists_target_constant,
        _extract_token_exists_target_mapping,
        _extract_source_is_not_null_mapping,
        _extract_hardcode_literal,
        _extract_if_equals_then_map,
        _extract_if_equals_chain_map,
        _extract_if_expression_chain_map,
        _extract_multi_condition_and_map,
        _extract_sequential_if_chain_map,
        _extract_startswith_replace_mapping,
        _extract_startswith_replace_append_mapping,
        _extract_startswith_substring_mapping,
        _extract_startswith_constant_mapping,
        _extract_if_exists_else_map,
        _extract_if_replace_map_to_target,
        _extract_if_equals_get_substring_mapping,
        _extract_if_in_list_substring_source_mapping,
        _extract_source_substring_date_part_mapping,
        _extract_char_offset_mapping,
        _extract_length_based_mapping,
        _extract_date_format_mapping,
        _extract_field_concat_mapping,
        _extract_concatenate_fields,
        _extract_conversion_if_chain_map,
        _extract_expression_map_to_target,
    )
    for extractor in enforceable_extractors:
        if extractor(condition_text):
            return True, False

    if _detect_pattern_family(condition_text) != "unknown":
        return True, False

    # Accept common guard + hardcode form used by real partner specs.
    if re.search(
        r"\bif\b.+\bthen\b\s*(?:hardcode|map)\s*['\"][^'\"]+['\"]\s*(?:to\s+target|as\s+target|target\s+as)",
        condition_text,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        return True, False

    if _extract_guard_only_condition(condition_text):
        return False, True
    if _extract_instruction_only_condition(condition_text):
        return False, True
    if _extract_compute_statement(condition_text):
        return False, True

    return False, False


def validate_spec_coverage(spec_path: str) -> dict:
    """Stage 10 dry-run mode: assess parser and rule-condition coverage without payload files."""
    df = read_mapping_table(spec_path)
    rules = extract_rules(df)
    parser_diagnostics = get_parser_diagnostics(df)
    semantic_profile = _get_semantic_profile(spec_path)
    confidence_thresholds = _confidence_guardrail_thresholds(dict(semantic_profile.get("thresholds", {})))

    support_summary = {
        "total_rules": len(rules),
        "enforced_rules": 0,
        "parsed_only_rules": 0,
        "unsupported_rules": 0,
        "abstained_rules": 0,
        "condition_based_rules": 0,
        "unsupported_rule_suggestions_provided": 0,
        "high_similarity_unsupported_rules": 0,
        "medium_similarity_unsupported_rules": 0,
        "low_similarity_unsupported_rules": 0,
        "ambiguous_unsupported_rules": 0,
        "auto_promote_candidate_rules": 0,
        "field_alias_normalized_rules": 0,
    }

    skipped_rules: list[dict] = []
    rule_decisions: list[dict] = []
    semantic_unsupported_conditions: Counter[str] = Counter()
    semantic_suggested_families: Counter[str] = Counter()

    missing_cardinality_rules = sum(1 for rule in rules if not str(rule.get("cardinality", "")).strip())
    mandatory_preflight = _build_mandatory_preflight_checklist(rules)
    reverse_validation_summary = _build_reverse_validation_summary(rules)
    mapping_completeness = _build_mapping_completeness_summary(
        mandatory_preflight,
        reverse_validation_summary,
    )
    unsupported_suggestions = _build_unsupported_suggestion_summary(skipped_rules)

    for index, rule in enumerate(rules, start=1):
        cond_text_raw = str(rule.get("condition", "") or "").strip()
        target_xpath = str(rule.get("target_xpath", "") or "")
        source_xpath = str(rule.get("source_xpath", "") or "")

        if _is_empty_condition_placeholder(cond_text_raw):
            support_summary["enforced_rules"] += 1
            rule_decisions.append(
                {
                    "row": index,
                    "target_xpath": target_xpath,
                    "source_xpath": source_xpath,
                    "status": "enforced",
                    "confidence": _estimate_rule_confidence("enforced", False, True, 0.0),
                    "family": "direct_map",
                    "reason": "Direct mapping rule without condition",
                }
            )
            continue

        support_summary["condition_based_rules"] += 1

        if _is_label_like_condition(cond_text_raw):
            support_summary["parsed_only_rules"] += 1
            rule_decisions.append(
                {
                    "row": index,
                    "target_xpath": target_xpath,
                    "source_xpath": source_xpath,
                    "status": "parsed_only",
                    "confidence": _estimate_rule_confidence("parsed_only", False, False, 0.0),
                    "family": "manual_review",
                    "reason": "Condition text is a label-like note without a source path",
                }
            )
            continue

        raw_direct_map_hint = bool(source_xpath) and (
            _is_if_source_map_rule(cond_text_raw)
            or
            _is_direct_map_rule(cond_text_raw)
            or _is_semantic_direct_map_comment(cond_text_raw, semantic_profile=semantic_profile)
            or bool(re.fullmatch(r"\s*direct\s+mapping\s*", cond_text_raw, flags=re.IGNORECASE))
        )

        cond_text, cond_transform_trace = _canonicalize_semantic_condition_with_trace(
            cond_text_raw,
            semantic_profile=semantic_profile,
        )
        semantic_parts = _extract_semantic_parts(
            cond_text,
            dict(semantic_profile.get("field_aliases", {})),
        )

        enforceable, parsed_only = _is_condition_supported_for_dry_run(cond_text)
        if enforceable:
            support_summary["enforced_rules"] += 1
            detected = _detect_pattern_family(cond_text)
            rule_decisions.append(
                {
                    "row": index,
                    "target_xpath": target_xpath,
                    "source_xpath": source_xpath,
                    "status": "enforced",
                    "confidence": _estimate_rule_confidence("enforced", True, False, 0.0),
                    "family": detected if detected != "unknown" else "direct_map",
                    "reason": (
                        "Condition text implies direct source-to-target mapping"
                        if raw_direct_map_hint and detected == "unknown"
                        else "Condition pattern is supported in deterministic mode"
                    ),
                }
            )
            continue

        if parsed_only:
            support_summary["parsed_only_rules"] += 1
            rule_decisions.append(
                {
                    "row": index,
                    "target_xpath": target_xpath,
                    "source_xpath": source_xpath,
                    "status": "parsed_only",
                    "confidence": _estimate_rule_confidence("parsed_only", True, False, 0.0),
                    "family": "manual_review",
                    "reason": "Condition recognized as procedural/instruction-only",
                }
            )
            continue

        suggested_patterns = _suggest_pattern_families(
            cond_text,
            top_n=3,
            semantic_profile=semantic_profile,
        )
        top_suggestion = suggested_patterns[0] if suggested_patterns else None
        ambiguity = _analyze_semantic_ambiguity(
            suggested_patterns,
            dict(semantic_profile.get("thresholds", {})),
        )
        why_not_enforced = _build_semantic_explanation(top_suggestion, ambiguity, semantic_parts)
        suggested_rewrite = _build_suggested_canonical_rewrite(
            str(top_suggestion["family"]) if top_suggestion else "",
            semantic_parts,
            ambiguity,
        )

        if top_suggestion:
            support_summary["unsupported_rule_suggestions_provided"] += 1
            semantic_suggested_families[str(top_suggestion["family"])] += 1
            if top_suggestion["confidence"] == "high":
                support_summary["high_similarity_unsupported_rules"] += 1
            elif top_suggestion["confidence"] == "medium":
                support_summary["medium_similarity_unsupported_rules"] += 1
            else:
                support_summary["low_similarity_unsupported_rules"] += 1
        if ambiguity.get("is_ambiguous"):
            support_summary["ambiguous_unsupported_rules"] += 1

        support_summary["unsupported_rules"] += 1
        semantic_unsupported_conditions[cond_text or cond_text_raw] += 1
        skipped_rules.append(
            {
                "row": str(index),
                "target_xpath": target_xpath,
                "reason": "Unsupported condition pattern",
                "condition": cond_text_raw,
                "normalized_condition": cond_text,
                "applied_transforms": cond_transform_trace,
                "detected_pattern": _detect_pattern_family(cond_text),
                "nearest_family": top_suggestion["family"] if top_suggestion else "",
                "similarity_score": float(top_suggestion["score"]) if top_suggestion else 0.0,
                "similarity_confidence": top_suggestion["confidence"] if top_suggestion else "low",
                "nearest_patterns": suggested_patterns,
                "why_not_enforced": why_not_enforced,
                "try_normalized_form": cond_text,
                "semantic_parts": semantic_parts,
                "ambiguous_families": list(ambiguity.get("candidate_families", [])),
                "ambiguity_reason": ambiguity.get("reason", ""),
                "suggested_canonical_rewrite": suggested_rewrite,
                "future_auto_promotion_eligible": False,
                "semantic_profile": semantic_profile.get("profile_key", "generic"),
                "workbook_family": semantic_profile.get("profile_key", "generic"),
            }
        )
        rule_decisions.append(
            {
                "row": index,
                "target_xpath": target_xpath,
                "source_xpath": source_xpath,
                "status": "unsupported",
                "confidence": _estimate_rule_confidence(
                    "unsupported",
                    True,
                    False,
                    float(top_suggestion["score"]) if top_suggestion else 0.0,
                ),
                "family": top_suggestion["family"] if top_suggestion else "",
                "reason": why_not_enforced,
            }
        )

    for decision in rule_decisions:
        row = int(decision.get("row", 0) or 0)
        has_condition = False
        source_xpath = str(decision.get("source_xpath", "") or "")
        target_xpath = str(decision.get("target_xpath", "") or "")
        semantic_action = "unknown"
        parser_confidence = "unknown"
        if row > 0 and row <= len(rules):
            row_rule = rules[row - 1]
            raw_condition = str(row_rule.get("condition", "") or "").strip()
            has_condition = bool(raw_condition)
            parser_confidence = str(row_rule.get("parser_confidence", "unknown") or "unknown")
            normalized_condition = _canonicalize_semantic_condition_with_trace(
                raw_condition,
                semantic_profile=semantic_profile,
            )[0]
            semantic_parts = _extract_semantic_parts(
                normalized_condition,
                dict(semantic_profile.get("field_aliases", {})),
            )
            semantic_action = str(semantic_parts.get("action", "unknown"))

        original_status = str(decision.get("status", "parsed_only"))
        ai_conflicts = _ai_review_conflicts(
            status=original_status,
            has_condition=has_condition,
            source_xpath=source_xpath,
            family=str(decision.get("family", "") or ""),
            semantic_action=semantic_action,
            row_error_count=0,
            enforce_source_path_guardrail=False,
        )
        if ai_conflicts:
            decision["status"] = "parsed_only"
            decision["reason"] = (
                "AI review demoted enforcement: " + "; ".join(ai_conflicts[:2])
            )
            _rebalance_support_summary_status(support_summary, original_status, "parsed_only")

        evidence = _build_ai_review_evidence(
            status=str(decision.get("status", "parsed_only")),
            has_condition=has_condition,
            source_xpath=source_xpath,
            target_xpath=str(decision.get("target_xpath", "") or ""),
            family=str(decision.get("family", "") or ""),
            semantic_action=semantic_action,
            similarity_score=float(decision.get("confidence", 0.0) or 0.0),
            row_error_count=0,
        )
        decision["ai_review"] = {
            "stage": "review_only",
            "conflicts": ai_conflicts,
            "evidence": evidence,
        }
        decision["confidence"] = float(evidence["score"])
        decision["reason_code"] = _reason_code(str(decision.get("reason", "")))
        decision["remediation_hint"] = _decision_fix_hint(
            str(decision.get("status", "")),
            str(decision.get("reason", "")),
            str(decision.get("family", "")),
        )

        guardrails = _build_pre_fail_guardrails(
            status=str(decision.get("status", "")),
            has_condition=has_condition,
            source_xpath=source_xpath,
            target_xpath=target_xpath,
            parser_confidence=parser_confidence,
            decision_confidence=float(decision.get("confidence", 0.0) or 0.0),
        )
        decision["guardrail_checks"] = guardrails["checks"]
        decision["guardrail_failed_checks"] = guardrails["failed_checks"]
        confidence_policy = _confidence_band_and_policy(float(decision.get("confidence", 0.0) or 0.0), confidence_thresholds)
        decision["confidence_band"] = confidence_policy["confidence_band"]
        decision["apply_policy"] = confidence_policy["apply_policy"]
        decision["row_error_count"] = 0
        outcome = _decision_outcome_from_evidence(
            status=str(decision.get("status", "")),
            row_error_count=0,
            decision_confidence=float(decision.get("confidence", 0.0) or 0.0),
            parser_confidence=parser_confidence,
            requires_abstain=bool(guardrails["requires_abstain"]),
            thresholds=confidence_thresholds,
        )
        decision["decision_outcome"] = outcome

    outcome_counts = Counter(str(d.get("decision_outcome", _DECISION_OUTCOME_FAIL)) for d in rule_decisions)
    support_summary["abstained_rules"] = int(outcome_counts.get(_DECISION_OUTCOME_ABSTAIN, 0))

    ai_review_summary = {
        "demoted_rules": sum(
            1
            for decision in rule_decisions
            if str(decision.get("reason", "")).startswith("AI review demoted enforcement:")
        ),
        "low_evidence_rules": sum(
            1
            for decision in rule_decisions
            if float(decision.get("confidence", 0.0) or 0.0) < 0.55
        ),
        "reviewed_rules": len(rule_decisions),
    }
    ai_review_summary["decision_outcomes"] = {
        "pass": int(outcome_counts.get(_DECISION_OUTCOME_PASS, 0)),
        "abstain": int(outcome_counts.get(_DECISION_OUTCOME_ABSTAIN, 0)),
        "fail": int(outcome_counts.get(_DECISION_OUTCOME_FAIL, 0)),
    }
    ai_review_summary["confidence_policy"] = {
        "high": confidence_thresholds["high"],
        "medium": confidence_thresholds["medium"],
    }

    agent_action_plan = _build_agent_action_plan(
        rule_decisions=rule_decisions,
        error_diagnostics=[],
        thresholds=confidence_thresholds,
    )
    parser_validator_calibration = _build_parser_validator_calibration(
        rule_decisions=rule_decisions,
        thresholds=confidence_thresholds,
    )

    total_condition_rules = int(support_summary.get("condition_based_rules", 0))
    semantic_supported_rules = max(total_condition_rules - int(support_summary.get("unsupported_rules", 0)), 0)
    semantic_coverage_percent = round((semantic_supported_rules / total_condition_rules) * 100, 2) if total_condition_rules else 100.0
    semantic_summary = {
        "profile": semantic_profile.get("profile_key", "generic"),
        "workbook_family": semantic_profile.get("profile_key", "generic"),
        "config_source": semantic_profile.get("config_source", "built-in"),
        "thresholds": dict(semantic_profile.get("thresholds", {})),
        "coverage": {
            "total_condition_rules": total_condition_rules,
            "supported_condition_rules": semantic_supported_rules,
            "unsupported_condition_rules": int(support_summary.get("unsupported_rules", 0)),
            "coverage_percent": semantic_coverage_percent,
        },
        "ambiguity": {
            "ambiguous_unsupported_rules": int(support_summary.get("ambiguous_unsupported_rules", 0)),
            "auto_promote_candidate_rules": int(support_summary.get("auto_promote_candidate_rules", 0)),
        },
        "field_aliases": {
            "normalized_rules": int(support_summary.get("field_alias_normalized_rules", 0)),
        },
        "top_unsupported_conditions": [
            {"condition": condition, "count": count}
            for condition, count in semantic_unsupported_conditions.most_common(10)
        ],
        "promote_to_generic_candidates": [
            {"condition": condition, "count": count}
            for condition, count in semantic_unsupported_conditions.most_common(10)
            if count >= 2
        ],
        "top_suggested_families": [
            {"family": family, "count": count}
            for family, count in semantic_suggested_families.most_common(10)
        ],
    }

    rule_gap_summary = _build_rule_gap_summary(
        support_summary,
        parser_diagnostics,
        semantic_summary,
        missing_cardinality_rules,
    )

    status = "PASS" if support_summary["unsupported_rules"] == 0 else "PASS_WITH_WARNINGS"
    issue_breakdown: list[dict[str, int | str]] = []
    if support_summary.get("unsupported_rules", 0) > 0:
        issue_breakdown.append(
            {"issue": "Conditions needing semantic review", "count": int(support_summary.get("unsupported_rules", 0))}
        )
    if int(reverse_validation_summary.get("unmapped_required_rules", 0)) > 0:
        issue_breakdown.append(
            {
                "issue": "Required targets missing source mapping rules",
                "count": int(reverse_validation_summary.get("unmapped_required_rules", 0)),
            }
        )

    what_to_fix_first = [
        f"Row {item.get('row')}: {item.get('suggested_canonical_rewrite') or 'Rewrite condition to a supported deterministic pattern.'}"
        for item in skipped_rules[:20]
    ]
    if unsupported_suggestions:
        what_to_fix_first = [
            (
                f"Row {item.get('row')}: {item.get('rewrite') or 'Rewrite condition to a supported deterministic pattern.'} "
                f"(confidence: {item.get('confidence')}; why: {item.get('why') or 'condition does not match deterministic family'})"
            )
            for item in unsupported_suggestions
        ]
    if int(reverse_validation_summary.get("unmapped_required_rules", 0)) > 0:
        what_to_fix_first.extend(
            [
                f"Row {item.get('row')}: Add a source mapping path for required target {item.get('target_xpath')}."
                for item in reverse_validation_summary.get("examples", [])[:10]
            ]
        )

    return {
        "validation_fingerprint": _build_validation_fingerprint("spec_coverage"),
        "summary": {
            "status": status,
            "error_count": 0,
            "grouped_error_counts": {},
            "top_critical_errors": [],
            "parser_status": parser_diagnostics.get("status", "unknown"),
            "parser_confidence": parser_diagnostics.get("confidence", "unknown"),
        },
        "human_summary": {
            "headline": f"Spec coverage ready: {semantic_coverage_percent}% of condition rules are supported",
            "what_to_fix_first": what_to_fix_first,
            "issue_breakdown": issue_breakdown,
            "checked_rules": len(rules),
            "skipped_rules": len(skipped_rules),
            "semantic_summary": {
                "headline": (
                    "All condition rules in this spec match supported deterministic patterns"
                    if int(support_summary.get("unsupported_rules", 0)) == 0
                    else f"{support_summary['unsupported_rules']} condition rule(s) still need manual review"
                ),
                "coverage_percent": semantic_coverage_percent,
                "top_suggested_families": semantic_summary["top_suggested_families"][:3],
            },
            "rule_gap_summary": rule_gap_summary,
            "ai_review_summary": ai_review_summary,
            "mandatory_preflight": mandatory_preflight,
            "reverse_validation_summary": reverse_validation_summary,
            "mapping_completeness": mapping_completeness,
            "unsupported_rule_suggestions": unsupported_suggestions,
        },
        "valid": True,
        "validation_mode": "spec_coverage",
        "strict_would_fail": False,
        "checked_rules": len(rules),
        "warnings": [
            "Spec coverage mode: payload files were not required; this report focuses on parser and semantic coverage only."
        ],
        "warning_taxonomy": _build_warning_taxonomy(
            [
                "Spec coverage mode: payload files were not required; this report focuses on parser and semantic coverage only."
            ]
        ),
        "rule_stats": {},
        "structure_summary": None,
        "semantic_summary": semantic_summary,
        "rule_gap_summary": rule_gap_summary,
        "mandatory_preflight": mandatory_preflight,
        "reverse_validation_summary": reverse_validation_summary,
        "mapping_completeness": mapping_completeness,
        "unsupported_rule_suggestions": unsupported_suggestions,
        "structure_findings": [],
        "parser_diagnostics": parser_diagnostics,
        "rule_support_summary": support_summary,
        "ai_review_summary": ai_review_summary,
        "agent_action_plan": agent_action_plan,
        "parser_validator_calibration": parser_validator_calibration,
        "rule_decisions": rule_decisions,
        "error_diagnostics": [],
        "skipped_rules": skipped_rules,
        "error_sections": {},
        "top_critical_errors": [],
        "error_count": 0,
        "inputs": {
            "spec_path": spec_path,
            "input_xml_path": "",
            "output_xml_path": "",
        },
        "errors": [],
    }


def validate_mapping_from_payload_bytes(
    spec_path: str,
    input_payload: bytes,
    input_filename: str,
    output_payload: bytes,
    output_filename: str,
    validation_mode: str = "strict",
) -> dict:
    """Validate output payload against spec rules using input payload as source.

    Supported combinations:
    - XML + XML (passthrough)
    - JSON + JSON (adapter bridge)
    - X12 + X12 (adapter bridge, homogeneous)
    - EDIFACT + EDIFACT (adapter bridge, homogeneous)
    - X12 input + JSON/XML output (cross-format, requires x12_segment spec layout)
    - EDIFACT input + JSON/XML output (cross-format, requires x12_segment spec layout)
    """
    _EDI_FORMATS = {"x12", "edifact"}
    _OUTPUT_FORMATS = {"json", "xml"}

    input_format = _infer_payload_format(input_filename, input_payload)
    output_format = _infer_payload_format(output_filename, output_payload)

    # Cross-format: EDI input + JSON/XML output.
    # Only valid when spec has x12_segment layout (specs that map EDI→JSON/XML).
    cross_format = (
        input_format in _EDI_FORMATS
        and output_format in _OUTPUT_FORMATS
        and _get_spec_layout(spec_path) == "x12_segment"
    )

    if input_format != output_format and not cross_format:
        raise ValueError(
            f"Input ({input_format}) and output ({output_format}) payload formats must match, "
            "or supply an X12/EDIFACT input with a JSON/XML output for a cross-format spec."
        )

    # ── Pure XML passthrough ──────────────────────────────────────────────────
    if input_format == "xml" and output_format == "xml":
        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            input_path = tmp_path / "input_payload.xml"
            output_path = tmp_path / "output_payload.xml"
            input_path.write_bytes(input_payload)
            output_path.write_bytes(output_payload)
            return validate_mapping(
                spec_path,
                str(input_path),
                str(output_path),
                validation_mode=validation_mode,
            )

    # ── Cross-format: EDI input → JSON/XML output ────────────────────────────
    if cross_format:
        output_population_summary = None
        if input_format == "x12":
            bridged_input_xml = _x12_bytes_to_segment_xml(input_payload)
        else:  # edifact
            bridged_input_xml = _edifact_bytes_to_segment_xml(input_payload)

        if output_format == "xml":
            bridged_output_xml = output_payload  # already XML
        else:  # json
            from core.adapters import build_default_registry
            registry = build_default_registry()
            output_doc = registry.get("json").parse(raw_payload=output_payload, source_name=output_filename)
            bridged_output_xml = _canonical_content_to_xml_bytes(output_doc.content)
            output_population_summary = _canonical_output_population_summary(output_doc.content)

        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            input_path = tmp_path / f"input.{input_format}.canonical.xml"
            output_path = tmp_path / f"output.{output_format}.bridge.xml"
            input_path.write_bytes(bridged_input_xml)
            output_path.write_bytes(bridged_output_xml)
            result = validate_mapping(
                spec_path,
                str(input_path),
                str(output_path),
                validation_mode=validation_mode,
            )

        warnings = list(result.get("warnings", []))
        warnings.append(
            f"Cross-format bridge: {input_format.upper()} input was normalized to segment-path XML; "
            f"{output_format.upper()} output was normalized for XPath validation. "
            "Loop-aware GROUP_* fallback is applied for XPath resolution when needed."
        )
        if output_population_summary is not None and output_population_summary["non_empty_scalar_fields"] == 0:
            warnings.append(
                "Output generation check: target JSON contains no populated scalar fields; "
                "verify mapping output generation/population logic."
            )
        result["warnings"] = warnings
        result["warning_taxonomy"] = _build_warning_taxonomy(warnings)
        result["adapter_pipeline"] = {
            "enabled": True,
            "mode": "cross_format",
            "input_format": input_format,
            "output_format": output_format,
            "input_source_name": input_filename,
            "output_source_name": output_filename,
        }
        result["inputs"]["input_payload_name"] = input_filename
        result["inputs"]["output_payload_name"] = output_filename
        if output_population_summary is not None:
            result["output_population"] = output_population_summary
        return result

    # ── Homogeneous non-XML (JSON/X12/EDIFACT + same format) ─────────────────
    from core.adapters import build_default_registry

    registry = build_default_registry()
    input_adapter = registry.get(input_format)
    output_adapter = registry.get(output_format)
    input_doc = input_adapter.parse(raw_payload=input_payload, source_name=input_filename)
    output_doc = output_adapter.parse(raw_payload=output_payload, source_name=output_filename)
    output_population_summary = _canonical_output_population_summary(output_doc.content) if output_format == "json" else None

    if input_format == "x12":
        bridged_input_xml = _x12_bytes_to_segment_xml(input_payload)
        bridged_output_xml = _x12_bytes_to_segment_xml(output_payload)
    elif input_format == "edifact":
        bridged_input_xml = _edifact_bytes_to_segment_xml(input_payload)
        bridged_output_xml = _edifact_bytes_to_segment_xml(output_payload)
    else:
        bridged_input_xml = _canonical_content_to_xml_bytes(input_doc.content)
        bridged_output_xml = _canonical_content_to_xml_bytes(output_doc.content)

    with TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        input_path = tmp_path / f"input.{input_format}.bridge.xml"
        output_path = tmp_path / f"output.{output_format}.bridge.xml"
        input_path.write_bytes(bridged_input_xml)
        output_path.write_bytes(bridged_output_xml)
        result = validate_mapping(
            spec_path,
            str(input_path),
            str(output_path),
            validation_mode=validation_mode,
        )

    warnings = list(result.get("warnings", []))
    warnings.append(
        f"Adapter pipeline mode: {input_format.upper()} payloads were normalized via the Stage 9 adapter bridge."
    )
    if output_population_summary is not None and output_population_summary["non_empty_scalar_fields"] == 0:
        warnings.append(
            "Output generation check: target JSON contains no populated scalar fields; "
            "verify mapping output generation/population logic."
        )
    result["warnings"] = warnings
    result["warning_taxonomy"] = _build_warning_taxonomy(warnings)
    result["adapter_pipeline"] = {
        "enabled": True,
        "mode": "homogeneous",
        "input_format": input_doc.source_format,
        "output_format": output_doc.source_format,
        "input_source_name": input_doc.source_name,
        "output_source_name": output_doc.source_name,
        "input_diagnostics": {
            "status": input_doc.diagnostics.status,
            "warnings": list(input_doc.diagnostics.warnings),
            "info": list(input_doc.diagnostics.info),
        },
        "output_diagnostics": {
            "status": output_doc.diagnostics.status,
            "warnings": list(output_doc.diagnostics.warnings),
            "info": list(output_doc.diagnostics.info),
        },
    }
    result["inputs"]["input_payload_name"] = input_filename
    result["inputs"]["output_payload_name"] = output_filename
    if output_population_summary is not None:
        result["output_population"] = output_population_summary
    return result


def validate_mapping(
    spec_path: str,
    input_xml_path: str,
    output_xml_path: str,
    validation_mode: str = "strict",
) -> dict:
    """Validate output XML against mapping rules and source XML."""
    mode = (validation_mode or "strict").strip().lower()
    if mode not in {"strict", "lenient", "structure_strict", "completion_status"}:
        raise ValueError("validation_mode must be one of 'strict', 'lenient', 'structure_strict', or 'completion_status'")

    df = read_mapping_table(spec_path)
    rules = extract_rules(df)
    parser_diagnostics = get_parser_diagnostics(df)
    semantic_profile = _get_semantic_profile(spec_path)
    confidence_thresholds = _confidence_guardrail_thresholds(dict(semantic_profile.get("thresholds", {})))
    validator_exception_entries = _normalized_validator_exception_entries()

    src_tree, src_ns = parse_xml(input_xml_path)
    tgt_tree, tgt_ns = parse_xml(output_xml_path)
    src_root_name = _local_name(src_tree.getroot().tag)
    tgt_root_name = _local_name(tgt_tree.getroot().tag)

    errors: list[str] = []
    checked_rules = 0
    support_summary = {
        "total_rules": len(rules),
        "enforced_rules": 0,
        "parsed_only_rules": 0,
        "unsupported_rules": 0,
        "abstained_rules": 0,
        "stage_8_5_canonicalized_rules": 0,
        "target_path_heuristic_rules": 0,
        "condition_based_rules": 0,
        "translated_condition_rules": 0,
        "source_exists_condition_rules": 0,
        "token_exists_condition_rules": 0,
        "source_is_not_null_rules": 0,
        "startswith_replace_rules": 0,
        "startswith_replace_append_rules": 0,
        "startswith_constant_rules": 0,
        "if_exists_else_map_rules": 0,
        "if_replace_map_rules": 0,
        "if_equals_map_rules": 0,
        "if_equals_chain_rules": 0,
        "if_expression_chain_rules": 0,
        "multi_condition_and_rules": 0,
        "guard_only_condition_rules": 0,
        "instruction_only_rules": 0,
        "expression_map_to_target_rules": 0,
        "compute_statement_rules": 0,
        "date_format_rules": 0,
        "field_concat_rules": 0,
        "direct_map_rules": 0,
        "hardcode_literal_rules": 0,
        "concatenate_rules": 0,
        "startswith_substring_rules": 0,
        "if_equals_get_substring_rules": 0,
        "if_in_list_substring_rules": 0,
        "date_part_substring_rules": 0,
        "conversion_if_chain_rules": 0,
        "char_offset_rules": 0,
        "length_based_rules": 0,
        "condition_transform_applied_rules": 0,
        "unsupported_rule_suggestions_provided": 0,
        "high_similarity_unsupported_rules": 0,
        "medium_similarity_unsupported_rules": 0,
        "low_similarity_unsupported_rules": 0,
        "auto_promoted_rules": 0,
        "ambiguous_unsupported_rules": 0,
        "auto_promote_candidate_rules": 0,
        "field_alias_normalized_rules": 0,
        "shadow_mode_rules": 0,
    }
    rule_stats = {
        "root_mismatches": 0,
        "missing_target_branches": 0,
        "unexpected_target_attributes": 0,
        "unexpected_target_nodes": 0,
        "cardinality_violations": 0,
        "source_target_missing": 0,
        "value_mismatches": 0,
        "translated_value_mismatches": 0,
        "source_exists_mismatches": 0,
        "startswith_transform_mismatches": 0,
        "startswith_append_mismatches": 0,
        "if_equals_mismatches": 0,
        "date_format_mismatches": 0,
        "constant_mismatches": 0,
        "concat_mismatches": 0,
        "field_concat_mismatches": 0,
        "startswith_substring_mismatches": 0,
        "char_offset_mismatches": 0,
        "length_based_mismatches": 0,
        "child_cardinality_violations": 0,
        "required_target_attributes_missing": 0,
        "sibling_order_violations": 0,
        "choice_group_violations": 0,
        "namespace_mismatches": 0,
    }
    error_sections = {
        "root_mismatches": [],
        "missing_target_branches": [],
        "unexpected_target_attributes": [],
        "unexpected_target_nodes": [],
        "cardinality_violations": [],
        "source_target_missing": [],
        "value_mismatches": [],
        "translated_value_mismatches": [],
        "source_exists_mismatches": [],
        "startswith_transform_mismatches": [],
        "startswith_append_mismatches": [],
        "if_equals_mismatches": [],
        "date_format_mismatches": [],
        "constant_mismatches": [],
        "concat_mismatches": [],
        "field_concat_mismatches": [],
        "startswith_substring_mismatches": [],
        "char_offset_mismatches": [],
        "length_based_mismatches": [],
        "child_cardinality_violations": [],
        "required_target_attributes_missing": [],
        "sibling_order_violations": [],
        "choice_group_violations": [],
        "namespace_mismatches": [],
        "other": [],
    }
    skipped_rules: list[dict[str, object]] = []
    semantic_unsupported_conditions: Counter[str] = Counter()
    semantic_suggested_families: Counter[str] = Counter()
    structure_required_paths: set[str] = set()
    structure_allowed_paths: set[str] = set()
    structure_allowed_attribute_paths: set[str] = set()
    structure_repeat_findings: list[str] = []
    structure_findings: list[dict[str, object]] = []
    error_diagnostics: list[dict[str, object]] = []
    rule_decisions: list[dict[str, object]] = []
    row_error_counts: Counter[int] = Counter()
    structure_parent_cardinality_rules: list[dict] = []
    structure_required_attribute_rules: list[dict] = []
    shadow_rule_families = _get_shadow_rule_families()
    token_resolution_stats: dict[str, int] = {
        "base_source": 0,
        "absolute_xpath": 0,
        "explicit_path": 0,
        "inferred_sibling": 0,
        "resolved_value": 0,
        "unresolved_value": 0,
        "unresolved_xpath": 0,
        "empty_token": 0,
    }
    global _ACTIVE_TOKEN_RESOLUTION_STATS
    _ACTIVE_TOKEN_RESOLUTION_STATS = token_resolution_stats
    structure_spec_exceptions = _get_structure_spec_exceptions(spec_path)
    normalized_rule_targets = {
        _simplify_xpath(_normalize_xpath(rule.get("target_xpath", ""), tgt_root_name))
        for rule in rules
        if _simplify_xpath(_normalize_xpath(rule.get("target_xpath", ""), tgt_root_name))
    }
    container_target_paths = _collect_container_target_paths(normalized_rule_targets)

    def _looks_like_supported_target(target_path: str) -> bool:
        return bool(target_path) and target_path.startswith("/")

    def _add_error(
        section: str,
        row: int,
        target_xpath: str,
        message: str,
        details: dict[str, object] | None = None,
    ) -> None:
        formatted = _format_error(row, target_xpath, message)
        errors.append(formatted)
        error_sections.setdefault(section, []).append(formatted)
        diag = {
            "section": section,
            "row": row,
            "target_xpath": target_xpath,
            "message": message,
            "error_text": formatted,
        }
        if details:
            diag.update(details)
        error_diagnostics.append(diag)
        if row > 0:
            row_error_counts[row] += 1
        if section in _STRUCTURE_SECTION_KEYS:
            finding = {
                "category": section,
                "row": row,
                "target_xpath": target_xpath,
                "message": message,
                "error_text": formatted,
            }
            if details:
                finding.update(details)
            structure_findings.append(finding)

    for i, rule in enumerate(rules, start=1):
        i = _resolve_rule_row(rule, i)
        tgt = _normalize_xpath(rule["target_xpath"], tgt_root_name)
        src = _normalize_xpath(rule["source_xpath"], src_root_name)
        cond_text_raw = _resolve_condition_from_rule_ir(rule)
        cond_text, cond_transform_trace = _canonicalize_semantic_condition_with_trace(
            cond_text_raw,
            semantic_profile=semantic_profile,
        )
        semantic_parts = _extract_semantic_parts(
            cond_text,
            dict(semantic_profile.get("field_aliases", {})),
        )
        if cond_transform_trace:
            support_summary["condition_transform_applied_rules"] += 1
        if cond_text_raw and cond_text and cond_text != _normalize_condition_text(cond_text_raw):
            support_summary["stage_8_5_canonicalized_rules"] += 1
        if semantic_parts.get("field_alias_normalizations"):
            support_summary["field_alias_normalized_rules"] += 1
        cond = " ".join(cond_text.lower().split())
        card = rule["cardinality"]
        mo_policy = _normalize_mo(str(rule.get("m_o", "")))

        checked_rules += 1
        decision_status = "enforced"
        decision_reason = "Rule was evaluated with supported parser paths"
        decision_similarity_score = 0.0
        decision_nearest_family = ""
        if cond_text.strip():
            support_summary["condition_based_rules"] += 1
        if rule["target_xpath"] and not _looks_like_supported_target(rule["target_xpath"]):
            support_summary["target_path_heuristic_rules"] += 1

        rule_supported_for_enforcement = _looks_like_supported_target(rule["target_xpath"])
        simplified_target_path = _simplify_xpath(tgt)
        simplified_attribute_path = _simplify_xpath(tgt, include_attributes=True)
        if simplified_target_path:
            for branch_path in _path_ancestors(simplified_target_path):
                structure_allowed_paths.add(branch_path)
        if "/@" in simplified_attribute_path:
            structure_allowed_attribute_paths.add(simplified_attribute_path)

        src_vals = xpath_values(src_tree, src_ns, src) if src else []
        tgt_vals = xpath_values(tgt_tree, tgt_ns, tgt)
        target_has_nodes = _target_path_has_nodes(tgt_tree, tgt_ns, tgt)
        target_elements = _elements_for_simplified_path(tgt_tree, simplified_target_path)
        target_is_container = (
            simplified_target_path in container_target_paths
            or any(any(isinstance(child.tag, str) for child in element) for element in target_elements)
        )

        parsed_cardinality = _parse_cardinality(card)
        condition_applies = _structure_condition_applies(cond_text, src_vals)
        if rule_supported_for_enforcement and simplified_target_path and _required_target_path(rule, tgt) and condition_applies:
            structure_required_paths.add(simplified_target_path)

        if parsed_cardinality is not None and condition_applies:
            min_count, max_count = parsed_cardinality
            target_count = len(tgt_vals)
            if target_count < min_count or (max_count is not None and target_count > max_count):
                rule_stats["cardinality_violations"] += 1
                _add_error(
                    "cardinality_violations",
                    i,
                    tgt,
                    f"Cardinality violation: expected {card}, got {target_count}",
                )
                if _is_repeat_count_structure_rule(
                    simplified_target_path,
                    simplified_attribute_path,
                    min_count,
                    max_count,
                    target_count,
                ):
                    structure_repeat_findings.append(
                        _format_error(i, tgt, f"Repeat count violation: expected {card}, got {target_count}")
                    )
                    structure_findings.append(
                        {
                            "category": "repeat_count_violations",
                            "row": i,
                            "target_xpath": tgt,
                            "message": "Repeat count violation",
                            "expected": card,
                            "actual": target_count,
                            "error_text": _format_error(i, tgt, f"Repeat count violation: expected {card}, got {target_count}"),
                        }
                    )

            if (
                rule_supported_for_enforcement
                and simplified_target_path
                and min_count > 0
                and "/@" not in simplified_attribute_path
            ):
                parent_path = simplified_target_path.rsplit("/", 1)[0]
                child_name = simplified_target_path.rsplit("/", 1)[-1]
                structure_parent_cardinality_rules.append(
                    {
                        "row": i,
                        "target_xpath": tgt,
                        "parent_path": parent_path,
                        "child_name": child_name,
                        "min_count": min_count,
                        "max_count": max_count,
                    }
                )

        if rule_supported_for_enforcement and "/@" in simplified_attribute_path and condition_applies:
            parsed_attribute_cardinality = _parse_cardinality(card)
            requires_attribute = (
                (parsed_attribute_cardinality is not None and parsed_attribute_cardinality[0] > 0)
                or mo_policy == "mandatory"
            )
            if requires_attribute:
                attribute_parent_path, attribute_name = simplified_attribute_path.rsplit("/@", 1)
                structure_required_attribute_rules.append(
                    {
                        "row": i,
                        "target_xpath": tgt,
                        "parent_path": attribute_parent_path,
                        "attribute_name": attribute_name,
                    }
                )

        handled_condition = False
        guard_only_condition_recognized = False

        # Extract all conditions early to check for compute statements
        expected = _extract_constant_expected(cond_text)
        concat_expected = _concat_expected(cond_text, src_vals)
        translation = _extract_source_value_translation(cond_text)
        source_exists_constant = _extract_source_exists_target_constant(cond_text)
        token_exists_mapping = _extract_token_exists_target_mapping(cond_text)
        source_is_not_null_mapping = _extract_source_is_not_null_mapping(cond_text)
        compute_statement = _extract_compute_statement(cond_text)
        guard_only_condition = _extract_guard_only_condition(cond_text)
        instruction_only_condition = _extract_instruction_only_condition(cond_text)
        expression_map_to_target = _extract_expression_map_to_target(cond_text)
        is_if_source_rule = _is_if_source_map_rule(cond_text)
        is_direct_map = _is_direct_map_rule(cond_text)
        is_semantic_direct_map_comment = bool(src) and _is_semantic_direct_map_comment(
            cond_text,
            semantic_profile=semantic_profile,
        )
        explicit_no_mapping_instruction = bool(
            re.match(r"^\s*no\s+mapping\b", cond_text or "", flags=re.IGNORECASE)
        )
        
        # Check for compute statements early - they're procedural, not mapping rules
        if compute_statement is not None:
            support_summary["compute_statement_rules"] += 1
            checked_rules += 1
            continue  # Skip validation - compute statements are not enforceable as mappings

        if guard_only_condition is not None:
            support_summary["guard_only_condition_rules"] += 1
            handled_condition = True
            guard_only_condition_recognized = True

        instruction_only_effective = bool(
            instruction_only_condition is not None
            and (
                explicit_no_mapping_instruction
                or not ((is_direct_map and bool(src)) or is_semantic_direct_map_comment)
            )
        )
        if instruction_only_effective:
            support_summary["instruction_only_rules"] += 1
            handled_condition = True
            guard_only_condition_recognized = True

        guard_only_condition_met = False
        guard_only_expected = None
        if guard_only_condition is not None and src:
            guard_only_condition_met = _evaluate_condition_expr(
                guard_only_condition["expr"],
                src,
                src_tree,
                src_ns,
                src_root_name,
            )
            if guard_only_condition_met:
                guard_only_expected = _first_non_empty_value(src_vals)

        expression_map_to_target_condition_met = False
        expression_map_to_target_expected: str | None = None
        if expression_map_to_target is not None:
            support_summary["expression_map_to_target_rules"] += 1
            if _evaluate_boolean_expr(
                expression_map_to_target["expr"],
                src,
                src_tree,
                src_ns,
                src_root_name,
            ):
                expression_map_to_target_condition_met = True
                expression_map_to_target_expected = _first_non_empty_value(src_vals)

        is_direct_mapping_rule = bool(src) and (
            not cond_text.strip()
            or is_if_source_rule
            or is_direct_map
            or is_semantic_direct_map_comment
        )

        if is_if_source_rule:
            handled_condition = True

        if is_direct_map:
            handled_condition = True
            support_summary["direct_map_rules"] += 1

        src_has_value = _has_non_empty_value(src_vals)
        tgt_has_scalar_value = _has_non_empty_value(tgt_vals)
        tgt_has_value = tgt_has_scalar_value or (target_is_container and target_has_nodes)

        startswith_replace = _extract_startswith_replace_mapping(cond_text)
        startswith_replace_append = _extract_startswith_replace_append_mapping(cond_text)
        startswith_constant = _extract_startswith_constant_mapping(cond_text)
        if_exists_else_map = _extract_if_exists_else_map(cond_text)
        if_replace_map = _extract_if_replace_map_to_target(cond_text)
        if_equals_map = _extract_if_equals_then_map(cond_text)
        if_equals_chain_map = _extract_if_equals_chain_map(cond_text)
        if_expression_chain_map = _extract_if_expression_chain_map(cond_text)
        sequential_if_chain_map = _extract_sequential_if_chain_map(cond_text)
        multi_condition_and_map = _extract_multi_condition_and_map(cond_text)
        date_format_mapping = _extract_date_format_mapping(cond_text)
        field_concat_mapping = _extract_field_concat_mapping(cond_text)
        startswith_substring = _extract_startswith_substring_mapping(cond_text)
        if_equals_get_substring = _extract_if_equals_get_substring_mapping(cond_text)
        if_in_list_substring = _extract_if_in_list_substring_source_mapping(cond_text)
        source_date_part_substring = _extract_source_substring_date_part_mapping(cond_text)
        conversion_if_chain_map = _extract_conversion_if_chain_map(cond_text)
        char_offset_mapping = _extract_char_offset_mapping(cond_text)
        hardcode_literal = _extract_hardcode_literal(cond_text)
        concatenate_mapping = _extract_concatenate_fields(cond_text)
        length_based_mapping = None if date_format_mapping is not None else _extract_length_based_mapping(cond_text)
        translated_expected = None
        translated_match = None
        if translation is not None:
            support_summary["translated_condition_rules"] += 1
            source_first = _first_non_empty_value(src_vals)
            if source_first:
                for clause in translation["clauses"]:
                    if source_first == clause["source"]:
                        translated_expected = clause["target"]
                        translated_match = clause
                        break
                if translated_expected is None and translation["else_maps_source"]:
                    translated_expected = source_first
                    translated_match = {"source": "else", "target": source_first}
        if source_exists_constant is not None:
            support_summary["source_exists_condition_rules"] += 1

        token_exists_condition_met = False
        token_exists_expected = None
        if token_exists_mapping is not None:
            support_summary["token_exists_condition_rules"] += 1
            token_val = _resolve_source_token_value(
                src,
                token_exists_mapping["token"],
                src_tree,
                src_ns,
                src_root_name,
            )
            if token_val:
                token_exists_condition_met = True
                if token_exists_mapping.get("target_from_source"):
                    token_exists_expected = _first_non_empty_value(src_vals)
                else:
                    token_exists_expected = _resolve_condition_target_value(
                        src,
                        token_exists_mapping["target_literal"],
                        token_exists_mapping["target_token"],
                        src_tree,
                        src_ns,
                        src_root_name,
                    )

        startswith_expected = None
        if startswith_replace is not None:
            support_summary["startswith_replace_rules"] += 1
            source_first = _first_non_empty_value(src_vals)
            if source_first and source_first.startswith(startswith_replace["prefix"]):
                startswith_expected = source_first.replace(
                    startswith_replace["prefix"],
                    startswith_replace["replace_to"],
                    1,
                )

        startswith_constant_condition_met = False
        startswith_constant_expected = None
        if startswith_constant is not None:
            support_summary["startswith_constant_rules"] += 1
            source_first = _first_non_empty_value(src_vals)
            if source_first and source_first.startswith(startswith_constant["prefix"]):
                startswith_constant_condition_met = True
                startswith_constant_expected = startswith_constant["target_literal"]

        source_is_not_null_condition_met = False
        source_is_not_null_expected = None
        if source_is_not_null_mapping is not None:
            support_summary["source_is_not_null_rules"] += 1
            source_first = _first_non_empty_value(src_vals)
            if source_first:  # Source is not null
                source_is_not_null_condition_met = True
                if source_is_not_null_mapping["action_type"] == "hardcode":
                    source_is_not_null_expected = source_is_not_null_mapping["value"]
                elif source_is_not_null_mapping["action_type"] == "map":
                    source_is_not_null_expected = source_is_not_null_mapping["target_literal"]
                elif source_is_not_null_mapping["action_type"] == "map_source":
                    source_is_not_null_expected = source_first

        if_exists_else_condition_met = False
        if_exists_else_expected = None
        if if_exists_else_map is not None:
            support_summary["if_exists_else_map_rules"] += 1
            expr = if_exists_else_map["expr"]
            expr_ok = _evaluate_condition_expr(expr, src, src_tree, src_ns, src_root_name)
            if not expr_ok and re.fullmatch(r"[^\s]+", expr or ""):
                expr_ok = bool(_resolve_source_token_value(src, expr, src_tree, src_ns, src_root_name))

            if expr_ok:
                if_exists_else_condition_met = True
                if if_exists_else_map.get("true_target_from_source"):
                    if_exists_else_expected = _first_non_empty_value(src_vals)
                else:
                    if_exists_else_expected = _resolve_condition_target_value(
                        src,
                        if_exists_else_map["true_target_literal"],
                        if_exists_else_map["true_target_token"],
                        src_tree,
                        src_ns,
                        src_root_name,
                    )
            else:
                if_exists_else_condition_met = True
                if if_exists_else_map.get("false_target_from_source"):
                    if_exists_else_expected = _first_non_empty_value(src_vals)
                else:
                    if_exists_else_expected = _resolve_condition_target_value(
                        src,
                        if_exists_else_map["false_target_literal"],
                        if_exists_else_map["false_target_token"],
                        src_tree,
                        src_ns,
                        src_root_name,
                    )

        if_replace_condition_met = False
        if_replace_expected = None
        if if_replace_map is not None:
            support_summary["if_replace_map_rules"] += 1
            lhs_actual = _resolve_source_token_value(
                src,
                if_replace_map["lhs_token"],
                src_tree,
                src_ns,
                src_root_name,
            )
            op = if_replace_map.get("operator", "=")
            cmp_value = if_replace_map.get("compare_value", "")
            lhs_value = lhs_actual or ""
            clause_ok = False
            if op in {"=", "=="}:
                clause_ok = lhs_value == cmp_value
            elif op in {"!=", "<>"}:
                clause_ok = lhs_value != cmp_value
            if clause_ok:
                if_replace_condition_met = True
                source_first = _first_non_empty_value(src_vals)
                if source_first:
                    if_replace_expected = source_first.replace(
                        if_replace_map["replace_from"],
                        if_replace_map["replace_to"],
                    )

        startswith_append_expected = None
        if startswith_replace_append is not None:
            support_summary["startswith_replace_append_rules"] += 1
            source_first = _first_non_empty_value(src_vals)
            if source_first and source_first.startswith(startswith_replace_append["prefix"]):
                transformed = source_first.replace(
                    startswith_replace_append["prefix"],
                    startswith_replace_append["replace_to"],
                    1,
                )

                append_value = None
                if startswith_replace_append["append_literal"] is not None:
                    append_value = startswith_replace_append["append_literal"]
                else:
                    sibling_xpath = _infer_sibling_xpath(src, startswith_replace_append["append_field"])
                    if sibling_xpath:
                        sibling_vals = xpath_values(src_tree, src_ns, sibling_xpath)
                        append_value = _first_non_empty_value(sibling_vals)

                if append_value is not None:
                    startswith_append_expected = f"{transformed}{append_value}"

        if_equals_condition_met = False
        if_equals_expected = None
        if if_equals_map is not None:
            support_summary["if_equals_map_rules"] += 1
            lhs_actual = _resolve_source_token_value(
                src,
                if_equals_map["lhs_token"],
                src_tree,
                src_ns,
                src_root_name,
            )
            op = if_equals_map.get("operator", "=")
            cmp_value = if_equals_map.get("compare_value", "")
            lhs_value = lhs_actual or ""
            clause_ok = False
            if op in {"=", "=="}:
                clause_ok = lhs_value == cmp_value
            elif op in {"!=", "<>"}:
                clause_ok = lhs_value != cmp_value

            if clause_ok:
                if_equals_condition_met = True
                if if_equals_map.get("target_from_source"):
                    if_equals_expected = _first_non_empty_value(src_vals)
                elif if_equals_map["target_literal"] is not None:
                    if_equals_expected = if_equals_map["target_literal"]
                elif if_equals_map["target_token"]:
                    if_equals_expected = _resolve_source_token_value(
                        src,
                        if_equals_map["target_token"],
                        src_tree,
                        src_ns,
                        src_root_name,
                    )

        if_equals_chain_condition_met = False
        if_equals_chain_expected = None
        if if_equals_chain_map is not None:
            support_summary["if_equals_chain_rules"] += 1
            matched_clause = None
            for clause in if_equals_chain_map["clauses"]:
                lhs_actual = _resolve_source_token_value(
                    src,
                    clause["lhs_token"],
                    src_tree,
                    src_ns,
                    src_root_name,
                )
                op = clause.get("operator", "=")
                cmp_value = clause.get("compare_value", "")
                lhs_value = lhs_actual or ""
                clause_ok = False
                if op in {"=", "=="}:
                    clause_ok = lhs_value == cmp_value
                elif op in {"!=", "<>"}:
                    clause_ok = lhs_value != cmp_value
                if clause_ok:
                    matched_clause = clause
                    break

            if matched_clause is not None:
                if_equals_chain_condition_met = True
                if matched_clause.get("target_from_source"):
                    if_equals_chain_expected = _first_non_empty_value(src_vals)
                else:
                    if_equals_chain_expected = _resolve_condition_target_value(
                        src,
                        matched_clause["target_literal"],
                        matched_clause["target_token"],
                        src_tree,
                        src_ns,
                        src_root_name,
                    )
            elif if_equals_chain_map["else_map"] is not None:
                if_equals_chain_condition_met = True
                if if_equals_chain_map["else_map"].get("target_from_source"):
                    if_equals_chain_expected = _first_non_empty_value(src_vals)
                else:
                    if_equals_chain_expected = _resolve_condition_target_value(
                        src,
                        if_equals_chain_map["else_map"]["target_literal"],
                        if_equals_chain_map["else_map"]["target_token"],
                        src_tree,
                        src_ns,
                        src_root_name,
                    )

        if_expression_chain_condition_met = False
        if_expression_chain_expected = None
        if if_expression_chain_map is not None:
            support_summary["if_expression_chain_rules"] += 1
            matched_clause = None
            for clause in if_expression_chain_map["clauses"]:
                if _evaluate_boolean_expr(clause["expr"], src, src_tree, src_ns, src_root_name):
                    matched_clause = clause
                    break
            if matched_clause is not None:
                if_expression_chain_condition_met = True
                if_expression_chain_expected = _resolve_condition_target_value(
                    src,
                    matched_clause["target_literal"],
                    matched_clause["target_token"],
                    src_tree,
                    src_ns,
                    src_root_name,
                )
            elif if_expression_chain_map["else_map"] is not None:
                if_expression_chain_condition_met = True
                if_expression_chain_expected = _resolve_condition_target_value(
                    src,
                    if_expression_chain_map["else_map"]["target_literal"],
                    if_expression_chain_map["else_map"]["target_token"],
                    src_tree,
                    src_ns,
                    src_root_name,
                )

        conversion_if_chain_condition_met = False
        conversion_if_chain_expected = None
        if conversion_if_chain_map is not None:
            support_summary["conversion_if_chain_rules"] += 1
            outer_ok = True
            if conversion_if_chain_map.get("outer_exists_token"):
                outer_val = _resolve_source_token_value(
                    src,
                    conversion_if_chain_map["outer_exists_token"],
                    src_tree,
                    src_ns,
                    src_root_name,
                )
                outer_ok = bool(outer_val)

            if outer_ok:
                matched_clause = None
                for clause in conversion_if_chain_map["clauses"]:
                    lhs_actual = _resolve_source_token_value(
                        src,
                        clause["lhs_token"],
                        src_tree,
                        src_ns,
                        src_root_name,
                    )
                    op = clause.get("operator", "=")
                    cmp_value = clause.get("compare_value", "")
                    actual_value = lhs_actual or ""
                    clause_ok = False
                    if op in {"=", "=="}:
                        clause_ok = actual_value == cmp_value
                    elif op in {"!=", "<>"}:
                        clause_ok = actual_value != cmp_value
                    elif op == "startswith":
                        clause_ok = actual_value.startswith(cmp_value)
                    if clause_ok:
                        matched_clause = clause
                        break

                if matched_clause is not None:
                    conversion_if_chain_condition_met = True
                    conversion_if_chain_expected = _resolve_condition_target_value(
                        src,
                        matched_clause["target_literal"],
                        matched_clause["target_token"],
                        src_tree,
                        src_ns,
                        src_root_name,
                    )
                elif conversion_if_chain_map["else_map"] is not None:
                    conversion_if_chain_condition_met = True
                    conversion_if_chain_expected = _resolve_condition_target_value(
                        src,
                        conversion_if_chain_map["else_map"]["target_literal"],
                        conversion_if_chain_map["else_map"]["target_token"],
                        src_tree,
                        src_ns,
                        src_root_name,
                    )

        multi_condition_and_condition_met = False
        multi_condition_and_expected = None
        if multi_condition_and_map is not None:
            support_summary["multi_condition_and_rules"] += 1
            all_conditions_met = True
            for condition in multi_condition_and_map["conditions"]:
                if condition["type"] == "equals":
                    token_value = _resolve_source_token_value(
                        src,
                        condition["token"],
                        src_tree,
                        src_ns,
                        src_root_name,
                    )
                    if token_value != condition["value"]:
                        all_conditions_met = False
                        break
                elif condition["type"] == "not_equals":
                    token_value = _resolve_source_token_value(
                        src,
                        condition["token"],
                        src_tree,
                        src_ns,
                        src_root_name,
                    )
                    if token_value == condition["value"]:
                        all_conditions_met = False
                        break
                elif condition["type"] == "exists":
                    token_value = _resolve_source_token_value(
                        src,
                        condition["token"],
                        src_tree,
                        src_ns,
                        src_root_name,
                    )
                    if not token_value:
                        all_conditions_met = False
                        break
            
            if all_conditions_met:
                multi_condition_and_condition_met = True
                target_tokens = multi_condition_and_map.get("target_tokens") or []
                if target_tokens:
                    parts: list[str] = []
                    all_parts_resolved = True
                    for tok in target_tokens:
                        if tok.get("kind") == "literal":
                            parts.append(tok.get("value", ""))
                            continue
                        token_value = _resolve_source_token_value(
                            src,
                            tok.get("value", ""),
                            src_tree,
                            src_ns,
                            src_root_name,
                        )
                        if token_value is None:
                            all_parts_resolved = False
                            break
                        parts.append(token_value)
                    if all_parts_resolved:
                        multi_condition_and_expected = "".join(parts)
                elif multi_condition_and_map.get("action_type") == "map_source":
                    multi_condition_and_expected = _first_non_empty_value(src_vals)
                else:
                    multi_condition_and_expected = _resolve_condition_target_value(
                        src,
                        multi_condition_and_map["target_literal"],
                        multi_condition_and_map["target_token"],
                        src_tree,
                        src_ns,
                        src_root_name,
                    )

        sequential_if_chain_condition_met = False
        sequential_if_chain_expected = None
        if sequential_if_chain_map is not None:
            support_summary["if_expression_chain_rules"] += 1
            matched_clause = None
            for clause in sequential_if_chain_map["clauses"]:
                if _evaluate_condition_expr(clause["expr"], src, src_tree, src_ns, src_root_name):
                    matched_clause = clause
                    break
            if matched_clause is not None:
                sequential_if_chain_condition_met = True
                sequential_if_chain_expected = _resolve_condition_target_value(
                    src,
                    matched_clause["target_literal"],
                    matched_clause["target_token"],
                    src_tree,
                    src_ns,
                    src_root_name,
                )

        date_format_condition_met = False
        date_format_expected = None
        if date_format_mapping is not None:
            support_summary["date_format_rules"] += 1
            guard_ok = _evaluate_optional_guard_expr(
                date_format_mapping.get("guard_expr"),
                src,
                src_tree,
                src_ns,
                src_root_name,
            )
            if guard_ok:
                base_source_value = ""
                if date_format_mapping.get("base_source"):
                    base_source_value = _resolve_source_token_value(
                        src,
                        date_format_mapping["base_source"],
                        src_tree,
                        src_ns,
                        src_root_name,
                    )
                if not date_format_mapping.get("base_source") or base_source_value:
                    date_format_condition_met = True
                    date_format_expected = date_format_mapping.get("base_token")
                    time_source = date_format_mapping.get("time_source")
                    if time_source and date_format_mapping.get("length_map"):
                        time_value = _resolve_source_token_value(
                            src,
                            time_source,
                            src_tree,
                            src_ns,
                            src_root_name,
                        )
                        append_token = date_format_mapping["length_map"].get(len(time_value or ""))
                        if append_token:
                            if date_format_expected:
                                date_format_expected = f"{date_format_expected}{append_token}"
                            else:
                                date_format_expected = append_token

        field_concat_condition_met = False
        field_concat_expected: str | None = None
        if field_concat_mapping is not None:
            support_summary["field_concat_rules"] += 1
            parts: list[str] = []
            all_resolved = True
            for tok in field_concat_mapping["tokens"]:
                if tok["kind"] == "literal":
                    parts.append(tok["value"])
                else:
                    val = _resolve_source_token_value(src, tok["value"], src_tree, src_ns, src_root_name)
                    if val is None:
                        all_resolved = False
                        break
                    parts.append(val)
            if all_resolved:
                field_concat_condition_met = True
                field_concat_expected = "".join(parts)

        startswith_substring_condition_met = False
        startswith_substring_expected: str | None = None
        if startswith_substring is not None:
            support_summary["startswith_substring_rules"] += 1
            src_first = _first_non_empty_value(src_vals)
            if src_first and src_first.startswith(startswith_substring["prefix"]):
                sliced = src_first[startswith_substring["skip_chars"]:]
                append_field = startswith_substring.get("append_field")
                if append_field:
                    append_val = _resolve_source_token_value(src, append_field, src_tree, src_ns, src_root_name) or ""
                    sliced = sliced + append_val
                startswith_substring_condition_met = True
                startswith_substring_expected = sliced

        if_equals_get_substring_condition_met = False
        if_equals_get_substring_expected: str | None = None
        if if_equals_get_substring is not None:
            support_summary["if_equals_get_substring_rules"] += 1
            lhs_value = _resolve_source_token_value(
                src,
                if_equals_get_substring["lhs_token"],
                src_tree,
                src_ns,
                src_root_name,
            )
            if lhs_value == if_equals_get_substring["equals_value"]:
                base_source_value = _resolve_source_token_value(
                    src,
                    if_equals_get_substring["source_field"],
                    src_tree,
                    src_ns,
                    src_root_name,
                )
                if base_source_value:
                    sliced = base_source_value[if_equals_get_substring["skip_chars"] :]
                    append_field = if_equals_get_substring.get("append_field")
                    if append_field:
                        append_val = _resolve_source_token_value(
                            src,
                            append_field,
                            src_tree,
                            src_ns,
                            src_root_name,
                        ) or ""
                        sliced = f"{sliced}{append_val}"
                    if_equals_get_substring_condition_met = True
                    if_equals_get_substring_expected = sliced

        if_in_list_substring_condition_met = False
        if_in_list_substring_expected: str | None = None
        if if_in_list_substring is not None:
            support_summary["if_in_list_substring_rules"] += 1
            lhs_value = _resolve_source_token_value(
                src,
                if_in_list_substring["lhs_token"],
                src_tree,
                src_ns,
                src_root_name,
            )
            if lhs_value in set(if_in_list_substring["values"]):
                source_first = _first_non_empty_value(src_vals)
                if source_first:
                    start = if_in_list_substring["start_offset"]
                    length = if_in_list_substring["length"]
                    if_in_list_substring_condition_met = True
                    if_in_list_substring_expected = source_first[start : start + length]

        source_date_part_substring_condition_met = False
        source_date_part_substring_expected: str | None = None
        if source_date_part_substring is not None:
            support_summary["date_part_substring_rules"] += 1
            source_first = _first_non_empty_value(src_vals)
            if source_first:
                source_date_part_substring_condition_met = True
                source_date_part_substring_expected = _extract_date_part_value(
                    source_first,
                    source_date_part_substring["part"],
                    tgt,
                )

        char_offset_condition_met = False
        char_offset_expected: str | None = None
        if char_offset_mapping is not None:
            support_summary["char_offset_rules"] += 1
            src_first = _first_non_empty_value(src_vals)
            if src_first:
                start = char_offset_mapping["start_offset"]
                length = char_offset_mapping["length"]
                sliced = src_first[start : start + length]
                char_offset_condition_met = True
                char_offset_expected = sliced

        hardcode_condition_met = False
        hardcode_expected: str | None = None
        if hardcode_literal is not None:
            support_summary["hardcode_literal_rules"] += 1
            hardcode_condition_met = True
            hardcode_expected = hardcode_literal

        concatenate_condition_met = False
        concatenate_expected: str | None = None
        if concatenate_mapping is not None:
            support_summary["concatenate_rules"] += 1
            parts: list[str] = []
            all_resolved = True
            for part in concatenate_mapping["parts"]:
                if part["kind"] == "literal":
                    parts.append(part["value"])
                elif part["kind"] == "xpath":
                    vals = xpath_values(src_tree, src_ns, part["value"])
                    val = _first_non_empty_value(vals)
                    if val is None:
                        all_resolved = False
                        break
                    parts.append(val)
                elif part["kind"] == "token":
                    val = _resolve_source_token_value(src, part["value"], src_tree, src_ns, src_root_name)
                    if val is None:
                        all_resolved = False
                        break
                    parts.append(val)
            if all_resolved:
                concatenate_condition_met = True
                concatenate_expected = "".join(parts)

        length_based_condition_met = False
        length_based_expected: str | None = None
        if length_based_mapping is not None:
            support_summary["length_based_rules"] += 1
            if _evaluate_optional_guard_expr(
                length_based_mapping.get("outer_guard_expr"),
                src,
                src_tree,
                src_ns,
                src_root_name,
            ):
                matched_clause = None
                for clause in length_based_mapping["clauses"]:
                    actual_value = _resolve_source_token_value(
                        src,
                        clause["token"],
                        src_tree,
                        src_ns,
                        src_root_name,
                    )
                    if _length_compare(len(actual_value or ""), clause["operator"], clause["threshold"]):
                        matched_clause = clause
                        break

                if matched_clause is not None:
                    length_based_condition_met = True
                    length_based_expected = _resolve_length_map_action(
                        src,
                        matched_clause["action"],
                        src_tree,
                        src_ns,
                        src_root_name,
                    )
                elif length_based_mapping["else_action"] is not None:
                    length_based_condition_met = True
                    length_based_expected = _resolve_length_map_action(
                        src,
                        length_based_mapping["else_action"],
                        src_tree,
                        src_ns,
                        src_root_name,
                    )

        family_signals = [
            ("guard_only", guard_only_condition is not None),
            ("instruction_only", instruction_only_effective),
            ("expression_map_to_target", expression_map_to_target is not None),
            ("translation", translation is not None),
            ("source_exists_constant", source_exists_constant is not None),
            ("token_exists", token_exists_mapping is not None),
            ("source_is_not_null", source_is_not_null_mapping is not None),
            ("startswith_replace", startswith_replace is not None),
            ("startswith_replace_append", startswith_replace_append is not None),
            ("startswith_constant", startswith_constant is not None),
            ("if_exists_else", if_exists_else_map is not None),
            ("if_replace", if_replace_map is not None),
            ("if_equals", if_equals_map is not None),
            ("if_equals_chain", if_equals_chain_map is not None),
            ("if_expression_chain", if_expression_chain_map is not None),
            ("sequential_if_chain", sequential_if_chain_map is not None),
            ("multi_condition_and", multi_condition_and_map is not None),
            ("date_format", date_format_mapping is not None),
            ("field_concat", field_concat_mapping is not None),
            ("startswith_substring", startswith_substring is not None),
            ("if_equals_get_substring", if_equals_get_substring is not None),
            ("if_in_list_substring", if_in_list_substring is not None),
            ("source_date_part_substring", source_date_part_substring is not None),
            ("conversion_if_chain", conversion_if_chain_map is not None),
            ("char_offset", char_offset_mapping is not None),
            ("hardcode", hardcode_literal is not None),
            ("concatenate", concatenate_mapping is not None),
            ("length_based", length_based_mapping is not None),
        ]
        primary_family = next((name for name, present in family_signals if present), "")
        shadow_mode_for_rule = bool(primary_family and primary_family in shadow_rule_families)
        if shadow_mode_for_rule:
            support_summary["shadow_mode_rules"] += 1
            support_summary["parsed_only_rules"] += 1
            for branch_path in _parsed_only_parent_branches(simplified_target_path):
                structure_required_paths.add(branch_path)
            rule_decisions.append(
                {
                    "row": i,
                    "target_xpath": tgt,
                    "source_xpath": src,
                    "status": "parsed_only",
                    "confidence": 0.5,
                    "family": primary_family,
                    "reason": f"Shadow mode guardrail active for family '{primary_family}'",
                }
            )
            continue

        # M/O enforcement:
        applicable_rule = (
            src_has_value
            or expected is not None
            or concat_expected is not None
            or translated_expected is not None
            or (source_exists_constant is not None and src_has_value)
            or (token_exists_condition_met and _is_actionable_expected(token_exists_expected))
            or (source_is_not_null_condition_met and _is_actionable_expected(source_is_not_null_expected))
            or startswith_expected is not None
            or (startswith_constant_condition_met and _is_actionable_expected(startswith_constant_expected))
            or (if_exists_else_condition_met and _is_actionable_expected(if_exists_else_expected))
            or (if_replace_condition_met and _is_actionable_expected(if_replace_expected))
            or startswith_append_expected is not None
            or (if_equals_condition_met and _is_actionable_expected(if_equals_expected))
            or (if_equals_chain_condition_met and _is_actionable_expected(if_equals_chain_expected))
            or (if_expression_chain_condition_met and _is_actionable_expected(if_expression_chain_expected))
            or (conversion_if_chain_condition_met and _is_actionable_expected(conversion_if_chain_expected))
            or (expression_map_to_target_condition_met and _is_actionable_expected(expression_map_to_target_expected))
            or (guard_only_condition_met and _is_actionable_expected(guard_only_expected))
            or (sequential_if_chain_condition_met and _is_actionable_expected(sequential_if_chain_expected))
            or (multi_condition_and_condition_met and _is_actionable_expected(multi_condition_and_expected))
            or (date_format_condition_met and _is_actionable_expected(date_format_expected))
            or (field_concat_condition_met and _is_actionable_expected(field_concat_expected))
            or (hardcode_condition_met and _is_actionable_expected(hardcode_expected))
            or (concatenate_condition_met and _is_actionable_expected(concatenate_expected))
            or (startswith_substring_condition_met and _is_actionable_expected(startswith_substring_expected))
            or (if_equals_get_substring_condition_met and _is_actionable_expected(if_equals_get_substring_expected))
            or (if_in_list_substring_condition_met and _is_actionable_expected(if_in_list_substring_expected))
            or (source_date_part_substring_condition_met and _is_actionable_expected(source_date_part_substring_expected))
            or (char_offset_condition_met and _is_actionable_expected(char_offset_expected))
            or (length_based_condition_met and _is_actionable_expected(length_based_expected))
        )
        missing_target_logged = False
        if mo_policy == "mandatory" and applicable_rule and not tgt_has_value:
            rule_stats["source_target_missing"] += 1
            _add_error("source_target_missing", i, tgt, "Mandatory target is missing")
            missing_target_logged = True

        # If a richer semantic condition was parsed from the sentence,
        # do not also apply generic direct-map equality checks.
        has_specialized_condition = any(
            [
                guard_only_condition is not None,
                instruction_only_effective,
                expression_map_to_target is not None,
                expected is not None,
                concat_expected is not None,
                translation is not None,
                source_exists_constant is not None,
                token_exists_mapping is not None,
                source_is_not_null_mapping is not None,
                startswith_replace is not None,
                startswith_replace_append is not None,
                startswith_constant is not None,
                if_exists_else_map is not None,
                if_replace_map is not None,
                if_equals_map is not None,
                if_equals_chain_map is not None,
                if_expression_chain_map is not None,
                sequential_if_chain_map is not None,
                multi_condition_and_map is not None,
                date_format_mapping is not None,
                field_concat_mapping is not None,
                startswith_substring is not None,
                if_equals_get_substring is not None,
                if_in_list_substring is not None,
                source_date_part_substring is not None,
                conversion_if_chain_map is not None,
                char_offset_mapping is not None,
                hardcode_literal is not None,
                concatenate_mapping is not None,
                length_based_mapping is not None,
            ]
        )

        if is_direct_mapping_rule and src_has_value and (is_if_source_rule or (not has_specialized_condition and not _looks_like_ambiguous_complex_condition(cond_text))):
            if not tgt_has_value:
                if mo_policy != "optional" and not missing_target_logged:
                    rule_stats["source_target_missing"] += 1
                    _add_error("source_target_missing", i, tgt, "Source exists but target is missing")
            elif "concat" not in cond and not target_is_container:
                src_first = _first_non_empty_value(src_vals)
                tgt_first = _first_non_empty_value(tgt_vals)
                if src_first != tgt_first:
                    rule_stats["value_mismatches"] += 1
                    _add_error(
                        "value_mismatches",
                        i,
                        tgt,
                        f"Value mismatch from source {src}: {src_first} != {tgt_first}",
                    )

        if guard_only_condition is not None and src:
            if guard_only_condition_met and _is_actionable_expected(guard_only_expected):
                if not tgt_has_value:
                    if mo_policy != "optional" and not missing_target_logged:
                        rule_stats["if_equals_mismatches"] += 1
                        _add_error(
                            "if_equals_mismatches",
                            i,
                            tgt,
                            "Conditional mapped target is missing",
                        )
                elif not target_is_container and guard_only_expected is not None:
                    tgt_first = _first_non_empty_value(tgt_vals)
                    if tgt_first != guard_only_expected:
                        rule_stats["if_equals_mismatches"] += 1
                        _add_error(
                            "if_equals_mismatches",
                            i,
                            tgt,
                            f"If-equals mapping mismatch: expected {guard_only_expected}, got {tgt_first}",
                        )

        if expected is not None:
            handled_condition = True
            if not tgt_has_value:
                if mo_policy != "optional" and not missing_target_logged:
                    rule_stats["constant_mismatches"] += 1
                    _add_error("constant_mismatches", i, tgt, "Required constant target is missing")
            else:
                found_value = _first_non_empty_value(tgt_vals)
                if (
                    found_value != expected
                    and not _is_rule_value_exception(
                        validator_exception_entries,
                        i,
                        tgt,
                        str(expected),
                        found_value,
                        "constant",
                    )
                ):
                    rule_stats["constant_mismatches"] += 1
                    _add_error(
                        "constant_mismatches",
                        i,
                        tgt,
                        f"Constant mismatch: expected {expected}, got {found_value}",
                    )

        if concat_expected is not None:
            handled_condition = True
            if not tgt_has_value:
                if mo_policy != "optional" and not missing_target_logged:
                    rule_stats["concat_mismatches"] += 1
                    _add_error("concat_mismatches", i, tgt, "Concat target is missing")
            elif _first_non_empty_value(tgt_vals) != concat_expected:
                rule_stats["concat_mismatches"] += 1
                _add_error(
                    "concat_mismatches",
                    i,
                    tgt,
                    f"Concat mismatch: expected {concat_expected}, got {_first_non_empty_value(tgt_vals)}",
                )

        if translated_expected is not None:
            handled_condition = True
            if not tgt_has_value:
                if mo_policy != "optional" and not missing_target_logged:
                    rule_stats["translated_value_mismatches"] += 1
                    _add_error(
                        "translated_value_mismatches",
                        i,
                        tgt,
                        f"Translated target is missing for source value {translated_match['source']}",
                    )
            elif _first_non_empty_value(tgt_vals) != translated_expected:
                rule_stats["translated_value_mismatches"] += 1
                _add_error(
                    "translated_value_mismatches",
                    i,
                    tgt,
                    f"Translated value mismatch: expected {translated_expected}, got {_first_non_empty_value(tgt_vals)}",
                )

        if source_exists_constant is not None:
            handled_condition = True
            if src_has_value:
                if not tgt_has_value:
                    if mo_policy != "optional" and not missing_target_logged:
                        rule_stats["source_exists_mismatches"] += 1
                        _add_error(
                            "source_exists_mismatches",
                            i,
                            tgt,
                            "Source-exists mapped target is missing",
                        )
                elif _first_non_empty_value(tgt_vals) != source_exists_constant:
                    rule_stats["source_exists_mismatches"] += 1
                    _add_error(
                        "source_exists_mismatches",
                        i,
                        tgt,
                        f"Source-exists mapped mismatch: expected {source_exists_constant}, got {_first_non_empty_value(tgt_vals)}",
                    )

        if token_exists_mapping is not None:
            handled_condition = True
            if token_exists_condition_met and _is_actionable_expected(token_exists_expected):
                if not tgt_has_value:
                    if mo_policy != "optional" and not missing_target_logged:
                        rule_stats["source_exists_mismatches"] += 1
                        _add_error(
                            "source_exists_mismatches",
                            i,
                            tgt,
                            "Token-exists mapped target is missing",
                        )
                elif token_exists_expected and _first_non_empty_value(tgt_vals) != token_exists_expected:
                    rule_stats["source_exists_mismatches"] += 1
                    _add_error(
                        "source_exists_mismatches",
                        i,
                        tgt,
                        f"Token-exists mapped mismatch: expected {token_exists_expected}, got {_first_non_empty_value(tgt_vals)}",
                    )

        if source_is_not_null_mapping is not None:
            handled_condition = True
            if source_is_not_null_condition_met and _is_actionable_expected(source_is_not_null_expected):
                if not tgt_has_value:
                    if mo_policy != "optional" and not missing_target_logged:
                        rule_stats["source_exists_mismatches"] += 1
                        _add_error(
                            "source_exists_mismatches",
                            i,
                            tgt,
                            "Source-is-not-null mapped target is missing",
                        )
                elif source_is_not_null_expected and _first_non_empty_value(tgt_vals) != source_is_not_null_expected:
                    rule_stats["source_exists_mismatches"] += 1
                    _add_error(
                        "source_exists_mismatches",
                        i,
                        tgt,
                        f"Source-is-not-null mapping mismatch: expected {source_is_not_null_expected}, got {_first_non_empty_value(tgt_vals)}",
                    )

        if startswith_replace is not None:
            handled_condition = True
            if startswith_expected is not None:
                if not tgt_has_value:
                    if mo_policy != "optional" and not missing_target_logged:
                        rule_stats["startswith_transform_mismatches"] += 1
                        _add_error(
                            "startswith_transform_mismatches",
                            i,
                            tgt,
                            "Starts-with transformed target is missing",
                        )
                elif _first_non_empty_value(tgt_vals) != startswith_expected:
                    rule_stats["startswith_transform_mismatches"] += 1
                    _add_error(
                        "startswith_transform_mismatches",
                        i,
                        tgt,
                        f"Starts-with transform mismatch: expected {startswith_expected}, got {_first_non_empty_value(tgt_vals)}",
                    )

        if if_exists_else_map is not None:
            handled_condition = True
            if if_exists_else_condition_met and _is_actionable_expected(if_exists_else_expected):
                if not tgt_has_value:
                    if mo_policy != "optional" and not missing_target_logged:
                        rule_stats["if_equals_mismatches"] += 1
                        _add_error(
                            "if_equals_mismatches",
                            i,
                            tgt,
                            "If-exists/else mapped target is missing",
                        )
                elif if_exists_else_expected is not None and _first_non_empty_value(tgt_vals) != if_exists_else_expected:
                    rule_stats["if_equals_mismatches"] += 1
                    _add_error(
                        "if_equals_mismatches",
                        i,
                        tgt,
                        f"If-exists/else mapping mismatch: expected {if_exists_else_expected}, got {_first_non_empty_value(tgt_vals)}",
                    )

        if if_replace_map is not None:
            handled_condition = True
            if if_replace_condition_met and _is_actionable_expected(if_replace_expected):
                if not tgt_has_value:
                    if mo_policy != "optional" and not missing_target_logged:
                        rule_stats["startswith_transform_mismatches"] += 1
                        _add_error(
                            "startswith_transform_mismatches",
                            i,
                            tgt,
                            "Conditional replace-mapped target is missing",
                        )
                elif if_replace_expected is not None and _first_non_empty_value(tgt_vals) != if_replace_expected:
                    rule_stats["startswith_transform_mismatches"] += 1
                    _add_error(
                        "startswith_transform_mismatches",
                        i,
                        tgt,
                        f"Conditional replace mismatch: expected {if_replace_expected}, got {_first_non_empty_value(tgt_vals)}",
                    )

        if startswith_constant is not None:
            handled_condition = True
            if startswith_constant_condition_met and _is_actionable_expected(startswith_constant_expected):
                if not tgt_has_value:
                    if mo_policy != "optional" and not missing_target_logged:
                        rule_stats["startswith_transform_mismatches"] += 1
                        _add_error(
                            "startswith_transform_mismatches",
                            i,
                            tgt,
                            "Starts-with mapped target is missing",
                        )
                elif _first_non_empty_value(tgt_vals) != startswith_constant_expected:
                    rule_stats["startswith_transform_mismatches"] += 1
                    _add_error(
                        "startswith_transform_mismatches",
                        i,
                        tgt,
                        f"Starts-with transform mismatch: expected {startswith_constant_expected}, got {_first_non_empty_value(tgt_vals)}",
                    )

        if startswith_replace_append is not None:
            handled_condition = True
            if startswith_append_expected is not None:
                if not tgt_has_value:
                    if mo_policy != "optional" and not missing_target_logged:
                        rule_stats["startswith_append_mismatches"] += 1
                        _add_error(
                            "startswith_append_mismatches",
                            i,
                            tgt,
                            "Starts-with append transformed target is missing",
                        )
                elif _first_non_empty_value(tgt_vals) != startswith_append_expected:
                    rule_stats["startswith_append_mismatches"] += 1
                    _add_error(
                        "startswith_append_mismatches",
                        i,
                        tgt,
                        f"Starts-with append transform mismatch: expected {startswith_append_expected}, got {_first_non_empty_value(tgt_vals)}",
                    )

        if if_equals_map is not None:
            handled_condition = True
            if if_equals_condition_met and _is_actionable_expected(if_equals_expected):
                if not tgt_has_value:
                    if mo_policy != "optional" and not missing_target_logged:
                        rule_stats["if_equals_mismatches"] += 1
                        _add_error(
                            "if_equals_mismatches",
                            i,
                            tgt,
                            "Conditional mapped target is missing",
                        )
                elif if_equals_expected and _first_non_empty_value(tgt_vals) != if_equals_expected:
                    rule_stats["if_equals_mismatches"] += 1
                    _add_error(
                        "if_equals_mismatches",
                        i,
                        tgt,
                        f"If-equals mapping mismatch: expected {if_equals_expected}, got {_first_non_empty_value(tgt_vals)}",
                    )

        if if_equals_chain_map is not None:
            handled_condition = True
            if if_equals_chain_condition_met and _is_actionable_expected(if_equals_chain_expected):
                if not tgt_has_value:
                    if mo_policy != "optional" and not missing_target_logged:
                        rule_stats["if_equals_mismatches"] += 1
                        _add_error(
                            "if_equals_mismatches",
                            i,
                            tgt,
                            "Conditional mapped target is missing",
                        )
                elif _first_non_empty_value(tgt_vals) != if_equals_chain_expected:
                    rule_stats["if_equals_mismatches"] += 1
                    _add_error(
                        "if_equals_mismatches",
                        i,
                        tgt,
                        f"If-equals mapping mismatch: expected {if_equals_chain_expected}, got {_first_non_empty_value(tgt_vals)}",
                    )

        if if_expression_chain_map is not None:
            handled_condition = True
            if if_expression_chain_condition_met and _is_actionable_expected(if_expression_chain_expected):
                if not tgt_has_value:
                    if mo_policy != "optional" and not missing_target_logged:
                        rule_stats["if_equals_mismatches"] += 1
                        _add_error(
                            "if_equals_mismatches",
                            i,
                            tgt,
                            "Conditional mapped target is missing",
                        )
                elif _first_non_empty_value(tgt_vals) != if_expression_chain_expected:
                    rule_stats["if_equals_mismatches"] += 1
                    _add_error(
                        "if_equals_mismatches",
                        i,
                        tgt,
                        f"If-equals mapping mismatch: expected {if_expression_chain_expected}, got {_first_non_empty_value(tgt_vals)}",
                    )

        if conversion_if_chain_map is not None:
            handled_condition = True
            if conversion_if_chain_condition_met and _is_actionable_expected(conversion_if_chain_expected):
                if not tgt_has_value:
                    if mo_policy != "optional" and not missing_target_logged:
                        rule_stats["if_equals_mismatches"] += 1
                        _add_error(
                            "if_equals_mismatches",
                            i,
                            tgt,
                            "Conditional mapped target is missing",
                        )
                elif _first_non_empty_value(tgt_vals) != conversion_if_chain_expected:
                    rule_stats["if_equals_mismatches"] += 1
                    _add_error(
                        "if_equals_mismatches",
                        i,
                        tgt,
                        f"If-equals mapping mismatch: expected {conversion_if_chain_expected}, got {_first_non_empty_value(tgt_vals)}",
                    )

        if expression_map_to_target is not None:
            handled_condition = True
            if expression_map_to_target_condition_met and _is_actionable_expected(expression_map_to_target_expected):
                if not tgt_has_value:
                    if mo_policy != "optional" and not missing_target_logged:
                        rule_stats["if_equals_mismatches"] += 1
                        _add_error(
                            "if_equals_mismatches",
                            i,
                            tgt,
                            "Conditional mapped target is missing",
                        )
                elif _first_non_empty_value(tgt_vals) != expression_map_to_target_expected:
                    rule_stats["if_equals_mismatches"] += 1
                    _add_error(
                        "if_equals_mismatches",
                        i,
                        tgt,
                        f"If-equals mapping mismatch: expected {expression_map_to_target_expected}, got {_first_non_empty_value(tgt_vals)}",
                    )

        if sequential_if_chain_map is not None:
            handled_condition = True
            if sequential_if_chain_condition_met and _is_actionable_expected(sequential_if_chain_expected):
                if not tgt_has_value:
                    if mo_policy != "optional" and not missing_target_logged:
                        rule_stats["if_equals_mismatches"] += 1
                        _add_error(
                            "if_equals_mismatches",
                            i,
                            tgt,
                            "Conditional mapped target is missing",
                        )
                elif _first_non_empty_value(tgt_vals) != sequential_if_chain_expected:
                    rule_stats["if_equals_mismatches"] += 1
                    _add_error(
                        "if_equals_mismatches",
                        i,
                        tgt,
                        f"If-equals mapping mismatch: expected {sequential_if_chain_expected}, got {_first_non_empty_value(tgt_vals)}",
                    )

        if multi_condition_and_map is not None:
            handled_condition = True
            if multi_condition_and_condition_met and _is_actionable_expected(multi_condition_and_expected):
                if not tgt_has_value:
                    if mo_policy != "optional" and not missing_target_logged:
                        rule_stats["if_equals_mismatches"] += 1
                        _add_error(
                            "if_equals_mismatches",
                            i,
                            tgt,
                            "Multi-condition target is missing",
                        )
                elif multi_condition_and_expected and _first_non_empty_value(tgt_vals) != multi_condition_and_expected:
                    rule_stats["if_equals_mismatches"] += 1
                    _add_error(
                        "if_equals_mismatches",
                        i,
                        tgt,
                        f"Multi-condition mapping mismatch: expected {multi_condition_and_expected}, got {_first_non_empty_value(tgt_vals)}",
                    )

        if date_format_mapping is not None:
            handled_condition = True
            if date_format_condition_met and _is_actionable_expected(date_format_expected):
                if not tgt_has_value:
                    if mo_policy != "optional" and not missing_target_logged:
                        rule_stats["date_format_mismatches"] += 1
                        _add_error(
                            "date_format_mismatches",
                            i,
                            tgt,
                            "Date-format target is missing",
                        )
                else:
                    found_value = _first_non_empty_value(tgt_vals)
                    date_format_exception = _is_rule_value_exception(
                        validator_exception_entries,
                        i,
                        tgt,
                        str(date_format_expected),
                        found_value,
                        "date_format",
                    )
                    hardcode_fallback_exception = _is_rule_value_exception(
                        validator_exception_entries,
                        i,
                        tgt,
                        str(date_format_expected),
                        found_value,
                        "hardcode",
                    )
                    if found_value != date_format_expected and not (date_format_exception or hardcode_fallback_exception):
                        rule_stats["date_format_mismatches"] += 1
                        _add_error(
                            "date_format_mismatches",
                            i,
                            tgt,
                            f"Date-format mapping mismatch: expected {date_format_expected}, got {found_value}",
                        )

        if field_concat_mapping is not None:
            handled_condition = True
            if field_concat_condition_met and _is_actionable_expected(field_concat_expected):
                if not tgt_has_value:
                    if mo_policy != "optional" and not missing_target_logged:
                        rule_stats["field_concat_mismatches"] += 1
                        _add_error(
                            "field_concat_mismatches",
                            i,
                            tgt,
                            "Field-concat target is missing",
                        )
                elif _first_non_empty_value(tgt_vals) != field_concat_expected:
                    rule_stats["field_concat_mismatches"] += 1
                    _add_error(
                        "field_concat_mismatches",
                        i,
                        tgt,
                        f"Field-concat mapping mismatch: expected {field_concat_expected}, got {_first_non_empty_value(tgt_vals)}",
                    )

        if startswith_substring is not None:
            handled_condition = True
            if startswith_substring_condition_met and _is_actionable_expected(startswith_substring_expected):
                if not tgt_has_value:
                    if mo_policy != "optional" and not missing_target_logged:
                        rule_stats["startswith_substring_mismatches"] += 1
                        _add_error(
                            "startswith_substring_mismatches",
                            i,
                            tgt,
                            "Starts-with substring target is missing",
                        )
                elif _first_non_empty_value(tgt_vals) != startswith_substring_expected:
                    rule_stats["startswith_substring_mismatches"] += 1
                    _add_error(
                        "startswith_substring_mismatches",
                        i,
                        tgt,
                        f"Starts-with substring mismatch: expected {startswith_substring_expected}, got {_first_non_empty_value(tgt_vals)}",
                    )

        if if_equals_get_substring is not None:
            handled_condition = True
            if if_equals_get_substring_condition_met and _is_actionable_expected(if_equals_get_substring_expected):
                if not tgt_has_value:
                    if mo_policy != "optional" and not missing_target_logged:
                        rule_stats["startswith_substring_mismatches"] += 1
                        _add_error(
                            "startswith_substring_mismatches",
                            i,
                            tgt,
                            "Conditional substring target is missing",
                        )
                elif _first_non_empty_value(tgt_vals) != if_equals_get_substring_expected:
                    rule_stats["startswith_substring_mismatches"] += 1
                    _add_error(
                        "startswith_substring_mismatches",
                        i,
                        tgt,
                        f"Conditional substring mismatch: expected {if_equals_get_substring_expected}, got {_first_non_empty_value(tgt_vals)}",
                    )

        if if_in_list_substring is not None:
            handled_condition = True
            if if_in_list_substring_condition_met and _is_actionable_expected(if_in_list_substring_expected):
                if not tgt_has_value:
                    if mo_policy != "optional" and not missing_target_logged:
                        rule_stats["char_offset_mismatches"] += 1
                        _add_error(
                            "char_offset_mismatches",
                            i,
                            tgt,
                            "In-list substring target is missing",
                        )
                elif _first_non_empty_value(tgt_vals) != if_in_list_substring_expected:
                    rule_stats["char_offset_mismatches"] += 1
                    _add_error(
                        "char_offset_mismatches",
                        i,
                        tgt,
                        f"In-list substring mismatch: expected {if_in_list_substring_expected}, got {_first_non_empty_value(tgt_vals)}",
                    )

        if source_date_part_substring is not None:
            handled_condition = True
            if source_date_part_substring_condition_met and _is_actionable_expected(source_date_part_substring_expected):
                if not tgt_has_value:
                    if mo_policy != "optional" and not missing_target_logged:
                        rule_stats["date_format_mismatches"] += 1
                        _add_error(
                            "date_format_mismatches",
                            i,
                            tgt,
                            "Date-part substring target is missing",
                        )
                elif _first_non_empty_value(tgt_vals) != source_date_part_substring_expected:
                    rule_stats["date_format_mismatches"] += 1
                    _add_error(
                        "date_format_mismatches",
                        i,
                        tgt,
                        f"Date-part substring mismatch: expected {source_date_part_substring_expected}, got {_first_non_empty_value(tgt_vals)}",
                    )

        if char_offset_mapping is not None:
            handled_condition = True
            if char_offset_condition_met and _is_actionable_expected(char_offset_expected):
                if not tgt_has_value:
                    if mo_policy != "optional" and not missing_target_logged:
                        rule_stats["char_offset_mismatches"] += 1
                        _add_error(
                            "char_offset_mismatches",
                            i,
                            tgt,
                            "Character-offset extraction target is missing",
                        )
                elif _first_non_empty_value(tgt_vals) != char_offset_expected:
                    rule_stats["char_offset_mismatches"] += 1
                    _add_error(
                        "char_offset_mismatches",
                        i,
                        tgt,
                        f"Character-offset extraction mismatch: expected {char_offset_expected}, got {_first_non_empty_value(tgt_vals)}",
                    )

        if length_based_mapping is not None:
            handled_condition = True
            if length_based_condition_met and _is_actionable_expected(length_based_expected):
                if not tgt_has_value:
                    if mo_policy != "optional" and not missing_target_logged:
                        rule_stats["length_based_mismatches"] += 1
                        _add_error(
                            "length_based_mismatches",
                            i,
                            tgt,
                            "Length-based mapped target is missing",
                        )
                elif _first_non_empty_value(tgt_vals) != length_based_expected:
                    rule_stats["length_based_mismatches"] += 1
                    _add_error(
                        "length_based_mismatches",
                        i,
                        tgt,
                        f"Length-based mapping mismatch: expected {length_based_expected}, got {_first_non_empty_value(tgt_vals)}",
                    )

        if hardcode_literal is not None:
            handled_condition = True
            if hardcode_condition_met and _is_actionable_expected(hardcode_expected):
                if not tgt_has_value:
                    if mo_policy != "optional" and not missing_target_logged:
                        rule_stats["constant_mismatches"] += 1
                        _add_error(
                            "constant_mismatches",
                            i,
                            tgt,
                            "Hardcoded constant target is missing",
                        )
                else:
                    found_value = _first_non_empty_value(tgt_vals)
                    if (
                        found_value != hardcode_expected
                        and not _is_rule_value_exception(
                            validator_exception_entries,
                            i,
                            tgt,
                            str(hardcode_expected),
                            found_value,
                            "hardcode",
                        )
                    ):
                        rule_stats["constant_mismatches"] += 1
                        _add_error(
                            "constant_mismatches",
                            i,
                            tgt,
                            f"Hardcode mismatch: expected {hardcode_expected}, got {found_value}",
                        )

        if concatenate_mapping is not None:
            handled_condition = True
            if concatenate_condition_met and _is_actionable_expected(concatenate_expected):
                if not tgt_has_value:
                    if mo_policy != "optional" and not missing_target_logged:
                        rule_stats["concat_mismatches"] += 1
                        _add_error(
                            "concat_mismatches",
                            i,
                            tgt,
                            "Concatenate target is missing",
                        )
                elif concatenate_expected and _first_non_empty_value(tgt_vals) != concatenate_expected:
                    rule_stats["concat_mismatches"] += 1
                    _add_error(
                        "concat_mismatches",
                        i,
                        tgt,
                        f"Concatenate mismatch: expected {concatenate_expected}, got {_first_non_empty_value(tgt_vals)}",
                    )

        if cond_text.strip() and not handled_condition:
            detected_pattern = _detect_pattern_family(cond_text)
            suggested_patterns = _suggest_pattern_families(
                cond_text,
                top_n=3,
                semantic_profile=semantic_profile,
            )
            top_suggestion = suggested_patterns[0] if suggested_patterns else None
            ambiguity = _analyze_semantic_ambiguity(
                suggested_patterns,
                dict(semantic_profile.get("thresholds", {})),
            )
            why_not_enforced = _build_semantic_explanation(top_suggestion, ambiguity, semantic_parts)
            suggested_rewrite = _build_suggested_canonical_rewrite(
                str(top_suggestion["family"]) if top_suggestion else "",
                semantic_parts,
                ambiguity,
            )
            auto_promotion_candidate = bool(
                top_suggestion
                and not ambiguity.get("is_ambiguous")
                and float(top_suggestion["score"]) >= float(semantic_profile.get("thresholds", {}).get("auto_promote", 0.9))
            )
            if top_suggestion:
                decision_similarity_score = float(top_suggestion["score"])
                decision_nearest_family = str(top_suggestion["family"])
                support_summary["unsupported_rule_suggestions_provided"] += 1
                semantic_suggested_families[str(top_suggestion["family"])] += 1
                if top_suggestion["confidence"] == "high":
                    support_summary["high_similarity_unsupported_rules"] += 1
                elif top_suggestion["confidence"] == "medium":
                    support_summary["medium_similarity_unsupported_rules"] += 1
                else:
                    support_summary["low_similarity_unsupported_rules"] += 1
            if ambiguity.get("is_ambiguous"):
                support_summary["ambiguous_unsupported_rules"] += 1
            if auto_promotion_candidate:
                support_summary["auto_promote_candidate_rules"] += 1

            semantic_unsupported_conditions[cond_text or str(cond_text_raw)] += 1
            skipped_rules.append(
                {
                    "row": str(i),
                    "target_xpath": tgt,
                    "reason": "Unsupported condition pattern",
                    "condition": cond_text_raw,
                    "normalized_condition": cond_text,
                    "applied_transforms": cond_transform_trace,
                    "detected_pattern": detected_pattern,
                    "nearest_family": top_suggestion["family"] if top_suggestion else "",
                    "similarity_score": float(top_suggestion["score"]) if top_suggestion else 0.0,
                    "similarity_confidence": top_suggestion["confidence"] if top_suggestion else "low",
                    "nearest_patterns": suggested_patterns,
                    "why_not_enforced": why_not_enforced,
                    "try_normalized_form": cond_text,
                    "semantic_parts": semantic_parts,
                    "ambiguous_families": list(ambiguity.get("candidate_families", [])),
                    "ambiguity_reason": ambiguity.get("reason", ""),
                    "suggested_canonical_rewrite": suggested_rewrite,
                    "future_auto_promotion_eligible": auto_promotion_candidate,
                    "semantic_profile": semantic_profile.get("profile_key", "generic"),
                    "workbook_family": semantic_profile.get("profile_key", "generic"),
                }
            )
            support_summary["unsupported_rules"] += 1
            if rule_supported_for_enforcement:
                support_summary["parsed_only_rules"] += 1
                for branch_path in _parsed_only_parent_branches(simplified_target_path):
                    structure_required_paths.add(branch_path)
            decision_status = "unsupported"
            decision_reason = why_not_enforced
        elif guard_only_condition_recognized:
            support_summary["parsed_only_rules"] += 1
            for branch_path in _parsed_only_parent_branches(simplified_target_path):
                structure_required_paths.add(branch_path)
            decision_status = "parsed_only"
            decision_reason = "Condition recognized as procedural/instruction-only; preserved for review"
        elif rule_supported_for_enforcement:
            support_summary["enforced_rules"] += 1
            decision_status = "enforced"
            decision_reason = "Rule was evaluated with deterministic parser support"
        else:
            support_summary["parsed_only_rules"] += 1
            for branch_path in _parsed_only_parent_branches(simplified_target_path):
                structure_required_paths.add(branch_path)
            decision_status = "parsed_only"
            decision_reason = "Rule parsed but not fully enforceable with deterministic evidence"

        semantic_action = str(semantic_parts.get("action", "unknown"))
        ai_conflicts = _ai_review_conflicts(
            status=decision_status,
            has_condition=bool(cond_text.strip()),
            source_xpath=src,
            family=decision_nearest_family,
            semantic_action=semantic_action,
            row_error_count=int(row_error_counts.get(i, 0)),
            enforce_source_path_guardrail=True,
        )
        reviewed_status = decision_status
        reviewed_reason = decision_reason
        if ai_conflicts:
            reviewed_status = "parsed_only"
            reviewed_reason = "AI review demoted enforcement: " + "; ".join(ai_conflicts[:2])
            _rebalance_support_summary_status(support_summary, decision_status, reviewed_status)

        evidence = _build_ai_review_evidence(
            status=reviewed_status,
            has_condition=bool(cond_text.strip()),
            source_xpath=src,
            target_xpath=tgt,
            family=decision_nearest_family,
            semantic_action=semantic_action,
            similarity_score=decision_similarity_score,
            row_error_count=int(row_error_counts.get(i, 0)),
            source_has_value=src_has_value,
            target_has_value=tgt_has_value,
        )

        rule_decisions.append(
            {
                "row": i,
                "target_xpath": tgt,
                "source_xpath": src,
                "status": reviewed_status,
                "confidence": float(evidence["score"]),
                "family": decision_nearest_family,
                "reason": reviewed_reason,
                "ai_review": {
                    "stage": "runtime_guardrail",
                    "conflicts": ai_conflicts,
                    "evidence": evidence,
                },
            }
        )

    contradiction_conflicts = _detect_enforced_target_intent_conflicts(rule_decisions)
    for conflict in contradiction_conflicts:
        conflict_rows = {int(row) for row in conflict.get("rows", []) if int(row) > 0}
        for decision in rule_decisions:
            row = int(decision.get("row", 0) or 0)
            if row not in conflict_rows:
                continue
            if str(decision.get("status", "")) != "enforced":
                continue

            _rebalance_support_summary_status(support_summary, "enforced", "parsed_only")
            decision["status"] = "parsed_only"
            decision["reason"] = str(conflict.get("reason", "Cross-rule contradiction detected"))

            ai_review = decision.get("ai_review") if isinstance(decision.get("ai_review"), dict) else {}
            existing_conflicts = ai_review.get("conflicts") if isinstance(ai_review.get("conflicts"), list) else []
            existing_conflicts.append(
                f"target={conflict.get('target_xpath', '')}; intent_classes={','.join(conflict.get('intent_classes', []))}"
            )
            ai_review["stage"] = "runtime_guardrail_contradiction_v2"
            ai_review["conflicts"] = existing_conflicts
            decision["ai_review"] = ai_review

    if mode == "structure_strict":
        expected_root_paths = {path for path in structure_allowed_paths if len([token for token in path.split("/") if token]) == 1}
        actual_root_path = f"/{tgt_root_name}"
        if expected_root_paths and actual_root_path not in expected_root_paths:
            rule_stats["root_mismatches"] += 1
            expected_roots = ", ".join(sorted(expected_root_paths))
            _add_error(
                "root_mismatches",
                0,
                actual_root_path,
                f"Target root does not match spec: expected {expected_roots}, got {actual_root_path}",
                details={"expected": sorted(expected_root_paths), "actual": actual_root_path},
            )

        missing_branch_paths: set[str] = set()
        for required_path in sorted(structure_required_paths):
            missing_branch_path = _find_missing_branch_path(tgt_tree, tgt_ns, required_path)
            if (
                missing_branch_path
                and missing_branch_path not in missing_branch_paths
                and missing_branch_path not in structure_spec_exceptions["ignore_required_paths"]
            ):
                missing_branch_paths.add(missing_branch_path)
                rule_stats["missing_target_branches"] += 1
                _add_error(
                    "missing_target_branches",
                    0,
                    missing_branch_path,
                    "Required target branch is missing",
                    details={"required_path": required_path, "actual": "missing"},
                )

        unexpected_attribute_paths: set[str] = set()
        for actual_path in _build_target_attribute_paths(tgt_tree):
            simplified_actual_path = _simplify_xpath(actual_path, include_attributes=True)
            if not simplified_actual_path or _is_allowlisted_structure_path(simplified_actual_path):
                continue
            if simplified_actual_path in structure_spec_exceptions["allow_attributes"]:
                continue
            if simplified_actual_path not in structure_allowed_attribute_paths:
                unexpected_attribute_paths.add(simplified_actual_path)

        for unexpected_attribute_path in sorted(unexpected_attribute_paths):
            rule_stats["unexpected_target_attributes"] += 1
            _add_error(
                "unexpected_target_attributes",
                0,
                unexpected_attribute_path,
                "Unexpected target attribute not described by the spec",
                details={"expected": "attribute path from spec", "actual": unexpected_attribute_path},
            )

        unexpected_paths: set[str] = set()
        for actual_path in _build_target_element_paths(tgt_tree):
            simplified_actual_path = _simplify_xpath(actual_path)
            if not simplified_actual_path or simplified_actual_path == f"/{tgt_root_name}":
                continue
            if _is_allowlisted_structure_path(simplified_actual_path):
                continue
            if simplified_actual_path in structure_spec_exceptions["allow_nodes"]:
                continue
            if simplified_actual_path not in structure_allowed_paths:
                unexpected_paths.add(simplified_actual_path)

        for unexpected_path in sorted(unexpected_paths):
            rule_stats["unexpected_target_nodes"] += 1
            _add_error(
                "unexpected_target_nodes",
                0,
                unexpected_path,
                "Unexpected target node not described by the spec",
                details={"expected": "node path from spec", "actual": unexpected_path},
            )

        for parent_cardinality_rule in structure_parent_cardinality_rules:
            parent_nodes = _elements_for_simplified_path(tgt_tree, parent_cardinality_rule["parent_path"])
            for parent_element in parent_nodes:
                child_count = 0
                for child in parent_element:
                    if isinstance(child.tag, str) and _local_name(child.tag) == parent_cardinality_rule["child_name"]:
                        child_count += 1
                min_count = parent_cardinality_rule["min_count"]
                max_count = parent_cardinality_rule["max_count"]
                if child_count < min_count or (max_count is not None and child_count > max_count):
                    rule_stats["child_cardinality_violations"] += 1
                    _add_error(
                        "child_cardinality_violations",
                        parent_cardinality_rule["row"],
                        parent_cardinality_rule["target_xpath"],
                        f"Per-parent cardinality violation under {parent_cardinality_rule['parent_path']}: expected {min_count}..{max_count if max_count is not None else 'N'}, got {child_count}",
                        details={
                            "parent_path": parent_cardinality_rule["parent_path"],
                            "expected": f"{min_count}..{max_count if max_count is not None else 'N'}",
                            "actual": child_count,
                            "rule_row": parent_cardinality_rule["row"],
                        },
                    )

        seen_required_attribute_misses: set[tuple[str, str]] = set()
        for required_attribute_rule in structure_required_attribute_rules:
            parent_nodes = _elements_for_simplified_path(tgt_tree, required_attribute_rule["parent_path"])
            for parent_element in parent_nodes:
                if required_attribute_rule["attribute_name"] not in {
                    _local_name(attr_name) for attr_name in parent_element.attrib
                }:
                    key = (required_attribute_rule["parent_path"], required_attribute_rule["attribute_name"])
                    if key in seen_required_attribute_misses:
                        continue
                    seen_required_attribute_misses.add(key)
                    rule_stats["required_target_attributes_missing"] += 1
                    _add_error(
                        "required_target_attributes_missing",
                        required_attribute_rule["row"],
                        f"{required_attribute_rule['parent_path']}/@{required_attribute_rule['attribute_name']}",
                        "Required target attribute is missing",
                        details={
                            "parent_path": required_attribute_rule["parent_path"],
                            "attribute_name": required_attribute_rule["attribute_name"],
                            "actual": "missing",
                            "rule_row": required_attribute_rule["row"],
                        },
                    )

        for choice_group in structure_spec_exceptions["choice_groups"]:
            parent_path = _simplify_xpath(choice_group.get("parent_path", ""))
            option_paths = [_simplify_xpath(path) for path in choice_group.get("options", [])]
            if not parent_path or not option_paths:
                continue
            min_choices = int(choice_group.get("min", 1))
            max_choices = choice_group.get("max", 1)
            max_choices = None if max_choices is None else int(max_choices)
            option_local_names = [path.rsplit("/", 1)[-1] for path in option_paths if path.startswith(parent_path + "/")]
            for parent_element in _elements_for_simplified_path(tgt_tree, parent_path):
                present = set()
                for child in parent_element:
                    if isinstance(child.tag, str):
                        local_name = _local_name(child.tag)
                        if local_name in option_local_names:
                            present.add(local_name)
                choice_count = len(present)
                if choice_count < min_choices or (max_choices is not None and choice_count > max_choices):
                    rule_stats["choice_group_violations"] += 1
                    _add_error(
                        "choice_group_violations",
                        0,
                        parent_path,
                        f"Choice group violation: expected {min_choices}..{max_choices if max_choices is not None else 'N'} branch(es), got {choice_count}",
                        details={
                            "expected": f"{min_choices}..{max_choices if max_choices is not None else 'N'}",
                            "actual": choice_count,
                            "parent_path": parent_path,
                        },
                    )

        for sibling_group in structure_spec_exceptions["ordered_sibling_groups"]:
            parent_path = _simplify_xpath(sibling_group.get("parent_path", ""))
            ordered_children = [
                _simplify_xpath(path).rsplit("/", 1)[-1]
                for path in sibling_group.get("children", [])
                if _simplify_xpath(path)
            ]
            if not parent_path or len(ordered_children) < 2:
                continue
            for parent_element in _elements_for_simplified_path(tgt_tree, parent_path):
                child_order = [_local_name(child.tag) for child in parent_element if isinstance(child.tag, str)]
                indexes = [child_order.index(name) for name in ordered_children if name in child_order]
                if indexes and indexes != sorted(indexes):
                    rule_stats["sibling_order_violations"] += 1
                    _add_error(
                        "sibling_order_violations",
                        0,
                        parent_path,
                        "Sibling order violation: children are not in the expected sequence",
                        details={"parent_path": parent_path, "expected_order": ordered_children},
                    )

        expected_namespace = _namespace_uri(tgt_tree.getroot().tag)
        if expected_namespace:
            namespace_mismatch_paths: set[str] = set()
            for actual_path, element in [
                (path, element)
                for path, element in [
                    ("/" + "/".join([_local_name(node.tag) for node in node.iterancestors()][::-1] + [_local_name(node.tag)]), node)
                    for node in tgt_tree.getroot().iter()
                    if isinstance(node.tag, str)
                ]
            ]:
                simplified_actual_path = _simplify_xpath(actual_path)
                if not simplified_actual_path or simplified_actual_path not in structure_allowed_paths:
                    continue
                if simplified_actual_path == f"/{tgt_root_name}":
                    continue
                if _namespace_uri(element.tag) != expected_namespace:
                    namespace_mismatch_paths.add(simplified_actual_path)
            for mismatch_path in sorted(namespace_mismatch_paths):
                rule_stats["namespace_mismatches"] += 1
                _add_error(
                    "namespace_mismatches",
                    0,
                    mismatch_path,
                    "Namespace mismatch: target node uses a different namespace than expected",
                    details={"expected_namespace": expected_namespace, "actual": "different"},
                )

    rule_by_row: dict[int, dict] = {}
    for idx, rule in enumerate(rules, start=1):
        rule_by_row[idx] = rule

    for decision in rule_decisions:
        row = int(decision.get("row", 0) or 0)
        row_rule = rule_by_row.get(row, {})
        has_condition = bool(str(row_rule.get("condition", "") or "").strip())
        source_xpath = str(decision.get("source_xpath", "") or "")
        target_xpath = str(decision.get("target_xpath", "") or "")
        parser_confidence_for_row = str(row_rule.get("parser_confidence", "unknown") or "unknown")
        row_error_count = int(row_error_counts.get(row, 0))
        guardrails = _build_pre_fail_guardrails(
            status=str(decision.get("status", "")),
            has_condition=has_condition,
            source_xpath=source_xpath,
            target_xpath=target_xpath,
            parser_confidence=parser_confidence_for_row,
            decision_confidence=float(decision.get("confidence", 0.0) or 0.0),
        )
        decision["guardrail_checks"] = guardrails["checks"]
        decision["guardrail_failed_checks"] = guardrails["failed_checks"]
        confidence_policy = _confidence_band_and_policy(float(decision.get("confidence", 0.0) or 0.0), confidence_thresholds)
        decision["confidence_band"] = confidence_policy["confidence_band"]
        decision["apply_policy"] = confidence_policy["apply_policy"]
        decision["row_error_count"] = row_error_count
        outcome = _decision_outcome_from_evidence(
            status=str(decision.get("status", "")),
            row_error_count=row_error_count,
            decision_confidence=float(decision.get("confidence", 0.0) or 0.0),
            parser_confidence=parser_confidence_for_row,
            requires_abstain=bool(guardrails["requires_abstain"]),
            thresholds=confidence_thresholds,
        )
        decision["decision_outcome"] = outcome

    decision_outcome_counts = Counter(
        str(decision.get("decision_outcome", _DECISION_OUTCOME_FAIL))
        for decision in rule_decisions
    )
    support_summary["abstained_rules"] = int(decision_outcome_counts.get(_DECISION_OUTCOME_ABSTAIN, 0))

    strict_would_fail = bool(errors)
    valid = not strict_would_fail if mode in {"strict", "structure_strict"} else True
    error_count = len(errors)
    warnings: list[str] = []
    if checked_rules == 0:
        warnings.append("No rules were checked against the target XML")
    if mode == "lenient" and strict_would_fail:
        warnings.append("Lenient mode enabled: validation contains errors but result is marked as valid")
    if mode == "structure_strict":
        warnings.append(
            "Structure-strict mode enabled: validation includes standard checks plus branch/attribute/node, conditional, cardinality-coupling, choice/order, and namespace structure checks"
        )
    if mode == "completion_status":
        warnings.append(
            "Completion-status mode enabled: report includes overall progress, mandatory/optional completion, and lines left"
        )
    if skipped_rules:
        warnings.append(f"Skipped {len(skipped_rules)} rule(s) due to unsupported conditions")
    parser_confidence = parser_diagnostics.get("confidence")
    if parser_confidence and parser_confidence != "high":
        warnings.append(
            f"Parser confidence is {parser_confidence}; review parser_diagnostics for fallbacks or ambiguities"
        )
    if support_summary["parsed_only_rules"]:
        warnings.append(
            f"{support_summary['parsed_only_rules']} rule(s) were parsed but not fully enforced"
        )
    if support_summary.get("abstained_rules", 0):
        warnings.append(
            f"{support_summary['abstained_rules']} rule decision(s) are marked ABSTAIN due to uncertainty guardrails"
        )
    if parser_diagnostics.get("extraction", {}).get("ambiguities"):
        warnings.append("Parser resolved ambiguous column matches heuristically")

    ai_demoted_rules = sum(
        1
        for decision in rule_decisions
        if str(decision.get("reason", "")).startswith("AI review demoted enforcement:")
    )
    low_evidence_rules = sum(
        1
        for decision in rule_decisions
        if float(decision.get("confidence", 0.0) or 0.0) < 0.55
    )
    ai_review_summary = {
        "demoted_rules": int(ai_demoted_rules),
        "low_evidence_rules": int(low_evidence_rules),
        "contradiction_conflicts": len(contradiction_conflicts),
        "reviewed_rules": len(rule_decisions),
        "decision_outcomes": {
            "pass": int(decision_outcome_counts.get(_DECISION_OUTCOME_PASS, 0)),
            "abstain": int(decision_outcome_counts.get(_DECISION_OUTCOME_ABSTAIN, 0)),
            "fail": int(decision_outcome_counts.get(_DECISION_OUTCOME_FAIL, 0)),
        },
    }
    ai_review_summary["confidence_policy"] = {
        "high": confidence_thresholds["high"],
        "medium": confidence_thresholds["medium"],
    }
    if ai_demoted_rules > 0:
        warnings.append(
            f"AI review guardrail demoted {ai_demoted_rules} rule(s) from enforced to parsed_only"
        )
    if contradiction_conflicts:
        warnings.append(
            f"Contradiction engine v2 detected {len(contradiction_conflicts)} target-level intent conflict(s)"
        )

    grouped_error_counts = {k: len(v) for k, v in error_sections.items()}
    actual_structure_paths = {
        simplified_path
        for simplified_path in (_simplify_xpath(path) for path in _build_target_element_paths(tgt_tree))
        if simplified_path
    }
    allowed_structure_paths = set(structure_allowed_paths)
    if f"/{tgt_root_name}" in allowed_structure_paths:
        allowed_structure_paths.remove(f"/{tgt_root_name}")
    missing_allowed_paths = sorted(
        path
        for path in allowed_structure_paths
        if path not in actual_structure_paths and path not in structure_spec_exceptions["ignore_required_paths"]
    )
    present_allowed_paths = sorted(path for path in allowed_structure_paths if path in actual_structure_paths)
    coverage_percent = round((len(present_allowed_paths) / len(allowed_structure_paths) * 100), 2) if allowed_structure_paths else 100.0
    structure_counts = {
        "root_mismatches": grouped_error_counts.get("root_mismatches", 0),
        "missing_target_branches": grouped_error_counts.get("missing_target_branches", 0),
        "unexpected_target_attributes": grouped_error_counts.get("unexpected_target_attributes", 0),
        "unexpected_target_nodes": grouped_error_counts.get("unexpected_target_nodes", 0),
        "repeat_count_violations": len(structure_repeat_findings),
        "child_cardinality_violations": grouped_error_counts.get("child_cardinality_violations", 0),
        "required_target_attributes_missing": grouped_error_counts.get("required_target_attributes_missing", 0),
        "sibling_order_violations": grouped_error_counts.get("sibling_order_violations", 0),
        "choice_group_violations": grouped_error_counts.get("choice_group_violations", 0),
        "namespace_mismatches": grouped_error_counts.get("namespace_mismatches", 0),
    }
    structure_summary = {
        "status": "FAIL" if any(structure_counts.values()) else "PASS",
        "counts": structure_counts,
        "repeat_count_examples": structure_repeat_findings[:5],
        "coverage": {
            "allowed_paths": len(allowed_structure_paths),
            "present_allowed_paths": len(present_allowed_paths),
            "missing_allowed_paths": len(missing_allowed_paths),
            "coverage_percent": coverage_percent,
            "missing_allowed_examples": missing_allowed_paths[:20],
        },
        "finding_count": len(structure_findings),
        "finding_examples": structure_findings[:20],
        "applied_exceptions": {
            "ignore_required_paths": sorted(structure_spec_exceptions["ignore_required_paths"]),
            "allow_nodes": sorted(structure_spec_exceptions["allow_nodes"]),
            "allow_attributes": sorted(structure_spec_exceptions["allow_attributes"]),
            "config_source": structure_spec_exceptions.get("config_source", "built-in"),
        },
    }
    top_critical_errors = _build_top_critical_errors(error_sections)
    status = "PASS"
    if mode in {"strict", "structure_strict"} and strict_would_fail:
        status = "FAIL"
    elif mode == "lenient" and strict_would_fail:
        status = "PASS_WITH_WARNINGS"

    total_condition_rules = int(support_summary.get("condition_based_rules", 0))
    semantic_supported_rules = max(total_condition_rules - int(support_summary.get("unsupported_rules", 0)), 0)
    semantic_coverage_percent = round((semantic_supported_rules / total_condition_rules) * 100, 2) if total_condition_rules else 100.0
    semantic_summary = {
        "profile": semantic_profile.get("profile_key", "generic"),
        "workbook_family": semantic_profile.get("profile_key", "generic"),
        "config_source": semantic_profile.get("config_source", "built-in"),
        "thresholds": dict(semantic_profile.get("thresholds", {})),
        "coverage": {
            "total_condition_rules": total_condition_rules,
            "supported_condition_rules": semantic_supported_rules,
            "unsupported_condition_rules": int(support_summary.get("unsupported_rules", 0)),
            "coverage_percent": semantic_coverage_percent,
        },
        "ambiguity": {
            "ambiguous_unsupported_rules": int(support_summary.get("ambiguous_unsupported_rules", 0)),
            "auto_promote_candidate_rules": int(support_summary.get("auto_promote_candidate_rules", 0)),
        },
        "field_aliases": {
            "normalized_rules": int(support_summary.get("field_alias_normalized_rules", 0)),
        },
        "top_unsupported_conditions": [
            {"condition": condition, "count": count}
            for condition, count in semantic_unsupported_conditions.most_common(10)
        ],
        "promote_to_generic_candidates": [
            {"condition": condition, "count": count}
            for condition, count in semantic_unsupported_conditions.most_common(10)
            if count >= 2
        ],
        "top_suggested_families": [
            {"family": family, "count": count}
            for family, count in semantic_suggested_families.most_common(10)
        ],
    }

    missing_cardinality_rules = sum(1 for rule in rules if not str(rule.get("cardinality", "") or "").strip())
    mandatory_preflight = _build_mandatory_preflight_checklist(rules, tgt_tree=tgt_tree, tgt_ns=tgt_ns)
    reverse_validation_summary = _build_reverse_validation_summary(rules)
    mapping_completeness = _build_mapping_completeness_summary(
        mandatory_preflight,
        reverse_validation_summary,
    )
    completion_status_summary = _build_completion_status_summary(
        rules,
        mandatory_preflight,
        reverse_validation_summary,
        tgt_tree=tgt_tree,
        tgt_ns=tgt_ns,
    )
    if mode == "completion_status":
        status = "PASS" if int(completion_status_summary.get("lines_left", 0)) == 0 else "PASS_WITH_WARNINGS"
        valid = True
    unsupported_suggestions = _build_unsupported_suggestion_summary(skipped_rules)
    rule_gap_summary = _build_rule_gap_summary(
        support_summary,
        parser_diagnostics,
        semantic_summary,
        missing_cardinality_rules,
    )
    issue_breakdown = _human_issue_breakdown(grouped_error_counts)
    if mode == "completion_status":
        issue_breakdown = [
            {
                "issue": "Overall fields not mapped",
                "count": int(completion_status_summary.get("lines_left", 0)),
            },
            {
                "issue": "Mandatory fields not mapped",
                "count": int(completion_status_summary.get("mandatory_lines_left", 0)),
            },
            {
                "issue": "Optional fields not mapped",
                "count": int(completion_status_summary.get("optional_lines_left", 0)),
            },
        ]
        if strict_would_fail:
            issue_breakdown.append(
                {
                    "issue": "Validation issues detected during completion run",
                    "count": int(error_count),
                }
            )
    if int(reverse_validation_summary.get("unmapped_required_rules", 0)) > 0:
        issue_breakdown.append(
            {
                "issue": "Required targets missing source mapping rules",
                "count": int(reverse_validation_summary.get("unmapped_required_rules", 0)),
            }
        )

    human_top_fixes = [_humanize_issue_text(issue) for issue in top_critical_errors]
    if mode == "completion_status" and not human_top_fixes:
        human_top_fixes = [
            f"Row {int(item.get('row', 0) or 0)}: [{item.get('requirement', 'rule')}] not mapped \u2014 {item.get('target_xpath', '')}"
            for item in completion_status_summary.get("pending_examples", [])[:20]
        ]
    if unsupported_suggestions:
        human_top_fixes.extend(
            [
                (
                    f"Row {item.get('row')}: {item.get('rewrite') or 'Rewrite condition to a supported deterministic pattern.'} "
                    f"(confidence: {item.get('confidence')}; why: {item.get('why') or 'condition does not match deterministic family'})"
                )
                for item in unsupported_suggestions[:10]
            ]
        )

    human_summary = {
        "headline": (
            f"Completion status: {completion_status_summary['overall_completion_percent']}% "
            f"({completion_status_summary['lines_completed']}/{completion_status_summary['lines_total']})"
            if mode == "completion_status"
            else (
                "No mapping issues found"
                if error_count == 0
                else f"Found {error_count} mapping issue(s); review all listed items"
            )
        ),
        "what_to_fix_first": human_top_fixes,
        "issue_breakdown": issue_breakdown,
        "structure_summary": structure_summary,
        "checked_rules": checked_rules,
        "skipped_rules": len(skipped_rules),
        "semantic_summary": {
            "headline": (
                "All rule conditions matched supported semantic patterns"
                if int(support_summary.get("unsupported_rules", 0)) == 0
                else f"{support_summary['unsupported_rules']} rule condition(s) still need manual semantic review"
            ),
            "coverage_percent": semantic_coverage_percent,
            "top_suggested_families": semantic_summary["top_suggested_families"][:3],
        },
        "support_confidence": {
            "parser": parser_diagnostics.get("confidence", "unknown"),
            "enforcement": (
                "high"
                if support_summary["unsupported_rules"] == 0 and support_summary["parsed_only_rules"] == 0
                else "medium"
                if support_summary["unsupported_rules"] == 0
                else "low"
            ),
        },
        "ai_review_summary": ai_review_summary,
        "rule_gap_summary": rule_gap_summary,
        "mandatory_preflight": mandatory_preflight,
        "reverse_validation_summary": reverse_validation_summary,
        "mapping_completeness": mapping_completeness,
        "completion_status": completion_status_summary,
        "unsupported_rule_suggestions": unsupported_suggestions,
    }

    for decision in rule_decisions:
        decision["reason_code"] = _reason_code(str(decision.get("reason", "")))
        decision["remediation_hint"] = _decision_fix_hint(
            str(decision.get("status", "")),
            str(decision.get("reason", "")),
            str(decision.get("family", "")),
        )

    agent_action_plan = _build_agent_action_plan(
        rule_decisions=rule_decisions,
        error_diagnostics=error_diagnostics,
        thresholds=confidence_thresholds,
    )
    parser_validator_calibration = _build_parser_validator_calibration(
        rule_decisions=rule_decisions,
        thresholds=confidence_thresholds,
    )

    rule_decision_by_row = {
        int(decision.get("row", 0)): decision
        for decision in rule_decisions
        if int(decision.get("row", 0)) > 0
    }
    for diag in error_diagnostics:
        row = int(diag.get("row", 0) or 0)
        if row > 0 and row in rule_decision_by_row:
            decision = rule_decision_by_row[row]
            diag["decision_status"] = decision.get("status")
            diag["decision_confidence"] = decision.get("confidence")
            diag["decision_family"] = decision.get("family")
            diag["decision_reason"] = decision.get("reason")
            diag["decision_reason_code"] = decision.get("reason_code")

    parser_diagnostics["token_resolution_diagnostics"] = dict(token_resolution_stats)
    parser_diagnostics["rollout_guardrails"] = {
        "shadow_rule_families": sorted(shadow_rule_families),
        "shadow_mode_rules": int(support_summary.get("shadow_mode_rules", 0)),
    }
    _ACTIVE_TOKEN_RESOLUTION_STATS = None

    return {
        "validation_fingerprint": _build_validation_fingerprint(mode),
        "summary": {
            "status": status,
            "error_count": error_count,
            "grouped_error_counts": grouped_error_counts,
            "top_critical_errors": top_critical_errors,
            "parser_status": parser_diagnostics.get("status", "unknown"),
            "parser_confidence": parser_diagnostics.get("confidence", "unknown"),
        },
        "human_summary": human_summary,
        "valid": valid,
        "validation_mode": mode,
        "strict_would_fail": strict_would_fail,
        "checked_rules": checked_rules,
        "warnings": warnings,
        "warning_taxonomy": _build_warning_taxonomy(warnings),
        "rule_stats": rule_stats,
        "structure_summary": structure_summary,
        "semantic_summary": semantic_summary,
        "rule_gap_summary": rule_gap_summary,
        "mandatory_preflight": mandatory_preflight,
        "reverse_validation_summary": reverse_validation_summary,
        "mapping_completeness": mapping_completeness,
        "completion_status": completion_status_summary,
        "unsupported_rule_suggestions": unsupported_suggestions,
        "structure_findings": structure_findings,
        "parser_diagnostics": parser_diagnostics,
        "rule_support_summary": support_summary,
        "ai_review_summary": ai_review_summary,
        "agent_action_plan": agent_action_plan,
        "parser_validator_calibration": parser_validator_calibration,
        "rule_decisions": rule_decisions,
        "error_diagnostics": error_diagnostics,
        "skipped_rules": skipped_rules,
        "error_sections": error_sections,
        "top_critical_errors": top_critical_errors,
        "error_count": error_count,
        "inputs": {
            "spec_path": spec_path,
            "input_xml_path": input_xml_path,
            "output_xml_path": output_xml_path,
        },
        "errors": errors,
    }


def write_report(result: dict, report_path: str) -> Path:
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "report_version": "1.1",
        "report_id": str(uuid4()),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        **result,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
