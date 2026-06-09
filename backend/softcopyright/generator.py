from __future__ import annotations

from pathlib import Path
import shutil
import time
import json

from .blueprint import generate_blueprint
from .docgen import (
    convert_to_pdf,
    ensure_docx_available,
    generate_info_txt,
    generate_manual_docx,
    generate_source_docx,
    pdf_converter_info,
)
from .feature_inference import harmonize_feature_hint
from .llm_blueprint import generate_blueprint_with_llm
from .llm_manual import generate_manual_content_with_llm
from .models import GenerationTask
from .packager import make_zip_files, write_json
from .screenshots import generate_ui_screenshots
from .ui_blueprint import ui_matches_software_type
from .sourcegen import generate_source_project, source_project_stats
from .validator import build_materials_manifest, validate_materials, validation_checks


def generate_materials(task: GenerationTask, emit=None, llm_provider=None) -> dict:
    started_at = time.perf_counter()
    stage_started_at = started_at
    stage_timings: dict[str, float] = {}

    def send(stage: str, progress: int, message: str, **extra) -> None:
        if emit:
            emit({"stage": stage, "progress": progress, "message": message, **extra})

    def mark(stage: str) -> None:
        nonlocal stage_started_at
        now = time.perf_counter()
        stage_timings[stage] = round(now - stage_started_at, 2)
        stage_started_at = now

    send("prepare", 3, "理解软件名称并补充业务关键词")
    feature_hint, feature_hint_meta = harmonize_feature_hint(
        task.software_name,
        task.product_type,
        task.feature_hint,
        provider=llm_provider,
    )
    task.feature_hint = feature_hint
    setattr(task, "semantic_contract", feature_hint_meta)

    send("prepare", 5, "准备输出目录")
    output_dir = task.output_dir
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    report: dict = {
        "task": task.to_dict(),
        "warnings": [],
        "files": [],
        "checks": {},
    }
    report["checks"]["generation_quality_profile"] = _generation_quality_profile()
    report["checks"]["blueprint_quality_target"] = _blueprint_quality_target()
    report["feature_hint"] = feature_hint_meta
    report["checks"]["auto_feature_hint"] = bool(feature_hint_meta.get("auto_feature_hint"))
    report["checks"]["feature_hint_profile"] = feature_hint_meta.get("feature_hint_profile", "")
    report["checks"]["feature_hint_source"] = feature_hint_meta.get("feature_hint_source", "")

    docx_available, docx_error = ensure_docx_available()
    if not docx_available:
        report["warnings"].append(f"python-docx 未安装，无法生成 Word 文档：{docx_error}")

    send("blueprint", 15, "生成产品蓝图")
    blueprint_source = "local-template"
    try:
        llm_blueprint = generate_blueprint_with_llm(
            task,
            llm_provider,
            emit=lambda progress, message, **extra: send("blueprint", progress, message, **extra),
        )
    except Exception as exc:
        llm_blueprint = None
        report["warnings"].append(f"模型蓝图生成失败，已回退本地模板：{exc}")
    if llm_blueprint:
        blueprint = llm_blueprint
        blueprint_source = "llm"
    else:
        blueprint = generate_blueprint(task)
    mark("blueprint")
    report["blueprint"] = blueprint.to_dict()
    report["blueprint_source"] = blueprint_source
    report["checks"]["blueprint_source"] = blueprint_source
    report["checks"]["blueprint_quality_score"] = blueprint.quality_score
    report["checks"]["blueprint_fingerprint"] = blueprint.generation_fingerprint
    report["checks"]["blueprint_business_object_count"] = len(blueprint.business_objects)
    report["checks"]["blueprint_workflow_count"] = len(blueprint.workflows)
    report["checks"]["blueprint_metric_count"] = len(blueprint.report_metrics)
    report["checks"]["blueprint_module_detail_ready"] = all(
        bool(module.operations) and bool(module.data_fields) and bool(module.rules)
        for module in blueprint.modules
    )

    manual_content = None
    manual_source = "local-template"
    if blueprint_source == "llm":
        try:
            send("manual_content", 24, "生成说明书正文")
            manual_content = generate_manual_content_with_llm(
                task,
                blueprint,
                llm_provider,
                emit=lambda progress, message, **extra: send("manual_content", progress, message, **extra),
            )
        except Exception as exc:
            manual_content = None
            report["warnings"].append(f"模型说明书正文生成失败，已回退本地模板：{exc}")
    if manual_content:
        manual_source = "llm"
        for warning in manual_content.pop("_warnings", []):
            report["warnings"].append(warning)
    report["manual_source"] = manual_source
    mark("manual_content")

    send("source", 32, "生成真实源码工程")
    source_info = generate_source_project(task, blueprint, output_dir)
    report["source"] = source_info
    source_lines = int(source_info["total_lines"])
    _emit_source_file_events(send, source_info, output_dir)
    mark("source")

    send("screenshots", 40, "生成界面截图")
    ui_screenshots, screenshot_warnings, ui_blueprint = generate_ui_screenshots(
        task,
        blueprint,
        output_dir,
        llm_provider,
        source_info=source_info,
        emit=lambda progress, message, **extra: send("screenshots", progress, message, **extra),
    )
    for warning in screenshot_warnings:
        report["warnings"].append(warning)
    source_info.update(source_project_stats(Path(source_info["source_dir"])))
    source_lines = int(source_info["total_lines"])
    report["source"] = source_info
    report["ui_blueprint"] = {
        "renderer": ui_blueprint.renderer,
        "visual_style": ui_blueprint.visual_style,
        "source": ui_blueprint.source,
        "design_brief": getattr(ui_blueprint, "design_brief", {}) or {},
        "path": str(output_dir / "ui_screenshots" / "ui_blueprint.json"),
        "prototype_dir": source_info.get("ui_prototype_dir", ""),
        "project_entry": source_info.get("ui_project_entry", {}),
        "layout_variant": _ui_layout_variant(ui_blueprint, ui_screenshots),
    }
    report["ui_screenshots"] = {
        key: {
            "title": item.title,
            "caption": item.caption,
            "html_path": item.html_path,
            "image_path": item.image_path,
            "width": item.width,
            "height": item.height,
        }
        for key, item in ui_screenshots.items()
    }
    report["checks"]["ui_screenshot_count"] = sum(1 for item in ui_screenshots.values() if item.image_path)
    _emit_screenshot_events(send, ui_screenshots, output_dir)
    report["checks"]["ui_blueprint_source"] = ui_blueprint.source
    report["checks"]["ui_renderer"] = ui_blueprint.renderer
    report["checks"]["ui_layout_variant"] = report["ui_blueprint"]["layout_variant"]
    design_brief = getattr(ui_blueprint, "design_brief", {}) or {}
    report["checks"]["ui_industry_subtype"] = design_brief.get("industry_subtype", getattr(blueprint, "industry_subtype", ""))
    report["checks"]["ui_nav_model"] = design_brief.get("nav_model", "")
    report["checks"]["ui_visual_mood"] = design_brief.get("visual_mood", ui_blueprint.visual_style)
    report["checks"]["ui_dashboard_pattern"] = design_brief.get("dashboard_pattern", "")
    report["checks"]["ui_module_pattern"] = design_brief.get("module_pattern", "")
    report["checks"]["ui_workspace_shape"] = design_brief.get("workspace_shape", "")
    report["checks"]["ui_login_pattern"] = design_brief.get("login_pattern", "")
    report["checks"]["ui_structure_id"] = (design_brief.get("structure_blueprint") or {}).get("id", "")
    report["checks"]["ui_domain_bias"] = (design_brief.get("design_dna") or {}).get("domain_bias", "")
    report["checks"]["ui_layout_signature"] = design_brief.get("layout_signature", "")
    report["checks"]["ui_secondary_mix"] = "、".join(str(item) for item in design_brief.get("secondary_mix", []) if str(item).strip())
    report["checks"]["ui_software_type_match"] = ui_matches_software_type(task, blueprint, ui_blueprint)
    report["checks"].update(_ui_project_entry_checks(source_info))
    if ui_blueprint.renderer == "game":
        dimensions = [(item.width, item.height) for item in ui_screenshots.values() if item.width and item.height]
        report["checks"]["ui_screenshot_aspect_ratio"] = "9:16"
        report["checks"]["ui_mobile_portrait_match"] = bool(dimensions) and all(height > width and abs((width / height) - (9 / 16)) < 0.02 for width, height in dimensions)
    else:
        dimensions = [(item.width, item.height) for item in ui_screenshots.values() if item.width and item.height]
        report["checks"]["ui_screenshot_aspect_ratio"] = "desktop"
        report["checks"]["ui_admin_desktop_match"] = bool(dimensions) and all(width >= 1200 and height >= 800 and width > height for width, height in dimensions)
        report["checks"]["ui_industry_profile"] = task.product_type
    mark("screenshots")

    manual_docx = None
    source_docx = None
    manual_pdf = None
    source_pdf = None
    source_report: dict = {}
    pdf_conversions: list[dict] = []
    if docx_available:
        send("manual", 48, "生成软件说明书")
        _emit_manual_outline_events(send, blueprint, ui_screenshots)
        manual_docx = generate_manual_docx(
            task,
            blueprint,
            output_dir,
            manual_content=manual_content,
            ui_screenshots=ui_screenshots,
            design_brief=design_brief,
        )
        _emit_output_file_event(send, "manual", 61, "写入软件说明书 Word", manual_docx, output_dir, "Word 文档")
        mark("manual_docx")
        send("source_doc", 62, "生成源码鉴别材料")
        source_docx, source_report = generate_source_docx(task, Path(source_info["source_dir"]), output_dir)
        report["checks"].update({key: value for key, value in source_report.items() if key != "source_page_sources"})
        _emit_source_page_events(send, source_report, output_dir)
        _emit_output_file_event(send, "source_doc", 76, "写入源码鉴别材料 Word", source_docx, output_dir, "Word 文档")
        mark("source_docx")

        send("pdf", 78, "转换 PDF 文件")
        converter_info = pdf_converter_info()
        for docx_path in [manual_docx, source_docx]:
            send(
                "pdf",
                78,
                f"转换 PDF：{docx_path.name}",
                docx_path=str(_path_label(docx_path, output_dir)),
                material_type="PDF 转换",
            )
            pdf_path, error = convert_to_pdf(docx_path, output_dir)
            pdf_conversions.append(
                {
                    "docx_path": str(docx_path),
                    "pdf_path": str(pdf_path) if pdf_path else "",
                    "method": converter_info.get("method", ""),
                    "soffice_path": converter_info.get("soffice_path", ""),
                    "fallback": converter_info.get("fallback", False),
                    "error": error or "",
                }
            )
            if pdf_path:
                if docx_path == manual_docx:
                    manual_pdf = pdf_path
                elif docx_path == source_docx:
                    source_pdf = pdf_path
            if error:
                report["warnings"].append(f"{docx_path.name}: {error}")
            if pdf_path:
                _emit_output_file_event(send, "pdf", 82, f"写入 PDF 文件：{pdf_path.name}", pdf_path, output_dir, "PDF 文件")
        mark("pdf")

    send("info", 86, "生成申请信息表")
    info_txt = generate_info_txt(task, blueprint, source_lines, output_dir)
    _emit_output_file_event(send, "info", 87, "写入申请信息表 TXT", info_txt, output_dir, "TXT 文本")
    mark("info")

    deliverable_files = [
        path
        for path in [manual_docx, manual_pdf, info_txt, source_docx, source_pdf]
        if path is not None
    ]

    report["checks"].update(
        {
            "software_name_consistent": True,
            "version_consistent": True,
            "source_total_lines": source_lines,
            "source_line_target_met": source_lines >= 3000,
            "docx_available": docx_available,
        }
    )
    report["checks"].update(_material_consistency_checks(blueprint, manual_content, ui_blueprint, source_info))
    report["files"] = [str(path) for path in deliverable_files]

    report_path = write_json(output_dir / "generation_report.json", report)
    _emit_output_file_event(send, "package", 90, "写入生成报告 JSON", report_path, output_dir, "JSON 报告")
    report["internal_files"] = [str(report_path)]

    send("package", 94, "打包 zip 材料包")
    zip_path = output_dir.parent / f"{task.task_id}--材料包.zip"
    _emit_zip_input_events(send, deliverable_files, output_dir)
    make_zip_files(deliverable_files, zip_path)
    _emit_output_file_event(send, "package", 95, "写入材料包 ZIP", zip_path, output_dir, "ZIP 材料包")
    mark("package")
    send("validate", 97, "校验材料真实性与规范性")
    validation = validate_materials(
        task=task,
        blueprint=blueprint,
        output_dir=output_dir,
        source_info=source_info,
        ui_blueprint=ui_blueprint,
        ui_screenshots=ui_screenshots,
        deliverable_files=deliverable_files,
        zip_path=zip_path,
        checks=report.get("checks", {}),
    )
    validation_path = write_json(output_dir / "validation_report.json", validation)
    _emit_output_file_event(send, "validate", 98, "写入真实性与规范性校验报告", validation_path, output_dir, "JSON 报告")
    materials_manifest = build_materials_manifest(
        task=task,
        blueprint=blueprint,
        validation=validation,
        source_info=source_info,
        source_report=source_report,
        ui_blueprint=ui_blueprint,
        ui_screenshots=ui_screenshots,
        pdf_conversions=pdf_conversions,
        generation_report_path=report_path,
    )
    materials_manifest_path = write_json(output_dir / "materials_manifest.json", materials_manifest)
    _emit_output_file_event(send, "validate", 99, "写入材料清单与来源追踪", materials_manifest_path, output_dir, "JSON 清单")
    report["validation"] = {
        "path": str(validation_path),
        "manifest_path": str(materials_manifest_path),
        "ready_for_delivery": validation.get("ready_for_delivery", False),
        "findings": validation.get("findings", []),
        "authenticity": validation.get("authenticity", {}),
        "normative": validation.get("normative", {}),
    }
    report["checks"].update(validation_checks(validation))
    report["internal_files"] = [str(report_path), str(validation_path), str(materials_manifest_path)]
    for finding in validation.get("findings", []):
        if finding.get("level") == "error":
            report["warnings"].append(f"材料校验：{finding.get('message')}")
    mark("validate")
    report["stage_timings"] = stage_timings
    report["total_seconds"] = round(time.perf_counter() - started_at, 2)
    report["checks"]["total_seconds"] = report["total_seconds"]
    report["zip_path"] = str(zip_path)
    write_json(report_path, report)
    send(
        "done",
        100,
        "生成完成",
        zip_path=str(zip_path),
        checks=report.get("checks", {}),
        warnings=report.get("warnings", []),
    )
    return report


