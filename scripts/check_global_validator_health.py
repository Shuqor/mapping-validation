import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from time import perf_counter


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import core.validate as validate_module
from scripts.regenerate_rules_extraction_baseline import project_rules_extraction_baseline


DEFAULT_CURATED_RUNS = [
    {
        "id": "xml_lenient",
        "spec": "rules/spec.xlsx",
        "input": "samples/input.xml",
        "output": "samples/output.xml",
        "mode": "lenient",
    },
    {
        "id": "x12_lenient",
        "spec": "rules/spec.xlsx",
        "input": "samples/input.x12",
        "output": "samples/output.x12",
        "mode": "lenient",
    },
    {
        "id": "edifact_lenient",
        "spec": "rules/spec.xlsx",
        "input": "samples/input.edifact",
        "output": "samples/output.edifact",
        "mode": "lenient",
    },
]


DEFAULT_DISALLOWED_STATUSES = ("FAIL",)


def _to_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _to_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]

    rank = max(0.0, min(float(percentile), 100.0)) / 100.0 * (len(ordered) - 1)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    fraction = rank - low
    return ordered[low] + (ordered[high] - ordered[low]) * fraction


def _build_rules_folder_summary(rules_projection: dict) -> dict:
    specs = rules_projection.get("specs") if isinstance(rules_projection.get("specs"), list) else []

    confidence_counter: Counter[str] = Counter()
    status_counter: Counter[str] = Counter()
    total_ambiguities = 0

    for spec in specs:
        if not isinstance(spec, dict):
            continue
        confidence_counter[str(spec.get("confidence") or "unknown")] += 1
        status_counter[str(spec.get("status") or "unknown")] += 1
        total_ambiguities += _to_int(spec.get("ambiguity_count"), 0)

    return {
        "spec_count": _to_int(rules_projection.get("spec_count"), 0),
        "failure_count": _to_int(rules_projection.get("failure_count"), 0),
        "total_ambiguities": total_ambiguities,
        "status_counts": dict(sorted(status_counter.items())),
        "confidence_counts": dict(sorted(confidence_counter.items())),
    }


def _run_curated_validation(run_cfg: dict) -> dict:
    spec = str(run_cfg.get("spec") or "")
    input_path = Path(str(run_cfg.get("input") or ""))
    output_path = Path(str(run_cfg.get("output") or ""))
    mode = str(run_cfg.get("mode") or "strict")

    start = perf_counter()
    report = validate_module.validate_mapping_from_payload_bytes(
        spec_path=spec,
        input_payload=input_path.read_bytes(),
        input_filename=input_path.name,
        output_payload=output_path.read_bytes(),
        output_filename=output_path.name,
        validation_mode=mode,
    )
    runtime_seconds = perf_counter() - start

    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    parser_diag = report.get("parser_diagnostics") if isinstance(report.get("parser_diagnostics"), dict) else {}
    rule_gap = report.get("rule_gap_summary") if isinstance(report.get("rule_gap_summary"), dict) else {}
    fingerprint = report.get("validation_fingerprint") if isinstance(report.get("validation_fingerprint"), dict) else {}

    return {
        "id": str(run_cfg.get("id") or "unnamed"),
        "spec": spec,
        "input": input_path.as_posix(),
        "output": output_path.as_posix(),
        "mode": mode,
        "status": str(summary.get("status") or "unknown"),
        "error_count": _to_int(report.get("error_count", summary.get("error_count", 0)), 0),
        "checked_rules": _to_int(report.get("checked_rules"), 0),
        "unsupported_rules": _to_int(rule_gap.get("unsupported_rules"), 0),
        "parser_status": str(summary.get("parser_status") or parser_diag.get("status") or "unknown"),
        "parser_confidence": str(summary.get("parser_confidence") or parser_diag.get("confidence") or "unknown"),
        "runtime_seconds": round(runtime_seconds, 6),
        "fingerprint": {
            "validator_version": str(fingerprint.get("validator_version") or ""),
            "parser_version": str(fingerprint.get("parser_version") or ""),
            "mode": str(fingerprint.get("mode") or ""),
            "exception_profile_hash": str(fingerprint.get("exception_profile_hash") or ""),
        },
    }


def build_global_validator_health_projection(
    *,
    rules_dir: str = "rules",
    curated_runs: list[dict] | None = None,
    max_p95_runtime_seconds: float = 5.0,
) -> dict:
    run_configs = curated_runs or DEFAULT_CURATED_RUNS
    rules_projection = project_rules_extraction_baseline(rules_dir=rules_dir)
    rules_summary = _build_rules_folder_summary(rules_projection)

    run_results: list[dict] = []
    run_failures: list[dict] = []
    for run_cfg in run_configs:
        try:
            run_results.append(_run_curated_validation(run_cfg))
        except Exception as exc:  # noqa: BLE001
            run_failures.append(
                {
                    "id": str(run_cfg.get("id") or "unnamed"),
                    "reason": f"runtime_exception: {exc}",
                }
            )

    status_counter: Counter[str] = Counter()
    total_errors = 0
    total_unsupported = 0
    total_checked_rules = 0
    runtimes: list[float] = []
    for result in run_results:
        status_counter[result.get("status", "unknown")] += 1
        total_errors += _to_int(result.get("error_count"), 0)
        total_unsupported += _to_int(result.get("unsupported_rules"), 0)
        total_checked_rules += _to_int(result.get("checked_rules"), 0)
        runtimes.append(_to_float(result.get("runtime_seconds"), 0.0))

    p95_runtime_seconds = round(_percentile(runtimes, 95.0), 6)
    max_runtime_seconds = round(max(runtimes), 6) if runtimes else 0.0

    return {
        "rules_folder": rules_summary,
        "curated_runtime": {
            "run_count": len(run_configs),
            "success_count": len(run_results),
            "failure_count": len(run_failures),
            "failures": sorted(run_failures, key=lambda item: item.get("id", "")),
            "status_counts": dict(sorted(status_counter.items())),
            "total_errors": total_errors,
            "total_unsupported_rules": total_unsupported,
            "total_checked_rules": total_checked_rules,
            "performance": {
                "p95_runtime_seconds": p95_runtime_seconds,
                "max_runtime_seconds": max_runtime_seconds,
                "max_p95_runtime_seconds": round(float(max_p95_runtime_seconds), 6),
            },
            "runs": sorted(run_results, key=lambda item: item.get("id", "")),
        },
    }


