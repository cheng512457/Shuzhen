import csv
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(2**31 - 1)

FORMAL_ROOT = Path('formal_artifact')
PRIOR_ROOT = Path('prior_artifact')
OUT = Path('out')
OUT.mkdir(exist_ok=True)
BATCH_SIZE = 20000
STUDENTS = 10
SHARD_SIZE = 1000

formal_files = list(FORMAL_ROOT.rglob('B006_E2_V2_formal_AB_download_pool.csv'))
prior_files = list(PRIOR_ROOT.rglob('B004_B005_226220_cumulative_master.csv'))
if len(formal_files) != 1:
    raise RuntimeError(f'Expected one B006 verified formal pool, found {len(formal_files)}')
if len(prior_files) != 1:
    raise RuntimeError(f'Expected one B004+B005 cumulative master, found {len(prior_files)}')

prior = set()
with prior_files[0].open('r', encoding='utf-8-sig', newline='') as f:
    for row in csv.DictReader(f):
        doi = (row.get('doi') or row.get('DOI') or '').strip().lower()
        if doi:
            prior.add(doi)
if len(prior) != 226220:
    raise RuntimeError(f'Unexpected prior DOI registry size: {len(prior)}')

priority_rank = {'P0': 0, 'P1': 1, 'P2': 2, 'P3': 3}
relevance_rank = {'A': 0, 'B': 1, 'C': 2, 'D': 3}

def num(value):
    try:
        return float(value or 0)
    except Exception:
        return 0.0

def record_key(row):
    return (
        priority_rank.get(row.get('download_priority'), 9),
        relevance_rank.get(row.get('relevance'), 9),
        -num(row.get('precision_score_max')),
        -num(row.get('classification_confidence')),
        -num(row.get('cited_by_count')),
        -int(bool((row.get('abstract') or '').strip())),
        row.get('title') or '',
    )

by_k = defaultdict(list)
formal_rows = []
overlap = 0
with formal_files[0].open('r', encoding='utf-8-sig', newline='') as f:
    for row in csv.DictReader(f):
        doi = (row.get('doi') or '').strip().lower()
        if not doi or row.get('download_eligible') != 'yes' or row.get('relevance') not in {'A', 'B'}:
            continue
        if doi in prior:
            overlap += 1
            continue
        row['doi'] = doi
        k = row.get('K_primary') or row.get('primary_k_domain') or 'K00'
        row['K_primary'] = k
        formal_rows.append(row)
        by_k[k].append(row)
if overlap:
    raise RuntimeError(f'B006 formal pool overlaps prior database by {overlap}')
if len(formal_rows) != 20803:
    raise RuntimeError(f'Unexpected verified formal pool size: {len(formal_rows)}')
if len({r["doi"] for r in formal_rows}) != len(formal_rows):
    raise RuntimeError('Duplicate DOI in verified formal pool')

# Proportional K-domain allocation with largest-remainder correction. Because the
# first round includes 20,000 of 20,803 records, this preserves nearly the full
# verified domain structure while prioritising P0/P1 and A records within each K.
counts = {k: len(v) for k, v in by_k.items()}
raw = {k: counts[k] * BATCH_SIZE / len(formal_rows) for k in counts}
quotas = {k: int(math.floor(raw[k])) for k in counts}
remaining = BATCH_SIZE - sum(quotas.values())
for k in sorted(counts, key=lambda x: (raw[x] - quotas[x], counts[x]), reverse=True)[:remaining]:
    quotas[k] += 1

selected = []
for k in sorted(by_k):
    selected.extend(sorted(by_k[k], key=record_key)[:quotas.get(k, 0)])
if len(selected) != BATCH_SIZE:
    used = {r['doi'] for r in selected}
    refill = sorted((r for r in formal_rows if r['doi'] not in used), key=record_key)
    selected.extend(refill[:BATCH_SIZE - len(selected)])
if len(selected) != BATCH_SIZE or len({r['doi'] for r in selected}) != BATCH_SIZE:
    raise RuntimeError('Selection count or DOI uniqueness failure')
if any(r['doi'] in prior for r in selected):
    raise RuntimeError('Prior-database overlap after selection')

selected.sort(key=lambda r: (r.get('K_primary') or 'K99', record_key(r)))
for index, row in enumerate(selected, 1):
    bid = f'B006-{index:06d}'
    row['B006_ID'] = bid
    row['PDF_filename'] = bid + '.pdf'
    row['DOI_URL'] = 'https://doi.org/' + row['doi']
    row['download_status'] = '待下载'
    row['download_round'] = 'B006-R01'

buckets = [[] for _ in range(STUDENTS)]
cursor = 0
for k in [f'K{i:02d}' for i in range(1, 17)]:
    for row in [x for x in selected if x.get('K_primary') == k]:
        minimum = min(map(len, buckets))
        choices = [i for i, bucket in enumerate(buckets) if len(bucket) == minimum]
        pick = choices[cursor % len(choices)]
        cursor += 1
        row['student'] = f'Student{pick + 1:02d}'
        buckets[pick].append(row)
if [len(bucket) for bucket in buckets] != [2000] * 10:
    raise RuntimeError(f'Student allocation mismatch: {[len(b) for b in buckets]}')

base_headers = list(selected[0].keys())
front = ['B006_ID', 'download_round', 'student', 'K_primary', 'K_primary_name', 'G_primary', 'relevance', 'download_priority', 'title', 'first_author', 'year', 'journal', 'doi', 'DOI_URL', 'PDF_filename', 'download_status']
headers = list(dict.fromkeys(front + [h for h in base_headers if h not in front] + ['link_http_status', 'link_audit_result', 'link_final_url', 'link_audit_note']))
for shard in range(1, 21):
    part = selected[(shard - 1) * SHARD_SIZE: shard * SHARD_SIZE]
    with (OUT / f'B006_R01_Shard{shard:02d}_{SHARD_SIZE}_pre_audit.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows([{h: row.get(h, '') for h in headers} for row in part])

summary = {
    'stage': 'B006-R01-prepare',
    'status': 'success',
    'verified_formal_pool': len(formal_rows),
    'prior_registry': len(prior),
    'prior_overlap': 0,
    'selected_records': len(selected),
    'unique_dois': len({r['doi'] for r in selected}),
    'id_start': 'B006-000001',
    'id_end': 'B006-020000',
    'proportional_K_quotas': quotas,
    'actual_K_counts': dict(Counter(r.get('K_primary') for r in selected)),
    'relevance_counts': dict(Counter(r.get('relevance') for r in selected)),
    'priority_counts': dict(Counter(r.get('download_priority') for r in selected)),
    'student_counts': {f'Student{i + 1:02d}': len(bucket) for i, bucket in enumerate(buckets)},
    'remaining_verified_AB_after_R01': len(formal_rows) - len(selected),
    'audit_shards': 20,
}
(OUT / 'B006_R01_prepare_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False), flush=True)
