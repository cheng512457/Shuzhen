import csv, json, os, re, time, math, html
from collections import defaultdict, Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher
from datetime import datetime, timezone
from urllib.parse import quote
import requests

GROUP_QUOTAS={"G1":1100,"G2":1200,"G3":1600,"G4":700,"G5":500,"G6":1500,"G7":1800,"G8":1000,"G9":300,"G10":300}
UNIT_QUOTAS={"1A":350,"1B":450,"1C":300,"2A":500,"2B":400,"2C":300,"3A":450,"3B":750,"3C":400,"4A":300,"4B":250,"4C":150,"5A":200,"5B":180,"5C":120,"6A":500,"6B":450,"6C":550,"7A":700,"7B":500,"7C":600,"8A":350,"8B":350,"8C":300,"9A":120,"9B":100,"9C":80,"10A":100,"10B":80,"10C":120}
assert sum(GROUP_QUOTAS.values())==10000 and sum(UNIT_QUOTAS.values())==10000
UNIT_GROUP={"1A":"G1","1B":"G1","1C":"G1","2A":"G2","2B":"G2","2C":"G2","3A":"G3","3B":"G3","3C":"G3","4A":"G4","4B":"G4","4C":"G4","5A":"G5","5B":"G5","5C":"G5","6A":"G6","6B":"G6","6C":"G6","7A":"G7","7B":"G7","7C":"G7","8A":"G8","8B":"G8","8C":"G8","9A":"G9","9B":"G9","9C":"G9","10A":"G10","10B":"G10","10C":"G10"}
UNIT_ORDER=["7A","7C","7B","6C","6A","6B","3B","3A","3C","2A","2B","2C","1B","1A","1C","8A","8B","8C","4A","4B","4C","5A","5B","5C","10C","10A","10B","9A","9B","9C"]
QUERIES={
"1A":["food protein ingredient batch proteomics structural fingerprint","milk protein ingredient quantitative proteomics processing","fish collagen protein proteomics food processing","soy protein isolate structure aggregation processing","food protein composition abundance structure functionality","food protein ingredient extraction method proteomics"],
"1B":["food protein peptidomics processing digestion mass spectrometry","time resolved peptidomics food protein hydrolysis","thermal processing peptide marker milk food","enzymatic digestion peptidomics food protein","LC-MS food-derived peptide processing","protein structure cleavage accessibility food"],
"1C":["food-derived bioactive peptide database dataset","bioactive peptide benchmark machine learning dataset","food peptide evidence database annotation","negative dataset bioactive peptide prediction","peptide database food protein precursor","bioactive peptide data curation quality"],
"2A":["food-derived bioactive peptide machine learning prediction","ACE inhibitory peptide deep learning prediction","osteogenic peptide prediction machine learning","mineral binding peptide prediction food","taste peptide machine learning classification","protein language model bioactive peptide prediction"],
"2B":["generative peptide design protein language model","multi-objective bioactive peptide design","de novo taste peptide design artificial intelligence","peptide binder design inverse folding","diffusion model peptide design","generative food-derived peptide design"],
"2C":["active learning peptide discovery experiment","target knowledge transfer peptide prediction","bioactive peptide knowledge graph","dry wet lab loop peptide discovery","transfer learning food-derived peptide","target-guided peptide design active learning"],
"3A":["pretreatment food protein hydrolysis bioactive peptides","heat ultrasound high pressure protein digestibility peptide","protein structure accessibility enzymatic hydrolysis food","pH shifting food protein hydrolysis peptides","high pressure homogenization protein hydrolysis peptide","aggregation disaggregation protease accessibility food"],
"3B":["food protein peptide release kinetics","peptide formation degradation reaction network hydrolysis","time-resolved hydrolysis peptidomics","target peptide release kinetics food protein","bioactive peptide generation degradation enzymatic hydrolysis","kinetic model food protein enzymatic hydrolysis peptides"],
"3C":["multi-enzyme sequential hydrolysis food protein","scale-up enzymatic protein hydrolysis bioactive peptides","high substrate concentration protein hydrolysis","marker peptide hydrolysis endpoint","industrial food protein hydrolysate process optimization","membrane reactor protein hydrolysis peptide"],
"4A":["protease specificity profiling mass spectrometry","food-grade protease cleavage site specificity","peptidase substrate profiling peptide library","protease cleavage site profiling proteomics","protease specificity database substrate","food protease substrate specificity"],
"4B":["protease engineering directed evolution specificity","rational design protease substrate specificity","FRET protease high throughput screening","protease specificity redesign mutation","directed evolution peptidase cleavage","enzyme engineering protease selectivity"],
"4C":["de novo protease design artificial intelligence","generative enzyme design protease","computational enzyme design catalytic motif","diffusion model enzyme design catalytic","AI designed protease","de novo enzyme design peptide bond hydrolysis"],
"5A":["tandem repeat bioactive peptide expression","fusion carrier short peptide expression","SUMO fusion peptide expression","linker protease precursor peptide design","multi-copy peptide precursor recombinant","recombinant short peptide tandem expression"],
"5B":["food-grade bacteria bioactive peptide production","Lactococcus lactis peptide expression","Bacillus food-grade peptide expression","yeast short peptide recombinant expression","food-grade microbial peptide production","fermentation recombinant bioactive peptide"],
"5C":["recombinant peptide purification cleavage","recombinant synthetic peptide equivalence","food-grade peptide purification","fusion peptide enzymatic release purification","recombinant bioactive peptide characterization","short peptide downstream processing"],
"6A":["dynamic gastrointestinal digestion bioactive peptide","food matrix peptide digestion peptidomics","human gastric peptidomics food protein","elderly digestion protein peptide","INFOGEST food protein peptide","gastrointestinal digestion food-derived peptide"],
"6B":["bioactive peptide intestinal transport Caco-2","PepT1 food-derived peptide transport","intestinal organoid peptide absorption","mucus barrier peptide transport food","transepithelial transport food peptide","intestinal epithelial uptake bioactive peptide"],
"6C":["food-derived peptide human plasma","collagen peptide blood oral ingestion","food peptide tissue distribution","stable isotope peptide bioavailability","plasma peptidomics dietary protein","human bioavailability food-derived bioactive peptide"],
"7A":["osteogenic peptide food protein target","bone joint bioactive peptide mechanism","collagen peptide osteoblast osteoclast","food-derived peptide target identification","casein peptide bone health mechanism","marine peptide osteogenic"],
"7B":["bioactive peptide binding site conformation","SPR food-derived peptide target","MST BLI ITC bioactive peptide","HDX peptide protein binding site","peptide target structural mechanism food","food peptide molecular binding affinity"],
"7C":["bioactive peptide knockout rescue mechanism","dose exposure effect food peptide","target necessity bioactive peptide","RANKL osteoclast peptide mechanism","genetic intervention food-derived peptide","pharmacological inhibition peptide mechanism"],
"8A":["high concentration food protein ingredient stability","food protein solubility heat salt freeze thaw","protein emulsion gel functionality food","functional protein ingredient rheology","high protein beverage stability","food protein interface gel structure"],
"8B":["dysphagia protein gel food","3D printed elderly food protein","fish surimi gel dysphagia","emulsion gel swallowing food","texture modified high protein food","older adult protein gel food"],
"8C":["bioactive peptide food matrix stability","food peptide bitter taste sensory","bioactive peptide encapsulation food delivery","peptide protein polysaccharide interaction food","food processing storage peptide bioactivity","food-derived peptide matrix release"],
"9A":["online monitoring protein hydrolysis food","near infrared enzymatic hydrolysis protein","Raman food protein process monitoring","soft sensor target peptide process","online LC-MS hydrolysis endpoint","process analytical technology protein hydrolysate"],
"9B":["food processing digital twin","hybrid mechanistic data model food process","bioprocess digital twin protein hydrolysis","digital shadow food bioprocess","mechanistic machine learning food processing","digital twin fermentation food"],
"9C":["model predictive control food processing","scale-up enzymatic hydrolysis reactor","techno-economic protein hydrolysate","closed-loop control enzymatic process","process optimization food protein hydrolysis","industrial scale protein hydrolysate production"],
"10A":["interindividual digestion phenotype food protein","food peptide response heterogeneity human","precision nutrition digestive phenotype","individual variability protein digestion","human response variability functional food","dietary peptide responder phenotype"],
"10B":["personalized nutrition response model functional food","product population matching functional food","stratified nutrition intervention model","precision nutrition prediction food response","personalized functional food recommendation evidence","nutrition phenotype product adaptation"],
"10C":["collagen peptide randomized controlled trial","milk peptide blood pressure randomized trial","casein peptide clinical trial human","bone joint functional food clinical trial","iron zinc peptide human trial","food-derived bioactive peptide placebo controlled trial"]}
UNIT_TERMS={"1A":["proteomics","protein composition","abundance","structure","aggregation","ingredient","extraction"],"1B":["peptidomics","mass spectrometry","digestion","processing","cleavage","peptide marker"],"1C":["database","dataset","benchmark","annotation","evidence","curation"],"2A":["machine learning","deep learning","prediction","classification","language model"],"2B":["generative","design","diffusion","inverse folding","multi-objective","de novo"],"2C":["active learning","transfer learning","knowledge graph","target-guided","dry wet"],"3A":["pretreatment","heat","ultrasound","pressure","accessibility","pH shift","homogenization"],"3B":["kinetic","time-resolved","formation","degradation","reaction network","release"],"3C":["multi-enzyme","sequential","scale-up","high substrate","endpoint","process optimization"],"4A":["protease specificity","substrate profiling","cleavage site","peptidase","peptide library"],"4B":["directed evolution","engineering","redesign","mutation","FRET","specificity"],"4C":["de novo","generative enzyme","computational enzyme","catalytic motif","AI designed"],"5A":["tandem","fusion","linker","precursor","SUMO","multi-copy"],"5B":["food-grade","Lactococcus","Bacillus","yeast","fermentation","microbial"],"5C":["purification","cleavage","equivalence","release","downstream","characterization"],"6A":["digestion","gastric","gastrointestinal","dynamic","INFOGEST","peptidomics"],"6B":["Caco-2","transport","intestinal","epithelial","PepT1","uptake"],"6C":["plasma","blood","tissue","human","bioavailability","stable isotope"],"7A":["osteogenic","bone","joint","osteoblast","osteoclast","target identification"],"7B":["binding site","conformation","SPR","MST","BLI","ITC","HDX","affinity"],"7C":["knockout","knockdown","rescue","dose-response","causal","necessity","pharmacological"],"8A":["high concentration","solubility","stability","rheology","emulsion","interface","gel"],"8B":["dysphagia","3D print","swallow","elderly","texture modified","surimi"],"8C":["matrix","encapsulation","sensory","bitter","storage","delivery","interaction"],"9A":["online monitoring","near infrared","Raman","soft sensor","process analytical","endpoint"],"9B":["digital twin","hybrid model","mechanistic model","digital shadow","machine learning"],"9C":["model predictive","closed-loop","scale-up","techno-economic","industrial","control"],"10A":["heterogeneity","phenotype","individual variability","responder","human response"],"10B":["personalized","stratification","prediction model","product adaptation","precision nutrition"],"10C":["randomized","clinical trial","placebo","human trial","intervention","controlled trial"]}
FOOD_TERMS=["food","milk","casein","whey","dairy","lactoferrin","collagen","gelatin","fish","marine","seafood","soy","pea","faba","bean","rice","wheat","oat","egg","meat","chicken","bovine","porcine","surimi","protein hydrolysate","fermented","kefir","nutritional","edible","dietary","food-derived","food derived","bioactive peptide","functional food","protein ingredient"]
FUNCTION_TERMS=["bone","joint","osteogenic","osteoblast","osteoclast","blood pressure","ACE inhibitory","iron","zinc","calcium","mineral binding","umami","salty","saltiness","taste","dysphagia","older adult","elderly"]
HARD_EXCLUDE=["cancer vaccine","tumor vaccine","epitope vaccine","hiv vaccine","malaria vaccine","radioimmunotherapy","opioid drug","venom peptide","amyloid beta","alzheimer","parkinson","sars-cov","covid-19 peptide","cell penetrating peptide delivery","peptide-drug conjugate","chemotherapy peptide"]
ALLOWED_OPENALEX_TYPES={"article","review","meta-analysis","systematic-review"}
STUDENT_ALLOCATION={"Student01":{"G1":1000},"Student02":{"G1":100,"G2":900},"Student03":{"G2":300,"G3":700},"Student04":{"G3":900,"G4":100},"Student05":{"G4":600,"G5":400},"Student06":{"G5":100,"G6":900},"Student07":{"G6":600,"G7":400},"Student08":{"G7":1000},"Student09":{"G7":400,"G8":600},"Student10":{"G8":400,"G9":300,"G10":300}}
assert all(sum(v.values())==1000 for v in STUDENT_ALLOCATION.values())
UA="Shuzhen-food-protein-peptide-literature-database/2.0 (mailto:research@example.com)"
session=requests.Session();session.headers.update({"User-Agent":UA,"Accept":"application/json,text/html;q=0.9,*/*;q=0.8"})
def norm_text(s):
 s=html.unescape(s or "").lower();s=re.sub(r"<[^>]+>"," ",s);s=re.sub(r"[^a-z0-9]+"," ",s);return " ".join(s.split())