def evaluate_global_validator_health(projection: dict) -> list[str]:
    issues: list[str] = []

    rules_folder = projection.get("rules_folder") if isinstance(projection.get("rules_folder"), dict) else {}
    runtime = projection.get("curated_runtime") if isinstance(projection.get("curated_runtime"), dict) else {}
    runtime_runs = runtime.get("runs") if isinstance(runtime.get("runs"), list) else []
    performance = runtime.get("performance") if isinstance(runtime.get("performance"), dict) else {}

    if _to_int(rules_folder.get("failure_count"), 0) > 0:
        issues.append(f"rules_folder.failure_count={rules_folder.get('failure_count')} (expected 0)")
    if _to_int(rules_folder.get("total_ambiguities"), 0) > 0:
        issues.append(f"rules_folder.total_ambiguities={rules_folder.get('total_ambiguities')} (expected 0)")
    if _to_int(runtime.get("failure_count"), 0) > 0:
        issues.append(f"curated_runtime.failure_count={runtime.get('failure_count')} (expected 0)")

    disallowed_statuses = {status.upper() for status in DEFAULT_DISALLOWED_STATUSES}
    seen_disallowed = sorted(
        {
            str(run.get("status") or "").upper()
            for run in runtime_runs
            if str(run.get("status") or "").upper() in disallowed_statuses
        }
    )
    if seen_disallowed:
        issues.append(
            "curated_runtime contains disallowed statuses: "
            f"{', '.join(seen_disallowed)}"
        )

    p95_runtime = _to_float(performance.get("p95_runtime_seconds"), 0.0)
    max_p95_runtime = _to_float(performance.get("max_p95_runtime_seconds"), 0.0)
    if max_p95_runtime > 0 and p95_runtime > max_p95_runtime:
        issues.append(
            "curated_runtime.p95_runtime_seconds="
            f"{p95_runtime:.6f} exceeds max_p95_runtime_seconds={max_p95_runtime:.6f}"
        )

    return issues


def _stable_projection_view(payload: dict) -> dict:
    """Remove volatile runtime timing fields for stable baseline drift checks."""
    projection = dict(payload)
    runtime = dict(projection.get("curated_runtime") or {})
    performance = dict(runtime.get("performance") or {})
    performance.pop("p95_runtime_seconds", None)
    performance.pop("max_runtime_seconds", None)
    runtime["performance"] = performance

    normalized_runs = []
    for run in runtime.get("runs") or []:
        run_copy = dict(run)
        run_copy.pop("runtime_seconds", None)
        normalized_runs.append(run_copy)
    runtime["runs"] = normalized_runs

    projection["curated_runtime"] = runtime
    return projection


def main() -> int:
    parser = argparse.ArgumentParser(description="Global validator health projection and drift checker")
    parser.add_argument("--rules-dir", default="rules", help="Directory containing mapping specs")
    parser.add_argument(
        "--baseline",
        default="results/ci/global_validator_health_baseline.json",
        help="Baseline projection artifact to compare against",
    )
    parser.add_argument(
        "--output",
        default="results/ci/global_validator_health.json",
        help="Where to write current health artifact",
    )
    parser.add_argument(
        "--fail-on-findings",
        action="store_true",
        help="Fail with non-zero exit code when findings are present",
    )
    parser.add_argument(
        "--max-p95-runtime-seconds",
        type=float,
        default=5.0,
        help="Maximum allowed p95 runtime seconds for curated runtime checks",
    )
    args = parser.parse_args()

    projection = build_global_validator_health_projection(
        rules_dir=args.rules_dir,
        max_p95_runtime_seconds=args.max_p95_runtime_seconds,
    )
    output_payload = {
        "rules_dir": str(Path(args.rules_dir).as_posix()),
        "projection": projection,
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output_payload, indent=2) + "\n", encoding="utf-8")

    findings = evaluate_global_validator_health(projection)

    baseline_path = Path(args.baseline)
    if baseline_path.exists():
        baseline_payload = json.loads(baseline_path.read_text(encoding="utf-8"))
        baseline_projection = (
            baseline_payload.get("projection")
            if isinstance(baseline_payload.get("projection"), dict)
            else {}
        )
        if _stable_projection_view(projection) != _stable_projection_view(baseline_projection):
            findings.append("projection drifted from baseline")
    else:
        findings.append(f"baseline not found: {baseline_path.as_posix()}")

    if findings:
        mode = "blocking" if args.fail_on_findings else "non-blocking"
        print(f"Global validator health drift detected ({mode}): {len(findings)} finding(s)")
        for finding in findings:
            print(f"::warning::{finding}")
    else:
        print("Global validator health check: no drift detected")

    print(f"Artifact written: {out_path}")
    if findings and args.fail_on_findings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
