from pathlib import Path
import csv
import re

import pandas as pd


_MAPPING_SHEET_CANDIDATES = [
    "Mapping",
    "Mapping cXML to CDM",
    "cXML to CDM",
]

_NON_DATA_SHEET_HINTS = {
    "change history",
    "conditions",
    "guidelines",
    "sample",
    "revision",
    "notes",
    "readme",
}

_HEADER_HINTS = [
    "segment",
    "field",
    "xpath",
    "cardinality",
    "condition",
    "mapping",
    "rule",
    "m/o",
    "mandatory",
    "optional",
    "index",
    "format",
    "note",
    "level",
    "display",
    "datatype",
]


def _norm_text(value: str) -> str:
    text = "" if value is None else str(value)
    return " ".join(text.replace("\n", " ").replace("\r", " ").strip().lower().split())


def _canonical_col(col_name: str) -> str:
    # Keep original punctuation for user visibility and tests, but normalize spacing/case.
    return _norm_text(col_name)


def _column_base(col_name: str) -> str:
    base = re.sub(r"(__dup\d+|\.\d+)$", "", col_name)
    return re.sub(r"\s*/\s*", "/", base)


def _split_duplicate_suffix(col_name: str) -> tuple[str, int | None]:
    normalized = _canonical_col(col_name)

    explicit_dup = re.fullmatch(r"(.+)__dup(\d+)$", normalized)
    if explicit_dup:
        return explicit_dup.group(1), int(explicit_dup.group(2))

    pandas_dup = re.fullmatch(r"(.+)\.(\d+)$", normalized)
    if pandas_dup:
        # pandas uses .1 for the second occurrence, .2 for the third, etc.
        return pandas_dup.group(1), int(pandas_dup.group(2)) + 1

    return normalized, None


def _keyword_match(col_name: str, *keywords: str) -> bool:
    base = _column_base(_norm_text(col_name))
    # Treat slash spacing variants equivalently when matching keywords.
    base = re.sub(r"\s*/\s*", "/", base)
    token_base = re.sub(r"[^a-z0-9]+", " ", base)
    return all(re.sub(r"[^a-z0-9]+", " ", k.lower()).strip() in token_base for k in keywords)


def _matching_columns(cols: list[str], *keywords: str) -> list[str]:
    return [col for col in cols if _keyword_match(col, *keywords)]


def _unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _resolve_column_by_priority(cols: list[str], patterns: list[tuple[str, ...]]) -> tuple[str | None, list[str]]:
    """Return (selected, candidates) from the first non-empty priority bucket."""
    for pattern in patterns:
        matches = _matching_columns(cols, *pattern)
        if matches:
            unique_matches = _unique_preserve_order(matches)
            return unique_matches[0], unique_matches
    return None, []


def _get_parser_diagnostics_container(df) -> dict:
    if not hasattr(df, "attrs"):
        return {}
    diagnostics = df.attrs.get("parser_diagnostics")
    if diagnostics is None:
        diagnostics = {}
        df.attrs["parser_diagnostics"] = diagnostics
    return diagnostics


def _finalize_parser_diagnostics(diagnostics: dict) -> dict:
    extraction = diagnostics.get("extraction", {})
    ambiguities = extraction.get("ambiguities", [])
    warnings = diagnostics.get("warnings", [])
    info = diagnostics.get("info", [])

    if diagnostics.get("rule_count", 0) == 0 and extraction:
        diagnostics["status"] = "low_confidence"
        diagnostics["confidence"] = "low"
    elif ambiguities:
        diagnostics["status"] = "low_confidence"
        diagnostics["confidence"] = "low"
    elif diagnostics.get("sheet_fallback_used"):
        diagnostics["status"] = "parsed_with_fallbacks"
        diagnostics["confidence"] = "medium"
    elif warnings:
        diagnostics["status"] = "parsed_with_warnings"
        diagnostics["confidence"] = "medium"
    else:
        diagnostics["status"] = "clean"
        diagnostics["confidence"] = "high"

    return diagnostics


def _record_column_resolution(
    extraction: dict,
    label: str,
    candidates: list[str],
    selected: str | None,
) -> None:
    unique_candidates = _unique_preserve_order(candidates)
    extraction.setdefault("candidate_columns", {})[label] = unique_candidates
    extraction.setdefault("selected_columns", {})[label] = selected
    # Treat same-base duplicates as one candidate role to avoid false ambiguity.
    unique_candidate_bases = _unique_preserve_order([_column_base(c) for c in unique_candidates])
    if len(unique_candidate_bases) > 1:
        extraction.setdefault("ambiguities", []).append(
            {
                "role": label,
                "candidates": unique_candidates,
                "selected": selected,
            }
        )


