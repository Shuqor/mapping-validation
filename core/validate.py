import json
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from core.spec_reader import extract_rules, read_mapping_table
from core.xml_tools import parse_xml, xpath_values


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


def _is_if_source_map_rule(condition: str) -> bool:
    normalized = " ".join(condition.lower().split())
    return "if source" in normalized and "map source to target" in normalized


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

    if message == "Source exists but target is missing":
        return f"Create target {target} because source has a value."

    card_match = re.search(r"Cardinality violation: expected\s+([^,]+),\s*got\s*(\d+)", message)
    if card_match:
        return (
            f"Fix target count at {target}: expected {card_match.group(1)}, "
            f"but found {card_match.group(2)}."
        )

    value_match = re.search(r"Value mismatch from source\s+([^:]+):\s*(.*?)\s*!=\s*(.*)", message)
    if value_match:
        return (
            f"Update mapping from {value_match.group(1).strip()} to {target}: "
            f"expected '{value_match.group(2).strip()}' but found '{value_match.group(3).strip()}'."
        )

    constant_match = re.search(r"Constant mismatch: expected\s*(.*?),\s*got\s*(.*)", message)
    if constant_match:
        return (
            f"Set constant value at {target}: expected '{constant_match.group(1).strip()}' "
            f"but found '{constant_match.group(2).strip()}'."
        )

    if message == "Required constant target is missing":
        return f"Create target {target} for the required constant value."

    concat_match = re.search(r"Concat mismatch: expected\s*(.*?),\s*got\s*(.*)", message)
    if concat_match:
        return (
            f"Fix concatenated value at {target}: expected '{concat_match.group(1).strip()}' "
            f"but found '{concat_match.group(2).strip()}'."
        )

    if message == "Concat target is missing":
        return f"Create target {target} for concatenated value output."

    return f"Fix mapping at {target}: {message}."


def _build_top_critical_errors(error_sections: dict[str, list[str]], limit: int = 10) -> list[str]:
    priority = [
        "source_target_missing",
        "cardinality_violations",
        "value_mismatches",
        "constant_mismatches",
        "concat_mismatches",
        "other",
    ]
    top: list[str] = []
    for key in priority:
        for err in _sorted_errors(error_sections.get(key, [])):
            top.append(err)
            if len(top) >= limit:
                return top
    return top


