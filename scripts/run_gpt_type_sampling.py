from __future__ import annotations

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

from softcopyright.generator import _material_consistency_checks  # noqa: E402
from softcopyright.llm.provider import build_provider, config_from_env  # noqa: E402
from softcopyright.llm_blueprint import generate_blueprint_with_llm  # noqa: E402
from softcopyright.models import GenerationTask  # noqa: E402
from softcopyright.packager import write_json  # noqa: E402
from softcopyright.screenshots import generate_ui_screenshots  # noqa: E402
from softcopyright.sourcegen import generate_source_project, source_project_stats  # noqa: E402
from softcopyright.ui_blueprint import ui_matches_software_type  # noqa: E402


SAMPLES = [
    {
        "key": "finance",
        "software_name": "社区小微贷款风险巡检系统",
        "product_type": "金融软件",
        "feature_hint": "商户授信、贷后走访、还款异常、风险预警、复核处置",
        "language": "Java",
    },
    {
        "key": "medical",
        "software_name": "门诊慢病随访处方核验系统",
        "product_type": "医疗软件",
        "feature_hint": "慢病随访、复诊提醒、处方核验、异常指标、医生回访",
        "language": "Java",
    },
    {
        "key": "game",
        "software_name": "星糖岛消除冒险",
        "product_type": "游戏软件",
        "feature_hint": "三消关卡、糖果棋盘、步数目标、道具背包、星级结算",
        "language": "C#",
    },
]


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


