from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

TARGET_RE = re.compile(r"Target:\s*([^|]+?)\s*\|")
ROW_RE = re.compile(r"Row\s+(\d+)\s*\|")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build fix-first summaries from a validation report")
    parser.add_argument("--report", required=True, help="Path to validation report JSON")
    parser.add_argument("--csv-out", required=True, help="Path to write grouped CSV summary")
    parser.add_argument("--json-out", required=True, help="Path to write grouped JSON summary")
    return parser.parse_args()


def _extract_target(error_text: str) -> str:
    match = TARGET_RE.search(error_text)
    return match.group(1).strip() if match else "(unknown)"


def _extract_row(error_text: str) -> int | None:
    match = ROW_RE.search(error_text)
    if not match:
        return None
    return int(match.group(1))


def build_grouped_summary(report: dict) -> tuple[list[dict], dict[str, int]]:
    error_sections = report.get("error_sections", {})
    grouped = defaultdict(lambda: {
        "count": 0,
        "rows": [],
        "categories": Counter(),
        "examples": [],
    })
    category_totals: dict[str, int] = {}

    for category, items in error_sections.items():
        if not isinstance(items, list):
            continue
        category_totals[category] = len(items)
        for item in items:
            target = _extract_target(item)
            row_no = _extract_row(item)
            bucket = grouped[target]
            bucket["count"] += 1
            bucket["categories"][category] += 1
            if row_no is not None:
                bucket["rows"].append(row_no)
            if len(bucket["examples"]) < 2:
                bucket["examples"].append(item)

    summary_rows: list[dict] = []
    for target, payload in grouped.items():
        rows_sorted = sorted(set(payload["rows"]))
        cats_sorted = sorted(payload["categories"].items(), key=lambda pair: (-pair[1], pair[0]))
        summary_rows.append(
            {
                "target_path": target,
                "issue_count": payload["count"],
                "row_numbers": rows_sorted,
                "category_breakdown": dict(cats_sorted),
                "examples": payload["examples"],
            }
        )

    summary_rows.sort(key=lambda item: (-item["issue_count"], item["target_path"]))
    return summary_rows, category_totals


def write_csv(path: Path, summary_rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["priority", "target_path", "issue_count", "row_numbers", "category_breakdown", "example"])
        for idx, item in enumerate(summary_rows, start=1):
            categories = "; ".join(
                f"{name}:{count}" for name, count in item["category_breakdown"].items()
            )
            rows = ",".join(str(r) for r in item["row_numbers"])
            example = item["examples"][0] if item["examples"] else ""
            writer.writerow([idx, item["target_path"], item["issue_count"], rows, categories, example])


def write_json(path: Path, report: dict, summary_rows: list[dict], category_totals: dict[str, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source_report": str(report.get("report_id", "")),
        "status": report.get("summary", {}).get("status"),
        "total_errors": report.get("summary", {}).get("error_count"),
        "category_totals": category_totals,
        "top_targets": summary_rows[:20],
        "all_targets": summary_rows,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> int:
    args = parse_args()
    report_path = Path(args.report)
    if not report_path.exists():
        raise FileNotFoundError(f"Report not found: {report_path}")

    report = json.loads(report_path.read_text(encoding="utf-8"))
    summary_rows, category_totals = build_grouped_summary(report)

    csv_out = Path(args.csv_out)
    json_out = Path(args.json_out)
    write_csv(csv_out, summary_rows)
    write_json(json_out, report, summary_rows, category_totals)

    print(f"Grouped targets: {len(summary_rows)}")
    print(f"CSV written to {csv_out}")
    print(f"JSON written to {json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
