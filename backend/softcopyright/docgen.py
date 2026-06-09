from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from .blueprint import ProductBlueprint
from .models import GenerationTask
from .sourcegen import read_source_line_entries, read_source_lines


def ensure_docx_available() -> tuple[bool, str | None]:
    try:
        import docx  # noqa: F401

        return True, None
    except ImportError as exc:
        return False, str(exc)


def generate_manual_docx(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    output_dir: Path,
    manual_content: dict | None = None,
    ui_screenshots: dict | None = None,
    design_brief: dict | None = None,
) -> Path:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt, RGBColor

    path = output_dir / f"{task.safe_name}.docx"
    document = Document()
    _set_default_font(document, "宋体", 10.5)

    section = document.sections[0]
    section.top_margin = Pt(54)
    section.bottom_margin = Pt(54)
    section.left_margin = Pt(72)
    section.right_margin = Pt(72)
    header = section.header.paragraphs[0]
    header.text = f"{task.software_name} {task.version}"
    header.alignment = WD_ALIGN_PARAGRAPH.CENTER

    title = document.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run(f"{task.software_name}软件说明书")
    run.bold = True
    run.font.size = Pt(18)

    subtitle = document.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.add_run(f"版本号：{task.version}")

    _add_heading(document, "一、软件概述")
    overview_paragraphs = _content_paragraphs(
        manual_content,
        "overview",
        [
            blueprint.summary,
            blueprint.positioning or f"本软件面向{blueprint.industry}场景，重点解决业务数据分散、处理流程不统一、运行状态缺少跟踪、统计分析依赖人工汇总等问题。",
            f"系统具体服务于{blueprint.scenario or blueprint.industry}，围绕{_join_items(blueprint.business_objects[:8]) or '核心业务对象'}完成登记、校验、处理、统计和归档。",
            f"系统采用{task.language}进行主要功能开发，通过模块化设计完成{_join_items(blueprint.technical_features[:4]) or '用户操作、业务处理、数据查询、统计分析和权限审计'}等能力。",
            f"产品方案内置{_workflow_summary(blueprint)}，确保说明书、源码工程和界面截图围绕同一业务闭环生成。",
            f"系统关注{_join_items(blueprint.report_metrics[:6]) or '新增记录数、待办数量、完成率和异常预警数'}等统计指标，便于管理人员掌握运行结果。",
        ],
        min_count=6,
    )
    for text in overview_paragraphs:
        document.add_paragraph(text)

    _add_heading(document, "二、运行环境")
    table = document.add_table(rows=1, cols=2)
    table.style = "Table Grid"
    table.rows[0].cells[0].text = "项目"
    table.rows[0].cells[1].text = "说明"
    rows = [
        ("开发硬件环境", blueprint.dev_environment["hardware"]),
        ("开发操作系统", blueprint.dev_environment["os"]),
        ("开发工具", blueprint.dev_environment["tool"]),
        ("运行硬件环境", blueprint.runtime_environment["hardware"]),
        ("运行操作系统", blueprint.runtime_environment["os"]),
        ("运行支撑环境", blueprint.runtime_environment["support"]),
        ("编程语言", task.language),
        ("软件技术特点", task.product_type),
        ("业务部署拓扑", blueprint.deployment_topology or "客户端访问业务服务，服务端完成数据处理、权限控制和文件导出。"),
    ]
    for key, value in rows:
        cells = table.add_row().cells
        cells[0].text = key
        cells[1].text = value

    _add_heading(document, "三、登录与主界面")
    _add_heading(document, "3.1 登录界面", level=2)
    _add_ui_figure(document, ui_screenshots, "login", "登录界面", "用户输入账号、密码和验证码后进入系统。")
    _add_heading(document, "3.2 系统首页", level=2)
    _add_ui_figure(document, ui_screenshots, "dashboard", "系统首页", "首页集中展示核心指标、待办事项、异常提醒和快捷入口。")
    login_paragraphs = _content_paragraphs(
        manual_content,
        "login_main",
        [
            "用户打开系统后首先进入登录界面，系统对账号、密码、验证码和账号状态进行校验。",
            f"登录成功后进入系统首页，首页集中展示{_join_items(blueprint.report_metrics[:4]) or '核心指标、待办事项、异常提醒和快捷入口'}。",
            f"主界面采用{_navigation_description(design_brief)}，{_join_items(blueprint.target_users or blueprint.roles)}登录后展示对应权限范围内的功能模块。",
            f"首页围绕{_join_items(blueprint.business_objects[:5]) or '业务记录'}展示待处理状态、最近操作和统计摘要。",
        ],
        min_count=8,
    )
    for text in login_paragraphs:
        document.add_paragraph(text)

    _add_heading(document, "四、功能模块说明")
    for index, module in enumerate(blueprint.modules, start=1):
        _add_heading(document, f"4.{index} {module.title}", level=2)
        module_paragraphs = _module_content_paragraphs(manual_content, module.key) or [
            module.description,
            f"进入{module.title}页面后，用户可围绕{_join_items(module.data_fields[:6]) or '业务字段'}进行条件筛选和详情查看。",
            f"系统支持{_join_items(module.operations[:6]) or f'{module.title}新增、编辑、审核、导出'}等操作，并根据当前状态控制可用按钮。",
            f"{module.title}与{_join_items(blueprint.report_metrics[:4]) or '统计指标'}保持联动，处理结果可进入报表分析和操作追踪。",
            f"在数据保存时，系统会执行{_join_items(module.rules[:3]) or '必填字段、业务编码、状态流转和重复记录校验'}，避免无效数据进入业务流程。",
            f"该模块产生的数据会与{_join_items(blueprint.data_relations[:3]) or '操作日志、统计报表和权限范围'}关联，便于后续查询和归档。",
        ]
        for text in _expand_paragraphs(module_paragraphs, min_count=10):
            document.add_paragraph(text)
        _add_module_operation_sections(document, module, index, ui_screenshots, design_brief)

    _add_heading(document, "五、统计分析")
    _add_heading(document, "5.1 统计报表界面", level=2)
    _add_ui_figure(document, ui_screenshots, "statistics", "统计报表界面", "系统按日期、模块、状态和角色维度生成统计结果。")
    statistics_paragraphs = _content_paragraphs(
        manual_content,
        "statistics",
        [
            f"统计分析功能围绕{_join_items(blueprint.report_metrics[:8]) or '系统运行过程中的业务数据'}进行汇总，帮助管理人员掌握整体运行情况。",
            f"用户可以选择统计周期、业务模块、组织范围和状态条件，系统按{_join_items(blueprint.business_objects[:6]) or '业务对象'}形成列表和图表数据。",
            "报表结果支持导出、打印和归档，便于形成日常运营分析材料。",
            f"统计页会结合{_workflow_summary(blueprint)}展示各流程节点的处理数量、完成率和异常情况。",
        ],
        min_count=8,
    )
    for text in statistics_paragraphs:
        document.add_paragraph(text)

    _add_heading(document, "六、权限与安全")
    security_paragraphs = _content_paragraphs(
        manual_content,
        "security",
        [
            "系统通过用户、角色、菜单和数据范围进行权限控制，避免越权访问。",
            "用户登录、数据新增、数据修改、状态变更、导出下载等关键操作均记录审计日志。",
            f"管理员可根据{_join_items(blueprint.target_users or blueprint.roles)}等岗位职责配置角色权限，并定期查看异常登录和高风险操作记录。",
            f"系统按照{_join_items(blueprint.quality_rules[:6]) or '字段校验、状态流转、导出审计和权限范围'}执行安全控制。",
            f"关键数据关系包括{_join_items(blueprint.data_relations[:5]) or '业务记录与操作日志关联'}，用于支撑追溯和审计。",
        ],
        min_count=8,
    )
    for text in security_paragraphs:
        document.add_paragraph(text)

    _add_heading(document, "七、常见问题处理")
    faq_paragraphs = _content_paragraphs(
        manual_content,
        "faq",
        [
        "无法登录系统时，应检查账号状态、密码输入、验证码和网络连接。",
        "查询不到数据时，应确认查询条件、数据权限和记录状态是否正确。",
        "报表统计结果异常时，应检查统计周期、业务模块和基础数据是否完整。",
        "导出文件失败时，应检查浏览器下载权限、磁盘空间和当前用户操作权限。",
        ],
        min_count=4,
    )
    for question in faq_paragraphs:
        document.add_paragraph(question)

    document.save(path)
    return path


