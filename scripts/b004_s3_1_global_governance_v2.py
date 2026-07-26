import csv
import hashlib
import json
import re
import sqlite3
import unicodedata
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import unquote

ROOT = Path("prior_artifacts")
OUT = Path("out")
OUT.mkdir(exist_ok=True)
DB = OUT / "b004_s3_1.sqlite"
if DB.exists():
    DB.unlink()

DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.I)
RETRACTION_RE = re.compile(r"\b(retract(?:ed|ion)?|withdrawn|withdrawal)\b", re.I)
CORRECTION_RE = re.compile(r"\b(correction|corrigendum|erratum|expression of concern)\b", re.I)
PREPRINT_TYPES = {"preprint", "posted-content"}


def clean_doi(value):
    x = unquote(str(value or "")).strip().lower()
    x = re.sub(r"^doi:\s*", "", x)
    x = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", x)
    x = x.strip().rstrip(".,;:)]}>")
    x = x.lstrip("([{<")
    x = re.sub(r"\s+", "", x)
    return x


def valid_doi(doi):
    return bool(doi and len(doi) <= 255 and DOI_RE.match(doi))


def norm_title(value):
    x = unicodedata.normalize("NFKD", str(value or "")).lower()
    x = "".join(ch for ch in x if not unicodedata.combining(ch))
    x = re.sub(r"<[^>]+>", " ", x)
    x = re.sub(r"[^a-z0-9]+", " ", x)
    return " ".join(x.split())


def integer(value):
    try:
        return int(float(value or 0))
    except Exception:
        return 0


def first_existing(pattern):
    files = list(ROOT.rglob(pattern))
    if not files:
        raise RuntimeError(f"Missing required input: {pattern}")
    return files[0]


def add_set_text(existing, new_value, separators=(";", "|")):
    vals = set()
    for value in [existing, new_value]:
        text = str(value or "")
        for sep in separators:
            text = text.replace(sep, ";")
        vals.update(x.strip() for x in text.split(";") if x.strip())
    return "; ".join(sorted(vals))


def record_score(row):
    title = str(row.get("title") or "")
    abstract = str(row.get("abstract") or "")
    score = 0.0
    score += 25 if title else 0
    score += min(len(title), 250) / 25
    score += 15 if row.get("journal") else 0
    score += 10 if integer(row.get("year")) else 0
    score += 8 if row.get("first_author") else 0
    score += min(len(abstract), 5000) / 500
    score += min(integer(row.get("cited_by_count")), 500) / 100
    dtype = str(row.get("document_type") or "").lower()
    if dtype not in PREPRINT_TYPES:
        score += 5
    score += {"S2.2": 3, "S2.1": 2, "S2.3": 1}.get(row.get("source_stage") or "", 0)
    return score


s21 = first_existing("B004_S2_1_global_unique_doi.csv")
s22 = first_existing("B004_S2_2_global_unique_doi.csv")
s23 = first_existing("B004_S2_3_global_new_unique_doi.csv")
prior_summaries = {}
for stage, folder in [("S2.1", "s2_1"), ("S2.2", "s2_2"), ("S2.3", "s2_3")]:
    paths = list((ROOT / folder).rglob("run_summary.json")) if (ROOT / folder).exists() else []
    if paths:
        try:
            prior_summaries[stage] = json.loads(paths[0].read_text(encoding="utf-8"))
        except Exception:
            pass

conn = sqlite3.connect(DB)
write_cur = conn.cursor()
write_cur.execute("PRAGMA journal_mode=WAL")
write_cur.execute("PRAGMA synchronous=NORMAL")
write_cur.execute("PRAGMA temp_store=FILE")
write_cur.execute("""CREATE TABLE raw_record (
    doi TEXT, doi_valid INTEGER, source_stage TEXT, source_names TEXT, title TEXT, title_norm TEXT,
    first_author TEXT, authors TEXT, year INTEGER, journal TEXT, document_type TEXT, abstract TEXT,
    cited_by_count INTEGER, is_oa TEXT, memberships TEXT, external_ids TEXT, article_link TEXT,
    openalex_id TEXT, input_order INTEGER
)""")
write_cur.execute("CREATE INDEX idx_raw_doi ON raw_record(doi)")

input_counts = Counter()
invalid_examples = []
input_order = 0


