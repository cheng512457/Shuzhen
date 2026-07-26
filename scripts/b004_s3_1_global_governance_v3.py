import csv
import sys
from pathlib import Path

# PubMed/Europe PMC abstracts can exceed Python's conservative CSV field limit.
try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(2**31 - 1)

source_path = Path("scripts/b004_s3_1_global_governance_v2.py")
source = source_path.read_text(encoding="utf-8")
old = 'write_cur.execute("INSERT INTO doi_registry VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", ('
new = 'write_cur.execute("INSERT INTO doi_registry VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", ('
if old not in source:
    raise RuntimeError("S3.1 insertion marker not found")
source = source.replace(old, new, 1)
exec(compile(source, "b004_s3_1_global_governance_v3_patched", "exec"))
