import csv,json,sys
from collections import Counter
from pathlib import Path
try: csv.field_size_limit(sys.maxsize)
except OverflowError: csv.field_size_limit(2**31-1)
FORMAL=Path('formal_artifact');PRIOR=Path('prior_artifact');OUT=Path('out');OUT.mkdir(exist_ok=True)
f=list(FORMAL.rglob('B007_E2_formal_AB_download_pool.csv'));p=list(PRIOR.rglob('B004_B005_B006_247023_cumulative_master.csv'))
if len(f)!=1 or len(p)!=1: raise RuntimeError(f'Missing formal/prior files: {len(f)}/{len(p)}')
prior=set()
with p[0].open('r',encoding='utf-8-sig',newline='') as h:
 for r in csv.DictReader(h):
  d=(r.get('doi') or r.get('doi_normalized') or r.get('DOI') or '').strip().lower()
  if d: prior.add(d)
if len(prior)!=247023: raise RuntimeError(f'Unexpected prior DOI count {len(prior)}')
rows=[];overlap=0
with f[0].open('r',encoding='utf-8-sig',newline='') as h:
 for r in csv.DictReader(h):
  d=(r.get('doi') or '').strip().lower()
  if not d or r.get('relevance') not in {'A','B'} or r.get('download_eligible')!='yes': continue
  if d in prior: overlap+=1;continue
  r['doi']=d;r['K_primary']=r.get('K_primary') or r.get('primary_k_domain') or 'K00';rows.append(r)
if overlap or len(rows)!=19775 or len({r['doi'] for r in rows})!=19775: raise RuntimeError(f'Formal pool check failed rows={len(rows)} overlap={overlap}')
pr={'P0':0,'P1':1,'P2':2,'P3':3};rr={'A':0,'B':1}
def num(x):
 try:return float(x or 0)
 except:return 0
rows.sort(key=lambda r:(r['K_primary'],pr.get(r.get('download_priority'),9),rr.get(r.get('relevance'),9),-num(r.get('precision_score_max')),-num(r.get('cited_by_count')),r.get('title') or ''))
for i,r in enumerate(rows,1):
 bid=f'B007-{i:06d}';r.update({'B007_ID':bid,'PDF_filename':bid+'.pdf','DOI_URL':'https://doi.org/'+r['doi'],'download_status':'待下载','download_round':'B007-R01'})
buckets=[[] for _ in range(10)];cursor=0
for k in [f'K{i:02d}' for i in range(1,17)]:
 for r in [x for x in rows if x['K_primary']==k]:
  m=min(map(len,buckets));choices=[i for i,b in enumerate(buckets) if len(b)==m];pick=choices[cursor%len(choices)];cursor+=1;r['student']=f'Student{pick+1:02d}';buckets[pick].append(r)
counts=[len(b) for b in buckets]
if max(counts)-min(counts)>1 or sum(counts)!=19775: raise RuntimeError(f'Student allocation failed {counts}')
base=list(rows[0]);front=['B007_ID','download_round','student','K_primary','K_primary_name','G_primary','relevance','download_priority','title','first_author','year','journal','doi','DOI_URL','PDF_filename','download_status'];headers=list(dict.fromkeys(front+[x for x in base if x not in front]+['link_http_status','link_audit_result','link_final_url','link_audit_note']))
for shard in range(1,21):
 part=rows[(shard-1)*1000:shard*1000]
 with (OUT/f'B007_R01_Shard{shard:02d}_pre_audit.csv').open('w',encoding='utf-8-sig',newline='') as h:
  w=csv.DictWriter(h,fieldnames=headers);w.writeheader();w.writerows([{x:r.get(x,'') for x in headers} for r in part])
summary={'stage':'B007-R01-prepare','status':'success','verified_formal_pool':19775,'prior_registry':247023,'prior_overlap':0,'selected_records':19775,'unique_dois':19775,'id_start':'B007-000001','id_end':'B007-019775','student_counts':{f'Student{i+1:02d}':len(b) for i,b in enumerate(buckets)},'K_counts':dict(Counter(r['K_primary'] for r in rows)),'relevance_counts':dict(Counter(r['relevance'] for r in rows)),'priority_counts':dict(Counter(r['download_priority'] for r in rows)),'audit_shards':20,'shard_sizes':{str(i):len(rows[(i-1)*1000:i*1000]) for i in range(1,21)}}
(OUT/'B007_R01_prepare_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(summary,ensure_ascii=False),flush=True)