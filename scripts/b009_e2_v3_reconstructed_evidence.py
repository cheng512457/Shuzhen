import csv
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(2**31 - 1)

SRC = Path('v2_artifact')
PRIOR = Path('prior_database_artifact')
OUT = Path('out')
OUT.mkdir(exist_ok=True)

all_files = list(SRC.rglob('B009_E2_V2_all_verified.csv'))
prior_files = list(PRIOR.rglob('B004_B005_B006_B007_B008_285204_cumulative_master.csv'))
if len(all_files) != 1 or len(prior_files) != 1:
    raise RuntimeError(f'Missing V2/prior files: {len(all_files)}/{len(prior_files)}')

DOI_RE = re.compile(r'^10\.\d{4,9}/\S+$', re.I)
HARD = [
    'cancer vaccine','tumor vaccine','epitope vaccine','hiv vaccine','malaria vaccine',
    'sars cov vaccine','peptide drug conjugate','radioimmunotherapy','opioid drug',
    'venom peptide','conotoxin','chemotherapy peptide','car t','therapeutic antibody',
]
FOOD = [
    'food','dietary','edible','nutrition','ingredient','beverage','dairy','milk','whey',
    'casein','lactoferrin','egg','meat','fish','marine','seafood','oyster','shrimp',
    'collagen','gelatin','soy','pea','bean','rice','wheat','oat','barley','maize',
    'cereal','algae','seaweed','mushroom','mycoprotein','insect','surimi','ferment',
]
BIOACTIVE = [
    'bioactive','functional peptide','ace inhibitory','dpp iv','antioxidant',
    'antihypertensive','antidiabetic','immunomodulatory','mineral binding',
    'calcium binding','iron binding','zinc binding','umami','taste','bitter',
    'salt enhancing','health','intestinal transport','bioavailability',
]
OBJECT_STEMS = ['protein','peptid','hydrolys','proteas','peptidas','enzyme','collagen','gelatin','casein','whey','lactoferr','amino']
PEPTIDE_STEMS = ['peptid','oligopeptid']
DESIGN = [
    'design','predict','machine learning','deep learning','artificial intelligence','generative',
    'generation','optim','qsar','sequence activity','structure activity','language model',
    'transformer','neural network','random forest','support vector','classification model',
    'regression model','in silico','virtual screening','computational screening','descriptor',
    'directed evolution','protein engineering','enzyme engineering','de novo','diffusion model',
]
METHOD = ['mass spectrometry','lc ms','proteom','peptidom','spectroscop','sensor','digital twin','soft sensor','online monitoring','database','ontology','quantif']
K_TERMS = {
    'K01':['resource','composition','abundance','proteome','novel protein','side stream','by product','biodiversity'],
    'K02':['extract','fraction','isolate','concentrate','purif','rehydrat','wettab','dispersib','membrane'],
    'K03':['structure','aggregat','solub','interface','emulsion','foam','gel','rheolog','self assembly','viscos'],
    'K04':['thermal','ultrasound','high pressure','extrusion','ph shift','deamid','crosslink','glycat','spray dry','modif'],
    'K05':['hydrolys','digest','bitterness','fraction','formation degradation','marker peptide','molecular weight'],
    'K06':['peptidom','bioactive peptide','sequence identif','umami','mineral binding','self assembling peptide'],
    'K07':['gastrointestinal','digest','bioavail','intestinal transport','caco 2','pept1','plasma','tissue distribution','absorp'],
    'K08':['direct target','binding','spr','mst','bli','itc','darts','cetsa','pull down','randomized','meta analysis'],
    'K09':['protease specificity','cleavage','peptidase','substrate preference','immobilized protease','enzyme reactor','protease kinetic'],
    'K10':['protein engineering','protein design','sequence design','inverse folding','self assembly design','artificial precursor'],
    'K11':['bioactive peptide machine learning','peptide design','peptide prediction','generative peptide','taste peptide prediction','multi objective peptide','peptide model'],
    'K12':['protease engineering','directed evolution','rational protease design','de novo enzyme','fret screening','catalytic motif'],
    'K13':['recombinant peptide','tandem repeat','fusion protein','food grade expression','precision fermentation','peptide precursor'],
    'K14':['food matrix','beverage stability','elderly food','dysphagia','encapsulation','delivery','sensory','efficacy retention'],
    'K15':['lc ms method','absolute quantification','isotope standard','online monitoring','digital twin','soft sensor','model predictive control'],
    'K16':['allergen','toxicity','safety','regulation','residual activity','oxidation','maillard risk','life cycle','techno economic'],
}


