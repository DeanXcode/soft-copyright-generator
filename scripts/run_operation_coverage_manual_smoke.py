from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str((ROOT / "backend").resolve()))

from softcopyright.docgen import (  # noqa: E402
    analyze_manual_density,
    analyze_manual_pdf_text_density,
    analyze_manual_ui_consistency,
    analyze_pdf_layout,
    convert_to_pdf,
    generate_manual_docx,
)
from softcopyright.models import GenerationTask  # noqa: E402
from softcopyright.screenshots import _build_page_specs  # noqa: E402
from softcopyright.stage_cache import product_blueprint_from_dict, ui_blueprint_from_dict  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_output", type=Path)
    parser.add_argument("target_output", type=Path)
    args = parser.parse_args()

    source = args.source_output.resolve()
    target = args.target_output.resolve()
    report = json.loads((source / "generation_report.json").read_text(encoding="utf-8"))
    checkpoint = json.loads((source / "ui_screenshots" / "screenshot-checkpoint.json").read_text(encoding="utf-8"))
    blueprint = product_blueprint_from_dict(report["blueprint"])
    ui_blueprint = ui_blueprint_from_dict(report["ui_blueprint"])
    task_data = report["task"]
    task = GenerationTask(
        software_name=task_data["software_name"],
        version=task_data.get("version", "V1.0"),
        language=task_data.get("language", "JavaScript/Java/SQL"),
        product_type=task_data.get("product_type", "应用软件"),
        software_category=task_data.get("software_category", "应用软件"),
        output_root=target,
    )
    task.seed = task_data.get("seed", task.seed)
    pages = _build_page_specs(task, blueprint, source / "ui_screenshots", ui_blueprint)
    checkpoint_pages = checkpoint.get("pages") if isinstance(checkpoint, dict) else {}
    checkpoint_pages = checkpoint_pages if isinstance(checkpoint_pages, dict) else {}
    screenshots = {}
    for item in pages:
        entry = checkpoint_pages.get(item.key) if isinstance(checkpoint_pages, dict) else {}
        entry = entry if isinstance(entry, dict) else {}
        image_path = source / "ui_screenshots" / f"{item.key}.png"
        if not image_path.exists():
            raise FileNotFoundError(image_path)
        item.image_path = str(image_path)
        item.width = int(entry.get("width") or 1280)
        item.height = int(entry.get("height") or 720)
        item.action_crops = dict(entry.get("action_crops") or {})
        item.visible_content_summary = dict(entry.get("visible_content_summary") or {})
        screenshots[item.key] = item

    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    docx_path = generate_manual_docx(
        task,
        blueprint,
        target,
        ui_screenshots=screenshots,
        design_brief=ui_blueprint.design_brief,
    )
    pdf_path, conversion_error = convert_to_pdf(docx_path, target)
    result = {
        "source_output": str(source),
        "target_output": str(target),
        "screenshot_count": len(screenshots),
        "operation_count": sum(1 for item in screenshots.values() if item.page_kind == "operation"),
        "docx_path": str(docx_path),
        "pdf_path": str(pdf_path or ""),
        "conversion_error": conversion_error or "",
        "manual_density": analyze_manual_density(docx_path),
        "manual_ui_consistency": analyze_manual_ui_consistency(docx_path, blueprint, screenshots),
        "pdf_layout": analyze_pdf_layout(pdf_path),
        "pdf_text_density": analyze_manual_pdf_text_density(pdf_path),
    }
    result_path = target / "smoke-result.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if pdf_path and result["manual_ui_consistency"].get("manual_ui_consistency_ready") else 1


if __name__ == "__main__":
    raise SystemExit(main())
