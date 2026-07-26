import csv
import json
import os
import re
import time
from collections import defaultdict
from pathlib import Path

import requests

K_DOMAIN = os.environ.get("K_DOMAIN", "").strip()
SHARD = int(os.environ.get("SHARD", "0"))
SHARD_COUNT = int(os.environ.get("SHARD_COUNT", "4"))
PAGES_PER_QUERY = int(os.environ.get("PAGES_PER_QUERY", "8"))

DOMAIN_CORES = {
"K01":["food protein resources composition","food protein proteomics abundance","edible protein source characterization","food protein ingredient composition","food protein biodiversity","novel food protein source","food processing by-product protein","food protein batch variability"],
"K02":["food protein extraction fractionation","protein isolate preparation food","protein concentrate processing","membrane separation food protein","dry fractionation plant protein","wet extraction food protein","protein ingredient powder rehydration","food protein purification"],
"K03":["food protein structure functionality","food protein aggregation solubility","protein emulsion interface food","food protein gel rheology","food protein foaming properties","protein self-assembly food","protein phase separation food","food protein structure digestibility"],
"K04":["food protein processing modification","thermal modification food protein","ultrasound food protein structure","high pressure food protein","pH shifting protein modification","protein glycation food","protein crosslinking food","limited hydrolysis protein functionality"],
"K05":["food protein hydrolysate","enzymatic protein hydrolysate","protein digest food","protein hydrolysate bitterness","protein hydrolysate fractionation","protein hydrolysis kinetics","hydrolyzed protein ingredient","peptide rich hydrolysate"],
"K06":["food derived peptide peptidomics","bioactive peptide food protein","taste peptide food","mineral binding peptide food","food peptide mass spectrometry","fermented food peptide","antimicrobial peptide food","interface active peptide food"],
"K07":["food peptide gastrointestinal digestion","protein digestion peptidomics","bioactive peptide intestinal transport","food peptide bioavailability","dietary peptide human plasma","food peptide tissue exposure","dynamic digestion food protein","food peptide metabolism"],
"K08":["food peptide target mechanism","bioactive peptide direct target","food peptide binding affinity","functional peptide health mechanism","food protein hydrolysate human trial","dietary peptide randomized trial","food peptide causal mechanism","functional protein human evidence"],
"K09":["food protease specificity","food enzyme catalysis protein","peptidase food protein hydrolysis","aminopeptidase food hydrolysate","protease cleavage profiling","immobilized protease food","enzyme membrane reactor protein","food grade protease"],
"K10":["protein design food application","food protein engineering","protein stability design","protein solubility engineering","protein self assembly design","artificial protein precursor","generative protein design food","protein sequence design functionality"],
"K11":["bioactive peptide machine learning","food peptide deep learning","peptide language model","generative peptide design","taste peptide prediction","multi objective peptide design","active learning peptide discovery","food derived peptide AI"],
"K12":["protease engineering specificity","enzyme directed evolution protease","de novo enzyme design hydrolysis","rational protease design","enzyme active site design","protease high throughput screening","food enzyme engineering","computational enzyme design"],
"K13":["recombinant bioactive peptide expression","food grade microbial peptide production","tandem repeat peptide expression","fusion protein peptide production","synthetic biology food peptide","precision fermentation protein peptide","recombinant food protein ingredient","peptide precursor linker design"],
"K14":["bioactive peptide food matrix","functional protein beverage stability","protein gel elderly food","food peptide encapsulation","protein peptide sensory bitterness","high protein food product","food peptide delivery system","protein peptide real food"],
"K15":["food protein proteomics method","food peptidomics LC MS","protein hydrolysate online monitoring","food process digital twin","soft sensor protein hydrolysis","food protein database ontology","targeted peptide quantification","model predictive control food"],
"K16":["food protein allergenicity","protein hydrolysate safety","food enzyme safety","bioactive peptide toxicity","food protein oxidation safety","food protein regulation","protein by-product valorization","protein ingredient life cycle assessment"]}

MATERIALS = [
"milk dairy casein whey lactoferrin","fish marine seafood collagen gelatin","soy pea faba bean chickpea lentil","wheat rice oat barley maize","egg meat chicken bovine porcine","algae seaweed microalgae mushroom","insect single cell protein mycoprotein","mixed protein protein blend by-product"]
METHODS = [
"proteomics mass spectrometry","peptidomics LC-MS/MS","structure spectroscopy microscopy","kinetics reaction network","machine learning deep learning","molecular dynamics docking","fermentation biomanufacturing","membrane separation chromatography"]
FUNCTIONS = [
"solubility emulsification gelation rheology","bone joint osteogenic","blood pressure ACE inhibitory","iron zinc calcium binding","umami saltiness bitterness","antioxidant immune inflammation","glucose lipid obesity","digestion absorption bioavailability"]

if K_DOMAIN not in DOMAIN_CORES or SHARD < 0 or SHARD >= SHARD_COUNT:
    raise SystemExit(f"Invalid K_DOMAIN={K_DOMAIN!r} SHARD={SHARD}")

