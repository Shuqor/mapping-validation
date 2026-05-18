import glob
import os
from collections import defaultdict
import core.spec_reader as spec_reader
import core.validate as validate

# Find all xlsx spec files
xlsx_files = sorted(glob.glob('rules/**/*.xlsx', recursive=True))
print(f"Found {len(xlsx_files)} spec files\n")

# Track stats
total_rules = 0
matched_rules = defaultdict(int)
unmatched_rules = []
spec_coverage = {}

for spec_file in xlsx_files:
    try:
        table = spec_reader.read_mapping_table(spec_file)
        rules = spec_reader.extract_rules(table)
        spec_total = len(rules)
        spec_matched = 0
        
        for rule in rules:
            total_rules += 1
            name = rule.get('name', 'unknown')
            cond_raw = rule.get('condition', '')
            
            # Convert dict conditions to string if needed
            if isinstance(cond_raw, dict):
                cond = str(cond_raw)
            else:
                cond = cond_raw if isinstance(cond_raw, str) else ''
            
            # Check for direct_map and empty conditions early
            cond_lower = cond.lower().strip()
            is_direct_map = cond_lower.startswith('direct map') or not cond_lower
            
            # Try each parser
            matched = False
            try:
                # Direct map or empty condition
                if is_direct_map:
                    matched_rules['direct_map'] += 1
                    matched = True
                
                # Other extraction methods
                if validate._extract_hardcode_literal(cond) is not None:
                    matched_rules['hardcode_literal'] += 1
                    matched = True
                if validate._extract_concatenate_fields(cond) is not None:
                    matched_rules['concatenate'] += 1
                    matched = True
                if validate._extract_length_based_mapping(cond) is not None:
                    matched_rules['length_based'] += 1
                    matched = True
                if validate._extract_date_format_mapping(cond) is not None:
                    matched_rules['date_format'] += 1
                    matched = True
                if validate._extract_sequential_if_chain_map(cond) is not None:
                    matched_rules['sequential_chain'] += 1
                    matched = True
                if validate._extract_if_equals_chain_map(cond) is not None:
                    matched_rules['if_equals_chain'] += 1
                    matched = True
                if validate._extract_if_expression_chain_map(cond) is not None:
                    matched_rules['if_expression_chain'] += 1
                    matched = True
                if validate._extract_multi_condition_and_map(cond) is not None:
                    matched_rules['multi_condition_and'] += 1
                    matched = True
                if validate._extract_source_is_not_null_mapping(cond) is not None:
                    matched_rules['source_is_not_null'] += 1
                    matched = True
                if validate._extract_compute_statement(cond) is not None:
                    matched_rules['compute_statement'] += 1
                    matched = True
                if validate._extract_source_value_translation(cond) is not None:
                    matched_rules['value_translation'] += 1
                    matched = True
                if validate._extract_field_concat_mapping(cond) is not None:
                    matched_rules['field_concat'] += 1
                    matched = True
                if validate._extract_startswith_replace_mapping(cond) is not None:
                    matched_rules['startswith_replace'] += 1
                    matched = True
            except Exception:
                pass  # Skip on parse errors
            
            if matched:
                spec_matched += 1
            else:
                unmatched_rules.append({
                    'spec': os.path.basename(spec_file),
                    'rule': name,
                    'condition': (cond[:80] if cond else '(no condition)')
                })
        
        spec_coverage[spec_file] = (spec_matched, spec_total)
        
    except Exception as e:
        print(f"Error loading {spec_file}: {e}")

print("COVERAGE SUMMARY")
print("=" * 60)
print(f"Total rules across all specs: {total_rules}")
print(f"Rules matched by at least one parser: {total_rules - len(unmatched_rules)}")
print(f"Unmatched rules: {len(unmatched_rules)}")
print()
print("Parser hits by type:")
for parser, count in sorted(matched_rules.items(), key=lambda x: x[1], reverse=True):
    print(f"  {parser}: {count}")
print()

print("SPEC FILE COVERAGE (top 15)")
print("=" * 60)
for spec, (matched, total) in sorted(spec_coverage.items(), key=lambda x: x[1][0]/x[1][1] if x[1][1] > 0 else 0, reverse=True)[:15]:
    pct = 100 * matched / total if total > 0 else 0
    print(f"  {os.path.basename(spec)}: {matched}/{total} ({pct:.1f}%)")
print()

print("UNMATCHED RULES SAMPLE (first 30)")
print("=" * 60)
for i, rule in enumerate(unmatched_rules[:30]):
    print(f"{i+1}. {rule['spec']} / {rule['rule']}")
    print(f"   {rule['condition'][:100]}")

print(f"\n(Total unmatched: {len(unmatched_rules)} out of {total_rules})")
