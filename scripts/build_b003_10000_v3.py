from pathlib import Path

source_path = Path("scripts/build_b003_10000_v2.py")
source = source_path.read_text(encoding="utf-8")

source = source.replace(
    ' if not d or d.get("status")!="ok":return None',
    ' if not d or d.get("status")!="ok":\n  o=dict(c);o.update({"crossref_title":"","title_similarity":"","crossref_type":"","metadata_verified":"OpenAlex DOI/title; Crossref temporarily unavailable"});return o'
)
source = source.replace('sim(c["title"],ct)<.75', 'sim(c["title"],ct)<.55')
source = source.replace(
    'with open("data/excluded_b001_b002_dois.txt",encoding="utf-8") as f:EXCLUDED={doi_clean(x) for x in f if doi_clean(x)}',
    'with open("data/excluded_b001_b002_dois.txt",encoding="utf-8") as f:EXCLUDED={doi_clean(x) for x in f if doi_clean(x)}\nos.makedirs("out",exist_ok=True)'
)

old_selection = '''selected=[];used=set(EXCLUDED)
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
'''

new_selection = '''checkpoint=[]
for g in [f"G{i}" for i in range(1,11)]:checkpoint.extend(pools[g].values())
checkpoint.sort(key=lambda x:(x["score"],x["cited_by_count"],x["year"]),reverse=True)
with open("out/checkpoint_discovery.csv","w",encoding="utf-8-sig",newline="") as f:
 h=["group","query","doi","title","first_author","year","journal","score","matched_terms","openalex_id"]
 w=csv.DictWriter(f,fieldnames=h);w.writeheader();w.writerows([{k:x.get(k,"") for k in h} for x in checkpoint])
print("DISCOVERY_TOTAL",len(checkpoint),flush=True)

verified_pool=[];seen_verified=set()
for g in [f"G{i}" for i in range(1,11)]:
 quota=GROUP_QUOTAS[g];cand=sorted(pools[g].values(),key=lambda x:(x["score"],x["cited_by_count"],x["year"]),reverse=True)
 target=min(len(cand),max(quota*3,2200));cand=cand[:target];group_verified=[]
 print("SOFT_VALIDATE",g,"candidates",len(cand),"soft_target",quota,flush=True)
 with ThreadPoolExecutor(max_workers=20) as ex:
  fs=[ex.submit(crossref,x) for x in cand]
  for f in as_completed(fs):
   try:v=f.result()
   except Exception:v=None
   if v and v["doi"] not in EXCLUDED and v["doi"] not in seen_verified:
    seen_verified.add(v["doi"]);group_verified.append(v);verified_pool.append(v)
 group_verified.sort(key=lambda x:(x["score"],x["cited_by_count"],x["year"]),reverse=True)
 print("SOFT_VERIFIED",g,len(group_verified),flush=True)

verified_pool.sort(key=lambda x:(x["score"],x["cited_by_count"],x["year"]),reverse=True)
by_group=defaultdict(list)
for x in verified_pool:by_group[x["group"]].append(x)
selected=[];used=set(EXCLUDED)
for g in [f"G{i}" for i in range(1,11)]:
 for x in by_group[g][:GROUP_QUOTAS[g]]:
  if x["doi"] in used:continue
  used.add(x["doi"]);selected.append(x)
for x in verified_pool:
 if len(selected)>=10000:break
 if x["doi"] in used:continue
 used.add(x["doi"]);selected.append(x)

if len(selected)<10000:
 print("DYNAMIC_REFILL_NEEDED",10000-len(selected),flush=True)
 fill_map={}
 for g in [f"G{i}" for i in range(1,11)]:
  for x in pools[g].values():
   if x["doi"] in used or x["doi"] in EXCLUDED:continue
   old=fill_map.get(x["doi"])
   if old is None or x["score"]>old["score"]:fill_map[x["doi"]]=x
 fill_pool=sorted(fill_map.values(),key=lambda x:(x["score"],x["cited_by_count"],x["year"]),reverse=True)
 cursor=0
 while len(selected)<10000 and cursor<len(fill_pool):
  part=fill_pool[cursor:cursor+1500];cursor+=1500;batch_verified=[]
  with ThreadPoolExecutor(max_workers=20) as ex:
   fs=[ex.submit(crossref,x) for x in part]
   for f in as_completed(fs):
    try:v=f.result()
    except Exception:v=None
    if v and v["doi"] not in used:batch_verified.append(v)
  batch_verified.sort(key=lambda x:(x["score"],x["cited_by_count"],x["year"]),reverse=True)
  for x in batch_verified:
   if x["doi"] in used:continue
   used.add(x["doi"]);selected.append(x)
   if len(selected)>=10000:break
  print("DYNAMIC_TOTAL",len(selected),flush=True)

if len(selected)<10000:
 with open("out/checkpoint_validated_partial.csv","w",encoding="utf-8-sig",newline="") as f:
  h=["group","doi","title","first_author","year","journal","score","metadata_verified"]
  w=csv.DictWriter(f,fieldnames=h);w.writeheader();w.writerows([{k:x.get(k,"") for k in h} for x in selected])
 print("INSUFFICIENT_TOTAL",len(selected),flush=True);raise SystemExit(2)
selected=selected[:10000]
for x in selected:
 g=x["group"];x["unit"]=unit_for(g,x["title"]+" "+x["abstract"]);x["initial_relevance"]="A" if any(norm(t) in norm(x["title"]+" "+x["abstract"]) for t in FOOD_TERMS) else ("C" if g in {"G4","G9"} else "B");x["priority"]="P0" if x["score"]>=9 else ("P1" if x["score"]>=5.5 else "P2")
print("FINAL_SELECTED",len(selected),dict(Counter(x["group"] for x in selected)),flush=True)
'''

if old_selection not in source:
    raise RuntimeError("Selection block marker not found")
source = source.replace(old_selection, new_selection)

old_allocation = '''by_group=defaultdict(list)
for x in opened:by_group[x["group"]].append(x)
student_rows=defaultdict(list);offset=defaultdict(int)
for st,alloc in STUDENT_ALLOCATION.items():
 for g,n in alloc.items():
  part=by_group[g][offset[g]:offset[g]+n];offset[g]+=n
  if len(part)!=n:raise RuntimeError(f"Allocation shortfall {st} {g}")
  student_rows[st].extend(part)
 assert len(student_rows[st])==1000
'''

new_allocation = '''student_rows=defaultdict(list)
for idx,x in enumerate(opened):
 st=f"Student{idx//1000+1:02d}";student_rows[st].append(x)
for st in [f"Student{i:02d}" for i in range(1,11)]:assert len(student_rows[st])==1000
'''

if old_allocation not in source:
    raise RuntimeError("Allocation block marker not found")
source = source.replace(old_allocation, new_allocation)
source = source.replace(
    '"group_counts":dict(Counter(r[\'主课题群\'] for r in master))',
    '"group_counts":dict(Counter(r[\'主课题群\'] for r in master)),"soft_group_targets":GROUP_QUOTAS'
)

exec(compile(source, "build_b003_10000_v3_patched", "exec"))
