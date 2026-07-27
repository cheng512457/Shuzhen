import csv,json,os,re,sys,time
from pathlib import Path
from collections import Counter
from concurrent.futures import ThreadPoolExecutor,as_completed
import requests
try: csv.field_size_limit(sys.maxsize)
except OverflowError: csv.field_size_limit(2**31-1)
SHARD=int(os.environ.get('SHARD','0')); ROOT=Path('input_artifact'); OUT=Path('out');OUT.mkdir(exist_ok=True)
files=list(ROOT.rglob(f'B006_E2_input_shard{SHARD}.csv'))
if len(files)!=1: raise RuntimeError(f'Missing shard {SHARD}')
source=files[0]
HARD=['cancer vaccine','tumor vaccine','epitope vaccine','hiv vaccine','malaria vaccine','sars cov vaccine','peptide drug conjugate','radioimmunotherapy','opioid peptide','venom peptide','conotoxin','car t','therapeutic antibody','amyloid beta','prion disease']
DOI_RE=re.compile(r'^10\.\d{4,9}/\S+$',re.I)
word=re.compile(r'[^a-z0-9]+')
def norm(x):return ' '.join(word.sub(' ',str(x or '').lower()).split())
def truth(x):return bool(str(x or '').strip())
def num(x):
    try:return float(x or 0)
    except:return 0.0
sess=requests.Session();sess.headers.update({'User-Agent':'Shuzhen-B006-E2/1.0 (mailto:research@example.com)','Accept':'application/json'})
def crossref(doi):
    for i in range(4):
        try:
            r=sess.get('https://api.crossref.org/works/'+doi,timeout=35)
            if r.status_code==200:
                m=(r.json().get('message') or {}); auth=m.get('author') or []
                title='; '.join(m.get('title') or []); journal='; '.join(m.get('container-title') or [])
                year=''
                for k in ['published-print','published-online','issued','created']:
                    parts=((m.get(k) or {}).get('date-parts') or [])
                    if parts and parts[0]:year=str(parts[0][0]);break
                first=''
                if auth:first=' '.join(x for x in [auth[0].get('given',''),auth[0].get('family','')] if x)
                return {'title':title,'first_author':first,'year':year,'journal':journal,'document_type':m.get('type') or '','article_link':m.get('URL') or ('https://doi.org/'+doi),'crossref_status':'resolved'}
            if r.status_code in {429,500,502,503,504}:time.sleep(1+i);continue
            return {'crossref_status':f'http_{r.status_code}'}
        except Exception:time.sleep(1+i)
    return {'crossref_status':'failed'}
with source.open('r',encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f)); base=csv.DictReader(source.open('r',encoding='utf-8-sig',newline='')).fieldnames or []
need=[r['doi'] for r in rows if not truth(r.get('first_author')) or not truth(r.get('year')) or not truth(r.get('journal'))]
updates={}
with ThreadPoolExecutor(max_workers=6) as ex:
    futs={ex.submit(crossref,d):d for d in need}
    for i,fut in enumerate(as_completed(futs),1):
        try:updates[futs[fut]]=fut.result()
        except Exception:updates[futs[fut]]={'crossref_status':'failed'}
        if i%250==0:print('CROSSREF',SHARD,i,len(need),flush=True)

def classify(r):
    doi=(r.get('doi') or '').strip().lower(); valid=bool(DOI_RE.match(doi))
    text=norm(' '.join([r.get('title',''),r.get('abstract',''),r.get('journal',''),r.get('queries','')]))
    hard=[x for x in HARD if norm(x) in text]
    tier=r.get('candidate_tier') or 'HP-C'; score=num(r.get('precision_score_max')); source_rows=int(num(r.get('source_rows'))); strategies=[x for x in (r.get('strategies') or '').split('; ') if x]
    food=truth(r.get('food_hits')); obj=truth(r.get('object_hits')); design=truth(r.get('design_hits')); titleev=truth(r.get('title_domain_hits')) or 'title' in (r.get('evidence_modes') or '')
    direct=('food-direct' in (r.get('transfer_modes') or '') or 'food-method' in (r.get('transfer_modes') or ''))
    if not valid: rel='D';reason='DOI格式无效'
    elif hard and not (food and direct):rel='D';reason='硬排除主题且缺乏食品迁移接口'
    elif tier=='HP-A' and score>=10 and titleev and obj and (food or direct or design):rel='A';reason='高精度题名/领域证据与食品或设计迁移证据同时成立'
    elif tier in {'HP-A','HP-B'} and score>=7.5 and obj and (food or direct or design) and (titleev or source_rows>=2 or len(strategies)>=2):rel='B';reason='多源或题名证据支持，具有明确食品研究或方法迁移价值'
    elif tier=='HP-C' and score>=8.5 and obj and food and titleev:rel='B';reason='边界候选但题名、食品对象和研究对象证据均较强'
    elif tier in {'HP-A','HP-B','HP-C'} and score>=5:rel='C';reason='相关边界或通用方法，保留复核但不自动下载'
    else:rel='D';reason='缺少足够的题名、食品对象或领域证据'
    cited=int(num(r.get('cited_by_count')))
    if rel=='A' and (score>=14 or source_rows>=3 or cited>=80):pri='P0'
    elif rel=='A' or (rel=='B' and score>=11):pri='P1'
    elif rel=='B':pri='P2'
    else:pri='P3'
    conf=min(.99,.42+min(score,20)/35+min(source_rows,3)*.04+(0.07 if titleev else 0)+(0.06 if food else 0))
    return {'relevance':rel,'download_priority':pri,'download_eligible':'yes' if rel in {'A','B'} else 'no','classification_confidence':round(conf,4),'classification_reason':reason,'invalid_doi':'no' if valid else 'yes','hard_exclusion_hits':'; '.join(hard)}
extra=['metadata_status','crossref_status','relevance','download_priority','download_eligible','classification_confidence','classification_reason','invalid_doi','hard_exclusion_hits']
headers=base+extra
counts=Counter();pc=Counter();mc=Counter();invalid=eligible=0
with (OUT/f'B006_E2_classified_shard{SHARD}.csv').open('w',encoding='utf-8-sig',newline='') as g:
    w=csv.DictWriter(g,fieldnames=headers);w.writeheader()
    for r in rows:
        u=updates.get((r.get('doi') or '').lower(),{})
        for fld in ['title','first_author','year','journal','document_type','article_link']:
            if not truth(r.get(fld)) and truth(u.get(fld)):r[fld]=u[fld]
        r['crossref_status']=u.get('crossref_status','not_needed')
        missing=[x for x in ['title','first_author','year','journal'] if not truth(r.get(x))]
        r['metadata_status']='complete' if not missing else 'partial:'+','.join(missing)
        c=classify(r);r.update(c);w.writerow({h:r.get(h,'') for h in headers})
        counts[c['relevance']]+=1;pc[c['download_priority']]+=1;mc[r['metadata_status']]+=1;invalid+=c['invalid_doi']=='yes';eligible+=c['download_eligible']=='yes'
summary={'stage':'B006-E2','shard':SHARD,'input_rows':len(rows),'classified_rows':len(rows),'relevance_counts':dict(counts),'priority_counts':dict(pc),'metadata_status_counts':dict(mc),'invalid_doi':invalid,'download_eligible':eligible,'crossref_queries':len(need)}
(OUT/f'B006_E2_shard{SHARD}_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False),flush=True)
if len(rows)<3000 or invalid>10:raise SystemExit(2)
