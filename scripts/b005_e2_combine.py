import csv
import json
import sys
from collections import Counter
from pathlib import Path

try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(2**31 - 1)

ROOT = Path('shard_artifacts')
OUT = Path('out')
OUT.mkdir(exist_ok=True)
files = sorted(ROOT.rglob('B005_E2_classified_shard*.csv'))
summary_files = sorted(ROOT.rglob('B005_E2_shard*_summary.json'))
if not files:
    raise RuntimeError('No B005 E2 classified shards')

paths = {
    'all': OUT/'B005_E2_all_classified.csv',
    'formal': OUT/'B005_E2_formal_download_pool.csv',
    'boundary': OUT/'B005_E2_boundary_C_pool.csv',
    'rejected': OUT/'B005_E2_rejected_D_pool.csv',
}
handles = {k:p.open('w',encoding='utf-8-sig',newline='') for k,p in paths.items()}
writers = {}
headers = None
rel = Counter(); kc = Counter(); pc = Counter(); meta = Counter(); evidence = Counter(); strata = Counter()
rows = formal = invalid_doi = missing_title = missing_abstract = 0
try:
    for path in files:
        with path.open('r',encoding='utf-8-sig',newline='') as f:
            reader = csv.DictReader(f)
            if headers is None:
                headers = reader.fieldnames or []
                for key in handles:
                    writers[key] = csv.DictWriter(handles[key],fieldnames=headers)
                    writers[key].writeheader()
            for row in reader:
                writers['all'].writerow(row)
                rows += 1
                r = row.get('relevance') or 'D'
                k = row.get('K_primary') or 'K00'
                p = row.get('download_priority') or 'P3'
                m = row.get('metadata_verification') or ''
                e = row.get('evidence_mode') or ''
                rel[r] += 1; kc[k] += 1; pc[p] += 1; meta[m] += 1; evidence[e] += 1
                for s in (row.get('strata') or '').split(';'):
                    s = s.strip()
                    if s: strata[s] += 1
                invalid_doi += row.get('doi_syntax_valid') != 'yes'
                missing_title += not bool((row.get('title') or '').strip())
                missing_abstract += not bool((row.get('abstract') or '').strip())
                if row.get('download_eligible') == 'yes':
                    writers['formal'].writerow(row); formal += 1
                elif r == 'C':
                    writers['boundary'].writerow(row)
                else:
                    writers['rejected'].writerow(row)
                if rows % 25000 == 0:
                    print('COMBINE_PROGRESS',rows,formal,dict(rel),flush=True)
finally:
    for h in handles.values():
        h.close()

small = [f'K{i:02d}' for i in range(1,17) if kc.get(f'K{i:02d}',0) < 100]
status = 'success'
if len(files) < 16 or rows < 130000 or formal < 30000 or invalid_doi > max(20,int(rows*0.001)) or small:
    status = 'failure'
summary = {
    'stage':'B005-E2-metadata-relevance-classification',
    'status':status,
    'shard_csv_files_found':len(files),
    'shard_summary_files_found':len(summary_files),
    'classified_rows':rows,
    'formal_download_pool':formal,
    'relevance_counts':dict(rel),
    'K_primary_counts':dict(kc),
    'priority_counts':dict(pc),
    'metadata_counts':dict(meta),
    'evidence_mode_counts':dict(evidence),
    'stratum_counts':dict(strata),
    'invalid_doi':invalid_doi,
    'missing_title':missing_title,
    'missing_abstract':missing_abstract,
    'missing_or_small_K_domains':small,
    'quality_gate':{
        'classified_rows_min':130000,
        'formal_download_pool_min':30000,
        'invalid_doi_max':max(20,int(rows*0.001)),
        'each_K_primary_min':100,
        'all_shards':16,
        'B004_overlap_expected':0,
    },
    'next_stage':'B005-R01 first non-overlapping student download round and DOI-link audit'
}
(OUT/'run_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'stage_report.md').write_text('\n'.join([
    '# B005 E2 Metadata and Relevance Classification','',
    f'- Status: **{status}**',
    f'- Classified rows: {rows:,}',
    f'- Formal A/B download pool: {formal:,}',
    f'- Relevance counts: {dict(rel)}',
    f'- Priority counts: {dict(pc)}',
    f'- K01-K16 counts: {dict(kc)}',
    f'- Metadata verification: {dict(meta)}',
    f'- Invalid DOI syntax: {invalid_doi:,}',
    f'- Missing abstracts: {missing_abstract:,}',
    f"- Next: {summary['next_stage']}",
]),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False),flush=True)
if status != 'success':
    raise SystemExit(2)
