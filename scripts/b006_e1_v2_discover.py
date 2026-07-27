import ast
import csv
import html
import json
import math
import os
import re
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote

import requests

K = os.environ.get('K_DOMAIN', '').strip()
STRATEGY = os.environ.get('STRATEGY', 'precision').strip()
OUT = Path('out'); OUT.mkdir(exist_ok=True)
VALID_K = {f'K{i:02d}' for i in range(1,17)}
if K not in VALID_K or STRATEGY not in {'precision','frontier','network'}:
    raise SystemExit(f'Invalid K_DOMAIN={K} STRATEGY={STRATEGY}')

# Reuse the curated B006 query matrix without importing and executing the old script.
source_text = Path('scripts/b006_e1_discover.py').read_text(encoding='utf-8')
tree = ast.parse(source_text)
QUERIES = None
for node in tree.body:
    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'QUERIES' for t in node.targets):
        QUERIES = ast.literal_eval(node.value); break
if not QUERIES or K not in QUERIES:
    raise RuntimeError('Unable to load B006 query matrix')
SEMANTICS = json.loads(Path('data/b006_e1_v2_semantics.json').read_text(encoding='utf-8'))
GROUPS = SEMANTICS[K]
DOMAIN_TERMS = json.loads(Path('data/b004_s3_2_terms.json').read_text(encoding='utf-8'))[K]

ROOT = Path('prepare_artifact')
excluded_files = list(ROOT.rglob('B004_B005_226220_excluded_dois.txt'))
seed_files = list(ROOT.rglob(f'B006_E1_seeds_{K}.csv'))
if len(excluded_files) != 1 or len(seed_files) != 1:
    raise RuntimeError(f'Missing registry or seeds: {len(excluded_files)}/{len(seed_files)}')
excluded = {x.strip().lower() for x in excluded_files[0].read_text(encoding='utf-8').splitlines() if x.strip()}
if len(excluded) != 226220:
    raise RuntimeError(f'Unexpected prior DOI count {len(excluded)}')
with seed_files[0].open('r',encoding='utf-8-sig',newline='') as f:
    seeds = list(csv.DictReader(f))

FOOD_ROOTS = ['food','edibl','diet','nutrit','ingredient','beverage','dairy','milk','casein','whey','lactoferr','egg','meat','fish','marine','seafood','oyster','shrimp','collagen','gelatin','soy','pea','bean','rice','wheat','oat','barley','maize','cereal','algae','seaweed','mushroom','mycoprotein','insect','surimi','ferment']
OBJECT_ROOTS = ['protein','peptid','hydrolys','proteas','peptidas','enzyme','digest','ferment','amino acid','collagen','gelatin','casein','whey']
DESIGN_ROOTS = ['design','engineer','generative','language model','directed evolution','mutagen','inverse folding','diffusion','computational','de novo']
METHOD_ROOTS = ['mass spectrom','lc ms','proteom','peptidom','spectroscop','sensor','digital twin','database','ontology','quantif']
HARD_EXCLUDE = ['cancer vaccine','tumor vaccine','epitope vaccine','hiv vaccine','malaria vaccine','sars cov vaccine','peptide drug conjugate','radioimmunotherapy','opioid drug','venom peptide','conotoxin','chemotherapy peptide','car t','therapeutic antibody']
ALLOWED_TYPES = {'article','review','meta-analysis','systematic-review','preprint','book-chapter'}
STOP = {'food','protein','peptide','enzyme','the','and','with','from','into','for','application','study','analysis','effect','effects','2023','2024','2025','2026','industrial','review'}
word_re = re.compile(r'[^a-z0-9]+')

session = requests.Session()
session.headers.update({'User-Agent':'Shuzhen-B006-v2-precision-expansion/1.0 (mailto:research@example.com)','Accept':'application/json'})

def norm(x): return ' '.join(word_re.sub(' ',html.unescape(str(x or '')).lower()).split())
def clean_doi(x):
    x=str(x or '').strip().lower(); x=re.sub(r'^https?://(dx\.)?doi\.org/','',x); return x.rstrip('.,;) ')
