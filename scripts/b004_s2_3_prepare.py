import csv
import json
import math
from collections import defaultdict
from pathlib import Path

ROOT = Path("prior_artifacts")
OUT = Path("out")
OUT.mkdir(exist_ok=True)

s21_files = list(ROOT.rglob("B004_S2_1_global_unique_doi.csv"))
s22_files = list(ROOT.rglob("B004_S2_2_global_unique_doi.csv"))
if not s21_files or not s22_files:
    raise RuntimeError(f"Missing prior stage files: S2.1={len(s21_files)} S2.2={len(s22_files)}")

records = {}
known_dois = set()

def nint(x):
    try:
        return int(float(x or 0))
    except Exception:
        return 0

def score(row):
    citations = nint(row.get("cited_by_count"))
    year = nint(row.get("year"))
    abstract_bonus = 1.5 if row.get("abstract") else 0.0
    recency = max(0, min(3.0, (year - 2015) * 0.18)) if year else 0.0
    return round(math.log1p(citations) * 1.8 + recency + abstract_bonus, 4)

# S2.1: full K01-K16 coverage.
with s21_files[0].open("r", encoding="utf-8-sig", newline="") as f:
    for row in csv.DictReader(f):
        doi = (row.get("doi") or "").strip().lower()
        if not doi:
            continue
        known_dois.add(doi)
        rec = {
            "doi": doi,
            "title": row.get("title") or "",
            "year": row.get("year") or "",
            "cited_by_count": nint(row.get("cited_by_count")),
            "group": row.get("primary_k_domain") or "K00",
            "memberships": row.get("k_domains") or row.get("primary_k_domain") or "K00",
            "source_stage": "S2.1",
            "score": score(row),
        }
        old = records.get(doi)
        if old is None or rec["score"] > old["score"]:
            records[doi] = rec

# S2.2: health, digestion, target, human, design, manufacturing, food and safety topics.
with s22_files[0].open("r", encoding="utf-8-sig", newline="") as f:
    for row in csv.DictReader(f):
        doi = (row.get("doi") or "").strip().lower()
        if not doi:
            continue
        known_dois.add(doi)
        topics = row.get("topics") or "T00"
        group = topics.split("; ")[0] if topics else "T00"
        rec = {
            "doi": doi,
            "title": row.get("title") or "",
            "year": row.get("year") or "",
            "cited_by_count": nint(row.get("cited_by_count")),
            "group": group,
            "memberships": (row.get("topics") or "") + " | " + (row.get("k_domains") or ""),
            "source_stage": "S2.2",
            "score": score(row),
        }
        old = records.get(doi)
        if old is None or rec["score"] > old["score"]:
            records[doi] = rec

by_group = defaultdict(list)
for rec in records.values():
    by_group[rec["group"]].append(rec)
for group in by_group:
    by_group[group].sort(key=lambda x: (x["score"], x["cited_by_count"], x["year"]), reverse=True)

selected = []
used = set()
# 300 seeds from each K-domain and 200 from each T-topic. Then global refill to 6,400.
for group in [f"K{i:02d}" for i in range(1,17)]:
    for rec in by_group.get(group, [])[:300]:
        if rec["doi"] not in used:
            used.add(rec["doi"]); selected.append(rec)
for group in [f"T{i:02d}" for i in range(1,9)]:
    for rec in by_group.get(group, [])[:200]:
        if rec["doi"] not in used:
            used.add(rec["doi"]); selected.append(rec)
all_ranked = sorted(records.values(), key=lambda x: (x["score"], x["cited_by_count"], x["year"]), reverse=True)
for rec in all_ranked:
    if len(selected) >= 6400:
        break
    if rec["doi"] not in used:
        used.add(rec["doi"]); selected.append(rec)
selected = selected[:6400]

headers = ["doi","title","year","cited_by_count","group","memberships","source_stage","score"]
parts = [[] for _ in range(8)]
# Round-robin distributes domains and topics across shards.
for idx, rec in enumerate(selected):
    parts[idx % 8].append(rec)
for shard, rows in enumerate(parts):
    with (OUT / f"B004_S2_3_seed_shard{shard}.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader(); w.writerows(rows)

(OUT / "B004_known_dois.txt").write_text("\n".join(sorted(known_dois)), encoding="utf-8")
summary = {
    "stage": "S2.3-prepare",
    "s2_1_file": str(s21_files[0]),
    "s2_2_file": str(s22_files[0]),
    "known_unique_dois": len(known_dois),
    "eligible_seed_records": len(records),
    "selected_seeds": len(selected),
    "seed_shard_counts": {str(i): len(parts[i]) for i in range(8)},
    "group_counts": {g: sum(1 for r in selected if r["group"] == g) for g in sorted({r["group"] for r in selected})},
}
(OUT / "prepare_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False), flush=True)
if len(selected) < 5000 or len(known_dois) < 300000:
    raise SystemExit(2)
