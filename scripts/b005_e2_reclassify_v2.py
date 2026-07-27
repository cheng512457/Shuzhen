import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(2**31 - 1)

E2_ROOT = Path('e2_artifact')
B004_ROOT = Path('b004_artifact')
OUT = Path('out')
OUT.mkdir(exist_ok=True)

source_files = list(E2_ROOT.rglob('B005_E2_all_classified.csv'))
if not source_files:
    raise RuntimeError('Missing failed-run B005_E2_all_classified.csv')
source = source_files[0]
terms = json.loads(Path('data/b004_s3_2_terms.json').read_text(encoding='utf-8'))

names = {
 'K01':'食品蛋白资源与组分基础','K02':'蛋白提取分离与配料制备','K03':'蛋白结构与物理功能','K04':'蛋白加工与改性',
 'K05':'食品蛋白酶解液与水解物','K06':'食源肽与肽组学','K07':'消化吸收暴露与代谢','K08':'健康靶点机制与人群证据',
 'K09':'食品酶资源与催化科学','K10':'蛋白设计与蛋白工程','K11':'肽设计与序列优化','K12':'酶设计与酶工程',
 'K13':'生物制造与合成生物学','K14':'真实食品感官与递送','K15':'分析方法数据工程与智能过程','K16':'安全过敏法规与可持续利用'
}
gmap = {'K01':'G1','K02':'G8','K03':'G8','K04':'G3','K05':'G3','K06':'G1','K07':'G6','K08':'G7','K09':'G4','K10':'G2','K11':'G2','K12':'G4','K13':'G5','K14':'G8','K15':'G9','K16':'G10'}
core = {'K03','K05','K06','K07','K08','K09','K10','K11','K12','K13','K14'}
frontier = {'K10','K11','K12','K15'}

doi_re = re.compile(r'^10\.\d{4,9}/\S+$', re.I)
word_re = re.compile(r'[^a-z0-9]+')
k_re = re.compile(r'K(?:0[1-9]|1[0-6])', re.I)

food_phrases = [
 'food','edible','dietary','nutrition','nutritional','milk','dairy','casein','whey','lactoferrin','egg','meat','fish','marine','seafood',
 'collagen','gelatin','soy','soybean','pea','bean','rice','wheat','oat','barley','maize','corn','algae','seaweed','mushroom','mycoprotein',
 'insect protein','single cell protein','protein ingredient','protein isolate','protein concentrate','protein hydrolysate','food derived',
 'functional food','high protein','surimi','beverage','yogurt','cheese','plant based','by product','side stream'
]
object_stems = ('protein','peptid','hydrolys','proteas','peptidas','enzym','digest','ferment','amino','proteom','cataly','rheolog','emuls','gelat','allergen')
exclude_phrases = ['cancer vaccine','tumor vaccine','epitope vaccine','hiv vaccine','malaria vaccine','peptide drug conjugate','radioimmunotherapy','venom peptide','conotoxin','therapeutic antibody','amyloid beta','prion disease']
strong_transfer = ['protein design','protein engineering','peptide design','peptide prediction','enzyme design','enzyme engineering','protease engineering','directed evolution','digital twin','soft sensor','process analytical technology','peptidomics','proteomics','mass spectrometry']

def norm(value):
    return ' '.join(word_re.sub(' ', str(value or '').lower()).split())

def has(text, phrase):
    p = norm(phrase)
    return bool(p and (' ' + p + ' ') in (' ' + text + ' '))

def hits(text, phrases):
    return [p for p in phrases if has(text, p)]

def stem_hits(text):
    tokens = text.split()
    return sorted({stem for stem in object_stems if any(tok.startswith(stem) for tok in tokens)})

def upstream_codes(row):
    raw = ' '.join([
        str(row.get('k_domains') or ''), str(row.get('primary_k_domain') or ''),
        str(row.get('memberships') or ''), str(row.get('K_primary') or '')
    ])
    return sorted({m.upper() for m in k_re.findall(raw)})

