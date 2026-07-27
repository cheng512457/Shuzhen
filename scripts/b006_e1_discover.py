import csv
import html
import json
import math
import os
import re
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote

import requests

K = os.environ.get("K_DOMAIN", "").strip()
STRATEGY = os.environ.get("STRATEGY", "precision").strip()
OUT = Path("out")
OUT.mkdir(exist_ok=True)
VALID_K = {f"K{i:02d}" for i in range(1, 17)}
if K not in VALID_K or STRATEGY not in {"precision", "frontier", "network"}:
    raise SystemExit(f"Invalid K_DOMAIN={K} STRATEGY={STRATEGY}")

QUERIES = {
"K01":["food protein proteome quantitative composition ingredient", "milk whey casein protein profile batch processing", "fish marine seafood protein proteomics by-product", "soy pea bean cereal protein composition proteomics", "collagen gelatin bone skin scale protein characterization", "algae fungi insect single cell food protein composition", "food protein ingredient authenticity batch variability", "food side stream protein resource characterization"],
"K02":["food protein extraction isolate concentrate functionality", "plant protein dry fractionation air classification", "food protein wet extraction isoelectric precipitation", "protein ingredient membrane ultrafiltration diafiltration", "protein powder wettability rehydration dispersibility", "food protein purification adsorption chromatography", "protein fractionation yield purity techno functionality", "food protein extraction environmental impact process"],
"K03":["food protein structure solubility aggregation functionality", "food protein emulsion interfacial adsorption", "food protein gel rheology viscoelasticity", "food protein foam stability structure", "food protein phase separation self assembly", "high concentration food protein viscosity crowding", "protein polysaccharide lipid interaction food structure", "food protein fibril nanofibril edible assembly"],
"K04":["food protein heat treatment structure functionality", "ultrasound high pressure food protein modification", "pH shifting food protein structure solubility", "extrusion shear food protein conformation", "food protein glycation maillard functionality", "transglutaminase deamidation food protein modification", "spray drying freeze drying food protein structure", "limited hydrolysis food protein techno functionality"],
"K05":["food protein hydrolysate peptide profile composition", "enzymatic hydrolysis peptide formation degradation kinetics", "food protein hydrolysate bitterness debittering", "protein hydrolysate umami flavor sensory", "hydrolysate molecular weight membrane fractionation", "protein hydrolysate drying rehydration stability", "protein hydrolysate batch consistency marker peptide", "high substrate concentration protein hydrolysis process"],
"K06":["food derived peptide peptidomics identification", "quantitative food peptidomics mass spectrometry", "bioactive peptide food protein sequence validation", "umami salt enhancing taste peptide food", "calcium iron zinc mineral binding peptide food", "fermented food peptide peptidomics", "collagen milk fish soy peptide sequence", "interface active self assembling food peptide"],
"K07":["food peptide gastrointestinal digestion bioavailability", "dynamic digestion food protein peptidomics", "food peptide intestinal transport Caco-2 PepT1", "dietary peptide plasma peptidomics", "food derived peptide tissue distribution metabolism", "food matrix peptide release absorption", "human plasma peptide dietary protein ingestion", "older adult protein digestion peptide exposure"],
"K08":["food derived peptide direct target binding mechanism", "bioactive peptide surface plasmon resonance target", "food peptide DARTS CETSA target identification", "protein hydrolysate randomized controlled trial", "dietary peptide human intervention trial", "food peptide systematic review meta analysis", "bone joint collagen peptide mechanism target", "antihypertensive mineral binding peptide mechanism"],
"K09":["food protease specificity cleavage profiling", "protease substrate specificity peptide library", "aminopeptidase carboxypeptidase food hydrolysis", "commercial protease food protein peptide profile", "food microbial protease discovery stability", "immobilized protease membrane enzyme reactor food", "protease kinetics product inhibition protein hydrolysis", "food protease inactivation residual activity"],
"K10":["food protein engineering structure functionality", "protein stability solubility sequence design", "protein self assembly interface computational design", "artificial precursor protein peptide release design", "generative protein design RFdiffusion ProteinMPNN", "protein language model sequence functionality", "de novo protein design binding assembly", "computational design edible food protein"],
"K11":["food bioactive peptide machine learning prediction", "generative peptide design protein language model", "peptide sequence optimization activity stability", "active learning peptide discovery experimental", "taste peptide prediction deep learning", "peptide manufacturability natural release constraint", "multi objective bioactive peptide design", "peptide diffusion model generative sequence"],
"K12":["protease engineering directed evolution specificity", "rational protease design substrate pocket", "de novo enzyme design peptide bond hydrolysis", "protease FRET peptide library high throughput", "enzyme stability engineering food processing", "computational enzyme design catalytic motif", "machine learning protease substrate specificity", "designed hydrolase protease catalytic activity"],
"K13":["recombinant bioactive peptide expression food grade", "tandem repeat peptide precursor linker", "fusion protein short peptide production", "Bacillus yeast Lactococcus peptide expression", "precision fermentation functional protein peptide", "cell free peptide expression production", "recombinant peptide purification enzymatic release", "recombinant synthetic natural peptide equivalence"],
"K14":["bioactive peptide real food matrix stability", "functional protein high protein beverage stability", "protein gel elderly dysphagia food", "food peptide encapsulation delivery sensory", "peptide protein polysaccharide matrix interaction", "food processing storage digestion efficacy retention", "protein peptide bitterness masking food", "functional peptide emulsion gel food application"],
"K15":["food protein peptidomics LC-MS method", "targeted peptide absolute quantification isotope", "food protein database ontology evidence standard", "protein hydrolysis online monitoring spectroscopy", "food process digital twin soft sensor", "model predictive control protein hydrolysis", "near infrared Raman protein hydrolysate monitoring", "process analytical technology food protein"],
"K16":["food protein allergenicity digestion safety", "protein hydrolysate toxicity safety", "food enzyme residual activity regulation", "bioactive peptide toxicity allergenicity", "food protein oxidation maillard reaction risk", "protein side stream valorization life cycle", "food protein techno economic analysis", "novel food protein regulatory risk assessment"]}

