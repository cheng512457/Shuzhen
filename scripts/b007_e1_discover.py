from pathlib import Path

source = Path('scripts/b006_e1_v2_discover.py').read_text(encoding='utf-8')
replacements = {
    "B004_B005_226220_excluded_dois.txt": "B004_B005_B006_247023_excluded_dois.txt",
    "B006_E1_seeds_": "B007_E1_seeds_",
    "B006_E1_V2": "B007_E1",
    "Unexpected prior DOI count {len(excluded)}": "Unexpected B007 prior DOI count {len(excluded)}",
    "if len(excluded) != 226220": "if len(excluded) != 247023",
    "pages=3": "pages=6",
    "pages=4": "pages=6",
    ")[:5000]": ")[:8000]",
    "[:45]": "[:60]",
    "[:30]": "[:45]",
    "[:80]": "[:120]",
    "most_common(90)": "most_common(120)",
    "per-page':100": "per-page':150",
}
for old,new in replacements.items():
    source = source.replace(old,new)
exec(compile(source,'scripts/b007_e1_discover_runtime.py','exec'))