def insert_row(stage, row):
    global input_order
    input_order += 1
    doi = clean_doi(row.get("doi"))
    ok = 1 if valid_doi(doi) else 0
    input_counts[f"{stage}_rows"] += 1
    if ok:
        input_counts[f"{stage}_valid_doi_rows"] += 1
    else:
        input_counts[f"{stage}_invalid_doi_rows"] += 1
        if len(invalid_examples) < 200:
            invalid_examples.append({"stage": stage, "raw_doi": row.get("doi") or "", "title": row.get("title") or ""})
    if not doi:
        doi = f"INVALID:{stage}:{input_order}"
    source_names = stage
    memberships = ""
    external_ids = ""
    article_link = row.get("article_link") or row.get("landing_page") or ""
    if stage == "S2.1":
        source_names = "OpenAlex"
        memberships = row.get("k_domains") or row.get("primary_k_domain") or ""
        external_ids = row.get("openalex_id") or ""
    elif stage == "S2.2":
        source_names = row.get("sources") or "PubMed/EuropePMC"
        memberships = add_set_text(row.get("topics"), row.get("k_domains"))
        external_ids = add_set_text(row.get("pmids"), row.get("pmcids"))
    elif stage == "S2.3":
        source_names = "OpenAlex-network-expansion"
        memberships = add_set_text(row.get("relation_types"), row.get("positive_hits"))
        external_ids = row.get("openalex_id") or ""
    write_cur.execute("INSERT INTO raw_record VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
        doi, ok, stage, source_names, row.get("title") or "", norm_title(row.get("title")),
        row.get("first_author") or "", row.get("authors") or "", integer(row.get("year")),
        row.get("journal") or "", row.get("document_type") or "", row.get("abstract") or "",
        integer(row.get("cited_by_count")), row.get("is_oa") or "", memberships, external_ids,
        article_link, row.get("openalex_id") or "", input_order
    ))

for stage, path in [("S2.1", s21), ("S2.2", s22), ("S2.3", s23)]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            insert_row(stage, row)
            if input_order % 50000 == 0:
                conn.commit()
                print("INGEST", input_order, dict(input_counts), flush=True)
conn.commit()

write_cur.execute("""CREATE TABLE doi_registry (
    doi TEXT PRIMARY KEY, title TEXT, title_norm TEXT, first_author TEXT, authors TEXT, year INTEGER,
    journal TEXT, document_type TEXT, abstract TEXT, cited_by_count INTEGER, is_oa TEXT,
    source_stages TEXT, source_names TEXT, memberships TEXT, external_ids TEXT, article_link TEXT,
    openalex_id TEXT, source_record_count INTEGER, metadata_status TEXT, title_consistency REAL,
    integrity_status TEXT, version_group_id TEXT, canonical_in_version_group INTEGER DEFAULT 1,
    alternate_version_dois TEXT DEFAULT ''
)""")

current_doi = None
bucket = []
conflicts = []


def flush_group(group):
    if not group or not group[0][1]:
        return
    doi = group[0][0]
    rows = []
    for g in group:
        rows.append({
            "doi": g[0], "source_stage": g[2], "source_names": g[3], "title": g[4], "title_norm": g[5],
            "first_author": g[6], "authors": g[7], "year": g[8], "journal": g[9], "document_type": g[10],
            "abstract": g[11], "cited_by_count": g[12], "is_oa": g[13], "memberships": g[14],
            "external_ids": g[15], "article_link": g[16], "openalex_id": g[17]
        })
    best = max(rows, key=record_score)
    source_stages = sorted({r["source_stage"] for r in rows if r["source_stage"]})
    source_names = ""
    memberships = ""
    external_ids = ""
    titles = []
    for r in rows:
        source_names = add_set_text(source_names, r["source_names"])
        memberships = add_set_text(memberships, r["memberships"])
        external_ids = add_set_text(external_ids, r["external_ids"])
        if r["title_norm"]:
            titles.append(r["title_norm"])
    consistency = 1.0
    if len(set(titles)) > 1:
        base = best["title_norm"]
        consistency = min(SequenceMatcher(None, base, t).ratio() for t in titles if t)
    if len(source_stages) >= 2 and consistency >= 0.80:
        metadata_status = "V2_multi_source_consistent"
    elif len(source_stages) >= 2:
        metadata_status = "V2_multi_source_title_conflict"
        if len(conflicts) < 10000:
            conflicts.append({
                "doi": doi, "source_stages": "; ".join(source_stages),
                "title_consistency": round(consistency, 4),
                "titles": " || ".join(sorted(set(r["title"] for r in rows if r["title"])))
            })
    elif best["title"] and best["journal"] and best["year"]:
        metadata_status = "V1_trusted_single_source"
    else:
        metadata_status = "V0_incomplete_metadata"
    text = f"{best['title']} {best['document_type']}"
    if RETRACTION_RE.search(text):
        integrity = "retracted_or_withdrawn"
    elif CORRECTION_RE.search(text):
        integrity = "correction_or_concern"
    else:
        integrity = "normal"
    write_cur.execute("INSERT INTO doi_registry VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
        doi, best["title"], best["title_norm"], best["first_author"], best["authors"], best["year"],
        best["journal"], best["document_type"], best["abstract"], max(r["cited_by_count"] for r in rows),
        best["is_oa"], "; ".join(source_stages), source_names, memberships, external_ids,
        best["article_link"] or ("https://doi.org/" + doi), best["openalex_id"], len(rows), metadata_status,
        round(consistency, 4), integrity, "", 1, ""
    ))

