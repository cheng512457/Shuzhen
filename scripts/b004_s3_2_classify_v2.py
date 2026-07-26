import csv
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(2**31 - 1)

SHARD = int(os.environ.get('SHARD', '0'))
ROOT = Path('input_artifact')
OUT = Path('out')
OUT.mkdir(exist_ok=True)
source_files = list(ROOT.rglob(f'B004_S3_2_input_shard{SHARD}.csv'))
if not source_files:
    raise RuntimeError(f'Missing input shard {SHARD}')
source = source_files[0]
terms = json.loads(Path('data/b004_s3_2_terms.json').read_text(encoding='utf-8'))

names = {
 'K01':'食品蛋白资源与组分基础','K02':'蛋白提取分离与配料制备','K03':'蛋白结构与物理功能','K04':'蛋白加工与改性',
 'K05':'食品蛋白酶解液与水解物','K06':'食源肽与肽组学','K07':'消化吸收暴露与代谢','K08':'健康靶点机制与人群证据',
 'K09':'食品酶资源与催化科学','K10':'蛋白设计与蛋白工程','K11':'肽设计与序列优化','K12':'酶设计与酶工程',
 'K13':'生物制造与合成生物学','K14':'真实食品感官与递送','K15':'分析方法数据工程与智能过程','K16':'安全过敏法规与可持续利用'
}
gmap = {'K01':'G1','K02':'G8','K03':'G8','K04':'G3','K05':'G3','K06':'G1','K07':'G6','K08':'G7','K09':'G4','K10':'G2','K11':'G2','K12':'G4','K13':'G5','K14':'G8','K15':'G9','K16':'G10'}
food_terms = [
 'food','edible','dietary','nutrition','nutritional','milk','dairy','casein','whey','lactoferrin','egg','meat','fish','marine','seafood',
 'collagen','gelatin','soy','soybean','pea','bean','rice','wheat','oat','barley','maize','corn','algae','seaweed','mushroom','mycoprotein',
 'insect protein','protein ingredient','protein isolate','protein concentrate','protein hydrolysate','food derived','functional food','beverage',
 'emulsion','gel food','surimi','fermented food','food matrix','food processing','food grade'
]
object_terms = [
 'protein','proteome','proteomics','peptide','peptidomics','hydrolysate','hydrolysis','proteolysis','digest','digestion','protease','peptidase',
 'enzyme','enzymatic','amino acid','fermentation','biomanufacturing','expression','allergen','allergenicity','rheology','gelation','emulsifying',
 'solubility','bioavailability','absorption','transport','binding','target','clinical trial','randomized','machine learning','deep learning',
 'language model','generative','molecular dynamics','mass spectrometry','digital twin','soft sensor','sustainability','valorization'
]
exclude_terms = ['cancer vaccine','tumor vaccine','epitope vaccine','hiv vaccine','malaria vaccine','peptide drug conjugate','radioimmunotherapy','venom peptide','conotoxin','therapeutic antibody','amyloid beta','prion disease']
frontier = {'K10','K11','K12','K15'}
core = {'K03','K05','K06','K07','K08','K09','K10','K11','K12','K13','K14'}
word_re = re.compile(r'[^a-z0-9]+')
code_re = re.compile(r'\bK(?:0[1-9]|1[0-6])\b', re.I)


def norm(value):
    return ' '.join(word_re.sub(' ', str(value or '').lower()).split())


def has(text, phrase):
    p = norm(phrase)
    return bool(p and (' ' + p + ' ') in (' ' + text + ' '))


def hits(text, phrases):
    return [p for p in phrases if has(text, p)]