def _score_row_for_header(values: list[str]) -> int:
    if not values:
        return 0

    normalized = [_norm_text(v) for v in values if _norm_text(v)]
    if not normalized:
        return 0

    matched_hints = 0
    for hint in _HEADER_HINTS:
        if any(hint in cell for cell in normalized):
            matched_hints += 1

    # Bonus for likely header density (several short labels, not long prose).
    short_cells = sum(1 for cell in normalized if len(cell) <= 35)
    likely_xpath_data = sum(1 for cell in normalized if "/" in cell and len(cell) > 20)

    score = matched_hints * 4 + short_cells
    if likely_xpath_data > short_cells:
        score -= 3
    return score


def _detect_csv_delimiter(file_path: str, sample_rows: int = 12) -> str:
    """Detect CSV delimiter with stable fallback ordering."""
    try:
        with open(file_path, "r", encoding="utf-8") as handle:
            sample = "".join(handle.readline() for _ in range(sample_rows))

        if not sample:
            return ","

        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            return dialect.delimiter
        except csv.Error:
            pass

        # Stable fallback order: comma > semicolon > tab > pipe on ties.
        candidates = [",", ";", "\t", "|"]
        scored = [(sample.count(d), i, d) for i, d in enumerate(candidates)]
        return max(scored, key=lambda item: (item[0], -item[1]))[2]
    except Exception:
        return ","


def _detect_csv_quoting(file_path: str) -> tuple[str, str | None]:
    """Return (quotechar, escapechar) for robust CSV parsing."""
    try:
        with open(file_path, "r", encoding="utf-8") as handle:
            sample = handle.read(4096)

        has_backslash_escape = '\\"' in sample or "\\'" in sample
        has_doubled_quotes = '""' in sample
        if has_backslash_escape:
            return '"', "\\"
        if has_doubled_quotes:
            return '"', '"'
        return '"', None
    except Exception:
        return '"', '"'


def _detect_file_format(spec_path: str) -> str:
    suffix = Path(spec_path).suffix.lower()
    if suffix in {".csv", ".tsv", ".txt"}:
        return "csv"
    if suffix in {".xlsx", ".xls"}:
        return "excel"
    raise ValueError(
        f"Unsupported file format: {suffix}. Expected .csv, .tsv, .txt, .xlsx, or .xls"
    )


def _score_sheet_name(sheet_name: str) -> int:
    lower_name = _norm_text(sheet_name)
    score = 0

    for candidate in _MAPPING_SHEET_CANDIDATES:
        if lower_name == _norm_text(candidate):
            score += 160
        elif lower_name.startswith(_norm_text(candidate)):
            score += 110

    if lower_name.startswith("mapping"):
        score += 90
    elif "mapping" in lower_name:
        score += 55

    if "x12" in lower_name:
        score += 25
    if "cdm" in lower_name:
        score += 15

    if any(skip in lower_name for skip in _NON_DATA_SHEET_HINTS):
        score -= 120

    return score


def _sample_sheet_header_score(path: Path, sheet_name: str, scan_rows: int = 35) -> tuple[int, int]:
    try:
        sample = pd.read_excel(
            str(path),
            sheet_name=sheet_name,
            header=None,
            engine="openpyxl",
            nrows=scan_rows,
        )
    except Exception:
        return 0, -1

    best_score = 0
    best_row = -1
    for idx in range(len(sample)):
        values = ["" if pd.isna(v) else str(v) for v in sample.iloc[idx].tolist()]
        score = _score_row_for_header(values)
        if score > best_score:
            best_score = score
            best_row = idx
    return best_score, best_row


def _find_mapping_sheet(path: Path) -> str:
    """Select the best mapping sheet using deterministic scoring and fallback."""
    xl = pd.ExcelFile(str(path), engine="openpyxl")
    available = [s.strip() for s in xl.sheet_names]
    if not available:
        raise ValueError(f"Workbook has no sheets: {path}")

    scored_sheets: list[tuple[int, int, int, str]] = []
    for idx, sheet_name in enumerate(available):
        name_score = _score_sheet_name(sheet_name)
        header_score, _ = _sample_sheet_header_score(path, sheet_name)
        total = name_score + header_score
        # Deterministic tie-breakers: higher total, higher header score, then earlier workbook order.
        scored_sheets.append((total, header_score, -idx, sheet_name))

    return max(scored_sheets, key=lambda item: (item[0], item[1], item[2]))[3]