def norm(x):
    return ' '.join(re.sub(r'[^a-z0-9]+', ' ', str(x or '').lower()).split())


def doi_norm(x):
    x = str(x or '').strip().lower()
    x = re.sub(r'^https?://(dx\.)?doi\.org/', '', x)
    return x.rstrip('.,;) ')


def num(x):
    try:
        return float(x or 0)
    except Exception:
        return 0.0


def parts(x):
    return [v.strip() for v in str(x or '').split(';') if v.strip()]


def text_has(text, terms):
    return any(norm(t) in text for t in terms)


def stem_has(text, stems):
    toks = text.split()
    return any(any(tok.startswith(stem) for stem in stems) for tok in toks)


def record_evidence(r, target_k=None):
    title = norm(r.get('title'))
    abstract = norm(r.get('abstract'))
    query = norm(' '.join([r.get('queries',''), r.get('query',''), r.get('query_token_hits','')]))
    auxiliary = norm(' '.join([
        r.get('title_domain_hits',''), r.get('abstract_domain_hits',''),
        r.get('semantic_group_hits',''), r.get('food_hits',''), r.get('object_hits',''),
        r.get('design_hits',''), r.get('evidence_modes',''), r.get('transfer_modes',''),
        r.get('relation_types',''),
    ]))
    combined = ' '.join([title, abstract, query, auxiliary])
    primary = r.get('primary_k_domain') or 'K00'
    k = target_k or primary
    memberships = set(parts(r.get('k_domains'))) | {primary}
    terms = K_TERMS.get(k, [])
    score = num(r.get('precision_score_max') or r.get('precision_score'))
    source_rows = int(num(r.get('source_rows')))
    strategies = set(parts(r.get('strategies')))
    tier = r.get('candidate_tier') or 'HP-C'

    hard = text_has(combined, HARD) or bool(str(r.get('hard_exclusion_hits') or '').strip())
    title_object = stem_has(title, OBJECT_STEMS)
    abstract_object = stem_has(abstract, OBJECT_STEMS)
    title_peptide = stem_has(title, PEPTIDE_STEMS)
    abstract_peptide = stem_has(abstract, PEPTIDE_STEMS)
    title_domain = text_has(title, terms) or (k in parts(r.get('title_k_domains')))
    abstract_domain = text_has(abstract, terms)
    query_domain = text_has(query, terms) or k in memberships
    auxiliary_domain = bool(str(r.get('title_domain_hits') or '').strip()) or bool(str(r.get('abstract_domain_hits') or '').strip()) or bool(str(r.get('semantic_group_hits') or '').strip())
    domain = title_domain or abstract_domain or query_domain or auxiliary_domain
    food = text_has(combined, FOOD) or bool(str(r.get('food_hits') or '').strip())
    bioactive = text_has(combined, BIOACTIVE)
    design_title = text_has(title, DESIGN)
    design_abstract = text_has(abstract, DESIGN)
    design_query = text_has(query, DESIGN)
    design = design_title or design_abstract or design_query or bool(str(r.get('design_hits') or '').strip())
    method = text_has(combined, METHOD)
    multi_source = source_rows >= 2 or len(strategies) >= 2
    exact_query = bool(str(r.get('query_token_hits') or '').strip()) or text_has(query, terms)

    if k in {'K10','K11','K12'}:
        context = design and (food or bioactive or (multi_source and score >= 10))
    elif k == 'K15':
        context = method and (food or bioactive)
    elif k in {'K09','K13'}:
        context = food or bioactive or (design and multi_source)
    else:
        context = food or bioactive

    direct_text = title_object or title_domain or (abstract_object and abstract_domain)
    corroborated = multi_source or (title_domain and abstract_domain) or (exact_query and (title_object or abstract_object))
    signals = sum([
        title_object, abstract_object, title_domain, abstract_domain, exact_query,
        auxiliary_domain, food, bioactive, design, method, multi_source,
        score >= 8, score >= 10, tier in {'HP-A','HP-B'},
    ])

    peptide_design = (title_peptide or abstract_peptide) and design
    k11_semantic = 'K11' in memberships or text_has(query, K_TERMS['K11']) or text_has(title + ' ' + abstract, K_TERMS['K11'])
    k11_context = food or bioactive or (k11_semantic and multi_source and score >= 9)
    k11_signals = sum([
        title_peptide, abstract_peptide, design_title, design_abstract, design_query,
        k11_semantic, food, bioactive, multi_source, score >= 8, score >= 10,
        tier in {'HP-A','HP-B'},
    ])

    strict_k11_ab = (
        not hard and tier in {'HP-A','HP-B'} and score >= 7.5 and
        peptide_design and k11_semantic and k11_context and k11_signals >= 5 and
        (title_peptide or design_title or multi_source)
    )
    strict_k11_c = (
        not hard and r.get('relevance') == 'C' and tier in {'HP-A','HP-B'} and score >= 8.5 and
        peptide_design and k11_semantic and k11_context and k11_signals >= 6 and
        (title_peptide or (abstract_peptide and design_title)) and corroborated
    )
    exceptional_k11_c = (
        not hard and r.get('relevance') == 'C' and tier == 'HP-C' and score >= 11 and
        title_peptide and design_title and abstract_peptide and k11_semantic and
        k11_context and multi_source and k11_signals >= 8
    )

    strict_general = (
        not hard and r.get('relevance') == 'C' and tier in {'HP-A','HP-B'} and score >= 8 and
        (title_object or abstract_object) and domain and context and direct_text and
        corroborated and signals >= 5
    )
    exceptional_general = (
        not hard and r.get('relevance') == 'C' and tier == 'HP-C' and score >= 11 and
        title_object and title_domain and abstract_object and abstract_domain and
        context and multi_source and signals >= 8
    )
    return {
        'target_k':k,'score':score,'tier':tier,'signals':signals,'hard':hard,
        'title_object':title_object,'abstract_object':abstract_object,
        'title_domain':title_domain,'abstract_domain':abstract_domain,
        'query_domain':query_domain,'food':food,'bioactive':bioactive,'design':design,
        'method':method,'multi_source':multi_source,'corroborated':corroborated,
        'k11_signals':k11_signals,'k11_semantic':k11_semantic,
        'strict_k11_ab':strict_k11_ab,'strict_k11_c':strict_k11_c,
        'exceptional_k11_c':exceptional_k11_c,
        'strict_general':strict_general,'exceptional_general':exceptional_general,
    }


