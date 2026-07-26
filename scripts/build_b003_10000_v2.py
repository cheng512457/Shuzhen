import csv, json, os, re, time, math, html
from collections import defaultdict, Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher
from datetime import datetime, timezone
from urllib.parse import quote
import requests

GROUP_QUOTAS={"G1":1100,"G2":1200,"G3":1600,"G4":700,"G5":500,"G6":1500,"G7":1800,"G8":1000,"G9":300,"G10":300}
assert sum(GROUP_QUOTAS.values())==10000

GROUP_QUERIES={
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

GROUP_TERMS={
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

UNIT_RULES={
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

FOOD_TERMS=["food","milk","casein","whey","dairy","lactoferrin","collagen","gelatin","fish","marine","seafood","soy","pea","faba","bean","rice","wheat","oat","egg","meat","chicken","bovine","porcine","surimi","protein hydrolysate","fermented","kefir","nutritional","edible","dietary","food-derived","food derived","bioactive peptide","functional food","protein ingredient"]
HARD_EXCLUDE=["cancer vaccine","tumor vaccine","epitope vaccine","hiv vaccine","malaria vaccine","radioimmunotherapy","opioid drug","venom peptide","amyloid beta","alzheimer","parkinson","sars-cov","covid-19 peptide","peptide-drug conjugate","chemotherapy peptide"]
ALLOWED_TYPES={"article","review","meta-analysis","systematic-review"}
STUDENT_ALLOCATION={"Student01":{"G1":1000},"Student02":{"G1":100,"G2":900},"Student03":{"G2":300,"G3":700},"Student04":{"G3":900,"G4":100},"Student05":{"G4":600,"G5":400},"Student06":{"G5":100,"G6":900},"Student07":{"G6":600,"G7":400},"Student08":{"G7":1000},"Student09":{"G7":400,"G8":600},"Student10":{"G8":400,"G9":300,"G10":300}}

UA="Shuzhen-food-protein-peptide-literature-database/2.1 (mailto:research@example.com)"
s=requests.Session();s.headers.update({"User-Agent":UA,"Accept":"application/json,text/html;q=0.9,*/*;q=0.8"})

def norm(x):
 x=html.unescape(str(x or "")).lower();x=re.sub(r"<[^>]+>"," ",x);x=re.sub(r"[^a-z0-9]+"," ",x);return " ".join(x.split())
def doi_clean(x):
 x=str(x or "").strip().lower();x=re.sub(r"^https?://(dx\.)?doi\.org/","",x);x=re.sub(r"^doi:\s*","",x);return x.rstrip(".,;) ")
def abstract(inv):
 if not inv:return ""
 z=[]
 for w,pp in inv.items():
  for p in pp:z.append((p,w))
 z.sort();return " ".join(w for _,w in z)
def get_json(url,params=None,tries=6):
 for i in range(tries):
  try:
   r=s.get(url,params=params,timeout=45)
   if r.status_code==200:return r.json()
   if r.status_code in (429,500,502,503,504):time.sleep(1.2*(i+1));continue
   return None
  except Exception:time.sleep(1.2*(i+1))
 return None
def search_openalex(q,pages=12):
 out=[];cursor="*"
 for _ in range(pages):
  d=get_json("https://api.openalex.org/works",{"search":q,"filter":"has_doi:true,from_publication_date:2000-01-01","per-page":200,"cursor":cursor,"mailto":"research@example.com"})
  if not d:break
  b=d.get("results") or [];out.extend(b);cursor=(d.get("meta") or {}).get("next_cursor")
  if not b or not cursor:break
  time.sleep(.07)
 return out
def score(group,w,q):
 title=w.get("title") or "";ab=abstract(w.get("abstract_inverted_index"));txt=norm(title+" "+ab)
 if not txt or any(x in txt for x in HARD_EXCLUDE) or (w.get("type") or "") not in ALLOWED_TYPES:return -999,[]
 hits=[t for t in GROUP_TERMS[group] if norm(t) in txt]
 if not hits:return -999,[]
 foods=[t for t in FOOD_TERMS if norm(t) in txt]
 sc=len(hits)*2.2+min(len(foods),4)*1.4+(.6 if ab else -.6)+min(math.log1p(w.get("cited_by_count") or 0),5)*.25
 if group not in {"G2","G4","G7","G9","G10"} and not foods:sc-=3
 if (w.get("publication_year") or 0)>=2021:sc+=.6
 return round(sc,3),sorted(set(hits+foods[:4]))
def unit_for(group,text):
 t=norm(text)
 for u,kws in UNIT_RULES[group]:
  if any(norm(k) in t for k in kws):return u
 return {"G1":"1B","G2":"2A","G3":"3B","G4":"4A","G5":"5B","G6":"6A","G7":"7A","G8":"8C","G9":"9B","G10":"10C"}[group]
def sim(a,b):return SequenceMatcher(None,norm(a),norm(b)).ratio()
def crossref(c):
 d=get_json("https://api.crossref.org/works/"+quote(c["doi"],safe=""),tries=5)
 if not d or d.get("status")!="ok":return None
 m=d.get("message") or {};ct=((m.get("title") or [""])[0] or "").strip()
 if doi_clean(m.get("DOI"))!=c["doi"] or not ct or sim(c["title"],ct)<.75:return None
 a=m.get("author") or [];fa=(a[0].get("family") or a[0].get("name") or "").strip() if a else c["first_author"]
 dp=(m.get("published-print") or m.get("published-online") or m.get("issued") or {}).get("date-parts") or [];yr=c["year"]
 if dp and dp[0]:yr=dp[0][0]
 j=((m.get("container-title") or [""])[0] or "").strip()
 o=dict(c);o.update({"crossref_title":ct,"title_similarity":round(sim(c["title"],ct),4),"first_author":fa or "Author","year":yr,"journal":j or c["journal"],"crossref_type":m.get("type") or "","metadata_verified":"Crossref DOI and title matched"});return o
def open_link(c):
 url=c.get("oa_pdf_url") or c.get("landing_page_url") or "https://doi.org/"+c["doi"]
 status=0;final=url
 try:
  r=s.get(url,timeout=18,allow_redirects=True,stream=True,headers={"User-Agent":"Mozilla/5.0 academic literature verification"});status=r.status_code;final=r.url or url;r.close()
 except Exception:pass
 o=dict(c);o["link_http_status"]=status;o["download_link"]=c.get("oa_pdf_url") or final or ("https://doi.org/"+c["doi"]);o["opened_at"]=datetime.now(timezone.utc).isoformat();return o

def safe_author(x):return re.sub(r"[^A-Za-z0-9-]+","",x or "") or "Author"
def tail(doi):
 x=re.sub(r"[^A-Za-z0-9]","",doi);return x[-4:]

with open("data/excluded_b001_b002_dois.txt",encoding="utf-8") as f:EXCLUDED={doi_clean(x) for x in f if doi_clean(x)}

pools=defaultdict(dict)
for g,queries in GROUP_QUERIES.items():
 print("DISCOVERY",g,flush=True)
 for q in queries:
  works=search_openalex(q,12);print(q,len(works),flush=True)
  for w in works:
   doi=doi_clean(w.get("doi"));title=(w.get("title") or "").strip()
   if not doi or doi in EXCLUDED or not title:continue
   sc,h=score(g,w,q)
   if sc<1.5:continue
   p=w.get("primary_location") or {};src=p.get("source") or {};aa=w.get("authorships") or [];fa=((aa[0].get("author") or {}).get("display_name") or "").split()[-1] if aa else "Author"
   item={"group":g,"query":q,"doi":doi,"title":title,"abstract":abstract(w.get("abstract_inverted_index"))[:3500],"year":w.get("publication_year") or "","first_author":fa,"journal":src.get("display_name") or "","openalex_id":w.get("id") or "","openalex_type":w.get("type") or "","cited_by_count":w.get("cited_by_count") or 0,"is_oa":bool((w.get("open_access") or {}).get("is_oa")),"oa_status":(w.get("open_access") or {}).get("oa_status") or "","oa_pdf_url":((w.get("best_oa_location") or {}).get("pdf_url") or ""),"landing_page_url":p.get("landing_page_url") or "","score":sc,"matched_terms":"; ".join(h)}
   old=pools[g].get(doi)
   if old is None or sc>old["score"]:pools[g][doi]=item
  time.sleep(.05)
 print("POOL",g,len(pools[g]),flush=True)

selected=[];used=set(EXCLUDED)
for g in [f"G{i}" for i in range(1,11)]:
 quota=GROUP_QUOTAS[g];cand=sorted([x for x in pools[g].values() if x["doi"] not in used],key=lambda x:(x["score"],x["cited_by_count"],x["year"]),reverse=True)
 verified=[];cursor=0;batch=max(1000,quota*2)
 while len(verified)<quota and cursor<len(cand):
  part=cand[cursor:cursor+batch];cursor+=batch
  with ThreadPoolExecutor(max_workers=20) as ex:
   fs=[ex.submit(crossref,x) for x in part]
   for f in as_completed(fs):
    try:v=f.result()
    except Exception:v=None
    if v and v["doi"] not in used and all(v["doi"]!=z["doi"] for z in verified):verified.append(v)
  verified.sort(key=lambda x:(x["score"],x["cited_by_count"],x["year"]),reverse=True)
  print("VERIFY",g,len(verified),"of",quota,flush=True)
 if len(verified)<quota:
  print("SHORTFALL",g,len(verified),quota,flush=True);raise SystemExit(2)
 pick=verified[:quota]
 for x in pick:
  used.add(x["doi"]);x["unit"]=unit_for(g,x["title"]+" "+x["abstract"]);x["initial_relevance"]="A" if any(norm(t) in norm(x["title"]+" "+x["abstract"]) for t in FOOD_TERMS) else ("C" if g in {"G4","G9"} else "B");x["priority"]="P0" if x["score"]>=9 else ("P1" if x["score"]>=5.5 else "P2")
 selected.extend(pick)

print("OPEN",len(selected),flush=True)
opened=[]
with ThreadPoolExecutor(max_workers=64) as ex:
 fs=[ex.submit(open_link,x) for x in selected]
 for i,f in enumerate(as_completed(fs),1):
  opened.append(f.result())
  if i%1000==0:print("OPENED",i,flush=True)
opened.sort(key=lambda x:(int(x["group"][1:]),x["unit"],{"P0":0,"P1":1,"P2":2}.get(x["priority"],9),-x["score"],-x["cited_by_count"]))
assert len(opened)==10000 and len({x["doi"] for x in opened})==10000
for i,x in enumerate(opened,1):
 bid=f"B003-{i:05d}";x["B003_ID"]=bid;x["pdf_name"]=f"{bid}_{safe_author(x['first_author'])}_{x['year']}_{tail(x['doi'])}.pdf";x["download_status"]="Pending download";x["link_status_note"]="Page opened successfully" if x["link_http_status"]==200 else f"Metadata verified; HTTP {x['link_http_status']} or access restriction"
by_group=defaultdict(list)
for x in opened:by_group[x["group"]].append(x)
student_rows=defaultdict(list);offset=defaultdict(int)
for st,alloc in STUDENT_ALLOCATION.items():
 for g,n in alloc.items():
  part=by_group[g][offset[g]:offset[g]+n];offset[g]+=n
  if len(part)!=n:raise RuntimeError(f"Allocation shortfall {st} {g}")
  student_rows[st].extend(part)
 assert len(student_rows[st])==1000
HEADERS=["B003_ID","学生文件","主课题群","研究单元","下载优先级","初筛相关性","第一作者","年份","论文题目","期刊","DOI","PDF文件命名","文献类型","被引次数","开放获取","OA状态","摘要","发现检索式","匹配关键词","相关性评分","Crossref题名","题名一致度","元数据核验","链接HTTP状态","链接状态说明","链接打开时间","下载状态","文献链接"]
def row(x,st):return {"B003_ID":x["B003_ID"],"学生文件":st,"主课题群":x["group"],"研究单元":x["unit"],"下载优先级":x["priority"],"初筛相关性":x["initial_relevance"],"第一作者":x["first_author"],"年份":x["year"],"论文题目":x["title"],"期刊":x["journal"],"DOI":x["doi"],"PDF文件命名":x["pdf_name"],"文献类型":x["crossref_type"] or x["openalex_type"],"被引次数":x["cited_by_count"],"开放获取":"是" if x["is_oa"] else "否","OA状态":x["oa_status"],"摘要":x["abstract"],"发现检索式":x["query"],"匹配关键词":x["matched_terms"],"相关性评分":x["score"],"Crossref题名":x["crossref_title"],"题名一致度":x["title_similarity"],"元数据核验":x["metadata_verified"],"链接HTTP状态":x["link_http_status"],"链接状态说明":x["link_status_note"],"链接打开时间":x["opened_at"],"下载状态":x["download_status"],"文献链接":x["download_link"]}
os.makedirs("out",exist_ok=True);master=[]
for st in [f"Student{i:02d}" for i in range(1,11)]:
 rr=[row(x,st) for x in student_rows[st]];master+=rr
 with open(f"out/B003_{st}_1000.csv","w",encoding="utf-8-sig",newline="") as f:w=csv.DictWriter(f,fieldnames=HEADERS);w.writeheader();w.writerows(rr)
with open("out/B003_10000_master.csv","w",encoding="utf-8-sig",newline="") as f:w=csv.DictWriter(f,fieldnames=HEADERS);w.writeheader();w.writerows(master)
summary={"generated_at":datetime.now(timezone.utc).isoformat(),"total_records":len(master),"unique_dois":len({r['DOI'] for r in master}),"group_counts":dict(Counter(r['主课题群'] for r in master)),"unit_counts":dict(Counter(r['研究单元'] for r in master)),"student_counts":dict(Counter(r['学生文件'] for r in master)),"http_status_counts":dict(Counter(str(r['链接HTTP状态']) for r in master)),"priority_counts":dict(Counter(r['下载优先级'] for r in master)),"relevance_counts":dict(Counter(r['初筛相关性'] for r in master))}
with open("out/run_summary.json","w",encoding="utf-8") as f:json.dump(summary,f,ensure_ascii=False,indent=2)
print(json.dumps(summary,ensure_ascii=False),flush=True)
