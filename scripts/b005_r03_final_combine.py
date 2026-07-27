import csv, json, sys
from collections import Counter
from pathlib import Path

try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(2**31 - 1)

PREPARED = Path('prepared_artifact')
ROOT = Path('audit_artifacts')
OUT = Path('out')
OUT.mkdir(exist_ok=True)
summary_files = list(PREPARED.rglob('prepare_summary.json'))
if len(summary_files) != 1:
    raise RuntimeError(f'Expected one preparation summary, found {len(summary_files)}')
prepared = json.loads(summary_files[0].read_text(encoding='utf-8'))
expected_records = int(prepared['remaining_records'])
expected_shards = int(prepared['audit_shards'])
files = sorted(ROOT.rglob('B005_R03_Shard*_audited.csv'))
if len(files) != expected_shards:
    raise RuntimeError(f'Expected {expected_shards} audited shards, found {len(files)}')

rows = []
headers = None
students = Counter(); relevance = Counter(); priority = Counter(); kcounts = Counter(); audit = Counter(); http = Counter(); evidence = Counter()
for path in files:
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        headers = headers or reader.fieldnames or []
        for row in reader:
            rows.append(row)
            students[row.get('student') or ''] += 1
            relevance[row.get('relevance') or ''] += 1
            priority[row.get('download_priority') or ''] += 1
            kcounts[row.get('K_primary') or ''] += 1
            audit[row.get('link_audit_result') or ''] += 1
            http[str(row.get('link_http_status') or '')] += 1
            evidence[row.get('evidence_mode') or ''] += 1
rows.sort(key=lambda r: r.get('B005_ID') or '')
unique_dois = len({(r.get('doi') or '').lower() for r in rows})
unique_ids = len({r.get('B005_ID') for r in rows})

with (OUT/'B005_R03_8303_master_audited.csv').open('w', encoding='utf-8-sig', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=headers)
    writer.writeheader(); writer.writerows(rows)
for student in range(1, 11):
    subset = [r for r in rows if r.get('student') == f'Student{student:02d}']
    subset.sort(key=lambda r: r.get('B005_ID') or '')
    with (OUT/f'B005_R03_Student{student:02d}_{len(subset)}.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader(); writer.writerows(subset)

student_values = [students.get(f'Student{i:02d}', 0) for i in range(1, 11)]
invalid = audit.get('链接无效', 0)
status = 'success'
checks = {
    'records_equal_expected': len(rows) == expected_records == 8303,
    'unique_dois_equal_records': unique_dois == len(rows),
    'unique_ids_equal_records': unique_ids == len(rows),
    'id_start_correct': bool(rows) and rows[0].get('B005_ID') == 'B005-060001',
    'id_end_correct': bool(rows) and rows[-1].get('B005_ID') == 'B005-068303',
    'students_balanced': bool(student_values) and max(student_values) - min(student_values) <= 1 and sum(student_values) == len(rows),
    'A_B_only': not (set(relevance) - {'A','B'}),
    'invalid_links_within_limit': invalid <= 100,
    'prior_overlap_zero': prepared.get('overlap_b004') == 0 and prepared.get('excluded_r01') == 30000 and prepared.get('excluded_r02') == 30000,
    'all_shards_present': len(files) == expected_shards,
}
if not all(checks.values()):
    status = 'failure'
summary = {
    'stage':'B005-R03','status':status,'records':len(rows),'unique_dois':unique_dois,'unique_ids':unique_ids,
    'id_start':rows[0].get('B005_ID') if rows else '','id_end':rows[-1].get('B005_ID') if rows else '',
    'excluded_previous_unique_dois':prepared.get('excluded_union'),
    'B004_overlap':prepared.get('overlap_b004'),'R01_excluded':prepared.get('excluded_r01'),'R02_excluded':prepared.get('excluded_r02'),
    'student_counts':dict(students),'K_counts':dict(kcounts),'relevance_counts':dict(relevance),'priority_counts':dict(priority),
    'evidence_mode_counts':dict(evidence),'link_audit_counts':dict(audit),'http_status_counts':dict(http),
    'invalid_link_records':invalid,'review_link_records':audit.get('需复核',0),'quality_checks':checks,
    'next':'Freeze B005 complete 68303-record A/B database and perform cumulative B004+B005 DOI audit'
}
(OUT/'run_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
(OUT/'stage_report.md').write_text('\n'.join([
    '# B005 R03 Final Remaining-Pool Report','',f'- Status: **{status}**',f'- Records: {len(rows):,}',
    f'- Unique DOIs: {unique_dois:,}',f'- IDs: {summary["id_start"]} to {summary["id_end"]}',
    f'- Previous unique DOIs excluded: {summary["excluded_previous_unique_dois"]:,}',f'- Students: {dict(students)}',
    f'- K counts: {dict(kcounts)}',f'- Relevance: {dict(relevance)}',f'- Priority: {dict(priority)}',
    f'- Link audit: {dict(audit)}',f'- Next: {summary["next"]}'
]), encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False), flush=True)
if status != 'success':
    raise SystemExit(2)
