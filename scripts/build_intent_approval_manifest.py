from __future__ import annotations

import argparse
import json
from pathlib import Path


def _confidence_rank(label: str) -> int:
    normalized = str(label or "").strip().lower()
    if normalized == "high":
        return 2
    if normalized == "medium":
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Build approval manifest for medium/low intent pattern promotions")
    parser.add_argument(
        "--suggestions",
        default="results/ci/intent_pattern_suggestions.json",
        help="Suggestions artifact path",
    )
    parser.add_argument(
        "--min-confidence",
        choices=["high", "medium"],
        default="medium",
        help="Minimum confidence to include as approval candidates",
    )
    parser.add_argument(
        "--min-count",
        type=int,
        default=2,
        help="Minimum count to include as approval candidates",
    )
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=100,
        help="Maximum number of candidates written",
    )
    parser.add_argument(
        "--out",
        default="results/ci/intent_pattern_approval_manifest.json",
        help="Approval manifest output path",
    )
    args = parser.parse_args()

    payload = json.loads(Path(args.suggestions).read_text(encoding="utf-8"))
    suggestions = payload.get("suggestions") if isinstance(payload.get("suggestions"), list) else []

    min_rank = _confidence_rank(args.min_confidence)
    approved_patterns: list[dict] = []

    for row in suggestions:
        if not isinstance(row, dict):
            continue
        conf = str(row.get("confidence") or "").strip().lower()
        cnt = int(row.get("count") or 0)
        if _confidence_rank(conf) < min_rank:
            continue
        if cnt < int(args.min_count):
            continue

        approved_patterns.append(
            {
                "condition": str(row.get("condition") or "").strip(),
                "proposed_regex": str(row.get("proposed_regex") or "").strip(),
                "confidence": conf,
                "count": cnt,
                "source_backed_ratio": float(row.get("source_backed_ratio") or 0.0),
                "approval_status": "approved",
            }
        )
        if len(approved_patterns) >= int(args.max_candidates):
            break

    out_payload = {
        "source_suggestions": str(Path(args.suggestions).as_posix()),
        "approval_policy": {
            "min_confidence": args.min_confidence,
            "min_count": int(args.min_count),
            "max_candidates": int(args.max_candidates),
        },
        "approved_pattern_count": len(approved_patterns),
        "approved_patterns": approved_patterns,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out_payload, indent=2) + "\n", encoding="utf-8")

    print(f"Approval manifest created: {out_path.as_posix()}")
    print(f"Approved patterns: {len(approved_patterns)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
