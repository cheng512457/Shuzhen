import csv
import html
import json
import os
import re
import time
from pathlib import Path

import requests

K = os.environ.get("K_DOMAIN", "").strip()
STRATUM = os.environ.get("STRATUM", "gap").strip()
PAGES = int(os.environ.get("PAGES_PER_QUERY", "10"))
OUT = Path("out")
OUT.mkdir(exist_ok=True)

QUERIES = {
"K01":["food protein resource proteome composition abundance", "edible protein biodiversity novel food source", "milk fish soy egg meat cereal protein proteomics", "food processing side stream protein characterization", "single cell fungal algae insect food protein", "protein ingredient batch variability authenticity"],
"K02":["food protein extraction fractionation isolate concentrate", "dry fractionation air classification plant protein", "wet extraction alkaline isoelectric food protein", "membrane ultrafiltration diafiltration protein ingredient", "protein powder rehydration wettability dispersibility", "food protein purification chromatography adsorption"],
"K03":["food protein structure techno functionality", "food protein aggregation solubility interface", "protein emulsion foam gel rheology food", "food protein self assembly fibril phase separation", "high concentration protein crowding viscosity", "protein polysaccharide lipid mineral interaction food"],
"K04":["food protein thermal processing structural modification", "ultrasound high pressure shear extrusion food protein", "pH shifting deamidation crosslinking protein food", "protein glycation maillard functional modification", "freeze thaw spray drying food protein structure", "limited enzymatic hydrolysis techno functionality"],
"K05":["food protein hydrolysate enzymatic digest", "protein hydrolysis formation degradation kinetics", "protein hydrolysate bitterness umami flavor", "hydrolysate molecular weight fractionation membrane", "protein hydrolysate powder drying rehydration", "protein hydrolysate batch consistency marker peptide"],
"K06":["food derived peptide peptidomics mass spectrometry", "bioactive peptide food protein sequence identification", "taste umami salty enhancing bitter peptide food", "mineral binding calcium iron zinc peptide", "fermented food peptide quantitative peptidomics", "interface active self assembling food peptide"],
"K07":["food peptide gastrointestinal digestion bioavailability", "dynamic digestion protein peptidomics INFOGEST", "bioactive peptide intestinal transport Caco-2 PepT1", "dietary peptide plasma peptidomics exposure", "food peptide tissue distribution metabolism", "food matrix peptide release absorption"],
"K08":["food peptide direct target mechanism binding", "bioactive peptide SPR MST BLI ITC", "food peptide DARTS CETSA pull down target", "functional protein hydrolysate human randomized trial", "dietary peptide systematic review meta analysis", "bone joint blood pressure mineral peptide mechanism"],
"K09":["food protease specificity cleavage profiling", "peptidase aminopeptidase carboxypeptidase food hydrolysis", "commercial food protease substrate preference", "immobilized protease membrane enzyme reactor food", "food microbial protease discovery stability", "protease kinetics product inhibition high substrate"],
"K10":["food protein engineering sequence design", "protein stability solubility design food application", "protein self assembly interface design", "artificial precursor protein peptide release", "generative protein design RFdiffusion ProteinMPNN food", "protein language model food protein functionality"],
"K11":["food bioactive peptide machine learning", "generative peptide design protein language model", "multi objective peptide optimization activity stability bitterness", "active learning peptide discovery experimental loop", "taste peptide prediction deep learning", "peptide natural release manufacturability constraint"],
"K12":["protease engineering directed evolution specificity", "rational protease design substrate binding pocket", "de novo enzyme design peptide bond hydrolysis", "protease FRET high throughput screening", "enzyme stability engineering food processing", "computational enzyme design catalytic motif scaffold"],
"K13":["recombinant bioactive peptide expression food grade", "tandem repeat peptide precursor linker", "fusion protein short peptide production", "Lactococcus Bacillus yeast peptide expression", "precision fermentation functional protein peptide", "recombinant synthetic natural peptide equivalence"],
"K14":["bioactive peptide real food matrix stability", "functional protein high protein beverage stability", "protein gel elderly dysphagia food", "food peptide encapsulation delivery sensory", "peptide protein polysaccharide matrix interaction", "food processing storage digestion efficacy retention"],
"K15":["food protein peptidomics LC-MS method", "targeted peptide absolute quantification isotope standard", "food protein database ontology evidence standard", "protein hydrolysis online monitoring spectroscopy", "food process digital twin soft sensor", "model predictive control protein hydrolysis"],
"K16":["food protein allergenicity digestion safety", "protein hydrolysate toxicity safety", "food enzyme residual activity safety regulation", "bioactive peptide toxicity allergenicity", "food protein oxidation maillard risk", "protein side stream valorization life cycle techno economic"]}

if K not in QUERIES or STRATUM not in {"gap", "frontier"}:
    raise SystemExit(f"Invalid K_DOMAIN={K} STRATUM={STRATUM}")

