import csv, html, json, os, re, time, math
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote
import requests

MODE=os.environ.get('MODE','').strip(); SHARD=int(os.environ.get('SHARD','0')); SHARD_COUNT=int(os.environ.get('SHARD_COUNT','8'))
MODES={'references','citations','related','authors','similar'}
if MODE not in MODES: raise SystemExit(f'invalid MODE {MODE}')
ROOT=Path('seed_input'); OUT=Path('out'); OUT.mkdir(exist_ok=True)
seed_files=list(ROOT.rglob('B004_S2_3_seeds.csv'))
if not seed_files: raise FileNotFoundError('B004_S2_3_seeds.csv')
with seed_files[0].open('r',encoding='utf-8-sig',newline='') as f: seeds=list(csv.DictReader(f))
seeds=[s for i,s in enumerate(seeds) if i%SHARD_COUNT==SHARD]
if MODE=='authors': seeds=[s for s in seeds if s.get('author_eligible')=='yes'][:300]
if MODE=='similar': seeds=seeds[:400]

S=requests.Session(); S.headers.update({'User-Agent':'Shuzhen-B004-S2.3/1.0 (mailto:research@example.com)','Accept':'application/json'})
OBJECT=['protein','peptide','enzyme','protease','peptidase','hydrolysate','hydrolyzed','digestion','proteomic','peptidomic','amino acid','fermentation','biomanufactur']
FOOD=['food','milk','dairy','casein','whey','lactoferrin','collagen','gelatin','fish','marine','seafood','soy','pea','bean','rice','wheat','oat','egg','meat','surimi','edible','dietary','nutrition','functional ingredient','food-derived']
DESIGN=['machine learning','deep learning','language model','generative','protein design','peptide design','enzyme design','directed evolution','rational design','inverse folding','diffusion model','active learning','digital twin']
EXCLUDE=['cancer vaccine','tumor vaccine','hiv vaccine','malaria vaccine','sars-cov','covid-19 peptide','peptide-drug conjugate','radioimmunotherapy','opioid drug','venom peptide','conotoxin']

def norm(x):
    x=html.unescape(str(x or '')).lower(); x=re.sub(r'<[^>]+>',' ',x); x=re.sub(r'[^a-z0-9]+',' ',x); return ' '.join(x.split())
def doi_clean(x):
    x=str(x or '').strip().lower(); x=re.sub(r'^https?://(dx\.)?doi\.org/','',x); return x.rstrip('.,;) ')
def abstract(inv):
    if not inv:return ''
    z=[]
    for w,pp in inv.items():
        for p in pp:z.append((p,w))
    z.sort();return ' '.join(w for _,w in z)
def get_json(url,params=None,tries=5):
    for i in range(tries):
        try:
            r=S.get(url,params=params,timeout=45)
            if r.status_code==200:return r.json()
            if r.status_code in {429,500,502,503,504}: time.sleep(1.0*(i+1));continue
            return None
        except Exception: time.sleep(1.0*(i+1))
    return None
def resolve(seed):
    oid=(seed.get('openalex_id') or '').strip()
    if oid:
        return get_json(oid.replace('https://openalex.org/','https://api.openalex.org/works/'))
    doi=doi_clean(seed.get('doi'))
    d=get_json('https://api.openalex.org/works',{'filter':f'doi:{doi}','per-page':1,'mailto':'research@example.com'})
    arr=(d or {}).get('results') or []
    return arr[0] if arr else None
def score(w):
    title=w.get('title') or ''; ab=abstract(w.get('abstract_inverted_index')); txt=norm(title+' '+ab)
    if not txt or any(x in txt for x in EXCLUDE): return -999,ab,[]
    oh=[x for x in OBJECT if x in txt]; fh=[x for x in FOOD if x in txt]; dh=[x for x in DESIGN if x in txt]
    if not oh and not dh:return -999,ab,[]
    sc=len(oh)*1.8+min(len(fh),4)*1.2+len(dh)*1.5+(0.5 if ab else 0)+min(math.log1p(w.get('cited_by_count') or 0),5)*0.2
    if not fh and not dh:sc-=1.5
    return round(sc,3),ab,sorted(set(oh+fh[:4]+dh))
def fetch_ids(ids):
    out=[]
    ids=[x.rsplit('/',1)[-1] for x in ids if x]
    for i in range(0,len(ids),25):
        q='|'.join(ids[i:i+25]); d=get_json('https://api.openalex.org/works',{'filter':f'openalex_id:{q}','per-page':25,'mailto':'research@example.com'})
        out.extend((d or {}).get('results') or [])
    return out
def citing(oid):
    wid=oid.rsplit('/',1)[-1]
    d=get_json('https://api.openalex.org/works',{'filter':f'cites:{wid},has_doi:true,from_publication_date:1990-01-01','per-page':100,'sort':'cited_by_count:desc','mailto':'research@example.com'})
    return (d or {}).get('results') or []
