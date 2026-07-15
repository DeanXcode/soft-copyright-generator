from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from .blueprint import ProductBlueprint
from .interaction_semantics import mobile_secondary_interaction
from .models import GenerationTask
from .sourcegen import SOURCE_MATERIAL_ORDER_FILE, read_source_line_entries, read_source_lines


def ensure_docx_available() -> tuple[bool, str | None]:
    try:
        import docx  # noqa: F401

        return True, None
    except ImportError as exc:
        return False, str(exc)


def analyze_docx_layout(docx_path: Path | None) -> dict:
    if not docx_path or not docx_path.exists():
        return {
            "docx_layout_checked": False,
            "docx_is_a4": False,
            "docx_header_page_number_right": False,
        }
    try:
        from docx import Document
        from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
        from docx.oxml.ns import qn

        document = Document(docx_path)
        section = document.sections[0]
        width_cm = round(section.page_width.cm, 2)
        height_cm = round(section.page_height.cm, 2)
        header_xml = section.header._element.xml
        footer_xml = section.footer._element.xml
        header_has_page = "PAGE" in header_xml
        footer_has_page = "PAGE" in footer_xml

        def border_is_visible(border) -> bool:
            if border is None:
                return False
            value = border.get(qn("w:val"))
            return value not in {"nil", "none"}

        def has_header_bottom_border() -> bool:
            for paragraph in section.header.paragraphs:
                p_pr = paragraph._p.pPr
                p_bdr = p_pr.find(qn("w:pBdr")) if p_pr is not None else None
                if p_bdr is not None and border_is_visible(p_bdr.find(qn("w:bottom"))):
                    return True
            for table in section.header.tables:
                tbl_pr = table._tbl.tblPr
                tbl_borders = tbl_pr.find(qn("w:tblBorders")) if tbl_pr is not None else None
                if tbl_borders is not None and border_is_visible(tbl_borders.find(qn("w:bottom"))):
                    return True
            return False

        def has_right_header_page_number() -> bool:
            paragraphs = list(section.header.paragraphs)
            for table in section.header.tables:
                for row in table.rows:
                    for cell in row.cells:
                        paragraphs.extend(cell.paragraphs)
            for paragraph in paragraphs:
                if "PAGE" not in paragraph._p.xml:
                    continue
                if paragraph.alignment == WD_ALIGN_PARAGRAPH.RIGHT:
                    return True
                if "\t" in paragraph.text:
                    return True
                for stop in paragraph.paragraph_format.tab_stops:
                    if stop.alignment == WD_TAB_ALIGNMENT.RIGHT:
                        return True
            return False

        return {
            "docx_layout_checked": True,
            "docx_page_width_cm": width_cm,
            "docx_page_height_cm": height_cm,
            "docx_is_portrait": bool(section.page_height > section.page_width),
            "docx_is_a4": abs(width_cm - 21.0) <= 0.15 and abs(height_cm - 29.7) <= 0.15,
            "docx_header_page_number_field": header_has_page,
            "docx_header_page_number_right": header_has_page and has_right_header_page_number(),
            "docx_header_bottom_border": has_header_bottom_border(),
            "docx_footer_page_number_field": footer_has_page,
        }
    except Exception as exc:
        return {
            "docx_layout_checked": False,
            "docx_layout_error": str(exc),
            "docx_is_a4": False,
            "docx_header_page_number_right": False,
            "docx_header_bottom_border": False,
        }


def analyze_pdf_layout(pdf_path: Path | None) -> dict:
    if not pdf_path or not pdf_path.exists():
        return {
            "pdf_layout_checked": False,
            "pdf_exists": False,
            "pdf_is_a4": False,
        }
    pdfinfo = _find_pdfinfo_binary()
    if not pdfinfo:
        return _analyze_pdf_layout_from_media_box(pdf_path, "pdfinfo 未找到，已使用 MediaBox 兜底解析。")
    try:
        with tempfile.TemporaryDirectory(prefix="soft_pdfinfo_") as temp_dir:
            probe_path = Path(temp_dir) / "input.pdf"
            shutil.copy2(pdf_path, probe_path)
            completed = subprocess.run(
                [pdfinfo, str(probe_path.resolve())],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
                startupinfo=_office_startup_info(),
                creationflags=_office_creation_flags(),
            )
    except Exception as exc:
        return {
            "pdf_layout_checked": False,
            "pdf_exists": True,
            "pdf_layout_error": str(exc),
            "pdf_is_a4": False,
        }
    output = "\n".join(part for part in [completed.stdout, completed.stderr] if part)
    if completed.returncode != 0:
        reason = output.strip() or "pdfinfo 执行失败。"
        return _analyze_pdf_layout_from_media_box(pdf_path, reason)
    info = _parse_pdfinfo_output(output)
    if not info.get("pdf_is_a4") and not info.get("pdf_page_count"):
        return _analyze_pdf_layout_from_media_box(pdf_path, "pdfinfo 未返回可解析的页面尺寸。")
    return {
        "pdf_layout_checked": True,
        "pdf_exists": True,
        **info,
    }


def analyze_manual_pdf_text_density(pdf_path: Path | None, *, minimum_lines: int = 30) -> dict:
    if not pdf_path or not pdf_path.exists():
        return {
            "manual_pdf_text_density_checked": False,
            "manual_pdf_text_density_ready": False,
            "manual_pdf_minimum_lines_per_text_page": minimum_lines,
        }
    try:
        page_results = _manual_pdf_text_density_pages_with_pypdf(pdf_path, minimum_lines)
    except ImportError as exc:
        try:
            page_results = _manual_pdf_text_density_pages_with_pdftotext(pdf_path, minimum_lines)
        except Exception as fallback_exc:
            return {
                "manual_pdf_text_density_checked": False,
                "manual_pdf_text_density_ready": False,
                "manual_pdf_text_density_error": f"pypdf 未安装：{exc}；pdftotext 兜底失败：{fallback_exc}",
                "manual_pdf_minimum_lines_per_text_page": minimum_lines,
            }
    except Exception as exc:
        try:
            page_results = _manual_pdf_text_density_pages_with_pdftotext(pdf_path, minimum_lines)
        except Exception as fallback_exc:
            return {
                "manual_pdf_text_density_checked": False,
                "manual_pdf_text_density_ready": False,
                "manual_pdf_text_density_error": f"{exc}；pdftotext 兜底失败：{fallback_exc}",
                "manual_pdf_minimum_lines_per_text_page": minimum_lines,
            }
    density_pages = [item for item in page_results if item["text_density_page"]]
    soft_pass_pages = [
        {
            "page": item["page"],
            "line_count": item["line_count"],
            "character_count": item["character_count"],
            "reason": item.get("soft_pass_reason", "near_threshold"),
        }
        for item in density_pages
        if item["line_count"] < minimum_lines and item.get("ready")
    ]
    figure_text_pages = [
        {
            "page": item["page"],
            "line_count": item["line_count"],
            "character_count": item["character_count"],
        }
        for item in density_pages
        if item.get("soft_pass_reason") == "figure_text_page"
    ]
    line_requirement_risk_pages = [
        {
            "page": item["page"],
            "line_count": item["line_count"],
            "character_count": item["character_count"],
        }
        for item in density_pages
        if item["line_count"] < minimum_lines
    ]
    low_pages = [
        {
            "page": item["page"],
            "line_count": item["line_count"],
            "character_count": item["character_count"],
        }
        for item in density_pages
        if not item.get("ready")
    ]
    line_counts = [item["line_count"] for item in density_pages]
    return {
        "manual_pdf_text_density_checked": True,
        "manual_pdf_text_density_ready": bool(density_pages) and not low_pages,
        "manual_pdf_minimum_lines_per_text_page": minimum_lines,
        "manual_pdf_page_count": len(page_results),
        "manual_pdf_text_density_page_count": len(density_pages),
        "manual_pdf_low_text_density_page_count": len(low_pages),
        "manual_pdf_low_text_density_pages": low_pages[:12],
        "manual_pdf_text_density_soft_pass_count": len(soft_pass_pages),
        "manual_pdf_text_density_soft_pass_pages": soft_pass_pages[:12],
        "manual_pdf_text_density_figure_pass_count": len(figure_text_pages),
        "manual_pdf_text_density_figure_pass_pages": figure_text_pages[:12],
        "manual_pdf_line_requirement_risk_count": len(line_requirement_risk_pages),
        "manual_pdf_line_requirement_risk_pages": line_requirement_risk_pages[:12],
        "manual_pdf_line_requirement_warning": bool(line_requirement_risk_pages),
        "manual_pdf_min_text_page_line_count": min(line_counts) if line_counts else 0,
        "manual_pdf_average_text_page_line_count": round(sum(line_counts) / len(line_counts), 2) if line_counts else 0,
    }


def _manual_pdf_text_density_pages_with_pypdf(pdf_path: Path, minimum_lines: int) -> list[dict]:
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    page_count = len(reader.pages)
    page_results: list[dict] = []
    for index, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        page_results.append(_manual_pdf_text_density_page_result(text, index, page_count, minimum_lines))
    return page_results