def clean_doi(s):
 if not s:return ""
 s=str(s).strip().lower();s=re.sub(r"^https?://(dx\.)?doi\.org/","",s);s=re.sub(r"^doi:\s*","",s);return s.rstrip(".,;) ")
def abstract_text(inv):
 if not inv:return ""
 pairs=[]
 for word,positions in inv.items():
  for p in positions:pairs.append((p,word))
 pairs.sort();return " ".join(w for _,w in pairs)
def get_json(url,params=None,attempts=6,base_pause=1.0):
 for i in range(attempts):
  try:
   r=session.get(url,params=params,timeout=45)
   if r.status_code==200:return r.json()
   if r.status_code in (429,500,502,503,504):time.sleep(base_pause*(i+1));continue
   return None
  except Exception:time.sleep(base_pause*(i+1))
 return None
def openalex_search(query,max_pages=4):
 results=[];cursor="*"
 for _ in range(max_pages):
  params={"search":query,"filter":"has_doi:true,from_publication_date:2000-01-01","per-page":200,"cursor":cursor,"mailto":"research@example.com"}
  data=get_json("https://api.openalex.org/works",params=params,attempts=6,base_pause=1.2)
  if not data:break
  batch=data.get("results") or [];results.extend(batch);cursor=(data.get("meta") or {}).get("next_cursor")
  if not batch or not cursor:break
  time.sleep(0.08)
 return results
