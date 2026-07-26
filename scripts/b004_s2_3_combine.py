import csv
import json
import sqlite3
from collections import Counter
from pathlib import Path

ROOT = Path("shard_artifacts")
OUT = Path("out")
OUT.mkdir(exist_ok=True)

csv_files = sorted(ROOT.rglob("B004_S2_3_shard*.csv"))
summary_files = sorted(ROOT.rglob("B004_S2_3_shard*_summary.json"))

summaries = []
for path in summary_files:
    try:
        summaries.append(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        pass

by_doi = {}
raw_rows = 0
for path in csv_files:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            raw_rows += 1
            doi = (row.get("doi") or "").strip().lower()
            if not doi:
                continue
            current = by_doi.get(doi)
            if current is None:
                current = dict(row)
                current["shards"] = {row.get("shard") or ""}
                current["relation_types_set"] = set(x for x in (row.get("relation_types") or "").split("; ") if x)
                current["seed_dois_set"] = set(x for x in (row.get("seed_dois") or "").split("; ") if x)
                current["positive_hits_set"] = set(x for x in (row.get("positive_hits") or "").split("; ") if x)
                current["relation_count_total"] = int(float(row.get("relation_count") or 0))
                by_doi[doi] = current
            else:
                current["shards"].add(row.get("shard") or "")
                current["relation_types_set"].update(x for x in (row.get("relation_types") or "").split("; ") if x)
                current["seed_dois_set"].update(x for x in (row.get("seed_dois") or "").split("; ") if x)
                current["positive_hits_set"].update(x for x in (row.get("positive_hits") or "").split("; ") if x)
                current["relation_count_total"] += int(float(row.get("relation_count") or 0))
                for field in ["title","first_author","year","journal","document_type","abstract","article_link","openalex_id"]:
                    if len(str(row.get(field) or "")) > len(str(current.get(field) or "")):
                        current[field] = row.get(field)
                try:
                    current["cited_by_count"] = max(int(float(current.get("cited_by_count") or 0)), int(float(row.get("cited_by_count") or 0)))
                except Exception:
                    pass

rows = []
for doi, row in by_doi.items():
    out = {k:v for k,v in row.items() if k not in {"shards","relation_types_set","seed_dois_set","positive_hits_set","relation_count_total"}}
    out["doi"] = doi
    out["shards"] = "; ".join(sorted(x for x in row["shards"] if x))
    out["relation_types"] = "; ".join(sorted(row["relation_types_set"]))
    out["seed_dois"] = "; ".join(sorted(row["seed_dois_set"])[:50])
    out["positive_hits"] = "; ".join(sorted(row["positive_hits_set"]))
    out["relation_count_total"] = row["relation_count_total"]
    rows.append(out)
rows.sort(key=lambda r: (int(r.get("relation_count_total") or 0), int(float(r.get("cited_by_count") or 0))), reverse=True)

headers = ["doi","title","first_author","year","journal","document_type","abstract","cited_by_count","is_oa","openalex_id","relation_count_total","relation_types","seed_dois","core_author_ids","positive_hits","shards","article_link"]
with (OUT / "B004_S2_3_global_new_unique_doi.csv").open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=headers)
    w.writeheader(); w.writerows([{k:r.get(k,"") for k in headers} for r in rows])

conn = sqlite3.connect(OUT / "b004_s2_3.sqlite")
conn.execute("DROP TABLE IF EXISTS expansion")
conn.execute("CREATE TABLE expansion (doi TEXT PRIMARY KEY, title TEXT, first_author TEXT, year TEXT, journal TEXT, document_type TEXT, abstract TEXT, cited_by_count INTEGER, is_oa TEXT, openalex_id TEXT, relation_count_total INTEGER, relation_types TEXT, seed_dois TEXT, core_author_ids TEXT, positive_hits TEXT, shards TEXT, article_link TEXT)")
conn.executemany("INSERT OR REPLACE INTO expansion VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [[r.get(h,"") for h in headers] for r in rows])
conn.commit(); conn.close()

relation_counts = Counter()
for row in rows:
    for t in (row.get("relation_types") or "").split("; "):
        if t:
            relation_counts[t] += 1
summary = {
    "stage":"S2.3",
    "status":"success",
    "shard_csv_files_found":len(csv_files),
    "shard_summary_files_found":len(summary_files),
    "seeds_input":sum(int(s.get("seeds_input") or 0) for s in summaries),
    "seeds_resolved":sum(int(s.get("seeds_resolved") or 0) for s in summaries),
    "candidate_openalex_ids":sum(int(s.get("candidate_openalex_ids") or 0) for s in summaries),
    "candidate_ids_fetched":sum(int(s.get("candidate_ids_fetched") or 0) for s in summaries),
    "raw_expansion_rows":raw_rows,
    "global_new_unique_dois":len(rows),
    "relation_type_counts":dict(relation_counts),
    "success_gate":{"shards_min":8,"seeds_resolved_min":3000,"global_new_unique_dois_min":8000},
    "next_stage":"S3.1 DOI normalization, version merging and global de-duplication across S2.1-S2.3"
}
if len(csv_files) < 8 or summary["seeds_resolved"] < 3000 or len(rows) < 8000:
    summary["status"] = "failure"
(OUT / "run_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
report = [
    "# B004 Stage S2.3 Report","",
    f"- Status: **{summary['status']}**",
    f"- Seed works resolved: {summary['seeds_resolved']:,}",
    f"- Candidate OpenAlex IDs collected: {summary['candidate_openalex_ids']:,}",
    f"- Candidate records fetched: {summary['candidate_ids_fetched']:,}",
    f"- Global new unique DOIs: {summary['global_new_unique_dois']:,}",
    f"- Relation coverage: {summary['relation_type_counts']}",
    "- Next: S3.1 global DOI normalization and de-duplication across S2.1-S2.3",
]
(OUT / "stage_report.md").write_text("\n".join(report),encoding="utf-8")
print(json.dumps(summary,ensure_ascii=False),flush=True)
if summary["status"] != "success":
    raise SystemExit(2)
