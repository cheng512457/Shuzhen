import csv
import json
import sys
import zlib
from pathlib import Path

try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(2**31 - 1)

root = Path('prior_artifact')
out = Path('out')
out.mkdir(exist_ok=True)
files = list(root.rglob('B004_S3_1_canonical_candidate_pool.csv'))
if not files:
    raise RuntimeError('Missing S3.1 canonical candidate pool')
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
            raise RuntimeError('Unexpected S3.1 headers')
        for shard in range(shard_count):
            handle = (out / f'B004_S3_2_input_shard{shard}.csv').open('w', encoding='utf-8-sig', newline='')
            handles.append(handle)
            writer = csv.DictWriter(handle, fieldnames=headers)
            writer.writeheader()
            writers.append(writer)
        for idx, row in enumerate(reader, 1):
            doi = (row.get('doi') or '').strip().lower()
            shard = zlib.crc32(doi.encode('utf-8')) % shard_count
            writers[shard].writerow(row)
            counts[shard] += 1
            if idx % 50000 == 0:
                print('SPLIT_PROGRESS', idx, counts, flush=True)
finally:
    for handle in handles:
        handle.close()
summary = {
    'stage': 'S3.2-prepare',
    'source_file': str(source),
    'total_candidate_rows': sum(counts),
    'shard_count': shard_count,
    'shard_counts': {str(i): counts[i] for i in range(shard_count)},
    'headers': headers,
}
(out / 'prepare_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False), flush=True)
if sum(counts) < 350000 or min(counts) < 10000:
    raise SystemExit(2)
