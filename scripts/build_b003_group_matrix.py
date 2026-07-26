import csv
import html
import json
import math
import os
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import quote

import requests

GROUP = os.environ.get("GROUP", "").strip()
QUOTAS = {"G1":1100,"G2":1200,"G3":1600,"G4":700,"G5":500,"G6":1500,"G7":1800,"G8":1000,"G9":300,"G10":300}
if GROUP not in QUOTAS:
    raise SystemExit(f"Invalid GROUP={GROUP!r}")

QUERIES = {
"G1":["food protein proteomics peptidomics processing","food protein ingredient structure functionality","milk fish soy collagen protein processing proteomics","food-derived peptide database dataset","food protein digestion mass spectrometry","food protein thermal processing peptide marker","quantitative peptidomics food","food protein batch variability structure"],
"G2":["food-derived bioactive peptide machine learning","bioactive peptide prediction deep learning","protein language model peptide prediction","generative peptide design","taste peptide machine learning","ACE inhibitory peptide artificial intelligence","peptide binder design inverse folding","bioactive peptide active learning"],
"G3":["food protein enzymatic hydrolysis bioactive peptide","food protein peptide release kinetics","time resolved peptidomics hydrolysis","pretreatment protein hydrolysis peptide","sequential multi enzyme hydrolysis food protein","protein structure protease accessibility food","industrial protein hydrolysate process optimization","gastrointestinal digestion peptide release food"],
"G4":["protease specificity profiling mass spectrometry","protease engineering directed evolution specificity","protease substrate peptide library","food protease specificity","de novo protease design","protease cleavage site profiling","FRET protease screening","computational enzyme design peptide bond"],
"G5":["recombinant bioactive peptide expression","food grade bacteria peptide production","tandem repeat peptide expression","SUMO fusion peptide expression","Lactococcus lactis peptide expression","recombinant food-derived peptide","short peptide purification cleavage","food grade microbial bioactive peptide"],
"G6":["food-derived peptide bioavailability human plasma","bioactive peptide intestinal transport Caco-2","collagen peptide human blood oral ingestion","dynamic gastrointestinal digestion peptide","food peptide absorption transport","plasma peptidomics dietary protein","food peptide tissue distribution","human gastric peptidomics food protein"],
"G7":["food-derived peptide target mechanism","osteogenic peptide collagen","bone health bioactive peptide","calcium binding peptide food protein","antihypertensive peptide mechanism","peptide target identification DARTS CETSA","food peptide protein binding affinity","marine peptide osteoblast osteoclast"],
"G8":["bioactive peptide food matrix stability","functional protein ingredient stability","dysphagia protein gel food","3D printing elderly food protein","bioactive peptide encapsulation food","high protein beverage stability","protein emulsion gel functionality","food peptide sensory bitterness matrix"],
"G9":["food processing digital twin","enzymatic hydrolysis online monitoring","food process soft sensor","near infrared protein hydrolysis","model predictive control food processing","bioprocess digital twin food","process analytical technology protein hydrolysate","industrial protein hydrolysis scale up"],
"G10":["collagen peptide randomized controlled trial","milk peptide blood pressure randomized","casein peptide human trial","food-derived peptide clinical trial","precision nutrition dietary intervention","bone joint functional food clinical trial","food peptide human intervention","personalized nutrition response model"]}

TERMS = {
"G1":["proteom","peptidom","protein ingredient","processing","mass spectrometry","database","dataset","structure","digest"],
"G2":["machine learning","deep learning","artificial intelligence","language model","generative","prediction","design","active learning"],
"G3":["hydrolys","enzym","peptide release","kinetic","protease","digestion","pretreatment","sequential"],
"G4":["protease","peptidase","specificity","directed evolution","substrate profiling","cleavage site","enzyme design","fret"],
"G5":["recombinant","expression","food-grade","food grade","lactococcus","fusion","tandem","purification"],
"G6":["bioavailability","absorption","transport","plasma","blood","digestion","intestinal","caco"],
"G7":["osteogenic","bone","joint","target","binding","calcium-binding","calcium binding","mechanism","osteoblast","osteoclast"],
"G8":["matrix","stability","encapsulation","gel","dysphagia","3d print","emulsion","sensory","high protein"],
"G9":["digital twin","online monitoring","soft sensor","process control","near infrared","model predictive","scale-up","scale up"],
"G10":["randomized","clinical trial","human","precision nutrition","intervention","placebo","personalized","response"]}