def _human_issue_breakdown(grouped_error_counts: dict[str, int]) -> list[dict[str, int | str]]:
    labels = {
        "source_target_missing": "Missing target when source has value",
        "cardinality_violations": "Cardinality mismatches",
        "value_mismatches": "Source and target value mismatches",
        "constant_mismatches": "Constant value mismatches",
        "concat_mismatches": "Concatenation mismatches",
        "other": "Other issues",
    }
    ordered_keys = [
        "source_target_missing",
        "cardinality_violations",
        "value_mismatches",
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


def validate_mapping(
    spec_path: str,
    input_xml_path: str,
    output_xml_path: str,
    validation_mode: str = "strict",
) -> dict:
    """Validate output XML against mapping rules and source XML."""
    mode = (validation_mode or "strict").strip().lower()
    if mode not in {"strict", "lenient"}:
        raise ValueError("validation_mode must be either 'strict' or 'lenient'")

    df = read_mapping_table(spec_path)
    rules = extract_rules(df)

    src_tree, src_ns = parse_xml(input_xml_path)
    tgt_tree, tgt_ns = parse_xml(output_xml_path)
    src_root_name = _local_name(src_tree.getroot().tag)
    tgt_root_name = _local_name(tgt_tree.getroot().tag)

    errors: list[str] = []
    checked_rules = 0
    rule_stats = {
        "cardinality_violations": 0,
        "source_target_missing": 0,
        "value_mismatches": 0,
        "constant_mismatches": 0,
        "concat_mismatches": 0,
    }
    error_sections = {
        "cardinality_violations": [],
        "source_target_missing": [],
        "value_mismatches": [],
        "constant_mismatches": [],
        "concat_mismatches": [],
        "other": [],
    }
    skipped_rules: list[dict[str, str]] = []

    def _add_error(section: str, row: int, target_xpath: str, message: str) -> None:
        formatted = _format_error(row, target_xpath, message)
        errors.append(formatted)
        error_sections.setdefault(section, []).append(formatted)

    for i, rule in enumerate(rules, start=1):
        tgt = _normalize_xpath(rule["target_xpath"], tgt_root_name)
        src = _normalize_xpath(rule["source_xpath"], src_root_name)
        cond_text = rule["condition"]
        cond = " ".join(cond_text.lower().split())
        card = rule["cardinality"]

        checked_rules += 1

        src_vals = xpath_values(src_tree, src_ns, src) if src else []
        tgt_vals = xpath_values(tgt_tree, tgt_ns, tgt)

        parsed_cardinality = _parse_cardinality(card)
        if parsed_cardinality is not None:
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

        handled_condition = False

        is_if_source_rule = _is_if_source_map_rule(cond_text)
        is_direct_mapping_rule = bool(src) and (not cond_text.strip() or is_if_source_rule)

        if is_if_source_rule:
            handled_condition = True

        src_has_value = _has_non_empty_value(src_vals)
        tgt_has_value = _has_non_empty_value(tgt_vals)

        if is_direct_mapping_rule and src_has_value:
            if not tgt_has_value:
                rule_stats["source_target_missing"] += 1
                _add_error("source_target_missing", i, tgt, "Source exists but target is missing")
            elif "concat" not in cond:
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

        expected = _extract_constant_expected(cond_text)
        if expected is not None:
            handled_condition = True
            if not tgt_has_value:
                rule_stats["constant_mismatches"] += 1
                _add_error("constant_mismatches", i, tgt, "Required constant target is missing")
            elif _first_non_empty_value(tgt_vals) != expected:
                rule_stats["constant_mismatches"] += 1
                _add_error(
                    "constant_mismatches",
                    i,
                    tgt,
                    f"Constant mismatch: expected {expected}, got {_first_non_empty_value(tgt_vals)}",
                )

        concat_expected = _concat_expected(cond_text, src_vals)
        if concat_expected is not None:
            handled_condition = True
            if not tgt_has_value:
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

        if cond_text.strip() and not handled_condition:
            skipped_rules.append(
                {
                    "row": str(i),
                    "target_xpath": tgt,
                    "reason": "Unsupported condition pattern",
                    "condition": cond_text,
                }
            )

    strict_would_fail = bool(errors)
    valid = not strict_would_fail if mode == "strict" else True
    error_count = len(errors)
    warnings: list[str] = []
    if checked_rules == 0:
        warnings.append("No rules were checked against the target XML")
    if mode == "lenient" and strict_would_fail:
        warnings.append("Lenient mode enabled: validation contains errors but result is marked as valid")
    if skipped_rules:
        warnings.append(f"Skipped {len(skipped_rules)} rule(s) due to unsupported conditions")

    grouped_error_counts = {k: len(v) for k, v in error_sections.items()}
    top_critical_errors = _build_top_critical_errors(error_sections, limit=10)
    status = "PASS"
    if mode == "strict" and strict_would_fail:
        status = "FAIL"
    elif mode == "lenient" and strict_would_fail:
        status = "PASS_WITH_WARNINGS"

    human_summary = {
        "headline": (
            "No mapping issues found"
            if error_count == 0
            else f"Found {error_count} mapping issue(s); fix the top items first"
        ),
        "what_to_fix_first": [_humanize_issue_text(issue) for issue in top_critical_errors],
        "issue_breakdown": _human_issue_breakdown(grouped_error_counts),
        "checked_rules": checked_rules,
        "skipped_rules": len(skipped_rules),
    }

    return {
        "summary": {
            "status": status,
            "error_count": error_count,
            "grouped_error_counts": grouped_error_counts,
            "top_critical_errors": top_critical_errors,
        },
        "human_summary": human_summary,
        "valid": valid,
        "validation_mode": mode,
        "strict_would_fail": strict_would_fail,
        "checked_rules": checked_rules,
        "warnings": warnings,
        "rule_stats": rule_stats,
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