def score_candidate(unit,work,query):
 title=work.get("title") or "";abstract=abstract_text(work.get("abstract_inverted_index"));text=norm_text(title+" "+abstract)
 if not text or any(x in text for x in HARD_EXCLUDE) or (work.get("type") or "") not in ALLOWED_OPENALEX_TYPES:return -999,[]
 terms=UNIT_TERMS[unit];hit_terms=[t for t in terms if norm_text(t) in text]
 if not hit_terms:return -999,[]
 score=len(hit_terms)*2.6;food_hits=[t for t in FOOD_TERMS if norm_text(t) in text];function_hits=[t for t in FUNCTION_TERMS if norm_text(t) in text];group=UNIT_GROUP[unit]
 if group in {"G4","G9"}:score+=min(len(food_hits),3)*0.8
 else:
  if not food_hits and group not in {"G2","G7","G10"}:score-=4.0
  score+=min(len(food_hits),4)*1.5
 score+=min(len(function_hits),3)*0.8;qterms=[x for x in norm_text(query).split() if len(x)>4];score+=min(sum(1 for x in qterms if x in text),6)*0.35
 score+=0.7 if abstract else -0.8;cited=work.get("cited_by_count") or 0;score+=min(math.log1p(cited),5)*0.28;year=work.get("publication_year") or 0
 if year>=2021:score+=0.7
 elif year<2005:score-=0.3
 if group=="G6" and any(x in text for x in ["human","plasma","blood","intestinal","caco"]):score+=1.5
 if group=="G7" and any(x in text for x in ["bone","osteogenic","target","binding"]):score+=1.4
 if group=="G10" and any(x in text for x in ["randomized","placebo","clinical trial","human"]):score+=2.0
 return round(score,3),sorted(set(hit_terms+food_hits[:4]+function_hits[:3]))
