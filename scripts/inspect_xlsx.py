import pandas as pd
from pathlib import Path

rules_dir = Path(r"c:\Users\mohdshuqor.nordin\OneDrive - WiseTech Global\Documents\Mapping Validation Program\rules")

for f in sorted(rules_dir.glob("*.xlsx")):
    print("\n" + "="*60)
    print("FILE:", f.name)
    try:
        xl = pd.ExcelFile(str(f), engine="openpyxl")
        print("SHEETS:", xl.sheet_names)
        for sheet in xl.sheet_names[:2]:
            print("\n  -- Sheet:", sheet, "--")
            df = pd.read_excel(str(f), sheet_name=sheet, header=None, engine="openpyxl", nrows=20)
            print(df.to_string())
    except Exception as e:
        print("  ERROR:", e)