def generate_source_docx(task: GenerationTask, source_dir: Path, output_dir: Path) -> tuple[Path, dict]:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt

    source_entries = [entry for entry in read_source_line_entries(source_dir) if str(entry.get("text", "")).strip()]
    lines = [str(entry.get("text", "")) for entry in source_entries]
    lines_per_page = 50
    entry_pages = [source_entries[index : index + lines_per_page] for index in range(0, len(source_entries), lines_per_page)]
    pages = [[str(entry.get("text", "")) for entry in page] for page in entry_pages]
    if len(pages) > 60:
        selected_pages = pages[:30] + pages[-30:]
        selected_entry_pages = entry_pages[:30] + entry_pages[-30:]
        selection_mode = "first_30_last_30"
    else:
        selected_pages = pages
        selected_entry_pages = entry_pages
        selection_mode = "all"

    path = output_dir / f"{task.safe_name}_代码-({task.language}).docx"
    document = Document()
    _set_default_font(document, "宋体", 9)
    section = document.sections[0]
    section.top_margin = Pt(36)
    section.bottom_margin = Pt(36)
    section.left_margin = Pt(54)
    section.right_margin = Pt(54)
    header = section.header.paragraphs[0]
    header.text = f"{task.software_name} {task.version} 源程序"
    header.alignment = WD_ALIGN_PARAGRAPH.CENTER

    for page_index, page_lines in enumerate(selected_pages, start=1):
        if page_index > 1:
            document.add_page_break()
        for line in page_lines:
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.space_before = Pt(0)
            paragraph.paragraph_format.space_after = Pt(0)
            paragraph.paragraph_format.line_spacing = 1
            run = paragraph.add_run(line)
            run.font.name = "宋体"
            run.font.size = Pt(8)
        footer = document.sections[0].footer.paragraphs[0]
        footer.text = f"第 {page_index} 页"
        footer.alignment = WD_ALIGN_PARAGRAPH.CENTER

    document.save(path)
    report = {
        "source_total_lines": len(lines),
        "source_total_pages": len(pages),
        "source_selected_pages": len(selected_pages),
        "lines_per_page": lines_per_page,
        "selection_mode": selection_mode,
        "source_page_sources": _source_page_sources(selected_entry_pages),
    }
    return path, report


