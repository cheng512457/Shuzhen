import csv, json, sys, zlib
from pathlib import Path
try: csv.field_size_limit(sys.maxsize)
except OverflowError: csv.field_size_limit(2**31-1)
SRC=Path('e1_artifact'); PRIOR=Path('prior_artifact'); OUT=Path('out'); OUT.mkdir(exist_ok=True)
files=list(SRC.rglob('B006_E1_V2_new_high_precision_candidates.csv'))
if len(files)!=1: raise RuntimeError(f'Expected one E1 candidate file, found {len(files)}')
source=files[0]
prior_files=list(PRIOR.rglob('B004_B005_226220_cumulative_master.csv'))
if len(prior_files)!=1: raise RuntimeError(f'Expected cumulative B004+B005 master, found {len(prior_files)}')
excluded=set()
with prior_files[0].open('r',encoding='utf-8-sig',newline='') as f:
    for r in csv.DictReader(f):
        d=(r.get('doi') or r.get('DOI') or '').strip().lower()
        if d: excluded.add(d)
if len(excluded)!=226220: raise RuntimeError(f'Unexpected prior DOI registry size {len(excluded)}')
(OUT/'B004_B005_226220_excluded_dois.txt').write_text('\n'.join(sorted(excluded)),encoding='utf-8')
shards=8; handles=[]; writers=[]; counts=[0]*shards; headers=[]; overlap=0; rows=0
try:
    with source.open('r',encoding='utf-8-sig',newline='') as f:
        rd=csv.DictReader(f); headers=rd.fieldnames or []
        if 'doi' not in headers or 'title' not in headers: raise RuntimeError('Unexpected E1 headers')
        for i in range(shards):
            h=(OUT/f'B006_E2_input_shard{i}.csv').open('w',encoding='utf-8-sig',newline='');handles.append(h)
            w=csv.DictWriter(h,fieldnames=headers);w.writeheader();writers.append(w)
        for r in rd:
            doi=(r.get('doi') or '').strip().lower(); rows+=1
            if doi in excluded: overlap+=1; continue
            s=zlib.crc32(doi.encode())%shards;writers[s].writerow(r);counts[s]+=1
finally:
    for h in handles:h.close()
summary={'stage':'B006-E2-prepare','source_rows':rows,'prior_registry_dois':len(excluded),'overlap_with_prior':overlap,'shard_count':shards,'shard_counts':{str(i):counts[i] for i in range(shards)},'headers':headers}
(OUT/'prepare_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False),flush=True)
if rows!=28399 or overlap!=0 or min(counts)<3000: raise SystemExit(2)
