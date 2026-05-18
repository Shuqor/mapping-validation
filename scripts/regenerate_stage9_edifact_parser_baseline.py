import json
from datetime import datetime, timezone
from pathlib import Path

import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.spec_reader import extract_rules, get_parser_diagnostics, read_mapping_table

BASELINE_PATH = Path("results/stage9_edifact_parser_baseline.json")


def project_stage9_edifact_parser(df, rules: list[dict], diagnostics: dict) -> dict:
    selected = diagnostics.get("extraction", {}).get("selected_columns", {})
    return {
        "parser": {
            "layout": diagnostics.get("layout", ""),
            "status": diagnostics.get("status", ""),
            "confidence": diagnostics.get("confidence", ""),
            "sheet_name": diagnostics.get("sheet_name", ""),
            "header_row": diagnostics.get("header_row", None),
            "rule_count": diagnostics.get("rule_count", 0),
        },
        "selected_columns": {
            "target": selected.get("target", ""),
            "source": selected.get("source", ""),
            "condition": selected.get("condition", ""),
            "note": selected.get("note", ""),
            "m_o": selected.get("m_o", ""),
        },
        "rules_preview": [
            {
                "target_xpath": rule.get("target_xpath", ""),
                "source_xpath": rule.get("source_xpath", ""),
            }
            for rule in rules[:4]
        ],
    }


def main() -> None:
    fixture_specs = [
        Path("samples/spec_edifact_guided.xlsx"),
        Path("samples/spec_edifact_orders_guided.xlsx"),
    ]

    fixture_projections: dict[str, dict] = {}
    for spec_path in fixture_specs:
        df = read_mapping_table(str(spec_path))
        rules = extract_rules(df)
        diagnostics = get_parser_diagnostics(df)
        fixture_projections[spec_path.name] = project_stage9_edifact_parser(df, rules, diagnostics)

    payload = {
        "snapshot_name": "stage9_edifact_parser_baseline",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "spec_paths": [str(path).replace("\\", "/") for path in fixture_specs],
        },
        "projection": {
            "fixtures": fixture_projections,
        },
    }

    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        f"Updated Stage 9 EDIFACT parser baseline: {BASELINE_PATH} | "
        f"fixtures={len(fixture_projections)} "
        f"names={','.join(fixture_projections.keys())}"
    )


if __name__ == "__main__":
    main()
