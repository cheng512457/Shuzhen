import csv, json, re
from collections import defaultdict
from pathlib import Path

ROOT=Path('inputs'); OUT=Path('out'); OUT.mkdir(exist_ok=True)

def doi_clean(x):
    x=str(x or '').strip().lower()
    x=re.sub(r'^https?://(dx\.)?doi\.org/','',x)
    x=re.sub(r'^doi:\s*','',x)
    return x.rstrip('.,;) ')

def as_int(x):
    try:return int(float(x or 0))
    except:return 0

def read_one(pattern):
    files=list(ROOT.rglob(pattern))
    if not files: raise FileNotFoundError(pattern)
    with files[0].open('r',encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

s21=read_one('B004_S2_1_global_unique_doi.csv')
s22=read_one('B004_S2_2_global_unique_doi.csv')
existing=set(); candidates=[]
for r in s21:
    doi=doi_clean(r.get('doi'))
    if not doi: continue
    existing.add(doi)
    candidates.append({'doi':doi,'title':r.get('title',''),'first_author':r.get('first_author',''),'year':r.get('year',''),'journal':r.get('journal',''),'cited_by_count':as_int(r.get('cited_by_count')),'openalex_id':r.get('openalex_id',''),'k_domains':r.get('k_domains') or r.get('primary_k_domain',''),'topics':'','source_stage':'S2.1','rank_score':as_int(r.get('total_query_hits'))*10+as_int(r.get('cited_by_count'))})
for r in s22:
    doi=doi_clean(r.get('doi'))
    if not doi: continue
    existing.add(doi)
    candidates.append({'doi':doi,'title':r.get('title',''),'first_author':r.get('first_author',''),'year':r.get('year',''),'journal':r.get('journal',''),'cited_by_count':as_int(r.get('cited_by_count')),'openalex_id':'','k_domains':r.get('k_domains',''),'topics':r.get('topics',''),'source_stage':'S2.2','rank_score':as_int(r.get('query_count'))*10+as_int(r.get('cited_by_count'))})

# Prefer one richest record per DOI.
by_doi={}
for r in candidates:
    old=by_doi.get(r['doi'])
    if old is None or (bool(r['openalex_id']),r['rank_score'],len(r['title']))>(bool(old['openalex_id']),old['rank_score'],len(old['title'])): by_doi[r['doi']]=r

selected=[]; used=set()
# S2.1: 220 seeds per K-domain.
for k in [f'K{i:02d}' for i in range(1,17)]:
    arr=[r for r in by_doi.values() if r['source_stage']=='S2.1' and k in (r['k_domains'] or '').split(';')]
    arr.sort(key=lambda r:(r['rank_score'],r['cited_by_count'],r['year']),reverse=True)
    for r in arr[:220]:
        if r['doi'] not in used: selected.append(r); used.add(r['doi'])
# S2.2: 250 seeds per topic.
for t in [f'T{i:02d}' for i in range(1,9)]:
    arr=[r for r in by_doi.values() if r['source_stage']=='S2.2' and t in (r['topics'] or '').split('; ')]
    arr.sort(key=lambda r:(r['rank_score'],r['cited_by_count'],r['year']),reverse=True)
    for r in arr[:250]:
        if r['doi'] not in used: selected.append(r); used.add(r['doi'])
# Global high-value fill to 5,500.
rest=sorted(by_doi.values(),key=lambda r:(r['rank_score'],r['cited_by_count'],r['year']),reverse=True)
for r in rest:
    if len(selected)>=5500: break
    if r['doi'] not in used: selected.append(r); used.add(r['doi'])

headers=['seed_id','doi','title','first_author','year','journal','cited_by_count','openalex_id','k_domains','topics','source_stage','rank_score','author_eligible']
for i,r in enumerate(selected,1):
    r['seed_id']=f'SEED-{i:05d}'; r['author_eligible']='yes' if r['cited_by_count']>=20 else 'no'
with (OUT/'B004_S2_3_seeds.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=headers);w.writeheader();w.writerows([{k:r.get(k,'') for k in headers} for r in selected])
(OUT/'B004_S2_3_existing_dois.txt').write_text('\n'.join(sorted(existing)),encoding='utf-8')
summary={'stage':'S2.3-seed-preparation','s21_rows':len(s21),'s22_rows':len(s22),'combined_existing_unique_dois':len(existing),'selected_seeds':len(selected),'s21_seeds':sum(r['source_stage']=='S2.1' for r in selected),'s22_seeds':sum(r['source_stage']=='S2.2' for r in selected),'author_eligible':sum(r['author_eligible']=='yes' for r in selected)}
(OUT/'seed_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False),flush=True)
if len(selected)<4000: raise SystemExit(2)