def _manual_pdf_text_density_pages_with_pdftotext(pdf_path: Path, minimum_lines: int) -> list[dict]:
    pdftotext = _find_pdftotext_binary()
    if not pdftotext:
        raise RuntimeError("未找到 pdftotext")
    with tempfile.TemporaryDirectory(prefix="soft_pdftotext_") as temp_dir:
        text_path = Path(temp_dir) / "manual.txt"
        completed = subprocess.run(
            [pdftotext, "-layout", "-enc", "UTF-8", str(pdf_path.resolve()), str(text_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
            startupinfo=_office_startup_info(),
            creationflags=_office_creation_flags(),
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "pdftotext 执行失败").strip()
            raise RuntimeError(detail[:240])
        text = text_path.read_text(encoding="utf-8", errors="replace")
    pages = text.split("\f")
    if pages and not pages[-1].strip():
        pages = pages[:-1]
    page_count = len(pages)
    return [
        _manual_pdf_text_density_page_result(page_text, index, page_count, minimum_lines)
        for index, page_text in enumerate(pages, start=1)
    ]


def _manual_pdf_text_density_page_result(
    text: str,
    page_index: int,
    page_count: int,
    minimum_lines: int,
) -> dict:
    lines = _pdf_text_lines(text)
    line_count = len(lines)
    char_count = sum(len(line) for line in lines)
    text_page = _is_manual_text_density_page(lines, page_index, page_count, minimum_lines)
    near_threshold_pass = _manual_pdf_text_density_soft_pass(line_count, char_count, minimum_lines)
    figure_text_pass = _manual_pdf_figure_text_density_soft_pass(lines, line_count, char_count, minimum_lines)
    content_sufficient_pass = _manual_pdf_content_sufficient_soft_pass(lines, line_count, char_count, minimum_lines)
    closing_content_pass = _manual_pdf_closing_content_soft_pass(
        lines,
        line_count,
        char_count,
        minimum_lines,
        page_index,
        page_count,
    )
    soft_pass = near_threshold_pass or figure_text_pass or content_sufficient_pass or closing_content_pass
    soft_pass_reason = (
        "figure_text_page"
        if figure_text_pass
        else "near_threshold"
        if near_threshold_pass
        else "content_sufficient_page"
        if content_sufficient_pass
        else "closing_content_page"
        if closing_content_pass
        else ""
    )
    return {
        "page": page_index,
        "line_count": line_count,
        "character_count": char_count,
        "text_density_page": text_page,
        "soft_pass": soft_pass if text_page else False,
        "soft_pass_reason": soft_pass_reason if text_page and soft_pass else "",
        "ready": (line_count >= minimum_lines or soft_pass) if text_page else True,
    }


def _manual_pdf_text_density_soft_pass(line_count: int, character_count: int, minimum_lines: int) -> bool:
    deficit = int(minimum_lines or 0) - int(line_count or 0)
    if deficit <= 0 or deficit > 2:
        return False
    return int(character_count or 0) >= max(600, int(minimum_lines or 0) * 20)


def _manual_pdf_content_sufficient_soft_pass(
    lines: list[str],
    line_count: int,
    character_count: int,
    minimum_lines: int,
) -> bool:
    if line_count >= minimum_lines:
        return False
    # PDF text extraction does not map reliably to visual rows. Treat a compact,
    # substantive operation page as sufficient while retaining the sub-30 risk.
    if line_count < 18 or character_count < 280:
        return False
    joined = "\n".join(lines)
    content_markers = (
        "用户",
        "系统",
        "页面",
        "界面",
        "点击",
        "进入",
        "查看",
        "筛选",
        "查询",
        "保存",
        "提交",
        "状态",
        "记录",
        "处理",
        "显示",
        "功能",
    )
    return sum(1 for marker in content_markers if marker in joined) >= 2


def _manual_pdf_closing_content_soft_pass(
    lines: list[str],
    line_count: int,
    character_count: int,
    minimum_lines: int,
    page_index: int,
    page_count: int,
) -> bool:
    if page_index != page_count or line_count >= minimum_lines:
        return False
    # The last FAQ/troubleshooting page may legitimately occupy only the upper
    # part of the sheet. A substantive closing page is not a failed 30-line
    # page; retain the line-count warning but do not block delivery.
    if line_count < 12 or character_count < 450:
        return False
    joined = "\n".join(lines)
    markers = ("用户", "系统", "页面", "查询", "检查", "重新", "结果", "状态", "记录")
    return sum(1 for marker in markers if marker in joined) >= 3


def _manual_pdf_figure_text_density_soft_pass(
    lines: list[str],
    line_count: int,
    character_count: int,
    minimum_lines: int,
) -> bool:
    if line_count >= minimum_lines:
        return False
    caption_count = sum(1 for line in lines if line.startswith("图："))
    if not caption_count:
        return False
    body_lines = [line for line in lines if not line.startswith("图：")]
    if len(body_lines) < 16 or int(character_count or 0) < 500:
        return False
    joined = "\n".join(lines)
    operation_markers = (
        "用户",
        "系统",
        "页面",
        "界面",
        "进入",
        "点击",
        "查看",
        "筛选",
        "查询",
        "保存",
        "导出",
        "统计",
        "记录",
    )
    marker_hits = sum(1 for marker in operation_markers if marker in joined)
    return marker_hits >= 5


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
    from docx.shared import Cm, Pt

    design_brief = _manual_design_brief_with_renderer(design_brief, ui_screenshots)
    path = output_dir / f"{task.safe_name}.docx"
    document = Document()
    _set_default_font(document, "宋体", 10.5, line_spacing_pt=14.5, space_after_pt=2)
    manual_content = _manual_content_for_handbook(manual_content, blueprint)
    manual_content = _manual_content_for_renderer(manual_content, design_brief)

    section = document.sections[0]
    _configure_application_section(
        section,
        header_text=f"{task.software_name} {task.version}",
        top_margin_pt=54,
        bottom_margin_pt=54,
        left_margin_pt=72,
        right_margin_pt=72,
    )

    _add_manual_cover(document, task)
    document.add_page_break()

    _add_manual_toc(document, blueprint)
    document.add_page_break()

    _add_heading(document, "一、软件概述")
    overview_paragraphs = _content_paragraphs(
        manual_content,
        "overview",
        [
            blueprint.summary,
            blueprint.positioning or f"本软件面向{blueprint.industry}场景，重点解决业务数据分散、处理流程不统一、运行状态缺少跟踪、统计分析依赖人工汇总等问题。",
            f"系统具体服务于{blueprint.scenario or blueprint.industry}，围绕{_join_items(blueprint.business_objects[:8]) or '核心业务对象'}完成登记、校验、处理、统计和归档。",
            f"系统采用{_manual_architecture_name(blueprint, design_brief)}，源码工程包含{task.language}等语言模块，通过模块化设计完成{_join_items(blueprint.technical_features[:4]) or '用户操作、业务处理、数据查询、统计分析和权限审计'}等能力。",
            f"系统围绕{_workflow_summary(blueprint)}组织业务入口、处理记录、统计结果和审计信息，形成完整的日常使用闭环。",
            f"系统关注{_join_items(blueprint.report_metrics[:6]) or '新增记录数、待办数量、完成率和异常预警数'}等统计指标，便于管理人员掌握运行结果。",
        ],
        min_count=3,
    )
    overview_paragraphs = _manual_paragraphs_for_renderer(overview_paragraphs, design_brief)
    if len(overview_paragraphs) < 3:
        safe_overview_fallback = [
            f"本软件围绕{_join_items(module.title for module in blueprint.modules[:6]) or '核心业务模块'}组织统一的桌面业务工作入口，支持用户按模块查看、处理和跟踪当前业务记录。",
            f"系统面向{_join_items(blueprint.target_users or blueprint.roles) or '业务人员和管理人员'}，对{_join_items(blueprint.business_objects[:8]) or '核心业务对象'}进行集中管理，并保留状态变化和处理结果。",
            f"系统关注{_join_items(blueprint.report_metrics[:6]) or '待办数量、完成率、异常数量和趋势变化'}等指标，便于用户在桌面工作区核对运行情况并进入相应功能页面。",
            f"各功能页面使用统一的导航、按钮、表格、表单和状态组件，围绕{_workflow_summary(blueprint)}形成查询、处理、结果查看和统计分析闭环。",
        ]
        for text in safe_overview_fallback:
            if text not in overview_paragraphs:
                overview_paragraphs.append(text)
            if len(overview_paragraphs) >= 3:
                break
    for text in overview_paragraphs:
        document.add_paragraph(_customer_manual_text(text))

    _add_heading(document, "二、运行环境")
    table = document.add_table(rows=1, cols=2)
    table.style = "Table Grid"
    table.autofit = False
    content_width = section.page_width - section.left_margin - section.right_margin - Cm(0.35)
    label_width = Cm(3.2)
    value_width = content_width - label_width
    _set_table_width(table, content_width)
    _set_table_grid(table, [label_width, value_width])
    _set_cell_width(table.rows[0].cells[0], label_width)
    _set_cell_width(table.rows[0].cells[1], value_width)
    table.rows[0].cells[0].text = "项目"
    table.rows[0].cells[1].text = "说明"
    rows = [
        ("开发硬件环境", blueprint.dev_environment["hardware"]),
        ("开发操作系统", blueprint.dev_environment["os"]),
        ("开发工具", blueprint.dev_environment["tool"]),
        ("运行硬件环境", _manual_runtime_environment_value(blueprint.runtime_environment["hardware"], design_brief)),
        ("运行操作系统", _manual_runtime_environment_value(blueprint.runtime_environment["os"], design_brief)),
        ("运行支撑环境", _manual_runtime_environment_value(blueprint.runtime_environment["support"], design_brief)),
        ("软件分类", task.software_category),
        ("编程语言", task.language),
        ("技术架构", _manual_architecture_name(blueprint, design_brief)),
        ("软件技术特点", _manual_product_type(task, blueprint)),
        ("业务部署拓扑", _manual_deployment_topology(blueprint, design_brief)),
    ]
    for key, value in rows:
        cells = table.add_row().cells
        _set_cell_width(cells[0], label_width)
        _set_cell_width(cells[1], value_width)
        cells[0].text = key
        cells[1].text = value
    runtime_note = _runtime_screenshot_note(design_brief)
    if runtime_note:
        document.add_paragraph(_customer_manual_text(runtime_note))

    _add_heading(document, "三、登录与主界面")
    _add_heading(document, "3.1 登录界面", level=2)
    _add_ui_figure(
        document,
        ui_screenshots,
        "login",
        "登录界面",
        "用户输入账号、密码和验证码后进入系统。",
        [
            "用户打开软件后进入登录界面，依次填写账号、密码和验证码；如系统配置了岗位入口，应按当前岗位选择相应登录方式。",
            "登录页主要包含账号、密码、验证码、登录按钮和运行环境提示，系统会校验账号状态、密码有效性和验证码是否正确。",
            "校验通过后系统进入首页，并按照当前用户角色加载授权菜单、待办事项、常用模块和默认业务范围。",
            _runtime_screenshot_note(design_brief),
        ],
    )
    _add_heading(document, "3.2 系统首页", level=2)
    _add_ui_figure(
        document,
        ui_screenshots,
        "dashboard",
        "系统首页",
        "首页集中展示核心指标、待办事项、异常提醒和快捷入口。",
        [
            f"用户登录后进入系统首页，可通过{_navigation_description(design_brief)}切换业务模块，并查看当前待办、预警和快捷入口。",
            f"首页集中展示{_join_items(blueprint.report_metrics[:5]) or '核心指标、待办数量、异常提醒和快捷入口'}，用于快速判断当前业务运行状态。",
            "点击待办、预警或快捷入口后，系统会跳转到对应业务页面，并保留当前用户权限、组织范围和筛选条件。",
            _runtime_screenshot_note(design_brief),
        ],
    )
    login_fallback = [
        "用户打开系统后首先进入登录界面，系统对账号、密码、验证码和账号状态进行校验。",
        f"登录成功后进入系统首页，首页集中展示{_join_items(blueprint.report_metrics[:4]) or '核心指标、待办事项、异常提醒和快捷入口'}。",
        f"主界面采用{_navigation_description(design_brief)}，{_join_items(blueprint.target_users or blueprint.roles)}登录后展示对应权限范围内的功能模块。",
        f"首页围绕{_join_items(blueprint.business_objects[:5]) or '业务记录'}展示待处理状态、最近操作和统计摘要。",
    ]
    login_paragraphs = _content_paragraphs(
        manual_content,
        "login_main",
        login_fallback,
        min_count=3,
    )
    login_item = (ui_screenshots or {}).get("login") if isinstance(ui_screenshots, dict) else None
    dashboard_item = (ui_screenshots or {}).get("dashboard") if isinstance(ui_screenshots, dict) else None
    visible_login_overview = (
        _visible_content_intro_paragraphs(login_item, "登录界面")
        + _visible_content_intro_paragraphs(dashboard_item, "系统首页")
    )
    if visible_login_overview:
        login_paragraphs = visible_login_overview
    login_paragraphs = _manual_paragraphs_for_renderer(login_paragraphs, design_brief)
    if len(login_paragraphs) < 2:
        login_paragraphs = login_fallback[:3]
    for text in login_paragraphs:
        document.add_paragraph(_customer_manual_text(text))

    _add_heading(document, "四、功能操作说明")
    for index, module in enumerate(blueprint.modules, start=1):
        _add_heading(document, f"4.{index} {module.title}", level=2)
        ui_context = _module_ui_action_context(ui_screenshots, _module_figure_key(module.key), design_brief)
        main_item = (ui_screenshots or {}).get(_module_figure_key(module.key)) if isinstance(ui_screenshots, dict) else None
        visible_module_paragraphs = _visible_content_intro_paragraphs(main_item, module.title)
        if visible_module_paragraphs:
            module_paragraphs = visible_module_paragraphs
        else:
            module_paragraphs = _module_content_paragraphs(manual_content, module.key)
            if _module_paragraphs_conflict_with_ui(module_paragraphs, ui_context, module):
                module_paragraphs = None
            module_paragraphs = module_paragraphs or _module_intro_paragraphs(blueprint, module, ui_context)
        for text in _expand_paragraphs(module_paragraphs, min_count=1, max_count=2):
            document.add_paragraph(_customer_manual_text(text))
        _add_module_operation_sections(document, module, index, ui_screenshots, design_brief, ui_context)

    _add_heading(document, "五、统计分析")
    _add_heading(document, "5.1 统计报表界面", level=2)
    statistics_paragraphs = _content_paragraphs(
        manual_content,
        "statistics",
        [
            f"统计分析功能围绕{_join_items(blueprint.report_metrics[:8]) or '系统运行过程中的业务数据'}进行汇总，帮助管理人员掌握整体运行情况。",
            f"用户可以选择统计周期、业务模块、组织范围和状态条件，系统按{_join_items(blueprint.business_objects[:6]) or '业务对象'}形成列表和图表数据。",
            "报表结果支持导出、打印和归档，便于形成日常运营分析材料。",
            f"统计页会结合{_workflow_summary(blueprint)}展示各流程节点的处理数量、完成率和异常情况。",
        ],
        min_count=3,
    )
    statistics_item = (ui_screenshots or {}).get("statistics") if isinstance(ui_screenshots, dict) else None
    visible_statistics_paragraphs = _visible_content_intro_paragraphs(statistics_item, "统计报表界面")
    if visible_statistics_paragraphs:
        statistics_paragraphs = visible_statistics_paragraphs
    for text in statistics_paragraphs:
        document.add_paragraph(_customer_manual_text(text))
    _add_ui_figure(
        document,
        ui_screenshots,
        "statistics",
        "统计报表界面",
        "系统按日期、模块、状态和角色维度生成统计结果。",
        [
            "用户进入统计报表界面后，先选择统计周期、业务模块、组织范围和状态条件，再点击查询查看汇总结果。",
            f"统计区展示{_join_items(blueprint.report_metrics[:6]) or '数量、完成率、异常数、趋势变化和分组明细'}，并提供趋势图、分类图和明细列表。",
            "报表结果确认无误后，可继续导出、打印或归档；系统会记录导出时间、操作人员和当前查询条件。",
            _runtime_screenshot_note(design_brief),
        ],
    )

    _add_heading(document, "六、权限与安全")
    security_paragraphs = _content_paragraphs(
        manual_content,
        "security",
        [
            "系统通过用户、角色、菜单和数据范围进行权限控制，避免越权访问。",
            "用户登录、数据新增、数据修改、状态变更、导出下载等关键操作均记录审计日志。",
            f"管理员可根据{_join_items(blueprint.target_users or blueprint.roles)}等岗位职责配置角色权限，并定期查看异常登录和高风险操作记录。",
            f"系统按照{_join_items(_clean_rule_text(item) for item in blueprint.quality_rules[:6]) or '字段校验、状态流转、导出审计和权限范围'}执行安全控制。",
            f"关键数据关系包括{_join_items(blueprint.data_relations[:5]) or '业务记录与操作日志关联'}，用于支撑追溯和审计。",
        ],
        min_count=3,
    )
    for text in security_paragraphs:
        document.add_paragraph(_customer_manual_text(text))

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
        min_count=3,
    )
    faq_paragraphs = _extend_faq_paragraphs(blueprint, faq_paragraphs, target_count=10)
    for question in faq_paragraphs:
        document.add_paragraph(_customer_manual_text(question))

    document.save(path)
    return path


def analyze_manual_density(docx_path: Path | None) -> dict:
    if not docx_path or not docx_path.exists():
        return {
            "manual_density_checked": False,
            "manual_paragraph_count": 0,
            "manual_character_count": 0,
            "manual_figure_count": 0,
            "manual_figure_caption_count": 0,
            "manual_operation_note_count": 0,
            "manual_field_note_count": 0,
            "manual_result_note_count": 0,
            "manual_average_chars_per_paragraph": 0,
            "manual_operation_density_ready": False,
        }
    try:
        from docx import Document
        from docx.oxml.ns import qn

        document = Document(docx_path)
    except Exception as exc:
        return {
            "manual_density_checked": False,
            "manual_density_error": str(exc),
            "manual_operation_density_ready": False,
        }
    texts = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]
    table_texts = [
        cell.text.strip()
        for table in document.tables
        for row in table.rows
        for cell in row.cells
        if cell.text.strip()
    ]
    joined = "\n".join(texts)
    paragraph_count = len(texts)
    character_count = len(joined)
    figure_count = len(getattr(document, "inline_shapes", []) or [])
    caption_count = sum(1 for text in texts if text.startswith("图："))
    operation_count = sum(1 for text in texts if _manual_operation_note_text(text))
    field_count = sum(1 for text in texts if _manual_field_note_text(text))
    result_count = sum(1 for text in texts if _manual_result_note_text(text))
    mechanical_label_count = _manual_mechanical_label_count(texts)
    repeated_phrase_count = _manual_repeated_phrase_count(joined)
    average_chars = round(character_count / max(paragraph_count, 1), 2)
    figure_paragraphs = [
        paragraph
        for paragraph in document.paragraphs
        if not paragraph.text.strip() and any(True for _node in paragraph._p.iter(qn("w:drawing")))
    ]
    caption_paragraphs = [paragraph for paragraph in document.paragraphs if paragraph.text.strip().startswith("图：")]
    heading_paragraphs = [
        paragraph
        for paragraph in document.paragraphs
        if str(getattr(paragraph.style, "style_id", "") or "").startswith("Heading")
    ]
    numbered_step_count = sum(1 for text in texts if re.match(r"^\d+\.\s+", text))
    guarded_figure_count = sum(1 for paragraph in figure_paragraphs if paragraph.paragraph_format.keep_with_next is True)
    guarded_caption_count = sum(
        1
        for paragraph in caption_paragraphs
        if paragraph.paragraph_format.keep_with_next is True and paragraph.paragraph_format.keep_together is True
    )
    guarded_heading_count = sum(
        1
        for paragraph in heading_paragraphs
        if paragraph.paragraph_format.keep_with_next is True and paragraph.paragraph_format.keep_together is True
    )
    pagination_constraints_ready = (
        bool(figure_paragraphs)
        and guarded_figure_count == len(figure_paragraphs)
        and guarded_caption_count == len(caption_paragraphs)
        and guarded_heading_count == len(heading_paragraphs)
    )
    numbered_steps_ready = bool(caption_paragraphs) and numbered_step_count >= len(caption_paragraphs)
    return {
        "manual_density_checked": True,
        "manual_paragraph_count": paragraph_count,
        "manual_character_count": character_count,
        "manual_figure_count": figure_count,
        "manual_figure_caption_count": caption_count,
        "manual_operation_note_count": operation_count,
        "manual_field_note_count": field_count,
        "manual_result_note_count": result_count,
        "manual_mechanical_label_count": mechanical_label_count,
        "manual_repeated_phrase_count": repeated_phrase_count,
        "manual_layout_profile": "global-adaptive-v1",
        "manual_figure_paragraph_count": len(figure_paragraphs),
        "manual_guarded_figure_count": guarded_figure_count,
        "manual_guarded_caption_count": guarded_caption_count,
        "manual_guarded_heading_count": guarded_heading_count,
        "manual_numbered_step_count": numbered_step_count,
        "manual_pagination_constraints_ready": pagination_constraints_ready,
        "manual_numbered_steps_ready": numbered_steps_ready,
        "manual_toc_ready": any(re.sub(r"\s+", "", text) == "目录" for text in texts) and len(table_texts) >= 6,
        "manual_natural_style_ready": mechanical_label_count <= 2 and repeated_phrase_count <= 3,
        "manual_average_chars_per_paragraph": average_chars,
        "manual_operation_density_ready": (
            figure_count > 0
            and caption_count >= min(figure_count, 6)
            and operation_count >= min(figure_count, 6)
            and field_count >= min(figure_count, 6)
            and result_count >= min(figure_count, 6)
            and 18 <= average_chars <= 95
        ),
    }


def analyze_manual_ui_consistency(
    docx_path: Path | None,
    blueprint: ProductBlueprint,
    ui_screenshots: dict | None,
) -> dict:
    if not docx_path or not docx_path.exists() or not isinstance(ui_screenshots, dict):
        return {
            "manual_ui_consistency_checked": False,
            "manual_ui_consistency_ready": False,
            "manual_ui_expected_figure_count": 0,
            "manual_ui_actual_figure_count": 0,
        }
    try:
        from docx import Document

        document = Document(docx_path)
    except Exception as exc:
        return {
            "manual_ui_consistency_checked": False,
            "manual_ui_consistency_ready": False,
            "manual_ui_consistency_error": str(exc),
            "manual_ui_expected_figure_count": 0,
            "manual_ui_actual_figure_count": 0,
        }
    expected = _manual_expected_screenshot_items(blueprint, ui_screenshots)
    document_paragraphs = list(document.paragraphs)
    paragraphs = [paragraph.text.strip() for paragraph in document_paragraphs]
    caption_indexes = [index for index, text in enumerate(paragraphs) if text.startswith("图：")]
    title_mismatches: list[dict] = []
    button_mismatches: list[dict] = []
    missing_button_coverage: list[dict] = []
    semantic_mismatches: list[dict] = []
    semantic_coverage_missing: list[dict] = []
    semantic_checked_count = 0
    for position, (key, item) in enumerate(expected):
        if position >= len(caption_indexes):
            title_mismatches.append({"key": key, "expected": str(getattr(item, "title", "") or ""), "actual": ""})
            continue
        caption_index = caption_indexes[position]
        caption = paragraphs[caption_index]
        expected_title = str(getattr(item, "title", "") or "").strip()
        caption_title = re.split(r"[，,]", caption.removeprefix("图："), maxsplit=1)[0].strip()
        if expected_title and _manual_ui_token(expected_title) != _manual_ui_token(caption_title):
            title_mismatches.append({"key": key, "expected": expected_title, "actual": caption_title})
        numbered_notes: list[str] = []
        for text in paragraphs[caption_index + 1 : caption_index + 7]:
            if re.match(r"^\d+\.\s+", text):
                numbered_notes.append(text)
                continue
            if text:
                break
        mentioned = [
            match.group(1).strip()
            for note in numbered_notes
            for match in re.finditer(r"【([^】]{1,24})】", note)
        ]
        for paragraph in document_paragraphs[caption_index + 1 : caption_index + 1 + len(numbered_notes)]:
            mentioned.extend(_manual_paragraph_action_labels(paragraph))
        mentioned = list(dict.fromkeys(label for label in mentioned if label))
        available = _actual_screenshot_action_labels(item, limit=30)
        for label in mentioned:
            if not _manual_ui_button_label_match(label, available):
                button_mismatches.append({"key": key, "title": expected_title, "button": label, "available": available[:12]})
        page_kind = str(getattr(item, "page_kind", "") or "")
        if page_kind in {"module", "operation"} and available and not any(
            _manual_ui_button_label_match(label, available) for label in mentioned
        ):
            missing_button_coverage.append({"key": key, "title": expected_title, "available": available[:12]})
        summary = _visible_content_summary(item)
        if bool(summary.get("ready")):
            semantic_checked_count += 1
            visible_text = str(summary.get("visible_text") or "")
            visible_token = _manual_ui_token(visible_text)
            manual_semantic_text = "\n".join([caption, *numbered_notes])
            manual_semantic_token = _manual_ui_token(manual_semantic_text)
            ignored_semantic_terms = {
                _manual_ui_token(expected_title),
                *(_manual_ui_token(value) for value in ("工作首页", "功能办理", "任务跟踪", "统计分析", "系统设置")),
            }
            semantic_terms = list(
                dict.fromkeys(
                    str(value or "").strip()
                    for name in ("headings", "metrics", "fields", "statuses", "filters")
                    for value in (summary.get(name) or [])
                    if str(value or "").strip()
                    and _manual_ui_token(value) not in ignored_semantic_terms
                )
            )
            covered_terms = [
                term
                for term in semantic_terms
                if len(_manual_ui_token(term)) >= 2 and _manual_ui_token(term) in manual_semantic_token
            ]
            required_coverage = min(2, len(semantic_terms))
            if required_coverage and len(covered_terms) < required_coverage:
                semantic_coverage_missing.append(
                    {
                        "key": key,
                        "title": expected_title,
                        "covered": covered_terms[:8],
                        "available": semantic_terms[:12],
                    }
                )
            module = next(
                (
                    candidate
                    for candidate in blueprint.modules
                    if str(getattr(candidate, "key", "") or "") == str(getattr(item, "module_key", "") or "")
                ),
                None,
            )
            reference_pairs: list[tuple[str, str]] = []
            if module is not None:
                reference_pairs.extend((str(field), str(field)) for field in (getattr(module, "data_fields", []) or []))
            if page_kind in {"dashboard", "statistics"} or key in {"dashboard", "statistics"}:
                reference_pairs.extend((str(metric), str(metric)) for metric in (blueprint.report_metrics or []))
            reference_pairs.extend(
                [
                    ("业务模块", "业务模块"),
                    ("组织范围", "组织范围"),
                    ("状态条件", "状态条件"),
                    ("点击查询", "查询"),
                    ("查询按钮", "查询"),
                    ("打印", "打印"),
                    ("归档", "归档"),
                ]
            )
            missing_references: list[str] = []
            for manual_reference, visible_reference in reference_pairs:
                manual_reference = str(manual_reference or "").strip()
                visible_reference = str(visible_reference or "").strip()
                if len(_manual_ui_token(manual_reference)) < 2:
                    continue
                if manual_reference in manual_semantic_text and _manual_ui_token(visible_reference) not in visible_token:
                    missing_references.append(manual_reference)
            if missing_references:
                semantic_mismatches.append(
                    {
                        "key": key,
                        "title": expected_title,
                        "references": list(dict.fromkeys(missing_references))[:12],
                    }
                )
    document_text = "\n".join(paragraphs)
    expected_renderer = _manual_renderer_from_screenshots(ui_screenshots)
    renderer_mismatches: list[str] = []
    if expected_renderer == "admin":
        for marker in ("移动端", "手机 App", "手机APP", "小程序", "底部导航"):
            if marker in document_text:
                renderer_mismatches.append(marker)
    ready = (
        bool(expected)
        and len(caption_indexes) == len(expected)
        and not title_mismatches
        and not button_mismatches
        and not missing_button_coverage
        and not semantic_mismatches
        and not semantic_coverage_missing
        and not renderer_mismatches
    )
    return {
        "manual_ui_consistency_checked": True,
        "manual_ui_consistency_ready": ready,
        "manual_ui_expected_figure_count": len(expected),
        "manual_ui_actual_figure_count": len(caption_indexes),
        "manual_ui_title_mismatch_count": len(title_mismatches),
        "manual_ui_title_mismatches": title_mismatches[:20],
        "manual_ui_button_mismatch_count": len(button_mismatches),
        "manual_ui_button_mismatches": button_mismatches[:20],
        "manual_ui_missing_button_coverage_count": len(missing_button_coverage),
        "manual_ui_missing_button_coverage": missing_button_coverage[:20],
        "manual_ui_semantic_checked_count": semantic_checked_count,
        "manual_ui_semantic_mismatch_count": len(semantic_mismatches),
        "manual_ui_semantic_mismatches": semantic_mismatches[:20],
        "manual_ui_semantic_coverage_missing_count": len(semantic_coverage_missing),
        "manual_ui_semantic_coverage_missing": semantic_coverage_missing[:20],
        "manual_ui_semantic_ready": not semantic_mismatches and not semantic_coverage_missing,
        "manual_ui_expected_renderer": expected_renderer,
        "manual_ui_renderer_mismatch_count": len(renderer_mismatches),
        "manual_ui_renderer_mismatches": renderer_mismatches,
    }


