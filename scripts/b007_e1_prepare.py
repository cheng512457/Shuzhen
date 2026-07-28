import csv
import json
import math
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
files = list(ROOT.rglob('B004_B005_B006_247023_cumulative_master.csv'))
if len(files) != 1:
    raise RuntimeError(f'Expected one cumulative master, found {len(files)}')
source = files[0]
records=[]; excluded=set(); counts=Counter()
with source.open('r',encoding='utf-8-sig',newline='') as f:
    for row in csv.DictReader(f):
        doi=(row.get('doi_normalized') or row.get('doi') or '').strip().lower()
        if not doi: continue
        excluded.add(doi); row['doi_normalized']=doi; records.append(row)
        counts[(row.get('K_primary') or 'K00').strip()] += 1
if len(records)!=247023 or len(excluded)!=247023:
    raise RuntimeError(f'Unexpected cumulative registry size rows={len(records)} dois={len(excluded)}')
(OUT/'B004_B005_B006_247023_excluded_dois.txt').write_text('\n'.join(sorted(excluded)),encoding='utf-8')

priority_weight={'P0':5.0,'P1':3.0,'P2':1.0,'P3':0.0}
relevance_weight={'A':4.0,'B':2.0,'C':0.5,'D':0.0}
def number(x):
    try: return int(float(x or 0))
    except Exception: return 0
def seed_score(row):
    s=priority_weight.get(row.get('download_priority'),0)+relevance_weight.get(row.get('relevance'),0)
    s+=min(math.log1p(number(row.get('cited_by_count'))),6.0)*0.55
    s+=1.0 if (row.get('abstract') or '').strip() else 0.0
    s+=0.6 if (row.get('openalex_id') or '').strip() else 0.0
    return round(s,4)
by_k=defaultdict(list)
for row in records:
    k=row.get('K_primary') or 'K00'
    if k in {f'K{i:02d}' for i in range(1,17)} and row.get('relevance') in {'A','B'}:
        by_k[k].append(row)
headers=['doi','title','year','journal','first_author','abstract','cited_by_count','K_primary','relevance','download_priority','openalex_id','seed_score']
seed_counts={}
for k in [f'K{i:02d}' for i in range(1,17)]:
    ranked=sorted(by_k[k],key=lambda r:(seed_score(r),number(r.get('cited_by_count')),number(r.get('year'))),reverse=True)
    selected=ranked[:500]
    seed_counts[k]=len(selected)
    with (OUT/f'B007_E1_seeds_{k}.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=headers);w.writeheader()
        for row in selected:
            w.writerow({'doi':row['doi_normalized'],'title':row.get('title') or '','year':row.get('year') or '','journal':row.get('journal') or '','first_author':row.get('first_author') or '','abstract':(row.get('abstract') or '')[:6000],'cited_by_count':number(row.get('cited_by_count')),'K_primary':k,'relevance':row.get('relevance') or '','download_priority':row.get('download_priority') or '','openalex_id':row.get('openalex_id') or '','seed_score':seed_score(row)})
summary={'stage':'B007-E1-prepare','source_file':str(source),'excluded_unique_dois':len(excluded),'source_K_counts':dict(counts),'seed_counts':seed_counts,'total_seeds':sum(seed_counts.values()),'quality_gate':{'excluded_unique_dois':247023,'each_K_seed_min':350,'total_seeds_min':7000}}
(OUT/'prepare_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False),flush=True)
if len(excluded)!=247023 or min(seed_counts.values())<350 or sum(seed_counts.values())<7000:
    raise SystemExit(2)
