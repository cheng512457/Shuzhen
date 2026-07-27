import csv,json,sys
from collections import Counter
from pathlib import Path
try: csv.field_size_limit(sys.maxsize)
except OverflowError: csv.field_size_limit(2**31-1)
ROOT=Path('audit_artifacts'); OUT=Path('out'); OUT.mkdir(exist_ok=True)
files=sorted(ROOT.rglob('B005_R02_Shard*_1000_audited.csv'))
if len(files)!=30: raise RuntimeError(f'Expected 30 audited shards, found {len(files)}')
rows=[];headers=None;students=Counter();rel=Counter();pri=Counter();kc=Counter();evidence=Counter();audit=Counter();http=Counter()
for path in files:
    with path.open('r',encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f);headers=headers or reader.fieldnames or []
        for r in reader:
            rows.append(r);students[r.get('student') or '']+=1;rel[r.get('relevance') or '']+=1;pri[r.get('download_priority') or '']+=1;kc[r.get('K_primary') or '']+=1;evidence[r.get('evidence_mode') or '']+=1;audit[r.get('link_audit_result') or '']+=1;http[str(r.get('link_http_status') or '')]+=1
rows.sort(key=lambda r:r.get('B005_ID') or '')
unique_dois=len({(r.get('doi') or '').lower() for r in rows});unique_ids=len({r.get('B005_ID') for r in rows})
with (OUT/'B005_R02_30000_master_audited.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=headers);w.writeheader();w.writerows(rows)
for i in range(1,11):
    sub=[r for r in rows if r.get('student')==f'Student{i:02d}'];sub.sort(key=lambda r:r.get('B005_ID') or '')
    with (OUT/f'B005_R02_Student{i:02d}_3000.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=headers);w.writeheader();w.writerows(sub)
invalid=audit.get('链接无效',0);status='success'
if len(rows)!=30000 or unique_dois!=30000 or unique_ids!=30000 or not rows or rows[0].get('B005_ID')!='B005-030001' or rows[-1].get('B005_ID')!='B005-060000' or any(students.get(f'Student{i:02d}',0)!=3000 for i in range(1,11)) or set(rel)-{'A','B'} or invalid>300: status='failure'
summary={'stage':'B005-R02','status':status,'records':len(rows),'unique_dois':unique_dois,'unique_ids':unique_ids,'id_start':rows[0].get('B005_ID') if rows else '','id_end':rows[-1].get('B005_ID') if rows else '','student_counts':dict(students),'K_counts':dict(kc),'relevance_counts':dict(rel),'priority_counts':dict(pri),'evidence_mode_counts':dict(evidence),'link_audit_counts':dict(audit),'http_status_counts':dict(http),'invalid_link_records':invalid,'review_link_records':audit.get('需复核',0),'quality_gate':{'records':30000,'unique_dois':30000,'each_student':3000,'id_start':'B005-030001','id_end':'B005-060000','A_B_only':True,'invalid_links_max':300,'audit_shards':30,'B004_R01_exclusion_required':True},'next':'Release B005-R02 to students and prepare the final remaining B005 A/B batch'}
(OUT/'run_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'stage_report.md').write_text('\n'.join(['# B005 R02 Report','',f'- Status: **{status}**',f'- Records: {len(rows):,}',f'- Unique DOIs: {unique_dois:,}',f'- IDs: {summary["id_start"]} to {summary["id_end"]}',f'- Students: {dict(students)}',f'- K counts: {dict(kc)}',f'- Relevance: {dict(rel)}',f'- Priority: {dict(pri)}',f'- Link audit: {dict(audit)}',f'- Next: {summary["next"]}']),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False),flush=True)
if status!='success': raise SystemExit(2)
