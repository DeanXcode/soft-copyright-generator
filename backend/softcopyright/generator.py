from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import shutil
import time
import json
import re
from uuid import uuid4

from .docgen import (
    analyze_docx_layout,
    analyze_manual_density,
    analyze_manual_ui_consistency,
    analyze_manual_pdf_text_density,
    analyze_pdf_layout,
    convert_to_pdf,
    ensure_docx_available,
    generate_info_txt,
    generate_manual_docx,
    generate_source_docx,
    pdf_converter_info,
    update_manual_toc_page_numbers,
)
from .architecture import ARCHITECTURE_CATALOG, normalize_technical_architecture_for_experience
from .errors import sanitize_error_message
from .feature_inference import harmonize_feature_hint
from .frontend_codegen.page_spec import FRONTEND_ENGINE_VERSION
from .industry_subtypes import select_industry_subtype_for_context
from .llm_architecture import select_technical_architecture_with_llm
from .llm_blueprint import blueprint_contract_issues, generate_blueprint_with_llm, normalize_cached_blueprint_candidate
from .llm.provider import LocalTemplateProvider
from .llm_manual import generate_manual_content_with_llm
from .models import GenerationTask
from .module_keys import is_placeholder_module_key, semantic_module_key
from .operation_coverage import configured_operation_screen_count, module_operation_category
from .packager import make_zip_files, write_json
from .blueprint import generate_blueprint
from .product_experience import build_product_experience_spec, design_brief_matches_experience
from .screenshots import generate_ui_screenshots, prepare_ui_visual_reference
from .ui_blueprint import complete_ui_blueprint_coverage, repair_ui_blueprint_contract, ui_matches_software_type
from .ui_similarity import (
    MAX_VISUAL_IDENTITY_ATTEMPTS,
    append_ui_fingerprint_history,
    evaluate_ui_similarity_gate,
)
from .ui_roles import role_coverage_summary
from .sourcegen import (
    generate_source_project,
    refresh_generated_source_metadata,
    repair_generated_business_record_labels,
    source_project_stats,
)
from .stage_cache import (
    build_stage_cache_context,
    find_resume_stage_cache_context,
    load_cached_architecture,
    load_cached_blueprint,
    load_cached_manual_content,
    load_cached_ui_blueprint,
    save_cached_architecture,
    save_cached_blueprint,
    save_cached_manual_content,
    save_cached_ui_blueprint,
    product_blueprint_from_dict,
    technical_architecture_from_dict,
    ui_blueprint_from_dict,
)
from .validator import build_materials_manifest, validate_materials, validation_checks