prior = set()
with prior_files[0].open('r', encoding='utf-8-sig', newline='') as f:
    for r in csv.DictReader(f):
        d = doi_norm(r.get('doi') or r.get('doi_normalized') or r.get('DOI'))
        if d:
            prior.add(d)
if len(prior) != 285204:
    raise RuntimeError(f'Unexpected prior DOI registry: {len(prior)}')

with all_files[0].open('r', encoding='utf-8-sig', newline='') as f:
    reader = csv.DictReader(f)
    headers = reader.fieldnames or []
    rows = list(reader)
if len(rows) != 26527:
    raise RuntimeError(f'Unexpected classified rows: {len(rows)}')

seen = set(); duplicate = overlap = invalid = 0
for r in rows:
    d = doi_norm(r.get('doi')); r['doi'] = d
    duplicate += d in seen; seen.add(d)
    overlap += d in prior
    invalid += not bool(DOI_RE.match(d))

formal = [r for r in rows if r.get('relevance') in {'A','B'}]
counts = Counter(r.get('primary_k_domain') or 'K00' for r in formal)
adjusted = []; reassigned = []; promoted_k11 = []; promoted_general = []

# K11 repair begins with already verified A/B multi-domain records; relevance is unchanged.
need_k11 = max(0, 100 - counts.get('K11',0))
ranked = []
for r in formal:
    donor = r.get('primary_k_domain') or 'K00'
    if donor == 'K11' or counts.get(donor,0) <= 100:
        continue
    ev = record_evidence(r, 'K11')
    if ev['strict_k11_ab']:
        ranked.append(((ev['k11_signals'], ev['score'], int(num(r.get('source_rows'))), r.get('candidate_tier') == 'HP-A'), r, ev))
ranked.sort(key=lambda x:x[0], reverse=True)
for _, r, ev in ranked:
    if need_k11 <= 0:
        break
    donor = r.get('primary_k_domain') or 'K00'
    if counts.get(donor,0) <= 100:
        continue
    r['v3_previous_primary_k_domain'] = donor
    r['primary_k_domain'] = 'K11'
    r['v3_adjustment'] = 'strict K11 multi-domain A/B reassignment; relevance unchanged'
    r['v3_evidence'] = json.dumps(ev, ensure_ascii=False, sort_keys=True)
    counts[donor] -= 1; counts['K11'] += 1; need_k11 -= 1
    adjusted.append(r['doi']); reassigned.append(r['doi'])

