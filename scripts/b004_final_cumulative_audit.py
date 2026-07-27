import csv
import json
import re
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path

try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(2**31 - 1)

ROOT = Path('round_artifacts')
OUT = Path('out')
OUT.mkdir(exist_ok=True)

EXPECTED = {
    'R01': {'records':10000, 'id_start':'B004-000001', 'id_end':'B004-010000'},
    'R02': {'records':30000, 'id_start':'B004-010001', 'id_end':'B004-040000'},
    'R03': {'records':30000, 'id_start':'B004-040001', 'id_end':'B004-070000'},
    'R04': {'records':30000, 'id_start':'B004-070001', 'id_end':'B004-100000'},
    'R05': {'records':30000, 'id_start':'B004-100001', 'id_end':'B004-130000'},
    'R06': {'records':27917, 'id_start':'B004-130001', 'id_end':'B004-157917'},
}

def id_num(value):
    m = re.fullmatch(r'B004-(\d{6})', str(value or '').strip())
    return int(m.group(1)) if m else -1

def find_master(round_code):
    matches = []
    for path in ROOT.rglob('*master_audited.csv'):
        name = path.name.upper()
        if f'_{round_code}_' in name:
            matches.append(path)
    if len(matches) != 1:
        raise RuntimeError(f'{round_code}: expected one master file, found {len(matches)}: {matches}')
    return matches[0]

round_rows = {}
round_dois = {}
round_ids = {}
round_headers = {}
round_checks = {}
all_headers = []

for round_code, expected in EXPECTED.items():
    path = find_master(round_code)
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        rows = list(reader)
    for h in headers:
        if h not in all_headers:
            all_headers.append(h)
    dois = [(r.get('doi') or '').strip().lower() for r in rows]
    ids = [(r.get('B004_ID') or '').strip() for r in rows]
    doi_set = {x for x in dois if x}
    id_set = {x for x in ids if x}
    sorted_ids = sorted(ids, key=id_num)
    expected_nums = list(range(id_num(expected['id_start']), id_num(expected['id_end']) + 1))
    actual_nums = [id_num(x) for x in sorted_ids]
    check = {
        'master_file': str(path),
        'records': len(rows),
        'unique_dois': len(doi_set),
        'unique_ids': len(id_set),
        'blank_dois': sum(not x for x in dois),
        'blank_ids': sum(not x for x in ids),
        'id_start': sorted_ids[0] if sorted_ids else '',
        'id_end': sorted_ids[-1] if sorted_ids else '',
        'id_continuous': actual_nums == expected_nums,
        'records_ok': len(rows) == expected['records'],
        'unique_dois_ok': len(doi_set) == expected['records'],
        'unique_ids_ok': len(id_set) == expected['records'],
        'id_range_ok': bool(sorted_ids) and sorted_ids[0] == expected['id_start'] and sorted_ids[-1] == expected['id_end'],
        'titles_blank': sum(not (r.get('title') or '').strip() for r in rows),
        'links_blank': sum(not ((r.get('DOI_URL') or r.get('article_link') or '').strip()) for r in rows),
        'relevance_counts': dict(Counter((r.get('relevance') or '').strip() for r in rows)),
        'priority_counts': dict(Counter((r.get('download_priority') or '').strip() for r in rows)),
        'K_counts': dict(Counter((r.get('K_primary') or '').strip() for r in rows)),
        'link_audit_counts': dict(Counter((r.get('link_audit_result') or '').strip() for r in rows)),
    }
    check['status'] = 'success' if all([
        check['records_ok'], check['unique_dois_ok'], check['unique_ids_ok'],
        check['id_range_ok'], check['id_continuous'], check['blank_dois'] == 0,
        check['blank_ids'] == 0, check['titles_blank'] == 0,
    ]) else 'failure'
    round_rows[round_code] = rows
    round_dois[round_code] = doi_set
    round_ids[round_code] = id_set
    round_headers[round_code] = headers
    round_checks[round_code] = check

pairwise = {}
overlap_rows = []
for left, right in combinations(EXPECTED, 2):
    inter = sorted(round_dois[left] & round_dois[right])
    pairwise[f'{left}_vs_{right}'] = len(inter)
    overlap_rows.append({'round_left':left, 'round_right':right, 'overlap_dois':len(inter), 'sample_dois':'; '.join(inter[:20])})

all_rows = []
for round_code in EXPECTED:
    for row in round_rows[round_code]:
        out = dict(row)
        out['cumulative_round'] = round_code
        all_rows.append(out)
all_rows.sort(key=lambda r: id_num(r.get('B004_ID')))
all_dois = [(r.get('doi') or '').strip().lower() for r in all_rows]
all_ids = [(r.get('B004_ID') or '').strip() for r in all_rows]
unique_dois = len(set(all_dois))
unique_ids = len(set(all_ids))
expected_total = sum(x['records'] for x in EXPECTED.values())
expected_id_nums = list(range(1, expected_total + 1))
actual_id_nums = [id_num(x) for x in all_ids]

