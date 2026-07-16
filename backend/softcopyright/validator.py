from __future__ import annotations

from hashlib import sha256
from datetime import datetime
from pathlib import Path
import json
import os
import re
import zipfile

from .blueprint import ProductBlueprint
from .models import GenerationTask
from .sourcegen import read_source_lines


DELIVERABLE_KINDS = {
    "manual_docx",
    "manual_pdf",
    "info_txt",
    "source_docx",
    "source_pdf",
}

SOURCE_SUFFIXES = {
    ".java",
    ".xml",
    ".py",
    ".js",
    ".ts",
    ".php",
    ".cs",
    ".cpp",
    ".h",
    ".hpp",
    ".html",
    ".css",
    ".sql",
    ".yml",
    ".yaml",
    ".properties",
}

PLACEHOLDER_PATTERNS = (
    "TODO",
    "FIXME",
    "your code here",
    "lorem ipsum",
    "示例内容",
    "待填写",
    "内容待完善",
    "说明待完善",
    "文案待完善",
    "描述待完善",
    "信息待完善",
    "资料待完善",
    "待补充内容",
    "内容待补充",
    "说明待补充",
    "????",
)

MANUAL_INTERNAL_LEAK_PATTERNS = (
    ("接口返回", r"接口返回"),
    ("运行服务", r"运行服务"),
    ("浏览器页面", r"浏览器页面"),
    ("生成项目", r"生成项目"),
    ("源码项目服务", r"源码项目服务"),
    ("可见区域核验", r"可见区域|可见数据核验"),
    ("AI生成说明", r"\bGPT\b|AI\s*(?:生成|提示词|模型说明|接口|代码)|生成说明|提示词|image2|视觉参考|参考稿"),
    ("内部证据文件", r"source-ui-evidence|generated_source|ui-prototype"),
)


