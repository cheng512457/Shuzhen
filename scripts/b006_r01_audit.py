import csv
import json
import os
import sys
import time
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
files = list(ROOT.rglob(f'B006_R01_Shard{SHARD:02d}_1000_pre_audit.csv'))
if not files:
    raise RuntimeError(f'Missing B006 R01 shard {SHARD}')
with files[0].open('r', encoding='utf-8-sig', newline='') as f:
    rows = list(csv.DictReader(f))

session = requests.Session()
session.headers.update({
    'User-Agent': 'Shuzhen-B006-DOI-audit/1.0 (mailto:research@example.com)',
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
                note = '页面存在访问限制或限流，不视为无效DOI' if status in {401, 403, 405, 406, 418, 429} else ''
                break
            if status in BAD:
                result = '链接无效'
                note = 'DOI解析返回404/410'
                break
            note = f'HTTP {status}'
        except requests.RequestException as exc:
            note = type(exc).__name__
            time.sleep(0.5 + attempt)
    output = dict(row)
    output['link_http_status'] = status
    output['link_audit_result'] = result
    output['link_final_url'] = final or url
    output['link_audit_note'] = note
    return output

results = []
with ThreadPoolExecutor(max_workers=24) as executor:
    futures = [executor.submit(audit, row) for row in rows]
    for index, future in enumerate(as_completed(futures), 1):
        results.append(future.result())
        if index % 100 == 0:
            print('AUDIT_PROGRESS', SHARD, index, dict(Counter(x['link_audit_result'] for x in results)), flush=True)
results.sort(key=lambda row: row.get('B006_ID') or '')
headers = list(results[0].keys())
with (OUT / f'B006_R01_Shard{SHARD:02d}_1000_audited.csv').open('w', encoding='utf-8-sig', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=headers)
    writer.writeheader()
    writer.writerows(results)
summary = {
    'stage': 'B006-R01-audit',
    'shard': SHARD,
    'input_rows': len(rows),
    'output_rows': len(results),
    'unique_dois': len({row.get('doi') for row in results}),
    'audit_result_counts': dict(Counter(row.get('link_audit_result') for row in results)),
    'http_status_counts': dict(Counter(str(row.get('link_http_status')) for row in results)),
}
(OUT / f'B006_R01_Shard{SHARD:02d}_audit_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False), flush=True)
if len(results) != 1000 or summary['unique_dois'] != 1000:
    raise SystemExit(2)