def author_works(work):
    auth=work.get('authorships') or []; ids=[]
    if auth: ids.append(((auth[0].get('author') or {}).get('id') or ''))
    if len(auth)>1: ids.append(((auth[-1].get('author') or {}).get('id') or ''))
    out=[]
    for aid in dict.fromkeys(x for x in ids if x):
        a=aid.rsplit('/',1)[-1]
        d=get_json('https://api.openalex.org/works',{'filter':f'author.id:{a},has_doi:true,from_publication_date:1990-01-01','per-page':100,'sort':'cited_by_count:desc','mailto':'research@example.com'})
        out.extend((d or {}).get('results') or [])
    return out
def similar(seed):
    q=' '.join((seed.get('title') or '').split()[:18])
    d=get_json('https://api.openalex.org/works',{'search':q,'filter':'has_doi:true,from_publication_date:1990-01-01','per-page':50,'mailto':'research@example.com'})
    return (d or {}).get('results') or []

def candidate_row(w,seed,sc,ab,hits):
    doi=doi_clean(w.get('doi')); p=w.get('primary_location') or {}; src=p.get('source') or {}; aa=w.get('authorships') or []
    fa=((aa[0].get('author') or {}).get('display_name') or '').split()[-1] if aa else ''
    return {'mode':MODE,'shard':SHARD,'seed_doi':seed.get('doi',''),'seed_title':seed.get('title',''),'seed_k_domains':seed.get('k_domains',''),'seed_topics':seed.get('topics',''),'doi':doi,'title':w.get('title') or '','first_author':fa,'year':w.get('publication_year') or '','journal':src.get('display_name') or '','document_type':w.get('type') or '','abstract':ab[:4000],'cited_by_count':w.get('cited_by_count') or 0,'is_oa':'yes' if (w.get('open_access') or {}).get('is_oa') else 'no','openalex_id':w.get('id') or '','landing_page':p.get('landing_page_url') or ('https://doi.org/'+doi if doi else ''),'relevance_score':sc,'matched_terms':'; '.join(hits)}

pool={}; raw=0; resolved=0; failures=0
for idx,seed in enumerate(seeds,1):
    work=resolve(seed)
    if not work: failures+=1;continue
    resolved+=1
    if MODE=='references': cand=fetch_ids((work.get('referenced_works') or [])[:60])
    elif MODE=='related': cand=fetch_ids((work.get('related_works') or [])[:25])
    elif MODE=='citations': cand=citing(work.get('id') or '')
    elif MODE=='authors': cand=author_works(work)
    else: cand=similar(seed)
    raw+=len(cand)
    for w in cand:
        doi=doi_clean(w.get('doi'))
        if not doi or doi==doi_clean(seed.get('doi')):continue
        sc,ab,hits=score(w)
        if sc<1.5:continue
        row=candidate_row(w,seed,sc,ab,hits)
        old=pool.get(doi)
        if old is None:
            row['seed_count']=1; row['seed_dois']={seed.get('doi','')}; pool[doi]=row
        else:
            old['seed_count']+=1; old['seed_dois'].add(seed.get('doi',''))
            if sc>float(old.get('relevance_score') or 0):
                keep_count=old['seed_count'];keep_seeds=old['seed_dois'];pool[doi]=row;pool[doi]['seed_count']=keep_count;pool[doi]['seed_dois']=keep_seeds
    if idx%100==0: print('PROGRESS',MODE,SHARD,idx,'resolved',resolved,'raw',raw,'kept',len(pool),flush=True)

headers=['mode','shard','seed_count','seed_dois','seed_k_domains','seed_topics','doi','title','first_author','year','journal','document_type','abstract','cited_by_count','is_oa','openalex_id','landing_page','relevance_score','matched_terms']
rows=[]
for r in pool.values():
    r['seed_dois']='; '.join(sorted(x for x in r['seed_dois'] if x)[:20]);rows.append(r)
rows.sort(key=lambda r:(float(r['relevance_score']),int(r['cited_by_count']),r['year']),reverse=True)
with (OUT/f'B004_S2_3_{MODE}_shard{SHARD}.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=headers);w.writeheader();w.writerows([{k:r.get(k,'') for k in headers} for r in rows])
summary={'stage':'S2.3','mode':MODE,'shard':SHARD,'seed_rows':len(seeds),'resolved_seeds':resolved,'resolve_failures':failures,'raw_occurrences':raw,'unique_doi_candidates':len(rows)}
(OUT/f'B004_S2_3_{MODE}_shard{SHARD}_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False),flush=True)
if resolved<max(20,int(len(seeds)*0.35)):raise SystemExit(2)
