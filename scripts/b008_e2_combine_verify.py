from pathlib import Path

source = Path('scripts/b007_e2_combine_verify.py').read_text(encoding='utf-8')
source = source.replace('B007', 'B008')
replacements = {
    'B004_B005_B006_247023_cumulative_master.csv': 'B004_B005_B006_B007_266798_cumulative_master.csv',
    'if len(prior)!=247023': 'if len(prior)!=266798',
    'if len(rows)!=31209': 'if len(rows)!=33036',
    "'classified_rows_31209':len(all_rows)==31209": "'classified_rows_33036':len(all_rows)==33036",
    'B008-R01 first verified non-overlapping student download round': 'B008-R01 first verified non-overlapping student download round',
}
for old, new in replacements.items():
    source = source.replace(old, new)
exec(compile(source, 'scripts/b008_e2_combine_verify_runtime.py', 'exec'))
