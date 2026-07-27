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

ROOT = Path("prior_rounds")
OUT = Path("out")
OUT.mkdir(exist_ok=True)


def clean_doi(value):
    value = str(value or "").strip().lower()
    value = re.sub(r"^https?://(dx\.)?doi\.org/", "", value)
    return value.rstrip(".,;) ")

master_files = sorted(
    p for p in ROOT.rglob("*.csv")
    if "master" in p.name.lower() and "audited" in p.name.lower()
)
if len(master_files) != 6:
    raise RuntimeError(f"Expected six B004 audited master CSVs, found {len(master_files)}: {[str(p) for p in master_files]}")

dois = set()
file_counts = {}
duplicates_within_or_across = Counter()
for path in master_files:
    local = set()
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            doi = clean_doi(row.get("doi"))
            if not doi:
                continue
            if doi in local:
                duplicates_within_or_across[doi] += 1
            local.add(doi)
            if doi in dois:
                duplicates_within_or_across[doi] += 1
            dois.add(doi)
    file_counts[path.name] = len(local)

expected = 157917
status = "success" if len(dois) == expected and not duplicates_within_or_across else "failure"
(OUT / "B004_157917_excluded_dois.txt").write_text("\n".join(sorted(dois)), encoding="utf-8")
summary = {
    "stage": "B005-exclusion-registry",
    "status": status,
    "master_files": [str(p) for p in master_files],
    "file_unique_doi_counts": file_counts,
    "global_unique_dois": len(dois),
    "expected_unique_dois": expected,
    "duplicate_dois_detected": len(duplicates_within_or_across),
}
(OUT / "B005_exclusion_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False), flush=True)
if status != "success":
    raise SystemExit(2)
