import csv, json, sys
from collections import Counter
from pathlib import Path
try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(2**31-1)
root=Path('shard_artifacts'); out=Path('out'); out.mkdir(exist_ok=True)
files=sorted(root.rglob('B004_S3_2_classified_shard*.csv'))
summary_files=sorted(root.rglob('B004_S3_2_shard*_summary.json'))
if not files:
    raise RuntimeError('No S3.2 classified shards')
paths={
 'all':out/'B004_S3_2_all_classified.csv',
 'formal':out/'B004_S3_2_formal_download_pool.csv',
 'boundary':out/'B004_S3_2_boundary_C_pool.csv',
 'not_selected':out/'B004_S3_2_not_selected_pool.csv'}
handles={k:p.open('w',encoding='utf-8-sig',newline='') for k,p in paths.items()}
writers={}; headers=None
rel=Counter(); kc=Counter(); pc=Counter(); ec=Counter(); sc=Counter()
rows=formal=missing_title=missing_abstract=0
try:
    for path in files:
        with path.open('r',encoding='utf-8-sig',newline='') as f:
            reader=csv.DictReader(f)
            if headers is None:
                headers=reader.fieldnames or []
                for key in handles:
                    writers[key]=csv.DictWriter(handles[key],fieldnames=headers); writers[key].writeheader()
            for row in reader:
                writers['all'].writerow(row); rows+=1
                r=row.get('relevance') or 'D'; k=row.get('K_primary') or 'K00'; p=row.get('download_priority') or 'P3'; e=row.get('download_eligible') or 'no'
                rel[r]+=1; kc[k]+=1; pc[p]+=1; ec[e]+=1; sc[row.get('source_stages') or '']+=1
                missing_title += not bool((row.get('title') or '').strip())
                missing_abstract += not bool((row.get('abstract') or '').strip())
                if e=='yes': writers['formal'].writerow(row); formal+=1
                elif r=='C': writers['boundary'].writerow(row)
                else: writers['not_selected'].writerow(row)
                if rows%50000==0: print('COMBINE_PROGRESS',rows,formal,dict(rel),flush=True)
finally:
    for h in handles.values(): h.close()
ab=rel.get('A',0)+rel.get('B',0)
ab_share=ab/formal if formal else 0.0
small=[f'K{i:02d}' for i in range(1,17) if kc.get(f'K{i:02d}',0)<500]
status='success'
if len(files)<16 or rows<400000 or formal<100000 or ab_share<0.80 or small: status='failure'
summary={
 'stage':'S3.2','status':status,'shard_csv_files_found':len(files),'shard_summary_files_found':len(summary_files),
 'classified_rows':rows,'formal_download_pool':formal,'relevance_counts':dict(rel),'K_primary_counts':dict(kc),
 'priority_counts':dict(pc),'download_eligible_counts':dict(ec),'A_B_share_of_formal_pool':round(ab_share,6),
 'missing_or_small_K_domains':small,'missing_title':missing_title,'missing_abstract':missing_abstract,
 'source_stage_counts':dict(sc),'success_gate':{'classified_rows_min':400000,'formal_download_pool_min':100000,'A_B_share_min':0.80,'each_K_min':500,'all_shards':16},
 'next_stage':'S4.1 first 10000-record student download round and DOI-link audit'}
(out/'run_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
(out/'stage_report.md').write_text('\n'.join(['# B004 Stage S3.2 Report','',f'- Status: **{status}**',f'- Classified rows: {rows:,}',f'- Formal download pool: {formal:,}',f'- Relevance counts: {dict(rel)}',f'- Priority counts: {dict(pc)}',f'- K counts: {dict(kc)}',f'- A+B share: {ab_share:.2%}',f'- Missing abstracts: {missing_abstract:,}',f"- Next: {summary['next_stage']}"]),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False),flush=True)
if status!='success': raise SystemExit(2)
