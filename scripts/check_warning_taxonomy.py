import argparse
import json
from pathlib import Path


def check_warning_taxonomy(report: dict) -> list[str]:
    issues: list[str] = []
    warnings = report.get("warnings") if isinstance(report, dict) else None
    if not isinstance(warnings, list):
        return ["warnings must be a list"]

    taxonomy = report.get("warning_taxonomy") if isinstance(report, dict) else None
    if not isinstance(taxonomy, dict):
        return ["warning_taxonomy must be an object"]

    counts = taxonomy.get("counts")
    if not isinstance(counts, dict):
        return ["warning_taxonomy.counts must be an object"]

    expected_keys = ("strict", "heuristic", "informational", "total")
    numeric_counts: dict[str, int] = {}
    for key in expected_keys:
        if key not in counts:
            issues.append(f"warning_taxonomy.counts.{key} is required")
            continue
        value = counts.get(key)
        if not isinstance(value, int) or value < 0:
            issues.append(f"warning_taxonomy.counts.{key} must be a non-negative integer")
            continue
        numeric_counts[key] = value

    list_fields = (
        ("strict_warnings", "strict"),
        ("heuristic_warnings", "heuristic"),
        ("informational_warnings", "informational"),
    )
    for field, count_key in list_fields:
        values = taxonomy.get(field)
        if not isinstance(values, list):
            issues.append(f"warning_taxonomy.{field} must be a list")
            continue
        if count_key in numeric_counts and len(values) != numeric_counts[count_key]:
            issues.append(
                f"warning_taxonomy.{field} length ({len(values)}) must match warning_taxonomy.counts.{count_key} ({numeric_counts[count_key]})"
            )

    if all(key in numeric_counts for key in ("strict", "heuristic", "informational", "total")):
        split_total = numeric_counts["strict"] + numeric_counts["heuristic"] + numeric_counts["informational"]
        if split_total != numeric_counts["total"]:
            issues.append(
                f"warning_taxonomy count split ({split_total}) must equal warning_taxonomy.counts.total ({numeric_counts['total']})"
            )
        if numeric_counts["total"] != len(warnings):
            issues.append(
                f"warning_taxonomy.counts.total ({numeric_counts['total']}) must equal len(warnings) ({len(warnings)})"
            )

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Check warning taxonomy contract in a validation report JSON")
    parser.add_argument("--report", required=True, help="Path to validation report JSON")
    args = parser.parse_args()

    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    issues = check_warning_taxonomy(report)
    if issues:
        print("Warning taxonomy contract check failed:")
        for issue in issues:
            print(f"- {issue}")
        return 1

    print("Warning taxonomy contract check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