def validate_materials(
    *,
    task: GenerationTask,
    blueprint: ProductBlueprint,
    output_dir: Path,
    source_info: dict,
    ui_blueprint,
    ui_screenshots: dict,
    deliverable_files: list[Path],
    zip_path: Path | None = None,
    checks: dict | None = None,
) -> dict:
    checks = checks or {}
    local_template_mode = task.model_provider.lower() in {"local", "local-template", "template", ""}
    blueprint_operation_contract_required = not local_template_mode
    blueprint_operation_contract_ready = (
        bool(checks.get("blueprint_operation_contract_ready"))
        if blueprint_operation_contract_required
        else True
    )
    source_dir = Path(source_info.get("source_dir") or output_dir / "generated_source")
    file_manifest = _source_file_manifest(source_dir)
    deliverables = _deliverable_manifest(task, deliverable_files)
    zip_summary = _zip_summary(zip_path) if zip_path else {"exists": False, "entries": []}
    source_lines = read_source_lines(source_dir) if source_dir.exists() else []
    source_text = "\n".join(source_lines)
    manual_text = _docx_text(_find_deliverable(deliverable_files, task.software_name, ".docx", source=False))
    source_doc_text = _docx_text(_find_deliverable(deliverable_files, "_代码-", ".docx", source=True))
    info_text = _read_text(_find_deliverable(deliverable_files, task.software_name, ".txt", source=False))
    ui_text = _ui_text(ui_blueprint, ui_screenshots)

    module_terms = _terms([module.title for module in blueprint.modules[:8]])
    module_keys = _terms([module.key for module in blueprint.modules[:8]])
    object_terms = _terms(blueprint.business_objects[:12])
    metric_terms = _terms(blueprint.report_metrics[:12])

    authenticity = {
        "source_file_count": len(file_manifest),
        "source_hash": _hash_many(file_manifest),
        "blueprint_hash": _hash_text(json.dumps(blueprint.to_dict(), ensure_ascii=False, sort_keys=True)),
        "blueprint_operation_contract_required": blueprint_operation_contract_required,
        "blueprint_operation_contract_ready": blueprint_operation_contract_ready,
        "blueprint_operation_contract_issues": checks.get("blueprint_operation_contract_issues") or [],
        "blueprint_structured_operation_count": int(checks.get("blueprint_structured_operation_count") or 0),
        "ui_screenshot_render_mode": str(checks.get("ui_screenshot_render_mode") or ""),
        "ui_screenshot_base_url": str(checks.get("ui_screenshot_base_url") or ""),
        "ui_project_server_started": bool(checks.get("ui_project_server_started")),
        "ui_runtime_probe_ready": bool(checks.get("ui_runtime_probe_ready")),
        "ui_runtime_probe_count": int(checks.get("ui_runtime_probe_count") or 0),
        "ui_runtime_api_ready": bool(checks.get("ui_runtime_api_ready")),
        "ui_runtime_api_page_count": int(checks.get("ui_runtime_api_page_count") or 0),
        "ui_runtime_api_fetch_count": int(checks.get("ui_runtime_api_fetch_count") or 0),
        "ui_runtime_api_ok_fetch_count": int(checks.get("ui_runtime_api_ok_fetch_count") or 0),
        "ui_source_evidence_ready": bool(checks.get("ui_source_evidence_ready")),
        "ui_source_evidence_module_count": int(checks.get("ui_source_evidence_module_count") or 0),
        "ui_source_evidence_file_hits": int(checks.get("ui_source_evidence_file_hits") or 0),
        "ui_source_evidence_route_hits": int(checks.get("ui_source_evidence_route_hits") or 0),
        "ui_source_evidence_service_hits": int(checks.get("ui_source_evidence_service_hits") or 0),
        "ui_business_facing_screenshots": bool(checks.get("ui_business_facing_screenshots")),
        "ui_screenshot_tech_leak_hits": str(checks.get("ui_screenshot_tech_leak_hits") or ""),
        "ui_visible_text_clean": bool(checks.get("ui_visible_text_clean")),
        "ui_visible_text_placeholder_hits": str(checks.get("ui_visible_text_placeholder_hits") or ""),
        "ui_visible_content_summary_ready": bool(checks.get("ui_visible_content_summary_ready")),
        "ui_visible_content_summary_count": int(checks.get("ui_visible_content_summary_count") or 0),
        "ui_operation_result_evidence_ready": bool(checks.get("ui_operation_result_evidence_ready")),
        "ui_operation_coverage_ready": bool(checks.get("ui_operation_coverage_ready")),
        "ui_operation_coverage_required_per_module": int(checks.get("ui_operation_coverage_required_per_module") or 0),
        "ui_operation_coverage_module_count": int(checks.get("ui_operation_coverage_module_count") or 0),
        "ui_operation_coverage_min_count": int(checks.get("ui_operation_coverage_min_count") or 0),
        "ui_operation_coverage_missing": checks.get("ui_operation_coverage_missing") or [],
        "ui_chart_context_ready": bool(checks.get("ui_chart_context_ready")),
        "ui_route_topology_ready": bool(checks.get("ui_route_topology_ready")),
        "ui_realism_missing_evidence": str(checks.get("ui_realism_missing_evidence") or ""),
        "ui_visual_identity_signature": str(checks.get("ui_visual_identity_signature") or ""),
        "ui_similarity_gate_ready": bool(checks.get("ui_similarity_gate_ready")),
        "ui_similarity_max_score": float(checks.get("ui_similarity_max_score") or 0),
        "ui_similarity_attempts": int(checks.get("ui_similarity_attempts") or 0),
        "ui_layout_role_count": int(checks.get("ui_layout_role_count") or 0),
        "ui_package_page_max_similarity": float(checks.get("ui_package_page_max_similarity") or 0),
        "ui_similarity_nearest_hash": str(checks.get("ui_similarity_nearest_hash") or ""),
        "ui_similarity_reason": str(checks.get("ui_similarity_reason") or ""),
        "ui_ai_frontend_enabled": bool(checks.get("ui_ai_frontend_enabled")),
        "ui_ai_frontend_ready": bool(checks.get("ui_ai_frontend_ready")),
        "ui_ai_frontend_source": str(checks.get("ui_ai_frontend_source") or ""),
        "ui_ai_frontend_page_count": int(checks.get("ui_ai_frontend_page_count") or 0),
        "ui_shared_confirmation_contract": str(checks.get("ui_shared_confirmation_contract") or ""),
        "ui_shared_confirmation_page_count": int(checks.get("ui_shared_confirmation_page_count") or 0),
        "ui_shared_confirmation_ready": bool(checks.get("ui_shared_confirmation_ready")),
        "ui_visual_prompt_ready": bool(checks.get("ui_visual_prompt_ready")),
        "ui_visual_reference_ready": bool(checks.get("ui_visual_reference_ready")),
        "ui_visual_reference_mode": str(checks.get("ui_visual_reference_mode") or "per_page"),
        "ui_visual_style_reference_ready": bool(checks.get("ui_visual_style_reference_ready")),
        "ui_visual_reference_source": str(checks.get("ui_visual_reference_source") or ""),
        "ui_visual_reference_count": int(checks.get("ui_visual_reference_count") or 0),
        "ui_visual_reference_page_count": int(checks.get("ui_visual_reference_page_count") or 0),
        "ui_visual_reference_image_model": str(checks.get("ui_visual_reference_image_model") or ""),
        "ui_visual_reference_retry_count": int(checks.get("ui_visual_reference_retry_count") or 0),
        "ui_visual_reference_failed_page": str(checks.get("ui_visual_reference_failed_page") or ""),
        "ui_visual_reference_error": str(checks.get("ui_visual_reference_error") or ""),
        "ui_visual_reference_to_code_ready": bool(checks.get("ui_visual_reference_to_code_ready")),
        "ui_visual_reference_before_source_ready": bool(checks.get("ui_visual_reference_before_source_ready")),
        "source_visual_reference_contract": str(checks.get("source_visual_reference_contract") or ""),
        "source_persistence_required": bool(checks.get("source_persistence_required")),
        "source_persistence_engine": str(checks.get("source_persistence_engine") or ""),
        "source_persistence_ready": bool(checks.get("source_persistence_ready")),
        "source_repository_file_count": int(checks.get("source_repository_file_count") or 0),
        "source_migration_file_count": int(checks.get("source_migration_file_count") or 0),
        "source_test_file_count": int(checks.get("source_test_file_count") or 0),
        "source_module_key_hits": _hit_count(module_keys, source_text),
        "source_module_title_hits": _hit_count(module_terms, source_text),
        "manual_module_title_hits": _hit_count(module_terms, manual_text),
        "manual_business_object_hits": _hit_count(object_terms, manual_text),
        "manual_metric_hits": _hit_count(metric_terms, manual_text),
        "ui_module_title_hits": _hit_count(module_terms, ui_text),
        "ui_business_object_hits": _hit_count(object_terms, ui_text),
        "ui_metric_hits": _hit_count(metric_terms, ui_text),
        "info_name_match": task.software_name in info_text,
        "info_version_match": task.version in info_text,
    }
    authenticity["score"] = _authenticity_score(
        authenticity,
        module_total=max(len(module_terms), 1),
        object_total=max(len(object_terms), 1),
        metric_total=max(len(metric_terms), 1),
    )
    authenticity["ready"] = (
        authenticity["score"] >= 80
        and bool(authenticity["blueprint_operation_contract_ready"])
        and authenticity["ui_screenshot_render_mode"] == "project-server"
        and bool(authenticity["ui_project_server_started"])
        and bool(authenticity["ui_runtime_probe_ready"])
        and bool(authenticity["ui_runtime_api_ready"])
        and bool(authenticity["ui_source_evidence_ready"])
        and bool(authenticity["ui_business_facing_screenshots"])
        and bool(authenticity["ui_visible_text_clean"])
        and bool(authenticity["ui_visible_content_summary_ready"])
        and bool(authenticity["ui_operation_result_evidence_ready"])
        and bool(authenticity["ui_operation_coverage_ready"])
        and bool(authenticity["ui_chart_context_ready"])
        and bool(authenticity["ui_route_topology_ready"])
        and bool(authenticity["ui_visual_identity_signature"])
        and bool(authenticity["ui_similarity_gate_ready"])
        and (
            not bool(authenticity["source_persistence_required"])
            or bool(authenticity["source_persistence_ready"])
        )
        and (
            task.model_provider.lower() in {"local", "local-template", "template", ""}
            or (
                bool(authenticity["ui_ai_frontend_ready"])
                and bool(authenticity["ui_shared_confirmation_ready"])
                and bool(authenticity["ui_visual_prompt_ready"])
                and bool(authenticity["ui_visual_reference_ready"])
                and bool(authenticity["ui_visual_reference_before_source_ready"])
                and bool(authenticity["source_visual_reference_contract"])
                and bool(authenticity["ui_visual_reference_to_code_ready"])
            )
        )
    )

    source_selected_pages = int(checks.get("source_selected_pages") or 0)
    source_total_pages = int(checks.get("source_total_pages") or 0)
    source_pdf_page_count = int(checks.get("source_pdf_page_count") or 0)
    expected_zip_names = {path.name for path in deliverable_files if path.exists()}
    normative = {
        "deliverable_count": len([item for item in deliverables if item["exists"]]),
        "deliverable_kinds": sorted({item["kind"] for item in deliverables if item["exists"]}),
        "zip_exists": bool(zip_summary.get("exists")),
        "zip_entry_count": len(zip_summary.get("entries") or []),
        "zip_entries_match_deliverables": set(zip_summary.get("entries") or []) == expected_zip_names if zip_path else False,
        "source_line_target_met": bool(checks.get("source_line_target_met")),
        "source_selection_rule_match": (
            (source_total_pages > 60 and source_selected_pages == 60)
            or (source_total_pages <= 60 and source_selected_pages == source_total_pages)
        ),
        "source_pdf_page_count_match": source_pdf_page_count == source_selected_pages and source_selected_pages > 0,
        "source_continuous_selection": bool(checks.get("source_continuous_selection")),
        "source_lines_per_page": int(checks.get("lines_per_page") or 0),
        "source_presentation_filter_enabled": bool(checks.get("source_presentation_filter_enabled")),
        "source_material_filler_line_count": int(checks.get("source_material_filler_line_count") or 0),
        "source_material_filler_line_ratio": float(checks.get("source_material_filler_line_ratio") or 0),
        "source_low_information_line_ratio": float(checks.get("source_low_information_line_ratio") or 0),
        "source_accessor_boilerplate_line_ratio": float(checks.get("source_accessor_boilerplate_line_ratio") or 0),
        "source_business_logic_line_ratio": float(checks.get("source_business_logic_line_ratio") or 0),
        "source_selected_unique_file_count": int(checks.get("source_selected_unique_file_count") or 0),
        "source_front_unique_file_count": int(checks.get("source_front_unique_file_count") or 0),
        "source_tail_unique_file_count": int(checks.get("source_tail_unique_file_count") or 0),
        "source_max_selected_file_ratio": float(checks.get("source_max_selected_file_ratio") or 0),
        "source_unique_line_ratio": float(checks.get("source_unique_line_ratio") or 0),
        "source_material_diversity_ready": bool(checks.get("source_material_diversity_ready")),
        "manual_pdf_exists": any(item["kind"] == "manual_pdf" and item["exists"] for item in deliverables),
        "source_pdf_exists": any(item["kind"] == "source_pdf" and item["exists"] for item in deliverables),
        "manual_pdf_layout_checked": bool(checks.get("manual_pdf_layout_checked")),
        "source_pdf_layout_checked": bool(checks.get("source_pdf_layout_checked")),
        "manual_pdf_page_count": int(checks.get("manual_pdf_page_count") or 0),
        "source_pdf_page_count": int(checks.get("source_pdf_page_count") or 0),
        "manual_pdf_is_a4": bool(checks.get("manual_pdf_is_a4")),
        "source_pdf_is_a4": bool(checks.get("source_pdf_is_a4")),
        "manual_pdf_text_density_checked": bool(checks.get("manual_pdf_text_density_checked")),
        "manual_pdf_text_density_ready": bool(checks.get("manual_pdf_text_density_ready")),
        "manual_pdf_minimum_lines_per_text_page": int(checks.get("manual_pdf_minimum_lines_per_text_page") or 30),
        "manual_pdf_text_density_page_count": int(checks.get("manual_pdf_text_density_page_count") or 0),
        "manual_pdf_low_text_density_page_count": int(checks.get("manual_pdf_low_text_density_page_count") or 0),
        "manual_pdf_low_text_density_pages": checks.get("manual_pdf_low_text_density_pages") or [],
        "manual_pdf_text_density_soft_pass_count": int(checks.get("manual_pdf_text_density_soft_pass_count") or 0),
        "manual_pdf_text_density_soft_pass_pages": checks.get("manual_pdf_text_density_soft_pass_pages") or [],
        "manual_pdf_text_density_figure_pass_count": int(checks.get("manual_pdf_text_density_figure_pass_count") or 0),
        "manual_pdf_text_density_figure_pass_pages": checks.get("manual_pdf_text_density_figure_pass_pages") or [],
        "manual_pdf_line_requirement_risk_count": int(checks.get("manual_pdf_line_requirement_risk_count") or 0),
        "manual_pdf_line_requirement_risk_pages": checks.get("manual_pdf_line_requirement_risk_pages") or [],
        "manual_pdf_line_requirement_warning": bool(checks.get("manual_pdf_line_requirement_warning")),
        "manual_pdf_min_text_page_line_count": int(checks.get("manual_pdf_min_text_page_line_count") or 0),
        "manual_pdf_average_text_page_line_count": float(checks.get("manual_pdf_average_text_page_line_count") or 0),
        "pdf_conversion_method": str(checks.get("pdf_conversion_method") or ""),
        "pdf_official_conversion_ready": bool(checks.get("pdf_official_conversion_ready")),
        "manual_docx_is_a4": bool(checks.get("manual_docx_is_a4")),
        "source_docx_is_a4": bool(checks.get("source_docx_is_a4")),
        "manual_docx_header_page_number_right": bool(checks.get("manual_docx_header_page_number_right")),
        "source_docx_header_page_number_right": bool(checks.get("source_docx_header_page_number_right")),
        "manual_density_checked": bool(checks.get("manual_density_checked")),
        "manual_character_count": int(checks.get("manual_character_count") or 0),
        "manual_paragraph_count": int(checks.get("manual_paragraph_count") or 0),
        "manual_figure_count": int(checks.get("manual_figure_count") or 0),
        "manual_figure_caption_count": int(checks.get("manual_figure_caption_count") or 0),
        "manual_operation_note_count": int(checks.get("manual_operation_note_count") or 0),
        "manual_field_note_count": int(checks.get("manual_field_note_count") or 0),
        "manual_result_note_count": int(checks.get("manual_result_note_count") or 0),
        "manual_mechanical_label_count": int(checks.get("manual_mechanical_label_count") or 0),
        "manual_repeated_phrase_count": int(checks.get("manual_repeated_phrase_count") or 0),
        "manual_layout_profile": str(checks.get("manual_layout_profile") or ""),
        "manual_figure_paragraph_count": int(checks.get("manual_figure_paragraph_count") or 0),
        "manual_guarded_figure_count": int(checks.get("manual_guarded_figure_count") or 0),
        "manual_guarded_caption_count": int(checks.get("manual_guarded_caption_count") or 0),
        "manual_guarded_heading_count": int(checks.get("manual_guarded_heading_count") or 0),
        "manual_numbered_step_count": int(checks.get("manual_numbered_step_count") or 0),
        "manual_pagination_constraints_ready": bool(checks.get("manual_pagination_constraints_ready")),
        "manual_numbered_steps_ready": bool(checks.get("manual_numbered_steps_ready")),
        "manual_natural_style_ready": bool(checks.get("manual_natural_style_ready")),
        "manual_average_chars_per_paragraph": float(checks.get("manual_average_chars_per_paragraph") or 0),
        "manual_operation_density_ready": bool(checks.get("manual_operation_density_ready")),
        "manual_ui_consistency_checked": bool(checks.get("manual_ui_consistency_checked")),
        "manual_ui_consistency_ready": bool(checks.get("manual_ui_consistency_ready")),
        "manual_ui_semantic_ready": bool(checks.get("manual_ui_semantic_ready")),
        "manual_ui_semantic_checked_count": int(checks.get("manual_ui_semantic_checked_count") or 0),
        "manual_ui_semantic_mismatch_count": int(checks.get("manual_ui_semantic_mismatch_count") or 0),
        "manual_ui_semantic_coverage_missing_count": int(checks.get("manual_ui_semantic_coverage_missing_count") or 0),
        "manual_ui_expected_renderer": str(checks.get("manual_ui_expected_renderer") or ""),
        "manual_ui_renderer_mismatch_count": int(checks.get("manual_ui_renderer_mismatch_count") or 0),
        "manual_ui_renderer_mismatches": checks.get("manual_ui_renderer_mismatches") or [],
        "manual_ui_expected_figure_count": int(checks.get("manual_ui_expected_figure_count") or 0),
        "manual_ui_actual_figure_count": int(checks.get("manual_ui_actual_figure_count") or 0),
        "manual_ui_title_mismatch_count": int(checks.get("manual_ui_title_mismatch_count") or 0),
        "manual_ui_title_mismatches": checks.get("manual_ui_title_mismatches") or [],
        "manual_ui_button_mismatch_count": int(checks.get("manual_ui_button_mismatch_count") or 0),
        "manual_ui_button_mismatches": checks.get("manual_ui_button_mismatches") or [],
        "manual_ui_missing_button_coverage_count": int(checks.get("manual_ui_missing_button_coverage_count") or 0),
        "manual_ui_missing_button_coverage": checks.get("manual_ui_missing_button_coverage") or [],
        "manual_toc_page_numbers_ready": bool(checks.get("manual_toc_page_numbers_ready")),
        "manual_toc_page_number_count": int(checks.get("manual_toc_page_number_count") or 0),
        "placeholder_hits": _placeholder_hits(source_text + "\n" + manual_text + "\n" + info_text),
        "manual_internal_generation_leak_hits": _manual_internal_generation_leak_hits(manual_text + "\n" + info_text),
        "third_party_risk_hits": _third_party_risk_hits(source_dir),
    }
    normative["score"] = _normative_score(normative)
    normative["ready"] = (
        normative["score"] >= 85
        and bool(normative["source_line_target_met"])
        and bool(normative["zip_entries_match_deliverables"])
        and bool(normative["source_continuous_selection"])
        and bool(normative["source_selection_rule_match"])
        and bool(normative["source_pdf_page_count_match"])
        and bool(normative["source_material_diversity_ready"])
        and bool(normative["pdf_official_conversion_ready"])
        and bool(normative["manual_docx_is_a4"])
        and bool(normative["source_docx_is_a4"])
        and bool(normative["manual_pdf_is_a4"])
        and bool(normative["source_pdf_is_a4"])
        and bool(normative["manual_pdf_text_density_ready"])
        and bool(normative["manual_pagination_constraints_ready"])
        and bool(normative["manual_numbered_steps_ready"])
        and bool(normative["manual_natural_style_ready"])
        and bool(normative["manual_ui_consistency_ready"])
        and bool(normative["manual_ui_semantic_ready"])
        and bool(normative["manual_toc_page_numbers_ready"])
        and bool(normative["manual_docx_header_page_number_right"])
        and bool(normative["source_docx_header_page_number_right"])
        and not normative["placeholder_hits"]
        and not normative["manual_internal_generation_leak_hits"]
    )

    findings = _findings(authenticity, normative)
    return {
        "version": "2026-07-16",
        "task_id": task.task_id,
        "software_name": task.software_name,
        "version_name": task.version,
        "language": task.language,
        "product_type": task.product_type,
        "authenticity": authenticity,
        "normative": normative,
        "source_files": file_manifest,
        "deliverables": deliverables,
        "zip": zip_summary,
        "findings": findings,
        "ready_for_delivery": authenticity["ready"] and normative["ready"] and not findings,
    }