def title_similarity(a,b):return SequenceMatcher(None,norm_text(a),norm_text(b)).ratio()
def crossref_validate(c):
 doi=c["doi"];data=get_json("https://api.crossref.org/works/"+quote(doi,safe=""),attempts=6,base_pause=1.5)
 if not data or data.get("status")!="ok":return None
 msg=data.get("message") or {}
 if clean_doi(msg.get("DOI"))!=doi:return None
 cr_title=((msg.get("title") or [""])[0] or "").strip()
 if not cr_title:return None
 sim=title_similarity(c["title"],cr_title)
 if sim<0.78:return None
 authors=msg.get("author") or [];first_author=(authors[0].get("family") or authors[0].get("name") or "").strip() if authors else "";dp=(msg.get("published-print") or msg.get("published-online") or msg.get("issued") or {}).get("date-parts") or [];year=c.get("year") or ""
 if dp and dp[0]:year=dp[0][0]
 journal=((msg.get("container-title") or [""])[0] or "").strip();out=dict(c);out.update({"crossref_title":cr_title,"title_similarity":round(sim,4),"first_author":first_author or c.get("first_author") or "Author","year":year,"journal":journal or c.get("journal") or "","crossref_type":msg.get("type") or "","metadata_verified":"Crossref DOI and title matched"});return out
