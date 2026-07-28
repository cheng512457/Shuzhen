import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(2**31 - 1)

ROOT = Path('artifacts')
OUT = Path('out')
OUT.mkdir(exist_ok=True)
SOURCES = [
    ('B004+B005+B006+B007', ROOT / 'prior', 266798, None, None, None),
    ('B008-R01', ROOT / 'b008_r01', 18406, 'B008', 1, 18406),
]

def normalize_doi(value):
    value = str(value or '').strip().lower()
    value = re.sub(r'^https?://(dx\.)?doi\.org/', '', value)
    value = re.sub(r'^doi:\s*', '', value)
    return value.rstrip('.,;) ')

def count_rows(path):
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        return max(0, sum(1 for _ in csv.reader(f)) - 1)

def choose_master(root, expected):
    files = list(root.rglob('*.csv'))
    if not files:
        raise RuntimeError(f'No CSV files under {root}')
    def rank(p):
        n = p.name.lower()
        return (1 if 'cumulative' in n or 'master' in n else 0,
                1 if 'final' in n or 'audited' in n or 'frozen' in n else 0,
                p.stat().st_size)
    diagnostics = []
    for path in sorted(files, key=rank, reverse=True):
        n = path.name.lower()
        if any(x in n for x in ['student','registry','overlap','duplicate','matrix']):
            continue
        try:
            rows = count_rows(path)
        except Exception:
            continue
        diagnostics.append((str(path), rows))
        if rows == expected:
            return path
    raise RuntimeError(f'No {expected}-row master under {root}; candidates={diagnostics[:20]}')

def find_field(headers, candidates):
    lowered = {h.lower(): h for h in headers}
    for c in candidates:
        if c.lower() in lowered:
            return lowered[c.lower()]
    for h in headers:
        if any(c.lower() in h.lower() for c in candidates):
            return h
    return None

def load_source(label, root, expected, prefix, start_num, end_num):
    path = choose_master(root, expected)
    rows = []
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        doi_field = find_field(headers, ['doi_normalized','doi'])
        id_field = find_field(headers, ['permanent_id', f'{prefix}_ID' if prefix else 'permanent_id', 'B008_ID','B007_ID','B006_ID','B005_ID','B004_ID'])
        if not doi_field or not id_field:
            raise RuntimeError(f'{label}: DOI/ID fields missing in {headers}')
        rel_field = find_field(headers, ['relevance'])
        for row in reader:
            row['_source'] = label
            row['_doi'] = normalize_doi(row.get(doi_field))
            row['_id'] = (row.get(id_field) or '').strip()
            row['_relevance'] = (row.get(rel_field) or '').strip() if rel_field else ''
            rows.append(row)
    dois = [r['_doi'] for r in rows]
    ids = [r['_id'] for r in rows]
    invalid = [d for d in dois if not re.match(r'^10\.\d{4,9}/\S+$', d)]
    checks = {
        'record_count': len(rows) == expected,
        'unique_doi_count': len(set(dois)) == expected,
        'unique_id_count': len(set(ids)) == expected,
        'valid_doi_syntax': len(invalid) == 0,
        'nonblank_ids': all(ids),
    }
    if prefix:
        pattern = re.compile(rf'^{prefix}-(\d{{6}})$')
        nums = [int(m.group(1)) for x in ids if (m := pattern.match(x))]
        checks.update({
            'id_format': len(nums) == expected,
            'id_range_continuous': set(nums) == set(range(start_num, end_num + 1)),
            'A_B_only': all(r['_relevance'] in {'A','B'} for r in rows),
        })
    else:
        checks['existing_id_format'] = all(re.match(r'^B00[4567]-\d{6}$', x) for x in ids)
    return {
        'label': label, 'path': path, 'rows': rows, 'dois': set(dois), 'ids': set(ids),
        'check': {'label':label,'source_file':str(path),'records':len(rows),'unique_dois':len(set(dois)),'unique_ids':len(set(ids)),'invalid_doi_syntax':len(invalid),'checks':checks},
    }

loaded = [load_source(*x) for x in SOURCES]
pairwise = {}
for i in range(len(loaded)):
    for j in range(i + 1, len(loaded)):
        pairwise[f"{loaded[i]['label']}__{loaded[j]['label']}"] = len(loaded[i]['dois'] & loaded[j]['dois'])

all_rows = [r for item in loaded for r in item['rows']]
all_dois = [r['_doi'] for r in all_rows]
all_ids = [r['_id'] for r in all_rows]
b008_rows = loaded[1]['rows']
b008_dois = [r['_doi'] for r in b008_rows]
b008_ids = [r['_id'] for r in b008_rows]

