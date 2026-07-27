import csv
import json
import sys
from collections import Counter
from pathlib import Path

try: csv.field_size_limit(sys.maxsize)
except OverflowError: csv.field_size_limit(2**31-1)

SHARDS=Path('shard_artifacts'); PREP=Path('prepare_artifact'); OUT=Path('out'); OUT.mkdir(exist_ok=True)
files=sorted(SHARDS.rglob('B006_E1_V2_K*_*.csv'))
summary_files=sorted(SHARDS.rglob('B006_E1_V2_K*_*_summary.json'))
reg=list(PREP.rglob('B004_B005_226220_excluded_dois.txt'))
if len(reg)!=1: raise RuntimeError(f'Expected one registry, found {len(reg)}')
excluded={x.strip().lower() for x in reg[0].read_text(encoding='utf-8').splitlines() if x.strip()}
if len(excluded)!=226220: raise RuntimeError(f'Unexpected registry size {len(excluded)}')

by_doi={}; raw=0
for path in files:
    with path.open('r',encoding='utf-8-sig',newline='') as f:
        for row in csv.DictReader(f):
            raw+=1; doi=(row.get('doi') or '').strip().lower()
            if not doi or doi in excluded: continue
            try: score=float(row.get('precision_score') or 0)
            except Exception: score=0
            try: cited=int(float(row.get('cited_by_count') or 0))
            except Exception: cited=0
            cur=by_doi.get(doi)
            if cur is None:
                cur=dict(row); cur['doi']=doi;cur['_max']=score;cur['_sum']=score;cur['_n']=1
                cur['_ks']={row.get('k_domain') or ''};cur['_ss']={row.get('strategy') or ''};cur['_ev']={row.get('evidence_mode') or ''};cur['_tr']={row.get('transfer_mode') or ''}
                cur['_queries']={row.get('query')} if row.get('query') else set();cur['_rel']=set(x for x in (row.get('relation_types') or '').split('; ') if x);cur['_seeds']=set(x for x in (row.get('seed_dois') or '').split('; ') if x);cur['cited_by_count']=cited
                by_doi[doi]=cur
            else:
                cur['_max']=max(cur['_max'],score);cur['_sum']+=score;cur['_n']+=1;cur['_ks'].add(row.get('k_domain') or '');cur['_ss'].add(row.get('strategy') or '');cur['_ev'].add(row.get('evidence_mode') or '');cur['_tr'].add(row.get('transfer_mode') or '')
                if row.get('query'): cur['_queries'].add(row['query'])
                cur['_rel'].update(x for x in (row.get('relation_types') or '').split('; ') if x);cur['_seeds'].update(x for x in (row.get('seed_dois') or '').split('; ') if x)
                old_key=(float(cur.get('precision_score') or 0),int(cur.get('cited_by_count') or 0),len(cur.get('abstract') or ''))
                new_key=(score,cited,len(row.get('abstract') or ''))
                if new_key>old_key:
                    for field in ['k_domain','strategy','title','first_author','year','journal','document_type','abstract','cited_by_count','is_oa','openalex_id','article_link','query','relation_count','title_domain_hits','abstract_domain_hits','semantic_group_hits','food_hits','object_hits','design_hits','query_token_hits','evidence_mode','transfer_mode','precision_score']:
                        if row.get(field) not in {None,''}: cur[field]=row[field]

rows=[]
for doi,r in by_doi.items():
    ks=sorted(x for x in r['_ks'] if x); ss=sorted(x for x in r['_ss'] if x); ev=sorted(x for x in r['_ev'] if x); tr=sorted(x for x in r['_tr'] if x)
    score=r['_max']; n=r['_n']; food=bool((r.get('food_hits') or '').strip()); title_evidence=any(x.startswith('title') for x in ev); direct='food-direct' in tr or 'food-method' in tr
    if score>=10 and title_evidence and (food or r.get('k_domain') in {'K10','K11','K12'}): tier='HP-A'
    elif score>=7.5 and (title_evidence or n>=2 or len(ss)>=2) and (food or direct or r.get('k_domain') in {'K09','K10','K11','K12','K13','K15'}): tier='HP-B'
    else: tier='HP-C'
    out={k:v for k,v in r.items() if not k.startswith('_')}
    out.update({'doi':doi,'primary_k_domain':r.get('k_domain') or (ks[0] if ks else ''),'k_domains':'; '.join(ks),'strategies':'; '.join(ss),'candidate_tier':tier,'precision_score_max':round(score,4),'precision_score_mean':round(r['_sum']/n,4),'source_rows':n,'evidence_modes':'; '.join(ev),'transfer_modes':'; '.join(tr),'queries':' || '.join(sorted(r['_queries'])),'relation_types':'; '.join(sorted(r['_rel'])),'seed_dois':'; '.join(sorted(r['_seeds'])[:80]),'prior_overlap':'no'})
    rows.append(out)
