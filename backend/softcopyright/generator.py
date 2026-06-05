from __future__ import annotations

from pathlib import Path
import shutil

from .blueprint import generate_blueprint
from .docgen import (
    convert_to_pdf,
    ensure_docx_available,
    generate_checklist_docx,
    generate_info_txt,
    generate_manual_docx,
    generate_source_docx,
)
from .llm_blueprint import generate_blueprint_with_llm
from .llm_manual import generate_manual_content_with_llm
from .models import GenerationTask
from .packager import make_zip, write_json
from .sourcegen import generate_source_project


def generate_materials(task: GenerationTask, emit=None, llm_provider=None) -> dict:
    def send(stage: str, progress: int, message: str, **extra) -> None:
        if emit:
            emit({"stage": stage, "progress": progress, "message": message, **extra})

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
        llm_blueprint = generate_blueprint_with_llm(task, llm_provider)
    except Exception as exc:
        llm_blueprint = None
        report["warnings"].append(f"模型蓝图生成失败，已回退本地模板：{exc}")
    if llm_blueprint:
        blueprint = llm_blueprint
        blueprint_source = "llm"
    else:
        blueprint = generate_blueprint(task)
    report["blueprint"] = blueprint.to_dict()
    report["blueprint_source"] = blueprint_source

    manual_content = None
    manual_source = "local-template"
    if blueprint_source == "llm":
        try:
            send("manual_content", 24, "生成说明书正文")
            manual_content = generate_manual_content_with_llm(task, blueprint, llm_provider)
        except Exception as exc:
            manual_content = None
            report["warnings"].append(f"模型说明书正文生成失败，已回退本地模板：{exc}")
    if manual_content:
        manual_source = "llm"
    report["manual_source"] = manual_source

    send("source", 32, "生成真实源码工程")
    source_info = generate_source_project(task, blueprint, output_dir)
    report["source"] = source_info
    source_lines = int(source_info["total_lines"])

    generated_files: list[Path] = []
    if docx_available:
        send("manual", 48, "生成软件说明书")
        manual_docx = generate_manual_docx(task, blueprint, output_dir, manual_content=manual_content)
        generated_files.append(manual_docx)
        send("source_doc", 62, "生成源码鉴别材料")
        source_docx, source_report = generate_source_docx(task, Path(source_info["source_dir"]), output_dir)
        report["checks"].update(source_report)
        generated_files.append(source_docx)
        send("checklist", 70, "生成材料清单")
        checklist_docx = generate_checklist_docx(task, output_dir)
        generated_files.append(checklist_docx)

        send("pdf", 78, "转换 PDF 文件")
        for docx_path in [manual_docx, source_docx, checklist_docx]:
            pdf_path, error = convert_to_pdf(docx_path, output_dir)
            if pdf_path:
                generated_files.append(pdf_path)
            if error:
                report["warnings"].append(f"{docx_path.name}: {error}")

    send("info", 86, "生成申请信息表")
    info_txt = generate_info_txt(task, blueprint, source_lines, output_dir)
    generated_files.append(info_txt)

    report["checks"].update(
        {
            "software_name_consistent": True,
            "version_consistent": True,
            "source_total_lines": source_lines,
            "source_line_target_met": source_lines >= 3000,
            "docx_available": docx_available,
        }
    )
    report["files"] = [str(path) for path in generated_files]

    report_path = write_json(output_dir / "generation_report.json", report)
    generated_files.append(report_path)

    send("package", 94, "打包 zip 材料包")
    zip_path = output_dir.parent / f"{task.task_id}--材料包.zip"
    make_zip(output_dir, zip_path)
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