def _emit_source_file_events(send, source_info: dict, output_dir: Path) -> None:
    source_dir = Path(str(source_info.get("source_dir") or ""))
    files = [Path(str(path)) for path in source_info.get("files", []) if str(path)]
    visible_files = [path for path in files if path.exists() and path.is_file()]
    total = len(visible_files)
    if not total:
        return
    for index, path in enumerate(visible_files, start=1):
        line_count = _count_text_lines(path)
        progress = 33 + min(6, int(index / max(total, 1) * 6))
        label = _path_label(path, source_dir if source_dir.exists() else output_dir)
        send(
            "source",
            progress,
            f"写入源码文件 {index}/{total}：{label}",
            file_path=str(label),
            line_count=line_count,
            file_count=total,
            material_type="源码文件",
        )


def _emit_manual_outline_events(send, blueprint, ui_screenshots: dict | None) -> None:
    send("manual", 49, "写入说明书封面、版本号和页眉")
    send("manual", 50, "写入软件概述、产品定位和开发目的")
    send("manual", 51, "写入运行环境、开发环境和部署拓扑")
    send("manual", 52, "写入登录与主界面操作说明")
    modules = list(getattr(blueprint, "modules", []) or [])
    total = len(modules)
    for index, module in enumerate(modules, start=1):
        progress = 53 + min(5, int(index / max(total, 1) * 5))
        send(
            "manual",
            progress,
            f"写入功能模块章节 {index}/{total}：{module.title}",
            material_type="说明书章节",
        )
    screenshot_count = sum(1 for item in (ui_screenshots or {}).values() if getattr(item, "image_path", None))
    if screenshot_count:
        send("manual", 59, f"插入说明书界面配图 {screenshot_count} 张", material_type="说明书配图")
    send("manual", 60, "写入统计分析、权限安全和常见问题章节", material_type="说明书章节")


