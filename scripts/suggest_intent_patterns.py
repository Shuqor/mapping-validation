from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.spec_reader import extract_rules, read_mapping_table
from core.validate import validate_spec_coverage


def _load_specs_from_probe(probe_path: Path) -> list[Path]:
    payload = json.loads(probe_path.read_text(encoding="utf-8"))
    rows = payload.get("results")
    if not isinstance(rows, list):
        raise ValueError("Probe file must contain a 'results' list")
    specs: list[Path] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        spec = str(row.get("spec") or "").strip()
        if spec:
            specs.append(Path(spec))
    return specs


def _load_existing_patterns(config_path: Path) -> list[re.Pattern[str]]:
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    profiles = payload.get("profiles") if isinstance(payload, dict) else None
    if not isinstance(profiles, dict):
        return []
    generic = profiles.get("generic") if isinstance(profiles.get("generic"), dict) else {}
    intent = generic.get("intent_patterns") if isinstance(generic.get("intent_patterns"), dict) else {}
    patterns = intent.get("direct_map_comment_patterns") if isinstance(intent.get("direct_map_comment_patterns"), list) else []

    compiled: list[re.Pattern[str]] = []
    for pattern in patterns:
        try:
            compiled.append(re.compile(str(pattern), flags=re.IGNORECASE))
        except re.error:
            continue
    return compiled


def _build_regex_from_phrase(phrase: str) -> str:
    cleaned = " ".join((phrase or "").strip().split())
    escaped = re.escape(cleaned)
    escaped = escaped.replace(r"\ ", r"\s+")
    return rf"\b{escaped}\b"


def _is_already_covered(phrase: str, compiled_patterns: list[re.Pattern[str]]) -> bool:
    normalized = " ".join((phrase or "").strip().split())
    if not normalized:
        return True
    for pattern in compiled_patterns:
        if pattern.search(normalized):
            return True
    return False


def _collect_parsed_only_conditions(spec_paths: list[Path]) -> tuple[Counter[str], dict[str, list[dict[str, str]]], Counter[str]]:
    counts: Counter[str] = Counter()
    source_backed_counts: Counter[str] = Counter()
    examples: dict[str, list[dict[str, str]]] = defaultdict(list)

    for spec_path in spec_paths:
        rules = extract_rules(read_mapping_table(str(spec_path)))
        report = validate_spec_coverage(str(spec_path))
        decisions = report.get("rule_decisions") if isinstance(report.get("rule_decisions"), list) else []

        for decision in decisions:
            if str(decision.get("status") or "").strip().lower() != "parsed_only":
                continue
            if "procedural/instruction-only" not in str(decision.get("reason") or "").lower():
                continue

            row_index = int(decision.get("row") or 0) - 1
            if row_index < 0 or row_index >= len(rules):
                continue

            rule = rules[row_index]
            condition = " ".join(str(rule.get("condition") or "").strip().split())
            source_xpath = str(rule.get("source_xpath") or "").strip()
            target_xpath = str(rule.get("target_xpath") or "").strip()

            if not condition:
                continue

            counts[condition] += 1
            if source_xpath:
                source_backed_counts[condition] += 1

            if len(examples[condition]) < 3:
                examples[condition].append(
                    {
                        "spec": spec_path.name,
                        "source_xpath": source_xpath,
                        "target_xpath": target_xpath,
                    }
                )

    return counts, examples, source_backed_counts


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Suggest semantic intent regex patterns by mining parsed-only procedural rules "
            "that still have source mappings."
        )
    )
    parser.add_argument(
        "--probe",
        default="results/ci/new_rules_spec_coverage_probe_after_patch2.json",
        help="Path to a probe JSON containing a 'results' list with spec paths",
    )
    parser.add_argument(
        "--semantic-config",
        default="rules/semantic_profiles.json",
        help="Path to semantic profile config",
    )
    parser.add_argument(
        "--min-count",
        type=int,
        default=2,
        help="Minimum number of occurrences to include a suggestion",
    )
    parser.add_argument(
        "--out",
        default="results/ci/intent_pattern_suggestions.json",
        help="Output path for suggestions artifact",
    )
    args = parser.parse_args()

    probe_path = Path(args.probe)
    semantic_config_path = Path(args.semantic_config)
    out_path = Path(args.out)

    spec_paths = _load_specs_from_probe(probe_path)
    existing_patterns = _load_existing_patterns(semantic_config_path)

    counts, examples, source_backed_counts = _collect_parsed_only_conditions(spec_paths)

    suggestions = []
    for condition, count in counts.most_common():
        if count < int(args.min_count):
            continue
        source_count = int(source_backed_counts.get(condition, 0))
        if source_count == 0:
            continue
        if _is_already_covered(condition, existing_patterns):
            continue

        source_ratio = round(source_count / count, 4) if count else 0.0
        confidence = "high" if source_ratio >= 0.9 and count >= 3 else "medium"
        suggestions.append(
            {
                "condition": condition,
                "count": count,
                "source_backed_count": source_count,
                "source_backed_ratio": source_ratio,
                "proposed_regex": _build_regex_from_phrase(condition),
                "confidence": confidence,
                "examples": examples.get(condition, []),
            }
        )

    grouped: dict[str, list[dict]] = {
        "high_count_ge_5": [],
        "high_count_lt_5": [],
        "medium_count_ge_5": [],
        "medium_count_lt_5": [],
    }
    for item in suggestions:
        conf = str(item.get("confidence", "") or "").strip().lower()
        cnt = int(item.get("count", 0) or 0)
        if conf == "high" and cnt >= 5:
            grouped["high_count_ge_5"].append(item)
        elif conf == "high":
            grouped["high_count_lt_5"].append(item)
        elif cnt >= 5:
            grouped["medium_count_ge_5"].append(item)
        else:
            grouped["medium_count_lt_5"].append(item)

    payload = {
        "probe_path": str(probe_path.as_posix()),
        "semantic_config": str(semantic_config_path.as_posix()),
        "spec_count": len(spec_paths),
        "min_count": int(args.min_count),
        "candidate_count": len(suggestions),
        "grouped_suggestions": grouped,
        "approval_policy": {
            "auto_apply_allowed_confidence": ["high"],
            "review_required_confidence": ["medium", "low"],
        },
        "suggestions": suggestions,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print(f"Specs scanned: {len(spec_paths)}")
    print(f"Candidates found: {len(suggestions)}")
    print(f"Suggestion artifact: {out_path.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