def generate_checklist_docx(task: GenerationTask, output_dir: Path) -> Path:
    from docx import Document
    from docx.shared import Pt

    path = output_dir / "软著申请材料清单.docx"
    document = Document()
    _set_default_font(document, "宋体", 10.5)
    title = document.add_paragraph()
    title.alignment = 1
    run = title.add_run("软著申请材料清单")
    run.bold = True
    run.font.size = Pt(16)

    document.add_paragraph(f"软件名称：{task.software_name}")
    document.add_paragraph(f"版本号：{task.version}")

    table = document.add_table(rows=1, cols=4)
    table.style = "Table Grid"
    headers = ["序号", "材料名称", "是否由系统生成", "备注"]
    for index, header in enumerate(headers):
        table.rows[0].cells[index].text = header
    rows = [
        ("1", "软件著作权登记申请表", "否", "需在登记系统或代理平台填写后打印。"),
        ("2", "软件说明书", "是", "系统生成 Word 和 PDF。"),
        ("3", "源程序鉴别材料", "是", "系统从生成源码工程中提取并排版。"),
        ("4", "申请人身份证明或营业执照", "否", "由申请人自行准备。"),
        ("5", "联系人身份证明", "否", "按受理平台要求准备。"),
        ("6", "权属证明材料", "视情况", "委托开发、合作开发或职务开发时按需提供。"),
        ("7", "补正说明或其他材料", "否", "以审核意见或代理机构要求为准。"),
    ]
    for row in rows:
        cells = table.add_row().cells
        for index, value in enumerate(row):
            cells[index].text = value

    document.save(path)
    return path


