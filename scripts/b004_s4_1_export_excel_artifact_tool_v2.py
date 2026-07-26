from pathlib import Path

source_path = Path("scripts/b004_s4_1_export_excel_artifact_tool.py")
source = source_path.read_text(encoding="utf-8")
source = source.replace(
    'zip_path = Path("/mnt/data/B004_R01_10000篇文献_10名学生Excel下载任务包.zip")',
    'zip_path = OUT / "B004_R01_10000篇文献_10名学生Excel下载任务包.zip"',
)
source = source.replace(
    'validation_path = Path("/mnt/data/B004_R01_Excel生成与核验报告.json")',
    'validation_path = OUT / "B004_R01_Excel生成与核验报告.json"',
)
exec(compile(source, "b004_s4_1_export_excel_artifact_tool_v2", "exec"))
