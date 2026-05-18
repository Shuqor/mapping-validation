import core.spec_reader as sr

spec = sr.read_mapping_table('rules/Inttra-Contivo_X12_300_5030_to_JSON_BOOKINGINBOUND.xlsx')
rules = sr.extract_rules(spec)

# Show first 15 rules with their structure
for i, rule in enumerate(rules[:15]):
    print(f'{i+1}. Name: {rule.get("name", "N/A")}')
    cond = rule.get("condition", "")
    if isinstance(cond, dict):
        print(f'   Condition (dict): {cond}')
    else:
        print(f'   Condition: {cond}')
    print(f'   Target: {rule.get("target", "N/A")}')
    conv = rule.get("conversion", "")
    if conv:
        print(f'   Conversion: {conv[:100]}...')
    print()
