import os
from pathlib import Path

import pytest

from core.validate import validate_mapping_from_payload_bytes


ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_PATH = ROOT_DIR / "web" / "index.html"
RULES_DIR = ROOT_DIR / "rules"
SAMPLES_DIR = ROOT_DIR / "samples"


@pytest.mark.skipif(os.getenv("RUN_BROWSER_PARITY_TESTS") != "1", reason="Enable with RUN_BROWSER_PARITY_TESTS=1")
def test_browser_python_parity_distribution_for_real_case():
    playwright_sync = pytest.importorskip("playwright.sync_api")

    case_candidates = [
        (
            "Inttra-Contivo_EDIFACT_IFTMBF_D99B_to_JSON_BOOKINGINBOUND.xlsx",
            "Inbound_BK3_CU2100_IFTMBF.edi",
            "output INTTRA.json",
        ),
        (
            "Inttra-Contivo_X12_300_5030_to_JSON_BOOKINGINBOUND.xlsx",
            "input.x12",
            "output.json",
        ),
    ]

    selected = None
    for spec_name, input_name, output_name in case_candidates:
        spec_path = RULES_DIR / spec_name
        input_path = SAMPLES_DIR / input_name
        output_path = SAMPLES_DIR / output_name
        if spec_path.exists() and input_path.exists() and output_path.exists():
            selected = (spec_path, input_path, output_path)
            break

    if not selected:
        pytest.skip("No parity candidate files are available")

    spec_path, input_path, output_path = selected

    py_result = validate_mapping_from_payload_bytes(
        str(spec_path),
        input_path.read_bytes(),
        input_path.name,
        output_path.read_bytes(),
        output_path.name,
        validation_mode="strict",
    )

    with playwright_sync.sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(WEB_PATH.resolve().as_uri())

        page.set_input_files("#mapping_spec", str(spec_path))
        page.set_input_files("#input_payload", str(input_path))
        page.set_input_files("#output_payload", str(output_path))
        page.click("#submit-btn")

        page.wait_for_function("() => Boolean(window.lastResult && window.lastResult.summary)", timeout=120000)
        js_result = page.evaluate(
            """
            () => ({
              checked_rules: window.lastResult?.checked_rules || 0,
              rule_support_summary: window.lastResult?.rule_support_summary || {},
              rule_decisions: window.lastResult?.rule_decisions || [],
            })
            """
        )
        browser.close()

    py_support = py_result.get("rule_support_summary", {})
    js_support = js_result.get("rule_support_summary", {})

    py_counts = {
        "enforced": int(py_support.get("enforced_rules", 0)),
        "parsed_only": int(py_support.get("parsed_only_rules", 0)),
        "unsupported": int(py_support.get("unsupported_rules", 0)),
    }
    js_counts = {
        "enforced": int(js_support.get("enforced_rules", 0)),
        "parsed_only": int(js_support.get("parsed_only_rules", 0)),
        "unsupported": int(js_support.get("unsupported_rules", 0)),
    }

    # Exact parity is ideal, but keep a narrow tolerance to avoid platform-format parser drift.
    assert abs(int(py_result.get("checked_rules", 0)) - int(js_result.get("checked_rules", 0))) <= 2
    assert abs(py_counts["enforced"] - js_counts["enforced"]) <= 5
    assert abs(py_counts["parsed_only"] - js_counts["parsed_only"]) <= 5
    assert abs(py_counts["unsupported"] - js_counts["unsupported"]) <= 5

    assert isinstance(py_result.get("rule_decisions", []), list)
    assert isinstance(js_result.get("rule_decisions", []), list)
