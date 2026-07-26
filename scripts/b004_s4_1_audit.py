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

STUDENT = int(os.environ.get('STUDENT','1'))
ROOT = Path('input_artifact')
OUT = Path('out')
OUT.mkdir(exist_ok=True)
files = list(ROOT.rglob(f'B004_R01_Student{STUDENT:02d}_1000_pre_audit.csv'))
if not files:
    raise RuntimeError(f'Missing Student{STUDENT:02d} pre-audit file')
source = files[0]
with source.open('r',encoding='utf-8-sig',newline='') as f:
    rows = list(csv.DictReader(f))

session = requests.Session()
session.headers.update({'User-Agent':'Shuzhen-B004-DOI-link-audit/1.0 (mailto:research@example.com)','Accept':'text/html,application/xhtml+xml,application/pdf,*/*;q=0.8'})

ACCEPTABLE = {200,201,202,203,204,206,301,302,303,307,308,401,403,405,406,418,429}
INVALID = {404,410}

def audit(row):
    url = row.get('DOI_URL') or ('https://doi.org/' + row['doi'])
    status = ''
    final = ''
    note = ''
    result = '需复核'
    for attempt in range(3):
        try:
            r = session.get(url, allow_redirects=True, timeout=18, stream=True)
            status = r.status_code
            final = r.url or url
            r.close()
            if status in ACCEPTABLE:
                result = '链接可用'
                if status in {401,403,405,406,418,429}:
                    note = '页面存在访问限制或限流，不视为无效DOI'
                break
            if status in INVALID:
                result = '链接无效'
                note = 'DOI解析返回404/410'
                break
            note = f'HTTP {status}'
        except requests.RequestException as exc:
            note = type(exc).__name__
            time.sleep(0.5 + attempt)
    out = dict(row)
    out['link_http_status'] = status
    out['link_audit_result'] = result
    out['link_final_url'] = final or url
    out['link_audit_note'] = note
    return out

results=[]
with ThreadPoolExecutor(max_workers=24) as ex:
    futures=[ex.submit(audit,r) for r in rows]
    for idx,fut in enumerate(as_completed(futures),1):
        results.append(fut.result())
        if idx%100==0:
            print('AUDIT_PROGRESS',STUDENT,idx,dict(Counter(r['link_audit_result'] for r in results)),flush=True)

# Restore permanent-ID order.
results.sort(key=lambda r:r.get('B004_ID') or '')
headers=list(results[0].keys()) if results else []
with (OUT/f'B004_R01_Student{STUDENT:02d}_1000_audited.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=headers); w.writeheader(); w.writerows(results)
summary={
 'stage':'S4.1-audit','student':f'Student{STUDENT:02d}','input_rows':len(rows),'output_rows':len(results),
 'unique_dois':len({r.get('doi') for r in results}),'audit_result_counts':dict(Counter(r.get('link_audit_result') for r in results)),
 'http_status_counts':dict(Counter(str(r.get('link_http_status')) for r in results))
}
(OUT/f'B004_R01_Student{STUDENT:02d}_audit_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False),flush=True)
if len(results)!=1000 or summary['unique_dois']!=1000:
    raise SystemExit(2)
