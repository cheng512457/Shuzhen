from pathlib import Path

source_path = Path("scripts/b004_s4_1_export_excel_artifact_tool.py")
source = source_path.read_text(encoding="utf-8")

replacements = [
    ("B004-R01", "B004-R02"),
    ("B004_R01", "B004_R02"),
    ("首轮10,000篇", "第二轮30,000篇"),
    ("首轮文献下载任务", "第二轮文献下载任务"),
    ("1,000篇文献全文下载任务", "3,000篇文献全文下载任务"),
    ("文献下载清单（1,000篇）", "文献下载清单（3,000篇）"),
    ("将1,000篇PDF放入", "将3,000篇PDF放入"),
    ("_Student{i:02d}_1000.csv", "_Student{i:02d}_3000.csv"),
    ("!= 1000", "!= 3000"),
    ("_文献下载任务_1000篇.xlsx", "_文献下载任务_3000篇.xlsx"),
    ("每名学生1,000篇，共10,000篇，编号B004-000001至B004-010000。", "每名学生3,000篇，共30,000篇，编号B004-010001至B004-040000。"),
    ("B004-000001.pdf", "B004-010001.pdf"),
    ('zip_path = Path("/mnt/data/B004_R02_10000篇文献_10名学生Excel下载任务包.zip")', 'zip_path = OUT / "B004_R02_30000篇文献_10名学生Excel下载任务包.zip"'),
    ('validation_path = Path("/mnt/data/B004_R02_Excel生成与核验报告.json")', 'validation_path = OUT / "B004_R02_Excel生成与核验报告.json"'),
]
for old, new in replacements:
    source = source.replace(old, new)

required_tokens = [
    "B004_R02_Student{i:02d}_3000.csv",
    "len(rows) != 3000",
    "B004_R02_Student{i:02d}_文献下载任务_3000篇.xlsx",
    "B004_R02_30000篇文献_10名学生Excel下载任务包.zip",
]
missing = [token for token in required_tokens if token not in source]
if missing:
    raise RuntimeError(f"R02 wrapper replacement incomplete: {missing}")

exec(compile(source, "b004_r02_export_excel_artifact_tool", "exec"))
