import csv
import json
import sys
import zlib
from pathlib import Path

try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(2**31 - 1)

ROOT = Path('prior_artifact')
OUT = Path('out')
OUT.mkdir(exist_ok=True)
files = list(ROOT.rglob('B005_E1_new_unique_candidates.csv'))
if not files:
    raise RuntimeError('Missing B005 E1 candidate file')
source = files[0]
shard_count = 16
handles = []
writers = []
counts = [0] * shard_count
headers = []
try:
    with source.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        if 'doi' not in headers or 'title' not in headers:
            raise RuntimeError('Unexpected B005 E1 headers')
        for shard in range(shard_count):
            h = (OUT / f'B005_E2_input_shard{shard}.csv').open('w', encoding='utf-8-sig', newline='')
            handles.append(h)
            w = csv.DictWriter(h, fieldnames=headers)
            w.writeheader()
            writers.append(w)
        for idx, row in enumerate(reader, 1):
            doi = (row.get('doi') or '').strip().lower()
            shard = zlib.crc32(doi.encode('utf-8')) % shard_count
            writers[shard].writerow(row)
            counts[shard] += 1
            if idx % 25000 == 0:
                print('SPLIT_PROGRESS', idx, counts, flush=True)
finally:
    for h in handles:
        h.close()
summary = {
    'stage':'B005-E2-prepare',
    'source_file':str(source),
    'total_candidate_rows':sum(counts),
    'shard_count':shard_count,
    'shard_counts':{str(i):counts[i] for i in range(shard_count)},
    'headers':headers,
}
(OUT/'prepare_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False),flush=True)
if sum(counts) < 130000 or min(counts) < 7000:
    raise SystemExit(2)