union_headers = []
seen = set()
for row in all_rows:
    for key in row:
        if key.startswith('_') or key in seen:
            continue
        seen.add(key)
        union_headers.append(key)
headers = ['database_source','permanent_id','doi_normalized'] + union_headers

def write_master(path, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        for row in rows:
            out = {h: row.get(h,'') for h in union_headers}
            out.update({'database_source':row['_source'],'permanent_id':row['_id'],'doi_normalized':row['_doi']})
            w.writerow(out)

cum = OUT / 'B004_B005_B006_B007_B008_285204_cumulative_master.csv'
b008 = OUT / 'B008_18406_frozen_formal_download_master.csv'
write_master(cum, all_rows)
write_master(b008, b008_rows)
reg = OUT / 'B004_B005_B006_B007_B008_285204_unique_doi_registry.csv'
with reg.open('w', encoding='utf-8-sig', newline='') as f:
    w = csv.writer(f)
    w.writerow(['doi_normalized'])
    for doi in sorted(set(all_dois)):
        w.writerow([doi])
mat = OUT / 'B004_B005_B006_B007_B008_pairwise_doi_overlap_matrix.csv'
labels = [x['label'] for x in loaded]
with mat.open('w', encoding='utf-8-sig', newline='') as f:
    w = csv.writer(f)
    w.writerow(['dataset'] + labels)
    for i, item in enumerate(loaded):
        w.writerow([item['label']] + [len(item['dois'] & other['dois']) if i != j else len(item['dois']) for j, other in enumerate(loaded)])

k_counts = Counter((r.get('K_primary') or '').strip() for r in b008_rows)
rel = Counter(r['_relevance'] for r in b008_rows)
pri = Counter((r.get('download_priority') or '').strip() for r in b008_rows)
links = Counter((r.get('link_audit_result') or '').strip() for r in b008_rows)
quality = {
    'total_records_equals_285204': len(all_rows) == 285204,
    'records_equal_unique_dois': len(all_rows) == len(set(all_dois)),
    'records_equal_unique_ids': len(all_rows) == len(set(all_ids)),
    'prior_B008_overlap_zero': len(loaded[0]['dois'] & set(b008_dois)) == 0,
    'B008_ids_continuous_000001_to_018406': set(int(x.split('-')[1]) for x in b008_ids) == set(range(1,18407)),
    'all_source_checks_success': all(all(item['check']['checks'].values()) for item in loaded),
    'B008_A_B_only': set(rel).issubset({'A','B'}),
}
summary = {
    'stage':'B004+B005+B006+B007+B008-final-cumulative-audit',
    'status':'success' if all(quality.values()) else 'failure',
    'total_records':len(all_rows),
    'total_unique_dois':len(set(all_dois)),
    'total_unique_permanent_ids':len(set(all_ids)),
    'prior_records':len(loaded[0]['rows']),
    'B008_records':len(b008_rows),
    'B008_unique_dois':len(set(b008_dois)),
    'prior_B008_overlap':len(loaded[0]['dois'] & set(b008_dois)),
    'all_pairwise_overlaps':pairwise,
    'B008_K_counts':dict(k_counts),
    'B008_relevance_counts':dict(rel),
    'B008_priority_counts':dict(pri),
    'B008_link_audit_counts':dict(links),
    'source_checks':[x['check'] for x in loaded],
    'quality_gate':quality,
    'outputs':{'cumulative_master':str(cum),'doi_registry':str(reg),'overlap_matrix':str(mat),'B008_frozen_master':str(b008)},
    'next':'B009-E1 next high-precision non-overlapping expansion from the frozen 285204-DOI registry',
}
(OUT/'run_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'stage_report.md').write_text('\n'.join([
    '# B004 + B005 + B006 + B007 + B008 Final Cumulative DOI Audit','',
    f"- Status: **{summary['status']}**",
    f"- Total records: {len(all_rows):,}",
    f"- Total unique DOIs: {len(set(all_dois)):,}",
    f"- Prior records: {len(loaded[0]['rows']):,}",
    f"- B008 records: {len(b008_rows):,}",
    f"- Prior vs B008 overlap: {summary['prior_B008_overlap']}",
    f"- B008 relevance: {dict(rel)}",
    f"- B008 priority: {dict(pri)}",
    f"- B008 link audit: {dict(links)}",
    f"- Quality gate: {quality}",
]),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False),flush=True)
if summary['status'] != 'success':
    raise SystemExit(2)
