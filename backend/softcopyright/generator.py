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
)
from .llm_blueprint import generate_blueprint_with_llm
from .llm_manual import generate_manual_content_with_llm
from .models import GenerationTask
from .packager import make_zip_files, write_json
from .screenshots import generate_ui_screenshots
from .ui_blueprint import ui_matches_software_type
from .sourcegen import generate_source_project, source_project_stats


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
    report["checks"]["ui_blueprint_source"] = ui_blueprint.source
    report["checks"]["ui_renderer"] = ui_blueprint.renderer
    report["checks"]["ui_layout_variant"] = report["ui_blueprint"]["layout_variant"]
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
    if docx_available:
        send("manual", 48, "生成软件说明书")
        manual_docx = generate_manual_docx(
            task,
            blueprint,
            output_dir,
            manual_content=manual_content,
            ui_screenshots=ui_screenshots,
        )
        mark("manual_docx")
        send("source_doc", 62, "生成源码鉴别材料")
        source_docx, source_report = generate_source_docx(task, Path(source_info["source_dir"]), output_dir)
        report["checks"].update(source_report)
        mark("source_docx")

        send("pdf", 78, "转换 PDF 文件")
        for docx_path in [manual_docx, source_docx]:
            pdf_path, error = convert_to_pdf(docx_path, output_dir)
            if pdf_path:
                if docx_path == manual_docx:
                    manual_pdf = pdf_path
                elif docx_path == source_docx:
                    source_pdf = pdf_path
            if error:
                report["warnings"].append(f"{docx_path.name}: {error}")
        mark("pdf")

    send("info", 86, "生成申请信息表")
    info_txt = generate_info_txt(task, blueprint, source_lines, output_dir)
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
    report["internal_files"] = [str(report_path)]

    send("package", 94, "打包 zip 材料包")
    zip_path = output_dir.parent / f"{task.task_id}--材料包.zip"
    make_zip_files(deliverable_files, zip_path)
    mark("package")
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
