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
food_terms = ['food','edible','dietary','nutrition','milk','dairy','casein','whey','lactoferrin','egg','meat','fish','marine','seafood','collagen','gelatin','soy','soybean','pea','bean','rice','wheat','oat','barley','maize','algae','seaweed','mushroom','mycoprotein','insect protein','protein ingredient','protein hydrolysate','food derived']
object_terms = ['protein','peptide','hydrolysate','protease','peptidase','enzyme','digestion','fermentation','amino acid']
exclude_terms = ['cancer vaccine','tumor vaccine','epitope vaccine','hiv vaccine','malaria vaccine','peptide drug conjugate','radioimmunotherapy','venom peptide','conotoxin','therapeutic antibody','amyloid beta','prion disease']
frontier = {'K10','K11','K12','K15'}
core = {'K03','K05','K06','K07','K08','K09','K10','K11','K12','K13','K14'}
word_re = re.compile(r'[^a-z0-9]+')

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
    memberships = norm(row.get('memberships'))
    combined = ' '.join([title, abstract, journal, memberships])
    food_hits = hits(combined, food_terms)
    object_hits = hits(combined, object_terms)
    exclusion_hits = hits(combined, exclude_terms)
    scores = {}
    evidence = {}
    for code, phrases in terms.items():
        title_hits = hits(title, phrases)
        abstract_hits = hits(abstract, phrases)
        journal_hits = hits(journal, phrases)
        prior = 4.0 if has(memberships, code) else 0.0
        scores[code] = round(len(title_hits)*4.0 + len(abstract_hits)*1.5 + len(journal_hits) + prior, 3)
        evidence[code] = title_hits[:5] + [x for x in abstract_hits[:7] if x not in title_hits]
    ranked = sorted(scores, key=lambda code: (scores[code], code), reverse=True)
    primary = ranked[0]
    secondary = [code for code in ranked[1:4] if scores[code] >= max(3.0, scores[primary]*0.45)]
    maximum = scores[primary]
    if exclusion_hits and not food_hits:
        relevance = 'D'; reason = '明确排除主题且缺乏食品迁移接口'
    elif food_hits and object_hits and maximum >= 4.0:
        relevance = 'A'; reason = '食品来源或食品体系明确，主领域证据充分'
    elif object_hits and maximum >= 5.0:
        relevance = 'B'; reason = '蛋白、肽、酶或方法学相关，可明确迁移'
    elif object_hits and maximum >= 2.5:
        relevance = 'C'; reason = '边界或通用方法文献，保留作方法与引用支撑'
    else:
        relevance = 'D'; reason = '题名摘要缺少足够的研究领域证据'
    cited = 0
    try:
        cited = int(float(row.get('cited_by_count') or 0))
    except Exception:
        pass
    multi = int(float(row.get('source_record_count') or 1)) >= 2 or str(row.get('metadata_status') or '').startswith('V2')
    if relevance == 'A' and primary in core and (maximum >= 10 or multi or cited >= 50):
        priority = 'P0'
    elif relevance == 'A' or (relevance == 'B' and maximum >= 9):
        priority = 'P1'
    elif relevance == 'B' or (relevance == 'C' and primary in frontier and maximum >= 5):
        priority = 'P2'
    else:
        priority = 'P3'
    eligible = relevance in {'A','B'} or (relevance == 'C' and primary in frontier and maximum >= 5)
    confidence = min(0.99, 0.45 + min(maximum,20)/35 + min(len(food_hits),3)*0.07 + (0.05 if multi else 0))
    return {
        'K_primary':primary,'K_primary_name':names[primary],'K_secondary':'; '.join(secondary),'G_primary':gmap[primary],
        'relevance':relevance,'download_priority':priority,'download_eligible':'yes' if eligible else 'no',
        'classification_score':maximum,'classification_confidence':round(confidence,4),
        'food_hits':'; '.join(food_hits[:12]),'object_hits':'; '.join(object_hits[:12]),
        'domain_evidence':'; '.join(evidence[primary][:12]),'exclusion_hits':'; '.join(exclusion_hits[:8]),
        'inclusion_reason':reason
    }

with source.open('r', encoding='utf-8-sig', newline='') as f:
    reader = csv.DictReader(f)
    base_headers = reader.fieldnames or []
    extra = ['K_primary','K_primary_name','K_secondary','G_primary','relevance','download_priority','download_eligible','classification_score','classification_confidence','food_hits','object_hits','domain_evidence','exclusion_hits','inclusion_reason']
    headers = base_headers + extra
    counts = Counter(); kcounts = Counter(); pcounts = Counter(); eligible = 0; rows = 0
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
            eligible += result['download_eligible'] == 'yes'
            if rows % 10000 == 0:
                print('CLASSIFY_PROGRESS', SHARD, rows, dict(counts), flush=True)
summary = {'stage':'S3.2','shard':SHARD,'input_rows':rows,'classified_rows':rows,'relevance_counts':dict(counts),'K_primary_counts':dict(kcounts),'priority_counts':dict(pcounts),'download_eligible':eligible}
(OUT / f'B004_S3_2_shard{SHARD}_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False), flush=True)
if rows < 10000 or sum(kcounts.values()) != rows:
    raise SystemExit(2)