def _emit_source_page_events(send, source_report: dict, output_dir: Path) -> None:
    pages = source_report.get("source_page_sources")
    if not isinstance(pages, list) or not pages:
        return
    total = len(pages)
    for item in pages:
        if not isinstance(item, dict):
            continue
        page = int(item.get("page") or 0)
        sources = item.get("sources") if isinstance(item.get("sources"), list) else []
        first_source = sources[0] if sources else {}
        file_name = str(first_source.get("file") or "源码文件")
        start_line = first_source.get("start_line")
        end_line = first_source.get("end_line")
        line_range = f"第 {start_line}-{end_line} 行" if start_line and end_line else f"{item.get('line_count', 0)} 行"
        progress = 63 + min(12, int(page / max(total, 1) * 12))
        send(
            "source_doc",
            progress,
            f"排版源码鉴别材料第 {page}/{total} 页：{file_name} {line_range}",
            page=page,
            total_pages=total,
            line_count=item.get("line_count", 0),
            file_path=file_name,
            material_type="源码鉴别材料",
        )


def _emit_screenshot_events(send, ui_screenshots: dict, output_dir: Path) -> None:
    items = [item for item in ui_screenshots.values() if getattr(item, "image_path", None)]
    total = len(items)
    for index, item in enumerate(items, start=1):
        path = Path(str(item.image_path))
        progress = 46 + min(8, int(index / max(total, 1) * 8))
        send(
            "screenshots",
            progress,
            f"写入界面截图 {index}/{total}：{item.title}",
            file_path=str(_path_label(path, output_dir)),
            width=item.width,
            height=item.height,
            material_type="界面截图",
        )


