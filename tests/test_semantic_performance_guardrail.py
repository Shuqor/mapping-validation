import json
import os
import time
from pathlib import Path

import core.validate as validate_module


REGRESSION_CORPUS_PATH = Path(__file__).resolve().parent / "fixtures" / "semantic_regression_corpus.json"
REAL_WORLD_CORPUS_PATH = Path(__file__).resolve().parent / "fixtures" / "semantic_real_world_corpus.json"


def _run_semantic_pass(fixtures, loops: int) -> float:
    start = time.perf_counter()

    for _ in range(loops):
        for fixture in fixtures:
            profile = validate_module._get_semantic_profile(fixture["spec_path"])
            normalized, _trace = validate_module._canonicalize_semantic_condition_with_trace(
                fixture["condition"],
                semantic_profile=profile,
            )
            validate_module._extract_semantic_parts(normalized, profile["field_aliases"])
            validate_module._suggest_pattern_families(
                normalized,
                top_n=3,
                semantic_profile=profile,
            )

    return time.perf_counter() - start


def test_semantic_runtime_medium_corpus_guardrail():
    fixtures = json.loads(REGRESSION_CORPUS_PATH.read_text(encoding="utf-8"))
    loops = int(os.getenv("SEMANTIC_PERF_MEDIUM_LOOPS", "12"))
    max_seconds = float(os.getenv("SEMANTIC_PERF_MEDIUM_MAX_SECONDS", "1.5"))

    duration = _run_semantic_pass(fixtures, loops)
    assert duration <= max_seconds, (
        f"Medium corpus semantic runtime exceeded guardrail: "
        f"duration={duration:.4f}s max={max_seconds:.4f}s loops={loops} size={len(fixtures)}"
    )


def test_semantic_runtime_large_corpus_guardrail():
    fixtures = json.loads(REAL_WORLD_CORPUS_PATH.read_text(encoding="utf-8"))
    loops = int(os.getenv("SEMANTIC_PERF_LARGE_LOOPS", "8"))
    max_seconds = float(os.getenv("SEMANTIC_PERF_LARGE_MAX_SECONDS", "2.2"))

    duration = _run_semantic_pass(fixtures, loops)
    assert duration <= max_seconds, (
        f"Large corpus semantic runtime exceeded guardrail: "
        f"duration={duration:.4f}s max={max_seconds:.4f}s loops={loops} size={len(fixtures)}"
    )
