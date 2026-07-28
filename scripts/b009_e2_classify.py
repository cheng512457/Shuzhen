from pathlib import Path

source = Path('scripts/b006_e2_classify.py').read_text(encoding='utf-8')
replacements = {
    'B006_E2_input_shard': 'B009_E2_input_shard',
    'Shuzhen-B006-E2/1.0': 'Shuzhen-B009-E2/1.0',
    'B006_E2_classified_shard': 'B009_E2_classified_shard',
    'B006_E2_shard': 'B009_E2_shard',
    "'stage':'B006-E2'": "'stage':'B009-E2'",
}
for old, new in replacements.items():
    source = source.replace(old, new)
exec(compile(source, 'scripts/b009_e2_classify_runtime.py', 'exec'))
