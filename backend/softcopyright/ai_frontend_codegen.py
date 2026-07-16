from __future__ import annotations

import base64
import copy
from concurrent.futures import ThreadPoolExecutor, as_completed
from hashlib import sha256
from html import escape
import io
import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from .blueprint import FeatureModule, ProductBlueprint
from .errors import sanitize_error_message
from .llm.provider import LLMProvider, LocalTemplateProvider, image_model_name, _inspect_generated_image
from .llm.trace import trace_event
from .models import GenerationTask
from .ui_blueprint import UiBlueprint


def generate_ai_frontend_pages(
    *,
    task: GenerationTask,
    blueprint: ProductBlueprint,
    ui_blueprint: UiBlueprint,
    screenshots: list[Any],
    provider: LLMProvider | None,
    emit=None,
    require_llm: bool = False,
    visual_reference_report: dict[str, Any] | None = None,
    codegen_progress_start: int = 44,
) -> dict[str, Any]:
    if provider is None or isinstance(provider, LocalTemplateProvider):
        if require_llm:
            raise RuntimeError("正式 GPT 流程要求由 GPT 生成界面页面代码，请配置 GPT/OpenAI-compatible。")
        return {"enabled": False, "ready": False, "source": "local-template", "pages": []}
    if not screenshots:
        raise RuntimeError("AI 前端代码生成缺少截图页面清单。")

    pages: list[dict[str, Any]] = []
    module_by_key = {module.key: module for module in blueprint.modules}
    design_brief = getattr(ui_blueprint, "design_brief", {}) or {}
    context = _codegen_context(task, blueprint, ui_blueprint)
    if not isinstance(visual_reference_report, dict) or not visual_reference_report:
        visual_reference_report = generate_style_reference_assets(
            task=task,
            blueprint=blueprint,
            ui_blueprint=ui_blueprint,
            screenshots=screenshots,
            provider=provider,
            emit=emit,
            require_llm=require_llm,
        )
    style_reference = visual_reference_report.get("style_reference")
    if not isinstance(style_reference, dict):
        style_reference = next(
            (item for item in visual_reference_report.get("pages", []) if isinstance(item, dict) and item.get("ready")),
            {},
        )
    if require_llm and not visual_reference_report.get("ready"):
        raise RuntimeError("正式 GPT 流程要求先生成 gpt-image-2 全局视觉风格参考图，当前参考图未生成。")
    provider = _frontend_provider(provider)
    renderer = str(getattr(ui_blueprint, "renderer", "") or "admin")
    if _use_react_framework(renderer):
        return _generate_react_frontend_pages(
            task=task,
            blueprint=blueprint,
            ui_blueprint=ui_blueprint,
            screenshots=screenshots,
            module_by_key=module_by_key,
            provider=provider,
            visual_reference_report=visual_reference_report,
            style_reference=style_reference,
            emit=emit,
            codegen_progress_start=codegen_progress_start,
        )
    if _use_stable_component_shell(renderer):
        return _generate_stable_component_shell_pages(
            task=task,
            blueprint=blueprint,
            ui_blueprint=ui_blueprint,
            screenshots=screenshots,
            module_by_key=module_by_key,
            visual_reference_report=visual_reference_report,
            style_reference=style_reference,
            emit=emit,
            codegen_progress_start=codegen_progress_start,
        )
    total = len(screenshots)
    for index, item in enumerate(screenshots, start=1):
        progress = codegen_progress_start + min(4, int(index / max(total, 1) * 4))
        _emit(emit, progress, f"根据全局视觉风格参考图生成界面代码 {index}/{total}")
        module = module_by_key.get(str(getattr(item, "module_key", "") or ""))
        reference = style_reference
        if require_llm and not _visual_reference_ready(reference):
            raise RuntimeError("缺少 gpt-image-2 全局视觉风格参考图。")
        creative_key = _page_creative_key(task, design_brief, item)
        cached_page = _load_reusable_page(item, creative_key=creative_key)
        if cached_page:
            pages.append(
                {
                    "key": str(getattr(item, "key", "")),
                    "file": cached_page.name,
                    "page_kind": str(getattr(item, "page_kind", "") or "general"),
                    "module_key": str(getattr(item, "module_key", "") or ""),
                    "source": "llm-html-cache",
                    "visual_reference": _report_reference_summary(reference),
                    "reused": True,
                }
            )
            trace_event(
                "ai_frontend_page_reused",
                page_key=str(getattr(item, "key", "") or cached_page.stem),
                file=cached_page.name,
                index=index,
                total=total,
            )
            continue
        try:
            html = _generate_page_html(
                task=task,
                blueprint=blueprint,
                ui_blueprint=ui_blueprint,
                provider=provider,
                screenshot=item,
                module=module,
                visual_reference=reference,
                context=context,
                design_brief=design_brief,
                index=index,
                total=total,
            )
            html = _stamp_creative_key(html, creative_key)
            html_path = Path(str(getattr(item, "html_path", "")))
            if not str(html_path).strip() or html_path.name == "":
                raise RuntimeError(f"{getattr(item, 'key', 'page')} 缺少界面 HTML 输出路径。")
            html_path.parent.mkdir(parents=True, exist_ok=True)
            html_path.write_text(html, encoding="utf-8")
            pages.append(
                {
                    "key": str(getattr(item, "key", "")),
                    "file": html_path.name,
                    "page_kind": str(getattr(item, "page_kind", "") or "general"),
                    "module_key": str(getattr(item, "module_key", "") or ""),
                    "source": "llm-html",
                    "visual_reference": _report_reference_summary(reference),
                }
            )
        except Exception as exc:
            if require_llm:
                raise RuntimeError(f"{getattr(item, 'key', 'page')} AI 界面代码生成失败：{exc}") from exc
            return {
                "enabled": True,
                "ready": False,
                "source": "gpt-style-reference-image2-to-html",
                "error": str(exc)[:240],
                "visual_references": visual_reference_report,
                "pages": pages,
            }
    return {
        "enabled": True,
        "ready": len(pages) == total,
        "source": "gpt-style-reference-image2-to-html",
        "page_count": len(pages),
        "visual_references": visual_reference_report,
        "pages": pages,
    }


def _use_stable_component_shell(renderer: str) -> bool:
    mode = os.getenv("SOFT_AI_FRONTEND_MODE", "react-vite").strip().lower()
    return renderer == "admin" and mode in {"stable-component-shell", "stable-shell", "component-shell"}


def _use_react_framework(renderer: str) -> bool:
    mode = os.getenv("SOFT_AI_FRONTEND_MODE", "react-vite").strip().lower()
    return mode not in {"llm-html", "freeform-html", "legacy", "stable-component-shell", "stable-shell", "component-shell"}


