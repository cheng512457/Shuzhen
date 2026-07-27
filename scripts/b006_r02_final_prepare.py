import csv, json, sys
from collections import Counter, defaultdict
from pathlib import Path
try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(2**31-1)
FORMAL=Path('formal_artifact'); PRIOR=Path('prior_artifact'); R01=Path('r01_artifact'); OUT=Path('out'); OUT.mkdir(exist_ok=True)
formal_files=list(FORMAL.rglob('B006_E2_V2_formal_AB_download_pool.csv'))
prior_files=list(PRIOR.rglob('B004_B005_226220_cumulative_master.csv'))
r01_files=list(R01.rglob('B006_R01_20000_master_audited.csv'))
if len(formal_files)!=1 or len(prior_files)!=1 or len(r01_files)!=1:
    raise RuntimeError(f'Missing inputs formal={len(formal_files)} prior={len(prior_files)} r01={len(r01_files)}')
def dois(path):
    out=set()
    with path.open('r',encoding='utf-8-sig',newline='') as f:
        for row in csv.DictReader(f):
            d=(row.get('doi') or row.get('DOI') or '').strip().lower()
            if d: out.add(d)
    return out
prior=dois(prior_files[0]); r01=dois(r01_files[0])
if len(prior)!=226220 or len(r01)!=20000 or prior & r01:
    raise RuntimeError(f'Unexpected registries prior={len(prior)} r01={len(r01)} overlap={len(prior&r01)}')
excluded=prior|r01
formal_total=overlap_prior=overlap_r01=0; remaining=[]
with formal_files[0].open('r',encoding='utf-8-sig',newline='') as f:
    for row in csv.DictReader(f):
        d=(row.get('doi') or '').strip().lower()
        if not d or row.get('download_eligible')!='yes' or row.get('relevance') not in {'A','B'}: continue
        formal_total+=1
        if d in prior: overlap_prior+=1; continue
        if d in r01: overlap_r01+=1; continue
        row['doi']=d; row['K_primary']=row.get('K_primary') or row.get('primary_k_domain') or 'K00'; remaining.append(row)
if formal_total!=20803 or overlap_prior!=0 or overlap_r01!=20000 or len(remaining)!=803:
    raise RuntimeError(f'Pool mismatch total={formal_total} prior={overlap_prior} r01={overlap_r01} remaining={len(remaining)}')
if len({r['doi'] for r in remaining})!=803 or any(r['doi'] in excluded for r in remaining):
    raise RuntimeError('Remaining DOI uniqueness/exclusion failure')
remaining.sort(key=lambda r:(r.get('K_primary') or 'K99',r.get('download_priority') or 'P9',r.get('relevance') or 'Z',r.get('title') or ''))
for n,row in enumerate(remaining,20001):
    bid=f'B006-{n:06d}'; row['B006_ID']=bid; row['PDF_filename']=bid+'.pdf'; row['DOI_URL']='https://doi.org/'+row['doi']; row['download_status']='待下载'; row['download_round']='B006-R02'; row['exclusion_checked']='B004+B005+B006-R01'
buckets=[[] for _ in range(10)]; byk=defaultdict(list)
for row in remaining: byk[row['K_primary']].append(row)
cursor=0
for k in sorted(byk):
    for row in byk[k]:
        m=min(map(len,buckets)); choices=[i for i,b in enumerate(buckets) if len(b)==m]; pick=choices[cursor%len(choices)]; cursor+=1; row['student']=f'Student{pick+1:02d}'; buckets[pick].append(row)
sizes=[len(b) for b in buckets]
if max(sizes)-min(sizes)>1 or sum(sizes)!=803: raise RuntimeError(f'Unbalanced students {sizes}')
base=list(remaining[0].keys()); front=['B006_ID','download_round','student','K_primary','K_primary_name','G_primary','relevance','download_priority','title','first_author','year','journal','doi','DOI_URL','PDF_filename','download_status']; headers=list(dict.fromkeys(front+[h for h in base if h not in front]+['link_http_status','link_audit_result','link_final_url','link_audit_note']))
with (OUT/'B006_R02_Shard01_803_pre_audit.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=headers); w.writeheader(); w.writerows([{h:r.get(h,'') for h in headers} for r in remaining])
summary={'stage':'B006-R02-prepare','status':'success','formal_pool_total':formal_total,'prior_registry':len(prior),'r01_registry':len(r01),'excluded_union':len(excluded),'overlap_prior':overlap_prior,'excluded_r01':overlap_r01,'remaining_records':803,'remaining_unique_dois':803,'id_start':'B006-020001','id_end':'B006-020803','student_counts':{f'Student{i+1:02d}':len(b) for i,b in enumerate(buckets)},'K_counts':dict(Counter(r['K_primary'] for r in remaining)),'relevance_counts':dict(Counter(r['relevance'] for r in remaining)),'priority_counts':dict(Counter(r['download_priority'] for r in remaining)),'audit_shards':1,'next':'Audit all 803 links and freeze the complete B006 20803-record A/B database'}
(OUT/'prepare_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(summary,ensure_ascii=False),flush=True)