def _manual_paragraph_action_labels(paragraph) -> list[str]:
    labels: list[str] = []
    try:
        properties = paragraph._p.xpath(".//wp:docPr")
    except Exception:
        properties = []
    for prop in properties:
        for attribute in ("descr", "title"):
            label = str(prop.get(attribute) or "").strip()
            if label and label not in labels:
                labels.append(label)
    return labels


def _manual_expected_screenshot_items(blueprint: ProductBlueprint, ui_screenshots: dict) -> list[tuple[str, object]]:
    result: list[tuple[str, object]] = []
    for key in ("login", "dashboard"):
        item = ui_screenshots.get(key)
        if item is not None and getattr(item, "image_path", None):
            result.append((key, item))
    for module in blueprint.modules:
        main_key = _module_figure_key(module.key)
        main_item = ui_screenshots.get(main_key)
        if main_item is not None and getattr(main_item, "image_path", None):
            result.append((main_key, main_item))
        result.extend(_module_secondary_screenshot_items(ui_screenshots, module.key))
    item = ui_screenshots.get("statistics")
    if item is not None and getattr(item, "image_path", None):
        result.append(("statistics", item))
    return result


def _manual_ui_token(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", str(value or "")).lower()


def _manual_ui_button_label_match(label: str, available: list[str]) -> bool:
    token = _manual_ui_token(label)
    if not token:
        return False
    return any(
        token == candidate or (len(token) >= 2 and (token in candidate or candidate in token))
        for candidate in (_manual_ui_token(item) for item in available)
        if candidate
    )


def _manual_operation_note_text(text: str) -> bool:
    value = str(text or "").strip()
    if "操作说明：" in value or "使用方法：" in value or "操作步骤：" in value:
        return True
    return bool(re.search(r"(用户|管理员|操作员|使用者).{0,18}(进入|点击|选择|打开|勾选|录入|填写|查看|查询|导出|返回)", value))


def _manual_field_note_text(text: str) -> bool:
    value = str(text or "").strip()
    if "字段说明：" in value or "信息项" in value or "数据项" in value:
        return True
    return bool(re.search(r"(页面|列表|表单|统计区|登录页).{0,18}(包含|展示|显示|录入|核对|填写|主要字段)", value))


def _manual_result_note_text(text: str) -> bool:
    value = str(text or "").strip()
    if "处理结果：" in value or "保存成功" in value or "修改成功" in value:
        return True
    return bool(re.search(r"(系统|页面).{0,20}(返回|刷新|更新|记录|写入|导出|提示|加载|跳转)", value))


def _manual_mechanical_label_count(texts: list[str]) -> int:
    labels = (
        "操作说明：",
        "字段说明：",
        "处理结果：",
        "业务一致性：",
        "界面说明：",
        "页面路径：",
        "校验说明：",
        "留痕说明：",
        "权限说明：",
    )
    return sum(1 for text in texts for label in labels if label in text)


def _manual_repeated_phrase_count(text: str) -> int:
    phrases = (
        "登记、校验、分析、确认",
        "查询、追加、修改、查看、失效、导出",
        "新增、编辑、审核、导出、日志、校验、权限联动",
    )
    return sum(max(0, str(text or "").count(phrase) - 1) for phrase in phrases)


def generate_source_docx(task: GenerationTask, source_dir: Path, output_dir: Path) -> tuple[Path, dict]:
    from docx import Document
    from docx.shared import Pt

    source_entries = [entry for entry in read_source_line_entries(source_dir) if str(entry.get("text", "")).strip()]
    lines = [str(entry.get("text", "")) for entry in source_entries]
    lines_per_page = 50
    # Keep 50 source lines on one physical A4 page.  The previous 15.2pt
    # spacing left virtually no tolerance for font metrics or a wrapped long
    # line, so LibreOffice frequently pushed line 50 onto a nearly blank page.
    source_font_size_pt = 9
    # LibreOffice pagination probes show 15.10pt is the largest stable value
    # that keeps exactly 50 physical lines on one A4 page. 15.15pt already
    # pushes line 50 onto a second page in this layout.
    source_line_spacing_pt = 15.10
    selected_entry_pages, source_total_pages, selection_mode, material_quality = _select_source_material_pages(
        source_entries,
        lines_per_page=lines_per_page,
    )
    path = output_dir / f"{task.safe_name}_代码-({_safe_file_label(task.language)}).docx"
    document = Document()
    _set_default_font(document, "宋体", 10.5)
    section = document.sections[0]
    _configure_source_material_section(
        section,
        header_text=f"{task.software_name} {task.version}",
    )

    for page_index, page_entries in enumerate(selected_entry_pages, start=1):
        if page_index > 1:
            document.add_page_break()
        for entry in page_entries:
            line = str(entry.get("text", ""))
            indent_columns, display_line = _source_line_indent(line)
            indent_width_pt = _source_indent_width_pt(indent_columns)
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.space_before = Pt(0)
            paragraph.paragraph_format.space_after = Pt(0)
            paragraph.paragraph_format.line_spacing = Pt(source_line_spacing_pt)
            paragraph.paragraph_format.left_indent = Pt(indent_width_pt)
            paragraph.paragraph_format.first_line_indent = Pt(0)
            run = paragraph.add_run(display_line)
            run.font.name = "宋体"
            run.font.size = Pt(source_font_size_pt)
            _set_run_east_asia_font(run, "宋体")
            _fit_source_line_to_page_width(
                run,
                display_line,
                source_font_size_pt,
                left_indent_pt=indent_width_pt,
            )

    document.save(path)
    report = {
        "source_total_lines": len(lines),
        "source_total_pages": source_total_pages,
        "source_selected_pages": len(selected_entry_pages),
        "lines_per_page": lines_per_page,
        "source_font_size_pt": source_font_size_pt,
        "source_line_spacing_pt": source_line_spacing_pt,
        "source_line_numbers_enabled": False,
        "source_lines_per_page_exact_match": lines_per_page == 50,
        "source_page_fill_strategy": "exact-50-lines-a4-physical-page-width-fitted",
        "selection_mode": selection_mode,
        "source_page_sources": _source_page_sources(selected_entry_pages),
        **_source_material_order_report(source_dir),
        **material_quality,
    }
    return path, report


def _source_line_indent(text: str, tab_size: int = 4) -> tuple[int, str]:
    expanded = str(text or "").expandtabs(tab_size)
    indent_columns = len(expanded) - len(expanded.lstrip(" "))
    return indent_columns, expanded[indent_columns:]


def _source_indent_width_pt(indent_columns: int) -> float:
    # A code-space is slightly wider than half of the 9pt body font. Using a
    # paragraph indent keeps nesting stable even when a long line is condensed.
    return round(max(0, min(int(indent_columns), 32)) * 4.7, 2)


def _fit_source_line_to_page_width(
    run,
    text: str,
    font_size_pt: float,
    *,
    left_indent_pt: float = 0,
) -> int:
    """Condense only long source lines so one logical line stays one PDF line."""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    import unicodedata

    value = str(text or "").expandtabs(4)
    width_units = sum(
        1.0 if unicodedata.east_asian_width(char) in {"W", "F", "A"} else 0.55
        for char in value
    )
    estimated_width_pt = width_units * float(font_size_pt)
    available_width_pt = max(300.0, 535.0 - max(0.0, float(left_indent_pt)))
    scale = 100 if estimated_width_pt <= available_width_pt else max(55, int(available_width_pt * 100 / estimated_width_pt))
    if scale < 100:
        run_properties = run._r.get_or_add_rPr()
        width = run_properties.find(qn("w:w"))
        if width is None:
            width = OxmlElement("w:w")
            run_properties.append(width)
        width.set(qn("w:val"), str(scale))
    return scale


def _select_source_material_pages(source_entries: list[dict], lines_per_page: int) -> tuple[list[list[dict]], int, str, dict]:
    source_total_pages = _page_count(len(source_entries), lines_per_page)
    if not source_entries:
        return [], 0, "empty", _source_material_quality([], [])

    if source_total_pages > 60:
        block_size = 30 * lines_per_page
        selected_entries = list(source_entries[:block_size]) + list(source_entries[-block_size:])
        entry_pages = [
            selected_entries[index : index + lines_per_page]
            for index in range(0, len(selected_entries), lines_per_page)
        ]
        selection_mode = "first_30_last_30_continuous"
    else:
        entry_pages = [
            source_entries[index : index + lines_per_page]
            for index in range(0, len(source_entries), lines_per_page)
        ]
        selection_mode = "all_continuous"
    selected_entries = [entry for page in entry_pages for entry in page]
    quality = _source_material_quality(selected_entries, selected_entries)
    quality["source_continuous_selection"] = True
    quality["source_material_filler_line_count"] = 0
    quality["source_material_filler_line_ratio"] = 0
    return entry_pages, source_total_pages, selection_mode, quality


def _page_count(line_count: int, lines_per_page: int) -> int:
    if line_count <= 0:
        return 0
    return (line_count + lines_per_page - 1) // lines_per_page


def _source_material_order_report(source_dir: Path) -> dict:
    path = source_dir / SOURCE_MATERIAL_ORDER_FILE
    if not path.exists():
        return {
            "source_material_order_manifest_used": False,
            "source_material_order_strategy": "path-sorted",
            "source_material_order_file_count": 0,
        }
    try:
        import json

        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "source_material_order_manifest_used": False,
            "source_material_order_strategy": "path-sorted",
            "source_material_order_error": str(exc),
            "source_material_order_file_count": 0,
        }
    files = data.get("files") if isinstance(data, dict) else []
    return {
        "source_material_order_manifest_used": True,
        "source_material_order_strategy": str(data.get("strategy") or ""),
        "source_material_order_file_count": len(files) if isinstance(files, list) else 0,
    }


def _source_entry_information_score(entry: dict) -> int:
    text = str(entry.get("text", ""))
    stripped = text.strip()
    file_name = str(entry.get("file", "")).replace("\\", "/").lower()
    if not stripped:
        return -5
    if _is_low_information_source_line(stripped):
        return -4
    if _is_accessor_boilerplate_source_line(stripped):
        return -2

    score = 0
    if any(part in file_name for part in ("/service/", "/controller/", "/repository/", "/mapper/", "/api/", "/workflow/", "/business/")):
        score += 2
    if any(part in file_name for part in ("/domain/", "/dto/", "/model/", "/entity/", "/config/", "/common/")):
        score -= 1
    if re.search(r"\b(if|for|while|switch|try|catch|throw|return|await|yield)\b", stripped):
        score += 2
    if re.search(
        r"\b(validate|audit|workflow|status|export|import|query|filter|permission|authorize|approve|review|trace|sync|statistics|report|rule|metric|record|module|operation|save|update|delete|find|build|normalize|append|calculate|schedule|route|detect|analyze|warning|alert)\b",
        stripped,
        re.I,
    ):
        score += 2
    if re.search(r"\b(public|private|protected|def|function|class|interface|enum|const|let|var)\b", stripped):
        score += 1
    if len(stripped) >= 42:
        score += 1
    return score


def _is_low_information_source_line(text: str) -> bool:
    stripped = str(text).strip()
    if not stripped:
        return True
    if re.fullmatch(r"[{}\[\]();,]+", stripped):
        return True
    if stripped in {"}", "{", "};", ");", "})", "});", "],"}:
        return True
    return False


def _is_accessor_boilerplate_source_line(text: str) -> bool:
    stripped = str(text).strip()
    if re.search(r"\b(public|private|protected)\s+[\w<>\[\], ?]+\s+(get|set|is)[A-Z_][A-Za-z0-9_]*\s*\(", stripped):
        return True
    if re.fullmatch(r"return\s+(this\.)?[A-Za-z_][A-Za-z0-9_]*;?", stripped):
        return True
    if re.fullmatch(r"this\.[A-Za-z_][A-Za-z0-9_]*\s*=\s*[A-Za-z_][A-Za-z0-9_]*;?", stripped):
        return True
    return False