def _emit_zip_input_events(send, files: list[Path], output_dir: Path) -> None:
    total = len(files)
    for index, path in enumerate(files, start=1):
        send(
            "package",
            94,
            f"加入材料包 {index}/{total}：{path.name}",
            file_path=str(_path_label(path, output_dir)),
            file_count=total,
            material_type="打包文件",
        )


def _emit_output_file_event(send, stage: str, progress: int, message: str, path: Path, output_dir: Path, material_type: str) -> None:
    send(
        stage,
        progress,
        message,
        file_path=str(_path_label(path, output_dir)),
        output_path=str(path),
        line_count=_count_text_lines(path) if path.suffix.lower() in {".txt", ".json"} else 0,
        material_type=material_type,
    )


def _path_label(path: Path, base: Path) -> Path:
    try:
        return path.resolve().relative_to(base.resolve())
    except Exception:
        return path


def _count_text_lines(path: Path) -> int:
    try:
        return len(path.read_text(encoding="utf-8").splitlines())
    except Exception:
        return 0


def _material_consistency_checks(blueprint, manual_content, ui_blueprint, source_info) -> dict:
    modules = list(blueprint.modules[:8])
    module_titles = _string_terms(module.title for module in modules)
    module_keys = _string_terms(module.key for module in modules)
    business_objects = _string_terms(blueprint.business_objects[:10])
    metrics = _string_terms(blueprint.report_metrics[:10])

    ui_text = _ui_consistency_text(ui_blueprint)
    manual_text, manual_text_source = _manual_consistency_text(blueprint, manual_content)
    source_text = _source_consistency_text(source_info)
    material_text = f"{ui_text}\n{manual_text}"

    module_hits = _term_hits(module_titles, material_text)
    object_hits = _term_hits(business_objects, material_text)
    metric_hits = _term_hits(metrics, material_text)
    ui_module_hits = _term_hits(module_titles, ui_text)
    manual_module_hits = _term_hits(module_titles, manual_text)
    source_name_hits = _term_hits(module_keys, source_text)
    source_title_hits = _term_hits(module_titles, source_text)

    module_target = min(4, len(module_titles))
    domain_target = min(5, len(business_objects) + len(metrics))
    source_target = min(4, len(module_keys))
    domain_hits = object_hits + metric_hits

    return {
        "material_manual_text_source": manual_text_source,
        "material_ui_text_source": getattr(ui_blueprint, "source", "unknown"),
        "material_module_title_hits": module_hits,
        "material_ui_module_title_hits": ui_module_hits,
        "material_manual_module_title_hits": manual_module_hits,
        "material_business_object_hits": object_hits,
        "material_metric_hits": metric_hits,
        "material_domain_term_hits": domain_hits,
        "material_source_module_key_hits": source_name_hits,
        "material_source_module_title_hits": source_title_hits,
        "material_consistency_ready": (
            module_hits >= module_target
            and (domain_target == 0 or domain_hits >= domain_target)
            and source_name_hits >= source_target
        ),
    }