def classify(row):
    title = norm(row.get('title'))
    abstract = norm(row.get('abstract'))
    journal = norm(row.get('journal'))
    memberships_raw = str(row.get('memberships') or '')
    memberships = norm(memberships_raw)
    combined = ' '.join([title, abstract, journal, memberships])
    food_hits = hits(combined, food_terms)
    title_food_hits = hits(title, food_terms)
    object_hits = hits(combined, object_terms)
    title_object_hits = hits(title, object_terms)
    exclusion_hits = hits(combined, exclude_terms)
    prior_codes = {x.upper() for x in code_re.findall(memberships_raw)}
    scores = {}
    evidence = {}
    title_evidence_counts = {}
    abstract_evidence_counts = {}
    for code, phrases in terms.items():
        title_hits = hits(title, phrases)
        abstract_hits = hits(abstract, phrases)
        journal_hits = hits(journal, phrases)
        prior = 4.0 if code in prior_codes else 0.0
        scores[code] = round(len(title_hits)*4.0 + len(abstract_hits)*1.5 + len(journal_hits) + prior, 3)
        evidence[code] = title_hits[:8] + [x for x in abstract_hits[:8] if x not in title_hits]
        title_evidence_counts[code] = len(title_hits)
        abstract_evidence_counts[code] = len(abstract_hits)
    ranked = sorted(scores, key=lambda code: (scores[code], code), reverse=True)
    primary = ranked[0]
    secondary = [code for code in ranked[1:4] if scores[code] >= max(3.0, scores[primary]*0.45)]
    maximum = scores[primary]
    title_domain = title_evidence_counts[primary]
    abstract_domain = abstract_evidence_counts[primary]
    prior_primary = primary in prior_codes
    has_abstract = bool(abstract.strip())

    if exclusion_hits and not title_food_hits and not food_hits:
        relevance = 'D'; reason = '明确排除主题且缺乏食品迁移接口'
    elif title_food_hits and (title_object_hits or title_domain) and maximum >= 4.0:
        relevance = 'A'; reason = '题名直接指向食品来源/食品体系及蛋白肽酶主题'
    elif food_hits and object_hits and maximum >= 4.0:
        relevance = 'A'; reason = '题名或摘要显示食品来源/食品体系明确，主领域证据充分'
    elif object_hits and maximum >= 2.5:
        relevance = 'B'; reason = '蛋白、肽、酶、消化、设计或过程方法明确，可迁移至研究体系'
    elif prior_primary and title_domain >= 1:
        relevance = 'B'; reason = '上游检索领域与题名证据一致，虽摘要缺失仍具有明确迁移价值'
    elif prior_primary and maximum >= 6.0 and (title_object_hits or abstract_domain >= 1):
        relevance = 'B'; reason = '上游领域先验与题名/摘要对象证据共同支持'
    elif title_domain >= 1 and primary in frontier and maximum >= 4.0:
        relevance = 'B'; reason = '蛋白/肽/酶设计或数据方法题名证据明确'
    elif prior_primary and maximum >= 4.0:
        relevance = 'C'; reason = '上游主题先验支持，但题名摘要直接证据有限'
    elif object_hits and maximum >= 1.5:
        relevance = 'C'; reason = '边界或通用方法文献，保留作方法与引用支撑'
    elif maximum >= 3.0:
        relevance = 'C'; reason = '领域词证据存在但食品迁移接口尚不充分'
    else:
        relevance = 'D'; reason = '题名摘要及上游主题缺少足够研究领域证据'

    cited = 0
    try:
        cited = int(float(row.get('cited_by_count') or 0))
    except Exception:
        pass
    multi = int(float(row.get('source_record_count') or 1)) >= 2 or str(row.get('metadata_status') or '').startswith('V2')
    if relevance == 'A' and primary in core and (maximum >= 10 or multi or cited >= 50):
        priority = 'P0'
    elif relevance == 'A' or (relevance == 'B' and (maximum >= 8 or multi or cited >= 40)):
        priority = 'P1'
    elif relevance == 'B':
        priority = 'P2'
    elif relevance == 'C' and primary in frontier and maximum >= 5:
        priority = 'P2'
    else:
        priority = 'P3'
    eligible = relevance in {'A','B'}
    confidence = 0.42 + min(maximum,20)/36 + min(len(title_food_hits),2)*0.08 + min(title_domain,2)*0.06 + (0.05 if multi else 0) + (0.03 if has_abstract else 0)
    confidence = min(0.99, confidence)
    evidence_mode = 'title+abstract' if has_abstract else ('title+prior' if prior_primary else 'title-only')
    return {
        'K_primary':primary,'K_primary_name':names[primary],'K_secondary':'; '.join(secondary),'G_primary':gmap[primary],
        'relevance':relevance,'download_priority':priority,'download_eligible':'yes' if eligible else 'no',
        'classification_score':maximum,'classification_confidence':round(confidence,4),
        'food_hits':'; '.join(food_hits[:12]),'object_hits':'; '.join(object_hits[:16]),
        'domain_evidence':'; '.join(evidence[primary][:16]),'exclusion_hits':'; '.join(exclusion_hits[:8]),
        'prior_K_codes':'; '.join(sorted(prior_codes)),'evidence_mode':evidence_mode,'inclusion_reason':reason
    }


with source.open('r', encoding='utf-8-sig', newline='') as f:
    reader = csv.DictReader(f)
    base_headers = reader.fieldnames or []
    extra = ['K_primary','K_primary_name','K_secondary','G_primary','relevance','download_priority','download_eligible','classification_score','classification_confidence','food_hits','object_hits','domain_evidence','exclusion_hits','prior_K_codes','evidence_mode','inclusion_reason']
    headers = base_headers + extra
    counts = Counter(); kcounts = Counter(); pcounts = Counter(); eligible = 0; rows = 0; modes = Counter()
    with (OUT / f'B004_S3_2_classified_shard{SHARD}.csv').open('w', encoding='utf-8-sig', newline='') as g:
        writer = csv.DictWriter(g, fieldnames=headers)
        writer.writeheader()
        for row in reader:
            result = classify(row)
            row.update(result)
            writer.writerow(row)
            rows += 1
            counts[result['relevance']] += 1
            kcounts[result['K_primary']] += 1
            pcounts[result['download_priority']] += 1
            modes[result['evidence_mode']] += 1
            eligible += result['download_eligible'] == 'yes'
            if rows % 10000 == 0:
                print('CLASSIFY_V2_PROGRESS', SHARD, rows, eligible, dict(counts), flush=True)
summary = {'stage':'S3.2-retry','classifier':'v2-title-prior-aware','shard':SHARD,'input_rows':rows,'classified_rows':rows,'relevance_counts':dict(counts),'K_primary_counts':dict(kcounts),'priority_counts':dict(pcounts),'evidence_mode_counts':dict(modes),'download_eligible':eligible}
(OUT / f'B004_S3_2_shard{SHARD}_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False), flush=True)
if rows < 10000 or sum(kcounts.values()) != rows:
    raise SystemExit(2)
