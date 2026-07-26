import csv
import json
import os
import re
import time
from collections import Counter
from pathlib import Path
from urllib.parse import quote

import requests

TOPIC = os.environ.get("TOPIC", "").strip()
SHARD = int(os.environ.get("SHARD", "0"))

TOPICS = {
    "T01": {
        "k_domain": "K06",
        "name": "Food-derived peptides and peptidomics",
        "queries": [
            '(food protein OR food-derived OR dietary OR milk OR casein OR whey OR collagen OR fish OR soy) AND (bioactive peptide OR peptidomics OR peptide profile)',
            '(protein hydrolysate OR enzymatic hydrolysate OR protein digest) AND (peptide identification OR LC-MS OR mass spectrometry)',
            '(taste peptide OR umami peptide OR bitter peptide OR mineral-binding peptide OR calcium-binding peptide OR iron-binding peptide OR zinc-binding peptide)',
            '(fermented food OR kefir OR cheese OR fish sauce) AND (peptide OR peptidomics)',
            '(antimicrobial peptide OR antioxidant peptide OR ACE inhibitory peptide) AND (food-derived OR dietary protein)',
            '(food protein) AND (targeted peptidomics OR quantitative peptidomics OR peptide biomarker)'
        ]
    },
    "T02": {
        "k_domain": "K07",
        "name": "Digestion absorption exposure metabolism",
        "queries": [
            '(food protein OR dietary protein OR protein hydrolysate OR bioactive peptide) AND (gastrointestinal digestion OR INFOGEST OR gastric digestion)',
            '(food-derived peptide OR dietary peptide) AND (intestinal transport OR Caco-2 OR PepT1 OR transepithelial)',
            '(collagen peptide OR milk peptide OR casein peptide OR food-derived peptide) AND (plasma OR blood OR bioavailability)',
            '(dietary peptide OR food peptide) AND (tissue distribution OR metabolism OR metabolite OR exposure)',
            '(older adult OR elderly OR ageing) AND (protein digestion OR peptide absorption OR gastric emptying)',
            '(food matrix) AND (peptide release OR peptide absorption OR protein digestion)'
        ]
    },
    "T03": {
        "k_domain": "K08",
        "name": "Direct targets binding and causal mechanisms",
        "queries": [
            '(food-derived peptide OR bioactive peptide OR dietary peptide) AND (target identification OR direct target OR pull-down OR DARTS OR CETSA)',
            '(food-derived peptide OR bioactive peptide) AND (SPR OR surface plasmon resonance OR MST OR microscale thermophoresis OR BLI OR ITC)',
            '(osteogenic peptide OR bone peptide OR collagen peptide) AND (osteoblast OR osteoclast OR cartilage OR joint)',
            '(ACE inhibitory peptide OR antihypertensive peptide) AND (mechanism OR endothelial OR vascular OR renin)',
            '(mineral-binding peptide OR calcium-binding peptide OR iron-binding peptide OR zinc-binding peptide) AND (transport OR bioavailability OR target)',
            '(bioactive peptide) AND (knockout OR knockdown OR rescue experiment OR causal mechanism)'
        ]
    },
    "T04": {
        "k_domain": "K08",
        "name": "Human interventions and evidence synthesis",
        "queries": [
            '(collagen peptide OR milk peptide OR casein peptide OR whey peptide OR protein hydrolysate) AND (randomized controlled trial OR placebo controlled)',
            '(food-derived peptide OR bioactive peptide OR dietary protein hydrolysate) AND (clinical trial OR human intervention)',
            '(collagen hydrolysate OR gelatin hydrolysate) AND (joint OR bone OR osteoarthritis) AND (trial OR meta-analysis)',
            '(milk-derived peptide OR lactotripeptide OR casein hydrolysate) AND (blood pressure OR hypertension) AND (trial OR meta-analysis)',
            '(iron peptide OR zinc peptide OR calcium peptide OR mineral-binding peptide) AND (human OR clinical OR bioavailability)',
            '(functional food OR high protein food OR peptide supplement) AND (systematic review OR meta-analysis OR randomized)'
        ]
    },
    "T05": {
        "k_domain": "K11",
        "name": "Protein peptide enzyme design methods",
        "queries": [
            '(peptide design OR protein design OR enzyme design) AND (machine learning OR deep learning OR protein language model)',
            '(bioactive peptide prediction OR peptide activity prediction) AND (artificial intelligence OR neural network)',
            '(generative peptide design OR de novo peptide design OR diffusion model peptide) AND (bioactivity OR binding)',
            '(protein engineering OR enzyme engineering OR protease engineering) AND (directed evolution OR rational design)',
            '(de novo enzyme OR computational enzyme design OR catalytic design) AND (hydrolase OR protease OR peptidase)',
            '(active learning OR transfer learning OR knowledge graph) AND (peptide OR protein OR enzyme design)'
        ]
    },
    "T06": {
        "k_domain": "K13",
        "name": "Biomanufacturing synthetic biology and expression",
        "queries": [
            '(recombinant peptide OR bioactive peptide expression OR short peptide expression) AND (fusion protein OR tandem repeat)',
            '(food-grade microorganism OR Lactococcus lactis OR Bacillus subtilis OR yeast) AND (peptide production OR protein expression)',
            '(multi-copy peptide precursor OR tandem peptide precursor OR linker design) AND (expression OR cleavage)',
            '(cell-free protein synthesis OR precision fermentation) AND (peptide OR food protein)',
            '(recombinant collagen peptide OR recombinant food-derived peptide) AND (purification OR equivalence)',
            '(intein OR SUMO fusion OR TEV cleavage) AND (short peptide OR bioactive peptide)'
        ]
    },
    "T07": {
        "k_domain": "K14",
        "name": "Real foods sensory delivery and matrix effects",
        "queries": [
            '(bioactive peptide OR protein hydrolysate) AND (food matrix OR beverage OR emulsion OR gel)',
            '(protein hydrolysate OR peptide) AND (bitterness OR bitter taste OR sensory OR masking)',
            '(bioactive peptide OR dietary peptide) AND (encapsulation OR microencapsulation OR delivery system)',
            '(high protein food OR high protein beverage OR protein gel) AND (stability OR digestion OR sensory)',
            '(dysphagia food OR texture modified food OR elderly food) AND (protein OR peptide OR gel)',
            '(food processing OR storage) AND (peptide stability OR bioactivity retention OR peptide release)'
        ]
    },
    "T08": {
        "k_domain": "K16",
        "name": "Safety allergenicity regulation and sustainability",
        "queries": [
            '(food protein OR protein hydrolysate OR peptide) AND (allergenicity OR allergen OR immunogenicity)',
            '(protein hydrolysate OR bioactive peptide OR food enzyme) AND (toxicity OR safety assessment OR cytotoxicity)',
            '(food enzyme OR protease preparation OR peptidase) AND (safety OR residual enzyme OR inactivation)',
            '(food protein processing OR protein hydrolysate) AND (oxidation OR Maillard reaction OR harmful product)',
            '(food protein by-product OR protein side stream OR fish by-product OR dairy by-product) AND (valorization OR sustainability)',
            '(functional food OR bioactive peptide) AND (regulation OR health claim OR risk assessment)'
        ]
    }
}