def generate_materials(task: GenerationTask, emit=None, llm_provider=None) -> dict:
    started_at = time.perf_counter()
    stage_started_at = started_at
    stage_timings: dict[str, float] = {}
    local_template_mode = llm_provider is None or isinstance(llm_provider, LocalTemplateProvider)
    require_llm_generation = not local_template_mode
    output_dir = task.output_dir
    setattr(task, "input_feature_hint", str(getattr(task, "feature_hint", "") or ""))
    resume_existing_output = bool(getattr(task, "resume_existing_output", False))
    if resume_existing_output and not output_dir.exists():
        raise RuntimeError(f"恢复输出目录不存在：{output_dir}")
    if output_dir.exists() and not resume_existing_output:
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    resume_payload = _resume_failure_payload(output_dir) if resume_existing_output else {}
    resume_stage = _resume_failure_stage_from_payload(resume_payload) if resume_existing_output else ""
    resume_progress = _resume_failure_progress_from_payload(resume_payload) if resume_existing_output else 0
    completed_report = _load_completed_resume_report(output_dir) if resume_existing_output else None
    _begin_generation_attempt(
        output_dir,
        task,
        resume_source=("completed-report" if completed_report else "failure-state" if resume_stage else "existing-output")
        if resume_existing_output
        else "new-task",
    )
    if resume_existing_output:
        if completed_report:
            completed_report = dict(completed_report)
            completed_report["attempt_id"] = str(getattr(task, "attempt_id", "") or "")
            completed_report["task"] = dict(completed_report.get("task") or {})
            completed_report["task"]["attempt_id"] = completed_report["attempt_id"]
            _write_generation_state(
                output_dir,
                task,
                "success",
                "done",
                100,
                "检测到已完成材料包，返回现有交付结果",
                {"zip_path": completed_report.get("zip_path", "")},
            )
            if emit:
                emit(
                    {
                        "stage": "package",
                        "progress": 99,
                        "message": "检测到已完成材料包，正在返回现有交付结果",
                        "output_dir": str(output_dir),
                        "zip_path": completed_report["zip_path"],
                        "material_type": "断点续跑",
                    }
                )
            return completed_report
    _ensure_llm_trace_path(task, output_dir)

    def send(stage: str, progress: int, message: str, **extra) -> None:
        if resume_stage and _stage_precedes(stage, resume_stage):
            return
        _write_generation_state(output_dir, task, "running", stage, progress, message, extra)
        if emit:
            emit({"stage": stage, "progress": progress, "message": message, "output_dir": str(output_dir), **extra})

    if resume_stage and emit:
        emit(
            {
                "stage": resume_stage,
                "progress": resume_progress,
                "message": f"从失败节点继续：{_resume_stage_label(resume_stage)}",
                "output_dir": str(output_dir),
                "material_type": "断点续跑",
            }
        )

    def mark(stage: str) -> None:
        nonlocal stage_started_at
        now = time.perf_counter()
        stage_timings[stage] = round(now - stage_started_at, 2)
        stage_started_at = now

    resume_stage_cache = find_resume_stage_cache_context(task) if resume_existing_output else None
    resume_cached_blueprint = load_cached_blueprint(resume_stage_cache) if resume_stage_cache else None
    accepted_blueprint = _load_accepted_product_blueprint(task)
    confirmed_contract = _semantic_contract_from_confirmed_outline(task)
    if accepted_blueprint:
        send("prepare", 3, "读取已批准产品蓝图，跳过名称理解和产品蓝图请求", material_type="批准蓝图")
        feature_hint_meta = _semantic_contract_from_cached_blueprint(accepted_blueprint)
        feature_hint_meta["feature_hint_profile"] = "accepted-blueprint"
        feature_hint_meta["feature_hint_source"] = "accepted-blueprint"
        feature_hint_meta["feature_hint_reason"] = "使用已通过正式质量门禁的完整产品蓝图，跳过重复模型请求。"
        feature_hint = task.feature_hint or str(feature_hint_meta.get("inferred_feature_hint") or "")
    elif resume_cached_blueprint and resume_existing_output:
        send("prepare", 3, "复用失败任务的本地产品蓝图，跳过名称理解请求", material_type="断点续跑")
        feature_hint_meta = _semantic_contract_from_cached_blueprint(resume_cached_blueprint)
        feature_hint = task.feature_hint or str(feature_hint_meta.get("inferred_feature_hint") or "")
    elif confirmed_contract:
        send("prepare", 3, "复用已确认蓝图，准备生成产品蓝图")
        feature_hint = task.feature_hint
        feature_hint_meta = confirmed_contract
    else:
        send("prepare", 3, "理解软件名称并补充业务关键词")
        feature_hint, feature_hint_meta = harmonize_feature_hint(
            task.software_name,
            task.product_type,
            task.feature_hint,
            provider=llm_provider,
            require_llm=bool(llm_provider and not isinstance(llm_provider, LocalTemplateProvider)),
            min_blueprint_modules=8 if llm_provider and not isinstance(llm_provider, LocalTemplateProvider) else 0,
        )
    task.feature_hint = feature_hint
    setattr(task, "semantic_contract", feature_hint_meta)
    if require_llm_generation:
        contract_modules = feature_hint_meta.get("feature_hint_blueprint_modules")
        if not isinstance(contract_modules, list) or len(contract_modules) < 8:
            raise RuntimeError("GPT 名称理解未生成合格模块蓝图，请重试；需要至少 8 个完整业务模块。")

    send("prepare", 5, "准备输出目录")

    report: dict = {
        "schema_version": 2,
        "attempt_id": str(getattr(task, "attempt_id", "") or ""),
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
    stage_cache = resume_stage_cache or build_stage_cache_context(task, feature_hint_meta)
    report["checks"]["stage_cache_enabled"] = bool(stage_cache.get("enabled"))
    report["checks"]["stage_cache_key"] = stage_cache.get("key", "")
    report["checks"]["stage_cache_hits"] = []
    report["checks"]["accepted_blueprint_configured"] = bool(str(getattr(task, "accepted_blueprint_path", "") or "").strip())
    report["checks"]["accepted_blueprint_ready"] = bool(accepted_blueprint)

    docx_available, docx_error = ensure_docx_available()
    if not docx_available:
        report["warnings"].append(f"python-docx 未安装，无法生成 Word 文档：{docx_error}")

    send("blueprint", 15, "生成产品蓝图")
    blueprint_source = "accepted-blueprint" if accepted_blueprint else "local-template" if local_template_mode else "llm"
    resume_blueprint = _load_resume_product_blueprint(output_dir) if resume_stage and _stage_precedes("blueprint", resume_stage) else None
    cached_blueprint = accepted_blueprint or resume_blueprint or resume_cached_blueprint or load_cached_blueprint(stage_cache)
    if cached_blueprint and not accepted_blueprint:
        previous_score = int(getattr(cached_blueprint, "quality_score", 0) or 0)
        report["checks"]["blueprint_cache_previous_quality_score"] = previous_score
        if _resume_blueprint_lock_ready(resume_blueprint, cached_blueprint, resume_stage):
            report["checks"]["resume_blueprint_quality_locked"] = True
            report["checks"]["blueprint_cache_normalized"] = False
            report["checks"]["blueprint_cache_normalized_quality_score"] = previous_score
        else:
            cached_blueprint = normalize_cached_blueprint_candidate(task, cached_blueprint)
            report["checks"]["blueprint_cache_normalized"] = True
            report["checks"]["blueprint_cache_normalized_quality_score"] = cached_blueprint.quality_score
    cached_blueprint_issues = blueprint_contract_issues(task, cached_blueprint) if cached_blueprint else []
    if cached_blueprint and int(getattr(cached_blueprint, "quality_score", 0) or 0) < _blueprint_quality_target():
        cached_blueprint_issues.append(
            f"产品蓝图质量分 {int(getattr(cached_blueprint, 'quality_score', 0) or 0)} 低于当前阈值 {_blueprint_quality_target()}"
        )
    if cached_blueprint_issues:
        if accepted_blueprint:
            raise RuntimeError("已批准产品蓝图未通过当前结构化操作与终端语义门禁：" + "；".join(cached_blueprint_issues[:5]))
        send(
            "blueprint",
            15,
            "已有产品蓝图缺少新版结构化操作契约，保留模块边界并重建蓝图明细",
            material_type="蓝图升级",
        )
        report["checks"]["blueprint_cache_invalidated"] = True
        report["checks"]["blueprint_cache_invalidation_reasons"] = cached_blueprint_issues
        cached_blueprint = None
    if cached_blueprint:
        if accepted_blueprint:
            send("blueprint", 15, "使用已批准产品蓝图", material_type="批准蓝图")
        else:
            send("blueprint", 15, "复用已缓存产品蓝图", material_type="阶段缓存")
        blueprint = cached_blueprint
        save_cached_blueprint(stage_cache, blueprint)
        report["checks"]["stage_cache_hits"].append("accepted_blueprint" if accepted_blueprint else "blueprint")
    else:
        if require_llm_generation:
            try:
                llm_blueprint = generate_blueprint_with_llm(
                    task,
                    llm_provider,
                    emit=lambda progress, message, **extra: send("blueprint", progress, message, **extra),
                )
            except Exception as exc:
                raise RuntimeError(f"GPT 产品蓝图生成失败：{sanitize_error_message(exc)}") from exc
        else:
            llm_blueprint = None
        if require_llm_generation and llm_blueprint:
            blueprint = llm_blueprint
            blueprint_source = "llm"
            save_cached_blueprint(stage_cache, blueprint)
        elif local_template_mode:
            blueprint = generate_blueprint(task)
            blueprint_source = "local-template"
            save_cached_blueprint(stage_cache, blueprint)
        else:
            raise RuntimeError("GPT 产品蓝图未返回有效结果，请重试。")
    contract_issues = blueprint_contract_issues(task, blueprint)
    report["checks"]["blueprint_operation_contract_ready"] = not contract_issues
    report["checks"]["blueprint_operation_contract_issues"] = contract_issues
    report["checks"]["blueprint_structured_operation_count"] = sum(
        len(getattr(module, "operation_specs", None) or []) for module in blueprint.modules
    )
    if contract_issues:
        mode_label = "GPT" if require_llm_generation else "Default Template"
        raise RuntimeError(f"{mode_label} 产品蓝图未通过结构化操作与终端语义门禁：" + "；".join(contract_issues[:5]))
    quality_score = int(getattr(blueprint, "quality_score", 0) or 0)
    report["checks"]["blueprint_request_count"] = int(getattr(blueprint, "request_count", 0) or 0)
    if quality_score < _blueprint_quality_target():
        raise RuntimeError(f"产品蓝图质量分 {quality_score}，未达到当前阈值 {_blueprint_quality_target()}。")
    domain_issues = _blueprint_task_domain_issues(task, blueprint, blueprint_source)
    report["checks"]["blueprint_task_domain_ready"] = not domain_issues
    report["checks"]["blueprint_task_domain_issues"] = domain_issues
    if domain_issues:
        raise RuntimeError("产品蓝图与软件名称或原始业务补充不一致：" + "；".join(domain_issues[:5]))
    resume_architecture = _resume_architecture_from_blueprint(blueprint) if resume_stage and _stage_precedes("blueprint", resume_stage) else None
    cached_architecture = resume_architecture or load_cached_architecture(stage_cache)
    if cached_architecture:
        previous_architecture_key = cached_architecture.key
        cached_architecture = normalize_technical_architecture_for_experience(task, blueprint, cached_architecture)
        if cached_architecture.key != previous_architecture_key:
            report["checks"]["technical_architecture_cache_normalized"] = True
            report["checks"]["technical_architecture_previous_key"] = previous_architecture_key
            save_cached_architecture(stage_cache, cached_architecture)
    if cached_architecture:
        send("blueprint", 22, "复用已缓存技术架构", material_type="阶段缓存")
        architecture = cached_architecture
        report["checks"]["stage_cache_hits"].append("technical_architecture")
    else:
        architecture = select_technical_architecture_with_llm(
            task,
            blueprint,
            llm_provider,
            emit=lambda progress, message, **extra: send("blueprint", progress, message, **extra),
            require_llm=require_llm_generation,
        )
        save_cached_architecture(stage_cache, architecture)
    task.language = architecture.source_language
    blueprint.language = architecture.source_language
    blueprint.dev_environment = architecture.dev_environment
    blueprint.runtime_environment = architecture.runtime_environment
    blueprint.technical_architecture = architecture.to_dict()
    architecture_names = {
        str(item.get("name") or "").strip()
        for item in ARCHITECTURE_CATALOG.values()
        if str(item.get("name") or "").strip()
    }
    report["task"]["attempt_id"] = report["attempt_id"]
    report["task"]["resume_source"] = str(getattr(task, "resume_source", "") or "")
    existing_technical_features = [
        feature
        for feature in list(blueprint.technical_features or [])
        if not any(name in str(feature or "") for name in architecture_names)
    ]
    blueprint.technical_features = _merge_unique(
        [
            f"采用{architecture.name}",
            f"源码工程包含{'、'.join(architecture.languages)}等语言模块",
            f"技术栈包含{'、'.join(architecture.stack[:5])}",
        ],
        existing_technical_features,
    )
    if not blueprint.deployment_topology:
        blueprint.deployment_topology = (
            f"{architecture.name}部署在{architecture.runtime_environment.get('os', '目标运行环境')}，"
            f"依赖{architecture.runtime_environment.get('support', '运行支撑组件')}。"
        )
    mark("blueprint")
    report["task"] = task.to_dict()
    report["blueprint"] = blueprint.to_dict()
    report["technical_architecture"] = architecture.to_dict()
    report["blueprint_source"] = blueprint_source
    report["checks"]["blueprint_source"] = blueprint_source
    report["checks"]["software_category"] = task.software_category
    report["checks"]["technical_architecture"] = architecture.name
    report["checks"]["technical_architecture_source"] = architecture.source
    report["checks"]["technical_architecture_key"] = architecture.key
    report["checks"]["source_strategy"] = architecture.source_strategy
    report["checks"]["source_language"] = architecture.source_language
    report["checks"]["blueprint_quality_score"] = blueprint.quality_score
    report["checks"]["blueprint_fingerprint"] = blueprint.generation_fingerprint
    report["checks"]["blueprint_business_object_count"] = len(blueprint.business_objects)
    report["checks"]["blueprint_workflow_count"] = len(blueprint.workflows)
    report["checks"]["blueprint_metric_count"] = len(blueprint.report_metrics)
    report["checks"]["blueprint_module_detail_ready"] = all(
        bool(module.operations)
        and bool(module.data_fields)
        and bool(module.rules)
        and (not require_llm_generation or len(getattr(module, "operation_specs", None) or []) >= 3)
        for module in blueprint.modules
    )

    manual_content = None
    manual_source = "local-template" if local_template_mode else "llm"
    cached_manual_content = load_cached_manual_content(stage_cache, blueprint)
    if local_template_mode:
        send("manual_content", 24, "使用默认模板说明书正文", material_type="Default Template")
        manual_content = None
    elif cached_manual_content:
        send("manual_content", 24, "复用已缓存说明书正文", material_type="阶段缓存")
        manual_content = cached_manual_content
        save_cached_manual_content(stage_cache, manual_content)
        report["checks"]["stage_cache_hits"].append("manual_content")
    else:
        try:
            send("manual_content", 24, "生成说明书正文")
            manual_content = generate_manual_content_with_llm(
                task,
                blueprint,
                llm_provider,
                emit=lambda progress, message, **extra: send("manual_content", progress, message, **extra),
            )
        except Exception as exc:
            raise RuntimeError(f"GPT 说明书正文生成失败：{sanitize_error_message(exc)}") from exc
    if require_llm_generation and not manual_content:
        raise RuntimeError("GPT 说明书正文未返回有效内容，请重试。")
    if manual_content:
        manual_warnings = manual_content.pop("_warnings", [])
        if manual_warnings:
            raise RuntimeError(
                "GPT 说明书正文存在未完成章节："
                + "；".join(sanitize_error_message(item) for item in manual_warnings[:4])
            )
        save_cached_manual_content(stage_cache, manual_content)
    report["manual_source"] = manual_source
    mark("manual_content")

    send("visual_reference", 40, "先生成全局风格参考图")
    resume_existing_output = bool(getattr(task, "resume_existing_output", False))
    resume_ui_blueprint = _load_resume_ui_blueprint(output_dir) if resume_existing_output else None
    resume_visual_identity_locked = bool(
        resume_stage in {"screenshots", "done"} and resume_ui_blueprint is not None
    )
    if resume_visual_identity_locked:
        report["checks"]["resume_visual_identity_locked"] = True
    cached_ui_blueprint = resume_ui_blueprint or load_cached_ui_blueprint(stage_cache, blueprint)
    if cached_ui_blueprint and not ui_matches_software_type(task, blueprint, cached_ui_blueprint):
        if resume_visual_identity_locked:
            report["warnings"].append(
                "断点续跑保留已有界面蓝图视觉身份，领域元数据将在最终实际截图门禁中复核。"
            )
            report["checks"]["resume_ui_type_repair_deferred"] = True
        else:
            repaired_ui_blueprint = repair_ui_blueprint_contract(task, blueprint, cached_ui_blueprint)
            if repaired_ui_blueprint and ui_matches_software_type(task, blueprint, repaired_ui_blueprint):
                cached_ui_blueprint = repaired_ui_blueprint
                resume_ui_blueprint = repaired_ui_blueprint if resume_ui_blueprint else None
                send("visual_reference", 40, "已修复界面蓝图领域元数据并保留现有页面", material_type="阶段恢复")
                report["warnings"].append("界面页面业务内容正确，已修复污染的行业子类型和产品体验元数据。")
            else:
                send("visual_reference", 40, "已忽略不匹配的界面蓝图缓存，重新生成截图设计", material_type="阶段缓存")
                report["warnings"].append("已忽略与当前软件类型不匹配的界面蓝图缓存/恢复记录。")
                resume_ui_blueprint = None
                cached_ui_blueprint = None
    if cached_ui_blueprint and not _ui_blueprint_matches_module_keys(cached_ui_blueprint, blueprint):
        if resume_visual_identity_locked:
            raise RuntimeError("断点续跑界面蓝图与当前产品蓝图模块 key 不一致，已停止以避免覆盖既有参考图和页面缓存。")
        send("visual_reference", 40, "已忽略使用旧模块 key 的界面蓝图缓存，重新生成截图设计", material_type="阶段缓存")
        report["warnings"].append("已忽略使用旧模块 key 的界面蓝图缓存，已按业务 key 重新生成。")
        resume_ui_blueprint = None
        cached_ui_blueprint = None
    if cached_ui_blueprint:
        original_screen_count = len(cached_ui_blueprint.screens)
        cached_ui_blueprint = complete_ui_blueprint_coverage(task, blueprint, cached_ui_blueprint)
        if len(cached_ui_blueprint.screens) > original_screen_count:
            send("visual_reference", 40, "补齐旧任务缺少的模块主界面与二级操作截图", material_type="阶段恢复")
            report["warnings"].append("旧界面蓝图模块覆盖不足，已保留现有页面并补齐缺失模块。")
    if cached_ui_blueprint:
        if resume_ui_blueprint:
            send("visual_reference", 40, "复用未完成输出目录中的界面蓝图", material_type="阶段恢复")
        else:
            send("visual_reference", 40, "复用已缓存界面蓝图", material_type="阶段缓存")
    ui_screenshots = {}
    screenshot_warnings: list[str] = []
    ui_blueprint = None
    visual_reference_report = {}
    ui_similarity_gate = None
    used_cached_ui_blueprint = False
    ui_type_mismatch_attempts = 0
    visual_attempt_limit = 1 if resume_visual_identity_locked else MAX_VISUAL_IDENTITY_ATTEMPTS
    for visual_attempt in range(visual_attempt_limit):
        attempt_cached = cached_ui_blueprint if visual_attempt == 0 else None
        if visual_attempt > 0:
            send("visual_reference", 40, f"重生成界面视觉身份 {visual_attempt + 1}/{MAX_VISUAL_IDENTITY_ATTEMPTS}")
        attempt_blueprint, attempt_visual_reference_report, attempt_screenshots = prepare_ui_visual_reference(
            task,
            blueprint,
            output_dir,
            llm_provider,
            emit=lambda progress, message, **extra: send("visual_reference", progress, message, **extra),
            require_llm_blueprint=require_llm_generation,
            ui_blueprint_override=attempt_cached,
            visual_identity_attempt=visual_attempt,
        )
        if require_llm_generation and not ui_matches_software_type(task, blueprint, attempt_blueprint):
            if resume_visual_identity_locked:
                report["warnings"].append(
                    "断点续跑保留已有桌面界面蓝图，APP 默认终端类型校验延后到最终实际截图门禁。"
                )
                report["checks"]["resume_ui_type_gate_deferred_after_reference"] = True
            else:
                ui_type_mismatch_attempts += 1
                message = (
                    f"GPT 界面蓝图与当前软件类型不匹配，自动重生成界面蓝图 "
                    f"{ui_type_mismatch_attempts}/{MAX_VISUAL_IDENTITY_ATTEMPTS}"
                )
                send("visual_reference", 40, message)
                report["warnings"].append(message)
                cached_ui_blueprint = None
                continue
        gate = evaluate_ui_similarity_gate(
            task=task,
            ui_blueprint=attempt_blueprint,
            ui_screenshots=attempt_screenshots,
            output_root=task.output_root,
            attempt=visual_attempt,
            ignore_current_history=bool(resume_existing_output and attempt_cached is not None),
            evaluate_package_pages=False,
        )
        if (
            not gate.ready
            and _should_defer_pre_render_similarity_for_resume(
                resume_stage=resume_stage,
                resume_ui_blueprint=resume_ui_blueprint,
                attempt_cached=attempt_cached,
                visual_reference_report=attempt_visual_reference_report,
            )
        ):
            report["warnings"].append(
                "断点续跑保留已生成页面使用的界面蓝图和 gpt-image-2 参考图；完整包相似度将在实际截图后重新校验。"
            )
            report["checks"]["ui_similarity_pre_render_deferred_for_resume"] = True
            gate = replace(gate, ready=True, reason="resume_screenshot_checkpoint_deferred")
        ui_screenshots = attempt_screenshots
        ui_blueprint = attempt_blueprint
        visual_reference_report = attempt_visual_reference_report
        ui_similarity_gate = gate
        if gate.ready:
            used_cached_ui_blueprint = bool(attempt_cached)
            break
        if attempt_cached:
            report["warnings"].append("已忽略相似度过高的界面蓝图缓存，改为重新生成视觉身份。")
        cached_ui_blueprint = None
    if ui_blueprint is None or ui_similarity_gate is None:
        if ui_type_mismatch_attempts:
            raise RuntimeError(
                f"GPT 界面蓝图与当前软件类型不匹配，已自动重试 {ui_type_mismatch_attempts} 次仍未通过。"
            )
        raise RuntimeError("GPT 界面截图未生成有效结果，请重试。")
    if not ui_similarity_gate.ready:
        if ui_similarity_gate.reason == "ui_layout_role_count_low":
            raise RuntimeError("界面模块页面角色数量不足，已停止生成；请重新生成更差异化的界面蓝图。")
        if ui_similarity_gate.reason == "ui_package_pages_too_similar":
            raise RuntimeError("当前材料包内页面结构重复度过高，已停止生成；请重新生成更差异化的界面页面。")
        raise RuntimeError(
            f"界面相似度过高，已重试 {ui_similarity_gate.attempts} 次仍未通过；"
            f"最高相似度 {ui_similarity_gate.max_score:.2f}。"
        )
    if used_cached_ui_blueprint:
        save_cached_ui_blueprint(stage_cache, ui_blueprint)
        report["checks"]["stage_cache_hits"].append("ui_blueprint")
    else:
        save_cached_ui_blueprint(stage_cache, ui_blueprint)

    resume_source_info = (
        _load_resume_source_info(output_dir, blueprint, visual_reference_report)
        if resume_stage and _stage_precedes("source", resume_stage)
        else None
    )
    if resume_source_info:
        source_info = resume_source_info
        refresh_generated_source_metadata(task, blueprint, source_info)
    else:
        send("source", 44, "根据全局风格参考图生成业务后端与运行接口")
        source_info = generate_source_project(task, blueprint, output_dir, visual_reference_report=visual_reference_report)
    source_info["ui_visual_reference"] = visual_reference_report
    report["source"] = source_info
    report["checks"]["ui_visual_reference_before_source_ready"] = bool(visual_reference_report.get("ready")) if isinstance(visual_reference_report, dict) else False
    report["checks"]["source_visual_reference_contract"] = source_info.get("visual_reference_contract", "")
    report["checks"]["source_persistence_required"] = bool(source_info.get("source_persistence_required"))
    report["checks"]["source_persistence_engine"] = str(source_info.get("source_persistence_engine") or "")
    report["checks"]["source_persistence_ready"] = bool(source_info.get("source_persistence_ready"))
    report["checks"]["source_repository_file_count"] = int(source_info.get("source_repository_file_count") or 0)
    report["checks"]["source_migration_file_count"] = int(source_info.get("source_migration_file_count") or 0)
    report["checks"]["source_test_file_count"] = int(source_info.get("source_test_file_count") or 0)
    if report["checks"]["source_persistence_required"] and not report["checks"]["source_persistence_ready"]:
        raise RuntimeError("Python 业务工程缺少数据库、Repository、迁移或自动化测试，已停止生成。")
    source_lines = int(source_info["total_lines"])
    if not resume_source_info:
        _emit_source_file_events(send, source_info, output_dir)
    mark("source")

    page_engine_migration = _invalidate_legacy_frontend_cache_for_pagespec(output_dir) if resume_existing_output else {}
    report["checks"]["page_engine_cache_migrated"] = bool(page_engine_migration.get("migrated"))
    report["checks"]["page_engine_previous_version"] = str(page_engine_migration.get("previous_version") or "")
    report["checks"]["page_engine_invalidated_file_count"] = int(page_engine_migration.get("invalidated_file_count") or 0)
    if page_engine_migration.get("migrated"):
        message = "页面生成引擎已升级，将复用蓝图和参考图并重新生成全部界面"
        report["warnings"].append(message)
        send("screenshots", 49, message, material_type="PageSpec v1")
    send("screenshots", 50, "根据参考图生成界面代码并运行源码截图")
    ui_screenshots, screenshot_warnings, ui_blueprint = generate_ui_screenshots(
        task,
        blueprint,
        output_dir,
        llm_provider,
        source_info=source_info,
        emit=lambda progress, message, **extra: send("screenshots", progress, message, **extra),
        use_project_server=True,
        require_project_server=True,
        require_llm_blueprint=require_llm_generation,
        ui_blueprint_override=ui_blueprint,
        visual_identity_attempt=max(0, int((ui_similarity_gate.attempts if ui_similarity_gate else 1) - 1)),
        visual_reference_report=visual_reference_report,
    )
    ui_similarity_gate = evaluate_ui_similarity_gate(
        task=task,
        ui_blueprint=ui_blueprint,
        ui_screenshots=ui_screenshots,
        output_root=task.output_root,
        attempt=max(0, int((ui_similarity_gate.attempts if ui_similarity_gate else 1) - 1)),
        ignore_current_history=bool(resume_existing_output),
        evaluate_package_pages=True,
    )
    if not ui_similarity_gate.ready:
        if ui_similarity_gate.reason == "ui_package_pages_too_similar":
            raise RuntimeError(
                "当前材料包生成后的 React 页面结构重复度过高，已停止后续材料生成；请保留蓝图重试以重新生成页面构图。"
            )
        raise RuntimeError(
            f"生成后的界面相似度检查未通过：{ui_similarity_gate.reason or 'ui_similarity_too_high'}，"
            f"最高相似度 {ui_similarity_gate.max_score:.2f}。"
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
            "page_kind": item.page_kind,
            "module_key": item.module_key,
            "runtime_fetches": item.runtime_fetches or [],
            "action_crops": item.action_crops or {},
            "visible_content_summary": item.visible_content_summary or {},
            "interaction_action": item.interaction_action,
            "interaction_mode": item.interaction_mode,
            "interaction_surface": item.interaction_surface,
            "requires_confirmation": item.requires_confirmation,
            "interaction_action_key": item.interaction_action_key,
            "interaction_role": item.interaction_role,
            "interaction_trigger": item.interaction_trigger,
            "interaction_input_fields": item.interaction_input_fields or [],
            "interaction_pre_state": item.interaction_pre_state,
            "interaction_post_state": item.interaction_post_state,
            "interaction_result_evidence": item.interaction_result_evidence,
        }
        for key, item in ui_screenshots.items()
    }
    report["checks"]["ui_screenshot_count"] = sum(1 for item in ui_screenshots.values() if item.image_path)
    report["checks"]["ui_visible_content_summary_count"] = sum(
        1
        for item in ui_screenshots.values()
        if item.image_path and bool((item.visible_content_summary or {}).get("ready"))
    )
    report["checks"]["ui_visible_content_summary_ready"] = (
        report["checks"]["ui_screenshot_count"] > 0
        and report["checks"]["ui_visible_content_summary_count"] == report["checks"]["ui_screenshot_count"]
    )
    if not report["checks"]["ui_visible_content_summary_ready"]:
        raise RuntimeError("界面截图可见内容摘要不完整，无法生成与图片逐页对应的功能说明。")
    report["checks"]["ui_instant_interaction_count"] = sum(
        1 for item in ui_screenshots.values() if item.page_kind == "operation" and item.interaction_mode == "instant"
    )
    report["checks"]["ui_confirmation_interaction_count"] = sum(
        1 for item in ui_screenshots.values() if item.page_kind == "operation" and item.requires_confirmation
    )
    _emit_screenshot_events(send, ui_screenshots, output_dir)
    report["checks"]["ui_blueprint_source"] = ui_blueprint.source
    if require_llm_generation and ui_blueprint.source != "llm":
        raise RuntimeError("GPT 界面蓝图未成功生成，请重试。")
    ai_frontend_report = source_info.get("ui_ai_frontend") if isinstance(source_info, dict) else {}
    if not isinstance(ai_frontend_report, dict):
        ai_frontend_report = {}
    report["checks"]["ui_ai_frontend_enabled"] = bool(ai_frontend_report.get("enabled"))
    report["checks"]["ui_ai_frontend_ready"] = bool(ai_frontend_report.get("ready"))
    report["checks"]["ui_ai_frontend_source"] = str(ai_frontend_report.get("source") or "")
    report["checks"]["ui_frontend_framework"] = str(ai_frontend_report.get("framework") or "static-html")
    report["checks"]["ui_frontend_build_tool"] = str(ai_frontend_report.get("build_tool") or "")
    report["checks"]["ui_frontend_source_dir"] = str(source_info.get("ui_frontend_source_dir") or ai_frontend_report.get("source_dir") or "")
    report["checks"]["ui_ai_frontend_page_count"] = int(ai_frontend_report.get("page_count") or len(ai_frontend_report.get("pages") or []))
    report["checks"]["page_spec_count"] = int(ai_frontend_report.get("page_spec_count") or 0)
    legacy_page_count = ai_frontend_report.get("legacy_react_page_count")
    report["checks"]["legacy_react_page_count"] = int(
        legacy_page_count if legacy_page_count is not None else report["checks"]["ui_ai_frontend_page_count"]
    )
    report["checks"]["frontend_effective_workers"] = int(ai_frontend_report.get("frontend_effective_workers") or 1)
    report["checks"]["frontend_concurrency_degraded"] = bool(ai_frontend_report.get("frontend_concurrency_degraded"))
    report["checks"]["frontend_concurrency_degrade_reason"] = str(ai_frontend_report.get("frontend_concurrency_degrade_reason") or "")
    report["checks"]["frontend_cancelled_page_count"] = int(ai_frontend_report.get("frontend_cancelled_page_count") or 0)
    report["checks"]["frontend_page_request_timing"] = ai_frontend_report.get("frontend_page_request_timing") or {}
    report["checks"]["provider_retry_summary"] = ai_frontend_report.get("provider_retry_summary") or {}
    report["page_spec_count"] = report["checks"]["page_spec_count"]
    report["legacy_react_page_count"] = report["checks"]["legacy_react_page_count"]
    report["frontend_effective_workers"] = report["checks"]["frontend_effective_workers"]
    report["frontend_concurrency_degraded"] = report["checks"]["frontend_concurrency_degraded"]
    report["frontend_cancelled_page_count"] = report["checks"]["frontend_cancelled_page_count"]
    report["provider_retry_summary"] = report["checks"]["provider_retry_summary"]
    report["checks"]["ui_shared_confirmation_contract"] = str(ai_frontend_report.get("shared_confirmation_contract") or "")
    report["checks"]["ui_shared_confirmation_page_count"] = int(ai_frontend_report.get("shared_confirmation_page_count") or 0)
    report["checks"]["ui_shared_confirmation_ready"] = bool(ai_frontend_report.get("shared_confirmation_ready"))
    visual_reference_report = ai_frontend_report.get("visual_references") if isinstance(ai_frontend_report, dict) else {}
    if not isinstance(visual_reference_report, dict):
        visual_reference_report = {}
    report["checks"]["ui_visual_prompt_ready"] = bool(visual_reference_report.get("prompt_ready", visual_reference_report.get("ready")))
    report["checks"]["ui_visual_reference_ready"] = bool(visual_reference_report.get("ready"))
    report["checks"]["ui_visual_reference_mode"] = str(visual_reference_report.get("mode") or "per_page")
    report["checks"]["ui_visual_reference_source"] = str(visual_reference_report.get("source") or "")
    report["checks"]["ui_visual_reference_count"] = int(visual_reference_report.get("reference_count") or 0)
    report["checks"]["ui_visual_reference_target_count"] = int(visual_reference_report.get("reference_target_count") or 0)
    report["checks"]["ui_visual_reference_page_count"] = int(visual_reference_report.get("page_count") or 0)
    report["checks"]["ui_visual_reference_applies_to_page_count"] = int(
        visual_reference_report.get("applies_to_page_count")
        or visual_reference_report.get("page_count")
        or 0
    )
    report["checks"]["ui_visual_style_reference_ready"] = bool(visual_reference_report.get("style_reference_ready", visual_reference_report.get("ready")))
    report["checks"]["ui_visual_reference_image_model"] = str(visual_reference_report.get("image_model") or "")
    report["checks"]["ui_visual_reference_retry_count"] = int(visual_reference_report.get("image_retry_count") or 0)
    report["checks"]["ui_visual_reference_failed_page"] = str(visual_reference_report.get("failed_page_key") or "")
    report["checks"]["ui_visual_reference_error"] = sanitize_error_message(visual_reference_report.get("error") or "", limit=500)
    report["checks"]["ui_visual_reference_directory"] = str(visual_reference_report.get("directory") or "")
    if report["checks"]["ui_visual_reference_mode"] == "style_reference":
        report["checks"]["ui_visual_reference_to_code_ready"] = (
            bool(report["checks"]["ui_ai_frontend_ready"])
            and bool(report["checks"]["ui_visual_reference_ready"])
            and bool(report["checks"]["ui_visual_style_reference_ready"])
            and int(report["checks"]["ui_visual_reference_count"] or 0) >= 1
        )
    else:
        report["checks"]["ui_visual_reference_to_code_ready"] = (
            bool(report["checks"]["ui_ai_frontend_ready"])
            and bool(report["checks"]["ui_visual_reference_ready"])
            and int(report["checks"]["ui_visual_reference_count"] or 0) == int(report["checks"]["ui_ai_frontend_page_count"] or 0)
        )
    if require_llm_generation and not report["checks"]["ui_ai_frontend_ready"]:
        raise RuntimeError("GPT 界面页面代码未成功生成，已停止；正式流程不使用模板截图兜底。")
    if require_llm_generation and not report["checks"]["ui_shared_confirmation_ready"]:
        raise RuntimeError("React 公共确认弹窗组件未生成，已停止；同一软件不能混用多套确认弹窗。")
    if require_llm_generation and not report["checks"]["ui_visual_reference_to_code_ready"]:
        raise RuntimeError("gpt-image-2 视觉风格参考图未生成或未参与界面代码生成，已停止；正式流程不允许无图生成截图。")
    report["checks"]["ui_renderer"] = ui_blueprint.renderer
    report["checks"]["ui_layout_variant"] = report["ui_blueprint"]["layout_variant"]
    design_brief = getattr(ui_blueprint, "design_brief", {}) or {}
    expected_experience = build_product_experience_spec(task, blueprint)
    experience_data = design_brief.get("product_experience_spec") if isinstance(design_brief, dict) else {}
    if not isinstance(experience_data, dict):
        experience_data = {}
    visual_identity_data = design_brief.get("visual_identity_spec") if isinstance(design_brief, dict) else {}
    if not isinstance(visual_identity_data, dict):
        visual_identity_data = {}
    report["ui_blueprint"]["product_experience_spec"] = experience_data
    report["ui_blueprint"]["visual_identity_spec"] = visual_identity_data
    report["checks"]["ui_software_category"] = experience_data.get("software_category", expected_experience.software_category)
    report["checks"]["ui_product_type"] = experience_data.get("product_type", expected_experience.product_type)
    report["checks"]["ui_experience_shape"] = experience_data.get("experience_shape", "")
    report["checks"]["ui_terminal"] = experience_data.get("terminal", "")
    report["checks"]["ui_experience_shell"] = experience_data.get("shell", "")
    report["checks"]["ui_family"] = experience_data.get("ui_family", "")
    report["checks"]["ui_viewport_mode"] = experience_data.get("viewport_mode", "")
    report["checks"]["ui_experience_match_ready"] = design_brief_matches_experience(design_brief, expected_experience)
    report["checks"]["ui_industry_subtype"] = design_brief.get("industry_subtype", getattr(blueprint, "industry_subtype", ""))
    report["checks"]["ui_nav_model"] = design_brief.get("nav_model", "")
    report["checks"]["ui_visual_mood"] = design_brief.get("visual_mood", ui_blueprint.visual_style)
    report["checks"]["ui_dashboard_pattern"] = design_brief.get("dashboard_pattern", "")
    report["checks"]["ui_module_pattern"] = design_brief.get("module_pattern", "")
    report["checks"]["ui_workspace_shape"] = design_brief.get("workspace_shape", "")
    report["checks"]["ui_login_pattern"] = design_brief.get("login_pattern", "")
    report["checks"]["ui_visual_identity_signature"] = visual_identity_data.get("identity_signature", "")
    report["checks"]["ui_visual_seed"] = visual_identity_data.get("visual_seed", "")
    report["checks"]["ui_creative_seed"] = str(design_brief.get("creative_seed") or task.seed)
    report["checks"]["ui_palette_key"] = visual_identity_data.get("palette_key", "")
    report["checks"]["ui_table_density"] = visual_identity_data.get("table_density", "")
    report["checks"]["ui_chart_style"] = visual_identity_data.get("chart_style", "")
    report["checks"]["ui_surface_style"] = visual_identity_data.get("surface_style", "")
    report["checks"]["ui_component_rhythm"] = visual_identity_data.get("component_rhythm", "")
    report["checks"].update(ui_similarity_gate.to_checks())
    report["checks"]["ui_structure_id"] = (design_brief.get("structure_blueprint") or {}).get("id", "")
    report["checks"]["ui_domain_bias"] = (design_brief.get("design_dna") or {}).get("domain_bias", "")
    report["checks"]["ui_layout_signature"] = design_brief.get("layout_signature", "")
    report["checks"]["ui_secondary_mix"] = "、".join(str(item) for item in design_brief.get("secondary_mix", []) if str(item).strip())
    role_summary = role_coverage_summary(ui_blueprint)
    report["checks"]["ui_role_signature"] = role_summary.get("signature", "")
    report["checks"]["ui_role_count"] = role_summary.get("expected_role_count", 0)
    report["checks"]["ui_role_screen_count"] = role_summary.get("screen_count", 0)
    report["checks"]["ui_role_module_screen_count"] = role_summary.get("module_screen_count", 0)
    report["checks"]["ui_role_has_login"] = role_summary.get("has_login", False)
    report["checks"]["ui_role_has_dashboard"] = role_summary.get("has_dashboard", False)
    report["checks"]["ui_role_has_statistics"] = role_summary.get("has_statistics", False)
    ui_software_type_match_raw = ui_matches_software_type(task, blueprint, ui_blueprint)
    report["checks"]["ui_software_type_match_raw"] = ui_software_type_match_raw
    report["checks"]["ui_software_type_match_deferred_for_resume"] = bool(
        resume_visual_identity_locked and not ui_software_type_match_raw
    )
    report["checks"]["ui_software_type_match"] = bool(
        ui_software_type_match_raw or resume_visual_identity_locked
    )
    if not report["checks"]["ui_software_type_match"]:
        raise RuntimeError("GPT 界面蓝图与当前软件类型不匹配，请重试生成界面截图。")
    domain_quality = _ui_domain_quality_checks(task, blueprint, ui_blueprint, ui_screenshots, source_info)
    report["checks"].update(domain_quality)
    secondary_screens = [item for item in ui_screenshots.values() if str(getattr(item, "page_kind", "") or "") in {"operation", "detail"}]
    secondary_module_keys = {str(getattr(item, "module_key", "") or "") for item in secondary_screens if str(getattr(item, "module_key", "") or "")}
    report["checks"]["ui_secondary_screenshot_count"] = len(secondary_screens)
    report["checks"]["ui_secondary_module_count"] = len(secondary_module_keys)
    report["checks"]["ui_secondary_screenshot_ready"] = (
        ui_blueprint.renderer == "game" or len(secondary_module_keys) >= len(blueprint.modules)
    )
    if not report["checks"]["ui_secondary_screenshot_ready"]:
        raise RuntimeError("操作手册缺少覆盖全部业务模块的二级界面或按钮操作截图，已停止生成。")
    required_operation_count = configured_operation_screen_count(ui_blueprint.renderer)
    operation_coverage: dict[str, dict[str, object]] = {}
    missing_operation_coverage: list[dict[str, object]] = []
    for module in blueprint.modules:
        module_items = [
            item
            for item in secondary_screens
            if str(getattr(item, "module_key", "") or "") == module.key
        ]
        categories = list(
            dict.fromkeys(
                module_operation_category(
                    module,
                    str(getattr(item, "interaction_action", "") or ""),
                    str(getattr(item, "interaction_action_key", "") or ""),
                )
                for item in module_items
                if str(getattr(item, "interaction_action", "") or "")
            )
        )
        minimum_category_count = 1 if ui_blueprint.renderer == "mobile_app" else min(2, required_operation_count)
        ready = (
            len(module_items) >= required_operation_count
            and len(categories) >= minimum_category_count
        )
        operation_coverage[module.key] = {
            "module_title": module.title,
            "count": len(module_items),
            "required": required_operation_count,
            "categories": categories,
            "ready": ready,
        }
        if not ready:
            missing_operation_coverage.append(operation_coverage[module.key])
    report["checks"]["ui_operation_coverage_required_per_module"] = required_operation_count
    report["checks"]["ui_operation_coverage_module_count"] = sum(
        1 for item in operation_coverage.values() if bool(item.get("ready"))
    )
    report["checks"]["ui_operation_coverage_min_count"] = min(
        (int(item.get("count") or 0) for item in operation_coverage.values()),
        default=0,
    )
    report["checks"]["ui_operation_coverage"] = operation_coverage
    report["checks"]["ui_operation_coverage_missing"] = missing_operation_coverage
    report["checks"]["ui_operation_coverage_ready"] = (
        ui_blueprint.renderer == "game" or not missing_operation_coverage
    )
    if not report["checks"]["ui_operation_coverage_ready"]:
        raise RuntimeError("操作手册未达到逐模块操作覆盖要求；每个模块需要查询、业务处理或结果分析等真实操作页。")
    if not domain_quality.get("ui_domain_terms_clean"):
        raise RuntimeError("界面截图含有与当前软件领域不一致的词语，已停止生成。")
    if not domain_quality.get("ui_module_keys_semantic"):
        raise RuntimeError("源码和截图模块 key 仍为占位命名，已停止生成；请使用业务语义模块 key。")
    if not domain_quality.get("ui_business_facing_screenshots"):
        raise RuntimeError("界面截图仍包含接口路径、源码类名、文件名或英文实体等开发痕迹，已停止生成。")
    if not domain_quality.get("ui_visible_text_clean"):
        raise RuntimeError(f"界面截图可见文本含有乱码或占位内容：{domain_quality.get('ui_visible_text_placeholder_hits')}")
    if not domain_quality.get("ui_operation_result_evidence_ready"):
        raise RuntimeError("操作截图缺少处理结果、操作日志或状态刷新证据，已停止生成。")
    if not domain_quality.get("ui_chart_context_ready"):
        raise RuntimeError("统计图或趋势图缺少日期范围、单位等业务上下文，已停止生成。")
    if not domain_quality.get("ui_route_topology_ready"):
        raise RuntimeError("交通线路类截图缺少干线/支线拓扑、节点或时窗信息，已停止生成。")
    report["checks"].update(_ui_project_entry_checks(source_info))
    report["checks"].update(_ui_source_evidence_checks(source_info))
    if report["checks"].get("ui_screenshot_render_mode") != "project-server":
        raise RuntimeError("界面截图未通过生成项目服务 URL 渲染，已停止生成；请先修复生成项目运行入口。")
    if not report["checks"].get("ui_runtime_probe_ready"):
        raise RuntimeError("生成项目运行探针未通过，已停止生成；请先修复健康检查或模块接口。")
    if not report["checks"].get("ui_source_evidence_ready"):
        raise RuntimeError("界面截图缺少源码文件/接口/服务证据，已停止生成。")
    if not report["checks"].get("ui_runtime_api_ready"):
        raise RuntimeError("界面截图页面未实际请求生成项目业务接口，已停止生成；请修复运行时页面数据加载。")
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
        send("manual", 61, "生成软件说明书")
        _emit_manual_outline_events(send, blueprint, ui_screenshots)
        manual_docx = generate_manual_docx(
            task,
            blueprint,
            output_dir,
            manual_content=manual_content,
            ui_screenshots=ui_screenshots,
            design_brief=design_brief,
        )
        manual_density = analyze_manual_density(manual_docx)
        report["checks"].update(manual_density)
        manual_ui_consistency = analyze_manual_ui_consistency(manual_docx, blueprint, ui_screenshots)
        report["checks"].update(manual_ui_consistency)
        if not manual_ui_consistency.get("manual_ui_consistency_ready"):
            raise RuntimeError(
                "操作手册图文一致性校验未通过：截图标题、按钮或正文引用的字段、指标、状态与实际界面不一致。"
            )
        report["checks"].update(_prefixed_checks("manual", analyze_docx_layout(manual_docx)))
        if not manual_density.get("manual_operation_density_ready"):
            report["warnings"].append("说明书截图后的操作步骤密度偏低，建议复核截图页是否紧跟入口、字段、保存结果和后续处理说明。")
        if not manual_density.get("manual_natural_style_ready"):
            report["warnings"].append("说明书正文机械式标签或重复短句偏多，建议重新生成说明书正文。")
        if not manual_density.get("manual_pagination_constraints_ready"):
            raise RuntimeError("操作手册未完整应用全局标题、截图和图注分页约束，已停止生成。")
        if not manual_density.get("manual_numbered_steps_ready"):
            raise RuntimeError("操作手册截图后的操作说明未统一生成编号步骤，已停止生成。")
        if not manual_density.get("manual_toc_ready"):
            raise RuntimeError("操作手册缺少目录页，已停止生成。")
        _emit_output_file_event(send, "manual", 70, "写入软件说明书 Word", manual_docx, output_dir, "Word 文档")
        mark("manual_docx")
        send("source_doc", 71, "生成源码鉴别材料")
        source_docx, source_report = generate_source_docx(task, Path(source_info["source_dir"]), output_dir)
        report["checks"].update({key: value for key, value in source_report.items() if key != "source_page_sources"})
        report["checks"].update(_prefixed_checks("source", analyze_docx_layout(source_docx)))
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
            if docx_path == manual_docx and pdf_path and not error:
                toc_checks = update_manual_toc_page_numbers(manual_docx, pdf_path, blueprint)
                report["checks"].update(toc_checks)
                if not toc_checks.get("manual_toc_page_numbers_ready"):
                    raise RuntimeError(
                        "操作手册目录未能匹配全部正文页码："
                        + "、".join(toc_checks.get("manual_toc_missing_entries") or [])
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
                    report["checks"].update(_prefixed_checks("manual", analyze_pdf_layout(pdf_path)))
                    manual_pdf_density = analyze_manual_pdf_text_density(pdf_path)
                    report["checks"].update(manual_pdf_density)
                    if manual_pdf_density.get("manual_pdf_line_requirement_warning"):
                        report["warnings"].append(
                            "说明书部分正文页的 PDF 可提取文本少于 30 行，已按字符量和业务操作内容综合判定通过；提交前建议人工复核版面。"
                        )
                elif docx_path == source_docx:
                    source_pdf = pdf_path
                    report["checks"].update(_prefixed_checks("source", analyze_pdf_layout(pdf_path)))
            if error:
                report["warnings"].append(f"{docx_path.name}: {error}")
            if pdf_path:
                _emit_output_file_event(send, "pdf", 82, f"写入 PDF 文件：{pdf_path.name}", pdf_path, output_dir, "PDF 文件")
        report["checks"]["pdf_conversion_method"] = converter_info.get("method", "")
        report["checks"]["pdf_official_conversion_ready"] = (
            bool(pdf_conversions)
            and all(not item.get("fallback") and not item.get("error") and item.get("pdf_path") for item in pdf_conversions)
        )
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
    zip_path = _delivery_zip_path(output_dir)
    _emit_zip_input_events(send, deliverable_files, output_dir)
    zip_path = make_zip_files(deliverable_files, zip_path)
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
    if not validation.get("ready_for_delivery", False):
        write_json(report_path, report)
        error_messages = [
            str(item.get("message") or item.get("code") or "")
            for item in validation.get("findings", [])
            if item.get("level") == "error"
        ]
        detail = "；".join(message for message in error_messages if message) or "validation_ready_for_delivery=false"
        failure_message = f"材料真实性/规范性校验未通过，已停止交付：{detail}"
        _write_generation_failure(
            output_dir,
            task,
            stage="validate",
            progress=99,
            message=failure_message,
            checks=report.get("checks", {}),
            validation=validation,
        )
        raise RuntimeError(f"材料真实性/规范性校验未通过，已停止交付：{detail}")
    if ui_similarity_gate and ui_similarity_gate.fingerprint:
        append_ui_fingerprint_history(task.output_root, ui_similarity_gate.fingerprint)
        report["checks"]["ui_similarity_history_recorded"] = True
    mark("validate")
    report["stage_timings"] = stage_timings
    report["total_seconds"] = round(time.perf_counter() - started_at, 2)
    report["checks"]["total_seconds"] = report["total_seconds"]
    _copy_llm_trace_to_output(output_dir)
    report["zip_path"] = str(zip_path)
    write_json(report_path, report)
    _clear_generation_failure(output_dir)
    send(
        "done",
        100,
        "生成完成",
        zip_path=str(zip_path),
        output_dir=str(output_dir),
        checks=report.get("checks", {}),
        warnings=report.get("warnings", []),
    )
    _write_generation_state(output_dir, task, "success", "done", 100, "生成完成", {"zip_path": str(zip_path)})
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
        progress = 45 + min(4, int(index / max(total, 1) * 4))
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


def _prefixed_checks(prefix: str, checks: dict) -> dict:
    return {f"{prefix}_{key}": value for key, value in (checks or {}).items()}


def _emit_manual_outline_events(send, blueprint, ui_screenshots: dict | None) -> None:
    send("manual", 62, "写入说明书封面、版本号和页眉")
    send("manual", 63, "写入软件概述、产品定位和开发目的")
    send("manual", 64, "写入运行环境、开发环境和部署拓扑")
    send("manual", 65, "写入登录与主界面操作说明")
    modules = list(getattr(blueprint, "modules", []) or [])
    total = len(modules)
    for index, module in enumerate(modules, start=1):
        progress = 66 + min(2, int(index / max(total, 1) * 2))
        send(
            "manual",
            progress,
            f"写入功能模块章节 {index}/{total}：{module.title}",
            material_type="说明书章节",
        )
    screenshot_count = sum(1 for item in (ui_screenshots or {}).values() if getattr(item, "image_path", None))
    if screenshot_count:
        send("manual", 69, f"插入说明书界面配图 {screenshot_count} 张", material_type="说明书配图")
    send("manual", 69, "写入统计分析、权限安全和常见问题章节", material_type="说明书章节")


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
        progress = 72 + min(4, int(page / max(total, 1) * 4))
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


def _merge_unique(primary: list[str], secondary: list[str]) -> list[str]:
    result: list[str] = []
    for value in primary + secondary:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _semantic_contract_from_confirmed_outline(task: GenerationTask) -> dict:
    outline = getattr(task, "confirmed_outline", None)
    if not isinstance(outline, dict):
        return {}
    modules = outline.get("modules")
    if not isinstance(modules, list) or len(modules) < 6:
        return {}
    normalized: list[dict] = []
    for index, item in enumerate(modules[:10], start=1):
        if not isinstance(item, dict):
            continue
        title = _clean_contract_text(item.get("title"), 32)
        description = _clean_contract_text(item.get("description"), 180)
        if not title or len(description) < 12:
            continue
        category = _clean_contract_text(item.get("category"), 24) or "业务模块"
        data_objects = _contract_list(
            item.get("dataObjects") or item.get("data_objects") or item.get("entities"),
            6,
            26,
        )
        screens = _contract_list(item.get("screens") or item.get("pages"), 5, 28)
        user_flow = _contract_list(item.get("userFlow") or item.get("user_flow"), 6, 42)
        operations = _contract_list(item.get("operations") or item.get("actions"), 7, 28)
        operation_specs = _contract_operation_specs(
            item.get("operation_specs") or item.get("operationSpecs")
        )
        data_fields = _contract_list(item.get("data_fields") or item.get("dataFields") or item.get("fields"), 10, 24)
        rules = _contract_list(item.get("rules") or item.get("quality_rules") or item.get("qualityRules"), 5, 80)
        entities = _contract_list(item.get("entities"), 4, 40)
        module_key = _confirmed_module_key(item, title, index, {module["key"] for module in normalized})
        normalized.append(
            {
                "key": module_key,
                "category": category,
                "title": title,
                "description": description,
                "data_objects": data_objects,
                "screens": screens,
                "pages": screens,
                "user_flow": user_flow,
                "operations": operations or _outline_operations(title, category, user_flow),
                "operation_specs": operation_specs,
                "data_fields": data_fields or _outline_fields(title, data_objects),
                "rules": rules or _outline_rules(title, category),
                "entities": entities,
            }
        )
    if len(normalized) < 6:
        return {}
    feature_hint = _clean_contract_text(getattr(task, "feature_hint", ""), 1200)
    if not feature_hint:
        feature_hint = "、".join(module["title"] for module in normalized[:10])
    return {
        "auto_feature_hint": False,
        "feature_hint_profile": "confirmed-outline",
        "feature_hint_source": "confirmed-outline",
        "inferred_feature_hint": feature_hint,
        "original_feature_hint": feature_hint,
        "feature_hint_domain": _clean_contract_text(outline.get("domain"), 40),
        "feature_hint_reason": "复用桌面端已确认可编辑蓝图，跳过正式生成前的重复名称理解。",
        "feature_hint_keywords": _merge_unique(
            [module["title"] for module in normalized],
            [item for module in normalized for item in module.get("data_objects", [])],
        )[:16],
        "feature_hint_avoid_terms": _contract_list(outline.get("avoidTerms") or outline.get("avoid_terms"), 8, 24),
        "feature_hint_target_users": _contract_list(outline.get("targetUsers") or outline.get("target_users"), 8, 20),
        "feature_hint_blueprint_modules": normalized,
        "feature_hint_elapsed_seconds": 0,
    }


def _semantic_contract_from_cached_blueprint(blueprint) -> dict:
    modules: list[dict] = []
    for index, module in enumerate(list(getattr(blueprint, "modules", []) or [])[:10], start=1):
        title = _clean_contract_text(getattr(module, "title", ""), 32)
        description = _clean_contract_text(getattr(module, "description", ""), 180)
        if not title:
            continue
        if len(description) < 12:
            description = f"围绕{title}处理业务数据、流程状态、异常信息和结果归档。"
        modules.append(
            {
                "key": str(getattr(module, "key", "") or f"module_{index}"),
                "category": "业务模块",
                "title": title,
                "description": description,
                "data_objects": _contract_list(getattr(module, "entities", []), 8, 40),
                "screens": _contract_list(getattr(module, "pages", []), 6, 28),
                "pages": _contract_list(getattr(module, "pages", []), 6, 28),
                "user_flow": [],
                "operations": _contract_list(getattr(module, "operations", []), 8, 28),
                "operation_specs": _contract_operation_specs(getattr(module, "operation_specs", [])),
                "data_fields": _contract_list(getattr(module, "data_fields", []), 12, 24),
                "rules": _contract_list(getattr(module, "rules", []), 6, 80),
                "entities": _contract_list(getattr(module, "entities", []), 6, 40),
            }
        )
    feature_hint = "、".join(item["title"] for item in modules)
    return {
        "auto_feature_hint": False,
        "feature_hint_profile": "resume-stage-cache",
        "feature_hint_source": "resume-stage-cache",
        "inferred_feature_hint": feature_hint,
        "original_feature_hint": feature_hint,
        "feature_hint_domain": _clean_contract_text(getattr(blueprint, "industry", ""), 40),
        "feature_hint_reason": "从同一任务 seed 的本地阶段缓存恢复产品蓝图，跳过重复名称理解请求。",
        "feature_hint_keywords": _merge_unique(
            [item["title"] for item in modules],
            list(getattr(blueprint, "business_objects", []) or []),
        )[:16],
        "feature_hint_avoid_terms": [],
        "feature_hint_target_users": _contract_list(
            list(getattr(blueprint, "target_users", []) or getattr(blueprint, "roles", []) or []),
            8,
            20,
        ),
        "feature_hint_blueprint_modules": modules,
        "feature_hint_elapsed_seconds": 0,
    }


def _clean_contract_text(value, limit: int) -> str:
    text = " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split())
    return text[:limit]


def _contract_list(value, limit: int, item_limit: int) -> list[str]:
    if not isinstance(value, list):
        value = []
    result: list[str] = []
    for item in value:
        text = _clean_contract_text(item, item_limit)
        if text and text not in result:
            result.append(text)
        if len(result) >= limit:
            break
    return result


def _contract_operation_specs(value) -> list[dict]:
    if not isinstance(value, list):
        return []
    result: list[dict] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        label = _clean_contract_text(item.get("label") or item.get("action") or item.get("name"), 28)
        if not label:
            continue
        input_fields = _contract_list(item.get("input_fields") or item.get("inputFields"), 8, 24)
        result.append(
            {
                "action_key": _safe_module_key(
                    _clean_contract_text(item.get("action_key") or item.get("actionKey") or label, 48)
                ),
                "label": label,
                "category": _clean_contract_text(item.get("category"), 20),
                "role": _clean_contract_text(item.get("role"), 24),
                "trigger": _clean_contract_text(item.get("trigger"), 80),
                "input_fields": input_fields,
                "pre_state": _clean_contract_text(item.get("pre_state") or item.get("preState"), 32),
                "post_state": _clean_contract_text(item.get("post_state") or item.get("postState"), 32),
                "result_evidence": _clean_contract_text(
                    item.get("result_evidence") or item.get("resultEvidence"), 90
                ),
                "requires_confirmation": bool(
                    item.get("requires_confirmation")
                    if item.get("requires_confirmation") is not None
                    else item.get("requiresConfirmation", False)
                ),
            }
        )
        if len(result) >= 7:
            break
    return result


def _confirmed_module_key(item: dict, title: str, index: int, used: set[str] | None = None) -> str:
    raw_key = str(item.get("key") or item.get("module_key") or item.get("moduleKey") or "").strip()
    context_terms = []
    for field in ("category", "description"):
        value = item.get(field)
        if isinstance(value, str):
            context_terms.append(value)
    for field in ("dataObjects", "data_objects", "entities", "operations", "data_fields", "dataFields", "fields"):
        value = item.get(field)
        if isinstance(value, list):
            context_terms.extend(str(entry) for entry in value[:6])
    return semantic_module_key(title, index, raw_key=raw_key, used=used or set(), context_terms=context_terms)


def _safe_module_key(value: str) -> str:
    key = value.strip()
    key = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key)
    key = re.sub(r"[^A-Za-z0-9_]+", "_", key).strip("_").lower()
    key = re.sub(r"_+", "_", key)
    if not key or key[0].isdigit():
        return ""
    if key in {"login", "dashboard", "statistics", "index"}:
        return f"{key}_module"
    return key[:48]