def open_article_link(c):
 doi_url="https://doi.org/"+c["doi"];candidates=[doi_url]
 if c.get("landing_page_url"):candidates.append(c["landing_page_url"])
 if c.get("oa_pdf_url"):candidates.insert(0,c["oa_pdf_url"])
 last={"status":0,"final_url":doi_url,"opened_url":doi_url,"content_type":"","error":""}
 for url in candidates:
  try:
   r=session.get(url,timeout=25,allow_redirects=True,stream=True,headers={"User-Agent":"Mozilla/5.0 academic literature verification"})
   try:next(r.iter_content(chunk_size=1024),b"")
   except Exception:pass
   status=r.status_code;final=r.url or url;ctype=r.headers.get("content-type","");r.close();last={"status":status,"final_url":final,"opened_url":url,"content_type":ctype,"error":""}
   if status not in (404,410) and status<500:break
  except Exception as e:last={"status":0,"final_url":url,"opened_url":url,"content_type":"","error":str(e)[:200]}
 out=dict(c);out.update({"link_http_status":last["status"],"opened_input_url":last["opened_url"],"opened_final_url":last["final_url"],"opened_content_type":last["content_type"],"link_error":last["error"],"opened_at":datetime.now(timezone.utc).isoformat()})
 if c.get("oa_pdf_url"):out["download_link"]=c["oa_pdf_url"];out["link_type"]="OA PDF"
 elif last["final_url"]:out["download_link"]=last["final_url"];out["link_type"]="DOI/publisher page"
 else:out["download_link"]=doi_url;out["link_type"]="DOI"
 return out
def sanitize_author(s):return re.sub(r"[^A-Za-z0-9-]+","",s or "") or "Author"
def doi_tail(doi):
 s=re.sub(r"[^A-Za-z0-9]","",doi);return s[-4:] if len(s)>=4 else s
with open("data/excluded_b001_b002_dois.txt","r",encoding="utf-8") as f:EXCLUDED={clean_doi(x) for x in f if clean_doi(x)}
unit_pools=defaultdict(dict)
for unit in UNIT_ORDER:
 print("DISCOVERY",unit,"quota",UNIT_QUOTAS[unit],flush=True)
 for q in QUERIES[unit]:
  works=openalex_search(q,max_pages=4);print(" ",q,len(works),flush=True)
  for w in works:
   doi=clean_doi(w.get("doi"))
   if not doi or doi in EXCLUDED:continue
   title=(w.get("title") or "").strip()
   if not title:continue
   score,hits=score_candidate(unit,w,q)
   if score<3.0:continue
   primary=w.get("primary_location") or {};source=primary.get("source") or {};authorships=w.get("authorships") or [];fa=((authorships[0].get("author") or {}).get("display_name") or "").split()[-1] if authorships else ""
   item={"unit":unit,"group":UNIT_GROUP[unit],"query":q,"doi":doi,"title":title,"abstract":abstract_text(w.get("abstract_inverted_index"))[:3500],"year":w.get("publication_year") or "","publication_date":w.get("publication_date") or "","first_author":fa or "Author","journal":source.get("display_name") or "","openalex_id":w.get("id") or "","openalex_type":w.get("type") or "","cited_by_count":w.get("cited_by_count") or 0,"is_oa":bool((w.get("open_access") or {}).get("is_oa")),"oa_status":(w.get("open_access") or {}).get("oa_status") or "","oa_pdf_url":((w.get("best_oa_location") or {}).get("pdf_url") or ""),"landing_page_url":primary.get("landing_page_url") or "","score":score,"matched_terms":"; ".join(hits[:12])}
   prev=unit_pools[unit].get(doi)
   if prev is None or item["score"]>prev["score"]:unit_pools[unit][doi]=item
  time.sleep(0.08)
 vals=list(unit_pools[unit].values());vals.sort(key=lambda x:(x["score"],x["cited_by_count"],x["year"]),reverse=True);unit_pools[unit]=vals;print("POOL",unit,len(vals),flush=True)