if TOPIC not in TOPICS or SHARD not in (0, 1):
    raise SystemExit(f"Invalid TOPIC/SHARD: {TOPIC} {SHARD}")

cfg = TOPICS[TOPIC]
queries = cfg["queries"][SHARD::2]
K_DOMAIN = cfg["k_domain"]

session = requests.Session()
session.headers.update({
    "User-Agent": "Shuzhen-B004-literature-database/2.0 (mailto:research@example.com)",
    "Accept": "application/json"
})

DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)

def clean_doi(value):
    text = str(value or "").strip().lower()
    text = re.sub(r"^https?://(dx\.)?doi\.org/", "", text)
    text = re.sub(r"^doi:\s*", "", text)
    match = DOI_RE.search(text)
    if not match:
        return ""
    return match.group(0).rstrip(".,;) ]}").lower()


def get_json(url, params=None, tries=6, pause=1.0):
    for attempt in range(tries):
        try:
            response = session.get(url, params=params, timeout=60)
            if response.status_code == 200:
                return response.json()
            if response.status_code in {429, 500, 502, 503, 504}:
                time.sleep(pause * (attempt + 1))
                continue
            return None
        except Exception:
            time.sleep(pause * (attempt + 1))
    return None


def europe_pmc_search(query, max_pages=8):
    records = []
    cursor = "*"
    for _ in range(max_pages):
        data = get_json(
            "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
            {
                "query": f"({query}) AND FIRST_PDATE:[2000-01-01 TO 2026-12-31]",
                "format": "json",
                "resultType": "core",
                "pageSize": 1000,
                "cursorMark": cursor,
                "email": "research@example.com"
            },
            tries=6,
            pause=1.2
        )
        if not data:
            break
        result_list = (data.get("resultList") or {}).get("result") or []
        if not result_list:
            break
        records.extend(result_list)
        next_cursor = data.get("nextCursorMark")
        if not next_cursor or next_cursor == cursor:
            break
        cursor = next_cursor
        time.sleep(0.12)
    return records


def pubmed_search(query, max_ids=8000):
    search_data = get_json(
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
        {
            "db": "pubmed",
            "term": f"({query}) AND (2000:2026[pdat])",
            "retmode": "json",
            "retmax": max_ids,
            "sort": "relevance",
            "tool": "B004LiteratureDatabase",
            "email": "research@example.com"
        },
        tries=7,
        pause=1.5
    )
    if not search_data:
        return []
    ids = ((search_data.get("esearchresult") or {}).get("idlist") or [])
    summaries = []
    for start in range(0, len(ids), 200):
        batch = ids[start:start+200]
        data = get_json(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
            {
                "db": "pubmed",
                "id": ",".join(batch),
                "retmode": "json",
                "version": "2.0",
                "tool": "B004LiteratureDatabase",
                "email": "research@example.com"
            },
            tries=7,
            pause=1.5
        )
        if data:
            result = data.get("result") or {}
            for uid in result.get("uids") or []:
                item = result.get(uid)
                if item:
                    summaries.append(item)
        time.sleep(0.38)
    return summaries