ROOT = Path("prepare_artifact")
excluded_files = list(ROOT.rglob("B004_B005_226220_excluded_dois.txt"))
seed_files = list(ROOT.rglob(f"B006_E1_seeds_{K}.csv"))
if len(excluded_files) != 1 or len(seed_files) != 1:
    raise RuntimeError(f"Missing registry or seed file: registry={len(excluded_files)} seeds={len(seed_files)}")
excluded = {x.strip().lower() for x in excluded_files[0].read_text(encoding="utf-8").splitlines() if x.strip()}
if len(excluded) != 226220:
    raise RuntimeError(f"Unexpected exclusion DOI count {len(excluded)}")
with seed_files[0].open("r", encoding="utf-8-sig", newline="") as f:
    seeds = list(csv.DictReader(f))

terms = json.loads(Path("data/b004_s3_2_terms.json").read_text(encoding="utf-8"))
domain_terms = terms[K]

FOOD_TERMS = [
    "food", "edible", "dietary", "nutrition", "nutritional", "ingredient", "beverage", "dairy", "milk", "casein", "whey", "lactoferrin", "egg", "meat", "fish", "marine", "seafood", "oyster", "shrimp", "collagen", "gelatin", "soy", "soybean", "pea", "bean", "rice", "wheat", "oat", "barley", "maize", "cereal", "algae", "seaweed", "mushroom", "mycoprotein", "insect protein", "surimi", "fermented food", "protein hydrolysate", "food derived", "food-derived"
]
OBJECT_ROOTS = ["protein", "peptid", "hydrolys", "proteas", "peptidas", "enzyme", "digest", "ferment", "amino acid"]
DESIGN_ROOTS = ["design", "engineer", "generative", "language model", "directed evolution", "mutagen", "inverse folding", "diffusion"]
HARD_EXCLUDE = [
    "cancer vaccine", "tumor vaccine", "epitope vaccine", "hiv vaccine", "malaria vaccine", "sars cov vaccine", "peptide drug conjugate", "radioimmunotherapy", "opioid drug", "venom peptide", "conotoxin", "chemotherapy peptide", "car t", "therapeutic antibody"
]
ALLOWED_TYPES = {"article", "review", "meta-analysis", "systematic-review", "preprint", "book-chapter"}
word_re = re.compile(r"[^a-z0-9]+")