def _ui_project_entry_checks(source_info) -> dict:
    project_entry = source_info.get("ui_project_entry") if isinstance(source_info, dict) else {}
    if not isinstance(project_entry, dict):
        project_entry = {}
    served_dir = Path(str(project_entry.get("served_dir") or ""))
    entry_doc = Path(str(project_entry.get("entry_doc") or ""))
    return {
        "ui_project_entry_exists": bool(project_entry),
        "ui_project_entry_doc_exists": bool(entry_doc) and entry_doc.exists(),
        "ui_project_served_dir_exists": bool(served_dir) and served_dir.exists(),
        "ui_project_served_index_exists": bool(served_dir) and (served_dir / "index.html").exists(),
        "ui_project_entry_url": project_entry.get("entry_url", ""),
        "ui_project_run_command": project_entry.get("run_command", ""),
        "ui_screenshot_render_mode": source_info.get("ui_screenshot_render_mode", "file") if isinstance(source_info, dict) else "file",
        "ui_screenshot_base_url": source_info.get("ui_screenshot_base_url", "") if isinstance(source_info, dict) else "",
        "ui_project_server_started": bool(source_info.get("ui_project_server_started")) if isinstance(source_info, dict) else False,
    }


def _ui_layout_variant(ui_blueprint, ui_screenshots) -> str:
    if getattr(ui_blueprint, "renderer", "") == "game":
        return "game"
    design_brief = getattr(ui_blueprint, "design_brief", {}) or {}
    if design_brief.get("layout_family"):
        return str(design_brief.get("layout_family"))
    dashboard = ui_screenshots.get("dashboard") if isinstance(ui_screenshots, dict) else None
    html_path = getattr(dashboard, "html_path", "") if dashboard else ""
    if not html_path:
        return "classic"
    try:
        html = Path(html_path).read_text(encoding="utf-8")
    except OSError:
        return "classic"
    marker = '<div class="app '
    if marker not in html:
        return "classic"
    return html.split(marker, 1)[1].split('"', 1)[0].strip() or "classic"


