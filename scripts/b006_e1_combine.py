import csv
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(2**31 - 1)

SHARDS = Path("shard_artifacts")
PREPARE = Path("prepare_artifact")
OUT = Path("out")
OUT.mkdir(exist_ok=True)

files = sorted(SHARDS.rglob("B006_E1_K*_*.csv"))
summary_files = sorted(SHARDS.rglob("B006_E1_K*_*_summary.json"))
excluded_files = list(PREPARE.rglob("B004_B005_226220_excluded_dois.txt"))
if len(excluded_files) != 1:
    raise RuntimeError(f"Expected one prior DOI registry, found {len(excluded_files)}")
excluded = {x.strip().lower() for x in excluded_files[0].read_text(encoding="utf-8").splitlines() if x.strip()}
if len(excluded) != 226220:
    raise RuntimeError(f"Unexpected prior DOI count {len(excluded)}")

by_doi = {}
raw_rows = 0
for path in files:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            raw_rows += 1
            doi = (row.get("doi") or "").strip().lower()
            if not doi or doi in excluded:
                continue
            try:
                score = float(row.get("precision_score") or 0)
            except Exception:
                score = 0.0
            try:
                cited = int(float(row.get("cited_by_count") or 0))
            except Exception:
                cited = 0
            current = by_doi.get(doi)
            if current is None:
                current = dict(row)
                current["doi"] = doi
                current["precision_score_max"] = score
                current["precision_score_sum"] = score
                current["source_rows"] = 1
                current["k_domains_set"] = {row.get("k_domain") or ""}
                current["strategies_set"] = {row.get("strategy") or ""}
                current["evidence_modes_set"] = {row.get("evidence_mode") or ""}
                current["queries_set"] = {row.get("query") or ""} if row.get("query") else set()
                current["relation_types_set"] = set(x for x in (row.get("relation_types") or "").split("; ") if x)
                current["seed_dois_set"] = set(x for x in (row.get("seed_dois") or "").split("; ") if x)
                current["cited_by_count"] = cited
                by_doi[doi] = current
            else:
                current["precision_score_max"] = max(current["precision_score_max"], score)
                current["precision_score_sum"] += score
                current["source_rows"] += 1
                current["k_domains_set"].add(row.get("k_domain") or "")
                current["strategies_set"].add(row.get("strategy") or "")
                current["evidence_modes_set"].add(row.get("evidence_mode") or "")
                if row.get("query"):
                    current["queries_set"].add(row.get("query"))
                current["relation_types_set"].update(x for x in (row.get("relation_types") or "").split("; ") if x)
                current["seed_dois_set"].update(x for x in (row.get("seed_dois") or "").split("; ") if x)
                current["cited_by_count"] = max(int(current.get("cited_by_count") or 0), cited)
                if (score, cited, len(row.get("abstract") or "")) > (float(current.get("precision_score") or 0), int(current.get("cited_by_count") or 0), len(current.get("abstract") or "")):
                    for field in ["k_domain", "strategy", "title", "first_author", "year", "journal", "document_type", "abstract", "is_oa", "openalex_id", "article_link", "query", "relation_count", "title_domain_hits", "abstract_domain_hits", "food_hits", "object_hits", "design_hits", "evidence_mode", "precision_score"]:
                        if row.get(field) not in {None, ""}:
                            current[field] = row.get(field)

rows = []
for doi, row in by_doi.items():
    k_domains = sorted(x for x in row["k_domains_set"] if x)
    strategies = sorted(x for x in row["strategies_set"] if x)
    evidence_modes = sorted(x for x in row["evidence_modes_set"] if x)
    max_score = row["precision_score_max"]
    source_rows = row["source_rows"]
    has_title = "title" in " ".join(evidence_modes)
    has_food = bool((row.get("food_hits") or "").strip())
    if has_title and has_food and max_score >= 10:
        candidate_tier = "HP-A"
    elif max_score >= 9 and (has_food or row.get("k_domain") in {"K10", "K11", "K12", "K15"}):
        candidate_tier = "HP-B"
    else:
        candidate_tier = "HP-C"
    out = {k: v for k, v in row.items() if not k.endswith("_set") and k not in {"precision_score_max", "precision_score_sum", "source_rows"}}
    out.update({
        "doi": doi,
        "primary_k_domain": row.get("k_domain") or (k_domains[0] if k_domains else ""),
        "k_domains": "; ".join(k_domains),
        "strategies": "; ".join(strategies),
        "evidence_modes": "; ".join(evidence_modes),
        "queries": " || ".join(sorted(row["queries_set"])),
        "relation_types": "; ".join(sorted(row["relation_types_set"])),
        "seed_dois": "; ".join(sorted(row["seed_dois_set"])[:60]),
        "precision_score_max": round(max_score, 4),
        "precision_score_mean": round(row["precision_score_sum"] / source_rows, 4),
        "source_rows": source_rows,
        "candidate_tier": candidate_tier,
        "prior_overlap": "no",
    })
    rows.append(out)