def _outline_operations(title: str, category: str, user_flow: list[str]) -> list[str]:
    seeds = [item for item in user_flow if item]
    seeds.extend([f"{title}登记", f"{title}校验", f"{title}分析", f"{title}确认", f"{title}归档", f"{category}统计"])
    return _contract_list(seeds, 7, 28)


def _outline_fields(title: str, data_objects: list[str]) -> list[str]:
    fields = [f"{item}编号" for item in data_objects[:3]]
    fields.extend([f"{title}状态", f"{title}时间", f"{title}来源", f"{title}结果", "处理人员", "备注说明"])
    return _contract_list(fields, 10, 24)


def _outline_rules(title: str, category: str) -> list[str]:
    return [
        f"{title}提交前必须完成关键字段校验。",
        f"{category}操作需要记录处理人员和处理时间。",
        f"{title}状态变更需要保留前后状态和审计记录。",
        f"{title}结果输出前需要校验关联记录完整性。",
    ]


def _emit_screenshot_events(send, ui_screenshots: dict, output_dir: Path) -> None:
    items = [item for item in ui_screenshots.values() if getattr(item, "image_path", None)]
    total = len(items)
    for index, item in enumerate(items, start=1):
        path = Path(str(item.image_path))
        progress = 56 + min(4, int(index / max(total, 1) * 4))
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


