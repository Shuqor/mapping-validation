import argparse
import json
from pathlib import Path


def _counts_from_report(report: dict) -> dict[str, int]:
    taxonomy = report.get("warning_taxonomy") if isinstance(report, dict) else {}
    if not isinstance(taxonomy, dict):
        return {"strict": 0, "heuristic": 0, "informational": 0, "total": 0}
    counts = taxonomy.get("counts") if isinstance(taxonomy.get("counts"), dict) else {}

    def _to_int(value: object) -> int:
        try:
            return max(int(value), 0)
        except (TypeError, ValueError):
            return 0

    return {
        "strict": _to_int(counts.get("strict", 0)),
        "heuristic": _to_int(counts.get("heuristic", 0)),
        "informational": _to_int(counts.get("informational", 0)),
        "total": _to_int(counts.get("total", 0)),
    }


def warning_taxonomy_drift_messages(report: dict, expected: dict[str, int]) -> list[str]:
    observed = _counts_from_report(report)
    messages: list[str] = []
    for key in ("strict", "heuristic", "informational", "total"):
        if key not in expected:
            continue
        exp = int(expected[key])
        obs = int(observed.get(key, 0))
        if obs != exp:
            messages.append(f"warning_taxonomy.{key} drift: observed={obs}, expected={exp}")
    return messages


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Warn-only drift checker for warning_taxonomy counts (never fails CI)."
    )
    parser.add_argument("--report", required=True, help="Path to validation report JSON")
    parser.add_argument("--expected-strict", type=int, help="Expected warning_taxonomy.counts.strict")
    parser.add_argument("--expected-heuristic", type=int, help="Expected warning_taxonomy.counts.heuristic")
    parser.add_argument("--expected-informational", type=int, help="Expected warning_taxonomy.counts.informational")
    parser.add_argument("--expected-total", type=int, help="Expected warning_taxonomy.counts.total")
    args = parser.parse_args()

    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    observed = _counts_from_report(report)
    expected = {
        key: value
        for key, value in {
            "strict": args.expected_strict,
            "heuristic": args.expected_heuristic,
            "informational": args.expected_informational,
            "total": args.expected_total,
        }.items()
        if value is not None
    }

    drift_messages = warning_taxonomy_drift_messages(report, expected)
    print(
        "Warning taxonomy counts: "
        f"strict={observed['strict']} heuristic={observed['heuristic']} "
        f"informational={observed['informational']} total={observed['total']}"
    )

    if drift_messages:
        print("Warning taxonomy drift detected (non-blocking):")
        for message in drift_messages:
            print(f"::warning::{message}")
    else:
        print("Warning taxonomy drift check: no drift detected")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
