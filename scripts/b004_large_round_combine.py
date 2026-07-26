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

ROUND_CODE = os.environ.get('ROUND_CODE', 'R02').strip()
BATCH_SIZE = int(os.environ.get('BATCH_SIZE', '30000'))
START_ID = int(os.environ.get('START_ID', '10001'))
STUDENT_COUNT = int(os.environ.get('STUDENT_COUNT', '10'))
SHARD_SIZE = int(os.environ.get('SHARD_SIZE', '1000'))
ROOT = Path('audit_artifacts')
OUT = Path('out')
OUT.mkdir(exist_ok=True)

expected_shards = BATCH_SIZE // SHARD_SIZE
files = sorted(ROOT.rglob(f'B004_{ROUND_CODE}_Shard*_{SHARD_SIZE}_audited.csv'))
if len(files) != expected_shards:
    raise RuntimeError(f'Expected {expected_shards} audited shard CSVs, found {len(files)}')

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
per_student = BATCH_SIZE // STUDENT_COUNT
id_start = f'B004-{START_ID:06d}'
id_end = f'B004-{START_ID+BATCH_SIZE-1:06d}'

with (OUT/f'B004_{ROUND_CODE}_{BATCH_SIZE}_master_audited.csv').open('w', encoding='utf-8-sig', newline='') as f:
    w = csv.DictWriter(f, fieldnames=headers)
    w.writeheader(); w.writerows(rows)

for i in range(1, STUDENT_COUNT + 1):
    subset = [r for r in rows if r.get('student') == f'Student{i:02d}']
    subset.sort(key=lambda r: r.get('B004_ID') or '')
    with (OUT/f'B004_{ROUND_CODE}_Student{i:02d}_{per_student}.csv').open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader(); w.writerows(subset)

invalid = audit.get('链接无效', 0)
review = audit.get('需复核', 0)
invalid_max = max(100, int(BATCH_SIZE * 0.01))
status = 'success'
if (
    len(rows) != BATCH_SIZE or unique_dois != BATCH_SIZE or unique_ids != BATCH_SIZE
    or rows[0].get('B004_ID') != id_start or rows[-1].get('B004_ID') != id_end
    or any(student_counts.get(f'Student{i:02d}', 0) != per_student for i in range(1, STUDENT_COUNT + 1))
    or invalid > invalid_max
):
    status = 'failure'

summary = {
    'stage':'S4-large-round','round_code':ROUND_CODE,'status':status,
    'records':len(rows),'unique_dois':unique_dois,'unique_ids':unique_ids,
    'id_start':rows[0].get('B004_ID') if rows else '',
    'id_end':rows[-1].get('B004_ID') if rows else '',
    'student_counts':dict(student_counts),'K_counts':dict(kc),
    'relevance_counts':dict(rel),'priority_counts':dict(pri),
    'evidence_mode_counts':dict(evidence),'link_audit_counts':dict(audit),
    'http_status_counts':dict(http),'invalid_link_records':invalid,
    'review_link_records':review,
    'quality_gate':{
        'records':BATCH_SIZE,'unique_dois':BATCH_SIZE,'each_student':per_student,
        'id_start':id_start,'id_end':id_end,'invalid_links_max':invalid_max,
        'audit_shards':expected_shards
    },
    'next':'Convert ten audited CSV task files to formatted Excel workbooks, release the round, then continue the next large-round aggregation'
}
(OUT/'run_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
(OUT/'stage_report.md').write_text('\n'.join([
    f'# B004 {ROUND_CODE} Large-Round Report','',f'- Status: **{status}**',
    f'- Records: {len(rows):,}',f'- Unique DOIs: {unique_dois:,}',
    f'- Permanent IDs: {summary["id_start"]} to {summary["id_end"]}',
    f'- Student counts: {dict(student_counts)}',f'- K counts: {dict(kc)}',
    f'- Relevance: {dict(rel)}',f'- Priority: {dict(pri)}',
    f'- Evidence modes: {dict(evidence)}',f'- Link audit: {dict(audit)}',
    f'- Next: {summary["next"]}'
]), encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False), flush=True)
if status != 'success':
    raise SystemExit(2)