queries = []
cores = DOMAIN_CORES[K_DOMAIN]
queries.extend(cores)
queries.extend([f"{c} {MATERIALS[i % len(MATERIALS)]}" for i,c in enumerate(cores)])
queries.extend([f"{c} {METHODS[i % len(METHODS)]}" for i,c in enumerate(cores)])
queries.extend([f"{c} {FUNCTIONS[i % len(FUNCTIONS)]}" for i,c in enumerate(cores)])
queries = [q for i,q in enumerate(queries) if i % SHARD_COUNT == SHARD]

session = requests.Session()
session.headers.update({"User-Agent":"B004-food-protein-enzyme-peptide-literature/2.0 (mailto:research@example.com)","Accept":"application/json"})

def clean_doi(value):
    value = str(value or "").strip().lower()
    value = re.sub(r"^https?://(dx\.)?doi\.org/", "", value)
    return value.rstrip(".,;) ")

def get_json(url, params, attempts=7):
    for attempt in range(attempts):
        try:
            response = session.get(url, params=params, timeout=50)
            if response.status_code == 200:
                return response.json()
            if response.status_code in {429,500,502,503,504}:
                time.sleep(1.5 * (attempt + 1))
                continue
            return None
        except Exception:
            time.sleep(1.5 * (attempt + 1))
    return None

def first_author(work):
    authorships = work.get("authorships") or []
    if not authorships:
        return ""
    return ((authorships[0].get("author") or {}).get("display_name") or "").strip()

def journal_name(work):
    primary = work.get("primary_location") or {}
    source = primary.get("source") or {}
    return source.get("display_name") or ""

def landing_page(work):
    primary = work.get("primary_location") or {}
    return primary.get("landing_page_url") or ""

records = {}
raw_occurrences = 0
query_stats = []
for query_index, query in enumerate(queries, 1):
    cursor = "*"
    query_count = 0
    for page in range(PAGES_PER_QUERY):
        params = {
            "search": query,
            "filter": "has_doi:true,from_publication_date:1950-01-01",
            "per-page": 200,
            "cursor": cursor,
            "mailto": "research@example.com",
        }
        data = get_json("https://api.openalex.org/works", params)
        if not data:
            break
        batch = data.get("results") or []
        if not batch:
            break
        raw_occurrences += len(batch)
        query_count += len(batch)
        for work in batch:
            doi = clean_doi(work.get("doi"))
            title = (work.get("title") or "").strip()
            if not doi or not title:
                continue
            item = records.get(doi)
            if item is None:
                item = {
                    "k_domain": K_DOMAIN,
                    "doi": doi,
                    "title": title,
                    "first_author": first_author(work),
                    "year": work.get("publication_year") or "",
                    "journal": journal_name(work),
                    "document_type": work.get("type") or "",
                    "cited_by_count": work.get("cited_by_count") or 0,
                    "is_oa": bool((work.get("open_access") or {}).get("is_oa")),
                    "oa_status": (work.get("open_access") or {}).get("oa_status") or "",
                    "openalex_id": work.get("id") or "",
                    "landing_page": landing_page(work),
                    "queries": set(),
                    "query_hits": 0,
                }
                records[doi] = item
            item["queries"].add(query)
            item["query_hits"] += 1
            if (work.get("cited_by_count") or 0) > item["cited_by_count"]:
                item["cited_by_count"] = work.get("cited_by_count") or 0
        cursor = (data.get("meta") or {}).get("next_cursor")
        if not cursor:
            break
        time.sleep(0.06)
    query_stats.append({"query":query,"occurrences":query_count})
    print("QUERY",K_DOMAIN,SHARD,query_index,len(queries),query_count,len(records),flush=True)

out_dir = Path("out")
out_dir.mkdir(exist_ok=True)
headers = ["k_domain","doi","title","first_author","year","journal","document_type","cited_by_count","is_oa","oa_status","openalex_id","landing_page","query_hits","queries"]
with (out_dir / f"B004_S2_1_{K_DOMAIN}_shard{SHARD}.csv").open("w",encoding="utf-8-sig",newline="") as f:
    writer = csv.DictWriter(f,fieldnames=headers)
    writer.writeheader()
    for item in sorted(records.values(),key=lambda x:(-x["query_hits"],-int(x["cited_by_count"] or 0),str(x["title"]))):
        row = dict(item)
        row["queries"] = " || ".join(sorted(item["queries"]))
        writer.writerow(row)
summary = {
    "k_domain":K_DOMAIN,
    "shard":SHARD,
    "shard_count":SHARD_COUNT,
    "queries":len(queries),
    "pages_per_query":PAGES_PER_QUERY,
    "raw_occurrences":raw_occurrences,
    "unique_dois_in_shard":len(records),
    "query_stats":query_stats,
}
(out_dir / f"B004_S2_1_{K_DOMAIN}_shard{SHARD}_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(summary,ensure_ascii=False),flush=True)
if len(records) < 300:
    raise SystemExit(2)