def _source_page_sources(entry_pages: list[list[dict]]) -> list[dict]:
    page_sources: list[dict] = []
    for page_index, entries in enumerate(entry_pages, start=1):
        grouped: dict[str, list[int]] = {}
        for entry in entries:
            file_name = str(entry.get("file", ""))
            line_number = int(entry.get("line") or 0)
            if not file_name or not line_number:
                continue
            grouped.setdefault(file_name, []).append(line_number)
        page_sources.append(
            {
                "page": page_index,
                "line_count": len(entries),
                "sources": [
                    {
                        "file": file_name,
                        "start_line": min(line_numbers),
                        "end_line": max(line_numbers),
                        "line_count": len(line_numbers),
                    }
                    for file_name, line_numbers in sorted(grouped.items())
                ],
            }
        )
    return page_sources


def generate_info_txt(task: GenerationTask, blueprint: ProductBlueprint, source_lines: int, output_dir: Path) -> Path:
    path = output_dir / f"{task.safe_name}.txt"
    text = "\n".join(
        [
            f"【软件全称】{task.software_name}",
            f"【版本号】{task.version}",
            "【软件分类】应用软件",
            f"【开发的硬件环境】{blueprint.dev_environment['hardware']}",
            f"【运行的硬件环境】{blueprint.runtime_environment['hardware']}",
            f"【开发该软件的操作系统】{blueprint.dev_environment['os']}",
            f"【软件开发环境/开发工具】{blueprint.dev_environment['tool']}",
            f"【该软件的运行平台/操作系统】{blueprint.runtime_environment['os']}",
            f"【软件运行支撑环境/支持软件】{blueprint.runtime_environment['support']}",
            f"【编程语言】{task.language}",
            f"【源程序量】{source_lines}行",
            f"【开发目的】{blueprint.purpose}",
            f"【面向领域/行业】{blueprint.industry}",
            f"【软件的主要功能】{blueprint.summary}{_module_summary(blueprint)}软件具体场景为{blueprint.scenario or blueprint.industry}，核心业务对象包括{_join_items(blueprint.business_objects[:8])}。",
            f"【软件的技术特点】{task.product_type}。{_join_items(blueprint.technical_features[:6]) or '系统采用模块化结构，界面、业务逻辑、数据模型和日志审计相互配合，具有良好的可维护性和扩展性。'}",
            "",
        ]
    )
    path.write_text(text, encoding="utf-8-sig")
    return path


def convert_to_pdf(docx_path: Path, output_dir: Path) -> tuple[Path | None, str | None]:
    office = _find_office_binary()
    if not office:
        fallback_path, fallback_error = _write_fallback_pdf(docx_path, output_dir)
        if fallback_path:
            return fallback_path, "LibreOffice/soffice 未安装，已生成简版 PDF 占位文件；正式版建议安装 LibreOffice 以获得完整排版。"
        return None, fallback_error or "LibreOffice/soffice 未安装，已跳过 PDF 转换。"
    try:
        with tempfile.TemporaryDirectory(prefix="lo-profile-") as profile_dir:
            profile_uri = Path(profile_dir).resolve().as_uri()
            command = [
                office,
                f"-env:UserInstallation={profile_uri}",
                "--headless",
                "--nologo",
                "--nodefault",
                "--norestore",
                "--nolockcheck",
                "--nofirststartwizard",
                "--convert-to",
                "pdf",
                "--outdir",
                str(output_dir.resolve()),
                str(docx_path.resolve()),
            ]
            completed = subprocess.run(command, capture_output=True, text=True, timeout=_office_timeout_seconds(), check=False)
    except Exception as exc:
        return None, f"PDF 转换失败：{exc}"
    pdf_path = output_dir / f"{docx_path.stem}.pdf"
    if completed.returncode != 0 or not pdf_path.exists():
        return None, completed.stderr.strip() or completed.stdout.strip() or "PDF 转换失败。"
    return pdf_path, None


