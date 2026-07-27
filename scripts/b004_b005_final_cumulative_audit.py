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
    ('B004', ROOT / 'b004', 157917, 'B004', 1, 157917),
    ('B005-R01', ROOT / 'b005_r01', 30000, 'B005', 1, 30000),
    ('B005-R02', ROOT / 'b005_r02', 30000, 'B005', 30001, 60000),
    ('B005-R03', ROOT / 'b005_r03', 8303, 'B005', 60001, 68303),
]


def count_rows(path):
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        return sum(1 for _ in csv.reader(f)) - 1


def choose_master(root, expected):
    files = list(root.rglob('*.csv'))
    if not files:
        raise RuntimeError(f'No CSV files found under {root}')
    def rank(p):
        name = p.name.lower()
        return (
            1 if 'master' in name or 'cumulative' in name else 0,
            1 if 'audited' in name or 'final' in name else 0,
            p.stat().st_size,
        )
    for path in sorted(files, key=rank, reverse=True):
        name = path.name.lower()
        if 'student' in name or 'registry' in name or 'overlap' in name or 'duplicate' in name:
            continue
        try:
            n = count_rows(path)
        except Exception:
            continue
        if n == expected:
            return path
    diagnostics = []
    for path in sorted(files, key=lambda p: p.stat().st_size, reverse=True)[:20]:
        try:
            diagnostics.append((str(path), count_rows(path), path.stat().st_size))
        except Exception:
            diagnostics.append((str(path), 'error', path.stat().st_size))
    raise RuntimeError(f'No {expected}-row master CSV found under {root}; candidates={diagnostics}')


def normalize_doi(value):
    value = str(value or '').strip().lower()
    value = re.sub(r'^https?://(dx\.)?doi\.org/', '', value)
    value = re.sub(r'^doi:\s*', '', value)
    return value.rstrip('.,;) ')


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
        doi_field = find_field(headers, ['doi'])
        id_field = find_field(headers, [f'{prefix}_ID', 'B004_ID', 'B005_ID'])
        if not doi_field or not id_field:
            raise RuntimeError(f'{label}: missing DOI/ID fields in {headers}')
        for row in reader:
            row['_database_source'] = label
            row['_doi_normalized'] = normalize_doi(row.get(doi_field))
            row['_permanent_id'] = (row.get(id_field) or '').strip()
            rows.append(row)
    dois = [r['_doi_normalized'] for r in rows]
    ids = [r['_permanent_id'] for r in rows]
    invalid_dois = [d for d in dois if not re.match(r'^10\.\d{4,9}/\S+$', d)]
    id_numbers = []
    bad_ids = []
    pattern = re.compile(rf'^{prefix}-(\d{{6}})$')
    for value in ids:
        m = pattern.match(value)
        if m:
            id_numbers.append(int(m.group(1)))
        else:
            bad_ids.append(value)
    expected_ids = set(range(start_num, end_num + 1))
    actual_ids = set(id_numbers)
    check = {
        'label': label,
        'source_file': str(path),
        'records': len(rows),
        'unique_dois': len(set(dois)),
        'unique_ids': len(set(ids)),
        'invalid_doi_syntax': len(invalid_dois),
        'blank_dois': sum(not d for d in dois),
        'bad_id_format': len(bad_ids),
        'id_min': min(id_numbers) if id_numbers else None,
        'id_max': max(id_numbers) if id_numbers else None,
        'id_missing_count': len(expected_ids - actual_ids),
        'id_extra_count': len(actual_ids - expected_ids),
        'expected_records': expected,
        'checks': {
            'record_count': len(rows) == expected,
            'unique_doi_count': len(set(dois)) == expected,
            'unique_id_count': len(set(ids)) == expected,
            'valid_doi_syntax': len(invalid_dois) == 0,
            'id_format': len(bad_ids) == 0,
            'id_range_continuous': actual_ids == expected_ids,
        },
    }
    return path, rows, set(dois), set(ids), check

loaded = []
for spec in SOURCES:
    loaded.append(load_source(*spec))

pairwise = {}
max_overlap = 0
for i in range(len(loaded)):
    for j in range(i + 1, len(loaded)):
        left = SOURCES[i][0]
        right = SOURCES[j][0]
        overlap = loaded[i][2] & loaded[j][2]
        pairwise[f'{left}__{right}'] = len(overlap)
        max_overlap = max(max_overlap, len(overlap))

all_rows = [row for item in loaded for row in item[1]]
all_dois = [row['_doi_normalized'] for row in all_rows]
all_ids = [row['_permanent_id'] for row in all_rows]

# Build a union-field cumulative master. Internal helper columns become explicit audit fields.
union_headers = []
seen_headers = set()
for row in all_rows:
    for key in row.keys():
        if key not in seen_headers and key not in {'_doi_normalized', '_permanent_id', '_database_source'}:
            seen_headers.add(key)
            union_headers.append(key)