def validation_checks(validation: dict) -> dict:
    authenticity = validation.get("authenticity") or {}
    normative = validation.get("normative") or {}
    return {
        "authenticity_score": authenticity.get("score", 0),
        "authenticity_ready": bool(authenticity.get("ready")),
        "normative_score": normative.get("score", 0),
        "normative_ready": bool(normative.get("ready")),
        "validation_ready_for_delivery": bool(validation.get("ready_for_delivery")),
        "validation_finding_count": len(validation.get("findings") or []),
        "validation_source_file_count": authenticity.get("source_file_count", 0),
        "validation_source_hash": authenticity.get("source_hash", ""),
        "validation_blueprint_operation_contract_required": bool(authenticity.get("blueprint_operation_contract_required")),
        "validation_blueprint_operation_contract_ready": bool(authenticity.get("blueprint_operation_contract_ready")),
        "validation_blueprint_operation_contract_issues": authenticity.get("blueprint_operation_contract_issues", []),
        "validation_blueprint_structured_operation_count": authenticity.get("blueprint_structured_operation_count", 0),
        "validation_zip_entries_match_deliverables": bool(normative.get("zip_entries_match_deliverables")),
        "validation_placeholder_hit_count": len(normative.get("placeholder_hits") or []),
        "validation_ui_project_server_started": bool(authenticity.get("ui_project_server_started")),
        "validation_ui_runtime_probe_ready": bool(authenticity.get("ui_runtime_probe_ready")),
        "validation_ui_source_evidence_ready": bool(authenticity.get("ui_source_evidence_ready")),
        "validation_ui_screenshot_render_mode": authenticity.get("ui_screenshot_render_mode", ""),
        "validation_ui_business_facing_screenshots": bool(authenticity.get("ui_business_facing_screenshots")),
        "validation_ui_visible_content_summary_ready": bool(authenticity.get("ui_visible_content_summary_ready")),
        "validation_ui_visible_content_summary_count": authenticity.get("ui_visible_content_summary_count", 0),
        "validation_ui_operation_result_evidence_ready": bool(authenticity.get("ui_operation_result_evidence_ready")),
        "validation_ui_operation_coverage_ready": bool(authenticity.get("ui_operation_coverage_ready")),
        "validation_ui_operation_coverage_required_per_module": authenticity.get("ui_operation_coverage_required_per_module", 0),
        "validation_ui_operation_coverage_min_count": authenticity.get("ui_operation_coverage_min_count", 0),
        "validation_ui_chart_context_ready": bool(authenticity.get("ui_chart_context_ready")),
        "validation_ui_route_topology_ready": bool(authenticity.get("ui_route_topology_ready")),
        "validation_ui_realism_missing_evidence": authenticity.get("ui_realism_missing_evidence", ""),
        "validation_ui_visual_identity_signature": authenticity.get("ui_visual_identity_signature", ""),
        "validation_ui_similarity_gate_ready": bool(authenticity.get("ui_similarity_gate_ready")),
        "validation_ui_similarity_max_score": authenticity.get("ui_similarity_max_score", 0),
        "validation_ui_similarity_attempts": authenticity.get("ui_similarity_attempts", 0),
        "validation_ui_layout_role_count": authenticity.get("ui_layout_role_count", 0),
        "validation_ui_similarity_nearest_hash": authenticity.get("ui_similarity_nearest_hash", ""),
        "validation_ui_shared_confirmation_contract": authenticity.get("ui_shared_confirmation_contract", ""),
        "validation_ui_shared_confirmation_page_count": authenticity.get("ui_shared_confirmation_page_count", 0),
        "validation_ui_shared_confirmation_ready": bool(authenticity.get("ui_shared_confirmation_ready")),
        "validation_ui_visual_prompt_ready": bool(authenticity.get("ui_visual_prompt_ready")),
        "validation_ui_visual_reference_ready": bool(authenticity.get("ui_visual_reference_ready")),
        "validation_ui_visual_reference_mode": authenticity.get("ui_visual_reference_mode", ""),
        "validation_ui_visual_style_reference_ready": bool(authenticity.get("ui_visual_style_reference_ready")),
        "validation_ui_visual_reference_count": authenticity.get("ui_visual_reference_count", 0),
        "validation_ui_visual_reference_source": authenticity.get("ui_visual_reference_source", ""),
        "validation_ui_visual_reference_image_model": authenticity.get("ui_visual_reference_image_model", ""),
        "validation_ui_visual_reference_failed_page": authenticity.get("ui_visual_reference_failed_page", ""),
        "validation_ui_visual_reference_to_code_ready": bool(authenticity.get("ui_visual_reference_to_code_ready")),
        "validation_ui_visual_reference_before_source_ready": bool(authenticity.get("ui_visual_reference_before_source_ready")),
        "validation_source_visual_reference_contract": authenticity.get("source_visual_reference_contract", ""),
        "validation_source_persistence_required": bool(authenticity.get("source_persistence_required")),
        "validation_source_persistence_engine": authenticity.get("source_persistence_engine", ""),
        "validation_source_persistence_ready": bool(authenticity.get("source_persistence_ready")),
        "validation_source_repository_file_count": authenticity.get("source_repository_file_count", 0),
        "validation_source_migration_file_count": authenticity.get("source_migration_file_count", 0),
        "validation_source_test_file_count": authenticity.get("source_test_file_count", 0),
        "manual_operation_density_ready": bool(normative.get("manual_operation_density_ready")),
        "manual_toc_page_numbers_ready": bool(normative.get("manual_toc_page_numbers_ready")),
        "manual_toc_page_number_count": normative.get("manual_toc_page_number_count", 0),
        "manual_natural_style_ready": bool(normative.get("manual_natural_style_ready")),
        "manual_mechanical_label_count": normative.get("manual_mechanical_label_count", 0),
        "manual_repeated_phrase_count": normative.get("manual_repeated_phrase_count", 0),
        "manual_layout_profile": normative.get("manual_layout_profile", ""),
        "manual_figure_paragraph_count": normative.get("manual_figure_paragraph_count", 0),
        "manual_guarded_figure_count": normative.get("manual_guarded_figure_count", 0),
        "manual_guarded_caption_count": normative.get("manual_guarded_caption_count", 0),
        "manual_guarded_heading_count": normative.get("manual_guarded_heading_count", 0),
        "manual_numbered_step_count": normative.get("manual_numbered_step_count", 0),
        "manual_pagination_constraints_ready": bool(normative.get("manual_pagination_constraints_ready")),
        "manual_numbered_steps_ready": bool(normative.get("manual_numbered_steps_ready")),
        "manual_figure_count": normative.get("manual_figure_count", 0),
        "manual_operation_note_count": normative.get("manual_operation_note_count", 0),
        "manual_ui_consistency_checked": bool(normative.get("manual_ui_consistency_checked")),
        "manual_ui_consistency_ready": bool(normative.get("manual_ui_consistency_ready")),
        "manual_ui_semantic_ready": bool(normative.get("manual_ui_semantic_ready")),
        "manual_ui_semantic_checked_count": normative.get("manual_ui_semantic_checked_count", 0),
        "manual_ui_semantic_mismatch_count": normative.get("manual_ui_semantic_mismatch_count", 0),
        "manual_ui_semantic_coverage_missing_count": normative.get("manual_ui_semantic_coverage_missing_count", 0),
        "manual_ui_expected_figure_count": normative.get("manual_ui_expected_figure_count", 0),
        "manual_ui_actual_figure_count": normative.get("manual_ui_actual_figure_count", 0),
        "manual_ui_title_mismatch_count": normative.get("manual_ui_title_mismatch_count", 0),
        "manual_ui_title_mismatches": normative.get("manual_ui_title_mismatches", []),
        "manual_ui_button_mismatch_count": normative.get("manual_ui_button_mismatch_count", 0),
        "manual_ui_button_mismatches": normative.get("manual_ui_button_mismatches", []),
        "manual_ui_missing_button_coverage_count": normative.get("manual_ui_missing_button_coverage_count", 0),
        "manual_ui_missing_button_coverage": normative.get("manual_ui_missing_button_coverage", []),
        "source_continuous_selection": bool(normative.get("source_continuous_selection")),
        "source_material_filler_line_count": normative.get("source_material_filler_line_count", 0),
        "pdf_official_conversion_ready": bool(normative.get("pdf_official_conversion_ready")),
        "manual_pdf_layout_checked": bool(normative.get("manual_pdf_layout_checked")),
        "source_pdf_layout_checked": bool(normative.get("source_pdf_layout_checked")),
        "manual_pdf_page_count": normative.get("manual_pdf_page_count", 0),
        "source_pdf_page_count": normative.get("source_pdf_page_count", 0),
        "source_pdf_page_count_match": bool(normative.get("source_pdf_page_count_match")),
        "manual_pdf_is_a4": bool(normative.get("manual_pdf_is_a4")),
        "source_pdf_is_a4": bool(normative.get("source_pdf_is_a4")),
        "manual_pdf_text_density_checked": bool(normative.get("manual_pdf_text_density_checked")),
        "manual_pdf_text_density_ready": bool(normative.get("manual_pdf_text_density_ready")),
        "manual_pdf_text_density_page_count": normative.get("manual_pdf_text_density_page_count", 0),
        "manual_pdf_low_text_density_page_count": normative.get("manual_pdf_low_text_density_page_count", 0),
        "manual_pdf_text_density_soft_pass_count": normative.get("manual_pdf_text_density_soft_pass_count", 0),
        "manual_pdf_text_density_soft_pass_pages": normative.get("manual_pdf_text_density_soft_pass_pages", []),
        "manual_pdf_line_requirement_risk_count": normative.get("manual_pdf_line_requirement_risk_count", 0),
        "manual_pdf_line_requirement_risk_pages": normative.get("manual_pdf_line_requirement_risk_pages", []),
        "manual_pdf_line_requirement_warning": bool(normative.get("manual_pdf_line_requirement_warning")),
        "manual_pdf_min_text_page_line_count": normative.get("manual_pdf_min_text_page_line_count", 0),
        "manual_pdf_average_text_page_line_count": normative.get("manual_pdf_average_text_page_line_count", 0),
        "manual_docx_is_a4": bool(normative.get("manual_docx_is_a4")),
        "source_docx_is_a4": bool(normative.get("source_docx_is_a4")),
        "manual_docx_header_page_number_right": bool(normative.get("manual_docx_header_page_number_right")),
        "source_docx_header_page_number_right": bool(normative.get("source_docx_header_page_number_right")),
        "source_low_information_line_ratio": normative.get("source_low_information_line_ratio", 0),
        "source_accessor_boilerplate_line_ratio": normative.get("source_accessor_boilerplate_line_ratio", 0),
        "source_business_logic_line_ratio": normative.get("source_business_logic_line_ratio", 0),
        "source_selected_unique_file_count": normative.get("source_selected_unique_file_count", 0),
        "source_front_unique_file_count": normative.get("source_front_unique_file_count", 0),
        "source_tail_unique_file_count": normative.get("source_tail_unique_file_count", 0),
        "source_max_selected_file_ratio": normative.get("source_max_selected_file_ratio", 0),
        "source_unique_line_ratio": normative.get("source_unique_line_ratio", 0),
        "source_material_diversity_ready": bool(normative.get("source_material_diversity_ready")),
    }


