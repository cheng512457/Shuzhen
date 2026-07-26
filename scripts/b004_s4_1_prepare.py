import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(2**31 - 1)

ROOT = Path('prior_artifact')
OUT = Path('out')
OUT.mkdir(exist_ok=True)
files = list(ROOT.rglob('B004_S3_2_formal_download_pool.csv'))
if not files:
    raise RuntimeError('Missing S3.2 formal download pool')
source = files[0]

# Scale the ontology plan to exactly 10,000 records. The previous configuration
# summed to 10,050 and stopped before selection; K16 is corrected from 350 to 300.
QUOTAS = {
    'K01':700,'K02':600,'K03':1000,'K04':700,'K05':1000,'K06':1100,'K07':700,'K08':750,
    'K09':450,'K10':450,'K11':550,'K12':450,'K13':500,'K14':500,'K15':250,'K16':300,
}
quota_total = sum(QUOTAS.values())
if quota_total != 10000:
    raise RuntimeError(f'K-domain quotas must sum to 10000, got {quota_total}')

rows_by_k = defaultdict(list)
with source.open('r', encoding='utf-8-sig', newline='') as f:
    for row in csv.DictReader(f):
        doi = (row.get('doi') or '').strip().lower()
        if not doi or row.get('download_eligible') != 'yes':
            continue
        row['doi'] = doi
        rows_by_k[row.get('K_primary') or 'K00'].append(row)

priority_rank = {'P0':0,'P1':1,'P2':2,'P3':3}
relevance_rank = {'A':0,'B':1,'C':2,'D':3}
def num(x):
    try: return float(x or 0)
    except Exception: return 0.0

def rank_key(row):
    return (
        priority_rank.get(row.get('download_priority'),9),
        relevance_rank.get(row.get('relevance'),9),
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
if len(selected) < 10000:
    refill = []
    for candidates in rows_by_k.values():
        for row in candidates:
            if row['doi'] not in used:
                refill.append(row)
    refill.sort(key=rank_key)
    for row in refill:
        if len(selected) >= 10000: break
        if row['doi'] in used: continue
        used.add(row['doi']); selected.append(row)

if len(selected) != 10000:
    raise RuntimeError(f'Expected exactly 10000 selected records, got {len(selected)}')
if len({r['doi'] for r in selected}) != 10000:
    raise RuntimeError('Selected records contain duplicate DOI values')

# Preserve topical grouping for permanent IDs, then distribute round-robin within each K domain to balance students.
selected.sort(key=lambda r: (r.get('K_primary') or 'K99', rank_key(r)))
for idx, row in enumerate(selected, 1):
    bid = f'B004-{idx:06d}'
    row['B004_ID'] = bid
    row['PDF_filename'] = bid + '.pdf'
    row['DOI_URL'] = 'https://doi.org/' + row['doi']
    row['download_status'] = '待下载'

student_buckets = [[] for _ in range(10)]
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

counts = [len(x) for x in student_buckets]
if counts != [1000]*10:
    raise RuntimeError(f'Unexpected student counts: {counts}')

base_headers = list(selected[0].keys())
front = ['B004_ID','student','K_primary','K_primary_name','G_primary','relevance','download_priority','title','first_author','year','journal','doi','DOI_URL','PDF_filename','download_status']
headers = front + [h for h in base_headers if h not in front]
headers += ['link_http_status','link_audit_result','link_final_url','link_audit_note']
headers = list(dict.fromkeys(headers))

with (OUT/'B004_R01_10000_selected.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=headers); w.writeheader(); w.writerows([{h:r.get(h,'') for h in headers} for r in selected])
for i,bucket in enumerate(student_buckets,1):
    with (OUT/f'B004_R01_Student{i:02d}_1000_pre_audit.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=headers); w.writeheader(); w.writerows([{h:r.get(h,'') for h in headers} for r in bucket])

summary={
 'stage':'S4.1-prepare','status':'success','source_file':str(source),'formal_pool_available':sum(len(v) for v in rows_by_k.values()),
 'selected_records':len(selected),'unique_dois':len({r['doi'] for r in selected}),'permanent_id_start':'B004-000001','permanent_id_end':'B004-010000',
 'target_K_quotas':QUOTAS,'actual_K_counts':dict(Counter(r.get('K_primary') for r in selected)),'quota_shortfalls_before_refill':shortfalls,
 'relevance_counts':dict(Counter(r.get('relevance') for r in selected)),'priority_counts':dict(Counter(r.get('download_priority') for r in selected)),
 'evidence_mode_counts':dict(Counter(r.get('evidence_mode') for r in selected)),'student_counts':{f'Student{i+1:02d}':len(b) for i,b in enumerate(student_buckets)},
 'next':'Audit 10,000 DOI links in ten 1,000-record shards and build student delivery files'
}
(OUT/'prepare_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False),flush=True)
