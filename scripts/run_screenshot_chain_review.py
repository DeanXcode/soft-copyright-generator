from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str((ROOT / "backend").resolve()))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from softcopyright.blueprint import generate_blueprint  # noqa: E402
from softcopyright.generator import _material_consistency_checks  # noqa: E402
from softcopyright.llm.provider import build_provider, config_from_env  # noqa: E402
from softcopyright.llm_blueprint import generate_blueprint_with_llm  # noqa: E402
from softcopyright.models import GenerationTask  # noqa: E402
from softcopyright.packager import write_json  # noqa: E402
from softcopyright.screenshots import generate_ui_screenshots  # noqa: E402
from softcopyright.sourcegen import generate_source_project, source_project_stats  # noqa: E402
from softcopyright.ui_blueprint import ui_matches_software_type  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate source + UI prototype + screenshots without Word/PDF packaging.")
    parser.add_argument("--task-file", help="UTF-8 JSON task file. Prefer this when task text contains Chinese.")
    parser.add_argument("--output-root", default="output-screenshot-chain-review")
    parser.add_argument("--model-provider", default="local-template", help="local-template or gpt/custom/openai-compatible.")
    parser.add_argument("--software-name", default="Screenshot Chain Review System")
    parser.add_argument("--version", default="V1.0")
    parser.add_argument("--language", default="Java")
    parser.add_argument("--product-type", default="智慧城市软件")
    parser.add_argument("--feature-hint", default="材料生成、界面截图、原型路由、验收报告")
    parser.add_argument("--randomness", default="高差异")
    parser.add_argument("--project-server", action="store_true", help="Start the generated project and capture screenshots from its local HTTP URL when supported.")
    return parser.parse_args()