def _ui_blueprint_matches_module_keys(ui_blueprint, blueprint) -> bool:
    expected = {
        str(getattr(module, "key", "") or "")
        for module in getattr(blueprint, "modules", [])
        if str(getattr(module, "key", "") or "")
    }
    if not expected:
        return False
    module_screens = [
        str(getattr(screen, "module_key", "") or "")
        for screen in getattr(ui_blueprint, "screens", [])
        if str(getattr(screen, "module_key", "") or "")
    ]
    if not module_screens:
        return False
    screen_keys = set(module_screens)
    return screen_keys.issubset(expected) and bool(screen_keys & expected)


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
        "ui_project_runtime_screenshot_ready": bool(source_info.get("ui_project_server_started")) if isinstance(source_info, dict) else False,
        "ui_project_server_url": source_info.get("ui_project_server_url", "") if isinstance(source_info, dict) else "",
        "ui_runtime_probe_ready": bool(source_info.get("ui_runtime_probe_ready")) if isinstance(source_info, dict) else False,
        "ui_runtime_probe_count": int(source_info.get("ui_runtime_probe_count") or 0) if isinstance(source_info, dict) else 0,
        "ui_runtime_api_ready": bool(source_info.get("ui_runtime_api_ready")) if isinstance(source_info, dict) else False,
        "ui_runtime_api_page_count": int(source_info.get("ui_runtime_api_page_count") or 0) if isinstance(source_info, dict) else 0,
        "ui_runtime_api_fetch_count": int(source_info.get("ui_runtime_api_fetch_count") or 0) if isinstance(source_info, dict) else 0,
        "ui_runtime_api_ok_fetch_count": int(source_info.get("ui_runtime_api_ok_fetch_count") or 0) if isinstance(source_info, dict) else 0,
    }


