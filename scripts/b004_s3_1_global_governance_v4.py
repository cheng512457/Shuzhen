import csv
import sys
import traceback
from pathlib import Path

# Retry strategy after run 30198906984: retain large CSV support, fix the 24-column
# insert, use a separate read connection while writing the DOI registry, commit
# progress checkpoints, and always emit a traceback artifact on failure.
try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(2**31 - 1)

source_path = Path("scripts/b004_s3_1_global_governance_v2.py")
source = source_path.read_text(encoding="utf-8")

replacements = [
    (
        'write_cur.execute("INSERT INTO doi_registry VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (',
        'write_cur.execute("INSERT INTO doi_registry VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", ('
    ),
    (
        'def flush_group(group):\n    if not group or not group[0][1]:',
        'def flush_group(group):\n    global registry_written\n    if not group or not group[0][1]:'
    ),
    (
        'conn = sqlite3.connect(DB)\nwrite_cur = conn.cursor()',
        'conn = sqlite3.connect(DB)\nwrite_cur = conn.cursor()\nregistry_written = 0'
    ),
    (
        '    ))\n\nread_cur = conn.cursor()\nquery = "SELECT doi,doi_valid,source_stage,source_names,title,title_norm,first_author,authors,year,journal,document_type,abstract,cited_by_count,is_oa,memberships,external_ids,article_link,openalex_id,input_order FROM raw_record ORDER BY doi,input_order"',
        '    ))\n    registry_written += 1\n    if registry_written % 50000 == 0:\n        conn.commit()\n        print("REGISTRY_PROGRESS", registry_written, flush=True)\n\nread_conn = sqlite3.connect(DB)\nread_cur = read_conn.cursor()\nquery = "SELECT doi,doi_valid,source_stage,source_names,title,title_norm,first_author,authors,year,journal,document_type,abstract,cited_by_count,is_oa,memberships,external_ids,article_link,openalex_id,input_order FROM raw_record ORDER BY doi,input_order"'
    ),
    (
        'flush_group(bucket)\nconn.commit()\n\nwrite_cur.execute("CREATE INDEX idx_registry_title_norm ON doi_registry(title_norm)")',
        'flush_group(bucket)\nread_conn.close()\nconn.commit()\nprint("REGISTRY_COMPLETE", registry_written, flush=True)\n\nwrite_cur.execute("CREATE INDEX idx_registry_title_norm ON doi_registry(title_norm)")'
    ),
]

for old, new in replacements:
    if old not in source:
        raise RuntimeError("S3.1 retry patch marker not found: " + old[:100])
    source = source.replace(old, new, 1)

try:
    exec(compile(source, "b004_s3_1_global_governance_v4_patched", "exec"))
except Exception:
    out = Path("out")
    out.mkdir(exist_ok=True)
    trace = traceback.format_exc()
    (out / "failure_traceback.txt").write_text(trace, encoding="utf-8")
    print(trace, flush=True)
    raise