def epmc_row(item, query):
    return {
        "topic": TOPIC,
        "topic_name": cfg["name"],
        "k_domain": K_DOMAIN,
        "shard": SHARD,
        "source": "EuropePMC",
        "source_id": item.get("id") or item.get("pmid") or item.get("pmcid") or "",
        "pmid": item.get("pmid") or "",
        "pmcid": item.get("pmcid") or "",
        "doi": clean_doi(item.get("doi")),
        "title": item.get("title") or "",
        "first_author": item.get("authorString", "").split(",")[0].strip(),
        "authors": item.get("authorString") or "",
        "year": item.get("pubYear") or "",
        "journal": item.get("journalTitle") or "",
        "document_type": "; ".join(item.get("pubTypeList") or []),
        "abstract": item.get("abstractText") or "",
        "cited_by_count": item.get("citedByCount") or 0,
        "is_oa": item.get("isOpenAccess") or "",
        "query": query,
        "article_link": ("https://doi.org/" + clean_doi(item.get("doi"))) if clean_doi(item.get("doi")) else ("https://europepmc.org/article/MED/" + str(item.get("pmid"))) if item.get("pmid") else ""
    }


def pubmed_doi(item):
    for aid in item.get("articleids") or []:
        if str(aid.get("idtype") or "").lower() == "doi":
            return clean_doi(aid.get("value"))
    for eloc in [item.get("elocationid"), item.get("articleid")]:
        doi = clean_doi(eloc)
        if doi:
            return doi
    return ""


def pubmed_row(item, query):
    doi = pubmed_doi(item)
    authors = item.get("authors") or []
    author_names = [str(a.get("name") or "") for a in authors if a.get("name")]
    return {
        "topic": TOPIC,
        "topic_name": cfg["name"],
        "k_domain": K_DOMAIN,
        "shard": SHARD,
        "source": "PubMed",
        "source_id": item.get("uid") or "",
        "pmid": item.get("uid") or "",
        "pmcid": "",
        "doi": doi,
        "title": item.get("title") or "",
        "first_author": author_names[0] if author_names else "",
        "authors": "; ".join(author_names),
        "year": str(item.get("pubdate") or "")[:4],
        "journal": item.get("fulljournalname") or item.get("source") or "",
        "document_type": "; ".join(item.get("pubtype") or []),
        "abstract": "",
        "cited_by_count": 0,
        "is_oa": "",
        "query": query,
        "article_link": ("https://doi.org/" + doi) if doi else ("https://pubmed.ncbi.nlm.nih.gov/" + str(item.get("uid")) + "/")
    }

rows = []
query_stats = []
raw_occurrences = 0

for query in queries:
    epmc = europe_pmc_search(query)
    raw_occurrences += len(epmc)
    rows.extend(epmc_row(item, query) for item in epmc)
    print("EUROPEPMC", TOPIC, SHARD, len(epmc), query, flush=True)

    pubmed = pubmed_search(query)
    raw_occurrences += len(pubmed)
    rows.extend(pubmed_row(item, query) for item in pubmed)
    print("PUBMED", TOPIC, SHARD, len(pubmed), query, flush=True)

    query_stats.append({"query": query, "europepmc": len(epmc), "pubmed": len(pubmed)})

# Deduplicate by source + source id, while retaining cross-source duplicates for the combine step.
seen = set()
unique_rows = []
for row in rows:
    key = (row["source"], row["source_id"] or row["doi"] or row["title"].lower())
    if key in seen:
        continue
    seen.add(key)
    unique_rows.append(row)

out = Path("out")
out.mkdir(exist_ok=True)
headers = [
    "topic","topic_name","k_domain","shard","source","source_id","pmid","pmcid","doi","title",
    "first_author","authors","year","journal","document_type","abstract","cited_by_count","is_oa","query","article_link"
]
with (out / f"B004_S2_2_{TOPIC}_shard{SHARD}.csv").open("w", encoding="utf-8-sig", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=headers)
    writer.writeheader()
    writer.writerows(unique_rows)

summary = {
    "stage": "S2.2",
    "topic": TOPIC,
    "topic_name": cfg["name"],
    "k_domain": K_DOMAIN,
    "shard": SHARD,
    "queries": queries,
    "query_stats": query_stats,
    "raw_occurrences": raw_occurrences,
    "unique_source_records": len(unique_rows),
    "records_with_doi": sum(1 for r in unique_rows if r["doi"]),
    "unique_dois": len({r["doi"] for r in unique_rows if r["doi"]}),
    "source_counts": dict(Counter(r["source"] for r in unique_rows))
}
(out / f"B004_S2_2_{TOPIC}_shard{SHARD}_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False), flush=True)

if not unique_rows:
    raise SystemExit(2)
