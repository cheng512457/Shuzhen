import csv, json, sys
from collections import Counter, defaultdict
from pathlib import Path

try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(2**31-1)

FORMAL_ROOT=Path('formal_artifact'); B004_ROOT=Path('b004_artifact'); OUT=Path('out'); OUT.mkdir(exist_ok=True)
BATCH_SIZE=30000; STUDENTS=10; SHARD_SIZE=1000; START_ID=1
formal_files=list(FORMAL_ROOT.rglob('B005_E2_v2_formal_AB_download_pool.csv'))
if not formal_files: raise RuntimeError('Missing B005 E2 v2 formal A/B pool')
formal_source=formal_files[0]
b004_files=sorted(B004_ROOT.rglob('*master*.csv'),key=lambda p:p.stat().st_size,reverse=True)
if not b004_files: raise RuntimeError('Missing B004 cumulative master')
b004_source=b004_files[0]
b004=set()
with b004_source.open('r',encoding='utf-8-sig',newline='') as f:
    for r in csv.DictReader(f):
        d=(r.get('doi') or r.get('DOI') or '').strip().lower()
        if d:b004.add(d)
if len(b004)!=157917: raise RuntimeError(f'Unexpected B004 DOI registry {len(b004)}')

BASE={'K01':700,'K02':600,'K03':1000,'K04':700,'K05':1000,'K06':1100,'K07':700,'K08':750,'K09':450,'K10':450,'K11':550,'K12':450,'K13':500,'K14':500,'K15':250,'K16':300}
assert sum(BASE.values())==10000
quotas={k:v*3 for k,v in BASE.items()}
priority={'P0':0,'P1':1,'P2':2,'P3':3}; relevance={'A':0,'B':1,'C':2,'D':3}
def num(x):
    try:return float(x or 0)
    except:return 0.0
def key(r):
    return (priority.get(r.get('download_priority'),9),relevance.get(r.get('relevance'),9),-num(r.get('classification_confidence')),-num(r.get('classification_score')),-num(r.get('cited_by_count')),-int(bool((r.get('abstract') or '').strip())),r.get('title') or '')
byk=defaultdict(list); formal_total=invalid=overlap=0
with formal_source.open('r',encoding='utf-8-sig',newline='') as f:
    for r in csv.DictReader(f):
        d=(r.get('doi') or '').strip().lower()
        if not d or r.get('download_eligible')!='yes' or r.get('relevance') not in {'A','B'}: continue
        formal_total+=1
        if d in b004: overlap+=1; continue
        r['doi']=d; byk[r.get('K_primary') or 'K00'].append(r)
if overlap: raise RuntimeError(f'B005 formal pool overlaps B004 by {overlap}')
selected=[]; shortfalls={}
for k in [f'K{i:02d}' for i in range(1,17)]:
    c=sorted(byk.get(k,[]),key=key); take=min(quotas[k],len(c)); selected.extend(c[:take])
    if take<quotas[k]:shortfalls[k]=quotas[k]-take
used={r['doi'] for r in selected}
if len(selected)<BATCH_SIZE:
    refill=sorted((r for vals in byk.values() for r in vals if r['doi'] not in used),key=key)
    for r in refill:
        if len(selected)>=BATCH_SIZE:break
        if r['doi'] in used:continue
        used.add(r['doi']);selected.append(r)
if len(selected)!=BATCH_SIZE: raise RuntimeError(f'Only {len(selected)} A/B records available')
if len({r['doi'] for r in selected})!=BATCH_SIZE: raise RuntimeError('Duplicate DOI in selection')
if any(r['doi'] in b004 for r in selected): raise RuntimeError('B004 overlap after selection')
selected.sort(key=lambda r:(r.get('K_primary') or 'K99',key(r)))
for i,r in enumerate(selected,START_ID):
    bid=f'B005-{i:06d}'; r['B005_ID']=bid; r['PDF_filename']=bid+'.pdf'; r['DOI_URL']='https://doi.org/'+r['doi']; r['download_status']='待下载'; r['download_round']='B005-R01'

buckets=[[] for _ in range(STUDENTS)]; cursor=0
for k in [f'K{i:02d}' for i in range(1,17)]:
    for r in [x for x in selected if x.get('K_primary')==k]:
        m=min(map(len,buckets)); choices=[i for i,b in enumerate(buckets) if len(b)==m]; pick=choices[cursor%len(choices)]; cursor+=1
        r['student']=f'Student{pick+1:02d}'; buckets[pick].append(r)
if [len(b) for b in buckets] != [3000]*10: raise RuntimeError('Student allocation mismatch')
base=list(selected[0].keys()); front=['B005_ID','download_round','student','K_primary','K_primary_name','G_primary','relevance','download_priority','title','first_author','year','journal','doi','DOI_URL','PDF_filename','download_status']
headers=list(dict.fromkeys(front+[h for h in base if h not in front]+['link_http_status','link_audit_result','link_final_url','link_audit_note']))
for shard in range(1,31):
    part=selected[(shard-1)*SHARD_SIZE:shard*SHARD_SIZE]
    with (OUT/f'B005_R01_Shard{shard:02d}_{SHARD_SIZE}_pre_audit.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=headers);w.writeheader();w.writerows([{h:r.get(h,'') for h in headers} for r in part])
summary={'stage':'B005-R01-prepare','status':'success','formal_pool_available':formal_total,'b004_registry':len(b004),'b004_overlap':0,'selected_records':len(selected),'unique_dois':len({r['doi'] for r in selected}),'id_start':'B005-000001','id_end':'B005-030000','target_K_quotas':quotas,'actual_K_counts':dict(Counter(r.get('K_primary') for r in selected)),'quota_shortfalls_before_refill':shortfalls,'relevance_counts':dict(Counter(r.get('relevance') for r in selected)),'priority_counts':dict(Counter(r.get('download_priority') for r in selected)),'student_counts':{f'Student{i+1:02d}':len(b) for i,b in enumerate(buckets)},'audit_shards':30}
(OUT/'B005_R01_prepare_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False),flush=True)
