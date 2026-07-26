import csv
import html
import json
import os
import re
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote

import requests

SHARD = int(os.environ.get("SHARD", "0"))
ROOT = Path("seed_artifact")
OUT = Path("out")
OUT.mkdir(exist_ok=True)

seed_files = list(ROOT.rglob(f"B004_S2_3_seed_shard{SHARD}.csv"))
known_files = list(ROOT.rglob("B004_known_dois.txt"))
if not seed_files or not known_files:
    raise RuntimeError("Missing seed shard or known DOI file")

with seed_files[0].open("r", encoding="utf-8-sig", newline="") as f:
    seeds = list(csv.DictReader(f))
known_dois = {x.strip().lower() for x in known_files[0].read_text(encoding="utf-8").splitlines() if x.strip()}

session = requests.Session()
session.headers.update({
    "User-Agent": "Shuzhen-B004-literature-expansion/1.0 (mailto:research@example.com)",
    "Accept": "application/json",
})

POSITIVE = [
    "food protein","protein hydrolysate","enzymatic hydrolysate","food-derived peptide","bioactive peptide",
    "peptidomics","proteomics","protein ingredient","food enzyme","protease","peptidase","protein digestion",
    "gastrointestinal digestion","peptide absorption","protein design","peptide design","enzyme design",
    "protein engineering","enzyme engineering","biomanufacturing","precision fermentation","food matrix",
    "protein gel","protein emulsion","sensory","allergenicity","functional food","collagen peptide","casein peptide",
    "whey peptide","soy protein","fish protein","marine protein","milk protein","plant protein"
]
HARD_EXCLUDE = [
    "cancer vaccine","tumor vaccine","epitope vaccine","hiv vaccine","malaria vaccine","sars-cov vaccine",
    "peptide-drug conjugate","radioimmunotherapy","opioid drug","venom peptide","conotoxin","chemotherapy peptide"
]
ALLOWED_TYPES = {"article","review","meta-analysis","systematic-review","preprint","book-chapter"}

def norm(x):
    x = html.unescape(str(x or "")).lower()
    x = re.sub(r"<[^>]+>", " ", x)
    x = re.sub(r"[^a-z0-9]+", " ", x)
    return " ".join(x.split())

def doi_clean(x):
    x = str(x or "").strip().lower()
    x = re.sub(r"^https?://(dx\.)?doi\.org/", "", x)
    x = re.sub(r"^doi:\s*", "", x)
    return x.rstrip(".,;) ")

def abstract_text(inv):
    if not inv:
        return ""
    seq = []
    for word, positions in inv.items():
        for p in positions:
            seq.append((p, word))
    seq.sort()
    return " ".join(w for _, w in seq)

def get_json(url, params=None, tries=5):
    for attempt in range(tries):
        try:
            r = session.get(url, params=params, timeout=45)
            if r.status_code == 200:
                return r.json()
            if r.status_code in {429,500,502,503,504}:
                time.sleep(1.0 + attempt * 1.5)
                continue
            return None
        except Exception:
            time.sleep(1.0 + attempt * 1.5)
    return None

def get_seed_work(seed):
    doi = seed["doi"]
    data = get_json("https://api.openalex.org/works/https://doi.org/" + doi, params={"mailto":"research@example.com"}, tries=5)
    if not data or not data.get("id"):
        return None
    return data

resolved = []
with ThreadPoolExecutor(max_workers=8) as ex:
    futures = {ex.submit(get_seed_work, s): s for s in seeds}
    for idx, fut in enumerate(as_completed(futures), 1):
        try:
            work = fut.result()
        except Exception:
            work = None
        if work:
            resolved.append((futures[fut], work))
        if idx % 100 == 0:
            print("SEED_PROGRESS", SHARD, idx, len(resolved), flush=True)

candidate = defaultdict(lambda: {"relation_count":0,"relation_types":set(),"seed_dois":set(),"author_ids":set()})
author_counts = Counter()
for seed, work in resolved:
    seed_doi = seed["doi"]
    for wid in (work.get("referenced_works") or [])[:30]:
        item = candidate[wid]; item["relation_count"] += 1; item["relation_types"].add("reference"); item["seed_dois"].add(seed_doi)
    for wid in (work.get("related_works") or [])[:20]:
        item = candidate[wid]; item["relation_count"] += 1; item["relation_types"].add("related"); item["seed_dois"].add(seed_doi)
    for auth in work.get("authorships") or []:
        aid = ((auth.get("author") or {}).get("id") or "").strip()
        if aid:
            author_counts[aid] += 1

# Add highly cited works from recurring seed authors.
def author_works(aid):
    data = get_json("https://api.openalex.org/works", params={
        "filter": f"authorships.author.id:{aid},has_doi:true,from_publication_date:1990-01-01",
        "sort": "cited_by_count:desc",
        "per-page": 100,
        "mailto": "research@example.com",
    }, tries=5)
    return aid, (data.get("results") or []) if data else []

