import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import core.validate as validate_module


DEFAULT_BASELINE_PATH = Path("results/stage10_parser_collapse_baseline.json")
DEFAULT_SPECS = [
    "rules/Inttra-Contivo_X12_300_5030_to_JSON_BOOKINGINBOUND 1 Update.xlsx",
    "rules/Inttra-Contivo_EDIFACT_IFTMBF_D99B_to_JSON_BOOKINGINBOUND.xlsx",
    "rules/JABIL_X12_214_4010_to_JSON_TMSCARRIERTENDERRESPONSE_v1.4.xlsx",
    "rules/TMSLSP-DHLLINK_Common_CUSTOMXML_Status_1.0_to_CUSTOMXML_Status_1.0.xlsx",
    "rules/P&G_CDM_DiscreteOrderDownload_1.0_to_cXML_PurchaseOrder_1.2.051.xlsx",
]


def _project_parser_diagnostics(report: dict) -> dict:
    parser = report.get("parser_diagnostics", {}) if isinstance(report, dict) else {}
    extraction = parser.get("extraction", {}) if isinstance(parser.get("extraction"), dict) else {}
    selected = extraction.get("selected_columns", {}) if isinstance(extraction.get("selected_columns"), dict) else {}
    candidates = extraction.get("candidate_columns", {}) if isinstance(extraction.get("candidate_columns"), dict) else {}

    return {
        "status": parser.get("status"),
        "confidence": parser.get("confidence"),
        "layout": parser.get("layout"),
        "header_row": parser.get("header_row"),
        "rule_count": int(parser.get("rule_count", 0) or 0),
        "duplicate_columns": sorted((parser.get("duplicate_columns") or {}).keys()),
        "selected_columns": {
            "m_o": selected.get("m_o"),
            "source": selected.get("source"),
            "condition": selected.get("condition"),
            "note": selected.get("note"),
            "cardinality": selected.get("cardinality"),
        },
        "candidate_column_counts": {
            key: len(value) if isinstance(value, list) else 0
            for key, value in sorted(candidates.items())
        },
        "ambiguity_count": len(extraction.get("ambiguities", []) if isinstance(extraction.get("ambiguities"), list) else []),
        "hierarchical_level_columns_count": len(extraction.get("hierarchical_level_columns", []) if isinstance(extraction.get("hierarchical_level_columns"), list) else []),
    }


def build_parser_collapse_projection(spec_paths: list[str]) -> dict:
    items = []
    for spec_path in spec_paths:
        report = validate_module.validate_spec_coverage(spec_path)
        items.append(
            {
                "spec_path": spec_path,
                "projection": _project_parser_diagnostics(report),
            }
        )
    return {
        "spec_count": len(items),
        "specs": items,
    }


def regenerate_parser_collapse_baseline(output_path: Path, spec_paths: list[str]) -> dict:
    payload = {
        "snapshot_name": "stage10_parser_collapse_baseline",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "inputs": {"spec_paths": spec_paths},
        "projection": build_parser_collapse_projection(spec_paths),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Regenerate Stage 10 parser collapse baseline snapshot")
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE_PATH), help="Baseline output path")
    parser.add_argument("--spec", action="append", dest="specs", help="Spec path (repeatable); defaults to representative set")
    args = parser.parse_args()

    spec_paths = args.specs if args.specs else list(DEFAULT_SPECS)
    payload = regenerate_parser_collapse_baseline(Path(args.baseline), spec_paths)
    print(
        f"Updated parser collapse baseline: {args.baseline} | specs={payload['projection']['spec_count']}"
    )


if __name__ == "__main__":
    main()