def build_materials_manifest(
    *,
    task: GenerationTask,
    blueprint: ProductBlueprint,
    validation: dict,
    source_info: dict,
    source_report: dict,
    ui_blueprint,
    ui_screenshots: dict,
    pdf_conversions: list[dict],
    generation_report_path: Path,
) -> dict:
    source_pages = source_report.get("source_page_sources") or []
    screenshot_refs = {
        key: {
            "title": getattr(item, "title", ""),
            "caption": getattr(item, "caption", ""),
            "image_path": getattr(item, "image_path", ""),
            "html_path": getattr(item, "html_path", ""),
        }
        for key, item in (ui_screenshots or {}).items()
    }
    ui_runtime = _ui_runtime_manifest(source_info, validation)
    return {
        "version": "2026-06-09",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "software": {
            "name": task.software_name,
            "version": task.version,
            "language": task.language,
            "product_type": task.product_type,
            "seed": task.seed,
            "generation_mode": task.model_provider,
            "randomness": task.randomness,
        },
        "blueprint": {
            "hash": (validation.get("authenticity") or {}).get("blueprint_hash", ""),
            "source": getattr(blueprint, "source", "") or "",
            "quality_score": getattr(blueprint, "quality_score", 0),
            "module_count": len(getattr(blueprint, "modules", []) or []),
            "business_object_count": len(getattr(blueprint, "business_objects", []) or []),
        },
        "source_project": {
            "directory": source_info.get("source_dir", ""),
            "hash": (validation.get("authenticity") or {}).get("source_hash", ""),
            "total_lines": source_report.get("source_total_lines", source_info.get("total_lines", 0)),
            "persistence": {
                "required": bool((validation.get("authenticity") or {}).get("source_persistence_required")),
                "engine": (validation.get("authenticity") or {}).get("source_persistence_engine", ""),
                "ready": bool((validation.get("authenticity") or {}).get("source_persistence_ready")),
                "repository_file_count": (validation.get("authenticity") or {}).get("source_repository_file_count", 0),
                "migration_file_count": (validation.get("authenticity") or {}).get("source_migration_file_count", 0),
                "test_file_count": (validation.get("authenticity") or {}).get("source_test_file_count", 0),
            },
            "material_order_manifest": source_info.get("material_order_manifest", ""),
            "material_order_strategy": source_info.get(
                "material_order_strategy",
                source_report.get("source_material_order_strategy", ""),
            ),
            "files": validation.get("source_files", []),
        },
        "ui_runtime": ui_runtime,
        "source_material_pages": {
            "lines_per_page": source_report.get("lines_per_page", 50),
            "selection_mode": source_report.get("selection_mode", ""),
            "total_pages": source_report.get("source_total_pages", 0),
            "selected_pages": source_report.get("source_selected_pages", 0),
            "continuous_selection": bool(source_report.get("source_continuous_selection")),
            "order": {
                "manifest_used": bool(source_report.get("source_material_order_manifest_used")),
                "strategy": source_report.get("source_material_order_strategy", ""),
                "file_count": source_report.get("source_material_order_file_count", 0),
            },
            "quality": {
                "presentation_filter_enabled": bool(source_report.get("source_presentation_filter_enabled")),
                "material_filler_line_count": source_report.get("source_material_filler_line_count", 0),
                "material_filler_line_ratio": source_report.get("source_material_filler_line_ratio", 0),
                "low_information_line_ratio": source_report.get("source_low_information_line_ratio", 0),
                "accessor_boilerplate_line_ratio": source_report.get("source_accessor_boilerplate_line_ratio", 0),
                "business_logic_line_ratio": source_report.get("source_business_logic_line_ratio", 0),
                "selected_unique_file_count": source_report.get("source_selected_unique_file_count", 0),
                "front_unique_file_count": source_report.get("source_front_unique_file_count", 0),
                "tail_unique_file_count": source_report.get("source_tail_unique_file_count", 0),
                "max_selected_file_ratio": source_report.get("source_max_selected_file_ratio", 0),
                "unique_line_ratio": source_report.get("source_unique_line_ratio", 0),
                "diversity_ready": bool(source_report.get("source_material_diversity_ready")),
                "candidate_low_information_line_ratio": source_report.get("source_candidate_low_information_line_ratio", 0),
            },
            "pages": source_pages,
        },
        "manual_references": _manual_reference_map(blueprint, screenshot_refs, source_info),
        "pdf_conversion": pdf_conversions,
        "llm_trace": _llm_trace_summary(),
        "deliverables": validation.get("deliverables", []),
        "zip": validation.get("zip", {}),
        "validation": {
            "authenticity_score": (validation.get("authenticity") or {}).get("score", 0),
            "normative_score": (validation.get("normative") or {}).get("score", 0),
            "ready_for_delivery": validation.get("ready_for_delivery", False),
            "findings": validation.get("findings", []),
        },
        "layout": {
            "manual_docx_is_a4": (validation.get("normative") or {}).get("manual_docx_is_a4", False),
            "source_docx_is_a4": (validation.get("normative") or {}).get("source_docx_is_a4", False),
            "manual_docx_header_page_number_right": (validation.get("normative") or {}).get("manual_docx_header_page_number_right", False),
            "source_docx_header_page_number_right": (validation.get("normative") or {}).get("source_docx_header_page_number_right", False),
            "pdf_official_conversion_ready": (validation.get("normative") or {}).get("pdf_official_conversion_ready", False),
            "pdf_conversion_method": (validation.get("normative") or {}).get("pdf_conversion_method", ""),
            "manual_pdf_is_a4": (validation.get("normative") or {}).get("manual_pdf_is_a4", False),
            "source_pdf_is_a4": (validation.get("normative") or {}).get("source_pdf_is_a4", False),
            "manual_pdf_page_count": (validation.get("normative") or {}).get("manual_pdf_page_count", 0),
            "source_pdf_page_count": (validation.get("normative") or {}).get("source_pdf_page_count", 0),
            "manual_pdf_text_density_checked": (validation.get("normative") or {}).get("manual_pdf_text_density_checked", False),
            "manual_pdf_text_density_ready": (validation.get("normative") or {}).get("manual_pdf_text_density_ready", False),
            "manual_pdf_text_density_page_count": (validation.get("normative") or {}).get("manual_pdf_text_density_page_count", 0),
            "manual_pdf_low_text_density_page_count": (validation.get("normative") or {}).get("manual_pdf_low_text_density_page_count", 0),
            "manual_pdf_low_text_density_pages": (validation.get("normative") or {}).get("manual_pdf_low_text_density_pages", []),
            "manual_pdf_text_density_soft_pass_count": (validation.get("normative") or {}).get("manual_pdf_text_density_soft_pass_count", 0),
            "manual_pdf_text_density_soft_pass_pages": (validation.get("normative") or {}).get("manual_pdf_text_density_soft_pass_pages", []),
            "manual_pdf_text_density_figure_pass_count": (validation.get("normative") or {}).get("manual_pdf_text_density_figure_pass_count", 0),
            "manual_pdf_text_density_figure_pass_pages": (validation.get("normative") or {}).get("manual_pdf_text_density_figure_pass_pages", []),
            "manual_pdf_line_requirement_risk_count": (validation.get("normative") or {}).get("manual_pdf_line_requirement_risk_count", 0),
            "manual_pdf_line_requirement_risk_pages": (validation.get("normative") or {}).get("manual_pdf_line_requirement_risk_pages", []),
            "manual_pdf_line_requirement_warning": (validation.get("normative") or {}).get("manual_pdf_line_requirement_warning", False),
        },
        "generation_report_path": str(generation_report_path),
    }