session = requests.Session()
session.headers.update({"User-Agent": "Shuzhen-B006-high-precision-expansion/1.0 (mailto:research@example.com)", "Accept": "application/json"})

def norm(value):
    return " ".join(word_re.sub(" ", html.unescape(str(value or "")).lower()).split())

def clean_doi(value):
    x = str(value or "").strip().lower()
    x = re.sub(r"^https?://(dx\.)?doi\.org/", "", x)
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

def has_phrase(text, phrase):
    p = norm(phrase)
    return bool(p and (" " + p + " ") in (" " + text + " "))

def root_hits(text, roots):
    return sorted({root for root in roots if root in text})

def phrase_hits(text, phrases):
    return [p for p in phrases if has_phrase(text, p)]

def get_json(url, params=None, attempts=6):
    for i in range(attempts):
        try:
            r = session.get(url, params=params, timeout=50)
            if r.status_code == 200:
                return r.json()
            if r.status_code in {429, 500, 502, 503, 504}:
                time.sleep(1.1 * (i + 1))
                continue
            return None
        except Exception:
            time.sleep(1.1 * (i + 1))
    return None

def first_author(work):
    a = work.get("authorships") or []
    return (((a[0].get("author") or {}).get("display_name")) if a else "") or ""

def journal(work):
    return (((work.get("primary_location") or {}).get("source") or {}).get("display_name")) or ""

def landing(work):
    return ((work.get("primary_location") or {}).get("landing_page_url")) or ""

def evaluate(work, query="", relation_count=0, relation_types=None, seed_dois=None):
    doi = clean_doi(work.get("doi"))
    title_raw = (work.get("title") or "").strip()
    if not doi or doi in excluded or not title_raw:
        return None
    if (work.get("type") or "") not in ALLOWED_TYPES:
        return None
    abstract_raw = abstract_text(work.get("abstract_inverted_index"))
    title = norm(title_raw)
    abstract = norm(abstract_raw)
    journal_text = norm(journal(work))
    combined = " ".join([title, abstract, journal_text])
    if any(has_phrase(combined, x) for x in HARD_EXCLUDE):
        return None
    t_domain = phrase_hits(title, domain_terms)
    a_domain = phrase_hits(abstract, domain_terms)
    t_food = phrase_hits(title, FOOD_TERMS)
    a_food = phrase_hits(abstract, FOOD_TERMS)
    t_obj = root_hits(title, OBJECT_ROOTS)
    a_obj = root_hits(abstract, OBJECT_ROOTS)
    design = root_hits(combined, DESIGN_ROOTS)
    object_ok = bool(t_obj or a_obj)
    food_ok = bool(t_food or a_food)
    domain_ok = bool(t_domain) or len(a_domain) >= 2
    if K in {"K10", "K11", "K12"}:
        transfer_ok = object_ok and bool(design) and domain_ok
    elif K == "K15":
        transfer_ok = object_ok and domain_ok
    else:
        transfer_ok = object_ok and food_ok and domain_ok
    if not transfer_ok:
        return None
    score = len(t_domain) * 4.0 + min(len(a_domain), 8) * 1.35
    score += min(len(t_food), 4) * 2.5 + min(len(a_food), 6) * 0.75
    score += min(len(t_obj), 4) * 1.5 + min(len(a_obj), 5) * 0.45
    score += min(len(design), 3) * (0.8 if K in {"K10", "K11", "K12", "K15"} else 0.2)
    score += min(math.log1p(max(relation_count, 0)), 3.5)
    if abstract_raw:
        score += 0.5
    if query:
        qtokens = [x for x in norm(query).split() if len(x) >= 5]
        score += min(sum(1 for x in qtokens if x in combined), 5) * 0.2
    minimum = 7.0 if STRATEGY in {"precision", "frontier"} else 6.0
    if score < minimum:
        return None
    primary = work.get("primary_location") or {}
    return {
        "k_domain": K,
        "strategy": STRATEGY,
        "doi": doi,
        "title": title_raw,
        "first_author": first_author(work),
        "year": work.get("publication_year") or "",
        "journal": journal(work),
        "document_type": work.get("type") or "",
        "abstract": abstract_raw[:6000],
        "cited_by_count": work.get("cited_by_count") or 0,
        "is_oa": "yes" if bool((work.get("open_access") or {}).get("is_oa")) else "no",
        "openalex_id": work.get("id") or "",
        "article_link": landing(work) or ("https://doi.org/" + doi),
        "query": query,
        "relation_count": relation_count,
        "relation_types": "; ".join(sorted(relation_types or [])),
        "seed_dois": "; ".join(sorted(seed_dois or [])[:30]),
        "precision_score": round(score, 4),
        "title_domain_hits": "; ".join(t_domain[:10]),
        "abstract_domain_hits": "; ".join(a_domain[:12]),
        "food_hits": "; ".join((t_food + [x for x in a_food if x not in t_food])[:12]),
        "object_hits": "; ".join(sorted(set(t_obj + a_obj))),
        "design_hits": "; ".join(design),
        "evidence_mode": "title+abstract" if abstract_raw and t_domain else ("title" if t_domain else "abstract-multi-hit"),
    }