UNIT_RULES = {
"G1":[("1C",["database","dataset","benchmark","annotation","evidence"]),("1B",["peptidomics","mass spectrometry","digestion","cleavage","processing"]),("1A",["proteomics","structure","ingredient","aggregation","batch"])],
"G2":[("2B",["generative","design","diffusion","inverse folding","language model"]),("2C",["active learning","transfer learning","knowledge graph","target-guided"]),("2A",["prediction","classification","machine learning","deep learning"])],
"G3":[("3B",["kinetic","time-resolved","formation","degradation","reaction network","release"]),("3A",["pretreatment","heat","ultrasound","pressure","accessibility"]),("3C",["sequential","multi-enzyme","scale-up","process optimization","industrial"])],
"G4":[("4C",["de novo","generative enzyme","computational enzyme","catalytic motif"]),("4B",["directed evolution","engineering","redesign","mutation","fret"]),("4A",["specificity","substrate profiling","cleavage site","peptide library"])],
"G5":[("5A",["tandem","fusion","linker","precursor","sumo"]),("5B",["food-grade","food grade","lactococcus","bacillus","yeast","fermentation"]),("5C",["purification","cleavage","equivalence","downstream"])],
"G6":[("6C",["plasma","blood","tissue","human","bioavailability"]),("6B",["caco","transport","intestinal","epithelial","pept1"]),("6A",["digestion","gastric","gastrointestinal","dynamic","infogest"])],
"G7":[("7B",["binding site","conformation","spr","mst","bli","itc","hdx","affinity"]),("7C",["knockout","knockdown","rescue","dose-response","causal","necessity"]),("7A",["osteogenic","bone","joint","osteoblast","osteoclast","target identification"])],
"G8":[("8B",["dysphagia","3d print","swallow","elderly","surimi"]),("8C",["matrix","encapsulation","sensory","bitter","storage","delivery"]),("8A",["high protein","solubility","rheology","emulsion","interface","gel"])],
"G9":[("9A",["online","near infrared","raman","soft sensor","monitoring"]),("9C",["control","scale-up","scale up","economic","model predictive"]),("9B",["digital twin","hybrid model","mechanistic model","digital shadow"])],
"G10":[("10C",["randomized","clinical trial","placebo","intervention"]),("10A",["heterogeneity","phenotype","response variability"]),("10B",["stratification","prediction model","personalized","precision nutrition"])]}

DEFAULT_UNIT = {"G1":"1B","G2":"2A","G3":"3B","G4":"4A","G5":"5B","G6":"6A","G7":"7A","G8":"8C","G9":"9B","G10":"10C"}
FOOD_TERMS = ["food","milk","casein","whey","dairy","lactoferrin","collagen","gelatin","fish","marine","seafood","soy","pea","faba","bean","rice","wheat","oat","egg","meat","chicken","bovine","porcine","surimi","protein hydrolysate","fermented","kefir","nutritional","edible","dietary","food-derived","food derived","bioactive peptide","functional food","protein ingredient"]
EXCLUDE = ["cancer vaccine","tumor vaccine","epitope vaccine","hiv vaccine","malaria vaccine","radioimmunotherapy","opioid drug","venom peptide","amyloid beta","alzheimer","parkinson","sars-cov","covid-19 peptide","peptide-drug conjugate","chemotherapy peptide"]
ALLOWED_TYPES = {"article","review","meta-analysis","systematic-review"}

