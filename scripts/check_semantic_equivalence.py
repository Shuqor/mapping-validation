import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.validate import _canonicalize_semantic_condition_with_trace


def find_semantic_equivalence_issues(report: dict) -> list[str]:
    skipped = report.get("skipped_rules") if isinstance(report.get("skipped_rules"), list) else []
    by_normalized: dict[str, set[str]] = defaultdict(set)

    for item in skipped:
        if not isinstance(item, dict):
            continue
        raw_condition = str(item.get("condition") or "").strip()
        normalized = str(item.get("normalized_condition") or "").strip()
        if not normalized:
            normalized, _ = _canonicalize_semantic_condition_with_trace(raw_condition)
        if not normalized:
            continue
        family = str(item.get("nearest_family") or item.get("detected_pattern") or "unknown").strip().lower() or "unknown"
        by_normalized[normalized].add(family)

    issues: list[str] = []
    for normalized, families in sorted(by_normalized.items()):
        concrete_families = {family for family in families if family and family != "unknown"}
        if len(concrete_families) > 1:
            issues.append(
                "Equivalent condition maps to multiple families: "
                f"normalized='{normalized}' families={sorted(concrete_families)}"
            )

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Check semantic-equivalence consistency for unsupported rules")
    parser.add_argument("--report", required=True, help="Path to validation report JSON")
    args = parser.parse_args()

    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    issues = find_semantic_equivalence_issues(report)
    if issues:
        print("Semantic equivalence check failed:")
        for issue in issues:
            print(f"- {issue}")
        return 1

    print("Semantic equivalence check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