def search_strategy():
    records = {}
    raw_occurrences = 0
    queries = list(QUERIES[K])
    if STRATEGY == "frontier":
        date_filter = "from_publication_date:2023-01-01"
        queries = [q + " 2024 2025 2026" for q in queries]
        pages = 10
    else:
        date_filter = "from_publication_date:1950-01-01"
        queries = queries + [q + " industrial application" for q in queries[:4]]
        pages = 12
    for qi, query in enumerate(queries, 1):
        cursor = "*"
        for _ in range(pages):
            data = get_json("https://api.openalex.org/works", {
                "search": query,
                "filter": f"has_doi:true,{date_filter}",
                "per-page": 200,
                "cursor": cursor,
                "mailto": "research@example.com",
            })
            if not data:
                break
            batch = data.get("results") or []
            if not batch:
                break
            raw_occurrences += len(batch)
            for work in batch:
                row = evaluate(work, query=query)
                if not row:
                    continue
                old = records.get(row["doi"])
                if old is None or (row["precision_score"], int(row["cited_by_count"] or 0)) > (old["precision_score"], int(old["cited_by_count"] or 0)):
                    records[row["doi"]] = row
            cursor = (data.get("meta") or {}).get("next_cursor")
            if not cursor:
                break
            time.sleep(0.05)
        print("SEARCH_PROGRESS", K, STRATEGY, qi, len(queries), raw_occurrences, len(records), flush=True)
    return records, {"raw_occurrences": raw_occurrences, "queries": len(queries)}

def fetch_seed(seed):
    oid = (seed.get("openalex_id") or "").strip()
    if oid:
        url = oid.replace("https://openalex.org/", "https://api.openalex.org/works/")
    else:
        url = "https://api.openalex.org/works/https://doi.org/" + quote(seed["doi"], safe="/:.")
    return seed, get_json(url, {"mailto": "research@example.com"})

def fetch_work_id(wid):
    url = wid.replace("https://openalex.org/", "https://api.openalex.org/works/")
    return wid, get_json(url, {"mailto": "research@example.com"})

def author_works(aid):
    data = get_json("https://api.openalex.org/works", {
        "filter": f"authorships.author.id:{aid},has_doi:true,from_publication_date:1990-01-01",
        "sort": "cited_by_count:desc",
        "per-page": 100,
        "mailto": "research@example.com",
    })
    return aid, (data.get("results") or []) if data else []