selected=[];used=set(EXCLUDED)
for unit in UNIT_ORDER:
 quota=UNIT_QUOTAS[unit];pool=[x for x in unit_pools[unit] if x["doi"] not in used];target_n=min(len(pool),max(quota*3,quota+500));candidates=pool[:target_n];print("VALIDATE",unit,"candidates",len(candidates),"quota",quota,flush=True);validated=[]
 with ThreadPoolExecutor(max_workers=28) as ex:
  futures={ex.submit(crossref_validate,c):c for c in candidates}
  for fut in as_completed(futures):
   try:v=fut.result()
   except Exception:v=None
   if v and v["doi"] not in used:validated.append(v)
 validated.sort(key=lambda x:(x["score"],x["cited_by_count"],x["year"]),reverse=True);picked=validated[:quota]
 for p in picked:
  used.add(p["doi"]);p["initial_relevance"]="A" if any(norm_text(t) in norm_text(p["title"]+" "+p["abstract"]) for t in FOOD_TERMS) else "B"
  if p["group"] in {"G4","G9"} and p["initial_relevance"]=="B":p["initial_relevance"]="C"
  p["priority"]="P0" if p["score"]>=10 else ("P1" if p["score"]>=6.5 else "P2")
 selected.extend(picked);print("SELECTED",unit,len(picked),flush=True)
selected_by_unit=Counter(x["unit"] for x in selected)
for unit in UNIT_ORDER:
 need=UNIT_QUOTAS[unit]-selected_by_unit[unit]
 if need<=0:continue
 deeper=[x for x in unit_pools[unit] if x["doi"] not in used];batch_size=max(need*4,400);cursor=0;print("REFILL",unit,"need",need,"pool",len(deeper),flush=True)
 while need>0 and cursor<len(deeper):
  batch=deeper[cursor:cursor+batch_size];cursor+=batch_size;validated=[]
  with ThreadPoolExecutor(max_workers=24) as ex:
   futures={ex.submit(crossref_validate,c):c for c in batch}
   for fut in as_completed(futures):
    try:v=fut.result()
    except Exception:v=None
    if v and v["doi"] not in used:validated.append(v)
  validated.sort(key=lambda x:(x["score"],x["cited_by_count"],x["year"]),reverse=True)
  for p in validated[:need]:
   used.add(p["doi"]);p["initial_relevance"]="A" if any(norm_text(t) in norm_text(p["title"]+" "+p["abstract"]) for t in FOOD_TERMS) else "B"
   if p["group"] in {"G4","G9"} and p["initial_relevance"]=="B":p["initial_relevance"]="C"
   p["priority"]="P0" if p["score"]>=10 else ("P1" if p["score"]>=6.5 else "P2");selected.append(p);need-=1
counts=Counter(x["unit"] for x in selected);failure_units={u:(counts[u],UNIT_QUOTAS[u]) for u in UNIT_QUOTAS if counts[u]!=UNIT_QUOTAS[u]}
if failure_units:print("FAILURE_UNITS",failure_units,flush=True);raise SystemExit(2)
print("OPEN_LINKS",len(selected),flush=True);opened=[]
with ThreadPoolExecutor(max_workers=48) as ex:
 futures={ex.submit(open_article_link,c):c for c in selected}
 for idx,fut in enumerate(as_completed(futures),1):
  try:v=fut.result()
  except Exception:v=open_article_link(futures[fut])
  opened.append(v)
  if idx%500==0:print(" opened",idx,flush=True)
