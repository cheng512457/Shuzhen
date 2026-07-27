import csv
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(2**31 - 1)

ROUND_CODE = os.environ.get('ROUND_CODE', 'R06').strip()
START_ID = int(os.environ.get('START_ID', '130001'))
STUDENT_COUNT = int(os.environ.get('STUDENT_COUNT', '10'))
SHARD_SIZE = int(os.environ.get('SHARD_SIZE', '1000'))
FORMAL_ROOT = Path('formal_artifact')
PREVIOUS_ROOT = Path('previous_artifacts')
OUT = Path('out')
OUT.mkdir(exist_ok=True)

formal_files = list(FORMAL_ROOT.rglob('B004_S3_2_formal_download_pool.csv'))
if len(formal_files) != 1:
    raise RuntimeError(f'Expected one formal download pool, found {len(formal_files)}')
formal_source = formal_files[0]
previous_files = sorted(PREVIOUS_ROOT.rglob('B004_R*_master_audited.csv'))
if len(previous_files) < 5:
    raise RuntimeError(f'Expected R01-R05 master files, found {len(previous_files)}')

excluded = set()
for path in previous_files:
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            doi = (row.get('doi') or '').strip().lower()
            if doi:
                excluded.add(doi)

priority_rank = {'P0':0,'P1':1,'P2':2,'P3':3}
relevance_rank = {'A':0,'B':1,'C':2,'D':3}
def num(x):
    try:
        return float(x or 0)
    except Exception:
        return 0.0

def rank_key(row):
    return (
        priority_rank.get(row.get('download_priority'), 9),
        relevance_rank.get(row.get('relevance'), 9),
        -num(row.get('classification_confidence')),
        -num(row.get('classification_score')),
        -num(row.get('source_record_count')),
        -num(row.get('cited_by_count')),
        -(1 if (row.get('abstract') or '').strip() else 0),
        row.get('title') or '',
    )

remaining = []
formal_total = 0
with formal_source.open('r', encoding='utf-8-sig', newline='') as f:
    for row in csv.DictReader(f):
        doi = (row.get('doi') or '').strip().lower()
        if not doi or row.get('download_eligible') != 'yes':
            continue
        formal_total += 1
        if doi in excluded:
            continue
        if row.get('relevance') not in {'A','B'}:
            raise RuntimeError('Formal pool contains a non-A/B record')
        row['doi'] = doi
        remaining.append(row)

remaining.sort(key=lambda r: (r.get('K_primary') or 'K99', rank_key(r)))
if not remaining:
    raise RuntimeError('No remaining A/B DOI records after R01-R05 exclusion')
if len({r['doi'] for r in remaining}) != len(remaining):
    raise RuntimeError('Remaining pool contains duplicate DOI values')
if any(r['doi'] in excluded for r in remaining):
    raise RuntimeError('Remaining pool overlaps R01-R05')

for offset, row in enumerate(remaining, START_ID):
    bid = f'B004-{offset:06d}'
    row['B004_ID'] = bid
    row['PDF_filename'] = bid + '.pdf'
    row['DOI_URL'] = 'https://doi.org/' + row['doi']
    row['download_status'] = '待下载'
    row['download_round'] = f'B004-{ROUND_CODE}'

# Balance K domains across students while allowing counts to differ by at most one.
student_buckets = [[] for _ in range(STUDENT_COUNT)]
by_k = defaultdict(list)
for row in remaining:
    by_k[row.get('K_primary') or 'K00'].append(row)
cursor = 0
for k in sorted(by_k):
    for row in by_k[k]:
        min_size = min(len(x) for x in student_buckets)
        choices = [i for i,b in enumerate(student_buckets) if len(b) == min_size]
        pick = choices[cursor % len(choices)]
        cursor += 1
        row['student'] = f'Student{pick+1:02d}'
        student_buckets[pick].append(row)
counts = [len(x) for x in student_buckets]
if max(counts) - min(counts) > 1 or sum(counts) != len(remaining):
    raise RuntimeError(f'Unbalanced student assignment: {counts}')

base_headers = list(remaining[0].keys())
front = ['B004_ID','download_round','student','K_primary','K_primary_name','G_primary','relevance','download_priority','title','first_author','year','journal','doi','DOI_URL','PDF_filename','download_status']
headers = front + [h for h in base_headers if h not in front]
headers += ['link_http_status','link_audit_result','link_final_url','link_audit_note']
headers = list(dict.fromkeys(headers))

shard_count = (len(remaining) + SHARD_SIZE - 1) // SHARD_SIZE
shard_counts = {}
for shard in range(1, shard_count + 1):
    part = remaining[(shard-1)*SHARD_SIZE:shard*SHARD_SIZE]
    shard_counts[f'{shard:02d}'] = len(part)
    with (OUT/f'B004_{ROUND_CODE}_Shard{shard:02d}_pre_audit.csv').open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader(); w.writerows([{h:r.get(h,'') for h in headers} for r in part])

summary = {
    'stage':'S4-final-prepare','status':'success','round_code':ROUND_CODE,
    'formal_pool_total':formal_total,'excluded_unique_dois':len(excluded),
    'remaining_records':len(remaining),'remaining_unique_dois':len({r['doi'] for r in remaining}),
    'permanent_id_start':f'B004-{START_ID:06d}',
    'permanent_id_end':f'B004-{START_ID+len(remaining)-1:06d}',
    'previous_round_files':[str(x) for x in previous_files],
    'K_counts':dict(Counter(r.get('K_primary') for r in remaining)),
    'relevance_counts':dict(Counter(r.get('relevance') for r in remaining)),
    'priority_counts':dict(Counter(r.get('download_priority') for r in remaining)),
    'evidence_mode_counts':dict(Counter(r.get('evidence_mode') for r in remaining)),
    'student_counts':{f'Student{i+1:02d}':len(b) for i,b in enumerate(student_buckets)},
    'audit_shards':shard_count,'shard_size_max':SHARD_SIZE,'shard_counts':shard_counts,
    'next':'Audit every remaining DOI link, combine final R06 pool and freeze the complete A/B download database'
}
(OUT/'prepare_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False), flush=True)
