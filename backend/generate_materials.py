from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
from types import SimpleNamespace

from softcopyright.domain_profile import build_domain_profile
from softcopyright.errors import sanitize_error_message
from softcopyright.generator import generate_materials
from softcopyright.llm.provider import build_provider, config_from_env
from softcopyright.models import GenerationTask, PRODUCT_TYPES, SOFTWARE_CATEGORIES, SUPPORTED_LANGUAGES
from softcopyright.packager import write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="软著材料一键生成原型")
    parser.add_argument("--name", required=True, help="软件全称")
    parser.add_argument("--version", default="V1.0", help="版本号")
    parser.add_argument("--language", default="自动选择", choices=SUPPORTED_LANGUAGES, help="编程语言；默认按软件名称和类型自动选择技术架构")
    parser.add_argument("--product-type", default="智慧城市软件", choices=PRODUCT_TYPES, help="产品类型/技术特点")
    parser.add_argument("--software-category", default="应用软件", choices=SOFTWARE_CATEGORIES, help="软件分类大类")
    parser.add_argument("--feature-hint", default="", help="100字以内业务补充说明")
    parser.add_argument("--model-provider", default="custom", help="模型供应商；GPT/OpenAI-compatible 为正式生成，local-template 为显式无 token 模板模式")
    parser.add_argument("--model-name", default="gpt-5.5", help="模型名称")
    parser.add_argument("--api-base-url", default="", help="OpenAI-compatible API Base URL")
    parser.add_argument("--api-key", default="", help="API Key；不传时读取环境变量")
    parser.add_argument("--randomness", default="standard", choices=["保守", "standard", "高差异"], help="随机度")
    parser.add_argument("--seed", default="", help="随机种子，不填则自动生成")
    parser.add_argument("--output-root", default="output", help="输出目录")
    parser.add_argument("--resume-output-dir", default="", help="从未完成输出目录继续生成")
    parser.add_argument("--confirmed-outline-json", default="", help="已确认蓝图 JSON 文件路径")
    parser.add_argument("--accepted-blueprint-json", default="", help="已通过正式质量门禁的完整产品蓝图 JSON 文件路径")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    task = GenerationTask(
        software_name=args.name,
        version=args.version,
        language=args.language,
        product_type=args.product_type,
        software_category=args.software_category,
        feature_hint=args.feature_hint,
        model_provider=args.model_provider,
        model_name=args.model_name,
        randomness=args.randomness,
        output_root=Path(args.output_root),
        accepted_blueprint_path=args.accepted_blueprint_json,
        resume_output_dir=args.resume_output_dir,
        resume_existing_output=bool(str(args.resume_output_dir or "").strip()),
    )
    if args.seed:
        task.seed = args.seed
    elif args.resume_output_dir:
        recovered_seed = _seed_from_output_dir(args.resume_output_dir)
        if recovered_seed:
            task.seed = recovered_seed
    if args.confirmed_outline_json:
        try:
            task.confirmed_outline = json.loads(Path(args.confirmed_outline_json).read_text(encoding="utf-8-sig"))
        except Exception as exc:
            print(f"错误：已确认蓝图 JSON 读取失败：{exc}", file=sys.stderr)
            return 2
    elif args.resume_output_dir:
        task.confirmed_outline = _confirmed_outline_from_resume_dir(Path(args.resume_output_dir))

    configure_generation_runtime(task)

    llm_config = config_from_env(
        provider=args.model_provider,
        model=args.model_name,
        base_url=args.api_base_url,
        api_key=args.api_key,
    )
    task.llm_base_url = llm_config.base_url
    task.llm_api_key_configured = bool(llm_config.api_key)

    def emit(event: dict) -> None:
        print("EVENT_JSON:" + json.dumps(event, ensure_ascii=True), flush=True)

    provider = build_provider(llm_config)
    try:
        report = generate_materials(task, emit=emit, llm_provider=provider)
    except Exception as exc:
        error_message = sanitize_error_message(exc)
        print(f"错误：{error_message}", file=sys.stderr)
        failure_checks = _collect_failure_checks(task.output_dir, task=task)
        _write_failure_report(task.output_dir, error_message, failure_checks)
        print(
            "RESULT_JSON:"
            + json.dumps(
                {
                    "zip_path": "",
                    "output_dir": str(task.output_dir),
                    "warnings": [error_message],
                    "checks": failure_checks,
                    "files": [],
                    "validation": {},
                    "blueprint_source": "gpt",
                    "manual_source": "gpt",
                    "technical_architecture": {},
                    "seed": task.seed,
                    "randomness": task.randomness,
                    "feature_hint": task.feature_hint,
                    "feature_hint_meta": getattr(task, "semantic_contract", {}) or {},
                    "message": error_message,
                },
                ensure_ascii=True,
            ),
            flush=True,
        )
        return 1
    print(f"生成完成：{report['zip_path']}")
    print(
        "RESULT_JSON:"
        + json.dumps(
            {
                "zip_path": report["zip_path"],
                "output_dir": report["task"].get("output_dir"),
                "warnings": report.get("warnings", []),
                "checks": report.get("checks", {}),
                "files": report.get("files", []),
                "validation": report.get("validation", {}),
                "blueprint_source": report.get("blueprint_source", "gpt"),
                "manual_source": report.get("manual_source", "gpt"),
                "technical_architecture": report.get("technical_architecture", {}),
                "seed": report["task"].get("seed", ""),
                "randomness": report["task"].get("randomness", ""),
                "feature_hint": report["task"].get("feature_hint", ""),
                "feature_hint_meta": report.get("feature_hint", {}),
            },
            ensure_ascii=True,
        ),
        flush=True,
    )
    if report.get("warnings"):
        print("警告：")
        for warning in report["warnings"]:
            print(f"- {warning}")
    return 0


