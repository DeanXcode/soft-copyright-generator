from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str((ROOT / "backend").resolve()))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from softcopyright.generator import generate_materials  # noqa: E402
from softcopyright.llm.provider import build_provider, config_from_env  # noqa: E402
from softcopyright.models import GenerationTask  # noqa: E402


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a GPT quality-first generation review.")
    parser.add_argument("--output-root", default="output-gpt-quality-first-review")
    parser.add_argument("--software-name", default="晚自习作业跟踪与学情干预系统")
    parser.add_argument("--version", default="V1.0")
    parser.add_argument("--language", default="Java")
    parser.add_argument("--product-type", default="教育软件")
    parser.add_argument("--feature-hint", default="晚自习签到、作业批改追踪、学情预警、班主任干预记录")
    parser.add_argument("--randomness", default="高差异")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_local_config()
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "ms-playwright")
    os.environ.setdefault("SOFT_LLM_BATCH_WORKERS", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

    task = GenerationTask(
        software_name=args.software_name,
        version=args.version,
        language=args.language,
        product_type=args.product_type,
        feature_hint=args.feature_hint,
        model_provider="custom",
        model_name=os.environ.get("SOFT_MODEL_GPT_NAME", "gpt-4o-mini"),
        randomness=args.randomness,
        output_root=Path(args.output_root),
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

    def emit(event: dict) -> None:
        safe = dict(event)
        safe.pop("api_key", None)
        print("EVENT_JSON:" + json.dumps(safe, ensure_ascii=False), flush=True)

    report = generate_materials(task, emit=emit, llm_provider=provider)
    checks = report.get("checks", {})
    summary = {
        "zip_path": report.get("zip_path"),
        "output_dir": report.get("task", {}).get("output_dir"),
        "warnings": report.get("warnings", []),
        "blueprint_source": report.get("blueprint_source"),
        "manual_source": report.get("manual_source"),
        "ui_blueprint_source": checks.get("ui_blueprint_source"),
        "ui_renderer": checks.get("ui_renderer"),
        "ui_software_type_match": checks.get("ui_software_type_match"),
        "ui_screenshot_count": checks.get("ui_screenshot_count"),
        "source_total_lines": checks.get("source_total_lines"),
        "blueprint_quality_score": checks.get("blueprint_quality_score"),
        "material_consistency_ready": checks.get("material_consistency_ready"),
        "material_module_title_hits": checks.get("material_module_title_hits"),
        "material_business_object_hits": checks.get("material_business_object_hits"),
        "material_metric_hits": checks.get("material_metric_hits"),
        "material_source_module_key_hits": checks.get("material_source_module_key_hits"),
        "stage_timings": report.get("stage_timings"),
        "total_seconds": report.get("total_seconds"),
    }
    print("RESULT_JSON:" + json.dumps(summary, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