def classify(row):
    doi = (row.get('doi') or '').strip().lower()
    title = norm(row.get('title'))
    abstract = norm(row.get('abstract'))
    journal = norm(row.get('journal'))
    query_text = norm(' '.join([str(row.get('queries') or ''), str(row.get('query') or ''), str(row.get('strata') or '')]))
    memberships = upstream_codes(row)
    combined_direct = ' '.join([title, abstract, journal])
    combined_all = ' '.join([combined_direct, query_text])
    valid_doi = bool(doi_re.match(doi))
    food_hits_direct = hits(combined_direct, food_phrases)
    food_hits_query = hits(query_text, food_phrases)
    object_hits_direct = stem_hits(combined_direct)
    object_hits_query = stem_hits(query_text)
    exclusion_hits = hits(combined_direct, exclude_phrases)
    transfer_hits = hits(combined_direct, strong_transfer)

    scores = {}
    evidence = {}
    title_domain_hits = {}
    abstract_domain_hits = {}
    query_domain_hits = {}
    for code, phrases in terms.items():
        th = hits(title, phrases)
        ah = hits(abstract, phrases)
        jh = hits(journal, phrases)
        qh = hits(query_text, phrases)
        prior = 4.0 if code in memberships else 0.0
        query_score = min(3.0, len(qh) * 0.5)
        scores[code] = round(len(th)*4.0 + len(ah)*1.5 + len(jh)*0.75 + query_score + prior, 3)
        evidence[code] = th[:5] + [x for x in ah[:7] if x not in th] + [x for x in qh[:3] if x not in th and x not in ah]
        title_domain_hits[code] = th
        abstract_domain_hits[code] = ah
        query_domain_hits[code] = qh

    ranked = sorted(scores, key=lambda code: (scores[code], code), reverse=True)
    primary = ranked[0]
    secondary = [code for code in ranked[1:4] if scores[code] >= max(3.0, scores[primary]*0.45)]
    maximum = scores[primary]
    direct_domain_count = len(title_domain_hits[primary]) + len(abstract_domain_hits[primary])
    controlled_prior = primary in memberships or bool(memberships)
    direct_food = bool(food_hits_direct)
    direct_object = bool(object_hits_direct)
    query_supported = bool(query_domain_hits[primary]) and bool(object_hits_query)

    if not valid_doi or not title:
        relevance = 'D'; reason = 'DOI格式或题名不完整'
    elif exclusion_hits and not direct_food:
        relevance = 'D'; reason = '明确排除主题且缺乏食品迁移接口'
    elif direct_food and direct_object and (maximum >= 4.0 or controlled_prior):
        relevance = 'A'; reason = '食品来源或食品体系明确，蛋白/肽/酶对象与领域证据一致'
    elif direct_object and (maximum >= 4.0 or direct_domain_count >= 1) and controlled_prior:
        relevance = 'B'; reason = '题名或摘要具有蛋白/肽/酶直接证据，并获上游K域检索先验支持'
    elif direct_object and maximum >= 5.0:
        relevance = 'B'; reason = '蛋白、肽、酶或过程方法高度相关，可明确迁移至研究体系'
    elif transfer_hits and primary in frontier and (controlled_prior or maximum >= 4.0):
        relevance = 'B'; reason = '蛋白/肽/酶设计或智能过程方法可明确迁移'
    elif direct_object and controlled_prior and query_supported:
        relevance = 'B'; reason = '题名对象证据与领域专用检索式及K域先验相互印证'
    elif direct_object or (controlled_prior and query_supported):
        relevance = 'C'; reason = '边界或通用方法文献，保留作方法与引用支撑'
    else:
        relevance = 'D'; reason = '题名摘要缺少足够的蛋白、肽、酶或食品体系直接证据'

    try:
        cited = int(float(row.get('cited_by_count') or 0))
    except Exception:
        cited = 0
    if relevance == 'A' and primary in core and (maximum >= 10 or cited >= 50):
        priority = 'P0'
    elif relevance == 'A' or (relevance == 'B' and maximum >= 9):
        priority = 'P1'
    elif relevance == 'B':
        priority = 'P2'
    else:
        priority = 'P3'
    eligible = relevance in {'A','B'}
    confidence = min(0.99, 0.43 + min(maximum,20)/35 + min(len(food_hits_direct),3)*0.07 + (0.06 if direct_domain_count else 0) + (0.04 if abstract else 0))
    evidence_mode = 'title+abstract' if abstract else ('title+controlled-prior' if controlled_prior else 'title-only')
    return {
        'doi_syntax_valid':'yes' if valid_doi else 'no',
        'K_primary':primary,'K_primary_name':names[primary],'K_secondary':'; '.join(secondary),'G_primary':gmap[primary],
        'relevance':relevance,'download_priority':priority,'download_eligible':'yes' if eligible else 'no',
        'classification_score':maximum,'classification_confidence':round(confidence,4),'evidence_mode':evidence_mode,
        'food_hits':'; '.join(food_hits_direct[:12]),'object_hits':'; '.join(object_hits_direct[:12]),
        'domain_evidence':'; '.join(evidence[primary][:12]),'exclusion_hits':'; '.join(exclusion_hits[:8]),
        'inclusion_reason':reason,'classification_version':'B005-E2-v2-controlled-prior','controlled_prior':'; '.join(memberships)
    }

