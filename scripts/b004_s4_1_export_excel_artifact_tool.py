import csv
import json
import sys
import zipfile
from collections import Counter
from pathlib import Path

from artifact_tool import Workbook, SpreadsheetFile

try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(2**31 - 1)

ROOT = Path("input_artifact")
OUT = Path("out_excel")
OUT.mkdir(exist_ok=True)

K_NAMES = {
    "K01":"食品蛋白资源与组分基础","K02":"蛋白提取、分离与配料制备","K03":"蛋白结构与物理功能",
    "K04":"蛋白加工与改性","K05":"食品蛋白酶解液与水解物","K06":"食源肽与肽组学",
    "K07":"消化、吸收、暴露与代谢","K08":"健康靶点、机制与人群证据","K09":"食品酶资源与催化科学",
    "K10":"蛋白设计与蛋白工程","K11":"肽设计与序列优化","K12":"酶设计与酶工程",
    "K13":"生物制造与合成生物学","K14":"真实食品、感官与递送","K15":"分析方法、数据工程与智能过程",
    "K16":"安全、过敏、法规与可持续利用",
}

DISPLAY_FIELDS = [
    ("B004_ID","B004编号"),("student","学生"),("K_primary","K域"),("K_primary_name","K域名称"),
    ("G_primary","G组映射"),("relevance","相关性"),("download_priority","优先级"),("evidence_mode","筛选证据"),
    ("title","文献题目"),("first_author","第一作者"),("year","年份"),("journal","期刊"),("doi","DOI"),
    ("DOI_URL","DOI链接"),("PDF_filename","PDF文件名"),("download_status","下载状态"),
    ("link_audit_result","链接审核"),("link_http_status","HTTP状态"),("link_audit_note","链接说明"),
    ("link_final_url","最终访问链接"),("classification_score","分类得分"),("classification_confidence","分类置信度"),
    ("inclusion_reason","纳入理由"),("abstract","摘要"),("document_type","文献类型"),("cited_by_count","被引次数"),
    ("is_oa","开放获取"),("source_stages","数据来源阶段"),("source_names","元数据来源"),("memberships","主题标签"),
    ("metadata_status","元数据状态"),("title_consistency","题名一致性"),("integrity_status","完整性状态"),
    ("source_record_count","来源记录数"),("article_link","原始文章链接"),
]

TITLE_FILL = "#173B57"
HEADER_FILL = "#2D678E"
SUB_FILL = "#DCEAF3"
LIGHT_FILL = "#F4F7F9"
GREEN_FILL = "#E8F5E9"
YELLOW_FILL = "#FFF4E5"
RED_FILL = "#FEE2E2"
BORDER = "#D7E0E6"


def style_title(sheet, cell_range, text):
    sheet.merge_cells(cell_range)
    first = cell_range.split(":")[0]
    sheet.get_range(first).values = [[text]]
    sheet.get_range(cell_range).format = {
        "fill": TITLE_FILL,
        "font": {"bold": True, "color": "#FFFFFF", "size": 16},
        "horizontal_alignment": "left",
        "vertical_alignment": "center",
    }
    sheet.get_range(cell_range).format.row_height = 30


def style_header(rng):
    rng.format = {
        "fill": HEADER_FILL,
        "font": {"bold": True, "color": "#FFFFFF"},
        "horizontal_alignment": "center",
        "vertical_alignment": "center",
        "wrap_text": True,
        "borders": {"items": [{"side":"EdgeBottom","color":BORDER,"style":"continuous","weight":1}]},
    }


def col_letter(n):
    out = ""
    while n:
        n, rem = divmod(n - 1, 26)
        out = chr(65 + rem) + out
    return out


