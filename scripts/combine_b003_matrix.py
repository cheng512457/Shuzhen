import csv
import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path

QUOTAS={"G1":1100,"G2":1200,"G3":1600,"G4":700,"G5":500,"G6":1500,"G7":1800,"G8":1000,"G9":300,"G10":300}
ROOT=Path("group_artifacts")
OUT=Path("out")
OUT.mkdir(exist_ok=True)

def safe_author(x):
    return re.sub(r"[^A-Za-z0-9-]+","",str(x or "")) or "Author"

def doi_tail(x):
    y=re.sub(r"[^A-Za-z0-9]","",str(x or ""))
    return y[-4:] if len(y)>=4 else y

def read_all():
    rows=[]
    for path in ROOT.rglob("B003_G*_candidates.csv"):
        with path.open("r",encoding="utf-8-sig",newline="") as f:
            for row in csv.DictReader(f):
                row["score_num"]=float(row.get("score") or 0)
                row["cited_num"]=int(float(row.get("cited_by_count") or 0))
                rows.append(row)
    return rows

rows=read_all()
print("MATRIX_INPUT_ROWS",len(rows),flush=True)
by_doi={}
for row in rows:
    doi=(row.get("doi") or "").strip().lower()
    if not doi:
        continue
    old=by_doi.get(doi)
    if old is None or (row["score_num"],row["cited_num"])>(old["score_num"],old["cited_num"]):
        by_doi[doi]=row
unique=list(by_doi.values())
unique.sort(key=lambda x:(x["score_num"],x["cited_num"],str(x.get("year") or "")),reverse=True)
print("MATRIX_UNIQUE_DOIS",len(unique),flush=True)

by_group=defaultdict(list)
for row in unique:
    by_group[row.get("group")].append(row)
selected=[]
used=set()
for group in [f"G{i}" for i in range(1,11)]:
    for row in by_group[group][:QUOTAS[group]]:
        doi=row["doi"].lower()
        if doi not in used:
            used.add(doi);selected.append(row)
for row in unique:
    if len(selected)>=10000:
        break
    doi=row["doi"].lower()
    if doi in used:
        continue
    used.add(doi);selected.append(row)

partial=selected[:]
if len(partial)<10000:
    with (OUT/"B003_matrix_partial.csv").open("w",encoding="utf-8-sig",newline="") as f:
        headers=list(partial[0].keys()) if partial else ["group","doi","title"]
        w=csv.DictWriter(f,fieldnames=headers,extrasaction="ignore");w.writeheader();w.writerows(partial)
    summary={"status":"insufficient","input_rows":len(rows),"unique_dois":len(unique),"selected":len(partial),"group_available":dict(Counter(x.get("group") for x in unique)),"group_selected":dict(Counter(x.get("group") for x in partial))}
    (OUT/"run_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False),flush=True)
    raise SystemExit(2)

selected=selected[:10000]
selected.sort(key=lambda x:(int((x.get("group") or "G99")[1:]),x.get("unit") or "",{"P0":0,"P1":1,"P2":2}.get(x.get("priority"),9),-x["score_num"],-x["cited_num"],x.get("title") or ""))
for idx,row in enumerate(selected,1):
    bid=f"B003-{idx:05d}"
    row["B003_ID"]=bid
    row["student_file"]=f"Student{(idx-1)//1000+1:02d}"
    row["pdf_name"]=f"{bid}_{safe_author(row.get('first_author'))}_{row.get('year')}_{doi_tail(row.get('doi'))}.pdf"
    row["download_status"]="待下载"

HEADERS=["B003_ID","student_file","group","unit","priority","initial_relevance","first_author","year","title","journal","doi","pdf_name","type","cited_by_count","is_oa","oa_status","abstract","query","matched_terms","score","crossref_title","title_similarity","metadata_verified","download_status","download_link"]

def export(path,subset):
    with path.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=HEADERS)
        w.writeheader();w.writerows([{k:r.get(k,"") for k in HEADERS} for r in subset])

export(OUT/"B003_10000_master.csv",selected)
for i in range(10):
    export(OUT/f"B003_Student{i+1:02d}_1000.csv",selected[i*1000:(i+1)*1000])
summary={"status":"success","total_records":len(selected),"unique_dois":len({x['doi'].lower() for x in selected}),"input_rows":len(rows),"input_unique_dois":len(unique),"group_counts":dict(Counter(x.get("group") for x in selected)),"unit_counts":dict(Counter(x.get("unit") for x in selected)),"student_counts":dict(Counter(x.get("student_file") for x in selected)),"priority_counts":dict(Counter(x.get("priority") for x in selected)),"relevance_counts":dict(Counter(x.get("initial_relevance") for x in selected)),"metadata_counts":dict(Counter(x.get("metadata_verified") for x in selected))}
(OUT/"run_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(summary,ensure_ascii=False),flush=True)