final_headers = ['database_source', 'permanent_id', 'doi_normalized'] + union_headers
master_path = OUT / 'B004_B005_226220_cumulative_master.csv'
with master_path.open('w', encoding='utf-8-sig', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=final_headers)
    writer.writeheader()
    for row in all_rows:
        out = {h: row.get(h, '') for h in union_headers}
        out.update({
            'database_source': row['_database_source'],
            'permanent_id': row['_permanent_id'],
            'doi_normalized': row['_doi_normalized'],
        })
        writer.writerow(out)

registry_path = OUT / 'B004_B005_226220_unique_doi_registry.csv'
with registry_path.open('w', encoding='utf-8-sig', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['doi_normalized'])
    for doi in sorted(set(all_dois)):
        writer.writerow([doi])

matrix_path = OUT / 'B004_B005_pairwise_doi_overlap_matrix.csv'
labels = [x[0] for x in SOURCES]
sets = [x[2] for x in loaded]
with matrix_path.open('w', encoding='utf-8-sig', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['dataset'] + labels)
    for i, label in enumerate(labels):
        writer.writerow([label] + [len(sets[i] & sets[j]) if i != j else len(sets[i]) for j in range(len(labels))])

# B005-only frozen master and registry.
b005_rows = loaded[1][1] + loaded[2][1] + loaded[3][1]
b005_dois = [r['_doi_normalized'] for r in b005_rows]
b005_ids = [r['_permanent_id'] for r in b005_rows]
b005_master_path = OUT / 'B005_68303_frozen_formal_download_master.csv'
with b005_master_path.open('w', encoding='utf-8-sig', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=final_headers)
    writer.writeheader()
    for row in b005_rows:
        out = {h: row.get(h, '') for h in union_headers}
        out.update({'database_source': row['_database_source'], 'permanent_id': row['_permanent_id'], 'doi_normalized': row['_doi_normalized']})
        writer.writerow(out)

summary = {
    'stage': 'B004+B005-final-cumulative-audit',
    'status': 'success',
    'total_records': len(all_rows),
    'total_unique_dois': len(set(all_dois)),
    'total_unique_permanent_ids': len(set(all_ids)),
    'B004_records': len(loaded[0][1]),
    'B005_records': len(b005_rows),
    'B005_unique_dois': len(set(b005_dois)),
    'B005_unique_ids': len(set(b005_ids)),
    'B004_B005_overlap': len(loaded[0][2] & set(b005_dois)),
    'B005_round_pairwise_overlap': {
        'R01_R02': len(loaded[1][2] & loaded[2][2]),
        'R01_R03': len(loaded[1][2] & loaded[3][2]),
        'R02_R03': len(loaded[2][2] & loaded[3][2]),
    },
    'all_pairwise_overlaps': pairwise,
    'max_pairwise_overlap': max_overlap,
    'source_checks': [item[4] for item in loaded],
    'quality_gate': {
        'total_records_equals_226220': len(all_rows) == 226220,
        'records_equal_unique_dois': len(all_rows) == len(set(all_dois)),
        'records_equal_unique_ids': len(all_rows) == len(set(all_ids)),
        'B004_B005_overlap_zero': len(loaded[0][2] & set(b005_dois)) == 0,
        'B005_round_overlaps_zero': all(v == 0 for v in [len(loaded[1][2] & loaded[2][2]), len(loaded[1][2] & loaded[3][2]), len(loaded[2][2] & loaded[3][2])]),
        'all_source_checks_success': all(all(c['checks'].values()) for c in [item[4] for item in loaded]),
        'B005_ids_continuous_000001_to_068303': set(int(x.split('-')[1]) for x in b005_ids) == set(range(1, 68304)),
    },
    'outputs': {
        'cumulative_master': str(master_path),
        'doi_registry': str(registry_path),
        'overlap_matrix': str(matrix_path),
        'B005_frozen_master': str(b005_master_path),
    },
}
if not all(summary['quality_gate'].values()):
    summary['status'] = 'failure'

(OUT / 'run_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
report = [
    '# B004 + B005 Final Cumulative DOI Audit', '',
    f"- Status: **{summary['status']}**",
    f"- Total records: {summary['total_records']:,}",
    f"- Total unique DOIs: {summary['total_unique_dois']:,}",
    f"- Total unique permanent IDs: {summary['total_unique_permanent_ids']:,}",
    f"- B004 records: {summary['B004_records']:,}",
    f"- B005 records: {summary['B005_records']:,}",
    f"- B004 vs B005 DOI overlap: {summary['B004_B005_overlap']}",
    f"- B005 round overlaps: {summary['B005_round_pairwise_overlap']}",
    f"- Maximum pairwise overlap: {summary['max_pairwise_overlap']}",
    f"- Quality gate: {summary['quality_gate']}",
]
(OUT / 'stage_report.md').write_text('\n'.join(report), encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False), flush=True)
if summary['status'] != 'success':
    raise SystemExit(2)