def build_workbook(student_no, rows):
    student = f"Student{student_no:02d}"
    wb = Workbook.create()

    # Instructions and statistics.
    s = wb.worksheets.add("任务说明与统计")
    style_title(s, "A1:H1", f"B004-R01｜{student}｜1,000篇文献全文下载任务")
    s.get_range("A3:B13").values = [
        ["项目","内容"],
        ["任务批次","B004-R01 首轮10,000篇"],
        ["学生编号",student],
        ["文献数量",len(rows)],
        ["编号范围",f"{rows[0].get('B004_ID','')} 至 {rows[-1].get('B004_ID','')}"],
        ["PDF命名","必须严格使用“PDF文件名”列，例如 B004-000001.pdf"],
        ["下载状态","下载完成后填写：已下载；无法获取时填写：无法获取；题录异常填写：需要替换"],
        ["403/429说明","访问受限、订阅墙或限流不等于DOI无效，可通过学校数据库、出版社、PubMed或作者主页获取"],
        ["链接无效处理","先复制DOI到学校数据库或Crossref检索；仍无法确认时标记“需要替换”，不得自行更换文献"],
        ["全文要求","优先下载Publisher Version PDF；无法获得时可下载Author Accepted Manuscript，并在备注中说明"],
        ["回收要求","保持文件名不变，将1,000篇PDF放入以学生编号命名的单独文件夹"],
    ]
    style_header(s.get_range("A3:B3"))
    s.get_range("A4:B13").format.wrap_text = True
    s.get_range("A:A").format.column_width = 25
    s.get_range("B:B").format.column_width = 82

    k_counts = Counter(r.get("K_primary") or "" for r in rows)
    rel_counts = Counter(r.get("relevance") or "" for r in rows)
    pri_counts = Counter(r.get("download_priority") or "" for r in rows)
    audit_counts = Counter(r.get("link_audit_result") or "" for r in rows)
    ev_counts = Counter(r.get("evidence_mode") or "" for r in rows)

    s.get_range("D3:H3").values = [["统计项目","类别","数量","占比","说明"]]
    style_header(s.get_range("D3:H3"))
    stat_rows = []
    for k in [f"K{i:02d}" for i in range(1,17)]:
        if k_counts.get(k):
            stat_rows.append(["K域",k,k_counts[k],k_counts[k]/len(rows),K_NAMES.get(k,"")])
    for key, count in sorted(rel_counts.items()):
        stat_rows.append(["相关性",key,count,count/len(rows),"A为直接核心，B为关键支撑"])
    for key, count in sorted(pri_counts.items()):
        stat_rows.append(["下载优先级",key,count,count/len(rows),"P0优先于P1/P2"])
    for key, count in sorted(ev_counts.items()):
        stat_rows.append(["证据模式",key,count,count/len(rows),"题名、摘要与上游领域先验组合"])
    for key, count in sorted(audit_counts.items()):
        stat_rows.append(["链接审核",key,count,count/len(rows),"访问限制不等于DOI无效"])
    end_stat = 3 + len(stat_rows)
    s.get_range(f"D4:H{end_stat}").values = stat_rows
    s.get_range(f"D4:H{end_stat}").format.wrap_text = True
    s.get_range(f"G4:G{end_stat}").format.number_format = "0.00%"
    for col, width in {"D:D":18,"E:E":18,"F:F":12,"G:G":12,"H:H":44}.items():
        s.get_range(col).format.column_width = width
    s.freeze_panes.freeze_rows(3)

    # Download task sheet.
    d = wb.worksheets.add("下载任务")
    style_title(d, "A1:AI1", f"{student}｜B004-R01文献下载清单（1,000篇）")
    d.get_range("A2:AI2").merge()
    d.get_range("A2").values = [["操作要求：按“PDF文件名”保存；下载完成后更新“下载状态”；不得自行删除、替换或重编号。最后三列保留文章访问链接。"]]
    d.get_range("A2:AI2").format = {"fill": SUB_FILL,"font":{"bold":True,"color":"#173B57"},"wrap_text":True,"vertical_alignment":"center"}
    d.get_range("A2:AI2").format.row_height = 32

    headers_cn = [cn for _,cn in DISPLAY_FIELDS]
    data = [[r.get(field, "") for field,_ in DISPLAY_FIELDS] for r in rows]
    last_col = col_letter(len(DISPLAY_FIELDS))
    d.get_range(f"A4:{last_col}{4+len(data)}").values = [headers_cn] + data
    style_header(d.get_range(f"A4:{last_col}4"))
    d.get_range(f"A5:{last_col}{4+len(data)}").format = {"vertical_alignment":"top","wrap_text":False}
    d.get_range(f"I5:I{4+len(data)}").format.wrap_text = True
    d.get_range(f"W5:X{4+len(data)}").format.wrap_text = True
    d.get_range(f"A4:{last_col}{4+len(data)}").format.borders = {"items":[{"side":"InsideHorizontal","color":"#E6ECEF","style":"continuous","weight":1}]}

    widths = {
        "A:A":16,"B:B":12,"C:C":9,"D:D":28,"E:E":12,"F:F":10,"G:G":11,"H:H":15,
        "I:I":62,"J:J":20,"K:K":9,"L:L":28,"M:M":28,"N:N":34,"O:O":20,"P:P":14,
        "Q:Q":13,"R:R":11,"S:S":34,"T:T":42,"U:V":13,"W:W":48,"X:X":72,"Y:Y":14,
        "Z:Z":12,"AA:AA":12,"AB:AB":18,"AC:AC":22,"AD:AD":35,"AE:AE":20,"AF:AF":14,
        "AG:AG":18,"AH:AH":14,"AI:AI":42,
    }
    for col, width in widths.items():
        d.get_range(col).format.column_width = width
    d.get_range(f"K5:K{4+len(data)}").format.number_format = "0"
    d.get_range(f"Z5:Z{4+len(data)}").format.number_format = "0"
    d.get_range(f"U5:V{4+len(data)}").format.number_format = "0.000"
    d.get_range(f"AF5:AF{4+len(data)}").format.number_format = "0.000"
    d.freeze_panes.freeze_rows(4)
    d.freeze_panes.freeze_columns(8)
    d.tables.add(f"A4:{last_col}{4+len(data)}", True, f"TaskTable{student_no:02d}")

    # Data validation and conditional formatting.
    d.get_range(f"P5:P{4+len(data)}").data_validation = {"rule":{"type":"list","values":["待下载","已下载","无法获取","需要替换"]}}
    d.get_range(f"F5:F{4+len(data)}").conditional_formats.add_custom('=F5="A"', {"fill":GREEN_FILL,"font":{"color":"#166534","bold":True}})
    d.get_range(f"F5:F{4+len(data)}").conditional_formats.add_custom('=F5="B"', {"fill":YELLOW_FILL,"font":{"color":"#92400E","bold":True}})
    d.get_range(f"G5:G{4+len(data)}").conditional_formats.add_custom('=G5="P0"', {"fill":"#DBEAFE","font":{"color":"#1D4ED8","bold":True}})
    d.get_range(f"Q5:Q{4+len(data)}").conditional_formats.add_custom('=Q5="链接可用"', {"fill":GREEN_FILL,"font":{"color":"#166534"}})
    d.get_range(f"Q5:Q{4+len(data)}").conditional_formats.add_custom('=Q5="需复核"', {"fill":YELLOW_FILL,"font":{"color":"#92400E"}})
    d.get_range(f"Q5:Q{4+len(data)}").conditional_formats.add_custom('=Q5="链接无效"', {"fill":RED_FILL,"font":{"color":"#991B1B","bold":True}})
    d.get_range(f"P5:P{4+len(data)}").conditional_formats.add_custom('=P5="已下载"', {"fill":GREEN_FILL,"font":{"color":"#166534"}})
    d.get_range(f"P5:P{4+len(data)}").conditional_formats.add_custom('=P5="需要替换"', {"fill":RED_FILL,"font":{"color":"#991B1B","bold":True}})

    # Compact audit list for records needing attention.
    a = wb.worksheets.add("链接复核")
    attention = [r for r in rows if r.get("link_audit_result") != "链接可用"]
    style_title(a, "A1:J1", f"{student}｜需复核或无效链接记录")
    a.get_range("A3:J3").values = [["B004编号","题目","DOI","DOI链接","审核结果","HTTP状态","审核说明","最终访问链接","PDF文件名","处理状态"]]
    style_header(a.get_range("A3:J3"))
    attention_data = [[r.get("B004_ID",""),r.get("title",""),r.get("doi",""),r.get("DOI_URL",""),r.get("link_audit_result",""),r.get("link_http_status",""),r.get("link_audit_note",""),r.get("link_final_url",""),r.get("PDF_filename",""),"待处理"] for r in attention]
    if attention_data:
        a.get_range(f"A4:J{3+len(attention_data)}").values = attention_data
        a.get_range(f"J4:J{3+len(attention_data)}").data_validation = {"rule":{"type":"list","values":["待处理","已解决","无法获取","申请替换"]}}
        a.get_range(f"B4:B{3+len(attention_data)}").format.wrap_text = True
    else:
        a.get_range("A4:J4").merge()
        a.get_range("A4").values = [["本学生任务中没有需复核或无效链接。"]]
    for col,width in {"A:A":16,"B:B":62,"C:C":30,"D:D":34,"E:E":14,"F:F":11,"G:G":38,"H:H":42,"I:I":20,"J:J":14}.items():
        a.get_range(col).format.column_width = width
    a.freeze_panes.freeze_rows(3)

    # Verify representative regions and error tokens before export.
    wb.inspect({"kind":"table","range":"任务说明与统计!A1:H12","include":"values,formulas","table_max_rows":14,"table_max_cols":10})
    wb.inspect({"kind":"table","range":"下载任务!A1:J12","include":"values,formulas","table_max_rows":14,"table_max_cols":12})
    errors = wb.inspect({
        "kind":"match",
        "search_term":"#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
        "options":{"use_regex":True,"max_results":100},
        "summary":"formula error scan",
    })
    if "#REF!" in errors.ndjson or "#DIV/0!" in errors.ndjson or "#VALUE!" in errors.ndjson or "#NAME?" in errors.ndjson:
        raise RuntimeError(f"Formula error detected for {student}: {errors.ndjson}")
    return wb