read_cur = conn.cursor()
query = "SELECT doi,doi_valid,source_stage,source_names,title,title_norm,first_author,authors,year,journal,document_type,abstract,cited_by_count,is_oa,memberships,external_ids,article_link,openalex_id,input_order FROM raw_record ORDER BY doi,input_order"
for row in read_cur.execute(query):
    doi = row[0]
    if current_doi is None:
        current_doi = doi
    if doi != current_doi:
        flush_group(bucket)
        bucket = []
        current_doi = doi
    bucket.append(row)
flush_group(bucket)
conn.commit()

write_cur.execute("CREATE INDEX idx_registry_title_norm ON doi_registry(title_norm)")
version_groups = 0
version_alternates = 0
version_relations = []
version_candidates = write_cur.execute("SELECT title_norm,COUNT(*) FROM doi_registry WHERE LENGTH(title_norm)>=40 GROUP BY title_norm HAVING COUNT(*)>1").fetchall()
for title_norm, count in version_candidates:
    items = write_cur.execute("SELECT doi,document_type,year,journal,title,metadata_status,cited_by_count FROM doi_registry WHERE title_norm=?", (title_norm,)).fetchall()
    if len(items) < 2:
        continue
    version_groups += 1
    gid = "VG-" + hashlib.sha1(title_norm.encode("utf-8")).hexdigest()[:12]
    def priority(item):
        doi, dtype, year, journal, title, mstatus, cited = item
        dtype_l = (dtype or "").lower()
        non_preprint = 0 if dtype_l in PREPRINT_TYPES or "preprint" in (journal or "").lower() else 1
        complete = 1 if journal and year else 0
        verified = 2 if mstatus.startswith("V2") else (1 if mstatus.startswith("V1") else 0)
        return (non_preprint, verified, complete, int(cited or 0), int(year or 0))
    canonical = max(items, key=priority)
    canonical_doi = canonical[0]
    all_dois = sorted(x[0] for x in items)
    write_cur.execute("UPDATE doi_registry SET version_group_id=?,canonical_in_version_group=1,alternate_version_dois=? WHERE doi=?", (gid, "; ".join(d for d in all_dois if d != canonical_doi), canonical_doi))
    for item in items:
        if item[0] == canonical_doi:
            continue
        version_alternates += 1
        write_cur.execute("UPDATE doi_registry SET version_group_id=?,canonical_in_version_group=0,alternate_version_dois=? WHERE doi=?", (gid, canonical_doi, item[0]))
        version_relations.append({
            "version_group_id": gid, "canonical_doi": canonical_doi, "alternate_doi": item[0],
            "normalized_title": title_norm, "canonical_type": canonical[1], "alternate_type": item[1]
        })
conn.commit()

registry_headers = ["doi","title","first_author","authors","year","journal","document_type","abstract","cited_by_count","is_oa","source_stages","source_names","memberships","external_ids","article_link","openalex_id","source_record_count","metadata_status","title_consistency","integrity_status","version_group_id","canonical_in_version_group","alternate_version_dois"]
select_registry = "SELECT doi,title,first_author,authors,year,journal,document_type,abstract,cited_by_count,is_oa,source_stages,source_names,memberships,external_ids,article_link,openalex_id,source_record_count,metadata_status,title_consistency,integrity_status,version_group_id,canonical_in_version_group,alternate_version_dois FROM doi_registry"
with (OUT / "B004_S3_1_all_unique_doi_registry.csv").open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f); w.writerow(registry_headers)
    for row in write_cur.execute(select_registry + " ORDER BY doi"):
        w.writerow(row)

candidate_where = " WHERE integrity_status='normal' AND metadata_status!='V0_incomplete_metadata' AND canonical_in_version_group=1"
with (OUT / "B004_S3_1_canonical_candidate_pool.csv").open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f); w.writerow(registry_headers)
    for row in write_cur.execute(select_registry + candidate_where + " ORDER BY source_record_count DESC,cited_by_count DESC"):
        w.writerow(row)

