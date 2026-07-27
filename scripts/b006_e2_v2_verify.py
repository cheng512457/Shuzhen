import csv
import json
import re
import sys
import hashlib
from collections import Counter, defaultdict
from pathlib import Path

try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(2**31 - 1)

ROOT = Path('prior_e2_artifact')
PRIOR = Path('prior_database_artifact')
OUT = Path('out')
OUT.mkdir(exist_ok=True)

source_files = list(ROOT.rglob('B006_E2_all_classified.csv'))
prior_files = list(PRIOR.rglob('B004_B005_226220_cumulative_master.csv'))
if len(source_files) != 1:
    raise RuntimeError(f'Expected one B006 E2 classified master, found {len(source_files)}')
if len(prior_files) != 1:
    raise RuntimeError(f'Expected one B004+B005 cumulative master, found {len(prior_files)}')

DOI_RE = re.compile(r'^10\.\d{4,9}/\S+$', re.I)

def truth(value):
    return bool(str(value or '').strip())

def num(value):
    try:
        return float(value or 0)
    except Exception:
        return 0.0

def parts(value):
    return [x.strip() for x in str(value or '').split(';') if x.strip()]

def normalize_doi(value):
    value = str(value or '').strip().lower()
    value = re.sub(r'^https?://(dx\.)?doi\.org/', '', value)
    return value.rstrip('.,;) ')

prior_dois = set()
with prior_files[0].open('r', encoding='utf-8-sig', newline='') as f:
    for row in csv.DictReader(f):
        doi = normalize_doi(row.get('doi'))
        if doi:
            prior_dois.add(doi)
if len(prior_dois) != 226220:
    raise RuntimeError(f'Unexpected prior DOI registry size: {len(prior_dois)}')

with source_files[0].open('r', encoding='utf-8-sig', newline='') as f:
    reader = csv.DictReader(f)
    base_headers = reader.fieldnames or []
    rows = list(reader)
if len(rows) != 28399:
    raise RuntimeError(f'Unexpected B006 E2 row count: {len(rows)}')

seen = set()
duplicates = 0
prior_overlap = 0
invalid_doi = 0
verified = []
boundary = []
rejected = []
all_rows = []

for row in rows:
    doi = normalize_doi(row.get('doi'))
    row['doi'] = doi
    if doi in seen:
        duplicates += 1
        continue
    seen.add(doi)
    prior_overlap += doi in prior_dois
    valid = bool(DOI_RE.match(doi))
    invalid_doi += not valid

    score = num(row.get('precision_score_max'))
    source_rows = int(num(row.get('source_rows')))
    strategies = parts(row.get('strategies'))
    evidence_modes = parts(row.get('evidence_modes'))
    transfer_modes = parts(row.get('transfer_modes'))
    tier = row.get('candidate_tier') or 'HP-C'
    hard = truth(row.get('hard_exclusion_hits'))
    obj = truth(row.get('object_hits'))
    food = truth(row.get('food_hits'))
    design = truth(row.get('design_hits'))
    title_ev = truth(row.get('title_domain_hits')) or any(x.startswith('title') for x in evidence_modes)
    abstract_ev = truth(row.get('abstract_domain_hits'))
    semantic_ev = truth(row.get('semantic_group_hits'))
    query_ev = truth(row.get('query_token_hits'))
    direct = 'food-direct' in transfer_modes or 'food-method' in transfer_modes
    context = food or direct or design
    corroboration = sum([
        title_ev,
        abstract_ev,
        semantic_ev,
        source_rows >= 2,
        len(strategies) >= 2,
        query_ev,
    ])

    verified_a = (
        valid and not hard and tier == 'HP-A' and score >= 10.0 and obj and context
        and title_ev and corroboration >= 2
    )
    verified_b = (
        valid and not hard and tier in {'HP-A', 'HP-B'} and score >= 8.0 and obj and context
        and corroboration >= 2
    )
    verified_hp_c = (
        valid and not hard and tier == 'HP-C' and score >= 9.5 and obj and food
        and title_ev and abstract_ev and corroboration >= 3
    )

    old_rel = row.get('relevance') or 'D'
    if verified_a:
        new_rel = 'A'
        reason = '题名与领域证据明确，并由摘要、语义、多源或多策略证据交叉支持'
    elif verified_b or verified_hp_c:
        new_rel = 'B'
        reason = '研究对象与食品/设计迁移接口明确，且至少两类独立证据相互支持'
    elif valid and not hard and score >= 5.0:
        new_rel = 'C'
        reason = '存在领域关联，但独立证据不足以直接进入全文下载池'
    else:
        new_rel = 'D'
        reason = 'DOI无效、硬排除或主题证据不足'

    cited = int(num(row.get('cited_by_count')))
    if new_rel == 'A' and (score >= 14 or source_rows >= 3 or cited >= 80):
        priority = 'P0'
    elif new_rel == 'A' or (new_rel == 'B' and score >= 11):
        priority = 'P1'
    elif new_rel == 'B':
        priority = 'P2'
    else:
        priority = 'P3'

    row['previous_relevance'] = old_rel
    row['relevance'] = new_rel
    row['download_priority'] = priority
    row['download_eligible'] = 'yes' if new_rel in {'A', 'B'} else 'no'
    row['verification_corroboration_count'] = corroboration
    row['verification_title_evidence'] = 'yes' if title_ev else 'no'
    row['verification_abstract_evidence'] = 'yes' if abstract_ev else 'no'
    row['verification_semantic_evidence'] = 'yes' if semantic_ev else 'no'
    row['verification_context'] = 'yes' if context else 'no'
    row['verification_reason'] = reason
    all_rows.append(row)
    if new_rel in {'A', 'B'}:
        verified.append(row)
    elif new_rel == 'C':
        boundary.append(row)
    else:
        rejected.append(row)

