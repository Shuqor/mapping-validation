from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.validate import validate_spec_coverage


def _run_batch_matrix(mode: str, batch_json_out: Path) -> dict:
    command = [
        sys.executable,
        "scripts/run_stage9_real_spec_batch.py",
        "--mode",
        mode,
        "--json-out",
        str(batch_json_out),
    ]
    completed = subprocess.run(command, check=False, cwd=str(REPO_ROOT))
    if completed.returncode != 0:
        raise RuntimeError("Stage 9 real workbook batch matrix failed")
    return json.loads(batch_json_out.read_text(encoding="utf-8"))


def _run_rules_coverage(rules_dir: Path, coverage_json_out: Path) -> dict:
    specs = sorted(rules_dir.glob("*.xlsx"))

    status_counts: Counter[str] = Counter()
    confidence_counts: Counter[str] = Counter()
    failures = []
    low_confidence_specs = []
    non_pass_specs = []

    aggregate = {
        "total_checked_rules": 0,
        "total_enforced_rules": 0,
        "total_parsed_only_rules": 0,
        "total_unsupported_rules": 0,
    }

    spec_rows = []
    for spec in specs:
        try:
            report = validate_spec_coverage(str(spec))
            summary = report.get("summary", {})
            parser = report.get("parser_diagnostics", {})
            support = report.get("rule_support_summary", {})

            status = str(summary.get("status") or "unknown")
            parser_status = str(parser.get("status") or "unknown")
            confidence = str(parser.get("confidence") or "unknown")
            checked_rules = int(report.get("checked_rules") or 0)
            enforced_rules = int(support.get("enforced_rules") or 0)
            parsed_only_rules = int(support.get("parsed_only_rules") or 0)
            unsupported_rules = int(support.get("unsupported_rules") or 0)

            status_counts[status] += 1
            confidence_counts[confidence] += 1
            aggregate["total_checked_rules"] += checked_rules
            aggregate["total_enforced_rules"] += enforced_rules
            aggregate["total_parsed_only_rules"] += parsed_only_rules
            aggregate["total_unsupported_rules"] += unsupported_rules

            if confidence == "low" or parser_status == "low_confidence":
                low_confidence_specs.append(spec.name)
            if status != "PASS":
                non_pass_specs.append(
                    {
                        "spec": spec.name,
                        "status": status,
                        "parser_status": parser_status,
                        "confidence": confidence,
                    }
                )

            spec_rows.append(
                {
                    "spec": spec.name,
                    "status": status,
                    "parser_status": parser_status,
                    "confidence": confidence,
                    "checked_rules": checked_rules,
                    "enforced_rules": enforced_rules,
                    "parsed_only_rules": parsed_only_rules,
                    "unsupported_rules": unsupported_rules,
                }
            )
        except Exception as exc:  # noqa: BLE001
            failures.append({"spec": spec.name, "error": f"{type(exc).__name__}: {exc}"})

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "spec_count": len(specs),
            "success_count": len(spec_rows),
            "failure_count": len(failures),
            "status_counts": dict(sorted(status_counts.items())),
            "confidence_counts": dict(sorted(confidence_counts.items())),
            **aggregate,
            "low_confidence_count": len(low_confidence_specs),
            "non_pass_count": len(non_pass_specs),
        },
        "low_confidence_specs": low_confidence_specs,
        "non_pass_specs": non_pass_specs,
        "failures": failures,
        "spec_results": spec_rows,
    }

    coverage_json_out.parent.mkdir(parents=True, exist_ok=True)
    coverage_json_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run browser-first integrator regression matrix")
    parser.add_argument("--mode", choices=["strict", "lenient", "structure_strict"], default="lenient")
    parser.add_argument("--rules-dir", default="rules")
    parser.add_argument("--batch-json-out", default="results/ci/integrator_browser_batch_allpass.json")
    parser.add_argument("--coverage-json-out", default="results/ci/integrator_browser_all_rules_coverage.json")
    parser.add_argument("--summary-json-out", default="results/ci/integrator_browser_regression.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    batch_json_out = Path(args.batch_json_out)
    coverage_json_out = Path(args.coverage_json_out)
    summary_json_out = Path(args.summary_json_out)
    rules_dir = Path(args.rules_dir)

    batch_json_out.parent.mkdir(parents=True, exist_ok=True)
    batch = _run_batch_matrix(args.mode, batch_json_out)
    coverage = _run_rules_coverage(rules_dir, coverage_json_out)

    batch_summary = batch.get("summary", {}) if isinstance(batch, dict) else {}
    coverage_summary = coverage.get("summary", {}) if isinstance(coverage, dict) else {}

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": args.mode,
        "artifacts": {
            "batch": str(batch_json_out).replace("\\", "/"),
            "coverage": str(coverage_json_out).replace("\\", "/"),
        },
        "batch_summary": batch_summary,
        "coverage_summary": coverage_summary,
        "gate": {
            "batch_failures": int(batch_summary.get("fail", 0) or 0),
            "coverage_failures": int(coverage_summary.get("failure_count", 0) or 0),
            "low_confidence_specs": int(coverage_summary.get("low_confidence_count", 0) or 0),
        },
    }

    summary_json_out.parent.mkdir(parents=True, exist_ok=True)
    summary_json_out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print("Integrator browser regression matrix")
    print(f"Mode: {args.mode}")
    print(
        "Batch summary: "
        f"pass={batch_summary.get('pass', 0)} "
        f"fail={batch_summary.get('fail', 0)} "
        f"skip={batch_summary.get('skip', 0)} "
        f"total={batch_summary.get('total', 0)}"
    )
    print(
        "Coverage summary: "
        f"specs={coverage_summary.get('spec_count', 0)} "
        f"failures={coverage_summary.get('failure_count', 0)} "
        f"low_confidence={coverage_summary.get('low_confidence_count', 0)} "
        f"status_counts={coverage_summary.get('status_counts', {})}"
    )
    print(f"Wrote summary to {summary_json_out}")

    has_blocking_findings = (
        int(batch_summary.get("fail", 0) or 0) > 0
        or int(coverage_summary.get("failure_count", 0) or 0) > 0
        or int(coverage_summary.get("low_confidence_count", 0) or 0) > 0
    )
    return 1 if has_blocking_findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
