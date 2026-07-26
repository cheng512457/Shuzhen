import csv
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path("shard_artifacts")
OUT = Path("out")
OUT.mkdir(exist_ok=True)

csv_files = sorted(ROOT.rglob("B004_S2_2_T*_shard*.csv"))
summary_files = sorted(ROOT.rglob("B004_S2_2_T*_shard*_summary.json"))

rows = []
for path in csv_files:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rows.extend(csv.DictReader(f))

summaries = []
for path in summary_files:
    try:
        summaries.append(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        pass

raw_occurrences = sum(int(s.get("raw_occurrences") or 0) for s in summaries)
unique_source_records = len(rows)

# Source-level canonical records.
source_seen = set()
source_unique = []
for row in rows:
    key = (row.get("source") or "", row.get("source_id") or row.get("doi") or (row.get("title") or "").lower())
    if key in source_seen:
        continue
    source_seen.add(key)
    source_unique.append(row)

# DOI-level merge. Preserve source and topic memberships.
by_doi = {}
for row in source_unique:
    doi = (row.get("doi") or "").strip().lower()
    if not doi:
        continue
    current = by_doi.get(doi)
    if current is None:
        current = dict(row)
        current["sources"] = {row.get("source") or ""}
        current["topics"] = {row.get("topic") or ""}
        current["k_domains"] = {row.get("k_domain") or ""}
        current["pmids"] = {row.get("pmid") or ""} if row.get("pmid") else set()
        current["pmcids"] = {row.get("pmcid") or ""} if row.get("pmcid") else set()
        current["queries"] = {row.get("query") or ""}
        by_doi[doi] = current
    else:
        current["sources"].add(row.get("source") or "")
        current["topics"].add(row.get("topic") or "")
        current["k_domains"].add(row.get("k_domain") or "")
        if row.get("pmid"):
            current["pmids"].add(row["pmid"])
        if row.get("pmcid"):
            current["pmcids"].add(row["pmcid"])
        current["queries"].add(row.get("query") or "")
        # Prefer richer metadata.
        for field in ["title","first_author","authors","year","journal","document_type","abstract","article_link"]:
            if len(str(row.get(field) or "")) > len(str(current.get(field) or "")):
                current[field] = row.get(field)
        try:
            current["cited_by_count"] = max(int(float(current.get("cited_by_count") or 0)), int(float(row.get("cited_by_count") or 0)))
        except Exception:
            pass

unique_doi_rows = []
for doi, row in by_doi.items():
    out = {k:v for k,v in row.items() if k not in {"sources","topics","k_domains","pmids","pmcids","queries"}}
    out["doi"] = doi
    out["sources"] = "; ".join(sorted(x for x in row["sources"] if x))
    out["topics"] = "; ".join(sorted(x for x in row["topics"] if x))
    out["k_domains"] = "; ".join(sorted(x for x in row["k_domains"] if x))
    out["pmids"] = "; ".join(sorted(row["pmids"]))
    out["pmcids"] = "; ".join(sorted(row["pmcids"]))
    out["query_count"] = len(row["queries"])
    if not out.get("article_link"):
        out["article_link"] = "https://doi.org/" + doi
    unique_doi_rows.append(out)

unique_doi_rows.sort(key=lambda x: (x.get("k_domains") or "", -(int(float(x.get("cited_by_count") or 0))), x.get("title") or ""))

source_headers = [
    "topic","topic_name","k_domain","shard","source","source_id","pmid","pmcid","doi","title","first_author",
    "authors","year","journal","document_type","abstract","cited_by_count","is_oa","query","article_link"
]
with (OUT / "B004_S2_2_source_records.csv").open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=source_headers)
    w.writeheader(); w.writerows([{k:r.get(k,"") for k in source_headers} for r in source_unique])

unique_headers = [
    "doi","title","first_author","authors","year","journal","document_type","abstract","cited_by_count","is_oa",
    "sources","topics","k_domains","pmids","pmcids","query_count","article_link"
]
with (OUT / "B004_S2_2_global_unique_doi.csv").open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=unique_headers)
    w.writeheader(); w.writerows([{k:r.get(k,"") for k in unique_headers} for r in unique_doi_rows])

