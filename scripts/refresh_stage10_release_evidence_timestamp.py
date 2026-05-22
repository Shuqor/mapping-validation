import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def refresh_timestamp(evidence_path: Path) -> dict:
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    payload["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    evidence_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh generated_at_utc in Stage 10 release evidence JSON")
    parser.add_argument(
        "--evidence",
        default="results/ci/stage10_release_evidence.json",
        help="Path to Stage 10 release evidence JSON",
    )
    args = parser.parse_args()

    evidence_path = Path(args.evidence)
    if not evidence_path.exists():
        print(f"Missing evidence file: {evidence_path}")
        return 1

    payload = refresh_timestamp(evidence_path)
    print(f"Refreshed generated_at_utc: {payload['generated_at_utc']}")
    print(f"Updated evidence file: {evidence_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
