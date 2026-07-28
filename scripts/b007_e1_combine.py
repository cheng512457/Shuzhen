from pathlib import Path

source = Path('scripts/b006_e1_v2_combine.py').read_text(encoding='utf-8')
replacements = {
    "B006_E1_V2": "B007_E1",
    "B004_B005_226220_excluded_dois.txt": "B004_B005_B006_247023_excluded_dois.txt",
    "if len(excluded)!=226220": "if len(excluded)!=247023",
    "'new_unique_dois_min_20000':len(rows)>=20000": "'new_unique_dois_min_15000':len(rows)>=15000",
    "'HP_A_B_min_12000':hpab>=12000": "'HP_A_B_min_10000':hpab>=10000",
    "km.get(f'K{i:02d}',0)<250": "km.get(f'K{i:02d}',0)<150",
    "'each_K_membership_min_250'": "'each_K_membership_min_150'",
    "'stage':'B006-E1-v2'": "'stage':'B007-E1'",
    "'prior_registry_dois':len(excluded)": "'prior_registry_dois':len(excluded)",
    "'overlap_with_B004_B005':overlap": "'overlap_with_B004_B005_B006':overlap",
    "B006-E2 metadata verification, conservative A/B/C classification and stratified precision audit": "B007-E2 metadata verification, conservative A/B/C classification and stratified precision audit",
    "# B006 E1 v2 High-Precision Expansion Report": "# B007 E1 High-Precision Expansion Report",
}
for old,new in replacements.items():
    source = source.replace(old,new)
exec(compile(source,'scripts/b007_e1_combine_runtime.py','exec'))
