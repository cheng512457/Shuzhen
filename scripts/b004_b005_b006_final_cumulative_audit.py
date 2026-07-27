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
    ('B004+B005', ROOT / 'prior', 226220, None, None, None),
    ('B006-R01', ROOT / 'b006_r01', 20000, 'B006', 1, 20000),
    ('B006-R02', ROOT / 'b006_r02', 803, 'B006', 20001, 20803),
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
        id_field = find_field(headers, ['permanent_id', f'{prefix}_ID' if prefix else 'permanent_id', 'B006_ID','B005_ID','B004_ID'])
        if not doi_field or not id_field:
            raise RuntimeError(f'{label}: DOI/ID fields missing in {headers}')
        relevance_field = find_field(headers, ['relevance'])
        for row in reader:
            row['_source'] = label
            row['_doi'] = normalize_doi(row.get(doi_field))
            row['_id'] = (row.get(id_field) or '').strip()
            row['_relevance'] = (row.get(relevance_field) or '').strip() if relevance_field else ''
            rows.append(row)
    dois = [r['_doi'] for r in rows]
    ids = [r['_id'] for r in rows]
    invalid_dois = [d for d in dois if not re.match(r'^10\.\d{4,9}/\S+$', d)]
    checks = {
        'record_count': len(rows) == expected,
        'unique_doi_count': len(set(dois)) == expected,
        'unique_id_count': len(set(ids)) == expected,
        'valid_doi_syntax': len(invalid_dois) == 0,
        'nonblank_ids': all(ids),
    }
    if prefix:
        pattern = re.compile(rf'^{prefix}-(\d{{6}})$')
        nums = [int(m.group(1)) for x in ids if (m := pattern.match(x))]
        expected_ids = set(range(start_num, end_num + 1))
        checks.update({
            'id_format': len(nums) == expected,
            'id_range_continuous': set(nums) == expected_ids,
            'A_B_only': all(r['_relevance'] in {'A','B'} for r in rows),
        })
    else:
        checks['existing_id_format'] = all(re.match(r'^B00[45]-\d{6}$', x) for x in ids)
    return {
        'label': label, 'path': path, 'rows': rows, 'dois': set(dois), 'ids': set(ids),
        'check': {
            'label': label, 'source_file': str(path), 'records': len(rows),
            'unique_dois': len(set(dois)), 'unique_ids': len(set(ids)),
            'invalid_doi_syntax': len(invalid_dois), 'checks': checks,
        }
    }

loaded = [load_source(*spec) for spec in SOURCES]
pairwise = {}
for i in range(len(loaded)):
    for j in range(i + 1, len(loaded)):
        pairwise[f"{loaded[i]['label']}__{loaded[j]['label']}"] = len(loaded[i]['dois'] & loaded[j]['dois'])

all_rows = [r for item in loaded for r in item['rows']]
all_dois = [r['_doi'] for r in all_rows]
all_ids = [r['_id'] for r in all_rows]
b006_rows = loaded[1]['rows'] + loaded[2]['rows']
b006_dois = [r['_doi'] for r in b006_rows]
b006_ids = [r['_id'] for r in b006_rows]

union_headers = []
seen = set()
for row in all_rows:
    for key in row:
        if key.startswith('_') or key in seen:
            continue
        seen.add(key); union_headers.append(key)
headers = ['database_source','permanent_id','doi_normalized'] + union_headers

def write_master(path, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=headers); w.writeheader()
        for row in rows:
            out = {h: row.get(h,'') for h in union_headers}
            out.update({'database_source':row['_source'],'permanent_id':row['_id'],'doi_normalized':row['_doi']})
            w.writerow(out)

cumulative_path = OUT / 'B004_B005_B006_247023_cumulative_master.csv'
b006_path = OUT / 'B006_20803_frozen_formal_download_master.csv'
write_master(cumulative_path, all_rows)
write_master(b006_path, b006_rows)