def _source_file_manifest(source_dir: Path) -> list[dict]:
    if not source_dir.exists():
        return []
    files: list[dict] = []
    for path in sorted(source_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SOURCE_SUFFIXES:
            continue
        relative = path.relative_to(source_dir).as_posix()
        if "node_modules/" in relative or "/vendor/" in relative:
            continue
        content = _read_text(path)
        files.append(
            {
                "path": relative,
                "suffix": path.suffix.lower(),
                "lines": len(content.splitlines()),
                "sha256": _hash_text(content),
            }
        )
    return files


def _ui_runtime_manifest(source_info: dict, validation: dict) -> dict:
    authenticity = validation.get("authenticity") or {}
    evidence = source_info.get("ui_source_evidence") if isinstance(source_info, dict) else {}
    if not isinstance(evidence, dict):
        evidence = {}
    return {
        "render_mode": authenticity.get("ui_screenshot_render_mode") or source_info.get("ui_screenshot_render_mode", ""),
        "base_url": authenticity.get("ui_screenshot_base_url") or source_info.get("ui_screenshot_base_url", ""),
        "project_server_started": bool(authenticity.get("ui_project_server_started") or source_info.get("ui_project_server_started")),
        "runtime_probe_ready": bool(authenticity.get("ui_runtime_probe_ready") or source_info.get("ui_runtime_probe_ready")),
        "runtime_probe_count": int(authenticity.get("ui_runtime_probe_count") or source_info.get("ui_runtime_probe_count") or 0),
        "runtime_probes": source_info.get("ui_runtime_probes") or evidence.get("runtime_probes") or [],
        "runtime_api_ready": bool(authenticity.get("ui_runtime_api_ready") or source_info.get("ui_runtime_api_ready") or evidence.get("runtime_api_ready")),
        "runtime_api_page_count": int(authenticity.get("ui_runtime_api_page_count") or source_info.get("ui_runtime_api_page_count") or evidence.get("runtime_api_page_count") or 0),
        "runtime_api_fetch_count": int(authenticity.get("ui_runtime_api_fetch_count") or source_info.get("ui_runtime_api_fetch_count") or evidence.get("runtime_api_fetch_count") or 0),
        "runtime_api_ok_fetch_count": int(authenticity.get("ui_runtime_api_ok_fetch_count") or source_info.get("ui_runtime_api_ok_fetch_count") or evidence.get("runtime_api_ok_fetch_count") or 0),
        "runtime_api_pages": source_info.get("ui_runtime_api_pages") or evidence.get("runtime_api_pages") or [],
        "source_evidence_ready": bool(authenticity.get("ui_source_evidence_ready") or evidence.get("ready")),
        "source_evidence_module_count": int(authenticity.get("ui_source_evidence_module_count") or evidence.get("module_count") or 0),
        "source_evidence_file_hits": int(authenticity.get("ui_source_evidence_file_hits") or evidence.get("file_hit_count") or 0),
        "source_evidence_route_hits": int(authenticity.get("ui_source_evidence_route_hits") or evidence.get("route_hit_count") or 0),
        "source_evidence_service_hits": int(authenticity.get("ui_source_evidence_service_hits") or evidence.get("service_hit_count") or 0),
        "source_evidence_file": "generated_source/ui-prototype/source-ui-evidence.json",
        "business_facing_screenshots": bool(authenticity.get("ui_business_facing_screenshots")),
        "tech_leak_hits": authenticity.get("ui_screenshot_tech_leak_hits", ""),
        "visible_text_clean": bool(authenticity.get("ui_visible_text_clean")),
        "visible_text_placeholder_hits": authenticity.get("ui_visible_text_placeholder_hits", ""),
        "operation_result_evidence_ready": bool(authenticity.get("ui_operation_result_evidence_ready")),
        "chart_context_ready": bool(authenticity.get("ui_chart_context_ready")),
        "route_topology_ready": bool(authenticity.get("ui_route_topology_ready")),
        "realism_missing_evidence": authenticity.get("ui_realism_missing_evidence", ""),
        "visual_identity_signature": authenticity.get("ui_visual_identity_signature", ""),
        "similarity_gate_ready": bool(authenticity.get("ui_similarity_gate_ready")),
        "similarity_max_score": authenticity.get("ui_similarity_max_score", 0),
        "similarity_attempts": authenticity.get("ui_similarity_attempts", 0),
        "layout_role_count": authenticity.get("ui_layout_role_count", 0),
        "similarity_nearest_hash": authenticity.get("ui_similarity_nearest_hash", ""),
    }


def _deliverable_manifest(task: GenerationTask, files: list[Path]) -> list[dict]:
    return [
        {
            "path": str(path),
            "name": path.name,
            "kind": _deliverable_kind(task, path),
            "exists": path.exists(),
            "size": path.stat().st_size if path.exists() else 0,
            "sha256": _hash_file(path) if path.exists() else "",
        }
        for path in files
    ]


def _deliverable_kind(task: GenerationTask, path: Path) -> str:
    name = path.name
    suffix = path.suffix.lower()
    is_source = _is_source_material_name(name, task.language)
    if suffix == ".txt":
        return "info_txt"
    if is_source:
        return "source_pdf" if suffix == ".pdf" else "source_docx"
    if task.software_name in name:
        return "manual_pdf" if suffix == ".pdf" else "manual_docx"
    return "unknown"


def _manual_reference_map(blueprint: ProductBlueprint, screenshot_refs: dict, source_info: dict) -> list[dict]:
    references: list[dict] = [
        {
            "chapter": "软件概述",
            "modules": [module.title for module in getattr(blueprint, "modules", [])[:3]],
            "screenshots": ["login", "dashboard"],
            "interfaces": [],
            "business_objects": list(getattr(blueprint, "business_objects", [])[:6]),
        },
        {
            "chapter": "统计分析",
            "modules": [module.title for module in getattr(blueprint, "modules", [])[:6]],
            "screenshots": ["statistics"],
            "interfaces": [],
            "business_objects": list(getattr(blueprint, "business_objects", [])[:8]),
        },
    ]
    for index, module in enumerate(getattr(blueprint, "modules", []) or [], start=1):
        screenshot_keys = [key for key in (module.key, f"module_{module.key}") if key in screenshot_refs]
        references.append(
            {
                "chapter": f"4.{index} {module.title}",
                "modules": [module.title],
                "module_key": module.key,
                "screenshots": screenshot_keys,
                "interfaces": _module_interface_refs(module.key, source_info),
                "business_objects": list(getattr(module, "entities", []) or [])[:6],
                "statistics": list(getattr(blueprint, "report_metrics", []) or [])[:6],
            }
        )
    return references


def _module_interface_refs(module_key: str, source_info: dict) -> list[str]:
    files = [str(path).replace("\\", "/") for path in source_info.get("files", []) or []]
    key = re.sub(r"[^A-Za-z0-9]+", "", module_key or "").lower()
    refs: list[str] = []
    for path in files:
        normalized = re.sub(r"[^A-Za-z0-9]+", "", Path(path).stem).lower()
        if key and key in normalized and any(part in path.lower() for part in ("controller", "router", "api", "service")):
            refs.append(path)
    return refs[:8]


def _llm_trace_summary() -> dict:
    trace_path = os.getenv("SOFT_LLM_TRACE_PATH", "").strip()
    summary = {
        "configured": bool(trace_path),
        "path": trace_path,
        "records": 0,
        "errors": 0,
        "api_key_recorded": False,
    }
    if not trace_path:
        return summary
    path = Path(trace_path)
    if not path.exists():
        return summary
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not line.strip():
                continue
            summary["records"] += 1
            lower = line.lower()
            if "error" in lower or "exception" in lower or "timeout" in lower:
                summary["errors"] += 1
            if "api_key" in lower or "authorization" in lower or "bearer " in lower:
                summary["api_key_recorded"] = True
    except Exception:
        return summary
    return summary


def _zip_summary(zip_path: Path | None) -> dict:
    if not zip_path or not zip_path.exists():
        return {"exists": False, "entries": []}
    with zipfile.ZipFile(zip_path, "r") as archive:
        entries = sorted(item.filename for item in archive.infolist() if not item.is_dir())
    return {
        "exists": True,
        "path": str(zip_path),
        "size": zip_path.stat().st_size,
        "entries": entries,
        "sha256": _hash_file(zip_path),
    }


def _find_deliverable(files: list[Path], marker: str, suffix: str, *, source: bool) -> Path | None:
    for path in files:
        name = path.name
        if path.suffix.lower() != suffix:
            continue
        is_source = bool("_代码-" in name or "代码" in name or "浠ｇ爜" in name or re.search(r"-\([^)]+\)", name))
        if source == is_source and marker in name:
            return path
        if source and is_source:
            return path
    return None


def _is_source_material_name(name: str, language: str) -> bool:
    return (
        "_代码-" in name
        or "代码" in name
        or "浠ｇ爜" in name
        or f"-({language})" in name
        or bool(re.search(r"-\([A-Za-z+#]+\)", name))
    )


def _docx_text(path: Path | None) -> str:
    if not path or not path.exists():
        return ""
    try:
        from docx import Document

        document = Document(path)
        parts = [paragraph.text for paragraph in document.paragraphs]
        for table in document.tables:
            for row in table.rows:
                for cell in row.cells:
                    parts.append(cell.text)
        return "\n".join(parts)
    except Exception:
        return ""


def _ui_text(ui_blueprint, ui_screenshots: dict) -> str:
    parts: list[str] = []
    if ui_blueprint:
        parts.append(getattr(ui_blueprint, "visual_style", "") or "")
        for screen in getattr(ui_blueprint, "screens", []) or []:
            parts.extend(
                [
                    getattr(screen, "key", "") or "",
                    getattr(screen, "title", "") or "",
                    getattr(screen, "caption", "") or "",
                    " ".join(str(item) for item in getattr(screen, "components", []) or []),
                    " ".join(str(item) for item in getattr(screen, "sample_data", []) or []),
                ]
            )
    for item in (ui_screenshots or {}).values():
        parts.extend([getattr(item, "title", "") or "", getattr(item, "caption", "") or ""])
    return "\n".join(parts)


def _read_text(path: Path | None) -> str:
    if not path or not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="gbk", errors="ignore")


