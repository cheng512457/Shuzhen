import csv, json, sys
from collections import Counter
from pathlib import Path

try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(2**31 - 1)

FORMAL = Path('formal_artifact')
PRIOR = Path('prior_artifact')
OUT = Path('out')
OUT.mkdir(exist_ok=True)
EXPECTED = 18406
PRIOR_EXPECTED = 266798
SHARDS = 19


def count_rows(path):
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        return max(0, sum(1 for _ in csv.reader(f)) - 1)


def choose_csv(root, expected, tokens):
    candidates = []
    for path in root.rglob('*.csv'):
        name = path.name.lower()
        if not all(t in name for t in tokens):
            continue
        try:
            n = count_rows(path)
        except Exception:
            continue
        candidates.append((path, n))
        if n == expected:
            return path
    # Fall back to any exact-row CSV, while preferring master/formal/cumulative names.
    ranked = []
    for path in root.rglob('*.csv'):
        name = path.name.lower()
        if any(x in name for x in ['student', 'registry', 'overlap', 'matrix', 'audit_sample']):
            continue
        try:
            n = count_rows(path)
        except Exception:
            continue
        ranked.append((1 if any(x in name for x in ['formal', 'master', 'cumulative', 'verified']) else 0, path.stat().st_size, path, n))
    for _, _, path, n in sorted(ranked, reverse=True):
        if n == expected:
            return path
    raise RuntimeError(f'No {expected}-row CSV under {root}; token candidates={candidates[:20]}')

formal_file = choose_csv(FORMAL, EXPECTED, ['formal', 'pool'])
prior_file = choose_csv(PRIOR, PRIOR_EXPECTED, ['cumulative', 'master'])

prior = set()
with prior_file.open('r', encoding='utf-8-sig', newline='') as f:
    for row in csv.DictReader(f):
        doi = (row.get('doi') or row.get('doi_normalized') or row.get('DOI') or '').strip().lower()
        if doi:
            prior.add(doi)
if len(prior) != PRIOR_EXPECTED:
    raise RuntimeError(f'Unexpected prior DOI count {len(prior)}')

rows = []
overlap = 0
with formal_file.open('r', encoding='utf-8-sig', newline='') as f:
    for row in csv.DictReader(f):
        doi = (row.get('doi') or row.get('doi_normalized') or '').strip().lower()
        relevance = (row.get('relevance') or '').strip()
        eligible = (row.get('download_eligible') or 'yes').strip().lower()
        if not doi or relevance not in {'A', 'B'} or eligible not in {'yes', 'true', '1'}:
            continue
        if doi in prior:
            overlap += 1
            continue
        row['doi'] = doi
        row['K_primary'] = row.get('K_primary') or row.get('primary_k_domain') or 'K00'
        rows.append(row)

if overlap or len(rows) != EXPECTED or len({r['doi'] for r in rows}) != EXPECTED:
    raise RuntimeError(f'Formal pool check failed rows={len(rows)} unique={len({r["doi"] for r in rows})} overlap={overlap}')

priority_order = {'P0': 0, 'P1': 1, 'P2': 2, 'P3': 3}
relevance_order = {'A': 0, 'B': 1}

def num(value):
    try:
        return float(value or 0)
    except Exception:
        return 0.0

rows.sort(key=lambda r: (
    r['K_primary'], priority_order.get(r.get('download_priority'), 9),
    relevance_order.get(r.get('relevance'), 9), -num(r.get('precision_score_max')),
    -num(r.get('cited_by_count')), r.get('title') or ''
))

for i, row in enumerate(rows, 1):
    permanent_id = f'B008-{i:06d}'
    row.update({
        'B008_ID': permanent_id,
        'PDF_filename': permanent_id + '.pdf',
        'DOI_URL': 'https://doi.org/' + row['doi'],
        'download_status': '待下载',
        'download_round': 'B008-R01',
    })

buckets = [[] for _ in range(10)]
cursor = 0
for k in [f'K{i:02d}' for i in range(1, 17)]:
    for row in [x for x in rows if x['K_primary'] == k]:
        minimum = min(map(len, buckets))
        choices = [i for i, bucket in enumerate(buckets) if len(bucket) == minimum]
        pick = choices[cursor % len(choices)]
        cursor += 1
        row['student'] = f'Student{pick + 1:02d}'
        buckets[pick].append(row)

counts = [len(bucket) for bucket in buckets]
if max(counts) - min(counts) > 1 or sum(counts) != EXPECTED:
    raise RuntimeError(f'Student allocation failed {counts}')

base_headers = list(rows[0])
front = ['B008_ID', 'download_round', 'student', 'K_primary', 'K_primary_name', 'G_primary',
         'relevance', 'download_priority', 'title', 'first_author', 'year', 'journal', 'doi',
         'DOI_URL', 'PDF_filename', 'download_status']
headers = list(dict.fromkeys(front + [x for x in base_headers if x not in front] +
                             ['link_http_status', 'link_audit_result', 'link_final_url', 'link_audit_note']))

for shard in range(1, SHARDS + 1):
    part = rows[(shard - 1) * 1000: shard * 1000]
    with (OUT / f'B008_R01_Shard{shard:02d}_pre_audit.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows([{h: row.get(h, '') for h in headers} for row in part])

summary = {
    'stage': 'B008-R01-prepare', 'status': 'success',
    'formal_source': str(formal_file), 'prior_source': str(prior_file),
    'verified_formal_pool': EXPECTED, 'prior_registry': PRIOR_EXPECTED, 'prior_overlap': 0,
    'selected_records': EXPECTED, 'unique_dois': EXPECTED,
    'id_start': 'B008-000001', 'id_end': 'B008-018406',
    'student_counts': {f'Student{i + 1:02d}': len(bucket) for i, bucket in enumerate(buckets)},
    'K_counts': dict(Counter(r['K_primary'] for r in rows)),
    'relevance_counts': dict(Counter(r['relevance'] for r in rows)),
    'priority_counts': dict(Counter(r['download_priority'] for r in rows)),
    'audit_shards': SHARDS,
    'shard_sizes': {str(i): len(rows[(i - 1) * 1000:i * 1000]) for i in range(1, SHARDS + 1)},
}
(OUT / 'B008_R01_prepare_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False), flush=True)
