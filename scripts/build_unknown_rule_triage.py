from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path


def _normalize_condition_text(value: str) -> str:
    text = " ".join(str(value or "").strip().split())
    text = text.lower()
    text = re.sub(r"[^a-z0-9_\s]", " ", text)
    return " ".join(text.split())


def _tokenize(text: str) -> set[str]:
    stop = {
        "if",
        "then",
        "map",
        "to",
        "the",
        "a",
        "an",
        "and",
        "or",
        "is",
        "are",
        "of",
        "with",
        "when",
        "else",
        "target",
        "source",
    }
    return {tok for tok in re.findall(r"[a-z0-9_]+", text) if tok and tok not in stop}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    inter = len(left & right)
    union = len(left | right)
    return inter / union if union else 0.0


def _load_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return payload


def _load_calibration_threshold(path: Path) -> float:
    if not path.exists():
        return 0.8
    payload = _load_json(path)
    buckets = payload.get("buckets") if isinstance(payload.get("buckets"), list) else []
    # Pick the lowest bucket with acceptable false-positive rate.
    for bucket in buckets:
        if not isinstance(bucket, dict):
            continue
        fp_rate = float(bucket.get("false_positive_rate", 1.0) or 1.0)
        bucket_range = str(bucket.get("bucket", "") or "")
        if fp_rate <= 0.08 and "-" in bucket_range:
            left = bucket_range.split("-", 1)[0].strip()
            try:
                return float(left)
            except ValueError:
                continue
    return 0.8


def _decision_outcome(decision: dict) -> str:
    outcome = str(decision.get("decision_outcome") or "").strip().upper()
    if outcome:
        return outcome
    status = str(decision.get("status") or "").strip().lower()
    if status in {"unsupported", "parsed_only"}:
        return "ABSTAIN"
    return "PASS"


def _collect_known_and_unknown(decisions: list[dict], abstain_floor: float) -> tuple[list[dict], list[dict]]:
    known: list[dict] = []
    unknown: list[dict] = []
    for d in decisions:
        if not isinstance(d, dict):
            continue
        status = str(d.get("status") or "").strip().lower()
        confidence = float(d.get("confidence", 0.0) or 0.0)
        outcome = _decision_outcome(d)

        norm = _normalize_condition_text(str(d.get("condition") or d.get("reason") or ""))
        tokens = _tokenize(norm)
        row = {
            "row": int(d.get("row", 0) or 0),
            "target_xpath": str(d.get("target_xpath") or ""),
            "source_xpath": str(d.get("source_xpath") or ""),
            "family": str(d.get("family") or ""),
            "status": status,
            "reason": str(d.get("reason") or ""),
            "reason_code": str(d.get("reason_code") or ""),
            "confidence": confidence,
            "decision_outcome": outcome,
            "condition_normalized": norm,
            "tokens": sorted(tokens),
        }

        is_unknown = (
            outcome == "ABSTAIN"
            or status in {"unsupported", "parsed_only"}
            or confidence < abstain_floor
        )
        if is_unknown:
            unknown.append(row)
        else:
            known.append(row)
    return known, unknown


def _cluster_unknown_rows(rows: list[dict], similarity_threshold: float) -> list[dict]:
    clusters: list[dict] = []
    for row in rows:
        row_tokens = set(row.get("tokens") or [])
        best_idx = -1
        best_score = 0.0
        for idx, cluster in enumerate(clusters):
            score = _jaccard(row_tokens, set(cluster.get("centroid_tokens") or []))
            if score > best_score:
                best_idx = idx
                best_score = score

        if best_idx >= 0 and best_score >= similarity_threshold:
            cluster = clusters[best_idx]
            cluster_rows = cluster["rows"]
            cluster_rows.append(row)
            merged_tokens = Counter()
            for item in cluster_rows:
                merged_tokens.update(item.get("tokens") or [])
            cluster["centroid_tokens"] = [tok for tok, _ in merged_tokens.most_common(12)]
            cluster["size"] = len(cluster_rows)
        else:
            clusters.append(
                {
                    "cluster_id": f"u{len(clusters) + 1:03d}",
                    "size": 1,
                    "centroid_tokens": list(row.get("tokens") or [])[:12],
                    "rows": [row],
                }
            )

    for cluster in clusters:
        rows_sorted = sorted(cluster["rows"], key=lambda item: (int(item.get("row", 0)), item.get("target_xpath", "")))
        cluster["rows"] = rows_sorted
        cluster["status_breakdown"] = dict(Counter(item.get("status", "") for item in rows_sorted))
        cluster["family_breakdown"] = dict(Counter(item.get("family", "") or "unknown" for item in rows_sorted))
    clusters.sort(key=lambda item: (-int(item.get("size", 0)), item.get("cluster_id", "")))
    return clusters


