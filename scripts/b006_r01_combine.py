import csv
import json
import sys
from collections import Counter
from pathlib import Path

try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(2**31 - 1)

ROOT = Path('audit_artifacts')
OUT = Path('out')
OUT.mkdir(exist_ok=True)
files = sorted(ROOT.rglob('B006_R01_Shard*_1000_audited.csv'))
if len(files) != 20:
    raise RuntimeError(f'Expected 20 audited shards, found {len(files)}')

rows = []
headers = None
students = Counter()
relevance = Counter()
priority = Counter()
k_counts = Counter()
audit_counts = Counter()
http_counts = Counter()
for path in files:
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        headers = headers or reader.fieldnames or []
        for row in reader:
            rows.append(row)
            students[row.get('student') or ''] += 1
            relevance[row.get('relevance') or ''] += 1
            priority[row.get('download_priority') or ''] += 1
            k_counts[row.get('K_primary') or row.get('primary_k_domain') or ''] += 1
            audit_counts[row.get('link_audit_result') or ''] += 1
            http_counts[str(row.get('link_http_status') or '')] += 1
rows.sort(key=lambda row: row.get('B006_ID') or '')
unique_dois = len({(row.get('doi') or '').lower() for row in rows})
unique_ids = len({row.get('B006_ID') for row in rows})

with (OUT / 'B006_R01_20000_master_audited.csv').open('w', encoding='utf-8-sig', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=headers)
    writer.writeheader()
    writer.writerows(rows)
for index in range(1, 11):
    student = f'Student{index:02d}'
    subset = sorted((row for row in rows if row.get('student') == student), key=lambda row: row.get('B006_ID') or '')
    with (OUT / f'B006_R01_{student}_2000.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(subset)

invalid = audit_counts.get('链接无效', 0)
status = 'success'
if (
    len(rows) != 20000
    or unique_dois != 20000
    or unique_ids != 20000
    or not rows
    or rows[0].get('B006_ID') != 'B006-000001'
    or rows[-1].get('B006_ID') != 'B006-020000'
    or any(students.get(f'Student{i:02d}', 0) != 2000 for i in range(1, 11))
    or set(relevance) - {'A', 'B'}
    or invalid > 200
):
    status = 'failure'
summary = {
    'stage': 'B006-R01',
    'status': status,
    'records': len(rows),
    'unique_dois': unique_dois,
    'unique_ids': unique_ids,
    'id_start': rows[0].get('B006_ID') if rows else '',
    'id_end': rows[-1].get('B006_ID') if rows else '',
    'student_counts': dict(students),
    'K_counts': dict(k_counts),
    'relevance_counts': dict(relevance),
    'priority_counts': dict(priority),
    'link_audit_counts': dict(audit_counts),
    'http_status_counts': dict(http_counts),
    'invalid_link_records': invalid,
    'review_link_records': audit_counts.get('需复核', 0),
    'quality_gate': {
        'records': 20000,
        'unique_dois': 20000,
        'each_student': 2000,
        'id_start': 'B006-000001',
        'id_end': 'B006-020000',
        'A_B_only': True,
        'invalid_links_max': 200,
        'audit_shards': 20,
    },
    'next': 'Release B006-R01 and prepare B006-R02 final remaining 803 verified A/B records',
}
(OUT / 'run_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
(OUT / 'stage_report.md').write_text('\n'.join([
    '# B006 R01 Report', '',
    f'- Status: **{status}**',
    f'- Records: {len(rows):,}',
    f'- Unique DOIs: {unique_dois:,}',
    f'- IDs: {summary["id_start"]} to {summary["id_end"]}',
    f'- Students: {dict(students)}',
    f'- K counts: {dict(k_counts)}',
    f'- Relevance: {dict(relevance)}',
    f'- Priority: {dict(priority)}',
    f'- Link audit: {dict(audit_counts)}',
    f'- Next: {summary["next"]}',
]), encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False), flush=True)
if status != 'success':
    raise SystemExit(2)