def _resolve_sheet_name(path: Path, sheet_name: str | None) -> tuple[str, bool]:
    """Return (resolved_sheet_name, fallback_used)."""
    if sheet_name is None:
        return _find_mapping_sheet(path), False

    xl = pd.ExcelFile(str(path), engine="openpyxl")
    available = [s.strip() for s in xl.sheet_names]
    target = _norm_text(sheet_name)

    for name in available:
        if _norm_text(name) == target:
            return name, False

    # Stage 7 fallback behavior: keep parsing with best candidate when requested sheet is absent.
    return _find_mapping_sheet(path), True


def _normalize_columns(columns: list[object]) -> tuple[list[str], dict[str, list[str]]]:
    """Normalize while preserving duplicates via deterministic suffixes."""
    seen: dict[str, int] = {}
    normalized: list[str] = []
    duplicate_groups: dict[str, list[str]] = {}

    for idx, raw_col in enumerate(columns, start=1):
        base, forced_dup_index = _split_duplicate_suffix(str(raw_col))
        if not base or base == "nan":
            base = f"unnamed_{idx}"

        if forced_dup_index is not None:
            seen[base] = max(seen.get(base, 0), forced_dup_index)
        else:
            seen[base] = seen.get(base, 0) + 1

        if seen[base] == 1:
            final_col = base
        else:
            final_col = f"{base}__dup{seen[base]}"
            duplicate_groups.setdefault(base, [base]).append(final_col)

        normalized.append(final_col)

    return normalized, duplicate_groups


def _detect_header_row_details(df: pd.DataFrame) -> tuple[int, dict]:
    max_rows = min(len(df), 80)
    scores: list[tuple[int, int]] = []

    for idx in range(max_rows):
        row = df.iloc[idx].tolist()
        values = ["" if pd.isna(v) else str(v) for v in row]
        score = _score_row_for_header(values)
        scores.append((score, idx))

    if not scores:
        raise ValueError("Could not detect header row in mapping spec: sheet has no rows")

    best_score, best_idx = max(scores, key=lambda item: (item[0], -item[1]))
    second_best = sorted(scores, key=lambda item: (item[0], -item[1]), reverse=True)[1:2]
    second_score = second_best[0][0] if second_best else 0

    diagnostics = {
        "header_row": best_idx,
        "header_score": best_score,
        "header_second_best_score": second_score,
        "warnings": [],
        "info": [],
    }

    if best_score < 7:
        raise ValueError(
            "Could not detect header row in mapping spec: "
            f"best score {best_score} was below threshold"
        )

    if best_idx == 4:
        diagnostics["info"].append(
            "Header row detected at row 5; template preamble rows were skipped"
        )
    elif best_idx >= 5:
        diagnostics["warnings"].append(
            f"Header row detected at row {best_idx + 1}; workbook appears to have offset preamble rows"
        )

    if second_score == best_score:
        diagnostics["warnings"].append(
            "Header detection had a tie score; selected earliest matching row deterministically"
        )

    return best_idx, diagnostics


def detect_header_row(df):
    """Backwards-compatible header row detection helper."""
    idx, _ = _detect_header_row_details(df)
    return idx