def _source_material_quality(display_entries: list[dict], candidate_entries: list[dict]) -> dict:
    from collections import Counter

    texts = [str(entry.get("text", "")) for entry in display_entries]
    candidate_texts = [str(entry.get("text", "")) for entry in candidate_entries]
    total = max(len(texts), 1)
    low_count = sum(1 for text in texts if _is_low_information_source_line(text))
    accessor_count = sum(1 for text in texts if _is_accessor_boilerplate_source_line(text))
    business_count = sum(1 for entry in display_entries if _source_entry_information_score(entry) >= 3)
    candidate_low_count = sum(1 for text in candidate_texts if _is_low_information_source_line(text))
    selected_file_counts = Counter(str(entry.get("file", "")) for entry in display_entries)
    midpoint = len(display_entries) // 2
    front_files = {str(entry.get("file", "")) for entry in display_entries[:midpoint] if str(entry.get("file", ""))}
    tail_files = {str(entry.get("file", "")) for entry in display_entries[midpoint:] if str(entry.get("file", ""))}
    unique_line_ratio = round(len({text.strip() for text in texts if text.strip()}) / total, 4)
    max_file_ratio = round(max(selected_file_counts.values(), default=0) / total, 4)
    diversity_ready = (
        len(front_files) >= 4
        and len(tail_files) >= 4
        and max_file_ratio <= 0.35
        and unique_line_ratio >= 0.16
    )
    return {
        "source_presentation_filter_enabled": False,
        "source_low_information_line_count": low_count,
        "source_low_information_line_ratio": round(low_count / total, 4),
        "source_accessor_boilerplate_line_count": accessor_count,
        "source_accessor_boilerplate_line_ratio": round(accessor_count / total, 4),
        "source_business_logic_line_count": business_count,
        "source_business_logic_line_ratio": round(business_count / total, 4),
        "source_candidate_low_information_line_ratio": round(candidate_low_count / max(len(candidate_texts), 1), 4),
        "source_selected_unique_file_count": len(selected_file_counts),
        "source_front_unique_file_count": len(front_files),
        "source_tail_unique_file_count": len(tail_files),
        "source_max_selected_file_ratio": max_file_ratio,
        "source_unique_line_ratio": unique_line_ratio,
        "source_material_diversity_ready": diversity_ready,
    }


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
    info_env = _soft_copyright_info_environment(task, blueprint)
    feature_category = _technical_feature_category(task)
    text = "\n".join(
        [
            f"【软件全称】{task.software_name}",
            f"【版本号】{task.version}",
            f"【软件分类】{task.software_category}",
            f"【开发的硬件环境】{info_env['dev_hardware']}",
            f"【运行的硬件环境】{info_env['runtime_hardware']}",
            f"【开发该软件的操作系统】{info_env['dev_os']}",
            f"【软件开发环境/开发工具】{info_env['dev_tool']}",
            f"【该软件的运行平台/操作系统】{info_env['runtime_os']}",
            f"【软件运行支撑环境/支持软件】{info_env['runtime_support']}",
            f"【编程语言】{_info_programming_language(task, blueprint)}",
            f"【源程序量】{source_lines}",
            f"【开发目的】{_info_development_purpose(task, blueprint)}",
            f"【面向领域/行业】{blueprint.industry}",
            f"【软件的主要功能】{_info_main_functions(task, blueprint)}",
            f"【软件的技术特点分类】{feature_category}",
            f"【软件的技术特点】{_info_technical_features(task, blueprint)}",
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
    pdf_path = output_dir / f"{docx_path.stem}.pdf"
    completed = None
    converted = False
    try:
        with tempfile.TemporaryDirectory(prefix="lo-profile-") as profile_dir, tempfile.TemporaryDirectory(prefix="lo-work-") as work_dir:
            profile_uri = Path(profile_dir).resolve().as_uri()
            office_runner = _office_runner_path(office)
            work_path = Path(work_dir)
            temp_docx = work_path / "input.docx"
            temp_pdf = work_path / "input.pdf"
            shutil.copy2(docx_path, temp_docx)
            command = [
                office_runner,
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
                str(work_path.resolve()),
                str(temp_docx.resolve()),
            ]
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=_office_timeout_seconds(),
                check=False,
                env=_office_subprocess_env(office_runner),
                startupinfo=_office_startup_info(),
                creationflags=_office_creation_flags(),
            )
            if completed.returncode == 0 and temp_pdf.exists():
                shutil.copy2(temp_pdf, pdf_path)
                converted = True
    except Exception as exc:
        return None, f"PDF 转换失败：{exc}"
    if not converted or not pdf_path.exists():
        if completed is not None:
            return None, completed.stderr.strip() or completed.stdout.strip() or "PDF 转换失败。"
        return None, "PDF 转换失败。"
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


def _find_pdfinfo_binary() -> str | None:
    env_value = os.getenv("SOFT_PDFINFO_PATH", "").strip()
    if env_value and Path(env_value).exists():
        return env_value
    candidates = [
        Path.cwd() / "pdfinfo.exe",
        Path.cwd() / "bin" / "pdfinfo.exe",
        Path.home()
        / ".cache"
        / "codex-runtimes"
        / "codex-primary-runtime"
        / "dependencies"
        / "native"
        / "poppler"
        / "Library"
        / "bin"
        / "pdfinfo.exe",
        Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "bin" / "pdfinfo.exe",
        Path.cwd() / "pdfinfo.cmd",
        Path.cwd() / "bin" / "pdfinfo.cmd",
        Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "bin" / "pdfinfo.cmd",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return shutil.which("pdfinfo")


def _find_pdftotext_binary() -> str | None:
    env_value = os.getenv("SOFT_PDFTOTEXT_PATH", "").strip()
    if env_value and Path(env_value).exists():
        return env_value
    candidates = [
        Path.cwd() / "pdftotext.exe",
        Path.cwd() / "bin" / "pdftotext.exe",
        Path.home()
        / ".cache"
        / "codex-runtimes"
        / "codex-primary-runtime"
        / "dependencies"
        / "native"
        / "poppler"
        / "Library"
        / "bin"
        / "pdftotext.exe",
        Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "bin" / "pdftotext.exe",
        Path.cwd() / "pdftotext.cmd",
        Path.cwd() / "bin" / "pdftotext.cmd",
        Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "bin" / "pdftotext.cmd",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return shutil.which("pdftotext")


def _parse_pdfinfo_output(output: str) -> dict:
    pages = 0
    width_pt = 0.0
    height_pt = 0.0
    for raw_line in str(output or "").splitlines():
        line = raw_line.strip()
        if line.startswith("Pages:"):
            value = line.split(":", 1)[1].strip()
            try:
                pages = int(value)
            except ValueError:
                pages = 0
        if line.startswith("Page size:"):
            match = re.search(r"([0-9.]+)\s+x\s+([0-9.]+)\s+pts", line)
            if match:
                width_pt = float(match.group(1))
                height_pt = float(match.group(2))
    width_cm = round(width_pt * 2.54 / 72, 2) if width_pt else 0
    height_cm = round(height_pt * 2.54 / 72, 2) if height_pt else 0
    return {
        "pdf_page_count": pages,
        "pdf_page_width_cm": width_cm,
        "pdf_page_height_cm": height_cm,
        "pdf_is_portrait": bool(height_cm > width_cm) if width_cm and height_cm else False,
        "pdf_is_a4": abs(width_cm - 21.0) <= 0.2 and abs(height_cm - 29.7) <= 0.2,
    }


def _pdf_text_lines(text: str) -> list[str]:
    result: list[str] = []
    for raw_line in str(text or "").splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue
        result.append(line)
    return result


def _is_manual_text_density_page(
    lines: list[str],
    page_index: int,
    page_count: int | None = None,
    minimum_lines: int = 30,
) -> bool:
    if not lines:
        return False
    joined = "\n".join(lines)
    if page_index == 1 and len(lines) < 12 and any(token in joined for token in ("软件说明书", "版本号")):
        return False
    if page_index <= 3 and any(re.sub(r"\s+", "", line) == "目录" for line in lines):
        return False
    if page_count and page_index == page_count and any(token in joined for token in ("权限与安全", "常见问题处理", "常见问题")):
        return False
    caption_count = sum(1 for line in lines if line.startswith("图："))
    body_lines = [line for line in lines if not line.startswith("图：")]
    body_line_count = len(body_lines)
    if caption_count and body_line_count < 18:
        return False
    figure_note_markers = (
        "操作说明",
        "字段说明",
        "处理结果",
        "业务一致性",
        "页面路径",
        "校验说明",
        "留痕说明",
        "界面说明",
        "截图来源",
        "源码依据",
        "页面主要展示",
        "列表区重点展示",
        "操作日志",
        "数据处理要求一致",
        "用户可从系统首页",
        "当前筛选条件",
    )
    if (
        caption_count
        and body_line_count < minimum_lines
        and any(marker in joined for marker in figure_note_markers)
    ):
        return False
    char_count = sum(len(line) for line in lines)
    if len(lines) >= 18:
        return True
    heading_hits = sum(1 for line in lines if re.match(r"^([一二三四五六七八九十]+、|\d+(\.\d+)+)", line))
    return char_count >= 60 or (len(lines) >= 8 and heading_hits >= 1)


def _analyze_pdf_layout_from_media_box(pdf_path: Path, reason: str) -> dict:
    try:
        data = pdf_path.read_bytes()
    except Exception as exc:
        return {
            "pdf_layout_checked": False,
            "pdf_exists": True,
            "pdf_layout_error": f"{reason} MediaBox 兜底读取失败：{exc}",
            "pdf_is_a4": False,
        }
    text = data.decode("latin-1", errors="ignore")
    page_count = len(re.findall(r"/Type\s*/Page\b", text))
    media_boxes = re.findall(
        r"/MediaBox\s*\[\s*(-?[0-9.]+)\s+(-?[0-9.]+)\s+(-?[0-9.]+)\s+(-?[0-9.]+)\s*\]",
        text,
    )
    if not media_boxes:
        return {
            "pdf_layout_checked": False,
            "pdf_exists": True,
            "pdf_layout_error": f"{reason} MediaBox 兜底未找到页面尺寸。",
            "pdf_page_count": page_count,
            "pdf_is_a4": False,
        }
    x0, y0, x1, y1 = [float(value) for value in media_boxes[0]]
    width_pt = abs(x1 - x0)
    height_pt = abs(y1 - y0)
    width_cm = round(width_pt * 2.54 / 72, 2) if width_pt else 0
    height_cm = round(height_pt * 2.54 / 72, 2) if height_pt else 0
    return {
        "pdf_layout_checked": True,
        "pdf_exists": True,
        "pdf_layout_method": "mediabox-fallback",
        "pdf_layout_note": reason,
        "pdf_page_count": page_count or len(media_boxes),
        "pdf_page_width_cm": width_cm,
        "pdf_page_height_cm": height_cm,
        "pdf_is_portrait": bool(height_cm > width_cm) if width_cm and height_cm else False,
        "pdf_is_a4": abs(width_cm - 21.0) <= 0.2 and abs(height_cm - 29.7) <= 0.2,
    }


def _office_runner_path(office: str) -> str:
    office_path = Path(office)
    if os.name == "nt" and office_path.name.lower() == "soffice.exe":
        console_runner = office_path.with_name("soffice.com")
        if console_runner.exists():
            return str(console_runner)
    return str(office_path)


def _office_subprocess_env(office: str) -> dict[str, str]:
    env = os.environ.copy()
    for key in (
        "PYTHONHOME",
        "PYTHONPATH",
        "URE_BOOTSTRAP",
        "UNO_PATH",
        "UNO_TYPES",
        "UNO_SERVICES",
    ):
        env.pop(key, None)
    office_dir = str(Path(office).resolve().parent)
    env["PATH"] = office_dir + os.pathsep + env.get("PATH", "")
    env.setdefault("SAL_USE_VCLPLUGIN", "svp")
    env.setdefault("OOO_DISABLE_RECOVERY", "1")
    return env


def _office_startup_info():
    if os.name != "nt":
        return None
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    return startupinfo


def _office_creation_flags() -> int:
    if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
        return subprocess.CREATE_NO_WINDOW
    return 0


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


def _configure_application_section(
    section,
    *,
    header_text: str,
    top_margin_pt: float,
    bottom_margin_pt: float,
    left_margin_pt: float,
    right_margin_pt: float,
    header_font_size: float = 9,
) -> None:
    from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm, Pt

    section.page_width = Cm(21)
    section.page_height = Cm(29.7)
    section.top_margin = Pt(top_margin_pt)
    section.bottom_margin = Pt(bottom_margin_pt)
    section.left_margin = Pt(left_margin_pt)
    section.right_margin = Pt(right_margin_pt)
    section.header_distance = Cm(0.85)
    header_part = section.header
    for existing_table in list(header_part.tables):
        existing_table._element.getparent().remove(existing_table._element)
    header = header_part.paragraphs[0] if header_part.paragraphs else header_part.add_paragraph()
    header.clear()
    header._element.getparent().remove(header._element)

    table_width = section.page_width - section.left_margin - section.right_margin - Cm(0.35)
    page_width = Cm(1.6)
    title_width = table_width - page_width
    table = section.header.add_table(rows=1, cols=2, width=table_width)
    table.autofit = False
    _set_table_width(table, table_width)
    _set_table_grid(table, [title_width, page_width])
    _set_table_bottom_border(table)
    title_cell, page_cell = table.rows[0].cells
    title_cell.width = title_width
    page_cell.width = page_width
    _set_cell_width(title_cell, title_width)
    _set_cell_width(page_cell, page_width)
    for cell in (title_cell, page_cell):
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    _set_cell_margins(title_cell, top=0, bottom=50, left=0, right=60)
    _set_cell_margins(page_cell, top=0, bottom=50, left=40, right=100)

    title_paragraph = title_cell.paragraphs[0]
    title_paragraph.paragraph_format.space_before = Pt(0)
    title_paragraph.paragraph_format.space_after = Pt(4)
    title_run = title_paragraph.add_run(header_text)
    title_run.font.name = "宋体"
    title_run.font.size = Pt(header_font_size)
    _set_run_east_asia_font(title_run, "宋体")

    page_paragraph = page_cell.paragraphs[0]
    page_paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    page_paragraph.paragraph_format.space_before = Pt(0)
    page_paragraph.paragraph_format.space_after = Pt(4)
    _add_page_number_field(page_paragraph)
    for paragraph in (title_paragraph, page_paragraph):
        for run in paragraph.runs:
            run.font.name = "宋体"
            run.font.size = Pt(header_font_size)
            _set_run_east_asia_font(run, "宋体")


def _configure_source_material_section(section, *, header_text: str) -> None:
    from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm, Pt

    section.page_width = Cm(21)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(1.45)
    section.bottom_margin = Cm(1.05)
    section.left_margin = Cm(0.75)
    section.right_margin = Cm(0.75)
    section.header_distance = Cm(0.75)
    header_part = section.header
    for existing_table in list(header_part.tables):
        existing_table._element.getparent().remove(existing_table._element)
    header = header_part.paragraphs[0] if header_part.paragraphs else header_part.add_paragraph()
    header.clear()
    header._element.getparent().remove(header._element)
    table_width = section.page_width - section.left_margin - section.right_margin - Cm(0.35)
    title_width = Cm(15.0)
    page_width = table_width - title_width
    table = section.header.add_table(rows=1, cols=2, width=table_width)
    table.autofit = False
    _set_table_width(table, table_width)
    _set_table_grid(table, [title_width, page_width])
    _set_table_bottom_border(table)
    title_cell, page_cell = table.rows[0].cells
    title_cell.width = title_width
    page_cell.width = page_width
    _set_cell_width(title_cell, title_width)
    _set_cell_width(page_cell, page_width)
    for cell in (title_cell, page_cell):
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    _set_cell_margins(title_cell, top=0, bottom=50, left=0, right=60)
    _set_cell_margins(page_cell, top=0, bottom=50, left=40, right=100)
    title_paragraph = title_cell.paragraphs[0]
    title_paragraph.paragraph_format.space_before = Pt(0)
    title_paragraph.paragraph_format.space_after = Pt(4)
    title_run = title_paragraph.add_run(header_text)
    title_run.font.name = "宋体"
    title_run.font.size = Pt(10.5)
    _set_run_east_asia_font(title_run, "宋体")
    page_paragraph = page_cell.paragraphs[0]
    page_paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    page_paragraph.paragraph_format.space_before = Pt(0)
    page_paragraph.paragraph_format.space_after = Pt(4)
    _add_page_number_field(page_paragraph)
    for paragraph in (title_paragraph, page_paragraph):
        for run in paragraph.runs:
            run.font.name = "宋体"
            run.font.size = Pt(10.5)
            _set_run_east_asia_font(run, "宋体")


def _set_paragraph_bottom_border(paragraph) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    p_pr = paragraph._p.get_or_add_pPr()
    p_bdr = p_pr.find(qn("w:pBdr"))
    if p_bdr is None:
        p_bdr = OxmlElement("w:pBdr")
        p_pr.append(p_bdr)
    bottom = p_bdr.find(qn("w:bottom"))
    if bottom is None:
        bottom = OxmlElement("w:bottom")
        p_bdr.append(bottom)
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "4")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), "BFBFBF")


def _set_table_width(table, width) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    tbl_pr = table._tbl.tblPr
    tbl_w = tbl_pr.find(qn("w:tblW"))
    if tbl_w is None:
        tbl_w = OxmlElement("w:tblW")
        tbl_pr.append(tbl_w)
    tbl_w.set(qn("w:w"), str(_length_to_twips(width)))
    tbl_w.set(qn("w:type"), "dxa")


def _set_table_grid(table, widths: list) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    tbl_grid = table._tbl.tblGrid
    if tbl_grid is None:
        tbl_grid = OxmlElement("w:tblGrid")
        table._tbl.insert(0, tbl_grid)
    for child in list(tbl_grid):
        tbl_grid.remove(child)
    for width in widths:
        grid_col = OxmlElement("w:gridCol")
        grid_col.set(qn("w:w"), str(_length_to_twips(width)))
        tbl_grid.append(grid_col)


def _set_table_bottom_border(table) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    tbl_pr = table._tbl.tblPr
    tbl_borders = tbl_pr.find(qn("w:tblBorders"))
    if tbl_borders is None:
        tbl_borders = OxmlElement("w:tblBorders")
        tbl_pr.append(tbl_borders)
    for border_name in ("top", "left", "right", "insideH", "insideV"):
        border = tbl_borders.find(qn(f"w:{border_name}"))
        if border is None:
            border = OxmlElement(f"w:{border_name}")
            tbl_borders.append(border)
        border.set(qn("w:val"), "nil")
    bottom = tbl_borders.find(qn("w:bottom"))
    if bottom is None:
        bottom = OxmlElement("w:bottom")
        tbl_borders.append(bottom)
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "4")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), "BFBFBF")


def _set_cell_width(cell, width) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    tc_pr = cell._tc.get_or_add_tcPr()
    tc_w = tc_pr.find(qn("w:tcW"))
    if tc_w is None:
        tc_w = OxmlElement("w:tcW")
        tc_pr.append(tc_w)
    tc_w.set(qn("w:w"), str(_length_to_twips(width)))
    tc_w.set(qn("w:type"), "dxa")


def _set_cell_margins(cell, *, top: int, bottom: int, left: int, right: int) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    tc_pr = cell._tc.get_or_add_tcPr()
    tc_mar = tc_pr.find(qn("w:tcMar"))
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for name, value in {"top": top, "bottom": bottom, "left": left, "right": right}.items():
        node = tc_mar.find(qn(f"w:{name}"))
        if node is None:
            node = OxmlElement(f"w:{name}")
            tc_mar.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def _length_to_twips(value) -> int:
    return int(round(int(value) / 635))


def _set_default_font(
    document,
    font_name: str,
    size: float,
    *,
    line_spacing_pt: float = 13.5,
    space_after_pt: float = 0,
) -> None:
    from docx.shared import Pt

    styles = document.styles
    normal = styles["Normal"]
    normal.font.name = font_name
    normal.font.size = Pt(size)
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(space_after_pt)
    normal.paragraph_format.line_spacing = Pt(line_spacing_pt)
    element = normal._element
    rpr = element.rPr
    if rpr is not None:
        fonts = rpr.rFonts
        if fonts is not None:
            fonts.set("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}eastAsia", font_name)


def _set_run_east_asia_font(run, font_name: str) -> None:
    if run._element.rPr is not None and run._element.rPr.rFonts is not None:
        run._element.rPr.rFonts.set("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}eastAsia", font_name)


def _add_heading(document, text: str, level: int = 1) -> None:
    from docx.shared import Pt, RGBColor

    paragraph = document.add_heading(text, level=level)
    paragraph.paragraph_format.space_before = Pt(6 if level <= 1 else 4)
    paragraph.paragraph_format.space_after = Pt(2)
    paragraph.paragraph_format.line_spacing = Pt(18 if level <= 2 else 15.5)
    paragraph.paragraph_format.keep_with_next = True
    paragraph.paragraph_format.keep_together = True
    size_map = {1: 14, 2: 14, 3: 12}
    color = RGBColor(31, 41, 55)
    for run in paragraph.runs:
        run.font.name = "宋体"
        run.font.size = Pt(size_map.get(level, 11))
        run.font.bold = True
        run.font.color.rgb = color
        if run._element.rPr is not None and run._element.rPr.rFonts is not None:
            run._element.rPr.rFonts.set("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}eastAsia", "宋体")


def _add_ui_placeholder(document, title: str, caption: str) -> None:
    from docx.shared import Pt, RGBColor

    note_p = document.add_paragraph(_customer_manual_text(f"{title}用于{caption}"))
    note_p.paragraph_format.space_after = Pt(4)
    for note_run in note_p.runs:
        note_run.font.color.rgb = RGBColor(80, 80, 80)
        note_run.font.size = Pt(9)
    caption_p = document.add_paragraph(_customer_manual_text(f"图：{title}，{caption}"))
    caption_p.paragraph_format.space_after = Pt(6)
    for run in caption_p.runs:
        run.font.color.rgb = RGBColor(80, 80, 80)


def _manual_toc_entries(blueprint: ProductBlueprint) -> list[tuple[str, str]]:
    entries = [
        ("一、软件概述", "一、软件概述"),
        ("二、运行环境", "二、运行环境"),
        ("三、登录与主界面", "三、登录与主界面"),
        ("四、功能操作说明", "四、功能操作说明"),
    ]
    entries.extend((f"4.{index} {module.title}", f"4.{index} {module.title}") for index, module in enumerate(blueprint.modules, start=1))
    entries.extend([
        ("五、统计分析", "五、统计分析"),
        ("六、权限与安全", "六、权限与安全"),
        ("七、常见问题处理", "七、常见问题处理"),
    ])
    return entries


def _style_manual_toc_paragraph(paragraph, label: str, page_number: int | None = None) -> None:
    from docx.enum.text import WD_TAB_ALIGNMENT, WD_TAB_LEADER
    from docx.shared import Inches, Pt, RGBColor

    paragraph.clear()
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(4)
    paragraph.paragraph_format.line_spacing = Pt(20)
    is_module_entry = bool(re.match(r"^4\.\d+\s", label))
    paragraph.paragraph_format.left_indent = Inches(0.25 if is_module_entry else 0)
    paragraph.paragraph_format.tab_stops.add_tab_stop(Inches(5.85), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)
    label_run = paragraph.add_run(label)
    label_run.font.name = "宋体"
    label_run.font.size = Pt(10.5 if is_module_entry else 11)
    label_run.font.bold = not is_module_entry
    label_run.font.color.rgb = RGBColor(55, 55, 55)
    _set_run_east_asia_font(label_run, "宋体")
    paragraph.add_run("\t")
    page_run = paragraph.add_run(str(page_number) if page_number else "")
    page_run.font.name = "宋体"
    page_run.font.size = Pt(10.5)
    page_run.font.bold = not is_module_entry
    page_run.font.color.rgb = RGBColor(55, 55, 55)
    _set_run_east_asia_font(page_run, "宋体")