rows.sort(key=lambda r: (
    {"HP-A": 0, "HP-B": 1, "HP-C": 2}.get(r["candidate_tier"], 9),
    -float(r["precision_score_max"]),
    -int(r["source_rows"]),
    -int(float(r.get("cited_by_count") or 0)),
    r.get("title") or "",
))

headers = [
    "doi", "title", "first_author", "year", "journal", "document_type", "abstract", "cited_by_count", "is_oa",
    "openalex_id", "article_link", "primary_k_domain", "k_domains", "strategies", "candidate_tier",
    "precision_score_max", "precision_score_mean", "source_rows", "evidence_modes", "title_domain_hits",
    "abstract_domain_hits", "food_hits", "object_hits", "design_hits", "queries", "relation_count",
    "relation_types", "seed_dois", "prior_overlap"
]
with (OUT / "B006_E1_new_high_precision_candidates.csv").open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=headers)
    w.writeheader()
    w.writerows([{h: r.get(h, "") for h in headers} for r in rows])

summaries = []
for path in summary_files:
    try:
        summaries.append(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        pass
k_membership = Counter()
primary_k = Counter()
strategy_membership = Counter()
tier_counts = Counter()
for row in rows:
    primary_k[row["primary_k_domain"]] += 1
    tier_counts[row["candidate_tier"]] += 1
    for k in row["k_domains"].split("; "):
        if k:
            k_membership[k] += 1
    for s in row["strategies"].split("; "):
        if s:
            strategy_membership[s] += 1

small = [f"K{i:02d}" for i in range(1, 17) if k_membership.get(f"K{i:02d}", 0) < 250]
overlap = len(set(by_doi) & excluded)
status = "success"
if len(files) < 48 or len(rows) < 20000 or overlap != 0 or small:
    status = "failure"
summary = {
    "stage": "B006-E1",
    "status": status,
    "shard_csv_files_found": len(files),
    "shard_summary_files_found": len(summary_files),
    "raw_high_precision_rows": raw_rows,
    "new_global_unique_dois": len(rows),
    "prior_registry_dois": len(excluded),
    "overlap_with_B004_B005": overlap,
    "candidate_tier_counts": dict(tier_counts),
    "primary_K_counts": dict(primary_k),
    "K_membership_counts": dict(k_membership),
    "strategy_membership_counts": dict(strategy_membership),
    "missing_or_small_K_domains": small,
    "shard_result_counts": {f"{s.get('k_domain')}-{s.get('strategy')}": s.get("new_high_precision_unique_dois", 0) for s in summaries},
    "quality_gate": {
        "all_48_shards": len(files) >= 48,
        "new_unique_dois_min_20000": len(rows) >= 20000,
        "prior_overlap_zero": overlap == 0,
        "each_K_membership_min_250": not small,
    },
    "next_stage": "B006-E2 Crossref/OpenAlex metadata verification, conservative A/B/C classification and stratified precision audit",
}
(OUT / "run_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
(OUT / "stage_report.md").write_text("\n".join([
    "# B006 E1 High-Precision Expansion Report", "",
    f"- Status: **{status}**",
    f"- Prior DOI registry: {len(excluded):,}",
    f"- Raw high-precision rows: {raw_rows:,}",
    f"- New global unique DOIs: {len(rows):,}",
    f"- Prior overlap: {overlap}",
    f"- Candidate tiers: {dict(tier_counts)}",
    f"- K membership counts: {dict(k_membership)}",
    f"- Strategy coverage: {dict(strategy_membership)}",
    f"- Missing/small domains: {small}",
    f"- Next: {summary['next_stage']}",
]), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False), flush=True)
if status != "success":
    raise SystemExit(2)