session = requests.Session()
session.headers.update({"User-Agent":"Shuzhen-food-protein-peptide-database/3.0 (mailto:research@example.com)","Accept":"application/json"})

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
    items = []
    for word, positions in inv.items():
        for p in positions:
            items.append((p, word))
    items.sort()
    return " ".join(word for _, word in items)

def get_json(url, params=None, tries=5):
    for i in range(tries):
        try:
            r = session.get(url, params=params, timeout=40)
            if r.status_code == 200:
                return r.json()
            if r.status_code in {429,500,502,503,504}:
                time.sleep(1.0 + i * 1.2)
                continue
            return None
        except Exception:
            time.sleep(1.0 + i * 1.2)
    return None

def search_openalex(query, pages=6):
    out, cursor = [], "*"
    for _ in range(pages):
        data = get_json("https://api.openalex.org/works", {"search":query,"filter":"has_doi:true,from_publication_date:2000-01-01","per-page":200,"cursor":cursor,"mailto":"research@example.com"})
        if not data:
            break
        batch = data.get("results") or []
        out.extend(batch)
        cursor = (data.get("meta") or {}).get("next_cursor")
        if not batch or not cursor:
            break
        time.sleep(0.06)
    return out

def unit_for(text):
    t = norm(text)
    for unit, kws in UNIT_RULES[GROUP]:
        if any(norm(k) in t for k in kws):
            return unit
    return DEFAULT_UNIT[GROUP]

def score_work(work, query):
    title = work.get("title") or ""
    abstract = abstract_text(work.get("abstract_inverted_index"))
    text = norm(title + " " + abstract)
    if not text or any(x in text for x in EXCLUDE) or (work.get("type") or "") not in ALLOWED_TYPES:
        return -999, [], abstract
    hits = [t for t in TERMS[GROUP] if norm(t) in text]
    if not hits:
        return -999, [], abstract
    foods = [t for t in FOOD_TERMS if norm(t) in text]
    s = len(hits)*2.3 + min(len(foods),4)*1.4 + (0.6 if abstract else -0.5)
    s += min(math.log1p(work.get("cited_by_count") or 0), 5)*0.25
    if GROUP not in {"G2","G4","G7","G9","G10"} and not foods:
        s -= 3.0
    if (work.get("publication_year") or 0) >= 2021:
        s += 0.6
    qhits = [x for x in norm(query).split() if len(x)>4 and x in text]
    s += min(len(qhits), 5)*0.25
    return round(s,3), sorted(set(hits + foods[:4])), abstract

def crossref_check(item):
    data = get_json("https://api.crossref.org/works/" + quote(item["doi"], safe=""), tries=3)
    if not data or data.get("status") != "ok":
        out = dict(item)
        out.update({"crossref_title":"","title_similarity":"","metadata_verified":"OpenAlex DOI/title verified; Crossref unavailable"})
        return out
    msg = data.get("message") or {}
    cr_doi = doi_clean(msg.get("DOI"))
    cr_title = ((msg.get("title") or [""])[0] or "").strip()
    if cr_doi != item["doi"] or not cr_title:
        return None
    similarity = SequenceMatcher(None, norm(item["title"]), norm(cr_title)).ratio()
    if similarity < 0.55:
        return None
    out = dict(item)
    authors = msg.get("author") or []
    if authors:
        out["first_author"] = (authors[0].get("family") or authors[0].get("name") or out["first_author"]).strip()
    dates = (msg.get("published-print") or msg.get("published-online") or msg.get("issued") or {}).get("date-parts") or []
    if dates and dates[0]:
        out["year"] = dates[0][0]
    journals = msg.get("container-title") or []
    if journals and journals[0]:
        out["journal"] = journals[0]
    out.update({"crossref_title":cr_title,"title_similarity":round(similarity,4),"metadata_verified":"Crossref DOI and title matched"})
    return out

excluded_path = Path("data/excluded_b001_b002_dois.txt")
excluded = set()
if excluded_path.exists():
    excluded = {doi_clean(x) for x in excluded_path.read_text(encoding="utf-8").splitlines() if doi_clean(x)}