def configure_generation_runtime(task: GenerationTask) -> None:
    os.environ.setdefault("SOFT_GENERATION_PROFILE", "balanced")
    os.environ.setdefault("SOFT_LLM_BATCH_WORKERS", "2")
    os.environ.setdefault("SOFT_LLM_RETRY_COUNT", "3")
    os.environ.setdefault("SOFT_LLM_IMAGE_RETRY_COUNT", "3")
    os.environ.setdefault("SOFT_LLM_AI_FRONTEND_TIMEOUT_SECONDS", "220")
    if not os.getenv("SOFT_LLM_TRACE_PATH", "").strip():
        os.environ["SOFT_LLM_TRACE_PATH"] = str(task.output_dir / "llm_trace.jsonl")


def _write_failure_report(output_dir: Path, message: str, checks: dict) -> None:
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        state_path = output_dir / "generation-state.json"
        if state_path.exists():
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
            except Exception:
                state = {}
        else:
            state = {}
        failure_path = output_dir / "generation-failure.json"
        if failure_path.exists():
            try:
                existing_failure = json.loads(failure_path.read_text(encoding="utf-8"))
            except Exception:
                existing_failure = {}
        else:
            existing_failure = {}
        state_attempt = str(state.get("attempt_id") or "").strip()
        failure_attempt = str(existing_failure.get("attempt_id") or "").strip()
        if state_attempt and failure_attempt and state_attempt != failure_attempt:
            existing_failure = {}
        merged_checks = {}
        if isinstance(existing_failure.get("checks"), dict):
            merged_checks.update(existing_failure.get("checks") or {})
        merged_checks.update(checks or {})
        payload = {
            **existing_failure,
            "schema_version": 2,
            "attempt_id": state_attempt,
            "started_at": str(state.get("started_at") or ""),
            "updated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "resume_source": str(state.get("resume_source") or ""),
            "status": "error",
            "stage": str(state.get("stage") or existing_failure.get("stage") or "error"),
            "progress": int(state.get("progress") or existing_failure.get("progress") or 0),
            "failed_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "message": sanitize_error_message(message, limit=1000),
            "checks": merged_checks,
        }
        write_json(failure_path, payload)
        state.update(payload)
        write_json(state_path, state)
    except OSError:
        return


