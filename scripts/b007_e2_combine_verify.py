import csv, json, re, sys, hashlib
from collections import Counter, defaultdict
from pathlib import Path

try: csv.field_size_limit(sys.maxsize)
except OverflowError: csv.field_size_limit(2**31-1)

SHARDS=Path('shard_artifacts'); PRIOR=Path('prior_database_artifact'); OUT=Path('out'); OUT.mkdir(exist_ok=True)
files=sorted(SHARDS.rglob('B007_E2_classified_shard*.csv'))
prior_files=list(PRIOR.rglob('B004_B005_B006_247023_cumulative_master.csv'))
if len(files)!=8: raise RuntimeError(f'Expected 8 classified shards, found {len(files)}')
if len(prior_files)!=1: raise RuntimeError(f'Expected one prior cumulative master, found {len(prior_files)}')

DOI_RE=re.compile(r'^10\.\d{4,9}/\S+$',re.I)
def truth(x): return bool(str(x or '').strip())
def num(x):
    try:return float(x or 0)
    except:return 0.0
def parts(x): return [v.strip() for v in str(x or '').split(';') if v.strip()]
def doi_norm(x):
    x=str(x or '').strip().lower(); x=re.sub(r'^https?://(dx\.)?doi\.org/','',x); return x.rstrip('.,;) ')

prior=set()
with prior_files[0].open('r',encoding='utf-8-sig',newline='') as f:
    for r in csv.DictReader(f):
        d=doi_norm(r.get('doi') or r.get('doi_normalized') or r.get('DOI'))
        if d: prior.add(d)
if len(prior)!=247023: raise RuntimeError(f'Unexpected prior DOI registry: {len(prior)}')

rows=[]; headers=None
for p in files:
    with p.open('r',encoding='utf-8-sig',newline='') as f:
        rd=csv.DictReader(f)
        if headers is None: headers=rd.fieldnames or []
        rows.extend(rd)
if len(rows)!=31209: raise RuntimeError(f'Unexpected classified row count: {len(rows)}')

seen=set(); duplicates=prior_overlap=invalid=0
all_rows=[]; formal=[]; boundary=[]; rejected=[]
for r in rows:
    doi=doi_norm(r.get('doi')); r['doi']=doi
    if doi in seen: duplicates+=1; continue
    seen.add(doi); prior_overlap += doi in prior
    valid=bool(DOI_RE.match(doi)); invalid += not valid
    score=num(r.get('precision_score_max')); source_rows=int(num(r.get('source_rows')))
    strategies=parts(r.get('strategies')); evidence=parts(r.get('evidence_modes')); transfer=parts(r.get('transfer_modes'))
    tier=r.get('candidate_tier') or 'HP-C'; hard=truth(r.get('hard_exclusion_hits'))
    obj=truth(r.get('object_hits')); food=truth(r.get('food_hits')); design=truth(r.get('design_hits'))
    title_ev=truth(r.get('title_domain_hits')) or any(v.startswith('title') for v in evidence)
    abstract_ev=truth(r.get('abstract_domain_hits')); semantic_ev=truth(r.get('semantic_group_hits')); query_ev=truth(r.get('query_token_hits'))
    direct='food-direct' in transfer or 'food-method' in transfer or 'food-or-controlled-transfer' in transfer
    context=food or direct or design
    corroboration=sum([title_ev,abstract_ev,semantic_ev,source_rows>=2,len(strategies)>=2,query_ev])
    verified_a=valid and not hard and tier=='HP-A' and score>=10 and obj and context and title_ev and corroboration>=2
    verified_b=valid and not hard and tier in {'HP-A','HP-B'} and score>=8 and obj and context and corroboration>=2
    verified_c_to_b=valid and not hard and tier=='HP-C' and score>=10 and obj and food and title_ev and abstract_ev and corroboration>=3
    if verified_a: rel='A'; reason='题名与领域证据明确，并由至少一类独立证据交叉支持'
    elif verified_b or verified_c_to_b: rel='B'; reason='研究对象和食品/设计迁移接口明确，且至少两类证据相互支持'
    elif valid and not hard and score>=5: rel='C'; reason='存在领域关联，但证据不足以进入正式全文下载池'
    else: rel='D'; reason='DOI无效、硬排除或主题证据不足'
    cited=int(num(r.get('cited_by_count')))
    if rel=='A' and (score>=14 or source_rows>=3 or cited>=80): pri='P0'
    elif rel=='A' or (rel=='B' and score>=11): pri='P1'
    elif rel=='B': pri='P2'
    else: pri='P3'
    r.update({'previous_relevance':r.get('relevance') or '','relevance':rel,'download_priority':pri,'download_eligible':'yes' if rel in {'A','B'} else 'no','verification_corroboration_count':corroboration,'verification_title_evidence':'yes' if title_ev else 'no','verification_abstract_evidence':'yes' if abstract_ev else 'no','verification_semantic_evidence':'yes' if semantic_ev else 'no','verification_context':'yes' if context else 'no','verification_reason':reason})
    all_rows.append(r)
    (formal if rel in {'A','B'} else boundary if rel=='C' else rejected).append(r)