def read_spec(spec_path: str, sheet_name: str = None) -> pd.DataFrame:
    """Read mapping spec and normalize columns (Excel or CSV)."""
    path = Path(spec_path)
    if not path.exists():
        raise FileNotFoundError(f"Spec file not found: {spec_path}")

    file_format = _detect_file_format(spec_path)
    diagnostics = {
        "file_format": file_format,
        "sheet_name": None,
        "sheet_fallback_used": False,
        "delimiter": None,
        "quote_char": None,
        "warnings": [],
        "info": [],
        "duplicate_columns": {},
    }

    if file_format == "csv":
        delimiter = _detect_csv_delimiter(spec_path)
        quote_char, escape_char = _detect_csv_quoting(spec_path)
        df = pd.read_csv(
            spec_path,
            delimiter=delimiter,
            quotechar=quote_char,
            escapechar=escape_char,
            skipinitialspace=True,
            skip_blank_lines=True,
            na_filter=True,
        )
        diagnostics["delimiter"] = delimiter
        diagnostics["quote_char"] = quote_char
    else:
        resolved_sheet, used_fallback = _resolve_sheet_name(path, sheet_name)
        diagnostics["sheet_name"] = resolved_sheet
        diagnostics["sheet_fallback_used"] = used_fallback
        if used_fallback:
            diagnostics["warnings"].append(
                f"Requested sheet '{sheet_name}' was not found; used '{resolved_sheet}'"
            )
        df = pd.read_excel(path, sheet_name=resolved_sheet, engine="openpyxl")

    normalized_cols, duplicate_cols = _normalize_columns(list(df.columns))
    df.columns = normalized_cols
    diagnostics["duplicate_columns"] = duplicate_cols
    if duplicate_cols:
        diagnostics["info"].append(
            "Duplicate headers detected and preserved with deterministic suffixes"
        )

    _finalize_parser_diagnostics(diagnostics)
    df.attrs["parser_diagnostics"] = diagnostics
    return df


def read_mapping_table(spec_path: str, sheet_name: str = None) -> pd.DataFrame:
    """
    Read mapping spec and return clean DataFrame beginning at detected header row.

    Stage 7 robustness:
    - Variable sheet names with deterministic fallback selection.
    - Header row detection for sparse/offset worksheets.
    - Duplicate header preservation via __dupN suffixes.
    - Diagnostics attached to df.attrs['parser_diagnostics'].
    """
    path = Path(spec_path)
    if not path.exists():
        raise FileNotFoundError(f"Spec file not found: {spec_path}")

    file_format = _detect_file_format(spec_path)
    diagnostics = {
        "file_format": file_format,
        "spec_name": path.name,
        "workbook_family": _infer_workbook_family(path.name),
        "sheet_name": None,
        "sheet_fallback_used": False,
        "delimiter": None,
        "quote_char": None,
        "header_row": None,
        "warnings": [],
        "info": [],
        "duplicate_columns": {},
    }

    if file_format == "csv":
        delimiter = _detect_csv_delimiter(spec_path)
        quote_char, escape_char = _detect_csv_quoting(spec_path)
        diagnostics["delimiter"] = delimiter
        diagnostics["quote_char"] = quote_char
        raw_df = pd.read_csv(
            spec_path,
            header=None,
            delimiter=delimiter,
            quotechar=quote_char,
            escapechar=escape_char,
            skipinitialspace=True,
            skip_blank_lines=True,
            na_filter=True,
        )
    else:
        resolved_sheet, used_fallback = _resolve_sheet_name(path, sheet_name)
        diagnostics["sheet_name"] = resolved_sheet
        diagnostics["sheet_fallback_used"] = used_fallback
        if used_fallback:
            diagnostics["warnings"].append(
                f"Requested sheet '{sheet_name}' was not found; used '{resolved_sheet}'"
            )
        raw_df = pd.read_excel(
            str(path),
            sheet_name=resolved_sheet,
            engine="openpyxl",
            header=None,
        )

    try:
        header_row, header_details = _detect_header_row_details(raw_df)
    except ValueError as exc:
        context = f"file={spec_path}, sheet={diagnostics['sheet_name'] or 'N/A'}"
        raise ValueError(f"{exc} ({context})") from exc

    diagnostics["header_row"] = header_row
    diagnostics["warnings"].extend(header_details.get("warnings", []))
    diagnostics["info"].extend(header_details.get("info", []))

    if file_format == "csv":
        delimiter = diagnostics["delimiter"]
        quote_char, escape_char = _detect_csv_quoting(spec_path)
        df = pd.read_csv(
            spec_path,
            header=header_row,
            delimiter=delimiter,
            quotechar=quote_char,
            escapechar=escape_char,
            skipinitialspace=True,
            skip_blank_lines=True,
            na_filter=True,
        )
    else:
        df = pd.read_excel(
            str(path),
            sheet_name=diagnostics["sheet_name"],
            engine="openpyxl",
            header=header_row,
        )

    normalized_cols, duplicate_cols = _normalize_columns(list(df.columns))
    df.columns = normalized_cols
    diagnostics["duplicate_columns"] = duplicate_cols
    if duplicate_cols:
        diagnostics["info"].append(
            "Duplicate headers detected and preserved with deterministic suffixes"
        )

    df = df.dropna(how="all")

    for col in df.columns:
        if df[col].dtype == "object":
            df[col] = df[col].apply(lambda v: v.strip() if isinstance(v, str) else v)

    if df.empty:
        raise ValueError(
            "Mapping table is empty after header detection "
            f"(file={spec_path}, sheet={diagnostics['sheet_name'] or 'N/A'}, header_row={header_row + 1})"
        )

    _finalize_parser_diagnostics(diagnostics)
    df.attrs["parser_diagnostics"] = diagnostics
    return df