excluded_files = list(Path("exclusion_artifact").rglob("B004_157917_excluded_dois.txt"))
if len(excluded_files) != 1:
    raise RuntimeError(f"Expected one exclusion registry, found {len(excluded_files)}")
excluded = {x.strip().lower() for x in excluded_files[0].read_text(encoding="utf-8").splitlines() if x.strip()}
if len(excluded) != 157917:
    raise RuntimeError(f"Unexpected exclusion DOI count: {len(excluded)}")

session = requests.Session()
session.headers.update({"User-Agent":"Shuzhen-B005-literature-expansion/1.0 (mailto:research@example.com)","Accept":"application/json"})

def clean_doi(x):
    x = str(x or "").strip().lower()
    x = re.sub(r"^https?://(dx\.)?doi\.org/", "", x)
    return x.rstrip(".,;) ")

def abstract_text(inv):
    if not inv:
        return ""
    seq=[]
    for word,positions in inv.items():
        for p in positions:
            seq.append((p,word))
    seq.sort()
    return " ".join(w for _,w in seq)

def get_json(params, attempts=7):
    for i in range(attempts):
        try:
            r=session.get("https://api.openalex.org/works",params=params,timeout=50)
            if r.status_code==200:
                return r.json()
            if r.status_code in {429,500,502,503,504}:
                time.sleep(1.2*(i+1)); continue
            return None
        except Exception:
            time.sleep(1.2*(i+1))
    return None

def first_author(work):
    a=work.get("authorships") or []
    return (((a[0].get("author") or {}).get("display_name")) if a else "") or ""

def journal(work):
    return (((work.get("primary_location") or {}).get("source") or {}).get("display_name")) or ""

def landing(work):
    return ((work.get("primary_location") or {}).get("landing_page_url")) or ""

queries=list(QUERIES[K])
if STRATUM=="frontier":
    queries=[q+" 2024 2025 2026" for q in queries] + [q+" artificial intelligence" for q in queries[:3]]
    date_filter="from_publication_date:2023-01-01"
else:
    queries=queries + [q+" review" for q in queries[:3]] + [q+" industrial application" for q in queries[3:]]
    date_filter="from_publication_date:1950-01-01"

records={}
raw_occurrences=0
for qi,query in enumerate(queries,1):
    cursor="*"; qcount=0
    for _ in range(PAGES):
        data=get_json({"search":query,"filter":f"has_doi:true,{date_filter}","per-page":200,"cursor":cursor,"mailto":"research@example.com"})
        if not data:
            break
        batch=data.get("results") or []
        if not batch:
            break
        raw_occurrences += len(batch); qcount += len(batch)
        for work in batch:
            doi=clean_doi(work.get("doi")); title=(work.get("title") or "").strip()
            if not doi or doi in excluded or not title:
                continue
            item=records.get(doi)
            if item is None:
                item={"k_domain":K,"stratum":STRATUM,"doi":doi,"title":title,"first_author":first_author(work),"year":work.get("publication_year") or "","journal":journal(work),"document_type":work.get("type") or "","abstract":abstract_text(work.get("abstract_inverted_index"))[:5000],"cited_by_count":work.get("cited_by_count") or 0,"is_oa":"yes" if bool((work.get("open_access") or {}).get("is_oa")) else "no","openalex_id":work.get("id") or "","article_link":landing(work) or ("https://doi.org/"+doi),"query_hits":0,"queries":set()}
                records[doi]=item
            item["query_hits"] += 1; item["queries"].add(query)
        cursor=(data.get("meta") or {}).get("next_cursor")
        if not cursor: break
        time.sleep(0.05)
    print("QUERY",K,STRATUM,qi,len(queries),qcount,len(records),flush=True)

headers=["k_domain","stratum","doi","title","first_author","year","journal","document_type","abstract","cited_by_count","is_oa","openalex_id","article_link","query_hits","queries"]
out_csv=OUT/f"B005_E1_{K}_{STRATUM}.csv"
with out_csv.open("w",encoding="utf-8-sig",newline="") as f:
    w=csv.DictWriter(f,fieldnames=headers); w.writeheader()
    for item in sorted(records.values(),key=lambda x:(-x["query_hits"],-int(x["cited_by_count"] or 0),x["title"])):
        row=dict(item); row["queries"]=" || ".join(sorted(item["queries"])); w.writerow(row)
summary={"stage":"B005-E1","k_domain":K,"stratum":STRATUM,"queries":len(queries),"pages_per_query":PAGES,"excluded_b004_dois":len(excluded),"raw_occurrences":raw_occurrences,"new_unique_dois":len(records)}
(OUT/f"B005_E1_{K}_{STRATUM}_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(summary,ensure_ascii=False),flush=True)
if len(records)<250:
    raise SystemExit(2)