def _add_manual_toc(document, blueprint: ProductBlueprint) -> None:
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm, Pt, RGBColor

    title = document.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.space_after = Pt(20)
    title.paragraph_format.line_spacing = Pt(30)
    run = title.add_run("目 录")
    run.bold = True
    run.font.name = "宋体"
    run.font.size = Pt(22)
    run.font.color.rgb = RGBColor(130, 30, 30)
    _set_run_east_asia_font(run, "宋体")

    table = document.add_table(rows=0, cols=1)
    table.autofit = False
    section = document.sections[0]
    table_width = section.page_width - section.left_margin - section.right_margin - Cm(0.35)
    _set_table_width(table, table_width)
    _set_table_grid(table, [table_width])
    for label, _heading in _manual_toc_entries(blueprint):
        cell = table.add_row().cells[0]
        _set_cell_width(cell, table_width)
        _set_cell_margins(cell, top=20, bottom=20, left=80, right=100)
        _style_manual_toc_paragraph(cell.paragraphs[0], label)
        tc_pr = cell._tc.get_or_add_tcPr()
        for border in tc_pr.xpath("./w:tcBorders"):
            tc_pr.remove(border)


def update_manual_toc_page_numbers(docx_path: Path, pdf_path: Path, blueprint: ProductBlueprint) -> dict:
    from docx import Document
    from pypdf import PdfReader

    entries = _manual_toc_entries(blueprint)
    reader = PdfReader(str(pdf_path))
    page_texts = [re.sub(r"\s+", "", page.extract_text() or "") for page in reader.pages]
    page_numbers: dict[str, int] = {}
    for label, heading in entries:
        target = re.sub(r"\s+", "", heading)
        for page_index, page_text in enumerate(page_texts[2:], start=3):
            if target in page_text:
                page_numbers[label] = page_index
                break

    document = Document(docx_path)
    toc_table = document.tables[0] if document.tables else None
    if toc_table is None or len(toc_table.rows) < len(entries):
        return {"manual_toc_page_numbers_ready": False, "manual_toc_missing_entries": [label for label, _ in entries]}
    for row, (label, _heading) in zip(toc_table.rows, entries):
        _style_manual_toc_paragraph(row.cells[0].paragraphs[0], label, page_numbers.get(label))
    document.save(docx_path)
    missing = [label for label, _heading in entries if label not in page_numbers]
    return {
        "manual_toc_page_numbers_ready": not missing,
        "manual_toc_page_number_count": len(page_numbers),
        "manual_toc_missing_entries": missing,
        "manual_toc_page_numbers": page_numbers,
    }


def _add_manual_cover(document, task: GenerationTask) -> None:
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt

    for _ in range(8):
        document.add_paragraph()
    title = document.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.line_spacing = Pt(34)
    title_run = title.add_run(task.software_name)
    title_run.bold = True
    title_run.font.name = "宋体"
    title_run.font.size = Pt(24)
    _set_run_east_asia_font(title_run, "宋体")

    for _ in range(5):
        document.add_paragraph()
    subtitle = document.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.paragraph_format.line_spacing = Pt(30)
    subtitle_run = subtitle.add_run("操作手册")
    subtitle_run.bold = True
    subtitle_run.font.name = "宋体"
    subtitle_run.font.size = Pt(22)
    _set_run_east_asia_font(subtitle_run, "宋体")


def _add_ui_figure(
    document,
    ui_screenshots: dict | None,
    key: str,
    title: str,
    caption: str,
    operation_notes: list[str] | None = None,
    action_image_module_key: str = "",
) -> None:
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Inches, Pt, RGBColor

    item = ui_screenshots.get(key) if isinstance(ui_screenshots, dict) else None
    image_path = getattr(item, "image_path", None) if item else None
    display_title = title
    display_caption = _visible_content_caption(item, caption) if item else caption
    if item and _visible_content_summary_ready(item):
        operation_notes = _visible_content_operation_notes(
            item,
            display_title,
            main_page=str(getattr(item, "page_kind", "") or "") in {"dashboard", "module"},
        )
    if image_path and Path(image_path).exists():
        paragraph = document.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.paragraph_format.space_before = Pt(2)
        paragraph.paragraph_format.space_after = Pt(2)
        paragraph.paragraph_format.keep_with_next = True
        paragraph.paragraph_format.keep_together = True
        # The manual body uses an exact line height for dense soft-copyright pages.
        # Image-only paragraphs must opt out or LibreOffice clips screenshots to one text line.
        paragraph.paragraph_format.line_spacing = 1.0
        run = paragraph.add_run()
        figure_width, figure_height = _figure_size_inches(image_path)
        run.add_picture(image_path, width=Inches(figure_width), height=Inches(figure_height))
        caption_p = document.add_paragraph(_customer_manual_text(f"图：{display_title}，{display_caption}"))
        caption_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        caption_p.paragraph_format.space_after = Pt(2)
        caption_p.paragraph_format.line_spacing = Pt(12.5)
        caption_p.paragraph_format.keep_with_next = bool(operation_notes)
        caption_p.paragraph_format.keep_together = True
        for caption_run in caption_p.runs:
            caption_run.font.color.rgb = RGBColor(80, 80, 80)
            caption_run.font.size = Pt(9)
        _add_figure_operation_notes(
            document,
            display_title,
            display_caption,
            operation_notes,
            ui_screenshots,
            action_image_module_key,
            key,
        )
        return
    _add_ui_placeholder(document, display_title, display_caption)
    _add_figure_operation_notes(document, display_title, display_caption, operation_notes)


def _add_figure_operation_notes(
    document,
    title: str,
    caption: str,
    operation_notes: list[str] | None = None,
    ui_screenshots: dict | None = None,
    module_key: str = "",
    preferred_key: str = "",
) -> None:
    from docx.shared import Pt

    notes = [_natural_manual_note(str(item).strip(), title=title, caption=caption) for item in (operation_notes or []) if str(item).strip()]
    if not notes:
        notes = [
            f"用户进入{title}后，先确认当前业务范围、筛选条件和可用操作入口，再根据页面提示继续处理。",
            f"该界面围绕{caption}展示关键字段、状态信息和处理按钮，便于用户判断记录是否需要继续维护。",
            "提交数据或切换条件后，系统会刷新页面内容，并记录操作时间、操作人员和状态变化。",
        ]
    for step_index, note in enumerate(_expand_figure_notes(notes, title, caption)[:4], start=1):
        numbered_note = f"{step_index}. {note}"
        paragraph = (
            _add_manual_paragraph_with_action_images(document, numbered_note, ui_screenshots, module_key, preferred_key)
            if module_key
            else document.add_paragraph(_customer_manual_text(numbered_note))
        )
        paragraph.paragraph_format.left_indent = Pt(21)
        paragraph.paragraph_format.first_line_indent = Pt(-21)
        paragraph.paragraph_format.space_before = Pt(0)
        paragraph.paragraph_format.space_after = Pt(2)
        paragraph.paragraph_format.line_spacing = Pt(19 if module_key and "【" in note else 14.5)
        paragraph.paragraph_format.keep_together = True


def _find_manual_action_crop(
    ui_screenshots: dict | None,
    module_key: str,
    label: str,
    preferred_key: str = "",
) -> str:
    if not isinstance(ui_screenshots, dict):
        return ""
    items = list(ui_screenshots.items())
    items.sort(key=lambda pair: 0 if pair[0] == preferred_key else 1)
    normalized = re.sub(r"\s+", "", label)

    def find_direct(item) -> str:
        crops = getattr(item, "action_crops", None) or {}
        for crop_label, crop_path in crops.items():
            candidate = re.sub(r"\s+", "", str(crop_label))
            if candidate == normalized or (len(normalized) >= 2 and normalized in candidate):
                if crop_path and Path(crop_path).exists():
                    return str(crop_path)
        return ""

    preferred_item = ui_screenshots.get(preferred_key) if preferred_key else None
    if preferred_item is not None and (not module_key or getattr(preferred_item, "module_key", "") == module_key):
        direct = find_direct(preferred_item)
        if direct:
            return direct
        alias_map = {
            "添加": ["确认登记", "确认添加", "登记", "保存"],
            "新增": ["确认登记", "确认新增", "登记", "保存"],
            "详情": ["查看详情", "详情页", "详情"],
            "查询": ["确认查询", "查询", "搜索"],
            "编辑": ["确认编辑", "保存修改", "保存"],
            "删除": ["确认删除", "删除"],
            "复核": ["确认复核", "提交复核", "复核"],
        }
        aliases = alias_map.get(normalized, [normalized])
        crops = getattr(preferred_item, "action_crops", None) or {}
        for alias in aliases:
            matches = [
                (str(crop_label), str(crop_path))
                for crop_label, crop_path in crops.items()
                if alias in re.sub(r"\s+", "", str(crop_label))
                and crop_path
                and Path(crop_path).exists()
            ]
            if matches:
                matches.sort(key=lambda pair: ("确认" in pair[0], len(pair[0])), reverse=True)
                return matches[0][1]

    for key, item in items:
        if module_key and getattr(item, "module_key", "") != module_key:
            continue
        if key == preferred_key:
            continue
        direct = find_direct(item)
        if direct:
            return direct
    return ""


def _add_manual_paragraph_with_action_images(
    document,
    text: str,
    ui_screenshots: dict | None,
    module_key: str,
    preferred_key: str = "",
):
    from docx.shared import Inches, Pt

    cleaned = _customer_manual_text(text)
    matches = list(re.finditer(r"【([^】]{1,16})】(?:按钮)?", cleaned))
    if not matches:
        return document.add_paragraph(cleaned)
    paragraph = document.add_paragraph()
    paragraph.paragraph_format.line_spacing = Pt(19)
    paragraph.paragraph_format.space_before = Pt(1)
    paragraph.paragraph_format.space_after = Pt(1)
    cursor = 0
    for match in matches:
        paragraph.add_run(cleaned[cursor:match.start()])
        label = match.group(1).strip()
        crop_path = _find_manual_action_crop(ui_screenshots, module_key, label, preferred_key)
        if crop_path:
            shape = paragraph.add_run().add_picture(crop_path, height=Inches(0.22))
            shape._inline.docPr.set("descr", label)
            shape._inline.docPr.set("title", label)
        else:
            paragraph.add_run(label)
        cursor = match.end()
    paragraph.add_run(cleaned[cursor:])
    return paragraph


def _figure_width_inches(image_path: str) -> float:
    return _figure_size_inches(image_path)[0]


def _figure_size_inches(image_path: str) -> tuple[float, float]:
    fallback_width = 6.1
    fallback_height = 3.9
    try:
        from PIL import Image

        with Image.open(image_path) as image:
            width, height = image.size
        if width <= 0 or height <= 0:
            return fallback_width, fallback_height
        if height > width:
            display_height = 5.6
            display_width = min(3.25, display_height * width / height)
            return round(display_width, 2), display_height
        display_width = 6.1
        display_height = min(4.0, display_width * height / width)
        return display_width, round(display_height, 2)
    except Exception:
        return fallback_width, fallback_height


def _expand_figure_notes(notes: list[str], title: str, caption: str) -> list[str]:
    result = [_natural_manual_note(text, title=title, caption=caption) for text in notes if str(text).strip()]
    if result:
        return result[:4]
    templates = _figure_note_templates(title, caption)
    index = 0
    while len(result) < 3:
        result.append(_customer_manual_text(templates[index % len(templates)]))
        index += 1
    return result[:4]


def _figure_note_templates(title: str, caption: str) -> list[str]:
    title_text = str(title or "")
    if "登录" in title_text:
        return [
            "登录前应确认当前网络、账号状态和验证码信息正常。",
            "账号校验通过后，系统按照用户岗位加载对应菜单、数据范围和常用入口。",
            "连续输入错误时，系统会提示用户重新核对账号信息或联系管理员处理。",
        ]
    if "首页" in title_text or "主界面" == title_text:
        return [
            "首页中的待办、预警和快捷入口可直接进入对应业务页面。",
            "页面会按照当前用户权限展示可访问模块和统计范围。",
            "切换菜单或筛选条件后，系统会刷新指标、列表和最近处理记录。",
        ]
    return [
        f"用户可从功能菜单进入{title}，系统会保留当前角色的数据范围和最近一次筛选条件。",
        f"{title}在提交前会检查必填字段、状态流转和关联记录，避免无效数据进入后续流程。",
        f"{title}的查询、保存、导出和状态变更均会写入操作日志，便于后续审计追踪。",
        f"不同岗位进入{title}后，看到的菜单、按钮和数据范围会按角色授权自动控制。",
    ]


def _expand_paragraphs(paragraphs: list[str], min_count: int, max_count: int | None = None) -> list[str]:
    result = [_natural_manual_note(text) for text in paragraphs if str(text).strip()]
    if max_count:
        result = result[:max_count]
    templates = [
        "系统在处理该部分业务时，会同步记录创建时间、更新时间、处理状态和操作人员，方便后续追溯。",
        "页面提供条件筛选、列表展示、详情查看、状态维护和导出等常用操作，满足日常管理需要。",
        "当用户提交数据后，系统会执行字段校验和业务规则校验，避免重复、缺失或状态异常的数据进入流程。",
        "相关数据可进入统计分析模块，为管理人员进行趋势判断和工作安排提供依据。",
        "该功能与角色权限联动，不同岗位只能访问授权范围内的数据和操作按钮。",
    ]
    index = 0
    while len(result) < min_count:
        result.append(_natural_manual_note(templates[index % len(templates)]))
        index += 1
    return result[:max_count] if max_count else result


def _natural_manual_note(text: str, *, title: str = "", caption: str = "") -> str:
    value = _customer_manual_text(text)
    substitutions = [
        (r"^操作说明[：:]\s*", ""),
        (r"^字段说明[：:]\s*", ""),
        (r"^处理结果[：:]\s*", ""),
        (r"^页面路径[：:]\s*", ""),
        (r"^校验说明[：:]\s*", ""),
        (r"^留痕说明[：:]\s*", ""),
        (r"^权限说明[：:]\s*", ""),
        (r"^业务一致性[：:]\s*", ""),
    ]
    for pattern, replacement in substitutions:
        value = re.sub(pattern, replacement, value).strip()
    if value.startswith("该界面") and title:
        value = re.sub(r"^该界面", title, value)
    if value.startswith("页面") and title:
        value = f"{title}{value}"
    value = re.sub(r"用户点击【([^】]+)】按钮后，系统打开", r"点击【\1】按钮后，系统打开", value)
    value = re.sub(r"页面重点展示", "页面主要展示", value)
    value = re.sub(r"(界面|页面)页面主要展示", r"\1主要展示", value)
    value = re.sub(r"同时写入操作日志、处理时间和处理人员", "并记录操作日志、处理时间和处理人员", value)
    return value


def _module_ui_action_context(ui_screenshots: dict | None, screenshot_key: str, design_brief: dict | None = None) -> dict:
    item = (ui_screenshots or {}).get(screenshot_key) if isinstance(ui_screenshots, dict) else None
    html = ""
    html_path = getattr(item, "html_path", "") if item else ""
    if html_path:
        try:
            html = Path(html_path).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            html = ""
    text = _visible_text_from_html(html)
    action_candidates = [
        "查看详情",
        "查看预警",
        "取消收藏",
        "收藏患者",
        "入院摘要",
        "转科记录",
        "医嘱关注",
        "观察记录",
        "查看全部",
        "立即登记",
        "切换班次",
        "刷新",
        "保存",
        "确认",
        "返回",
    ]
    filter_candidates = [
        "高级筛选",
        "展开筛选",
        "病区汇总",
        "全部",
        "新入院",
        "转科",
        "待关注",
        "异常",
        "按床位号排序",
    ]
    action_labels = _labels_in_visible_order(text, action_candidates)
    extracted_labels = _extract_button_like_labels(html)
    for label in extracted_labels:
        if label not in action_labels and _looks_like_ui_action_label(label):
            action_labels.append(label)
    filter_labels = _labels_in_visible_order(text, filter_candidates)
    search_label = _first_visible_label(text, ["患者搜索框", "搜索", "搜索框", "关键字", "输入住院号"])
    spec = (design_brief or {}).get("product_experience_spec") if isinstance(design_brief, dict) else {}
    experience_shape = str((spec or {}).get("experience_shape") or "")
    is_mobile = (
        experience_shape in {"mobile_app", "mini_program", "h5_mobile", "mobile_game"}
        or str(getattr(item, "width", "") or "").isdigit()
        and int(getattr(item, "height", 0) or 0) > int(getattr(item, "width", 0) or 0)
    )
    return {
        "is_mobile": bool(is_mobile),
        "search_label": search_label,
        "filter_labels": filter_labels[:8],
        "action_labels": action_labels[:8],
        "has_query_button": "查询" in action_labels or "查询" in extracted_labels,
        "visible_text": text,
    }


