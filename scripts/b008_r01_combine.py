import csv, json, sys
from collections import Counter
from pathlib import Path

try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(2**31 - 1)

ROOT = Path('audit_artifacts')
OUT = Path('out')
OUT.mkdir(exist_ok=True)
EXPECTED = 18406
SHARDS = 19
files = sorted(ROOT.rglob('B008_R01_Shard*_audited.csv'))
if len(files) != SHARDS:
    raise RuntimeError(f'Expected {SHARDS} audited shards, found {len(files)}')

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

rows.sort(key=lambda r: r.get('B008_ID') or '')
unique_dois = len({(r.get('doi') or '').lower() for r in rows})
unique_ids = len({r.get('B008_ID') for r in rows})

with (OUT / 'B008_R01_18406_master_audited.csv').open('w', encoding='utf-8-sig', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=headers)
    writer.writeheader()
    writer.writerows(rows)
for i in range(1, 11):
    student = f'Student{i:02d}'
    subset = [r for r in rows if r.get('student') == student]
    with (OUT / f'B008_R01_{student}_{len(subset)}.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(subset)

invalid = audit_counts.get('链接无效', 0)
student_counts = [students.get(f'Student{i:02d}', 0) for i in range(1, 11)]
quality = {
    'records_18406': len(rows) == EXPECTED,
    'unique_dois_18406': unique_dois == EXPECTED,
    'unique_ids_18406': unique_ids == EXPECTED,
    'id_start_B008_000001': bool(rows) and rows[0].get('B008_ID') == 'B008-000001',
    'id_end_B008_018406': bool(rows) and rows[-1].get('B008_ID') == 'B008-018406',
    'student_difference_max_1': bool(student_counts) and max(student_counts) - min(student_counts) <= 1,
    'student_total_18406': sum(student_counts) == EXPECTED,
    'A_B_only': not (set(relevance) - {'A', 'B'}),
    'invalid_links_max_200': invalid <= 200,
    'audit_shards_19': len(files) == SHARDS,
}
status = 'success' if all(quality.values()) else 'failure'
summary = {
    'stage': 'B008-R01', 'status': status,
    'records': len(rows), 'unique_dois': unique_dois, 'unique_ids': unique_ids,
    'id_start': rows[0].get('B008_ID') if rows else '',
    'id_end': rows[-1].get('B008_ID') if rows else '',
    'student_counts': dict(students), 'K_counts': dict(k_counts),
    'relevance_counts': dict(relevance), 'priority_counts': dict(priority),
    'link_audit_counts': dict(audit_counts), 'http_status_counts': dict(http_counts),
    'invalid_link_records': invalid, 'review_link_records': audit_counts.get('需复核', 0),
    'quality_gate': quality,
    'next': 'Freeze B008 complete 18406-record A/B database and perform cumulative B004+B005+B006+B007+B008 DOI audit',
}
(OUT / 'run_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
(OUT / 'stage_report.md').write_text('\n'.join([
    '# B008 R01 Final Report', '', f'- Status: **{status}**',
    f'- Records: {len(rows):,}', f'- Unique DOIs: {unique_dois:,}',
    f'- IDs: {summary["id_start"]} to {summary["id_end"]}',
    f'- Students: {dict(students)}', f'- K counts: {dict(k_counts)}',
    f'- Relevance: {dict(relevance)}', f'- Priority: {dict(priority)}',
    f'- Link audit: {dict(audit_counts)}', f'- Quality gate: {quality}',
    f'- Next: {summary["next"]}',
]), encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False), flush=True)
if status != 'success':
    raise SystemExit(2)
