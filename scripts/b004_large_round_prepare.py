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

ROUND_CODE = os.environ.get('ROUND_CODE', 'R02').strip()
BATCH_SIZE = int(os.environ.get('BATCH_SIZE', '30000'))
START_ID = int(os.environ.get('START_ID', '10001'))
STUDENT_COUNT = int(os.environ.get('STUDENT_COUNT', '10'))
SHARD_SIZE = int(os.environ.get('SHARD_SIZE', '1000'))

if BATCH_SIZE <= 0 or BATCH_SIZE % 10000 != 0:
    raise RuntimeError('BATCH_SIZE must be a positive multiple of 10000')
if BATCH_SIZE % STUDENT_COUNT != 0:
    raise RuntimeError('BATCH_SIZE must divide evenly across students')
if BATCH_SIZE % SHARD_SIZE != 0:
    raise RuntimeError('BATCH_SIZE must divide evenly across audit shards')

FORMAL_ROOT = Path('formal_artifact')
PREVIOUS_ROOT = Path('previous_artifacts')
OUT = Path('out')
OUT.mkdir(exist_ok=True)

formal_files = list(FORMAL_ROOT.rglob('B004_S3_2_formal_download_pool.csv'))
if not formal_files:
    raise RuntimeError('Missing S3.2 formal download pool')
formal_source = formal_files[0]

previous_files = sorted(PREVIOUS_ROOT.rglob('B004_R*_master_audited.csv'))
excluded = set()
for path in previous_files:
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            doi = (row.get('doi') or '').strip().lower()
            if doi:
                excluded.add(doi)

BASE_QUOTAS = {
    'K01':700,'K02':600,'K03':1000,'K04':700,'K05':1000,'K06':1100,'K07':700,'K08':750,
    'K09':450,'K10':450,'K11':550,'K12':450,'K13':500,'K14':500,'K15':250,'K16':300,
}
assert sum(BASE_QUOTAS.values()) == 10000
factor = BATCH_SIZE // 10000
QUOTAS = {k: v * factor for k, v in BASE_QUOTAS.items()}
assert sum(QUOTAS.values()) == BATCH_SIZE

rows_by_k = defaultdict(list)
formal_total = 0
formal_after_exclusion = 0
with formal_source.open('r', encoding='utf-8-sig', newline='') as f:
    for row in csv.DictReader(f):
        doi = (row.get('doi') or '').strip().lower()
        if not doi or row.get('download_eligible') != 'yes':
            continue
        formal_total += 1
        if doi in excluded:
            continue
        formal_after_exclusion += 1
        row['doi'] = doi
        rows_by_k[row.get('K_primary') or 'K00'].append(row)

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

selected = []
shortfalls = {}
for k in [f'K{i:02d}' for i in range(1,17)]:
    candidates = sorted(rows_by_k.get(k, []), key=rank_key)
    take = min(QUOTAS[k], len(candidates))
    selected.extend(candidates[:take])
    if take < QUOTAS[k]:
        shortfalls[k] = QUOTAS[k] - take

used = {r['doi'] for r in selected}
if len(selected) < BATCH_SIZE:
    refill = []
    for candidates in rows_by_k.values():
        for row in candidates:
            if row['doi'] not in used:
                refill.append(row)
    refill.sort(key=rank_key)
    for row in refill:
        if len(selected) >= BATCH_SIZE:
            break
        if row['doi'] in used:
            continue
        used.add(row['doi'])
        selected.append(row)

if len(selected) != BATCH_SIZE:
    raise RuntimeError(f'Only {len(selected)} records available for {ROUND_CODE}')
if len({r['doi'] for r in selected}) != BATCH_SIZE:
    raise RuntimeError(f'{ROUND_CODE} selection contains duplicate DOI values')
if any(r['doi'] in excluded for r in selected):
    raise RuntimeError(f'{ROUND_CODE} selection overlaps previous rounds')

selected.sort(key=lambda r: (r.get('K_primary') or 'K99', rank_key(r)))
for offset, row in enumerate(selected, START_ID):
    bid = f'B004-{offset:06d}'
    row['B004_ID'] = bid
    row['PDF_filename'] = bid + '.pdf'
    row['DOI_URL'] = 'https://doi.org/' + row['doi']
    row['download_status'] = '待下载'
    row['download_round'] = f'B004-{ROUND_CODE}'

student_buckets = [[] for _ in range(STUDENT_COUNT)]
by_k_selected = defaultdict(list)
for row in selected:
    by_k_selected[row.get('K_primary') or 'K00'].append(row)
student_cursor = 0
for k in [f'K{i:02d}' for i in range(1,17)]:
    for row in by_k_selected[k]:
        min_size = min(len(x) for x in student_buckets)
        choices = [i for i,b in enumerate(student_buckets) if len(b) == min_size]
        pick = choices[student_cursor % len(choices)]
        student_cursor += 1
        row['student'] = f'Student{pick+1:02d}'
        student_buckets[pick].append(row)

per_student = BATCH_SIZE // STUDENT_COUNT
counts = [len(x) for x in student_buckets]
if counts != [per_student] * STUDENT_COUNT:
    raise RuntimeError(f'Unexpected student counts: {counts}')

base_headers = list(selected[0].keys())
front = ['B004_ID','download_round','student','K_primary','K_primary_name','G_primary','relevance','download_priority','title','first_author','year','journal','doi','DOI_URL','PDF_filename','download_status']
headers = front + [h for h in base_headers if h not in front]
headers += ['link_http_status','link_audit_result','link_final_url','link_audit_note']
headers = list(dict.fromkeys(headers))

# Keep one copy of every record in the shard files only. This makes every audit
# runner download a much smaller preparation artifact while preserving complete
# recoverability from the independent checkpoints.
shard_count = BATCH_SIZE // SHARD_SIZE
for shard in range(1, shard_count + 1):
    part = selected[(shard-1)*SHARD_SIZE:shard*SHARD_SIZE]
    with (OUT/f'B004_{ROUND_CODE}_Shard{shard:02d}_{SHARD_SIZE}_pre_audit.csv').open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader(); w.writerows([{h:r.get(h,'') for h in headers} for r in part])

summary = {
    'stage':'S4-large-prepare','status':'success','round_code':ROUND_CODE,'batch_size':BATCH_SIZE,
    'formal_pool_available':formal_total,'formal_after_exclusion':formal_after_exclusion,
    'previous_round_files':[str(x) for x in previous_files],'excluded_unique_dois':len(excluded),
    'selected_records':len(selected),'unique_dois':len({r['doi'] for r in selected}),
    'permanent_id_start':f'B004-{START_ID:06d}','permanent_id_end':f'B004-{START_ID+BATCH_SIZE-1:06d}',
    'target_K_quotas':QUOTAS,'actual_K_counts':dict(Counter(r.get('K_primary') for r in selected)),
    'quota_shortfalls_before_refill':shortfalls,'relevance_counts':dict(Counter(r.get('relevance') for r in selected)),
    'priority_counts':dict(Counter(r.get('download_priority') for r in selected)),
    'evidence_mode_counts':dict(Counter(r.get('evidence_mode') for r in selected)),
    'student_counts':{f'Student{i+1:02d}':len(b) for i,b in enumerate(student_buckets)},
    'audit_shards':shard_count,'shard_size':SHARD_SIZE,
    'next':f'Audit {BATCH_SIZE} DOI links in {shard_count} independent shards'
}
(OUT/f'B004_{ROUND_CODE}_prepare_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False),flush=True)