top_authors = [aid for aid, _ in author_counts.most_common(60)]
with ThreadPoolExecutor(max_workers=6) as ex:
    futures = [ex.submit(author_works, aid) for aid in top_authors]
    for fut in as_completed(futures):
        try:
            aid, works = fut.result()
        except Exception:
            continue
        for work in works:
            wid = work.get("id") or ""
            if not wid:
                continue
            item = candidate[wid]; item["relation_count"] += 1; item["relation_types"].add("core_author"); item["author_ids"].add(aid)

# Fetch metadata for the strongest expansion candidates.
ranked_ids = sorted(candidate, key=lambda wid: (
    candidate[wid]["relation_count"],
    1 if "core_author" in candidate[wid]["relation_types"] else 0,
    1 if "related" in candidate[wid]["relation_types"] else 0,
), reverse=True)[:2500]

def get_work(wid):
    data = get_json(wid.replace("https://openalex.org/", "https://api.openalex.org/works/"), params={"mailto":"research@example.com"}, tries=5)
    return wid, data

fetched = []
with ThreadPoolExecutor(max_workers=8) as ex:
    futures = [ex.submit(get_work, wid) for wid in ranked_ids]
    for idx, fut in enumerate(as_completed(futures), 1):
        try:
            wid, work = fut.result()
        except Exception:
            continue
        if work:
            fetched.append((wid, work))
        if idx % 250 == 0:
            print("CANDIDATE_PROGRESS", SHARD, idx, len(fetched), flush=True)

rows = []
for wid, work in fetched:
    doi = doi_clean(work.get("doi"))
    title = (work.get("title") or "").strip()
    if not doi or doi in known_dois or not title:
        continue
    if (work.get("type") or "") not in ALLOWED_TYPES:
        continue
    abstract = abstract_text(work.get("abstract_inverted_index"))
    text = norm(title + " " + abstract)
    if any(term in text for term in HARD_EXCLUDE):
        continue
    positive_hits = [term for term in POSITIVE if norm(term) in text]
    rel = candidate[wid]
    # Citation/author network candidates may have sparse abstracts; require either a positive hit or repeated network support.
    if not positive_hits and rel["relation_count"] < 2:
        continue
    primary = work.get("primary_location") or {}
    source = primary.get("source") or {}
    authorships = work.get("authorships") or []
    first_author = ""
    if authorships:
        first_author = ((authorships[0].get("author") or {}).get("display_name") or "").strip()
    rows.append({
        "shard": SHARD,
        "doi": doi,
        "title": title,
        "first_author": first_author,
        "year": work.get("publication_year") or "",
        "journal": source.get("display_name") or "",
        "document_type": work.get("type") or "",
        "abstract": abstract[:5000],
        "cited_by_count": work.get("cited_by_count") or 0,
        "is_oa": "yes" if bool((work.get("open_access") or {}).get("is_oa")) else "no",
        "openalex_id": wid,
        "relation_count": rel["relation_count"],
        "relation_types": "; ".join(sorted(rel["relation_types"])),
        "seed_dois": "; ".join(sorted(rel["seed_dois"])[:20]),
        "core_author_ids": "; ".join(sorted(rel["author_ids"])),
        "positive_hits": "; ".join(positive_hits),
        "article_link": primary.get("landing_page_url") or ("https://doi.org/" + doi),
    })

# DOI de-duplication within shard, retaining richer/highly cited record.
by_doi = {}
for row in rows:
    old = by_doi.get(row["doi"])
    key = (int(row["relation_count"]), int(row["cited_by_count"] or 0), len(row["abstract"]))
    if old is None or key > (int(old["relation_count"]), int(old["cited_by_count"] or 0), len(old["abstract"])):
        by_doi[row["doi"]] = row
rows = sorted(by_doi.values(), key=lambda r: (int(r["relation_count"]), int(r["cited_by_count"] or 0)), reverse=True)
headers = ["shard","doi","title","first_author","year","journal","document_type","abstract","cited_by_count","is_oa","openalex_id","relation_count","relation_types","seed_dois","core_author_ids","positive_hits","article_link"]
with (OUT / f"B004_S2_3_shard{SHARD}.csv").open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=headers)
    w.writeheader(); w.writerows(rows)
summary = {
    "stage":"S2.3",
    "shard":SHARD,
    "seeds_input":len(seeds),
    "seeds_resolved":len(resolved),
    "core_authors":len(top_authors),
    "candidate_openalex_ids":len(candidate),
    "candidate_ids_fetched":len(fetched),
    "new_unique_dois":len(rows),
    "relation_type_counts":dict(Counter(t for r in rows for t in r["relation_types"].split("; ") if t)),
}
(OUT / f"B004_S2_3_shard{SHARD}_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(summary,ensure_ascii=False),flush=True)
if len(resolved) < 400 or len(rows) < 500:
    raise SystemExit(2)