def load_local_config() -> None:
    config: dict = {}
    for candidate in [ROOT / "config" / "desktop.local.json", ROOT / "config" / "production.json"]:
        if not candidate.exists():
            continue
        data = json.loads(candidate.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            config.update(data)
    for key, value in config.items():
        if isinstance(value, str):
            os.environ[key] = value


def load_task_spec(args: argparse.Namespace) -> dict:
    spec: dict = {}
    if args.task_file:
        task_file = Path(args.task_file)
        if not task_file.is_absolute():
            task_file = ROOT / task_file
        spec = json.loads(task_file.read_text(encoding="utf-8"))
        if not isinstance(spec, dict):
            raise ValueError("--task-file must contain a JSON object")
    return spec


def build_task(args: argparse.Namespace, spec: dict) -> GenerationTask:
    seed = spec.get("seed")
    model_provider = _normalize_provider(str(spec.get("model_provider") or args.model_provider))
    default_model_name = os.environ.get("SOFT_MODEL_GPT_NAME", "gpt-4o-mini") if _uses_llm(model_provider) else "template-v1"
    kwargs = {
        "software_name": str(spec.get("software_name") or args.software_name),
        "version": str(spec.get("version") or args.version),
        "language": str(spec.get("language") or args.language),
        "product_type": str(spec.get("product_type") or args.product_type),
        "feature_hint": str(spec.get("feature_hint") or args.feature_hint),
        "model_provider": model_provider,
        "model_name": str(spec.get("model_name") or default_model_name),
        "randomness": str(spec.get("randomness") or args.randomness),
        "output_root": Path(str(spec.get("output_root") or args.output_root)),
    }
    if seed:
        kwargs["seed"] = str(seed)
    return GenerationTask(**kwargs)


def main() -> int:
    args = parse_args()
    load_local_config()
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "ms-playwright")
    os.environ.setdefault("SOFT_LLM_BATCH_WORKERS", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

    spec = load_task_spec(args)
    task = build_task(args, spec)
    output_dir = task.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    started_at = time.perf_counter()
    events: list[dict] = []

    def emit(stage: str, progress: int, message: str, **extra) -> None:
        event = {"stage": stage, "progress": progress, "message": message, **extra}
        events.append(event)
        print("EVENT_JSON:" + json.dumps(event, ensure_ascii=False), flush=True)

    provider = None
    blueprint_source = "local-template"
    trace_path = output_dir / "llm_trace.jsonl"
    previous_trace_path = os.environ.get("SOFT_LLM_TRACE_PATH")
    try:
        if _uses_llm(task.model_provider):
            os.environ["SOFT_LLM_TRACE_PATH"] = str(trace_path)
            llm_config = config_from_env(
                provider=task.model_provider,
                model=task.model_name,
                base_url=os.environ.get("SOFT_MODEL_GPT_BASE_URL", ""),
                api_key=os.environ.get("SOFT_MODEL_GPT_API_KEY", ""),
            )
            task.llm_api_key_configured = bool(llm_config.api_key)
            provider = build_provider(llm_config)
            blueprint = generate_blueprint_with_llm(
                task,
                provider,
                emit=lambda progress, message, **extra: emit("blueprint", progress, message, **extra),
            )
            if blueprint is None:
                raise RuntimeError("GPT blueprint was not generated")
            blueprint_source = "llm"
        else:
            blueprint = generate_blueprint(task)

        emit("source", 32, "生成源码项目")
        source_info = generate_source_project(task, blueprint, output_dir)
        emit("screenshots", 40, "生成 UI 原型和界面截图")
        ui_screenshots, warnings, ui_blueprint = generate_ui_screenshots(
            task,
            blueprint,
            output_dir,
            provider,
            source_info=source_info,
            emit=lambda progress, message, **extra: emit("screenshots", progress, message, **extra),
            use_project_server=bool(spec.get("project_server") or args.project_server),
        )
        source_info.update(source_project_stats(Path(source_info["source_dir"])))
    except Exception as exc:
        failure = {
            "task": _safe_task_dict(task),
            "error_type": type(exc).__name__,
            "error": str(exc),
            "events": events,
            "trace_path": str(trace_path) if trace_path.exists() else "",
            "total_seconds": round(time.perf_counter() - started_at, 2),
        }
        write_json(output_dir / "screenshot_chain_failure.json", failure)
        raise
    finally:
        if previous_trace_path is None:
            os.environ.pop("SOFT_LLM_TRACE_PATH", None)
        else:
            os.environ["SOFT_LLM_TRACE_PATH"] = previous_trace_path

    checks = _checks(task, blueprint, blueprint_source, ui_blueprint, ui_screenshots, source_info)
    checks.update(_material_consistency_checks(blueprint, None, ui_blueprint, source_info))
    report = {
        "task": _safe_task_dict(task),
        "warnings": warnings,
        "checks": checks,
        "blueprint_source": blueprint_source,
        "blueprint": blueprint.to_dict(),
        "source": source_info,
        "ui_blueprint": ui_blueprint.to_dict(),
        "ui_prototype_dir": source_info.get("ui_prototype_dir", ""),
        "ui_screenshots": {
            key: {
                "title": item.title,
                "caption": item.caption,
                "html_path": item.html_path,
                "image_path": item.image_path,
                "width": item.width,
                "height": item.height,
            }
            for key, item in ui_screenshots.items()
        },
        "events": events,
        "trace_path": str(trace_path) if trace_path.exists() else "",
        "total_seconds": round(time.perf_counter() - started_at, 2),
    }
    report_path = write_json(output_dir / "screenshot_chain_report.json", report)
    summary = {
        "output_dir": str(output_dir),
        "report_path": str(report_path),
        "ui_prototype_dir": source_info.get("ui_prototype_dir", ""),
        "warnings": warnings,
        "checks": checks,
        "total_seconds": report["total_seconds"],
    }
    print("RESULT_JSON:" + json.dumps(summary, ensure_ascii=False), flush=True)
    return 0


def _checks(
    task: GenerationTask,
    blueprint,
    blueprint_source: str,
    ui_blueprint,
    ui_screenshots: dict,
    source_info: dict,
) -> dict:
    dimensions = [(item.width, item.height) for item in ui_screenshots.values() if item.width and item.height]
    prototype_dir = Path(str(source_info.get("ui_prototype_dir") or ""))
    project_entry = source_info.get("ui_project_entry") if isinstance(source_info, dict) else {}
    served_dir = Path(str(project_entry.get("served_dir") or "")) if isinstance(project_entry, dict) else Path("")
    entry_doc = Path(str(project_entry.get("entry_doc") or "")) if isinstance(project_entry, dict) else Path("")
    checks = {
        "blueprint_source": blueprint_source,
        "blueprint_quality_score": blueprint.quality_score,
        "ui_blueprint_source": ui_blueprint.source,
        "ui_renderer": ui_blueprint.renderer,
        "ui_layout_variant": _layout_variant(ui_screenshots, ui_blueprint.renderer),
        "ui_software_type_match": ui_matches_software_type(task, blueprint, ui_blueprint),
        "ui_screenshot_count": sum(1 for item in ui_screenshots.values() if item.image_path),
        "source_total_lines": int(source_info.get("total_lines") or 0),
        "source_line_target_met": int(source_info.get("total_lines") or 0) >= 3000,
        "prototype_dir_exists": prototype_dir.exists(),
        "prototype_index_exists": (prototype_dir / "index.html").exists(),
        "prototype_readme_exists": (prototype_dir / "README.md").exists(),
        "prototype_manifest_exists": (prototype_dir / "prototype-manifest.json").exists(),
        "ui_project_entry_exists": bool(project_entry),
        "ui_project_entry_doc_exists": bool(entry_doc) and entry_doc.exists(),
        "ui_project_served_dir_exists": bool(served_dir) and served_dir.exists(),
        "ui_project_served_index_exists": bool(served_dir) and (served_dir / "index.html").exists(),
        "ui_project_entry_url": project_entry.get("entry_url", "") if isinstance(project_entry, dict) else "",
        "ui_project_run_command": project_entry.get("run_command", "") if isinstance(project_entry, dict) else "",
        "ui_screenshot_render_mode": source_info.get("ui_screenshot_render_mode", "file") if isinstance(source_info, dict) else "file",
        "ui_screenshot_base_url": source_info.get("ui_screenshot_base_url", "") if isinstance(source_info, dict) else "",
        "ui_project_server_started": bool(source_info.get("ui_project_server_started")) if isinstance(source_info, dict) else False,
    }
    if ui_blueprint.renderer == "game":
        checks["ui_screenshot_aspect_ratio"] = "9:16"
        checks["ui_mobile_portrait_match"] = bool(dimensions) and all(
            height > width and abs((width / height) - (9 / 16)) < 0.02
            for width, height in dimensions
        )
        checks["ui_game_board_screen_count"] = sum(
            1 for screen in ui_blueprint.screens if getattr(screen, "view_type", "") == "game_board"
        )
    else:
        checks["ui_screenshot_aspect_ratio"] = "desktop"
        checks["ui_admin_desktop_match"] = bool(dimensions) and all(
            width >= 1200 and height >= 800 and width > height
            for width, height in dimensions
        )
    return checks


def _layout_variant(ui_screenshots: dict, renderer: str) -> str:
    if renderer == "game":
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


def _uses_llm(provider: str) -> bool:
    return _normalize_provider(provider) not in {"", "local", "local-template", "template"}


def _normalize_provider(provider: str) -> str:
    lowered = (provider or "").strip().lower()
    if lowered in {"gpt", "newapi", "openai-compatible"}:
        return "custom"
    return lowered or "local-template"


def _safe_task_dict(task: GenerationTask) -> dict:
    data = task.to_dict()
    data.pop("llm_base_url", None)
    data.pop("llm_api_key", None)
    return data


if __name__ == "__main__":
    raise SystemExit(main())