def pdf_converter_info() -> dict:
    office = _find_office_binary()
    if office:
        return {
            "method": "libreoffice",
            "soffice_path": office,
            "fallback": False,
        }
    return {
        "method": "fallback-reportlab",
        "soffice_path": "",
        "fallback": True,
    }


def _find_office_binary() -> str | None:
    env_candidates = [
        os.getenv("SOFT_LIBREOFFICE_PATH", ""),
        os.getenv("SOFFICE_PATH", ""),
        os.getenv("LIBREOFFICE_PATH", ""),
    ]
    for value in env_candidates:
        if not value:
            continue
        candidate = Path(value)
        if candidate.is_dir():
            candidate = candidate / "program" / "soffice.exe"
        if candidate.exists():
            return str(candidate)

    resource_root = Path(__file__).resolve().parents[2]
    candidates = [
        resource_root / "libreoffice" / "program" / "soffice.exe",
        resource_root.parent / "libreoffice" / "program" / "soffice.exe",
        Path.cwd() / "libreoffice" / "program" / "soffice.exe",
        Path("C:/Program Files/LibreOffice/program/soffice.exe"),
        Path("C:/Program Files (x86)/LibreOffice/program/soffice.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    office = shutil.which("soffice") or shutil.which("libreoffice")
    if office:
        return office
    return None


def _office_timeout_seconds() -> int:
    raw_value = os.getenv("SOFT_LIBREOFFICE_TIMEOUT_SECONDS", "").strip()
    if raw_value:
        try:
            return max(60, int(raw_value))
        except ValueError:
            pass
    return 360


def _write_fallback_pdf(docx_path: Path, output_dir: Path) -> tuple[Path | None, str | None]:
    try:
        from docx import Document
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.pdfgen import canvas
    except ImportError as exc:
        return None, f"PDF 兜底依赖缺失：{exc}"

    pdf_path = output_dir / f"{docx_path.stem}.pdf"
    document = Document(docx_path)
    font_name = "Helvetica"
    font_candidates = [
        Path("C:/Windows/Fonts/simsun.ttc"),
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
    ]
    for font_path in font_candidates:
        if font_path.exists():
            try:
                pdfmetrics.registerFont(TTFont("ChineseFont", str(font_path)))
                font_name = "ChineseFont"
                break
            except Exception:
                continue

    page_width, page_height = A4
    margin = 42
    y = page_height - margin
    c = canvas.Canvas(str(pdf_path), pagesize=A4)
    c.setFont(font_name, 10)
    c.drawString(margin, y, f"{docx_path.stem}（原型简版 PDF）")
    y -= 24

    def new_page() -> None:
        nonlocal y
        c.showPage()
        c.setFont(font_name, 10)
        y = page_height - margin

    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        for line in _wrap_text(text, 42):
            if y < margin:
                new_page()
            c.drawString(margin, y, line)
            y -= 15
    c.save()
    return pdf_path, None


def _wrap_text(text: str, width: int) -> list[str]:
    return [text[index : index + width] for index in range(0, len(text), width)] or [""]


def _set_default_font(document, font_name: str, size: float) -> None:
    from docx.shared import Pt

    styles = document.styles
    normal = styles["Normal"]
    normal.font.name = font_name
    normal.font.size = Pt(size)
    element = normal._element
    rpr = element.rPr
    if rpr is not None:
        fonts = rpr.rFonts
        if fonts is not None:
            fonts.set("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}eastAsia", font_name)


def _add_heading(document, text: str, level: int = 1) -> None:
    paragraph = document.add_heading(text, level=level)
    for run in paragraph.runs:
        run.font.name = "宋体"


def _add_ui_placeholder(document, title: str, caption: str) -> None:
    from docx.shared import Pt, RGBColor

    note_p = document.add_paragraph(f"{title}用于{caption}")
    note_p.paragraph_format.space_after = Pt(4)
    for note_run in note_p.runs:
        note_run.font.color.rgb = RGBColor(80, 80, 80)
        note_run.font.size = Pt(9)
    caption_p = document.add_paragraph(f"图：{title}，{caption}")
    caption_p.paragraph_format.space_after = Pt(6)
    for run in caption_p.runs:
        run.font.color.rgb = RGBColor(80, 80, 80)


def _add_ui_figure(document, ui_screenshots: dict | None, key: str, title: str, caption: str) -> None:
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Inches, Pt, RGBColor

    item = ui_screenshots.get(key) if isinstance(ui_screenshots, dict) else None
    image_path = getattr(item, "image_path", None) if item else None
    display_title = title
    display_caption = caption
    if image_path and Path(image_path).exists():
        paragraph = document.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = paragraph.add_run()
        run.add_picture(image_path, width=Inches(5.9))
        caption_p = document.add_paragraph(f"图：{display_title}，{display_caption}")
        caption_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        caption_p.paragraph_format.space_after = Pt(6)
        for caption_run in caption_p.runs:
            caption_run.font.color.rgb = RGBColor(80, 80, 80)
            caption_run.font.size = Pt(9)
        return
    _add_ui_placeholder(document, display_title, display_caption)


def _expand_paragraphs(paragraphs: list[str], min_count: int) -> list[str]:
    result = list(paragraphs)
    templates = [
        "系统在处理该部分业务时，会同步记录创建时间、更新时间、处理状态和操作人员，方便后续追溯。",
        "页面提供条件筛选、列表展示、详情查看、状态维护和导出等常用操作，满足日常管理需要。",
        "当用户提交数据后，系统会执行字段校验和业务规则校验，避免重复、缺失或状态异常的数据进入流程。",
        "相关数据可进入统计分析模块，为管理人员进行趋势判断和工作安排提供依据。",
        "该功能与角色权限联动，不同岗位只能访问授权范围内的数据和操作按钮。",
    ]
    index = 0
    while len(result) < min_count:
        result.append(templates[index % len(templates)])
        index += 1
    return result


def _add_module_operation_sections(document, module, module_index: int, ui_screenshots: dict | None, design_brief: dict | None = None) -> None:
    _add_heading(document, f"4.{module_index}.1 {module.title}主界面", level=3)
    _add_ui_figure(
        document,
        ui_screenshots,
        _module_figure_key(module.key),
        f"{module.title}主界面",
        f"{module.title}页面展示查询条件、数据列表、状态摘要和常用操作入口。",
    )
    fields = _join_items(module.data_fields[:5]) or "名称、状态、责任角色、更新时间和处理备注"
    document.add_paragraph(
        f"{module.title}主界面用于集中展示{fields}等核心信息，用户可在该界面完成查询、筛选和记录定位。"
    )
    document.add_paragraph(
        f"界面操作区提供{_join_items(module.operations[:5]) or '新增、编辑、查询、导出和状态维护'}等入口，"
        "用户根据业务状态选择对应操作后进入后续处理流程。"
    )
    operations = _module_operation_items(module, design_brief)
    for operation_index, operation in enumerate(operations[:4], start=2):
        _add_heading(document, f"4.{module_index}.{operation_index} {operation}", level=3)
        action = _operation_action(operation)
        document.add_paragraph(
            f"用户在{module.title}页面选择【{action}】入口后，系统打开对应的{action}窗口或详情区域。"
            f"页面展示{fields}等信息，用户可根据业务需要完成查看、填写、修改或确认。"
        )
        _add_ui_figure(
            document,
            ui_screenshots,
            _module_operation_figure_key(module.key, action, operation_index),
            f"{module.title}{action}界面",
            f"{module.title}{action}界面用于展示二级窗口、业务字段和处理按钮，用户在该界面完成当前操作。",
        )
        document.add_paragraph(
            f"提交前系统会校验{_join_items(module.rules[:2]) or '必填项、业务状态和权限范围'}，"
            f"校验通过后保存{module.title}处理结果，并同步记录操作人员、处理时间和状态变化。"
        )
        document.add_paragraph(
            f"完成{action}后，列表区刷新当前记录状态，相关数据进入查询、统计和审计流程，便于后续跟踪。"
        )


def _operation_action(operation: str) -> str:
    for suffix in [
        "登记",
        "查询",
        "编辑",
        "审核",
        "发布",
        "归档",
        "导入",
        "导出",
        "预警",
        "复核",
        "统计",
        "追踪",
        "新增",
        "删除",
        "详情",
        "配置",
        "定位",
        "调度",
        "训练",
        "道具",
        "结算",
        "活动",
        "确认",
        "处置",
    ]:
        if suffix in operation:
            return suffix
    return str(operation).strip() or "处理"


def _module_operation_items(module, design_brief: dict | None = None) -> list[str]:
    operations = [str(item).strip() for item in module.operations if str(item).strip()]
    if not operations:
        operations = [
            f"{module.title}列表查看",
            f"{module.title}详情维护",
            f"{module.title}数据保存",
            f"{module.title}结果导出",
        ]
    secondary_mix = [str(item).strip() for item in (design_brief or {}).get("secondary_mix", []) if str(item).strip()]
    if not secondary_mix:
        return operations
    selected: list[str] = []
    used: set[int] = set()
    for preferred_action in secondary_mix:
        for index, operation in enumerate(operations):
            if index in used:
                continue
            if _operation_action(operation) == preferred_action or preferred_action in operation:
                selected.append(operation)
                used.add(index)
                break
    for index, operation in enumerate(operations):
        if index not in used:
            selected.append(operation)
    return selected


def _navigation_description(design_brief: dict | None) -> str:
    nav_model = str((design_brief or {}).get("nav_model") or "")
    if nav_model == "top_tabs":
        return "顶部页签导航和主体工作区布局"
    if nav_model == "rail":
        return "窄侧栏导航和右侧工作区布局"
    return "左侧菜单和右侧工作区布局"


def _content_paragraphs(
    manual_content: dict | None,
    key: str,
    fallback: list[str],
    min_count: int,
) -> list[str]:
    if manual_content:
        paragraphs = manual_content.get(key)
        if isinstance(paragraphs, list) and paragraphs:
            return _expand_paragraphs([str(item) for item in paragraphs], min_count=min_count)
    return _expand_paragraphs(fallback, min_count=min_count)


def _module_content_paragraphs(manual_content: dict | None, module_key: str) -> list[str] | None:
    if not manual_content:
        return None
    modules = manual_content.get("modules")
    if not isinstance(modules, dict):
        return None
    module = modules.get(module_key)
    if not isinstance(module, dict):
        return None
    paragraphs = module.get("paragraphs")
    if not isinstance(paragraphs, list) or not paragraphs:
        return None
    return [str(item) for item in paragraphs]


def _module_summary(blueprint: ProductBlueprint) -> str:
    details = []
    for module in blueprint.modules:
        details.append(f"{module.title}用于{module.description}")
    return "系统主要包括" + "、".join(details) + "等功能。"


def _join_items(items: list[str]) -> str:
    return "、".join(str(item) for item in items if str(item).strip())


def _workflow_summary(blueprint: ProductBlueprint) -> str:
    if not blueprint.workflows:
        return "业务提交、字段校验、状态流转和结果归档流程"
    names = [str(item.get("name") or "") for item in blueprint.workflows[:3] if isinstance(item, dict)]
    names = [name for name in names if name]
    return "、".join(names) or "业务提交、字段校验、状态流转和结果归档流程"


def _module_figure_key(module_key: str) -> str:
    if module_key in {"login", "dashboard", "statistics"}:
        return f"module_{module_key}"
    return module_key


def _module_operation_figure_key(module_key: str, action: str, operation_index: int) -> str:
    token = re.sub(r"[^a-zA-Z0-9]+", "_", action).strip("_").lower()
    token = token or f"operation_{operation_index}"
    return f"{_module_figure_key(module_key)}_{token}_{operation_index}"