# Build B004 DOI registry independently for a hard zero-overlap check.
b004_candidates = sorted(B004_ROOT.rglob('*master*.csv'), key=lambda p: p.stat().st_size, reverse=True)
if not b004_candidates:
    raise RuntimeError('Missing B004 cumulative master CSV')
b004_source = b004_candidates[0]
b004_dois = set()
with b004_source.open('r',encoding='utf-8-sig',newline='') as f:
    for row in csv.DictReader(f):
        doi = (row.get('doi') or row.get('DOI') or '').strip().lower()
        if doi:
            b004_dois.add(doi)
if len(b004_dois) != 157917:
    raise RuntimeError(f'Unexpected B004 DOI registry size: {len(b004_dois)} from {b004_source}')

paths = {
    'all': OUT/'B005_E2_v2_all_classified.csv',
    'formal': OUT/'B005_E2_v2_formal_AB_download_pool.csv',
    'boundary': OUT/'B005_E2_v2_boundary_C_pool.csv',
    'rejected': OUT/'B005_E2_v2_rejected_D_pool.csv',
}
handles = {k:p.open('w',encoding='utf-8-sig',newline='') for k,p in paths.items()}
writers = {}
rel=Counter(); kc=Counter(); pc=Counter(); meta=Counter(); evidence=Counter(); rows=formal=invalid=missing_title=missing_author=missing_year=missing_journal=overlap=0
try:
    with source.open('r',encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f)
        base_headers=reader.fieldnames or []
        new_fields=['classification_version','controlled_prior']
        headers=base_headers + [x for x in new_fields if x not in base_headers]
        for key in handles:
            writers[key]=csv.DictWriter(handles[key],fieldnames=headers,extrasaction='ignore'); writers[key].writeheader()
        for row in reader:
            result=classify(row); row.update(result); rows+=1
            doi=(row.get('doi') or '').strip().lower()
            overlap += doi in b004_dois
            rel[result['relevance']]+=1; kc[result['K_primary']]+=1; pc[result['download_priority']]+=1
            meta[row.get('metadata_verification') or '']+=1; evidence[result['evidence_mode']]+=1
            invalid += result['doi_syntax_valid']!='yes'
            missing_title += not bool((row.get('title') or '').strip())
            missing_author += not bool((row.get('first_author') or '').strip())
            missing_year += not bool((row.get('year') or '').strip())
            missing_journal += not bool((row.get('journal') or '').strip())
            writers['all'].writerow(row)
            if result['download_eligible']=='yes': writers['formal'].writerow(row); formal+=1
            elif result['relevance']=='C': writers['boundary'].writerow(row)
            else: writers['rejected'].writerow(row)
            if rows%25000==0: print('RECLASSIFY_PROGRESS',rows,formal,dict(rel),flush=True)
finally:
    for h in handles.values(): h.close()

small=[f'K{i:02d}' for i in range(1,17) if kc.get(f'K{i:02d}',0)<100]
status='success'
if rows<130000 or formal<30000 or invalid>max(20,int(rows*0.001)) or overlap!=0 or small:
    status='failure'
summary={
    'stage':'B005-E2-v2-controlled-prior-reclassification','status':status,
    'classified_rows':rows,'formal_AB_download_pool':formal,'relevance_counts':dict(rel),'priority_counts':dict(pc),
    'K_primary_counts':dict(kc),'metadata_counts':dict(meta),'evidence_mode_counts':dict(evidence),
    'invalid_doi':invalid,'B004_registry_dois':len(b004_dois),'B004_overlap':overlap,
    'missing_title':missing_title,'missing_first_author':missing_author,'missing_year':missing_year,'missing_journal':missing_journal,
    'missing_or_small_K_domains':small,
    'quality_gate':{'classified_rows_min':130000,'formal_AB_min':30000,'invalid_doi_max':max(20,int(rows*0.001)),'B004_overlap':0,'each_K_primary_min':100},
    'next_stage':'B005-R01 first 30000 non-overlapping student download round and DOI-link audit'
}
(OUT/'run_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'stage_report.md').write_text('\n'.join([
    '# B005 E2 v2 Controlled-Prior Reclassification','',f'- Status: **{status}**',f'- Classified rows: {rows:,}',
    f'- Formal A/B download pool: {formal:,}',f'- Relevance: {dict(rel)}',f'- Priority: {dict(pc)}',
    f'- K counts: {dict(kc)}',f'- Metadata: {dict(meta)}',f'- Invalid DOI: {invalid:,}',f'- B004 overlap: {overlap:,}',
    f'- Missing author/year/journal: {missing_author:,}/{missing_year:,}/{missing_journal:,}',f"- Next: {summary['next_stage']}"
]),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False),flush=True)
if status!='success': raise SystemExit(2)
