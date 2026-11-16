from __future__ import annotations

from dataclasses import dataclass
from html import escape
import json
from pathlib import Path
import re
import shutil
from typing import Any, Iterable

from .ai_frontend_codegen import generate_ai_frontend_pages, generate_style_reference_assets
from .blueprint import FeatureModule, ProductBlueprint
from .domain_profile import build_domain_profile
from .llm.provider import LLMProvider
from .models import GenerationTask
from .navigation_contract import NAVIGATION_CONTRACT_VERSION, build_local_navigation_contract
from .operation_coverage import module_operation_coverage, operation_caption, operation_page_title
from .packager import write_json
from .screenshot_checkpoint import (
    SCREENSHOT_CHECKPOINT_VERSION,
    restore_screenshot_checkpoint_prefix as _restore_screenshot_checkpoint_prefix,
    save_screenshot_checkpoint_page as _save_screenshot_checkpoint_page,
)
from .screenshot_capture import (
    _capture_visible_action_crops,
    _capture_visible_content_summary,
    _action_crop_has_visible_content,
    _is_action_crop_label,
    _normalize_action_crop_image,
    _normalize_visible_action_label,
    _normalize_visible_content_summary,
    _navigate_for_screenshot,
    _render_url,
    _wait_for_page_runtime_api,
)
from .screenshot_layout_quality import (
    _assert_page_text_layout_quality,
    _assert_screenshot_content_geometry,
    _auto_repair_page_text_layout,
    _collect_page_text_layout_issues,
    _mobile_canvas_metrics,
    _mobile_canvas_width_ready,
)
from .screenshot_page_runtime import (
    start_project_server as _start_project_server,
    stop_project_server as _stop_project_server,
    verify_project_runtime as _verify_project_runtime,
)
from .ui_blueprint import UiBlueprint, UiScreenBlueprint, build_ui_blueprint, is_game_like, is_mobile_app_like

ADMIN_VIEWPORT = {"width": 1280, "height": 720}
GAME_VIEWPORT = {"width": 720, "height": 1280}
MOBILE_VIEWPORT = {"width": 720, "height": 1280}
def _is_mobile_renderer(renderer: str) -> bool:
    return renderer in {"game", "mobile_app"}


def _viewport_for_renderer(renderer: str) -> dict[str, int]:
    if renderer == "game":
        return GAME_VIEWPORT
    if renderer == "mobile_app":
        return MOBILE_VIEWPORT
    return ADMIN_VIEWPORT


@dataclass
class UiScreenshot:
    key: str
    title: str
    caption: str
    html_path: str
    page_kind: str = "general"
    module_key: str = ""
    image_path: str | None = None
    width: int = 0
    height: int = 0
    runtime_fetches: list[dict[str, Any]] | None = None
    action_crops: dict[str, str] | None = None
    visible_content_summary: dict[str, Any] | None = None
    interaction_action: str = ""
    interaction_mode: str = ""
    interaction_surface: str = ""
    requires_confirmation: bool = False
    interaction_action_key: str = ""
    interaction_role: str = ""
    interaction_trigger: str = ""
    interaction_input_fields: list[str] | None = None
    interaction_pre_state: str = ""
    interaction_post_state: str = ""
    interaction_result_evidence: str = ""


def generate_ui_screenshots(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    output_dir: Path,
    llm_provider: LLMProvider | None = None,
    source_info: dict | None = None,
    emit=None,
    use_project_server: bool = False,
    require_project_server: bool = False,
    require_llm_blueprint: bool = False,
    ui_blueprint_override: UiBlueprint | None = None,
    visual_identity_attempt: int = 0,
    visual_reference_report: dict[str, Any] | None = None,
) -> tuple[dict[str, UiScreenshot], list[str], UiBlueprint]:
    ui_dir = output_dir / "ui_screenshots"
    ui_dir.mkdir(parents=True, exist_ok=True)
    prototype_dir = _prototype_dir(output_dir, source_info)
    prototype_dir.mkdir(parents=True, exist_ok=True)
    ui_blueprint = ui_blueprint_override or build_ui_blueprint(
        task,
        blueprint,
        llm_provider,
        emit=emit,
        require_llm=require_llm_blueprint,
        visual_identity_attempt=visual_identity_attempt,
    )
    source_evidence = _source_ui_evidence(source_info, blueprint)
    _attach_source_ui_evidence(ui_blueprint, source_evidence)
    if isinstance(source_info, dict):
        source_info["ui_source_evidence"] = source_evidence
    write_json(ui_dir / "ui_blueprint.json", ui_blueprint.to_dict())
    write_json(prototype_dir / "ui_blueprint.json", ui_blueprint.to_dict())
    write_json(prototype_dir / "source-ui-evidence.json", source_evidence)
    if require_llm_blueprint:
        if visual_reference_report:
            _emit(emit, 50, "复用全局风格参考图，准备生成界面代码")
        else:
            _emit(emit, 41, "准备截图页面清单（暂不写入界面代码）")
        screenshots = _build_page_specs(task, blueprint, prototype_dir, ui_blueprint)
    else:
        _emit(emit, 41, "准备截图页面清单")
        screenshots = _build_pages(task, blueprint, prototype_dir, ui_blueprint)
    ai_frontend_report = generate_ai_frontend_pages(
        task=task,
        blueprint=blueprint,
        ui_blueprint=ui_blueprint,
        screenshots=screenshots,
        provider=llm_provider,
        emit=emit,
        require_llm=require_llm_blueprint,
        visual_reference_report=visual_reference_report,
        codegen_progress_start=50 if visual_reference_report else 44,
    )
    if ai_frontend_report.get("ready"):
        runtime_module_keys = _runtime_module_keys(blueprint)
        for item in screenshots:
            _inject_runtime_script_into_ai_page(Path(item.html_path), module_keys=runtime_module_keys)
    if isinstance(source_info, dict):
        source_info["ui_ai_frontend"] = ai_frontend_report
    design_brief = dict(getattr(ui_blueprint, "design_brief", {}) or {})
    design_brief["ai_frontend_codegen"] = ai_frontend_report
    ui_blueprint.design_brief = design_brief
    _write_prototype_manifest(task, blueprint, prototype_dir, ui_blueprint, screenshots)
    _write_prototype_index(task, blueprint, prototype_dir, ui_blueprint, screenshots)
    _write_prototype_readme(task, prototype_dir, ui_blueprint, screenshots)
    _publish_project_prototype(task, prototype_dir, ui_blueprint, screenshots, source_info)
    warnings: list[str] = list(ui_blueprint.warnings)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        if require_project_server:
            raise RuntimeError(f"Playwright 未安装，无法执行生成项目服务截图：{exc}") from exc
        _render_fallback_images(task, blueprint, screenshots, ui_dir)
        return _to_map(screenshots), warnings + [f"Playwright 未安装，已使用本地图像渲染生成界面截图：{exc}"], ui_blueprint

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            viewport = _viewport_for_renderer(ui_blueprint.renderer)
            checkpoint = {"version": SCREENSHOT_CHECKPOINT_VERSION, "pages": {}}
            restored_screenshot_count = 0
            if bool(getattr(task, "resume_existing_output", False)):
                checkpoint, restored_screenshot_count = _restore_screenshot_checkpoint_prefix(
                    ui_dir,
                    screenshots,
                    ui_blueprint.renderer,
                    viewport,
                )
                if restored_screenshot_count:
                    next_page = min(restored_screenshot_count + 1, len(screenshots))
                    _emit(
                        emit,
                        55 + min(5, int(restored_screenshot_count / max(len(screenshots), 1) * 5)),
                        f"复用已完成运行截图 {restored_screenshot_count}/{len(screenshots)}，从第 {next_page} 页继续",
                    )
            page = browser.new_page(viewport=viewport, device_scale_factor=1, is_mobile=_is_mobile_renderer(ui_blueprint.renderer))
            project_server = None
            render_base_url = ""
            render_mode = "file"
            try:
                if use_project_server:
                    try:
                        project_server = _start_project_server(source_info)
                        render_base_url = project_server["base_url"]
                        render_mode = "project-server"
                        _verify_project_runtime(source_info, source_evidence, render_base_url)
                    except Exception as exc:
                        if require_project_server:
                            raise RuntimeError(f"生成项目服务截图不可用：{exc}") from exc
                        warnings.append(f"生成项目服务截图不可用，已回退本地文件截图：{exc}")
                if isinstance(source_info, dict):
                    source_info["ui_screenshot_render_mode"] = render_mode
                    source_info["ui_screenshot_base_url"] = render_base_url
                    source_info["ui_project_server_started"] = render_mode == "project-server"
                _stamp_render_evidence(ui_blueprint, source_evidence, source_info, render_mode, render_base_url)
                render_message = "启动生成项目服务并准备运行截图" if render_mode == "project-server" else "准备本地页面运行截图"
                _emit(emit, 54, render_message)
                for index, item in enumerate(screenshots, start=1):
                    if index <= restored_screenshot_count:
                        continue
                    _emit(emit, 55 + min(5, int(index / max(len(screenshots), 1) * 5)), f"渲染界面截图 {index}/{len(screenshots)}")
                    image_path = ui_dir / f"{item.key}.png"
                    _navigate_for_screenshot(
                        page,
                        _render_url(item, render_base_url),
                        project_server=render_mode == "project-server",
                    )
                    if render_mode == "project-server":
                        _wait_for_page_runtime_api(page, item)
                    _auto_repair_page_text_layout(page, ui_blueprint.renderer)
                    _assert_interaction_semantics(page, item)
                    _assert_page_text_layout_quality(page, item, ui_blueprint.renderer)
                    item.visible_content_summary = _capture_visible_content_summary(page, item)
                    page.screenshot(path=str(image_path), full_page=False)
                    _assert_screenshot_content_geometry(image_path, ui_blueprint.renderer, item)
                    item.action_crops = _capture_visible_action_crops(page, item, ui_dir)
                    item.visible_content_summary = _normalize_visible_content_summary(item.visible_content_summary, item)
                    item.image_path = str(image_path)
                    item.width = viewport["width"]
                    item.height = viewport["height"]
                    _save_screenshot_checkpoint_page(
                        ui_dir,
                        checkpoint,
                        item,
                        ui_blueprint.renderer,
                        viewport,
                    )
            finally:
                _stop_project_server(project_server)
            browser.close()
    except Exception as exc:
        if require_project_server:
            raise
        _render_fallback_images(task, blueprint, screenshots, ui_dir)
        warnings.append(f"Playwright 截图不可用，已使用本地图像渲染生成界面截图：{exc}")
    _stamp_render_evidence(ui_blueprint, source_evidence, source_info, source_evidence.get("render_mode", "file"), source_evidence.get("base_url", ""))
    _stamp_page_runtime_fetch_evidence(source_evidence, source_info, screenshots)
    _attach_source_ui_evidence(ui_blueprint, source_evidence)
    write_json(ui_dir / "ui_blueprint.json", ui_blueprint.to_dict())
    write_json(prototype_dir / "ui_blueprint.json", ui_blueprint.to_dict())
    write_json(prototype_dir / "source-ui-evidence.json", source_evidence)
    _write_prototype_manifest(task, blueprint, prototype_dir, ui_blueprint, screenshots)
    return _to_map(screenshots), warnings, ui_blueprint


def prepare_ui_visual_reference(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    output_dir: Path,
    llm_provider: LLMProvider | None = None,
    emit=None,
    require_llm_blueprint: bool = False,
    ui_blueprint_override: UiBlueprint | None = None,
    visual_identity_attempt: int = 0,
) -> tuple[UiBlueprint, dict[str, Any], dict[str, UiScreenshot]]:
    ui_dir = output_dir / "ui_screenshots"
    ui_dir.mkdir(parents=True, exist_ok=True)
    prototype_dir = _prototype_dir(output_dir, None)
    prototype_dir.mkdir(parents=True, exist_ok=True)
    ui_blueprint = ui_blueprint_override or build_ui_blueprint(
        task,
        blueprint,
        llm_provider,
        emit=emit,
        require_llm=require_llm_blueprint,
        visual_identity_attempt=visual_identity_attempt,
    )
    write_json(ui_dir / "ui_blueprint.json", ui_blueprint.to_dict())
    write_json(prototype_dir / "ui_blueprint.json", ui_blueprint.to_dict())
    _emit(emit, 41, "准备视觉参考页面清单（先生成参考图，暂不写入源码工程）")
    screenshots = _build_page_specs(task, blueprint, prototype_dir, ui_blueprint)
    visual_reference_report = generate_style_reference_assets(
        task=task,
        blueprint=blueprint,
        ui_blueprint=ui_blueprint,
        screenshots=screenshots,
        provider=llm_provider,
        emit=emit,
        require_llm=require_llm_blueprint,
    )
    design_brief = dict(getattr(ui_blueprint, "design_brief", {}) or {})
    design_brief["pre_source_visual_reference"] = visual_reference_report
    ui_blueprint.design_brief = design_brief
    write_json(ui_dir / "ui_blueprint.json", ui_blueprint.to_dict())
    write_json(prototype_dir / "ui_blueprint.json", ui_blueprint.to_dict())
    return ui_blueprint, visual_reference_report, _to_map(screenshots)


def _stamp_page_runtime_fetch_evidence(
    source_evidence: dict[str, Any],
    source_info: dict | None,
    screenshots: list[UiScreenshot],
) -> None:
    pages: list[dict[str, Any]] = []
    total_fetches = 0
    ok_fetches = 0
    for item in screenshots:
        fetches = [fetch for fetch in (item.runtime_fetches or []) if isinstance(fetch, dict)]
        page_ok_fetches = [fetch for fetch in fetches if fetch.get("ok")]
        if fetches:
            total_fetches += len(fetches)
            ok_fetches += len(page_ok_fetches)
        pages.append(
            {
                "key": item.key,
                "title": item.title,
                "page_kind": item.page_kind,
                "module_key": item.module_key,
                "api_ready": bool(page_ok_fetches),
                "fetch_count": len(fetches),
                "ok_fetch_count": len(page_ok_fetches),
                "record_count": max([int(fetch.get("record_count") or 0) for fetch in fetches] or [0]),
                "visible_match": any(bool(fetch.get("visible_match")) for fetch in page_ok_fetches),
                "urls": [str(fetch.get("url") or "") for fetch in page_ok_fetches[:4]],
            }
        )
    ready_pages = [page for page in pages if page.get("api_ready")]
    source_evidence["runtime_api_ready"] = bool(pages) and len(ready_pages) == len(pages)
    source_evidence["runtime_api_page_count"] = len(ready_pages)
    source_evidence["runtime_api_fetch_count"] = total_fetches
    source_evidence["runtime_api_ok_fetch_count"] = ok_fetches
    source_evidence["runtime_api_pages"] = pages
    if isinstance(source_info, dict):
        source_info["ui_runtime_api_ready"] = source_evidence["runtime_api_ready"]
        source_info["ui_runtime_api_page_count"] = source_evidence["runtime_api_page_count"]
        source_info["ui_runtime_api_fetch_count"] = source_evidence["runtime_api_fetch_count"]
        source_info["ui_runtime_api_ok_fetch_count"] = source_evidence["runtime_api_ok_fetch_count"]
        source_info["ui_runtime_api_pages"] = pages



def _stamp_render_evidence(
    ui_blueprint: UiBlueprint,
    source_evidence: dict[str, Any],
    source_info: dict | None,
    render_mode: str,
    base_url: str,
) -> None:
    source_evidence["render_mode"] = render_mode
    source_evidence["base_url"] = base_url
    source_evidence["project_server_started"] = render_mode == "project-server"
    if isinstance(source_info, dict):
        source_info["ui_source_evidence"] = source_evidence
    _attach_source_ui_evidence(ui_blueprint, source_evidence)



def _prototype_dir(output_dir: Path, source_info: dict | None) -> Path:
    if isinstance(source_info, dict) and source_info.get("source_dir"):
        source_dir = Path(str(source_info["source_dir"]))
        source_info["ui_prototype_dir"] = str(source_dir / "ui-prototype")
        return source_dir / "ui-prototype"
    return output_dir / "generated_source" / "ui-prototype"


def _attach_source_ui_evidence(ui_blueprint: UiBlueprint, evidence: dict[str, Any]) -> None:
    brief = dict(getattr(ui_blueprint, "design_brief", {}) or {})
    brief["source_ui_evidence"] = evidence
    ui_blueprint.design_brief = brief


def _source_ui_evidence(source_info: dict | None, blueprint: ProductBlueprint) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "ready": False,
        "source_dir": "",
        "source_strategy": "",
        "source_language": "",
        "module_count": 0,
        "file_hit_count": 0,
        "route_hit_count": 0,
        "service_hit_count": 0,
        "modules": {},
    }
    if not isinstance(source_info, dict):
        return evidence
    source_dir_raw = str(source_info.get("source_dir") or "").strip()
    source_dir = Path(source_dir_raw) if source_dir_raw else None
    evidence["source_dir"] = str(source_dir) if source_dir else ""
    evidence["source_strategy"] = str(source_info.get("source_strategy") or "")
    evidence["source_language"] = str(source_info.get("source_language") or "")
    paths = _source_evidence_paths(source_info, source_dir)
    if not paths:
        return evidence
    for module in getattr(blueprint, "modules", []) or []:
        module_evidence = _module_source_evidence(module, paths, source_dir)
        evidence["modules"][module.key] = module_evidence
        if module_evidence["files"]:
            evidence["module_count"] += 1
            evidence["file_hit_count"] += len(module_evidence["files"])
            evidence["route_hit_count"] += len(module_evidence["routes"])
            evidence["service_hit_count"] += len(module_evidence["services"])
    evidence["ready"] = evidence["module_count"] > 0 and evidence["file_hit_count"] > 0
    return evidence


def _source_evidence_paths(source_info: dict, source_dir: Path | None) -> list[Path]:
    seen: set[str] = set()
    paths: list[Path] = []
    for value in source_info.get("files", []) or []:
        path = Path(str(value))
        key = str(path.resolve()) if path.exists() else str(path)
        if key in seen or not path.exists() or not path.is_file():
            continue
        if _is_source_evidence_file(path):
            seen.add(key)
            paths.append(path)
    if paths or not source_dir or not source_dir.exists():
        return paths
    for path in source_dir.rglob("*"):
        if path.is_file() and _is_source_evidence_file(path):
            key = str(path.resolve())
            if key not in seen:
                seen.add(key)
                paths.append(path)
    return paths


def _is_source_evidence_file(path: Path) -> bool:
    suffix = path.suffix.lower()
    if suffix not in {".java", ".py", ".js", ".ts", ".cs", ".php", ".cpp", ".h", ".hpp", ".html", ".xml", ".sql", ".yml", ".yaml"}:
        return False
    lower = path.as_posix().lower()
    return "ui-prototype" not in lower and "node_modules" not in lower and ".source-material-order" not in lower


def _module_source_evidence(module: FeatureModule, paths: list[Path], source_dir: Path | None) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "key": module.key,
        "title": module.title,
        "files": [],
        "interfaces": [],
        "services": [],
        "models": [],
        "routes": [],
        "methods": [],
        "service_methods": [],
        "classes": [],
        "fields": [str(field) for field in (module.data_fields or []) if str(field).strip()][:8],
    }
    matched: list[tuple[int, Path, str]] = []
    for path in paths:
        rel = _relative_source_path(path, source_dir)
        if not _source_path_matches_module(module, rel, path):
            continue
        kind = _source_file_kind(path)
        matched.append((_source_file_priority(kind), path, kind))
    for _priority, path, kind in sorted(matched, key=lambda item: (item[0], _relative_source_path(item[1], source_dir)))[:12]:
        rel = _relative_source_path(path, source_dir)
        text = _read_source_evidence_text(path)
        methods = _extract_source_methods(text, path, kind)
        file_item = {"path": rel, "kind": kind, "class": _primary_source_class(text, path), "methods": methods[:6]}
        evidence["files"].append(file_item)
        if kind == "interface":
            evidence["interfaces"].append(rel)
        elif kind == "service":
            evidence["services"].append(rel)
        elif kind == "model":
            evidence["models"].append(rel)
        evidence["routes"].extend(_extract_source_routes(text, path, module))
        evidence["methods"].extend(methods)
        if kind == "service":
            evidence["service_methods"].extend(methods)
        evidence["classes"].extend(_extract_source_classes(text))
        if len(evidence["fields"]) < 8:
            evidence["fields"].extend(_extract_source_fields(text, path))
    for key in ["routes", "methods", "service_methods", "classes", "fields", "interfaces", "services", "models"]:
        evidence[key] = _unique_texts(evidence[key])[:8]
    evidence["primary_interface"] = _primary_interface_label(evidence, module)
    evidence["primary_service"] = _primary_service_label(evidence, module)
    return evidence


def _source_path_matches_module(module: FeatureModule, relative_path: str, path: Path) -> bool:
    normalized_path = _source_token(relative_path)
    aliases = _source_module_aliases(module)
    if any(alias and alias in normalized_path for alias in aliases):
        return True
    title = str(module.title or "").strip()
    if not _source_title_is_distinct(title):
        return False
    try:
        text = _read_source_evidence_text(path)
    except Exception:
        return False
    return title in text


def _source_module_aliases(module: FeatureModule) -> list[str]:
    values = [module.key, _source_snake(module.key), _source_pascal(module.key), module.title]
    return _unique_texts([_source_token(value) for value in values if str(value).strip()])


def _source_title_is_distinct(title: str) -> bool:
    text = str(title or "").strip()
    if len(text) < 3 or "?" in text:
        return False
    compact = re.sub(r"\s+", "", text)
    return len(set(compact)) >= 2


def _source_token(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9\u4e00-\u9fff]+", "", str(value or "")).lower()


def _source_snake(value: str) -> str:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(value or ""))
    value = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    return value or "business"


def _source_pascal(value: str) -> str:
    words = [word for word in re.split(r"[^a-zA-Z0-9]+", str(value or "")) if word]
    return "".join(word[:1].upper() + word[1:] for word in words) or "Business"


def _source_file_kind(path: Path) -> str:
    lower = path.as_posix().lower()
    stem = path.stem.lower()
    if any(term in lower for term in ["/service", "\\service", "/services", "\\services", "/worker", "\\worker", "/manager", "\\manager"]) or any(term in stem for term in ["service", "worker", "manager"]):
        return "service"
    if any(term in lower for term in ["/model", "\\model", "/models", "\\models", "/domain", "\\domain", "/dto", "\\dto", "/queries", "\\queries"]) or any(term in stem for term in ["record", "model", "query", "dto"]):
        return "model"
    if any(term in lower for term in ["/repository", "\\repository", "/repositories", "\\repositories", "/mapper", "\\mapper"]) or path.suffix.lower() in {".xml", ".sql"}:
        return "persistence"
    if (
        any(term in lower for term in ["/controller", "\\controller", "/controllers", "\\controllers", "/router", "\\router", "/routes", "\\routes", "/api", "\\api"])
        or "controller" in stem
        or "router" in stem
        or stem.endswith("route")
    ):
        return "interface"
    return "source"


def _source_file_priority(kind: str) -> int:
    return {"interface": 0, "service": 1, "model": 2, "persistence": 3}.get(kind, 4)


def _relative_source_path(path: Path, source_dir: Path | None) -> str:
    if source_dir:
        try:
            return path.resolve().relative_to(source_dir.resolve()).as_posix()
        except Exception:
            pass
    return path.as_posix()


def _read_source_evidence_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")[:120000]


def _primary_source_class(text: str, path: Path) -> str:
    classes = _extract_source_classes(text)
    return classes[0] if classes else path.stem


def _extract_source_classes(text: str) -> list[str]:
    patterns = [
        r"\bpublic\s+(?:partial\s+)?(?:class|record|interface)\s+([A-Za-z_][A-Za-z0-9_]*)",
        r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)",
        r"\b@dataclass\s+class\s+([A-Za-z_][A-Za-z0-9_]*)",
    ]
    classes: list[str] = []
    for pattern in patterns:
        classes.extend(re.findall(pattern, text))
    return _unique_texts(classes)


def _extract_source_methods(text: str, path: Path, kind: str) -> list[str]:
    methods: list[str] = []
    if path.suffix.lower() in {".py"}:
        methods.extend(re.findall(r"^\s*def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", text, flags=re.M))
    elif path.suffix.lower() in {".js", ".ts"}:
        methods.extend(re.findall(r"^\s*(?:async\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*\([^)]*\)\s*\{", text, flags=re.M))
        methods.extend(re.findall(r"router\.(get|post|put|patch|delete)\s*\(", text))
    else:
        methods.extend(re.findall(r"\bpublic\s+(?:async\s+)?(?:[A-Za-z0-9_<>,.?]+\s+)+([A-Za-z_][A-Za-z0-9_]*)\s*\(", text))
        methods.extend(re.findall(r"\b(?:void|bool|int|string|auto)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", text))
    if kind == "interface":
        preferred = [name for name in methods if not name.lower().startswith(("get", "set"))]
        methods = preferred or methods
    return _unique_texts(methods)[:8]


def _extract_source_routes(text: str, path: Path, module: FeatureModule) -> list[str]:
    routes: list[str] = []
    module_base = "/" + _source_snake(module.key).replace("_", "-")
    fastapi_prefix = ""
    prefix_match = re.search(r"APIRouter\s*\([^)]*prefix\s*=\s*[\"']([^\"']+)[\"']", text)
    if prefix_match:
        fastapi_prefix = prefix_match.group(1)
    for method, route in re.findall(r"@router\.(get|post|put|patch|delete)\s*\(\s*[\"']([^\"']*)[\"']", text, flags=re.I):
        routes.append(f"{method.upper()} {_join_route(fastapi_prefix or module_base, route)}")
    for method, route in re.findall(r"router\.(get|post|put|patch|delete)\s*\(\s*[\"']([^\"']*)[\"']", text, flags=re.I):
        routes.append(f"{method.upper()} {_join_route(module_base, route)}")
    route_match = re.search(r"\[Route\(\s*[\"']([^\"']+)[\"']\s*\)\]", text)
    csharp_prefix = _join_route("", route_match.group(1)) if route_match else ""
    for verb, route in re.findall(r"\[Http(Get|Post|Put|Patch|Delete)(?:\(\s*[\"']([^\"']*)[\"']\s*\))?\]", text):
        routes.append(f"{verb.upper()} {_join_route(csharp_prefix or module_base, route)}")
    for annotation, route in re.findall(r"@(GetMapping|PostMapping|PutMapping|PatchMapping|DeleteMapping|RequestMapping)\s*(?:\(\s*[\"']([^\"']*)[\"']\s*\))?", text):
        verb = annotation.replace("Mapping", "").upper() or "REQ"
        routes.append(f"{verb} {_join_route(module_base, route)}")
    for class_name in _extract_source_classes(text):
        if class_name.lower().endswith("controller"):
            for method in _extract_source_methods(text, path, "interface")[:5]:
                routes.append(f"{class_name}.{method}")
            break
    return _unique_texts(routes)[:8]


def _join_route(prefix: str, route: str) -> str:
    prefix = str(prefix or "").strip()
    route = str(route or "").strip()
    if prefix and not prefix.startswith("/"):
        prefix = "/" + prefix
    if route and not route.startswith("/"):
        route = "/" + route
    combined = (prefix.rstrip("/") + route) if route else (prefix or "/")
    combined = re.sub(r"/+", "/", combined)
    return combined or "/"


def _extract_source_fields(text: str, path: Path) -> list[str]:
    fields: list[str] = []
    fields.extend(re.findall(r"\bprivate\s+[A-Za-z0-9_<>,.?]+\s+([A-Za-z_][A-Za-z0-9_]*)\s*;", text))
    fields.extend(re.findall(r"\bpublic\s+[A-Za-z0-9_<>,.?]+\s+([A-Za-z_][A-Za-z0-9_]*)\s*\{\s*get;\s*set;", text))
    fields.extend(re.findall(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*[A-Za-z_][A-Za-z0-9_\[\] |.]*", text, flags=re.M))
    fields.extend(re.findall(r"this\.([A-Za-z_][A-Za-z0-9_]*)\s*=", text))
    ignored = {"serialVersionUID", "records", "service", "router", "app"}
    return [field for field in _unique_texts(fields) if field not in ignored][:8]


def _primary_interface_label(evidence: dict[str, Any], module: FeatureModule) -> str:
    routes = evidence.get("routes") or []
    if routes:
        return str(routes[0])
    classes = [item for item in evidence.get("classes", []) or [] if str(item).lower().endswith(("controller", "router", "route"))]
    methods = evidence.get("methods") or []
    if classes and methods:
        return f"{classes[0]}.{methods[0]}"
    interfaces = evidence.get("interfaces") or []
    if interfaces:
        return Path(str(interfaces[0])).name
    return f"{_source_pascal(module.key)}Controller"


def _primary_service_label(evidence: dict[str, Any], module: FeatureModule) -> str:
    classes = [str(item) for item in evidence.get("classes", []) or [] if "service" in str(item).lower()]
    methods = evidence.get("service_methods") or evidence.get("methods") or []
    preferred_class = f"{_source_pascal(module.key)}Service"
    service_class = preferred_class if preferred_class in classes else (classes[0] if classes else "")
    preferred_methods = ["query", "Query", "list_records", "listRecords", "list", "create", "create_record", "createRecord"]
    file_methods = _source_methods_for_class(evidence, service_class)
    if file_methods:
        methods = file_methods
    service_method = next((method for method in preferred_methods if method in methods), "")
    if service_class and (service_method or methods):
        return f"{service_class}.{service_method or methods[0]}"
    services = evidence.get("services") or []
    if services:
        return Path(str(services[0])).name
    return f"{_source_pascal(module.key)}Service"


def _source_methods_for_class(evidence: dict[str, Any], class_name: str) -> list[str]:
    if not class_name:
        return []
    for item in evidence.get("files") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("kind") or "") != "service":
            continue
        if str(item.get("class") or "") == class_name:
            return [str(method) for method in (item.get("methods") or []) if str(method).strip()]
    return []


def _unique_texts(values: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _write_prototype_manifest(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    prototype_dir: Path,
    ui_blueprint: UiBlueprint,
    screenshots: list[UiScreenshot],
) -> None:
    design_brief = getattr(ui_blueprint, "design_brief", {}) or {}
    experience_spec = design_brief.get("product_experience_spec") if isinstance(design_brief, dict) else {}
    if not isinstance(experience_spec, dict):
        experience_spec = {}
    visual_identity_spec = design_brief.get("visual_identity_spec") if isinstance(design_brief, dict) else {}
    if not isinstance(visual_identity_spec, dict):
        visual_identity_spec = {}
    manifest = {
        "software_name": task.software_name,
        "version": task.version,
        "software_category": getattr(task, "software_category", ""),
        "product_type": task.product_type,
        "renderer": ui_blueprint.renderer,
        "experience_shape": experience_spec.get("experience_shape", ""),
        "experience_terminal": experience_spec.get("terminal", ""),
        "experience_shell": experience_spec.get("shell", ""),
        "product_experience_spec": experience_spec,
        "visual_identity_spec": visual_identity_spec,
        "identity_signature": visual_identity_spec.get("identity_signature", ""),
        "visual_seed": visual_identity_spec.get("visual_seed", ""),
        "palette_key": visual_identity_spec.get("palette_key", ""),
        "layout_variant": visual_identity_spec.get("layout_variant", design_brief.get("layout_variant", "")),
        "nav_model": visual_identity_spec.get("nav_model", design_brief.get("nav_model", "")),
        "workspace_shape": visual_identity_spec.get("workspace_shape", design_brief.get("workspace_shape", "")),
        "login_pattern": visual_identity_spec.get("login_pattern", design_brief.get("login_pattern", "")),
        "dashboard_pattern": design_brief.get("dashboard_pattern", ""),
        "module_pattern": design_brief.get("module_pattern", ""),
        "visual_mood": design_brief.get("visual_mood", ui_blueprint.visual_style),
        "creative_seed": str(design_brief.get("creative_seed") or task.seed),
        "source": ui_blueprint.source,
        "visual_style": ui_blueprint.visual_style,
        "entry": "index.html",
        "viewport": _viewport_for_renderer(ui_blueprint.renderer),
        "source_evidence_file": "source-ui-evidence.json",
        "source_ui_evidence": _source_evidence_from_brief(ui_blueprint),
        "modules": [{"key": module.key, "title": module.title} for module in blueprint.modules],
        "pages": [
            {
                "key": item.key,
                "title": item.title,
                "caption": item.caption,
                "file": Path(item.html_path).name,
                "html_path": item.html_path,
            }
            for item in screenshots
        ],
    }
    write_json(prototype_dir / "prototype-manifest.json", manifest)


def _source_evidence_from_brief(ui_blueprint: UiBlueprint) -> dict[str, Any]:
    brief = getattr(ui_blueprint, "design_brief", {}) or {}
    evidence = brief.get("source_ui_evidence")
    return evidence if isinstance(evidence, dict) else {}


def _write_prototype_index(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    prototype_dir: Path,
    ui_blueprint: UiBlueprint,
    screenshots: list[UiScreenshot],
) -> None:
    pages = [
        {
            "key": item.key,
            "title": item.title,
            "caption": item.caption,
            "file": Path(item.html_path).name,
        }
        for item in screenshots
    ]
    viewport = _viewport_for_renderer(ui_blueprint.renderer)
    first_page = pages[0]["file"] if pages else ""
    page_json = json.dumps(pages, ensure_ascii=False)
    module_titles = " / ".join(module.title for module in blueprint.modules[:5])
    index_html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escape(task.software_name)}运行界面预览</title>
  <style>
    :root {{ color: #1f2937; background: #eef2f6; font-family: "Microsoft YaHei", "PingFang SC", "Segoe UI", sans-serif; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; min-height: 100vh; }}
    .shell {{ display: grid; grid-template-columns: 288px 1fr; min-height: 100vh; }}
    aside {{ background: #172033; color: #d9e6f7; padding: 22px 18px; }}
    h1 {{ margin: 0 0 8px; font-size: 18px; line-height: 1.35; }}
    .meta {{ color: #91a5c2; font-size: 12px; line-height: 1.65; margin-bottom: 18px; }}
    nav {{ display: grid; gap: 8px; }}
    button {{ width: 100%; border: 0; border-radius: 7px; padding: 10px 11px; text-align: left; color: #d9e6f7; background: rgba(255,255,255,.07); cursor: pointer; font: inherit; }}
    button strong {{ display: block; font-size: 13px; line-height: 1.35; }}
    button span {{ display: block; margin-top: 4px; color: #9fb1cc; font-size: 11px; line-height: 1.45; }}
    button.active {{ background: #2f6fed; color: #fff; }}
    button.active span {{ color: #dbe8ff; }}
    main {{ min-width: 0; padding: 20px; }}
    .toolbar {{ min-height: 58px; display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 0 16px; background: #fff; border: 1px solid #dce5f1; border-radius: 8px; margin-bottom: 14px; }}
    .toolbar strong {{ font-size: 18px; }}
    .toolbar span {{ color: #64748b; font-size: 12px; }}
    a {{ color: #2563eb; font-weight: 700; text-decoration: none; }}
    .preview {{ height: calc(100vh - 112px); overflow: auto; display: grid; place-items: start center; padding: 18px; background: #dbe4ef; border-radius: 8px; border: 1px solid #ccd7e6; }}
    iframe {{ width: {viewport["width"]}px; height: {viewport["height"]}px; border: 0; background: #fff; box-shadow: 0 18px 46px rgba(31,41,55,.18); }}
  </style>
</head>
<body>
  <div class="shell">
    <aside>
      <h1>{escape(task.software_name)}</h1>
      <div class="meta">
        <div>{escape(task.product_type)} · {escape(task.version)} · {escape(ui_blueprint.renderer)}</div>
        <div>{escape(module_titles)}</div>
      </div>
      <nav id="pageList"></nav>
    </aside>
    <main>
      <div class="toolbar">
        <div>
          <strong id="pageTitle"></strong><br />
          <span id="pageCaption"></span>
        </div>
        <a id="openPage" href="{escape(first_page)}" target="_blank" rel="noreferrer">打开当前界面</a>
      </div>
      <div class="preview">
        <iframe id="previewFrame" src="{escape(first_page)}"></iframe>
      </div>
    </main>
  </div>
  <script>
    const pages = {page_json};
    const list = document.getElementById("pageList");
    const title = document.getElementById("pageTitle");
    const caption = document.getElementById("pageCaption");
    const frame = document.getElementById("previewFrame");
    const openPage = document.getElementById("openPage");
    function selectPage(index) {{
      const page = pages[index];
      if (!page) return;
      title.textContent = page.title;
      caption.textContent = page.caption || "运行界面";
      frame.src = page.file;
      openPage.href = page.file;
      Array.from(list.children).forEach((item, itemIndex) => item.classList.toggle("active", itemIndex === index));
    }}
    pages.forEach((page, index) => {{
      const item = document.createElement("button");
      item.type = "button";
      const pageTitle = document.createElement("strong");
      const pageKey = document.createElement("span");
      pageTitle.textContent = page.title;
      pageKey.textContent = "界面 " + String(index + 1).padStart(2, "0");
      item.append(pageTitle, pageKey);
      item.addEventListener("click", () => selectPage(index));
      list.appendChild(item);
    }});
    selectPage(0);
  </script>
</body>
</html>
"""
    (prototype_dir / "index.html").write_text(index_html, encoding="utf-8")
    _inject_prototype_page_navigation(pages, prototype_dir=prototype_dir)


def _inject_prototype_page_navigation(pages: list[dict[str, Any]], *, prototype_dir: Path) -> int:
    page_files = {
        str(page.get("key") or ""): str(page.get("file") or "")
        for page in pages
        if str(page.get("key") or "") and str(page.get("file") or "")
    }
    if not page_files:
        return 0
    script = f'''<script data-prototype-navigation="v1">
(() => {{
  const pageFiles = {json.dumps(page_files, ensure_ascii=False)};
  document.addEventListener("click", (event) => {{
    const trigger = event.target.closest("[data-navigation-page-key], [data-navigation-back-target]");
    if (!trigger) return;
    const pageKey = trigger.getAttribute("data-navigation-page-key") || trigger.getAttribute("data-navigation-back-target") || "";
    const target = pageFiles[pageKey];
    if (!target) return;
    event.preventDefault();
    const destination = new URL(target, window.location.href);
    if (destination.href !== window.location.href) window.location.assign(destination.href);
  }});
}})();
</script>'''
    injected = 0
    marker_pattern = re.compile(
        r'<script data-prototype-navigation="v1">.*?</script>',
        flags=re.DOTALL,
    )
    for page in pages:
        html_path = prototype_dir / str(page.get("file") or "")
        if not html_path.exists() or not html_path.is_file():
            continue
        html = html_path.read_text(encoding="utf-8")
        html = marker_pattern.sub("", html)
        if re.search(r"</body\s*>", html, flags=re.I):
            html = re.sub(r"</body\s*>", script + "</body>", html, count=1, flags=re.I)
        else:
            html += script
        html_path.write_text(html, encoding="utf-8")
        injected += 1
    return injected


def _write_prototype_readme(
    task: GenerationTask,
    prototype_dir: Path,
    ui_blueprint: UiBlueprint,
    screenshots: list[UiScreenshot],
) -> None:
    viewport = _viewport_for_renderer(ui_blueprint.renderer)
    design_brief = getattr(ui_blueprint, "design_brief", {}) or {}
    experience_spec = design_brief.get("product_experience_spec") if isinstance(design_brief, dict) else {}
    if not isinstance(experience_spec, dict):
        experience_spec = {}
    page_lines = "\n".join(f"- `{Path(item.html_path).name}`：{item.title}" for item in screenshots)
    content = f"""# {task.software_name} 运行界面原型

该目录是生成源码项目的一部分，用于保存软著说明书截图所对应的可浏览页面原型。

- 入口文件：`index.html`
- 蓝图文件：`ui_blueprint.json`
- 清单文件：`prototype-manifest.json`
- 渲染器：`{ui_blueprint.renderer}`
- 体验形态：`{experience_spec.get("experience_shape", "") or "未记录"}`
- 目标终端：`{experience_spec.get("terminal", "") or "未记录"}`
- 截图尺寸：`{viewport["width"]}x{viewport["height"]}`

页面列表：

{page_lines}
"""
    (prototype_dir / "README.md").write_text(content, encoding="utf-8")


def _publish_project_prototype(
    task: GenerationTask,
    prototype_dir: Path,
    ui_blueprint: UiBlueprint,
    screenshots: list[UiScreenshot],
    source_info: dict | None,
) -> None:
    if not isinstance(source_info, dict) or not source_info.get("source_dir"):
        return
    source_dir = Path(str(source_info["source_dir"]))
    target = _project_prototype_target(source_dir)
    served_dir = Path(target["served_dir"])
    react_source_dir = prototype_dir / "react-app"
    published_frontend_source = ""
    if react_source_dir.exists():
        frontend_target = source_dir / "frontend-app"
        if frontend_target.exists():
            shutil.rmtree(frontend_target)
        shutil.copytree(
            react_source_dir,
            frontend_target,
            ignore=shutil.ignore_patterns("dist", "node_modules", "vite.runtime.config.js"),
        )
        published_frontend_source = str(frontend_target)
        if isinstance(source_info, dict):
            source_info["ui_framework"] = "react"
            source_info["ui_frontend_source_dir"] = published_frontend_source
    runtime_served_dirs = _project_runtime_served_dirs(source_dir, served_dir)
    for runtime_served_dir in runtime_served_dirs:
        if runtime_served_dir.resolve() == prototype_dir.resolve():
            continue
        if runtime_served_dir.exists():
            shutil.rmtree(runtime_served_dir)
        shutil.copytree(prototype_dir, runtime_served_dir)
        _write_static_redirect(runtime_served_dir.parent)
    entry = {
        "entry_file": str(prototype_dir / "index.html"),
        "source_prototype_dir": str(prototype_dir),
        "served_dir": str(served_dir),
        "entry_url": target["entry_url"],
        "run_command": target["run_command"],
        "route_mode": target["route_mode"],
        "renderer": ui_blueprint.renderer,
        "experience_shape": (getattr(ui_blueprint, "design_brief", {}) or {}).get("experience_shape", ""),
        "experience_terminal": (getattr(ui_blueprint, "design_brief", {}) or {}).get("experience_terminal", ""),
        "screen_count": len(screenshots),
        "framework": "react" if published_frontend_source else "static-html",
        "frontend_source_dir": published_frontend_source,
    }
    write_json(prototype_dir / "project-entry.json", entry)
    for runtime_served_dir in runtime_served_dirs:
        if runtime_served_dir.resolve() != prototype_dir.resolve():
            write_json(runtime_served_dir / "project-entry.json", entry)
    entry_doc = _write_project_entry_doc(task, source_dir, entry)
    entry["entry_doc"] = str(entry_doc)
    write_json(prototype_dir / "project-entry.json", entry)
    for runtime_served_dir in runtime_served_dirs:
        if runtime_served_dir.resolve() != prototype_dir.resolve():
            write_json(runtime_served_dir / "project-entry.json", entry)
    source_info["ui_project_entry"] = entry


def _project_prototype_target(source_dir: Path) -> dict[str, str]:
    if (source_dir / "gateway-service" / "src" / "server.js").exists():
        return {
            "served_dir": str(source_dir / "gateway-service" / "ui-prototype"),
            "entry_url": "http://127.0.0.1:8080/ui-prototype/index.html",
            "run_command": "node gateway-service/src/server.js",
            "route_mode": "node-static",
        }
    if (source_dir / "pom.xml").exists():
        return {
            "served_dir": str(source_dir / "src" / "main" / "resources" / "static" / "ui-prototype"),
            "entry_url": "http://127.0.0.1:8080/ui-prototype/index.html",
            "run_command": "mvn spring-boot:run",
            "route_mode": "spring-static",
        }
    if list(source_dir.glob("*.csproj")):
        return {
            "served_dir": str(source_dir / "wwwroot" / "ui-prototype"),
            "entry_url": "http://127.0.0.1:5000/ui-prototype/index.html",
            "run_command": "dotnet run --urls http://127.0.0.1:5000",
            "route_mode": "aspnet-static",
        }
    if (source_dir / "app" / "main.py").exists():
        return {
            "served_dir": str(source_dir / "ui-prototype"),
            "entry_url": "http://127.0.0.1:8080/ui-prototype/index.html",
            "run_command": "uvicorn app.main:app --host 127.0.0.1 --port 8080",
            "route_mode": "fastapi-static",
        }
    if (source_dir / "web-console" / "src" / "server.js").exists():
        return {
            "served_dir": str(source_dir / "web-console" / "ui-prototype"),
            "entry_url": "http://127.0.0.1:8080/ui-prototype/index.html",
            "run_command": "node web-console/src/server.js",
            "route_mode": "node-static",
        }
    if (source_dir / "package.json").exists():
        return {
            "served_dir": str(source_dir / "ui-prototype"),
            "entry_url": "http://127.0.0.1:8080/ui-prototype/index.html",
            "run_command": "node src/server.js",
            "route_mode": "node-static",
        }
    return {
        "served_dir": str(source_dir / "ui-prototype"),
        "entry_url": "ui-prototype/index.html",
        "run_command": "open ui-prototype/index.html",
        "route_mode": "file",
    }


def _project_runtime_served_dirs(source_dir: Path, primary: Path) -> list[Path]:
    candidates = [primary]
    for folder in ("web-console", "gateway-service"):
        runtime_dir = source_dir / folder
        if (runtime_dir / "src" / "server.js").exists():
            candidates.append(runtime_dir / "ui-prototype")
    result: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate.resolve()).lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(candidate)
    return result


def _write_static_redirect(static_root: Path) -> None:
    static_root.mkdir(parents=True, exist_ok=True)
    (static_root / "index.html").write_text(
        """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta http-equiv="refresh" content="0; url=/ui-prototype/index.html" />
  <title>运行界面入口</title>
</head>
<body>
  <a href="/ui-prototype/index.html">打开运行界面</a>
</body>
</html>
""",
        encoding="utf-8",
    )


def _write_project_entry_doc(task: GenerationTask, source_dir: Path, entry: dict[str, str]) -> Path:
    content = f"""# 运行界面原型入口

本源码工程已包含软著说明书截图对应的可浏览前端原型。

- 软件名称：{task.software_name}
- 本地原型目录：`ui-prototype/`
- 项目服务目录：`{_relative_display(source_dir, Path(entry["served_dir"]))}`
- 项目访问地址：`{entry["entry_url"]}`
- 启动命令：`{entry["run_command"]}`
- 路由模式：`{entry["route_mode"]}`

也可以不启动项目，直接打开：

```text
ui-prototype/index.html
```
"""
    path = source_dir / "UI_PROTOTYPE_ENTRY.md"
    path.write_text(content, encoding="utf-8")
    return path


def _relative_display(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _emit(emit, progress: int, message: str, **extra) -> None:
    if emit:
        emit(progress, message, **extra)


def _build_pages(task: GenerationTask, blueprint: ProductBlueprint, ui_dir: Path, ui_blueprint: UiBlueprint) -> list[UiScreenshot]:
    if ui_blueprint.renderer == "game":
        return _build_game_pages(task, blueprint, ui_dir, ui_blueprint)
    if ui_blueprint.renderer == "mobile_app":
        return _build_mobile_app_pages(task, blueprint, ui_dir, ui_blueprint)

    design_brief = getattr(ui_blueprint, "design_brief", {}) or {}
    screen_by_key = {screen.key: screen for screen in ui_blueprint.screens}
    screen_by_module_key = {screen.module_key: screen for screen in ui_blueprint.screens if screen.module_key}
    login_screen = screen_by_key.get("login")
    dashboard_screen = screen_by_key.get("dashboard")
    statistics_screen = screen_by_key.get("statistics")
    pages = [
            _write_page(
                ui_dir,
                "login",
                "登录界面",
                _screen_caption(login_screen, "用户输入账号、密码和验证码后进入系统。"),
                _login_body(task, blueprint, design_brief),
                renderer="admin",
                page_kind="login",
                design_brief=design_brief,
            ),
        _write_page(
            ui_dir,
            "dashboard",
            "系统首页",
            _screen_caption(dashboard_screen, "首页集中展示核心指标、待办事项、异常提醒和快捷入口。"),
                _dashboard_body(task, blueprint, design_brief),
                renderer="admin",
                page_kind="dashboard",
                design_brief=design_brief,
            ),
    ]
    for module_index, module in enumerate(blueprint.modules):
        screen = screen_by_module_key.get(module.key) or screen_by_key.get(module.key)
        pages.append(
            _write_page(
                ui_dir,
                screen.key if screen else _module_page_key(module.key),
                module.title,
                _screen_caption(screen, module.description),
                _module_body(task, blueprint, module, design_brief, screen=screen),
                renderer="admin",
                page_kind="module",
                module_key=module.key,
                design_brief=design_brief,
            )
        )
        for operation_index, operation in enumerate(
            module_operation_coverage(module, renderer="admin", module_index=module_index),
            start=2,
        ):
            action = operation.action
            operation_page_key = _module_operation_page_key(module.key, action, operation_index)
            pages.append(
                _write_page(
                    ui_dir,
                    operation_page_key,
                    operation_page_title(module.title, action),
                    operation_caption(module.title, operation),
                    _module_operation_body(
                        task,
                        blueprint,
                        module,
                        action,
                        design_brief,
                        page_key=operation_page_key,
                        interaction_action_key=operation.action_key,
                    ),
                    renderer="admin",
                    page_kind="operation",
                    module_key=module.key,
                    design_brief=design_brief,
                    interaction_action=action,
                    interaction_mode=operation.mode,
                    interaction_surface=operation.surface,
                    requires_confirmation=operation.requires_confirmation,
                    interaction_action_key=operation.action_key,
                    interaction_role=operation.role,
                    interaction_trigger=operation.trigger,
                    interaction_input_fields=list(operation.input_fields),
                    interaction_pre_state=operation.pre_state,
                    interaction_post_state=operation.post_state,
                    interaction_result_evidence=operation.result_evidence,
                )
            )
    pages.append(
        _write_page(
            ui_dir,
            "statistics",
            "统计报表界面",
            _screen_caption(statistics_screen, "系统按日期、模块、状态和角色维度生成统计结果。"),
            _statistics_body(task, blueprint, design_brief),
            renderer="admin",
            page_kind="statistics",
            design_brief=design_brief,
        )
    )
    return pages


def _build_page_specs(task: GenerationTask, blueprint: ProductBlueprint, ui_dir: Path, ui_blueprint: UiBlueprint) -> list[UiScreenshot]:
    if ui_blueprint.renderer in {"game", "mobile_app"}:
        renderer = "game" if ui_blueprint.renderer == "game" else "mobile_app"
        module_keys = {module.key for module in blueprint.modules}
        pages: list[UiScreenshot] = []
        for screen in ui_blueprint.screens:
            module_key = screen.module_key or (screen.key if screen.key in module_keys else "")
            pages.append(
                _page_spec(
                    ui_dir,
                    screen.key,
                    screen.title,
                    screen.caption,
                    renderer=renderer,
                    page_kind=_page_kind_from_screen(screen),
                    module_key=module_key,
                )
            )
        if renderer == "mobile_app":
            screen_module_keys = {screen.module_key for screen in ui_blueprint.screens if screen.module_key}
            for module_index, module in enumerate(blueprint.modules):
                if module.key not in screen_module_keys:
                    continue
                for operation_index, operation in enumerate(
                    module_operation_coverage(module, renderer="mobile_app", module_index=module_index),
                    start=2,
                ):
                    action = operation.action
                    pages.append(
                        _page_spec(
                            ui_dir,
                            _module_operation_page_key(module.key, action, operation_index),
                            operation_page_title(module.title, action, mobile=True),
                            operation_caption(module.title, operation),
                            renderer=renderer,
                            page_kind="operation",
                            module_key=module.key,
                            interaction_action=action,
                            interaction_mode=operation.mode,
                            interaction_surface=operation.surface,
                            requires_confirmation=operation.requires_confirmation,
                            interaction_action_key=operation.action_key,
                            interaction_role=operation.role,
                            interaction_trigger=operation.trigger,
                            interaction_input_fields=list(operation.input_fields),
                            interaction_pre_state=operation.pre_state,
                            interaction_post_state=operation.post_state,
                            interaction_result_evidence=operation.result_evidence,
                        )
                    )
        return pages

    screen_by_key = {screen.key: screen for screen in ui_blueprint.screens}
    screen_by_module_key = {screen.module_key: screen for screen in ui_blueprint.screens if screen.module_key}
    login_screen = screen_by_key.get("login")
    dashboard_screen = screen_by_key.get("dashboard")
    statistics_screen = screen_by_key.get("statistics")
    pages = [
        _page_spec(
            ui_dir,
            "login",
            "登录界面",
            _screen_caption(login_screen, "用户输入账号、密码和验证码后进入系统。"),
            renderer="admin",
            page_kind="login",
        ),
        _page_spec(
            ui_dir,
            "dashboard",
            "系统首页",
            _screen_caption(dashboard_screen, "首页集中展示核心指标、待办事项、异常提醒和快捷入口。"),
            renderer="admin",
            page_kind="dashboard",
        ),
    ]
    for module_index, module in enumerate(blueprint.modules):
        screen = screen_by_module_key.get(module.key) or screen_by_key.get(module.key)
        pages.append(
            _page_spec(
                ui_dir,
                screen.key if screen else _module_page_key(module.key),
                module.title,
                _screen_caption(screen, module.description),
                renderer="admin",
                page_kind="module",
                module_key=module.key,
            )
        )
        for operation_index, operation in enumerate(
            module_operation_coverage(module, renderer="admin", module_index=module_index),
            start=2,
        ):
            action = operation.action
            pages.append(
                _page_spec(
                    ui_dir,
                    _module_operation_page_key(module.key, action, operation_index),
                    operation_page_title(module.title, action),
                    operation_caption(module.title, operation),
                    renderer="admin",
                    page_kind="operation",
                    module_key=module.key,
                    interaction_action=action,
                    interaction_mode=operation.mode,
                    interaction_surface=operation.surface,
                    requires_confirmation=operation.requires_confirmation,
                    interaction_action_key=operation.action_key,
                    interaction_role=operation.role,
                    interaction_trigger=operation.trigger,
                    interaction_input_fields=list(operation.input_fields),
                    interaction_pre_state=operation.pre_state,
                    interaction_post_state=operation.post_state,
                    interaction_result_evidence=operation.result_evidence,
                )
            )
    pages.append(
        _page_spec(
            ui_dir,
            "statistics",
            "统计报表界面",
            _screen_caption(statistics_screen, "系统按日期、模块、状态和角色维度生成统计结果。"),
            renderer="admin",
            page_kind="statistics",
        )
    )
    return pages


def _page_kind_from_screen(screen: UiScreenBlueprint) -> str:
    view_type = str(getattr(screen, "view_type", "") or "")
    key = str(getattr(screen, "key", "") or "")
    if "login" in view_type or key == "login":
        return "login"
    if "dashboard" in view_type or "home" in view_type or key in {"dashboard", "home"}:
        return "dashboard"
    if "statistics" in view_type or "report" in view_type or key == "statistics":
        return "statistics"
    if "detail" in view_type:
        return "detail"
    return "module" if str(getattr(screen, "module_key", "") or "") else "general"


def _screen_caption(screen: UiScreenBlueprint | None, fallback: str) -> str:
    if not screen:
        return fallback
    caption = str(screen.caption or "").strip()
    if caption and not _contains_any(caption, _off_context_profile_terms(fallback)):
        return caption
    return fallback


def _module_page_key(module_key: str) -> str:
    if module_key in {"login", "dashboard", "statistics"}:
        return f"module_{module_key}"
    return module_key


def _module_operation_page_key(module_key: str, action: str, operation_index: int) -> str:
    token = re.sub(r"[^a-zA-Z0-9]+", "_", action).strip("_").lower()
    token = token or f"operation_{operation_index}"
    return f"{_module_page_key(module_key)}_{token}_{operation_index}"


def _module_operation_items(module: FeatureModule, design_brief: dict[str, Any] | None = None, module_index: int = 0) -> list[str]:
    operations = [str(item).strip() for item in module.operations if str(item).strip()]
    if not operations:
        operations = [
            f"{module.title}详情",
            f"{module.title}记录",
            f"{module.title}编辑",
            f"{module.title}新增",
        ]
    secondary_mix = [str(item).strip() for item in (design_brief or {}).get("secondary_mix", []) if str(item).strip()]
    if not secondary_mix:
        return _rotate_operation_roles(operations, module_index)
    selected: list[str] = []
    used: set[int] = set()
    for preferred_action in secondary_mix:
        for index, operation in enumerate(operations):
            if index in used:
                continue
            if _operation_action_label(operation) == preferred_action or preferred_action in operation:
                selected.append(operation)
                used.add(index)
                break
    for index, operation in enumerate(operations):
        if index not in used:
            selected.append(operation)
    return _rotate_operation_roles(selected, module_index)


def _rotate_operation_roles(operations: list[str], module_index: int) -> list[str]:
    preferred = [
        ["查询", "导入"],
        ["导出", "复核"],
        ["统计", "详情"],
        ["配置", "发布"],
        ["预警", "追踪"],
        ["新增", "审核"],
        ["查看", "导出"],
        ["归档", "统计"],
    ][module_index % 8]
    selected: list[str] = []
    used: set[int] = set()
    for action in preferred:
        for index, operation in enumerate(operations):
            if index in used:
                continue
            label = _operation_action_label(operation)
            if label == action or action in operation:
                selected.append(operation)
                used.add(index)
                break
        else:
            selected.append(action)
    for index, operation in enumerate(operations):
        if index not in used:
            selected.append(operation)
    return selected


def _operation_action_label(operation: str) -> str:
    for suffix in [
        "详情",
        "查看",
        "记录",
        "编辑",
        "新增",
        "删除",
        "登记",
        "查询",
        "审核",
        "发布",
        "归档",
        "导入",
        "导出",
        "预警",
        "复核",
        "统计",
        "追踪",
        "配置",
        "定位",
        "调度",
        "训练",
        "道具",
        "结算",
        "活动",
        "确认",
        "处置",
        "失效",
    ]:
        if suffix in operation:
            return suffix
    return str(operation).strip() or "处理"


def _module_operation_body(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    module: FeatureModule,
    action: str,
    design_brief: dict[str, Any] | None = None,
    *,
    page_key: str = "",
    interaction_action_key: str = "",
) -> str:
    profile = _profile_for_blueprint(task, blueprint, design_brief)
    profile = dict(profile)
    profile["table_headers"] = _module_table_headers(profile, module)
    fields = module.data_fields[:6] or ["业务编号", "业务名称", "业务状态", "责任角色", "更新时间", "处理备注"]
    title = operation_page_title(module.title, action)
    standalone = _operation_standalone_content(profile, blueprint, module, action, fields)
    if standalone:
        return _layout(
            task,
            blueprint,
            title,
            standalone,
            module.title,
            design_brief,
            page_key=page_key or f"{module.key}__operation",
            page_kind="operation",
            module=module,
            interaction_action=action,
            interaction_action_key=interaction_action_key,
        )
    dialog = _operation_dialog(module, action, title, fields)
    background = _module_content(profile, blueprint, module)
    content = f"""
<div class="operation-preview">
  <div class="operation-background">{background}</div>
  <div class="modal-backdrop">
{dialog}
  </div>
</div>
"""
    return _layout(
        task,
        blueprint,
        title,
        content,
        module.title,
        design_brief,
        page_key=page_key or f"{module.key}__operation",
        page_kind="operation",
        module=module,
        interaction_action=action,
        interaction_action_key=interaction_action_key,
    )


def _operation_standalone_content(
    profile: dict[str, Any],
    blueprint: ProductBlueprint,
    module: FeatureModule,
    action: str,
    fields: list[str],
) -> str:
    rows = _module_rows(module, profile)
    filters = _operation_filter_grid(fields[:4])
    if action == "查询":
        return f"""
<div class="op-query-page">
  <section class="panel query-conditions"><h2>{escape(module.title)}查询条件</h2><div class="query-grid">{filters}</div><div class="query-actions"><span class="button">查询</span><span class="button ghost">重置</span><span class="button ghost">保存条件</span></div></section>
  <section class="panel query-results"><h2>查询结果</h2>{_table(profile["table_headers"], rows)}</section>
  <section class="panel query-side"><h2>常用筛选</h2>{_case_cards_for_module(profile, module)}{_operation_result_bar(module, "查询")}</section>
</div>
"""
    if action == "导入":
        return f"""
<div class="op-import-page">
  <section class="panel import-zone-panel"><h2>{escape(module.title)}数据导入</h2><div class="upload-zone"><strong>拖入或选择业务数据文件</strong><span>系统先执行字段匹配、重复校验和状态校验。</span></div><div class="file-row"><span>{escape(_safe_display_file_stem(module.title))}导入模板_20260608.xlsx</span><b>已选择</b></div><div class="progress-line"><span style="width:72%"></span></div></section>
  <section class="panel"><h2>校验结果</h2><div class="validation-list"><div><b>字段匹配</b><span>已匹配 12 个字段</span></div><div><b>重复校验</b><span>发现 2 条待确认记录</span></div><div><b>导入方式</b><span>追加写入并保留原状态</span></div></div>{_operation_result_bar(module, "导入")}</section>
  <section class="panel import-preview"><h2>导入预览</h2>{_table(profile["table_headers"], rows[:5])}</section>
</div>
"""
    if action == "导出":
        return f"""
<div class="op-export-page">
  <section class="panel export-config"><h2>{escape(module.title)}导出配置</h2>{_runtime_record_panel(module)}<div class="format-tabs"><span class="active">Excel</span><span>PDF</span><span>CSV</span></div><div class="option-list"><div><span class="check-mark">✓</span>导出当前筛选结果</div><div><span class="check-mark">✓</span>包含处理状态和更新时间</div><div><span class="check-mark muted-check">✓</span>同步生成导出结果</div></div>{_operation_result_bar(module, "导出")}</section>
  <section class="panel export-preview-wide"><h2>导出字段预览</h2>{_table(profile["table_headers"], rows[:5])}</section>
</div>
"""
    if action == "统计":
        return f"""
<div class="op-stat-page">
  <section class="panel stat-main"><h2>{escape(module.title)}统计分析</h2>{_mini_chart(profile)}<div class="stat-dialog-grid"><div><span>本期数量</span><strong>128</strong></div><div><span>完成率</span><strong>92%</strong></div><div><span>异常数</span><strong>6</strong></div></div>{_operation_result_bar(module, "统计")}</section>
  <section class="panel"><h2>分组明细</h2>{_table(profile["stat_headers"], rows[:6])}</section>
  <section class="panel"><h2>处理趋势</h2>{_timeline(profile)}</section>
</div>
"""
    if action in {"审核", "复核", "发布"}:
        return f"""
<div class="op-review-page">
  <section class="panel review-record"><h2>{escape(module.title)}{escape(action)}记录</h2>{_runtime_record_panel(module)}<div class="detail-grid">{_field_rows(module, fields[:6])}</div></section>
  <section class="panel review-steps"><h2>{escape(action)}流程</h2><div class="approval-panel"><div class="approval-step done"><b>资料校验</b><span>字段完整，状态满足处理要求</span></div><div class="approval-step active"><b>{escape(action)}意见</b><span>等待当前岗位确认处理意见</span></div><div class="approval-step"><b>结果发布</b><span>完成后刷新列表和统计口径</span></div></div>{_operation_result_bar(module, action)}</section>
  <section class="panel review-history"><h2>处理轨迹</h2>{_timeline(profile)}</section>
</div>
"""
    return ""


def _operation_filter_grid(fields: list[str]) -> str:
    labels = [str(field).strip() for field in fields if str(field).strip()] or ["业务编号", "业务名称", "状态", "更新时间"]
    return "".join(
        f"<div class='query-filter'><span>{escape(label)}</span><div>请选择或输入{escape(label)}</div></div>"
        for label in labels[:4]
    )


def _operation_dialog(module: FeatureModule, action: str, title: str, fields: list[str]) -> str:
    if action == "查询":
        return _query_dialog(module, title, fields)
    if action == "导入":
        return _import_dialog(module, title)
    if action == "导出":
        return _export_dialog(module, title)
    if action == "统计":
        return _statistics_dialog(module, title)
    if action == "预警":
        return _warning_dialog(module, title, fields)
    if action in {"审核", "复核", "发布"}:
        return _review_dialog(module, action, title, fields)
    if action in {"删除", "归档"}:
        return _confirm_dialog(module, action)
    if action in {"详情", "记录", "追踪"}:
        return _detail_dialog(module, action, title, fields)
    return _form_dialog(module, action, title, fields)


def _dialog_head(title: str) -> str:
    return f'<div class="dialog-head"><strong>{escape(title)}</strong><span class="dialog-close">×</span></div>'


def _field_rows(module: FeatureModule, fields: list[str]) -> str:
    return "".join(
        f"<div class='detail-row'><span>{escape(field)}</span><strong>{escape(_operation_sample_value(module, field, index))}</strong></div>"
        for index, field in enumerate(fields)
    )


def _form_items(module: FeatureModule, fields: list[str]) -> str:
    return "".join(
        f"<div class='form-item'><span>{escape(field)}</span><div class='form-value'>{escape(_operation_sample_value(module, field, index))}</div></div>"
        for index, field in enumerate(fields)
    )


def _query_dialog(module: FeatureModule, title: str, fields: list[str]) -> str:
    query_fields = fields[:4] or ["业务编号", "业务名称", "业务状态", "责任角色"]
    states = _module_operation_states(module)
    filters = "".join(f"<div class='query-filter'><span>{escape(field)}</span><div>请输入{escape(field)}</div></div>" for field in query_fields)
    rows = "".join(
        "<tr>"
        f"<td data-field='编号'>{escape(_operation_sample_value(module, query_fields[0], index))}</td>"
        f"<td data-field='名称'>{escape(_operation_sample_value(module, query_fields[1] if len(query_fields) > 1 else '名称', index))}</td>"
        f"<td data-field='状态'><span class='status {'warn' if index % 3 == 1 else ''}'>{escape(states[index % len(states)])}</span></td>"
        f"<td data-field='更新时间'>2026-06-0{index + 3}</td>"
        "</tr>"
        for index in range(4)
    )
    return f"""
    <section class="dialog query-dialog">
      {_dialog_head(title)}
      <div class="dialog-body">
        <div class="query-grid">{filters}</div>
        <div class="query-actions"><span class="button">查询</span><span class="button ghost">重置</span><span class="button ghost">高级筛选</span></div>
        <div class="result-box"><table><thead><tr><th>编号</th><th>名称</th><th>状态</th><th>更新时间</th></tr></thead><tbody>{rows}</tbody></table></div>
        {_operation_result_bar(module, "查询")}
      </div>
      <div class="dialog-footer"><span class="muted">共 128 条记录，当前显示前 4 条</span><span class="button">打开详情</span></div>
    </section>
"""


def _import_dialog(module: FeatureModule, title: str) -> str:
    file_name = f"{_safe_display_file_stem(module.title)}导入模板_20260608.xlsx"
    return f"""
    <section class="dialog import-dialog">
      {_dialog_head(title)}
      <div class="dialog-body">
        {_runtime_record_panel(module)}
        <div class="upload-zone">
          <strong>选择{escape(module.title)}导入文件</strong>
          <span>支持 xlsx、csv 文件，系统会先完成字段匹配和重复校验。</span>
        </div>
        <div class="file-row"><span>{escape(file_name)}</span><b>已选择</b></div>
        <div class="progress-line"><span style="width:72%"></span></div>
        <div class="validation-list">
          <div><b>字段匹配</b><span>已匹配 12 个字段</span></div>
          <div><b>重复校验</b><span>发现 2 条待确认记录</span></div>
          <div><b>导入方式</b><span>追加写入并保留原状态</span></div>
        </div>
        {_operation_result_bar(module, "导入")}
      </div>
      <div class="dialog-footer"><span class="button ghost">取消</span><span class="button">开始导入</span></div>
    </section>
"""


def _export_dialog(module: FeatureModule, title: str) -> str:
    file_name = f"{_safe_display_file_stem(module.title)}导出_20260608.xlsx"
    return f"""
    <section class="dialog export-dialog">
      {_dialog_head(title)}
      <div class="dialog-body">
        {_runtime_record_panel(module)}
        <div class="export-layout">
          <div>
            <div class="section-label">导出范围</div>
            <div class="option-list">
              <div><span class="check-mark">✓</span>当前查询结果</div>
              <div><span class="check-mark">✓</span>{escape(module.title)}明细字段</div>
              <div><span class="check-mark muted-check"> </span>更新时间与结果信息</div>
            </div>
          </div>
          <div>
            <div class="section-label">文件格式</div>
            <div class="format-tabs"><span class="active">Excel</span><span>PDF</span><span>CSV</span></div>
            <div class="export-preview">预计导出 128 条数据<br>文件名：{escape(file_name)}</div>
          </div>
        </div>
        {_operation_result_bar(module, "导出")}
      </div>
      <div class="dialog-footer"><span class="button ghost">取消</span><span class="button">确认导出</span></div>
    </section>
"""


def _statistics_dialog(module: FeatureModule, title: str) -> str:
    bars = "".join(f"<span style='height:{54 + index * 18}px'></span>" for index in range(6))
    states = _module_operation_states(module)
    legend = "".join(f"<span>{escape(state)}</span>" for state in states[:4])
    return f"""
    <section class="dialog statistics-dialog">
      {_dialog_head(title)}
      <div class="dialog-body">
        {_runtime_record_panel(module)}
        <div class="stat-dialog-grid">
          <div><span>本月处理量</span><strong>1,286</strong></div>
          <div><span>完成率</span><strong>86.4%</strong></div>
          <div><span>异常记录</span><strong>72</strong></div>
        </div>
        <div class="dialog-chart">{bars}</div>
        <div class="legend-row">{legend}</div>
        {_operation_result_bar(module, "统计")}
      </div>
      <div class="dialog-footer"><span class="button ghost">导出图表</span><span class="button">查看明细</span></div>
    </section>
"""


def _warning_dialog(module: FeatureModule, title: str, fields: list[str]) -> str:
    rows = "".join(
        f"<div><span>{escape(field)}</span><strong>{80 + index * 6}%</strong></div>"
        for index, field in enumerate((fields[:4] or ["业务状态", "更新时间", "处理备注", "责任角色"]))
    )
    return f"""
    <section class="dialog warning-dialog">
      {_dialog_head(title)}
      <div class="dialog-body">
        {_runtime_record_panel(module)}
        <div class="warning-banner"><strong>{escape(module.title)}预警触发</strong><span>请确认阈值、责任人和处理时限。</span></div>
        <div class="threshold-grid">{rows}</div>
        <div class="dialog-note">系统根据阈值规则、状态变化和处理时长生成预警，确认后生成处理事项。</div>
        {_operation_result_bar(module, "预警")}
      </div>
      <div class="dialog-footer"><span class="button ghost">暂不处理</span><span class="button">生成事项</span></div>
    </section>
"""


def _review_dialog(module: FeatureModule, action: str, title: str, fields: list[str]) -> str:
    role = _module_operation_role(module, action)
    return f"""
    <section class="dialog review-dialog">
      {_dialog_head(title)}
      <div class="dialog-body review-layout">
        {_runtime_record_panel(module)}
        <div class="detail-grid">{_field_rows(module, fields[:4])}</div>
        <div class="approval-panel">
          <div class="approval-step done"><b>提交</b><span>{escape(role)} 10:12</span></div>
          <div class="approval-step active"><b>{escape(action)}</b><span>等待当前用户处理</span></div>
          <div class="approval-step"><b>完成</b><span>确认后更新状态与结果</span></div>
        </div>
        <div class="opinion-box">请输入{escape(action)}意见或处理说明</div>
        {_operation_result_bar(module, action)}
      </div>
      <div class="dialog-footer"><span class="button ghost">退回</span><span class="button">通过{escape(action)}</span></div>
    </section>
"""


def _confirm_dialog(module: FeatureModule, action: str) -> str:
    note = f"窗口要求用户确认{action}原因，系统提交前校验权限范围并保存处理结果。"
    return f"""
    <section class="dialog confirm-dialog">
      {_dialog_head("信息")}
      {_runtime_record_panel(module)}
      <div class="confirm-body">
        <div class="confirm-icon">!</div>
        <div>
          <strong>确认{escape(action)}{escape(module.title)}记录？</strong>
          <p>{escape(note)}</p>
        </div>
      </div>
      {_operation_result_bar(module, action)}
      <div class="dialog-footer"><span class="button">确定</span><span class="button ghost">取消</span></div>
    </section>
"""


def _detail_dialog(module: FeatureModule, action: str, title: str, fields: list[str]) -> str:
    note = f"窗口用于查看{module.title}的基础信息、处理轨迹、状态变化和关联记录，便于用户核对业务结果。"
    role = _module_operation_role(module, action)
    pre_state, post_state = _module_operation_transition(module, action)
    evidence = _module_result_evidence(module, action)
    return f"""
    <section class="dialog detail-dialog">
      {_dialog_head(title)}
      <div class="dialog-body">
        {_runtime_record_panel(module)}
        <div class="detail-grid">{_field_rows(module, fields)}</div>
        <div class="track-list">
          <div><b>{escape(action)}记录</b><span>提交人：{escape(role)}　时间：2026-06-08 10:30</span></div>
          <div><b>状态变化</b><span>{escape(pre_state)} → {escape(post_state)}，{escape(evidence)}已保存</span></div>
          <div><b>关联说明</b><span>{escape(note)}</span></div>
        </div>
        {_operation_result_bar(module, action)}
      </div>
      <div class="dialog-footer"><span class="button ghost">导出记录</span><span class="button">关闭</span></div>
    </section>
"""


def _form_dialog(module: FeatureModule, action: str, title: str, fields: list[str]) -> str:
    note = f"窗口用于填写或维护{module.title}数据，系统按必填项、状态流转和业务编码规则进行校验。"
    primary = "提交" if action in {"登记", "新增"} else "保存"
    return f"""
    <section class="dialog form-dialog">
      {_dialog_head(title)}
      <div class="dialog-body">
        {_runtime_record_panel(module)}
        <div class="form-grid">{_form_items(module, fields)}</div>
        <div class="dialog-note">{escape(note)}</div>
        {_operation_result_bar(module, action)}
      </div>
      <div class="dialog-footer"><span class="button ghost">取消</span><span class="button">{escape(primary)}</span></div>
    </section>
"""


def _operation_result_bar(module: FeatureModule, action: str) -> str:
    code = _operation_sample_value(module, "编号", 0)
    subject = _module_business_subject(module)
    status = _module_operation_result_status(module, action)
    evidence = _module_result_evidence(module, action)
    return (
        f"<div class='operation-result' data-action='{escape(action)}'>"
        f"{escape(action)}结果：{escape(subject)} {escape(code)} 已进入“{escape(status)}”状态，{escape(evidence)}已保存。"
        "</div>"
    )


def _runtime_record_panel(module: FeatureModule) -> str:
    subject = _module_business_subject(module)
    code = _operation_sample_value(module, "编号", 0)
    name = _operation_sample_value(module, "名称", 0)
    scope = _operation_sample_value(module, "服务范围", 0)
    status = _operation_sample_value(module, "状态", 0)
    return f"""
        <div class="runtime-record-panel">
          <div><span>{escape(subject)}编号</span><b data-runtime-field="code">{escape(code)}</b></div>
          <div><span>{escape(subject)}名称</span><b data-runtime-field="name">{escape(name)}</b></div>
          <div><span>服务/覆盖范围</span><b data-runtime-field="scope">{escape(scope)}</b></div>
          <div><span>处理状态</span><b data-runtime-field="status">{escape(status)}</b></div>
        </div>
"""


def _operation_sample_value(module: FeatureModule, field: str, index: int) -> str:
    label = str(field or "")
    title = str(getattr(module, "title", "") or "")
    attendance = _ui_attendance_module(module)
    code = f"{_business_code_prefix(module)}-{1001 + index}"
    names = _business_record_names_for_ui(module)
    name = names[index % len(names)]
    transport = _ui_transport_module(module)
    if attendance:
        attendance_values = (
            (r"员工编号", f"EMP-{1001 + index}"),
            (r"班次名称|原班次|新班次", ["早班 09:00-18:00", "晚班 13:00-22:00", "弹性班次", "周末值班"][index % 4]),
            (r"排班日期|考勤日期", f"2026-06-{24 + (index % 4):02d}"),
            (r"上班时间", "09:00"),
            (r"下班时间", "18:00"),
            (r"打卡时间", f"2026-06-{24 + (index % 4):02d} 09:{2 + index:02d}"),
            (r"打卡位置", ["总部办公区东门", "研发中心前台", "园区南门考勤点", "客户现场考勤点"][index % 4]),
            (r"缺卡时段", ["上班打卡", "下班打卡"][index % 2]),
            (r"补卡原因", "外勤返回后补录打卡"),
            (r"证明附件", "外勤任务单.pdf"),
            (r"请假类型", ["年假", "事假", "病假", "调休"][index % 4]),
            (r"请假事由", "个人事务请假"),
            (r"统计周期", "2026年6月"),
            (r"统计口径", "按员工与班次统计"),
            (r"员工范围|适用员工", ["研发中心全员", "市场一组", "客服中心", "总部全员"][index % 4]),
            (r"班次范围", "全部生效班次"),
            (r"对比范围", "本月与上月"),
            (r"正常打卡率", "96.8%"),
            (r"迟到人数", "3人"),
            (r"请假人数", "5人"),
        )
        for pattern, value in attendance_values:
            if re.search(pattern, label):
                return value
    if re.search(r"编号|编码|单号|代码|ID", label, re.I):
        return code
    if re.search(r"名称|标题|线路|路径|方案|节点", label):
        return name
    if transport and re.search(r"途经|节点序列|站点序列", label):
        return ["沪杭枢纽-浦东东区-临港接驳点", "虹桥枢纽-外环货运站-南环联络口", "机场北站-航站楼集散点-东区短驳口", "外高桥港区-保税仓节点-主干线入口"][index % 4]
    if transport and re.search(r"方向|通行", label):
        return ["北向", "南向", "双向", "东向"][index % 4]
    if re.search(r"范围|服务|覆盖|片区|区域", label):
        if transport:
            return ["浦东东区至临港片区", "虹桥枢纽至南环货运带", "机场枢纽至东部接驳区", "港区集疏运服务圈"][index % 4]
        return f"{title}服务区域{index + 1}"
    if re.search(r"状态|进度", label):
        states = _module_operation_states(module)
        return states[index % len(states)]
    if re.search(r"单位|部门|责任|角色|人员", label):
        return "线路管理员" if transport else _module_operation_role(module)
    if re.search(r"时间|日期|更新|生效|闭环", label):
        return f"2026-06-{24 + (index % 4):02d} 15:{20 + index % 4:02d}"
    if re.search(r"等级|适配|优先级", label):
        return ["一级适配", "二级适配", "重点关注", "冲突校验"][index % 4]
    if re.search(r"结果|结论|说明|备注|意见", label):
        actions = _module_semantic_actions(module, limit=4) or ["更新", "确认", "处理", "完成"]
        return f"{title}已完成{actions[index % len(actions)]}"
    states = _module_operation_states(module)
    values = [code, name, states[index % len(states)], "线路管理员" if transport else _module_operation_role(module), "2026-06-24 15:20", f"{title}数据已完成校验"]
    return values[index % len(values)]


def _business_record_names_for_ui(module: FeatureModule) -> list[str]:
    title = str(getattr(module, "title", "") or "业务记录")
    if _ui_attendance_module(module):
        if "统计" in title:
            return ["本月出勤汇总", "部门出勤对比", "异常考勤趋势", "班次出勤分析"]
        if "排班" in title:
            return ["研发中心六月排班", "市场一组周排班", "客服中心晚班安排", "总部周末值班"]
        return [f"{title}{suffix}" for suffix in ["当日记录", "申请明细", "处理结果", "历史记录"]]
    if "干线" in title:
        return ["沪杭干线北向联络线", "城际货运南环干线", "机场枢纽快速干线", "港区集疏运主干线"]
    if "支线" in title:
        return ["临港园区接驳支线", "东部片区社区支线", "冷链仓储短驳支线", "客运站微循环支线"]
    if "节点" in title or "衔接" in title:
        return ["综合客运枢纽A区", "铁路货场换装节点", "港区东门接驳点", "机场北侧集散节点"]
    if "匹配" in title or "评估" in title:
        return ["干支线接驳时效评估", "覆盖盲区匹配复核", "节点容量冲突评估", "跨区线路组合测算"]
    if "规则" in title:
        return ["接驳距离阈值规则", "等待时长上限规则", "节点容量窗口规则", "服务范围重叠规则"]
    if "问题" in title and _ui_transport_module(module):
        return ["支线覆盖缺口工单", "节点容量冲突工单", "方向不一致处置单", "服务范围越界工单"]
    if "发布" in title or "方案" in title:
        return ["临港干支线适配方案", "机场枢纽接驳发布单", "港区集疏运生效方案", "城际线路换乘方案"]
    if "统计" in title or "报表" in title:
        return ["日运行适配汇总", "区域衔接效率报表", "规则命中趋势分析", "问题闭环统计清单"]
    return [f"{title}{suffix}" for suffix in ["事项", "明细", "任务", "结果"]]


def _ui_transport_module(module: FeatureModule) -> bool:
    text = " ".join(
        [
            str(getattr(module, "title", "") or ""),
            str(getattr(module, "description", "") or ""),
            " ".join(str(item) for item in (getattr(module, "data_fields", []) or [])),
        ]
    )
    return build_domain_profile(context_text=text).requires_route_topology


def _ui_attendance_module(module: FeatureModule) -> bool:
    text = " ".join(
        [
            str(getattr(module, "key", "") or ""),
            str(getattr(module, "title", "") or ""),
            str(getattr(module, "description", "") or ""),
            " ".join(str(item) for item in (getattr(module, "data_fields", []) or [])),
        ]
    )
    return bool(re.search(r"clock_in_out|missed_punch|leave_request|attendance|shift_schedule|考勤|打卡|补卡|请假|班次排班|出勤统计", text, re.I))


def _business_code_prefix(module: FeatureModule) -> str:
    title = str(getattr(module, "title", "") or "")
    if "干线" in title:
        return "TR-HX"
    if "支线" in title:
        return "BR-JR"
    if "节点" in title:
        return "TN-JD"
    if "匹配" in title or "评估" in title:
        return "MT-PG"
    if "规则" in title:
        return "CR-GZ"
    if "问题" in title:
        return "WT-CZ"
    if "发布" in title or "方案" in title:
        return "FA-FB"
    if "统计" in title:
        return "TJ-BB"
    return "YW"


def _safe_display_file_stem(value: str) -> str:
    text = _humanize_visible_text(str(value or "")).strip()
    text = re.sub(r"[\\/:*?\"<>|\s]+", "", text)
    return text or "业务数据"


def _build_mobile_app_pages(task: GenerationTask, blueprint: ProductBlueprint, ui_dir: Path, ui_blueprint: UiBlueprint) -> list[UiScreenshot]:
    module_by_key = {module.key: module for module in blueprint.modules}
    design_brief = getattr(ui_blueprint, "design_brief", {}) or {}
    pages: list[UiScreenshot] = []
    for screen in ui_blueprint.screens:
        module_key = screen.module_key or (screen.key if screen.key in module_by_key else "")
        module = module_by_key.get(module_key)
        body = _mobile_body_from_screen(task, blueprint, screen, module, design_brief=design_brief)
        pages.append(
            _write_page(
                ui_dir,
                screen.key,
                screen.title,
                screen.caption,
                body,
                renderer="mobile_app",
                page_kind=_page_kind_from_screen(screen),
                module_key=module_key,
                design_brief=design_brief,
            )
        )
    screen_module_keys = {screen.module_key for screen in ui_blueprint.screens if screen.module_key}
    for module_index, module in enumerate(blueprint.modules):
        if module.key not in screen_module_keys:
            continue
        for operation_index, operation in enumerate(
            module_operation_coverage(module, renderer="mobile_app", module_index=module_index),
            start=2,
        ):
            action = operation.action
            caption = operation_caption(module.title, operation)
            operation_page_key = _module_operation_page_key(module.key, action, operation_index)
            pages.append(
                _write_page(
                    ui_dir,
                    operation_page_key,
                    operation_page_title(module.title, action, mobile=True),
                    caption,
                    _mobile_operation_body(
                        task,
                        blueprint,
                        module,
                        action,
                        caption,
                        operation.mode,
                        design_brief,
                        page_key=operation_page_key,
                        interaction_action_key=operation.action_key,
                    ),
                    renderer="mobile_app",
                    page_kind="operation",
                    module_key=module.key,
                    design_brief=design_brief,
                    interaction_action=action,
                    interaction_mode=operation.mode,
                    interaction_surface=operation.surface,
                    requires_confirmation=operation.requires_confirmation,
                    interaction_action_key=operation.action_key,
                    interaction_role=operation.role,
                    interaction_trigger=operation.trigger,
                    interaction_input_fields=list(operation.input_fields),
                    interaction_pre_state=operation.pre_state,
                    interaction_post_state=operation.post_state,
                    interaction_result_evidence=operation.result_evidence,
                )
            )
    return pages


def _mobile_operation_body(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    module: FeatureModule,
    action: str,
    caption: str,
    mode: str,
    design_brief: dict[str, Any] | None = None,
    *,
    page_key: str = "",
    interaction_action_key: str = "",
) -> str:
    fields = list(module.data_fields[:4] or ["业务编号", "处理状态", "更新时间", "责任人"])
    if mode == "query":
        rows = "".join(
            f"<div><b>{escape(_operation_sample_value(module, field, index))}</b><small>{escape(field)}</small></div>"
            for index, field in enumerate(fields)
        )
        content = f"""
        <div class="mobile-search active">输入条件查询{escape(module.title)}</div>
        <div class="mobile-chip-row"><span>全部</span><span>处理中</span><span>已完成</span></div>
        <section class="mobile-result-list">{rows}</section>
        """
    else:
        rows = "".join(
            f"<div><span>{escape(field)}</span><b>{escape(_operation_sample_value(module, field, index))}</b></div>"
            for index, field in enumerate(fields)
        )
        content = f"""
        <section class="mobile-detail-head"><b>{escape(module.title)}{escape(action)}</b><small>{escape(_clip(caption, 54))}</small></section>
        <section class="mobile-detail-list">{rows}</section>
        <section class="mobile-panel compact"><b>处理结果</b><small>{escape(action)}已完成，当前状态已同步更新</small></section>
        <div class="mobile-primary">{escape(action)}</div>
        """
    return _mobile_shell(
        task,
        blueprint,
        f"{module.title}-{action}",
        content,
        active="发现",
        design_brief=design_brief,
        page_key=page_key or f"{module.key}__operation",
        page_kind="operation",
        module=module,
        interaction_action=action,
        interaction_action_key=interaction_action_key,
    )


def _mobile_body_from_screen(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    screen: UiScreenBlueprint,
    module: FeatureModule | None = None,
    design_brief: dict[str, Any] | None = None,
) -> str:
    if screen.view_type == "mobile_login":
        return _mobile_login_body(task, blueprint, screen, design_brief)
    if screen.view_type == "mobile_player":
        return _mobile_player_body(task, blueprint, screen, module, design_brief)
    if screen.view_type == "mobile_search":
        return _mobile_search_body(task, blueprint, screen, module, design_brief)
    if screen.view_type == "mobile_detail":
        return _mobile_detail_body(task, blueprint, screen, module, design_brief)
    if screen.view_type in {"mobile_profile", "mobile_statistics"}:
        return _mobile_profile_body(task, blueprint, screen, design_brief)
    return _mobile_home_body(task, blueprint, screen, module, design_brief)


def _mobile_shell(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    title: str,
    content: str,
    active: str = "首页",
    design_brief: dict[str, Any] | None = None,
    show_header: bool = True,
    show_nav: bool = True,
    page_key: str = "dashboard",
    page_kind: str = "dashboard",
    module: FeatureModule | None = None,
    interaction_action: str = "",
    interaction_action_key: str = "",
) -> str:
    contract = build_local_navigation_contract(
        task,
        blueprint,
        page_key=page_key,
        title=title,
        page_kind=page_kind,
        module=module,
        interaction_action=interaction_action,
        interaction_action_key=interaction_action_key,
        renderer="mobile_app",
        nav_model="phone_tabs",
    )
    primary_items = list(contract.get("primary_items") or [])
    active_primary_key = str(contract.get("active_primary_key") or "")
    nav_html = "".join(
        f"<span class='{'active' if str(item.get('key') or '') == active_primary_key else ''}' "
        f"data-navigation-primary-item='{escape(str(item.get('key') or ''))}' "
        f"data-navigation-page-key='{escape(str(item.get('page_key') or ''))}'>"
        f"{escape(str(item.get('label') or '功能'))}</span>"
        for item in primary_items
    )
    breadcrumb_html = "<i>/</i>".join(
        f"<span data-navigation-breadcrumb-item='{escape(str(item.get('key') or ''))}' "
        f"data-navigation-page-key='{escape(str(item.get('page_key') or ''))}'>{escape(str(item.get('label') or ''))}</span>"
        for item in list(contract.get("breadcrumb") or [])
        if str(item.get("label") or "").strip()
    )
    back_target = contract.get("back_target") if isinstance(contract.get("back_target"), dict) else {}
    back_html = ""
    if back_target and str(back_target.get("page_key") or ""):
        back_html = (
            f"<span class='mobile-navigation-back' data-navigation-back-target='{escape(str(back_target.get('page_key') or ''))}'>"
            f"← {escape(str(back_target.get('label') or '返回'))}</span>"
        )
    secondary_items = list(contract.get("secondary_items") or [])
    active_secondary_key = str(contract.get("active_secondary_key") or "")
    secondary_html = "".join(
        f"<span class='{'active' if str(item.get('key') or '') == active_secondary_key else ''}' "
        f"data-navigation-secondary-item='{escape(str(item.get('key') or ''))}' "
        f"data-navigation-page-key='{escape(str(item.get('page_key') or ''))}'>"
        f"{escape(_clip(str(item.get('label') or '功能'), 8))}</span>"
        for item in secondary_items
    )
    header_html = (
        f'<div class="mobile-header"><div class="mobile-navigation-context">{back_html}<div class="mobile-breadcrumb">{breadcrumb_html}</div></div><strong>{escape(title)}</strong><small>{escape(task.software_name)}</small></div>'
        if show_header
        else ""
    )
    secondary_block = (
        f'<nav class="mobile-secondary mobile-secondary-{escape(str(contract.get("secondary_style") or "segmented"))}">{secondary_html}</nav>'
        if show_nav and secondary_html
        else ""
    )
    nav_block = f'<nav class="mobile-nav">{nav_html}</nav>' if show_nav else ""
    profile = _profile_for_blueprint(task, blueprint, design_brief)
    classes = _identity_classes_from_brief(design_brief)
    style = _identity_style_vars(profile)
    navigation_attrs = ""
    if show_nav and page_kind != "login":
        navigation_attrs = (
            f'data-navigation-contract="{escape(str(contract.get("schema_version") or NAVIGATION_CONTRACT_VERSION))}" '
            f'data-navigation-ready="{"true" if contract.get("ready") else "false"}" '
            f'data-navigation-level="{escape(str(contract.get("level") or ""))}" '
            f'data-navigation-signature="{escape(str(contract.get("hierarchy_signature") or ""))}" '
            f'data-navigation-active-primary="{escape(active_primary_key)}" '
            f'data-navigation-active-secondary="{escape(active_secondary_key)}" '
            f'data-navigation-back-target="{escape(str(back_target.get("page_key") or ""))}"'
        )
    return f"""
<div class="mobile-screen {escape(classes)}" style="{style}" {navigation_attrs}>
  <div class="mobile-status"><span>9:41</span><span>5G 100%</span></div>
  {header_html}
  {secondary_block}
  <main class="mobile-content">{content}</main>
  {nav_block}
</div>
"""


def _mobile_login_body(task: GenerationTask, blueprint: ProductBlueprint, screen: UiScreenBlueprint, design_brief: dict[str, Any] | None = None) -> str:
    content = f"""
    <section class="mobile-hero">
      <div class="mobile-logo">{escape(task.software_name[:2] or "App")}</div>
      <h1>{escape(task.software_name)}</h1>
      <p>{escape(screen.caption or blueprint.summary)}</p>
    </section>
    <section class="mobile-panel">
      <label>手机号</label><div class="mobile-input">请输入手机号</div>
      <label>验证码</label><div class="mobile-input">请输入短信验证码</div>
      <div class="mobile-primary">登录并进入应用</div>
      <small>已阅读并同意用户协议与隐私政策</small>
    </section>
"""
    return _mobile_shell(
        task,
        blueprint,
        screen.title,
        content,
        active="我的",
        design_brief=design_brief,
        show_header=False,
        show_nav=False,
        page_key=str(getattr(screen, "key", "") or "login"),
        page_kind="login",
    )


def _mobile_home_body(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    screen: UiScreenBlueprint,
    module: FeatureModule | None = None,
    design_brief: dict[str, Any] | None = None,
) -> str:
    modules = blueprint.modules[:5]
    chips = "".join(f"<span>{escape(module.title[:8])}</span>" for module in modules)
    cards = "".join(
        f"<article class='mobile-card'><b>{escape(module.title)}</b><small>{escape(_clip(module.description, 34))}</small></article>"
        for module in modules[:4]
    )
    content = f"""
    <div class="mobile-search">搜索 {escape(task.software_name)} 内容或功能</div>
    <section class="mobile-banner"><b>{escape(screen.title)}</b><span>{escape(_clip(screen.caption, 42))}</span></section>
    <div class="mobile-chip-row">{chips}</div>
    <section class="mobile-list">{cards}</section>
"""
    return _mobile_shell(
        task,
        blueprint,
        screen.title,
        content,
        active="首页",
        design_brief=design_brief,
        page_key=str(getattr(screen, "key", "") or "dashboard"),
        page_kind=_page_kind_from_screen(screen),
        module=module,
    )


def _mobile_player_body(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    screen: UiScreenBlueprint,
    module: FeatureModule | None,
    design_brief: dict[str, Any] | None = None,
) -> str:
    title = module.title if module else screen.title
    content = f"""
    <section class="mobile-cover"><div>{escape(title[:6])}</div></section>
    <section class="mobile-player-info">
      <h2>{escape(title)}</h2>
      <p>{escape(_clip(screen.caption, 54))}</p>
      <div class="mobile-progress"><span></span></div>
      <div class="mobile-time"><span>03:28</span><span>04:52</span></div>
      <div class="mobile-controls"><b>上一首</b><strong>播放</strong><b>下一首</b></div>
    </section>
    <section class="mobile-panel compact"><b>相关推荐</b><small>{escape('、'.join(screen.components[:4]))}</small></section>
"""
    return _mobile_shell(
        task,
        blueprint,
        screen.title,
        content,
        active="发现",
        design_brief=design_brief,
        page_key=str(getattr(screen, "key", "") or (module.key if module else "player")),
        page_kind=_page_kind_from_screen(screen),
        module=module,
    )


def _mobile_search_body(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    screen: UiScreenBlueprint,
    module: FeatureModule | None,
    design_brief: dict[str, Any] | None = None,
) -> str:
    rows = "".join(f"<div><b>{escape(item)}</b><small>与 {escape(task.software_name)} 场景匹配</small></div>" for item in (screen.components[:5] or ["热门推荐", "最近搜索"]))
    content = f"""
    <div class="mobile-search active">输入关键词搜索</div>
    <div class="mobile-chip-row"><span>综合</span><span>最新</span><span>收藏</span><span>离线</span></div>
    <section class="mobile-result-list">{rows}</section>
"""
    return _mobile_shell(
        task,
        blueprint,
        screen.title,
        content,
        active="发现",
        design_brief=design_brief,
        page_key=str(getattr(screen, "key", "") or (module.key if module else "search")),
        page_kind=_page_kind_from_screen(screen),
        module=module,
    )


def _mobile_detail_body(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    screen: UiScreenBlueprint,
    module: FeatureModule | None,
    design_brief: dict[str, Any] | None = None,
) -> str:
    title = module.title if module else screen.title
    fields = module.data_fields[:5] if module else list(screen.sample_data.keys())[:5]
    rows = "".join(
        f"<div><span>{escape(field)}</span><b>{escape(_operation_sample_value(module, field, index) if module else '已同步')}</b></div>"
        for index, field in enumerate(fields)
    )
    content = f"""
    <section class="mobile-detail-head"><b>{escape(title)}</b><small>{escape(_clip(screen.caption, 64))}</small></section>
    <section class="mobile-detail-list">{rows}</section>
    <div class="mobile-primary">继续使用</div>
"""
    return _mobile_shell(
        task,
        blueprint,
        screen.title,
        content,
        active="首页",
        design_brief=design_brief,
        page_key=str(getattr(screen, "key", "") or (module.key if module else "detail")),
        page_kind=_page_kind_from_screen(screen),
        module=module,
    )


def _mobile_profile_body(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    screen: UiScreenBlueprint,
    design_brief: dict[str, Any] | None = None,
) -> str:
    attendance_app = str(getattr(blueprint, "industry_subtype_key", "") or "") == "workforce_attendance"
    items = list(screen.components[:5])
    if attendance_app:
        items = ["员工资料", "考勤设置", "打卡记录", "请假补卡记录", "应用设置"]
    elif not items or any(re.search(r"会员权益|收藏记录|下载缓存", str(item)) for item in items):
        items = ["用户资料", "使用记录", "消息设置", "隐私与安全", "应用设置"]
    rows = "".join(f"<div><b>{escape(item)}</b><small>已同步</small></div>" for item in items)
    content = f"""
    <section class="mobile-user"><div class="mobile-avatar">用户</div><b>{escape((blueprint.roles or ['用户'])[0])}</b><small>{escape(task.software_name)} 个人中心</small></section>
    <section class="mobile-result-list">{rows}</section>
"""
    return _mobile_shell(
        task,
        blueprint,
        screen.title,
        content,
        active="我的",
        design_brief=design_brief,
        page_key=str(getattr(screen, "key", "") or "statistics"),
        page_kind="statistics",
    )


def _build_game_pages(task: GenerationTask, blueprint: ProductBlueprint, ui_dir: Path, ui_blueprint: UiBlueprint) -> list[UiScreenshot]:
    module_by_key = {module.key: module for module in blueprint.modules}
    design_brief = getattr(ui_blueprint, "design_brief", {}) or {}
    pages: list[UiScreenshot] = []
    for screen in ui_blueprint.screens:
        module = module_by_key.get(screen.module_key or screen.key)
        body = _game_body_from_screen(task, blueprint, screen, module)
        pages.append(_write_page(ui_dir, screen.key, screen.title, screen.caption, body, renderer="game", design_brief=design_brief))
    return pages


def _write_page(
    ui_dir: Path,
    key: str,
    title: str,
    caption: str,
    body: str,
    renderer: str = "admin",
    page_kind: str = "general",
    module_key: str = "",
    design_brief: dict[str, Any] | None = None,
    interaction_action: str = "",
    interaction_mode: str = "",
    interaction_surface: str = "",
    requires_confirmation: bool = False,
    interaction_action_key: str = "",
    interaction_role: str = "",
    interaction_trigger: str = "",
    interaction_input_fields: list[str] | None = None,
    interaction_pre_state: str = "",
    interaction_post_state: str = "",
    interaction_result_evidence: str = "",
) -> UiScreenshot:
    html_path = ui_dir / f"{key}.html"
    html_path.write_text(
        _sanitize_formal_ui_html(_page_shell(title, body, renderer, page_kind=page_kind, module_key=module_key, design_brief=design_brief)),
        encoding="utf-8",
    )
    return UiScreenshot(
        key=key,
        title=title,
        caption=caption,
        html_path=str(html_path),
        page_kind=page_kind,
        module_key=module_key,
        interaction_action=interaction_action,
        interaction_mode=interaction_mode,
        interaction_surface=interaction_surface,
        requires_confirmation=requires_confirmation,
        interaction_action_key=interaction_action_key,
        interaction_role=interaction_role,
        interaction_trigger=interaction_trigger,
        interaction_input_fields=list(interaction_input_fields or []),
        interaction_pre_state=interaction_pre_state,
        interaction_post_state=interaction_post_state,
        interaction_result_evidence=interaction_result_evidence,
    )


def _page_spec(
    ui_dir: Path,
    key: str,
    title: str,
    caption: str,
    renderer: str = "admin",
    page_kind: str = "general",
    module_key: str = "",
    interaction_action: str = "",
    interaction_mode: str = "",
    interaction_surface: str = "",
    requires_confirmation: bool = False,
    interaction_action_key: str = "",
    interaction_role: str = "",
    interaction_trigger: str = "",
    interaction_input_fields: list[str] | None = None,
    interaction_pre_state: str = "",
    interaction_post_state: str = "",
    interaction_result_evidence: str = "",
) -> UiScreenshot:
    html_path = ui_dir / f"{key}.html"
    return UiScreenshot(
        key=key,
        title=title,
        caption=caption,
        html_path=str(html_path),
        page_kind=page_kind,
        module_key=module_key,
        interaction_action=interaction_action,
        interaction_mode=interaction_mode,
        interaction_surface=interaction_surface,
        requires_confirmation=requires_confirmation,
        interaction_action_key=interaction_action_key,
        interaction_role=interaction_role,
        interaction_trigger=interaction_trigger,
        interaction_input_fields=list(interaction_input_fields or []),
        interaction_pre_state=interaction_pre_state,
        interaction_post_state=interaction_post_state,
        interaction_result_evidence=interaction_result_evidence,
    )


def _page_shell(
    title: str,
    body: str,
    renderer: str = "admin",
    page_kind: str = "general",
    module_key: str = "",
    design_brief: dict[str, Any] | None = None,
) -> str:
    body_class = "game" if renderer == "game" else "mobile" if renderer == "mobile_app" else "admin"
    body_class = f"{body_class} {_identity_classes_from_brief(design_brief)}".strip()
    runtime_attrs = (
        f'data-page-kind="{escape(page_kind)}" '
        f'data-module-key="{escape(module_key)}" '
        f'data-renderer="{escape(renderer)}"'
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escape(title)}</title>
  <style>
    :root {{ font-family: "Microsoft YaHei", "PingFang SC", "Segoe UI", sans-serif; color: #1f2937; background: #eef2f6; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; min-height: 100vh; background: #edf2f7; }}
    body.admin {{ width: 1280px; min-height: 820px; overflow: hidden; background: #dfe7f1; }}
    .app {{ height: 100vh; min-height: 820px; display: grid; grid-template-columns: 220px 1fr; overflow: hidden; background: var(--canvas, #eef3f8); }}
    .sidebar {{ background: var(--sidebar, #1f314f); color: #dce7f7; padding: 24px 18px; box-shadow: inset -1px 0 0 rgba(255,255,255,.08); }}
    .brand {{ font-size: 18px; font-weight: 800; line-height: 1.32; margin-bottom: 22px; overflow-wrap: anywhere; }}
    .sidebar-subtitle {{ margin: -12px 0 18px; color: rgba(220,231,247,.76); font-size: 12px; line-height: 1.45; }}
    .nav {{ display: grid; gap: 8px; }}
    .nav span {{ display: block; padding: 10px 12px; border-radius: 6px; background: rgba(255,255,255,.06); font-size: 13px; border: 1px solid rgba(255,255,255,.04); overflow: hidden; text-overflow: ellipsis; }}
    [data-navigation-page-key]:not([data-navigation-page-key=""]), [data-navigation-back-target]:not([data-navigation-back-target=""]) {{ cursor: pointer; }}
    .nav span.active {{ background: var(--accent, #2f6fed); color: white; box-shadow: 0 10px 22px rgba(0,0,0,.14); }}
    .topbar {{ min-height: 96px; display: grid; grid-template-columns: minmax(260px, 330px) minmax(0, 1fr) auto; align-items: center; gap: 12px; padding: 14px 24px; background: var(--sidebar, #1f314f); color: #dce7f7; }}
    .topbar .brand-block {{ min-width: 0; align-self: stretch; display: grid; align-content: center; gap: 5px; }}
    .topbar .brand {{ margin: 0 0 4px; color: #ffffff; }}
    .topbar .muted {{ max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: rgba(220,231,247,.72); }}
    .topbar .nav {{ min-width: 0; display: flex; gap: 7px; overflow: hidden; align-items: center; }}
    .topbar .nav span {{ max-width: 172px; white-space: nowrap; flex: 0 1 auto; }}
    .topbar .nav .nav-more {{ max-width: 48px; background: rgba(255,255,255,.12); color: rgba(255,255,255,.84); }}
    .topbar .top-tools {{ max-width: 300px; min-width: 0; flex-wrap: nowrap; overflow: hidden; justify-content: flex-end; }}
    .topbar .top-tools span {{ flex: 0 0 auto; }}
    .topbar .top-tools b {{ max-width: 142px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .app.nav-top_tabs {{ grid-template-columns: 1fr; grid-template-rows: auto 1fr; }}
    .app.nav-top_tabs .main {{ padding: 20px 24px; }}
    .app.nav-rail {{ grid-template-columns: 92px 1fr; }}
    .app.nav-rail .sidebar {{ padding: 18px 12px; }}
    .app.nav-rail .brand {{ font-size: 13px; writing-mode: vertical-rl; min-height: 120px; margin: 0 auto 16px; }}
    .app.nav-rail .sidebar-subtitle {{ display: none; }}
    .app.nav-rail .nav span {{ min-height: 48px; display: grid; place-items: center; padding: 6px; font-size: 12px; text-align: center; }}
    .main {{ min-width: 0; height: 100vh; padding: 18px 22px 16px; overflow: hidden; }}
    .top {{ min-height: 78px; display: grid; grid-template-columns: minmax(0, 1fr) minmax(190px, 270px); align-items: center; gap: 16px; padding: 12px 16px; background: white; border: 1px solid #d6e0ec; border-radius: 8px; margin-bottom: 10px; box-shadow: 0 8px 24px rgba(15,23,42,.06); }}
    .top-main {{ min-width: 0; }}
    .navigation-context {{ min-width: 0; display: flex; align-items: center; gap: 9px; margin-bottom: 5px; }}
    .navigation-back {{ flex: 0 0 auto; display: inline-flex; align-items: center; height: 24px; padding: 0 8px; border: 1px solid color-mix(in srgb,var(--accent,#2f6fed) 34%,#fff); border-radius: 5px; background: var(--accent-soft,#eef6ff); color: var(--accent,#2f6fed); font-size: 11px; font-weight: 700; }}
    .breadcrumb {{ min-width: 0; display: flex; align-items: center; gap: 6px; color: #7b8798; font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    .breadcrumb span {{ min-width: 0; overflow: hidden; text-overflow: ellipsis; }}
    .breadcrumb span:last-child {{ color: #334155; font-weight: 700; }}
    .breadcrumb i {{ color: #b3bfce; font-style: normal; }}
    .title {{ font-size: 21px; font-weight: 800; line-height: 1.22; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .top-tools {{ min-width: 0; display: flex; align-items: center; justify-content: flex-end; gap: 8px; overflow: hidden; color: #52637a; font-size: 12px; white-space: nowrap; }}
    .top-tools span, .env-chip {{ height: 28px; display: inline-flex; align-items: center; padding: 0 9px; border: 1px solid #dce5ef; border-radius: 999px; background: #f8fafc; }}
    .top-tools b {{ min-width: 0; max-width: 120px; height: 32px; display: inline-flex; align-items: center; padding: 0 11px; overflow: hidden; border-radius: 999px; background: var(--accent-soft, #eef6ff); color: var(--accent, #2f6fed); text-overflow: ellipsis; }}
    .workspace-ribbon {{ height: 42px; display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 0 12px; margin-bottom: 12px; background: #ffffff; border: 1px solid #dce5ef; border-radius: 8px; }}
    .workspace-ribbon .tabs {{ min-width: 0; display: flex; gap: 6px; overflow: hidden; }}
    .workspace-ribbon .tabs span {{ height: 28px; display: inline-flex; align-items: center; padding: 0 10px; border-radius: 6px; color: #52637a; font-size: 12px; font-weight: 700; }}
    .workspace-ribbon .tabs span.active {{ background: var(--accent, #2f6fed); color: #ffffff; }}
    .workspace-ribbon.navigation-secondary-segmented .tabs {{ gap: 0; padding: 2px; border-radius: 7px; background: #edf2f7; }}
    .workspace-ribbon.navigation-secondary-segmented .tabs span {{ border-radius: 5px; }}
    .workspace-ribbon.navigation-secondary-segmented .tabs span.active {{ background: #ffffff; color: var(--accent,#2f6fed); box-shadow: 0 2px 6px rgba(15,23,42,.12); }}
    .workspace-ribbon.navigation-secondary-rail .tabs {{ padding-left: 8px; border-left: 3px solid var(--accent,#2f6fed); }}
    .workspace-ribbon .ops {{ min-width: 0; display: flex; gap: 8px; color: #64748b; font-size: 12px; overflow: hidden; white-space: nowrap; }}
    .workspace-ribbon .ops span {{ overflow: hidden; text-overflow: ellipsis; }}
    .muted {{ color: #64748b; font-size: 13px; }}
    .grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin-bottom: 16px; }}
    .card {{ background: white; border: 1px solid #dde5ef; border-radius: 8px; padding: 16px; }}
    .metric strong {{ display: block; margin-top: 8px; font-size: 26px; color: var(--accent, #1f2937); }}
    .panel {{ background: white; border: 1px solid #dde5ef; border-radius: 8px; padding: 16px; margin-bottom: 14px; overflow: hidden; box-shadow: 0 8px 22px rgba(15,23,42,.04); }}
    .panel h2 {{ margin: 0 0 12px; font-size: 17px; }}
    .table-frame {{ overflow: hidden; border: 1px solid #dde5ef; border-radius: 6px; background: #ffffff; }}
    .table-scroll {{ max-height: 342px; overflow: auto hidden; }}
    table {{ width: 100%; min-width: 720px; border-collapse: collapse; font-size: 13px; table-layout: fixed; }}
    th, td {{ padding: 10px 10px; border-bottom: 1px solid #edf1f6; text-align: left; vertical-align: middle; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    th {{ color: #52637a; background: #f8fafc; font-weight: 800; }}
    th.col-primary, td.col-primary {{ width: 21%; }}
    th.col-wide, td.col-wide {{ width: 22%; }}
    th.col-code, td.col-code {{ width: 18%; }}
    th.col-status, td.col-status {{ width: 13%; }}
    th.col-actions, td.col-actions {{ width: 22%; white-space: normal; overflow: visible; }}
    tbody tr:nth-child(even) {{ background: #fbfdff; }}
    .check-col {{ width: 38px; text-align: center; }}
    .check-dot {{ width: 14px; height: 14px; display: inline-block; border-radius: 4px; border: 1px solid #b8c4d4; background: #ffffff; }}
    .entity-cell {{ display: grid; gap: 3px; min-width: 130px; }}
    .entity-cell b {{ color: #172033; font-size: 13px; }}
    .entity-cell small {{ color: #64748b; font-size: 12px; }}
    .mono {{ font-family: "Cascadia Mono", "Consolas", monospace; color: #334155; font-size: 12px; }}
    .row-actions {{ display: flex; gap: 6px; flex-wrap: wrap; white-space: normal; max-height: 54px; overflow: hidden; }}
    .row-actions span {{ min-height: 24px; display: inline-flex; align-items: center; padding: 0 7px; border-radius: 5px; background: var(--accent-soft, #eef6ff); color: var(--accent, #2f6fed); font-size: 12px; font-weight: 800; line-height: 1.45; }}
    .table-footer {{ height: 38px; display: flex; align-items: center; justify-content: space-between; padding: 0 10px; color: #64748b; font-size: 12px; background: #fbfdff; }}
    .pager {{ display: flex; gap: 6px; align-items: center; }}
    .pager span {{ min-width: 24px; height: 24px; display: inline-grid; place-items: center; border: 1px solid #d8e1ec; border-radius: 5px; background: #ffffff; color: #52637a; }}
    .pager .active {{ background: var(--accent, #2f6fed); border-color: var(--accent, #2f6fed); color: #ffffff; }}
    .live-footer {{ margin-top: 12px; display: grid; grid-template-columns: 1.02fr 1.08fr .86fr .98fr; gap: 10px; }}
    .app.nav-rail .live-footer {{ left: 114px; }}
    .app.nav-top_tabs .live-footer, .app.workflow .live-footer {{ left: 24px; }}
    .live-card {{ min-height: 98px; padding: 12px; border: 1px solid #cfd8e5; border-radius: 8px; background: #ffffff; box-shadow: 0 8px 22px rgba(15,23,42,.05); }}
    .live-card h3 {{ margin: 0 0 10px; color: #172033; font-size: 14px; }}
    .kv-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }}
    .kv-grid div {{ min-height: 34px; padding: 6px 8px; border-radius: 5px; background: #f8fafc; border: 1px solid #e5ebf3; }}
    .kv-grid span {{ display: block; color: #64748b; font-size: 11px; }}
    .kv-grid b {{ color: #1f2937; font-size: 12px; }}
    .audit-strip {{ display: grid; gap: 7px; }}
    .audit-strip div {{ min-height: 29px; display: flex; justify-content: space-between; gap: 10px; padding: 6px 9px; border-left: 3px solid var(--accent, #2f6fed); background: #fbfdff; color: #52637a; font-size: 12px; }}
    .attachment-list {{ display: grid; gap: 8px; }}
    .attachment-list div {{ height: 29px; display: flex; align-items: center; justify-content: space-between; padding: 0 9px; border-radius: 5px; background: #f8fafc; border: 1px solid #e5ebf3; color: #52637a; font-size: 12px; }}
    .source-strip {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-bottom: 12px; }}
    .source-chip {{ min-height: 58px; padding: 9px 10px; border: 1px solid #d5e2f1; border-radius: 7px; background: linear-gradient(180deg, #ffffff, #f8fbff); overflow: hidden; }}
    .source-chip span, .source-list span {{ display: block; color: #64748b; font-size: 11px; line-height: 1.35; }}
    .source-chip b {{ display: block; margin-top: 5px; color: #172033; font-size: 12px; line-height: 1.35; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    .source-list {{ display: grid; gap: 6px; }}
    .source-list div {{ min-height: 26px; padding: 5px 7px; border-radius: 5px; background: #f8fafc; border: 1px solid #e5ebf3; overflow: hidden; }}
    .source-list b {{ display: block; color: #1f2937; font-size: 11px; line-height: 1.35; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    .source-mini {{ margin-top: 6px; color: #64748b; font-size: 11px; line-height: 1.45; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    .toolbar {{ display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 12px; align-items: center; }}
    .input {{ height: 38px; min-width: 156px; border: 1px solid #cfd8e5; border-radius: 6px; padding: 0 10px; color: #64748b; display: inline-flex; align-items: center; gap: 8px; background: #fbfdff; }}
    .input small {{ color: #7b8798; font-size: 12px; }}
    .input b {{ color: #334155; font-size: 12px; font-weight: 800; }}
    .button {{ height: 36px; padding: 0 14px; border-radius: 6px; background: var(--accent, #2f6fed); color: white; display: inline-flex; align-items: center; font-weight: 700; }}
    .status {{ padding: 4px 8px; border-radius: 999px; background: #e8f6ef; color: #157347; font-weight: 700; font-size: 12px; }}
    .warn {{ background: #fff3cd; color: #8a5a00; }}
    .operation-preview {{ position: relative; min-height: 620px; }}
    .operation-background {{ filter: saturate(.82); pointer-events: none; }}
    .modal-backdrop {{ position: fixed; inset: 0; display: grid; place-items: center; padding: 38px; background: rgba(0,0,0,.38); }}
    .dialog {{ width: min(620px, calc(100vw - 96px)); max-height: calc(100vh - 76px); overflow: hidden; border-radius: 4px; background: #ffffff; border: 1px solid #b8c2d0; box-shadow: 0 18px 52px rgba(0,0,0,.24); }}
    .detail-dialog {{ width: min(690px, calc(100vw - 96px)); }}
    .confirm-dialog {{ width: 360px; }}
    .form-dialog {{ width: 450px; }}
    .query-dialog {{ width: min(780px, calc(100vw - 96px)); }}
    .import-dialog {{ width: 500px; }}
    .export-dialog {{ width: 560px; }}
    .statistics-dialog {{ width: 620px; }}
    .warning-dialog {{ width: 520px; }}
    .review-dialog {{ width: min(720px, calc(100vw - 96px)); }}
    .dialog-head {{ height: 48px; padding: 0 16px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #e5e7eb; background: #f8fafc; }}
    .dialog-head strong {{ min-width: 0; overflow: hidden; color: #1f2937; font-size: 18px; text-overflow: ellipsis; white-space: nowrap; }}
    .dialog-close {{ width: 22px; height: 22px; display: grid; place-items: center; color: #64748b; font-size: 20px; line-height: 1; }}
    .dialog-body {{ padding: 16px; display: grid; gap: 14px; }}
    .form-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px 14px; }}
    .form-item {{ display: grid; gap: 7px; }}
    .form-item span {{ font-size: 12px; color: #52637a; font-weight: 700; }}
    .form-value {{ min-height: 38px; display: flex; align-items: center; padding: 0 10px; border: 1px solid #ccd6e3; border-radius: 6px; background: #fbfdff; color: #1f2937; font-size: 13px; }}
    .dialog-note {{ min-height: 64px; padding: 10px; border: 1px solid #ccd6e3; border-radius: 6px; background: #fbfdff; color: #52637a; line-height: 1.6; font-size: 13px; }}
    .detail-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); border: 1px solid #d7dee8; border-bottom: 0; border-right: 0; }}
    .detail-row {{ min-height: 38px; display: grid; grid-template-columns: 104px 1fr; border-right: 1px solid #d7dee8; border-bottom: 1px solid #d7dee8; }}
    .detail-row span {{ padding: 9px 10px; background: #f7f9fc; color: #52637a; font-size: 12px; }}
    .detail-row strong {{ padding: 9px 10px; color: #1f2937; font-size: 13px; font-weight: 600; }}
    .track-list {{ display: grid; gap: 8px; }}
    .track-list div {{ min-height: 42px; padding: 9px 10px; border: 1px solid #e1e7ef; border-radius: 4px; background: #fbfdff; }}
    .track-list b {{ display: block; margin-bottom: 4px; color: #1f2937; font-size: 13px; }}
    .track-list span {{ color: #64748b; font-size: 12px; line-height: 1.45; }}
    .confirm-body {{ min-height: 112px; display: grid; grid-template-columns: 38px 1fr; gap: 14px; align-items: start; padding: 22px 18px 12px; }}
    .confirm-body strong {{ display: block; margin-bottom: 10px; color: #1f2937; font-size: 16px; }}
    .confirm-body p {{ margin: 0; color: #64748b; line-height: 1.55; font-size: 13px; }}
    .confirm-icon {{ width: 32px; height: 32px; border-radius: 50%; display: grid; place-items: center; background: #eaf4ff; color: #1d8cff; font-weight: 900; font-size: 20px; }}
    .dialog-footer {{ height: 54px; padding: 0 16px; display: flex; align-items: center; justify-content: flex-end; gap: 10px; border-top: 1px solid #e5e7eb; background: #ffffff; }}
    .ghost {{ background: #eef2f7; color: #334155; }}
    .query-grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }}
    .op-query-page {{ display: grid; grid-template-columns: minmax(0, 1fr) 330px; grid-template-rows: auto 1fr; gap: 14px; align-items: start; }}
    .op-query-page .query-conditions {{ grid-column: 1 / -1; }}
    .op-query-page .query-results {{ min-height: 430px; margin-bottom: 0; }}
    .op-query-page .query-side {{ min-height: 430px; margin-bottom: 0; }}
    .op-import-page {{ display: grid; grid-template-columns: 390px minmax(0, 1fr); grid-template-rows: auto 1fr; gap: 14px; align-items: start; }}
    .op-import-page .import-zone-panel {{ min-height: 300px; margin-bottom: 0; }}
    .op-import-page .import-preview {{ grid-column: 1 / -1; margin-bottom: 0; }}
    .op-export-page {{ display: grid; grid-template-columns: 390px minmax(0, 1fr); gap: 14px; align-items: start; }}
    .op-export-page .export-config, .op-export-page .export-preview-wide {{ min-height: 540px; margin-bottom: 0; }}
    .op-stat-page {{ display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(0, .9fr); grid-template-rows: auto auto; gap: 14px; align-items: start; }}
    .op-stat-page .stat-main {{ grid-row: span 2; margin-bottom: 0; }}
    .op-review-page {{ display: grid; grid-template-columns: minmax(0, 1.1fr) 350px; grid-template-rows: auto auto; gap: 14px; align-items: start; }}
    .op-review-page .review-record {{ margin-bottom: 0; }}
    .op-review-page .review-steps {{ margin-bottom: 0; }}
    .op-review-page .review-history {{ grid-column: 1 / -1; margin-bottom: 0; }}
    .query-filter {{ min-height: 58px; display: grid; gap: 6px; }}
    .query-filter span, .section-label {{ color: #52637a; font-size: 12px; font-weight: 800; }}
    .query-filter div {{ height: 32px; display: flex; align-items: center; padding: 0 9px; border: 1px solid #ccd6e3; border-radius: 4px; color: #94a3b8; background: #fbfdff; font-size: 12px; }}
    .query-actions {{ display: flex; gap: 8px; justify-content: flex-end; }}
    .result-box {{ max-height: 210px; overflow: hidden; border: 1px solid #e1e7ef; border-radius: 4px; }}
    .upload-zone {{ min-height: 116px; display: grid; place-items: center; gap: 8px; text-align: center; border: 1px dashed #8ab4f8; background: #f4f8ff; color: #365375; }}
    .upload-zone strong {{ font-size: 16px; color: #1f2937; }}
    .upload-zone span, .file-row span {{ color: #64748b; font-size: 13px; }}
    .file-row {{ height: 42px; display: flex; align-items: center; justify-content: space-between; padding: 0 12px; border: 1px solid #e1e7ef; border-radius: 4px; background: #ffffff; }}
    .file-row b {{ color: #157347; font-size: 13px; }}
    .progress-line {{ height: 8px; overflow: hidden; border-radius: 999px; background: #e5edf6; }}
    .progress-line span {{ display: block; height: 100%; border-radius: 999px; background: var(--accent, #2f6fed); }}
    .validation-list {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }}
    .validation-list div {{ min-height: 70px; padding: 10px; border: 1px solid #e1e7ef; border-radius: 4px; background: #fbfdff; }}
    .validation-list b, .approval-step b {{ display: block; margin-bottom: 5px; color: #1f2937; font-size: 13px; }}
    .validation-list span, .approval-step span {{ color: #64748b; font-size: 12px; line-height: 1.45; }}
    .export-layout {{ display: grid; grid-template-columns: 1fr 1fr; gap: 18px; align-items: start; }}
    .runtime-record-panel {{ min-height: 76px; display: grid; grid-template-columns: 1fr 1.25fr 1fr .7fr; gap: 8px; padding: 10px; border-radius: 6px; background: #f8fafc; border: 1px solid #dce5ef; }}
    .runtime-record-panel div {{ min-width: 0; }}
    .runtime-record-panel span {{ display: block; color: #64748b; font-size: 11px; margin-bottom: 4px; }}
    .runtime-record-panel b {{ display: block; color: #172033; font-size: 12px; line-height: 1.35; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    .option-list {{ display: grid; gap: 10px; margin-top: 10px; }}
    .option-list div {{ min-height: 36px; display: flex; gap: 9px; align-items: center; padding: 0 10px; border: 1px solid #e1e7ef; border-radius: 4px; background: #fbfdff; color: #334155; font-size: 13px; }}
    .check-mark {{ width: 18px; height: 18px; display: grid; place-items: center; border-radius: 3px; background: var(--accent, #2f6fed); color: white; font-size: 12px; }}
    .muted-check {{ background: #eef2f7; color: #eef2f7; }}
    .format-tabs {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; margin: 10px 0 12px; }}
    .format-tabs span {{ height: 34px; display: grid; place-items: center; border: 1px solid #ccd6e3; border-radius: 4px; color: #52637a; font-weight: 700; font-size: 12px; }}
    .format-tabs .active {{ background: var(--accent, #2f6fed); border-color: var(--accent, #2f6fed); color: #ffffff; }}
    .export-preview {{ min-height: 86px; padding: 12px; border: 1px solid #e1e7ef; border-radius: 4px; background: #fbfdff; color: #52637a; line-height: 1.7; font-size: 13px; }}
    .operation-result {{ min-height: 54px; padding: 10px 12px; border-left: 4px solid #16a34a; background: #f0fdf4; color: #166534; font-size: 12px; line-height: 1.55; }}
    .review-layout .operation-result, .confirm-dialog .operation-result {{ grid-column: 1 / -1; margin: 0 16px 14px; }}
    .stat-dialog-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }}
    .stat-dialog-grid div {{ min-height: 82px; padding: 12px; border-radius: 4px; background: #f8fafc; border: 1px solid #e1e7ef; }}
    .stat-dialog-grid span {{ display: block; color: #52637a; font-size: 12px; margin-bottom: 8px; }}
    .stat-dialog-grid strong {{ color: var(--accent, #2f6fed); font-size: 24px; }}
    .dialog-chart {{ height: 180px; display: flex; align-items: end; gap: 14px; padding: 16px; border-radius: 4px; background: linear-gradient(180deg, #fbfdff, #f1f5f9); border: 1px solid #e1e7ef; }}
    .dialog-chart span {{ flex: 1; border-radius: 5px 5px 0 0; background: linear-gradient(180deg, var(--accent, #2f6fed), rgba(47,111,237,.32)); }}
    .legend-row {{ display: flex; gap: 14px; color: #64748b; font-size: 12px; }}
    .warning-banner {{ min-height: 74px; padding: 14px; border-left: 5px solid #f59e0b; background: #fff7ed; }}
    .warning-banner strong {{ display: block; margin-bottom: 7px; color: #92400e; font-size: 15px; }}
    .warning-banner span {{ color: #8a5a00; font-size: 13px; }}
    .threshold-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }}
    .threshold-grid div {{ min-height: 62px; display: flex; align-items: center; justify-content: space-between; padding: 0 12px; border: 1px solid #e1e7ef; border-radius: 4px; background: #fbfdff; }}
    .threshold-grid span {{ color: #52637a; font-size: 12px; }}
    .threshold-grid strong {{ color: #dc2626; font-size: 18px; }}
    .review-layout {{ grid-template-columns: 1.2fr .8fr; }}
    .review-layout .detail-grid {{ grid-column: 1; }}
    .approval-panel {{ grid-column: 2; display: grid; gap: 10px; }}
    .approval-step {{ min-height: 58px; padding: 10px 12px; border-left: 4px solid #cbd5e1; background: #fbfdff; border-radius: 4px; }}
    .approval-step.done {{ border-left-color: #16a34a; }}
    .approval-step.active {{ border-left-color: var(--accent, #2f6fed); background: var(--accent-soft, #eef6ff); }}
    .opinion-box {{ grid-column: 1 / -1; min-height: 70px; padding: 12px; border: 1px solid #ccd6e3; border-radius: 4px; background: #fbfdff; color: #94a3b8; font-size: 13px; }}
    .two-col {{ display: grid; grid-template-columns: 1.4fr .9fr; gap: 16px; align-items: start; }}
    .focus-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }}
    .focus-card {{ min-height: 88px; border: 1px solid #e3ebf5; border-radius: 8px; padding: 12px; background: linear-gradient(180deg, #ffffff, var(--accent-soft, #f7fbff)); }}
    .focus-card span {{ display: block; color: #52637a; font-size: 12px; margin-bottom: 8px; }}
    .focus-card strong {{ display: block; color: var(--accent, #2f6fed); font-size: 22px; }}
    .focus-card small {{ display: block; margin-top: 6px; color: #64748b; line-height: 1.45; }}
    .process {{ display: flex; gap: 10px; flex-wrap: wrap; }}
    .process span {{ display: inline-flex; height: 32px; align-items: center; padding: 0 10px; border-radius: 999px; background: var(--accent-soft, #eef6ff); color: #365375; font-weight: 700; font-size: 12px; }}
    .mini-chart {{ height: 164px; display: grid; grid-template-rows: 1fr auto; gap: 8px; padding: 12px; border-radius: 8px; background: #f8fafc; border: 1px solid #e5ebf3; }}
    .mini-bars {{ min-height: 112px; display: flex; align-items: end; gap: 12px; padding: 0 4px 0 28px; border-left: 1px solid #cbd5e1; border-bottom: 1px solid #cbd5e1; background: linear-gradient(180deg, rgba(148,163,184,.16) 1px, transparent 1px) 0 0 / 100% 28px; }}
    .bar {{ flex: 1; min-width: 24px; border-radius: 5px 5px 1px 1px; background: linear-gradient(180deg, var(--accent, #2f6fed), rgba(47,111,237,.35)); position: relative; }}
    .bar::after {{ content: attr(data-label); position: absolute; left: 50%; bottom: -20px; transform: translateX(-50%); color: #64748b; font-size: 10px; white-space: nowrap; }}
    .chart-meta {{ display: flex; justify-content: space-between; gap: 10px; color: #64748b; font-size: 11px; padding-left: 28px; }}
    .density-compact .panel {{ padding: 12px; margin-bottom: 10px; }}
    .density-compact th, .density-compact td {{ padding: 7px 8px; font-size: 12px; }}
    .density-compact .grid, .density-compact .pipeline-grid, .density-compact .command-strip {{ gap: 10px; margin-bottom: 10px; }}
    .density-roomy .panel {{ padding: 20px; }}
    .density-roomy th, .density-roomy td {{ padding: 13px 12px; }}
    .surface-outlined .panel, .surface-outlined .card, .surface-outlined .workspace-ribbon {{ box-shadow: none; border-color: #b9c8d9; }}
    .surface-tinted .panel, .surface-tinted .card {{ background: linear-gradient(180deg, #ffffff, var(--accent-soft, #eef6ff)); }}
    .surface-terminal .panel, .surface-terminal .card, .surface-terminal .workspace-ribbon {{ background: #111827; border-color: rgba(255,255,255,.10); color: #dbeafe; }}
    .surface-terminal .panel h2, .surface-terminal .card span, .surface-terminal .metric strong {{ color: #ffffff; }}
    .rhythm-compact .top {{ min-height: 66px; }}
    .rhythm-compact .workspace-ribbon {{ height: 34px; }}
    .rhythm-spacious .top {{ min-height: 90px; margin-bottom: 16px; }}
    .rhythm-spacious .workspace-ribbon {{ height: 50px; margin-bottom: 16px; }}
    .rhythm-instrumented .panel {{ border-left: 4px solid var(--accent, #2f6fed); }}
    .chart-line .bar {{ border-radius: 999px; min-height: 5px; background: var(--accent, #2f6fed); }}
    .chart-line .mini-bars {{ align-items: center; gap: 6px; }}
    .chart-line .bar:nth-child(odd) {{ transform: translateY(-18px); }}
    .chart-line .bar:nth-child(even) {{ transform: translateY(16px); }}
    .chart-stacked .bar {{ background: linear-gradient(180deg, var(--accent, #2f6fed) 0 46%, #f59e0b 46% 72%, #22c55e 72%); }}
    .chart-donut .mini-bars {{ display: grid; place-items: center; border: 0; background: transparent; padding: 0; }}
    .chart-donut .bar {{ width: 128px; height: 128px !important; flex: none; border-radius: 50%; background: conic-gradient(var(--accent, #2f6fed) 0 68%, #e2e8f0 68%); }}
    .chart-donut .bar:not(:first-child), .chart-donut .bar::after {{ display: none; }}
    .chart-radar .mini-bars {{ align-items: center; justify-content: center; border: 0; background: radial-gradient(circle, transparent 0 32px, rgba(148,163,184,.22) 33px 34px, transparent 35px 58px, rgba(148,163,184,.22) 59px 60px, transparent 61px); }}
    .chart-radar .bar {{ flex: 0 0 18px; min-width: 18px; border-radius: 999px; transform-origin: bottom center; }}
    .chart-radar .bar:nth-child(1) {{ transform: rotate(0deg); }} .chart-radar .bar:nth-child(2) {{ transform: rotate(45deg); }} .chart-radar .bar:nth-child(3) {{ transform: rotate(90deg); }} .chart-radar .bar:nth-child(4) {{ transform: rotate(135deg); }}
    .chart-spark .mini-chart {{ height: 116px; }}
    .chart-spark .mini-bars {{ min-height: 62px; gap: 5px; border-left: 0; }}
    .app.workflow {{ grid-template-columns: 1fr; grid-template-rows: 104px 1fr; }}
    .app.workflow .sidebar {{ display: flex; align-items: center; gap: 20px; padding: 16px 24px; }}
    .app.workflow .brand {{ width: 270px; margin: 0; }}
    .app.workflow .nav {{ min-width: 0; display: flex; gap: 8px; overflow: hidden; align-items: center; }}
    .app.workflow .nav span {{ max-width: 136px; white-space: nowrap; flex: 0 1 auto; }}
    .app.workflow .nav .nav-more {{ max-width: 48px; background: rgba(255,255,255,.12); }}
    .app.workflow .main {{ padding: 20px 26px; }}
    .app.risk {{ background: #f8fafc; grid-template-columns: 246px 1fr; }}
    .app.risk .sidebar {{ background: #17212f; }}
    .app.risk .top {{ border-left: 5px solid var(--accent, #0f766e); }}
    .app.map {{ background: #edf7f1; grid-template-columns: 248px 1fr; }}
    .app.map .sidebar {{ background: #14352b; }}
    .app.pipeline {{ background: #f6f7fb; grid-template-columns: 205px 1fr; }}
    .app.pipeline .sidebar {{ background: #251b4d; }}
    .app.nav-top_tabs {{ grid-template-columns: 1fr; grid-template-rows: auto 1fr; }}
    .app.nav-top_tabs .main {{ padding: 20px 24px; }}
    .app.nav-rail {{ grid-template-columns: 92px 1fr; }}
    .app.nav-rail .sidebar {{ padding: 18px 12px; }}
    .dashboard-split {{ display: grid; grid-template-columns: 1.15fr .85fr; gap: 16px; align-items: stretch; margin-bottom: 16px; }}
    .queue-list {{ display: grid; gap: 10px; }}
    .queue-item {{ min-height: 56px; display: grid; grid-template-columns: 1fr auto; gap: 10px; align-items: center; padding: 11px 12px; border: 1px solid #e3ebf5; border-radius: 8px; background: #fbfdff; }}
    .queue-item strong {{ display: block; font-size: 14px; color: #1f2937; }}
    .queue-item small {{ color: #64748b; line-height: 1.45; }}
    .risk-strip {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 16px; }}
    .risk-tile {{ min-height: 92px; padding: 14px; border-radius: 8px; background: #17212f; color: #d8e5f6; border: 1px solid rgba(255,255,255,.08); }}
    .risk-tile span {{ display: block; font-size: 12px; color: #9fb3ca; margin-bottom: 9px; }}
    .risk-tile strong {{ display: block; font-size: 25px; color: #ffffff; }}
    .risk-tile small {{ display: block; margin-top: 6px; color: #8de0d3; }}
    .map-board {{ position: relative; min-height: 378px; overflow: hidden; border-radius: 8px; background:
      linear-gradient(90deg, rgba(255,255,255,.54) 1px, transparent 1px) 0 0 / 48px 48px,
      linear-gradient(0deg, rgba(255,255,255,.46) 1px, transparent 1px) 0 0 / 48px 48px,
      linear-gradient(135deg, #c8f0d1, #d8ecff 58%, #fff7c8); border: 1px solid #d6e4d8; }}
    .map-board::after {{ content: ""; position: absolute; left: 8%; right: 8%; top: 47%; height: 34px; border-radius: 999px; background: rgba(22,101,52,.16); transform: rotate(-8deg); }}
    .route-line {{ position: absolute; height: 8px; border-radius: 999px; background: rgba(15,118,110,.46); transform-origin: left center; box-shadow: 0 0 0 3px rgba(255,255,255,.24); }}
    .route-line.branch {{ height: 5px; background: rgba(37,99,235,.38); box-shadow: 0 0 0 2px rgba(255,255,255,.26); }}
    .map-pin {{ position: absolute; min-width: 86px; max-width: 150px; padding: 8px 10px; border-radius: 8px; background: white; color: #1f2937; font-size: 12px; font-weight: 800; box-shadow: 0 10px 24px rgba(31,41,55,.16); border-left: 4px solid var(--accent, #16a34a); z-index: 2; }}
    .map-pin small {{ display: block; margin-top: 4px; color: #64748b; font-weight: 600; }}
    .map-legend {{ position: absolute; left: 12px; bottom: 12px; display: flex; gap: 8px; padding: 6px 8px; border-radius: 6px; background: rgba(255,255,255,.86); color: #52637a; font-size: 11px; }}
    .map-legend span::before {{ content: ""; display: inline-block; width: 16px; height: 4px; margin-right: 5px; vertical-align: middle; border-radius: 99px; background: #0f766e; }}
    .map-legend span:nth-child(2)::before {{ background: #2563eb; }}
    .pipeline-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 16px; }}
    .pipeline-card {{ min-height: 118px; display: grid; align-content: space-between; padding: 14px; border-radius: 8px; background: white; border: 1px solid #dde5ef; box-shadow: inset 0 4px 0 var(--accent-soft, #eef6ff); }}
    .pipeline-card span {{ color: #52637a; font-size: 12px; }}
    .pipeline-card strong {{ color: var(--accent, #4f46e5); font-size: 22px; }}
    .command-strip {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 16px; }}
    .command-strip .card {{ background: #111827; color: #dbeafe; border-color: rgba(255,255,255,.08); }}
    .command-strip .metric strong {{ color: #ffffff; }}
    .command-grid {{ display: grid; grid-template-columns: 1.4fr .8fr; gap: 16px; align-items: start; }}
    .command-main {{ grid-row: span 2; min-height: 420px; }}
    .app.command .top {{ border-left: 5px solid var(--accent, #334155); }}
    .app.experience-gis_map .main {{ background:
      linear-gradient(90deg, rgba(20,83,45,.08) 1px, transparent 1px) 0 0 / 36px 36px,
      linear-gradient(0deg, rgba(20,83,45,.06) 1px, transparent 1px) 0 0 / 36px 36px,
      var(--canvas, #edf7f1); }}
    .app.experience-gis_map .top {{ border-left: 5px solid var(--accent, #16a34a); }}
    .app.experience-industrial_hmi, .app.shell-industrial_hmi_panel, .app.shell-device_panel_console {{ background: #0f172a; color: #dbeafe; }}
    .app.experience-industrial_hmi .main, .app.shell-industrial_hmi_panel .main {{ background: #111827; }}
    .app.experience-industrial_hmi .panel, .app.shell-industrial_hmi_panel .panel {{ background: #172033; border-color: rgba(255,255,255,.10); color: #dbeafe; }}
    .app.experience-industrial_hmi .top, .app.shell-industrial_hmi_panel .top {{ background: #172033; border-color: rgba(255,255,255,.12); color: #dbeafe; }}
    .app.experience-cloud_ops_console .pipeline-card, .app.experience-ai_pipeline .pipeline-card {{ border-top: 4px solid var(--accent, #4f46e5); box-shadow: 0 10px 24px rgba(79,70,229,.10); }}
    .app.experience-legacy_windows {{ background: #cfd8e3; grid-template-columns: 238px 1fr; }}
    .app.experience-legacy_windows .sidebar {{ background: #dbe3ee; color: #1f2937; border-right: 1px solid #93a4b8; box-shadow: none; }}
    .app.experience-legacy_windows .sidebar-subtitle {{ color: #52637a; }}
    .app.experience-legacy_windows .nav span {{ background: #edf2f7; color: #334155; border-color: #b8c4d4; border-radius: 2px; }}
    .app.experience-legacy_windows .nav span.active {{ background: #2b579a; color: #ffffff; box-shadow: none; }}
    .app.experience-legacy_windows .panel, .app.experience-legacy_windows .top, .app.experience-legacy_windows .workspace-ribbon {{ border-radius: 2px; box-shadow: none; }}
    .kanban-board {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }}
    .kanban-col {{ min-height: 318px; padding: 12px; border: 1px solid #e1e7ef; border-radius: 8px; background: #f8fafc; }}
    .kanban-col h3 {{ margin: 0 0 10px; color: #334155; font-size: 14px; }}
    .kanban-card {{ min-height: 86px; display: grid; gap: 6px; padding: 10px; margin-bottom: 10px; border-radius: 6px; background: #ffffff; border-left: 4px solid var(--accent, #ca8a04); box-shadow: 0 6px 14px rgba(15,23,42,.06); }}
    .kanban-card strong {{ color: #1f2937; font-size: 13px; }}
    .kanban-card span, .kanban-card small {{ color: #64748b; font-size: 12px; line-height: 1.45; }}
    .matrix-layout {{ display: grid; grid-template-columns: 1.35fr .9fr; gap: 16px; align-items: start; }}
    .matrix-main {{ grid-row: span 2; }}
    .matrix-board {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }}
    .matrix-cell {{ min-height: 118px; display: grid; align-content: space-between; padding: 12px; border-radius: 8px; background: linear-gradient(180deg, #ffffff, var(--accent-soft, #faf5ff)); border: 1px solid #e1e7ef; }}
    .matrix-cell span {{ color: #52637a; font-size: 12px; }}
    .matrix-cell strong {{ color: var(--accent, #9333ea); font-size: 24px; }}
    .matrix-cell small {{ color: #64748b; line-height: 1.45; }}
    .geo-desk, .pipeline-desk, .risk-desk, .table-desk {{ display: grid; grid-template-columns: minmax(0, 1.28fr) 330px; gap: 14px; align-items: start; margin-bottom: 14px; }}
    .geo-desk .panel, .pipeline-desk .panel, .risk-desk .panel, .table-desk .panel, .case-desk .panel, .form-desk .panel {{ margin-bottom: 0; }}
    .geo-side, .table-side {{ display: grid; gap: 14px; }}
    .geo-canvas .map-board {{ min-height: 360px; }}
    .pipeline-main .table-scroll, .risk-main .table-scroll, .table-main .table-scroll {{ max-height: 300px; }}
    .case-desk {{ display: grid; grid-template-columns: 300px minmax(0, 1fr) 300px; gap: 14px; align-items: start; }}
    .case-summary .case-card {{ min-height: 82px; margin-bottom: 9px; }}
    .case-detail .table-scroll {{ max-height: 358px; }}
    .form-desk {{ display: grid; grid-template-columns: minmax(0, 1.04fr) minmax(0, 1fr); grid-template-rows: auto auto; gap: 14px; align-items: start; }}
    .form-main {{ grid-row: span 2; }}
    .module-context {{ display: grid; gap: 10px; }}
    .module-context p {{ margin: 0; color: #52637a; font-size: 13px; line-height: 1.55; }}
    .context-chips {{ display: flex; gap: 7px; flex-wrap: wrap; }}
    .context-chips span {{ min-height: 26px; display: inline-flex; align-items: center; padding: 0 8px; border-radius: 5px; background: var(--accent-soft, #eef6ff); color: var(--accent, #2f6fed); font-size: 12px; font-weight: 800; }}
    .compact-panel {{ margin-top: 0; }}
    .inline-footer {{ height: auto; padding: 12px 0 0; border-top: 0; background: transparent; }}
    .shape-triage {{ display: grid; grid-template-columns: 280px 1fr 300px; gap: 14px; align-items: stretch; }}
    .shape-triage .panel {{ margin: 0; }}
    .triage-stack {{ display: grid; gap: 10px; }}
    .triage-item {{ min-height: 68px; padding: 12px; border-left: 5px solid var(--accent, #2f6fed); background: #ffffff; box-shadow: 0 6px 16px rgba(15,23,42,.06); }}
    .triage-item strong {{ display: block; color: #172033; font-size: 13px; }}
    .triage-item span {{ display: block; margin-top: 6px; color: #64748b; font-size: 12px; }}
    .shape-ledger {{ display: grid; grid-template-columns: 1.2fr .8fr; grid-template-rows: auto 1fr; gap: 14px; }}
    .shape-ledger .ledger-toolbar {{ grid-column: 1 / -1; display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; }}
    .ledger-box {{ min-height: 54px; display: grid; align-content: center; padding: 8px 12px; border: 1px solid #dbe3ef; background: #fff; color: #52637a; font-size: 12px; }}
    .shape-wall {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; padding: 14px; background: #111827; color: #dbeafe; }}
    .shape-wall .panel {{ margin: 0; background: #172033; border-color: rgba(255,255,255,.10); color: #dbeafe; }}
    .shape-wall .panel h2 {{ color: #ffffff; }}
    .shape-wall .wall-wide {{ grid-column: span 2; min-height: 300px; }}
    .shape-wall .wall-full {{ grid-column: 1 / -1; }}
    .shape-lane {{ display: grid; gap: 14px; }}
    .lane-strip {{ display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 10px; }}
    .lane-step {{ min-height: 118px; padding: 12px; background: linear-gradient(180deg, #ffffff, var(--accent-soft, #eef6ff)); border-top: 5px solid var(--accent, #2f6fed); }}
    .lane-step b {{ display: block; color: var(--accent, #2f6fed); font-size: 22px; margin-bottom: 8px; }}
    .lane-step span {{ color: #52637a; font-size: 12px; line-height: 1.5; }}
    .shape-case {{ display: grid; grid-template-columns: 330px 1fr 310px; gap: 14px; align-items: start; }}
    .case-card {{ min-height: 96px; padding: 14px; background: #ffffff; border: 1px solid #e1e7ef; border-radius: 4px; }}
    .case-card span {{ color: #52637a; font-size: 12px; }}
    .case-card strong {{ display: block; margin-top: 8px; color: #172033; font-size: 18px; }}
    .shape-board {{ display: grid; grid-template-columns: 1fr 340px; gap: 14px; align-items: start; }}
    .shape-board .board-side {{ display: grid; gap: 14px; }}
    .freeform-grid {{ display: grid; grid-template-columns: repeat(12, minmax(0, 1fr)); gap: 14px; align-items: start; }}
    .app.shape-freeform_grid {{ height: 100vh; overflow: hidden; }}
    .app.shape-freeform_grid .main {{ min-height: 0; overflow: hidden; }}
    .app.shape-freeform_grid .top {{ min-height: 76px; margin-bottom: 12px; }}
    .freeform-slot {{ min-height: 128px; max-height: 300px; margin: 0; overflow: hidden; padding: 12px; }}
    .freeform-slot h2 {{ margin-bottom: 8px; font-size: 15px; }}
    .freeform-slot .grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin-bottom: 0; }}
    .freeform-slot .card {{ padding: 10px; }}
    .freeform-slot .metric strong {{ font-size: 20px; }}
    .freeform-slot .mini-chart {{ height: 132px; padding: 8px; }}
    .freeform-slot .mini-bars {{ min-height: 82px; gap: 8px; padding-left: 22px; }}
    .freeform-slot .queue-list {{ max-height: 230px; overflow: hidden; }}
    .freeform-slot .queue-item {{ min-height: 48px; padding: 8px 10px; }}
    .freeform-slot .map-board {{ min-height: 210px; }}
    .freeform-slot .map-pin {{ min-width: 74px; max-width: 118px; padding: 6px 8px; font-size: 11px; }}
    .freeform-slot .map-pin small {{ font-size: 10px; line-height: 1.25; }}
    .freeform-slot .map-pin:nth-of-type(5) {{ display: none; }}
    .freeform-slot .map-legend {{ left: 8px; right: 8px; bottom: 8px; flex-wrap: wrap; gap: 5px; font-size: 10px; }}
    .freeform-slot .kanban-col {{ min-height: 210px; }}
    .freeform-slot .timeline-step {{ min-height: 50px; padding-top: 8px; padding-bottom: 8px; }}
    .freeform-slot th, .freeform-slot td {{ padding: 7px 8px; font-size: 12px; }}
    .freeform-slot .table-scroll {{ max-height: 218px; }}
    .freeform-slot .table-footer {{ display: none; }}
    .freeform-slot-ledger .table-frame {{ display: none; }}
    .freeform-slot .case-card {{ min-height: 58px; padding: 9px 10px; }}
    .freeform-slot .case-card strong {{ margin-top: 3px; font-size: 15px; }}
    .freeform-slot .kv-grid, .freeform-slot .focus-grid {{ gap: 8px; }}
    .freeform-slot .ledger-toolbar {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    .freeform-dense_console {{ padding: 14px; background: #111827; }}
    .freeform-dense_console .freeform-slot {{ background: #172033; border-color: rgba(255,255,255,.10); color: #dbeafe; }}
    .freeform-dense_console .freeform-slot h2 {{ color: #ffffff; }}
    .freeform-document_desk .freeform-slot {{ border-radius: 2px; box-shadow: none; border-left: 5px solid var(--accent, #2f6fed); }}
    .freeform-wide_board .freeform-slot:first-child {{ min-height: 360px; }}
    .timeline {{ display: grid; gap: 11px; }}
    .timeline-step {{ position: relative; min-height: 62px; padding: 11px 12px 11px 42px; border: 1px solid #e3ebf5; border-radius: 8px; background: #ffffff; }}
    .timeline-step::before {{ content: attr(data-step); position: absolute; left: 12px; top: 13px; width: 22px; height: 22px; border-radius: 50%; background: var(--accent, #2f6fed); color: white; display: grid; place-items: center; font-size: 12px; font-weight: 800; }}
    .timeline-step strong {{ display: block; margin-bottom: 4px; }}
    .timeline-step small {{ color: #64748b; }}
    .login-wrap {{ min-height: 100vh; color: #172033; background: var(--login-bg, linear-gradient(135deg, #1f314f, #2f6fed)); }}
    .login-wrap .button {{ height: 42px; display: grid; place-items: center; border-radius: 6px; background: var(--accent, #2f6fed); color: white; font-weight: 800; }}
    .login-brand h1, .login-hero h1 {{ font-size: 34px; line-height: 1.18; margin: 0 0 14px; color: inherit; }}
    .login-brand p, .login-hero p {{ margin: 0; line-height: 1.7; color: inherit; opacity: .82; }}
    .login-box {{ background: white; padding: 42px; display: flex; flex-direction: column; justify-content: center; box-shadow: 0 18px 48px rgba(15,23,42,.14); }}
    .login-box h2 {{ margin: 0 0 24px; font-size: 24px; color: #172033; }}
    .login-split_brand {{ display: grid; grid-template-columns: 1fr 430px; --login-bg: linear-gradient(135deg, var(--sidebar, #1f314f), var(--accent, #2f6fed)); }}
    .login-split_brand .login-hero {{ color: white; padding: 80px 70px; display: flex; flex-direction: column; justify-content: center; }}
    .login-center_card {{ display: grid; place-items: center; padding: 64px; --login-bg: linear-gradient(180deg, #f8fafc, var(--accent-soft, #eef6ff)); }}
    .login-center_card .login-box {{ width: 460px; min-height: 490px; border-radius: 8px; }}
    .login-center_card .login-brand {{ width: 720px; max-width: calc(100vw - 620px); position: absolute; left: 70px; top: 86px; color: var(--sidebar, #1f314f); }}
    .login-console_gate {{ display: grid; grid-template-columns: 1.15fr .85fr; padding: 54px; gap: 30px; --login-bg: #0f172a; color: #dbeafe; }}
    .login-console_gate .login-box {{ background: #111827; border: 1px solid rgba(255,255,255,.12); box-shadow: none; color: #e5eefc; }}
    .login-console_gate .login-box h2 {{ color: #ffffff; }}
    .login-console_gate .field label {{ color: #9fb3ca; }}
    .login-console_gate .field div {{ background: #0b1220; border-color: #334155; color: #94a3b8; }}
    .login-console {{ border: 1px solid rgba(255,255,255,.12); background: #111827; padding: 24px; display: grid; align-content: start; gap: 14px; }}
    .login-console div {{ min-height: 44px; padding: 12px; background: #0b1220; color: #9fb3ca; border-left: 4px solid var(--accent, #2f6fed); font-size: 13px; }}
    .login-portal_grid {{ display: grid; grid-template-columns: .9fr 1.1fr; gap: 28px; padding: 56px; --login-bg: #eef2f7; }}
    .login-portal_grid .login-box {{ border-radius: 0; min-height: 520px; }}
    .login-portal {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; align-content: center; }}
    .login-portal div {{ min-height: 132px; padding: 18px; display: grid; align-content: space-between; background: white; border-left: 5px solid var(--accent, #2f6fed); box-shadow: 0 10px 24px rgba(15,23,42,.08); }}
    .login-portal span {{ color: #64748b; font-size: 12px; }}
    .login-portal strong {{ color: #172033; font-size: 20px; }}
    .login-side_preview {{ display: grid; grid-template-columns: 520px 1fr; min-height: 100vh; --login-bg: #f8fafc; }}
    .login-side_preview .login-box {{ box-shadow: none; border-right: 1px solid #d9e2ef; }}
    .login-preview {{ padding: 56px; display: grid; gap: 16px; align-content: center; }}
    .login-preview .panel {{ margin: 0; }}
    .login-security_console {{ display: grid; grid-template-columns: 1.15fr .85fr; padding: 54px; gap: 30px; --login-bg: #0f172a; color: #dbeafe; }}
    .login-security_console .login-box {{ background: #111827; border: 1px solid rgba(255,255,255,.12); box-shadow: none; color: #e5eefc; }}
    .login-security_console .login-box h2 {{ color: #ffffff; }}
    .login-security_console .field label {{ color: #9fb3ca; }}
    .login-security_console .field div {{ background: #0b1220; border-color: #334155; color: #94a3b8; }}
    .login-left_product_panel {{ display: grid; grid-template-columns: .9fr 1.1fr; gap: 28px; padding: 56px; --login-bg: #eef2f7; }}
    .login-left_product_panel .login-box {{ border-radius: 0; min-height: 520px; }}
    .login-mobile_authorize {{ display: grid; place-items: center; padding: 64px; --login-bg: linear-gradient(180deg, #f8fafc, var(--accent-soft, #eef6ff)); }}
    .login-mobile_authorize .login-box {{ width: 430px; min-height: 520px; border-radius: 22px; }}
    .login-mobile_authorize .login-box::before {{ content: "微信授权"; height: 48px; display: grid; place-items: center; margin-bottom: 18px; border-radius: 999px; background: var(--accent-soft, #eef6ff); color: var(--accent, #2f6fed); font-weight: 900; }}
    .field {{ display: grid; gap: 8px; margin-bottom: 16px; }}
    .field label {{ color: #52637a; font-size: 13px; font-weight: 700; }}
    .field div {{ height: 42px; border: 1px solid #ccd6e3; border-radius: 7px; padding: 0 12px; display: flex; align-items: center; color: #64748b; }}
    body.mobile {{ width: 720px; min-height: 1280px; overflow: hidden; background: #f4f6fb; }}
    .mobile-screen {{ width: 720px; height: 1280px; overflow: hidden; display: flex; flex-direction: column; background: linear-gradient(180deg, #f9fbff 0%, #edf3f8 100%); color: #172033; }}
    .mobile-status {{ height: 42px; padding: 12px 30px 0; display: flex; justify-content: space-between; color: #29364a; font-size: 15px; font-weight: 800; }}
    .mobile-header {{ min-height: 132px; padding: 18px 34px 16px; display: grid; gap: 7px; }}
    .mobile-navigation-context {{ min-width: 0; display: flex; align-items: center; gap: 10px; }}
    .mobile-navigation-back {{ flex: 0 0 auto; height: 28px; display: inline-flex; align-items: center; padding: 0 10px; border: 1px solid color-mix(in srgb,var(--accent,#172033) 30%,#fff); border-radius: 14px; background: var(--accent-soft,#eef6ff); color: var(--accent,#172033); font-size: 14px; font-weight: 800; }}
    .mobile-breadcrumb {{ min-width: 0; display: flex; align-items: center; gap: 6px; color: #708197; font-size: 14px; overflow: hidden; white-space: nowrap; }}
    .mobile-breadcrumb span {{ min-width: 0; overflow: hidden; text-overflow: ellipsis; }}
    .mobile-breadcrumb span:last-child {{ color: #334155; font-weight: 800; }}
    .mobile-breadcrumb i {{ color: #b4c0cf; font-style: normal; }}
    .mobile-header strong {{ font-size: 34px; line-height: 1.18; color: #172033; }}
    .mobile-header small {{ color: #66758a; font-size: 18px; }}
    .mobile-secondary {{ min-height: 62px; margin: 0 30px 16px; padding: 6px; display: grid; grid-template-columns: repeat(4,minmax(0,1fr)); gap: 5px; border-radius: 18px; background: #e8eef5; overflow: hidden; }}
    .mobile-secondary span {{ min-width: 0; display: grid; place-items: center; padding: 0 7px; border-radius: 13px; color: #66758a; font-size: 16px; font-weight: 800; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .mobile-secondary span.active {{ background: #ffffff; color: var(--accent,#172033); box-shadow: 0 4px 12px rgba(15,23,42,.12); }}
    .mobile-secondary-rail {{ border-left: 5px solid var(--accent,#172033); border-radius: 8px; }}
    .mobile-content {{ flex: 1; min-height: 0; overflow: hidden; padding: 0 30px 22px; display: grid; align-content: start; gap: 18px; }}
    .mobile-nav {{ height: 92px; padding: 10px 34px 22px; display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; background: rgba(255,255,255,.86); border-top: 1px solid #dfe7f1; }}
    .mobile-nav span {{ display: grid; place-items: center; border-radius: 18px; color: #708197; font-size: 18px; font-weight: 800; }}
    .mobile-nav span.active {{ background: #172033; color: #ffffff; }}
    .mobile-screen.identity-harbor_teal .mobile-nav span.active,
    .mobile-screen.identity-signal_green .mobile-nav span.active,
    .mobile-screen.identity-slate_cyan .mobile-nav span.active,
    .mobile-screen.identity-indigo_line .mobile-nav span.active,
    .mobile-screen.identity-amber_ops .mobile-nav span.active,
    .mobile-screen.identity-rose_audit .mobile-nav span.active,
    .mobile-screen.identity-violet_data .mobile-nav span.active,
    .mobile-screen.identity-steel_orange .mobile-nav span.active {{ background: var(--accent, #172033); }}
    .mobile-screen.shell-mini_program_shell {{ background: #f4f8f6; }}
    .mobile-screen.shell-mini_program_shell .mobile-status::after {{ content: "小程序"; margin-left: auto; padding: 3px 10px; border-radius: 999px; background: rgba(0,0,0,.06); color: #52637a; font-size: 13px; }}
    .mobile-screen.shell-mini_program_shell .mobile-banner {{ border-radius: 16px; background: linear-gradient(135deg, var(--accent, #0f766e), #17356f); }}
    .mobile-screen.shell-mini_program_shell .mobile-card,
    .mobile-screen.shell-mini_program_shell .mobile-panel,
    .mobile-screen.shell-mini_program_shell .mobile-result-list div {{ border-radius: 12px; box-shadow: none; }}
    .mobile-screen.density-compact .mobile-header {{ min-height: 92px; padding-bottom: 10px; }}
    .mobile-screen.density-compact .mobile-content {{ gap: 12px; }}
    .mobile-screen.density-compact .mobile-card, .mobile-screen.density-compact .mobile-result-list div {{ min-height: 78px; padding: 14px 16px; }}
    .mobile-screen.rhythm-spacious .mobile-content {{ gap: 24px; padding-left: 38px; padding-right: 38px; }}
    .mobile-screen.surface-outlined .mobile-card,
    .mobile-screen.surface-outlined .mobile-panel,
    .mobile-screen.surface-outlined .mobile-result-list div {{ box-shadow: none; border-color: #bccbdd; }}
    .mobile-screen.surface-tinted .mobile-card,
    .mobile-screen.surface-tinted .mobile-panel {{ background: linear-gradient(180deg, #ffffff, var(--accent-soft, #eef6ff)); }}
    .mobile-search {{ min-height: 58px; padding: 0 20px; display: flex; align-items: center; border-radius: 22px; background: #ffffff; border: 1px solid #dfe7f1; color: #7b8ba0; font-size: 18px; }}
    .mobile-search.active {{ color: #172033; box-shadow: 0 12px 26px rgba(23,32,51,.08); }}
    .mobile-banner {{ min-height: 170px; padding: 24px; display: grid; align-content: space-between; border-radius: 28px; background: linear-gradient(135deg, #182033, #2e5c72); color: #ffffff; box-shadow: 0 20px 42px rgba(23,32,51,.16); }}
    .mobile-banner b {{ font-size: 28px; line-height: 1.22; }}
    .mobile-banner span {{ color: rgba(255,255,255,.78); font-size: 17px; line-height: 1.55; }}
    .mobile-chip-row {{ display: flex; gap: 10px; flex-wrap: wrap; }}
    .mobile-chip-row span {{ min-height: 40px; display: inline-flex; align-items: center; padding: 0 16px; border-radius: 999px; background: #ffffff; border: 1px solid #dfe7f1; color: #52637a; font-size: 16px; font-weight: 800; }}
    .mobile-list, .mobile-result-list {{ display: grid; gap: 14px; }}
    .mobile-card, .mobile-result-list div, .mobile-panel, .mobile-detail-head, .mobile-detail-list, .mobile-user {{ border-radius: 24px; background: #ffffff; border: 1px solid #dfe7f1; box-shadow: 0 12px 28px rgba(23,32,51,.06); }}
    .mobile-card {{ min-height: 112px; padding: 18px 20px; display: grid; gap: 10px; }}
    .mobile-card b, .mobile-result-list b, .mobile-panel b {{ color: #172033; font-size: 20px; }}
    .mobile-card small, .mobile-result-list small, .mobile-panel small {{ color: #66758a; font-size: 15px; line-height: 1.5; }}
    .mobile-hero {{ min-height: 340px; display: grid; justify-items: center; align-content: center; gap: 18px; text-align: center; }}
    .mobile-logo, .mobile-avatar {{ width: 116px; height: 116px; border-radius: 34px; display: grid; place-items: center; background: #172033; color: #ffffff; font-size: 30px; font-weight: 900; }}
    .mobile-hero h1 {{ margin: 0; font-size: 38px; }}
    .mobile-hero p {{ margin: 0; max-width: 520px; color: #66758a; font-size: 18px; line-height: 1.65; }}
    .mobile-panel {{ padding: 24px; display: grid; gap: 13px; }}
    .mobile-panel label {{ color: #52637a; font-size: 15px; font-weight: 800; }}
    .mobile-input {{ height: 56px; display: flex; align-items: center; padding: 0 16px; border-radius: 16px; background: #f7f9fc; border: 1px solid #dce4ef; color: #8290a3; font-size: 17px; }}
    .mobile-primary {{ height: 58px; display: grid; place-items: center; border-radius: 18px; background: #172033; color: #ffffff; font-size: 19px; font-weight: 900; }}
    .mobile-cover {{ height: 430px; border-radius: 36px; display: grid; place-items: center; background: linear-gradient(145deg, #162033, #47616e 55%, #d6b16f); color: #ffffff; box-shadow: 0 24px 48px rgba(23,32,51,.22); }}
    .mobile-cover div {{ width: 230px; height: 230px; border-radius: 42px; display: grid; place-items: center; background: rgba(255,255,255,.15); border: 1px solid rgba(255,255,255,.32); font-size: 32px; font-weight: 900; text-align: center; }}
    .mobile-player-info {{ display: grid; gap: 12px; text-align: center; }}
    .mobile-player-info h2 {{ margin: 0; font-size: 30px; color: #172033; }}
    .mobile-player-info p {{ margin: 0; color: #66758a; font-size: 16px; line-height: 1.55; }}
    .mobile-progress {{ height: 8px; border-radius: 999px; background: #dbe4ef; overflow: hidden; }}
    .mobile-progress span {{ display: block; width: 58%; height: 100%; background: #172033; }}
    .mobile-time, .mobile-controls {{ display: flex; justify-content: space-between; align-items: center; color: #66758a; font-size: 15px; }}
    .mobile-controls strong {{ width: 98px; height: 98px; border-radius: 50%; display: grid; place-items: center; background: #172033; color: #ffffff; font-size: 20px; }}
    .mobile-controls b {{ font-size: 17px; color: #29364a; }}
    .mobile-panel.compact {{ padding: 18px 20px; }}
    .mobile-result-list div {{ min-height: 82px; padding: 18px 20px; display: grid; gap: 8px; }}
    .mobile-detail-head {{ min-height: 154px; padding: 24px; display: grid; align-content: center; gap: 12px; background: #172033; color: #ffffff; }}
    .mobile-detail-head b {{ font-size: 28px; }}
    .mobile-detail-head small {{ color: rgba(255,255,255,.76); font-size: 16px; line-height: 1.55; }}
    .mobile-detail-list {{ overflow: hidden; }}
    .mobile-detail-list div {{ min-height: 66px; padding: 0 20px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #edf1f6; }}
    .mobile-detail-list span {{ color: #66758a; font-size: 16px; }}
    .mobile-detail-list b {{ color: #172033; font-size: 17px; }}
    .mobile-user {{ min-height: 238px; padding: 28px; display: grid; justify-items: center; align-content: center; gap: 12px; }}
    .mobile-user b {{ font-size: 26px; color: #172033; }}
    .mobile-user small {{ color: #66758a; font-size: 16px; }}
    .game-screen {{ min-height: 100vh; padding: 28px; background: linear-gradient(160deg, #7dd3fc 0%, #fef3c7 45%, #f9a8d4 100%); color: #243044; }}
    .game-frame {{ width: 1180px; min-height: 744px; margin: 0 auto; border-radius: 24px; background: rgba(255,255,255,.78); box-shadow: 0 24px 70px rgba(43,55,90,.22); overflow: hidden; border: 6px solid rgba(255,255,255,.65); }}
    .game-top {{ height: 86px; display: flex; align-items: center; justify-content: space-between; padding: 0 30px; background: rgba(255,255,255,.82); }}
    .game-title {{ font-size: 28px; font-weight: 900; color: #30436b; }}
    .game-pill {{ display: inline-flex; align-items: center; height: 38px; padding: 0 16px; border-radius: 999px; background: #ffffff; color: #4b5f85; font-weight: 800; margin-left: 8px; box-shadow: inset 0 -2px 0 rgba(0,0,0,.05); }}
    .game-content {{ display: grid; grid-template-columns: 1fr 360px; gap: 22px; padding: 24px 30px 30px; }}
    .game-panel {{ background: rgba(255,255,255,.88); border-radius: 18px; padding: 20px; border: 2px solid rgba(255,255,255,.75); }}
    .game-board {{ display: grid; grid-template-columns: repeat(8, 54px); grid-auto-rows: 54px; gap: 8px; justify-content: center; padding: 18px; border-radius: 20px; background: #4f46e5; box-shadow: inset 0 0 0 6px rgba(255,255,255,.18); }}
    .gem {{ width: 54px; height: 54px; border-radius: 15px; box-shadow: inset 0 -8px 0 rgba(0,0,0,.12), 0 5px 12px rgba(31,41,55,.18); }}
    .gem.a {{ background: #fb7185; }} .gem.b {{ background: #fbbf24; }} .gem.c {{ background: #34d399; }} .gem.d {{ background: #60a5fa; }} .gem.e {{ background: #a78bfa; }} .gem.f {{ background: #f472b6; }}
    .target-row {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-top: 12px; }}
    .target {{ border-radius: 14px; background: #f8fafc; padding: 12px; text-align: center; font-weight: 800; color: #334155; }}
    .target b {{ display: block; font-size: 24px; color: #2563eb; margin-top: 4px; }}
    .level-map {{ position: relative; height: 470px; border-radius: 22px; background: linear-gradient(180deg, #bbf7d0, #bfdbfe); overflow: hidden; }}
    .level-node {{ position: absolute; width: 62px; height: 62px; border-radius: 50%; background: #fff; display: grid; place-items: center; font-weight: 900; color: #2563eb; box-shadow: 0 8px 18px rgba(30,64,175,.18); border: 5px solid #facc15; }}
    .game-list {{ display: grid; gap: 12px; }}
    .game-list div {{ border-radius: 14px; background: #ffffff; padding: 13px 15px; display: flex; align-items: center; justify-content: space-between; font-weight: 800; color: #41516f; }}
    .big-action {{ height: 58px; border-radius: 18px; background: linear-gradient(180deg, #f97316, #ea580c); color: white; display: grid; place-items: center; font-size: 22px; font-weight: 900; margin-top: 16px; box-shadow: inset 0 -5px 0 rgba(0,0,0,.14); }}
    .game-card-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }}
    .game-card {{ min-height: 132px; border-radius: 18px; background: #fff; padding: 18px; display: grid; align-content: space-between; box-shadow: 0 12px 24px rgba(30,41,59,.12); }}
    .game-card strong {{ font-size: 28px; color: #2563eb; }}
    body.game {{ width: 720px; min-height: 1280px; overflow: hidden; background: #67d8ff; }}
    body.game .game-screen {{ width: 720px; height: 1280px; min-height: 1280px; padding: 0; overflow: hidden; position: relative; background:
      radial-gradient(circle at 14% 10%, rgba(255,255,255,.9) 0 42px, transparent 44px),
      radial-gradient(circle at 86% 12%, rgba(255,246,174,.9) 0 58px, transparent 60px),
      radial-gradient(circle at 82% 82%, rgba(255,142,200,.85) 0 92px, transparent 94px),
      linear-gradient(180deg, #60d7ff 0%, #9cf3bd 42%, #ffd66d 72%, #ff91c8 100%); color: #27324f; }}
    body.game .game-screen::before {{ content: ""; position: absolute; inset: 0; background:
      linear-gradient(135deg, rgba(255,255,255,.22) 25%, transparent 25%) 0 0 / 42px 42px,
      linear-gradient(315deg, rgba(255,255,255,.12) 25%, transparent 25%) 0 0 / 42px 42px; pointer-events: none; }}
    body.game .game-frame {{ width: 720px; height: 1280px; min-height: 1280px; margin: 0; border: 0; border-radius: 0; background: transparent; box-shadow: none; position: relative; overflow: hidden; padding: 28px 28px 34px; }}
    body.game .game-frame::before {{ content: ""; position: absolute; left: 230px; top: 12px; width: 260px; height: 24px; border-radius: 999px; background: rgba(20,34,65,.18); }}
    body.game .game-top {{ height: auto; min-height: 150px; padding: 46px 22px 18px; margin: -28px -28px 22px; border-radius: 0 0 34px 34px; background: rgba(255,255,255,.82); backdrop-filter: blur(10px); align-items: flex-start; flex-direction: column; justify-content: flex-start; gap: 12px; box-shadow: 0 16px 34px rgba(65,78,119,.14); }}
    body.game .game-top > div:last-child {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    body.game .game-title {{ max-width: 650px; font-size: 34px; line-height: 1.18; color: #263b72; text-shadow: 0 2px 0 rgba(255,255,255,.8); }}
    body.game .game-pill {{ height: 42px; margin: 0; padding: 0 15px; border-radius: 999px; background: #ffffff; color: #345083; font-size: 16px; box-shadow: inset 0 -4px 0 rgba(37,99,235,.08), 0 8px 18px rgba(30,64,175,.10); }}
    body.game .game-content {{ display: flex; flex-direction: column; gap: 18px; padding: 0; }}
    body.game .game-panel {{ width: 100%; border-radius: 30px; padding: 22px; background: rgba(255,255,255,.86); border: 4px solid rgba(255,255,255,.72); box-shadow: 0 18px 42px rgba(38,55,100,.16); }}
    body.game .game-panel h2 {{ margin: 0 0 18px; color: #223b71; font-size: 28px; }}
    body.game .game-board {{ grid-template-columns: repeat(8, 58px); grid-auto-rows: 58px; gap: 6px; justify-content: center; padding: 18px; border-radius: 28px; background: linear-gradient(180deg, #6654ff, #4934d8); box-shadow: inset 0 0 0 8px rgba(255,255,255,.20), 0 18px 35px rgba(55,48,163,.24); }}
    body.game .gem {{ width: 58px; height: 58px; border-radius: 17px; box-shadow: inset 0 -9px 0 rgba(0,0,0,.13), inset 0 8px 0 rgba(255,255,255,.18), 0 7px 13px rgba(31,41,55,.18); }}
    body.game .target-row {{ grid-template-columns: repeat(3, 1fr); gap: 12px; }}
    body.game .target {{ min-height: 96px; border-radius: 22px; padding: 14px 8px; font-size: 16px; background: linear-gradient(180deg, #ffffff, #f5fbff); box-shadow: inset 0 -4px 0 rgba(37,99,235,.07); }}
    body.game .target b {{ font-size: 30px; color: #315df4; }}
    body.game .level-map {{ height: 560px; border-radius: 32px; background:
      radial-gradient(circle at 25% 20%, rgba(255,255,255,.62) 0 54px, transparent 56px),
      radial-gradient(circle at 72% 70%, rgba(255,255,255,.45) 0 72px, transparent 74px),
      linear-gradient(180deg, #b8ffc8, #8bd7ff); box-shadow: inset 0 0 0 7px rgba(255,255,255,.35); }}
    body.game .level-node {{ width: 76px; height: 76px; border-width: 7px; font-size: 22px; box-shadow: 0 12px 24px rgba(30,64,175,.22), inset 0 -5px 0 rgba(250,204,21,.18); }}
    body.game .game-list {{ gap: 14px; }}
    body.game .game-list div {{ min-height: 58px; border-radius: 20px; padding: 14px 18px; font-size: 18px; box-shadow: inset 0 -4px 0 rgba(37,99,235,.05); }}
    body.game .big-action {{ height: 76px; border-radius: 28px; font-size: 28px; letter-spacing: 0; background: linear-gradient(180deg, #ff9b21, #f35b0b); box-shadow: inset 0 -8px 0 rgba(149,49,0,.22), 0 14px 24px rgba(234,88,12,.24); }}
    body.game .game-card-grid {{ grid-template-columns: repeat(2, 1fr); gap: 16px; }}
    body.game .game-card {{ min-height: 148px; border-radius: 26px; padding: 20px; background: linear-gradient(180deg, #ffffff, #fff9ed); box-shadow: 0 14px 28px rgba(31,41,55,.12), inset 0 -5px 0 rgba(37,99,235,.05); font-size: 18px; }}
    body.game .game-card strong {{ font-size: 34px; color: #2d63f5; }}
  </style>
</head>
<body class="{body_class}" {runtime_attrs}>{body}{runtime_api_script()}</body>
</html>"""


def _sanitize_formal_ui_html(html: str) -> str:
    """Keep generated screenshots business-facing while evidence stays in JSON/report files."""
    text = _humanize_visible_text(html)
    text = re.sub(r"\bGET\s*/[A-Za-z0-9_./-]+", "业务接口已连接", text)
    text = re.sub(r"\bPOST\s*/[A-Za-z0-9_./-]+", "业务提交接口", text)
    text = re.sub(r"\bPATCH\s*/[A-Za-z0-9_./-]+", "状态更新接口", text)
    text = re.sub(r"\b[A-Z][A-Za-z0-9_]*(?:Service|Controller|Router|Route)\.[A-Za-z0-9_]+", "业务处理服务", text)
    text = re.sub(r"\b[A-Z][A-Za-z0-9_]*(?:Service|Controller|Router|Route)\b", "业务服务", text)
    text = re.sub(r"\b[a-z][a-z0-9_]+_(?:router|service|model)\.py\b", "业务模块文件", text)
    text = re.sub(r"\b[a-z][a-z0-9_]+(?:Route|Service|Record)\.js\b", "业务前端模块", text)
    text = re.sub(r"\b[a-z][a-z0-9_]+(?:_export|_detail|_audit)?\.(?:xlsx|pdf|log|csv)\b", "业务导出文件", text)
    return _dedupe_business_phrases(text)


def _ensure_runtime_layout_guard(html: str) -> str:
    body_attrs = _body_attrs(html)
    renderer = _html_data_attribute(body_attrs, "renderer") or "admin"
    guard = _runtime_layout_guard_style(renderer)
    style_pattern = r"<style\b[^>]*id=[\"']soft-ai-runtime-guard[\"'][^>]*>[\s\S]*?</style>"
    if re.search(style_pattern, html, flags=re.I):
        return re.sub(style_pattern, guard, html, count=1, flags=re.I)
    if re.search(r"</head\s*>", html, flags=re.I):
        return re.sub(r"</head\s*>", lambda _match: guard + "\n</head>", html, count=1, flags=re.I)
    if re.search(r"<body\b", html, flags=re.I):
        return re.sub(r"<body\b", lambda _match: "<head>" + guard + "</head>\n<body", html, count=1, flags=re.I)
    return guard + "\n" + html


def _runtime_layout_guard_style(renderer: str) -> str:
    if renderer in {"mobile_app", "game"}:
        size = "body{width:720px!important;height:1280px!important;min-height:1280px!important;overflow:hidden!important;}"
        app_rules = ""
    else:
        size = "body{width:1280px!important;height:720px!important;min-height:720px!important;overflow:hidden!important;background:#fff8f3;}"
        app_rules = """
body[data-ai-frontend="true"][data-renderer="admin"] .app{width:1280px!important;height:720px!important;max-width:1280px!important;max-height:720px!important;overflow:hidden!important;}
body[data-ai-frontend="true"][data-renderer="admin"] :is(.main,.content,.workspace,.grid,.bottom,.middle){min-width:0!important;min-height:0!important;}
body[data-ai-frontend="true"][data-renderer="admin"] .work-area{min-width:0!important;min-height:0!important;grid-template-rows:minmax(0,1fr)!important;overflow:hidden!important;}
body[data-ai-frontend="true"][data-renderer="admin"] .screen-root>.metric-strip{flex:0 0 auto!important;height:auto!important;min-height:0!important;max-height:86px!important;overflow:hidden!important;}
body[data-ai-frontend="true"][data-renderer="admin"] .workspace{grid-template-rows:minmax(0,1fr)!important;}
body[data-ai-frontend="true"][data-renderer="admin"] table{width:100%!important;table-layout:fixed!important;border-collapse:collapse;}
body[data-ai-frontend="true"][data-renderer="admin"] :is(th,td){min-width:0!important;max-width:100%!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important;line-height:1.18!important;vertical-align:middle!important;}
body[data-ai-frontend="true"][data-renderer="admin"] :is(button,.btn,.mini-btn,.tab,.nav-item,.select,.input,.mini-input,.tag,.badge,.status span,.field label,.op a){min-width:0!important;max-width:100%!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important;line-height:1.18!important;word-break:keep-all!important;}
body[data-ai-frontend="true"][data-renderer="admin"] :is(button,.btn,.mini-btn){display:inline-flex!important;align-items:center!important;justify-content:center!important;font-size:12px!important;padding-left:8px!important;padding-right:8px!important;}
body[data-ai-frontend="true"][data-renderer="admin"] :is(.opbtn,button.opbtn){height:20px!important;min-height:20px!important;max-height:20px!important;font-size:11px!important;line-height:1!important;padding-top:0!important;padding-bottom:0!important;}
body[data-ai-frontend="true"][data-renderer="admin"] :is(.tag,.badge){display:inline-flex!important;align-items:center!important;justify-content:center!important;padding-left:6px!important;padding-right:6px!important;}
body[data-ai-frontend="true"][data-renderer="admin"] :is(.code,.num,.val,.metric .num,.mcell .val,.record-title .code){display:block!important;min-width:0!important;max-width:100%!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important;line-height:1.12!important;}
body[data-ai-frontend="true"][data-renderer="admin"] :is(.code,.record-title .code){font-size:20px!important;}
body[data-ai-frontend="true"][data-renderer="admin"] :is(.metric .num,.mcell .val,.val){font-size:20px!important;}
body[data-ai-frontend="true"][data-renderer="admin"] :is(.runtime-record-panel b,.meta b,.rec .r-line b,.source-list b){min-width:0!important;max-width:100%!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important;}
body[data-ai-frontend="true"][data-renderer="admin"] .runtime-record-panel :is(div,article,section,li){min-width:0!important;}
body[data-ai-frontend="true"][data-renderer="admin"] .runtime-record-panel :is(b,strong,time,[class*="value"]){display:block!important;min-width:0!important;max-width:100%!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important;}
body[data-ai-frontend="true"][data-renderer="admin"] :is(.operation-result){max-width:100%!important;overflow:hidden!important;text-overflow:ellipsis!important;line-height:1.28!important;}
body[data-ai-frontend="true"][data-renderer="admin"] :is(.work-area,.workspace,.content)>.detail-panel.operation-result{height:100%!important;min-height:0!important;max-height:100%!important;overflow:hidden!important;}
body[data-ai-frontend="true"][data-renderer="admin"] .detail-panel.operation-result>.detail-grid{flex:1 1 0%!important;min-height:0!important;grid-template-rows:minmax(0,1.03fr) minmax(0,.97fr)!important;overflow:hidden!important;}
body[data-ai-frontend="true"][data-renderer="admin"] .comparison-main:has(>.table-panel.operation-result){height:100%!important;min-height:0!important;grid-template-rows:minmax(0,1fr) minmax(0,170px)!important;overflow:hidden!important;}
body[data-ai-frontend="true"][data-renderer="admin"] .comparison-main>.table-panel.operation-result{height:100%!important;min-height:0!important;max-height:170px!important;overflow:hidden!important;}
body[data-ai-frontend="true"][data-renderer="admin"] .workspace>.execution-rail{height:100%!important;min-height:0!important;max-height:100%!important;overflow:hidden!important;}
body[data-ai-frontend="true"][data-renderer="admin"] :is(.map-pin,.map-node,.relation-node,.flow-node) :is(b,strong,span,em){display:block!important;min-width:0!important;max-width:100%!important;white-space:nowrap!important;word-break:keep-all!important;overflow:hidden!important;text-overflow:ellipsis!important;}
body[data-ai-frontend="true"][data-renderer="admin"][data-page-kind="login"] :is(.left-console,.login-hero,.login-brand) h1{max-width:none!important;font-size:31px!important;line-height:1.15!important;white-space:nowrap!important;word-break:keep-all!important;overflow:hidden!important;text-overflow:ellipsis!important;}
body[data-ai-frontend="true"] .page-spec-root :is(button,th,td,.detail-item,.workflow-step,.timeline-item,.kanban-column,.mobile-list-item,.operation-result,.map-pin,.graph-node){overflow:visible!important;}
body[data-ai-frontend="true"] .page-spec-root :is(button,th,td,.detail-item span,.detail-item strong,.workflow-step strong,.workflow-step small,.timeline-item strong,.timeline-item p,.kanban-column strong,.kanban-column article span,.mobile-list-item strong,.mobile-list-item span,.operation-result strong,.operation-result span,.map-pin b,.map-pin small,.graph-node span,.graph-node strong){white-space:normal!important;overflow-wrap:anywhere!important;word-break:break-word!important;text-overflow:clip!important;}
body[data-ai-frontend="true"] .page-spec-root .page-spec-workspace{overflow:auto!important;}
""".strip()
    return f"""
<style id="soft-ai-runtime-guard">
html,body{{margin:0!important;box-sizing:border-box;}}
*,*::before,*::after{{box-sizing:inherit;}}
{size}
body[data-ai-frontend="true"]{{font-family:"Microsoft YaHei","PingFang SC",Arial,sans-serif;-webkit-font-smoothing:antialiased;text-rendering:geometricPrecision;}}
{app_rules}
body[data-renderer="mobile_app"][data-page-kind="operation"] #root,
body[data-renderer="mobile_app"][data-page-kind="operation"] .screen-root,
body[data-renderer="mobile_app"][data-page-kind="operation"] :is(.phone-shell,.mobile-shell,.app-shell){{width:720px!important;min-width:720px!important;max-width:720px!important;margin-left:0!important;margin-right:0!important;}}
body[data-renderer="mobile_app"][data-page-kind="operation"] :is(.confirm-drawer,.detail-drawer,.confirm-panel,[class*="modal"]:not([class*="layer"]):not([class*="overlay"]),[class*="dialog"]:not([class*="layer"]):not([class*="overlay"]),[role="dialog"]:not(:has([class*="dialog"],[class*="modal"]))){{position:fixed!important;left:50%!important;right:auto!important;top:50%!important;bottom:auto!important;transform:translate(-50%,-50%)!important;width:calc(100vw - 32px)!important;max-width:688px!important;max-height:calc(100vh - 48px)!important;margin:0!important;overflow:auto!important;z-index:10000!important;border-radius:12px!important;}}
body[data-renderer="admin"][data-page-kind="operation"] :is(.confirm-drawer,.detail-drawer,.confirm-panel,[class*="modal"]:not([class*="layer"]):not([class*="overlay"]),[class*="dialog"]:not([class*="layer"]):not([class*="overlay"]),[role="dialog"]:not(:has([class*="dialog"],[class*="modal"]))){{position:fixed!important;left:50%!important;right:auto!important;top:50%!important;bottom:auto!important;transform:translate(-50%,-50%)!important;width:min(720px,calc(100vw - 48px))!important;max-height:calc(100vh - 48px)!important;margin:0!important;overflow:auto!important;z-index:10000!important;border-radius:12px!important;}}
.runtime-generated-record{{display:none!important;}}
.runtime-generated-record span{{display:block;color:#64748b;font-size:11px;margin-bottom:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
.runtime-generated-record b{{display:block;font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
.runtime-audit-evidence[data-runtime-operation-result]{{display:block!important;min-width:0!important;max-width:100%!important;height:18px!important;margin-top:4px!important;padding:0 6px!important;border-radius:4px!important;background:#ecfdf5!important;color:#166534!important;font-size:10px!important;line-height:18px!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important;}}
</style>
""".strip()


def _instant_interaction_text_hits(text: str) -> list[str]:
    patterns = ["登记", "确认播放", "确认下载", "确认收藏", "确认查看", "等待用户确认", "提交确认"]
    return [pattern for pattern in patterns if pattern in str(text or "")]


def _assert_interaction_semantics(page, item: UiScreenshot) -> None:
    if item.page_kind != "operation":
        return
    visible_text = page.locator("body").inner_text()
    hits = _instant_interaction_text_hits(visible_text)
    visible_filter = "elements => elements.filter(el => { const s=getComputedStyle(el); const r=el.getBoundingClientRect(); return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0; }).length"
    dialog_selector = '[role="dialog"], .confirm-drawer, .detail-drawer, .confirm-panel, [class*="modal"], [class*="dialog"]'
    visible_dialog_count = page.locator(dialog_selector).evaluate_all(visible_filter)
    shared_dialog_count = page.locator(
        '[data-shared-confirm-dialog="true"][data-shared-confirm-ready="true"][role="dialog"]'
    ).evaluate_all(visible_filter)
    local_dialog_count = page.locator(
        '.screen-root [role="dialog"], .screen-root .confirm-drawer, .screen-root .detail-drawer, .screen-root .confirm-panel, .screen-root [class*="modal"], .screen-root [class*="dialog"]'
    ).evaluate_all(visible_filter)
    error = _interaction_semantics_error(
        item,
        hits=hits,
        visible_dialog_count=visible_dialog_count,
        shared_dialog_count=shared_dialog_count,
        local_dialog_count=local_dialog_count,
        shared_contract_enabled=page.locator('[data-shared-confirmation-contract="v1"]').count() > 0,
    )
    if error:
        raise RuntimeError(error)


def _interaction_semantics_error(
    item: UiScreenshot,
    *,
    hits: list[str],
    visible_dialog_count: int,
    shared_dialog_count: int = 0,
    local_dialog_count: int = 0,
    shared_contract_enabled: bool = False,
) -> str:
    if item.page_kind != "operation":
        return ""
    if item.interaction_mode == "instant" and (hits or visible_dialog_count):
        details = "、".join(hits) if hits else f"可见确认弹窗 {visible_dialog_count} 个"
        return f"{item.key} 即时操作页出现不应存在的登记/确认流程：{details}"
    if item.requires_confirmation and shared_contract_enabled:
        if shared_dialog_count != 1:
            return f"{item.key} 确认操作页必须且只能显示 1 个 SharedConfirmDialog，当前为 {shared_dialog_count} 个"
        if local_dialog_count:
            return f"{item.key} 已启用 SharedConfirmDialog，但仍有 {local_dialog_count} 个页面私有弹窗可见"
    return ""


def _body_attrs(html: str) -> str:
    match = re.search(r"<body\b([^>]*)>", str(html or ""), flags=re.I)
    return match.group(1) if match else ""


def _runtime_module_keys(blueprint: ProductBlueprint, limit: int = 4) -> list[str]:
    return _unique_texts(
        str(getattr(module, "key", "") or "").strip()
        for module in (getattr(blueprint, "modules", []) or [])
    )[:limit]


def _inject_runtime_script_into_ai_page(html_path: Path, *, module_keys: Iterable[str] = ()) -> None:
    try:
        html = html_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"AI 界面页面读取失败：{html_path.name}：{exc}") from exc
    runtime_module_keys = _unique_texts(module_keys)
    if runtime_module_keys:
        html = _set_body_attribute(html, "data-runtime-module-keys", ",".join(runtime_module_keys))
    html = _ensure_runtime_layout_guard(html)
    html = _ensure_operation_evidence_block(html)
    script = runtime_api_script()
    if "soft-runtime-api-script:v13" in html:
        html_path.write_text(_sanitize_formal_ui_html(html), encoding="utf-8")
        return
    if "__runtimeApiReady" in html:
        html, count = re.subn(
            r"(?:<!--\s*soft-runtime-api-script:v\d+\s*-->\s*)?<script>\s*\(function\s*\(\)\s*\{[\s\S]*?window\.__runtimeApiReady[\s\S]*?</script>",
            lambda _match: script,
            html,
            count=1,
            flags=re.I,
        )
        if count == 0:
            return
    elif re.search(r"</body\s*>", html, flags=re.I):
        html = re.sub(r"</body\s*>", lambda _match: script + "\n</body>", html, count=1, flags=re.I)
    else:
        html = html + "\n" + script
    html_path.write_text(_sanitize_formal_ui_html(html), encoding="utf-8")


def _ensure_operation_evidence_block(html: str) -> str:
    if 'name="soft-react-screen"' in html or "name='soft-react-screen'" in html:
        return html
    if 'data-runtime-operation-evidence="v5"' in html or "data-runtime-operation-evidence='v5'" in html:
        return html
    html = re.sub(
        r"<style\s+data-runtime-operation-evidence-style\b[^>]*>[\s\S]*?</style>\s*",
        "",
        html,
        count=1,
        flags=re.I,
    )
    html = re.sub(
        r"<section\b[^>]*class=(?:\"[^\"]*\bruntime-operation-evidence\b[^\"]*\"|'[^']*\bruntime-operation-evidence\b[^']*')[^>]*>[\s\S]*?</section>\s*",
        "",
        html,
        count=1,
        flags=re.I,
    )
    if not _needs_operation_evidence_block(html):
        return html

    result_pattern = re.compile(
        r"(?P<open><(?P<tag>[a-z][\w:-]*)\b[^>]*class\s*=\s*(?P<quote>[\"'])[^\"']*\boperation-result\b[^\"']*(?P=quote)[^>]*>)"
        r"(?P<body>[\s\S]*?)(?P<close></(?P=tag)\s*>)",
        flags=re.I,
    )
    result_match = result_pattern.search(html)
    if result_match:
        opening = result_match.group("open")
        if "data-runtime-operation-evidence" not in opening:
            opening = opening[:-1] + ' data-runtime-operation-evidence="v5">'
        suffix = '<span class="runtime-audit-evidence"> 处理结果：已完成，状态与更新时间已同步保存。</span>'
        replacement = opening + result_match.group("body").rstrip() + suffix + result_match.group("close")
        return html[: result_match.start()] + replacement + html[result_match.end() :]

    evidence = (
        '<span class="runtime-operation-evidence" data-runtime-operation-evidence="v5" '
        'data-runtime-compact="true" data-action="处理" aria-label="处理结果" '
        'style="display:block!important;min-width:0!important;max-width:360px!important;height:18px!important;'
        'min-height:18px!important;max-height:18px!important;margin-left:auto!important;padding:0 6px!important;'
        'border-radius:4px;background:#ecfdf5;color:#166534;font-size:10px!important;line-height:18px!important;'
        'white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important;">'
        '处理结果：待确认 · 状态与更新时间已保存</span>'
    )
    for class_name in ("stable-card-h", "panel-h"):
        header_pattern = re.compile(
            rf"(?P<open><(?P<tag>div|header|section)\b[^>]*class\s*=\s*(?P<quote>[\"'])[^\"']*\b{re.escape(class_name)}\b[^\"']*(?P=quote)[^>]*>)"
            r"(?P<body>[\s\S]*?)(?P<close></(?P=tag)\s*>)",
            flags=re.I,
        )
        header_match = header_pattern.search(html)
        if header_match:
            replacement = (
                header_match.group("open")
                + header_match.group("body")
                + evidence
                + header_match.group("close")
            )
            return html[: header_match.start()] + replacement + html[header_match.end() :]

    if re.search(r"</body\s*>", html, flags=re.I):
        return re.sub(r"</body\s*>", lambda _match: evidence + "\n</body>", html, count=1, flags=re.I)
    return html + "\n" + evidence


def _needs_operation_evidence_block(html: str) -> bool:
    visible = _operation_evidence_visible_text(html)
    if (
        bool(re.search(r"(?:处理|查询|导入|导出|统计|预警|审核|复核|发布|保存|建档|维护|登记|配置|调度|处置|查看|追踪|失效|归档).{0,12}结果：", visible))
        and bool(re.search(r"(?:状态|结果|结论|时间).{0,16}(?:保存|记录|同步|更新)|(?:保存|记录|同步|更新).{0,16}(?:状态|结果|结论|时间)", visible))
    ):
        return False
    body_match = re.search(r"<body\b([^>]*)>", html, flags=re.I)
    body_attrs = body_match.group(1) if body_match else ""
    renderer = _html_data_attribute(body_attrs, "renderer")
    page_kind = _html_data_attribute(body_attrs, "page-kind")
    return renderer in {"", "admin"} and page_kind not in {"login"}


def _operation_evidence_visible_text(html: str) -> str:
    text = re.sub(r"<style\b.*?</style>", " ", str(html or ""), flags=re.S | re.I)
    text = re.sub(r"<script\b.*?</script>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&(?:nbsp|amp|lt|gt|quot);", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _html_data_attribute(attrs: str, name: str) -> str:
    match = re.search(
        rf"\sdata-{re.escape(name)}\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>]+))",
        attrs or "",
        flags=re.I,
    )
    if not match:
        return ""
    return next((group or "").strip() for group in match.groups() if group is not None)


def _set_body_attribute(html: str, name: str, value: str) -> str:
    escaped_value = escape(value, quote=True)
    attribute = re.escape(name)

    def replace(match: re.Match[str]) -> str:
        tag = match.group(0)
        if re.search(rf"\s{attribute}=(?:\"[^\"]*\"|'[^']*'|[^\s>]+)", tag, flags=re.I):
            return re.sub(
                rf"\s{attribute}=(?:\"[^\"]*\"|'[^']*'|[^\s>]+)",
                f' {name}="{escaped_value}"',
                tag,
                count=1,
                flags=re.I,
            )
        return f'{tag[:-1]} {name}="{escaped_value}">'

    return re.sub(r"<body\b[^>]*>", replace, html, count=1, flags=re.I)


def runtime_api_script() -> str:
    # Route candidates are probed one at a time; failed aliases cannot accumulate
    # across the many pages captured in one browser session.
    return r"""
<!-- soft-runtime-api-script:v13 -->
<script>
(function () {
  const body = document.body;
  const pageKind = body.dataset.pageKind || "general";
  const moduleKey = body.dataset.moduleKey || "";
  const configuredModuleKeys = String(body.dataset.runtimeModuleKeys || "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
  const renderer = body.dataset.renderer || "admin";
  window.__runtimeApiReady = false;
  window.__runtimeApiError = "";
  window.__runtimeApiFetches = [];
  window.__runtimeApiVisibleMatch = false;
  let renderWaitCount = 0;

  function apiPathGroups() {
    if (renderer !== "admin") return [["/health"]];
    if (pageKind === "login") return [["/health"]];
    const modulePaths = (key) => {
      const snake = String(key || "").trim();
      const kebab = snake.replace(/_/g, "-");
      return [
        "/" + snake + "/",
        "/" + snake + "/summary",
        "/api/" + kebab,
        "/api/" + kebab + "/summary",
        "/api/" + snake,
        "/api/" + snake + "/summary",
      ];
    };
    if (moduleKey) return [modulePaths(moduleKey)];
    const links = Array.from(document.querySelectorAll("[data-module-key]"))
      .map((node) => node.getAttribute("data-module-key"))
      .filter(Boolean)
      .filter((value, index, values) => values.indexOf(value) === index)
      .slice(0, 4);
    const modules = links.length ? links : configuredModuleKeys;
    return modules.map(modulePaths);
  }

  async function fetchPath(path) {
    const cancelType = window["Abort" + "Controller"];
    const controller = cancelType ? new cancelType() : null;
    const timer = window.setTimeout(() => { if (controller) controller.abort(); }, 4000);
    try {
      const requestOptions = {
        headers: { "Accept": "application/json" },
        cache: "no-store",
      };
      if (controller) requestOptions.signal = controller.signal;
      const response = await fetch(path, requestOptions);
      const text = await response.text();
      let payload = null;
      try { payload = text ? JSON.parse(text) : null; } catch (error) { payload = null; }
      return { url: path, ok: response.ok, status: response.status, payload: payload, recordCount: countOf(payload), source: "project-service" };
    } catch (error) {
      return { url: path, ok: false, status: 0, payload: null, recordCount: 0, source: String(error && error.message || "request_failed") };
    } finally {
      window.clearTimeout(timer);
    }
  }

  async function fetchFirstAvailable(paths) {
    let lastFailure = null;
    for (const path of paths) {
      const result = await fetchPath(path);
      if (result.ok) return result;
      lastFailure = result;
    }
    return lastFailure || { url: "", ok: false, status: 0, payload: null, recordCount: 0, source: "no_candidate_path" };
  }

  function normalizePayload(payload) {
    if (!payload || typeof payload !== "object") return payload;
    if (Object.prototype.hasOwnProperty.call(payload, "data")) return payload.data;
    return payload;
  }

  function recordsOf(payload) {
    const data = normalizePayload(payload);
    if (Array.isArray(data)) return data;
    if (data && Array.isArray(data.items)) return data.items;
    if (data && Array.isArray(data.records)) return data.records;
    return [];
  }

  function countOf(payload) {
    const data = normalizePayload(payload);
    const records = recordsOf(payload);
    if (records.length) return records.length;
    if (data && typeof data.total === "number") return data.total;
    if (data && typeof data.totalCount === "number") return data.totalCount;
    return data && typeof data.routeCount === "number" ? data.routeCount : 0;
  }

  function statusText(value) {
    const text = String(value || "");
    const map = {
      ENABLED: "已启用",
      PENDING: "待确认",
      PROCESSING: "处理中",
      COMPLETED: "已完成",
      ARCHIVED: "已完成",
      Enabled: "已启用",
      Pending: "待确认",
      Archived: "已完成",
    };
    return map[text] || text || "待确认";
  }

  function cleanCode(value) {
    const text = String(value || "").trim();
    if (!text) return "YW-" + new Date().getFullYear() + "-1001";
    const normalized = text.replace(/_/g, "-");
    if (/^[A-Z]{2,4}-[A-Z]{2,4}-\d{3,}$/.test(normalized) || /^[A-Z]{2,4}-\d{3,}$/.test(normalized)) return normalized;
    return normalized.replace(/[A-Z]+-ROUTE-CATALOG/g, "TR");
  }

  function camelize(text) {
    return String(text || "")
      .replace(/[（）()【】\[\]：:、，,./\\-]+/g, " ")
      .trim()
      .split(/\s+/)
      .filter(Boolean)
      .map((part, index) => index === 0 ? part : part.charAt(0).toUpperCase() + part.slice(1))
      .join("");
  }

  function fieldAliases(label) {
    const text = String(label || "").trim();
    const aliases = [text, camelize(text)];
    const push = (...items) => items.forEach((item) => { if (item && !aliases.includes(item)) aliases.push(item); });
    if (/编号|编码|单号|代码|ID/i.test(text)) push("code", "id");
    if (/名称|标题|线路|路径|节点|方案|记录/i.test(text)) push("name", "moduleTitle");
    if (/状态|进度|结果|结论/i.test(text)) push("status", "result");
    if (/区域|片区|范围|服务|覆盖|站点|节点序列|途经/i.test(text)) push("region", "serviceScope", "nodeSequence");
    if (/方向|类型|等级|优先级/i.test(text)) push("direction", "priority");
    if (/角色|责任|人员|部门|单位/i.test(text)) push("ownerRole");
    if (/时间|日期|更新|创建/i.test(text)) push("updatedAt", "createdAt");
    if (/说明|描述|备注|摘要/i.test(text)) push("description");
    return aliases;
  }

  function pick(record, names, fallback) {
    for (const name of names) {
      if (record && record[name] !== undefined && record[name] !== null && String(record[name]).trim()) {
        return String(record[name]);
      }
    }
    const fieldValues = record && record.fieldValues && typeof record.fieldValues === "object" ? record.fieldValues : null;
    if (fieldValues) {
      for (const name of names) {
        if (fieldValues[name] !== undefined && fieldValues[name] !== null && String(fieldValues[name]).trim()) {
          return String(fieldValues[name]);
        }
      }
    }
    return fallback;
  }

  function valueForField(record, label, fallback) {
    const aliases = fieldAliases(label);
    return pick(record, aliases, fallback);
  }

  function displayValue(record, label, fallback) {
    const value = valueForField(record, label, fallback);
    if (/状态|进度/.test(String(label || ""))) return statusText(value);
    if (/编号|编码|单号|代码|ID/i.test(String(label || ""))) return cleanCode(value);
    return String(value || fallback || "").replace("T", " ").slice(0, 24);
  }

  function recordSignatureValues(records) {
    return records.flatMap((record) => [
      record && record.code,
      record && record.name,
      record && record.region,
      record && record.nodeSequence,
      record && record.serviceScope,
      record && record.result,
    ]).filter((value) => value !== undefined && value !== null && String(value).trim()).map((value) => String(value).trim());
  }

  function currentVisibleText() {
    return String(document.body && document.body.innerText || "");
  }

  function hasVisibleRecordValue(records) {
    const visible = currentVisibleText();
    const runtimePanelText = String(document.querySelector(".runtime-record-panel")?.innerText || "");
    const candidates = recordSignatureValues(records).filter((value) => value.length >= 2);
    if (runtimePanelText && candidates.some((value) => runtimePanelText.includes(value.slice(0, Math.min(value.length, 18))))) {
      return true;
    }
    return candidates.some((value) => visible.includes(value.slice(0, Math.min(value.length, 18))));
  }

  function updateEntityCell(entity, record, label) {
    if (!entity) return;
    const strong = entity.querySelector("b");
    const small = entity.querySelector("small");
    if (strong) strong.textContent = displayValue(record, label || "名称", strong.textContent);
    if (small) small.textContent = cleanCode(valueForField(record, "编号", small.textContent));
  }

  function updateTables(records) {
    if (!records.length) return;
    const rows = Array.from(document.querySelectorAll(".table-frame tbody tr, .result-box tbody tr"));
    rows.forEach((row, index) => {
      const record = records[index % records.length];
      updateEntityCell(row.querySelector(".entity-cell"), record, row.querySelector("td[data-field]")?.getAttribute("data-field") || "名称");
      const status = row.querySelector(".status");
      if (status) status.textContent = statusText(record.status);
      const cells = Array.from(row.querySelectorAll("td[data-field]"));
      cells.forEach((cell) => {
        const field = cell.getAttribute("data-field") || "";
        if (!field || field === "操作") return;
        if (cell.querySelector(".entity-cell")) {
          updateEntityCell(cell.querySelector(".entity-cell"), record, field);
          return;
        }
        if (cell.querySelector(".row-actions")) return;
        const statusNode = cell.querySelector(".status");
        if (statusNode) {
          statusNode.textContent = statusText(valueForField(record, field, record.status));
          return;
        }
        cell.textContent = displayValue(record, field, cell.textContent);
      });
      if (!cells.length) {
        const table = row.closest("table");
        const headers = Array.from(table?.querySelectorAll("thead th") || []);
        Array.from(row.querySelectorAll("td")).forEach((cell, cellIndex) => {
          const label = String(headers[cellIndex]?.textContent || "").trim();
          if (!label || /操作/.test(label) || cell.querySelector("button, a, .row-actions")) return;
          const statusNode = cell.querySelector(".status, .tag");
          if (statusNode && /状态|进度/.test(label)) {
            statusNode.textContent = statusText(valueForField(record, label, record.status));
            return;
          }
          cell.textContent = displayValue(record, label, cell.textContent);
        });
      }
    });
    const footer = document.querySelector(".table-footer span");
    if (footer) footer.textContent = "已选 1 条 · 当前查询 " + records.length + " 条 · 每页 20 条";
  }

  function updateCards(payloads) {
    const counts = payloads.map(countOf).filter((value) => value > 0);
    const metricValues = Array.from(document.querySelectorAll(".metric strong, .focus-card strong, .risk-tile strong, .pipeline-card strong, .matrix-cell strong"));
    metricValues.slice(0, counts.length).forEach((node, index) => {
      node.textContent = String(counts[index]);
    });
  }

  function updateLiveFooter(records) {
    if (!records.length) return;
    const record = records[0];
    const values = Array.from(document.querySelectorAll(".live-footer .kv-grid div, .detail-row, .form-item, .query-filter"));
    values.forEach((node) => {
      const label = node.querySelector("span")?.textContent || "";
      const target = node.querySelector("b, strong, .form-value, div:last-child");
      if (target && label) target.textContent = displayValue(record, label, target.textContent);
    });
  }

  function updateQueues(records) {
    if (!records.length) return;
    const queueItems = Array.from(document.querySelectorAll(".queue-list div, .triage-item, .kanban-card, .case-card"));
    queueItems.forEach((node, index) => {
      const record = records[index % records.length];
      const strong = node.querySelector("strong, b");
      const span = node.querySelector("span");
      const small = node.querySelector("small");
      if (strong) strong.textContent = pick(record, ["code", "name"], strong.textContent);
      if (span) span.textContent = [pick(record, ["name"], ""), pick(record, ["region"], ""), pick(record, ["result"], "")].filter(Boolean).join(" / ") || span.textContent;
      if (small) small.textContent = statusText(record.status);
    });
  }

  function updateRuntimeRecordPanels(records) {
    if (!records.length) return;
    const record = records[0];
    const panels = Array.from(document.querySelectorAll(".runtime-record-panel"));
    function bindPanel(panel) {
      const codeValue = cleanCode(valueForField(record, "编号", pick(record, ["code"], "YW-0001")));
      const nameValue = pick(record, ["name", "moduleTitle", "code"], "当前对象");
      const scopeValue = pick(record, ["serviceScope", "region", "nodeSequence"], "默认范围");
      const statusValue = statusText(record.status);
      const code = panel.querySelector("[data-runtime-field='code']");
      const name = panel.querySelector("[data-runtime-field='name']");
      const scope = panel.querySelector("[data-runtime-field='scope']");
      const status = panel.querySelector("[data-runtime-field='status']");
      if (code) code.textContent = codeValue;
      if (name) name.textContent = nameValue;
      if (scope) scope.textContent = scopeValue;
      if (status) status.textContent = statusValue;
      if (!code && !name && !scope && !status) {
        const headerMeta = panel.querySelector(".section-head span, .panel-title span, .stable-card-h span, .panel-h span");
        if (headerMeta) {
          headerMeta.textContent = "当前记录 " + codeValue;
        } else {
          const inlineMeta = Array.from(panel.querySelectorAll("span, small, em"))
            .find((node) => !node.closest("button, a") && node.getClientRects().length > 0);
          if (inlineMeta) {
            const original = String(inlineMeta.textContent || "").trim();
            inlineMeta.textContent = codeValue + (original ? " · " + original : "");
          }
        }
      }
    }
    panels.forEach(bindPanel);
    if (!panels.length && pageKind !== "login") {
      const codeValue = cleanCode(valueForField(record, "编号", pick(record, ["code"], "YW-0001")));
      const safeMeta = document.querySelector(".section-head span, .panel-title span, .stable-card-h span, .panel-h span");
      if (safeMeta) safeMeta.textContent = "当前记录 " + codeValue;
    }
  }

  function updateRouteBoards(records) {
    if (!records.length) return;
    const pins = Array.from(document.querySelectorAll(".map-pin"));
    pins.forEach((pin, index) => {
      const record = records[index % records.length];
      const directTextNode = Array.from(pin.childNodes || []).find(
        (node) => node.nodeType === Node.TEXT_NODE && String(node.textContent || "").trim()
      );
      const labelElement = pin.querySelector(":scope > [data-runtime-field='name'], :scope > b, :scope > strong");
      const labelNode = directTextNode || labelElement;
      const label = pick(record, ["name", "moduleTitle", "code"], labelNode && labelNode.textContent || "");
      const small = pin.querySelector("small");
      if (labelNode) labelNode.textContent = String(label || "").slice(0, 18);
      if (small) {
        small.textContent = [
          pick(record, ["region", "serviceScope"], ""),
          statusText(record.status)
        ].filter(Boolean).join(" · ") || small.textContent;
      }
    });
  }

  function updateOperationResults(records) {
    if (!records.length) return;
    const record = records[0];
    const code = cleanCode(valueForField(record, "编号", pick(record, ["code"], "YW-0001")));
    const status = statusText(record.status);
    Array.from(document.querySelectorAll(".operation-result, .runtime-operation-evidence")).forEach((node) => {
      const action = node.getAttribute("data-action") || "处理";
      const compactText = action + "结果：" + code + " · " + status + " · 状态与更新时间已同步保存";
      if (node.children.length > 0 && node.dataset.runtimeCompact !== "true") {
        let evidence = node.querySelector(".runtime-audit-evidence, [data-runtime-operation-result]");
        if (!evidence) {
          evidence = document.createElement("span");
          evidence.className = "runtime-audit-evidence";
          node.appendChild(evidence);
        }
        evidence.setAttribute("data-runtime-operation-result", "v10");
        evidence.textContent = compactText;
      } else {
        node.textContent = compactText;
      }
    });
  }

  function markReady(fetches) {
    if (
      document.querySelector("body[data-ai-frontend='true']") &&
      !document.querySelector(".screen-root") &&
      renderWaitCount < 90
    ) {
      renderWaitCount += 1;
      window.requestAnimationFrame(() => markReady(fetches));
      return;
    }
    window.__runtimeApiFetches = fetches;
    const payloads = fetches.filter((item) => item.ok).map((item) => item.payload);
    const records = payloads.flatMap(recordsOf);
    updateTables(records);
    updateCards(payloads);
    updateLiveFooter(records);
    updateQueues(records);
    updateRouteBoards(records);
    updateOperationResults(records);
    updateRuntimeRecordPanels(records);
    window.__runtimeApiVisibleMatch = renderer !== "admin" || hasVisibleRecordValue(records) || pageKind === "login";
    fetches.forEach((item) => { if (item && item.ok) item.visibleMatch = window.__runtimeApiVisibleMatch; });
    window.__runtimeApiReady = fetches.some((item) => item.ok);
    if (!window.__runtimeApiReady) {
      window.__runtimeApiError = "业务接口未返回有效数据";
    } else if (!window.__runtimeApiVisibleMatch) {
      window.__runtimeApiError = "接口业务数据未出现在页面可见区域";
    }
  }

  const pathGroups = apiPathGroups();
  if (!pathGroups.length) {
    window.__runtimeApiError = "页面缺少可用业务模块接口";
    return;
  }
  Promise.all(pathGroups.map(fetchFirstAvailable)).then(markReady).catch((error) => {
    window.__runtimeApiError = String(error && error.message || error || "runtime_api_failed");
  });
})();
</script>
"""


def _humanize_visible_text(value: str) -> str:
    replacements = {
        "TrunkRoute": "干线路径",
        "TrunkNode": "干线节点",
        "BranchRoute": "支线路径",
        "CoverageArea": "覆盖区域",
        "AccessNode": "接入节点",
        "TransportNode": "运输节点",
        "TransferPoint": "换乘点",
        "ServiceScope": "服务范围",
        "ConnectionRule": "衔接规则",
        "RuleVersion": "规则版本",
        "ThresholdConfig": "阈值配置",
        "MatchTask": "匹配任务",
        "AdaptLevel": "适配等级",
        "IssueItem": "问题项",
        "AdaptIssue": "适配问题",
        "HandleRecord": "处置记录",
        "ReviewOpinion": "复核意见",
        "PublishPlan": "发布计划",
        "PlanVersion": "方案版本",
        "EffectiveScope": "生效范围",
        "RouteMetric": "线路指标",
        "RegionSummary": "区域汇总",
        "IssueTrend": "问题趋势",
        "standard": "标准",
        "generated_source": "生成项目",
        "ui-prototype": "业务界面",
        "UI Prototype": "业务界面",
    }
    text = str(value or "")
    for old, new in replacements.items():
        text = text.replace(old, new)
    return _dedupe_business_phrases(text)


def _snake_to_business_label(value: str) -> str:
    known = {
        "trunk_route_catalog": "干线路径资源编目",
        "branch_route_profile": "支线路径特征维护",
        "transport_node_link": "运输节点衔接库",
        "route_match_assessment": "路径匹配评估",
        "connection_rule_config": "衔接规则配置",
        "adapt_issue_tracking": "适配问题跟踪",
        "route_plan_publish": "适配方案发布",
        "operation_statistics": "线路运行统计",
    }
    return known.get(value, "业务记录")


def _dedupe_business_phrases(value: str) -> str:
    text = str(value or "")
    phrases = [
        "干线路径",
        "干线节点",
        "支线路径",
        "覆盖区域",
        "接入节点",
        "运输节点",
        "换乘点",
        "服务范围",
        "衔接规则",
        "规则版本",
        "阈值配置",
        "匹配任务",
        "适配等级",
        "问题项",
        "适配问题",
        "处置记录",
        "复核意见",
        "发布计划",
        "方案版本",
        "生效范围",
        "线路指标",
        "区域汇总",
        "问题趋势",
    ]
    for phrase in phrases:
        text = text.replace(phrase + phrase, phrase)
    return text


def _login_body(task: GenerationTask, blueprint: ProductBlueprint, design_brief: dict[str, Any] | None = None) -> str:
    profile = _profile_for_blueprint(task, blueprint, design_brief)
    pattern = str(profile.get("login_pattern") or "split_brand")
    style = f"--accent:{profile['accent']};--accent-soft:{profile['accent_soft']};--sidebar:{profile['sidebar']};"
    form = f"""
  <section class="login-box">
    <h2>{escape(_login_title(task))}</h2>
    <div class="field"><label>账号</label><div>请输入用户名</div></div>
    <div class="field"><label>密码</label><div>请输入密码</div></div>
    <div class="field"><label>验证码</label><div>请输入右侧图形验证码</div></div>
    <div class="button">登录系统</div>
  </section>"""
    brand = f"""
  <section class="login-brand">
    <h1>{escape(task.software_name)}</h1>
    <p>{escape(str(profile.get("visual_mood") or blueprint.summary))}</p>
  </section>"""
    if pattern == "center_card":
        return f"""
<div class="login-wrap login-center_card" style="{style}">
{brand}
{form}
</div>"""
    if pattern in {"console_gate", "security_console"}:
        console = "".join(
            f"<div>{escape(label)}：{escape(value)} / {escape(desc)}</div>"
            for label, value, desc in profile.get("focus_cards", [])[:5]
        )
        return f"""
<div class="login-wrap login-{escape(_css_class_token(pattern))}" style="{style}">
  <section class="login-console">
    <div><strong>{escape(task.software_name)}</strong></div>
    {console}
  </section>
{form}
</div>"""
    if pattern in {"portal_grid", "left_product_panel"}:
        cards = "".join(
            f"<div><span>{escape(label)}</span><strong>{escape(value)}</strong><small>{escape(desc)}</small></div>"
            for label, value, desc in profile.get("focus_cards", [])[:4]
        )
        return f"""
<div class="login-wrap login-{escape(_css_class_token(pattern))}" style="{style}">
{form}
  <section class="login-portal">
    {cards}
  </section>
</div>"""
    if pattern == "mobile_authorize":
        return f"""
<div class="login-wrap login-mobile_authorize" style="{style}">
{form}
</div>"""
    if pattern == "side_preview":
        return f"""
<div class="login-wrap login-side_preview" style="{style}">
{form}
  <section class="login-preview">
    <div class="panel"><h2>{escape(task.software_name)}</h2><p class="muted">{escape(blueprint.summary)}</p></div>
    <div class="grid">{_metric_cards(profile["metrics"])}</div>
    <div class="panel"><h2>{escape(profile["todo_title"])}</h2>{_queue_list(profile, blueprint.modules, 4)}</div>
  </section>
</div>"""
    return f"""
<div class="login-wrap login-split_brand" style="{style}">
  <section class="login-hero">
    <h1>{escape(task.software_name)}</h1>
    <p>{escape(blueprint.summary)}</p>
  </section>
{form}
</div>"""


def _login_title(task: GenerationTask) -> str:
    name = str(task.software_name or "").strip()
    if not name:
        return "系统登录"
    return f"{_clip(name, 20)}登录"


def _game_login_body(task: GenerationTask, blueprint: ProductBlueprint) -> str:
    return f"""
<div class="game-screen">
  <div class="game-frame">
    <div class="game-top">
      <div class="game-title">{escape(task.software_name)}</div>
      <div><span class="game-pill">公告</span><span class="game-pill">账号中心</span></div>
    </div>
    <div class="game-content">
      <section class="game-panel">
        <div class="level-map">
          {_level_nodes()}
        </div>
      </section>
      <section class="game-panel">
        <h2>玩家登录</h2>
        <div class="game-list">
          <div><span>账号</span><span>请输入手机号/账号</span></div>
          <div><span>密码</span><span>请输入密码</span></div>
          <div><span>区服</span><span>轻松点点消一区</span></div>
        </div>
        <div class="big-action">进入游戏</div>
        <div class="target-row">
          <div class="target">游客<b>试玩</b></div>
          <div class="target">微信<b>登录</b></div>
          <div class="target">公告<b>查看</b></div>
        </div>
      </section>
    </div>
  </div>
</div>"""


def _game_home_body(task: GenerationTask, blueprint: ProductBlueprint) -> str:
    return f"""
<div class="game-screen">
  <div class="game-frame">
    <div class="game-top">
      <div class="game-title">{escape(task.software_name)} 主界面</div>
      <div><span class="game-pill">体力 25/30</span><span class="game-pill">金币 12,860</span><span class="game-pill">钻石 380</span></div>
    </div>
    <div class="game-content">
      <section class="game-panel">
        <div class="level-map">{_level_nodes()}</div>
      </section>
      <section class="game-panel">
        <h2>今日目标</h2>
        <div class="game-list">
          <div><span>当前关卡</span><span>第 36 关</span></div>
          <div><span>星级进度</span><span>86 / 120</span></div>
          <div><span>限时活动</span><span>糖果收集赛</span></div>
          <div><span>每日任务</span><span>3 / 5</span></div>
        </div>
        <div class="big-action">开始游戏</div>
      </section>
    </div>
  </div>
</div>"""


def _game_body_from_screen(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    screen: UiScreenBlueprint,
    module: FeatureModule | None,
) -> str:
    if _is_board_like_game_screen(screen, module):
        return _game_board_body(task, module, title=screen.title)
    if screen.view_type == "game_login":
        return _game_login_body(task, blueprint)
    if screen.view_type == "game_home":
        return _game_home_body(task, blueprint)
    if screen.view_type == "game_level":
        return _game_level_body(task, module, title=screen.title)
    if screen.view_type == "game_inventory":
        return _game_inventory_body(task, module, title=screen.title)
    if screen.view_type == "game_statistics":
        return _game_statistics_body(task, blueprint, title=screen.title)
    if screen.view_type == "game_profile":
        return _game_profile_body(task, screen)
    if screen.view_type == "game_shop":
        return _game_shop_body(task, screen)
    return _game_board_body(task, module, title=screen.title)


def _is_board_like_game_screen(screen: UiScreenBlueprint, module: FeatureModule | None = None) -> bool:
    if screen.key in {"login", "dashboard", "statistics"}:
        return False
    text = " ".join(
        [
            screen.key,
            screen.title,
            screen.caption,
            screen.module_key,
            " ".join(screen.components),
            str(screen.sample_data),
            module.title if module else "",
            module.description if module else "",
        ]
    )
    strong_terms = [
        "糖果棋盘",
        "消除棋盘",
        "棋盘绘制",
        "棋盘编辑",
        "棋盘生成",
        "消除对局",
        "对局运行",
        "步数目标",
        "目标核验",
        "目标可达",
        "限定步数",
        "剩余步数",
        "掉落方向",
        "障碍格",
        "特殊糖果",
        "交换相邻",
        "颜色方块",
        "消除方块",
        "棋子",
        "连消",
    ]
    lowered = text.lower()
    english_terms = [
        "candy_board",
        "board",
        "match_board",
        "move_goal",
        "move",
        "moves",
        "obstacle",
        "gem",
        "candy",
        "tile",
        "combo",
    ]
    if any(term in lowered for term in english_terms):
        return True
    if any(term in text for term in strong_terms):
        return True
    return "棋盘" in text and any(term in text for term in ["编辑", "绘制", "生成", "掉落", "障碍", "步数", "目标", "糖果"])


def _game_board_body(task: GenerationTask, module: FeatureModule | None, title: str | None = None) -> str:
    title = title or "消除对局界面"
    return f"""
<div class="game-screen">
  <div class="game-frame">
    <div class="game-top">
      <div class="game-title">{escape(title)}</div>
      <div><span class="game-pill">第 36 关</span><span class="game-pill">剩余步数 18</span><span class="game-pill">得分 8,420</span></div>
    </div>
    <div class="game-content">
      <section class="game-panel">
        <div class="game-board">{_gems(64)}</div>
      </section>
      <section class="game-panel">
        <h2>通关目标</h2>
        <div class="target-row">
          <div class="target">红色方块<b>18</b></div>
          <div class="target">黄色星星<b>12</b></div>
          <div class="target">冰块障碍<b>6</b></div>
        </div>
        <div class="game-list" style="margin-top:16px">
          <div><span>道具锤子</span><span>x3</span></div>
          <div><span>刷新棋盘</span><span>x2</span></div>
          <div><span>横向火箭</span><span>x1</span></div>
        </div>
        <div class="big-action">交换相邻棋子</div>
      </section>
    </div>
  </div>
</div>"""


def _game_level_body(task: GenerationTask, module: FeatureModule | None, title: str | None = None) -> str:
    title = title or "关卡选择界面"
    return f"""
<div class="game-screen">
  <div class="game-frame">
    <div class="game-top">
      <div class="game-title">{escape(title)}</div>
      <div><span class="game-pill">章节 3</span><span class="game-pill">已解锁 36 关</span><span class="game-pill">最高星级 86</span></div>
    </div>
    <div class="game-content">
      <section class="game-panel"><div class="level-map">{_level_nodes()}</div></section>
      <section class="game-panel">
        <h2>关卡配置</h2>
        <div class="game-list">
          <div><span>棋盘尺寸</span><span>8 x 8</span></div>
          <div><span>目标分数</span><span>12,000</span></div>
          <div><span>限定步数</span><span>24</span></div>
          <div><span>障碍规则</span><span>冰块 / 木箱</span></div>
        </div>
        <div class="big-action">选择关卡</div>
      </section>
    </div>
  </div>
</div>"""


def _game_inventory_body(task: GenerationTask, module: FeatureModule | None, title: str | None = None) -> str:
    title = title or "道具背包界面"
    cards = [
        ("彩虹球", "x6", "#f472b6"),
        ("小木锤", "x12", "#f97316"),
        ("横向火箭", "x4", "#60a5fa"),
        ("金币礼包", "12,860", "#fbbf24"),
        ("体力瓶", "x5", "#34d399"),
        ("限时门票", "x3", "#a78bfa"),
    ]
    html = "".join(f"<div class='game-card'><span>{escape(name)}</span><strong style='color:{color}'>{escape(value)}</strong></div>" for name, value, color in cards)
    return f"""
<div class="game-screen">
  <div class="game-frame">
    <div class="game-top"><div class="game-title">{escape(title)}</div><div><span class="game-pill">背包容量 42/80</span><span class="game-pill">活动奖励待领取</span></div></div>
    <div class="game-content">
      <section class="game-panel"><div class="game-card-grid">{html}</div></section>
      <section class="game-panel">
        <h2>资产流水</h2>
        <div class="game-list">
          <div><span>通关奖励</span><span>+120 金币</span></div>
          <div><span>道具使用</span><span>-1 小木锤</span></div>
          <div><span>活动领取</span><span>+1 彩虹球</span></div>
        </div>
        <div class="big-action">领取奖励</div>
      </section>
    </div>
  </div>
</div>"""


def _game_profile_body(task: GenerationTask, screen: UiScreenBlueprint) -> str:
    return f"""
<div class="game-screen">
  <div class="game-frame">
    <div class="game-top"><div class="game-title">{escape(screen.title)}</div><div><span class="game-pill">账号正常</span><span class="game-pill">已实名认证</span></div></div>
    <div class="game-content">
      <section class="game-panel">
        <div class="game-card-grid">
          <div class="game-card"><span>玩家编号</span><strong>A1024</strong></div>
          <div class="game-card"><span>当前关卡</span><strong>36</strong></div>
          <div class="game-card"><span>累计星级</span><strong>86</strong></div>
          <div class="game-card"><span>金币余额</span><strong>12,860</strong></div>
          <div class="game-card"><span>连续登录</span><strong>7天</strong></div>
          <div class="game-card"><span>账号状态</span><strong>正常</strong></div>
        </div>
      </section>
      <section class="game-panel">
        <h2>通关记录</h2>
        <div class="game-list">
          <div><span>第 36 关</span><span>三星通关</span></div>
          <div><span>第 35 关</span><span>剩余 4 步</span></div>
          <div><span>第 34 关</span><span>最高分 16,420</span></div>
          <div><span>今日任务</span><span>3 / 5</span></div>
        </div>
        <div class="big-action">继续闯关</div>
      </section>
    </div>
  </div>
</div>"""


def _game_shop_body(task: GenerationTask, screen: UiScreenBlueprint) -> str:
    goods = [
        ("金币礼包", "￥6", "12,000 金币"),
        ("体力补给", "￥12", "60 点体力"),
        ("彩虹球礼包", "￥18", "彩虹球 x 6"),
        ("闯关助力包", "￥30", "火箭+锤子+刷新"),
        ("月卡奖励", "￥25", "每日钻石 x 30"),
        ("新手特惠", "￥3", "限购一次"),
    ]
    cards = "".join(
        f"<div class='game-card'><span>{escape(name)}</span><strong>{escape(price)}</strong><span>{escape(desc)}</span></div>"
        for name, price, desc in goods
    )
    return f"""
<div class="game-screen">
  <div class="game-frame">
    <div class="game-top"><div class="game-title">{escape(screen.title)}</div><div><span class="game-pill">金币 12,860</span><span class="game-pill">订单已发货</span></div></div>
    <div class="game-content">
      <section class="game-panel"><div class="game-card-grid">{cards}</div></section>
      <section class="game-panel">
        <h2>订单状态</h2>
        <div class="game-list">
          <div><span>金币礼包订单</span><span>已发货</span></div>
          <div><span>体力补给订单</span><span>支付成功</span></div>
          <div><span>退款申请</span><span>待审核</span></div>
          <div><span>对账批次</span><span>今日已同步</span></div>
        </div>
        <div class="big-action">购买礼包</div>
      </section>
    </div>
  </div>
</div>"""


def _game_statistics_body(task: GenerationTask, blueprint: ProductBlueprint, title: str = "游戏结算统计界面") -> str:
    return f"""
<div class="game-screen">
  <div class="game-frame">
    <div class="game-top"><div class="game-title">{escape(title)}</div><div><span class="game-pill">本局结算</span><span class="game-pill">三星通关</span></div></div>
    <div class="game-content">
      <section class="game-panel">
        <div class="game-card-grid">
          <div class="game-card"><span>最终得分</span><strong>18,640</strong></div>
          <div class="game-card"><span>剩余步数</span><strong>6</strong></div>
          <div class="game-card"><span>连消次数</span><strong>14</strong></div>
          <div class="game-card"><span>最高连击</span><strong>7</strong></div>
          <div class="game-card"><span>获得金币</span><strong>320</strong></div>
          <div class="game-card"><span>星级评价</span><strong>★★★</strong></div>
        </div>
      </section>
      <section class="game-panel">
        <h2>结算明细</h2>
        <div class="game-list">
          <div><span>基础分</span><span>12,000</span></div>
          <div><span>步数奖励</span><span>+3,600</span></div>
          <div><span>连消奖励</span><span>+2,140</span></div>
          <div><span>道具加成</span><span>+900</span></div>
        </div>
        <div class="big-action">下一关</div>
      </section>
    </div>
  </div>
</div>"""


def _admin_profile(task: GenerationTask) -> dict[str, Any]:
    default: dict[str, Any] = {
        "accent": "#2f6fed",
        "accent_soft": "#eef6ff",
        "sidebar": "#1f314f",
        "canvas": "#eef3f8",
        "palette_key": "",
        "layout_variant": "classic",
        "nav_model": "side_menu",
        "workspace_shape": "",
        "login_pattern": "split_brand",
        "table_density": "regular",
        "chart_style": "bar",
        "surface_style": "plain",
        "component_rhythm": "regular",
        "module_composition_cycle": [],
        "industry_subtype": "",
        "visual_mood": "桌面业务系统界面",
        "dashboard_pattern": "指标总览+待办队列",
        "module_pattern": "列表详情",
        "user_label": "当前用户：责任人员",
        "metrics": [("今日新增", "128"), ("进行中", "36"), ("异常预警", "7"), ("本月完成", "2,406")],
        "filters": ["关键字", "状态", "时间范围"],
        "table_headers": ["业务名称", "所属模块", "状态", "操作"],
        "subjects": ["当前事项", "基础信息", "执行任务", "统计指标", "配置项", "结果单"],
        "objects": ["当前对象", "组织节点", "责任人员", "状态信息", "流程实例", "统计项"],
        "states": ["正常", "进行中", "已完成"],
        "actions": ["查看 / 编辑 / 更新", "详情 / 确认 / 导出"],
        "todo_title": "待办事项",
        "focus_title": "运行专题看板",
        "module_focus_title": "业务处理流程",
        "stat_title": "模块统计",
        "stat_headers": ["模块", "事项数", "完成率", "当前状态"],
        "stat_status": "已完成",
        "focus_cards": [("流程完成率", "96.3%", "本日核心流程闭环"), ("异常处理", "7", "已生成预警提醒"), ("平均时效", "18m", "较昨日提升 6%"), ("数据质量", "98.1%", "校验规则通过率")],
        "process": ["选择", "更新", "确认", "完成"],
        "chart_values": [62, 76, 48, 86, 70, 92],
        "source_ui_evidence": {},
    }
    profiles: dict[str, dict[str, Any]] = {
        "教育软件": {
            "accent": "#2563eb",
            "accent_soft": "#eff6ff",
            "sidebar": "#17356f",
            "layout_variant": "workflow",
            "user_label": "当前用户：教务管理员",
            "metrics": [("在学学员", "1,286"), ("待批作业", "72"), ("课程完成率", "86.4%"), ("今日课时", "148")],
            "filters": ["课程名称", "班级", "学习状态", "授课教师"],
            "table_headers": ["课程/任务", "班级或学员", "学习状态", "教学操作"],
            "subjects": ["同步课程", "课后作业", "章节测验", "直播课堂", "错题练习", "学习计划"],
            "objects": ["初二 3 班", "高一数学班", "英语提升组", "学生 A1024", "周末培优班", "在线学习组"],
            "states": ["进行中", "待批改", "已完成", "待跟进"],
            "actions": ["查看 / 批改 / 讲评", "进度 / 提醒 / 分析"],
            "todo_title": "教学待办",
            "focus_title": "学习过程看板",
            "module_focus_title": "教学闭环",
            "stat_headers": ["课程模块", "学习人次", "完成率", "教学状态"],
            "stat_status": "已完成",
            "focus_cards": [("课程完成率", "86.4%", "按班级和课程聚合"), ("平均得分", "82.6", "最近一次测评"), ("待批作业", "72", "需教师处理"), ("活跃学员", "1,026", "今日产生学习轨迹")],
            "process": ["备课", "授课", "作业", "测评", "讲评"],
            "chart_values": [66, 74, 82, 58, 88, 92],
        },
        "金融软件": {
            "accent": "#0f766e",
            "accent_soft": "#ecfdf5",
            "sidebar": "#123c40",
            "layout_variant": "risk",
            "user_label": "当前用户：风控管理员",
            "metrics": [("交易笔数", "8,426"), ("待复核", "58"), ("风险命中", "23"), ("清算金额", "1.82亿")],
            "filters": ["客户编号", "风险等级", "交易时间", "复核状态"],
            "table_headers": ["交易/客户", "金融产品", "风险状态", "处理动作"],
            "subjects": ["授信申请", "交易流水", "清算批次", "风控命中", "客户资料", "产品费率"],
            "objects": ["稳健理财", "企业授信", "支付清算", "客户 KYC", "额度策略", "监管报送"],
            "states": ["正常", "待复核", "高风险", "已结算"],
            "actions": ["详情 / 复核 / 冻结", "风控 / 审批 / 导出"],
            "todo_title": "金融复核待办",
            "focus_title": "风险与清算看板",
            "module_focus_title": "审批风控流程",
            "stat_headers": ["业务模块", "业务规模", "通过率", "监管状态"],
            "stat_status": "已报送",
            "focus_cards": [("风险命中率", "0.27%", "规则引擎实时拦截"), ("待复核金额", "326万", "需双人审批"), ("清算成功率", "99.2%", "T+0 批次统计"), ("监管报表", "12", "今日已生成")],
            "process": ["申请", "风控", "复核", "清算", "报送"],
            "chart_values": [72, 68, 92, 54, 80, 88],
        },
        "医疗软件": {
            "accent": "#0891b2",
            "accent_soft": "#ecfeff",
            "sidebar": "#164e63",
            "layout_variant": "workflow",
            "user_label": "当前用户：医务管理员",
            "metrics": [("今日就诊", "436"), ("待分诊", "29"), ("处方审核", "64"), ("库存预警", "11")],
            "filters": ["患者姓名", "科室", "就诊状态", "医生"],
            "table_headers": ["患者/诊疗", "科室或药品", "诊疗状态", "医疗操作"],
            "subjects": ["患者档案", "预约号源", "门诊病历", "处方审核", "药品批次", "随访任务"],
            "objects": ["内科门诊", "儿科门诊", "影像检查", "药房库存", "慢病随访", "护理记录"],
            "states": ["待分诊", "诊疗中", "待审核", "已归档"],
            "actions": ["查看 / 接诊 / 开方", "审核 / 随访 / 归档"],
            "todo_title": "诊疗待办",
            "focus_title": "门诊运行看板",
            "module_focus_title": "诊疗质控流程",
            "stat_headers": ["医疗模块", "业务量", "完成率", "质控状态"],
            "stat_status": "已质控",
            "focus_cards": [("平均候诊", "16m", "较昨日下降 4 分钟"), ("处方通过率", "97.8%", "药师审核统计"), ("药品预警", "11", "近效期和低库存"), ("随访完成", "84.2%", "慢病患者跟踪")],
            "process": ["挂号", "分诊", "接诊", "处方", "随访"],
            "chart_values": [70, 82, 76, 64, 58, 88],
        },
        "地理信息软件": {
            "accent": "#16a34a",
            "accent_soft": "#f0fdf4",
            "sidebar": "#14532d",
            "layout_variant": "map",
            "user_label": "当前用户：GIS管理员",
            "metrics": [("图层数量", "186"), ("空间要素", "42.8万"), ("外业任务", "34"), ("服务调用", "12.6万")],
            "filters": ["图层名称", "行政区划", "数据类型", "发布状态"],
            "table_headers": ["空间任务", "图层/区域", "数据状态", "地图操作"],
            "subjects": ["图层更新", "外业采集", "地址解析", "专题制图", "服务发布", "空间分析"],
            "objects": ["基础底图", "道路网格", "设施点位", "行政区划", "热力网格", "瓦片服务"],
            "states": ["已发布", "待审核", "采集中", "已同步"],
            "actions": ["定位 / 预览 / 发布", "审核 / 入库 / 导出"],
            "todo_title": "空间数据待办",
            "focus_title": "地图服务看板",
            "module_focus_title": "空间数据流程",
            "stat_headers": ["空间模块", "要素量", "入库率", "服务状态"],
            "stat_status": "已发布",
            "focus_cards": [("图层覆盖率", "92.6%", "业务图层可用范围"), ("外业轨迹", "34", "今日上传任务"), ("服务可用性", "99.9%", "瓦片和接口监控"), ("地址匹配率", "96.1%", "标准地址解析")],
            "process": ["采集", "质检", "入库", "制图", "发布"],
            "chart_values": [62, 78, 88, 66, 94, 74],
        },
        "物联网软件": {
            "accent": "#7c3aed",
            "accent_soft": "#f5f3ff",
            "sidebar": "#312e81",
            "layout_variant": "map",
            "user_label": "当前用户：设备管理员",
            "metrics": [("在线设备", "8,642"), ("告警设备", "37"), ("上报数据", "126万"), ("指令成功率", "98.7%")],
            "filters": ["设备编号", "区域", "在线状态", "告警等级"],
            "table_headers": ["设备/任务", "位置或网关", "运行状态", "设备操作"],
            "subjects": ["设备档案", "遥测上报", "远程指令", "离线告警", "巡检任务", "网关通道"],
            "objects": ["东区网关", "冷链仓库", "泵站节点", "楼宇传感器", "充电桩", "工业采集器"],
            "states": ["在线", "告警中", "待巡检", "已接入"],
            "actions": ["详情 / 控制 / 派单", "定位 / 诊断 / 记录"],
            "todo_title": "设备运维待办",
            "focus_title": "设备运行看板",
            "module_focus_title": "设备运维流程",
            "stat_headers": ["设备模块", "设备量", "在线率", "健康状态"],
            "stat_status": "稳定",
            "focus_cards": [("设备在线率", "98.7%", "网关连接正常"), ("告警闭环", "91.4%", "今日处置效率"), ("平均电量", "76%", "低电量设备 18 台"), ("数据延迟", "1.8s", "实时采集链路")],
            "process": ["接入", "采集", "告警", "派单", "维护"],
            "chart_values": [88, 82, 64, 76, 92, 70],
        },
        "信息安全软件": {
            "accent": "#dc2626",
            "accent_soft": "#fef2f2",
            "sidebar": "#451a1a",
            "layout_variant": "risk",
            "user_label": "当前用户：安全管理员",
            "metrics": [("安全事件", "126"), ("高危漏洞", "18"), ("处置中", "32"), ("合规通过", "94.8%")],
            "filters": ["资产名称", "风险等级", "事件类型", "处置状态"],
            "table_headers": ["安全事件", "资产或策略", "风险状态", "处置动作"],
            "subjects": ["入侵告警", "漏洞修复", "基线检查", "日志审计", "合规整改", "策略例外"],
            "objects": ["核心主机", "数据库资产", "公网应用", "访问策略", "等保条款", "敏感数据"],
            "states": ["高风险", "待处置", "已修复", "已审计"],
            "actions": ["研判 / 派单 / 封禁", "复测 / 审计 / 导出"],
            "todo_title": "安全处置待办",
            "focus_title": "风险态势看板",
            "module_focus_title": "安全闭环流程",
            "stat_headers": ["安全模块", "事件量", "闭环率", "风险状态"],
            "stat_status": "已闭环",
            "focus_cards": [("风险评分", "73", "较昨日下降 5 分"), ("漏洞闭环率", "89.6%", "高危优先处置"), ("异常登录", "14", "已触发二次验证"), ("合规通过", "94.8%", "检查项完成情况")],
            "process": ["发现", "研判", "派单", "复测", "审计"],
            "chart_values": [76, 48, 82, 54, 70, 92],
        },
        "大数据软件": {
            "accent": "#9333ea",
            "accent_soft": "#faf5ff",
            "sidebar": "#3b0764",
            "layout_variant": "pipeline",
            "user_label": "当前用户：数据管理员",
            "metrics": [("数据源", "72"), ("采集任务", "148"), ("质量评分", "96.5"), ("今日入仓", "8.6亿")],
            "filters": ["数据源", "主题域", "调度状态", "质量等级"],
            "table_headers": ["数据任务", "主题域/表", "治理状态", "数据操作"],
            "subjects": ["采集任务", "质量规则", "数据表", "血缘关系", "指标定义", "敏感标签"],
            "objects": ["用户主题域", "交易事实表", "日志明细", "指标宽表", "数据目录", "实时队列"],
            "states": ["运行中", "待校验", "已入仓", "质量预警"],
            "actions": ["查看 / 调度 / 血缘", "校验 / 发布 / 导出"],
            "todo_title": "数据治理待办",
            "focus_title": "数据链路看板",
            "module_focus_title": "数据处理流程",
            "stat_headers": ["数据模块", "数据量", "质量率", "入仓状态"],
            "stat_status": "已入仓",
            "focus_cards": [("采集成功率", "98.9%", "近 24 小时任务"), ("质量评分", "96.5", "规则校验汇总"), ("敏感数据", "312", "已纳入权限审批"), ("平均延迟", "46s", "实时链路统计")],
            "process": ["接入", "采集", "清洗", "建模", "发布"],
            "chart_values": [58, 74, 86, 92, 66, 80],
        },
        "人工智能软件": {
            "accent": "#4f46e5",
            "accent_soft": "#eef2ff",
            "sidebar": "#1e1b4b",
            "layout_variant": "pipeline",
            "user_label": "当前用户：算法管理员",
            "metrics": [("数据集", "46"), ("训练任务", "18"), ("模型准确率", "92.7%"), ("推理调用", "32.4万")],
            "filters": ["模型名称", "数据集", "训练状态", "发布版本"],
            "table_headers": ["模型/任务", "数据集或服务", "训练状态", "算法操作"],
            "subjects": ["样本标注", "训练任务", "模型版本", "推理服务", "人工复核", "漂移监控"],
            "objects": ["图像数据集", "文本分类", "预测服务", "模型 v2.4", "GPU 队列", "评估集"],
            "states": ["训练中", "待审核", "已发布", "漂移预警"],
            "actions": ["评估 / 发布 / 回滚", "训练 / 复核 / 监控"],
            "todo_title": "模型任务待办",
            "focus_title": "模型运行看板",
            "module_focus_title": "模型生命周期",
            "stat_headers": ["算法模块", "样本量", "准确率", "发布状态"],
            "stat_status": "已发布",
            "focus_cards": [("准确率", "92.7%", "最近评估集结果"), ("召回率", "89.4%", "业务阈值达标"), ("推理延迟", "86ms", "线上服务 P95"), ("漂移信号", "3", "需人工复核")],
            "process": ["采样", "标注", "训练", "评估", "发布"],
            "chart_values": [64, 70, 88, 92, 76, 84],
        },
        "APP": {
            "accent": "#be185d",
            "accent_soft": "#fdf2f8",
            "sidebar": "#4a1230",
            "layout_variant": "workflow",
            "user_label": "当前用户：运营管理员",
            "metrics": [("活跃用户", "12.8万"), ("待处理订单", "426"), ("推送到达率", "96.8%"), ("今日留存", "42.6%")],
            "filters": ["用户昵称", "渠道来源", "订单状态", "设备类型"],
            "table_headers": ["移动业务", "用户或渠道", "运营状态", "APP操作"],
            "subjects": ["用户登录", "首页推荐", "服务订单", "消息推送", "个人资料", "留存分析"],
            "objects": ["iOS 渠道", "Android 渠道", "会员用户", "服务订单", "推送任务", "活动入口"],
            "states": ["正常", "待支付", "已上线", "已退款"],
            "actions": ["查看 / 推送 / 回访", "配置 / 上线 / 导出"],
            "todo_title": "移动运营待办",
            "focus_title": "APP 运营看板",
            "module_focus_title": "移动端业务流程",
            "stat_headers": ["移动模块", "访问量", "转化率", "运营状态"],
            "stat_status": "已上线",
            "focus_cards": [("日活用户", "12.8万", "按设备和渠道统计"), ("订单转化", "18.6%", "首页入口转化率"), ("推送到达", "96.8%", "近 24 小时任务"), ("崩溃率", "0.08%", "移动端稳定性")],
            "process": ["注册", "浏览", "下单", "支付", "通知"],
            "chart_values": [72, 86, 64, 78, 92, 70],
        },
        "云计算软件": {
            "accent": "#0284c7",
            "accent_soft": "#f0f9ff",
            "sidebar": "#0c4a6e",
            "layout_variant": "pipeline",
            "user_label": "当前用户：云平台管理员",
            "metrics": [("活跃租户", "268"), ("云主机", "3,642"), ("资源告警", "19"), ("账单金额", "86.4万")],
            "filters": ["租户名称", "资源类型", "运行状态", "告警等级"],
            "table_headers": ["云资源", "租户或项目", "资源状态", "云平台操作"],
            "subjects": ["租户配额", "云主机实例", "对象存储", "安全组", "监控告警", "计量账单"],
            "objects": ["生产项目", "测试项目", "虚拟网络", "云硬盘", "边缘节点", "资源池"],
            "states": ["运行中", "资源告警", "待审核", "已归档"],
            "actions": ["详情 / 扩容 / 回收", "监控 / 审批 / 导出"],
            "todo_title": "云资源待办",
            "focus_title": "云资源运行看板",
            "module_focus_title": "云资源生命周期",
            "stat_headers": ["云模块", "资源量", "利用率", "运行状态"],
            "stat_status": "运行中",
            "focus_cards": [("CPU 利用率", "68.2%", "多租户资源池均值"), ("存储容量", "742TB", "对象存储和云硬盘"), ("告警闭环", "93.5%", "运维工单处理"), ("成本优化", "12.4%", "闲置资源回收")],
            "process": ["申请", "审批", "开通", "监控", "回收"],
            "chart_values": [80, 62, 88, 74, 68, 92],
        },
        "VR软件": {
            "accent": "#7e22ce",
            "accent_soft": "#faf5ff",
            "sidebar": "#3b0764",
            "layout_variant": "pipeline",
            "user_label": "当前用户：内容管理员",
            "metrics": [("虚拟场景", "126"), ("在线设备", "384"), ("体验记录", "8,426"), ("素材待审", "37")],
            "filters": ["场景名称", "设备编号", "体验状态", "素材类型"],
            "table_headers": ["VR业务", "场景或设备", "体验状态", "VR操作"],
            "subjects": ["场景版本", "头显设备", "交互脚本", "沉浸培训", "体验记录", "素材审核"],
            "objects": ["应急演练场景", "培训教室", "VR 头显", "手柄定位器", "三维模型", "体验用户"],
            "states": ["体验中", "待校准", "待审核", "已完成"],
            "actions": ["预览 / 校准 / 发布", "审核 / 回放 / 导出"],
            "todo_title": "VR内容待办",
            "focus_title": "沉浸体验看板",
            "module_focus_title": "VR内容发布流程",
            "stat_headers": ["VR模块", "体验次数", "完成率", "发布状态"],
            "stat_status": "已发布",
            "focus_cards": [("设备在线率", "97.4%", "头显与定位器状态"), ("平均沉浸时长", "18m", "单次体验均值"), ("场景完成率", "91.2%", "培训任务统计"), ("素材待审", "37", "模型贴图音视频")],
            "process": ["建模", "审核", "发布", "体验", "复盘"],
            "chart_values": [60, 76, 88, 70, 92, 66],
        },
        "5G软件": {
            "accent": "#0d9488",
            "accent_soft": "#f0fdfa",
            "sidebar": "#134e4a",
            "layout_variant": "map",
            "user_label": "当前用户：网络管理员",
            "metrics": [("基站站点", "1,284"), ("切片实例", "72"), ("边缘节点", "46"), ("网络告警", "23")],
            "filters": ["站点名称", "网络切片", "业务等级", "告警状态"],
            "table_headers": ["网络业务", "站点或切片", "网络状态", "5G操作"],
            "subjects": ["基站巡检", "切片开通", "边缘应用", "终端接入", "QoS 监控", "流量分析"],
            "objects": ["核心城区", "工业园区", "低时延切片", "边缘节点 A", "物联终端", "专网业务"],
            "states": ["正常", "边缘告警", "已激活", "待维护"],
            "actions": ["拓扑 / 诊断 / 派单", "开通 / 调优 / 导出"],
            "todo_title": "网络运维待办",
            "focus_title": "5G 网络运行看板",
            "module_focus_title": "网络业务保障流程",
            "stat_headers": ["网络模块", "连接数", "达标率", "保障状态"],
            "stat_status": "已保障",
            "focus_cards": [("平均时延", "12ms", "核心业务 P95"), ("切片达标", "98.1%", "带宽和隔离指标"), ("边缘负载", "64%", "节点资源均值"), ("告警闭环", "90.6%", "站点故障处理")],
            "process": ["开通", "接入", "监控", "告警", "优化"],
            "chart_values": [74, 82, 60, 88, 70, 94],
        },
        "小程序": {
            "accent": "#16a34a",
            "accent_soft": "#f0fdf4",
            "sidebar": "#14532d",
            "layout_variant": "workflow",
            "user_label": "当前用户：小程序运营",
            "metrics": [("授权用户", "6.4万"), ("预约订单", "312"), ("优惠券核销", "1,826"), ("订阅触达", "95.3%")],
            "filters": ["微信昵称", "服务分类", "订单状态", "活动渠道"],
            "table_headers": ["小程序业务", "用户或服务", "服务状态", "运营操作"],
            "subjects": ["微信授权", "首页轮播", "服务预约", "订单支付", "优惠券", "订阅消息"],
            "objects": ["微信用户", "服务门店", "预约时段", "支付订单", "营销活动", "订阅模板"],
            "states": ["已预约", "待支付", "已核销", "已上线"],
            "actions": ["查看 / 核销 / 退款", "配置 / 推送 / 导出"],
            "todo_title": "小程序待办",
            "focus_title": "轻应用运营看板",
            "module_focus_title": "小程序服务流程",
            "stat_headers": ["小程序模块", "访问量", "核销率", "运营状态"],
            "stat_status": "已上线",
            "focus_cards": [("访问转化率", "21.8%", "首页到预约链路"), ("核销订单", "1,826", "门店服务完成量"), ("订阅触达", "95.3%", "模板消息发送"), ("活动领券", "4,208", "优惠券领取记录")],
            "process": ["授权", "浏览", "预约", "支付", "核销"],
            "chart_values": [68, 84, 76, 58, 92, 80],
        },
        "智慧城市软件": {
            "accent": "#0f766e",
            "accent_soft": "#ecfdf5",
            "sidebar": "#123c40",
            "layout_variant": "map",
            "user_label": "当前用户：线路调度员",
            "metrics": [("线路覆盖率", "92.6%"), ("班次准点率", "96.8%"), ("接驳成功率", "91.4%"), ("高风险匹配", "18")],
            "filters": ["线路编号", "接驳节点", "适配等级", "运行区域"],
            "table_headers": ["线路/节点", "接驳区域", "适配状态", "调度操作"],
            "subjects": ["干线线路", "支线线路", "运输节点", "路径匹配", "衔接规则", "适配问题"],
            "objects": ["北向干线", "东区支线", "中心枢纽", "临时接驳点", "换乘时窗", "运行方案"],
            "states": ["已适配", "待评估", "有冲突", "已发布"],
            "actions": ["定位 / 匹配 / 调度", "评估 / 发布 / 导出"],
            "todo_title": "线路适配待办",
            "focus_title": "干支线衔接看板",
            "module_focus_title": "路径适配闭环",
            "stat_headers": ["线路模块", "线路数量", "适配率", "运行状态"],
            "stat_status": "已发布",
            "focus_cards": [("接驳成功率", "91.4%", "按干支线路径组合统计"), ("平均换乘时长", "12m", "节点服务时窗内完成"), ("覆盖盲区", "6", "待补充支线或临时接驳"), ("方案发布", "24", "本周已生效版本")],
            "process": ["编目", "匹配", "评估", "发布", "复盘"],
            "chart_values": [74, 86, 68, 92, 80, 88],
        },
    }
    profile = dict(default)
    for key, value in profiles.get(task.product_type, {}).items():
        profile[key] = value
    return profile


def _dashboard_body(task: GenerationTask, blueprint: ProductBlueprint, design_brief: dict[str, Any] | None = None) -> str:
    profile = _profile_for_blueprint(task, blueprint, design_brief)
    content = f"{_source_dashboard_strip(profile, blueprint)}{_dashboard_content(profile, blueprint)}"
    return _layout(
        task,
        blueprint,
        "系统首页",
        content,
        active="系统首页",
        design_brief=design_brief,
        page_key="dashboard",
        page_kind="dashboard",
    )


def _module_body(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    module: FeatureModule,
    design_brief: dict[str, Any] | None = None,
    screen: UiScreenBlueprint | None = None,
) -> str:
    profile = _profile_for_blueprint(task, blueprint, design_brief)
    profile = dict(profile)
    profile["table_headers"] = _module_table_headers(profile, module)
    view_type = _admin_render_view_type(profile, blueprint, module, screen=screen)
    content = _with_module_live_footer(_module_content(profile, blueprint, module, view_type=view_type, screen=screen), profile, module)
    return _layout(
        task,
        blueprint,
        module.title,
        content,
        active=module.title,
        design_brief=design_brief,
        page_key=(screen.key if screen else _module_page_key(module.key)),
        page_kind="module",
        module=module,
    )


def _statistics_body(task: GenerationTask, blueprint: ProductBlueprint, design_brief: dict[str, Any] | None = None) -> str:
    profile = _profile_for_blueprint(task, blueprint, design_brief)
    content = f"{_source_statistics_strip(profile, blueprint)}{_statistics_content(profile, blueprint)}"
    return _layout(
        task,
        blueprint,
        "统计报表界面",
        content,
        active="统计报表页",
        design_brief=design_brief,
        page_key="statistics",
        page_kind="statistics",
    )


def _dashboard_content(profile: dict[str, Any], blueprint: ProductBlueprint) -> str:
    variant = str(profile.get("layout_variant") or "classic")
    shaped = _dashboard_shape_content(profile, blueprint)
    if shaped:
        return shaped
    if variant == "risk":
        return f"""
{_risk_tiles(profile)}
<div class="dashboard-split">
  <div class="panel"><h2>{escape(profile["todo_title"])}</h2>{_table(profile["table_headers"], _domain_rows(blueprint.modules, profile, 7))}</div>
  <div class="panel"><h2>{escape(profile["focus_title"])}</h2>{_focus_panel(profile)}{_mini_chart(profile)}</div>
</div>
<div class="panel"><h2>风险事项</h2>{_queue_list(profile, blueprint.modules, 4)}</div>
"""
    if variant == "map":
        return f"""
<div class="grid">{_metric_cards(profile["metrics"])}</div>
<div class="dashboard-split">
  <div class="panel"><h2>{escape(profile["focus_title"])}</h2>{_map_board(profile, blueprint.modules)}</div>
  <div class="panel"><h2>{escape(profile["todo_title"])}</h2>{_queue_list(profile, blueprint.modules, 5)}</div>
</div>
<div class="panel"><h2>业务入口</h2><div class="toolbar">{_quick_buttons(blueprint.modules)}</div></div>
"""
    if variant == "pipeline":
        return f"""
{_pipeline_cards(profile)}
<div class="two-col">
  <div class="panel"><h2>{escape(profile["todo_title"])}</h2>{_queue_list(profile, blueprint.modules, 6)}</div>
  <div class="panel"><h2>{escape(profile["module_focus_title"])}</h2>{_timeline(profile)}</div>
</div>
<div class="panel"><h2>{escape(profile["focus_title"])}</h2>{_mini_chart(profile)}<div class="process">{_process(profile)}</div></div>
"""
    if variant == "workflow":
        return f"""
<div class="grid">{_metric_cards(profile["metrics"])}</div>
<div class="dashboard-split">
  <div class="panel"><h2>{escape(profile["module_focus_title"])}</h2>{_timeline(profile)}</div>
  <div class="panel"><h2>{escape(profile["focus_title"])}</h2>{_focus_panel(profile)}</div>
</div>
<div class="panel"><h2>{escape(profile["todo_title"])}</h2>{_queue_list(profile, blueprint.modules, 5)}</div>
"""
    if variant == "command":
        return f"""
<div class="command-strip">{_metric_cards(profile["metrics"])}</div>
<div class="command-grid">
  <div class="panel command-main"><h2>{escape(profile["dashboard_pattern"])}</h2>{_mini_chart(profile)}<div class="process">{_process(profile)}</div></div>
  <div class="panel"><h2>{escape(profile["todo_title"])}</h2>{_queue_list(profile, blueprint.modules, 5)}</div>
  <div class="panel"><h2>{escape(profile["focus_title"])}</h2>{_focus_panel(profile, compact=True)}</div>
</div>
"""
    if variant == "kanban":
        return f"""
<div class="grid">{_metric_cards(profile["metrics"])}</div>
<div class="panel"><h2>{escape(profile["dashboard_pattern"])}</h2>{_kanban_board(profile, blueprint.modules)}</div>
<div class="dashboard-split">
  <div class="panel"><h2>{escape(profile["focus_title"])}</h2>{_focus_panel(profile, compact=True)}</div>
  <div class="panel"><h2>近期趋势</h2>{_mini_chart(profile)}</div>
</div>
"""
    if variant == "matrix":
        return f"""
<div class="matrix-layout">
  <div class="panel matrix-main"><h2>{escape(profile["dashboard_pattern"])}</h2>{_matrix_board(profile, blueprint.modules)}</div>
  <div class="panel"><h2>{escape(profile["todo_title"])}</h2>{_queue_list(profile, blueprint.modules, 4)}</div>
  <div class="panel"><h2>指标趋势</h2>{_mini_chart(profile)}</div>
</div>
"""
    return f"""
<div class="grid">{_metric_cards(profile["metrics"])}</div>
<div class="two-col">
  <div class="panel"><h2>{escape(profile["todo_title"])}</h2>{_table(profile["table_headers"], _domain_rows(blueprint.modules, profile, 6))}</div>
  <div class="panel"><h2>{escape(profile["focus_title"])}</h2>{_focus_panel(profile)}</div>
</div>
<div class="panel"><h2>快捷入口</h2><div class="toolbar">{_quick_buttons(blueprint.modules)}</div></div>
"""


def _module_content(
    profile: dict[str, Any],
    blueprint: ProductBlueprint,
    module: FeatureModule,
    view_type: str = "",
    screen: UiScreenBlueprint | None = None,
) -> str:
    variant = str(profile.get("layout_variant") or "classic")
    filters = _filter_toolbar(profile)
    routed = _module_content_by_view_type(profile, blueprint, module, filters, view_type, screen)
    if routed:
        return routed
    if _is_transport_route_context(blueprint):
        return _transport_route_module_content(profile, blueprint, module, filters)
    shaped = _module_shape_content(profile, blueprint, module, filters)
    if shaped:
        return shaped
    if variant == "risk":
        return f"""
{_risk_tiles(profile)}
<div class="panel">
  <div class="toolbar">{filters}<span class="button">风险研判</span><span class="button">导出</span></div>
  {_table(profile["table_headers"], _module_rows(module, profile))}
</div>
<div class="two-col">
  <div class="panel"><h2>研判规则</h2>{_focus_panel(profile, compact=True)}</div>
  <div class="panel"><h2>{escape(profile["module_focus_title"])}</h2>{_timeline(profile)}</div>
</div>
"""
    if variant == "map":
        return f"""
<div class="toolbar">{filters}<span class="button">定位</span><span class="button">同步</span></div>
<div class="dashboard-split">
  <div class="panel"><h2>{escape(module.title)}</h2>{_map_board(profile, [module] + blueprint.modules[:5])}</div>
  <div class="panel"><h2>空间任务</h2>{_queue_list(profile, [module] + blueprint.modules[:5], 5)}</div>
</div>
<div class="panel"><h2>业务明细</h2>{_table(profile["table_headers"], _module_rows(module, profile))}</div>
"""
    if variant == "pipeline":
        return f"""
{_pipeline_cards(profile, module)}
<div class="two-col">
  <div class="panel"><div class="toolbar">{filters}<span class="button">调度</span><span class="button">发布</span></div>{_table(profile["table_headers"], _module_rows(module, profile))}</div>
  <div class="panel"><h2>{escape(module.title)}流程</h2>{_timeline(profile)}</div>
</div>
<div class="panel"><h2>模块说明</h2><p class="muted">{escape(module.description)}</p><div class="process">{_process(profile)}</div></div>
"""
    if variant == "workflow":
        return f"""
<div class="dashboard-split">
  <div class="panel"><h2>{escape(module.title)}处理流</h2>{_timeline(profile)}</div>
  <div class="panel"><h2>{escape(profile["module_focus_title"])}</h2>{_focus_panel(profile, compact=True)}</div>
</div>
<div class="panel">
  <div class="toolbar">{filters}<span class="button">查询</span><span class="button">新增</span></div>
  {_table(profile["table_headers"], _module_rows(module, profile))}
</div>
<div class="panel"><h2>模块说明</h2><p class="muted">{escape(module.description)}</p></div>
"""
    if variant == "command":
        return f"""
<div class="command-strip">{_metric_cards(profile["metrics"])}</div>
<div class="command-grid">
  <div class="panel command-main"><h2>{escape(module.title)}指挥区</h2><div class="toolbar">{filters}<span class="button">处置</span><span class="button">联动</span></div>{_table(profile["table_headers"], _module_rows(module, profile))}</div>
  <div class="panel"><h2>处置步骤</h2>{_timeline(profile)}</div>
  <div class="panel"><h2>专题规则</h2>{_focus_panel(profile, compact=True)}</div>
</div>
"""
    if variant == "kanban":
        return f"""
<div class="panel"><h2>{escape(module.title)}任务看板</h2>{_kanban_board(profile, [module] + blueprint.modules[:5])}</div>
<div class="dashboard-split">
  <div class="panel"><div class="toolbar">{filters}<span class="button">新增任务</span><span class="button">批量处理</span></div>{_table(profile["table_headers"], _module_rows(module, profile))}</div>
  <div class="panel"><h2>模块说明</h2><p class="muted">{escape(module.description)}</p>{_focus_panel(profile, compact=True)}</div>
</div>
"""
    if variant == "matrix":
        return f"""
<div class="matrix-layout">
  <div class="panel matrix-main"><h2>{escape(module.title)}矩阵</h2>{_matrix_board(profile, [module] + blueprint.modules[:5])}</div>
  <div class="panel"><h2>处理列表</h2>{_table(profile["table_headers"], _module_rows(module, profile))}</div>
  <div class="panel"><h2>{escape(profile["module_focus_title"])}</h2>{_timeline(profile)}</div>
</div>
"""
    return f"""
<div class="panel">
  <div class="toolbar">{filters}<span class="button">查询</span><span class="button">新增</span></div>
  {_table(profile["table_headers"], _module_rows(module, profile))}
</div>
<div class="two-col">
  <div class="panel"><h2>模块说明</h2><p class="muted">{escape(module.description)}</p><div class="process">{_process(profile)}</div></div>
  <div class="panel"><h2>{escape(profile["module_focus_title"])}</h2>{_focus_panel(profile, compact=True)}</div>
</div>
"""


def _transport_route_module_content(profile: dict[str, Any], blueprint: ProductBlueprint, module: FeatureModule, filters: str) -> str:
    return f"""
<div class="toolbar">{filters}<span class="button">查询</span><span class="button">同步</span><span class="button">导出</span></div>
<div class="dashboard-split">
  <div class="panel"><h2>{escape(module.title)}清单</h2>{_table(profile["table_headers"], _module_rows(module, profile))}</div>
  <div class="panel"><h2>线路衔接概览</h2>{_map_board(profile, [module] + blueprint.modules[:5])}</div>
</div>
<div class="two-col">
  <div class="panel"><h2>{escape(module.title)}处理轨迹</h2>{_timeline(profile)}</div>
  <div class="panel"><h2>关键指标</h2>{_focus_panel(profile, compact=True)}</div>
</div>
"""


def _module_content_by_view_type(
    profile: dict[str, Any],
    blueprint: ProductBlueprint,
    module: FeatureModule,
    filters: str,
    view_type: str,
    screen: UiScreenBlueprint | None,
) -> str:
    view = view_type or _admin_render_view_type(profile, blueprint, module, screen=screen)
    if view in {"", "admin_module"}:
        return ""
    context_panel = _screen_context_panel(screen, module)
    rows = _module_rows(module, profile)
    if view == "admin_map":
        return f"""
<div class="toolbar">{filters}<span class="button">定位</span><span class="button">框选</span><span class="button">同步图层</span></div>
<div class="geo-desk">
  <section class="panel geo-canvas"><h2>{escape(module.title)}分布图</h2>{_map_board(profile, [module] + blueprint.modules[:5])}</section>
  <aside class="geo-side">
    <section class="panel"><h2>点位详情</h2>{_case_cards_for_module(profile, module)}</section>
    <section class="panel"><h2>业务队列</h2>{_queue_list(profile, [module] + blueprint.modules[:5], 4)}</section>
  </aside>
</div>
<div class="panel compact-panel"><h2>{escape(module.title)}明细</h2>{_table(profile["table_headers"], rows)}</div>
"""
    if view == "admin_pipeline":
        return f"""
{_pipeline_cards(profile, module)}
<div class="pipeline-desk">
  <section class="panel pipeline-main"><div class="toolbar">{filters}<span class="button">重试</span><span class="button">发布</span></div>{_table(profile["table_headers"], rows)}</section>
  <section class="panel"><h2>{escape(module.title)}阶段链路</h2>{_timeline(profile)}</section>
</div>
<div class="panel compact-panel"><h2>执行上下文</h2>{context_panel}<div class="process">{_process(profile)}</div></div>
"""
    if view == "admin_risk":
        return f"""
{_risk_tiles(profile)}
<div class="risk-desk">
  <section class="panel risk-main"><div class="toolbar">{filters}{_module_action_buttons(module, fallback=["研判", "确认结论", "导出"])}</div>{_table(profile["table_headers"], rows)}</section>
  <section class="panel"><h2>规则命中</h2>{_focus_panel(profile, compact=True)}{_timeline(profile)}</section>
</div>
"""
    if view == "admin_case":
        return f"""
<div class="case-desk">
  <section class="panel case-summary"><h2>{escape(module.title)}档案</h2>{_case_cards_for_module(profile, module)}{context_panel}</section>
  <section class="panel case-detail"><div class="toolbar">{filters}<span class="button">查看</span><span class="button">更新</span></div>{_table(profile["table_headers"], rows)}</section>
  <section class="panel"><h2>关联轨迹</h2>{_timeline(profile)}</section>
</div>
"""
    if view == "admin_board":
        return f"""
<div class="panel"><h2>{escape(module.title)}工作看板</h2>{_kanban_board(profile, [module] + blueprint.modules[:5])}</div>
<div class="dashboard-split">
  <section class="panel"><div class="toolbar">{filters}<span class="button">分派</span><span class="button">流转</span></div>{_table(profile["table_headers"], rows)}</section>
  <section class="panel"><h2>处理依据</h2>{context_panel}{_focus_panel(profile, compact=True)}</section>
</div>
"""
    if view == "admin_form":
        return f"""
<div class="form-desk">
  <section class="panel form-main"><h2>{escape(module.title)}配置表单</h2>{_module_form_panel(module, profile)}</section>
  <section class="panel"><h2>预览结果</h2>{_table(profile["table_headers"], rows[:4])}</section>
  <section class="panel"><h2>校验规则</h2>{_focus_panel(profile, compact=True)}{_timeline(profile)}</section>
</div>
"""
    if view == "admin_matrix":
        return f"""
<div class="matrix-layout">
  <section class="panel matrix-main"><h2>{escape(module.title)}指标矩阵</h2>{_matrix_board(profile, [module] + blueprint.modules[:5])}</section>
  <section class="panel"><h2>统计口径</h2>{context_panel}{_focus_panel(profile, compact=True)}</section>
  <section class="panel"><h2>明细数据</h2>{_table(profile["table_headers"], rows[:5])}</section>
</div>
"""
    if view == "admin_table":
        return f"""
<div class="table-desk">
  <section class="panel table-main"><div class="toolbar">{filters}<span class="button">查询</span><span class="button">新增</span><span class="button">导出</span></div>{_table(profile["table_headers"], rows)}</section>
  <aside class="table-side">
    <section class="panel"><h2>当前{escape(_module_business_subject(module))}</h2>{context_panel}</section>
    <section class="panel"><h2>处理流程</h2>{_timeline(profile)}</section>
  </aside>
</div>
"""
    return ""


def _admin_render_view_type(
    profile: dict[str, Any],
    blueprint: ProductBlueprint,
    module: FeatureModule,
    screen: UiScreenBlueprint | None = None,
) -> str:
    explicit = str(getattr(screen, "view_type", "") or "").strip()
    if explicit and explicit not in {"admin_module", "admin_login", "admin_dashboard", "admin_statistics"}:
        return explicit
    title_text = " ".join(
        [
            str(getattr(module, "key", "") or ""),
            str(getattr(module, "title", "") or ""),
        ]
    )
    description_text = str(getattr(module, "description", "") or "")
    strong_text = f"{title_text} {description_text}"
    operation_text = " ".join(str(item) for item in (getattr(module, "operations", []) or [])[:8])
    identity_cycle = _profile_module_cycle(profile)
    if identity_cycle:
        try:
            index = list(getattr(blueprint, "modules", []) or []).index(module)
        except ValueError:
            index = 0
        return identity_cycle[index % len(identity_cycle)]
    if re.search(r"风险|风控|安全|告警|漏洞|审计|合规|征信|授信|反欺诈|预警|权限|监管", strong_text, re.IGNORECASE):
        return "admin_risk"
    if re.search(r"地图|图层|GIS|定位|轨迹|点位|区域|网格|站点|车辆|基站|线路|路径|接驳|换乘|客流|门禁", title_text, re.IGNORECASE) or ("空间" in title_text and "命名空间" not in title_text):
        return "admin_map"
    if re.search(r"配置|规则|模板|参数|策略|排班|预约|上架", title_text, re.IGNORECASE) or re.search(r"配置|登记|新增|编辑|申请", operation_text, re.IGNORECASE):
        return "admin_form"
    if re.search(r"患者|病历|档案|客户|会员|资料|画像|处方|随访|门诊|科室|资产|账号|用户", title_text, re.IGNORECASE):
        return "admin_case"
    if re.search(r"看板|工单|派单|作业|批改|测评|课堂|班级|课程|通知|事件|处置|售后|回访", title_text, re.IGNORECASE) or re.search(r"分派|处置|批改|确认|归档", operation_text, re.IGNORECASE):
        return "admin_board"
    if re.search(r"流水线|链路|调度|编排|训练|模型|部署|资源|集群|容器|云主机|数据源|入仓|血缘|作业实例|作业调度|边缘|计划|班次|命名空间", title_text, re.IGNORECASE) or re.search(r"调度|训练|重跑|部署", operation_text, re.IGNORECASE):
        return "admin_pipeline"
    if re.search(r"统计|报表|指标|分析|矩阵|质量|评分|趋势", title_text, re.IGNORECASE) or re.search(r"统计|分析|导出图表", operation_text, re.IGNORECASE):
        return "admin_matrix"
    modules = list(getattr(blueprint, "modules", []) or [])
    try:
        index = modules.index(module)
    except ValueError:
        index = 0
    family = str(profile.get("layout_variant") or "")
    cycles = {
        "map": ["admin_map", "admin_table", "admin_board", "admin_form", "admin_risk", "admin_matrix"],
        "risk": ["admin_risk", "admin_case", "admin_board", "admin_table", "admin_form", "admin_matrix"],
        "pipeline": ["admin_pipeline", "admin_table", "admin_board", "admin_risk", "admin_form", "admin_matrix"],
        "workflow": ["admin_board", "admin_form", "admin_case", "admin_table", "admin_risk", "admin_matrix"],
        "kanban": ["admin_board", "admin_case", "admin_table", "admin_form", "admin_risk", "admin_matrix"],
        "matrix": ["admin_matrix", "admin_table", "admin_case", "admin_form", "admin_board", "admin_risk"],
        "command": ["admin_risk", "admin_table", "admin_pipeline", "admin_board", "admin_form", "admin_case"],
    }
    cycle = cycles.get(family) or ["admin_table", "admin_board", "admin_form", "admin_case", "admin_pipeline", "admin_risk"]
    return cycle[index % len(cycle)]


def _profile_module_cycle(profile: dict[str, Any]) -> list[str]:
    values = profile.get("module_composition_cycle")
    if not isinstance(values, list):
        return []
    allowed = {
        "admin_table",
        "admin_map",
        "admin_pipeline",
        "admin_board",
        "admin_case",
        "admin_risk",
        "admin_form",
        "admin_matrix",
    }
    return [str(value) for value in values if str(value) in allowed]


def _screen_context_panel(screen: UiScreenBlueprint | None, module: FeatureModule) -> str:
    components = [str(item).strip() for item in (getattr(screen, "components", []) if screen else []) if str(item).strip()]
    if not components:
        components = (module.data_fields or module.operations or ["业务字段", "处理状态", "操作结果"])[:5]
    sample = getattr(screen, "sample_data", {}) if screen else {}
    rows: list[tuple[str, str]] = []
    if isinstance(sample, dict):
        rows.extend((str(key), str(value)) for key, value in list(sample.items())[:4])
    if not rows:
        rows = [(field, _operation_sample_value(module, field, index)) for index, field in enumerate((module.data_fields or ["业务编号", "业务名称", "处理状态"])[:4])]
    chip_html = "".join(f"<span>{escape(_clip(item, 12))}</span>" for item in components[:6])
    row_html = "".join(f"<div><span>{escape(_clip(str(label), 12))}</span><b>{escape(_clip(str(value), 24))}</b></div>" for label, value in rows[:4])
    caption = str(getattr(screen, "caption", "") or module.description or "")
    return f"""
<div class="module-context">
  <p>{escape(_clip(caption, 78))}</p>
  <div class="context-chips">{chip_html}</div>
  <div class="kv-grid">{row_html}</div>
</div>
"""


def _case_cards_for_module(profile: dict[str, Any], module: FeatureModule) -> str:
    fields = list(module.data_fields or [])[:4]
    if not fields:
        return _case_cards(profile)
    states = list(profile.get("states") or ["正常", "进行中", "已完成"])
    cards = []
    for index, field in enumerate(fields[:4]):
        cards.append(
            f"<div class='case-card'><span>{escape(field)}</span><strong>{escape(_operation_sample_value(module, field, index))}</strong><small>{escape(states[index % len(states)])}</small></div>"
        )
    return "".join(cards)


def _module_form_panel(module: FeatureModule, profile: dict[str, Any]) -> str:
    fields = list(module.data_fields or [])[:8]
    if not fields:
        fields = ["业务编号", "业务名称", "状态", "责任角色", "生效时间", "备注"]
    items = "".join(
        f"<div class='form-item'><span>{escape(field)}</span><div class='form-value'>{escape(_operation_sample_value(module, field, index))}</div></div>"
        for index, field in enumerate(fields[:8])
    )
    return f"""
<div class="form-grid">{items}</div>
<div class="dialog-note">{escape(module.description)}</div>
<div class="dialog-footer inline-footer"><span class="button ghost">重置</span><span class="button">保存配置</span></div>
"""


def _statistics_content(profile: dict[str, Any], blueprint: ProductBlueprint) -> str:
    variant = str(profile.get("layout_variant") or "classic")
    rows = _stat_rows(profile)
    shaped = _statistics_shape_content(profile, blueprint, rows)
    if shaped:
        return shaped
    if variant == "risk":
        return f"""
{_risk_tiles(profile)}
<div class="two-col">
  <div class="panel"><h2>{escape(profile["stat_title"])}</h2>{_table(profile["stat_headers"], rows)}</div>
  <div class="panel"><h2>风险趋势</h2>{_mini_chart(profile)}{_focus_panel(profile, compact=True)}</div>
</div>
"""
    if variant == "map":
        return f"""
<div class="dashboard-split">
  <div class="panel"><h2>区域态势</h2>{_map_board(profile, blueprint.modules)}</div>
  <div class="panel"><h2>{escape(profile["stat_title"])}</h2>{_table(profile["stat_headers"], rows)}</div>
</div>
<div class="panel"><h2>区域趋势</h2>{_mini_chart(profile)}<div class="process">{_process(profile)}</div></div>
"""
    if variant == "pipeline":
        return f"""
{_pipeline_cards(profile)}
<div class="two-col">
  <div class="panel"><h2>{escape(profile["stat_title"])}</h2>{_table(profile["stat_headers"], rows)}</div>
  <div class="panel"><h2>链路趋势</h2>{_mini_chart(profile)}<div class="process">{_process(profile)}</div></div>
</div>
"""
    if variant == "workflow":
        return f"""
<div class="grid">{_metric_cards(profile["metrics"])}</div>
<div class="two-col">
  <div class="panel"><h2>{escape(profile["stat_title"])}</h2>{_table(profile["stat_headers"], rows)}</div>
  <div class="panel"><h2>流程完成趋势</h2>{_timeline(profile)}</div>
</div>
"""
    if variant == "command":
        return f"""
<div class="command-strip">{_metric_cards(profile["metrics"])}</div>
<div class="command-grid">
  <div class="panel command-main"><h2>{escape(profile["stat_title"])}</h2>{_mini_chart(profile)}<div class="process">{_process(profile)}</div></div>
  <div class="panel"><h2>统计明细</h2>{_table(profile["stat_headers"], rows)}</div>
  <div class="panel"><h2>重点指标</h2>{_focus_panel(profile, compact=True)}</div>
</div>
"""
    if variant == "kanban":
        return f"""
<div class="panel"><h2>{escape(profile["stat_title"])}看板</h2>{_kanban_board(profile, blueprint.modules)}</div>
<div class="dashboard-split">
  <div class="panel"><h2>统计明细</h2>{_table(profile["stat_headers"], rows)}</div>
  <div class="panel"><h2>趋势分析</h2>{_mini_chart(profile)}</div>
</div>
"""
    if variant == "matrix":
        return f"""
<div class="matrix-layout">
  <div class="panel matrix-main"><h2>{escape(profile["stat_title"])}</h2>{_matrix_board(profile, blueprint.modules)}</div>
  <div class="panel"><h2>统计明细</h2>{_table(profile["stat_headers"], rows)}</div>
  <div class="panel"><h2>趋势分析</h2>{_mini_chart(profile)}</div>
</div>
"""
    return f"""
<div class="grid">{_metric_cards(profile["metrics"])}</div>
<div class="two-col">
  <div class="panel"><h2>{escape(profile["stat_title"])}</h2>{_table(profile["stat_headers"], rows)}</div>
  <div class="panel"><h2>趋势分析</h2>{_mini_chart(profile)}<div class="process">{_process(profile)}</div></div>
</div>
"""


def _dashboard_shape_content(profile: dict[str, Any], blueprint: ProductBlueprint) -> str:
    shape = str(profile.get("workspace_shape") or "")
    if shape == "freeform_grid":
        return _freeform_structure_content(profile, blueprint, "dashboard")
    if shape == "triage_console":
        return f"""
<div class="shape-triage">
  <section class="panel"><h2>{escape(profile["todo_title"])}</h2>{_triage_stack(profile, blueprint.modules)}</section>
  <section class="panel"><h2>{escape(profile["dashboard_pattern"])}</h2>{_table(profile["table_headers"], _domain_rows(blueprint.modules, profile, 8))}</section>
  <section class="panel"><h2>{escape(profile["focus_title"])}</h2>{_focus_panel(profile, compact=True)}{_mini_chart(profile)}</section>
</div>
"""
    if shape == "ledger_split":
        return f"""
<div class="shape-ledger">
  <div class="ledger-toolbar">{_ledger_boxes(profile)}</div>
  <section class="panel"><h2>{escape(profile["dashboard_pattern"])}</h2>{_table(profile["table_headers"], _domain_rows(blueprint.modules, profile, 9))}</section>
  <section class="panel"><h2>{escape(profile["focus_title"])}</h2>{_focus_panel(profile)}<div class="process">{_process(profile)}</div></section>
</div>
"""
    if shape == "monitor_wall":
        return f"""
<div class="shape-wall">
  <section class="panel wall-wide"><h2>{escape(profile["dashboard_pattern"])}</h2>{_mini_chart(profile)}</section>
  <section class="panel wall-wide"><h2>{escape(profile["todo_title"])}</h2>{_queue_list(profile, blueprint.modules, 5)}</section>
  <section class="panel">{_focus_panel(profile, compact=True)}</section>
  <section class="panel wall-full"><h2>{escape(profile["module_focus_title"])}</h2>{_timeline(profile)}</section>
</div>
"""
    if shape == "process_lane":
        return f"""
<div class="shape-lane">
  <div class="lane-strip">{_lane_steps(profile)}</div>
  <section class="panel"><h2>{escape(profile["todo_title"])}</h2>{_queue_list(profile, blueprint.modules, 6)}</section>
  <section class="panel"><h2>{escape(profile["focus_title"])}</h2>{_mini_chart(profile)}</section>
</div>
"""
    if shape == "case_desk":
        return f"""
<div class="shape-case">
  <section class="panel"><h2>业务档案</h2>{_case_cards(profile)}</section>
  <section class="panel"><h2>{escape(profile["dashboard_pattern"])}</h2>{_table(profile["table_headers"], _domain_rows(blueprint.modules, profile, 8))}</section>
  <section class="panel"><h2>{escape(profile["module_focus_title"])}</h2>{_timeline(profile)}</section>
</div>
"""
    if shape == "board_columns":
        return f"""
<div class="shape-board">
  <section class="panel"><h2>{escape(profile["dashboard_pattern"])}</h2>{_kanban_board(profile, blueprint.modules)}</section>
  <aside class="board-side">
    <section class="panel"><h2>{escape(profile["focus_title"])}</h2>{_focus_panel(profile, compact=True)}</section>
    <section class="panel"><h2>趋势</h2>{_mini_chart(profile)}</section>
  </aside>
</div>
"""
    return ""


def _module_shape_content(profile: dict[str, Any], blueprint: ProductBlueprint, module: FeatureModule, filters: str) -> str:
    shape = str(profile.get("workspace_shape") or "")
    if shape == "freeform_grid":
        return _freeform_structure_content(profile, blueprint, "module", module=module, filters=filters)
    if shape == "triage_console":
        return f"""
<div class="shape-triage">
  <section class="panel"><h2>{escape(module.title)}待办</h2>{_triage_stack(profile, [module] + blueprint.modules[:5])}</section>
  <section class="panel"><div class="toolbar">{filters}{_module_action_buttons(module, fallback=["查看", "分派", "更新"])}</div>{_table(profile["table_headers"], _module_rows(module, profile))}</section>
  <section class="panel"><h2>处置依据</h2>{_focus_panel(profile, compact=True)}{_timeline(profile)}</section>
</div>
"""
    if shape == "ledger_split":
        return f"""
<div class="shape-ledger">
  <div class="ledger-toolbar">{_ledger_boxes(profile)}</div>
  <section class="panel"><div class="toolbar">{filters}<span class="button">查询</span><span class="button">导出</span></div>{_table(profile["table_headers"], _module_rows(module, profile))}</section>
  <section class="panel"><h2>{escape(module.title)}详情</h2>{_case_cards(profile)}<p class="muted">{escape(module.description)}</p></section>
</div>
"""
    if shape == "monitor_wall":
        return f"""
<div class="shape-wall">
  <section class="panel wall-wide"><h2>{escape(module.title)}监控</h2>{_mini_chart(profile)}</section>
  <section class="panel wall-wide"><h2>实时队列</h2>{_queue_list(profile, [module] + blueprint.modules[:5], 5)}</section>
  <section class="panel wall-full"><div class="toolbar">{filters}<span class="button">处置</span><span class="button">联动</span></div>{_table(profile["table_headers"], _module_rows(module, profile))}</section>
</div>
"""
    if shape == "process_lane":
        return f"""
<div class="shape-lane">
  <div class="lane-strip">{_lane_steps(profile)}</div>
  <section class="panel"><div class="toolbar">{filters}{_module_action_buttons(module, fallback=["提交", "确认", "查看结果"])}</div>{_table(profile["table_headers"], _module_rows(module, profile))}</section>
  <section class="panel"><h2>{escape(module.title)}说明</h2><p class="muted">{escape(module.description)}</p></section>
</div>
"""
    if shape == "case_desk":
        return f"""
<div class="shape-case">
  <section class="panel"><h2>{escape(module.title)}档案</h2>{_case_cards(profile)}</section>
  <section class="panel"><div class="toolbar">{filters}<span class="button">保存</span><span class="button">流转</span></div>{_table(profile["table_headers"], _module_rows(module, profile))}</section>
  <section class="panel"><h2>规则与流转</h2>{_timeline(profile)}{_focus_panel(profile, compact=True)}</section>
</div>
"""
    if shape == "board_columns":
        return f"""
<div class="shape-board">
  <section class="panel"><h2>{escape(module.title)}看板</h2>{_kanban_board(profile, [module] + blueprint.modules[:5])}</section>
  <aside class="board-side">
    <section class="panel"><div class="toolbar">{filters}<span class="button">新增</span></div>{_queue_list(profile, [module] + blueprint.modules[:5], 4)}</section>
    <section class="panel"><h2>模块指标</h2>{_focus_panel(profile, compact=True)}</section>
  </aside>
</div>
"""
    return ""


def _statistics_shape_content(profile: dict[str, Any], blueprint: ProductBlueprint, rows: list[list[str]]) -> str:
    shape = str(profile.get("workspace_shape") or "")
    if shape == "freeform_grid":
        return _freeform_structure_content(profile, blueprint, "statistics", rows=rows)
    if shape == "monitor_wall":
        return f"""
<div class="shape-wall">
  <section class="panel wall-wide"><h2>{escape(profile["stat_title"])}</h2>{_mini_chart(profile)}</section>
  <section class="panel wall-wide"><h2>统计明细</h2>{_table(profile["stat_headers"], rows)}</section>
  <section class="panel wall-full"><h2>流程状态</h2>{_timeline(profile)}</section>
</div>
"""
    if shape in {"triage_console", "case_desk"}:
        return f"""
<div class="shape-case">
  <section class="panel"><h2>统计对象</h2>{_case_cards(profile)}</section>
  <section class="panel"><h2>{escape(profile["stat_title"])}</h2>{_table(profile["stat_headers"], rows)}</section>
  <section class="panel"><h2>趋势分析</h2>{_mini_chart(profile)}{_focus_panel(profile, compact=True)}</section>
</div>
"""
    if shape == "process_lane":
        return f"""
<div class="shape-lane">
  <div class="lane-strip">{_lane_steps(profile)}</div>
  <section class="panel"><h2>{escape(profile["stat_title"])}</h2>{_table(profile["stat_headers"], rows)}</section>
</div>
"""
    if shape == "board_columns":
        return f"""
<div class="shape-board">
  <section class="panel"><h2>{escape(profile["stat_title"])}</h2>{_kanban_board(profile, blueprint.modules)}</section>
  <aside class="board-side"><section class="panel">{_table(profile["stat_headers"], rows)}</section><section class="panel">{_mini_chart(profile)}</section></aside>
</div>
"""
    if shape == "ledger_split":
        return f"""
<div class="shape-ledger">
  <div class="ledger-toolbar">{_ledger_boxes(profile)}</div>
  <section class="panel"><h2>{escape(profile["stat_title"])}</h2>{_table(profile["stat_headers"], rows)}</section>
  <section class="panel"><h2>趋势分析</h2>{_mini_chart(profile)}<div class="process">{_process(profile)}</div></section>
</div>
"""
    return ""


def _source_dashboard_strip(profile: dict[str, Any], blueprint: ProductBlueprint) -> str:
    module = blueprint.modules[0] if blueprint.modules else None
    if not module:
        return ""
    return f"<div class='panel runtime-strip'>{_runtime_record_panel(module)}</div>"


def _source_statistics_strip(profile: dict[str, Any], blueprint: ProductBlueprint) -> str:
    module = blueprint.modules[-1] if blueprint.modules else None
    if not module:
        return ""
    return f"<div class='panel runtime-strip'>{_runtime_record_panel(module)}</div>"


def _profile_source_evidence(profile: dict[str, Any]) -> dict[str, Any]:
    evidence = profile.get("source_ui_evidence")
    return evidence if isinstance(evidence, dict) else {}


def _module_source_evidence_from_profile(profile: dict[str, Any], module: FeatureModule) -> dict[str, Any]:
    evidence = _profile_source_evidence(profile)
    modules = evidence.get("modules") if isinstance(evidence.get("modules"), dict) else {}
    item = modules.get(module.key) if isinstance(modules, dict) else {}
    return item if isinstance(item, dict) else {}


def _source_file_display(evidence: dict[str, Any]) -> str:
    files = evidence.get("files") if isinstance(evidence.get("files"), list) else []
    if not files:
        return ""
    first = files[0]
    path = first.get("path") if isinstance(first, dict) else str(first)
    return Path(str(path)).name


def _module_table_headers(profile: dict[str, Any], module: FeatureModule) -> list[str]:
    fields = [str(field).strip() for field in (module.data_fields or []) if str(field).strip()]
    if len(fields) >= 3:
        return fields[:3] + ["状态", "操作"]
    evidence = _module_source_evidence_from_profile(profile, module)
    evidence_fields = [str(field).strip() for field in (evidence.get("fields") or []) if str(field).strip()]
    if len(evidence_fields) >= 3:
        return evidence_fields[:3] + ["状态", "操作"]
    return list(profile.get("table_headers") or ["业务名称", "所属模块", "状态", "操作"])


def _with_module_live_footer(content: str, profile: dict[str, Any], module: FeatureModule) -> str:
    if "live-footer" in content:
        return content
    return f"{content}{_module_live_footer(profile, module)}"


def _module_live_footer(profile: dict[str, Any], module: FeatureModule) -> str:
    fields = module.data_fields[:4] or ["业务编号", "业务名称", "业务状态", "责任角色"]
    kv_items = "".join(
        f"<div><span>{escape(field)}</span><b>{escape(_operation_sample_value(module, field, index))}</b></div>"
        for index, field in enumerate(fields[:4])
    )
    steps = list(profile.get("process") or _module_semantic_actions(module, limit=4) or ["创建", "更新", "确认", "完成"])[:4]
    audit_items = "".join(
        f"<div><span>{escape(str(step))}</span><b>{escape(_audit_time(index))}</b></div>"
        for index, step in enumerate(steps)
    )
    attachments = [
        (f"{_safe_display_file_stem(module.title)}详情.pdf", "已生成"),
        (f"{_safe_display_file_stem(module.title)}操作留痕.log", "已留痕"),
        (f"{_safe_display_file_stem(module.title)}导出.xlsx", "待导出"),
    ]
    attachment_items = "".join(
        f"<div><span>{escape(name)}</span><b>{escape(state)}</b></div>"
        for name, state in attachments
    )
    return f"""
<div class="live-footer">
  <section class="live-card"><h3>当前{escape(_module_business_subject(module))}详情</h3><div class="kv-grid">{kv_items}</div></section>
  <section class="live-card"><h3>处理轨迹</h3><div class="audit-strip">{audit_items}</div></section>
  <section class="live-card"><h3>附件与导出</h3><div class="attachment-list">{attachment_items}</div></section>
  <section class="live-card"><h3>操作结果</h3>{_business_review_card(profile, module)}</section>
</div>"""


def _module_source_card(profile: dict[str, Any], module: FeatureModule) -> str:
    evidence = _module_source_evidence_from_profile(profile, module)
    if not evidence or not evidence.get("files"):
        file_name = f"{_source_pascal(module.key)}Service"
        rows = [
            ("接口", f"{_source_pascal(module.key)}Controller.list"),
            ("服务", f"{file_name}.query"),
            ("字段", "、".join((module.data_fields or ["业务编号", "业务名称"])[:2])),
        ]
    else:
        rows = [
            ("接口", str(evidence.get("primary_interface") or "")),
            ("服务", str(evidence.get("primary_service") or "")),
            ("字段", "、".join(str(item) for item in (evidence.get("fields") or module.data_fields or [])[:3])),
            ("文件", _source_file_display(evidence)),
        ]
    rows = [(label, _clip(value, 34)) for label, value in rows if str(value).strip()][:4]
    items = "".join(f"<div><span>{escape(label)}</span><b>{escape(value)}</b></div>" for label, value in rows)
    return f"<section class='live-card'><h3>源码接口映射</h3><div class='source-list'>{items}</div></section>"


def _business_review_card(profile: dict[str, Any], module: FeatureModule) -> str:
    states = list(profile.get("states") or ["进行中", "已完成", "需更新"])
    fields = [str(field).strip() for field in (module.data_fields or []) if str(field).strip()]
    focus = fields[:2] or [module.title, "处理结论"]
    actions = _module_semantic_actions(module, limit=1)
    rows = [
        ("当前状态", states[1 % len(states)] if states else "已完成"),
        ("操作内容", actions[0] if actions else "更新当前信息"),
        ("结果依据", "、".join(focus)),
        ("处理结论", _business_review_result(module, profile)),
    ]
    items = "".join(f"<div><span>{escape(label)}</span><b>{escape(_clip(value, 34))}</b></div>" for label, value in rows)
    return f"<div class='source-list business-review-list'>{items}</div>"


def _business_review_result(module: FeatureModule, profile: dict[str, Any]) -> str:
    title = str(getattr(module, "title", "") or "")
    if re.search(r"路径|线路|节点|适配|衔接|交通|运输", title):
        return "节点、方向和服务范围口径一致"
    if re.search(r"统计|报表|指标", title):
        return "统计口径与发布数据一致"
    subjects = list(profile.get("subjects") or [])
    return f"{subjects[0]}信息与当前状态一致" if subjects else f"{_module_business_subject(module)}信息已更新"


def _audit_time(index: int) -> str:
    times = ["09:12", "09:28", "09:36", "09:41", "10:06", "10:22"]
    return f"2026-06-29 {times[index % len(times)]}"


def _freeform_structure_content(
    profile: dict[str, Any],
    blueprint: ProductBlueprint,
    page_kind: str,
    module: FeatureModule | None = None,
    rows: list[list[str]] | None = None,
    filters: str = "",
) -> str:
    structure = dict(profile.get("structure_blueprint") or {})
    page = dict(structure.get(page_kind) or {})
    slots = list(page.get("slots") or [])
    if not slots:
        return ""
    layout = str(page.get("layout") or "asymmetric_grid")
    rendered = []
    for index, slot in enumerate(slots):
        rendered.append(_render_structure_slot(profile, blueprint, page_kind, slot, index, module=module, rows=rows, filters=filters))
    return f"<div class='freeform-grid freeform-{escape(layout)}'>{''.join(rendered)}</div>"


def _render_structure_slot(
    profile: dict[str, Any],
    blueprint: ProductBlueprint,
    page_kind: str,
    slot: dict[str, Any],
    index: int,
    module: FeatureModule | None = None,
    rows: list[list[str]] | None = None,
    filters: str = "",
) -> str:
    kind = str(slot.get("kind") or "focus")
    title = str(slot.get("title") or "业务区域")
    span = _slot_span(slot.get("span"), index)
    modules = ([module] + blueprint.modules[:5]) if module else blueprint.modules
    table_rows = rows or (_module_rows(module, profile) if module else _domain_rows(blueprint.modules, profile, 7))
    if kind == "metrics":
        body = f"<div class='grid'>{_metric_cards(profile['metrics'])}</div>"
    elif kind == "queue":
        body = _queue_list(profile, modules, 6)
    elif kind == "table":
        headers = profile["stat_headers"] if page_kind == "statistics" else profile["table_headers"]
        toolbar = f"<div class='toolbar'>{filters}<span class='button'>处理</span></div>" if filters else ""
        body = f"{toolbar}{_table(headers, table_rows)}"
    elif kind == "chart":
        body = f"{_mini_chart(profile)}<div class='process'>{_process(profile)}</div>"
    elif kind == "timeline":
        body = _timeline(profile)
    elif kind == "map":
        body = _map_board(profile, modules)
    elif kind == "matrix":
        body = _matrix_board(profile, modules)
    elif kind == "ledger":
        body = f"<div class='ledger-toolbar'>{_ledger_boxes(profile)}</div>{_table(profile['table_headers'], table_rows[:5])}"
    elif kind == "kanban":
        body = _kanban_board(profile, modules)
    elif kind == "case":
        body = _case_cards(profile)
    else:
        body = _focus_panel(profile, compact=span <= 4)
    return f"<section class='panel freeform-slot freeform-slot-{escape(kind)}' style='grid-column: span {span};'><h2>{escape(title)}</h2>{body}</section>"


def _slot_span(value: Any, index: int) -> int:
    try:
        span = int(value)
    except Exception:
        span = [8, 4, 6, 6, 4, 4][index % 6]
    return max(3, min(12, span))


def _layout(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    title: str,
    content: str,
    active: str,
    design_brief: dict[str, Any] | None = None,
    *,
    page_key: str = "dashboard",
    page_kind: str = "dashboard",
    module: FeatureModule | None = None,
    interaction_action: str = "",
    interaction_action_key: str = "",
) -> str:
    profile = _profile_for_blueprint(task, blueprint, design_brief)
    variant = str(profile.get("layout_variant") or "classic")
    nav_model = str(profile.get("nav_model") or "side_menu")
    contract = build_local_navigation_contract(
        task,
        blueprint,
        page_key=page_key,
        title=title,
        page_kind=page_kind,
        module=module,
        interaction_action=interaction_action,
        interaction_action_key=interaction_action_key,
        renderer="admin",
        nav_model=nav_model,
    )
    compact_nav = nav_model == "top_tabs" or variant == "workflow"
    nav_html = _contract_nav_items_html(
        list(contract.get("primary_items") or []),
        str(contract.get("active_primary_key") or ""),
        compact=compact_nav,
    )
    workspace_shape = str(profile.get("workspace_shape") or "")
    app_class = f"{variant} nav-{nav_model}"
    if workspace_shape:
        app_class = f"{app_class} shape-{workspace_shape}"
    experience_shape = str(profile.get("experience_shape") or "")
    if experience_shape:
        app_class = f"{app_class} experience-{_css_class_token(experience_shape)}"
    identity_classes = _identity_classes_from_brief(design_brief)
    if identity_classes:
        app_class = f"{app_class} {identity_classes}"
    ribbon = _workspace_ribbon(profile, active, contract)
    top_head = _top_head(task, blueprint, profile, title, active, contract)
    style_vars = _identity_style_vars(profile)
    navigation_attrs = (
        f'data-navigation-contract="{escape(str(contract.get("schema_version") or NAVIGATION_CONTRACT_VERSION))}" '
        f'data-navigation-ready="{"true" if contract.get("ready") else "false"}" '
        f'data-navigation-level="{escape(str(contract.get("level") or ""))}" '
        f'data-navigation-signature="{escape(str(contract.get("hierarchy_signature") or ""))}" '
        f'data-navigation-active-primary="{escape(str(contract.get("active_primary_key") or ""))}" '
        f'data-navigation-active-secondary="{escape(str(contract.get("active_secondary_key") or ""))}" '
        f'data-navigation-back-target="{escape(str((contract.get("back_target") or {}).get("page_key") or ""))}"'
    )
    if nav_model == "top_tabs":
        return f"""
<div class="app {escape(app_class)}" style="{style_vars}" {navigation_attrs}>
  <header class="topbar">
    <div class="brand-block"><div class="brand">{escape(task.software_name)}</div><div class="muted">{escape(task.version)} / {escape(_display_context(task, blueprint))}</div></div>
    <nav class="nav">{nav_html}</nav>
    <div class="top-tools"><span>消息 3</span><span>生产</span><b>{escape(str(profile["user_label"]).replace("当前用户：", ""))}</b></div>
  </header>
  <main class="main">
    {top_head}
    {ribbon}
    {_runtime_module_markers(blueprint)}
    {content}
  </main>
</div>"""
    return f"""
<div class="app {escape(app_class)}" style="{style_vars}" {navigation_attrs}>
  <aside class="sidebar">
    <div class="brand">{escape(task.software_name)}</div>
    <div class="sidebar-subtitle">{escape(_display_context(task, blueprint))}</div>
    <nav class="nav">{nav_html}</nav>
  </aside>
  <main class="main">
    {top_head}
    {ribbon}
    {_runtime_module_markers(blueprint)}
    {content}
  </main>
</div>"""


def _runtime_module_markers(blueprint: ProductBlueprint) -> str:
    markers = "".join(
        f"<span data-module-key='{escape(str(module.key))}'></span>"
        for module in (getattr(blueprint, "modules", []) or [])[:8]
        if str(getattr(module, "key", "") or "").strip()
    )
    return f"<div class='runtime-api-modules' hidden>{markers}</div>" if markers else ""


def _nav_items_html(items: list[str], active: str, compact: bool = False) -> str:
    visible = list(items)
    if compact and len(items) > 7:
        visible = items[:5]
        if active in items and active not in visible:
            visible = items[:4] + [active]
    hidden_count = max(0, len(items) - len(visible))
    label_limit = 10 if compact else 16
    parts = []
    for item in visible:
        item_text = str(item)
        class_name = "active" if item_text == active else ""
        title_attr = f" title=\"{escape(item_text)}\""
        parts.append(f"<span class='{class_name}'{title_attr}>{escape(_clip(item_text, label_limit))}</span>")
    if hidden_count:
        parts.append(f"<span class='nav-more'>+{hidden_count}</span>")
    return "".join(parts)


def _contract_nav_items_html(items: list[dict[str, Any]], active_key: str, compact: bool = False) -> str:
    visible = list(items)
    if compact and len(visible) > 7:
        active_item = next((item for item in visible if str(item.get("key") or "") == active_key), None)
        visible = visible[:5]
        if active_item and active_item not in visible:
            visible = visible[:4] + [active_item]
    hidden_count = max(0, len(items) - len(visible))
    label_limit = 10 if compact else 16
    parts: list[str] = []
    for item in visible:
        key = str(item.get("key") or "")
        label = str(item.get("label") or key or "功能")
        page_key = str(item.get("page_key") or "")
        class_name = "active" if key == active_key else ""
        parts.append(
            f"<span class='{class_name}' data-navigation-primary-item='{escape(key)}' "
            f"data-navigation-page-key='{escape(page_key)}' title=\"{escape(label)}\">{escape(_clip(label, label_limit))}</span>"
        )
    if hidden_count:
        parts.append(f"<span class='nav-more'>+{hidden_count}</span>")
    return "".join(parts)


def _css_class_token(value: str) -> str:
    token = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(value or "").strip().lower()).strip("-")
    return token or "default"


def _identity_classes_from_brief(design_brief: dict[str, Any] | None) -> str:
    if not isinstance(design_brief, dict):
        return ""
    identity = design_brief.get("visual_identity_spec")
    if not isinstance(identity, dict):
        identity = {}
    experience = design_brief.get("product_experience_spec")
    if not isinstance(experience, dict):
        experience = {}
    tokens = []
    for prefix, value in [
        ("identity", identity.get("palette_key") or design_brief.get("palette_key")),
        ("density", identity.get("table_density") or design_brief.get("table_density")),
        ("chart", identity.get("chart_style") or design_brief.get("chart_style")),
        ("surface", identity.get("surface_style") or design_brief.get("surface_style")),
        ("rhythm", identity.get("component_rhythm") or design_brief.get("component_rhythm")),
        ("shell", experience.get("shell") or design_brief.get("experience_shell")),
    ]:
        if value:
            tokens.append(f"{prefix}-{_css_class_token(str(value))}")
    return " ".join(tokens)


def _identity_style_vars(profile: dict[str, Any]) -> str:
    return (
        f"--accent:{profile.get('accent', '#2f6fed')};"
        f"--accent-soft:{profile.get('accent_soft', '#eef6ff')};"
        f"--sidebar:{profile.get('sidebar', '#1f314f')};"
        f"--canvas:{profile.get('canvas', '#eef3f8')};"
    )


def _top_head(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    profile: dict[str, Any],
    title: str,
    active: str,
    contract: dict[str, Any] | None = None,
) -> str:
    subtitle = _display_context(task, blueprint)
    user = str(profile.get("user_label") or "当前用户：责任人员").replace("当前用户：", "")
    contract = contract or {}
    breadcrumb_items = list(contract.get("breadcrumb") or [])
    breadcrumb_html = "<i>/</i>".join(
        f"<span data-navigation-breadcrumb-item='{escape(str(item.get('key') or ''))}' "
        f"data-navigation-page-key='{escape(str(item.get('page_key') or ''))}'>{escape(str(item.get('label') or ''))}</span>"
        for item in breadcrumb_items
        if str(item.get("label") or "").strip()
    )
    if not breadcrumb_html:
        breadcrumb_html = f"<span>{escape(task.software_name)}</span><i>/</i><span>{escape(active)}</span>"
    back_target = contract.get("back_target") if isinstance(contract.get("back_target"), dict) else {}
    back_html = ""
    if back_target and str(back_target.get("page_key") or ""):
        back_html = (
            f"<span class='navigation-back' data-navigation-back-target='{escape(str(back_target.get('page_key') or ''))}'>"
            f"← {escape(str(back_target.get('label') or '返回上级'))}</span>"
        )
    return f"""
    <div class="top">
      <div class="top-main">
        <div class="navigation-context">{back_html}<div class="breadcrumb">{breadcrumb_html}</div></div>
        <div class="title">{escape(title)}</div>
        <div class="muted">{escape(task.version)} · {escape(subtitle)}</div>
      </div>
      <div class="top-tools">
        <span>2026-06-29 09:41</span>
        <span>通知 3</span>
        <span>刷新</span>
        <b>{escape(user)}</b>
      </div>
    </div>"""


def _display_context(task: GenerationTask, blueprint: ProductBlueprint) -> str:
    domain_hint = _domain_display_hint(task, blueprint)
    if domain_hint:
        return domain_hint
    for value in [getattr(blueprint, "industry", ""), getattr(blueprint, "scenario", ""), task.product_type]:
        text = str(value or "").strip()
        if text:
            return _clip(text, 24)
    return "业务管理平台"


def _domain_display_hint(task: GenerationTask, blueprint: ProductBlueprint) -> str:
    text = _profile_context_text(task, blueprint)
    if build_domain_profile(task, blueprint).requires_route_topology:
        return "智慧交通干支线路径适配"
    if re.search(r"手术|手术室|术前|术后|麻醉|科室|医生|护士|排班|排程", text):
        return "医疗手术排班与科室协同"
    return ""


def _is_transport_route_context(blueprint: ProductBlueprint) -> bool:
    return build_domain_profile(blueprint=blueprint).requires_route_topology


def _workspace_ribbon(profile: dict[str, Any], active: str, contract: dict[str, Any] | None = None) -> str:
    contract = contract or {}
    tabs = list(contract.get("secondary_items") or [])
    active_key = str(contract.get("active_secondary_key") or "")
    tab_html = "".join(
        f"<span class='{'active' if str(tab.get('key') or '') == active_key else ''}' "
        f"data-navigation-secondary-item='{escape(str(tab.get('key') or ''))}' "
        f"data-navigation-page-key='{escape(str(tab.get('page_key') or ''))}'>"
        f"{escape(_clip(str(tab.get('label') or '功能'), 10))}</span>"
        for tab in tabs
    )
    workspace_label = f"当前视图：{active or '业务工作台'}"
    style = escape(str(contract.get("secondary_style") or "tabs"))
    return f"""
    <div class="workspace-ribbon navigation-secondary-{style}">
      <div class="tabs">{tab_html}</div>
      <div class="ops"><span>状态：在线</span><span>数据源：业务库</span><span>{escape(_clip(workspace_label, 32))}</span></div>
    </div>"""


def _profile_for_blueprint(task: GenerationTask, blueprint: ProductBlueprint, design_brief: dict[str, Any] | None = None) -> dict[str, Any]:
    profile = _admin_profile(task)
    brief = design_brief or {}
    if brief:
        for key in ["accent", "accent_soft", "sidebar", "canvas", "palette_key", "table_density", "chart_style", "surface_style", "component_rhythm"]:
            if brief.get(key):
                profile[key] = str(brief[key])
        identity = brief.get("visual_identity_spec")
        if isinstance(identity, dict):
            palette = identity.get("palette") if isinstance(identity.get("palette"), dict) else {}
            for key in ["accent", "accent_soft", "sidebar", "canvas"]:
                if palette.get(key):
                    profile[key] = str(palette[key])
            for key in ["palette_key", "table_density", "chart_style", "surface_style", "component_rhythm", "login_pattern"]:
                if identity.get(key):
                    profile[key] = str(identity[key])
            if isinstance(identity.get("module_composition_cycle"), list):
                profile["module_composition_cycle"] = [str(item) for item in identity.get("module_composition_cycle") if str(item).strip()]
        if brief.get("layout_family"):
            profile["layout_variant"] = str(brief["layout_family"])
        if brief.get("nav_model"):
            profile["nav_model"] = str(brief["nav_model"])
        if brief.get("workspace_shape"):
            profile["workspace_shape"] = str(brief["workspace_shape"])
        if brief.get("login_pattern"):
            profile["login_pattern"] = str(brief["login_pattern"])
        if brief.get("structure_blueprint"):
            profile["structure_blueprint"] = dict(brief.get("structure_blueprint") or {})
        if brief.get("semantic_terms"):
            profile["semantic_terms"] = [str(item) for item in list(brief.get("semantic_terms") or []) if str(item).strip()]
        if brief.get("optimized_prompt"):
            profile["optimized_prompt"] = str(brief.get("optimized_prompt") or "")
        if brief.get("layout_signature"):
            profile["layout_signature"] = str(brief.get("layout_signature") or "")
        if isinstance(brief.get("source_ui_evidence"), dict):
            profile["source_ui_evidence"] = dict(brief.get("source_ui_evidence") or {})
        experience_spec = brief.get("product_experience_spec")
        if isinstance(experience_spec, dict):
            profile["experience_shape"] = str(experience_spec.get("experience_shape") or "")
            profile["experience_terminal"] = str(experience_spec.get("terminal") or "")
            profile["experience_shell"] = str(experience_spec.get("shell") or "")
            profile["ui_family"] = str(experience_spec.get("ui_family") or "")
            if experience_spec.get("visual_direction") and not profile.get("visual_mood"):
                profile["visual_mood"] = str(experience_spec.get("visual_direction") or "")
        profile["industry_subtype"] = str(brief.get("industry_subtype") or getattr(blueprint, "industry_subtype", ""))
        profile["visual_mood"] = str(brief.get("visual_mood") or "")
        profile["dashboard_pattern"] = str(brief.get("dashboard_pattern") or "")
        profile["module_pattern"] = str(brief.get("module_pattern") or "")
        if brief.get("domain_terms"):
            terms = [str(item) for item in list(brief.get("domain_terms") or []) if str(item).strip()]
            if terms:
                profile["subjects"] = terms[:6]
                profile["objects"] = (terms[3:9] or terms)[:6]
        if brief.get("metrics"):
            metrics = [str(item) for item in list(brief.get("metrics") or []) if str(item).strip()]
            if metrics:
                profile["metrics"] = [(metric, _metric_value(index)) for index, metric in enumerate(metrics[:4])]
                profile["stat_subjects"] = metrics[:6]
                profile["stat_title"] = str(brief.get("dashboard_pattern") or "产品指标统计")
    if blueprint.target_users:
        profile["user_label"] = f"当前用户：{blueprint.target_users[0]}"
    if blueprint.business_objects:
        profile["subjects"] = blueprint.business_objects[:6]
        profile["objects"] = (blueprint.business_objects[3:9] or blueprint.business_objects)[:6]
    if blueprint.report_metrics:
        profile["metrics"] = [(metric, _metric_value(index)) for index, metric in enumerate(blueprint.report_metrics[:4])]
        profile["stat_subjects"] = blueprint.report_metrics[:6]
        profile["stat_title"] = "产品指标统计"
    else:
        profile["stat_subjects"] = [module.title for module in blueprint.modules[:6]]
    profile["states"] = _business_states(blueprint)
    if profile["states"]:
        profile["stat_status"] = profile["states"][-1]
    if blueprint.workflows:
        workflow = blueprint.workflows[0]
        if isinstance(workflow, dict):
            steps = workflow.get("steps")
            if isinstance(steps, list) and steps:
                profile["process"] = [str(step) for step in steps[:6]]
            name = str(workflow.get("name") or "")
            if name:
                profile["module_focus_title"] = name
    if blueprint.quality_rules:
        focus_cards = []
        for index, rule in enumerate(blueprint.quality_rules[:4]):
            label = f"规则{index + 1}"
            value = "已启用"
            focus_cards.append((label, value, str(rule)))
        if focus_cards:
            profile["focus_cards"] = focus_cards
            profile["focus_title"] = "方案规则看板"
    actions = _business_actions_from_modules(blueprint.modules)
    if actions:
        profile["actions"] = actions
    _sanitize_profile_display_texts(task, blueprint, profile)
    _sanitize_profile_process_vocabulary(blueprint, profile)
    return profile


def _sanitize_profile_display_texts(task: GenerationTask, blueprint: ProductBlueprint, profile: dict[str, Any]) -> None:
    context = _profile_context_text(task, blueprint)
    off_terms = _off_context_profile_terms(context)
    if not off_terms:
        return
    subject = _profile_subject(blueprint)
    replacements = {
        "industry_subtype": _display_context(task, blueprint),
        "visual_mood": blueprint.summary or _display_context(task, blueprint),
        "dashboard_pattern": f"{subject}指标总览",
        "module_pattern": "列表详情",
        "todo_title": f"{subject}待办",
        "focus_title": f"{subject}运行看板",
        "module_focus_title": f"{subject}处理流程",
        "stat_title": f"{subject}统计",
        "layout_signature": f"{_display_context(task, blueprint)}工作区",
    }
    for key, replacement in replacements.items():
        value = str(profile.get(key) or "")
        if _contains_any(value, off_terms):
            profile[key] = replacement
    if _contains_any(" ".join(str(item) for item in profile.get("stat_headers", []) or []), off_terms):
        profile["stat_headers"] = ["业务模块", "业务量", "完成率", "状态"]
    if _contains_any(" ".join(str(item) for item in profile.get("table_headers", []) or []), off_terms):
        profile["table_headers"] = _business_table_headers(blueprint)
    if _contains_any(" ".join(str(item) for item in profile.get("states", []) or []), off_terms):
        profile["states"] = _business_states(blueprint)
    if _contains_any(str(profile.get("stat_status") or ""), off_terms):
        profile["stat_status"] = "已完成"
    if _contains_any(str(profile.get("user_label") or ""), off_terms):
        users = [str(item) for item in (getattr(blueprint, "target_users", []) or []) if str(item).strip()]
        profile["user_label"] = f"当前用户：{users[0] if users else '业务管理员'}"
    if _contains_any(_profile_pairs_text(profile.get("focus_cards")), off_terms):
        metrics = list(getattr(blueprint, "report_metrics", []) or [])[:4]
        profile["focus_cards"] = [
            (metric, _metric_value(index), f"{subject}统计指标")
            for index, metric in enumerate(metrics)
        ] or profile.get("focus_cards", [])
    if _contains_any(_profile_pairs_text(profile.get("metrics")), off_terms):
        metric_names = list(getattr(blueprint, "report_metrics", []) or [])[:4]
        if not metric_names:
            metric_names = [f"{subject}数量", f"{subject}完成率", f"{subject}进行中", f"{subject}预警"]
        profile["metrics"] = [(metric, _metric_value(index)) for index, metric in enumerate(metric_names[:4])]
    if _contains_any(" ".join(str(item) for item in profile.get("filters", []) or []), off_terms):
        profile["filters"] = _business_filter_labels(blueprint)
    if _contains_any(" ".join(str(item) for item in profile.get("subjects", []) or []), off_terms):
        profile["subjects"] = _business_subjects(blueprint)
    if _contains_any(" ".join(str(item) for item in profile.get("objects", []) or []), off_terms):
        profile["objects"] = _business_subjects(blueprint)[3:9] or _business_subjects(blueprint)
    if _contains_any(" ".join(str(item) for item in profile.get("process", []) or []), off_terms):
        profile["process"] = _business_process_steps(blueprint)


def _sanitize_profile_process_vocabulary(blueprint: ProductBlueprint, profile: dict[str, Any]) -> None:
    explicit_parts: list[str] = []
    for module in getattr(blueprint, "modules", []) or []:
        explicit_parts.extend(_module_semantic_actions(module, limit=8))
        for spec in getattr(module, "operation_specs", []) or []:
            if not isinstance(spec, dict):
                continue
            explicit_parts.extend(
                str(spec.get(key) or "")
                for key in ("pre_state", "preState", "post_state", "postState", "result_evidence", "resultEvidence")
            )
    for workflow in getattr(blueprint, "workflows", []) or []:
        if isinstance(workflow, dict):
            explicit_parts.append(str(workflow.get("name") or ""))
            explicit_parts.extend(str(step) for step in (workflow.get("steps") or []))
    explicit_text = " ".join(part for part in explicit_parts if part)
    states = _business_states(blueprint)
    actions = [_operation_label(action) for module in getattr(blueprint, "modules", []) or [] for action in (module.operations or [])]
    actions = [action for action in actions if action]
    subject = _profile_subject(blueprint)
    role = next((str(item) for item in (getattr(blueprint, "target_users", []) or []) if str(item).strip()), "责任人员")
    replacement = {
        "待复核": states[0] if states else "待确认",
        "待审核": states[0] if states else "待确认",
        "待处理": states[0] if states else "待确认",
        "操作日志": f"{subject}结果记录",
        "业务台账": f"{subject}清单",
        "模块台账": "模块清单",
        "台账": "清单",
        "复核": actions[0] if actions else "处理",
        "审核": actions[0] if actions else "处理",
        "归档": states[-1] if states else "完成",
        "系统管理员": role,
    }
    controlled = ("待复核", "待审核", "待处理", "操作日志", "业务台账", "模块台账", "台账", "复核", "审核", "归档", "系统管理员")

    def clean(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: clean(item) for key, item in value.items()}
        if isinstance(value, list):
            return [clean(item) for item in value]
        if isinstance(value, tuple):
            return tuple(clean(item) for item in value)
        if not isinstance(value, str):
            return value
        result = value
        for term in controlled:
            if term in explicit_text or term not in result:
                continue
            result = result.replace(term, replacement[term])
        return result

    cleaned = clean(profile)
    profile.clear()
    profile.update(cleaned)


def _profile_context_text(task: GenerationTask, blueprint: ProductBlueprint) -> str:
    parts = [
        task.software_name,
        task.product_type,
        task.feature_hint,
        getattr(blueprint, "industry", ""),
        getattr(blueprint, "purpose", ""),
        getattr(blueprint, "summary", ""),
        getattr(blueprint, "scenario", ""),
        getattr(blueprint, "positioning", ""),
    ]
    for attr in ["business_objects", "report_metrics", "quality_rules", "target_users", "roles"]:
        values = getattr(blueprint, attr, []) or []
        parts.extend(str(item) for item in values[:12] if str(item).strip())
    for module in getattr(blueprint, "modules", []) or []:
        parts.extend(
            [
                str(getattr(module, "title", "") or ""),
                str(getattr(module, "description", "") or ""),
                " ".join(str(item) for item in (getattr(module, "operations", []) or [])[:5]),
            ]
        )
    return " ".join(str(item) for item in parts if str(item).strip())


def _off_context_profile_terms(context: str) -> list[str]:
    business_context = _strip_generic_product_type_terms(context)
    groups = [
        ["Kubernetes", "kubernetes", "K8S", "k8s", "k8s_ops", "cmp_platform", "容器", "集群", "命名空间", "Pod", "镜像", "工作负载", "发布流水线", "弹性伸缩", "资源水位", "集群健康", "节点负载", "云资源", "云平台", "云主机", "云运维", "DevOps"],
        ["景区", "票务", "门禁", "闸机", "游客", "年卡", "入园", "客流"],
        ["医疗", "医院", "手术", "手术室", "术前", "术后", "术式", "麻醉", "科室", "医生", "护士", "患者", "病历", "处方", "诊疗", "排班", "排程"],
    ]
    terms: list[str] = []
    for group in groups:
        if not any(term in business_context for term in group):
            terms.extend(group)
    return terms


def _strip_generic_product_type_terms(context: str) -> str:
    text = str(context or "")
    for term in ["云计算软件", "智慧城市软件", "医疗软件", "APP", "小程序", "平台"]:
        text = text.replace(term, "")
    return text


def _profile_subject(blueprint: ProductBlueprint) -> str:
    if getattr(blueprint, "business_objects", None):
        return _clip(str(blueprint.business_objects[0]), 10)
    if getattr(blueprint, "modules", None):
        return _clip(str(blueprint.modules[0].title), 10)
    return "业务"


def _profile_pairs_text(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    return " ".join(
        " ".join(str(part) for part in item)
        if isinstance(item, (list, tuple))
        else str(item)
        for item in value
    )


def _contains_any(value: str, terms: list[str]) -> bool:
    return any(term and term in value for term in terms)


def _business_subjects(blueprint: ProductBlueprint) -> list[str]:
    values = [str(item) for item in (getattr(blueprint, "business_objects", []) or []) if str(item).strip()]
    if not values:
        values = [str(module.title) for module in (getattr(blueprint, "modules", []) or []) if str(module.title).strip()]
    return values[:6] or ["当前事项", "状态信息", "执行任务", "统计指标"]


def _business_filter_labels(blueprint: ProductBlueprint) -> list[str]:
    labels: list[str] = []
    for module in (getattr(blueprint, "modules", []) or [])[:3]:
        labels.extend(str(field) for field in (getattr(module, "data_fields", []) or [])[:2] if str(field).strip())
    labels = [label for label in labels if len(label) <= 12]
    return labels[:4] or ["关键字", "状态", "时间范围", "责任科室"]


def _business_table_headers(blueprint: ProductBlueprint) -> list[str]:
    subject = _profile_subject(blueprint)
    return [f"{subject}记录", "关联模块", "处理状态", "操作"]


def _business_states(blueprint: ProductBlueprint) -> list[str]:
    explicit_states: list[str] = []
    for module in (getattr(blueprint, "modules", []) or [])[:8]:
        for spec in getattr(module, "operation_specs", []) or []:
            if not isinstance(spec, dict):
                continue
            for key in ("pre_state", "preState", "post_state", "postState"):
                value = str(spec.get(key) or "").strip()
                if value and value not in explicit_states and len(value) <= 14:
                    explicit_states.append(value)
    if explicit_states:
        return explicit_states[:6]
    context = " ".join(
        str(item)
        for item in [
            getattr(blueprint, "industry", ""),
            getattr(blueprint, "scenario", ""),
            getattr(blueprint, "summary", ""),
            " ".join(getattr(blueprint, "business_objects", []) or []),
        ]
        if str(item).strip()
    )
    if re.search(r"手术|手术室|术前|术后|麻醉|排班|排程", context):
        return ["待确认", "已排班", "进行中", "已完成"]
    return ["正常", "进行中", "已完成", "已更新"]


def _business_process_steps(blueprint: ProductBlueprint) -> list[str]:
    for workflow in getattr(blueprint, "workflows", []) or []:
        if isinstance(workflow, dict):
            steps = [str(step) for step in (workflow.get("steps") or []) if str(step).strip()]
            if steps:
                return steps[:6]
    actions: list[str] = []
    for module in (getattr(blueprint, "modules", []) or [])[:4]:
        for action in _module_semantic_actions(module, limit=3):
            if action not in actions:
                actions.append(action)
    return actions[:6] or ["选择事项", "更新信息", "确认结果", "完成操作"]


def _business_actions_from_modules(modules: list[FeatureModule]) -> list[str]:
    actions: list[str] = []
    for module in modules:
        operations = [_operation_label(operation) for operation in module.operations if operation]
        operations = [operation for operation in operations if operation]
        if not operations:
            continue
        parts = operations[:2]
        if not any("导出" in operation for operation in parts):
            parts.append("导出")
        actions.append(" / ".join(parts[:3]))
    return actions[:6]


def _module_semantic_actions(module: FeatureModule, *, limit: int = 3) -> list[str]:
    actions: list[str] = []
    for spec in getattr(module, "operation_specs", []) or []:
        if not isinstance(spec, dict):
            continue
        label = str(spec.get("label") or spec.get("action") or spec.get("name") or "").strip()
        if label and label not in actions:
            actions.append(label)
    for value in getattr(module, "operations", []) or []:
        label = _operation_label(value)
        if label and label not in actions:
            actions.append(label)
    return actions[:limit]


def _module_operation_specs(module: FeatureModule, action: str = "") -> list[dict[str, Any]]:
    specs = [spec for spec in (getattr(module, "operation_specs", []) or []) if isinstance(spec, dict)]
    action_text = str(action or "").strip()
    if not action_text:
        return specs
    matched = []
    for spec in specs:
        label = str(spec.get("label") or spec.get("action") or spec.get("name") or "").strip()
        if label and (action_text in label or label in action_text):
            matched.append(spec)
    return matched or specs


def _module_operation_states(module: FeatureModule) -> list[str]:
    states: list[str] = []
    for spec in _module_operation_specs(module):
        for key in ("pre_state", "preState", "post_state", "postState"):
            value = str(spec.get(key) or "").strip()
            if value and value not in states and len(value) <= 14:
                states.append(value)
    return states[:4] or ["待确认", "进行中", "已完成", "已更新"]


def _module_operation_transition(module: FeatureModule, action: str = "") -> tuple[str, str]:
    for spec in _module_operation_specs(module, action):
        pre_state = str(spec.get("pre_state") or spec.get("preState") or "").strip()
        post_state = str(spec.get("post_state") or spec.get("postState") or "").strip()
        if pre_state or post_state:
            states = _module_operation_states(module)
            return pre_state or states[0], post_state or states[-1]
    states = _module_operation_states(module)
    return states[0], states[-1]


def _module_operation_result_status(module: FeatureModule, action: str = "") -> str:
    return _module_operation_transition(module, action)[1]


def _module_operation_role(module: FeatureModule, action: str = "") -> str:
    for spec in _module_operation_specs(module, action):
        role = str(spec.get("role") or "").strip()
        if role:
            return _clip(role, 12)
    return "责任人员"


def _module_result_evidence(module: FeatureModule, action: str = "") -> str:
    for spec in _module_operation_specs(module, action):
        value = str(spec.get("result_evidence") or spec.get("resultEvidence") or "").strip()
        if value:
            return _clip(value, 24)
    return f"{_module_business_subject(module)}状态和更新时间"


def _module_action_buttons(module: FeatureModule, *, fallback: list[str]) -> str:
    actions = _module_semantic_actions(module, limit=3) or list(fallback)
    return "".join(f'<span class="button">{escape(_clip(action, 10))}</span>' for action in actions[:3])


def _module_business_subject(module: FeatureModule) -> str:
    title = str(getattr(module, "title", "") or "").strip()
    for suffix in ("智能管理平台", "管理平台", "管理系统", "信息系统", "工作台", "管理", "平台", "系统", "模块"):
        if title.endswith(suffix) and len(title) > len(suffix) + 1:
            title = title[: -len(suffix)].strip()
            break
    return _clip(title or "事项", 12)


def _operation_label(value: str) -> str:
    text = str(value).strip()
    match = re.search(r"['\"](?:name|title|operation|label|value)['\"]\s*:\s*['\"]([^'\"]+)['\"]", text)
    if match:
        return match.group(1).strip()
    if text.startswith("{") and text.endswith("}"):
        return ""
    return text


def _triage_stack(profile: dict[str, Any], modules: list[FeatureModule]) -> str:
    items = []
    states = list(profile.get("states") or ["计划中", "进行中", "已完成"])
    for index, module in enumerate((modules or [])[:6]):
        state = states[index % len(states)]
        items.append(
            f"<div class='triage-item'><strong>{escape(module.title)}</strong><span>{escape(state)} / {escape(_metric_value(index))}</span></div>"
        )
    if not items:
        items.append("<div class='triage-item'><strong>暂无新增事项</strong><span>0</span></div>")
    return f"<div class='triage-stack'>{''.join(items)}</div>"


def _ledger_boxes(profile: dict[str, Any]) -> str:
    metrics = list(profile.get("metrics") or [])[:5]
    return "".join(
        f"<div class='ledger-box'><span>{escape(label)}</span><strong>{escape(value)}</strong></div>"
        for label, value in metrics
    )


def _lane_steps(profile: dict[str, Any]) -> str:
    steps = list(profile.get("process") or ["选择", "更新", "确认", "完成"])[:5]
    return "".join(
        f"<div class='lane-step'><b>{index + 1:02d}</b><strong>{escape(str(step))}</strong><span>{escape(_pipeline_detail(profile, None, index))}</span></div>"
        for index, step in enumerate(steps)
    )


def _case_cards(profile: dict[str, Any]) -> str:
    subjects = list(profile.get("subjects") or [])[:4]
    states = list(profile.get("states") or ["正常", "进行中", "已完成"])
    cards = []
    for index, subject in enumerate(subjects):
        cards.append(
            f"<div class='case-card'><span>{escape(str(subject))}</span><strong>{escape(_metric_value(index))}</strong><small>{escape(states[index % len(states)])}</small></div>"
        )
    return "".join(cards)


def _kanban_board(profile: dict[str, Any], modules: list[FeatureModule]) -> str:
    stages = list(profile.get("process") or ["计划中", "进行中", "待确认", "已完成"])[:4]
    cards: list[str] = []
    source_modules = modules or []
    for stage_index, stage in enumerate(stages):
        items = []
        for item_index, module in enumerate(source_modules[stage_index:: max(1, len(stages))][:3]):
            status = profile["states"][(stage_index + item_index) % len(profile["states"])]
            items.append(
                f"<div class='kanban-card'><strong>{escape(module.title)}</strong><span>{escape(module.description)}</span><small>{escape(status)} · {escape(_metric_value(stage_index + item_index))}</small></div>"
            )
        if not items:
            items.append(f"<div class='kanban-card'><strong>{escape(stage)}任务</strong><span>暂无新的处理事项</span><small>0</small></div>")
        cards.append(f"<div class='kanban-col'><h3>{escape(str(stage))}</h3>{''.join(items)}</div>")
    return f"<div class='kanban-board'>{''.join(cards)}</div>"


def _matrix_board(profile: dict[str, Any], modules: list[FeatureModule]) -> str:
    subjects = list(profile.get("subjects") or [])
    modules = modules or []
    cells = []
    for index in range(9):
        module = modules[index % len(modules)] if modules else None
        label = subjects[index % len(subjects)] if subjects else (module.title if module else f"业务项{index + 1}")
        value = _metric_value(index)
        state = profile["states"][index % len(profile["states"])]
        cells.append(
            f"<div class='matrix-cell'><span>{escape(label)}</span><strong>{escape(value)}</strong><small>{escape(module.title if module else state)} · {escape(state)}</small></div>"
        )
    return f"<div class='matrix-board'>{''.join(cells)}</div>"


def _metric_value(index: int) -> str:
    values = ["1,286", "86.4%", "72", "98.7%", "3.2万", "12.6万"]
    return values[index % len(values)]


def _table(headers: Iterable[str], rows: Iterable[Iterable[str]]) -> str:
    header_items = [str(item) for item in headers]
    row_items = [list(row) for row in rows]
    head = "<th class='check-col'><span class='check-dot'></span></th>" + "".join(
        f"<th class='{escape(_table_column_class(item, index, len(header_items)))}' data-field='{escape(str(item))}'>{escape(str(item))}</th>"
        for index, item in enumerate(header_items)
    )
    body = "".join(_table_row(row, index, header_items) for index, row in enumerate(row_items))
    total = max(128, len(row_items) * 23)
    return f"""
<div class="table-frame">
  <div class="table-scroll"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>
  <div class="table-footer">
    <span>已选 2 条 · 共 {total} 条 · 每页 20 条</span>
    <div class="pager"><span>&lt;</span><span class="active">1</span><span>2</span><span>3</span><span>&gt;</span></div>
  </div>
</div>"""


def _table_row(row: list[Any], index: int, headers: list[str] | None = None) -> str:
    cells: list[str] = ["<td class='check-col'><span class='check-dot'></span></td>"]
    for cell_index, value in enumerate(row):
        field = headers[cell_index] if headers and cell_index < len(headers) else ""
        cells.append(_cell(value, index=index, cell_index=cell_index, field=field))
    return "<tr>" + "".join(cells) + "</tr>"


def _cell(value: str, index: int = 0, cell_index: int = 0, field: str = "") -> str:
    text = escape(str(value))
    data_field = escape(str(field or ""))
    class_name = escape(_table_column_class(field, cell_index, 0))
    class_attr = f" class='{class_name}'" if class_name else ""
    warn_values = {"高风险", "待处置", "质量预警", "漂移预警", "告警中", "库存预警", "资源告警", "边缘告警"}
    status_values = {"正常", "已归档", "待处理", "进行中", "待批改", "已完成", "待跟进", "待复核", "已结算", "待分诊", "诊疗中", "待审核", "已发布", "采集中", "已同步", "在线", "待巡检", "已接入", "已修复", "已审计", "运行中", "待校验", "已入仓", "训练中", "已上线", "待支付", "已退款", "体验中", "待校准", "已激活", "待维护", "已预约", "已核销", "已核验"}
    if cell_index == 0:
        code = f"YW-20260629-{index + 1001}"
        return f"<td{class_attr} data-field='{data_field}'><div class='entity-cell'><b>{text}</b><small class='mono'>{code}</small></div></td>"
    if text in warn_values:
        return f"<td{class_attr} data-field='{data_field}'><span class='status warn'>{text}</span></td>"
    if text in status_values:
        return f"<td{class_attr} data-field='{data_field}'><span class='status'>{text}</span></td>"
    if cell_index >= 3 or " / " in text:
        actions = [part.strip() for part in str(value).split("/") if part.strip()][:3]
        action_html = "".join(f"<span>{escape(action)}</span>" for action in actions)
        return f"<td{class_attr} data-field='{data_field}'><div class='row-actions'>{action_html}</div></td>"
    return f"<td{class_attr} data-field='{data_field}'>{text}</td>"


def _table_column_class(field: Any, index: int, total: int) -> str:
    label = str(field or "")
    classes: list[str] = []
    if index == 0:
        classes.append("col-primary")
    if re.search(r"状态|进度", label):
        classes.append("col-status")
    if re.search(r"操作|动作", label) or (total and index >= max(0, total - 1)):
        classes.append("col-actions")
    if re.search(r"编号|编码", label):
        classes.append("col-code")
    if re.search(r"名称|路径|线路|节点|范围|区域", label):
        classes.append("col-wide")
    return " ".join(classes)


def _metric_cards(metrics: list[tuple[str, str]]) -> str:
    return "".join(f"<div class='card metric'><span>{escape(label)}</span><strong>{escape(value)}</strong></div>" for label, value in metrics[:4])


def _risk_tiles(profile: dict[str, Any]) -> str:
    cards = list(profile["metrics"][:2]) + [(label, value) for label, value, _desc in profile["focus_cards"][:2]]
    html = "".join(
        f"<div class='risk-tile'><span>{escape(label)}</span><strong>{escape(value)}</strong><small>{escape(_risk_hint(index, profile))}</small></div>"
        for index, (label, value) in enumerate(cards[:4])
    )
    return f"<div class='risk-strip'>{html}</div>"


def _risk_hint(index: int, profile: dict[str, Any]) -> str:
    hints = ["实时监测", "风险事项", "规则命中", str(profile.get("stat_status", "已完成"))]
    return hints[index % len(hints)]


def _filter_toolbar(profile: dict[str, Any]) -> str:
    return "".join(f"<span class='input'>{escape(label)}</span>" for label in profile["filters"])


def _quick_buttons(modules: list[FeatureModule]) -> str:
    return "".join(f"<span class='button'>{escape(module.title)}</span>" for module in modules[:4])


def _queue_list(profile: dict[str, Any], modules: list[FeatureModule], count: int) -> str:
    rows = _domain_rows(modules, profile, count)
    items = []
    for index, row in enumerate(rows, start=1):
        title = row[0]
        detail = f"{row[1]} / {row[3]}"
        state = row[2]
        badge_class = "status warn" if state in {"高风险", "待处置", "质量预警", "漂移预警", "告警中", "库存预警", "资源告警", "边缘告警"} else "status"
        items.append(
            f"<div class='queue-item'><div><strong>{escape(title)}</strong><small>{escape(detail)}</small></div>"
            f"<span class='{badge_class}'>{escape(state)}</span></div>"
        )
    return f"<div class='queue-list'>{''.join(items)}</div>"


def _map_board(profile: dict[str, Any], modules: list[FeatureModule]) -> str:
    labels = [module.title for module in modules[:5]] or list(profile["subjects"][:5])
    positions = [(10, 18), (56, 12), (72, 42), (28, 58), (48, 73)]
    line_specs = [
        (13, 31, 47, -7, "main"),
        (56, 25, 22, 24, "branch"),
        (35, 63, 24, -18, "branch"),
        (49, 74, 27, -34, "main"),
    ]
    lines = "".join(
        f"<span class='route-line {'branch' if kind == 'branch' else ''}' style='left:{x}%;top:{y}%;width:{width}%;transform:rotate({rotate}deg)'></span>"
        for x, y, width, rotate, kind in line_specs[: max(1, min(4, len(labels) - 1))]
    )
    pins = []
    for index, label in enumerate(labels[:5]):
        x, y = positions[index % len(positions)]
        state = profile["states"][index % len(profile["states"])]
        code = _route_node_code(index)
        pins.append(
            f"<div class='map-pin' style='left:{x}%;top:{y}%'>{escape(_clip(label, 14))}<small>{escape(code)} · {escape(state)}</small></div>"
        )
    legend = "<div class='map-legend'><span>干线</span><span>支线接驳</span><span>时窗 09:00-11:30</span></div>"
    return f"<div class='map-board'>{lines}{''.join(pins)}{legend}</div>"


def _route_node_code(index: int) -> str:
    values = ["TR-HX-1001", "BR-JR-2002", "ND-PD-3103", "MT-LG-4104", "RL-SH-5205"]
    return values[index % len(values)]


def _pipeline_cards(profile: dict[str, Any], module: FeatureModule | None = None) -> str:
    process = list(profile["process"][:4])
    while len(process) < 4:
        process.append(f"阶段{len(process) + 1}")
    values = [value for _label, value in profile["metrics"][:4]]
    html = "".join(
        f"<div class='pipeline-card'><span>{escape(step)}</span><strong>{escape(values[index % len(values)])}</strong><small>{escape(_pipeline_detail(profile, module, index))}</small></div>"
        for index, step in enumerate(process[:4])
    )
    return f"<div class='pipeline-grid'>{html}</div>"


def _pipeline_detail(profile: dict[str, Any], module: FeatureModule | None, index: int) -> str:
    if module and index == 0:
        return module.title
    subjects = profile["subjects"]
    return subjects[index % len(subjects)]


def _timeline(profile: dict[str, Any]) -> str:
    steps = list(profile["process"][:5])
    cards = list(profile["focus_cards"])
    items = []
    for index, step in enumerate(steps, start=1):
        label, value, desc = cards[(index - 1) % len(cards)]
        items.append(
            f"<div class='timeline-step' data-step='{index}'><strong>{escape(step)} / {escape(label)}：{escape(value)}</strong>"
            f"<small>{escape(desc)}</small></div>"
        )
    return f"<div class='timeline'>{''.join(items)}</div>"


def _stat_rows(profile: dict[str, Any]) -> list[list[str]]:
    return [
        [metric, f"{index * 238}", f"{88 + index % 9}%", profile["stat_status"]]
        for index, metric in enumerate(profile["stat_subjects"][:6], start=1)
    ]


def _domain_rows(modules: list[FeatureModule], profile: dict[str, Any], count: int) -> list[list[str]]:
    rows: list[list[str]] = []
    modules = modules or [FeatureModule("business", "业务模块", "业务处理", ["BusinessLedger"])]
    for index in range(count):
        module = modules[index % len(modules)]
        rows.append(
            [
                _domain_row_name(module, profile, index),
                _humanize_visible_text(profile["objects"][index % len(profile["objects"])]),
                profile["states"][index % len(profile["states"])],
                profile["actions"][index % len(profile["actions"])],
            ]
        )
        if module.title and index % 2 == 1:
            rows[-1][1] = module.title
    return rows


def _domain_row_name(module: FeatureModule | None, profile: dict[str, Any], index: int) -> str:
    if module:
        names = _business_record_names_for_ui(module)
        if names:
            return names[index % len(names)]
    subjects = [str(item).strip() for item in (profile.get("subjects") or []) if str(item).strip()]
    value = subjects[index % len(subjects)] if subjects else "当前事项"
    value = re.sub(r"记录\d{2,}$", "", value)
    if value == "业务记录":
        return "当前事项"
    return value or "当前事项"


def _module_rows(module: FeatureModule, profile: dict[str, Any]) -> list[list[str]]:
    rows: list[list[str]] = []
    headers = list(profile.get("table_headers") or [])
    field_headers = [header for header in headers if header not in {"状态", "操作", "处理状态", "诊疗状态", "医疗操作", "教学操作", "城市操作", "数据操作", "算法操作", "APP操作", "小程序业务", "小程序操作", "5G操作", "VR操作", "设备操作", "云平台操作", "处置动作", "地图操作"}]
    if len(field_headers) >= 3:
        for index in range(6):
            values = [_operation_sample_value(module, field, field_index + index) for field_index, field in enumerate(field_headers[:3])]
            values.append(profile["states"][(index + 1) % len(profile["states"])])
            values.append(profile["actions"][index % len(profile["actions"])])
            rows.append(values)
        return rows
    entities = module.entities or ["BusinessRecord", "BusinessQuery"]
    for index in range(6):
        entity = entities[index % len(entities)]
        rows.append(
            [
                f"{module.title}{index + 1:03d}",
                _business_object_label(entity, profile, index),
                profile["states"][(index + 1) % len(profile["states"])],
                profile["actions"][index % len(profile["actions"])],
            ]
        )
    return rows


def _business_object_label(entity: str, profile: dict[str, Any], index: int) -> str:
    if entity and any("\u4e00" <= char <= "\u9fff" for char in entity):
        return entity
    return profile["objects"][index % len(profile["objects"])]


def _focus_panel(profile: dict[str, Any], compact: bool = False) -> str:
    cards = profile["focus_cards"][:2 if compact else 4]
    return "<div class='focus-grid'>" + "".join(
        f"<div class='focus-card'><span>{escape(label)}</span><strong>{escape(value)}</strong><small>{escape(desc)}</small></div>"
        for label, value, desc in cards
    ) + "</div>"


def _process(profile: dict[str, Any]) -> str:
    return "".join(f"<span>{escape(item)}</span>" for item in profile["process"])


def _mini_chart(profile: dict[str, Any]) -> str:
    labels = ["06-24", "06-25", "06-26", "06-27", "06-28", "06-29"]
    bars = "".join(
        f"<span class='bar' aria-label='{labels[index % len(labels)]}' style='height:{int(value)}%'></span>"
        for index, value in enumerate(profile["chart_values"])
    )
    metric_name = str((profile.get("metrics") or [("业务量", "")])[0][0])
    return (
        "<div class='mini-chart'>"
        f"<div class='mini-bars'>{bars}</div>"
        f"<div class='chart-meta'><span>{escape(metric_name)} · 06-24 至 06-29</span><span>单位：条 / %</span></div>"
        "</div>"
    )


def _gems(count: int) -> str:
    classes = ["a", "b", "c", "d", "e", "f"]
    return "".join(f"<span class='gem {classes[index % len(classes)]}'></span>" for index in range(count))


def _level_nodes() -> str:
    points = [(54, 420), (142, 355), (245, 405), (345, 305), (448, 350), (532, 245), (470, 135), (340, 190)]
    return "".join(
        f"<div class='level-node' style='left:{x}px;top:{y}px'>{index}</div>"
        for index, (x, y) in enumerate(points, start=29)
    )


def _to_map(items: list[UiScreenshot]) -> dict[str, UiScreenshot]:
    return {item.key: item for item in items}


def _render_fallback_images(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    screenshots: list[UiScreenshot],
    ui_dir: Path,
) -> None:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return

    font_regular = _font(ImageFont, 18)
    font_small = _font(ImageFont, 14)
    font_title = _font(ImageFont, 28)
    font_metric = _font(ImageFont, 32)

    for item in screenshots:
        path = ui_dir / f"{item.key}.png"
        game = is_game_like(task, blueprint)
        mobile = (not game) and is_mobile_app_like(task, blueprint)
        image_size = (
            (GAME_VIEWPORT["width"], GAME_VIEWPORT["height"])
            if game
            else (MOBILE_VIEWPORT["width"], MOBILE_VIEWPORT["height"])
            if mobile
            else (ADMIN_VIEWPORT["width"], ADMIN_VIEWPORT["height"])
        )
        image = Image.new("RGB", image_size, "#eef2f6")
        draw = ImageDraw.Draw(image)
        if game:
            _draw_game_phone_page(draw, task, blueprint, item, font_title, font_regular, font_small, font_metric)
        elif mobile:
            _draw_mobile_app_page(draw, task, blueprint, item, font_title, font_regular, font_small, font_metric)
        elif item.key == "login":
            _draw_login(draw, task, blueprint, font_title, font_regular, font_small)
        else:
            _draw_app_page(draw, task, blueprint, item, font_title, font_regular, font_small, font_metric)
        image.save(path)
        item.image_path = str(path)
        item.width, item.height = image_size


def _font(ImageFont, size: int):
    candidates = [
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simsun.ttc",
        "C:/Windows/Fonts/simhei.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _draw_login(draw, task: GenerationTask, blueprint: ProductBlueprint, title_font, regular_font, small_font) -> None:
    draw.rectangle((0, 0, 790, 820), fill="#1f314f")
    draw.rectangle((790, 0, 1280, 820), fill="#ffffff")
    draw.text((72, 190), task.software_name, fill="#ffffff", font=title_font)
    draw.text((72, 245), _clip(blueprint.summary, 42), fill="#dbe8ff", font=regular_font)
    draw.text((72, 288), _clip(blueprint.industry, 36), fill="#9fc2ff", font=small_font)
    draw.text((850, 180), "系统登录", fill="#1f2937", font=title_font)
    fields = [("账号", "请输入用户名"), ("密码", "请输入密码"), ("验证码", "请输入图形验证码")]
    y = 250
    for label, placeholder in fields:
        draw.text((850, y), label, fill="#52637a", font=small_font)
        draw.rounded_rectangle((850, y + 28, 1190, y + 76), radius=8, outline="#ccd6e3", fill="#fbfdff")
        draw.text((866, y + 42), placeholder, fill="#64748b", font=regular_font)
        y += 96
    draw.rounded_rectangle((850, y + 12, 1190, y + 62), radius=8, fill="#2f6fed")
    draw.text((990, y + 27), "登录系统", fill="#ffffff", font=regular_font)


def _draw_app_page(draw, task: GenerationTask, blueprint: ProductBlueprint, item: UiScreenshot, title_font, regular_font, small_font, metric_font) -> None:
    draw.rectangle((0, 0, 220, 820), fill="#1f314f")
    draw.text((24, 30), _clip(task.software_name, 12), fill="#ffffff", font=regular_font)
    nav = ["系统首页"] + [module.title for module in blueprint.modules[:6]] + ["统计报表页", "系统设置页"]
    y = 90
    for nav_item in nav:
        active = nav_item in {item.title, "系统首页" if item.key == "dashboard" else "", "统计报表页" if item.key == "statistics" else ""}
        draw.rounded_rectangle((18, y, 202, y + 40), radius=7, fill="#2f6fed" if active else "#294260")
        draw.text((32, y + 10), _clip(nav_item, 12), fill="#ffffff", font=small_font)
        y += 48

    draw.rounded_rectangle((244, 24, 1254, 86), radius=8, outline="#dde5ef", fill="#ffffff")
    draw.text((266, 42), item.title, fill="#1f2937", font=title_font)
    users = [str(item) for item in (getattr(blueprint, "target_users", []) or []) if str(item).strip()]
    draw.text((1030, 48), f"当前用户：{users[0] if users else '责任人员'}", fill="#64748b", font=small_font)

    subject = _profile_subject(blueprint)
    metric_names = [str(item) for item in (getattr(blueprint, "report_metrics", []) or []) if str(item).strip()]
    defaults = [f"{subject}数量", f"{subject}进行中", f"{subject}预警", f"{subject}完成率"]
    metric_names = (metric_names + [item for item in defaults if item not in metric_names])[:4]
    metric_values = ["128", "36", "7", "92.6%"]
    metrics = list(zip(metric_names[:4], metric_values))
    for index, (label, value) in enumerate(metrics):
        x = 244 + index * 252
        draw.rounded_rectangle((x, 112, x + 230, 210), radius=8, outline="#dde5ef", fill="#ffffff")
        draw.text((x + 18, 132), label, fill="#64748b", font=small_font)
        draw.text((x + 18, 160), value, fill="#1f2937", font=metric_font)

    draw.rounded_rectangle((244, 236, 1254, 760), radius=8, outline="#dde5ef", fill="#ffffff")
    draw.text((266, 260), item.caption, fill="#52637a", font=regular_font)
    draw.rectangle((266, 310, 1232, 352), fill="#f8fafc")
    headers = ["业务名称", "所属模块", "状态", "操作"]
    for index, header in enumerate(headers):
        draw.text((286 + index * 230, 322), header, fill="#52637a", font=small_font)
    rows = blueprint.modules[:6] or []
    for row_index, module in enumerate(rows, start=1):
        y = 352 + row_index * 54
        draw.line((266, y - 10, 1232, y - 10), fill="#edf1f6")
        values = [f"{module.title}记录{row_index:03d}", module.title, "正常", "查看 / 编辑"]
        for col_index, value in enumerate(values):
            draw.text((286 + col_index * 230, y + 6), _clip(value, 16), fill="#1f2937", font=small_font)


def _draw_mobile_app_page(draw, task: GenerationTask, blueprint: ProductBlueprint, item: UiScreenshot, title_font, regular_font, small_font, metric_font) -> None:
    draw.rectangle((0, 0, 720, 1280), fill="#f4f6fb")
    draw.text((30, 14), "9:41", fill="#29364a", font=small_font)
    draw.text((604, 14), "5G 100%", fill="#29364a", font=small_font)
    draw.text((34, 72), _clip(item.title, 16), fill="#172033", font=title_font)
    draw.text((34, 116), _clip(task.software_name, 24), fill="#66758a", font=regular_font)

    title_text = item.title + item.caption
    if item.key == "login":
        draw.rounded_rectangle((302, 250, 418, 366), radius=34, fill="#172033")
        draw.text((326, 292), _clip(task.software_name[:2] or "App", 4), fill="#ffffff", font=regular_font)
        draw.text((180, 410), _clip(task.software_name, 16), fill="#172033", font=title_font)
        y = 540
        for label in ["手机号", "验证码"]:
            draw.text((70, y), label, fill="#52637a", font=small_font)
            draw.rounded_rectangle((70, y + 30, 650, y + 88), radius=18, outline="#dce4ef", fill="#ffffff")
            y += 112
        draw.rounded_rectangle((70, y + 10, 650, y + 72), radius=20, fill="#172033")
        draw.text((280, y + 30), "登录并进入应用", fill="#ffffff", font=regular_font)
    elif any(word in title_text for word in ["播放", "听歌", "音乐", "歌曲", "听书", "朗读", "视频", "音频"]):
        draw.rounded_rectangle((88, 190, 632, 704), radius=42, fill="#263445")
        draw.rounded_rectangle((245, 332, 475, 562), radius=42, fill="#d6b16f")
        draw.text((278, 430), _clip(item.title, 6), fill="#ffffff", font=regular_font)
        draw.text((74, 750), _clip(item.title, 18), fill="#172033", font=title_font)
        draw.text((74, 800), _clip(item.caption, 32), fill="#66758a", font=regular_font)
        draw.rounded_rectangle((74, 880, 646, 890), radius=5, fill="#dbe4ef")
        draw.rounded_rectangle((74, 880, 406, 890), radius=5, fill="#172033")
        for x, label in [(128, "上一首"), (310, "播放"), (504, "下一首")]:
            radius = 58 if label == "播放" else 38
            draw.ellipse((x, 950, x + radius, 950 + radius), fill="#172033" if label == "播放" else "#ffffff")
            draw.text((x + 8, 970), label, fill="#ffffff" if label == "播放" else "#29364a", font=small_font)
    else:
        draw.rounded_rectangle((34, 178, 686, 236), radius=22, fill="#ffffff", outline="#dfe7f1")
        draw.text((58, 198), "搜索内容或功能", fill="#7b8ba0", font=regular_font)
        draw.rounded_rectangle((34, 262, 686, 432), radius=30, fill="#172033")
        draw.text((62, 306), _clip(item.title, 18), fill="#ffffff", font=title_font)
        draw.text((62, 356), _clip(item.caption, 36), fill="#cbd5e1", font=regular_font)
        rows = blueprint.modules[:5] or []
        y = 464
        for module in rows:
            draw.rounded_rectangle((34, y, 686, y + 98), radius=24, fill="#ffffff", outline="#dfe7f1")
            draw.text((58, y + 20), _clip(module.title, 18), fill="#172033", font=regular_font)
            draw.text((58, y + 54), _clip(module.description, 32), fill="#66758a", font=small_font)
            y += 116
    draw.rectangle((0, 1188, 720, 1280), fill="#ffffff")
    for index, label in enumerate(["首页", "发现", "收藏", "我的"]):
        x = 64 + index * 164
        draw.text((x, 1220), label, fill="#172033" if index == 0 else "#708197", font=regular_font)


def _draw_game_phone_page(draw, task: GenerationTask, blueprint: ProductBlueprint, item: UiScreenshot, title_font, regular_font, small_font, metric_font) -> None:
    draw.rectangle((0, 0, 720, 1280), fill="#69d8ff")
    draw.ellipse((-120, -80, 170, 210), fill="#b7fbce")
    draw.ellipse((480, 40, 820, 380), fill="#ffe27a")
    draw.ellipse((430, 900, 850, 1330), fill="#ff91c8")
    draw.rounded_rectangle((230, 12, 490, 36), radius=12, fill="#6c7ca3")
    draw.rounded_rectangle((28, 54, 692, 190), radius=32, fill="#ffffff")
    draw.text((56, 86), _clip(item.title, 15), fill="#263b72", font=title_font)
    for index, label in enumerate(["体力25/30", "金币12860", "第36关"]):
        x = 56 + index * 196
        draw.rounded_rectangle((x, 138, x + 168, 178), radius=18, fill="#eef6ff")
        draw.text((x + 16, 149), label, fill="#345083", font=small_font)

    title_text = item.title + item.caption
    if item.key in {"login", "dashboard"} or any(word in title_text for word in ["关卡", "地图"]):
        draw.rounded_rectangle((42, 224, 678, 800), radius=34, fill="#e8fff0")
        points = [(86, 666), (176, 592), (284, 640), (388, 520), (508, 574), (570, 424), (482, 312), (350, 374)]
        for index, (x, y) in enumerate(points, start=29):
            draw.ellipse((x, y, x + 78, y + 78), fill="#ffffff", outline="#facc15", width=7)
            draw.text((x + 24, y + 24), str(index), fill="#2563eb", font=regular_font)
        draw.rounded_rectangle((42, 830, 678, 1128), radius=34, fill="#ffffff")
        for index, (label, value) in enumerate([("当前关卡", "36"), ("星级进度", "86/120"), ("每日任务", "3/5")]):
            y = 866 + index * 72
            draw.text((80, y), label, fill="#41516f", font=regular_font)
            draw.text((535, y), value, fill="#2563eb", font=regular_font)
        draw.rounded_rectangle((72, 1060, 648, 1142), radius=30, fill="#f97316")
        draw.text((292, 1086), "开始游戏", fill="#ffffff", font=regular_font)
    elif any(word in title_text for word in ["道具", "背包", "资产"]):
        cards = [("彩虹球", "x6"), ("小木锤", "x12"), ("横向火箭", "x4"), ("金币礼包", "12860"), ("体力瓶", "x5"), ("限时门票", "x3")]
        for index, (label, value) in enumerate(cards):
            x = 42 + (index % 2) * 324
            y = 232 + (index // 2) * 176
            draw.rounded_rectangle((x, y, x + 288, y + 140), radius=28, fill="#ffffff")
            draw.text((x + 28, y + 28), label, fill="#27324f", font=regular_font)
            draw.text((x + 28, y + 80), value, fill="#f97316" if index == 1 else "#2563eb", font=metric_font)
        draw.rounded_rectangle((42, 820, 678, 1126), radius=34, fill="#ffffff")
        for index, line in enumerate(["通关奖励 +120 金币", "道具使用 -1 小木锤", "活动领取 +1 彩虹球"]):
            draw.text((78, 868 + index * 72), line, fill="#41516f", font=regular_font)
    elif any(word in title_text for word in ["统计", "结算", "星级"]):
        cards = [("最终得分", "18,640"), ("剩余步数", "6"), ("连消次数", "14"), ("最高连击", "7"), ("获得金币", "320"), ("星级评价", "★★★")]
        for index, (label, value) in enumerate(cards):
            x = 42 + (index % 2) * 324
            y = 232 + (index // 2) * 176
            draw.rounded_rectangle((x, y, x + 288, y + 140), radius=28, fill="#ffffff")
            draw.text((x + 28, y + 28), label, fill="#27324f", font=regular_font)
            draw.text((x + 28, y + 80), value, fill="#2563eb", font=metric_font)
        draw.rounded_rectangle((72, 1060, 648, 1142), radius=30, fill="#f97316")
        draw.text((318, 1086), "下一关", fill="#ffffff", font=regular_font)
    else:
        draw.rounded_rectangle((42, 224, 678, 876), radius=34, fill="#5749ec")
        colors = ["#fb7185", "#fbbf24", "#34d399", "#60a5fa", "#a78bfa", "#f472b6"]
        for row in range(8):
            for col in range(8):
                x = 88 + col * 70
                y = 270 + row * 70
                draw.rounded_rectangle((x, y, x + 58, y + 58), radius=18, fill=colors[(row * 3 + col * 2) % len(colors)])
        draw.rounded_rectangle((42, 906, 678, 1158), radius=34, fill="#ffffff")
        for index, (label, value) in enumerate([("红色方块", "18"), ("黄色星星", "12"), ("冰块障碍", "6")]):
            x = 72 + index * 204
            draw.rounded_rectangle((x, 942, x + 174, 1038), radius=24, fill="#f5fbff")
            draw.text((x + 26, 956), label, fill="#27324f", font=small_font)
            draw.text((x + 68, 988), value, fill="#315df4", font=regular_font)
        draw.rounded_rectangle((72, 1060, 648, 1142), radius=30, fill="#f97316")
        draw.text((260, 1086), "交换相邻棋子", fill="#ffffff", font=regular_font)


def _draw_game_page(draw, task: GenerationTask, blueprint: ProductBlueprint, item: UiScreenshot, title_font, regular_font, small_font, metric_font) -> None:
    draw.rectangle((0, 0, 1280, 820), fill="#8dd8ff")
    draw.rectangle((0, 360, 1280, 820), fill="#ffd6e8")
    draw.rounded_rectangle((50, 36, 1230, 784), radius=28, fill="#fff7df", outline="#ffffff", width=6)
    draw.rounded_rectangle((76, 62, 1204, 140), radius=18, fill="#ffffff")
    draw.text((106, 86), item.title, fill="#30436b", font=title_font)
    for index, label in enumerate(["体力 25/30", "金币 12,860", "第36关"]):
        x = 780 + index * 130
        draw.rounded_rectangle((x, 82, x + 116, 122), radius=18, fill="#eef6ff")
        draw.text((x + 14, 93), label, fill="#41516f", font=small_font)

    if item.key in {"login", "dashboard"} or any(word in item.title for word in ["关卡", "任务"]):
        _draw_level_map(draw, regular_font, small_font)
        draw.rounded_rectangle((850, 182, 1168, 642), radius=22, fill="#ffffff")
        labels = [("当前关卡", "36"), ("星级进度", "86/120"), ("目标分数", "12000"), ("限定步数", "24")]
        y = 220
        for label, value in labels:
            draw.rounded_rectangle((884, y, 1134, y + 58), radius=14, fill="#f8fafc")
            draw.text((904, y + 18), label, fill="#41516f", font=small_font)
            draw.text((1064, y + 13), value, fill="#2563eb", font=regular_font)
            y += 78
        draw.rounded_rectangle((884, 560, 1134, 620), radius=18, fill="#f97316")
        draw.text((968, 580), "开始游戏", fill="#ffffff", font=regular_font)
    elif any(word in item.title for word in ["统计", "结算", "匹配", "对战"]):
        cards = [("最终得分", "18,640"), ("剩余步数", "6"), ("最高连击", "7"), ("星级评价", "★★★"), ("获得金币", "320"), ("连消奖励", "+2140")]
        for index, (label, value) in enumerate(cards):
            x = 110 + (index % 3) * 250
            y = 190 + (index // 3) * 170
            draw.rounded_rectangle((x, y, x + 210, y + 130), radius=18, fill="#ffffff")
            draw.text((x + 22, y + 26), label, fill="#41516f", font=regular_font)
            draw.text((x + 22, y + 70), value, fill="#2563eb", font=metric_font)
        draw.rounded_rectangle((890, 190, 1138, 560), radius=20, fill="#ffffff")
        for index, line in enumerate(["基础分 12000", "步数奖励 +3600", "连消奖励 +2140", "道具加成 +900"]):
            draw.text((920, 230 + index * 70), line, fill="#41516f", font=regular_font)
    else:
        _draw_match_board(draw)
        draw.rounded_rectangle((850, 182, 1168, 642), radius=22, fill="#ffffff")
        for index, (label, value) in enumerate([("红色方块", "18"), ("黄色星星", "12"), ("冰块障碍", "6"), ("剩余步数", "18"), ("当前得分", "8420")]):
            y = 212 + index * 72
            draw.rounded_rectangle((884, y, 1134, y + 52), radius=14, fill="#f8fafc")
            draw.text((904, y + 15), label, fill="#41516f", font=small_font)
            draw.text((1068, y + 10), value, fill="#2563eb", font=regular_font)


def _draw_match_board(draw) -> None:
    colors = ["#fb7185", "#fbbf24", "#34d399", "#60a5fa", "#a78bfa", "#f472b6"]
    draw.rounded_rectangle((120, 182, 740, 720), radius=24, fill="#4f46e5")
    for row in range(8):
        for col in range(8):
            x = 166 + col * 66
            y = 216 + row * 60
            draw.rounded_rectangle((x, y, x + 48, y + 48), radius=14, fill=colors[(row * 3 + col * 2) % len(colors)])


def _draw_level_map(draw, regular_font, small_font) -> None:
    draw.rounded_rectangle((120, 182, 790, 642), radius=24, fill="#c7f9d4")
    points = [(170, 520), (260, 455), (360, 500), (465, 405), (570, 450), (650, 345), (720, 380)]
    for index, (x, y) in enumerate(points, start=30):
        draw.ellipse((x, y, x + 62, y + 62), fill="#ffffff", outline="#facc15", width=5)
        draw.text((x + 20, y + 19), str(index), fill="#2563eb", font=regular_font)


def _clip(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 1] + "…"


# Keep the public compatibility surface in screenshots.py while the runtime
# injection implementation lives in its own module.
from .screenshot_runtime_injection import (  # noqa: E402
    _ensure_runtime_layout_guard,
    _inject_runtime_script_into_ai_page,
    _runtime_layout_guard_style,
    _runtime_module_keys,
    runtime_api_script,
)
