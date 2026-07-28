import csv, json, os, sys, time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(2**31 - 1)

SHARD = int(os.environ.get('SHARD', '1'))
ROOT = Path('input_artifact')
OUT = Path('out')
OUT.mkdir(exist_ok=True)
files = list(ROOT.rglob(f'B008_R01_Shard{SHARD:02d}_pre_audit.csv'))
if len(files) != 1:
    raise RuntimeError(f'Missing shard {SHARD}')
with files[0].open('r', encoding='utf-8-sig', newline='') as f:
    rows = list(csv.DictReader(f))
expected = 406 if SHARD == 19 else 1000
if len(rows) != expected:
    raise RuntimeError(f'Unexpected shard size {len(rows)} expected {expected}')

session = requests.Session()
session.headers.update({
    'User-Agent': 'Shuzhen-B008-DOI-audit/1.0 (mailto:research@example.com)',
    'Accept': 'text/html,application/xhtml+xml,application/pdf,*/*;q=0.8',
})
OK = {200, 201, 202, 203, 204, 206, 301, 302, 303, 307, 308, 401, 403, 405, 406, 418, 429}
BAD = {404, 410}

def audit(row):
    url = row.get('DOI_URL') or 'https://doi.org/' + row['doi']
    status = ''
    final = ''
    note = ''
    result = '需复核'
    for attempt in range(3):
        try:
            response = session.get(url, allow_redirects=True, timeout=18, stream=True)
            status = response.status_code
            final = response.url or url
            response.close()
            if status in OK:
                result = '链接可用'
                if status in {401, 403, 405, 406, 418, 429}:
                    note = '页面存在访问限制或限流，不视为无效DOI'
                break
            if status in BAD:
                result = '链接无效'
                note = 'DOI解析返回404/410'
                break
            note = f'HTTP {status}'
        except requests.RequestException as exc:
            note = type(exc).__name__
            time.sleep(0.5 + attempt)
    out = dict(row)
    out.update({
        'link_http_status': status,
        'link_audit_result': result,
        'link_final_url': final or url,
        'link_audit_note': note,
    })
    return out

out_rows = []
with ThreadPoolExecutor(max_workers=24) as executor:
    futures = [executor.submit(audit, row) for row in rows]
    for i, future in enumerate(as_completed(futures), 1):
        out_rows.append(future.result())
        if i % 100 == 0:
            print('AUDIT_PROGRESS', SHARD, i, dict(Counter(r['link_audit_result'] for r in out_rows)), flush=True)

out_rows.sort(key=lambda r: r.get('B008_ID') or '')
headers = list(out_rows[0])
with (OUT / f'B008_R01_Shard{SHARD:02d}_audited.csv').open('w', encoding='utf-8-sig', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=headers)
    writer.writeheader()
    writer.writerows(out_rows)
summary = {
    'stage': 'B008-R01-audit', 'shard': SHARD,
    'input_rows': len(rows), 'output_rows': len(out_rows),
    'unique_dois': len({r['doi'] for r in out_rows}),
    'audit_result_counts': dict(Counter(r['link_audit_result'] for r in out_rows)),
    'http_status_counts': dict(Counter(str(r['link_http_status']) for r in out_rows)),
}
(OUT / f'B008_R01_Shard{SHARD:02d}_audit_summary.json').write_text(
    json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8'
)
print(json.dumps(summary, ensure_ascii=False), flush=True)
if len(out_rows) != expected or summary['unique_dois'] != expected:
    raise SystemExit(2)
