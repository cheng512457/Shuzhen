import csv,json,sys
from collections import Counter
from pathlib import Path
try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(2**31-1)
PREP=Path('prepared_artifact'); ROOT=Path('audit_artifacts'); OUT=Path('out'); OUT.mkdir(exist_ok=True)
ps=list(PREP.rglob('prepare_summary.json')); files=list(ROOT.rglob('B006_R02_Shard01_803_audited.csv'))
if len(ps)!=1 or len(files)!=1: raise RuntimeError(f'Missing prepared/audited inputs prep={len(ps)} audit={len(files)}')
prepared=json.loads(ps[0].read_text(encoding='utf-8'))
with files[0].open('r',encoding='utf-8-sig',newline='') as f:
    reader=csv.DictReader(f); headers=reader.fieldnames or []; rows=list(reader)
rows.sort(key=lambda r:r.get('B006_ID') or '')
students=Counter(r.get('student') or '' for r in rows); rel=Counter(r.get('relevance') or '' for r in rows); pri=Counter(r.get('download_priority') or '' for r in rows); kc=Counter(r.get('K_primary') or '' for r in rows); audit=Counter(r.get('link_audit_result') or '' for r in rows); http=Counter(str(r.get('link_http_status') or '') for r in rows)
unique_dois=len({(r.get('doi') or '').lower() for r in rows}); unique_ids=len({r.get('B006_ID') for r in rows})
with (OUT/'B006_R02_803_master_audited.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=headers); w.writeheader(); w.writerows(rows)
for i in range(1,11):
    subset=[r for r in rows if r.get('student')==f'Student{i:02d}']
    with (OUT/f'B006_R02_Student{i:02d}_{len(subset)}.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=headers); w.writeheader(); w.writerows(subset)
vals=[students.get(f'Student{i:02d}',0) for i in range(1,11)]; invalid=audit.get('链接无效',0)
checks={'records_equal_803':len(rows)==803,'unique_dois_equal_records':unique_dois==803,'unique_ids_equal_records':unique_ids==803,'id_start_correct':bool(rows) and rows[0].get('B006_ID')=='B006-020001','id_end_correct':bool(rows) and rows[-1].get('B006_ID')=='B006-020803','students_balanced':max(vals)-min(vals)<=1 and sum(vals)==803,'A_B_only':not(set(rel)-{'A','B'}),'invalid_links_within_limit':invalid<=20,'prior_overlap_zero':prepared.get('overlap_prior')==0 and prepared.get('excluded_r01')==20000,'all_shards_present':len(files)==1}
status='success' if all(checks.values()) else 'failure'
summary={'stage':'B006-R02','status':status,'records':len(rows),'unique_dois':unique_dois,'unique_ids':unique_ids,'id_start':rows[0].get('B006_ID') if rows else '','id_end':rows[-1].get('B006_ID') if rows else '','excluded_previous_unique_dois':prepared.get('excluded_union'),'prior_overlap':prepared.get('overlap_prior'),'R01_excluded':prepared.get('excluded_r01'),'student_counts':dict(students),'K_counts':dict(kc),'relevance_counts':dict(rel),'priority_counts':dict(pri),'link_audit_counts':dict(audit),'http_status_counts':dict(http),'invalid_link_records':invalid,'review_link_records':audit.get('需复核',0),'quality_checks':checks,'next':'Freeze complete B006 20803-record A/B database and perform cumulative B004+B005+B006 DOI audit'}
(OUT/'run_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'stage_report.md').write_text('\n'.join(['# B006 R02 Final Remaining-Pool Report','',f'- Status: **{status}**',f'- Records: {len(rows):,}',f'- Unique DOIs: {unique_dois:,}',f'- IDs: {summary["id_start"]} to {summary["id_end"]}',f'- Students: {dict(students)}',f'- K counts: {dict(kc)}',f'- Relevance: {dict(rel)}',f'- Priority: {dict(pri)}',f'- Link audit: {dict(audit)}',f'- Next: {summary["next"]}']),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False),flush=True)
if status!='success': raise SystemExit(2)