def _terms(values) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        text = str(value or "").strip()
        if len(text) < 2 or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _hit_count(terms: list[str], text: str) -> int:
    if not text:
        return 0
    return sum(1 for term in terms if term and term in text)


def _placeholder_hits(text: str) -> list[str]:
    hits: list[str] = []
    lower_text = text.lower()
    for pattern in PLACEHOLDER_PATTERNS:
        haystack = lower_text if pattern.isascii() else text
        needle = pattern.lower() if pattern.isascii() else pattern
        if needle in haystack:
            hits.append(pattern)
    return hits


def _manual_internal_generation_leak_hits(text: str) -> list[str]:
    hits: list[str] = []
    for label, pattern in MANUAL_INTERNAL_LEAK_PATTERNS:
        if re.search(pattern, text, flags=re.I):
            hits.append(label)
    return sorted(set(hits))


def _third_party_risk_hits(source_dir: Path) -> list[str]:
    if not source_dir.exists():
        return []
    risky_roots = {"node_modules", "vendor", ".venv", "venv", "packages"}
    hits: list[str] = []
    for path in source_dir.rglob("*"):
        if path.is_dir() and path.name in risky_roots:
            hits.append(path.relative_to(source_dir).as_posix())
    return sorted(hits)


def _authenticity_score(auth: dict, *, module_total: int, object_total: int, metric_total: int) -> int:
    score = 0
    source_module_hits = max(auth.get("source_module_key_hits", 0), auth.get("source_module_title_hits", 0))
    score += 20 if auth.get("source_file_count", 0) >= 12 else 10 if auth.get("source_file_count", 0) >= 6 else 0
    score += min(20, round(20 * source_module_hits / module_total))
    score += min(15, round(15 * auth.get("manual_module_title_hits", 0) / module_total))
    score += min(15, round(15 * auth.get("manual_business_object_hits", 0) / object_total))
    score += min(10, round(10 * auth.get("manual_metric_hits", 0) / metric_total))
    score += min(10, round(10 * auth.get("ui_module_title_hits", 0) / module_total))
    score += 5 if auth.get("ui_screenshot_render_mode") == "project-server" and auth.get("ui_project_server_started") else 0
    score += 5 if auth.get("ui_runtime_probe_ready") and auth.get("ui_runtime_api_ready") and auth.get("ui_source_evidence_ready") else 0
    score += 5 if auth.get("info_name_match") else 0
    score += 5 if auth.get("info_version_match") else 0
    return min(100, int(score))


def _normative_score(norm: dict) -> int:
    score = 0
    score += 15 if norm.get("deliverable_count") == 5 else 8 if norm.get("deliverable_count", 0) >= 3 else 0
    score += 15 if norm.get("zip_entries_match_deliverables") else 0
    score += 15 if norm.get("source_line_target_met") else 0
    score += 10 if norm.get("source_selection_rule_match") else 0
    score += 10 if norm.get("source_pdf_page_count_match") else 0
    score += 10 if norm.get("source_lines_per_page") == 50 else 0
    score += 10 if norm.get("manual_pdf_exists") and norm.get("source_pdf_exists") and norm.get("pdf_official_conversion_ready") else 0
    score += 5 if norm.get("source_continuous_selection") else 0
    score += 5 if norm.get("manual_docx_is_a4") and norm.get("source_docx_is_a4") else 0
    score += 5 if norm.get("manual_pdf_is_a4") and norm.get("source_pdf_is_a4") else 0
    score += 5 if norm.get("manual_pdf_text_density_ready") else 0
    score += 5 if norm.get("manual_docx_header_page_number_right") and norm.get("source_docx_header_page_number_right") else 0
    score += 5 if not norm.get("placeholder_hits") else 0
    score += 5 if not norm.get("third_party_risk_hits") else 0
    return min(100, int(score))