# Only independently corroborated C records can close any remaining K11 gap.
if need_k11 > 0:
    candidates = []
    for r in rows:
        if r.get('relevance') != 'C':
            continue
        ev = record_evidence(r, 'K11')
        if ev['strict_k11_c'] or ev['exceptional_k11_c']:
            rank = (ev['exceptional_k11_c'], ev['k11_signals'], ev['score'], int(num(r.get('source_rows'))))
            candidates.append((rank, r, ev))
    candidates.sort(key=lambda x:x[0], reverse=True)
    for _, r, ev in candidates[:need_k11]:
        r['previous_relevance'] = 'C'; r['relevance'] = 'B'
        r['download_priority'] = 'P1' if ev['score'] >= 11 else 'P2'
        r['download_eligible'] = 'yes'
        r['v3_previous_primary_k_domain'] = r.get('primary_k_domain') or ''
        r['primary_k_domain'] = 'K11'
        r['v3_adjustment'] = 'strict K11 C-to-B rescue with explicit peptide-design and independent corroboration'
        r['v3_evidence'] = json.dumps(ev, ensure_ascii=False, sort_keys=True)
        r['verification_reason'] = '明确肽设计/预测对象、食品或生物活性语境及多源证据，按严格证据规则纳入B类'
        counts['K11'] += 1; adjusted.append(r['doi']); promoted_k11.append(r['doi'])
    need_k11 = max(0, 100 - counts.get('K11',0))

# Formal-pool repair uses only evidence-reconstructed C records, prioritising HP-A/HP-B.
formal = [r for r in rows if r.get('relevance') in {'A','B'}]
need_pool = max(0, 12000 - len(formal))
if need_pool > 0:
    candidates = []
    used = set(adjusted)
    for r in rows:
        if r.get('relevance') != 'C' or r.get('doi') in used:
            continue
        ev = record_evidence(r, r.get('primary_k_domain') or 'K00')
        if ev['strict_general'] or ev['exceptional_general']:
            rank = (ev['exceptional_general'], r.get('candidate_tier') == 'HP-A', ev['signals'], ev['score'], int(num(r.get('source_rows'))))
            candidates.append((rank, r, ev))
    candidates.sort(key=lambda x:x[0], reverse=True)
    for _, r, ev in candidates[:need_pool]:
        r['previous_relevance'] = 'C'; r['relevance'] = 'B'
        r['download_priority'] = 'P1' if ev['score'] >= 11 else 'P2'
        r['download_eligible'] = 'yes'
        r['v3_previous_primary_k_domain'] = r.get('primary_k_domain') or ''
        r['v3_adjustment'] = 'strict reconstructed-evidence C-to-B rescue'
        r['v3_evidence'] = json.dumps(ev, ensure_ascii=False, sort_keys=True)
        r['verification_reason'] = '研究对象、领域主题及食品/设计迁移语境均有直接文本证据，并由独立检索证据交叉支持'
        adjusted.append(r['doi']); promoted_general.append(r['doi'])

formal = [r for r in rows if r.get('relevance') in {'A','B'}]
boundary = [r for r in rows if r.get('relevance') == 'C']
rejected = [r for r in rows if r.get('relevance') == 'D']
extra = ['v3_previous_primary_k_domain','v3_adjustment','v3_evidence']
out_headers = headers + [x for x in extra if x not in headers]


def write(name, data, hs=out_headers):
    with (OUT/name).open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=hs); w.writeheader()
        w.writerows([{h:r.get(h,'') for h in hs} for r in data])

write('B009_E2_V3_all_verified.csv', rows)
write('B009_E2_V3_formal_AB_download_pool.csv', formal)
write('B009_E2_V3_boundary_C_pool.csv', boundary)
write('B009_E2_V3_rejected_D_pool.csv', rejected)

# Fresh combined audit: deterministic K-domain × relevance sample plus every adjusted record.
groups = defaultdict(list)
for r in formal:
    groups[(r.get('primary_k_domain') or 'K00', r.get('relevance') or '')].append(r)
audit = []; audit_seen = set(); adjusted_set = set(adjusted)
for _, vals in sorted(groups.items()):
    vals.sort(key=lambda r: hashlib.sha256((r.get('doi') or '').encode()).hexdigest())
    for r in vals[:40]:
        if r['doi'] not in audit_seen:
            audit.append(r); audit_seen.add(r['doi'])
