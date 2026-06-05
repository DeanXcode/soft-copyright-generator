from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile

from .blueprint import ProductBlueprint
from .models import GenerationTask
from .sourcegen import read_source_lines


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
) -> Path:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt, RGBColor

    path = output_dir / f"{task.software_name}.docx"
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
            f"本软件面向{blueprint.industry}场景，重点解决业务数据分散、处理流程不统一、运行状态缺少跟踪、统计分析依赖人工汇总等问题。",
            f"系统采用{task.language}进行主要功能开发，通过模块化设计完成用户操作、业务处理、数据查询、统计分析和权限审计等能力。",
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
    ]
    for key, value in rows:
        cells = table.add_row().cells
        cells[0].text = key
        cells[1].text = value

    _add_heading(document, "三、登录与主界面")
    _add_ui_placeholder(document, "登录界面", "用户输入账号、密码和验证码后进入系统。")
    login_paragraphs = _content_paragraphs(
        manual_content,
        "login_main",
        [
            "用户打开系统后首先进入登录界面，系统对账号、密码、验证码和账号状态进行校验。",
            "登录成功后进入系统首页，首页集中展示核心指标、待办事项、异常提醒和快捷入口。",
            "主界面采用左侧菜单和右侧工作区布局，不同角色登录后展示对应权限范围内的功能模块。",
        ],
        min_count=8,
    )
    for text in login_paragraphs:
        document.add_paragraph(text)

    _add_heading(document, "四、功能模块说明")
    for index, module in enumerate(blueprint.modules, start=1):
        _add_heading(document, f"4.{index} {module.title}", level=2)
        _add_ui_placeholder(document, module.title, module.description)
        module_paragraphs = _module_content_paragraphs(manual_content, module.key) or [
            module.description,
            f"进入{module.title}页面后，用户可以按关键字、状态、时间范围和业务分类进行查询。",
            f"系统支持{module.title}数据的新增、编辑、删除、查看详情和状态维护操作。",
            f"{module.title}与权限审计、日志记录、统计报表等公共能力保持联动，确保业务操作可以追溯。",
            f"在数据保存时，系统会校验必填字段、业务编码、状态流转和重复记录，避免无效数据进入业务流程。",
            f"对于需要审核的记录，系统会记录提交人、审核人、审核时间和审核意见，便于后续查询和归档。",
        ]
        for text in _expand_paragraphs(module_paragraphs, min_count=10):
            document.add_paragraph(text)

    _add_heading(document, "五、统计分析")
    _add_ui_placeholder(document, "统计报表界面", "系统按日期、模块、状态和角色维度生成统计结果。")
    statistics_paragraphs = _content_paragraphs(
        manual_content,
        "statistics",
        [
            "统计分析功能用于汇总系统运行过程中的业务数据，帮助管理人员掌握整体运行情况。",
            "用户可以选择统计周期、业务模块、组织范围和状态条件，系统自动生成列表和图表数据。",
            "报表结果支持导出、打印和归档，便于形成日常运营分析材料。",
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
            "管理员可根据岗位职责配置角色权限，并定期查看异常登录和高风险操作记录。",
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

    lines = read_source_lines(source_dir)
    lines_per_page = 52
    pages = [lines[index : index + lines_per_page] for index in range(0, len(lines), lines_per_page)]
    if len(pages) > 60:
        selected_pages = pages[:30] + pages[-30:]
        selection_mode = "first_30_last_30"
    else:
        selected_pages = pages
        selection_mode = "all"

    path = output_dir / f"{task.software_name}_代码-({task.language}).docx"
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
            run = paragraph.add_run(line if line else " ")
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


def generate_info_txt(task: GenerationTask, blueprint: ProductBlueprint, source_lines: int, output_dir: Path) -> Path:
    path = output_dir / f"{task.software_name}.txt"
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
            f"【软件的主要功能】{blueprint.summary}{_module_summary(blueprint)}",
            f"【软件的技术特点】{task.product_type}。系统采用模块化结构，界面、业务逻辑、数据模型和日志审计相互配合，具有良好的可维护性和扩展性。",
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
                "--nofirststartwizard",
                "--convert-to",
                "pdf",
                "--outdir",
                str(output_dir),
                str(docx_path),
            ]
            completed = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
    except Exception as exc:
        return None, f"PDF 转换失败：{exc}"
    pdf_path = output_dir / f"{docx_path.stem}.pdf"
    if completed.returncode != 0 or not pdf_path.exists():
        return None, completed.stderr.strip() or completed.stdout.strip() or "PDF 转换失败。"
    return pdf_path, None


def _find_office_binary() -> str | None:
    office = shutil.which("soffice") or shutil.which("libreoffice")
    if office:
        return office
    candidates = [
        Path("C:/Program Files/LibreOffice/program/soffice.exe"),
        Path("C:/Program Files (x86)/LibreOffice/program/soffice.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


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
    from docx.shared import Inches, Pt, RGBColor

    table = document.add_table(rows=5, cols=4)
    table.style = "Table Grid"
    merged = table.rows[0].cells[0].merge(table.rows[0].cells[-1])
    merged.text = title
    for row_index in range(1, 5):
        for col_index in range(4):
            cell = table.rows[row_index].cells[col_index]
            cell.text = ["功能入口", "业务数据", "状态信息", "操作按钮"][col_index]
    caption_p = document.add_paragraph(f"图：{title}，{caption}")
    caption_p.paragraph_format.space_after = Pt(6)
    for run in caption_p.runs:
        run.font.color.rgb = RGBColor(80, 80, 80)


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
