from pathlib import Path

source = Path('scripts/b006_e1_v2_discover.py').read_text(encoding='utf-8')
replacements = {
    "B004_B005_226220_excluded_dois.txt": "B004_B005_B006_B007_B008_285204_excluded_dois.txt",
    "B006_E1_seeds_": "B009_E1_seeds_",
    "B006_E1_V2": "B009_E1",
    "Unexpected prior DOI count {len(excluded)}": "Unexpected B009 prior DOI count {len(excluded)}",
    "if len(excluded) != 226220": "if len(excluded) != 285204",
    "pages=3": "pages=8",
    "pages=4": "pages=8",
    ")[:5000]": ")[:10000]",
    "[:45]": "[:75]",
    "[:30]": "[:55]",
    "[:80]": "[:150]",
    "most_common(90)": "most_common(150)",
    "per-page':100": "per-page':200",
}
for old, new in replacements.items():
    source = source.replace(old, new)
exec(compile(source, 'scripts/b009_e1_discover_runtime.py', 'exec'))
