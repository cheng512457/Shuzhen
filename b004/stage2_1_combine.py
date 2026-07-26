import csv
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path("stage2_1_artifacts")
OUT = Path("out")
OUT.mkdir(exist_ok=True)
DB = OUT / "b004_s2_1.sqlite"
if DB.exists():
    DB.unlink()
conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("""CREATE TABLE domain_doi (
    k_domain TEXT NOT NULL,
    doi TEXT NOT NULL,
    title TEXT,
    first_author TEXT,
    year TEXT,
    journal TEXT,
    document_type TEXT,
    cited_by_count INTEGER,
    is_oa TEXT,
    oa_status TEXT,
    openalex_id TEXT,
    landing_page TEXT,
    query_hits INTEGER,
    queries TEXT,
    PRIMARY KEY (k_domain, doi)
)""")
cur.execute("""CREATE TABLE global_doi (
    doi TEXT PRIMARY KEY,
    title TEXT,
    first_author TEXT,
    year TEXT,
    journal TEXT,
    document_type TEXT,
    cited_by_count INTEGER,
    is_oa TEXT,
    oa_status TEXT,
    openalex_id TEXT,
    landing_page TEXT,
    primary_k_domain TEXT,
    k_domains TEXT,
    total_query_hits INTEGER,
    queries TEXT
)""")

summary_files = list(ROOT.rglob("*_summary.json"))
csv_files = list(ROOT.rglob("B004_S2_1_K*_shard*.csv"))
raw_occurrences = 0
shard_summaries = []
for path in summary_files:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        continue
    shard_summaries.append(data)
    raw_occurrences += int(data.get("raw_occurrences") or 0)

input_rows = 0
for path in csv_files:
    with path.open("r",encoding="utf-8-sig",newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            input_rows += 1
            doi = (row.get("doi") or "").strip().lower()
            domain = (row.get("k_domain") or "").strip()
            if not doi or not domain:
                continue
            values = (
                domain, doi, row.get("title") or "", row.get("first_author") or "", row.get("year") or "",
                row.get("journal") or "", row.get("document_type") or "", int(float(row.get("cited_by_count") or 0)),
                row.get("is_oa") or "", row.get("oa_status") or "", row.get("openalex_id") or "",
                row.get("landing_page") or "", int(float(row.get("query_hits") or 0)), row.get("queries") or ""
            )
            cur.execute("SELECT query_hits,queries,cited_by_count FROM domain_doi WHERE k_domain=? AND doi=?",(domain,doi))
            old = cur.fetchone()
            if old is None:
                cur.execute("INSERT INTO domain_doi VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",values)
            else:
                hits = int(old[0] or 0) + values[12]
                queries = " || ".join(sorted(set((old[1] or "").split(" || ") + (values[13] or "").split(" || "))))
                cited = max(int(old[2] or 0), values[7])
                cur.execute("UPDATE domain_doi SET query_hits=?,queries=?,cited_by_count=? WHERE k_domain=? AND doi=?",(hits,queries,cited,domain,doi))
conn.commit()

# Build global DOI table from domain-level rows.
cur.execute("SELECT * FROM domain_doi ORDER BY doi,k_domain")
current_doi = None
bucket = []

def flush_bucket(items):
    if not items:
        return
    best = max(items,key=lambda x:(int(x[12] or 0),int(x[7] or 0),x[0]))
    domains = sorted({x[0] for x in items})
    queries = sorted({q for x in items for q in (x[13] or "").split(" || ") if q})
    total_hits = sum(int(x[12] or 0) for x in items)
    cur.execute("INSERT OR REPLACE INTO global_doi VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(
        best[1],best[2],best[3],best[4],best[5],best[6],best[7],best[8],best[9],best[10],best[11],
        best[0],";".join(domains),total_hits," || ".join(queries)
    ))

for row in cur.fetchall():
    doi = row[1]
    if current_doi is None:
        current_doi = doi
    if doi != current_doi:
        flush_bucket(bucket)
        bucket = []
        current_doi = doi
    bucket.append(row)
flush_bucket(bucket)
conn.commit()

