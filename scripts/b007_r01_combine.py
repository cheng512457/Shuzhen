import csv,json,sys
from collections import Counter
from pathlib import Path
try: csv.field_size_limit(sys.maxsize)
except OverflowError: csv.field_size_limit(2**31-1)
ROOT=Path('audit_artifacts');OUT=Path('out');OUT.mkdir(exist_ok=True)
files=sorted(ROOT.rglob('B007_R01_Shard*_audited.csv'))
if len(files)!=20: raise RuntimeError(f'Expected 20 audited shards, found {len(files)}')
rows=[];headers=None;students=Counter();rel=Counter();pri=Counter();kc=Counter();ac=Counter();hc=Counter()
for p in files:
 with p.open('r',encoding='utf-8-sig',newline='') as f:
  rd=csv.DictReader(f);headers=headers or rd.fieldnames or []
  for r in rd:
   rows.append(r);students[r.get('student') or '']+=1;rel[r.get('relevance') or '']+=1;pri[r.get('download_priority') or '']+=1;kc[r.get('K_primary') or r.get('primary_k_domain') or '']+=1;ac[r.get('link_audit_result') or '']+=1;hc[str(r.get('link_http_status') or '')]+=1
rows.sort(key=lambda r:r.get('B007_ID') or '');ud=len({(r.get('doi') or '').lower() for r in rows});ui=len({r.get('B007_ID') for r in rows})
with (OUT/'B007_R01_19775_master_audited.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.DictWriter(f,fieldnames=headers);w.writeheader();w.writerows(rows)
for i in range(1,11):
 s=f'Student{i:02d}';sub=[r for r in rows if r.get('student')==s]
 with (OUT/f'B007_R01_{s}_{len(sub)}.csv').open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=headers);w.writeheader();w.writerows(sub)
invalid=ac.get('链接无效',0);counts=[students.get(f'Student{i:02d}',0) for i in range(1,11)]
status='success'
if len(rows)!=19775 or ud!=19775 or ui!=19775 or not rows or rows[0].get('B007_ID')!='B007-000001' or rows[-1].get('B007_ID')!='B007-019775' or max(counts)-min(counts)>1 or sum(counts)!=19775 or set(rel)-{'A','B'} or invalid>200: status='failure'
summary={'stage':'B007-R01','status':status,'records':len(rows),'unique_dois':ud,'unique_ids':ui,'id_start':rows[0].get('B007_ID') if rows else '','id_end':rows[-1].get('B007_ID') if rows else '','student_counts':dict(students),'K_counts':dict(kc),'relevance_counts':dict(rel),'priority_counts':dict(pri),'link_audit_counts':dict(ac),'http_status_counts':dict(hc),'invalid_link_records':invalid,'review_link_records':ac.get('需复核',0),'quality_gate':{'records':19775,'unique_dois':19775,'student_difference_max':1,'id_start':'B007-000001','id_end':'B007-019775','A_B_only':True,'invalid_links_max':200,'audit_shards':20},'next':'Freeze B007 complete 19775-record A/B database and perform cumulative B004+B005+B006+B007 DOI audit'}
(OUT/'run_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');(OUT/'stage_report.md').write_text('\n'.join(['# B007 R01 Final Report','',f'- Status: **{status}**',f'- Records: {len(rows):,}',f'- Unique DOIs: {ud:,}',f'- IDs: {summary["id_start"]} to {summary["id_end"]}',f'- Students: {dict(students)}',f'- K counts: {dict(kc)}',f'- Relevance: {dict(rel)}',f'- Priority: {dict(pri)}',f'- Link audit: {dict(ac)}',f'- Next: {summary["next"]}']),encoding='utf-8');print(json.dumps(summary,ensure_ascii=False),flush=True)
if status!='success': raise SystemExit(2)