def abstract_text(inv):
    if not inv: return ''
    seq=[]
    for w,ps in inv.items():
        for p in ps: seq.append((p,w))
    seq.sort(); return ' '.join(w for _,w in seq)
def words(text): return set(norm(text).split())
def contains_root(text, root): return norm(root) in text
def root_hits(text, roots): return sorted({r for r in roots if contains_root(text,r)})
def phrase_hits(text, phrases):
    padded=' '+text+' '; out=[]
    for p in phrases:
        q=norm(p)
        if q and (' '+q+' ') in padded: out.append(p)
    return out
def group_hits(text): return [i for i,g in enumerate(GROUPS) if any(contains_root(text,x) for x in g)]
def query_hits(text, query):
    toks=[]
    for t in norm(query).split():
        if len(t)>=4 and t not in STOP and not any(t.startswith(x[:5]) for x in ['protein','peptide','enzyme']): toks.append(t)
    return sorted({t for t in toks if t in text or (len(t)>=6 and t[:6] in text)})
def get_json(url,params=None,attempts=7):
    for i in range(attempts):
        try:
            r=session.get(url,params=params,timeout=55)
            if r.status_code==200: return r.json()
            if r.status_code in {429,500,502,503,504}: time.sleep(1.2*(i+1)); continue
            return None
        except Exception: time.sleep(1.2*(i+1))
    return None
def first_author(w):
    a=w.get('authorships') or []; return ((((a[0].get('author') or {}).get('display_name')) if a else '') or '')
def journal(w): return ((((w.get('primary_location') or {}).get('source') or {}).get('display_name')) or '')
def landing(w): return ((w.get('primary_location') or {}).get('landing_page_url') or '')

def evaluate(work,query='',relation_count=0,relation_types=None,seed_dois=None):
    doi=clean_doi(work.get('doi')); title_raw=(work.get('title') or '').strip()
    if not doi or doi in excluded or not title_raw or (work.get('type') or '') not in ALLOWED_TYPES: return None
    abstract_raw=abstract_text(work.get('abstract_inverted_index'))
    title=norm(title_raw); abstract=norm(abstract_raw); combined=' '.join([title,abstract,norm(journal(work))])
    if any(x in combined for x in HARD_EXCLUDE): return None
    t_exact=phrase_hits(title,DOMAIN_TERMS); a_exact=phrase_hits(abstract,DOMAIN_TERMS)
    tg=group_hits(title); cg=group_hits(combined)
    food=root_hits(combined,FOOD_ROOTS); obj=root_hits(combined,OBJECT_ROOTS); design=root_hits(combined,DESIGN_ROOTS); method=root_hits(combined,METHOD_ROOTS)
    tq=query_hits(title,query); cq=query_hits(combined,query)
    exact_ok=bool(t_exact or a_exact)
    semantic_ok=bool(tg) or len(cg)>=2 or (len(tq)>=1 and len(cq)>=2)
    object_ok=bool(obj)
    food_ok=bool(food)
    if K in {'K10','K11','K12'}:
        gate=object_ok and bool(design) and semantic_ok
        transfer='design-transfer'
    elif K=='K15':
        gate=object_ok and bool(method) and semantic_ok and (food_ok or len(cg)>=2)
        transfer='food-method'
    elif K in {'K09','K13'}:
        gate=object_ok and semantic_ok and (food_ok or (len(cg)>=2 and len(cq)>=2))
        transfer='food-or-controlled-transfer'
    else:
        gate=object_ok and food_ok and semantic_ok
        transfer='food-direct'
    if not gate: return None
    score=4.0*len(t_exact)+1.2*min(len(a_exact),8)+2.8*len(tg)+0.9*len(cg)
    score+=1.8*min(len(food),4)+1.1*min(len(obj),4)+0.9*min(len(design),3)+0.7*min(len(method),3)
    score+=1.1*min(len(tq),4)+0.3*min(len(cq),6)+min(math.log1p(max(relation_count,0)),3.8)
    if abstract_raw: score+=0.4
    minimum=6.5 if STRATEGY in {'precision','frontier'} else 5.8
    if score<minimum: return None
    evidence='title-exact' if t_exact else ('title-semantic' if tg or tq else ('abstract-exact' if a_exact else 'multi-semantic'))
    return {'k_domain':K,'strategy':STRATEGY,'doi':doi,'title':title_raw,'first_author':first_author(work),'year':work.get('publication_year') or '','journal':journal(work),'document_type':work.get('type') or '','abstract':abstract_raw[:6000],'cited_by_count':work.get('cited_by_count') or 0,'is_oa':'yes' if bool((work.get('open_access') or {}).get('is_oa')) else 'no','openalex_id':work.get('id') or '','article_link':landing(work) or ('https://doi.org/'+doi),'query':query,'relation_count':relation_count,'relation_types':'; '.join(sorted(relation_types or [])),'seed_dois':'; '.join(sorted(seed_dois or [])[:40]),'precision_score':round(score,4),'title_domain_hits':'; '.join(t_exact[:10]),'abstract_domain_hits':'; '.join(a_exact[:12]),'semantic_group_hits':'; '.join(str(x) for x in cg),'food_hits':'; '.join(food[:12]),'object_hits':'; '.join(obj[:12]),'design_hits':'; '.join(design[:10]),'query_token_hits':'; '.join(cq[:12]),'evidence_mode':evidence,'transfer_mode':transfer}