pool = {}
for query in QUERIES[GROUP]:
    works = search_openalex(query, pages=6)
    print("SEARCH", GROUP, query, len(works), flush=True)
    for work in works:
        doi = doi_clean(work.get("doi"))
        title = (work.get("title") or "").strip()
        if not doi or doi in excluded or not title:
            continue
        sc, matched, abstract = score_work(work, query)
        if sc < 1.2:
            continue
        primary = work.get("primary_location") or {}
        source = primary.get("source") or {}
        authorships = work.get("authorships") or []
        author = "Author"
        if authorships:
            display = ((authorships[0].get("author") or {}).get("display_name") or "").strip()
            author = display.split()[-1] if display else "Author"
        item = {"group":GROUP,"unit":unit_for(title+" "+abstract),"query":query,"doi":doi,"title":title,"abstract":abstract[:3500],"first_author":author,"year":work.get("publication_year") or "","journal":source.get("display_name") or "","openalex_id":work.get("id") or "","type":work.get("type") or "","cited_by_count":work.get("cited_by_count") or 0,"is_oa":"是" if bool((work.get("open_access") or {}).get("is_oa")) else "否","oa_status":(work.get("open_access") or {}).get("oa_status") or "","oa_pdf_url":((work.get("best_oa_location") or {}).get("pdf_url") or ""),"landing_page_url":primary.get("landing_page_url") or "","score":sc,"matched_terms":"; ".join(matched)}
        old = pool.get(doi)
        if old is None or sc > old["score"]:
            pool[doi] = item

candidates = sorted(pool.values(), key=lambda x:(x["score"],x["cited_by_count"],x["year"]), reverse=True)
quota = QUOTAS[GROUP]
reserve = max(250, int(quota*0.25))
validate_n = min(len(candidates), quota + reserve + 800)
candidates = candidates[:validate_n]
print("POOL", GROUP, len(pool), "VALIDATE", len(candidates), flush=True)

verified = []
with ThreadPoolExecutor(max_workers=16) as ex:
    futures = [ex.submit(crossref_check, x) for x in candidates]
    for idx, future in enumerate(as_completed(futures), 1):
        try:
            result = future.result()
        except Exception:
            result = None
        if result:
            verified.append(result)
        if idx % 500 == 0:
            print("VERIFIED_PROGRESS", GROUP, idx, len(verified), flush=True)

verified.sort(key=lambda x:(x["score"],x["cited_by_count"],x["year"]), reverse=True)
target = min(len(verified), quota + reserve)
verified = verified[:target]
for x in verified:
    x["priority"] = "P0" if x["score"] >= 9 else ("P1" if x["score"] >= 5.5 else "P2")
    x["initial_relevance"] = "A" if any(norm(t) in norm(x["title"]+" "+x["abstract"]) for t in FOOD_TERMS) else ("C" if GROUP in {"G4","G9"} else "B")
    x["download_link"] = x["oa_pdf_url"] or x["landing_page_url"] or ("https://doi.org/" + x["doi"])

out_dir = Path("out")
out_dir.mkdir(exist_ok=True)
headers = ["group","unit","priority","initial_relevance","first_author","year","title","journal","doi","type","cited_by_count","is_oa","oa_status","abstract","query","matched_terms","score","crossref_title","title_similarity","metadata_verified","download_link"]
with (out_dir / f"B003_{GROUP}_candidates.csv").open("w", encoding="utf-8-sig", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=headers)
    writer.writeheader()
    writer.writerows([{k:x.get(k,"") for k in headers} for x in verified])
summary = {"group":GROUP,"quota":quota,"pool":len(pool),"validated":len(verified),"unique_dois":len({x['doi'] for x in verified}),"priority_counts":dict(Counter(x['priority'] for x in verified)),"relevance_counts":dict(Counter(x['initial_relevance'] for x in verified))}
(out_dir / f"B003_{GROUP}_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(summary,ensure_ascii=False), flush=True)
if len(verified) < max(100, int(quota*0.6)):
    raise SystemExit(2)