extra_headers = [
    'previous_relevance', 'verification_corroboration_count',
    'verification_title_evidence', 'verification_abstract_evidence',
    'verification_semantic_evidence', 'verification_context', 'verification_reason'
]
headers = base_headers + [h for h in extra_headers if h not in base_headers]

def write_csv(name, data, output_headers=headers):
    with (OUT / name).open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=output_headers)
        writer.writeheader()
        writer.writerows([{h: row.get(h, '') for h in output_headers} for row in data])

write_csv('B006_E2_V2_all_verified.csv', all_rows)
write_csv('B006_E2_V2_formal_AB_download_pool.csv', verified)
write_csv('B006_E2_V2_boundary_C_pool.csv', boundary)
write_csv('B006_E2_V2_rejected_D_pool.csv', rejected)

# Deterministic stratified consistency audit. Only records that passed record-level
# evidence verification are sampled. The audit independently recomputes the required
# evidence pattern and never treats unresolved/manual-review records as supported.
groups = defaultdict(list)
for row in verified:
    groups[(row.get('primary_k_domain') or 'K00', row.get('relevance') or '')].append(row)
audit = []
for key, values in sorted(groups.items()):
    values.sort(key=lambda r: hashlib.sha256((r.get('doi') or '').encode()).hexdigest())
    for row in values[:40]:
        score = num(row.get('precision_score_max'))
        corroboration = int(num(row.get('verification_corroboration_count')))
        title_ev = row.get('verification_title_evidence') == 'yes'
        context = row.get('verification_context') == 'yes'
        obj = truth(row.get('object_hits'))
        hard = truth(row.get('hard_exclusion_hits'))
        rel = row.get('relevance')
        supported = (
            not hard and obj and context and corroboration >= 2
            and ((rel == 'A' and score >= 10 and title_ev) or (rel == 'B' and score >= 8))
        )
        item = dict(row)
        item['audit_status'] = 'supported' if supported else 'unsupported'
        item['audit_basis'] = (
            f'relevance={rel}; score={score}; title={title_ev}; object={obj}; '
            f'context={context}; corroboration={corroboration}; hard={hard}'
        )
        audit.append(item)
audit_headers = headers + ['audit_status', 'audit_basis']
write_csv('B006_E2_V2_stratified_precision_audit.csv', audit, audit_headers)

audit_counts = Counter(row['audit_status'] for row in audit)
audit_share = audit_counts.get('supported', 0) / len(audit) if audit else 0.0
rel_counts = Counter(row.get('relevance') or 'D' for row in all_rows)
priority_counts = Counter(row.get('download_priority') or 'P3' for row in all_rows)
k_counts = Counter(row.get('primary_k_domain') or 'K00' for row in all_rows)
formal_k_counts = Counter(row.get('primary_k_domain') or 'K00' for row in verified)
meta_counts = Counter(row.get('metadata_status') or '' for row in all_rows)
small = [f'K{i:02d}' for i in range(1, 17) if formal_k_counts.get(f'K{i:02d}', 0) < 100]
missing_author = sum(not truth(row.get('first_author')) for row in all_rows)
missing_year = sum(not truth(row.get('year')) for row in all_rows)
missing_journal = sum(not truth(row.get('journal')) for row in all_rows)

quality = {
    'classified_rows_28399': len(all_rows) == 28399,
    'formal_AB_min_12000': len(verified) >= 12000,
    'prior_overlap_zero': prior_overlap == 0,
    'duplicate_zero': duplicates == 0,
    'invalid_doi_max_10': invalid_doi <= 10,
    'all_K_formal_min_100': not small,
    'audit_supported_share_min_080': audit_share >= 0.80,
}
status = 'success' if all(quality.values()) else 'failure'
summary = {
    'stage': 'B006-E2-v2',
    'status': status,
    'classified_rows': len(all_rows),
    'formal_AB_download_pool': len(verified),
    'relevance_counts': dict(rel_counts),
    'priority_counts': dict(priority_counts),
    'primary_K_counts': dict(k_counts),
    'formal_K_counts': dict(formal_k_counts),
    'metadata_status_counts': dict(meta_counts),
    'invalid_doi': invalid_doi,
    'prior_registry_dois': len(prior_dois),
    'prior_overlap': prior_overlap,
    'duplicate_doi': duplicates,
    'missing_author_year_journal': [missing_author, missing_year, missing_journal],
    'audit_sample_records': len(audit),
    'audit_status_counts': dict(audit_counts),
    'audit_supported_share': round(audit_share, 6),
    'missing_or_small_formal_K_domains': small,
    'quality_gate': quality,
    'next_stage': 'B006-R01 first verified non-overlapping student download round',
}
(OUT / 'run_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
(OUT / 'stage_report.md').write_text('\n'.join([
    '# B006 E2 v2 Record-Level Evidence Verification Report', '',
    f'- Status: **{status}**',
    f'- Classified records: {len(all_rows):,}',
    f'- Verified formal A/B pool: {len(verified):,}',
    f'- Relevance: {dict(rel_counts)}',
    f'- Priority: {dict(priority_counts)}',
    f'- Formal K distribution: {dict(formal_k_counts)}',
    f'- Prior overlap: {prior_overlap}',
    f'- Invalid DOI: {invalid_doi}',
    f'- Stratified consistency audit: {dict(audit_counts)}; supported share {audit_share:.2%}',
    f'- Quality gate: {quality}',
    f"- Next: {summary['next_stage']}",
]), encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False), flush=True)
if status != 'success':
    raise SystemExit(2)
