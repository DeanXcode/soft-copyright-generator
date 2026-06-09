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
    "待补充",
    "????",
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
    authenticity["ready"] = authenticity["score"] >= 80

    source_selected_pages = int(checks.get("source_selected_pages") or 0)
    source_total_pages = int(checks.get("source_total_pages") or 0)
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
        "source_lines_per_page": int(checks.get("lines_per_page") or 0),
        "manual_pdf_exists": any(item["kind"] == "manual_pdf" and item["exists"] for item in deliverables),
        "source_pdf_exists": any(item["kind"] == "source_pdf" and item["exists"] for item in deliverables),
        "placeholder_hits": _placeholder_hits(source_text + "\n" + manual_text + "\n" + info_text),
        "third_party_risk_hits": _third_party_risk_hits(source_dir),
    }
    normative["score"] = _normative_score(normative)
    normative["ready"] = (
        normative["score"] >= 85
        and bool(normative["source_line_target_met"])
        and bool(normative["zip_entries_match_deliverables"])
        and not normative["placeholder_hits"]
    )

    findings = _findings(authenticity, normative)
    return {
        "version": "2026-06-09",
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
        "validation_zip_entries_match_deliverables": bool(normative.get("zip_entries_match_deliverables")),
        "validation_placeholder_hit_count": len(normative.get("placeholder_hits") or []),
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
            "files": validation.get("source_files", []),
        },
        "source_material_pages": {
            "lines_per_page": source_report.get("lines_per_page", 50),
            "selection_mode": source_report.get("selection_mode", ""),
            "total_pages": source_report.get("source_total_pages", 0),
            "selected_pages": source_report.get("source_selected_pages", 0),
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
    score += 5 if auth.get("info_name_match") else 0
    score += 5 if auth.get("info_version_match") else 0
    return min(100, int(score))


def _normative_score(norm: dict) -> int:
    score = 0
    score += 20 if norm.get("deliverable_count") == 5 else 10 if norm.get("deliverable_count", 0) >= 3 else 0
    score += 20 if norm.get("zip_entries_match_deliverables") else 0
    score += 15 if norm.get("source_line_target_met") else 0
    score += 15 if norm.get("source_selection_rule_match") else 0
    score += 10 if norm.get("source_lines_per_page") == 50 else 0
    score += 10 if norm.get("manual_pdf_exists") and norm.get("source_pdf_exists") else 0
    score += 5 if not norm.get("placeholder_hits") else 0
    score += 5 if not norm.get("third_party_risk_hits") else 0
    return min(100, int(score))


def _findings(auth: dict, norm: dict) -> list[dict]:
    findings: list[dict] = []
    if auth.get("score", 0) < 80:
        findings.append({"level": "warning", "code": "authenticity_score_low", "message": "真实性评分低于 80，建议复查蓝图、源码、说明书和截图是否充分呼应。"})
    if norm.get("score", 0) < 85:
        findings.append({"level": "warning", "code": "normative_score_low", "message": "规范性评分低于 85，建议复查交付文件、源码页数、PDF 和 ZIP 内容。"})
    if not norm.get("source_line_target_met"):
        findings.append({"level": "error", "code": "source_line_target_not_met", "message": "源码有效行数未达到 3000 行目标，建议补齐业务源码后再交付。"})
    if norm.get("placeholder_hits"):
        findings.append({"level": "error", "code": "placeholder_text_found", "message": "材料中发现占位符或乱码标记。"})
    if norm.get("third_party_risk_hits"):
        findings.append({"level": "warning", "code": "third_party_source_risk", "message": "源码工程中发现可能的第三方目录，源码鉴别材料不应混入第三方源码。"})
    if not norm.get("zip_entries_match_deliverables"):
        findings.append({"level": "error", "code": "zip_entries_mismatch", "message": "ZIP 内容与交付文件白名单不一致。"})
    for finding in findings:
        finding.setdefault("suggestion", _finding_suggestion(finding.get("code", "")))
    return findings


def _finding_suggestion(code: str) -> str:
    suggestions = {
        "authenticity_score_low": "优先使用 GPT 模式重新生成产品蓝图，或补充更具体的业务提示；确认模块标题、业务对象和统计指标能同时出现在说明书、源码实体/注释和截图文本中。",
        "normative_score_low": "先打开 validation_report.json 查看扣分项；重点确认最终 ZIP 是否只有 5 个交付文件、两个 PDF 是否存在、源码材料是否按不足 60 页全量或超过 60 页前 30 后 30 规则生成。",
        "source_line_target_not_met": "优先切换到 C# 或 JavaScript/Python 等当前源码量更稳定的语言重新生成；也可以补充更具体业务提示、启用 GPT 蓝图扩展模块，或增加业务模块数量后再生成。",
        "placeholder_text_found": "打开 validation_report.json 查看命中的占位符；优先检查业务提示、模板文本和 PowerShell 中文参数传递方式，中文任务请改用 UTF-8 JSON 任务文件重新生成。",
        "third_party_source_risk": "删除或排除 node_modules、vendor、venv、packages 等第三方目录；源码鉴别材料应只抽取本工具生成的业务源码和必要配置文件。",
        "zip_entries_mismatch": "重新生成材料包，确认最终 ZIP 只包含说明书 Word/PDF、申请信息 TXT、源码材料 Word/PDF 五个文件，不应包含截图、源码工程、报告或临时文件。",
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
