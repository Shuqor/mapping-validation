
from core.spec_reader import read_mapping_table

df = read_mapping_table("rules/spec.xlsx")

print("=== Columns in Mapping sheet ===")
for c in df.columns:
    print("-", c)

xpath_cols = ["segment / field xpath", "xpath", "segment / field xpath.1"]
existing = [c for c in xpath_cols if c in df.columns]

df2 = df.dropna(subset=existing, how="all")

print("\n=== First 10 real mapping rows (all xpath cols) ===")
print(df2[existing + ["cardinality", "condition", "note"]].head(10))