def _findings(auth: dict, norm: dict) -> list[dict]:
    findings: list[dict] = []
    if auth.get("blueprint_operation_contract_required") and not auth.get("blueprint_operation_contract_ready"):
        issues = [str(item) for item in (auth.get("blueprint_operation_contract_issues") or []) if str(item).strip()]
        detail = f" 主要问题：{'；'.join(issues[:3])}" if issues else ""
        findings.append({
            "level": "error",
            "code": "blueprint_operation_contract_not_ready",
            "message": "GPT 产品蓝图缺少可核验的结构化操作契约，不能进入正式材料交付。" + detail,
        })
    if auth.get("source_persistence_required") and not auth.get("source_persistence_ready"):
        findings.append({
            "level": "error",
            "code": "source_persistence_not_ready",
            "message": "生成源码缺少可验证的数据库持久化、Repository、迁移脚本或自动化测试，不能作为完整业务工程交付。",
        })
    if auth.get("score", 0) < 80:
        findings.append({"level": "warning", "code": "authenticity_score_low", "message": "真实性评分低于 80，建议复查蓝图、源码、说明书和截图是否充分呼应。"})
    if auth.get("ui_screenshot_render_mode") != "project-server":
        findings.append({"level": "error", "code": "ui_screenshot_not_project_server", "message": "界面截图不是通过生成项目服务 URL 渲染，不能作为真实项目运行截图交付。"})
    if not auth.get("ui_project_server_started") or not auth.get("ui_runtime_probe_ready"):
        findings.append({"level": "error", "code": "ui_runtime_probe_not_ready", "message": "生成项目服务健康检查或模块接口探针未通过，截图运行来源不足。"})
    if not auth.get("ui_runtime_api_ready"):
        findings.append({"level": "error", "code": "ui_runtime_api_not_ready", "message": "截图页面未在浏览器中实际请求生成项目业务接口，运行截图证据不足。"})
    if not auth.get("ui_source_evidence_ready"):
        findings.append({"level": "error", "code": "ui_source_evidence_not_ready", "message": "界面截图缺少源码文件、接口、服务或字段映射证据。"})
    if not auth.get("ui_business_facing_screenshots"):
        findings.append({"level": "error", "code": "ui_screenshot_tech_leak", "message": "界面截图仍包含接口路径、源码类名、源码文件名或英文实体等开发痕迹，不适合作为用户手册截图。"})
    if not auth.get("ui_visible_text_clean"):
        findings.append({"level": "error", "code": "ui_screenshot_placeholder_text", "message": "界面截图可见区域存在乱码、占位模块名或泛化记录名，不适合作为真实项目截图。"})
    if not auth.get("ui_visible_content_summary_ready"):
        findings.append({"level": "error", "code": "ui_visible_content_summary_missing", "message": "界面截图缺少逐页可见内容摘要，无法保证手册功能说明与图片真实内容对应。"})
    if not auth.get("ui_operation_result_evidence_ready"):
        findings.append({"level": "error", "code": "ui_operation_result_evidence_missing", "message": "操作截图缺少处理结果、操作日志或状态刷新证据，真实业务操作痕迹不足。"})
    if not auth.get("ui_operation_coverage_ready"):
        findings.append({
            "level": "error",
            "code": "ui_operation_coverage_missing",
            "message": "部分业务模块缺少足够的查询、处理或结果分析操作页，手册尚未形成逐模块操作证据链。",
        })
    if not auth.get("ui_chart_context_ready"):
        findings.append({"level": "error", "code": "ui_chart_context_missing", "message": "统计图或趋势图缺少日期范围、单位等业务上下文，仍偏原型展示。"})
    if not auth.get("ui_route_topology_ready"):
        findings.append({"level": "error", "code": "ui_route_topology_missing", "message": "交通线路类截图缺少干线/支线拓扑、节点或时窗信息，线路业务特征不足。"})
    if not auth.get("ui_visual_identity_signature"):
        findings.append({"level": "error", "code": "ui_visual_identity_missing", "message": "界面蓝图缺少视觉身份签名，无法证明同类型软件的界面差异化。"})
    if not auth.get("ui_similarity_gate_ready"):
        reason = str(auth.get("ui_similarity_reason") or "")
        if reason == "ui_layout_role_count_low":
            code = "ui_layout_role_count_low"
        elif reason == "ui_package_pages_too_similar":
            code = "ui_package_pages_too_similar"
        else:
            code = "ui_similarity_too_high"
        message = (
            "后台模块页面角色数量不足，二级界面过于相似。"
            if code == "ui_layout_role_count_low"
            else "当前材料包内多个页面结构过于相似，需重新生成差异化页面。"
            if code == "ui_package_pages_too_similar"
            else "界面结构与同类型历史样本相似度过高，需重新生成视觉身份。"
        )
        findings.append({"level": "error", "code": code, "message": message})
    if auth.get("ui_ai_frontend_enabled") and not auth.get("ui_ai_frontend_ready"):
        findings.append({"level": "error", "code": "ui_ai_frontend_not_ready", "message": "AI 界面页面代码未完整生成，正式 GPT 流程不能使用模板截图兜底。"})
    if auth.get("ui_ai_frontend_enabled") and not auth.get("ui_shared_confirmation_ready"):
        findings.append({"level": "error", "code": "ui_shared_confirmation_not_ready", "message": "React 界面未接入统一确认弹窗契约，同一软件内可能混用不同弹窗结构，不能进入正式交付。"})
    if auth.get("ui_ai_frontend_enabled") and not auth.get("ui_visual_reference_ready"):
        findings.append({"level": "error", "code": "ui_visual_reference_missing", "message": "gpt-image-2 全局视觉风格参考图未生成，正式 GPT 流程不能无图生成界面截图。"})
    if auth.get("ui_ai_frontend_enabled") and (
        not auth.get("ui_visual_reference_before_source_ready")
        or not auth.get("source_visual_reference_contract")
    ):
        findings.append({"level": "error", "code": "ui_visual_reference_not_before_source", "message": "缺少全局视觉风格参考图先于业务源码工程生成的证据。"})
    if auth.get("ui_ai_frontend_enabled") and not auth.get("ui_visual_reference_to_code_ready"):
        findings.append({"level": "error", "code": "ui_visual_reference_to_code_missing", "message": "界面代码缺少按全局视觉风格参考图生成的证据，最终手册截图不能直接来自模板或中间图。"})
    if norm.get("score", 0) < 85:
        findings.append({"level": "warning", "code": "normative_score_low", "message": "规范性评分低于 85，建议复查交付文件、源码页数、PDF 和 ZIP 内容。"})
    if not norm.get("source_line_target_met"):
        findings.append({"level": "error", "code": "source_line_target_not_met", "message": "源码有效行数未达到 3000 行目标，建议补齐业务源码后再交付。"})
    if norm.get("placeholder_hits"):
        findings.append({"level": "error", "code": "placeholder_text_found", "message": "材料中发现占位符或乱码标记。"})
    if norm.get("manual_internal_generation_leak_hits"):
        findings.append({"level": "error", "code": "manual_internal_generation_leak", "message": "说明书或申请信息中出现接口返回、生成项目、AI/GPT 等内部生成说明，不适合作为客户交付材料。"})
    if norm.get("third_party_risk_hits"):
        findings.append({"level": "warning", "code": "third_party_source_risk", "message": "源码工程中发现可能的第三方目录，源码鉴别材料不应混入第三方源码。"})
    if not norm.get("zip_entries_match_deliverables"):
        findings.append({"level": "error", "code": "zip_entries_mismatch", "message": "ZIP 内容与交付文件白名单不一致。"})
    if not norm.get("source_continuous_selection"):
        findings.append({"level": "error", "code": "source_selection_not_continuous", "message": "源码鉴别材料未按真实源码顺序连续抽取。"})
    if not norm.get("source_selection_rule_match"):
        findings.append({"level": "error", "code": "source_selection_rule_mismatch", "message": "源码鉴别材料未按不足 60 页全量、超过 60 页前 30 页加后 30 页的规则输出。"})
    if not norm.get("source_pdf_page_count_match"):
        findings.append({"level": "error", "code": "source_pdf_page_count_mismatch", "message": "源码 PDF 实际页数与选定源码页数不一致，可能存在换行溢出或空白页。"})
    if not norm.get("source_material_diversity_ready"):
        findings.append({"level": "error", "code": "source_material_diversity_low", "message": "源码鉴别材料被少量超大文件或重复代码占据，前后 30 页未覆盖足够多的真实业务文件。"})
    if not norm.get("pdf_official_conversion_ready"):
        findings.append({"level": "error", "code": "pdf_official_conversion_not_ready", "message": "PDF 未通过 LibreOffice 正式转换，简版兜底 PDF 不建议作为申报交付文件。"})
    if not norm.get("manual_docx_is_a4") or not norm.get("source_docx_is_a4"):
        findings.append({"level": "error", "code": "docx_page_size_not_a4", "message": "说明书或源码鉴别材料不是 A4 页面。"})
    if not norm.get("manual_pdf_is_a4") or not norm.get("source_pdf_is_a4"):
        findings.append({"level": "error", "code": "pdf_page_size_not_a4", "message": "说明书或源码鉴别材料 PDF 不是 A4 页面，或未完成 PDF 页面尺寸检查。"})
    if not norm.get("manual_pdf_text_density_ready"):
        findings.append({"level": "error", "code": "manual_pdf_text_density_not_ready", "message": "说明书 PDF 存在正文内容明显不足的页面，或未完成逐页文本密度检查。"})
    if not norm.get("manual_pagination_constraints_ready"):
        findings.append({"level": "error", "code": "manual_pagination_constraints_not_ready", "message": "说明书未完整应用标题防孤行、截图与图注同页等全局分页约束。"})
    if not norm.get("manual_numbered_steps_ready"):
        findings.append({"level": "error", "code": "manual_numbered_steps_not_ready", "message": "说明书截图后的操作说明未统一使用编号步骤。"})
    if not norm.get("manual_natural_style_ready"):
        findings.append({"level": "error", "code": "manual_style_too_mechanical", "message": "说明书正文存在过多固定标签或重复操作短句，读起来偏机械模板。"})
    if not norm.get("manual_ui_consistency_ready"):
        findings.append({"level": "error", "code": "manual_ui_consistency_not_ready", "message": "说明书截图标题、按钮或可见内容语义与实际界面不一致。"})
    if not norm.get("manual_ui_semantic_ready"):
        findings.append({"level": "error", "code": "manual_ui_semantic_not_ready", "message": "说明书引用了截图中不存在的字段、指标或操作，或未解释截图中的主要业务内容。"})
    if not norm.get("manual_docx_header_page_number_right") or not norm.get("source_docx_header_page_number_right"):
        findings.append({"level": "error", "code": "docx_page_number_not_top_right", "message": "说明书或源码鉴别材料未在页眉右上角设置页码。"})
    for finding in findings:
        finding.setdefault("suggestion", _finding_suggestion(finding.get("code", "")))
    return findings


