import csv
import json
import os
import sys
from collections import Counter
from pathlib import Path

try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(2**31 - 1)

ROUND_CODE = os.environ.get('ROUND_CODE', 'R06').strip()
START_ID = int(os.environ.get('START_ID', '130001'))
STUDENT_COUNT = int(os.environ.get('STUDENT_COUNT', '10'))
ROOT = Path('audit_artifacts')
PREP = Path('prepared_artifact')
OUT = Path('out')
OUT.mkdir(exist_ok=True)

prep_files = list(PREP.rglob('prepare_summary.json'))
if len(prep_files) != 1:
    raise RuntimeError(f'Expected one prepare summary, found {len(prep_files)}')
prep = json.loads(prep_files[0].read_text(encoding='utf-8'))
expected_records = int(prep['remaining_records'])
expected_shards = int(prep['audit_shards'])
expected_student_counts = {k:int(v) for k,v in prep['student_counts'].items()}

files = sorted(ROOT.rglob(f'B004_{ROUND_CODE}_Shard*_audited.csv'))
if len(files) != expected_shards:
    raise RuntimeError(f'Expected {expected_shards} audited shards, found {len(files)}')

rows = []
headers = None
student_counts = Counter(); rel = Counter(); pri = Counter(); kc = Counter(); evidence = Counter(); audit = Counter(); http = Counter()
for path in files:
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if headers is None:
            headers = reader.fieldnames or []
        for row in reader:
            rows.append(row)
            student_counts[row.get('student') or ''] += 1
            rel[row.get('relevance') or ''] += 1
            pri[row.get('download_priority') or ''] += 1
            kc[row.get('K_primary') or ''] += 1
            evidence[row.get('evidence_mode') or ''] += 1
            audit[row.get('link_audit_result') or ''] += 1
            http[str(row.get('link_http_status') or '')] += 1
rows.sort(key=lambda r: r.get('B004_ID') or '')
unique_dois = len({(r.get('doi') or '').lower() for r in rows})
unique_ids = len({r.get('B004_ID') for r in rows})
id_start = f'B004-{START_ID:06d}'
id_end = f'B004-{START_ID+expected_records-1:06d}'

with (OUT/f'B004_{ROUND_CODE}_{expected_records}_master_audited.csv').open('w', encoding='utf-8-sig', newline='') as f:
    w = csv.DictWriter(f, fieldnames=headers)
    w.writeheader(); w.writerows(rows)
for i in range(1, STUDENT_COUNT + 1):
    student = f'Student{i:02d}'
    subset = [r for r in rows if r.get('student') == student]
    subset.sort(key=lambda r: r.get('B004_ID') or '')
    with (OUT/f'B004_{ROUND_CODE}_{student}_{len(subset)}.csv').open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader(); w.writerows(subset)

invalid = audit.get('链接无效', 0)
review = audit.get('需复核', 0)
invalid_max = max(100, int(expected_records * 0.01))
status = 'success'
if (
    len(rows) != expected_records or unique_dois != expected_records or unique_ids != expected_records
    or not rows or rows[0].get('B004_ID') != id_start or rows[-1].get('B004_ID') != id_end
    or any(student_counts.get(k, 0) != v for k,v in expected_student_counts.items())
    or set(rel) - {'A','B'} or invalid > invalid_max
):
    status = 'failure'
summary = {
    'stage':'S4-final-round','round_code':ROUND_CODE,'status':status,
    'records':len(rows),'unique_dois':unique_dois,'unique_ids':unique_ids,
    'id_start':rows[0].get('B004_ID') if rows else '',
    'id_end':rows[-1].get('B004_ID') if rows else '',
    'student_counts':dict(student_counts),'K_counts':dict(kc),
    'relevance_counts':dict(rel),'priority_counts':dict(pri),
    'evidence_mode_counts':dict(evidence),'link_audit_counts':dict(audit),
    'http_status_counts':dict(http),'invalid_link_records':invalid,'review_link_records':review,
    'excluded_previous_unique_dois':prep.get('excluded_unique_dois'),
    'formal_pool_total':prep.get('formal_pool_total'),
    'quality_gate':{
        'records':expected_records,'unique_dois':expected_records,
        'student_counts':expected_student_counts,'id_start':id_start,'id_end':id_end,
        'A_B_only':True,'invalid_links_max':invalid_max,'audit_shards':expected_shards
    },
    'next':'Freeze the complete non-overlapping B004 A/B download pool and create final cumulative DOI audit'
}
(OUT/'run_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'stage_report.md').write_text('\n'.join([
    f'# B004 {ROUND_CODE} Final-Round Report','',f'- Status: **{status}**',
    f'- Records: {len(rows):,}',f'- Unique DOIs: {unique_dois:,}',
    f'- Permanent IDs: {summary["id_start"]} to {summary["id_end"]}',
    f'- Student counts: {dict(student_counts)}',f'- K counts: {dict(kc)}',
    f'- Relevance: {dict(rel)}',f'- Priority: {dict(pri)}',
    f'- Link audit: {dict(audit)}',f'- Next: {summary["next"]}'
]),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False),flush=True)
if status != 'success':
    raise SystemExit(2)
