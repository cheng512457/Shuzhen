from pathlib import Path

source = Path('scripts/b009_e2_v3_reconstructed_evidence.py').read_text(encoding='utf-8')
old = """    if r.get('doi') in adjusted_set:
        supported = ev['strict_k11_ab'] or ev['strict_k11_c'] or ev['exceptional_k11_c'] if k == 'K11' else ev['strict_general'] or ev['exceptional_general']
    else:
        supported = r.get('relevance') in {'A','B'} and not ev['hard'] and bool(DOI_RE.match(r.get('doi') or ''))
"""
new = """    if r.get('doi') in adjusted_set:
        try:
            saved = json.loads(r.get('v3_evidence') or '{}')
        except Exception:
            saved = {}
        adjustment = r.get('v3_adjustment') or ''
        if 'K11 multi-domain A/B reassignment' in adjustment:
            supported = bool(saved.get('strict_k11_ab'))
        elif 'K11 C-to-B rescue' in adjustment:
            supported = bool(saved.get('strict_k11_c') or saved.get('exceptional_k11_c'))
        else:
            supported = bool(saved.get('strict_general') or saved.get('exceptional_general'))
        ev = saved or ev
    else:
        supported = r.get('relevance') in {'A','B'} and not ev['hard'] and bool(DOI_RE.match(r.get('doi') or ''))
"""
if old not in source:
    raise RuntimeError('Unable to patch B009 E2 v3 audit block')
source = source.replace(old, new)
exec(compile(source, 'scripts/b009_e2_v3_reconstructed_evidence_runtime.py', 'exec'))
