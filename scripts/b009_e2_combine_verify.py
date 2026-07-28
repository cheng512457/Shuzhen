from pathlib import Path

source = Path('scripts/b008_e2_combine_verify.py').read_text(encoding='utf-8')
source = source.replace('B008', 'B009')
replacements = {
    'B004_B005_B006_B007_266798_cumulative_master.csv': 'B004_B005_B006_B007_B008_285204_cumulative_master.csv',
    'if len(prior)!=266798': 'if len(prior)!=285204',
    'if len(rows)!=33036': 'if len(rows)!=26527',
    "'classified_rows_33036':len(all_rows)==33036": "'classified_rows_26527':len(all_rows)==26527",
    'B009-R01 first verified non-overlapping student download round': 'B009-R01 first verified non-overlapping student download round',
}
for old, new in replacements.items():
    source = source.replace(old, new)
exec(compile(source, 'scripts/b009_e2_combine_verify_runtime.py', 'exec'))