def _seed_from_output_dir(output_dir: str) -> str:
    output_path = Path(str(output_dir or ""))
    for filename in ("generation-state.json", "generation-failure.json", "generation_report.json"):
        try:
            data = json.loads((output_path / filename).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        task_data = data.get("task") if isinstance(data, dict) else None
        seed = str(task_data.get("seed") or "").strip() if isinstance(task_data, dict) else ""
        if seed:
            return seed
    name = output_path.name
    match = re.search(r"(\d{8}-\d{6}-\d{4})$", name)
    return match.group(1) if match else ""


def _confirmed_outline_from_resume_dir(output_dir: Path) -> dict:
    for filename in ("generation_report.json", "generation-state.json", "generation-failure.json"):
        path = output_dir / filename
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        task_data = data.get("task") if isinstance(data, dict) else None
        outline = task_data.get("confirmed_outline") if isinstance(task_data, dict) else None
        if isinstance(outline, dict) and isinstance(outline.get("modules"), list) and outline["modules"]:
            return outline
    blueprint_path = output_dir / "generated_source" / "product-blueprint.json"
    try:
        blueprint = json.loads(blueprint_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        blueprint = {}
    if isinstance(blueprint, dict) and isinstance(blueprint.get("modules"), list) and blueprint["modules"]:
        return blueprint
    return {}


def _collect_failure_checks(output_dir: Path, *, task: GenerationTask | None = None) -> dict:
    checks: dict = _persisted_domain_checks(output_dir)
    if task is not None and not checks.get("ui_domain_profile_key"):
        blueprint = _domain_blueprint_from_output(output_dir)
        profile = build_domain_profile(task, blueprint)
        checks.update(
            {
                "ui_domain_profile_key": profile.key,
                "ui_domain_profile_confidence": profile.confidence,
                "ui_domain_profile_source": profile.source,
                "ui_domain_profile_evidence": "、".join(profile.evidence),
                "ui_domain_profile_weak_evidence": "、".join(profile.weak_evidence),
                "ui_domain_profile_excluded_evidence": "、".join(profile.excluded_evidence),
                "ui_domain_gate_keys": "、".join(profile.enabled_gate_keys),
                "ui_domain_gate_reasons": "；".join(profile.gate_reasons),
                "ui_transport_related": profile.transport_related,
                "ui_route_topology_required": profile.requires_route_topology,
            }
        )
    manifest = _latest_visual_reference_manifest(output_dir)
    if manifest:
        mode = str(manifest.get("mode") or "")
        source = str(manifest.get("source") or "")
        failed_page = str(manifest.get("failed_page_key") or "")
        if not mode and (failed_page == "style_reference" or "style-reference" in source or "style_reference" in source):
            mode = "style_reference"
        if not mode:
            mode = "per_page"
        page_count = int(manifest.get("page_count") or 0)
        if manifest.get("reference_target_count") is not None:
            reference_target_count = int(manifest.get("reference_target_count") or 0)
        else:
            reference_target_count = 1 if mode == "style_reference" else page_count
        style_reference = manifest.get("style_reference") if isinstance(manifest.get("style_reference"), dict) else {}
        applies_to_page_count = int(
            manifest.get("applies_to_page_count")
            or style_reference.get("applies_to_page_count")
            or page_count
            or 0
        )
        checks["ui_visual_prompt_ready"] = bool(manifest.get("prompt_ready", manifest.get("ready")))
        checks["ui_visual_reference_ready"] = bool(manifest.get("ready"))
        checks["ui_visual_reference_mode"] = mode
        checks["ui_visual_reference_source"] = source
        checks["ui_visual_reference_count"] = int(manifest.get("reference_count") or 0)
        checks["ui_visual_reference_target_count"] = reference_target_count
        checks["ui_visual_reference_page_count"] = page_count
        checks["ui_visual_reference_applies_to_page_count"] = applies_to_page_count
        checks["ui_visual_style_reference_ready"] = bool(
            manifest.get("style_reference_ready") or style_reference.get("ready")
        )
        checks["ui_visual_reference_image_model"] = str(manifest.get("image_model") or "")
        checks["ui_visual_reference_retry_count"] = int(manifest.get("image_retry_count") or 0)
        checks["ui_visual_reference_failed_page"] = failed_page
        checks["ui_visual_reference_error"] = sanitize_error_message(manifest.get("error") or "", limit=500)
        checks["ui_visual_reference_directory"] = str(manifest.get("directory") or "")
    return checks


def _persisted_domain_checks(output_dir: Path) -> dict:
    keys = {
        "ui_domain_profile_key",
        "ui_domain_profile_confidence",
        "ui_domain_profile_source",
        "ui_domain_profile_evidence",
        "ui_domain_profile_weak_evidence",
        "ui_domain_profile_excluded_evidence",
        "ui_domain_gate_keys",
        "ui_domain_gate_reasons",
        "ui_transport_related",
        "ui_route_topology_required",
        "ui_route_topology_ready",
        "ui_realism_missing_evidence",
    }
    collected: dict = {}
    for filename in ("generation_report.json", "validation_report.json"):
        try:
            payload = json.loads((output_dir / filename).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        candidates = [payload.get("checks"), payload.get("authenticity")]
        validation = payload.get("validation") if isinstance(payload, dict) else None
        if isinstance(validation, dict):
            candidates.append(validation.get("authenticity"))
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            for key in keys:
                if key in candidate:
                    collected[key] = candidate[key]
    return collected


def _domain_blueprint_from_output(output_dir: Path) -> SimpleNamespace | None:
    path = output_dir / "generated_source" / "product-blueprint.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    modules = [
        SimpleNamespace(title=str(item.get("title") or item.get("name") or ""))
        for item in payload.get("modules", [])
        if isinstance(item, dict)
    ]
    return SimpleNamespace(
        industry=str(payload.get("industry") or ""),
        summary=str(payload.get("summary") or ""),
        scenario=str(payload.get("scenario") or ""),
        positioning=str(payload.get("positioning") or ""),
        business_objects=payload.get("business_objects") if isinstance(payload.get("business_objects"), list) else [],
        modules=modules,
        industry_subtype_key=str(payload.get("industry_subtype_key") or ""),
    )


def _latest_visual_reference_manifest(output_dir: Path) -> dict:
    try:
        candidates = sorted(
            output_dir.rglob("visual-reference-manifest.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return {}
    for path in candidates:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            return data
    return {}


if __name__ == "__main__":
    sys.exit(main())