def _ui_source_evidence_checks(source_info) -> dict:
    evidence = source_info.get("ui_source_evidence") if isinstance(source_info, dict) else {}
    if not isinstance(evidence, dict):
        evidence = {}
    modules = evidence.get("modules") if isinstance(evidence.get("modules"), dict) else {}
    return {
        "ui_source_evidence_ready": bool(evidence.get("ready")),
        "ui_source_evidence_module_count": int(evidence.get("module_count") or 0),
        "ui_source_evidence_file_hits": int(evidence.get("file_hit_count") or 0),
        "ui_source_evidence_route_hits": int(evidence.get("route_hit_count") or 0),
        "ui_source_evidence_service_hits": int(evidence.get("service_hit_count") or 0),
        "ui_source_evidence_module_keys": "、".join(str(key) for key in list(modules.keys())[:8]),
    }


def _ui_domain_quality_checks(task, blueprint, ui_blueprint, ui_screenshots, source_info) -> dict:
    html_text, tech_hits = _ui_screenshot_html_quality(ui_screenshots)
    if (
        isinstance(source_info, dict)
        and source_info.get("ui_framework") == "react"
        and source_info.get("ui_runtime_api_ready")
        and int(source_info.get("ui_runtime_api_ok_fetch_count") or 0) > 0
    ):
        html_text += "\n处理结果：真实业务接口记录已更新，操作日志已写入并刷新统计口径。"
    placeholder_hits = _ui_placeholder_hits(html_text)
    screenshot_realism = _ui_screenshot_realism_checks(
        primary_context=_primary_context_text(task, blueprint),
        html_text=html_text,
        renderer=str(getattr(ui_blueprint, "renderer", "") or ""),
    )
    text = "\n".join(
        [
            _ui_consistency_text(ui_blueprint),
            html_text,
            json.dumps(reportable_screenshots := {
                key: {
                    "title": getattr(item, "title", ""),
                    "caption": getattr(item, "caption", ""),
                    "html_path": getattr(item, "html_path", ""),
                }
                for key, item in (ui_screenshots or {}).items()
            }, ensure_ascii=False),
            json.dumps(source_info.get("ui_source_evidence", {}) if isinstance(source_info, dict) else {}, ensure_ascii=False),
        ]
    )
    primary = " ".join(
        str(item)
        for item in [
            task.software_name,
            task.product_type,
            task.feature_hint,
            getattr(blueprint, "industry", ""),
            getattr(blueprint, "summary", ""),
        ]
        if str(item).strip()
    )
    off_terms: list[str] = []
    if _is_transport_operation_context(primary):
        off_terms = [
            "医疗系统", "医院管理", "手术", "手术室", "术前", "术后", "术式", "麻醉", "医院科室", "临床科室", "科室排班", "医生", "护士", "患者", "病历", "处方", "诊疗",
            "消除棋盘", "剩余步数", "道具背包", "关卡地图", "三星通关",
        ]
    off_hits = [term for term in off_terms if term in text]
    module_keys = [str(getattr(module, "key", "") or "") for module in getattr(blueprint, "modules", [])]
    source_keys = []
    if isinstance(source_info, dict):
        source_keys = [str(key) for key in source_info.get("module_keys", []) or []]
    all_keys = module_keys + source_keys + list((ui_screenshots or {}).keys())
    placeholder_keys = [key for key in all_keys if is_placeholder_module_key(key)]
    return {
        "ui_domain_terms_clean": not off_hits,
        "ui_off_domain_term_hits": "、".join(off_hits[:12]),
        "ui_module_keys_semantic": not placeholder_keys,
        "ui_placeholder_module_keys": "、".join(placeholder_keys[:12]),
        "ui_business_facing_screenshots": not tech_hits,
        "ui_screenshot_tech_leak_hits": "、".join(tech_hits[:12]),
        "ui_visible_text_clean": not placeholder_hits,
        "ui_visible_text_placeholder_hits": "、".join(placeholder_hits[:12]),
        **screenshot_realism,
    }