def merge_record(records,row):
    if not row: return
    old=records.get(row['doi'])
    if old is None or (row['precision_score'],int(row.get('cited_by_count') or 0),len(row.get('abstract') or ''))>(old['precision_score'],int(old.get('cited_by_count') or 0),len(old.get('abstract') or '')): records[row['doi']]=row

def search_strategy():
    records={}; raw=0; calls=0; base=list(QUERIES[K])
    if STRATEGY=='precision':
        queries=base+[q+' method' for q in base[:4]]
        windows=[('1950-01-01','1999-12-31'),('2000-01-01','2009-12-31'),('2010-01-01','2016-12-31'),('2017-01-01','2022-12-31')]
        pages=3
    else:
        queries=base
        windows=[('2023-01-01','2023-12-31'),('2024-01-01','2024-12-31'),('2025-01-01','2025-12-31'),('2026-01-01','2026-12-31')]
        pages=4
    for qi,q in enumerate(queries,1):
        for start,end in windows:
            cursor='*'
            for _ in range(pages):
                data=get_json('https://api.openalex.org/works',{'search':q,'filter':f'has_doi:true,from_publication_date:{start},to_publication_date:{end}','per-page':200,'cursor':cursor,'mailto':'research@example.com'})
                calls+=1
                if not data: break
                batch=data.get('results') or []
                if not batch: break
                raw+=len(batch)
                for work in batch: merge_record(records,evaluate(work,query=q))
                cursor=(data.get('meta') or {}).get('next_cursor')
                if not cursor: break
                time.sleep(0.04)
        print('SEARCH_PROGRESS',K,STRATEGY,qi,len(queries),raw,len(records),flush=True)
    return records,{'raw_occurrences':raw,'queries':len(queries),'date_windows':len(windows),'api_calls':calls}

def fetch_seed(seed):
    oid=(seed.get('openalex_id') or '').strip()
    url=oid.replace('https://openalex.org/','https://api.openalex.org/works/') if oid else 'https://api.openalex.org/works/https://doi.org/'+quote(seed['doi'],safe='/:.')
    return seed,get_json(url,{'mailto':'research@example.com'})
def fetch_work(wid): return wid,get_json(wid.replace('https://openalex.org/','https://api.openalex.org/works/'),{'mailto':'research@example.com'})
def author_works(aid):
    d=get_json('https://api.openalex.org/works',{'filter':f'authorships.author.id:{aid},has_doi:true,from_publication_date:1980-01-01','sort':'cited_by_count:desc','per-page':200,'mailto':'research@example.com'})
    return aid,(d.get('results') or []) if d else []
def citing_works(wid,sdoi):
    short=wid.rsplit('/',1)[-1]
    d=get_json('https://api.openalex.org/works',{'filter':f'cites:{short},has_doi:true','sort':'cited_by_count:desc','per-page':100,'mailto':'research@example.com'})
    return sdoi,(d.get('results') or []) if d else []