def get_parser_diagnostics(df: pd.DataFrame) -> dict:
    """Return parser diagnostics captured by read_spec/read_mapping_table."""
    if not hasattr(df, "attrs"):
        return {}
    diagnostics = dict(df.attrs.get("parser_diagnostics", {}))
    if "layout" not in diagnostics and hasattr(df, "columns"):
        try:
            diagnostics["layout"] = _detect_layout(df)
        except Exception:
            pass
    if diagnostics.get("rule_count") in {None, 0} and hasattr(df, "columns"):
        try:
            extract_rules(df)
            diagnostics = dict(df.attrs.get("parser_diagnostics", diagnostics))
        except Exception:
            pass
    return _finalize_parser_diagnostics(diagnostics)


def _infer_workbook_family(spec_name: str) -> str:
    lowered = _norm_text(spec_name)
    if lowered.startswith("jabil"):
        return "jabil"
    if lowered.startswith("p&g"):
        return "p_and_g"
    if lowered.startswith("tmslsp"):
        return "tmslsp"
    if lowered.startswith("inttra"):
        return "inttra"
    return "generic"


def _detect_layout(df) -> str:
    """
    Detect the mapping layout type from normalized columns and sample values.

    Returns one of: xpath_target, cdm_target, x12_segment.
    Note: x12_segment is used as the generic EDI segment layout bucket
    for both X12 and EDIFACT-style source paths.
    """
    cols = list(df.columns)

    has_field_name = any(_keyword_match(c, "field", "name") for c in cols)
    has_segment_xpath = any(_keyword_match(c, "segment", "xpath") for c in cols)
    if has_field_name and not has_segment_xpath:
        return "cdm_target"

    # Matrix-style X12 reference sheets use qualifier/description rows with target document
    # columns such as "shipment status", "planned shipment", etc.
    has_reference_qualifier = any(_keyword_match(c, "reference", "qualifier") for c in cols)
    has_segment_identifier = any(_keyword_match(c, "segment", "element", "identifier") for c in cols)
    x12_document_columns = {
        "planned receipt",
        "actual receipt",
        "planned shipment",
        "actual shipment",
        "item master",
        "inventory adjustment",
        "inventory balance",
        "invoice",
        "load tender",
        "shipment status",
    }
    if has_reference_qualifier and (has_segment_identifier or any(_norm_text(c) in x12_document_columns for c in cols)):
        return "x12_segment"

    sample_rows = min(len(df), 30)
    for col in cols:
        if any(_keyword_match(col, key) for key in ["xpath", "source", "segment", "element"]):
            try:
                values = df[col].dropna().astype(str).head(sample_rows)
            except Exception:
                continue
            if any("/x12/" in v.lower() or "/x12/ts_" in v.lower() for v in values):
                return "x12_segment"
            if any("/edifact/" in v.lower() or "/edifact/msg_" in v.lower() for v in values):
                return "x12_segment"
            if any(v.strip().upper().startswith("UNH+") or v.strip().upper().startswith("UNB+") for v in values):
                return "x12_segment"

    return "xpath_target"


def _first_col_matching(cols: list[str], *keywords: str) -> str | None:
    for col in cols:
        if _keyword_match(col, *keywords):
            return col
    return None


def _last_col_matching(cols: list[str], *keywords: str) -> str | None:
    for col in reversed(cols):
        if _keyword_match(col, *keywords):
            return col
    return None


def _iter_preview_values(df: pd.DataFrame, col: str, sample_rows: int = 40):
    try:
        values = df[col].dropna().astype(str).head(sample_rows)
    except Exception:
        return []
    return [v.strip() for v in values if str(v).strip()]


