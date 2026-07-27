import csv,json,sys,hashlib
from pathlib import Path
from collections import Counter,defaultdict
try: csv.field_size_limit(sys.maxsize)
except OverflowError: csv.field_size_limit(2**31-1)
ROOT=Path('shard_artifacts'); PREP=Path('input_artifact'); OUT=Path('out');OUT.mkdir(exist_ok=True)
files=sorted(ROOT.rglob('B006_E2_classified_shard*.csv')); summaries=sorted(ROOT.rglob('B006_E2_shard*_summary.json'))
if len(files)!=8:raise RuntimeError(f'Expected 8 classified shards, found {len(files)}')
reg=list(PREP.rglob('B004_B005_226220_excluded_dois.txt'))
if len(reg)!=1:raise RuntimeError('Missing prior DOI registry')
excluded={x.strip().lower() for x in reg[0].read_text(encoding='utf-8').splitlines() if x.strip()}
rows=[];headers=None;seen=set();dup=overlap=0
for p in files:
    with p.open('r',encoding='utf-8-sig',newline='') as f:
        rd=csv.DictReader(f)
        if headers is None:headers=rd.fieldnames or []
        for r in rd:
            doi=(r.get('doi') or '').strip().lower()
            if doi in seen:dup+=1;continue
            seen.add(doi);overlap+=doi in excluded;rows.append(r)
rel=Counter(r.get('relevance') or 'D' for r in rows);pri=Counter(r.get('download_priority') or 'P3' for r in rows);kc=Counter(r.get('primary_k_domain') or 'K00' for r in rows);tiers=Counter(r.get('candidate_tier') or '' for r in rows);meta=Counter(r.get('metadata_status') or '' for r in rows);strat=Counter()
for r in rows:
    for s in (r.get('strategies') or '').split('; '):
        if s:strat[s]+=1
formal=[r for r in rows if r.get('relevance') in {'A','B'}]
boundary=[r for r in rows if r.get('relevance')=='C'];rejected=[r for r in rows if r.get('relevance')=='D']
def write(name,data):
    with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=headers);w.writeheader();w.writerows(data)
write('B006_E2_all_classified.csv',rows);write('B006_E2_formal_AB_download_pool.csv',formal);write('B006_E2_boundary_C_pool.csv',boundary);write('B006_E2_rejected_D_pool.csv',rejected)
# Deterministic stratified audit: up to 40 records for each primary K x relevance A/B, independently flag evidence sufficiency.
groups=defaultdict(list)
for r in formal:groups[(r.get('primary_k_domain'),r.get('relevance'))].append(r)
audit=[]
for key,vals in sorted(groups.items()):
    vals.sort(key=lambda r:hashlib.sha256((r.get('doi') or '').encode()).hexdigest())
    for r in vals[:40]:
        score=float(r.get('precision_score_max') or 0); title=bool((r.get('title_domain_hits') or '').strip()); food=bool((r.get('food_hits') or '').strip()); obj=bool((r.get('object_hits') or '').strip()); design=bool((r.get('design_hits') or '').strip()); hard=bool((r.get('hard_exclusion_hits') or '').strip()); direct='food-' in (r.get('transfer_modes') or '')
        supported=(not hard) and obj and score>=7.5 and (food or direct or design) and (title or int(float(r.get('source_rows') or 1))>=2)
        x=dict(r);x['audit_status']='supported' if supported else 'manual_review';x['audit_basis']=f'score={score}; title={title}; food={food}; object={obj}; design={design}; direct={direct}; hard={hard}';audit.append(x)
audit_headers=headers+['audit_status','audit_basis']
with (OUT/'B006_E2_stratified_precision_audit.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=audit_headers);w.writeheader();w.writerows(audit)
audit_counts=Counter(r['audit_status'] for r in audit); audit_supported=audit_counts.get('supported',0)/len(audit) if audit else 0
invalid=sum(r.get('invalid_doi')=='yes' for r in rows);missing_title=sum(not (r.get('title') or '').strip() for r in rows);missing_author=sum(not (r.get('first_author') or '').strip() for r in rows);missing_year=sum(not (r.get('year') or '').strip() for r in rows);missing_journal=sum(not (r.get('journal') or '').strip() for r in rows)
small=[f'K{i:02d}' for i in range(1,17) if sum(1 for r in formal if r.get('primary_k_domain')==f'K{i:02d}')<100]
quality={'all_8_shards':len(files)==8,'classified_rows_28399':len(rows)==28399,'formal_AB_min_12000':len(formal)>=12000,'prior_overlap_zero':overlap==0,'duplicate_zero':dup==0,'invalid_doi_max_10':invalid<=10,'all_K_formal_min_100':not small,'audit_supported_share_min_080':audit_supported>=0.80}
status='success' if all(quality.values()) else 'failure'
summary={'stage':'B006-E2','status':status,'classified_rows':len(rows),'formal_AB_download_pool':len(formal),'relevance_counts':dict(rel),'priority_counts':dict(pri),'candidate_tier_counts':dict(tiers),'primary_K_counts':dict(kc),'strategy_counts':dict(strat),'metadata_status_counts':dict(meta),'invalid_doi':invalid,'prior_overlap':overlap,'duplicate_doi':dup,'missing_title_author_year_journal':[missing_title,missing_author,missing_year,missing_journal],'audit_sample_records':len(audit),'audit_status_counts':dict(audit_counts),'audit_supported_share':round(audit_supported,6),'missing_or_small_formal_K_domains':small,'quality_gate':quality,'next_stage':'B006-R01 first high-precision non-overlapping student download round'}
(OUT/'run_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'stage_report.md').write_text('\n'.join(['# B006 E2 Metadata, Relevance and Precision Audit Report','',f'- Status: **{status}**',f'- Classified: {len(rows):,}',f'- Formal A/B pool: {len(formal):,}',f'- Relevance: {dict(rel)}',f'- Priority: {dict(pri)}',f'- K domains: {dict(kc)}',f'- Metadata: {dict(meta)}',f'- Invalid DOI: {invalid}',f'- Prior overlap: {overlap}',f'- Stratified audit: {dict(audit_counts)}; supported share {audit_supported:.2%}',f'- Quality gate: {quality}',f"- Next: {summary['next_stage']}"]),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False),flush=True)
if status!='success':raise SystemExit(2)