rows.sort(key=lambda r:({'HP-A':0,'HP-B':1,'HP-C':2}.get(r['candidate_tier'],9),-float(r['precision_score_max']),-int(r['source_rows']),-int(float(r.get('cited_by_count') or 0)),r.get('title') or ''))
headers=['doi','title','first_author','year','journal','document_type','abstract','cited_by_count','is_oa','openalex_id','article_link','primary_k_domain','k_domains','strategies','candidate_tier','precision_score_max','precision_score_mean','source_rows','evidence_modes','transfer_modes','title_domain_hits','abstract_domain_hits','semantic_group_hits','food_hits','object_hits','design_hits','query_token_hits','queries','relation_count','relation_types','seed_dois','prior_overlap']
with (OUT/'B006_E1_V2_new_high_precision_candidates.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=headers);w.writeheader();w.writerows([{h:r.get(h,'') for h in headers} for r in rows])
for tier in ['HP-A','HP-B','HP-C']:
    with (OUT/f'B006_E1_V2_{tier}_candidates.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=headers);w.writeheader();w.writerows([{h:r.get(h,'') for h in headers} for r in rows if r['candidate_tier']==tier])

summaries=[]
for p in summary_files:
    try: summaries.append(json.loads(p.read_text(encoding='utf-8')))
    except Exception: pass
km=Counter();pk=Counter();sm=Counter();tiers=Counter()
for r in rows:
    pk[r['primary_k_domain']]+=1;tiers[r['candidate_tier']]+=1
    for k in r['k_domains'].split('; '):
        if k: km[k]+=1
    for s in r['strategies'].split('; '):
        if s: sm[s]+=1
small=[f'K{i:02d}' for i in range(1,17) if km.get(f'K{i:02d}',0)<250]
overlap=len(set(by_doi)&excluded); hpab=tiers.get('HP-A',0)+tiers.get('HP-B',0)
quality={'all_48_shards':len(files)>=48,'new_unique_dois_min_20000':len(rows)>=20000,'HP_A_B_min_12000':hpab>=12000,'prior_overlap_zero':overlap==0,'each_K_membership_min_250':not small,'all_three_strategies':all(sm.get(s,0)>0 for s in ['precision','frontier','network'])}
status='success' if all(quality.values()) else 'failure'
summary={'stage':'B006-E1-v2','status':status,'shard_csv_files_found':len(files),'shard_summary_files_found':len(summary_files),'raw_high_precision_rows':raw,'new_global_unique_dois':len(rows),'HP_A_B_candidates':hpab,'prior_registry_dois':len(excluded),'overlap_with_B004_B005':overlap,'candidate_tier_counts':dict(tiers),'primary_K_counts':dict(pk),'K_membership_counts':dict(km),'strategy_membership_counts':dict(sm),'missing_or_small_K_domains':small,'shard_result_counts':{f"{s.get('k_domain')}-{s.get('strategy')}":s.get('new_high_precision_unique_dois',0) for s in summaries},'quality_gate':quality,'next_stage':'B006-E2 metadata verification, conservative A/B/C classification and stratified precision audit'}
(OUT/'run_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'stage_report.md').write_text('\n'.join(['# B006 E1 v2 High-Precision Expansion Report','',f'- Status: **{status}**',f'- Prior DOI registry: {len(excluded):,}',f'- Raw accepted shard rows: {raw:,}',f'- New global unique DOIs: {len(rows):,}',f'- HP-A + HP-B: {hpab:,}',f'- Prior overlap: {overlap}',f'- Candidate tiers: {dict(tiers)}',f'- K memberships: {dict(km)}',f'- Strategies: {dict(sm)}',f'- Missing/small domains: {small}',f"- Next: {summary['next_stage']}"]),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False),flush=True)
if status!='success': raise SystemExit(2)
