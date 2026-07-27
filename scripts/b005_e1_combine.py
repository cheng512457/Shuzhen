import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(2**31 - 1)

ROOT=Path("shard_artifacts")
EXC=Path("exclusion_artifact")
OUT=Path("out")
OUT.mkdir(exist_ok=True)

exc_files=list(EXC.rglob("B004_157917_excluded_dois.txt"))
if len(exc_files)!=1:
    raise RuntimeError(f"Expected one exclusion registry, found {len(exc_files)}")
excluded={x.strip().lower() for x in exc_files[0].read_text(encoding="utf-8").splitlines() if x.strip()}

csv_files=sorted(ROOT.rglob("B005_E1_K*_*.csv"))
summary_files=sorted(ROOT.rglob("B005_E1_K*_*_summary.json"))
if len(csv_files)!=32:
    raise RuntimeError(f"Expected 32 discovery CSV files, found {len(csv_files)}")

records={}
raw_rows=0
for path in csv_files:
    with path.open("r",encoding="utf-8-sig",newline="") as f:
        for row in csv.DictReader(f):
            raw_rows+=1
            doi=(row.get("doi") or "").strip().lower()
            if not doi or doi in excluded:
                continue
            old=records.get(doi)
            if old is None:
                row["k_domains_set"]={row.get("k_domain") or ""}
                row["strata_set"]={row.get("stratum") or ""}
                row["queries_set"]={q for q in (row.get("queries") or "").split(" || ") if q}
                row["query_hits_total"]=int(float(row.get("query_hits") or 0))
                records[doi]=row
            else:
                old["k_domains_set"].add(row.get("k_domain") or "")
                old["strata_set"].add(row.get("stratum") or "")
                old["queries_set"].update(q for q in (row.get("queries") or "").split(" || ") if q)
                old["query_hits_total"] += int(float(row.get("query_hits") or 0))
                for field in ["title","first_author","year","journal","document_type","abstract","article_link","openalex_id"]:
                    if len(str(row.get(field) or "")) > len(str(old.get(field) or "")):
                        old[field]=row.get(field)
                try:
                    old["cited_by_count"]=max(int(float(old.get("cited_by_count") or 0)),int(float(row.get("cited_by_count") or 0)))
                except Exception:
                    pass

rows=[]
for doi,row in records.items():
    out={k:v for k,v in row.items() if k not in {"k_domains_set","strata_set","queries_set","query_hits_total"}}
    out["doi"]=doi
    out["k_domains"]="; ".join(sorted(x for x in row["k_domains_set"] if x))
    out["strata"]="; ".join(sorted(x for x in row["strata_set"] if x))
    out["queries"]=" || ".join(sorted(row["queries_set"]))
    out["query_hits_total"]=row["query_hits_total"]
    out["B004_overlap"]="no"
    rows.append(out)
rows.sort(key=lambda r:(-int(r.get("query_hits_total") or 0),-int(float(r.get("cited_by_count") or 0)),r.get("title") or ""))

headers=["doi","title","first_author","year","journal","document_type","abstract","cited_by_count","is_oa","openalex_id","article_link","k_domains","strata","query_hits_total","queries","B004_overlap"]
with (OUT/"B005_E1_new_unique_candidates.csv").open("w",encoding="utf-8-sig",newline="") as f:
    w=csv.DictWriter(f,fieldnames=headers); w.writeheader(); w.writerows([{h:r.get(h,"") for h in headers} for r in rows])

k_counts=Counter()
stratum_counts=Counter()
for row in rows:
    for k in (row.get("k_domains") or "").split("; "):
        if k: k_counts[k]+=1
    for s in (row.get("strata") or "").split("; "):
        if s: stratum_counts[s]+=1

overlap=sum(1 for r in rows if r["doi"] in excluded)
missing_k=[f"K{i:02d}" for i in range(1,17) if k_counts.get(f"K{i:02d}",0)<300]
status="success"
if len(csv_files)!=32 or len(rows)<20000 or overlap!=0 or missing_k:
    status="failure"
summary={
    "stage":"B005-E1-gap-frontier-expansion",
    "status":status,
    "discovery_csv_files":len(csv_files),
    "discovery_summary_files":len(summary_files),
    "raw_rows_after_shard_dedup":raw_rows,
    "new_global_unique_dois":len(rows),
    "excluded_B004_dois":len(excluded),
    "overlap_with_B004":overlap,
    "K_membership_counts":dict(sorted(k_counts.items())),
    "stratum_membership_counts":dict(stratum_counts),
    "missing_or_small_K_domains":missing_k,
    "quality_gate":{"new_unique_dois_min":20000,"K_domain_min":300,"B004_overlap":0,"expected_shards":32},
    "next":"B005-E2 metadata verification, relevance classification and first non-overlapping student download round"
}
(OUT/"run_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
(OUT/"stage_report.md").write_text("\n".join([
"# B005 E1 Gap and Frontier Expansion","",f"- Status: **{status}**",f"- New unique DOIs: {len(rows):,}",f"- Overlap with B004: {overlap}",f"- K-domain membership counts: {dict(sorted(k_counts.items()))}",f"- Next: {summary['next']}"
]),encoding="utf-8")
print(json.dumps(summary,ensure_ascii=False),flush=True)
if status!="success":
    raise SystemExit(2)
