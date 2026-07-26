import csv
import json
import sys
from collections import Counter
from pathlib import Path

try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(2**31-1)

ROOT=Path('audit_artifacts'); OUT=Path('out'); OUT.mkdir(exist_ok=True)
files=sorted(ROOT.rglob('B004_R01_Student*_1000_audited.csv'))
summary_files=sorted(ROOT.rglob('B004_R01_Student*_audit_summary.json'))
if len(files)!=10:
    raise RuntimeError(f'Expected 10 audited student CSVs, found {len(files)}')
rows=[]
student_counts=Counter(); rel=Counter(); pri=Counter(); kc=Counter(); evidence=Counter(); audit=Counter(); http=Counter()
headers=None
for path in files:
    with path.open('r',encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f)
        if headers is None: headers=reader.fieldnames or []
        for row in reader:
            rows.append(row)
            student_counts[row.get('student') or '']+=1
            rel[row.get('relevance') or '']+=1
            pri[row.get('download_priority') or '']+=1
            kc[row.get('K_primary') or '']+=1
            evidence[row.get('evidence_mode') or '']+=1
            audit[row.get('link_audit_result') or '']+=1
            http[str(row.get('link_http_status') or '')]+=1

rows.sort(key=lambda r:r.get('B004_ID') or '')
unique_dois=len({(r.get('doi') or '').lower() for r in rows})
unique_ids=len({r.get('B004_ID') for r in rows})
with (OUT/'B004_R01_10000_master_audited.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=headers); w.writeheader(); w.writerows(rows)
# Also copy each student file into the final artifact with simple names.
for i in range(1,11):
    subset=[r for r in rows if r.get('student')==f'Student{i:02d}']
    subset.sort(key=lambda r:r.get('B004_ID') or '')
    with (OUT/f'B004_R01_Student{i:02d}_1000.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=headers); w.writeheader(); w.writerows(subset)

invalid=audit.get('链接无效',0)
review=audit.get('需复核',0)
status='success'
if len(rows)!=10000 or unique_dois!=10000 or unique_ids!=10000 or any(student_counts.get(f'Student{i:02d}',0)!=1000 for i in range(1,11)) or invalid>100:
    status='failure'
summary={
 'stage':'S4.1','status':status,'records':len(rows),'unique_dois':unique_dois,'unique_ids':unique_ids,
 'id_start':rows[0].get('B004_ID') if rows else '','id_end':rows[-1].get('B004_ID') if rows else '',
 'student_counts':dict(student_counts),'K_counts':dict(kc),'relevance_counts':dict(rel),'priority_counts':dict(pri),
 'evidence_mode_counts':dict(evidence),'link_audit_counts':dict(audit),'http_status_counts':dict(http),
 'invalid_link_records':invalid,'review_link_records':review,
 'quality_gate':{'records':10000,'unique_dois':10000,'each_student':1000,'invalid_links_max':100},
 'next':'Convert ten audited CSV task files to formatted Excel workbooks and release to students'
}
(OUT/'run_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'stage_report.md').write_text('\n'.join([
 '# B004 Stage S4.1 Report','',f'- Status: **{status}**',f'- Records: {len(rows):,}',f'- Unique DOIs: {unique_dois:,}',
 f'- Student counts: {dict(student_counts)}',f'- K counts: {dict(kc)}',f'- Relevance: {dict(rel)}',f'- Priority: {dict(pri)}',
 f'- Evidence modes: {dict(evidence)}',f'- Link audit: {dict(audit)}',f"- Next: {summary['next']}"
]),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False),flush=True)
if status!='success': raise SystemExit(2)
