import csv, json, sys
from collections import Counter, defaultdict
from pathlib import Path

try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(2**31 - 1)

FORMAL_ROOT = Path('formal_artifact')
B004_ROOT = Path('b004_artifact')
R01_ROOT = Path('r01_artifact')
R02_ROOT = Path('r02_artifact')
OUT = Path('out')
OUT.mkdir(exist_ok=True)
START_ID = 60001
STUDENTS = 10
SHARD_SIZE = 1000

formal_files = list(FORMAL_ROOT.rglob('B005_E2_v2_formal_AB_download_pool.csv'))
if len(formal_files) != 1:
    raise RuntimeError(f'Expected one B005 E2 v2 formal pool, found {len(formal_files)}')
formal_source = formal_files[0]
b004_files = sorted(B004_ROOT.rglob('*master*.csv'), key=lambda p: p.stat().st_size, reverse=True)
r01_files = list(R01_ROOT.rglob('B005_R01_30000_master_audited.csv'))
r02_files = list(R02_ROOT.rglob('B005_R02_30000_master_audited.csv'))
if not b004_files or len(r01_files) != 1 or len(r02_files) != 1:
    raise RuntimeError('Missing B004, B005-R01 or B005-R02 master')

def load_dois(path):
    result = set()
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            doi = (row.get('doi') or row.get('DOI') or '').strip().lower()
            if doi:
                result.add(doi)
    return result

b004 = load_dois(b004_files[0])
r01 = load_dois(r01_files[0])
r02 = load_dois(r02_files[0])
if len(b004) != 157917 or len(r01) != 30000 or len(r02) != 30000:
    raise RuntimeError(f'Unexpected prior registries B004={len(b004)} R01={len(r01)} R02={len(r02)}')
if b004 & r01 or b004 & r02 or r01 & r02:
    raise RuntimeError('Prior DOI registries are not disjoint')
excluded = b004 | r01 | r02

priority_rank = {'P0':0,'P1':1,'P2':2,'P3':3}
relevance_rank = {'A':0,'B':1,'C':2,'D':3}
def num(value):
    try:
        return float(value or 0)
    except Exception:
        return 0.0

def rank_key(row):
    return (
        priority_rank.get(row.get('download_priority'), 9),
        relevance_rank.get(row.get('relevance'), 9),
        -num(row.get('classification_confidence')),
        -num(row.get('classification_score')),
        -num(row.get('cited_by_count')),
        -(1 if (row.get('abstract') or '').strip() else 0),
        row.get('title') or '',
    )

formal_total = overlap_b004 = overlap_r01 = overlap_r02 = 0
remaining = []
with formal_source.open('r', encoding='utf-8-sig', newline='') as f:
    for row in csv.DictReader(f):
        doi = (row.get('doi') or '').strip().lower()
        if not doi or row.get('download_eligible') != 'yes' or row.get('relevance') not in {'A','B'}:
            continue
        formal_total += 1
        if doi in b004:
            overlap_b004 += 1
            continue
        if doi in r01:
            overlap_r01 += 1
            continue
        if doi in r02:
            overlap_r02 += 1
            continue
        row['doi'] = doi
        remaining.append(row)

if formal_total != 68303:
    raise RuntimeError(f'Unexpected B005 formal A/B pool size {formal_total}')
if overlap_b004:
    raise RuntimeError(f'B005 formal pool overlaps B004 by {overlap_b004}')
if overlap_r01 != 30000 or overlap_r02 != 30000:
    raise RuntimeError(f'Prior B005 exclusion mismatch R01={overlap_r01} R02={overlap_r02}')
if len(remaining) != 8303:
    raise RuntimeError(f'Expected 8303 final A/B records, found {len(remaining)}')
if len({r['doi'] for r in remaining}) != len(remaining):
    raise RuntimeError('Duplicate DOI in final remaining pool')
if any(r['doi'] in excluded for r in remaining):
    raise RuntimeError('Excluded DOI present in final remaining pool')

remaining.sort(key=lambda r: (r.get('K_primary') or 'K99', rank_key(r)))
for number, row in enumerate(remaining, START_ID):
    bid = f'B005-{number:06d}'
    row['B005_ID'] = bid
    row['PDF_filename'] = bid + '.pdf'
    row['DOI_URL'] = 'https://doi.org/' + row['doi']
    row['download_status'] = '待下载'
    row['download_round'] = 'B005-R03'
    row['exclusion_checked'] = 'B004+R01+R02'

buckets = [[] for _ in range(STUDENTS)]
by_k = defaultdict(list)
for row in remaining:
    by_k[row.get('K_primary') or 'K00'].append(row)
cursor = 0
for k in sorted(by_k):
    for row in by_k[k]:
        minimum = min(len(b) for b in buckets)
        choices = [i for i,b in enumerate(buckets) if len(b) == minimum]
        pick = choices[cursor % len(choices)]
        cursor += 1
        row['student'] = f'Student{pick+1:02d}'
        buckets[pick].append(row)
student_sizes = [len(b) for b in buckets]
if max(student_sizes) - min(student_sizes) > 1 or sum(student_sizes) != len(remaining):
    raise RuntimeError(f'Unbalanced student allocation {student_sizes}')

base_headers = list(remaining[0].keys())
front = ['B005_ID','download_round','student','K_primary','K_primary_name','G_primary','relevance','download_priority','title','first_author','year','journal','doi','DOI_URL','PDF_filename','download_status']
headers = list(dict.fromkeys(front + [h for h in base_headers if h not in front] + ['link_http_status','link_audit_result','link_final_url','link_audit_note']))
shard_count = (len(remaining) + SHARD_SIZE - 1) // SHARD_SIZE
shard_counts = {}
for shard in range(1, shard_count + 1):
    part = remaining[(shard-1)*SHARD_SIZE:shard*SHARD_SIZE]
    shard_counts[f'{shard:02d}'] = len(part)
    with (OUT / f'B005_R03_Shard{shard:02d}_{len(part)}_pre_audit.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows([{h:r.get(h,'') for h in headers} for r in part])

summary = {
    'stage':'B005-R03-prepare','status':'success','formal_pool_total':formal_total,
    'b004_registry':len(b004),'r01_registry':len(r01),'r02_registry':len(r02),'excluded_union':len(excluded),
    'overlap_b004':overlap_b004,'excluded_r01':overlap_r01,'excluded_r02':overlap_r02,
    'remaining_records':len(remaining),'remaining_unique_dois':len({r['doi'] for r in remaining}),
    'id_start':'B005-060001','id_end':'B005-068303',
    'student_counts':{f'Student{i+1:02d}':len(b) for i,b in enumerate(buckets)},
    'K_counts':dict(Counter(r.get('K_primary') for r in remaining)),
    'relevance_counts':dict(Counter(r.get('relevance') for r in remaining)),
    'priority_counts':dict(Counter(r.get('download_priority') for r in remaining)),
    'audit_shards':shard_count,'shard_counts':shard_counts,
    'next':'Audit all 8303 links and freeze the complete B005 A/B download database'
}
(OUT/'prepare_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False), flush=True)