opened.sort(key=lambda x:(int(x["group"][1:]),x["unit"],{"P0":0,"P1":1,"P2":2}.get(x["priority"],9),-x["score"],-x["cited_by_count"],str(x["title"])))
assert len(opened)==10000 and len({x["doi"] for x in opened})==10000 and not ({x["doi"] for x in opened}&EXCLUDED)
for i,x in enumerate(opened,1):
 bid=f"B003-{i:05d}";x["B003_ID"]=bid;x["pdf_name"]=f"{bid}_{sanitize_author(x['first_author'])}_{x['year']}_{doi_tail(x['doi'])}.pdf";status=x.get("link_http_status")
 if status==200:x["link_status_note"]="Page opened successfully"
 elif status in (401,403,429):x["link_status_note"]=f"Metadata verified; HTTP {status} access restriction/rate limit"
 elif status and status<500:x["link_status_note"]=f"Metadata verified; HTTP {status}"
 else:x["link_status_note"]="Metadata verified; article access page unavailable during automated check"
 x["download_status"]="Pending download"
by_group=defaultdict(list)
for x in opened:by_group[x["group"]].append(x)
student_rows=defaultdict(list);group_offsets=defaultdict(int)
for student,alloc in STUDENT_ALLOCATION.items():
 for group,n in alloc.items():
  start=group_offsets[group];end=start+n;part=by_group[group][start:end]
  if len(part)!=n:raise RuntimeError(f"Allocation shortfall {student} {group} {len(part)}/{n}")
  student_rows[student].extend(part);group_offsets[group]=end
 student_rows[student].sort(key=lambda x:(int(x["group"][1:]),x["unit"],{"P0":0,"P1":1,"P2":2}.get(x["priority"],9),-x["score"]));assert len(student_rows[student])==1000
for g,q in GROUP_QUOTAS.items():assert group_offsets[g]==q,(g,group_offsets[g],q)
HEADERS=["B003_ID","学生文件","主课题群","研究单元","下载优先级","初筛相关性","第一作者","年份","论文题目","期刊","DOI","PDF文件命名","文献类型","被引次数","开放获取","OA状态","摘要","发现检索式","匹配关键词","相关性评分","Crossref题名","题名一致度","元数据核验","链接HTTP状态","链接状态说明","链接打开时间","下载状态","文献链接"]
def to_row(x,student):return {"B003_ID":x["B003_ID"],"学生文件":student,"主课题群":x["group"],"研究单元":x["unit"],"下载优先级":x["priority"],"初筛相关性":x["initial_relevance"],"第一作者":x["first_author"],"年份":x["year"],"论文题目":x["title"],"期刊":x["journal"],"DOI":x["doi"],"PDF文件命名":x["pdf_name"],"文献类型":x["crossref_type"] or x["openalex_type"],"被引次数":x["cited_by_count"],"开放获取":"是" if x["is_oa"] else "否","OA状态":x["oa_status"],"摘要":x["abstract"],"发现检索式":x["query"],"匹配关键词":x["matched_terms"],"相关性评分":x["score"],"Crossref题名":x["crossref_title"],"题名一致度":x["title_similarity"],"元数据核验":x["metadata_verified"],"链接HTTP状态":x["link_http_status"],"链接状态说明":x["link_status_note"],"链接打开时间":x["opened_at"],"下载状态":x["download_status"],"文献链接":x["download_link"]}
os.makedirs("out",exist_ok=True);master=[]
for student in [f"Student{i:02d}" for i in range(1,11)]:
 rr=[to_row(x,student) for x in student_rows[student]];master.extend(rr)
 with open(f"out/B003_{student}_1000.csv","w",encoding="utf-8-sig",newline="") as f:w=csv.DictWriter(f,fieldnames=HEADERS);w.writeheader();w.writerows(rr)
with open("out/B003_10000_master.csv","w",encoding="utf-8-sig",newline="") as f:w=csv.DictWriter(f,fieldnames=HEADERS);w.writeheader();w.writerows(master)
summary={"generated_at":datetime.now(timezone.utc).isoformat(),"total_records":len(master),"unique_dois":len({r["DOI"] for r in master}),"excluded_existing_dois":len(EXCLUDED),"group_quotas":GROUP_QUOTAS,"unit_quotas":UNIT_QUOTAS,"student_allocation":STUDENT_ALLOCATION,"student_counts":{s:len(v) for s,v in student_rows.items()},"http_status_counts":dict(Counter(str(x["link_http_status"]) for x in opened)),"priority_counts":dict(Counter(x["priority"] for x in opened)),"relevance_counts":dict(Counter(x["initial_relevance"] for x in opened))}
with open("out/run_summary.json","w",encoding="utf-8") as f:json.dump(summary,f,ensure_ascii=False,indent=2)
print(json.dumps(summary,ensure_ascii=False),flush=True)