summary_files = list(ROOT.rglob("run_summary.json"))
if not summary_files:
    raise RuntimeError("Missing S4.1 run_summary.json")
run_summary = json.loads(summary_files[0].read_text(encoding="utf-8"))
if run_summary.get("status") != "success":
    raise RuntimeError("S4.1 artifact status is not success")

created = []
validation = {}
for i in range(1, 11):
    files = list(ROOT.rglob(f"B004_R01_Student{i:02d}_1000.csv"))
    if len(files) != 1:
        raise RuntimeError(f"Expected one Student{i:02d} CSV, found {len(files)}")
    with files[0].open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if len(rows) != 1000 or len({r.get('doi','').lower() for r in rows}) != 1000:
        raise RuntimeError(f"Student{i:02d} CSV failed count/DOI validation")
    validation[f"Student{i:02d}"] = {
        "records": len(rows),
        "unique_dois": len({r.get('doi','').lower() for r in rows}),
        "attention_links": sum(1 for r in rows if r.get('link_audit_result') != '链接可用'),
    }
    wb = build_workbook(i, rows)
    out_path = OUT / f"B004_R01_Student{i:02d}_文献下载任务_1000篇.xlsx"
    SpreadsheetFile.export_xlsx(wb).save(out_path)
    created.append(out_path)

readme = OUT / "B004_R01_学生下载说明.txt"
readme.write_text(
    "B004-R01首轮文献下载任务\n"
    "1. 每名学生1,000篇，共10,000篇，编号B004-000001至B004-010000。\n"
    "2. PDF必须严格按照Excel中的PDF文件名保存，不得增加作者、题目或其他字符。\n"
    "3. 403、429、订阅墙等访问限制不等于DOI无效，请通过学校数据库、出版社、PubMed或作者主页获取。\n"
    "4. 链接审核为“需复核”或“链接无效”的记录已单独列入“链接复核”工作表。\n"
    "5. 不得自行替换文献；确认题录异常后标记“需要替换”，统一回收处理。\n",
    encoding="utf-8",
)

zip_path = Path("/mnt/data/B004_R01_10000篇文献_10名学生Excel下载任务包.zip")
with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    for path in created + [readme]:
        zf.write(path, arcname=path.name)

validation_path = Path("/mnt/data/B004_R01_Excel生成与核验报告.json")
validation_path.write_text(json.dumps({"source_summary":run_summary,"excel_validation":validation,"files":[p.name for p in created],"zip":zip_path.name},ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps({"created_files":len(created),"zip":str(zip_path),"validation":validation},ensure_ascii=False))