with (OUT / "B004_S3_1_version_relations.csv").open("w", encoding="utf-8-sig", newline="") as f:
    headers = ["version_group_id","canonical_doi","alternate_doi","normalized_title","canonical_type","alternate_type"]
    w = csv.DictWriter(f, fieldnames=headers); w.writeheader(); w.writerows(version_relations)
with (OUT / "B004_S3_1_metadata_conflicts.csv").open("w", encoding="utf-8-sig", newline="") as f:
    headers = ["doi","source_stages","title_consistency","titles"]
    w = csv.DictWriter(f, fieldnames=headers); w.writeheader(); w.writerows(conflicts)
with (OUT / "B004_S3_1_invalid_doi_examples.csv").open("w", encoding="utf-8-sig", newline="") as f:
    headers = ["stage","raw_doi","title"]
    w = csv.DictWriter(f, fieldnames=headers); w.writeheader(); w.writerows(invalid_examples)

all_unique = write_cur.execute("SELECT COUNT(*) FROM doi_registry").fetchone()[0]
canonical_candidates = write_cur.execute("SELECT COUNT(*) FROM doi_registry" + candidate_where).fetchone()[0]
status_counts = dict(write_cur.execute("SELECT metadata_status,COUNT(*) FROM doi_registry GROUP BY metadata_status"))
integrity_counts = dict(write_cur.execute("SELECT integrity_status,COUNT(*) FROM doi_registry GROUP BY integrity_status"))
source_stage_counts = dict(write_cur.execute("SELECT source_stages,COUNT(*) FROM doi_registry GROUP BY source_stages"))
missing_title = write_cur.execute("SELECT COUNT(*) FROM doi_registry WHERE title='' OR title IS NULL").fetchone()[0]
missing_journal = write_cur.execute("SELECT COUNT(*) FROM doi_registry WHERE journal='' OR journal IS NULL").fetchone()[0]
invalid_total = sum(v for k, v in input_counts.items() if k.endswith("invalid_doi_rows"))
input_total = sum(input_counts.get(f"{stage}_rows", 0) for stage in ["S2.1", "S2.2", "S2.3"])
invalid_ratio = invalid_total / input_total if input_total else 1.0
missing_title_ratio = missing_title / all_unique if all_unique else 1.0
summary = {
    "stage": "S3.1", "status": "success",
    "input_files": {"S2.1": str(s21), "S2.2": str(s22), "S2.3": str(s23)},
    "prior_stage_summaries": prior_summaries,
    "input_counts": dict(input_counts), "input_total_rows": input_total,
    "invalid_doi_rows": invalid_total, "invalid_doi_ratio": round(invalid_ratio, 6),
    "all_normalized_unique_dois": all_unique, "canonical_candidate_pool": canonical_candidates,
    "metadata_status_counts": status_counts, "integrity_status_counts": integrity_counts,
    "source_stage_combination_counts": source_stage_counts,
    "missing_title": missing_title, "missing_journal": missing_journal,
    "metadata_title_conflicts": len(conflicts), "exact_title_version_groups": version_groups,
    "alternate_versions_removed_from_canonical_pool": version_alternates,
    "success_gate": {
        "all_normalized_unique_dois_min": 350000, "canonical_candidate_pool_min": 350000,
        "invalid_doi_ratio_max": 0.05, "missing_title_ratio_max": 0.01,
        "all_three_stages_present": True
    },
    "next_stage": "S3.2 title-abstract relevance classification, K01-K16 assignment and downloadable-pool prioritization"
}
if all_unique < 350000 or canonical_candidates < 350000 or invalid_ratio > 0.05 or missing_title_ratio > 0.01:
    summary["status"] = "failure"
(OUT / "run_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
report = [
    "# B004 Stage S3.1 Report", "", f"- Status: **{summary['status']}**",
    f"- Input rows: {input_total:,}", f"- Normalized unique DOIs: {all_unique:,}",
    f"- Canonical candidate pool: {canonical_candidates:,}",
    f"- Invalid DOI rows: {invalid_total:,} ({invalid_ratio:.2%})",
    f"- Metadata status: {status_counts}", f"- Integrity status: {integrity_counts}",
    f"- Exact-title version groups: {version_groups:,}",
    f"- Alternate versions excluded from canonical pool: {version_alternates:,}",
    f"- Next: {summary['next_stage']}"
]
(OUT / "stage_report.md").write_text("\n".join(report), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False), flush=True)
conn.commit(); conn.close()
if summary["status"] != "success":
    raise SystemExit(2)