def sample_task(sample: dict, output_root: Path) -> dict:
    task = GenerationTask(
        software_name=sample["software_name"],
        version="V1.0",
        language=sample["language"],
        product_type=sample["product_type"],
        feature_hint=sample["feature_hint"],
        model_provider="custom",
        model_name=os.environ.get("SOFT_MODEL_GPT_NAME", "gpt-4o-mini"),
        randomness="高差异",
        output_root=output_root,
    )
    llm_config = config_from_env(
        provider="custom",
        model=task.model_name,
        base_url=os.environ.get("SOFT_MODEL_GPT_BASE_URL", ""),
        api_key=os.environ.get("SOFT_MODEL_GPT_API_KEY", ""),
    )
    task.llm_base_url = llm_config.base_url
    task.llm_api_key_configured = bool(llm_config.api_key)
    provider = build_provider(llm_config)

    started_at = time.perf_counter()
    events: list[dict] = []

    def emit(stage: str, progress: int, message: str, **extra) -> None:
        event = {"stage": stage, "progress": progress, "message": message, **extra}
        events.append(event)
        print("EVENT_JSON:" + json.dumps(event, ensure_ascii=False), flush=True)

    output_dir = task.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    trace_path = output_dir / "llm_trace.jsonl"
    previous_trace_path = os.environ.get("SOFT_LLM_TRACE_PATH")
    os.environ["SOFT_LLM_TRACE_PATH"] = str(trace_path)

    try:
        blueprint = generate_blueprint_with_llm(
            task,
            provider,
            emit=lambda progress, message, **extra: emit("blueprint", progress, message, **extra),
        )
        if blueprint is None:
            raise RuntimeError(f"{task.software_name} GPT 蓝图未生成")
        source_info = generate_source_project(task, blueprint, output_dir)
        ui_screenshots, warnings, ui_blueprint = generate_ui_screenshots(
            task,
            blueprint,
            output_dir,
            provider,
            source_info=source_info,
            emit=lambda progress, message, **extra: emit("screenshots", progress, message, **extra),
        )
    except Exception as exc:
        failure = {
            "task": task.to_dict(),
            "sample_key": sample.get("key", ""),
            "error_type": type(exc).__name__,
            "error": str(exc),
            "events": events,
            "trace_path": str(trace_path),
            "total_seconds": round(time.perf_counter() - started_at, 2),
        }
        write_json(output_dir / "type_sampling_failure.json", failure)
        raise
    finally:
        if previous_trace_path is None:
            os.environ.pop("SOFT_LLM_TRACE_PATH", None)
        else:
            os.environ["SOFT_LLM_TRACE_PATH"] = previous_trace_path
    source_info.update(source_project_stats(Path(source_info["source_dir"])))

    dimensions = [(item.width, item.height) for item in ui_screenshots.values() if item.width and item.height]
    layout_variant = _layout_variant(ui_screenshots, ui_blueprint.renderer)
    checks = {
        "blueprint_source": "llm",
        "blueprint_quality_score": blueprint.quality_score,
        "blueprint_business_object_count": len(blueprint.business_objects),
        "blueprint_workflow_count": len(blueprint.workflows),
        "blueprint_metric_count": len(blueprint.report_metrics),
        "blueprint_module_detail_ready": all(
            bool(module.operations) and bool(module.data_fields) and bool(module.rules)
            for module in blueprint.modules
        ),
        "ui_blueprint_source": ui_blueprint.source,
        "ui_renderer": ui_blueprint.renderer,
        "ui_layout_variant": layout_variant,
        "ui_software_type_match": ui_matches_software_type(task, blueprint, ui_blueprint),
        "ui_screenshot_count": sum(1 for item in ui_screenshots.values() if item.image_path),
        "source_total_lines": int(source_info["total_lines"]),
    }
    if ui_blueprint.renderer == "game":
        checks["ui_mobile_portrait_match"] = bool(dimensions) and all(
            height > width and abs((width / height) - (9 / 16)) < 0.02
            for width, height in dimensions
        )
    else:
        checks["ui_admin_desktop_match"] = bool(dimensions) and all(
            width >= 1200 and height >= 800 and width > height
            for width, height in dimensions
        )
    checks.update(_material_consistency_checks(blueprint, None, ui_blueprint, source_info))

    report = {
        "task": task.to_dict(),
        "warnings": warnings,
        "checks": checks,
        "blueprint": blueprint.to_dict(),
        "source": source_info,
        "ui_blueprint": ui_blueprint.to_dict(),
        "ui_layout_variant": layout_variant,
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
        "trace_path": str(trace_path),
        "total_seconds": round(time.perf_counter() - started_at, 2),
    }
    write_json(output_dir / "type_sampling_report.json", report)
    return {
        "software_name": task.software_name,
        "product_type": task.product_type,
        "output_dir": str(output_dir),
        "warnings": warnings,
        "checks": checks,
        "module_titles": [module.title for module in blueprint.modules],
        "screen_titles": [screen.title for screen in ui_blueprint.screens],
        "ui_layout_variant": layout_variant,
        "ui_prototype_dir": source_info.get("ui_prototype_dir", ""),
        "trace_path": str(trace_path),
        "total_seconds": report["total_seconds"],
    }


def main() -> int:
    load_local_config()
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "ms-playwright")
    os.environ.setdefault("SOFT_LLM_BATCH_WORKERS", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

    output_root = Path("output-gpt-type-sampling-review")
    results = []
    for sample in _selected_samples():
        result = sample_task(sample, output_root)
        results.append(result)
        print("SAMPLE_JSON:" + json.dumps(result, ensure_ascii=False), flush=True)
    summary_path = write_json(output_root / "type_sampling_summary.json", {"results": results})
    print(
        "RESULT_JSON:"
        + json.dumps({"summary_path": str(summary_path), "results": results}, ensure_ascii=False),
        flush=True,
    )
    return 0


def _selected_samples() -> list[dict]:
    raw = os.environ.get("SOFT_GPT_TYPE_SAMPLES", "").strip()
    if not raw:
        return SAMPLES
    requested = {item.strip().lower() for item in raw.split(",") if item.strip()}
    return [
        sample
        for sample in SAMPLES
        if sample.get("key", "").lower() in requested
        or sample.get("product_type", "").lower() in requested
        or sample.get("software_name", "").lower() in requested
    ]


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


if __name__ == "__main__":
    raise SystemExit(main())