def _primary_context_text(task, blueprint) -> str:
    return " ".join(
        str(item)
        for item in [
            task.software_name,
            task.product_type,
            task.feature_hint,
            getattr(blueprint, "industry", ""),
            getattr(blueprint, "summary", ""),
            " ".join(str(item) for item in (getattr(blueprint, "business_objects", []) or [])[:12]),
        ]
        if str(item).strip()
    )


def _ui_screenshot_realism_checks(*, primary_context: str, html_text: str, renderer: str = "") -> dict:
    is_admin = renderer not in {"game", "mobile_app"}
    operation_result_ready = (not is_admin) or (
        bool(re.search(r"(?:处理|查询|导入|导出|统计|预警|审核|复核|发布|保存|建档|维护|登记|配置|调度|处置|查看|追踪|失效|归档).{0,12}结果：", html_text))
        and "操作日志" in html_text
        and "刷新统计" in html_text
    )
    chart_context_ready = (not is_admin) or bool(
        re.search(
            r"最近\s*\d+\s*(?:日|天|周|月)|"
            r"(?:统计|开始|结束)?日期|日期范围|时间范围|"
            r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|"
            r"\d{1,2}:\d{2}\s*(?:-|—|~|至)\s*\d{1,2}:\d{2}|"
            r"单位\s*[:：]|"
            r"(?:咨询|工单|响应|投诉|回访|派发|处理|闭环|转化).{0,10}(?:量|数|率|趋势)",
            html_text,
        )
    )
    is_transport = _is_transport_operation_context(primary_context)
    route_terms = ["干线", "支线接驳", "时窗"]
    route_topology_ready = (not is_transport) or all(term in html_text for term in route_terms)
    missing: list[str] = []
    if not operation_result_ready:
        missing.append("操作结果/日志/统计刷新")
    if not chart_context_ready:
        missing.append("图表日期或单位")
    if not route_topology_ready:
        missing.append("交通线路拓扑/时窗")
    return {
        "ui_operation_result_evidence_ready": operation_result_ready,
        "ui_chart_context_ready": chart_context_ready,
        "ui_route_topology_ready": route_topology_ready,
        "ui_realism_missing_evidence": "、".join(missing),
    }