def _retrieve_nearest_known(unknown_row: dict, known_rows: list[dict], top_k: int = 3) -> list[dict]:
    scored: list[tuple[float, dict]] = []
    unknown_tokens = set(unknown_row.get("tokens") or [])
    for known in known_rows:
        known_tokens = set(known.get("tokens") or [])
        similarity = _jaccard(unknown_tokens, known_tokens)
        if similarity <= 0.0:
            continue
        scored.append(
            (
                similarity,
                {
                    "row": int(known.get("row", 0) or 0),
                    "family": str(known.get("family") or ""),
                    "status": str(known.get("status") or ""),
                    "confidence": float(known.get("confidence", 0.0) or 0.0),
                    "target_xpath": str(known.get("target_xpath") or ""),
                    "similarity": round(similarity, 4),
                },
            )
        )
    scored.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in scored[:top_k]]


def _counterfactual_checks(row: dict) -> list[str]:
    checks: list[str] = []
    if not str(row.get("source_xpath") or "").strip() and str(row.get("status") or "") == "enforced":
        checks.append("enforced_without_source_path")
    cond = str(row.get("condition_normalized") or "")
    if "no mapping" in cond and str(row.get("status") or "") == "enforced":
        checks.append("instruction_only_conflicts_with_enforced")
    if "direct map" in cond and str(row.get("source_xpath") or "").strip() and str(row.get("status") or "") == "unsupported":
        checks.append("direct_map_like_rule_marked_unsupported")
    return checks


def _propose_patch_patterns(cluster: dict) -> list[dict]:
    token_candidates = [tok for tok in cluster.get("centroid_tokens") or [] if len(tok) >= 4][:4]
    proposals: list[dict] = []
    for tok in token_candidates:
        escaped_token = re.escape(tok)
        escaped_token = escaped_token.replace("\\_", "_")
        regex = r"\\b" + escaped_token + r"\\b"
        proposals.append(
            {
                "type": "regex_candidate",
                "target_config": "rules/semantic_profiles.json:profiles.generic.intent_patterns.direct_map_comment_patterns",
                "pattern": regex,
                "rationale": f"Frequent token in unknown cluster {cluster.get('cluster_id', '')}",
            }
        )
    return proposals