def _looks_like_edi_source_value(value: str) -> bool:
    lowered = _norm_text(value)
    return (
        "/x12/" in lowered
        or "/edifact/" in lowered
        or lowered.startswith("unb+")
        or lowered.startswith("unh+")
        or lowered.startswith("isa*")
        or lowered.startswith("st*")
    )


def _looks_like_target_xpath_value(value: str) -> bool:
    text = (value or "").strip()
    if not text.startswith("/"):
        return False
    return not _looks_like_edi_source_value(text)


def _column_signature_scores(df: pd.DataFrame, col: str) -> tuple[int, int]:
    values = _iter_preview_values(df, col)
    source_like = sum(1 for value in values if _looks_like_edi_source_value(value))
    target_like = sum(1 for value in values if _looks_like_target_xpath_value(value))
    return source_like, target_like


def extract_rules(df):
    """
    Extract mapping rules from normalized DataFrame.

    Returns list of dict keys:
      target_xpath, source_xpath, cardinality, condition, note, m_o, layout
    """

    def clean(value):
        return "" if pd.isna(value) else str(value).strip()

    cols = list(df.columns)
    layout = _detect_layout(df)
    parser_diagnostics = _get_parser_diagnostics_container(df)
    extraction = {
        "layout": layout,
        "candidate_columns": {},
        "selected_columns": {},
        "ambiguities": [],
        "warnings": [],
    }
    parser_diagnostics["layout"] = layout
    workbook_family = parser_diagnostics.get("workbook_family", "generic")
    extraction["workbook_family"] = workbook_family

    mo_col = (
        _first_col_matching(cols, "m/o")
        or _first_col_matching(cols, "mandatory")
        or _first_col_matching(cols, "usage")
    )
    _record_column_resolution(
        extraction,
        "m_o",
        _matching_columns(cols, "m/o") + _matching_columns(cols, "mandatory") + _matching_columns(cols, "usage"),
        mo_col,
    )

    if layout == "x12_segment":
        matrix_target_cols = [
            c for c in cols
            if _norm_text(c) in {
                "planned receipt",
                "actual receipt",
                "planned shipment",
                "actual shipment",
                "item master",
                "inventory adjustment",
                "inventory balance",
                "invoice",
                "load tender",
                "shipment status",
                "(other)",
            }
        ]
        qualifier_col = _first_col_matching(cols, "reference", "qualifier")
        description_col = _first_col_matching(cols, "description")
        segment_id_col = _first_col_matching(cols, "segment", "element", "identifier")
        instruction_col = _first_col_matching(cols, "mapping", "instruction")
        _record_column_resolution(extraction, "reference_qualifier", _matching_columns(cols, "reference", "qualifier"), qualifier_col)
        _record_column_resolution(extraction, "description", _matching_columns(cols, "description"), description_col)
        _record_column_resolution(extraction, "segment_identifier", _matching_columns(cols, "segment", "element", "identifier"), segment_id_col)
        _record_column_resolution(extraction, "mapping_instruction", _matching_columns(cols, "mapping", "instruction"), instruction_col)
        extraction.setdefault("candidate_columns", {})["matrix_targets"] = matrix_target_cols

        if qualifier_col and matrix_target_cols:
            rules = []
            for _, row in df.iterrows():
                qualifier = clean(row.get(qualifier_col))
                description = clean(row.get(description_col)) if description_col else ""
                segment_identifier = clean(row.get(segment_id_col)) if segment_id_col else ""
                source_value = qualifier or segment_identifier
                if not source_value:
                    continue

                for target_col in matrix_target_cols:
                    marker = clean(row.get(target_col))
                    if marker.upper() not in {"X", "Y", "YES", "TRUE", "1"}:
                        continue

                    note_parts = [part for part in [description, clean(row.get(instruction_col)) if instruction_col else ""] if part]
                    rules.append(
                        {
                            "target_xpath": _norm_text(target_col),
                            "source_xpath": source_value,
                            "cardinality": "",
                            "condition": "",
                            "note": " | ".join(note_parts),
                            "m_o": clean(row.get(mo_col)) if mo_col else "",
                            "layout": "x12_segment",
                        }
                    )

            if rules:
                extraction["selected_columns"]["target_matrix_columns"] = matrix_target_cols
                parser_diagnostics["extraction"] = extraction
                parser_diagnostics["rule_count"] = len(rules)
                _finalize_parser_diagnostics(parser_diagnostics)
                return rules

        tgt_col, tgt_candidates = _resolve_column_by_priority(
            cols,
            [
                ("target", "xpath"),
                ("element", "xpath"),
                ("segment", "field", "xpath"),
                ("field", "name"),
                ("target",),
                ("xpath",),
            ],
        )

        src_col, src_candidates = _resolve_column_by_priority(
            cols,
            [
                ("x12", "segment"),
                ("x12", "xpath"),
                ("edifact", "segment"),
                ("edifact", "xpath"),
                ("source", "xpath"),
                ("segment", "xpath"),
                ("xpath",),
            ],
        )

        # Use value-signature disambiguation when xpath-like candidates overlap.
        source_scores = {candidate: _column_signature_scores(df, candidate) for candidate in _unique_preserve_order(tgt_candidates + src_candidates)}
        if len(tgt_candidates) > 1:
            tgt_col = max(
                tgt_candidates,
                key=lambda candidate: (
                    source_scores[candidate][1],  # target-like signals
                    -source_scores[candidate][0],  # avoid source-like columns for target
                ),
            )
        if len(src_candidates) > 1:
            src_col = max(
                src_candidates,
                key=lambda candidate: (
                    source_scores[candidate][0],  # source-like signals
                    -source_scores[candidate][1],  # avoid target-like columns for source
                ),
            )

        # For JABIL/X12 specs, prefer right-most xpath-style source if multiple appear.
        if workbook_family == "jabil" and len(src_candidates) > 1:
            src_col = src_candidates[-1]
        if src_col == tgt_col:
            alternative_src_candidates = [candidate for candidate in src_candidates if candidate != tgt_col]
            if alternative_src_candidates:
                src_col = max(
                    alternative_src_candidates,
                    key=lambda candidate: (
                        source_scores.get(candidate, (0, 0))[0],
                        -source_scores.get(candidate, (0, 0))[1],
                    ),
                )
            else:
                src_col = None

        cond_col = _first_col_matching(cols, "mapping", "rule") or _first_col_matching(cols, "condition")
        note_col = _first_col_matching(cols, "format", "note") or _first_col_matching(cols, "note")
        _record_column_resolution(
            extraction,
            "target",
            tgt_candidates,
            tgt_col,
        )
        _record_column_resolution(
            extraction,
            "source",
            src_candidates,
            src_col,
        )
        _record_column_resolution(
            extraction,
            "condition",
            _matching_columns(cols, "mapping", "rule") + _matching_columns(cols, "condition"),
            cond_col,
        )
        _record_column_resolution(
            extraction,
            "note",
            _matching_columns(cols, "format", "note") + _matching_columns(cols, "note"),
            note_col,
        )

        if not tgt_col:
            extraction["warnings"].append("No target column could be resolved for x12_segment layout")
            parser_diagnostics["extraction"] = extraction
            parser_diagnostics["rule_count"] = 0
            _finalize_parser_diagnostics(parser_diagnostics)
            return []

        rules = []
        df2 = df.dropna(subset=[tgt_col], how="all")
        for _, row in df2.iterrows():
            tgt = clean(row.get(tgt_col))
            src = clean(row.get(src_col)) if src_col else ""
            if not tgt:
                continue
            rules.append(
                {
                    "target_xpath": tgt,
                    "source_xpath": src,
                    "cardinality": "",
                    "condition": clean(row.get(cond_col)) if cond_col else "",
                    "note": clean(row.get(note_col)) if note_col else "",
                    "m_o": clean(row.get(mo_col)) if mo_col else "",
                    "layout": "x12_segment",
                }
            )
        parser_diagnostics["extraction"] = extraction
        parser_diagnostics["rule_count"] = len(rules)
        _finalize_parser_diagnostics(parser_diagnostics)
        return rules

    if layout == "cdm_target":
        tgt_col, tgt_candidates = _resolve_column_by_priority(
            cols,
            [("field", "name"), ("target", "field")],
        )
        src_col, src_candidates = _resolve_column_by_priority(cols, [("source", "xpath"), ("xpath",)])
        cond_col, cond_candidates = _resolve_column_by_priority(cols, [("condition",)])
        note_col, note_candidates = _resolve_column_by_priority(cols, [("format",), ("note",)])
        _record_column_resolution(extraction, "target", tgt_candidates, tgt_col)
        _record_column_resolution(extraction, "source", src_candidates, src_col)
        _record_column_resolution(extraction, "condition", cond_candidates, cond_col)
        _record_column_resolution(extraction, "note", note_candidates, note_col)

        anchor_col = tgt_col or src_col
        if not anchor_col:
            extraction["warnings"].append("No anchor column could be resolved for cdm_target layout")
            parser_diagnostics["extraction"] = extraction
            parser_diagnostics["rule_count"] = 0
            _finalize_parser_diagnostics(parser_diagnostics)
            return []

        rules = []
        df2 = df.dropna(subset=[anchor_col], how="all")
        for _, row in df2.iterrows():
            tgt = clean(row.get(tgt_col)) if tgt_col else ""
            src = clean(row.get(src_col)) if src_col else ""
            if not tgt and not src:
                continue
            rules.append(
                {
                    "target_xpath": tgt,
                    "source_xpath": src,
                    "cardinality": "",
                    "condition": clean(row.get(cond_col)) if cond_col else "",
                    "note": clean(row.get(note_col)) if note_col else "",
                    "m_o": clean(row.get(mo_col)) if mo_col else "",
                    "layout": "cdm_target",
                }
            )
        parser_diagnostics["extraction"] = extraction
        parser_diagnostics["rule_count"] = len(rules)
        _finalize_parser_diagnostics(parser_diagnostics)
        return rules

    # xpath_target
    tgt_col, tgt_candidates = _resolve_column_by_priority(
        cols,
        [
            ("target", "xpath"),
            ("segment", "field", "xpath"),
            ("element", "xpath"),
            ("xpath",),
        ],
    )

    src_col = None
    xpath_like = [c for c in cols if _keyword_match(c, "xpath")]
    src_candidates: list[str] = []
    if tgt_col and xpath_like:
        src_candidates = _unique_preserve_order([c for c in xpath_like if c != tgt_col])
        if src_candidates:
            # Common workbook pattern: target uses base xpath header while source is the duplicate
            # variant of the same base (e.g., segment/field xpath + segment/field xpath__dup2).
            duplicate_of_target = [
                candidate for candidate in src_candidates
                if _column_base(candidate) == _column_base(tgt_col) and candidate != tgt_col
            ]
            if duplicate_of_target:
                src_col = duplicate_of_target[-1]
                src_candidates = [src_col]

            explicit_source, explicit_candidates = _resolve_column_by_priority(
                src_candidates,
                [("source", "xpath"), ("source",)],
            )
            src_col = explicit_source or src_candidates[-1]
            if explicit_candidates:
                src_candidates = explicit_candidates

    card_col, card_candidates = _resolve_column_by_priority(cols, [("cardinality",)])
    cond_col, cond_candidates = _resolve_column_by_priority(cols, [("condition",)])
    note_col, note_candidates = _resolve_column_by_priority(cols, [("note",)])
    _record_column_resolution(
        extraction,
        "target",
        tgt_candidates,
        tgt_col,
    )
    _record_column_resolution(extraction, "source", src_candidates, src_col)
    _record_column_resolution(extraction, "cardinality", card_candidates, card_col)
    _record_column_resolution(extraction, "condition", cond_candidates, cond_col)
    _record_column_resolution(extraction, "note", note_candidates, note_col)

    if not tgt_col:
        extraction["warnings"].append("No target column could be resolved for xpath_target layout")
        parser_diagnostics["extraction"] = extraction
        parser_diagnostics["rule_count"] = 0
        _finalize_parser_diagnostics(parser_diagnostics)
        return []

    rules = []
    df2 = df.dropna(subset=[tgt_col], how="all")
    for _, row in df2.iterrows():
        tgt = clean(row.get(tgt_col))
        src = clean(row.get(src_col)) if src_col else ""
        if not tgt:
            continue
        rules.append(
            {
                "target_xpath": tgt,
                "source_xpath": src,
                "cardinality": clean(row.get(card_col)) if card_col else "",
                "condition": clean(row.get(cond_col)) if cond_col else "",
                "note": clean(row.get(note_col)) if note_col else "",
                "m_o": clean(row.get(mo_col)) if mo_col else "",
                "layout": "xpath_target",
            }
        )
    parser_diagnostics["extraction"] = extraction
    parser_diagnostics["rule_count"] = len(rules)
    _finalize_parser_diagnostics(parser_diagnostics)
    return rules