registry_path = OUT / 'B004_B005_B006_247023_unique_doi_registry.csv'
with registry_path.open('w', encoding='utf-8-sig', newline='') as f:
    w = csv.writer(f); w.writerow(['doi_normalized'])
    for doi in sorted(set(all_dois)): w.writerow([doi])

matrix_path = OUT / 'B004_B005_B006_pairwise_doi_overlap_matrix.csv'
labels = [x['label'] for x in loaded]
with matrix_path.open('w', encoding='utf-8-sig', newline='') as f:
    w = csv.writer(f); w.writerow(['dataset'] + labels)
    for i, item in enumerate(loaded):
        w.writerow([item['label']] + [len(item['dois'] & other['dois']) if i != j else len(item['dois']) for j, other in enumerate(loaded)])

k_counts = Counter((r.get('K_primary') or '').strip() for r in b006_rows)
rel_counts = Counter(r['_relevance'] for r in b006_rows)
priority_counts = Counter((r.get('download_priority') or '').strip() for r in b006_rows)
link_counts = Counter((r.get('link_audit_result') or '').strip() for r in b006_rows)
quality = {
    'total_records_equals_247023': len(all_rows) == 247023,
    'records_equal_unique_dois': len(all_rows) == len(set(all_dois)),
    'records_equal_unique_ids': len(all_rows) == len(set(all_ids)),
    'prior_B006_overlap_zero': len(loaded[0]['dois'] & set(b006_dois)) == 0,
    'B006_round_overlap_zero': len(loaded[1]['dois'] & loaded[2]['dois']) == 0,
    'B006_ids_continuous_000001_to_020803': set(int(x.split('-')[1]) for x in b006_ids) == set(range(1,20804)),
    'all_source_checks_success': all(all(item['check']['checks'].values()) for item in loaded),
    'B006_A_B_only': set(rel_counts).issubset({'A','B'}),
}
summary = {
    'stage':'B004+B005+B006-final-cumulative-audit',
    'status':'success' if all(quality.values()) else 'failure',
    'total_records':len(all_rows), 'total_unique_dois':len(set(all_dois)),
    'total_unique_permanent_ids':len(set(all_ids)),
    'prior_records':len(loaded[0]['rows']), 'B006_records':len(b006_rows),
    'B006_unique_dois':len(set(b006_dois)), 'prior_B006_overlap':len(loaded[0]['dois'] & set(b006_dois)),
    'B006_R01_R02_overlap':len(loaded[1]['dois'] & loaded[2]['dois']),
    'all_pairwise_overlaps':pairwise, 'B006_K_counts':dict(k_counts),
    'B006_relevance_counts':dict(rel_counts), 'B006_priority_counts':dict(priority_counts),
    'B006_link_audit_counts':dict(link_counts), 'source_checks':[x['check'] for x in loaded],
    'quality_gate':quality,
    'outputs':{'cumulative_master':str(cumulative_path),'doi_registry':str(registry_path),'overlap_matrix':str(matrix_path),'B006_frozen_master':str(b006_path)},
}
(OUT/'run_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
report = [
    '# B004 + B005 + B006 Final Cumulative DOI Audit','',
    f"- Status: **{summary['status']}**", f"- Total records: {len(all_rows):,}",
    f"- Total unique DOIs: {len(set(all_dois)):,}", f"- Total unique permanent IDs: {len(set(all_ids)):,}",
    f"- B004+B005 records: {len(loaded[0]['rows']):,}", f"- B006 records: {len(b006_rows):,}",
    f"- Prior vs B006 overlap: {summary['prior_B006_overlap']}",
    f"- B006 R01 vs R02 overlap: {summary['B006_R01_R02_overlap']}",
    f"- B006 relevance: {dict(rel_counts)}", f"- B006 priority: {dict(priority_counts)}",
    f"- B006 link audit: {dict(link_counts)}", f"- Quality gate: {quality}",
]
(OUT/'stage_report.md').write_text('\n'.join(report),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False),flush=True)
if summary['status'] != 'success': raise SystemExit(2)