# Counts.
domain_counts = {row[0]:row[1] for row in cur.execute("SELECT k_domain,COUNT(*) FROM domain_doi GROUP BY k_domain ORDER BY k_domain")}
domain_query_hits = {row[0]:row[1] for row in cur.execute("SELECT k_domain,SUM(query_hits) FROM domain_doi GROUP BY k_domain ORDER BY k_domain")}
domain_doi_rows = cur.execute("SELECT COUNT(*) FROM domain_doi").fetchone()[0]
global_unique = cur.execute("SELECT COUNT(*) FROM global_doi").fetchone()[0]
overlap_counts = Counter()
for (domains,) in cur.execute("SELECT k_domains FROM global_doi"):
    overlap_counts[len((domains or "").split(";"))] += 1

# Export domain DOI candidates.
domain_headers = ["k_domain","doi","title","first_author","year","journal","document_type","cited_by_count","is_oa","oa_status","openalex_id","landing_page","query_hits","queries"]
with (OUT/"B004_S2_1_domain_doi_candidates.csv").open("w",encoding="utf-8-sig",newline="") as f:
    w=csv.writer(f);w.writerow(domain_headers)
    for row in cur.execute("SELECT k_domain,doi,title,first_author,year,journal,document_type,cited_by_count,is_oa,oa_status,openalex_id,landing_page,query_hits,queries FROM domain_doi ORDER BY k_domain,query_hits DESC,cited_by_count DESC"):
        w.writerow(row)

global_headers = ["doi","title","first_author","year","journal","document_type","cited_by_count","is_oa","oa_status","openalex_id","landing_page","primary_k_domain","k_domains","total_query_hits","queries"]
with (OUT/"B004_S2_1_global_unique_doi.csv").open("w",encoding="utf-8-sig",newline="") as f:
    w=csv.writer(f);w.writerow(global_headers)
    for row in cur.execute("SELECT doi,title,first_author,year,journal,document_type,cited_by_count,is_oa,oa_status,openalex_id,landing_page,primary_k_domain,k_domains,total_query_hits,queries FROM global_doi ORDER BY total_query_hits DESC,cited_by_count DESC"):
        w.writerow(row)

missing_domains = [f"K{i:02d}" for i in range(1,17) if domain_counts.get(f"K{i:02d}",0)<500]
summary = {
    "stage":"S2.1",
    "source":"OpenAlex",
    "status":"success",
    "artifact_shards_found":len(csv_files),
    "summary_files_found":len(summary_files),
    "raw_occurrences":raw_occurrences,
    "input_shard_unique_rows":input_rows,
    "domain_doi_rows":domain_doi_rows,
    "global_unique_dois":global_unique,
    "domain_counts":domain_counts,
    "domain_query_hits":domain_query_hits,
    "doi_domain_overlap_distribution":dict(sorted(overlap_counts.items())),
    "missing_or_small_domains":missing_domains,
    "success_gate":{
        "raw_occurrences_min":300000,
        "global_unique_dois_min":100000,
        "each_domain_min":500,
    }
}
if raw_occurrences < 300000 or global_unique < 100000 or missing_domains:
    summary["status"]="failure"
summary["next_stage"] = "S2.2 PubMed/Europe PMC health, digestion and human-evidence supplementation" if summary["status"]=="success" else "Repeat S2.1 with more shards/pages and domain-specific query expansion"
(OUT/"run_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
(OUT/"stage_report.md").write_text(
    "# B004 Stage S2.1 Report\n\n"+
    f"- Status: **{summary['status']}**\n"+
    f"- Raw occurrences: {raw_occurrences:,}\n"+
    f"- Domain-DOI rows: {domain_doi_rows:,}\n"+
    f"- Global unique DOIs: {global_unique:,}\n"+
    f"- Shards found: {len(csv_files)}\n"+
    f"- Next: {summary['next_stage']}\n",
    encoding="utf-8"
)
print(json.dumps(summary,ensure_ascii=False),flush=True)
conn.close()
if summary["status"]!="success":
    raise SystemExit(2)