def network_strategy():
    resolved=[]
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs=[ex.submit(fetch_seed,s) for s in seeds]
        for fut in as_completed(futs):
            try: s,w=fut.result()
            except Exception: continue
            if w and w.get('id'): resolved.append((s,w))
    candidates=defaultdict(lambda:{'count':0,'types':set(),'seeds':set()}); authors=Counter(); direct=[]
    for s,w in resolved:
        sd=s['doi']
        for wid in (w.get('referenced_works') or [])[:45]: c=candidates[wid]; c['count']+=1;c['types'].add('reference');c['seeds'].add(sd)
        for wid in (w.get('related_works') or [])[:30]: c=candidates[wid]; c['count']+=1;c['types'].add('related');c['seeds'].add(sd)
        for a in w.get('authorships') or []:
            aid=((a.get('author') or {}).get('id') or '').strip()
            if aid: authors[aid]+=1
    top_seed=sorted(resolved,key=lambda sw:int(sw[1].get('cited_by_count') or 0),reverse=True)[:80]
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs=[ex.submit(citing_works,w['id'],s['doi']) for s,w in top_seed]
        for fut in as_completed(futs):
            try: sd,works=fut.result()
            except Exception: continue
            for w in works: direct.append((w,1,{'citing'},{sd}))
    top_auth=[a for a,_ in authors.most_common(90)]
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs=[ex.submit(author_works,a) for a in top_auth]
        for fut in as_completed(futs):
            try: aid,works=fut.result()
            except Exception: continue
            for w in works:
                wid=w.get('id') or ''
                if wid: c=candidates[wid];c['count']+=1;c['types'].add('core_author')
    ranked=sorted(candidates,key=lambda x:(candidates[x]['count'],'related' in candidates[x]['types'],'core_author' in candidates[x]['types']),reverse=True)[:5000]
    fetched=[]
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs=[ex.submit(fetch_work,wid) for wid in ranked]
        for fut in as_completed(futs):
            try: wid,w=fut.result()
            except Exception: continue
            if w: fetched.append((wid,w))
    records={}
    for w,count,types,sds in direct: merge_record(records,evaluate(w,relation_count=count,relation_types=types,seed_dois=sds))
    for wid,w in fetched:
        m=candidates[wid]; merge_record(records,evaluate(w,relation_count=m['count'],relation_types=m['types'],seed_dois=m['seeds']))
    return records,{'seeds_input':len(seeds),'seeds_resolved':len(resolved),'candidate_openalex_ids':len(candidates),'candidate_ids_fetched':len(fetched),'citing_records_fetched':len(direct),'core_authors':len(top_auth)}

records,extra=network_strategy() if STRATEGY=='network' else search_strategy()
headers=['k_domain','strategy','doi','title','first_author','year','journal','document_type','abstract','cited_by_count','is_oa','openalex_id','article_link','query','relation_count','relation_types','seed_dois','precision_score','title_domain_hits','abstract_domain_hits','semantic_group_hits','food_hits','object_hits','design_hits','query_token_hits','evidence_mode','transfer_mode']
with (OUT/f'B006_E1_V2_{K}_{STRATEGY}.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=headers);w.writeheader();w.writerows([{h:r.get(h,'') for h in headers} for r in sorted(records.values(),key=lambda r:(r['precision_score'],int(r.get('cited_by_count') or 0)),reverse=True)])
summary={'stage':'B006-E1-v2','k_domain':K,'strategy':STRATEGY,'excluded_prior_dois':len(excluded),'new_high_precision_unique_dois':len(records),'evidence_mode_counts':dict(Counter(r['evidence_mode'] for r in records.values())),'score_min':min((r['precision_score'] for r in records.values()),default=0),**extra}
(OUT/f'B006_E1_V2_{K}_{STRATEGY}_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False),flush=True)
# Per-shard failure is reserved for a complete API collapse; global quality is decided after all checkpoints are merged.
if (STRATEGY=='network' and extra.get('seeds_resolved',0)<200) or (STRATEGY!='network' and extra.get('raw_occurrences',0)<500): raise SystemExit(2)