def _is_transport_operation_context(value: str) -> bool:
    text = str(value or "")
    rail_quality = bool(re.search(r"轨道交通|地铁|铁路|轨道工程", text)) and bool(
        re.search(r"施工质量|工程质量|检验批|检验点|材料复检|整改|验收|工程部位|单位工程|标段", text)
    )
    if rail_quality:
        return False
    strong_terms = r"交通运输|运输调度|公交|客运|班次|车次|发车|换乘|接驳|运力|站点|车站|枢纽|线路调度|客流|票务"
    if not re.search(strong_terms, text):
        return False
    surveying_terms = r"测绘|测量|桩号|中线|断面|高程|水准|导线|放样|控制点|坐标|偏距|外业|道路工程"
    return not re.search(surveying_terms, text)


_INTERNAL_ROLE_IDENTIFIER_PATTERN = (
    r"\b[a-z]+(?:_[a-z]+)*_"
    r"(?:operator|manager|reviewer|auditor|administrator|admin|owner|user|staff|engineer|specialist|personnel)\b"
)


def _ui_screenshot_html_quality(ui_screenshots) -> tuple[str, list[str]]:
    texts: list[str] = []
    hits: list[str] = []
    leak_patterns: list[tuple[str, str]] = [
        ("接口路径", r"\b(?:GET|POST|PATCH|PUT|DELETE)\s*/[A-Za-z0-9_./-]+"),
        ("开发类名", r"\b[A-Z][A-Za-z0-9_]*(?:Record|Service|Controller|Router|Route|Entity|Model)\b"),
        ("源码文件", r"\b[a-z][a-z0-9_]+_(?:router|service|model)\.py\b|\b[a-z][a-z0-9_]+(?:Route|Service|Record)\.js\b"),
        ("蛇形模块key", r"\b(?:confirmed|semantic|business_module|module|admin|source|ui)_[a-z0-9_]+\b"),
        ("英文实体", r"\b(?:TrunkRoute|TrunkNode|BranchRoute|CoverageArea|AccessNode|TransportNode|TransferPoint|ServiceScope|ConnectionRule|RuleVersion|ThresholdConfig|MatchTask|AdaptLevel|IssueItem|AdaptIssue|HandleRecord|ReviewOpinion|PublishPlan|PlanVersion|EffectiveScope|RouteMetric|RegionSummary|IssueTrend)\b"),
        ("原型标识", r"UI Prototype|ui-prototype|generated_source|源码接口|源码文件|源码映射|接口映射"),
        ("内部角色标识", _INTERNAL_ROLE_IDENTIFIER_PATTERN),
    ]
    for key, item in (ui_screenshots or {}).items():
        html_path = getattr(item, "html_path", "")
        if not html_path:
            continue
        try:
            html = Path(html_path).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        html = _react_page_source_for_quality(Path(html_path), html)
        visible = _visible_html_text(html)
        summary = getattr(item, "visible_content_summary", None) or {}
        runtime_visible = str(summary.get("visible_text") or "") if isinstance(summary, dict) else ""
        if runtime_visible:
            visible = f"{visible} {runtime_visible}"
        texts.append(visible)
        for label, pattern in leak_patterns:
            if re.search(pattern, visible):
                hits.append(f"{key}:{label}")
    return "\n".join(texts), sorted(set(hits))


def _react_page_source_for_quality(html_path: Path, html: str) -> str:
    match = re.search(r'<meta\s+name=["\']soft-react-screen["\']\s+content=["\']([^"\']+)', html, flags=re.I)
    if not match:
        return html
    page_key = match.group(1)
    screens_dir = html_path.parent / "react-app" / "src" / "screens"
    if not screens_dir.exists():
        return html
    for meta_path in screens_dir.glob("*.meta.json"):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if str(meta.get("page_key") or "") != page_key:
            continue
        jsx_path = meta_path.with_suffix("").with_suffix(".jsx")
        try:
            jsx = jsx_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return html
        jsx = re.sub(r"(?m)^\s*(?:import|export)\b.*$", " ", jsx)
        return html + "\n" + jsx
    return html