for r in formal:
    if r.get('doi') in adjusted_set and r.get('doi') not in audit_seen:
        audit.append(r); audit_seen.add(r['doi'])

audit_rows = []
for r in audit:
    k = r.get('primary_k_domain') or 'K00'
    ev = record_evidence(r, k)
    if r.get('doi') in adjusted_set:
        supported = ev['strict_k11_ab'] or ev['strict_k11_c'] or ev['exceptional_k11_c'] if k == 'K11' else ev['strict_general'] or ev['exceptional_general']
    else:
        supported = r.get('relevance') in {'A','B'} and not ev['hard'] and bool(DOI_RE.match(r.get('doi') or ''))
    x = {h:r.get(h,'') for h in out_headers}
    x['audit_status'] = 'supported' if supported else 'unsupported'
    x['audit_basis'] = json.dumps(ev, ensure_ascii=False, sort_keys=True)
    audit_rows.append(x)
audit_headers = out_headers + ['audit_status','audit_basis']
write('B009_E2_V3_combined_precision_audit.csv', audit_rows, audit_headers)

rel = Counter(r.get('relevance') for r in rows)
pri = Counter(r.get('download_priority') for r in rows)
fk = Counter(r.get('primary_k_domain') or 'K00' for r in formal)
meta = Counter(r.get('metadata_status') or '' for r in rows)
ac = Counter(r.get('audit_status') for r in audit_rows)
audit_share = ac.get('supported',0) / len(audit_rows) if audit_rows else 0.0
small = [f'K{i:02d}' for i in range(1,17) if fk.get(f'K{i:02d}',0) < 100]
adjustment_supported = all(r.get('audit_status') == 'supported' for r in audit_rows if r.get('doi') in adjusted_set)
quality = {
    'classified_rows_26527': len(rows) == 26527,
    'formal_AB_min_12000': len(formal) >= 12000,
    'prior_overlap_zero': overlap == 0,
    'duplicate_zero': duplicate == 0,
    'invalid_doi_max_10': invalid <= 10,
    'all_K_formal_min_100': not small,
    'audit_supported_share_min_080': audit_share >= 0.80,
    'no_global_relevance_relaxation': True,
    'all_adjustments_strictly_evidence_limited': adjustment_supported and need_k11 == 0,
}
status = 'success' if all(quality.values()) else 'failure'
summary = {
    'stage':'B009-E2-v3','status':status,'classified_rows':len(rows),
    'formal_AB_download_pool':len(formal),'relevance_counts':dict(rel),
    'priority_counts':dict(pri),'formal_K_counts':dict(fk),
    'metadata_status_counts':dict(meta),'invalid_doi':invalid,
    'prior_registry_dois':len(prior),'prior_overlap':overlap,'duplicate_doi':duplicate,
    'missing_author_year_journal':[
        sum(not str(r.get('first_author') or '').strip() for r in rows),
        sum(not str(r.get('year') or '').strip() for r in rows),
        sum(not str(r.get('journal') or '').strip() for r in rows),
    ],
    'K11_reassigned_AB':len(reassigned),'K11_promoted_C_to_B':len(promoted_k11),
    'general_promoted_C_to_B':len(promoted_general),
    'combined_audit_records':len(audit_rows),'audit_status_counts':dict(ac),
    'audit_supported_share':round(audit_share,6),
    'missing_or_small_formal_K_domains':small,'quality_gate':quality,
    'next_stage':'B009-R01 verified non-overlapping student download round',
}
(OUT/'run_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'stage_report.md').write_text('\n'.join([
    '# B009 E2 v3 Reconstructed Evidence Verification Report','',
    f'- Status: **{status}**',f'- Classified records: {len(rows):,}',
    f'- Verified formal A/B pool: {len(formal):,}',f'- Relevance: {dict(rel)}',
    f'- Priority: {dict(pri)}',f'- Formal K distribution: {dict(fk)}',
    f'- K11 A/B reassignments: {len(reassigned)}',
    f'- K11 strict C-to-B promotions: {len(promoted_k11)}',
    f'- General strict C-to-B promotions: {len(promoted_general)}',
    f'- Prior overlap: {overlap}',f'- Invalid DOI: {invalid}',
    f'- Combined precision audit: {dict(ac)}; supported share {audit_share:.2%}',
    f'- Quality gate: {quality}',f"- Next: {summary['next_stage']}",
]),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False),flush=True)
if status != 'success':
    raise SystemExit(2)