cumulative_headers = ['cumulative_round'] + [h for h in all_headers if h != 'cumulative_round']
with (OUT / 'B004_R01_R06_cumulative_master_157917.csv').open('w', encoding='utf-8-sig', newline='') as f:
    w = csv.DictWriter(f, fieldnames=cumulative_headers, extrasaction='ignore')
    w.writeheader(); w.writerows([{h:r.get(h,'') for h in cumulative_headers} for r in all_rows])

with (OUT / 'B004_R01_R06_unique_doi_registry.csv').open('w', encoding='utf-8-sig', newline='') as f:
    headers = ['B004_ID','round','doi','title','first_author','year','journal','K_primary','G_primary','relevance','download_priority','PDF_filename','DOI_URL','link_audit_result']
    w = csv.DictWriter(f, fieldnames=headers)
    w.writeheader()
    for r in all_rows:
        w.writerow({
            'B004_ID':r.get('B004_ID',''),'round':r.get('cumulative_round',''),'doi':(r.get('doi') or '').lower(),
            'title':r.get('title',''),'first_author':r.get('first_author',''),'year':r.get('year',''),'journal':r.get('journal',''),
            'K_primary':r.get('K_primary',''),'G_primary':r.get('G_primary',''),'relevance':r.get('relevance',''),
            'download_priority':r.get('download_priority',''),'PDF_filename':r.get('PDF_filename',''),
            'DOI_URL':r.get('DOI_URL',''),'link_audit_result':r.get('link_audit_result',''),
        })

with (OUT / 'B004_R01_R06_pairwise_overlap_matrix.csv').open('w', encoding='utf-8-sig', newline='') as f:
    rounds = list(EXPECTED)
    w = csv.writer(f)
    w.writerow(['round'] + rounds)
    for left in rounds:
        row = [left]
        for right in rounds:
            row.append(len(round_dois[left]) if left == right else len(round_dois[left] & round_dois[right]))
        w.writerow(row)

with (OUT / 'B004_R01_R06_pairwise_overlap_details.csv').open('w', encoding='utf-8-sig', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['round_left','round_right','overlap_dois','sample_dois'])
    w.writeheader(); w.writerows(overlap_rows)

summary = {
    'project':'B004 formal A/B download pool',
    'status':'success',
    'rounds':round_checks,
    'expected_total_records':expected_total,
    'total_records':len(all_rows),
    'total_unique_dois':unique_dois,
    'total_unique_ids':unique_ids,
    'id_start':all_ids[0] if all_ids else '',
    'id_end':all_ids[-1] if all_ids else '',
    'global_id_continuous':actual_id_nums == expected_id_nums,
    'pairwise_doi_overlaps':pairwise,
    'maximum_pairwise_overlap':max(pairwise.values()) if pairwise else 0,
    'blank_dois':sum(not x for x in all_dois),
    'blank_ids':sum(not x for x in all_ids),
    'blank_titles':sum(not (r.get('title') or '').strip() for r in all_rows),
    'relevance_counts':dict(Counter((r.get('relevance') or '').strip() for r in all_rows)),
    'priority_counts':dict(Counter((r.get('download_priority') or '').strip() for r in all_rows)),
    'K_counts':dict(Counter((r.get('K_primary') or '').strip() for r in all_rows)),
    'link_audit_counts':dict(Counter((r.get('link_audit_result') or '').strip() for r in all_rows)),
    'quality_gate':{
        'total_records_equals_157917':len(all_rows) == 157917,
        'total_records_equals_unique_dois':len(all_rows) == unique_dois,
        'total_records_equals_unique_ids':len(all_rows) == unique_ids,
        'all_pairwise_overlaps_zero':all(v == 0 for v in pairwise.values()),
        'ids_continuous_B004_000001_to_157917':actual_id_nums == expected_id_nums,
        'all_round_checks_success':all(x['status'] == 'success' for x in round_checks.values()),
        'A_B_only':set((r.get('relevance') or '').strip() for r in all_rows) <= {'A','B'},
    },
}
if not all(summary['quality_gate'].values()):
    summary['status'] = 'failure'

(OUT / 'B004_R01_R06_final_cumulative_audit.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
report = [
    '# B004 R01-R06 Final Cumulative DOI Audit','',
    f"- Status: **{summary['status']}**",
    f"- Total records: {summary['total_records']:,}",
    f"- Total unique DOIs: {summary['total_unique_dois']:,}",
    f"- Total unique B004 IDs: {summary['total_unique_ids']:,}",
    f"- Permanent ID range: {summary['id_start']} to {summary['id_end']}",
    f"- Maximum pairwise DOI overlap: {summary['maximum_pairwise_overlap']}",
    f"- Relevance counts: {summary['relevance_counts']}",
    f"- Priority counts: {summary['priority_counts']}",
    f"- K01-K16 counts: {summary['K_counts']}",
    f"- Link audit counts: {summary['link_audit_counts']}",
    f"- Quality gate: {summary['quality_gate']}",
]
(OUT / 'B004_R01_R06_final_cumulative_audit.md').write_text('\n'.join(report), encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False), flush=True)
if summary['status'] != 'success':
    raise SystemExit(2)