def build_unknown_rule_triage(
    report: dict,
    *,
    calibration: dict | None = None,
    similarity_threshold: float = 0.55,
) -> dict:
    decisions = report.get("rule_decisions") if isinstance(report.get("rule_decisions"), list) else []
    calibration_floor = 0.8
    if isinstance(calibration, dict):
        buckets = calibration.get("buckets") if isinstance(calibration.get("buckets"), list) else []
        # compute via helper semantics on the payload path would be redundant, derive directly.
        for bucket in buckets:
            if not isinstance(bucket, dict):
                continue
            fp_rate = float(bucket.get("false_positive_rate", 1.0) or 1.0)
            label = str(bucket.get("bucket", "") or "")
            if fp_rate <= 0.08 and "-" in label:
                try:
                    calibration_floor = float(label.split("-", 1)[0])
                    break
                except ValueError:
                    continue

    known_rows, unknown_rows = _collect_known_and_unknown(decisions, abstain_floor=calibration_floor)
    clusters = _cluster_unknown_rows(unknown_rows, similarity_threshold=similarity_threshold)

    for cluster in clusters:
        for row in cluster.get("rows", []):
            row["nearest_known"] = _retrieve_nearest_known(row, known_rows)
            row["counterfactual_flags"] = _counterfactual_checks(row)
        cluster["suggested_parser_patches"] = _propose_patch_patterns(cluster)
        cluster["review_priority"] = round(
            (int(cluster.get("size", 0)) * 1.5)
            + sum(1 for r in cluster.get("rows", []) if str(r.get("status", "")) == "unsupported")
            + sum(len(r.get("counterfactual_flags", [])) for r in cluster.get("rows", [])),
            2,
        )

    top_clusters = sorted(clusters, key=lambda c: (-float(c.get("review_priority", 0.0)), c.get("cluster_id", "")))

    unknown_count = len(unknown_rows)
    total_decisions = len([d for d in decisions if isinstance(d, dict)])
    unknown_ratio = round((unknown_count / total_decisions), 4) if total_decisions else 0.0

    status_breakdown = dict(Counter(row.get("status", "") for row in unknown_rows))
    family_breakdown = dict(Counter((row.get("family") or "unknown") for row in unknown_rows))

    return {
        "summary": {
            "total_decisions": total_decisions,
            "known_count": len(known_rows),
            "unknown_count": unknown_count,
            "unknown_ratio": unknown_ratio,
            "abstain_confidence_floor": calibration_floor,
            "cluster_count": len(top_clusters),
            "status_breakdown": status_breakdown,
            "family_breakdown": family_breakdown,
        },
        "closed_loop_program": {
            "cadence": "weekly",
            "steps": [
                "review_top_unknown_clusters",
                "approve_parser_or_intent_pattern_patch",
                "add_or_update_targeted_tests",
                "re-run_quality_gates_and_refresh_baselines",
            ],
            "exit_metrics": {
                "max_unknown_ratio": 0.1,
                "max_unsupported_ratio": 0.05,
                "max_oldest_cluster_age_days": 14,
            },
        },
        "clusters": top_clusters,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build unknown-rule triage artifact with clustering and retrieval evidence")
    parser.add_argument("--report", default="results/ci/stage10_spec_coverage_runtime.json", help="Validation report JSON")
    parser.add_argument("--calibration", default="results/ci/confidence_calibration.json", help="Calibration artifact JSON")
    parser.add_argument("--output", default="results/ci/unknown_rule_triage.json", help="Output triage JSON")
    parser.add_argument("--similarity-threshold", type=float, default=0.55, help="Jaccard threshold for cluster assignment")
    parser.add_argument("--max-unknown-ratio", type=float, default=0.25, help="Fail when unknown_ratio exceeds this threshold")
    parser.add_argument("--fail-on-findings", action="store_true", help="Return non-zero when unknown ratio exceeds threshold")
    args = parser.parse_args()

    report_path = Path(args.report)
    calibration_path = Path(args.calibration)
    output_path = Path(args.output)

    report = _load_json(report_path)
    calibration = _load_json(calibration_path) if calibration_path.exists() else {}
    payload = build_unknown_rule_triage(
        report,
        calibration=calibration,
        similarity_threshold=float(args.similarity_threshold),
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    summary = payload.get("summary", {}) if isinstance(payload.get("summary"), dict) else {}
    unknown_ratio = float(summary.get("unknown_ratio", 0.0) or 0.0)
    print(
        "Unknown triage built: "
        f"unknown_count={int(summary.get('unknown_count', 0) or 0)} "
        f"unknown_ratio={unknown_ratio:.4f} "
        f"clusters={int(summary.get('cluster_count', 0) or 0)}"
    )
    print(f"Artifact written: {output_path.as_posix()}")

    if args.fail_on_findings and unknown_ratio > float(args.max_unknown_ratio):
        print(
            "Unknown ratio exceeded threshold: "
            f"ratio={unknown_ratio:.4f} max={float(args.max_unknown_ratio):.4f}"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
