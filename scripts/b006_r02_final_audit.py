import csv,json,sys,time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import requests
try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(2**31-1)
ROOT=Path('input_artifact'); OUT=Path('out'); OUT.mkdir(exist_ok=True)
files=list(ROOT.rglob('B006_R02_Shard01_803_pre_audit.csv'))
if len(files)!=1: raise RuntimeError(f'Expected one input shard, found {len(files)}')
with files[0].open('r',encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f))
if len(rows)!=803: raise RuntimeError(f'Expected 803 rows, found {len(rows)}')
s=requests.Session(); s.headers.update({'User-Agent':'Shuzhen-B006-R02-DOI-audit/1.0 (mailto:research@example.com)','Accept':'text/html,application/xhtml+xml,application/pdf,*/*;q=0.8'})
OK={200,201,202,203,204,206,301,302,303,307,308,401,403,405,406,418,429}; BAD={404,410}
def audit(row):
    url=row.get('DOI_URL') or 'https://doi.org/'+row['doi']; status=''; final=''; note=''; result='需复核'
    for attempt in range(3):
        try:
            r=s.get(url,allow_redirects=True,timeout=18,stream=True); status=r.status_code; final=r.url or url; r.close()
            if status in OK:
                result='链接可用'; note='页面存在访问限制或限流，不视为无效DOI' if status in {401,403,405,406,418,429} else ''; break
            if status in BAD: result='链接无效'; note='DOI解析返回404/410'; break
            note=f'HTTP {status}'
        except requests.RequestException as exc:
            note=type(exc).__name__; time.sleep(0.5+attempt)
    out=dict(row); out.update({'link_http_status':status,'link_audit_result':result,'link_final_url':final or url,'link_audit_note':note}); return out
results=[]
with ThreadPoolExecutor(max_workers=24) as ex:
    futures=[ex.submit(audit,r) for r in rows]
    for i,f in enumerate(as_completed(futures),1):
        results.append(f.result())
        if i%100==0: print('AUDIT_PROGRESS',i,dict(Counter(x['link_audit_result'] for x in results)),flush=True)
results.sort(key=lambda r:r.get('B006_ID') or '')
headers=list(results[0].keys())
with (OUT/'B006_R02_Shard01_803_audited.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=headers); w.writeheader(); w.writerows(results)
summary={'stage':'B006-R02-audit','input_rows':len(rows),'output_rows':len(results),'unique_dois':len({r.get('doi') for r in results}),'audit_result_counts':dict(Counter(r.get('link_audit_result') for r in results)),'http_status_counts':dict(Counter(str(r.get('link_http_status')) for r in results))}
(OUT/'audit_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(summary,ensure_ascii=False),flush=True)
if len(results)!=803 or summary['unique_dois']!=803: raise SystemExit(2)