extra=['previous_relevance','verification_corroboration_count','verification_title_evidence','verification_abstract_evidence','verification_semantic_evidence','verification_context','verification_reason']
out_headers=(headers or [])+[x for x in extra if x not in (headers or [])]
def write(name,data,hs=out_headers):
    with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=hs);w.writeheader();w.writerows([{h:r.get(h,'') for h in hs} for r in data])
write('B007_E2_all_verified.csv',all_rows);write('B007_E2_formal_AB_download_pool.csv',formal);write('B007_E2_boundary_C_pool.csv',boundary);write('B007_E2_rejected_D_pool.csv',rejected)

groups=defaultdict(list)
for r in formal: groups[(r.get('primary_k_domain') or 'K00',r.get('relevance') or '')].append(r)
audit=[]
for key,vals in sorted(groups.items()):
    vals.sort(key=lambda r:hashlib.sha256((r.get('doi') or '').encode()).hexdigest())
    for r in vals[:40]:
        score=num(r.get('precision_score_max')); corr=int(num(r.get('verification_corroboration_count'))); title=r.get('verification_title_evidence')=='yes'; context=r.get('verification_context')=='yes'; obj=truth(r.get('object_hits')); hard=truth(r.get('hard_exclusion_hits')); rel=r.get('relevance')
        supported=not hard and obj and context and corr>=2 and ((rel=='A' and score>=10 and title) or (rel=='B' and score>=8))
        x=dict(r);x['audit_status']='supported' if supported else 'unsupported';x['audit_basis']=f'rel={rel};score={score};title={title};object={obj};context={context};corroboration={corr};hard={hard}';audit.append(x)
audit_headers=out_headers+['audit_status','audit_basis'];write('B007_E2_stratified_precision_audit.csv',audit,audit_headers)

rel=Counter(r['relevance'] for r in all_rows); pri=Counter(r['download_priority'] for r in all_rows); fk=Counter(r.get('primary_k_domain') or 'K00' for r in formal); meta=Counter(r.get('metadata_status') or '' for r in all_rows); ac=Counter(r['audit_status'] for r in audit)
ashare=ac.get('supported',0)/len(audit) if audit else 0
small=[f'K{i:02d}' for i in range(1,17) if fk.get(f'K{i:02d}',0)<100]
quality={'all_8_shards':len(files)==8,'classified_rows_31209':len(all_rows)==31209,'formal_AB_min_12000':len(formal)>=12000,'prior_overlap_zero':prior_overlap==0,'duplicate_zero':duplicates==0,'invalid_doi_max_10':invalid<=10,'all_K_formal_min_100':not small,'audit_supported_share_min_080':ashare>=0.80}
status='success' if all(quality.values()) else 'failure'
summary={'stage':'B007-E2','status':status,'classified_rows':len(all_rows),'formal_AB_download_pool':len(formal),'relevance_counts':dict(rel),'priority_counts':dict(pri),'formal_K_counts':dict(fk),'metadata_status_counts':dict(meta),'invalid_doi':invalid,'prior_registry_dois':len(prior),'prior_overlap':prior_overlap,'duplicate_doi':duplicates,'missing_author_year_journal':[sum(not truth(r.get('first_author')) for r in all_rows),sum(not truth(r.get('year')) for r in all_rows),sum(not truth(r.get('journal')) for r in all_rows)],'audit_sample_records':len(audit),'audit_status_counts':dict(ac),'audit_supported_share':round(ashare,6),'missing_or_small_formal_K_domains':small,'quality_gate':quality,'next_stage':'B007-R01 first verified non-overlapping student download round'}
(OUT/'run_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'stage_report.md').write_text('\n'.join(['# B007 E2 Conservative Verification Report','',f'- Status: **{status}**',f'- Classified records: {len(all_rows):,}',f'- Verified formal A/B pool: {len(formal):,}',f'- Relevance: {dict(rel)}',f'- Priority: {dict(pri)}',f'- Formal K distribution: {dict(fk)}',f'- Prior overlap: {prior_overlap}',f'- Invalid DOI: {invalid}',f'- Stratified audit: {dict(ac)}; supported share {ashare:.2%}',f'- Quality gate: {quality}',f"- Next: {summary['next_stage']}"]),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False),flush=True)
if status!='success': raise SystemExit(2)