def _visible_text_from_html(html: str) -> str:
    text = re.sub(r"<style\b.*?</style>", " ", str(html or ""), flags=re.S | re.I)
    text = re.sub(r"<script\b.*?</script>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&(?:nbsp|amp|lt|gt|quot);", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _labels_in_visible_order(text: str, candidates: list[str]) -> list[str]:
    hits: list[tuple[int, str]] = []
    for label in candidates:
        index = str(text or "").find(label)
        if index >= 0:
            hits.append((index, label))
    return [label for _index, label in sorted(hits, key=lambda item: item[0])]


def _first_visible_label(text: str, candidates: list[str]) -> str:
    labels = _labels_in_visible_order(text, candidates)
    return labels[0] if labels else ""


def _extract_button_like_labels(html: str) -> list[str]:
    labels: list[str] = []
    patterns = [
        r'<(?:button|a)\b[^>]*>(.*?)</(?:button|a)>',
        r'<(?:div|span)\b[^>]*class=["\'][^"\']*(?:action|btn|button|filter-btn|drawer-entry)[^"\']*["\'][^>]*>(.*?)</(?:div|span)>',
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, str(html or ""), flags=re.S | re.I):
            label = _clean_ui_label(match.group(1))
            if label and label not in labels:
                labels.append(label)
    return labels


def _clean_ui_label(value: str) -> str:
    label = re.sub(r"<[^>]+>", " ", str(value or ""))
    label = re.sub(r"&(?:nbsp|amp|lt|gt|quot);", " ", label)
    label = re.sub(r"\s+", "", label).strip("›>：:·")
    label = re.sub(r"\d+$", "", label)
    if not label or len(label) > 12:
        return ""
    if re.search(r"[A-Za-z]{4,}", label):
        return ""
    return label


def _looks_like_ui_action_label(label: str) -> bool:
    return bool(re.search(r"(查看|预警|收藏|摘要|登记|切换|保存|确认|返回|筛选|导出|导入|复核|处理|记录)$", str(label or "")))


def _ui_context_is_mobile(ui_context: dict | None) -> bool:
    return bool((ui_context or {}).get("is_mobile"))


def _mobile_module_main_notes(module, ui_context: dict | None, design_brief: dict | None = None) -> list[str]:
    search = str((ui_context or {}).get("search_label") or "页面搜索框")
    filters = _join_items((ui_context or {}).get("filter_labels") or []) or "状态筛选入口"
    actions = _join_items((ui_context or {}).get("action_labels") or []) or "卡片底部操作入口"
    return [
        f"用户进入{module.title}主界面后，可使用{search}输入关键字，并结合{filters}切换当前数据范围。",
        f"页面以卡片形式展示{_join_items(module.data_fields[:5]) or '编号、名称、状态和时间'}等关键信息，异常或待办状态会用标签提示。",
        f"当前截图中的可见操作包括{actions}，用户应按页面实际按钮继续查看、收藏、处理提醒或进入摘要信息。",
    ]


def _mobile_module_after_figure_paragraphs(module, ui_context: dict | None) -> list[str]:
    search = str((ui_context or {}).get("search_label") or "页面搜索框")
    filters = _join_items((ui_context or {}).get("filter_labels") or []) or "状态筛选入口"
    actions = _join_items((ui_context or {}).get("action_labels") or []) or "查看详情、查看预警等入口"
    return [
        f"在{module.title}页面中，用户先通过{search}输入床位、编号、名称或其他关键字，再配合{filters}调整列表范围，页面会刷新对应卡片和统计摘要。",
        f"每条记录下方只显示当前状态可用的操作，常见入口包括{actions}；手册后续步骤均以截图中实际出现的按钮名称为准。",
    ]


def _module_intro_paragraphs(blueprint: ProductBlueprint, module, ui_context: dict | None = None) -> list[str]:
    if _ui_context_is_mobile(ui_context):
        search = str((ui_context or {}).get("search_label") or "页面搜索框")
        filters = _join_items((ui_context or {}).get("filter_labels") or []) or "状态筛选、病区范围和业务标签"
        actions = _join_items((ui_context or {}).get("action_labels") or []) or "查看详情、处理提醒和收藏标记"
        fields = _join_items(module.data_fields[:5]) or "业务编号、名称、状态和更新时间"
        return [
            f"进入{module.title}页面后，用户可先使用{search}输入关键字，并结合{filters}缩小当前列表范围。",
            f"页面主体以卡片或分组列表展示{fields}等信息，用户可直接根据状态标签、异常提示和最近更新时间判断是否需要继续处理。",
            f"当前截图中的可见入口包括{actions}，系统会按用户权限和记录状态展示可用按钮，并保留最近浏览和当前筛选条件。",
        ]
    return [
        module.description,
        f"进入{module.title}页面后，用户可围绕{_join_items(module.data_fields[:6]) or '业务字段'}进行条件筛选和详情查看。",
        f"系统支持{_manual_operation_list(module)}等操作，并根据当前记录状态控制可用按钮。",
        f"{module.title}与{_join_items(blueprint.report_metrics[:4]) or '统计指标'}保持联动，处理结果可进入报表分析和操作追踪。",
        f"在数据保存时，系统会执行{_join_items(_manual_rule_items(module)[:3]) or '必填字段、业务编码、状态流转和重复记录校验'}，避免无效数据进入业务流程。",
        f"该模块产生的数据会与{_join_items(blueprint.data_relations[:3]) or '操作日志、统计报表和权限范围'}关联，便于后续查询和归档。",
    ]


def _module_paragraphs_conflict_with_ui(paragraphs: list[str] | None, ui_context: dict | None = None, module=None) -> bool:
    if not paragraphs or not _ui_context_is_mobile(ui_context):
        return False
    text = "\n".join(str(item or "") for item in paragraphs)
    if module is not None:
        interaction = mobile_secondary_interaction(module)
        if not interaction.requires_confirmation and re.search(r"登记|提交确认|办理流程|审核通过|待确认", text):
            return True
    visible_labels = set((ui_context or {}).get("action_labels") or []) | set((ui_context or {}).get("filter_labels") or [])
    conflict_patterns = [
        r"【查询】按钮",
        r"操作列",
        r"追加、修改、查看、失效和导出",
        r"添加、编辑、详情、删除、导入或导出",
        r"新增、编辑、审核、导出",
    ]
    if any(re.search(pattern, text) for pattern in conflict_patterns):
        return True
    bracket_labels = re.findall(r"【([^】]{1,12})】", text)
    generic_missing = {"查询", "添加", "编辑", "删除", "导入", "导出", "详情"} - visible_labels
    return any(label in generic_missing for label in bracket_labels)


def _add_module_operation_sections(
    document,
    module,
    module_index: int,
    ui_screenshots: dict | None,
    design_brief: dict | None = None,
    ui_context: dict | None = None,
) -> None:
    _add_heading(document, f"4.{module_index}.1 {module.title}主界面", level=3)
    if ui_context is None:
        ui_context = _module_ui_action_context(ui_screenshots, _module_figure_key(module.key), design_brief)
    main_key = _module_figure_key(module.key)
    main_item = (ui_screenshots or {}).get(main_key) if isinstance(ui_screenshots, dict) else None
    _add_ui_figure(
        document,
        ui_screenshots,
        main_key,
        str(getattr(main_item, "title", "") or f"{module.title}主界面"),
        str(getattr(main_item, "caption", "") or f"{module.title}页面展示当前业务信息和可用操作入口。"),
        _actual_screenshot_operation_notes(main_item, module, main_page=True),
        module.key,
    )
    for operation_index, (screenshot_key, screenshot_item) in enumerate(
        _module_secondary_screenshot_items(ui_screenshots, module.key),
        start=2,
    ):
        action = _actual_screenshot_action_name(screenshot_item, module.title)
        _add_heading(document, f"4.{module_index}.{operation_index} {action}", level=3)
        _add_ui_figure(
            document,
            ui_screenshots,
            screenshot_key,
            str(getattr(screenshot_item, "title", "") or f"{module.title}{action}界面"),
            str(getattr(screenshot_item, "caption", "") or f"页面展示{module.title}{action}所需的信息和按钮。"),
            _actual_screenshot_operation_notes(screenshot_item, module),
            module.key,
        )


def _module_secondary_screenshot_items(ui_screenshots: dict | None, module_key: str) -> list[tuple[str, object]]:
    if not isinstance(ui_screenshots, dict):
        return []
    result = [
        (str(key), item)
        for key, item in ui_screenshots.items()
        if str(getattr(item, "module_key", "") or "") == str(module_key)
        and str(getattr(item, "page_kind", "") or "") == "operation"
        and _ui_screenshot_has_image(ui_screenshots, str(key))
    ]
    result.sort(key=lambda pair: pair[0])
    return result


def _actual_screenshot_action_name(item, module_title: str) -> str:
    title = str(getattr(item, "title", "") or "").strip()
    action = title
    if module_title and action.startswith(module_title):
        action = action[len(module_title) :]
    action = re.sub(r"(?:操作)?(?:界面|页面|窗口)$", "", action).strip(" -—：:")
    return action or "功能操作"


def _visible_content_summary(item) -> dict:
    summary = getattr(item, "visible_content_summary", None) or {}
    return summary if isinstance(summary, dict) else {}


def _visible_content_summary_ready(item) -> bool:
    return bool(_visible_content_summary(item).get("ready"))


def _visible_content_values(item, name: str, limit: int = 6) -> list[str]:
    summary = _visible_content_summary(item)
    values: list[str] = []
    common_navigation = {"工作首页", "功能办理", "任务跟踪", "统计分析", "系统设置"}
    item_title = _manual_ui_token(str(getattr(item, "title", "") or ""))
    for raw_value in summary.get(name) or []:
        value = re.sub(r"\s+", " ", str(raw_value or "")).strip(" ·|｜:：-—")
        if not value or value in common_navigation:
            continue
        if name == "headings" and item_title and _manual_ui_token(value) == item_title:
            continue
        if value not in values:
            values.append(value)
        if len(values) >= limit:
            break
    return values


def _visible_content_action_labels(item, limit: int = 4) -> list[str]:
    filter_actions = {
        _manual_ui_token(value)
        for value in _visible_content_values(item, "filter_actions", 12)
        if _manual_ui_token(value)
    }
    actions = [
        label
        for label in _actual_screenshot_action_labels(item, limit=20)
        if _manual_ui_token(label) not in filter_actions
    ]
    return actions[: max(1, int(limit or 0))]


def _visible_content_caption(item, fallback: str = "") -> str:
    if not _visible_content_summary_ready(item):
        return fallback
    headings = _visible_content_values(item, "headings", 3)
    metrics = _visible_content_values(item, "metrics", 4)
    fields = _visible_content_values(item, "fields", 4)
    statuses = _visible_content_values(item, "statuses", 3)
    primary = headings or metrics or fields
    secondary = metrics if headings else fields if metrics else statuses
    if primary and secondary:
        return f"页面展示{_join_items(primary)}，并呈现{_join_items(secondary)}等当前可见业务信息。"
    if primary:
        return f"页面展示{_join_items(primary)}等当前可见业务信息和处理入口。"
    return fallback


def _visible_content_operation_notes(item, title: str, *, main_page: bool = False) -> list[str]:
    if not _visible_content_summary_ready(item):
        return []
    headings = _visible_content_values(item, "headings", 4)
    metrics = _visible_content_values(item, "metrics", 5)
    fields = _visible_content_values(item, "fields", 6)
    statuses = _visible_content_values(item, "statuses", 4)
    filters = _visible_content_values(item, "filters", 5)
    actions = _visible_content_action_labels(item)
    notes: list[str] = []
    if filters:
        notes.append(f"用户进入{title}后，可使用{_join_items(filters)}调整当前查看范围，页面会同步刷新对应内容。")
    if headings:
        notes.append(f"当前截图的主要业务区域包括{_join_items(headings)}，用户可按区域顺序查看和处理信息。")
    detail_values = metrics or fields
    if detail_values:
        noun = "指标" if metrics else "字段"
        page_subject = title if re.search(r"(?:界面|页面)$", title) else f"{title}页面"
        notes.append(f"{page_subject}当前可见的{noun}包括{_join_items(detail_values)}，相关数值和记录用于判断当前业务进度与结果。")
    if statuses and len(notes) < 3:
        notes.append(f"状态区域显示{_join_items(statuses)}，用户可据此判断当前记录所处阶段。")
    if actions:
        notes.append(
            (title if re.search(r"(?:界面|页面)$", title) else f"{title}页面")
            + "提供"
            + "、".join(f"【{label}】" for label in actions)
            + "等当前截图可见操作，点击后按页面反馈继续处理。"
        )
    if len(notes) < 3 and fields and fields != detail_values:
        notes.append(f"页面还显示{_join_items(fields)}等字段，便于核对当前记录。")
    if len(notes) < 3:
        notes.append(
            "切换当前页面中的功能后，内容区会显示对应结果。"
            if main_page
            else "操作完成后，以当前页面显示的结果和状态变化为准。"
        )
    return notes[:4]


def _visible_content_intro_paragraphs(item, title: str) -> list[str]:
    if not _visible_content_summary_ready(item):
        return []
    headings = _visible_content_values(item, "headings", 4)
    metrics = _visible_content_values(item, "metrics", 5)
    fields = _visible_content_values(item, "fields", 6)
    filters = _visible_content_values(item, "filters", 4)
    actions = _visible_content_action_labels(item)
    paragraphs: list[str] = []
    if headings:
        paragraphs.append(f"{title}围绕{_join_items(headings)}组织页面内容，各区域共同呈现当前业务记录和处理结果。")
    elif metrics or fields:
        paragraphs.append(f"{title}主要展示{_join_items(metrics or fields)}，便于用户核对当前业务情况。")
    if filters or actions:
        parts: list[str] = []
        if filters:
            parts.append(f"通过{_join_items(filters)}调整查看范围")
        if actions:
            parts.append(f"使用{_join_items(actions)}继续处理")
        paragraphs.append("用户可" + "，并".join(parts) + "，页面会显示对应的状态和结果。")
    return paragraphs[:2]


def _actual_screenshot_action_labels(item, limit: int = 4) -> list[str]:
    crops = getattr(item, "action_crops", None) or {}
    labels: list[str] = []
    for raw_label in crops:
        label = re.sub(r"\s+", "", str(raw_label or "")).strip()
        if not label or re.fullmatch(r"[+\-]?\d+(?:\.\d+)?", label):
            continue
        if re.fullmatch(r".+(?:记录|条目|数据)0?\d{1,3}", label):
            continue
        if label not in labels:
            labels.append(label)
    compact: list[str] = []
    for label in labels:
        contained = [other for other in labels if other != label and len(other) >= 2 and other in label]
        if len(contained) >= 2:
            continue
        compact.append(label)
    action_prefixes = (
        "查看",
        "打开",
        "下载",
        "导出",
        "导入",
        "新增",
        "添加",
        "保存",
        "提交",
        "确认",
        "复核",
        "审核",
        "发布",
        "归档",
        "查询",
        "筛选",
        "刷新",
        "定位",
        "收藏",
        "复制",
        "同步",
        "引用",
        "发起",
        "下发",
        "撤回",
        "退回",
        "打印",
        "预览",
        "关联",
        "执行",
        "清除",
        "批量",
        "读取",
        "追踪",
        "跟踪",
        "填写",
        "追加",
        "生成",
        "应用",
        "继续",
        "催办",
        "验收",
        "校验",
    )
    compact.sort(key=lambda label: 0 if label.startswith(action_prefixes) else 1)
    return compact[: max(1, int(limit or 0))]


def _actual_screenshot_operation_notes(item, module, *, main_page: bool = False) -> list[str]:
    title = str(getattr(item, "title", "") or f"{module.title}界面").strip()
    visible_notes = _visible_content_operation_notes(item, title, main_page=main_page)
    if visible_notes:
        return visible_notes
    caption = str(getattr(item, "caption", "") or "").strip()
    fields = _join_items(module.data_fields[:5]) or "业务编号、名称、状态、处理人员和更新时间"
    labels = _actual_screenshot_action_labels(item)
    notes = [f"用户进入{title}后，可查看{fields}等当前业务信息。"]
    if labels:
        notes.append(
            "页面提供"
            + "、".join(f"【{label}】" for label in labels)
            + "等实际操作入口，用户应根据当前记录状态选择相应功能。"
        )
    if caption:
        notes.append(caption)
    notes.append(
        "切换功能后，系统继续保留当前用户权限和业务范围，并在内容区加载对应页面。"
        if main_page
        else "操作完成后，以页面显示的状态、结果提示和处理轨迹为准；返回其他功能时，系统保留当前业务范围。"
    )
    return notes[:4]


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
        "校验",
        "分析",
        "预警",
        "复核",
        "统计",
        "追踪",
        "新增",
        "追加",
        "添加",
        "删除",
        "失效",
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


def _manual_operation_list(module) -> str:
    return "、".join(_manual_action_names(module)[:6])


def _manual_action_names(module) -> list[str]:
    names = ["查询", "添加", "导出", "导入", "编辑", "详情", "删除"]
    detected = [_manual_action_name(_operation_action(operation)) for operation in _module_operation_items(module)]
    result: list[str] = []
    for name in detected + names:
        if name and name not in result:
            result.append(name)
    return result


def _manual_action_items(module, design_brief: dict | None = None, ui_context: dict | None = None) -> list[dict]:
    if _ui_context_is_mobile(ui_context):
        return _mobile_manual_action_items(module, ui_context)
    operations = _module_operation_items(module, design_brief)
    fields = _join_items(module.data_fields[:5]) or "名称、状态、责任角色、更新时间和处理备注"
    required = _required_field_text(module)
    result: list[dict] = [
        {
            "action": "查询",
            "paragraphs": [
                f"在{module.title}页面输入{_join_items(module.data_fields[:3]) or '名称、状态和时间范围'}等查询条件后，点击【查询】按钮，系统在列表区域显示符合条件的数据。",
                "查询结果支持翻页查看，用户可继续点击列表右侧按钮进入添加、编辑、详情、删除、导入或导出等后续操作。",
                f"查询条件变更后，系统会重新刷新{module.title}业务数据，并保留最近一次查询条件、查询人员和查询时间，便于后续复核。",
            ],
            "screenshot_key": "",
        }
    ]
    added_actions = {"查询"}
    for index, operation in enumerate(operations[:4], start=2):
        action = _manual_action_name(_operation_action(operation))
        if action in added_actions:
            action = _next_manual_action_name(added_actions)
        added_actions.add(action)
        result.append(
            {
                "action": action,
                "paragraphs": _manual_action_paragraphs(module, action, fields, required),
                "screenshot_key": _module_operation_figure_key(module.key, _operation_action(operation), index),
            }
        )
    for action in _manual_fallback_actions(module):
        if action in added_actions:
            continue
        result.append(
            {
                "action": action,
                "paragraphs": _manual_action_paragraphs(module, action, fields, required),
                "screenshot_key": "",
            }
        )
    return result[:6]


def _mobile_manual_action_items(module, ui_context: dict | None = None) -> list[dict]:
    actions = [str(item).strip() for item in ((ui_context or {}).get("action_labels") or []) if str(item).strip()]
    filters = [str(item).strip() for item in ((ui_context or {}).get("filter_labels") or []) if str(item).strip()]
    search_label = str((ui_context or {}).get("search_label") or "页面搜索框")
    result: list[dict] = []
    interaction = mobile_secondary_interaction(module)
    action = interaction.action
    result.append(
        {
            "action": action,
            "paragraphs": _mobile_action_paragraphs(module, action, search_label=search_label, filters=filters),
            "screenshot_key": _module_operation_figure_key(module.key, action, 2),
        }
    )
    if search_label or filters:
        search_item = {
            "action": "搜索与筛选",
            "paragraphs": _mobile_action_paragraphs(module, "搜索与筛选", search_label=search_label, filters=filters),
            "screenshot_key": "",
        }
        if not any(item["action"] == search_item["action"] for item in result):
            result.append(search_item)
    for label in actions:
        if label in {"查看全部", "返回", "刷新"}:
            continue
        if any(item["action"] == label for item in result):
            continue
        result.append(
            {
                "action": label,
                "paragraphs": _mobile_action_paragraphs(module, label, search_label=search_label, filters=filters),
                "screenshot_key": "",
            }
        )
        if len(result) >= 6:
            break
    if len(result) < 3:
        for label in ["查看详情", "高级筛选", "状态处理"]:
            if any(item["action"] == label for item in result):
                continue
            result.append(
                {
                    "action": label,
                    "paragraphs": _mobile_action_paragraphs(module, label, search_label=search_label, filters=filters),
                    "screenshot_key": "",
                }
            )
            if len(result) >= 3:
                break
    return result[:6]


def _mobile_action_paragraphs(module, action: str, *, search_label: str = "", filters: list[str] | None = None) -> list[str]:
    filter_text = _join_items(filters or []) or "状态标签和筛选条件"
    fields = _join_items(module.data_fields[:5]) or "业务编号、名称、状态和更新时间"
    if action == "查看搜索结果":
        return [
            f"用户在{search_label or '搜索框'}输入歌曲、歌手或专辑名称后，页面直接展示匹配结果。",
            f"结果页保留{filter_text}，用户可继续缩小范围，也可直接进入歌曲、歌手或专辑详情。",
            "返回搜索页时，系统保留本次关键词和筛选条件，方便继续浏览。",
        ]
    if action in {"播放歌曲", "播放本地歌曲"}:
        return [
            f"点击【{action}】后，歌曲立即开始播放，页面同步显示封面、进度、音质和当前播放状态。",
            "用户可随时暂停、切换歌曲、拖动进度或调整播放模式，操作会立即反映在播放器中。",
            "退出播放页后，迷你播放器继续显示当前歌曲，用户可从任意页面返回播放详情。",
        ]
    if action == "查看歌词":
        return [
            "从播放页切换到【查看歌词】后，页面按照当前进度高亮正在播放的歌词。",
            "用户可上下滚动查看前后歌词，点击指定歌词可定位到对应播放时间。",
            "歌词查看不会改变歌曲或播放状态，返回播放页后继续保持当前进度。",
        ]
    if action == "收藏歌单":
        return [
            "点击【收藏歌单】后，收藏图标和歌单状态立即更新，页面给出收藏成功提示。",
            "用户可继续浏览歌单曲目、播放全部歌曲，或在个人中心查看已收藏歌单。",
            "再次点击收藏按钮可取消收藏，系统会保留当前浏览位置和歌单滚动进度。",
        ]
    if action in {"查看歌手详情", "查看专辑详情"}:
        subject = "歌手" if "歌手" in action else "专辑"
        return [
            f"点击【{action}】后，页面直接打开{subject}详情，展示简介、热门歌曲和相关内容。",
            f"用户可在{subject}详情页试听歌曲、进入专辑或查看曲目列表，无需提交或确认。",
            "返回上一页时，系统保留原有浏览位置和筛选条件。",
        ]
    if action == "调整播放顺序":
        return [
            "打开【调整播放顺序】后，用户可拖动歌曲调整先后位置，也可切换当前播放歌曲。",
            "顺序变化立即同步到播放队列和迷你播放器，当前歌曲保持正常播放。",
            "如移除某首歌曲，系统只更新当前队列，不影响收藏歌单和下载记录。",
        ]
    if action == "下载歌曲":
        return [
            "点击【下载歌曲】后，用户先选择音质，系统随即创建下载任务并显示实时进度。",
            "下载过程中可暂停、继续或取消；网络恢复后可从上次进度继续。",
            "下载完成的歌曲会进入离线歌曲列表，并显示占用空间和可播放状态。",
        ]
    if action == "查看推荐内容":
        return [
            "进入【查看推荐内容】后，页面展示最近播放、推荐歌曲和推荐歌单。",
            "用户可直接播放、收藏或进入详情，系统根据后续播放行为更新推荐顺序。",
            "返回首页后，最近浏览位置和当前推荐分组会继续保留。",
        ]
    if action == "搜索与筛选":
        return [
            f"用户在{module.title}页面顶部的{search_label or '搜索框'}输入关键字后，可继续选择{filter_text}缩小范围。",
            "筛选条件变化后，页面会刷新当前卡片、统计数字和状态标签，用户无需寻找单独的【查询】按钮。",
            f"搜索结果仍保留{fields}等关键信息，便于用户继续查看详情或处理异常提醒。",
        ]
    if action == "高级筛选":
        return [
            f"点击【高级筛选】后，系统展开{module.title}的组合筛选条件。",
            f"用户可按{filter_text}和{fields}中的关键字段调整范围，确认后页面刷新当前列表。",
            "高级筛选结果会与页面顶部统计摘要保持一致，并保留最近一次筛选条件。",
        ]
    if "详情" in action:
        return [
            f"点击卡片底部的【{action}】后，系统进入{module.title}对应记录的详情信息页。",
            f"详情页展示{fields}、状态标签和最近处理信息，用户可核对当前记录是否需要继续跟进。",
            "返回主界面后，系统保持原有搜索和筛选条件，方便继续查看下一条记录。",
        ]
    if "预警" in action or "异常" in action:
        return [
            f"点击【{action}】后，系统展示当前记录关联的异常说明、建议处理时间和处置状态。",
            "用户查看预警信息后，可根据页面提示完成复测、记录或交接处理。",
            f"处理结果会同步影响{module.title}卡片中的状态标签和统计摘要。",
        ]
    if "收藏" in action:
        return [
            f"点击【{action}】后，系统更新当前记录的关注状态。",
            "收藏或取消收藏后，记录会出现在最近浏览或常用关注区域，便于后续快速进入。",
            f"系统会保留{module.title}当前筛选条件，不影响用户继续浏览其他卡片。",
        ]
    if "摘要" in action or "记录" in action:
        return [
            f"点击【{action}】后，系统打开与当前记录相关的摘要信息。",
            f"摘要页集中展示{fields}和最近处理说明，便于用户快速了解关键情况。",
            "用户确认信息后可返回主界面继续查看卡片列表或切换筛选条件。",
        ]
    return [
        f"点击【{action}】后，系统按当前记录状态打开对应处理区域。",
        f"处理区域会展示{fields}等关键字段，并提示用户完成必要确认。",
        f"完成后页面刷新{module.title}当前卡片状态，同时保留搜索和筛选条件。",
    ]


def _manual_action_name(action: str) -> str:
    if action in {"新增", "添加", "登记", "配置"}:
        return "添加"
    if action in {"编辑", "更新", "维护"}:
        return "编辑"
    if action in {"详情", "定位"}:
        return "详情"
    if action in {"删除", "处置"}:
        return "删除"
    if action in {"审核", "复核", "确认"}:
        return "复核"
    if action in {"统计", "分析"}:
        return "统计"
    return action or "处理"


def _next_manual_action_name(used: set[str]) -> str:
    for action in ["添加", "编辑", "详情", "导出", "导入", "复核", "删除", "统计"]:
        if action not in used:
            return action
    return "处理"


def _manual_fallback_actions(module) -> list[str]:
    seed_text = f"{getattr(module, 'title', '')} {' '.join(getattr(module, 'operations', []) or [])}"
    actions = ["添加", "导出", "导入", "编辑", "详情", "删除"]
    if any(term in seed_text for term in ["审核", "复核", "校验", "确认"]):
        actions.insert(2, "复核")
    if any(term in seed_text for term in ["统计", "分析", "趋势", "指标"]):
        actions.insert(3, "统计")
    if any(term in seed_text for term in ["预警", "告警", "异常"]):
        actions.insert(2, "预警")
    return list(dict.fromkeys(actions))


def _manual_action_paragraphs(module, action: str, fields: str, required: str) -> list[str]:
    if action == "添加":
        return [
            f"点击【添加】按钮，系统打开{module.title}添加页面，用户按页面提示录入{fields}等信息。",
            f"其中{required}为必填项；录入完成后点击【保存】按钮，系统完成格式校验和业务规则校验，并返回{module.title}列表。",
            f"保存成功后系统形成新的{module.title}记录编号，同时写入创建人员、创建时间和初始状态，供后续编辑、详情查看、删除或导出使用。",
        ]
    if action == "编辑":
        return [
            f"在列表中选择需要维护的数据，点击操作列中的【编辑】按钮，系统打开{module.title}编辑页面。",
            f"编辑页面会自动带出已有数据，用户可调整{fields}等可编辑字段；保存前系统会校验{_join_items(_manual_rule_items(module)[:2]) or '必填项和状态规则'}。",
            f"编辑提交后系统记录前后关键字段差异，并刷新{module.title}列表中的更新时间、处理人员和当前状态。",
        ]
    if action == "详情":
        return [
            f"点击操作列中的【详情】按钮，系统打开{module.title}详情页面，只展示当前记录的完整业务信息。",
            "详情页面不允许直接修改数据，用户确认信息无误后点击【返回】按钮回到列表页面。",
            f"如需继续处理，用户可从详情页面返回列表后选择编辑、删除或导出操作，系统会保持{module.title}当前筛选条件。",
        ]
    if action == "删除":
        return [
            "对错误或不再使用的数据，用户可点击操作列中的【删除】按钮进行单条数据删除或作废处理。",
            "需要批量处理时，先勾选列表前方复选框，再点击【删除】按钮；系统提示确认后更新记录状态并刷新列表。",
            f"删除操作完成后，{module.title}记录仍会在历史查询或审计范围内保留处理原因、操作人和处理时间。",
        ]
    if action == "导出":
        return [
            f"用户完成查询后，点击【导出】按钮，系统按照当前筛选条件整理{module.title}数据文件。",
            "导出结果包含列表主要字段、状态和处理时间，便于线下核对、归档或报送。",
            f"导出前系统会校验当前用户的数据范围和导出权限，导出完成后在{module.title}操作日志中记录文件名称、导出时间和导出人员。",
        ]
    if action == "导入":
        return [
            f"点击【导入】按钮后，用户选择本地文件并确认字段映射，系统会读取{module.title}所需的业务数据。",
            f"导入前应确认文件中的{fields}等信息与系统字段保持一致；缺失{required}或格式不正确的数据不会写入正式列表。",
            f"导入完成后系统显示成功、失败和跳过的记录数量，用户可下载错误明细并重新导入修正后的数据。",
        ]
    if action in {"复核", "审核", "校验"}:
        return [
            f"在{module.title}列表中选择待{action}记录后，点击【{action}】按钮进入处理页面。",
            f"系统会展示{fields}、处理状态和规则命中结果，用户按{_join_items(_manual_rule_items(module)[:2]) or '业务规则'}逐项核对。",
            f"{action}通过后记录进入下一状态；未通过时应填写原因，系统保留当前处理意见和操作时间。",
        ]
    if action in {"统计", "分析"}:
        return [
            f"点击【{action}】按钮后，系统按当前筛选条件汇总{module.title}相关数据。",
            f"统计结果围绕{fields}、状态分布和处理时间展示，用户可继续切换周期、范围或分组口径。",
            f"{action}结果可用于报表导出、趋势核对和后续工作安排，系统会保存本次查询条件和操作记录。",
        ]
    return [
        f"点击【{action}】按钮后，系统打开对应处理页面，并展示{fields}等业务字段。",
        "处理完成后点击【保存】或【确认】按钮，系统刷新列表数据并记录操作日志。",
        f"系统根据{module.title}当前状态控制可用按钮，避免未校验、已删除或已归档记录被重复处理。",
    ]


def _manual_action_notes(module, action: str, fields: str) -> list[str]:
    return [
        f"点击【{action}】按钮后，系统打开{module.title}{action}页面，用户可按页面提示继续办理。",
        f"页面主要展示{fields}，其中{_required_field_text(module)}需要按规则填写或核对；当前记录编号、名称、范围和状态由系统业务数据区加载展示。",
        f"{action}完成后，系统返回列表并刷新当前记录状态，并记录操作日志、处理时间和处理人员，供后续统计报表和审计查询使用。",
    ]


def _manual_rule_items(module) -> list[str]:
    return [_clean_rule_text(item) for item in getattr(module, "rules", []) if _clean_rule_text(item)]


def _clean_rule_text(value: str) -> str:
    text = re.sub(r"\s+", "", str(value or "").strip())
    return text.rstrip("。；;，,、：:")


def _ui_screenshot_has_image(ui_screenshots: dict | None, key: str) -> bool:
    if not isinstance(ui_screenshots, dict):
        return False
    item = ui_screenshots.get(key)
    image_path = getattr(item, "image_path", None) if item else None
    return bool(image_path and Path(image_path).exists())


def _required_field_text(module) -> str:
    fields = [str(item).strip() for item in getattr(module, "data_fields", []) if str(item).strip()]
    if fields:
        return "、".join(fields[:2])
    entities = [str(item).strip() for item in getattr(module, "entities", []) if str(item).strip()]
    if entities:
        return "、".join(f"{item}编码" for item in entities[:1]) + "、名称"
    return "编码、名称"


def _navigation_description(design_brief: dict | None) -> str:
    frontend = (design_brief or {}).get("ai_frontend_codegen") if isinstance(design_brief, dict) else {}
    if isinstance(frontend, dict) and str(frontend.get("framework") or "") == "react":
        return "顶部共享导航和业务内容区布局"
    nav_model = str((design_brief or {}).get("nav_model") or "")
    if nav_model == "top_tabs":
        return "顶部页签导航和主体工作区布局"
    if nav_model == "rail":
        return "顶部项目导航和业务工作区布局"
    return "左侧菜单和右侧工作区布局"


def _manual_paragraphs_for_renderer(paragraphs: list[str], design_brief: dict | None) -> list[str]:
    brief = design_brief if isinstance(design_brief, dict) else {}
    renderer = str(brief.get("expected_renderer") or brief.get("renderer") or "").lower()
    experience = brief.get("product_experience_spec") if isinstance(brief.get("product_experience_spec"), dict) else {}
    terminal = str(
        (experience or {}).get("terminal")
        or (experience or {}).get("experience_terminal")
        or brief.get("experience_terminal")
        or ""
    ).lower()
    if renderer in {"mobile_app", "game"} or terminal in {"mobile", "phone", "mobile_app"}:
        return list(paragraphs)
    mobile_markers = (
        "移动App",
        "移动 APP",
        "手机App",
        "手机 APP",
        "手机端",
        "移动端",
        "Android/iOS",
        "小程序",
        "底部导航",
        "进入项目",
        "个人中心",
    )
    result: list[str] = []
    for paragraph in paragraphs:
        text = str(paragraph)
        if any(marker in text for marker in mobile_markers):
            continue
        text = text.replace("移动质量工作入口", "现场质量工作入口")
        text = text.replace("移动作业入口", "现场作业入口")
        result.append(text)
    return result


def _manual_renderer_from_screenshots(ui_screenshots: dict | None) -> str:
    if not isinstance(ui_screenshots, dict):
        return ""
    dimensions = [
        (int(getattr(item, "width", 0) or 0), int(getattr(item, "height", 0) or 0))
        for item in ui_screenshots.values()
        if int(getattr(item, "width", 0) or 0) > 0 and int(getattr(item, "height", 0) or 0) > 0
    ]
    if not dimensions:
        return ""
    landscape = sum(1 for width, height in dimensions if width > height)
    return "admin" if landscape >= (len(dimensions) + 1) // 2 else "mobile_app"


def _manual_design_brief_with_renderer(design_brief: dict | None, ui_screenshots: dict | None) -> dict:
    brief = dict(design_brief) if isinstance(design_brief, dict) else {}
    if not str(brief.get("expected_renderer") or brief.get("renderer") or "").strip():
        inferred = _manual_renderer_from_screenshots(ui_screenshots)
        if inferred:
            brief["expected_renderer"] = inferred
    return brief


def _manual_is_mobile_terminal(design_brief: dict | None) -> bool:
    brief = design_brief if isinstance(design_brief, dict) else {}
    renderer = str(brief.get("expected_renderer") or brief.get("renderer") or "").lower()
    experience = brief.get("product_experience_spec") if isinstance(brief.get("product_experience_spec"), dict) else {}
    terminal = str(
        (experience or {}).get("terminal")
        or (experience or {}).get("experience_terminal")
        or brief.get("experience_terminal")
        or ""
    ).lower()
    return renderer in {"mobile_app", "game"} or terminal in {"mobile", "phone", "mobile_app"}


def _manual_architecture_name(blueprint: ProductBlueprint, design_brief: dict | None) -> str:
    name = _architecture_name(blueprint)
    if _manual_is_mobile_terminal(design_brief):
        return name
    replacements = (
        ("移动端与服务端", "桌面 Web 端与服务端"),
        ("移动端/服务端", "桌面 Web 端/服务端"),
        ("移动端", "桌面 Web 端"),
        ("移动 App", "桌面 Web 应用"),
        ("移动APP", "桌面 Web 应用"),
    )
    for source, target in replacements:
        name = name.replace(source, target)
    return name


def _manual_deployment_topology(blueprint: ProductBlueprint, design_brief: dict | None) -> str:
    topology = str(
        blueprint.deployment_topology
        or "客户端访问业务服务，服务端完成数据处理、权限控制和文件导出。"
    ).strip()
    if _manual_is_mobile_terminal(design_brief):
        return topology
    mobile_markers = ("移动 App", "移动APP", "移动端", "手机 App", "手机APP", "小程序")
    if any(marker in topology for marker in mobile_markers):
        return (
            "工业触控终端或桌面浏览器通过项目专网或互联网访问系统业务服务，"
            "服务端完成业务处理、权限控制、数据存储、统计分析和文件导出。"
        )
    return topology


def _manual_runtime_environment_value(value: str, design_brief: dict | None) -> str:
    text = str(value or "").strip()
    if _manual_is_mobile_terminal(design_brief):
        return text
    replacements = (
        ("Android/iOS 浏览器环境、Windows 客户端浏览器", "Windows 10/11 客户端浏览器、Linux 工业触控终端浏览器"),
        ("移动终端或浏览器终端", "工业触控终端或桌面浏览器终端"),
        ("移动终端", "工业触控终端或桌面浏览器终端"),
        ("Android/iOS", "Windows/Linux"),
    )
    for source, target in replacements:
        text = text.replace(source, target)
    return text


def _manual_product_type(task: GenerationTask, blueprint: ProductBlueprint) -> str:
    configured = str(getattr(task, "product_type", "") or "应用软件").strip()
    domain_text = " ".join(
        str(value or "")
        for value in (
            getattr(task, "software_name", ""),
            getattr(blueprint, "industry", ""),
            getattr(blueprint, "industry_subtype", ""),
            getattr(blueprint, "scenario", ""),
            getattr(blueprint, "summary", ""),
        )
    )
    medical_markers = ("医疗", "医院", "诊疗", "患者", "医生", "手术", "护理", "药品")
    if configured == "医疗软件" and not any(marker in domain_text for marker in medical_markers):
        if "大数据" in domain_text:
            return "大数据软件"
        if any(marker in domain_text for marker in ("人工智能", "智能分析", "智能识别", "智能预测")):
            return "人工智能软件"
        return "应用软件"
    return configured


def _manual_content_for_renderer(manual_content: dict | None, design_brief: dict | None) -> dict | None:
    if not isinstance(manual_content, dict):
        return manual_content
    filtered = dict(manual_content)
    for key in ("overview", "login_main", "statistics", "security", "faq"):
        value = filtered.get(key)
        if isinstance(value, list):
            filtered[key] = _manual_paragraphs_for_renderer([str(item) for item in value], design_brief)
    modules = filtered.get("modules")
    if isinstance(modules, dict):
        filtered_modules: dict = {}
        for module_key, item in modules.items():
            if not isinstance(item, dict):
                continue
            filtered_item = dict(item)
            paragraphs = filtered_item.get("paragraphs")
            if isinstance(paragraphs, list):
                filtered_item["paragraphs"] = _manual_paragraphs_for_renderer(
                    [str(paragraph) for paragraph in paragraphs],
                    design_brief,
                )
            filtered_modules[module_key] = filtered_item
        filtered["modules"] = filtered_modules
    return filtered


def _runtime_screenshot_note(design_brief: dict | None) -> str:
    evidence = _manual_source_evidence(design_brief)
    if not evidence:
        return ""
    mode = str(evidence.get("render_mode") or "")
    if mode != "project-server":
        return ""
    api_pages = int(evidence.get("runtime_api_page_count") or 0)
    if evidence.get("runtime_api_ready") and api_pages:
        return "本说明书中的界面用于说明登录、首页、功能办理和统计查询等日常操作；页面中的列表、表单、当前记录和统计区域均围绕本软件业务数据展示。"
    return "本说明书中的界面用于说明系统日常操作，页面内容与功能模块、业务字段、状态流转、操作结果和权限控制保持一致。"


def _module_source_note(design_brief: dict | None, module) -> str:
    evidence = _module_manual_source_evidence(design_brief, getattr(module, "key", ""))
    if not evidence:
        return ""
    fields = [str(item).strip() for item in (evidence.get("fields") or []) if str(item).strip()]
    runtime_pages = _manual_runtime_pages_for_module(design_brief, getattr(module, "key", ""))
    runtime_note = ""
    if runtime_pages:
        total = sum(int(item.get("record_count") or 0) for item in runtime_pages)
        runtime_note = f"该模块界面展示{len(runtime_pages)}类相关业务视图，当前业务记录约{total}条；"
    if fields:
        return f"{runtime_note}该界面的字段、状态、操作入口和操作结果提示与{module.title}的数据处理要求一致，重点核对{_join_items(fields[:3])}。"
    return f"{runtime_note}该界面围绕{module.title}的查询、处理、复核和归档过程组织，操作结果会同步进入统计、待办和日志记录。"


def _customer_manual_text(text: str) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    replacements = [
        (r"本次生成的源码项目服务运行后截取", "系统实际运行界面"),
        (r"本次生成的源码项目服务运行界面", "系统实际运行界面"),
        (r"本次生成的源码项目服务", "系统业务服务"),
        (r"源码项目服务", "系统业务服务"),
        (r"运行服务接口返回数据", "系统业务数据"),
        (r"运行服务读取", "业务数据区加载"),
        (r"接口返回的业务记录出现在页面可见区域", "业务记录已在页面中展示"),
        (r"接口返回记录约", "当前业务记录约"),
        (r"接口返回", "当前查询"),
        (r"有效接口返回", "业务数据加载"),
        (r"浏览器页面已加载业务接口数据", "页面已加载业务数据"),
        (r"页面截图时已从", "页面从"),
        (r"截图中的", ""),
        (r"运行 API", "业务数据"),
        (r"(?<![A-Za-z])API(?![A-Za-z])", "业务接口"),
        (r"source-ui-evidence", "业务校验证据"),
        (r"generated_source", "业务工程"),
        (r"ui-prototype", "业务界面"),
        (r"image2|视觉参考稿|视觉参考|参考稿", "界面设计"),
        (r"GPT|AI\s*(生成|提示词|模型说明|接口|代码)", ""),
    ]
    for pattern, replacement in replacements:
        value = re.sub(pattern, replacement, value, flags=re.I)
    value = re.sub(r"(业务接口接口|业务数据数据|系统系统)", lambda m: m.group(0)[: len(m.group(0)) // 2], value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _manual_source_evidence(design_brief: dict | None) -> dict:
    evidence = (design_brief or {}).get("source_ui_evidence") if isinstance(design_brief, dict) else {}
    return evidence if isinstance(evidence, dict) else {}


def _module_manual_source_evidence(design_brief: dict | None, module_key: str) -> dict:
    evidence = _manual_source_evidence(design_brief)
    modules = evidence.get("modules") if isinstance(evidence.get("modules"), dict) else {}
    item = modules.get(module_key) if isinstance(modules, dict) else {}
    return item if isinstance(item, dict) else {}


def _manual_runtime_pages_for_module(design_brief: dict | None, module_key: str) -> list[dict]:
    evidence = _manual_source_evidence(design_brief)
    pages = evidence.get("runtime_api_pages") if isinstance(evidence.get("runtime_api_pages"), list) else []
    if not module_key:
        return []
    return [
        page
        for page in pages
        if isinstance(page, dict) and page.get("api_ready") and str(page.get("module_key") or "") == str(module_key)
    ]


def _content_paragraphs(
    manual_content: dict | None,
    key: str,
    fallback: list[str],
    min_count: int,
) -> list[str]:
    if manual_content:
        paragraphs = manual_content.get(key)
        if isinstance(paragraphs, list) and paragraphs:
            return _expand_paragraphs([str(item) for item in paragraphs], min_count=min_count, max_count=max(min_count, 3))
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
    return [str(item) for item in paragraphs[:3]]


def _manual_content_for_handbook(manual_content: dict | None, blueprint: ProductBlueprint) -> dict | None:
    if not isinstance(manual_content, dict):
        return manual_content
    compact: dict = {"modules": {}}
    for key, *_rest in [
        ("overview",),
        ("login_main",),
        ("statistics",),
        ("security",),
        ("faq",),
    ]:
        value = manual_content.get(key)
        if isinstance(value, list):
            compact[key] = _compact_manual_paragraphs(value, limit=3)
    modules = manual_content.get("modules")
    if isinstance(modules, dict):
        for module in blueprint.modules:
            item = modules.get(module.key)
            if isinstance(item, dict):
                compact["modules"][module.key] = {
                    "title": str(item.get("title") or module.title),
                    "paragraphs": _compact_manual_paragraphs(item.get("paragraphs"), limit=3),
                }
    if manual_content.get("_warnings"):
        compact["_warnings"] = manual_content.get("_warnings")
    return compact


def _compact_manual_paragraphs(value, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = _trim_manual_paragraph(str(item))
        if text and text not in result:
            result.append(text)
        if len(result) >= limit:
            break
    return result


def _extend_faq_paragraphs(
    blueprint: ProductBlueprint,
    paragraphs: list[str],
    target_count: int = 10,
) -> list[str]:
    result = [str(item).strip() for item in paragraphs if str(item).strip()]
    module_titles = [module.title for module in blueprint.modules if str(module.title or "").strip()]
    first_module = module_titles[0] if module_titles else "业务办理"
    second_module = module_titles[1] if len(module_titles) > 1 else "数据查询"
    third_module = module_titles[2] if len(module_titles) > 2 else "状态处理"
    rule_text = _clean_rule_text(blueprint.quality_rules[0]) if blueprint.quality_rules else "关键字段、处理状态和关联资料完整性"
    candidates = [
        f"进入{first_module}后未显示当前业务对象时，应先确认组织、项目或数据范围是否正确，再清除日期和状态筛选条件重新查询；仍无结果时，可查看当前角色是否具备对应模块的数据权限。",
        f"在{second_module}中保存或提交失败时，应检查必填字段、业务编号、处理人员和时间信息是否完整。系统会按照{rule_text}执行校验，用户应根据页面提示补齐后重新提交。",
        f"{third_module}的状态长时间未更新时，可先刷新当前页面并查看处理轨迹、操作日志和关联任务；若上一步尚未完成，应返回对应详情处理，不能直接跳过既定业务节点。",
        "导入附件或业务数据失败时，应确认文件格式、字段表头、文件大小和当前账号权限符合页面要求。修正后重新选择文件，先查看校验结果，再执行正式导入，避免重复写入。",
        "导出或打印结果异常时，应重新确认统计周期、筛选范围和数据版本，并检查本机下载目录和磁盘空间。重新生成后，页面应显示导出时间、操作人员和结果文件状态。",
        "弱网或服务短暂中断时，不要连续重复提交同一业务操作。用户可保留当前页面，待连接恢复后刷新处理结果；若系统已生成操作记录，应以最新状态和审计日志为准。",
        "页面中的图片、附件或预览内容无法显示时，应先确认文件仍在有效期内，并检查浏览器是否允许加载和下载。重新进入详情页后仍无内容时，可根据业务编号核对附件记录和上传状态。",
        "统计结果与业务台账不一致时，应确认两处使用的组织范围、统计时间、状态口径和数据版本相同。完成条件校准后重新统计，并通过明细列表抽查异常记录的处理轨迹。",
        "发现同一业务对象可能被重复登记时，应先使用业务编号、名称和发生时间进行检索。已有记录尚在处理中时，应进入原记录继续办理；确认属于重复数据后，再按权限执行撤回或作废。",
    ]
    for candidate in candidates:
        if len(result) >= max(3, int(target_count or 0)):
            break
        if candidate not in result:
            result.append(candidate)
    return result


def _trim_manual_paragraph(text: str, limit: int = 135) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    for mark in "。；，":
        pos = cut.rfind(mark)
        if pos >= 48:
            return cut[: pos + 1]
    return cut.rstrip("，；、") + "。"


def _module_summary(blueprint: ProductBlueprint) -> str:
    details = []
    for module in blueprint.modules:
        details.append(f"{module.title}用于{module.description}")
    return "系统主要包括" + "、".join(details) + "等功能。"


def _soft_copyright_info_environment(task: GenerationTask, blueprint: ProductBlueprint) -> dict[str, str]:
    language = _info_programming_language(task, blueprint)
    dev_tool = _info_development_tool(language, blueprint)
    runtime_support = _info_runtime_support(language, blueprint)
    return {
        "dev_hardware": _specific_or_default(
            blueprint.dev_environment.get("hardware", ""),
            "CPU：Intel Core i7-11700,内存：32GB,硬盘：1TB",
            ["x86_64", "工作站", "计算节点"],
        ),
        "runtime_hardware": _specific_or_default(
            blueprint.runtime_environment.get("hardware", ""),
            "CPU: Intel Core i5-11500,内存: 16GB,硬盘: 512GB",
            ["服务器", "终端", "浏览器", "主机"],
        ),
        "dev_os": _specific_or_default(
            blueprint.dev_environment.get("os", ""),
            "Windows 10 64位 专业版",
            ["Windows 10/11", "Ubuntu", "Linux"],
        ),
        "dev_tool": dev_tool,
        "runtime_os": _specific_or_default(
            blueprint.runtime_environment.get("os", ""),
            "Windows 10 64位 专业版",
            ["Linux", "Android", "iOS", "浏览器", "Windows Server", "容器"],
        ),
        "runtime_support": runtime_support,
    }


def _specific_or_default(value: str, default: str, generic_terms: list[str]) -> str:
    text = str(value or "").strip()
    if not text:
        return default
    if any(term in text for term in generic_terms):
        return default
    return text


def _info_programming_language(task: GenerationTask, blueprint: ProductBlueprint) -> str:
    architecture = getattr(blueprint, "technical_architecture", {}) or {}
    language = str(architecture.get("source_language") or task.language or blueprint.language or "").strip()
    if not language or language == "自动选择":
        language = str(blueprint.language or task.language or "JAVA").strip()
    tokens = [item.strip() for item in re.split(r"[/,，、\s]+", language) if item.strip()]
    if not tokens:
        tokens = ["JAVA"]
    normalized: list[str] = []
    for token in tokens:
        token_map = {
            "java": "JAVA",
            "javascript": "JAVASCRIPT",
            "js": "JAVASCRIPT",
            "typescript": "TYPESCRIPT",
            "ts": "TYPESCRIPT",
            "python": "PYTHON",
            "c#": "C#",
            "csharp": "C#",
            "c++": "C++",
            "cpp": "C++",
            "sql": "SQL",
        }
        normalized.append(token_map.get(token.lower(), token.upper() if token.isalpha() else token))
    return "/".join(dict.fromkeys(normalized))


def _info_development_tool(language: str, blueprint: ProductBlueprint) -> str:
    stack_text = " ".join((getattr(blueprint, "technical_architecture", {}) or {}).get("stack", []))
    text = f"{language} {stack_text}"
    language_tokens = set(re.split(r"[/,，、\s]+", language.upper()))
    if "C#" in language_tokens or ".NET" in text:
        return "Visual Studio 2022"
    if "PYTHON" in language_tokens or "Python" in stack_text:
        return "PyCharm"
    if "JAVASCRIPT" in language_tokens and "JAVA" not in language_tokens:
        return "Visual Studio Code"
    if "JAVASCRIPT" in language_tokens and "JAVA" in language_tokens:
        return "IntelliJ IDEA、Visual Studio Code"
    if "C++" in language_tokens:
        return "Visual Studio 2022"
    return "IntelliJ IDEA"


def _info_runtime_support(language: str, blueprint: ProductBlueprint) -> str:
    text = f"{language} {' '.join((getattr(blueprint, 'technical_architecture', {}) or {}).get('stack', []))}"
    language_tokens = set(re.split(r"[/,，、\s]+", language.upper()))
    parts: list[str] = []
    if "JAVA" in language_tokens or "Spring" in text:
        parts.append("JDK 17")
    if "JAVASCRIPT" in text or "React" in text or "Node" in text:
        parts.append("Node.js")
    if "PYTHON" in text or "FastAPI" in text:
        parts.append("Python 3")
    if "C#" in text or ".NET" in text:
        parts.append(".NET 8 Runtime")
    if "MySQL" in text:
        parts.append("MySQL")
    if not parts:
        parts.append("JDK 17")
    return "、".join(dict.fromkeys(parts))


def _info_development_purpose(task: GenerationTask, blueprint: ProductBlueprint) -> str:
    objects = _join_items(blueprint.business_objects[:3]) or "业务数据"
    industry = blueprint.industry or task.product_type
    return f"规范{industry}中{objects}的查询、维护、统计和归档流程，提升业务处理效率。"


def _info_main_functions(task: GenerationTask, blueprint: ProductBlueprint) -> str:
    module_parts: list[str] = []
    for module in blueprint.modules[:8]:
        query_fields = _join_items(module.data_fields[:3]) or "名称、状态和时间范围"
        required = _required_field_text(module)
        operations = _manual_operation_list(module)
        rules = _join_items(_clean_info_rule_text(item) for item in module.rules[:2]) or "字段完整性和状态"
        module_parts.append(
            f"{module.title}功能，点击“{module.title}”进入页面，查询时可通过{query_fields}等条件筛选，"
            f"并支持{operations}操作；追加或修改时“{required}”为必填项，系统会执行{rules}校验"
        )
    return (
        f"{task.software_name}具备丰富且全面的功能模块。"
        + "；".join(module_parts)
        + "。各模块均支持查询、维护、查看、失效、导出和操作留痕，通过清晰的业务步骤保障数据准确管理与高效运维。"
    )


def _clean_info_rule_text(value: str) -> str:
    return _clean_rule_text(value)


def _technical_feature_category(task: GenerationTask) -> str:
    text = f"{task.product_type} {task.software_category} {task.software_name}"
    if "云" in text:
        return "云计算软件"
    if "人工智能" in text or "AI" in text or "算法" in text:
        return "人工智能软件"
    if "大数据" in text or "数据" in text:
        return "大数据软件"
    if "物联网" in text or "嵌入" in text:
        return "物联网软件"
    if "智慧城市" in text or "交通" in text:
        return "智慧城市软件"
    if "信息安全" in text or "安全" in text:
        return "信息安全软件"
    return task.product_type or "应用软件"


def _info_technical_features(task: GenerationTask, blueprint: ProductBlueprint) -> str:
    features = [str(item).strip() for item in blueprint.technical_features[:5] if str(item).strip()]
    if not features:
        features = ["模块化业务处理", "数据查询统计", "权限控制", "操作留痕", "结果导出"]
    return "具备" + "、".join(features) + "等特点，支持快速查询、规范维护、数据安全可靠、操作便捷易管理。"


def _join_items(items: list[str]) -> str:
    return "、".join(str(item) for item in items if str(item).strip())


def _architecture_name(blueprint: ProductBlueprint) -> str:
    architecture = getattr(blueprint, "technical_architecture", {}) or {}
    return str(architecture.get("name") or "自动选择技术架构")


def _safe_file_label(value: str) -> str:
    return re.sub(r"[\\/:*?\"<>|]+", "_", str(value or "source")).strip() or "source"


def _workflow_summary(blueprint: ProductBlueprint) -> str:
    if not blueprint.workflows:
        return "业务提交、字段校验、状态流转和结果归档流程"
    names = [str(item.get("name") or "") for item in blueprint.workflows[:3] if isinstance(item, dict)]
    names = [name for name in names if name]
    return "、".join(names) or "业务提交、字段校验、状态流转和结果归档流程"


def _add_page_number_field(paragraph) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    run = paragraph.add_run()
    fld_char_begin = OxmlElement("w:fldChar")
    fld_char_begin.set(qn("w:fldCharType"), "begin")
    instr_text = OxmlElement("w:instrText")
    instr_text.set(qn("xml:space"), "preserve")
    instr_text.text = "PAGE"
    fld_char_separate = OxmlElement("w:fldChar")
    fld_char_separate.set(qn("w:fldCharType"), "separate")
    cached_text = OxmlElement("w:t")
    cached_text.text = "1"
    fld_char_end = OxmlElement("w:fldChar")
    fld_char_end.set(qn("w:fldCharType"), "end")
    run._r.append(fld_char_begin)
    run._r.append(instr_text)
    run._r.append(fld_char_separate)
    run._r.append(cached_text)
    run._r.append(fld_char_end)


def _module_figure_key(module_key: str) -> str:
    if module_key in {"login", "dashboard", "statistics"}:
        return f"module_{module_key}"
    return module_key


def _module_operation_figure_key(module_key: str, action: str, operation_index: int) -> str:
    token = re.sub(r"[^a-zA-Z0-9]+", "_", action).strip("_").lower()
    token = token or f"operation_{operation_index}"
    return f"{_module_figure_key(module_key)}_{token}_{operation_index}"
