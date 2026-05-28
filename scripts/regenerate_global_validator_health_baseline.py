import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.check_global_validator_health import build_global_validator_health_projection


DEFAULT_BASELINE_PATH = Path("results/ci/global_validator_health_baseline.json")


def regenerate_global_validator_health_baseline(
    output_path: Path,
    rules_dir: str = "rules",
    max_p95_runtime_seconds: float = 5.0,
) -> dict:
    projection = build_global_validator_health_projection(
        rules_dir=rules_dir,
        max_p95_runtime_seconds=max_p95_runtime_seconds,
    )
    payload = {
        "snapshot_name": "global_validator_health_baseline",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "rules_dir": str(Path(rules_dir).as_posix()),
        "projection": projection,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Regenerate global validator health baseline artifact")
    parser.add_argument("--rules-dir", default="rules", help="Directory containing mapping specs")
    parser.add_argument(
        "--baseline",
        default=str(DEFAULT_BASELINE_PATH),
        help="Baseline artifact path",
    )
    parser.add_argument(
        "--max-p95-runtime-seconds",
        type=float,
        default=5.0,
        help="Maximum allowed p95 runtime seconds for curated runtime checks",
    )
    args = parser.parse_args()

    payload = regenerate_global_validator_health_baseline(
        output_path=Path(args.baseline),
        rules_dir=args.rules_dir,
        max_p95_runtime_seconds=args.max_p95_runtime_seconds,
    )
    runtime = payload["projection"]["curated_runtime"]
    print(
        f"Updated baseline: {args.baseline} | "
        f"runs={runtime['run_count']} runtime_failures={runtime['failure_count']} "
        f"total_errors={runtime['total_errors']} p95={runtime['performance']['p95_runtime_seconds']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
