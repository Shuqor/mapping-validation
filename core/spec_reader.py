
from pathlib import Path
import pandas as pd


def _detect_file_format(spec_path: str) -> str:
    """
    Detect file format based on extension.
    Returns 'csv' or 'excel'.
    """
    path = Path(spec_path)
    suffix = path.suffix.lower()
    
    if suffix == ".csv":
        return "csv"
    elif suffix in [".xlsx", ".xls"]:
        return "excel"
    else:
        raise ValueError(f"Unsupported file format: {suffix}. Expected .csv, .xlsx, or .xls")


def read_spec(spec_path: str, sheet_name: str = "Mapping") -> pd.DataFrame:
    """
    Read and return the Mapping sheet from spec file (Excel or CSV).
    CSV files are read directly; Excel uses the specified sheet_name.
    """
    path = Path(spec_path)
    if not path.exists():
        raise FileNotFoundError(f"Spec file not found: {spec_path}")

    file_format = _detect_file_format(spec_path)
    
    if file_format == "csv":
        df = pd.read_csv(spec_path)
    else:  # excel
        df = pd.read_excel(path, sheet_name=sheet_name, engine="openpyxl")

    # Normalize column names for easier matching later
    df.columns = [str(c).strip().lower() for c in df.columns]

    return df


def detect_header_row(df):
    """
    Find the row index that contains real column headers
    like 'segment / field xpath', 'cardinality', 'condition'.
    """
    header_keywords = [
        "segment",
        "xpath",
        "cardinality",
        "condition",
        "description",
        "value"
    ]

    for idx, row in df.iterrows():
        values = " ".join(str(v).lower() for v in row.values if pd.notna(v))
        if any(k in values for k in header_keywords):
            return idx

    raise ValueError("Could not detect header row in mapping spec")



def read_mapping_table(spec_path: str, sheet_name: str = "Mapping") -> pd.DataFrame:
    """
    Read mapping spec and return a clean DataFrame starting
    from the detected header row.
    Works with both CSV and Excel files.
    """
    file_format = _detect_file_format(spec_path)
    
    if file_format == "csv":
        raw_df = pd.read_csv(spec_path, header=None)
    else:  # excel
        raw_df = pd.read_excel(spec_path, sheet_name=sheet_name, engine="openpyxl", header=None)

    header_row = detect_header_row(raw_df)

    if file_format == "csv":
        df = pd.read_csv(spec_path, header=header_row)
    else:  # excel
        df = pd.read_excel(
            spec_path,
            sheet_name=sheet_name,
            engine="openpyxl",
            header=header_row
        )

    df.columns = [str(c).strip().lower() for c in df.columns]
    df = df.dropna(how="all")  # remove completely empty rows

    return df



def extract_rules(df):
    tgt_col = "segment / field xpath"
    src_col1 = "xpath"
    src_col2 = "segment / field xpath.1"

    card_col = "cardinality"
    cond_col = "condition"
    note_col = "note"

    def clean(v):
        return "" if pd.isna(v) else str(v).strip()

    df2 = df.dropna(subset=[tgt_col], how="all")

    rules = []
    for _, r in df2.iterrows():
        src = clean(r.get(src_col1)) or clean(r.get(src_col2))

        rule = {
            "target_xpath": clean(r.get(tgt_col)),
            "source_xpath": src,
            "cardinality": clean(r.get(card_col)),
            "condition": clean(r.get(cond_col)),
            "note": clean(r.get(note_col)),
        }

        if rule["target_xpath"]:
            rules.append(rule)

    return rules