def _finding_suggestion(code: str) -> str:
    suggestions = {
        "blueprint_operation_contract_not_ready": "重新执行 GPT 产品蓝图阶段；每个业务模块至少提供 3 个包含角色、触发条件、输入字段、前后状态和结果证据的结构化操作，并清除 coverage-fallback、弱模块键及终端语义冲突后再生成 React 页面。",
        "source_persistence_not_ready": "检查 generated_source 中的数据库初始化、migrations、repositories 和 tests；运行生成项目测试并确认重启 Repository 后数据仍可读取，再重新生成材料。",
        "authenticity_score_low": "优先使用 GPT 模式重新生成产品蓝图，或补充更具体的业务提示；确认模块标题、业务对象和统计指标能同时出现在说明书、源码实体/注释和截图文本中。",
        "ui_screenshot_not_project_server": "重新生成材料；正式截图必须启动 generated_source 项目服务，并从 http://127.0.0.1:{port}/ui-prototype 页面截图，不允许使用本地文件或静态图片兜底。",
        "ui_runtime_probe_not_ready": "检查 generated_source 的启动命令、/health 接口和模块接口路由；项目服务无法启动或模块接口不可访问时不应继续交付。",
        "ui_source_evidence_not_ready": "检查 generated_source/ui-prototype/source-ui-evidence.json；截图应能映射到本次生成的 Controller/Router、Service、Model 和字段。",
        "ui_screenshot_tech_leak": "检查 generated_source/ui-prototype/*.html；用户可见界面应展示业务字段、状态和操作，不应展示 GET 路径、Service 类、router 文件或源码映射面板。",
        "ui_screenshot_placeholder_text": "检查 generated_source/ui-prototype/*.html 和截图可见区域；中文任务请使用 UTF-8 JSON 文件生成，并确保接口返回业务编号、名称、范围、状态等真实字段后再截图。",
        "ui_visible_content_summary_missing": "重新执行截图阶段；每张截图必须从浏览器 DOM 提取标题、指标、字段、状态、筛选项和按钮，并写入 generation_report.json 的 visible_content_summary。",
        "ui_operation_result_evidence_missing": "检查操作类截图页面；弹窗内应显示当前记录、处理结果、状态刷新和操作日志写入说明，并由运行接口数据覆盖当前记录。",
        "ui_chart_context_missing": "检查统计图和趋势图组件；应显示日期范围、统计单位、图例或业务指标名称，不应只展示无上下文柱形图。",
        "ui_route_topology_missing": "检查交通运输类地图/线路组件；应显示干线、支线接驳、节点编号、服务时窗等业务拓扑信息。",
        "ui_package_pages_too_similar": "检查 generated_source/ui-prototype 页面；同一本手册内模块页和操作页应使用不同工作区结构，不应只是相同页面换标题或相同背景加弹窗。",
        "ui_ai_frontend_not_ready": "重新生成界面页面代码；正式 GPT 流程要求由模型生成可运行 HTML/CSS 页面，再从生成项目服务截图，不允许回退共享模板 renderer。",
        "ui_visual_reference_missing": "检查 generated_source/ui-prototype/visual-references/visual-reference-manifest.json；正式流程应先生成全局视觉风格提示词和 gpt-image-2 参考图，再生成 HTML 页面。",
        "ui_visual_reference_not_before_source": "检查 generation_report.json 的 ui_visual_reference_before_source_ready 和 generated_source/ui-visual-reference-contract.json；正式流程应先生成全局风格参考图，再生成业务工程源码。",
        "ui_visual_reference_to_code_missing": "检查 generation_report.json 的 ui_visual_reference_to_code_ready；应确保所有 HTML 页面都带同一张 gpt-image-2 全局风格参考图通过多模态输入生成代码，最后再运行项目截图。",
        "normative_score_low": "先打开 validation_report.json 查看扣分项；重点确认最终 ZIP 是否只有 5 个交付文件、两个 PDF 是否存在、源码材料是否按不足 60 页全量或超过 60 页前 30 后 30 规则生成。",
        "source_line_target_not_met": "优先切换到 C# 或 JavaScript/Python 等当前源码量更稳定的语言重新生成；也可以补充更具体业务提示、启用 GPT 蓝图扩展模块，或增加业务模块数量后再生成。",
        "placeholder_text_found": "打开 validation_report.json 查看命中的占位符；优先检查业务提示、模板文本和 PowerShell 中文参数传递方式，中文任务请改用 UTF-8 JSON 任务文件重新生成。",
        "manual_internal_generation_leak": "检查说明书正文和截图说明；客户可见材料只能描述软件业务操作，不应出现接口返回、运行服务、生成项目、浏览器页面、AI/GPT 或内部证据文件名。",
        "third_party_source_risk": "删除或排除 node_modules、vendor、venv、packages 等第三方目录；源码鉴别材料应只抽取本工具生成的业务源码和必要配置文件。",
        "zip_entries_mismatch": "重新生成材料包，确认最终 ZIP 只包含说明书 Word/PDF、申请信息 TXT、源码材料 Word/PDF 五个文件，不应包含截图、源码工程、报告或临时文件。",
        "source_selection_not_continuous": "重新生成源码鉴别材料；超过 60 页时应按真实源码读取顺序输出前 30 页和后 30 页，不应在抽取阶段筛行、重排或补行。",
        "source_selection_rule_mismatch": "检查 source_total_pages、source_selected_pages 和 selection_mode；源码超过 60 页时必须严格输出前 30 页与后 30 页。",
        "source_pdf_page_count_mismatch": "重新生成源码 DOCX/PDF；检查长代码行是否发生自动换行，并确保每 50 行只占一个 A4 物理页。",
        "source_material_diversity_low": "拆分超大业务文件，确保前 30 页和后 30 页分别覆盖至少 4 个源码文件，单文件占比不超过 35%，并降低重复代码行。",
        "pdf_official_conversion_not_ready": "安装或打包 LibreOffice 运行时后重新生成；正式交付应以 LibreOffice 转换出的完整 PDF 为准，fallback-reportlab 仅作开发预览。",
        "docx_page_size_not_a4": "重新生成材料；生成器应将说明书和源码鉴别材料页面设置为 A4 纵向。",
        "pdf_page_size_not_a4": "确认 LibreOffice 转换链路和 pdfinfo 可用后重新生成；PDF 页面应保持 A4 纵向。",
        "manual_pdf_text_density_not_ready": "打开 validation_report.json 查看 manual_pdf_low_text_density_pages；补充真正稀疏页面的操作步骤或调整说明书排版后重新生成。",
        "manual_pagination_constraints_not_ready": "重新生成操作手册，并确认所有标题、截图和图注段落均写入 keep_with_next/keep_together 分页属性。",
        "manual_numbered_steps_not_ready": "将每张界面截图后的操作说明转换为连续编号步骤，并重新生成 Word/PDF。",
        "manual_style_too_mechanical": "检查 manual_mechanical_label_count 和 manual_repeated_phrase_count；说明书正文应使用自然操作指南句式，避免反复出现“操作说明/字段说明/处理结果”等固定标签。",
        "manual_ui_consistency_not_ready": "检查 manual_ui_title_mismatches、manual_ui_button_mismatches、manual_ui_semantic_mismatches 和 manual_ui_semantic_coverage_missing；说明书只能引用对应截图的真实可见内容。",
        "manual_ui_semantic_not_ready": "重新生成手册；每张图的说明应直接使用该页 visible_content_summary，禁止引用截图中不存在的模块字段、统计指标、筛选项或按钮。",
        "docx_page_number_not_top_right": "重新生成材料；说明书和源码鉴别材料应在页眉右上角显示连续页码。",
    }
    return suggestions.get(code, "打开 validation_report.json 查看完整校验数据；根据发现项复核源码、说明书、截图和 ZIP 内容后重新生成。")


def _hash_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hash_text(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def _hash_many(items: list[dict]) -> str:
    payload = json.dumps(
        [{"path": item["path"], "sha256": item["sha256"]} for item in items],
        ensure_ascii=False,
        sort_keys=True,
    )
    return _hash_text(payload)