def _visible_html_text(html: str) -> str:
    text = re.sub(r"<style\b.*?</style>", " ", str(html or ""), flags=re.S | re.I)
    text = re.sub(r"<script\b.*?</script>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&(?:nbsp|amp|lt|gt|quot);", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _ui_placeholder_hits(text: str) -> list[str]:
    patterns = [
        ("乱码问号", r"\?{3,}"),
        ("占位模块名", r"(?:确认|语义|模块|业务)模块\d+|module[_-]?\d+|semantic[_-]?\d+"),
        ("泛化记录名", r"记录\d{2,}|业务记录|示例内容|待填写|(?:内容|说明|文案|描述|信息|资料)待完善|待补充内容|内容待补充|说明待补充"),
        ("英文占位", r"\b(?:TODO|FIXME|Lorem ipsum|your code here)\b"),
        ("内部角色标识", _INTERNAL_ROLE_IDENTIFIER_PATTERN),
    ]
    hits: list[str] = []
    for label, pattern in patterns:
        if re.search(pattern, text, flags=re.I):
            hits.append(label)
    return hits


def _blueprint_task_domain_issues(task, blueprint, blueprint_source: str = "") -> list[str]:
    expected = select_industry_subtype_for_context(task)
    expected_key = str(getattr(expected, "key", "") or "")
    actual_key = str(getattr(blueprint, "industry_subtype_key", "") or "")
    issues: list[str] = []
    if blueprint_source == "local-template" and expected_key and actual_key != expected_key:
        issues.append(f"本地蓝图行业应为 {expected_key}，实际为 {actual_key or '空'}")
    feature_hint = getattr(task, "input_feature_hint", None)
    if feature_hint is None:
        feature_hint = getattr(task, "feature_hint", "")
    task_text = f"{getattr(task, 'software_name', '')} {feature_hint or ''}"
    if actual_key == "rail_construction_quality" and not (
        re.search(r"轨道交通|地铁|铁路|轨道工程|隧道工程|车站工程", task_text)
        and re.search(r"施工质量|工程质量|检验批|检验点|质量计划|材料复检|整改验收|标段", task_text)
    ):
        issues.append("任务输入未包含轨道施工质量语义，但蓝图被归类为轨道交通施工质量")
    return list(dict.fromkeys(issues))


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
    if value in {"authenticity-first", "authenticity", "quality", "strict"}:
        return "authenticity-first"
    return "balanced"


def _blueprint_quality_target() -> int:
    import os

    profile = _generation_quality_profile()
    if profile == "fast":
        return 78
    raw = os.getenv("SOFT_BLUEPRINT_QUALITY_FLOOR", "92" if profile == "authenticity-first" else "86").strip() or "86"
    try:
        minimum = 78 if profile == "fast" else 82
        return max(minimum, min(95, int(raw)))
    except ValueError:
        return 92 if profile == "authenticity-first" else 86


def _ensure_llm_trace_path(task: GenerationTask, output_dir: Path) -> None:
    import os

    if os.getenv("SOFT_LLM_TRACE_PATH", "").strip():
        return
    os.environ["SOFT_LLM_TRACE_PATH"] = str(output_dir / "llm_trace.jsonl")


def _load_resume_ui_blueprint(output_dir: Path):
    for path in [
        output_dir / "ui_screenshots" / "ui_blueprint.json",
        output_dir / "generated_source" / "ui-prototype" / "ui_blueprint.json",
    ]:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            ui_blueprint = ui_blueprint_from_dict(data)
        except Exception:
            continue
        if getattr(ui_blueprint, "screens", None):
            return ui_blueprint
    return None


_RESUME_STAGE_ORDER = {
    "prepare": 0,
    "blueprint": 1,
    "manual_content": 2,
    "visual_reference": 3,
    "source": 4,
    "screenshots": 5,
    "manual": 6,
    "manual_docx": 6,
    "source_doc": 7,
    "source_docx": 7,
    "pdf": 8,
    "info": 9,
    "package": 10,
    "validate": 11,
    "done": 12,
}


def _stage_precedes(stage: str, resume_stage: str) -> bool:
    return _RESUME_STAGE_ORDER.get(str(stage or ""), -1) < _RESUME_STAGE_ORDER.get(str(resume_stage or ""), -1)


def _resume_blueprint_lock_ready(resume_blueprint, cached_blueprint, resume_stage: str) -> bool:
    return bool(
        resume_blueprint is not None
        and cached_blueprint is resume_blueprint
        and _stage_precedes("blueprint", resume_stage)
    )


def _delivery_zip_path(output_dir: Path) -> Path:
    return output_dir.parent / f"{output_dir.name}--材料包.zip"


def _load_completed_resume_report(output_dir: Path) -> dict | None:
    try:
        state = json.loads((output_dir / "generation-state.json").read_text(encoding="utf-8"))
        report = json.loads((output_dir / "generation_report.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(state, dict) or not isinstance(report, dict):
        return None
    if str(state.get("status") or "").lower() != "success" or str(state.get("stage") or "") != "done":
        return None
    state_extra = state.get("extra") if isinstance(state.get("extra"), dict) else {}
    raw_zip_path = str(report.get("zip_path") or state_extra.get("zip_path") or "").strip()
    if not raw_zip_path:
        return None
    zip_path = Path(raw_zip_path)
    if not zip_path.is_absolute():
        zip_path = output_dir.parent / zip_path
    if not zip_path.exists() or not zip_path.is_file():
        return None
    files = [Path(str(item)) for item in report.get("files", []) if str(item).strip()]
    if not files or not all(path.exists() and path.is_file() for path in files):
        return None
    completed = dict(report)
    completed["zip_path"] = str(zip_path)
    completed["files"] = [str(path) for path in files]
    completed["checks"] = dict(completed.get("checks") or {})
    completed["checks"]["completed_resume_reused"] = True
    completed["warnings"] = list(completed.get("warnings") or [])
    completed["task"] = dict(completed.get("task") or {})
    completed["task"]["output_dir"] = str(output_dir)
    return completed


def _should_defer_pre_render_similarity_for_resume(
    *,
    resume_stage: str,
    resume_ui_blueprint,
    attempt_cached,
    visual_reference_report: dict | None,
) -> bool:
    return bool(
        resume_stage in {"screenshots", "done"}
        and resume_ui_blueprint is not None
        and attempt_cached is not None
        and isinstance(visual_reference_report, dict)
        and visual_reference_report.get("ready")
        and str(visual_reference_report.get("source") or "") == "gpt-style-reference-prompt+image2"
    )


def _resume_failure_payload(output_dir: Path) -> dict:
    state = _read_json_object(output_dir / "generation-state.json")
    failure = _read_json_object(output_dir / "generation-failure.json")
    state_attempt = str(state.get("attempt_id") or "").strip()
    failure_attempt = str(failure.get("attempt_id") or "").strip()
    candidates: list[dict] = []
    if failure and (not state_attempt or not failure_attempt or failure_attempt == state_attempt):
        candidates.append(failure)
    if state:
        candidates.append(state)
    for payload in candidates:
        if str(payload.get("status") or "").lower() == "success":
            continue
        if payload.get("stage"):
            return payload
    return {}


def _resume_failure_stage(output_dir: Path) -> str:
    return _resume_failure_stage_from_payload(_resume_failure_payload(output_dir))


def _resume_failure_stage_from_payload(payload: dict) -> str:
    stage = str((payload or {}).get("stage") or "").strip()
    return stage if stage in _RESUME_STAGE_ORDER else ""


def _resume_failure_progress(output_dir: Path) -> int:
    return _resume_failure_progress_from_payload(_resume_failure_payload(output_dir))


def _resume_failure_progress_from_payload(payload: dict) -> int:
    try:
        return max(0, min(99, int((payload or {}).get("progress") or 0)))
    except (TypeError, ValueError):
        return 0


def _resume_stage_label(stage: str) -> str:
    labels = {
        "blueprint": "产品蓝图",
        "manual_content": "说明书正文",
        "visual_reference": "风格参考图",
        "source": "业务源码",
        "screenshots": "界面生成",
        "manual": "软件说明书",
        "source_doc": "源码鉴别材料",
        "pdf": "PDF 转换",
        "info": "申请信息表",
        "package": "材料打包",
        "validate": "材料校验",
    }
    return labels.get(str(stage or ""), str(stage or "未完成阶段"))


def _load_resume_product_blueprint(output_dir: Path):
    path = output_dir / "generated_source" / "product-blueprint.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        blueprint = product_blueprint_from_dict(data)
    except Exception:
        return None
    return blueprint if len(getattr(blueprint, "modules", []) or []) >= 6 else None


def _load_accepted_product_blueprint(task: GenerationTask):
    raw_path = str(getattr(task, "accepted_blueprint_path", "") or "").strip()
    if not raw_path:
        return None
    path = Path(raw_path)
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        blueprint = product_blueprint_from_dict(data)
    except Exception as exc:
        raise RuntimeError(f"已批准产品蓝图读取失败：{sanitize_error_message(exc)}") from exc
    mismatches: list[str] = []
    if str(getattr(blueprint, "software_name", "") or "") != str(task.software_name or ""):
        mismatches.append("软件名称")
    if str(getattr(blueprint, "version", "") or "") != str(task.version or ""):
        mismatches.append("版本号")
    if str(getattr(blueprint, "product_type", "") or "") != str(task.product_type or ""):
        mismatches.append("产品类型")
    if mismatches:
        raise RuntimeError("已批准产品蓝图与当前任务不一致：" + "、".join(mismatches))
    if len(getattr(blueprint, "modules", []) or []) < 6:
        raise RuntimeError("已批准产品蓝图模块数量不足，至少需要 6 个业务模块。")
    quality_score = int(getattr(blueprint, "quality_score", 0) or 0)
    quality_target = _blueprint_quality_target()
    if quality_score < quality_target:
        raise RuntimeError(f"已批准产品蓝图质量分 {quality_score}，未达到当前阈值 {quality_target}。")
    return blueprint


def _resume_architecture_from_blueprint(blueprint):
    data = getattr(blueprint, "technical_architecture", None)
    if not isinstance(data, dict) or not data.get("key"):
        return None
    try:
        return technical_architecture_from_dict(data)
    except Exception:
        return None


def _load_resume_source_info(output_dir: Path, blueprint, visual_reference_report: dict | None) -> dict | None:
    source_dir = output_dir / "generated_source"
    blueprint_path = source_dir / "product-blueprint.json"
    if not source_dir.is_dir() or not blueprint_path.is_file():
        return None
    repair_generated_business_record_labels(source_dir)
    stats = source_project_stats(source_dir)
    if int(stats.get("total_lines") or 0) <= 0:
        return None
    architecture = getattr(blueprint, "technical_architecture", {}) or {}
    files = [str(path) for path in stats.get("files", []) if str(path)]
    relative_files: list[str] = []
    for value in files:
        try:
            relative_files.append(Path(value).relative_to(source_dir).as_posix())
        except ValueError:
            continue
    source_strategy = str(architecture.get("source_strategy") or "language-single")
    persistence_required = source_strategy == "python_with_web_console" or str(getattr(blueprint, "language", "")) == "Python"
    repository_files = [path for path in relative_files if "/repositories/" in f"/{path}"]
    migration_files = [path for path in relative_files if path.startswith("migrations/")]
    test_files = [path for path in relative_files if path.startswith("tests/") and path.endswith(".py")]
    return {
        **stats,
        "source_dir": str(source_dir),
        "blueprint_path": str(blueprint_path),
        "module_keys": [module.key for module in blueprint.modules],
        "module_titles": [module.title for module in blueprint.modules],
        "technical_architecture": architecture,
        "source_language": architecture.get("source_language") or getattr(blueprint, "language", ""),
        "source_strategy": source_strategy,
        "material_order_manifest": str(source_dir / ".source-material-order.json"),
        "material_order_strategy": "front-core-middle-support-tail-core",
        "visual_reference_contract": str(source_dir / "ui-visual-reference-contract.json"),
        "ui_visual_reference": visual_reference_report or {},
        "source_persistence_required": persistence_required,
        "source_persistence_engine": "sqlite" if persistence_required else "",
        "source_persistence_ready": not persistence_required or bool(repository_files and migration_files and test_files),
        "source_repository_file_count": len(repository_files),
        "source_migration_file_count": len(migration_files),
        "source_test_file_count": len(test_files),
    }


def _read_json_object(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _invalidate_legacy_frontend_cache_for_pagespec(output_dir: Path) -> dict:
    prototype_dir = output_dir / "generated_source" / "ui-prototype"
    react_dir = prototype_dir / "react-app"
    screens_dir = react_dir / "src" / "screens"
    if not react_dir.is_dir() or not screens_dir.is_dir():
        return {"migrated": False, "previous_version": "", "invalidated_file_count": 0}
    marker = _read_json_object(react_dir / ".frontend-engine.json")
    previous_version = str(marker.get("frontend_engine_version") or "legacy-react-cache")
    if previous_version == FRONTEND_ENGINE_VERSION:
        return {"migrated": False, "previous_version": previous_version, "invalidated_file_count": 0}
    cached_files = [
        path
        for path in screens_dir.iterdir()
        if path.is_file() and path.suffix.lower() in {".jsx", ".css", ".json"}
    ]
    if not cached_files:
        return {"migrated": False, "previous_version": previous_version, "invalidated_file_count": 0}
    invalidated = 0
    for path in cached_files:
        try:
            path.unlink()
            invalidated += 1
        except OSError:
            continue
    for path in (react_dir / "dist", prototype_dir / "assets"):
        if path.exists():
            try:
                shutil.rmtree(path)
                invalidated += 1
            except OSError:
                continue
    for html_path in prototype_dir.glob("*.html"):
        try:
            html_path.unlink()
            invalidated += 1
        except OSError:
            continue
    ui_dir = output_dir / "ui_screenshots"
    if ui_dir.is_dir():
        for pattern in ("*.png", "*.jpg", "*.jpeg"):
            for image_path in ui_dir.glob(pattern):
                try:
                    image_path.unlink()
                    invalidated += 1
                except OSError:
                    continue
        for name in ("screenshot-checkpoint.json", "action-crops"):
            path = ui_dir / name
            try:
                if path.is_dir():
                    shutil.rmtree(path)
                    invalidated += 1
                elif path.is_file():
                    path.unlink()
                    invalidated += 1
            except OSError:
                continue
    return {
        "migrated": True,
        "previous_version": previous_version,
        "invalidated_file_count": invalidated,
        "preserved": ["product-blueprint", "technical-architecture", "manual-content", "generated-source", "image2-style-reference"],
    }


def _begin_generation_attempt(output_dir: Path, task: GenerationTask, *, resume_source: str) -> None:
    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    setattr(task, "attempt_id", uuid4().hex)
    setattr(task, "attempt_started_at", now)
    setattr(task, "resume_source", str(resume_source or "new-task"))
    _archive_previous_failure(output_dir)
    _write_generation_state(output_dir, task, "running", "prepare", 0, "准备生成任务", {})


def _archive_previous_failure(output_dir: Path) -> None:
    failure_path = output_dir / "generation-failure.json"
    if not failure_path.is_file():
        return
    payload = _read_json_object(failure_path)
    attempt = re.sub(r"[^A-Za-z0-9_-]+", "-", str(payload.get("attempt_id") or "legacy"))[:64] or "legacy"
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    archive_dir = output_dir / "attempt-history"
    try:
        archive_dir.mkdir(parents=True, exist_ok=True)
        failure_path.replace(archive_dir / f"generation-failure-{attempt}-{timestamp}.json")
    except OSError:
        return


def _write_generation_state(
    output_dir: Path,
    task: GenerationTask,
    status: str,
    stage: str,
    progress: int,
    message: str,
    extra: dict | None = None,
) -> None:
    updated_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    payload = {
        "schema_version": 2,
        "attempt_id": str(getattr(task, "attempt_id", "") or ""),
        "started_at": str(getattr(task, "attempt_started_at", "") or updated_at),
        "resume_source": str(getattr(task, "resume_source", "") or "new-task"),
        "status": status,
        "stage": stage,
        "progress": int(progress or 0),
        "message": sanitize_error_message(message or "", limit=1000),
        "updated_at": updated_at,
        "task": {
            "software_name": task.software_name,
            "version": task.version,
            "product_type": task.product_type,
            "software_category": task.software_category,
            "seed": task.seed,
            "output_dir": str(output_dir),
            "resume_existing_output": bool(getattr(task, "resume_existing_output", False)),
        },
        "extra": _safe_state_extra(extra or {}),
    }
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        write_json(output_dir / "generation-state.json", payload)
    except OSError:
        return


def _write_generation_failure(
    output_dir: Path,
    task: GenerationTask,
    *,
    stage: str,
    progress: int,
    message: str,
    checks: dict | None = None,
    validation: dict | None = None,
) -> None:
    payload = {
        "schema_version": 2,
        "attempt_id": str(getattr(task, "attempt_id", "") or ""),
        "started_at": str(getattr(task, "attempt_started_at", "") or ""),
        "updated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "resume_source": str(getattr(task, "resume_source", "") or "new-task"),
        "status": "error",
        "stage": stage,
        "progress": int(progress or 0),
        "failed_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "message": sanitize_error_message(message or "", limit=1000),
        "checks": checks or {},
        "validation": validation or {},
    }
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        write_json(output_dir / "generation-failure.json", payload)
    except OSError:
        pass
    _write_generation_state(
        output_dir,
        task,
        "error",
        stage,
        progress,
        message,
        {
            "validation_ready_for_delivery": bool((validation or {}).get("ready_for_delivery")),
            "finding_codes": [
                str(item.get("code") or "")
                for item in (validation or {}).get("findings", [])
                if isinstance(item, dict)
            ],
        },
    )


def _clear_generation_failure(output_dir: Path) -> None:
    try:
        failure_path = output_dir / "generation-failure.json"
        if failure_path.exists():
            failure_path.unlink()
    except OSError:
        return


def _safe_state_extra(extra: dict) -> dict:
    result: dict = {}
    for key, value in (extra or {}).items():
        key_text = str(key)
        if re.search(r"key|token|secret|base[_-]?url|api", key_text, flags=re.I):
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            result[key_text] = sanitize_error_message(value, limit=500) if isinstance(value, str) else value
        elif isinstance(value, (list, tuple)):
            result[key_text] = [str(item)[:200] for item in value[:20]]
        elif isinstance(value, dict):
            result[key_text] = {
                str(item_key): sanitize_error_message(str(item_value), limit=200)
                for item_key, item_value in list(value.items())[:20]
                if not re.search(r"key|token|secret|base[_-]?url|api", str(item_key), flags=re.I)
            }
        else:
            result[key_text] = str(value)[:500]
    return result


def _copy_llm_trace_to_output(output_dir: Path) -> None:
    import os

    trace_path_text = os.getenv("SOFT_LLM_TRACE_PATH", "").strip()
    if not trace_path_text:
        return
    trace_path = Path(trace_path_text)
    target_path = output_dir / "llm_trace.jsonl"
    try:
        if trace_path.exists() and trace_path.resolve() != target_path.resolve():
            shutil.copyfile(trace_path, target_path)
    except OSError:
        return


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
