import csv,json,os,sys,time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import requests
try: csv.field_size_limit(sys.maxsize)
except OverflowError: csv.field_size_limit(2**31-1)
SHARD=int(os.environ.get('SHARD','1')); ROOT=Path('input_artifact'); OUT=Path('out'); OUT.mkdir(exist_ok=True)
files=list(ROOT.rglob(f'B005_R02_Shard{SHARD:02d}_1000_pre_audit.csv'))
if not files: raise RuntimeError(f'Missing B005 R02 shard {SHARD}')
with files[0].open('r',encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f))
s=requests.Session();s.headers.update({'User-Agent':'Shuzhen-B005-R02-DOI-audit/1.0 (mailto:research@example.com)','Accept':'text/html,application/xhtml+xml,application/pdf,*/*;q=0.8'})
OK={200,201,202,203,204,206,301,302,303,307,308,401,403,405,406,418,429}; BAD={404,410}
def audit(r):
    url=r.get('DOI_URL') or 'https://doi.org/'+r['doi']; status=''; final=''; note=''; result='需复核'
    for attempt in range(3):
        try:
            x=s.get(url,allow_redirects=True,timeout=18,stream=True);status=x.status_code;final=x.url or url;x.close()
            if status in OK:
                result='链接可用'; note='页面存在访问限制或限流，不视为无效DOI' if status in {401,403,405,406,418,429} else '';break
            if status in BAD:
                result='链接无效';note='DOI解析返回404/410';break
            note=f'HTTP {status}'
        except requests.RequestException as exc:
            note=type(exc).__name__;time.sleep(0.5+attempt)
    o=dict(r);o['link_http_status']=status;o['link_audit_result']=result;o['link_final_url']=final or url;o['link_audit_note']=note;return o
res=[]
with ThreadPoolExecutor(max_workers=24) as ex:
    fut=[ex.submit(audit,r) for r in rows]
    for i,f in enumerate(as_completed(fut),1):
        res.append(f.result())
        if i%100==0: print('AUDIT_PROGRESS',SHARD,i,dict(Counter(x['link_audit_result'] for x in res)),flush=True)
res.sort(key=lambda r:r.get('B005_ID') or '')
headers=list(res[0].keys())
with (OUT/f'B005_R02_Shard{SHARD:02d}_1000_audited.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=headers);w.writeheader();w.writerows(res)
summary={'stage':'B005-R02-audit','shard':SHARD,'input_rows':len(rows),'output_rows':len(res),'unique_dois':len({r.get('doi') for r in res}),'audit_result_counts':dict(Counter(r.get('link_audit_result') for r in res)),'http_status_counts':dict(Counter(str(r.get('link_http_status')) for r in res))}
(OUT/f'B005_R02_Shard{SHARD:02d}_audit_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False),flush=True)
if len(res)!=1000 or summary['unique_dois']!=1000: raise SystemExit(2)
