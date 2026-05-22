import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def _as_count_map(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, int] = {}
    for key, count in value.items():
        try:
            result[str(key)] = int(count)
        except (TypeError, ValueError):
            continue
    return result


def build_shadow_delta(strict_report: dict, shadow_report: dict) -> dict:
    strict_counts = _as_count_map((strict_report.get("summary") or {}).get("grouped_error_counts"))
    shadow_counts = _as_count_map((shadow_report.get("summary") or {}).get("grouped_error_counts"))
    keys = sorted(set(strict_counts) | set(shadow_counts))

    deltas = []
    for key in keys:
        strict_value = int(strict_counts.get(key, 0))
        shadow_value = int(shadow_counts.get(key, 0))
        deltas.append(
            {
                "type": key,
                "strict": strict_value,
                "shadow": shadow_value,
                "delta": shadow_value - strict_value,
            }
        )

    strict_summary = strict_report.get("summary") or {}
    shadow_summary = shadow_report.get("summary") or {}
    return {
        "snapshot_name": "shadow_delta",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "strict": {
            "report_id": strict_report.get("report_id", ""),
            "status": strict_summary.get("status", "unknown"),
            "error_count": int(strict_report.get("error_count", strict_summary.get("error_count", 0)) or 0),
        },
        "shadow": {
            "report_id": shadow_report.get("report_id", ""),
            "status": shadow_summary.get("status", "unknown"),
            "error_count": int(shadow_report.get("error_count", shadow_summary.get("error_count", 0)) or 0),
        },
        "grouped_error_deltas": deltas,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build shadow delta artifact from strict and shadow report JSON files")
    parser.add_argument("--strict-report", required=True, help="Path to strict-mode report JSON")
    parser.add_argument("--shadow-report", required=True, help="Path to shadow-mode report JSON")
    parser.add_argument("--output", required=True, help="Path to write shadow delta JSON")
    args = parser.parse_args()

    strict_payload = json.loads(Path(args.strict_report).read_text(encoding="utf-8"))
    shadow_payload = json.loads(Path(args.shadow_report).read_text(encoding="utf-8"))
    delta = build_shadow_delta(strict_payload, shadow_payload)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(delta, indent=2) + "\n", encoding="utf-8")
    print(f"Shadow delta written to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())