# No-DOI records remain useful as a discovery index.
no_doi = [r for r in source_unique if not (r.get("doi") or "").strip()]
with (OUT / "B004_S2_2_no_doi_records.csv").open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=source_headers)
    w.writeheader(); w.writerows([{k:r.get(k,"") for k in source_headers} for r in no_doi])

# SQLite for future incremental merging.
conn = sqlite3.connect(OUT / "b004_s2_2.sqlite")
conn.execute("DROP TABLE IF EXISTS unique_doi")
conn.execute("DROP TABLE IF EXISTS source_record")
conn.execute("CREATE TABLE unique_doi (doi TEXT PRIMARY KEY, title TEXT, first_author TEXT, authors TEXT, year TEXT, journal TEXT, document_type TEXT, abstract TEXT, cited_by_count INTEGER, is_oa TEXT, sources TEXT, topics TEXT, k_domains TEXT, pmids TEXT, pmcids TEXT, query_count INTEGER, article_link TEXT)")
conn.execute("CREATE TABLE source_record (topic TEXT, topic_name TEXT, k_domain TEXT, shard TEXT, source TEXT, source_id TEXT, pmid TEXT, pmcid TEXT, doi TEXT, title TEXT, first_author TEXT, authors TEXT, year TEXT, journal TEXT, document_type TEXT, abstract TEXT, cited_by_count INTEGER, is_oa TEXT, query TEXT, article_link TEXT)")
conn.executemany(
    "INSERT OR REPLACE INTO unique_doi VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
    [[r.get(h,"") for h in unique_headers] for r in unique_doi_rows]
)
conn.executemany(
    "INSERT INTO source_record VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
    [[r.get(h,"") for h in source_headers] for r in source_unique]
)
conn.commit(); conn.close()

topic_doi_counts = Counter()
topic_source_counts = Counter()
source_counts = Counter(r.get("source") or "" for r in source_unique)
for r in source_unique:
    topic_source_counts[r.get("topic") or ""] += 1
for r in unique_doi_rows:
    for topic in (r.get("topics") or "").split("; "):
        if topic:
            topic_doi_counts[topic] += 1

expected_topics = {f"T{i:02d}" for i in range(1,9)}
missing_topics = sorted(expected_topics - set(topic_source_counts))
small_topics = {t:topic_doi_counts.get(t,0) for t in sorted(expected_topics) if topic_doi_counts.get(t,0) < 500}

success_gate = {
    "raw_occurrences_min": 100000,
    "global_unique_dois_min": 30000,
    "each_topic_unique_dois_min": 500
}
status = "success"
if raw_occurrences < success_gate["raw_occurrences_min"] or len(unique_doi_rows) < success_gate["global_unique_dois_min"] or small_topics:
    status = "failure"

summary = {
    "stage": "S2.2",
    "sources": ["PubMed","EuropePMC"],
    "status": status,
    "shard_csv_files_found": len(csv_files),
    "shard_summary_files_found": len(summary_files),
    "raw_occurrences": raw_occurrences,
    "source_unique_records": len(source_unique),
    "records_with_doi": sum(1 for r in source_unique if (r.get("doi") or "").strip()),
    "records_without_doi": len(no_doi),
    "global_unique_dois": len(unique_doi_rows),
    "source_counts": dict(source_counts),
    "topic_source_counts": dict(topic_source_counts),
    "topic_unique_doi_counts": dict(topic_doi_counts),
    "missing_topics": missing_topics,
    "small_topics": small_topics,
    "success_gate": success_gate,
    "next_stage": "S2.3 citation network, similar-abstract and core-author expansion"
}
(OUT / "run_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
report = [
    "# B004 Stage S2.2 Report",
    "",
    f"- Status: **{status}**",
    f"- Raw occurrences: {raw_occurrences:,}",
    f"- Source-unique records: {len(source_unique):,}",
    f"- Global unique DOIs: {len(unique_doi_rows):,}",
    f"- Records without DOI retained for discovery: {len(no_doi):,}",
    f"- Topic DOI counts: {dict(topic_doi_counts)}",
    "- Next: S2.3 citation network, similar-abstract and core-author expansion"
]
(OUT / "stage_report.md").write_text("\n".join(report), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False), flush=True)
if status != "success":
    raise SystemExit(2)