def _generate_react_frontend_pages(
    *,
    task: GenerationTask,
    blueprint: ProductBlueprint,
    ui_blueprint: UiBlueprint,
    screenshots: list[Any],
    module_by_key: dict[str, FeatureModule],
    provider: LLMProvider,
    visual_reference_report: dict[str, Any],
    style_reference: dict[str, Any],
    emit=None,
    codegen_progress_start: int = 50,
) -> dict[str, Any]:
    prototype_dir = Path(str(getattr(screenshots[0], "html_path", ""))).parent
    react_dir = prototype_dir / "react-app"
    screens_dir = react_dir / "src" / "screens"
    screens_dir.mkdir(parents=True, exist_ok=True)
    design_brief = getattr(ui_blueprint, "design_brief", {}) or {}
    context = _codegen_context(task, blueprint, ui_blueprint)
    total = len(screenshots)
    visual_style_contract = _visual_reference_style_contract(style_reference)
    trace_event(
        "ai_frontend_reference_contract_ready",
        image_width=int(visual_style_contract.get("image_width") or 0),
        image_height=int(visual_style_contract.get("image_height") or 0),
        palette_count=len(visual_style_contract.get("dominant_colors") or []),
    )
    stop_event = threading.Event()
    pending_indexes: list[int] = []
    for pending_index, pending_item in enumerate(screenshots, start=1):
        pending_key = str(getattr(pending_item, "key", "") or f"page_{pending_index}")
        pending_token = _react_component_token(pending_key, pending_index)
        pending_creative_key = _page_creative_key(task, design_brief, pending_item)
        if not _react_component_cache_ready(
            screens_dir / f"{pending_token}.jsx",
            screens_dir / f"{pending_token}.css",
            screens_dir / f"{pending_token}.meta.json",
            pending_creative_key,
        ):
            pending_indexes.append(pending_index)
    if pending_indexes and pending_indexes[0] > 1:
        _emit(emit, codegen_progress_start, f"从未完成页面继续 {pending_indexes[0]}/{total}")
    elif not pending_indexes:
        _emit(emit, codegen_progress_start, f"复用全部 React 页面组件 {total}/{total}")

    def build_page(index: int, item: Any) -> dict[str, Any]:
        if stop_event.is_set():
            raise RuntimeError("React 页面生成已因模型网关错误停止")
        page_key = str(getattr(item, "key", "") or f"page_{index}")
        token = _react_component_token(page_key, index)
        component_name = f"Screen{token}"
        component_path = screens_dir / f"{token}.jsx"
        css_path = screens_dir / f"{token}.css"
        meta_path = screens_dir / f"{token}.meta.json"
        creative_key = _page_creative_key(task, design_brief, item)
        progress = codegen_progress_start + min(4, int(index / max(total, 1) * 4))
        if not _react_component_cache_ready(component_path, css_path, meta_path, creative_key):
            _emit(emit, progress, f"生成 React 界面组件 {index}/{total}")
            module = module_by_key.get(str(getattr(item, "module_key", "") or ""))
            data = None
            last_error: Exception | None = None
            try:
                for component_attempt in range(2):
                    if stop_event.is_set():
                        raise RuntimeError("React 页面生成已因模型网关错误停止")
                    try:
                        data = _generate_react_component(
                            task=task,
                            blueprint=blueprint,
                            ui_blueprint=ui_blueprint,
                            provider=provider,
                            screenshot=item,
                            module=module,
                            visual_reference=style_reference,
                            visual_style_contract=visual_style_contract,
                            context=context,
                            design_brief=design_brief,
                            index=index,
                            total=total,
                            component_name=component_name,
                            css_scope=_react_css_scope(page_key, index),
                            creative_key=creative_key,
                        )
                        break
                    except ValueError as exc:
                        last_error = exc
                        if component_attempt == 0:
                            _emit(emit, progress, f"React 组件格式不合格，重新生成 {page_key}")
                    except Exception as exc:
                        last_error = exc
                        if component_attempt == 0 and _is_transient_frontend_error(exc):
                            trace_event(
                                "ai_frontend_page_retry",
                                page_key=page_key,
                                index=index,
                                total=total,
                                reason=sanitize_error_message(exc, limit=300),
                            )
                            _emit(emit, progress, f"{page_key} 模型暂时无响应，正在重试当前页面")
                            continue
                        raise
                if data is None:
                    raise RuntimeError(f"{page_key} React 组件生成失败：{last_error}") from last_error
            except Exception as exc:
                stop_event.set()
                trace_event(
                    "ai_frontend_circuit_open",
                    page_key=page_key,
                    index=index,
                    total=total,
                    error=sanitize_error_message(exc, limit=500),
                )
                raise RuntimeError(
                    f"{page_key} 前端模型请求失败，已停止剩余页面，避免长时间重复等待：{sanitize_error_message(exc)}"
                ) from exc
            component_path.write_text(
                f'import React from "react";\nimport "./{token}.css";\n\n'
                f"export default function {component_name}() {{\n  return (\n{data['jsx']}\n  );\n}}\n",
                encoding="utf-8",
            )
            css_path.write_text(data["css"], encoding="utf-8")
            meta_path.write_text(
                json.dumps({"creative_key": creative_key, "page_key": page_key, "framework": "react-vite"}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        _sanitize_cached_react_component(component_path)
        return {
            "index": index,
            "import": f'import {component_name} from "./screens/{token}.jsx";',
            "registration": f'  {json.dumps(page_key, ensure_ascii=False)}: {component_name},',
            "page": {
                "key": page_key,
                "title": str(getattr(item, "title", "") or page_key),
                "caption": str(getattr(item, "caption", "") or ""),
                "file": Path(str(getattr(item, "html_path", ""))).name,
                "page_kind": str(getattr(item, "page_kind", "") or "general"),
                "module_key": str(getattr(item, "module_key", "") or ""),
                "source": "react-vite-component",
                "component": str(component_path),
                "creative_key": creative_key,
                "visual_reference": _report_reference_summary(style_reference),
            },
        }

    workers = _react_codegen_workers(total)
    results: list[dict[str, Any]] = []
    if workers == 1:
        results = [build_page(index, item) for index, item in enumerate(screenshots, start=1)]
    else:
        executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="react-codegen")
        try:
            futures = {
                executor.submit(build_page, index, item): index
                for index, item in enumerate(screenshots, start=1)
            }
            for future in as_completed(futures):
                try:
                    results.append(future.result())
                except Exception:
                    stop_event.set()
                    for pending in futures:
                        pending.cancel()
                    raise
        finally:
            executor.shutdown(wait=True, cancel_futures=True)
    results.sort(key=lambda item: int(item["index"]))
    imports = [str(item["import"]) for item in results]
    registrations = [str(item["registration"]) for item in results]
    pages = [dict(item["page"]) for item in results]
    _write_react_app_files(
        task=task,
        blueprint=blueprint,
        ui_blueprint=ui_blueprint,
        react_dir=react_dir,
        imports=imports,
        registrations=registrations,
        pages=pages,
        default_key=str(getattr(screenshots[0], "key", "") or "page_1"),
    )
    _emit(emit, codegen_progress_start + 5, "构建 React + Vite 运行工程")
    _build_react_vite_bundle(react_dir)
    _publish_react_page_entries(
        prototype_dir,
        react_dir / "dist",
        screenshots,
        renderer=str(getattr(ui_blueprint, "renderer", "") or "admin"),
    )
    return {
        "enabled": True,
        "ready": len(pages) == total,
        "source": "gpt-style-reference-image2-to-react-vite",
        "framework": "react",
        "build_tool": "vite",
        "renderer": str(getattr(ui_blueprint, "renderer", "") or "admin"),
        "page_count": len(pages),
        "source_dir": str(react_dir),
        "visual_references": visual_reference_report,
        "pages": pages,
    }


def _react_codegen_workers(total: int) -> int:
    raw = os.getenv("SOFT_LLM_AI_FRONTEND_WORKERS", "1").strip()
    try:
        configured = int(raw)
    except ValueError:
        configured = 1
    return max(1, min(4, int(total or 1), configured))


def _is_transient_frontend_error(exc: Exception) -> bool:
    text = str(exc or "").lower()
    if "已因模型网关错误停止" in text:
        return False
    transient_markers = (
        "timed out",
        "timeout",
        "read timeout",
        "connection reset",
        "connection aborted",
        "temporarily unavailable",
        "server error",
    )
    if any(marker in text for marker in transient_markers):
        return True
    return bool(re.search(r"\b(?:408|409|425|429|500|502|503|504|520|522|523|524)\b", text))


def _frontend_provider(provider: LLMProvider) -> LLMProvider:
    config = getattr(provider, "config", None)
    if config is None:
        return provider
    cloned_provider = copy.copy(provider)
    cloned_config = copy.copy(config)
    frontend_model = os.getenv("SOFT_MODEL_GPT_FRONTEND_NAME", "").strip()
    if frontend_model:
        cloned_config.model = frontend_model
    cloned_config.retry_count = _ai_frontend_retry_count()
    cloned_config.timeout = _ai_frontend_timeout_seconds(provider)
    cloned_provider.config = cloned_config
    trace_event(
        "ai_frontend_provider_config",
        model=str(getattr(cloned_config, "model", "") or ""),
        retry_count=int(getattr(cloned_config, "retry_count", 0) or 0),
        timeout=int(getattr(cloned_config, "timeout", 0) or 0),
    )
    return cloned_provider


def _ai_frontend_retry_count() -> int:
    raw = os.getenv("SOFT_LLM_AI_FRONTEND_RETRY_COUNT", "0").strip()
    try:
        value = int(raw)
    except ValueError:
        value = 0
    return max(0, min(1, value))


def _react_component_max_tokens() -> int:
    raw = os.getenv("SOFT_REACT_COMPONENT_MAX_TOKENS", "3000").strip()
    try:
        configured = int(raw)
    except ValueError:
        configured = 3000
    return max(2400, min(4000, configured))


def _operation_prompt_rule(screenshot: Any) -> str:
    if str(getattr(screenshot, "page_kind", "") or "") != "operation":
        return ""
    action = str(getattr(screenshot, "interaction_action", "") or "当前操作")
    surface = str(getattr(screenshot, "interaction_surface", "") or "detail")
    mode = str(getattr(screenshot, "interaction_mode", "") or "instant")
    role = str(getattr(screenshot, "interaction_role", "") or "当前岗位")
    trigger = str(getattr(screenshot, "interaction_trigger", "") or "进入当前业务场景")
    fields = [str(item) for item in (getattr(screenshot, "interaction_input_fields", None) or []) if str(item).strip()]
    pre_state = str(getattr(screenshot, "interaction_pre_state", "") or "当前状态")
    post_state = str(getattr(screenshot, "interaction_post_state", "") or "处理后状态")
    evidence = str(getattr(screenshot, "interaction_result_evidence", "") or "可见状态和操作日志")
    contract = (
        f"执行角色：{role}；触发条件：{trigger}；输入字段：{'、'.join(fields) or '按模块业务字段'}；"
        f"状态变化：{pre_state} -> {post_state}；结果证据：{evidence}。"
    )
    if bool(getattr(screenshot, "requires_confirmation", False)):
        return (
            f"当前动作是“{action}”，目标界面类型为 {surface}。{contract}该动作确需确认：使用接近屏幕宽度的居中弹窗，"
            "说明影响范围并提供取消与确认；禁止贴底窄抽屉，禁止使用‘登记’替代真实动作名称。"
        )
    if mode == "query":
        return (
            f"当前动作是“{action}”，目标界面类型为 {surface}。{contract}页面应展示真实查询条件、已选范围、"
            "查询结果列表和结果数量；查询后直接刷新结果，不要生成确认弹窗。"
        )
    if mode == "form":
        return (
            f"当前动作是“{action}”，目标界面类型为 {surface}。{contract}页面应展示与当前模块对应的字段表单、"
            "必填标识、校验提示、保存/取消入口和保存后的状态反馈；普通保存不需要二次确认。"
        )
    if mode == "import":
        return (
            f"当前动作是“{action}”，目标界面类型为 {surface}。{contract}页面应展示文件选择、文件信息、字段映射、"
            "格式校验、错误明细和导入结果；不得只放一个上传按钮。"
        )
    if mode == "export":
        return (
            f"当前动作是“{action}”，目标界面类型为 {surface}。{contract}页面应展示导出范围、文件格式、字段选择、"
            "生成进度和下载结果；普通导出不需要确认弹窗。"
        )
    if mode == "analysis":
        return (
            f"当前动作是“{action}”，目标界面类型为 {surface}。{contract}页面应展示统计范围、关键指标、趋势或分组结果、"
            "异常提示和导出入口，所有图表必须有名称、日期或单位。"
        )
    if mode in {"workflow", "detail"}:
        return (
            f"当前动作是“{action}”，目标界面类型为 {surface}。{contract}页面应展示当前记录、处理条件、流程轨迹、"
            "责任人和执行后的状态结果；只有确实高风险的动作才允许确认弹窗。"
        )
    return (
        f"当前动作是“{action}”，目标界面类型为 {surface}。{contract}该动作属于即时或可随时撤销的低风险操作。"
        "必须直接展示详情、播放器、歌词、搜索结果、下载选项、队列编辑或状态反馈；"
        "禁止确认弹窗、确认登记、登记表单、取消/确认按钮对，也不要把浏览和播放写成提交办理流程。"
    )


def _generate_react_component(
    *,
    task: GenerationTask,
    blueprint: ProductBlueprint,
    ui_blueprint: UiBlueprint,
    provider: LLMProvider,
    screenshot: Any,
    module: FeatureModule | None,
    visual_reference: dict[str, Any] | None,
    visual_style_contract: dict[str, Any],
    context: dict[str, Any],
    design_brief: dict[str, Any],
    index: int,
    total: int,
    component_name: str,
    css_scope: str,
    creative_key: str,
) -> dict[str, str]:
    renderer = str(getattr(ui_blueprint, "renderer", "") or "admin")
    terminal_rule = (
        "这是 720x1280 竖屏手机 App 页面：根节点及主要手机内容壳必须使用完整 720px 逻辑宽度并铺满画布，"
        "禁止使用 max-width:375px、390px、430px 等窄手机模拟框，禁止在 720px 画布中居中放置缩小版手机页面；"
        "使用触控友好的尺寸、移动导航和单手操作动线，禁止出现压缩后的桌面侧栏后台。"
        if renderer in {"mobile_app", "game"}
        else "这是 1280x720 横屏桌面软件页面：利用横向空间形成真实业务工作区，禁止模拟手机卡片流。"
    )
    payload = {
        "creative_seed": str(getattr(task, "seed", "") or ""),
        "page_structure_seed": creative_key,
        "software_context": context,
        "screen": {
            "key": str(getattr(screenshot, "key", "") or ""),
            "title": str(getattr(screenshot, "title", "") or ""),
            "caption": str(getattr(screenshot, "caption", "") or ""),
            "page_kind": str(getattr(screenshot, "page_kind", "") or ""),
            "module_key": str(getattr(screenshot, "module_key", "") or ""),
            "interaction_action": str(getattr(screenshot, "interaction_action", "") or ""),
            "interaction_mode": str(getattr(screenshot, "interaction_mode", "") or ""),
            "interaction_surface": str(getattr(screenshot, "interaction_surface", "") or ""),
            "requires_confirmation": bool(getattr(screenshot, "requires_confirmation", False)),
            "interaction_action_key": str(getattr(screenshot, "interaction_action_key", "") or ""),
            "interaction_role": str(getattr(screenshot, "interaction_role", "") or ""),
            "interaction_trigger": str(getattr(screenshot, "interaction_trigger", "") or ""),
            "interaction_input_fields": list(getattr(screenshot, "interaction_input_fields", None) or []),
            "interaction_pre_state": str(getattr(screenshot, "interaction_pre_state", "") or ""),
            "interaction_post_state": str(getattr(screenshot, "interaction_post_state", "") or ""),
            "interaction_result_evidence": str(getattr(screenshot, "interaction_result_evidence", "") or ""),
        },
        "module": _module_payload(module),
        "visual_identity": design_brief.get("visual_identity_spec") if isinstance(design_brief, dict) else {},
        "product_experience": design_brief.get("product_experience_spec") if isinstance(design_brief, dict) else {},
        "reference": _prompt_reference_payload(visual_reference),
        "reference_style_contract": visual_style_contract,
    }
    operation_rule = _operation_prompt_rule(screenshot)
    prompt = f"""
为第 {index}/{total} 个页面生成 React 组件的 JSX 主体和独立 CSS。组件名由系统包装为 {component_name}。

{json.dumps(payload, ensure_ascii=False, indent=2)}

要求：
- {terminal_rule}
- {operation_rule or "按当前 page_kind 构建对应层级的真实软件页面。"}
- 只返回 JSON：{{"jsx":"单个根节点的 JSX","css":"完整 CSS"}}；不要返回 import、export、函数声明、Markdown 或外部依赖。
 - JSX 与 CSS 合计控制在 4500-7500 个字符，其中 CSS 控制在 1800-3200 个字符；用 CSS 类复用样式，不要为每个数据行重复冗长结构，也不要输出解释性注释。
- JSX 必须完全自包含：不要引用未声明变量、数组 map、自定义组件或图标组件；业务样例直接写成 JSX 节点，保证无需额外上下文即可渲染。
- JSX 根节点必须包含 className="screen-root {css_scope}" 和 data-page-structure="{creative_key}"。
- 系统会在组件外层统一渲染共享品牌栏、主导航和当前功能标题；本组件只生成页面内容区，禁止再次生成全局 header、品牌名称、线路/项目切换页签、主导航或重复的系统标题。
- 按随消息附带的 image2 全局参考图继承色彩、控件质感和视觉节奏，但当前页面结构必须由 page_structure_seed 和业务用途独立决定。
- 页面保持简洁，围绕当前功能设置一个主要工作区和不超过两个辅助区域；指标卡不超过 4 个、主要操作按钮不超过 6 个、示例表格不超过 5 行。
- 相邻页面只在内容区的主体拓扑、数据呈现和操作路径上体现差异，不得改变共享外壳或重新设计顶栏。
- 登录、仪表盘、模块工作区、操作页和统计页要像同一产品中的不同真实路由，而不是同一模板换文字。
- 操作页必须严格服从 interaction_action、interaction_surface 和 requires_confirmation；即时操作不得擅自增加确认弹窗、登记表单或“确认登记”按钮。
- 使用真实中文业务数据、按钮、状态、表单、表格、图表、流程、时间线、任务板或地图工作区；按当前业务选择，不要求每类控件都出现。
- CSS 必须以 .{css_scope} 为作用域，不引用 CDN、图片、字体、SVG 或网络资源；首屏铺满且文字不能溢出。
- 所有样式都写入 css 字段，JSX 中不要使用 style 字符串或 style 对象。
- 保留可供运行数据覆盖的 .table-frame、.runtime-record-panel、.map-pin、.operation-result 中至少一个适合本页的区域。
- 可见内容禁止出现 AI、GPT、image2、提示词、视觉参考、接口返回、Base URL、API Key、内部文件名。
- 禁止使用“待填写、待补充、待完善、示例内容、业务记录、记录01”等未完成占位文案；缺省值也要写成自然业务状态，例如“无异常”“未发现冲突”或“正常流转”。
""".strip()
    # The same large image on every page disables streaming on compatible gateways and
    # can hit their idle timeout. The contract above is extracted from the actual image.
    user_message = {"role": "user", "content": prompt}
    content = provider.chat(
        [
            {
                "role": "system",
                "content": "你是资深 React 产品工程师。根据真实业务和视觉参考生成可编译 JSX 与 CSS，只返回 JSON，不使用模板化后台骨架。",
            },
            user_message,
        ],
        temperature=0.68,
        max_tokens=_react_component_max_tokens(),
        response_format={"type": "json_object"},
        trace_label=f"react_frontend:{getattr(screenshot, 'key', index)}",
        timeout=_ai_frontend_timeout_seconds(provider),
    )
    data = _parse_json(content)
    jsx = str(data.get("jsx") or data.get("component_jsx") or "").strip()
    css = str(data.get("css") or "").strip()
    if len(jsx) < 700 or len(css) < 500:
        raise ValueError("模型返回的 React JSX/CSS 过短")
    if re.search(r"(?m)^\s*(?:import|export)\s+", jsx) or re.search(r"dangerouslySetInnerHTML|<script\b", jsx, flags=re.I):
        raise ValueError("React 页面包含不允许的导入、脚本或 HTML 注入")
    if re.search(r"<\/?[A-Z][A-Za-z0-9_.]*\b", jsx):
        raise ValueError("React 页面引用了未声明的自定义组件")
    if re.search(r"\sstyle\s*=", jsx, flags=re.I):
        raise ValueError("React 页面包含内联 style，无法保证样式隔离")
    jsx = re.sub(r"\sclass=", " className=", jsx)
    jsx = _sanitize_react_visible_terms(jsx)
    _reject_internal_visible_terms(jsx)
    if f"screen-root {css_scope}" not in jsx or creative_key not in jsx:
        raise ValueError("React 页面缺少页面作用域或独立构图标识")
    if f".{css_scope}" not in css:
        raise ValueError("React 页面 CSS 未按页面作用域隔离")
    if re.search(r"@import|url\s*\(", css, flags=re.I):
        raise ValueError("React 页面 CSS 引用了外部资源")
    return {"jsx": jsx, "css": css}


def _sanitize_react_visible_terms(value: str) -> str:
    developer_type = re.compile(
        r"\b[A-Z][A-Za-z0-9]*(Record|Service|Controller|Router|Route|Entity|Model|Query|Trace|DTO|ViewModel)\b"
    )

    replacements = {
        "Record": "业务对象",
        "Entity": "业务对象",
        "Model": "业务对象",
        "Query": "查询条件",
        "Trace": "追踪信息",
        "DTO": "业务对象",
        "ViewModel": "业务视图",
        "Service": "业务处理",
        "Controller": "业务处理",
        "Router": "业务处理",
        "Route": "业务处理",
    }

    def replace_developer_type(match: re.Match[str]) -> str:
        return replacements.get(match.group(1), "业务对象")

    def replace_text(match: re.Match[str]) -> str:
        visible = developer_type.sub(replace_developer_type, match.group(1))
        # These phrases are useful while drafting but must not leak into a
        # delivery screenshot as template-like or unfinished content.
        visible = visible.replace("业务记录", "业务对象").replace("待填写", "请选择")
        visible = re.sub(
            r"(?:备注)?(?:内容|说明|文案|描述|信息|资料)待(?:补充|完善)(?:：[^，。；<]*)?",
            "相关信息已核验",
            visible,
        )
        visible = re.sub(r"待补充内容|内容待补充|说明待补充", "相关信息已核验", visible)
        return f">{visible}<"

    return re.sub(r">([^<>{]+)<", replace_text, str(value or ""))


def _sanitize_cached_react_component(path: Path) -> None:
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return
    sanitized = _sanitize_react_visible_terms(source)
    if sanitized != source:
        path.write_text(sanitized, encoding="utf-8")


def _react_component_token(page_key: str, index: int) -> str:
    parts = [part for part in re.split(r"[^a-zA-Z0-9]+", page_key) if part]
    token = "".join(part[:1].upper() + part[1:] for part in parts)
    base = token or f"Page{index}"
    return f"{base}{sha256(page_key.encode('utf-8')).hexdigest()[:6]}"


def _react_css_scope(page_key: str, index: int) -> str:
    token = re.sub(r"[^a-zA-Z0-9_-]+", "-", page_key).strip("-_").lower()
    return f"screen-{token or f'page-{index}'}"


def _react_component_cache_ready(component_path: Path, css_path: Path, meta_path: Path, creative_key: str) -> bool:
    if not component_path.exists() or not css_path.exists() or not meta_path.exists():
        return False
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    return str(meta.get("creative_key") or "") == creative_key and component_path.stat().st_size > 900 and css_path.stat().st_size > 500


def _write_react_app_files(
    *,
    task: GenerationTask,
    blueprint: ProductBlueprint,
    ui_blueprint: UiBlueprint,
    react_dir: Path,
    imports: list[str],
    registrations: list[str],
    pages: list[dict[str, Any]],
    default_key: str,
) -> None:
    src_dir = react_dir / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    renderer = str(getattr(ui_blueprint, "renderer", "") or "admin")
    (react_dir / "package.json").write_text(
        json.dumps(
            {
                "name": "generated-react-ui",
                "private": True,
                "version": "1.0.0",
                "type": "module",
                "scripts": {"build": "vite build"},
                "dependencies": {"react": "^19.2.3", "react-dom": "^19.2.3"},
                "devDependencies": {"vite": "^7.2.7"},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    build_config = (
        "export default { base: './', esbuild: { jsx: 'automatic' }, build: { outDir: 'dist', emptyOutDir: true, "
        "rollupOptions: { output: { entryFileNames: 'assets/app.js', assetFileNames: 'assets/[name][extname]' } } } };\n"
    )
    (react_dir / "vite.config.js").write_text(build_config, encoding="utf-8")
    module_root = _frontend_node_module_root()
    alias_entries = [
        ("react/jsx-runtime", module_root / "react" / "jsx-runtime.js"),
        ("react/jsx-dev-runtime", module_root / "react" / "jsx-dev-runtime.js"),
        ("react-dom/client", module_root / "react-dom" / "client.js"),
        ("react-dom", module_root / "react-dom" / "index.js"),
        ("react", module_root / "react" / "index.js"),
    ]
    alias_source = ",".join(
        "{find:" + json.dumps(name) + ",replacement:" + json.dumps(str(path).replace("\\", "/")) + "}"
        for name, path in alias_entries
    )
    (react_dir / "vite.runtime.config.js").write_text(
        build_config.replace("export default {", f"export default {{ resolve: {{ alias: [{alias_source}] }},"),
        encoding="utf-8",
    )
    (react_dir / "index.html").write_text('<!doctype html><html><head><meta charset="UTF-8"></head><body><div id="root"></div><script type="module" src="/src/main.jsx"></script></body></html>', encoding="utf-8")
    (src_dir / "main.jsx").write_text('import React from "react";\nimport { createRoot } from "react-dom/client";\nimport App from "./App.jsx";\nimport "./theme.css";\ncreateRoot(document.getElementById("root")).render(<App />);\n', encoding="utf-8")
    screen_meta = {
        str(page.get("key") or ""): {
            "title": str(page.get("title") or "功能界面"),
            "page_kind": str(page.get("page_kind") or "general"),
            "module_key": str(page.get("module_key") or ""),
            "section": _shared_shell_section(page),
        }
        for page in pages
        if str(page.get("key") or "")
    }
    shell_config = {
        "software_name": task.software_name,
        "version": task.version,
        "industry": blueprint.industry or task.product_type,
        "role": str((blueprint.roles or blueprint.target_users or ["当前用户"])[0]),
        "navigation": [
            {"key": "dashboard", "label": "工作首页"},
            {"key": "business", "label": "功能办理"},
            {"key": "tracking", "label": "任务跟踪"},
            {"key": "statistics", "label": "统计分析"},
            {"key": "settings", "label": "系统设置"},
        ],
    }
    (src_dir / "SharedAppShell.jsx").write_text(_shared_app_shell_source(), encoding="utf-8")
    app_source = "\n".join(imports) + '\nimport SharedAppShell from "./SharedAppShell.jsx";\n\nconst screens = {\n' + "\n".join(registrations) + "\n};\n" + f'''\nconst screenMeta = {json.dumps(screen_meta, ensure_ascii=False, indent=2)};
const shellConfig = {json.dumps(shell_config, ensure_ascii=False, indent=2)};

export default function App() {{
  const key = window.__SOFT_SCREEN_KEY__ || new URLSearchParams(window.location.search).get("screen") || {json.dumps(default_key, ensure_ascii=False)};
  const Screen = screens[key] || screens[{json.dumps(default_key, ensure_ascii=False)}];
  return <div className="generated-product" data-renderer={json.dumps(renderer)} data-software={json.dumps(task.software_name, ensure_ascii=False)}>
    <SharedAppShell renderer={json.dumps(renderer)} screenKey={{key}} screenMeta={{screenMeta[key] || {{}}}} config={{shellConfig}}>
      <Screen />
    </SharedAppShell>
  </div>;
}}
'''
    (src_dir / "App.jsx").write_text(app_source, encoding="utf-8")
    mobile_css = "max-width:720px;margin:0 auto;" if renderer in {"mobile_app", "game"} else "width:100%;"
    (src_dir / "theme.css").write_text(_shared_app_shell_css(mobile_css), encoding="utf-8")


def _shared_shell_section(page: dict[str, Any]) -> str:
    page_kind = str(page.get("page_kind") or "").lower()
    title = str(page.get("title") or "")
    if page_kind == "dashboard":
        return "dashboard"
    if page_kind == "statistics":
        return "statistics"
    if page_kind == "login":
        return "login"
    if any(token in title for token in ("任务", "待办", "跟踪", "整改", "复验", "审核")):
        return "tracking"
    return "business"


def _shared_app_shell_source() -> str:
    return '''import React from "react";

export default function SharedAppShell({ renderer, screenKey, screenMeta, config, children }) {
  if (screenMeta?.section === "login" || screenKey === "login") return children;
  const activeSection = screenMeta?.section || "business";
  const mark = String(config?.software_name || "软").trim().slice(0, 1) || "软";
  return <div className={`shared-app-shell shared-app-shell-${renderer || "admin"}`}>
    <header className="shared-app-header">
      <div className="shared-app-brand"><span className="shared-app-mark">{mark}</span><div><strong>{config?.software_name}</strong><small>{config?.version} · 业务操作平台</small></div></div>
      <nav className="shared-app-nav" aria-label="主导航">
        {(config?.navigation || []).map((item) => <span key={item.key} className={item.key === activeSection ? "active" : ""}>{item.label}</span>)}
      </nav>
      <div className="shared-app-context"><span>{config?.industry}</span><strong>{screenMeta?.title || "功能界面"}</strong><em>{config?.role}</em></div>
    </header>
    <main className="shared-app-main">{children}</main>
  </div>;
}
'''


def _shared_app_shell_css(mobile_css: str) -> str:
    return f'''*{{box-sizing:border-box}}html,body,#root{{margin:0;width:100%;height:100%;overflow:hidden}}body{{font-family:'Microsoft YaHei','PingFang SC',Arial,sans-serif;background:#eef2f7;color:#172033}}button,input,select,textarea{{font:inherit}}.generated-product{{height:100%;{mobile_css}}}.shared-app-shell{{height:100%;display:grid;grid-template-rows:66px minmax(0,1fr);background:#081a31;overflow:hidden}}.shared-app-header{{display:grid;grid-template-columns:minmax(280px,360px) minmax(420px,1fr) minmax(210px,280px);align-items:center;gap:18px;padding:0 18px;background:linear-gradient(90deg,#0a1c35,#102b4d 58%,#0a203c);border-bottom:1px solid rgba(96,165,250,.28);color:#e8f3ff;box-shadow:0 8px 22px rgba(2,12,27,.24);z-index:20}}.shared-app-brand{{display:flex;align-items:center;gap:11px;min-width:0}}.shared-app-mark{{width:38px;height:38px;flex:0 0 38px;border-radius:10px;display:grid;place-items:center;background:linear-gradient(135deg,#f59e0b,#2563eb);color:white;font-weight:900;box-shadow:0 4px 14px rgba(37,99,235,.35)}}.shared-app-brand div,.shared-app-context{{min-width:0}}.shared-app-brand strong,.shared-app-brand small{{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}.shared-app-brand strong{{font-size:15px}}.shared-app-brand small{{margin-top:4px;color:#93c5fd;font-size:11px}}.shared-app-nav{{display:flex;align-items:center;justify-content:center;gap:6px;min-width:0;overflow:hidden}}.shared-app-nav span{{height:34px;display:inline-flex;align-items:center;padding:0 13px;border:1px solid rgba(147,197,253,.2);border-radius:6px;background:rgba(9,30,57,.62);color:#bfd7f5;font-size:12px;white-space:nowrap}}.shared-app-nav span.active{{background:#2563eb;border-color:#60a5fa;color:white;box-shadow:inset 0 -3px 0 #f59e0b}}.shared-app-context{{display:grid;grid-template-columns:1fr auto;align-items:center;column-gap:9px;text-align:right}}.shared-app-context span{{grid-column:1/3;color:#93c5fd;font-size:10px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}.shared-app-context strong{{margin-top:3px;color:#fef3c7;font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}.shared-app-context em{{margin-top:3px;color:#7dd3fc;font-size:10px;font-style:normal;white-space:nowrap}}.shared-app-main{{min-height:0;overflow:hidden;position:relative}}.shared-app-main .screen-root{{width:100%!important;height:100%!important;min-height:0!important;max-height:100%!important;overflow:hidden!important}}.shared-app-main .screen-root>header:first-child,.shared-app-main .screen-root>.topbar:first-child,.shared-app-main .screen-root>.mobile-header:first-child,.shared-app-main .screen-root>.app-header:first-child{{display:none!important}}.shared-app-main .screen-root:has(>.mobile-header:first-child){{grid-template-rows:minmax(0,1fr) 78px!important}}@media(max-width:980px){{.shared-app-header{{grid-template-columns:minmax(220px,1fr) auto;padding:0 14px}}.shared-app-nav{{justify-content:flex-end}}.shared-app-nav span{{padding:0 9px}}.shared-app-context{{display:none}}}}.shared-app-shell-mobile_app{{grid-template-rows:72px minmax(0,1fr)}}.shared-app-shell-mobile_app .shared-app-header{{grid-template-columns:minmax(210px,1fr) minmax(300px,1.4fr);gap:10px;padding:0 16px}}.shared-app-shell-mobile_app .shared-app-context{{display:none}}.shared-app-shell-mobile_app .shared-app-nav{{justify-content:flex-end;overflow:hidden}}.shared-app-shell-mobile_app .shared-app-nav span{{padding:0 9px;font-size:11px}}.screen-root{{width:100%;height:100%;overflow:hidden}}
'''


def _build_react_vite_bundle(react_dir: Path) -> None:
    electron_node = os.getenv("SOFT_ELECTRON_NODE", "").strip()
    node = shutil.which("node") or shutil.which("node.exe") or electron_node
    vite_bin = _frontend_node_module_root() / "vite" / "bin" / "vite.js"
    if not node or (not vite_bin.exists() and not os.getenv("SOFT_NODE_MODULE_ROOT", "").strip()):
        raise RuntimeError("缺少随软件提供的 Node/Vite 运行环境，无法构建 React 界面工程")
    env = dict(os.environ)
    if electron_node and str(node).lower() == electron_node.lower():
        env["ELECTRON_RUN_AS_NODE"] = "1"
    result = subprocess.run(
        [node, str(vite_bin), "build", "--config", "vite.runtime.config.js"],
        cwd=str(react_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="ignore",
        timeout=180,
        env=env,
    )
    if result.returncode != 0:
        detail = "\n".join((result.stdout or "").strip().splitlines()[-8:])
        raise RuntimeError(f"React + Vite 界面工程构建失败：{detail[:900]}")


def _frontend_node_module_root() -> Path:
    configured = os.getenv("SOFT_NODE_MODULE_ROOT", "").strip()
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[2] / "node_modules"


def _publish_react_page_entries(prototype_dir: Path, dist_dir: Path, screenshots: list[Any], *, renderer: str) -> None:
    assets_source = dist_dir / "assets"
    assets_target = prototype_dir / "assets"
    if not assets_source.exists():
        raise RuntimeError("React + Vite 构建产物缺少 assets")
    if assets_target.exists():
        shutil.rmtree(assets_target)
    shutil.copytree(assets_source, assets_target)
    css_links = "".join(f'<link rel="stylesheet" href="./assets/{escape(path.name)}">' for path in sorted(assets_target.glob("*.css")))
    for item in screenshots:
        page_key = str(getattr(item, "key", "") or "")
        page_kind = str(getattr(item, "page_kind", "") or "general")
        module_key = str(getattr(item, "module_key", "") or "")
        title = str(getattr(item, "title", "") or page_key)
        html_path = Path(str(getattr(item, "html_path", "") or ""))
        html_path.write_text(
            '<!doctype html><html lang="zh-CN"><head><meta charset="UTF-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">'
            f'<meta name="soft-react-screen" content="{escape(page_key)}"><title>{escape(title)}</title>{css_links}</head>'
            f'<body data-ai-frontend="true" data-renderer="{escape(renderer)}" data-page-kind="{escape(page_kind)}" data-module-key="{escape(module_key)}"><div id="root"></div>'
            f'<script>window.__SOFT_SCREEN_KEY__={json.dumps(page_key, ensure_ascii=False)};</script>'
            '<script type="module" src="./assets/app.js"></script></body></html>',
            encoding="utf-8",
        )


def _generate_stable_component_shell_pages(
    *,
    task: GenerationTask,
    blueprint: ProductBlueprint,
    ui_blueprint: UiBlueprint,
    screenshots: list[Any],
    module_by_key: dict[str, FeatureModule],
    visual_reference_report: dict[str, Any],
    style_reference: dict[str, Any],
    emit=None,
    codegen_progress_start: int = 44,
) -> dict[str, Any]:
    total = len(screenshots)
    pages: list[dict[str, Any]] = []
    design_brief = getattr(ui_blueprint, "design_brief", {}) or {}
    shell_spec = _stable_shell_spec(task, blueprint, ui_blueprint, visual_reference_report)
    for index, item in enumerate(screenshots, start=1):
        progress = codegen_progress_start + min(4, int(index / max(total, 1) * 4))
        _emit(emit, progress, f"根据参考图选择稳定组件架构并生成界面 {index}/{total}")
        page_key = str(getattr(item, "key", "") or f"page_{index}")
        page_kind = str(getattr(item, "page_kind", "") or "general")
        module_key = str(getattr(item, "module_key", "") or "")
        module = module_by_key.get(module_key)
        html_path = Path(str(getattr(item, "html_path", "") or ""))
        if not str(html_path).strip() or html_path.name == "":
            raise RuntimeError(f"{page_key} 缺少界面 HTML 输出路径。")
        html = _stable_shell_html(
            task=task,
            blueprint=blueprint,
            ui_blueprint=ui_blueprint,
            screenshot=item,
            module=module,
            shell_spec=shell_spec,
            design_brief=design_brief,
            index=index,
        )
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(html, encoding="utf-8")
        pages.append(
            {
                "key": page_key,
                "file": html_path.name,
                "page_kind": page_kind,
                "module_key": module_key,
                "source": "stable-component-shell",
                "visual_reference": _report_reference_summary(style_reference),
                "architecture": shell_spec,
            }
        )
        trace_event(
            "ai_frontend_stable_shell_page_success",
            page_key=page_key,
            index=index,
            total=total,
            module_key=module_key,
            page_kind=page_kind,
        )
    return {
        "enabled": True,
        "ready": len(pages) == total,
        "source": "gpt-visual-reference-stable-component-shell",
        "page_count": len(pages),
        "architecture": shell_spec,
        "visual_references": visual_reference_report,
        "pages": pages,
    }


def _stable_shell_spec(task: GenerationTask, blueprint: ProductBlueprint, ui_blueprint: UiBlueprint, visual_reference_report: dict[str, Any]) -> dict[str, Any]:
    design_brief = getattr(ui_blueprint, "design_brief", {}) or {}
    identity = design_brief.get("visual_identity_spec") if isinstance(design_brief, dict) else {}
    reference = visual_reference_report.get("style_reference") if isinstance(visual_reference_report, dict) else {}
    tokens = reference.get("visual_tokens") if isinstance(reference, dict) else []
    return {
        "strategy": "reference-driven-stable-component-shell",
        "renderer": "admin",
        "viewport": "1280x720",
        "shell": "desktop-operations-console",
        "component_library": "local-stable-admin-components",
        "palette_key": str((identity or {}).get("palette_key") or "industrial-teal-amber"),
        "style_tokens": [str(item) for item in (tokens or [])[:8]],
        "software_name": task.software_name,
        "module_count": len(getattr(blueprint, "modules", []) or []),
    }


def _stable_shell_html(
    *,
    task: GenerationTask,
    blueprint: ProductBlueprint,
    ui_blueprint: UiBlueprint,
    screenshot: Any,
    module: FeatureModule | None,
    shell_spec: dict[str, Any],
    design_brief: dict[str, Any],
    index: int,
) -> str:
    page_key = str(getattr(screenshot, "key", "") or f"page_{index}")
    page_kind = str(getattr(screenshot, "page_kind", "") or "general")
    module_key = str(getattr(screenshot, "module_key", "") or "")
    title = str(getattr(screenshot, "title", "") or _page_title(page_kind, module))
    active_module = module or (getattr(blueprint, "modules", []) or [None])[0]
    nav = _stable_nav(blueprint, active_module)
    if page_kind == "login":
        body = _stable_login_body(task, blueprint, shell_spec)
    elif page_kind == "dashboard":
        body = _stable_dashboard_body(task, blueprint, shell_spec)
    elif page_kind == "statistics":
        body = _stable_statistics_body(task, blueprint, shell_spec)
    elif page_kind == "operation":
        body = _stable_operation_body(task, blueprint, active_module, title, shell_spec, screenshot=screenshot)
    else:
        body = _stable_module_body(task, blueprint, active_module, title, shell_spec)
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=1280,height=720,initial-scale=1" />
<title>{escape(title)}</title>
{_stable_shell_css(shell_spec)}
</head>
<body>
<div class="stable-app">
  <aside class="stable-side">
    <div class="stable-brand"><span>{escape(_brand_mark(task.software_name))}</span><b>{escape(_clip(task.software_name, 18))}</b></div>
    <nav>{nav}</nav>
    <div class="stable-side-foot">版本 {escape(task.version)} · 运行监测</div>
  </aside>
  <main class="stable-main">
    <header class="stable-top">
      <div><b>{escape(title)}</b><span>{escape(_clip(blueprint.scenario or blueprint.summary or task.product_type, 54))}</span></div>
      <div class="stable-top-actions"><span>在线</span><span>告警 {len(blueprint.modules) + 7}</span><span>2026-07-10 18:30</span></div>
    </header>
    {body}
  </main>
</div>
</body>
</html>"""
    return _prepare_runtime_html(
        html,
        title=title,
        renderer="admin",
        page_kind=page_kind,
        module_key=module_key,
    )


def _stable_shell_css(shell_spec: dict[str, Any]) -> str:
    return """
<style>
html,body{margin:0;width:1280px;height:720px;overflow:hidden;box-sizing:border-box;background:#f3f6f8;color:#172033;font-family:"Microsoft YaHei","PingFang SC",Arial,sans-serif}
*,*::before,*::after{box-sizing:inherit}
.stable-app{width:1280px;height:720px;display:grid;grid-template-columns:176px 1fr;background:#f3f6f8;overflow:hidden}
.stable-side{min-width:0;background:#172033;color:#dbe7f3;display:flex;flex-direction:column;border-right:1px solid #0f172a}
.stable-brand{height:58px;display:flex;align-items:center;gap:9px;padding:0 13px;border-bottom:1px solid rgba(255,255,255,.08)}
.stable-brand span{width:28px;height:28px;border-radius:6px;background:#0f9f8f;color:#fff;display:grid;place-items:center;font-weight:800}
.stable-brand b{font-size:13px;line-height:1.2;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.stable-side nav{padding:10px 8px;display:grid;gap:5px;overflow:hidden}
.stable-nav-item{height:31px;display:flex;align-items:center;gap:8px;padding:0 9px;border-radius:5px;color:#bfd0df;font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.stable-nav-item.active{background:#0f766e;color:#fff}
.stable-nav-item i{width:7px;height:7px;border-radius:50%;background:#38bdf8;flex:0 0 auto}
.stable-side-foot{margin-top:auto;height:34px;display:flex;align-items:center;padding:0 12px;border-top:1px solid rgba(255,255,255,.08);font-size:11px;color:#94a3b8;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.stable-main{min-width:0;height:720px;display:grid;grid-template-rows:58px 1fr;overflow:hidden}
.stable-top{min-width:0;background:#fff;display:flex;align-items:center;justify-content:space-between;padding:0 18px;border-bottom:1px solid #dbe4ee}
.stable-top b{display:block;font-size:18px;line-height:1.2;max-width:560px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.stable-top span{display:block;margin-top:4px;color:#64748b;font-size:12px;max-width:650px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.stable-top-actions{display:flex;gap:8px;align-items:center;max-width:420px;overflow:hidden}
.stable-top-actions span{margin:0;height:24px;padding:0 8px;border:1px solid #cfe0ed;border-radius:12px;background:#f8fafc;color:#475569;font-size:11px;display:flex;align-items:center;white-space:nowrap}
.stable-workspace{height:662px;padding:12px;display:grid;gap:10px;overflow:hidden}
.stable-grid{display:grid;gap:10px;min-width:0;min-height:0}
.cols-3{grid-template-columns:1.04fr 1.22fr .9fr}.cols-2{grid-template-columns:1.35fr .9fr}.rows-main{grid-template-rows:92px 1fr 188px}
.stable-card{min-width:0;min-height:0;background:#fff;border:1px solid #dbe4ee;border-radius:7px;overflow:hidden;box-shadow:0 6px 18px rgba(15,23,42,.045)}
.stable-card-h{height:34px;display:flex;align-items:center;justify-content:space-between;padding:0 11px;border-bottom:1px solid #e5edf5;background:#f8fafc}
.stable-card-h b{font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.stable-card-h span{font-size:11px;color:#64748b;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.metric-row{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.metric{height:82px;padding:10px;border:1px solid #dbe4ee;border-radius:7px;background:#fff;overflow:hidden}
.metric span{font-size:12px;color:#64748b;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;display:block}.metric b{font-size:23px;line-height:1.2;color:#0f766e;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;display:block;margin-top:7px}
.runtime-record-panel{padding:10px;display:grid;grid-template-columns:1fr 1fr;gap:8px}
.runtime-record-panel div{min-width:0;border:1px solid #e5edf5;border-radius:6px;padding:7px;background:#fbfdff;overflow:hidden}.runtime-record-panel span{display:block;color:#64748b;font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.runtime-record-panel b{display:block;color:#172033;font-size:13px;margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.stable-map{position:relative;height:100%;min-height:210px;background:linear-gradient(135deg,#dcebf1,#f6f1e6);overflow:hidden}
.stable-map::before{content:"";position:absolute;inset:24px;background:repeating-linear-gradient(36deg,rgba(15,118,110,.12) 0 18px,rgba(14,165,233,.10) 19px 32px);border:1px solid rgba(15,118,110,.18)}
.map-pin{position:absolute;min-width:62px;height:24px;border-radius:12px;background:#0f766e;color:#fff;font-size:11px;line-height:24px;text-align:center;padding:0 8px;box-shadow:0 5px 16px rgba(15,118,110,.22);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.p1{left:68px;top:64px}.p2{left:210px;top:118px;background:#d97706}.p3{left:340px;top:72px;background:#dc2626}.p4{left:150px;top:176px;background:#2563eb}
.table-frame{height:100%;overflow:hidden}.stable-table{width:100%;table-layout:fixed;border-collapse:collapse;font-size:12px}.stable-table th,.stable-table td{height:28px;max-height:28px;border-bottom:1px solid #e8eef5;padding:0 8px;line-height:1.12;text-align:left;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.stable-table th{background:#f8fafc;color:#475569;font-weight:700}
.tag{display:inline-flex;height:20px;max-width:100%;align-items:center;justify-content:center;border-radius:10px;padding:0 7px;font-size:11px;line-height:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;border:1px solid #cbd5e1;color:#475569;background:#f8fafc}.tag.green{border-color:#86efac;color:#15803d;background:#f0fdf4}.tag.orange{border-color:#fdba74;color:#c2410c;background:#fff7ed}.tag.red{border-color:#fca5a5;color:#b91c1c;background:#fef2f2}
.stable-actions{display:flex;gap:7px;flex-wrap:wrap;align-content:start;overflow:hidden}.opbtn,.stable-btn{height:22px;max-height:22px;border:1px solid #cbd5e1;background:#fff;border-radius:5px;padding:0 9px;font-size:11px;line-height:1;display:inline-flex;align-items:center;justify-content:center;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:#334155}.opbtn.primary,.stable-btn.primary{background:#0f766e;border-color:#0f766e;color:#fff}
.stable-form{padding:12px;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.stable-form label{display:flex;flex-direction:column;gap:5px;color:#5b6678;font-size:12px}.stable-form input{height:34px;border:1px solid #d6dee8;border-radius:5px;padding:0 9px;background:#fff;color:#172033;box-sizing:border-box;min-width:0}
.stable-upload{margin:12px;padding:18px;border:1px dashed #9fb0c5;border-radius:8px;background:#f8fafc;display:flex;flex-direction:column;gap:10px}.stable-upload b{font-size:15px}.stable-upload span{color:#64748b;font-size:12px}.stable-upload .opbtn{align-self:flex-start}
.operation-result{min-height:42px;padding:9px 10px;border-left:4px solid #0f766e;background:#ecfdf5;color:#166534;font-size:12px;line-height:1.35;overflow:hidden}
.chart-bars{height:180px;display:flex;align-items:end;gap:8px;padding:14px 18px 12px}.chart-bars i{flex:1;border-radius:4px 4px 0 0;background:linear-gradient(180deg,#2dd4bf,#0f766e);min-height:28px}
.login-panel{width:420px;margin:44px auto;background:#fff;border:1px solid #dbe4ee;border-radius:8px;padding:22px;box-shadow:0 14px 44px rgba(15,23,42,.12)}.login-panel input{width:100%;height:34px;border:1px solid #cbd5e1;border-radius:5px;margin:8px 0;padding:0 10px}.login-panel button{width:100%;height:36px;border:0;border-radius:5px;background:#0f766e;color:#fff;font-weight:700}
</style>""".strip()


def _stable_nav(blueprint: ProductBlueprint, active_module: FeatureModule | None) -> str:
    items = [("dashboard", "系统首页"), ("statistics", "统计报表")]
    for module in (getattr(blueprint, "modules", []) or [])[:9]:
        items.insert(-1, (module.key, module.title))
    active_key = getattr(active_module, "key", "") if active_module else "dashboard"
    html = []
    for key, title in items:
        cls = "stable-nav-item active" if key == active_key else "stable-nav-item"
        html.append(f'<div class="{cls}" data-module-key="{escape(key)}"><i></i>{escape(_clip(title, 16))}</div>')
    return "".join(html)


def _stable_login_body(task: GenerationTask, blueprint: ProductBlueprint, shell_spec: dict[str, Any]) -> str:
    return f"""
<section class="stable-workspace">
  <div class="login-panel">
    <h2>{escape(task.software_name)}</h2>
    <p>{escape(_clip(blueprint.positioning or blueprint.summary, 56))}</p>
    <input value="operator@mine.local" aria-label="账号" />
    <input value="******" aria-label="密码" />
    <input value="7K8Q" aria-label="验证码" />
    <button>登录系统</button>
  </div>
</section>"""


def _stable_dashboard_body(task: GenerationTask, blueprint: ProductBlueprint, shell_spec: dict[str, Any]) -> str:
    modules = (getattr(blueprint, "modules", []) or [])[:4]
    metrics = _metric_items(blueprint)
    return f"""
<section class="stable-workspace rows-main">
  <div class="metric-row">{''.join(_metric_card(name, value) for name, value in metrics[:4])}</div>
  <div class="stable-grid cols-3">
    <section class="stable-card"><div class="stable-card-h"><b>当前运行记录</b><span>实时接入</span></div>{_runtime_panel(modules[0] if modules else None)}</section>
    <section class="stable-card"><div class="stable-card-h"><b>设备分布与风险态势</b><span>矿区地图</span></div><div class="stable-map"><span class="map-pin p1">主井提升</span><span class="map-pin p2">皮带运输</span><span class="map-pin p3">温升告警</span><span class="map-pin p4">巡检完成</span></div></section>
    <section class="stable-card"><div class="stable-card-h"><b>处置快捷入口</b><span>待办</span></div><div class="stable-actions" style="padding:12px">{''.join(f'<button class="opbtn">{escape(_clip(module.title, 8))}</button>' for module in modules)}<button class="opbtn primary">生成工单</button><button class="opbtn">审计记录</button></div><div class="operation-result" style="margin:12px">处理结果：记录 KS-2026-1001 已进入“待复核”状态，系统同步写入操作日志并刷新统计口径。</div></section>
  </div>
  <section class="stable-card table-frame"><div class="stable-card-h"><b>核心模块运行明细</b><span>最近更新</span></div>{_stable_table(blueprint, modules, max_rows=3)}</section>
</section>"""


def _stable_module_body(task: GenerationTask, blueprint: ProductBlueprint, module: FeatureModule | None, title: str, shell_spec: dict[str, Any]) -> str:
    return f"""
<section class="stable-workspace">
  <div class="stable-grid cols-2" style="height:100%">
    <section class="stable-card"><div class="stable-card-h"><b>{escape(title)}</b><span>档案与状态</span></div>{_runtime_panel(module)}<div class="operation-result" style="margin:10px">处理结果：记录 KS-2026-1001 已进入“监测中”状态，系统同步写入操作日志并刷新统计口径。</div></section>
    <section class="stable-card"><div class="stable-card-h"><b>趋势与定位</b><span>设备拓扑</span></div><div class="stable-map"><span class="map-pin p1">采集网关</span><span class="map-pin p2">风险点</span><span class="map-pin p3">待维护</span></div></section>
    <section class="stable-card table-frame" style="grid-column:1 / 3"><div class="stable-card-h"><b>业务数据列表</b><span>查询结果</span></div>{_stable_table(blueprint, [module] if module else [], max_rows=4)}</section>
  </div>
</section>"""


def _stable_operation_body(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    module: FeatureModule | None,
    title: str,
    shell_spec: dict[str, Any],
    *,
    screenshot: Any | None = None,
) -> str:
    action = str(getattr(screenshot, "interaction_action", "") or "处理")
    mode = str(getattr(screenshot, "interaction_mode", "") or "workflow")
    fields = list(getattr(module, "data_fields", []) or ["业务编号", "业务名称", "处理状态", "责任人员"])[:6]
    if mode == "query":
        filters = "".join(
            f'<label>{escape(_clip(field, 12))}<input value="{escape(_sample_value(getattr(module, "title", ""), field, index))}" /></label>'
            for index, field in enumerate(fields[:4])
        )
        return f"""
<section class="stable-workspace">
  <section class="stable-card"><div class="stable-card-h"><b>{escape(title)}</b><span>查询条件</span></div><div class="stable-form">{filters}</div><div class="stable-actions" style="padding:0 12px 12px"><button class="opbtn primary">执行查询</button><button class="opbtn">重置条件</button><span>共 18 条结果</span></div></section>
  <section class="stable-card table-frame"><div class="stable-card-h"><b>查询结果列表</b><span>当前范围已刷新</span></div>{_stable_table(blueprint, [module] if module else [], max_rows=4)}<div class="operation-result" style="margin:8px 12px">查询结果：已按当前条件刷新列表，筛选范围和查询时间已记录。</div></section>
</section>"""
    if mode == "form":
        form_fields = "".join(
            f'<label>{escape(_clip(field, 14))}<input value="{escape(_sample_value(getattr(module, "title", ""), field, index))}" /></label>'
            for index, field in enumerate(fields)
        )
        return f"""
<section class="stable-workspace">
  <div class="stable-grid cols-2" style="height:100%">
    <section class="stable-card"><div class="stable-card-h"><b>{escape(title)}</b><span>字段维护</span></div><div class="stable-form">{form_fields}</div><div class="stable-actions" style="padding:0 12px 12px"><button class="opbtn primary">保存{escape(action)}</button><button class="opbtn">取消</button></div></section>
    <section class="stable-card"><div class="stable-card-h"><b>校验与保存结果</b><span>即时检查</span></div>{_runtime_panel(module)}<div class="operation-result" style="margin:10px">保存结果：必填字段已通过校验，记录状态已更新并写入操作日志。</div></section>
  </div>
</section>"""
    if mode == "import":
        return f"""
<section class="stable-workspace">
  <div class="stable-grid cols-2" style="height:100%">
    <section class="stable-card"><div class="stable-card-h"><b>{escape(title)}</b><span>文件与字段映射</span></div><div class="stable-upload"><b>{escape(_clip(getattr(module, "title", "业务数据"), 14))}_20260710.xlsx</b><span>2.8 MB · 126 条记录 · 格式校验通过</span><button class="opbtn">重新选择文件</button></div>{_runtime_panel(module)}</section>
    <section class="stable-card"><div class="stable-card-h"><b>导入校验结果</b><span>可导入 121 / 需修正 5</span></div>{_stable_table(blueprint, [module] if module else [], max_rows=3)}<div class="stable-actions" style="padding:10px"><button class="opbtn primary">确认导入</button><button class="opbtn">下载错误明细</button></div><div class="operation-result" style="margin:0 10px 10px">导入结果：字段映射已完成，5 条异常记录等待修正，其余记录可继续导入。</div></section>
  </div>
</section>"""
    if mode == "export":
        return f"""
<section class="stable-workspace">
  <div class="stable-grid cols-2" style="height:100%">
    <section class="stable-card"><div class="stable-card-h"><b>{escape(title)}</b><span>导出范围</span></div><div class="stable-form"><label>数据范围<input value="当前查询结果 18 条" /></label><label>文件格式<input value="XLSX" /></label><label>字段范围<input value="编号、状态、责任人、更新时间" /></label><label>文件名称<input value="{escape(_clip(getattr(module, "title", "业务数据"), 12))}_20260710" /></label></div><div class="stable-actions" style="padding:0 12px 12px"><button class="opbtn primary">生成导出文件</button><button class="opbtn">预览字段</button></div></section>
    <section class="stable-card"><div class="stable-card-h"><b>文件生成结果</b><span>已完成</span></div>{_runtime_panel(module)}<div class="operation-result" style="margin:10px">导出结果：文件已生成，可下载 XLSX；当前筛选条件、导出人员和生成时间已记录。</div><div class="stable-actions" style="padding:0 10px"><button class="opbtn primary">下载文件</button><button class="opbtn">复制校验码</button></div></section>
  </div>
</section>"""
    if mode == "analysis":
        metrics = _metric_items(blueprint)
        return f"""
<section class="stable-workspace rows-main">
  <div class="metric-row">{''.join(_metric_card(name, value) for name, value in metrics[:4])}</div>
  <div class="stable-grid cols-2"><section class="stable-card"><div class="stable-card-h"><b>{escape(title)}</b><span>近 30 日</span></div><div class="chart-bars"><i style="height:48%"></i><i style="height:66%"></i><i style="height:58%"></i><i style="height:82%"></i><i style="height:72%"></i></div></section><section class="stable-card"><div class="stable-card-h"><b>分组结果</b><span>单位：条 / %</span></div>{_runtime_panel(module)}</section></div>
  <section class="stable-card table-frame"><div class="stable-card-h"><b>统计明细</b><span>当前范围</span></div>{_stable_table(blueprint, [module] if module else [], max_rows=3)}<div class="operation-result" style="margin:8px 12px">统计结果：指标和趋势已按当前范围刷新，可继续导出统计快照。</div></section>
</section>"""
    operations = list(getattr(module, "operations", []) or ["登记", "校验", "分析", "确认", "归档"])[:6]
    return f"""
<section class="stable-workspace">
  <div class="stable-grid cols-2" style="height:100%">
    <section class="stable-card"><div class="stable-card-h"><b>{escape(title)}</b><span>操作处理</span></div>{_runtime_panel(module)}<div class="stable-actions" style="padding:0 10px 10px">{''.join(f'<button class="opbtn{ " primary" if i == 0 else ""}">{escape(_clip(op, 8))}</button>' for i, op in enumerate(operations))}</div><div class="operation-result" style="margin:0 10px 10px">处理结果：记录 KS-2026-1001 已进入“待复核”状态，系统同步写入操作日志并刷新统计口径。</div></section>
    <section class="stable-card"><div class="stable-card-h"><b>处理流程轨迹</b><span>审计留痕</span></div><div class="chart-bars"><i style="height:68%"></i><i style="height:82%"></i><i style="height:54%"></i><i style="height:76%"></i><i style="height:62%"></i></div>{_stable_table(blueprint, [module] if module else [], max_rows=3)}</section>
  </div>
</section>"""


def _stable_statistics_body(task: GenerationTask, blueprint: ProductBlueprint, shell_spec: dict[str, Any]) -> str:
    modules = (getattr(blueprint, "modules", []) or [])[:6]
    return f"""
<section class="stable-workspace rows-main">
  <div class="metric-row">{''.join(_metric_card(name, value) for name, value in _metric_items(blueprint)[:4])}</div>
  <div class="stable-grid cols-2">
    <section class="stable-card"><div class="stable-card-h"><b>近 30 日趋势</b><span>单位：条 / %</span></div><div class="chart-bars"><i style="height:52%"></i><i style="height:68%"></i><i style="height:61%"></i><i style="height:83%"></i><i style="height:74%"></i><i style="height:90%"></i><i style="height:65%"></i></div></section>
    <section class="stable-card"><div class="stable-card-h"><b>风险分布</b><span>分组统计</span></div><div class="stable-map"><span class="map-pin p1">东区 18</span><span class="map-pin p2">西区 11</span><span class="map-pin p3">告警 6</span></div></section>
  </div>
  <section class="stable-card table-frame"><div class="stable-card-h"><b>模块统计明细</b><span>2026-07-10</span></div>{_stable_table(blueprint, modules, max_rows=3)}</section>
</section>"""


def _runtime_panel(module: FeatureModule | None) -> str:
    title = getattr(module, "title", "") or "运行监测"
    fields = list(getattr(module, "data_fields", []) or ["设备编号", "设备名称", "运行状态", "维护人员"])[:4]
    return "<div class=\"runtime-record-panel\">" + "".join(
        f"<div><span>{escape(_clip(field, 12))}</span><b data-runtime-field=\"{escape(key)}\">{escape(_sample_value(title, field, index))}</b></div>"
        for index, (field, key) in enumerate(zip(fields, ["code", "name", "scope", "status"]))
    ) + "</div>"


def _stable_table(blueprint: ProductBlueprint, modules: list[FeatureModule | None], *, max_rows: int = 5) -> str:
    rows = []
    source_modules = [module for module in modules if module] or list(getattr(blueprint, "modules", []) or [])[:5]
    for index, module in enumerate(source_modules[:max(1, max_rows)], start=1):
        status_class = ["green", "orange", "red"][index % 3]
        status = ["正常", "待复核", "未开始"][index % 3]
        rows.append(
            f"<tr><td>KS-2026-{1000 + index}</td><td>{escape(_clip(module.title, 16))}</td><td>{escape(_clip((module.data_fields or ['运行状态'])[0], 12))}</td><td><span class=\"tag {status_class}\">{status}</span></td><td>2026-07-10</td><td><button class=\"opbtn\">查看</button></td></tr>"
        )
    return f"""<table class="stable-table"><thead><tr><th>编号</th><th>模块</th><th>监测项</th><th>状态</th><th>更新时间</th><th>操作</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"""


def _metric_items(blueprint: ProductBlueprint) -> list[tuple[str, str]]:
    metrics = list(getattr(blueprint, "report_metrics", []) or [])[:4]
    defaults = ["在线设备", "异常告警", "维护完成率", "预测准确率"]
    names = (metrics + defaults)[:4]
    values = ["128", "6", "92.6%", "96.8%"]
    return list(zip(names, values))


def _metric_card(name: str, value: str) -> str:
    return f"<div class=\"metric\"><span>{escape(_clip(name, 14))}</span><b>{escape(value)}</b></div>"


def _sample_value(title: str, field: str, index: int) -> str:
    samples = ["KS-2026-1001", title or "运行设备", "主井设备区", "监测中"]
    return samples[index % len(samples)]


def _page_title(page_kind: str, module: FeatureModule | None) -> str:
    if page_kind == "login":
        return "登录界面"
    if page_kind == "dashboard":
        return "系统首页"
    if page_kind == "statistics":
        return "统计报表"
    return getattr(module, "title", "") or "业务界面"


def _brand_mark(name: str) -> str:
    text = str(name or "软").strip()
    return text[0] if text else "软"


def _clip(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: max(1, limit - 1)] + "…"


def generate_style_reference_assets(
    *,
    task: GenerationTask,
    blueprint: ProductBlueprint,
    ui_blueprint: UiBlueprint,
    screenshots: list[Any],
    provider: LLMProvider | None,
    emit=None,
    require_llm: bool = False,
) -> dict[str, Any]:
    if provider is None or isinstance(provider, LocalTemplateProvider):
        if require_llm:
            raise RuntimeError("正式 GPT 流程要求先由 gpt-image-2 生成全局视觉风格参考图。")
        return {"enabled": False, "ready": False, "source": "local-template", "pages": []}
    if not screenshots:
        raise RuntimeError("全局视觉风格参考图缺少页面清单。")
    module_by_key = {module.key: module for module in blueprint.modules}
    design_brief = getattr(ui_blueprint, "design_brief", {}) or {}
    context = _codegen_context(task, blueprint, ui_blueprint)
    return _generate_visual_reference_assets(
        task=task,
        blueprint=blueprint,
        ui_blueprint=ui_blueprint,
        screenshots=screenshots,
        module_by_key=module_by_key,
        provider=provider,
        context=context,
        design_brief=design_brief,
        emit=emit,
        require_llm=require_llm,
    )


def _generate_page_html(
    *,
    task: GenerationTask,
    blueprint: ProductBlueprint,
    ui_blueprint: UiBlueprint,
    provider: LLMProvider,
    screenshot: Any,
    module: FeatureModule | None,
    visual_reference: dict[str, Any] | None,
    context: dict[str, Any],
    design_brief: dict[str, Any],
    index: int,
    total: int,
) -> str:
    page_key = str(getattr(screenshot, "key", "") or f"page_{index}")
    page_kind = str(getattr(screenshot, "page_kind", "") or "general")
    module_key = str(getattr(screenshot, "module_key", "") or "")
    renderer = str(getattr(ui_blueprint, "renderer", "") or "admin")
    prompt = _page_prompt(
        task=task,
        blueprint=blueprint,
        ui_blueprint=ui_blueprint,
        screenshot=screenshot,
        module=module,
        visual_reference=visual_reference,
        context=context,
        design_brief=design_brief,
        index=index,
        total=total,
    )
    user_message: dict[str, Any]
    image_path = Path(str((visual_reference or {}).get("image_path") or ""))
    if image_path.is_file():
        user_message = {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": _image_data_url(image_path)}},
            ],
        }
    else:
        user_message = {"role": "user", "content": prompt}
    started_at = time.perf_counter()
    trace_event(
        "ai_frontend_page_begin",
        page_key=page_key,
        page_kind=page_kind,
        renderer=renderer,
        module_key=module_key,
        index=index,
        total=total,
        visual_reference_ready=image_path.is_file(),
    )
    content = provider.chat(
        [
            {"role": "system", "content": _system_prompt()},
            user_message,
        ],
        temperature=0.48,
        max_tokens=5200,
        response_format={"type": "json_object"},
        trace_label=f"ai_frontend:{page_key}",
        timeout=_ai_frontend_timeout_seconds(provider),
    )
    data = _parse_json(content)
    html = str(data.get("html") or "").strip()
    if len(html) < 1800:
        raise ValueError("模型返回 HTML 过短")
    if not re.search(r"<html\b", html, flags=re.I) or not re.search(r"<body\b", html, flags=re.I):
        raise ValueError("模型返回内容不是完整 HTML 页面")
    _reject_direct_image_embedding(html)
    _reject_internal_visible_terms(html)
    html = _prepare_runtime_html(
        html,
        title=str(getattr(screenshot, "title", "") or page_key),
        renderer=renderer,
        page_kind=page_kind,
        module_key=module_key,
    )
    trace_event(
        "ai_frontend_page_success",
        page_key=page_key,
        elapsed_seconds=round(time.perf_counter() - started_at, 3),
        html_chars=len(html),
    )
    return html


def _load_reusable_page(screenshot: Any, *, creative_key: str = "") -> Path | None:
    html_path = Path(str(getattr(screenshot, "html_path", "") or ""))
    if not html_path.exists() or not html_path.is_file():
        return None
    try:
        html = html_path.read_text(encoding="utf-8")
    except OSError:
        return None
    if len(html) < 1800:
        return None
    if not re.search(r"<html\b", html, flags=re.I) or not re.search(r"<body\b", html, flags=re.I):
        return None
    if creative_key and f'name="soft-creative-key" content="{creative_key}"' not in html:
        return None
    try:
        _reject_direct_image_embedding(html)
        _reject_internal_visible_terms(html)
    except ValueError:
        return None
    return html_path


def _page_creative_key(task: GenerationTask, design_brief: dict[str, Any], screenshot: Any) -> str:
    identity = design_brief.get("visual_identity_spec") if isinstance(design_brief, dict) else {}
    payload = {
        "task_seed": str(getattr(task, "seed", "") or ""),
        "identity_signature": str(identity.get("identity_signature") or "") if isinstance(identity, dict) else "",
        "page_key": str(getattr(screenshot, "key", "") or ""),
        "page_kind": str(getattr(screenshot, "page_kind", "") or ""),
        "module_key": str(getattr(screenshot, "module_key", "") or ""),
    }
    if payload["page_kind"] == "operation":
        payload.update(
            {
                "interaction_action": str(getattr(screenshot, "interaction_action", "") or ""),
                "interaction_mode": str(getattr(screenshot, "interaction_mode", "") or ""),
                "interaction_surface": str(getattr(screenshot, "interaction_surface", "") or ""),
                "requires_confirmation": bool(getattr(screenshot, "requires_confirmation", False)),
                "interaction_action_key": str(getattr(screenshot, "interaction_action_key", "") or ""),
                "interaction_role": str(getattr(screenshot, "interaction_role", "") or ""),
                "interaction_trigger": str(getattr(screenshot, "interaction_trigger", "") or ""),
                "interaction_input_fields": list(getattr(screenshot, "interaction_input_fields", None) or []),
                "interaction_pre_state": str(getattr(screenshot, "interaction_pre_state", "") or ""),
                "interaction_post_state": str(getattr(screenshot, "interaction_post_state", "") or ""),
                "interaction_result_evidence": str(getattr(screenshot, "interaction_result_evidence", "") or ""),
            }
        )
    return sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:20]


def _stamp_creative_key(html: str, creative_key: str) -> str:
    if not creative_key or 'name="soft-creative-key"' in html:
        return html
    marker = f'<meta name="soft-creative-key" content="{creative_key}">'
    return re.sub(r"(<head\b[^>]*>)", rf"\1{marker}", html, count=1, flags=re.I)


def _load_reusable_visual_reference_report(visual_dir: Path, *, image_size: str, total: int, cache_key: str = "") -> dict[str, Any] | None:
    manifest_path = visual_dir / "visual-reference-manifest.json"
    if not manifest_path.exists():
        return None
    try:
        report = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(report, dict) or not report.get("ready"):
        return None
    if str(report.get("mode") or "") != "style_reference":
        return None
    if str(report.get("image_size") or "") and str(report.get("image_size") or "") != image_size:
        return None
    if cache_key and str(report.get("cache_key") or "") != cache_key:
        return None
    style_reference = report.get("style_reference")
    if not isinstance(style_reference, dict):
        return None
    image_path = Path(str(style_reference.get("image_path") or ""))
    if not image_path.exists() or image_path.stat().st_size <= 1024:
        return None
    pages = report.get("pages")
    if not isinstance(pages, list) or not any(isinstance(item, dict) and item.get("ready") for item in pages):
        return None
    report["page_count"] = total
    report["applies_to_page_count"] = total
    style_reference["applies_to_page_count"] = total
    for item in pages:
        if isinstance(item, dict):
            item["applies_to_page_count"] = total
    return report


def _recover_rejected_visual_reference_report(
    *,
    visual_dir: Path,
    image_size: str,
    total: int,
    cache_key: str,
    provider: LLMProvider,
) -> dict[str, Any] | None:
    prompt_path = visual_dir / "style_reference.prompt.json"
    rejected_path = visual_dir / "style_reference.rejected.png"
    image_path = visual_dir / "style_reference.png"
    if not prompt_path.exists() or not rejected_path.exists() or rejected_path.stat().st_size <= 1024:
        return None
    try:
        prompt_payload = json.loads(prompt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if cache_key and str(prompt_payload.get("cache_key") or "") != cache_key:
        return None
    if str(prompt_payload.get("image_size") or "") and str(prompt_payload.get("image_size") or "") != image_size:
        return None
    try:
        raw = rejected_path.read_bytes()
        image_meta = _inspect_generated_image(raw)
        image_path.write_bytes(raw)
        width, height = _image_dimensions(image_path)
    except Exception:
        return None
    prompt_data = prompt_payload.get("prompt") if isinstance(prompt_payload.get("prompt"), dict) else {}
    page_report = {
        "key": "style_reference",
        "mode": "style_reference",
        "reference_page_key": str(prompt_payload.get("reference_page_key") or "dashboard"),
        "page_kind": str(prompt_payload.get("page_kind") or "dashboard"),
        "module_key": str(prompt_payload.get("module_key") or ""),
        "applies_to_page_count": int(prompt_payload.get("applies_to_page_count") or total or 0),
        "prompt_path": str(prompt_path),
        "image_path": str(image_path),
        "image_sha256": _sha256_file(image_path),
        "image_width": width,
        "image_height": height,
        "image_model": _configured_image_model(provider),
        "image_size": image_size,
        "image_source": "recovered_rejected_image",
        "image_quality": image_meta.get("image_quality", {}),
        "prompt_summary": _prompt_summary(prompt_data),
        "ready": True,
        "recovered_from_rejected": True,
    }
    report = _visual_reference_report(
        visual_dir=visual_dir,
        pages=[page_report],
        total=total,
        image_size=image_size,
        cache_key=cache_key,
        provider=provider,
    )
    _write_visual_reference_manifest(visual_dir, report)
    return report


def _recover_existing_visual_reference_report(
    *,
    visual_dir: Path,
    image_size: str,
    total: int,
    cache_key: str,
    task: GenerationTask,
    ui_blueprint: UiBlueprint,
    provider: LLMProvider,
) -> dict[str, Any] | None:
    """Recover a valid style image when only the manifest was overwritten by a failed retry."""
    prompt_path = visual_dir / "style_reference.prompt.json"
    image_path = visual_dir / "style_reference.png"
    if not prompt_path.exists() or not image_path.exists() or image_path.stat().st_size <= 1024:
        return None
    try:
        prompt_payload = json.loads(prompt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if str(prompt_payload.get("image_size") or "") not in {"", image_size}:
        return None
    prompt_total = int(prompt_payload.get("applies_to_page_count") or 0)
    prompt_cache_key = str(prompt_payload.get("cache_key") or "")
    acceptable_keys = {
        cache_key,
        _legacy_visual_reference_cache_key(task, ui_blueprint, prompt_total, image_size),
    }
    if prompt_cache_key and prompt_cache_key not in acceptable_keys:
        return None
    try:
        raw = image_path.read_bytes()
        image_meta = _inspect_generated_image(raw)
        width, height = _image_dimensions(image_path)
    except Exception:
        return None
    prompt_data = prompt_payload.get("prompt") if isinstance(prompt_payload.get("prompt"), dict) else {}
    page_report = {
        "key": "style_reference",
        "mode": "style_reference",
        "reference_page_key": str(prompt_payload.get("reference_page_key") or "dashboard"),
        "page_kind": str(prompt_payload.get("page_kind") or "dashboard"),
        "module_key": str(prompt_payload.get("module_key") or ""),
        "applies_to_page_count": total,
        "prompt_path": str(prompt_path),
        "image_path": str(image_path),
        "image_sha256": _sha256_file(image_path),
        "image_width": width,
        "image_height": height,
        "image_model": _configured_image_model(provider),
        "image_size": image_size,
        "image_source": "recovered_existing_style_reference",
        "image_quality": image_meta.get("image_quality", {}),
        "prompt_summary": _prompt_summary(prompt_data),
        "ready": True,
        "recovered_existing_image": True,
    }
    report = _visual_reference_report(
        visual_dir=visual_dir,
        pages=[page_report],
        total=total,
        image_size=image_size,
        cache_key=cache_key,
        provider=provider,
    )
    _write_visual_reference_manifest(visual_dir, report)
    return report


def _system_prompt() -> str:
    return (
        "你是资深中文企业软件 UI 设计师和前端工程师。"
        "你要为软件著作权操作手册生成真实可运行的界面页面代码。"
        "你会收到 gpt-image-2 生成的全局视觉风格参考图，请按参考图的色彩、密度、导航风格、控件质感和组件语言生成 HTML/CSS。"
        "只返回 JSON 对象，字段为 html。不要返回 Markdown，不要解释。"
        "页面必须像真实软件截图，不能像模板、原型图、营销页或生成说明。"
        "禁止把参考图作为 img、背景图或 data URL 直接嵌入页面，必须用真实 HTML/CSS 组件复刻。"
    )


def _page_prompt(
    *,
    task: GenerationTask,
    blueprint: ProductBlueprint,
    ui_blueprint: UiBlueprint,
    screenshot: Any,
    module: FeatureModule | None,
    visual_reference: dict[str, Any] | None,
    context: dict[str, Any],
    design_brief: dict[str, Any],
    index: int,
    total: int,
) -> str:
    renderer = str(getattr(ui_blueprint, "renderer", "") or "admin")
    viewport = {"admin": "1280x720", "mobile_app": "720x1280", "game": "720x1280"}.get(renderer, "1280x720")
    module_data = _module_payload(module)
    screen_payload = {
        "key": getattr(screenshot, "key", ""),
        "title": getattr(screenshot, "title", ""),
        "caption": getattr(screenshot, "caption", ""),
        "page_kind": getattr(screenshot, "page_kind", ""),
        "module_key": getattr(screenshot, "module_key", ""),
        "page_structure_seed": _page_creative_key(task, design_brief, screenshot),
        "interaction_action": str(getattr(screenshot, "interaction_action", "") or ""),
        "interaction_mode": str(getattr(screenshot, "interaction_mode", "") or ""),
        "interaction_surface": str(getattr(screenshot, "interaction_surface", "") or ""),
        "requires_confirmation": bool(getattr(screenshot, "requires_confirmation", False)),
        "interaction_action_key": str(getattr(screenshot, "interaction_action_key", "") or ""),
        "interaction_role": str(getattr(screenshot, "interaction_role", "") or ""),
        "interaction_trigger": str(getattr(screenshot, "interaction_trigger", "") or ""),
        "interaction_input_fields": list(getattr(screenshot, "interaction_input_fields", None) or []),
        "interaction_pre_state": str(getattr(screenshot, "interaction_pre_state", "") or ""),
        "interaction_post_state": str(getattr(screenshot, "interaction_post_state", "") or ""),
        "interaction_result_evidence": str(getattr(screenshot, "interaction_result_evidence", "") or ""),
    }
    visual_identity = design_brief.get("visual_identity_spec") if isinstance(design_brief, dict) else {}
    product_experience = design_brief.get("product_experience_spec") if isinstance(design_brief, dict) else {}
    reference_payload = _prompt_reference_payload(visual_reference)
    operation_rule = _operation_prompt_rule(screenshot) or "按当前页面层级生成真实可操作界面。"
    return f"""
请生成第 {index}/{total} 张操作手册截图对应的完整 HTML 页面。

软件上下文：
{json.dumps(context, ensure_ascii=False, indent=2)}

当前页面：
{json.dumps(screen_payload, ensure_ascii=False, indent=2)}

当前模块：
{json.dumps(module_data, ensure_ascii=False, indent=2)}

产品体验规格：
{json.dumps(product_experience if isinstance(product_experience, dict) else {{}}, ensure_ascii=False, indent=2)}

视觉身份规格：
{json.dumps(visual_identity if isinstance(visual_identity, dict) else {{}}, ensure_ascii=False, indent=2)}

gpt-image-2 全局视觉风格参考图：
{json.dumps(reference_payload, ensure_ascii=False, indent=2)}

强制要求：
- 只返回 JSON：{{"html":"完整 HTML 字符串"}}
- 画布尺寸必须适合 {viewport}，页面首屏必须铺满，不能右侧大空白，不能像线框图。
- renderer={renderer}；如果是 admin，要像真实桌面业务软件；如果是 mobile_app，要像真实手机 App/小程序；如果是 game，要像真实手机游戏界面。
- 如果 renderer 是 mobile_app 或 game，根内容壳必须铺满 720px 逻辑宽度；禁止 `max-width:375px/390px/430px`、窄手机模型居中或左右大面积空白。
- 页面内容必须严格围绕软件名称、模块字段、业务对象、流程、统计指标和当前页面用途设计。
- {operation_rule}
- 必须根据随消息附带的全局风格参考图延续视觉语言：导航风格、控件边界、卡片密度、表格/图表/地图/面板质感、色彩和留白应与参考图一致；同一材料包所有页面必须使用同一套字体、主色、侧栏/顶栏外壳、按钮样式、状态标签样式和表格密度。
- 参考图只提供全局风格，不代表当前页面结构；当前页面必须按“当前页面”和“当前模块”的用途重新组织布局，不能复制参考图成为所有页面同构。
- `page_structure_seed` 是本页独有的构图种子。请据此自主决定信息层级、主工作区占比、侧面板位置、控件组合和阅读动线；禁止套用固定的“侧栏 + 四指标卡 + 筛选栏 + 表格”骨架。
- 相邻页面至少在以下三项中有两项明显不同：主内容拓扑、首屏视觉焦点、工具区位置、数据呈现方式、操作路径。共享设计语言不等于共享 DOM 骨架。
- 参考图只用于视觉约束，禁止把参考图、提示词、gpt-image-2、视觉参考稿等词写到页面中，禁止直接嵌入参考图图片。
- 同一本手册内页面结构要有差异：登录、首页、主界面、查询、导入、导出、统计、复核/发布等不能只是同背景加弹窗。
- 使用内联 CSS，不引用外部 CDN、图片、字体或网络资源，不使用 SVG 大面积插画，不写营销介绍。
- 可使用纯 HTML/CSS 表格、图表、地图感工作区、工单卡片、时间线、审批栏、设备面板等真实业务组件。
- 所有文字必须在 1280x720 或 720x1280 画布内可读且不重叠：按钮、状态标签、表格单元格、长编号、指标数字必须使用 nowrap、ellipsis、固定行高或足够容器宽度；禁止让“待确认”“开始校验”“当前记录编号”等文字竖向断行、越过边框或压到相邻内容。
- 装饰性柱、进度条、趋势块必须放在独立绘图区内，禁止用 absolute/fixed 把无文字色块叠在指标数字、状态名称、辅助说明或坐标标签上；同一指标卡已有数字和文字时，不要再叠加会穿过文字的装饰柱。
- 每个面板标题必须能概括面板内全部直接子项；当子项横跨检验批、材料、试验、测量、隐蔽验收等多个模块时，使用“综合质量任务”“业务任务进度”等上位名称，禁止只用其中一两个模块命名整个面板。
- 所有可见文字必须是客户能看到的业务语言，禁止出现：AI、GPT、提示词、image2、视觉参考、参考稿、接口返回、运行服务、生成项目、浏览器页面、source-ui-evidence、generated_source、ui-prototype。
- 页面中要预留可被运行数据覆盖的可见业务区域：表格可使用 .table-frame，当前记录卡可使用 .runtime-record-panel，地图点可使用 .map-pin，处理结果可使用 .operation-result。
- 不要写任何 API Key、Base URL、真实公司信息或承诺包过。
""".strip()


def _generate_visual_reference_assets(
    *,
    task: GenerationTask,
    blueprint: ProductBlueprint,
    ui_blueprint: UiBlueprint,
    screenshots: list[Any],
    module_by_key: dict[str, FeatureModule],
    provider: LLMProvider,
    context: dict[str, Any],
    design_brief: dict[str, Any],
    emit,
    require_llm: bool,
) -> dict[str, Any]:
    total = len(screenshots)
    visual_dir = _visual_reference_dir(screenshots)
    visual_dir.mkdir(parents=True, exist_ok=True)
    pages: list[dict[str, Any]] = []
    image_size = _visual_reference_size(str(getattr(ui_blueprint, "renderer", "") or "admin"))
    cache_key = _visual_reference_cache_key(task, ui_blueprint, total, image_size)
    cached_report = _load_reusable_visual_reference_report(visual_dir, image_size=image_size, total=total, cache_key=cache_key)
    if cached_report:
        _emit(emit, 43, "复用已生成的 gpt-image-2 全局视觉风格参考图")
        trace_event(
            "ai_visual_reference_reused",
            image_model=str(cached_report.get("image_model") or ""),
            image_size=str(cached_report.get("image_size") or ""),
            reference_count=int(cached_report.get("reference_count") or 0),
        )
        return cached_report
    existing_report = _recover_existing_visual_reference_report(
        visual_dir=visual_dir,
        image_size=image_size,
        total=total,
        cache_key=cache_key,
        task=task,
        ui_blueprint=ui_blueprint,
        provider=provider,
    )
    if existing_report:
        _emit(emit, 43, "复用现有全局视觉风格参考图")
        return existing_report
    recovered_report = _recover_rejected_visual_reference_report(
        visual_dir=visual_dir,
        image_size=image_size,
        total=total,
        cache_key=cache_key,
        provider=provider,
    )
    if recovered_report:
        _emit(emit, 43, "复用已恢复的 gpt-image-2 全局视觉风格参考图")
        return recovered_report
    item = _select_style_reference_screenshot(screenshots)
    page_key = "style_reference"
    reference_page_key = str(getattr(item, "key", "") or "page_1")
    _emit(emit, 42, "生成全局视觉风格提示词")
    module = module_by_key.get(str(getattr(item, "module_key", "") or ""))
    image_path = visual_dir / "style_reference.png"
    prompt_path = visual_dir / "style_reference.prompt.json"
    try:
        prompt_data = _generate_visual_prompt(
            task=task,
            blueprint=blueprint,
            ui_blueprint=ui_blueprint,
            provider=provider,
            screenshot=item,
            module=module,
            context=context,
            design_brief=design_brief,
            index=1,
            total=1,
        )
        prompt_text = _style_reference_prompt_text(
            prompt_data,
            task=task,
            blueprint=blueprint,
            ui_blueprint=ui_blueprint,
            screenshot=item,
            module=module,
            design_brief=design_brief,
        )
        _validate_image_prompt_text(prompt_text)
        prompt_path.write_text(
            json.dumps(
                {
                    "key": page_key,
                    "mode": "style_reference",
                    "reference_page_key": reference_page_key,
                    "page_kind": str(getattr(item, "page_kind", "") or ""),
                    "module_key": str(getattr(item, "module_key", "") or ""),
                    "applies_to_page_count": total,
                    "cache_key": cache_key,
                    "prompt": prompt_data,
                    "image_prompt_text": prompt_text,
                    "image_size": image_size,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        _emit(emit, 43, "生成 gpt-image-2 全局视觉风格参考图")
        image_meta = provider.generate_image(
            prompt=prompt_text,
            output_path=image_path,
            size=image_size,
            trace_label="ui_visual_reference:style_reference",
        )
        width, height = _image_dimensions(image_path)
        page_report = {
            "key": page_key,
            "mode": "style_reference",
            "reference_page_key": reference_page_key,
            "page_kind": str(getattr(item, "page_kind", "") or ""),
            "module_key": str(getattr(item, "module_key", "") or ""),
            "applies_to_page_count": total,
            "prompt_path": str(prompt_path),
            "image_path": str(image_path),
            "image_sha256": _sha256_file(image_path),
            "image_width": width,
            "image_height": height,
            "image_model": image_meta.get("model", ""),
            "image_size": image_meta.get("size", image_size),
            "image_source": image_meta.get("source", ""),
            "image_quality": image_meta.get("image_quality", {}),
            "prompt_summary": _prompt_summary(prompt_data),
            "ready": image_path.exists() and image_path.stat().st_size > 1024,
        }
        pages.append(page_report)
    except Exception as exc:
        safe_error = sanitize_error_message(exc, limit=500)
        pages.append(
            {
                "key": page_key,
                "mode": "style_reference",
                "reference_page_key": reference_page_key,
                "page_kind": str(getattr(item, "page_kind", "") or ""),
                "module_key": str(getattr(item, "module_key", "") or ""),
                "applies_to_page_count": total,
                "prompt_path": str(prompt_path if prompt_path.exists() else ""),
                "image_path": str(image_path),
                "image_model": _configured_image_model(provider),
                "image_size": image_size,
                "ready": False,
                "error": safe_error,
            }
        )
        failure_report = _visual_reference_report(
            visual_dir=visual_dir,
            pages=pages,
            total=total,
            image_size=image_size,
            cache_key=cache_key,
            provider=provider,
            error=safe_error,
            failed_page_key=page_key,
        )
        _write_visual_reference_manifest(visual_dir, failure_report)
        if require_llm:
            raise RuntimeError(f"全局视觉风格参考图生成失败：{safe_error}") from exc
    report = _visual_reference_report(
        visual_dir=visual_dir,
        pages=pages,
        total=total,
        image_size=image_size,
        cache_key=cache_key,
        provider=provider,
    )
    _write_visual_reference_manifest(visual_dir, report)
    return report


def _visual_reference_report(
    *,
    visual_dir: Path,
    pages: list[dict[str, Any]],
    total: int,
    image_size: str,
    provider: LLMProvider,
    cache_key: str = "",
    error: str = "",
    failed_page_key: str = "",
) -> dict[str, Any]:
    ready_count = sum(1 for item in pages if item.get("ready"))
    prompt_ready_count = sum(1 for item in pages if item.get("prompt_path") and Path(str(item.get("prompt_path"))).exists())
    image_model = next((str(item.get("image_model") or "") for item in pages if item.get("image_model")), "")
    if not image_model:
        image_model = _configured_image_model(provider)
    style_reference = next((item for item in pages if item.get("ready")), pages[0] if pages else {})
    report = {
        "enabled": True,
        "mode": "style_reference",
        "ready": ready_count >= 1,
        "prompt_ready": prompt_ready_count >= 1,
        "source": "gpt-style-reference-prompt+image2",
        "prompt_count": len(pages),
        "prompt_ready_count": prompt_ready_count,
        "reference_count": ready_count,
        "reference_target_count": len(pages) or 1,
        "page_count": total,
        "applies_to_page_count": total,
        "style_reference": style_reference,
        "style_reference_ready": bool(style_reference.get("ready")) if isinstance(style_reference, dict) else False,
        "image_size": image_size,
        "cache_key": cache_key,
        "image_model": image_model,
        "image_retry_count": _configured_image_retry_count(provider),
        "directory": str(visual_dir),
        "pages": pages,
    }
    if error:
        report["error"] = error
    if failed_page_key:
        report["failed_page_key"] = failed_page_key
    return report


def _visual_reference_cache_key(task: GenerationTask, ui_blueprint: UiBlueprint, total: int, image_size: str) -> str:
    design_brief = getattr(ui_blueprint, "design_brief", {}) or {}
    identity = design_brief.get("visual_identity_spec") if isinstance(design_brief, dict) else {}
    experience = design_brief.get("product_experience_spec") if isinstance(design_brief, dict) else {}
    payload = {
        "cache_contract": "style-identity-v2",
        "creative_seed": str(getattr(task, "seed", "") or ""),
        "software_name": str(getattr(task, "software_name", "") or ""),
        "product_type": str(getattr(task, "product_type", "") or ""),
        "renderer": str(getattr(ui_blueprint, "renderer", "") or ""),
        "identity_signature": str(identity.get("identity_signature") or "") if isinstance(identity, dict) else "",
        "experience_shape": str(experience.get("experience_shape") or "") if isinstance(experience, dict) else "",
        "image_size": str(image_size or ""),
    }
    return sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:24]


def _legacy_visual_reference_cache_key(
    task: GenerationTask,
    ui_blueprint: UiBlueprint,
    total: int,
    image_size: str,
) -> str:
    design_brief = getattr(ui_blueprint, "design_brief", {}) or {}
    identity = design_brief.get("visual_identity_spec") if isinstance(design_brief, dict) else {}
    experience = design_brief.get("product_experience_spec") if isinstance(design_brief, dict) else {}
    payload = {
        "creative_seed": str(getattr(task, "seed", "") or ""),
        "software_name": str(getattr(task, "software_name", "") or ""),
        "product_type": str(getattr(task, "product_type", "") or ""),
        "renderer": str(getattr(ui_blueprint, "renderer", "") or ""),
        "identity_signature": str(identity.get("identity_signature") or "") if isinstance(identity, dict) else "",
        "experience_shape": str(experience.get("experience_shape") or "") if isinstance(experience, dict) else "",
        "page_count": int(total or 0),
        "image_size": str(image_size or ""),
    }
    return sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:24]


def _select_style_reference_screenshot(screenshots: list[Any]) -> Any:
    if not screenshots:
        raise RuntimeError("AI 前端代码生成缺少截图页面清单。")

    def score(item: Any) -> int:
        key = str(getattr(item, "key", "") or "").lower()
        page_kind = str(getattr(item, "page_kind", "") or "").lower()
        title = str(getattr(item, "title", "") or "")
        text = f"{key} {page_kind} {title}".lower()
        if page_kind == "dashboard" or "dashboard" in text or "首页" in title or "主界面" in title:
            return 100
        if page_kind in {"home", "main"}:
            return 90
        if page_kind == "module":
            return 70
        if page_kind == "login":
            return 40
        return 50

    return max(screenshots, key=score)


def _write_visual_reference_manifest(visual_dir: Path, report: dict[str, Any]) -> None:
    visual_dir.mkdir(parents=True, exist_ok=True)
    (visual_dir / "visual-reference-manifest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _configured_image_model(provider: LLMProvider) -> str:
    config = getattr(provider, "config", None)
    if config is None:
        return ""
    try:
        return image_model_name(config)
    except Exception:
        return str(getattr(config, "image_model", "") or "")


def _configured_image_retry_count(provider: LLMProvider) -> int:
    config = getattr(provider, "config", None)
    if config is None:
        return 0
    return int(getattr(config, "image_retry_count", getattr(config, "retry_count", 0)) or 0)


def _generate_visual_prompt(
    *,
    task: GenerationTask,
    blueprint: ProductBlueprint,
    ui_blueprint: UiBlueprint,
    provider: LLMProvider,
    screenshot: Any,
    module: FeatureModule | None,
    context: dict[str, Any],
    design_brief: dict[str, Any],
    index: int,
    total: int,
) -> dict[str, Any]:
    page_key = str(getattr(screenshot, "key", "") or f"page_{index}")
    page_kind = str(getattr(screenshot, "page_kind", "") or "general")
    started_at = time.perf_counter()
    trace_event(
        "ai_visual_prompt_begin",
        page_key=page_key,
        page_kind=page_kind,
        renderer=str(getattr(ui_blueprint, "renderer", "") or ""),
        index=index,
        total=total,
    )
    content = provider.chat(
        [
            {"role": "system", "content": _visual_prompt_system_prompt()},
            {
                "role": "user",
                "content": _visual_prompt_user_prompt(
                    task=task,
                    blueprint=blueprint,
                    ui_blueprint=ui_blueprint,
                    screenshot=screenshot,
                    module=module,
                    context=context,
                    design_brief=design_brief,
                    index=index,
                    total=total,
                ),
            },
        ],
        temperature=0.62,
        max_tokens=1800,
        response_format={"type": "json_object"},
        trace_label=f"ui_visual_prompt:{page_key}",
    )
    data = _parse_json(content)
    prompt = str(data.get("visual_prompt") or "").strip()
    if len(prompt) < 180:
        raise ValueError("视觉提示词过短")
    data["visual_prompt"] = prompt
    data.setdefault("layout_brief", "")
    data.setdefault("negative_prompt", "")
    data.setdefault("visual_tokens", [])
    trace_event(
        "ai_visual_prompt_success",
        page_key=page_key,
        elapsed_seconds=round(time.perf_counter() - started_at, 3),
        prompt_chars=len(prompt),
    )
    return data


def _visual_prompt_system_prompt() -> str:
    return (
        "你是资深企业软件视觉总监。"
        "请编写供图片生成模型使用的真实软件界面截图提示词，只返回 JSON，不要 Markdown。"
        "提示词必须用于生成单张高保真软件运行界面截图，不要解释生成过程。"
    )


def _visual_prompt_user_prompt(
    *,
    task: GenerationTask,
    blueprint: ProductBlueprint,
    ui_blueprint: UiBlueprint,
    screenshot: Any,
    module: FeatureModule | None,
    context: dict[str, Any],
    design_brief: dict[str, Any],
    index: int,
    total: int,
) -> str:
    renderer = str(getattr(ui_blueprint, "renderer", "") or "admin")
    viewport = {"admin": "1280x720 横向 16:9 桌面软件", "mobile_app": "720x1280 竖向 9:16 手机界面", "game": "720x1280 竖向 9:16 手机游戏"}.get(renderer, "1280x720 横向 16:9 桌面软件")
    screen_payload = {
        "key": getattr(screenshot, "key", ""),
        "title": getattr(screenshot, "title", ""),
        "caption": getattr(screenshot, "caption", ""),
        "page_kind": getattr(screenshot, "page_kind", ""),
        "module_key": getattr(screenshot, "module_key", ""),
    }
    payload = {
        "creative_seed": str(getattr(task, "seed", "") or ""),
        "software_context": context,
        "screen": screen_payload,
        "module": _module_payload(module),
        "product_experience_spec": design_brief.get("product_experience_spec") if isinstance(design_brief, dict) else {},
        "visual_identity_spec": design_brief.get("visual_identity_spec") if isinstance(design_brief, dict) else {},
    }
    return f"""
请为第 {index}/{total} 张软著说明书界面生成图片参考稿提示词。

输入上下文：
{json.dumps(payload, ensure_ascii=False, indent=2)}

要求：
- 参考稿必须是 {viewport} 的真实软件截图视觉稿，不是营销海报、线框图、插画或说明页。
- `visual_prompt` 必须以“单张软件运行界面截图：”开头，第一句话就写清楚软件名称和当前页面名称。
- 必须根据软件名称、业务对象、模块字段、统计指标和当前页面角色设计，不能像通用模板。
- creative_seed 只用于本次任务的原创构图选择；请把它解释为独立的版式方向、空间比例、导航关系和组件节奏，不要在画面中显示 seed。
- 不要默认使用常见后台四宫格。可按业务选择主从分栏、工作台、时间轴、地图联动、流程泳道、矩阵、任务板、档案阅读器或监测台等不同构图。
- 同一本手册每页要形成不同截图角色：登录、首页、模块工作区、操作处理、统计分析的结构应明显不同。
- 明确写出导航形态、主体工作区、控件密度、表格/图表/地图/看板/流程/面板布局、配色和业务文字氛围。
- 可出现少量中文业务界面文字，但不要出现任何生成说明、模型说明、提示词、接口、Base URL、API Key、内部文件名。
- 不要让参考稿出现知识讲解页、概念对比页、VS 图、教程海报、水印、浏览器地址栏、代码、英文占位、乱码或大面积空白。

返回 JSON：
{{
  "visual_prompt": "给图片模型的完整中文提示词，包含画面比例、布局、组件、色彩、业务内容和真实软件质感",
  "layout_brief": "一句话描述页面布局",
  "negative_prompt": "需要避免的视觉问题",
  "visual_tokens": ["导航/布局/组件/配色等关键词"]
}}
""".strip()


def _image_prompt_text(
    prompt_data: dict[str, Any],
    *,
    task: GenerationTask,
    blueprint: ProductBlueprint,
    ui_blueprint: UiBlueprint,
    screenshot: Any,
    module: FeatureModule | None,
    design_brief: dict[str, Any],
) -> str:
    page_kind = str(getattr(screenshot, "page_kind", "") or "general")
    is_module_page = page_kind == "module"
    visual_prompt = _shorten_prompt_part(
        _sanitize_image_prompt_terms(str(prompt_data.get("visual_prompt") or "").strip()),
        340 if is_module_page else 520,
    )
    layout = _shorten_prompt_part(
        _sanitize_image_prompt_terms(str(prompt_data.get("layout_brief") or "").strip()),
        130 if is_module_page else 160,
    )
    tokens = "、".join(
        _sanitize_image_prompt_terms(str(item))
        for item in prompt_data.get("visual_tokens", [])[:12]
        if str(item).strip()
    )
    parts = [
        _image_prompt_context_frame(
            task=task,
            blueprint=blueprint,
            ui_blueprint=ui_blueprint,
            screenshot=screenshot,
            module=module,
            design_brief=design_brief,
        ),
        visual_prompt,
    ]
    if layout:
        parts.append(f"布局约束：{layout}")
    if tokens:
        parts.append(f"视觉关键词：{tokens}")
    if is_module_page:
        parts.append(
            "桌面软件骨架：顶部项目栏、左侧深色模块导航、筛选工具栏、主操作按钮、业务数据表格、指标卡片、流程或图表面板必须清晰可见。"
            "地图、三维场景或遥感影像只能作为其中一个业务卡片内的视窗，周围必须有表格、按钮、状态标签和操作日志。"
        )
    parts.append("画面要求：仅生成一张运行中的软件界面截图，首屏完整铺满画面，有真实控件边界、导航、表格/图表/表单/地图/面板、按钮、状态标签和业务数据。")
    parts.append("画面内容限定：只呈现该软件自身的业务菜单、字段、数值、流程状态、操作按钮和工作区内容。")
    return _limit_image_prompt_text("\n".join(parts), default_limit=720 if is_module_page else 820)


def _style_reference_prompt_text(
    prompt_data: dict[str, Any],
    *,
    task: GenerationTask,
    blueprint: ProductBlueprint,
    ui_blueprint: UiBlueprint,
    screenshot: Any,
    module: FeatureModule | None,
    design_brief: dict[str, Any],
) -> str:
    renderer = str(getattr(ui_blueprint, "renderer", "") or "admin")
    viewport = "720x1280 竖屏手机界面" if renderer in {"mobile_app", "game"} else "1280x720 横向桌面软件界面"
    layout = _shorten_prompt_part(
        _sanitize_image_prompt_terms(str(prompt_data.get("layout_brief") or "").strip()),
        110,
    )
    visual_excerpt = _shorten_prompt_part(
        _sanitize_image_prompt_terms(str(prompt_data.get("visual_prompt") or "").strip()),
        190,
    )
    tokens = "、".join(
        _sanitize_image_prompt_terms(str(item))
        for item in prompt_data.get("visual_tokens", [])[:10]
        if str(item).strip()
    )
    business_terms = _image_prompt_business_terms(blueprint=blueprint, module=module)
    if renderer in {"mobile_app", "game"}:
        skeleton = (
            "手机软件界面必须占满画面，并根据业务自主选择沉浸式工作区、卡片流、分段列表、地图联动或任务面板；"
            "状态栏、导航与主操作的关系要像真实产品，但不要强制复用固定的顶部栏加底部标签骨架。"
        )
    else:
        skeleton = (
            "桌面业务软件界面必须占画面主体，并依据业务自主选择侧栏、顶栏、双栏工作台、监测墙、流程台、档案台或地图联动等构图；"
            "画面至少 70% 是可识别的软件控件与工作区，地图或三维视图必须与真实业务控件形成联动，不能成为纯场景图。"
        )
    parts = [
        f"生成一张全局视觉风格参考图：{task.software_name}，{viewport}，必须是单张真实软件运行界面截图。",
        f"本次原创构图种子：{task.seed}。种子只用于选择独立的空间比例、导航形态、信息密度和组件节奏，不得显示在画面中。",
        skeleton,
        f"业务文字围绕：{business_terms}。",
    ]
    if layout:
        parts.append(f"布局方向：{layout}")
    if tokens:
        parts.append(f"视觉关键词：{tokens}")
    if visual_excerpt:
        parts.append(f"风格细节参考：{visual_excerpt}")
    parts.append(
        "严格禁止生成海报、概念图、纯地图、纯三维场景、空白占位图、问号占位图、浏览器地址栏、代码窗口或教程说明页；"
        "必须有大量横平竖直的软件控件边界。"
    )
    return _limit_image_prompt_text("\n".join(parts), default_limit=860)


def _validate_image_prompt_text(value: str) -> None:
    text = str(value or "")
    if re.search(r"\?{4,}", text):
        raise ValueError("视觉提示词包含疑似乱码，已停止图片生成。")
    if re.search(r"(?i)app\s*(?:与|和|vs|/)\s*tab", text):
        raise ValueError("视觉提示词仍包含 App/Tab 对比语义，已停止图片生成。")


def _image_prompt_context_frame(
    *,
    task: GenerationTask,
    blueprint: ProductBlueprint,
    ui_blueprint: UiBlueprint,
    screenshot: Any,
    module: FeatureModule | None,
    design_brief: dict[str, Any],
) -> str:
    renderer = str(getattr(ui_blueprint, "renderer", "") or "admin")
    renderer_label = {
        "admin": "横向桌面业务软件窗口",
        "mobile_app": "竖屏手机业务软件界面",
        "game": "竖屏手机游戏运行界面",
    }.get(renderer, "横向桌面业务软件窗口")
    screen_title = str(getattr(screenshot, "title", "") or getattr(screenshot, "key", "") or "业务页面")
    module_title = str(getattr(module, "title", "") or "")
    experience = {}
    if isinstance(design_brief, dict):
        raw_experience = design_brief.get("product_experience_spec")
        experience = raw_experience if isinstance(raw_experience, dict) else {}
    business_terms = _image_prompt_business_terms(blueprint=blueprint, module=module)
    subject = f"{task.software_name} - {screen_title}"
    if module_title and module_title not in subject:
        subject = f"{subject} / {module_title}"
    terminal = str(experience.get("terminal") or renderer_label)
    return (
        f"单张软件运行界面截图：{subject}。"
        f"画面载体为{renderer_label}，目标终端为{terminal}，只能表现该软件正在使用中的业务操作界面。"
        f"可见中文业务词围绕：{business_terms}。"
    )


def _image_prompt_business_terms(*, blueprint: ProductBlueprint, module: FeatureModule | None) -> str:
    terms: list[str] = []
    if module is not None:
        terms.extend([module.title, module.description])
        terms.extend(module.operations[:4])
        terms.extend(module.data_fields[:5])
    terms.extend(blueprint.business_objects[:5])
    terms.extend(blueprint.report_metrics[:4])
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in terms:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        cleaned.append(text)
    return "、".join(cleaned[:12]) or "业务台账、状态监测、处理记录、统计指标"


def _sanitize_image_prompt_terms(value: str) -> str:
    text = str(value or "")
    replacements = [
        (r"(?i)app[\s\S]{0,8}tab", "软件运行界面"),
        (r"(?i)tab[\s\S]{0,8}app", "软件运行界面"),
        (r"(?i)app\s*(?:与|和|vs|/)\s*tab", "软件运行界面"),
        (r"(?i)tab\s*(?:与|和|vs|/)\s*app", "软件运行界面"),
        (r"(?:概念|知识)?(?:区别|对比|比较)(?:风格|页面|图)?", "运行界面"),
        (r"(?:说明|教程|科普|宣传)(?:页|图|海报|画面|风格)?", "运行界面"),
        (r"(?:不是|避免|不要|禁止|不得)[^。；\n]{0,20}", ""),
        (r"(?i)\btabs?\b", "软件内标签页"),
        (r"(?i)\bapp\b", "手机端业务界面"),
        (r"\bAPP\b", "手机端业务界面"),
        (r"(?i)\bimage2\b", "图片模型"),
    ]
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text)
    return text


def _shorten_prompt_part(value: str, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    for marker in ("。", "；", "，", "、", ";", ","):
        marker_index = cut.rfind(marker)
        if marker_index >= int(limit * 0.65):
            cut = cut[: marker_index + 1]
            break
    return cut.rstrip("，、；;,. ") + "。"


def _limit_image_prompt_text(value: str, *, default_limit: int = 760) -> str:
    raw_limit = os.getenv("SOFT_UI_VISUAL_REFERENCE_PROMPT_CHARS", "").strip()
    try:
        limit = max(560, min(1800, int(raw_limit))) if raw_limit else default_limit
    except ValueError:
        limit = default_limit
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    required_tail = (
        "必须是单张高保真软件运行界面截图，有清晰业务控件、导航、卡片、表格或图表；"
        "画面只包含该软件正在运行的业务界面和真实控件。"
    )
    head_limit = max(300, limit - len(required_tail) - 1)
    return f"{text[:head_limit].rstrip()} {required_tail}"


def _visual_reference_dir(screenshots: list[Any]) -> Path:
    for item in screenshots:
        html_path = Path(str(getattr(item, "html_path", "") or ""))
        if html_path:
            return html_path.parent / "visual-references"
    return Path("visual-references")


def _visual_reference_size(renderer: str) -> str:
    explicit = os.getenv("SOFT_UI_VISUAL_REFERENCE_SIZE", "").strip()
    if explicit:
        return explicit
    if renderer in {"mobile_app", "game"}:
        return os.getenv("SOFT_UI_VISUAL_REFERENCE_MOBILE_SIZE", "720x1280").strip() or "720x1280"
    return os.getenv("SOFT_UI_VISUAL_REFERENCE_DESKTOP_SIZE", "1280x720").strip() or "1280x720"


def _visual_reference_ready(reference: dict[str, Any] | None) -> bool:
    if not isinstance(reference, dict) or not reference.get("ready"):
        return False
    image_path = Path(str(reference.get("image_path") or ""))
    return image_path.exists() and image_path.stat().st_size > 1024


def _report_reference_summary(reference: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(reference, dict):
        return {"ready": False}
    return {
        "ready": bool(reference.get("ready")),
        "mode": str(reference.get("mode") or ""),
        "reference_page_key": str(reference.get("reference_page_key") or ""),
        "applies_to_page_count": int(reference.get("applies_to_page_count") or 0),
        "image_path": str(reference.get("image_path") or ""),
        "image_sha256": str(reference.get("image_sha256") or ""),
        "image_model": str(reference.get("image_model") or ""),
        "image_width": int(reference.get("image_width") or 0),
        "image_height": int(reference.get("image_height") or 0),
        "prompt_summary": str(reference.get("prompt_summary") or ""),
    }


def _prompt_reference_payload(reference: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(reference, dict):
        return {"ready": False}
    return {
        "ready": bool(reference.get("ready")),
        "mode": str(reference.get("mode") or ""),
        "reference_page_key": str(reference.get("reference_page_key") or ""),
        "applies_to_page_count": int(reference.get("applies_to_page_count") or 0),
        "image_sha256": str(reference.get("image_sha256") or ""),
        "image_width": int(reference.get("image_width") or 0),
        "image_height": int(reference.get("image_height") or 0),
        "prompt_summary": str(reference.get("prompt_summary") or ""),
    }


def _visual_reference_style_contract(reference: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(reference, dict):
        return {"ready": False, "dominant_colors": []}
    contract: dict[str, Any] = {
        "ready": bool(reference.get("ready")),
        "image_width": int(reference.get("image_width") or 0),
        "image_height": int(reference.get("image_height") or 0),
        "prompt_summary": str(reference.get("prompt_summary") or ""),
        "dominant_colors": [],
    }
    image_path = Path(str(reference.get("image_path") or ""))
    if not image_path.is_file():
        return contract
    try:
        from PIL import Image

        with Image.open(image_path) as image:
            rgb = image.convert("RGB")
            contract["image_width"] = int(rgb.width)
            contract["image_height"] = int(rgb.height)
            rgb.thumbnail((96, 96))
            quantized = rgb.quantize(colors=8)
            palette = quantized.getpalette() or []
            ranked = sorted(quantized.getcolors() or [], reverse=True)
            colors: list[str] = []
            for _count, color_index in ranked:
                offset = int(color_index) * 3
                if offset + 2 >= len(palette):
                    continue
                color = f"#{palette[offset]:02x}{palette[offset + 1]:02x}{palette[offset + 2]:02x}"
                if color not in colors:
                    colors.append(color)
                if len(colors) >= 6:
                    break
            contract["dominant_colors"] = colors
    except Exception as exc:
        trace_event(
            "ai_frontend_reference_contract_fallback",
            error=sanitize_error_message(exc, limit=240),
        )
    return contract


def _prompt_summary(prompt_data: dict[str, Any]) -> str:
    text = " ".join(
        str(item or "").strip()
        for item in [
            prompt_data.get("layout_brief"),
            "、".join(str(token) for token in prompt_data.get("visual_tokens", []) if str(token).strip()),
        ]
        if str(item or "").strip()
    )
    return text[:220]


def _image_data_url(path: Path) -> str:
    raw = path.read_bytes()
    mime = "image/jpeg" if path.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
    optimized = _optimized_reference_image_bytes(raw)
    if optimized:
        optimized_raw, optimized_mime = optimized
        trace_event(
            "ai_frontend_reference_image_optimized",
            original_bytes=len(raw),
            optimized_bytes=len(optimized_raw),
            mime=optimized_mime,
        )
        raw = optimized_raw
        mime = optimized_mime
    return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"


def _optimized_reference_image_bytes(raw: bytes) -> tuple[bytes, str] | None:
    if len(raw) <= 260_000:
        return None
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        with Image.open(io.BytesIO(raw)) as image:
            rgb = image.convert("RGB")
            rgb.thumbnail((960, 960))
            buffer = io.BytesIO()
            rgb.save(buffer, format="JPEG", quality=82, optimize=True)
            optimized = buffer.getvalue()
    except Exception:
        return None
    if len(optimized) >= len(raw):
        return None
    return optimized, "image/jpeg"


def _ai_frontend_timeout_seconds(provider: LLMProvider) -> int:
    raw = (
        os.getenv("SOFT_LLM_AI_FRONTEND_TIMEOUT_SECONDS", "").strip()
        or os.getenv("SOFT_LLM_CODEGEN_TIMEOUT_SECONDS", "").strip()
    )
    configured = int(getattr(getattr(provider, "config", None), "timeout", 90) or 90)
    default = min(120, configured)
    if raw:
        try:
            default = int(raw)
        except ValueError:
            pass
    return max(60, min(240, default))


def _image_dimensions(path: Path) -> tuple[int, int]:
    try:
        from PIL import Image

        with Image.open(path) as image:
            return int(image.width), int(image.height)
    except Exception:
        return 0, 0


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_key(value: str) -> str:
    key = re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(value or "page")).strip("._-")
    return key or "page"


def _codegen_context(task: GenerationTask, blueprint: ProductBlueprint, ui_blueprint: UiBlueprint) -> dict[str, Any]:
    workflows: list[str] = []
    for item in blueprint.workflows[:5]:
        if isinstance(item, dict):
            steps = " -> ".join(str(step) for step in item.get("steps", [])[:6])
            workflows.append(f"{item.get('name', '业务流程')}：{steps}")
    return {
        "software_name": task.software_name,
        "version": task.version,
        "software_category": getattr(task, "software_category", ""),
        "product_type": task.product_type,
        "feature_hint": task.feature_hint,
        "industry": blueprint.industry,
        "scenario": blueprint.scenario,
        "positioning": blueprint.positioning,
        "summary": blueprint.summary,
        "target_users": blueprint.target_users or blueprint.roles,
        "business_objects": blueprint.business_objects[:12],
        "report_metrics": blueprint.report_metrics[:12],
        "quality_rules": blueprint.quality_rules[:8],
        "workflows": workflows,
        "renderer": ui_blueprint.renderer,
        "visual_style": ui_blueprint.visual_style,
        "screens": [
            {
                "key": screen.key,
                "title": screen.title,
                "view_type": screen.view_type,
                "module_key": screen.module_key,
                "components": screen.components[:6],
            }
            for screen in getattr(ui_blueprint, "screens", [])[:16]
        ],
        "modules": [_module_payload(module) for module in blueprint.modules[:8]],
    }


def _module_payload(module: FeatureModule | None) -> dict[str, Any]:
    if module is None:
        return {}
    return {
        "key": module.key,
        "title": module.title,
        "description": module.description,
        "operations": module.operations[:8],
        "operation_specs": list(getattr(module, "operation_specs", []) or [])[:7],
        "data_fields": module.data_fields[:10],
        "pages": module.pages[:6],
        "rules": module.rules[:6],
        "entities": list(getattr(module, "entities", []) or [])[:5],
    }


def _prepare_runtime_html(html: str, *, title: str, renderer: str, page_kind: str, module_key: str) -> str:
    result = html.strip()
    if not result.lower().startswith("<!doctype"):
        result = "<!doctype html>\n" + result
    if "<meta charset" not in result.lower():
        result = re.sub(r"(<head[^>]*>)", r'\1\n<meta charset="utf-8" />', result, count=1, flags=re.I)
    if "<title" not in result.lower():
        title_html = f"<title>{escape(title)}</title>\n</head>"
        result = re.sub(r"</head>", lambda _match: title_html, result, count=1, flags=re.I)
    attrs = (
        f'data-page-kind="{escape(page_kind)}" '
        f'data-module-key="{escape(module_key)}" '
        f'data-renderer="{escape(renderer)}" '
        'data-ai-frontend="true"'
    )
    result = re.sub(r"<body\b([^>]*)>", lambda m: _body_tag_with_attrs(m.group(1), attrs), result, count=1, flags=re.I)
    guard = _runtime_guard_style(renderer)
    if "</head>" in result.lower():
        result = re.sub(r"</head>", lambda _match: guard + "\n</head>", result, count=1, flags=re.I)
    else:
        result = result.replace("<body", f"<head>{guard}</head><body", 1)
    return result


def _body_tag_with_attrs(existing: str, attrs: str) -> str:
    text = str(existing or "")
    for name in ["data-page-kind", "data-module-key", "data-renderer"]:
        text = re.sub(rf"\s{name}=(\"[^\"]*\"|'[^']*')", "", text, flags=re.I)
    return f"<body{text} {attrs}>"


def _runtime_guard_style(renderer: str) -> str:
    if renderer in {"mobile_app", "game"}:
        size = "body{width:720px!important;height:1280px!important;min-height:1280px!important;overflow:hidden!important;}"
        admin_rules = ""
    else:
        size = "body{width:1280px!important;height:720px!important;min-height:720px!important;overflow:hidden!important;background:#fff8f3;}"
        admin_rules = """
body[data-ai-frontend="true"][data-renderer="admin"] .app{width:1280px!important;height:720px!important;max-width:1280px!important;max-height:720px!important;overflow:hidden!important;}
body[data-ai-frontend="true"][data-renderer="admin"] :is(.main,.content,.workspace,.grid,.bottom,.middle){min-width:0!important;min-height:0!important;}
body[data-ai-frontend="true"][data-renderer="admin"] table{width:100%!important;table-layout:fixed!important;border-collapse:collapse;}
body[data-ai-frontend="true"][data-renderer="admin"] :is(th,td){min-width:0!important;max-width:100%!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important;line-height:1.18!important;vertical-align:middle!important;}
body[data-ai-frontend="true"][data-renderer="admin"] :is(button,.btn,.mini-btn,.tab,.nav-item,.select,.input,.mini-input,.tag,.badge,.status span,.field label,.op a){min-width:0!important;max-width:100%!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important;line-height:1.18!important;word-break:keep-all!important;}
body[data-ai-frontend="true"][data-renderer="admin"] :is(button,.btn,.mini-btn){display:inline-flex!important;align-items:center!important;justify-content:center!important;font-size:12px!important;padding-left:8px!important;padding-right:8px!important;}
body[data-ai-frontend="true"][data-renderer="admin"] :is(.opbtn,button.opbtn){height:20px!important;min-height:20px!important;max-height:20px!important;font-size:11px!important;line-height:1!important;padding-top:0!important;padding-bottom:0!important;}
body[data-ai-frontend="true"][data-renderer="admin"] :is(.tag,.badge){display:inline-flex!important;align-items:center!important;justify-content:center!important;padding-left:6px!important;padding-right:6px!important;}
body[data-ai-frontend="true"][data-renderer="admin"] :is(.code,.num,.val,.metric .num,.mcell .val,.record-title .code){display:block!important;min-width:0!important;max-width:100%!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important;line-height:1.12!important;}
body[data-ai-frontend="true"][data-renderer="admin"] :is(.code,.record-title .code,.metric .num,.mcell .val,.val){font-size:20px!important;}
body[data-ai-frontend="true"][data-renderer="admin"] :is(.runtime-record-panel b,.meta b,.rec .r-line b,.source-list b){min-width:0!important;max-width:100%!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important;}
body[data-ai-frontend="true"][data-renderer="admin"] :is(.operation-result){max-width:100%!important;overflow:hidden!important;text-overflow:ellipsis!important;line-height:1.28!important;}
""".strip()
    return f"""
<style id="soft-ai-runtime-guard">
html,body{{margin:0!important;box-sizing:border-box;}}
*,*::before,*::after{{box-sizing:inherit;}}
{size}
body[data-ai-frontend="true"]{{font-family:"Microsoft YaHei","PingFang SC",Arial,sans-serif;-webkit-font-smoothing:antialiased;text-rendering:geometricPrecision;}}
{admin_rules}
body[data-renderer="mobile_app"][data-page-kind="operation"] #root,
body[data-renderer="mobile_app"][data-page-kind="operation"] .screen-root,
body[data-renderer="mobile_app"][data-page-kind="operation"] :is(.phone-shell,.mobile-shell,.app-shell){{width:720px!important;min-width:720px!important;max-width:720px!important;margin-left:0!important;margin-right:0!important;}}
body[data-renderer="mobile_app"][data-page-kind="operation"] :is(.confirm-drawer,.detail-drawer,.confirm-panel,[class*="modal"],[class*="dialog"],[role="dialog"]){{position:fixed!important;left:50%!important;right:auto!important;top:50%!important;bottom:auto!important;transform:translate(-50%,-50%)!important;width:calc(100vw - 32px)!important;max-width:688px!important;max-height:calc(100vh - 48px)!important;margin:0!important;overflow:auto!important;z-index:10000!important;border-radius:12px!important;}}
body[data-renderer="admin"][data-page-kind="operation"] :is(.confirm-drawer,.detail-drawer,.confirm-panel,[class*="modal"],[class*="dialog"],[role="dialog"]){{position:fixed!important;left:50%!important;right:auto!important;top:50%!important;bottom:auto!important;transform:translate(-50%,-50%)!important;width:min(720px,calc(100vw - 48px))!important;max-height:calc(100vh - 48px)!important;margin:0!important;overflow:auto!important;z-index:10000!important;border-radius:12px!important;}}
.runtime-generated-record{{position:fixed;left:24px;right:24px;bottom:18px;z-index:9999;display:grid;grid-template-columns:1fr 1.2fr 1fr .7fr;gap:10px;padding:10px 12px;border-radius:8px;background:rgba(255,255,255,.94);border:1px solid rgba(148,163,184,.45);box-shadow:0 12px 28px rgba(15,23,42,.16);font-family:"Microsoft YaHei","PingFang SC",sans-serif;color:#1f2937;}}
.runtime-generated-record span{{display:block;color:#64748b;font-size:11px;margin-bottom:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
.runtime-generated-record b{{display:block;font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
</style>
""".strip()


def _reject_internal_visible_terms(html: str) -> None:
    visible = re.sub(r"<style\b.*?</style>", " ", html, flags=re.S | re.I)
    visible = re.sub(r"<script\b.*?</script>", " ", visible, flags=re.S | re.I)
    visible = re.sub(r"<[^>]+>", " ", visible)
    patterns = [
        "GPT",
        "提示词",
        "image2",
        "视觉参考",
        "参考稿",
        "接口返回",
        "运行服务",
        "生成项目",
        "浏览器页面",
        "source-ui-evidence",
        "generated_source",
        "ui-prototype",
    ]
    hits = [item for item in patterns if re.search(re.escape(item), visible, flags=re.I)]
    if re.search(r"AI\s*(生成|提示词|模型说明|接口|代码)", visible, flags=re.I):
        hits.append("AI生成说明")
    if hits:
        raise ValueError("模型页面包含客户不可见内部说明：" + "、".join(sorted(set(hits))))


def _reject_direct_image_embedding(html: str) -> None:
    patterns = [
        ("图片标签", r"<img\b"),
        ("内联图片", r"data:image/"),
        ("图片背景", r"background(?:-image)?\s*:[^;{}]*url\s*\("),
        ("外部资源", r"\burl\s*\("),
    ]
    hits = [label for label, pattern in patterns if re.search(pattern, html, flags=re.I)]
    if hits:
        raise ValueError("模型页面疑似直接嵌入参考图或外部资源：" + "、".join(sorted(set(hits))))


def _parse_json(content: str) -> dict[str, Any]:
    cleaned = str(content or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.I).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        cleaned = cleaned[start : end + 1]
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError("AI 前端代码返回值不是 JSON 对象")
    return data


def _emit(emit, progress: int, message: str, **extra) -> None:
    if emit:
        emit(progress, message, **extra)
