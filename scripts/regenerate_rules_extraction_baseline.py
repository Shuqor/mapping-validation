import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow direct script execution from repository root without package install.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import core.validate as validate_module


DEFAULT_BASELINE_PATH = Path("results/rules_extraction_baseline.json")


def _norm_text(value: object) -> str:
    text = "" if value is None else str(value)
    return " ".join(text.replace("\n", " ").replace("\r", " ").strip().split())


def _fingerprint_rules(rules: list[dict]) -> str:
    normalized_rows: list[list[str]] = []
    for rule in rules:
        normalized_rows.append(
            [
                _norm_text(rule.get("target_xpath", "")),
                _norm_text(rule.get("source_xpath", "")),
                _norm_text(rule.get("cardinality", "")),
                _norm_text(rule.get("condition", "")),
                _norm_text(rule.get("note", "")),
                _norm_text(rule.get("m_o", "")),
                _norm_text(rule.get("layout", "")),
            ]
        )

    # Rule iteration order can vary across platforms/engines. Fingerprint the
    # canonical sorted rows so snapshots remain stable for equivalent rule sets.
    normalized_rows.sort()

    payload = json.dumps(normalized_rows, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def project_rules_extraction_baseline(rules_dir: str = "rules") -> dict:
    specs = sorted(Path(rules_dir).glob("*.xlsx"))

    projections: list[dict] = []
    failures: list[dict] = []
    for spec_path in specs:
        try:
            df = validate_module.read_mapping_table(str(spec_path))
            rules = validate_module.extract_rules(df)
            diagnostics = validate_module.get_parser_diagnostics(df)

            projection = {
                "spec": spec_path.as_posix(),
                "sheet_name": diagnostics.get("sheet_name"),
                "layout": diagnostics.get("layout"),
                "status": diagnostics.get("status"),
                "confidence": diagnostics.get("confidence"),
                "rule_count": len(rules),
                "rule_fingerprint": _fingerprint_rules(rules),
                "ambiguity_count": len((diagnostics.get("extraction") or {}).get("ambiguities") or []),
            }
            projections.append(projection)
            if projection["rule_count"] <= 0:
                failures.append({
                    "spec": spec_path.as_posix(),
                    "reason": "zero_rules_extracted",
                })
        except Exception as exc:  # noqa: BLE001
            failures.append({
                "spec": spec_path.as_posix(),
                "reason": f"parser_exception: {exc}",
            })

    return {
        "rules_dir": str(Path(rules_dir).as_posix()),
        "spec_count": len(specs),
        "failure_count": len(failures),
        "failures": failures,
        "specs": projections,
    }


def regenerate_rules_extraction_baseline(output_path: Path, rules_dir: str) -> dict:
    projection = project_rules_extraction_baseline(rules_dir=rules_dir)
    payload = {
        "snapshot_name": "rules_extraction_baseline",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "projection": projection,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Regenerate rules extraction baseline snapshot artifact.")
    parser.add_argument("--rules-dir", default="rules", help="Directory containing mapping specs")
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE_PATH), help="Baseline artifact path")
    args = parser.parse_args()

    baseline_path = Path(args.baseline)
    payload = regenerate_rules_extraction_baseline(
        output_path=baseline_path,
        rules_dir=args.rules_dir,
    )

    projection = payload["projection"]
    print(
        f"Updated baseline: {baseline_path} | "
        f"spec_count={projection['spec_count']} failures={projection['failure_count']}"
    )


if __name__ == "__main__":
    main()
