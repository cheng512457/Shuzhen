from pathlib import Path

source = Path('scripts/b006_e2_prepare.py').read_text(encoding='utf-8')
replacements = {
    'B006_E1_V2_new_high_precision_candidates.csv': 'B009_E1_new_high_precision_candidates.csv',
    'B004_B005_226220_cumulative_master.csv': 'B004_B005_B006_B007_B008_285204_cumulative_master.csv',
    'if len(excluded)!=226220': 'if len(excluded)!=285204',
    'B004_B005_226220_excluded_dois.txt': 'B004_B005_B006_B007_B008_285204_excluded_dois.txt',
    'B006_E2_input_shard': 'B009_E2_input_shard',
    "'stage':'B006-E2-prepare'": "'stage':'B009-E2-prepare'",
    'if rows!=28399': 'if rows!=26527',
}
for old, new in replacements.items():
    source = source.replace(old, new)
exec(compile(source, 'scripts/b009_e2_prepare_runtime.py', 'exec'))