def _ui_consistency_text(ui_blueprint) -> str:
    if not ui_blueprint:
        return ""
    parts = [getattr(ui_blueprint, "visual_style", "")]
    for screen in getattr(ui_blueprint, "screens", []):
        parts.extend(
            [
                getattr(screen, "title", ""),
                getattr(screen, "caption", ""),
                " ".join(str(item) for item in getattr(screen, "components", []) if item),
                json.dumps(getattr(screen, "sample_data", {}) or {}, ensure_ascii=False),
            ]
        )
    return "\n".join(str(item) for item in parts if item)


def _manual_consistency_text(blueprint, manual_content) -> tuple[str, str]:
    if manual_content:
        return json.dumps({key: value for key, value in manual_content.items() if key != "_warnings"}, ensure_ascii=False), "llm-content"

    parts = [
        blueprint.purpose,
        blueprint.summary,
        blueprint.scenario,
        blueprint.positioning,
        " ".join(blueprint.business_objects),
        " ".join(blueprint.report_metrics),
        " ".join(blueprint.quality_rules),
        " ".join(blueprint.data_relations),
    ]
    for module in blueprint.modules:
        parts.extend(
            [
                module.title,
                module.description,
                " ".join(module.operations),
                " ".join(module.data_fields),
                " ".join(module.rules),
            ]
        )
    return "\n".join(str(item) for item in parts if item), "local-template-derived"


def _source_consistency_text(source_info) -> str:
    parts = [json.dumps(source_info or {}, ensure_ascii=False)]
    blueprint_path = (source_info or {}).get("blueprint_path") if isinstance(source_info, dict) else None
    if blueprint_path:
        try:
            parts.append(Path(blueprint_path).read_text(encoding="utf-8"))
        except OSError:
            pass
    return "\n".join(parts)


def _generation_quality_profile() -> str:
    import os

    value = os.getenv("SOFT_GENERATION_PROFILE", "").strip().lower()
    if value in {"fast", "speed", "batch"}:
        return "fast"
    return "authenticity-first"


def _blueprint_quality_target() -> int:
    import os

    if _generation_quality_profile() != "authenticity-first":
        return 78
    raw = os.getenv("SOFT_BLUEPRINT_QUALITY_FLOOR", "92").strip() or "92"
    try:
        return max(78, min(95, int(raw)))
    except ValueError:
        return 92


def _string_terms(values) -> list[str]:
    terms: list[str] = []
    for value in values:
        if value is None:
            continue
        term = str(value).strip()
        if term:
            terms.append(term)
    return terms


def _term_hits(terms: list[str], text: str) -> int:
    return sum(1 for term in terms if _contains_term(text, term))


def _contains_term(text: str, term: str) -> bool:
    if not text or not term:
        return False
    return term in text or term.lower() in text.lower()