def network_strategy():
    resolved = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = [ex.submit(fetch_seed, seed) for seed in seeds]
        for idx, fut in enumerate(as_completed(futures), 1):
            try:
                seed, work = fut.result()
            except Exception:
                continue
            if work and work.get("id"):
                resolved.append((seed, work))
            if idx % 100 == 0:
                print("SEED_PROGRESS", K, idx, len(resolved), flush=True)
    candidates = defaultdict(lambda: {"count": 0, "types": set(), "seeds": set()})
    author_counts = Counter()
    for seed, work in resolved:
        sdoi = seed["doi"]
        for wid in (work.get("referenced_works") or [])[:25]:
            c = candidates[wid]; c["count"] += 1; c["types"].add("reference"); c["seeds"].add(sdoi)
        for wid in (work.get("related_works") or [])[:20]:
            c = candidates[wid]; c["count"] += 1; c["types"].add("related"); c["seeds"].add(sdoi)
        for auth in work.get("authorships") or []:
            aid = ((auth.get("author") or {}).get("id") or "").strip()
            if aid:
                author_counts[aid] += 1
    top_authors = [aid for aid, _ in author_counts.most_common(50)]
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
                c = candidates[wid]; c["count"] += 1; c["types"].add("core_author")
    ranked_ids = sorted(candidates, key=lambda wid: (candidates[wid]["count"], "related" in candidates[wid]["types"], "core_author" in candidates[wid]["types"]), reverse=True)[:3000]
    fetched = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = [ex.submit(fetch_work_id, wid) for wid in ranked_ids]
        for idx, fut in enumerate(as_completed(futures), 1):
            try:
                wid, work = fut.result()
            except Exception:
                continue
            if work:
                fetched.append((wid, work))
            if idx % 300 == 0:
                print("NETWORK_FETCH_PROGRESS", K, idx, len(fetched), flush=True)
    records = {}
    for wid, work in fetched:
        meta = candidates[wid]
        row = evaluate(work, relation_count=meta["count"], relation_types=meta["types"], seed_dois=meta["seeds"])
        if not row:
            continue
        old = records.get(row["doi"])
        if old is None or (row["precision_score"], int(row["cited_by_count"] or 0)) > (old["precision_score"], int(old["cited_by_count"] or 0)):
            records[row["doi"]] = row
    return records, {
        "seeds_input": len(seeds),
        "seeds_resolved": len(resolved),
        "candidate_openalex_ids": len(candidates),
        "candidate_ids_fetched": len(fetched),
        "core_authors": len(top_authors),
    }

if STRATEGY == "network":
    records, extra_summary = network_strategy()
else:
    records, extra_summary = search_strategy()

headers = [
    "k_domain", "strategy", "doi", "title", "first_author", "year", "journal", "document_type", "abstract",
    "cited_by_count", "is_oa", "openalex_id", "article_link", "query", "relation_count", "relation_types",
    "seed_dois", "precision_score", "title_domain_hits", "abstract_domain_hits", "food_hits", "object_hits",
    "design_hits", "evidence_mode"
]
with (OUT / f"B006_E1_{K}_{STRATEGY}.csv").open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=headers)
    w.writeheader()
    w.writerows([{h: row.get(h, "") for h in headers} for row in sorted(records.values(), key=lambda r: (r["precision_score"], int(r["cited_by_count"] or 0)), reverse=True)])
summary = {
    "stage": "B006-E1",
    "k_domain": K,
    "strategy": STRATEGY,
    "excluded_prior_dois": len(excluded),
    "new_high_precision_unique_dois": len(records),
    "evidence_mode_counts": dict(Counter(r["evidence_mode"] for r in records.values())),
    "score_min": min((r["precision_score"] for r in records.values()), default=0),
    "score_median_approx": sorted([r["precision_score"] for r in records.values()])[len(records)//2] if records else 0,
    **extra_summary,
}
(OUT / f"B006_E1_{K}_{STRATEGY}_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False), flush=True)
minimum = 150 if STRATEGY == "network" else 300
if len(records) < minimum:
    raise SystemExit(2)
