from pathlib import Path

source = Path('scripts/b006_e2_prepare.py').read_text(encoding='utf-8')
replacements = {
    'B006_E1_V2_new_high_precision_candidates.csv': 'B007_E1_new_high_precision_candidates.csv',
    'B004_B005_226220_cumulative_master.csv': 'B004_B005_B006_247023_cumulative_master.csv',
    'if len(excluded)!=226220': 'if len(excluded)!=247023',
    'B004_B005_226220_excluded_dois.txt': 'B004_B005_B006_247023_excluded_dois.txt',
    'B006_E2_input_shard': 'B007_E2_input_shard',
    "'stage':'B006-E2-prepare'": "'stage':'B007-E2-prepare'",
    'if rows!=28399': 'if rows!=31209',
}
for old, new in replacements.items():
    source = source.replace(old, new)
exec(compile(source, 'scripts/b007_e2_prepare_runtime.py', 'exec'))
