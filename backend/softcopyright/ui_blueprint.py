from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
import json
import os
import re
import time
from typing import Any

from .blueprint import ProductBlueprint
from .industry_subtypes import build_ui_design_brief
from .llm.provider import LLMProvider, LocalTemplateProvider
from .llm.trace import trace_event
from .models import GenerationTask


@dataclass
class UiScreenBlueprint:
    key: str
    title: str
    caption: str
    view_type: str
    module_key: str = ""
    components: list[str] = field(default_factory=list)
    sample_data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "title": self.title,
            "caption": self.caption,
            "view_type": self.view_type,
            "module_key": self.module_key,
            "components": self.components,
            "sample_data": self.sample_data,
        }


@dataclass
class UiBlueprint:
    renderer: str
    visual_style: str
    screens: list[UiScreenBlueprint]
    source: str = "local-template"
    warnings: list[str] = field(default_factory=list)
    design_brief: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "renderer": self.renderer,
            "visual_style": self.visual_style,
            "source": self.source,
            "warnings": self.warnings,
            "design_brief": self.design_brief,
            "screens": [screen.to_dict() for screen in self.screens],
        }


def build_ui_blueprint(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    provider: LLMProvider | None = None,
    emit=None,
) -> UiBlueprint:
    fallback = _typed_ui_blueprint(task, blueprint)
    if provider is None or isinstance(provider, LocalTemplateProvider):
        return fallback

    try:
        llm_blueprint = _generate_ui_blueprint_with_llm(task, blueprint, provider, fallback, emit=emit)
    except Exception as exc:
        fallback.warnings.append(f"模型界面蓝图生成失败，已回退本地规则：{exc}")
        return fallback
    return llm_blueprint


def _typed_ui_blueprint(task: GenerationTask, blueprint: ProductBlueprint) -> UiBlueprint:
    if is_game_like(task, blueprint):
        return _game_ui_blueprint(task, blueprint)
    return _admin_ui_blueprint(task, blueprint)


def _generate_ui_blueprint_with_llm(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    provider: LLMProvider,
    fallback: UiBlueprint,
    emit=None,
) -> UiBlueprint:
    expected_renderer = "game" if is_game_like(task, blueprint) else "admin"
    warnings: list[str] = []
    try:
        _emit(emit, 41, "生成界面风格")
        style_data = _chat_json(
            provider,
            [
                {"role": "system", "content": _ui_system_prompt()},
                {"role": "user", "content": _build_ui_style_prompt(task, blueprint, expected_renderer)},
            ],
            max_tokens=700,
            label="界面风格蓝图",
        )
        visual_style = str(style_data.get("visual_style") or fallback.visual_style)
    except Exception as exc:
        visual_style = fallback.visual_style
        warnings.append(f"模型界面风格生成失败，已沿用本地风格：{exc}")

    screens: list[dict[str, Any]] = []
    batches = _screen_batches(fallback.screens, 3)
    screen_results: dict[int, list[dict[str, Any]]] = {}

    def run_batch(index: int, batch: list[UiScreenBlueprint]) -> list[dict[str, Any]]:
        _emit(emit, 41 + index, f"生成截图蓝图 {index}/{len(batches)}")
        data = _chat_json(
            provider,
            [
                {"role": "system", "content": _ui_system_prompt()},
                {"role": "user", "content": _build_ui_screen_batch_prompt(task, blueprint, expected_renderer, batch)},
            ],
            max_tokens=1200,
            label=f"界面截图蓝图批次{index}",
        )
        batch_screens = data.get("screens")
        if not isinstance(batch_screens, list):
            raise ValueError("模型界面批次缺少 screens 数组")
        return [item for item in batch_screens if isinstance(item, dict)]

    workers = _llm_batch_workers()
    if workers <= 1 or len(batches) <= 1:
        for index, batch in enumerate(batches, start=1):
            try:
                screen_results[index] = run_batch(index, batch)
            except Exception as exc:
                warnings.append(f"模型界面截图批次 {index} 生成失败，已沿用本地截图定义：{exc}")
    else:
        with ThreadPoolExecutor(max_workers=min(workers, len(batches))) as executor:
            futures = {
                executor.submit(run_batch, index, batch): index
                for index, batch in enumerate(batches, start=1)
            }
            for future in as_completed(futures):
                index = futures[future]
                try:
                    screen_results[index] = future.result()
                except Exception as exc:
                    warnings.append(f"模型界面截图批次 {index} 生成失败，已沿用本地截图定义：{exc}")

    for index in sorted(screen_results):
        screens.extend(screen_results[index])

    if not screens:
        raise RuntimeError("模型界面蓝图所有批次均失败")

    data = {
        "renderer": expected_renderer,
        "visual_style": visual_style,
        "screens": screens,
    }
    candidate = _ui_blueprint_from_data(data, fallback, expected_renderer)
    candidate.source = "llm"
    candidate.warnings.extend(warnings)
    return candidate


def _emit(emit, progress: int, message: str, **extra) -> None:
    if emit:
        emit(progress, message, **extra)


def _llm_batch_workers() -> int:
    try:
        value = int(os.getenv("SOFT_LLM_BATCH_WORKERS", "1"))
    except ValueError:
        value = 1
    return max(1, min(3, value))


def _ui_system_prompt() -> str:
    return (
        "你是中文软件产品经理和 UI 信息架构专家。"
        "请为软件著作权说明书截图生成结构化界面蓝图，只返回 JSON，不要返回 Markdown。"
        "界面必须和软件类型、软件名称、功能模块严格匹配。"
    )


def _build_ui_style_prompt(task: GenerationTask, blueprint: ProductBlueprint, expected_renderer: str) -> str:
    renderer_note = (
        "手机游戏 9:16 竖屏界面，强调玩家、关卡、棋盘、道具、结算等游戏元素。"
        if expected_renderer == "game"
        else "桌面业务系统界面，强调业务看板、表格列表、筛选、流程状态和统计报表。"
    )
    return f"""
请为软著截图生成整体界面风格。只返回 JSON。

软件名称：{task.software_name}
软件类型：{task.product_type}
本次行业子类型：{getattr(blueprint, "industry_subtype", "") or "未提供"}
业务补充：{task.feature_hint or "无"}
行业领域：{blueprint.industry}
具体场景：{blueprint.scenario or "未提供"}
产品定位：{blueprint.positioning or "未提供"}
模块标题：{"、".join(module.title for module in blueprint.modules[:8])}
本次界面设计 brief：
{json.dumps(build_ui_design_brief(task, blueprint), ensure_ascii=False, indent=2)}

强制要求：
- renderer 必须为 "{expected_renderer}"
- 风格应符合：{renderer_note}
- visual_style 用中文短语，体现软件业务领域，不要写通用风格

返回 JSON：
{{"renderer":"{expected_renderer}","visual_style":"中文短语"}}
""".strip()


def _build_ui_screen_batch_prompt(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    expected_renderer: str,
    screens: list[UiScreenBlueprint],
) -> str:
    if expected_renderer == "game":
        renderer_note = "本批截图必须保持手机游戏场景，不能出现后台管理表格。"
    else:
        renderer_note = "本批截图必须保持桌面业务系统场景，不能出现游戏棋盘、道具背包或关卡画面。"
    return f"""
请为本批软著说明书截图补齐内容。只返回 JSON。

软件上下文：
{_compact_ui_context(task, blueprint)}

本次界面设计 brief：
{json.dumps(build_ui_design_brief(task, blueprint), ensure_ascii=False, indent=2)}

本批截图固定结构：
{json.dumps(_screen_batch_payload(screens, blueprint), ensure_ascii=False, indent=2)}

强制要求：
- renderer 必须为 "{expected_renderer}"
- {renderer_note}
- 每个 screen 的 key、view_type、module_key 必须原样返回，不能新增或改名
- title/caption/components/sample_data 必须来自软件场景、业务对象、模块操作、字段、规则或统计指标
- caption 要像说明书图注，说明这张截图展示了什么业务功能
- components 返回 4-7 个具体界面组件或业务区域
- sample_data 返回 3-6 个字段和值，字段必须有业务含义
- 禁止只写“通用系统、数据维护、管理列表、统计分析”

返回 JSON：
{{"renderer":"{expected_renderer}","screens":[{{"key":"...","title":"...","caption":"...","view_type":"...","module_key":"...","components":["..."],"sample_data":{{"字段":"值"}}}}]}}
""".strip()


def _compact_ui_context(task: GenerationTask, blueprint: ProductBlueprint) -> str:
    workflows: list[str] = []
    for item in blueprint.workflows[:4]:
        if isinstance(item, dict):
            steps = " -> ".join(str(step) for step in item.get("steps", [])[:5])
            workflows.append(f"{item.get('name', '业务流程')}：{steps}")
    context = {
        "software_name": task.software_name,
        "product_type": task.product_type,
        "feature_hint": task.feature_hint,
        "scenario": blueprint.scenario,
        "positioning": blueprint.positioning,
        "target_users": blueprint.target_users or blueprint.roles,
        "business_objects": blueprint.business_objects[:10],
        "report_metrics": blueprint.report_metrics[:10],
        "quality_rules": blueprint.quality_rules[:6],
        "workflows": workflows,
        "modules": [
            {
                "key": module.key,
                "title": module.title,
                "operations": module.operations[:5],
                "fields": module.data_fields[:6],
            }
            for module in blueprint.modules[:8]
        ],
    }
    return json.dumps(context, ensure_ascii=False, indent=2)[:4200]


def _screen_batch_payload(screens: list[UiScreenBlueprint], blueprint: ProductBlueprint) -> list[dict[str, Any]]:
    modules = {module.key: module for module in blueprint.modules}
    payload: list[dict[str, Any]] = []
    for screen in screens:
        item: dict[str, Any] = {
            "key": screen.key,
            "view_type": screen.view_type,
            "module_key": screen.module_key,
            "fallback_title": screen.title,
            "fallback_caption": screen.caption,
        }
        module = modules.get(screen.module_key)
        if module:
            item["module"] = {
                "title": module.title,
                "description": module.description,
                "operations": module.operations[:7],
                "data_fields": module.data_fields[:10],
                "pages": module.pages[:4],
                "rules": module.rules[:5],
            }
        payload.append(item)
    return payload


def _screen_batches(screens: list[UiScreenBlueprint], batch_size: int) -> list[list[UiScreenBlueprint]]:
    return [screens[index : index + batch_size] for index in range(0, len(screens), batch_size)]


def _chat_json(
    provider: LLMProvider,
    messages: list[dict[str, str]],
    *,
    max_tokens: int,
    label: str,
    attempts: int = 3,
) -> dict[str, Any]:
    last_error: Exception | None = None
    current_messages = messages
    provider_retries = int(getattr(getattr(provider, "config", None), "retry_count", 0) or 0)
    total_attempts = 1 if provider_retries > 0 else max(1, attempts)
    for attempt in range(total_attempts):
        started_at = time.perf_counter()
        trace_event(
            "chat_json_begin",
            layer="ui_blueprint",
            label=label,
            attempt=attempt + 1,
            total_attempts=total_attempts,
            max_tokens=max_tokens,
            temperature=0.35,
            message_count=len(current_messages),
        )
        try:
            content = provider.chat(
                current_messages,
                temperature=0.35,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
                trace_label=f"ui_blueprint:{label}",
            )
            data = _parse_json(content)
            trace_event(
                "chat_json_success",
                layer="ui_blueprint",
                label=label,
                attempt=attempt + 1,
                elapsed_seconds=round(time.perf_counter() - started_at, 3),
                content_chars=len(content or ""),
            )
            return data
        except Exception as exc:
            last_error = exc
            trace_event(
                "chat_json_error",
                layer="ui_blueprint",
                label=label,
                attempt=attempt + 1,
                elapsed_seconds=round(time.perf_counter() - started_at, 3),
                error_type=type(exc).__name__,
                error=str(exc)[:500],
            )
            if attempt < total_attempts - 1:
                current_messages = messages + [
                    {
                        "role": "user",
                        "content": (
                            f"上一次{label}没有得到可解析 JSON，错误摘要：{str(exc)[:120]}。"
                            "请重新输出严格 JSON 对象，不要 Markdown，不要解释文字。"
                        ),
                    }
                ]
    raise RuntimeError(f"{label}请求失败：{last_error}")


def _build_ui_prompt(task: GenerationTask, blueprint: ProductBlueprint, expected_renderer: str) -> str:
    modules = "\n".join(
        f"- key={module.key}, title={module.title}, description={module.description}, "
        f"operations={', '.join(module.operations[:6])}, fields={', '.join(module.data_fields[:8])}, pages={', '.join(module.pages[:4])}"
        for module in blueprint.modules
    )
    workflows = "\n".join(
        f"- {item.get('name', '业务流程')}：{' -> '.join(str(step) for step in item.get('steps', []))}；输出：{item.get('output', '')}"
        for item in blueprint.workflows[:5]
        if isinstance(item, dict)
    )
    if expected_renderer == "game":
        view_types = "game_login, game_home, game_level, game_board, game_inventory, game_statistics, game_profile, game_shop"
        renderer_note = (
            "本软件是游戏类，renderer 必须是 game。"
            "截图必须按手机游戏 9:16 竖屏画幅组织，呈现玩家登录、游戏主界面、关卡/棋盘/道具/结算/玩家资料等游戏场景，不能输出后台管理表格风格。"
        )
    else:
        view_types = "admin_login, admin_dashboard, admin_module, admin_statistics"
        renderer_note = (
            "本软件不是游戏类，renderer 必须是 admin。"
            "截图应呈现业务系统、运营后台、数据管理、统计报表等软件界面，不能输出游戏棋盘、关卡、道具背包等游戏场景。"
        )
    return f"""
请为以下软件生成软著说明书界面截图蓝图：

软件名称：{task.software_name}
版本：{task.version}
软件类型：{task.product_type}
编程语言：{task.language}
业务补充：{task.feature_hint or "无"}
行业领域：{blueprint.industry}
具体场景：{blueprint.scenario or "未提供"}
产品定位：{blueprint.positioning or "未提供"}
软件概述：{blueprint.summary}
目标用户：{"、".join(blueprint.target_users or blueprint.roles)}
核心业务对象：{"、".join(blueprint.business_objects[:12])}
统计指标：{"、".join(blueprint.report_metrics[:12])}
质量规则：{"；".join(blueprint.quality_rules[:8])}

功能模块：
{modules}

业务流程：
{workflows or "无"}

强制要求：
- {renderer_note}
- renderer 只能为 "{expected_renderer}"
- view_type 只能从以下值选择：{view_types}
- 必须包含 login、dashboard、statistics，以及每个功能模块 key 对应的截图
- 每张截图 title/caption/components/sample_data 必须来自具体场景、业务对象、统计指标、模块操作或字段，不允许只写“通用系统”“管理列表”“数据维护”
- dashboard 截图必须体现 report_metrics 中的指标
- module 截图必须体现对应模块的 operations、data_fields、rules
- statistics 截图必须体现 workflows 和 report_metrics

返回 JSON：
{{
  "renderer": "{expected_renderer}",
  "visual_style": "中文短语",
  "screens": [
    {{
      "key": "login",
      "title": "截图标题",
      "caption": "图注",
      "view_type": "{'game_login' if expected_renderer == 'game' else 'admin_login'}",
      "module_key": "",
      "components": ["组件1", "组件2"],
      "sample_data": {{"字段": "样例值"}}
    }}
  ]
}}
只返回 JSON。
""".strip()


def _parse_json(content: str) -> dict[str, Any]:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        cleaned = cleaned[start : end + 1]
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError("界面蓝图不是 JSON 对象")
    return data


def _ui_blueprint_from_data(data: dict[str, Any], fallback: UiBlueprint, expected_renderer: str) -> UiBlueprint:
    renderer = str(data.get("renderer") or "").strip().lower()
    if renderer != expected_renderer:
        raise ValueError(f"模型界面蓝图 renderer={renderer or '空'}，预期 {expected_renderer}")

    screens_data = data.get("screens")
    if not isinstance(screens_data, list):
        raise ValueError("模型界面蓝图缺少 screens 数组")

    model_screens: dict[str, dict[str, Any]] = {}
    for item in screens_data:
        if not isinstance(item, dict):
            continue
        key = _safe_screen_key(str(item.get("key") or ""))
        if key:
            model_screens[key] = item

    screens: list[UiScreenBlueprint] = []
    for fallback_screen in fallback.screens:
        item = model_screens.get(fallback_screen.key)
        if not item and fallback_screen.module_key:
            item = model_screens.get(fallback_screen.module_key)
        if not item:
            screens.append(fallback_screen)
            continue
        view_type = _normalize_view_type(
            expected_renderer,
            fallback_screen.key,
            str(item.get("view_type") or ""),
            fallback_screen.view_type,
        )
        title = _clean_text(str(item.get("title") or fallback_screen.title), fallback_screen.title, 32)
        caption = _clean_text(str(item.get("caption") or fallback_screen.caption), fallback_screen.caption, 120)
        components = _clean_list(item.get("components"), fallback_screen.components)
        sample_data = item.get("sample_data") if isinstance(item.get("sample_data"), dict) else fallback_screen.sample_data
        if expected_renderer == "game":
            view_type = _coerce_game_view_type(fallback_screen, view_type, title, caption, components, sample_data)
        screens.append(
            UiScreenBlueprint(
                key=fallback_screen.key,
                title=title,
                caption=caption,
                view_type=view_type,
                module_key=fallback_screen.module_key,
                components=components,
                sample_data=sample_data,
            )
        )

    visual_style = _clean_text(str(data.get("visual_style") or fallback.visual_style), fallback.visual_style, 40)
    return UiBlueprint(
        renderer=expected_renderer,
        visual_style=visual_style,
        screens=screens,
        design_brief=dict(getattr(fallback, "design_brief", {}) or {}),
    )


def _safe_screen_key(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]+", "_", value).strip("_").lower()


def _module_screen_key(module_key: str) -> str:
    key = _safe_screen_key(module_key)
    if key in {"login", "dashboard", "statistics"}:
        return f"module_{key}"
    return key


def _clean_text(value: str, fallback: str, limit: int) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    if not value:
        return fallback
    return value[:limit]


def _clean_list(value: Any, fallback: list[str]) -> list[str]:
    if not isinstance(value, list):
        return fallback
    cleaned = [_clean_text(str(item), "", 24) for item in value[:8]]
    cleaned = [item for item in cleaned if item]
    return cleaned or fallback


def _normalize_view_type(renderer: str, key: str, value: str, fallback: str) -> str:
    value = value.strip()
    if renderer == "game":
        forced = {"login": "game_login", "dashboard": "game_home", "statistics": "game_statistics"}
        allowed = {"game_login", "game_home", "game_level", "game_board", "game_inventory", "game_statistics", "game_profile", "game_shop"}
    else:
        forced = {"login": "admin_login", "dashboard": "admin_dashboard", "statistics": "admin_statistics"}
        allowed = {"admin_login", "admin_dashboard", "admin_module", "admin_statistics"}
    if key in forced:
        return forced[key]
    if value in allowed:
        return value
    return fallback if fallback in allowed else next(iter(allowed))


def _coerce_game_view_type(
    fallback_screen: UiScreenBlueprint,
    view_type: str,
    title: str,
    caption: str,
    components: list[str],
    sample_data: dict[str, Any],
) -> str:
    if fallback_screen.key in {"login", "dashboard", "statistics"}:
        return view_type
    text = " ".join(
        [
            fallback_screen.key,
            fallback_screen.module_key,
            fallback_screen.title,
            fallback_screen.caption,
            title,
            caption,
            " ".join(components),
            json.dumps(sample_data, ensure_ascii=False),
        ]
    )
    if _looks_like_game_board_text(text):
        return "game_board"
    return view_type


def is_game_like(task: GenerationTask, blueprint: ProductBlueprint) -> bool:
    if task.product_type == "游戏软件":
        return True
    text = " ".join([task.software_name, task.product_type, task.feature_hint])
    keywords = ["游戏", "消除", "点消", "关卡", "棋盘", "步数", "道具", "玩家", "星级", "得分", "连消"]
    return any(keyword in text for keyword in keywords)


def ui_matches_software_type(task: GenerationTask, blueprint: ProductBlueprint, ui_blueprint: UiBlueprint) -> bool:
    if is_game_like(task, blueprint):
        allowed = {"game_login", "game_home", "game_level", "game_board", "game_inventory", "game_statistics", "game_profile", "game_shop"}
        required_any = {"game_level", "game_board", "game_inventory", "game_statistics"}
        view_types = {screen.view_type for screen in ui_blueprint.screens}
        text = " ".join(
            [ui_blueprint.visual_style]
            + [screen.title + screen.caption + " ".join(screen.components) for screen in ui_blueprint.screens]
        )
        domain_keywords = ["游戏", "玩家", "关卡", "棋盘", "步数", "道具", "得分", "星级", "消除"]
        return (
            ui_blueprint.renderer == "game"
            and bool(view_types)
            and view_types.issubset(allowed)
            and bool(view_types & required_any)
            and any(keyword in text for keyword in domain_keywords)
        )

    view_types = {screen.view_type for screen in ui_blueprint.screens}
    return ui_blueprint.renderer == "admin" and not any(view_type.startswith("game_") for view_type in view_types)


def _game_ui_blueprint(task: GenerationTask, blueprint: ProductBlueprint) -> UiBlueprint:
    design_brief = build_ui_design_brief(task, blueprint)
    screens = [
        UiScreenBlueprint(
            key="login",
            title="启动登录界面",
            caption="玩家进入游戏后，可进行账号登录、游客进入和公告查看。",
            view_type="game_login",
            components=["账号登录", "游客进入", "区服选择", "公告入口"],
            sample_data={"server": f"{task.software_name}一区", "entry": "进入游戏"},
        ),
        UiScreenBlueprint(
            key="dashboard",
            title="游戏主界面",
            caption="主界面展示当前体力、金币、关卡进度、活动入口和开始游戏按钮。",
            view_type="game_home",
            components=["关卡地图", "体力金币", "每日任务", "开始游戏"],
            sample_data={"energy": "25/30", "coins": "12,860", "level": "36"},
        ),
    ]
    for module in blueprint.modules[:6]:
        view_type, title, caption, components = _game_module_screen(module)
        screens.append(
            UiScreenBlueprint(
                key=_module_screen_key(module.key),
                title=title,
                caption=caption,
                view_type=view_type,
                module_key=module.key,
                components=components,
                sample_data=_game_sample_data(view_type),
            )
        )
    screens.append(
        UiScreenBlueprint(
            key="statistics",
            title="游戏结算统计界面",
            caption="系统按关卡、星级、步数、得分和道具使用情况展示结算统计。",
            view_type="game_statistics",
            components=["得分统计", "星级评价", "步数奖励", "道具加成"],
            sample_data={"score": "18,640", "stars": "★★★", "combo": "7"},
        )
    )
    visual_style = str(design_brief.get("visual_mood") or "bright-casual-game")
    return UiBlueprint(renderer="game", visual_style=visual_style, screens=screens, design_brief=design_brief)


def _admin_ui_blueprint(task: GenerationTask, blueprint: ProductBlueprint) -> UiBlueprint:
    design_brief = build_ui_design_brief(task, blueprint)
    screens = [
        UiScreenBlueprint(
            key="login",
            title="登录界面",
            caption="用户输入账号、密码和验证码后进入系统。",
            view_type="admin_login",
            components=["账号", "密码", "验证码", "登录按钮"],
        ),
        UiScreenBlueprint(
            key="dashboard",
            title="系统首页",
            caption="首页集中展示核心指标、待办事项、异常提醒和快捷入口。",
            view_type="admin_dashboard",
            components=["指标卡片", "待办事项", "快捷入口"],
        ),
    ]
    for module in blueprint.modules[:6]:
        screens.append(
            UiScreenBlueprint(
                key=_module_screen_key(module.key),
                title=module.title,
                caption=module.description,
                view_type="admin_module",
                module_key=module.key,
                components=["条件筛选", "业务列表", "状态标签", "操作按钮", "模块说明"],
                sample_data={"entities": module.entities},
            )
        )
    screens.append(
        UiScreenBlueprint(
            key="statistics",
            title="统计报表界面",
            caption="系统按日期、模块、状态和角色维度生成统计结果。",
            view_type="admin_statistics",
            components=["指标卡片", "模块统计", "导出报表"],
        )
    )
    visual_style = str(design_brief.get("visual_mood") or "desktop-admin")
    return UiBlueprint(renderer="admin", visual_style=visual_style, screens=screens, design_brief=design_brief)


def _game_module_screen(module) -> tuple[str, str, str, list[str]]:
    text = f"{module.title}{module.description}{' '.join(module.entities)}"
    if module.key == "custom" or _looks_like_game_board_text(text):
        return (
            "game_board",
            module.title or "消除对局界面",
            "展示 8x8 消除棋盘、通关目标、剩余步数、得分、障碍格、道具栏和玩家操作区。",
            ["8x8 消除棋盘", "通关目标", "剩余步数", "障碍格", "道具栏"],
        )
    if any(word in text for word in ["关卡", "任务", "Level", "Quest", "Progress", "Config"]):
        return (
            "game_level",
            "关卡选择界面",
            "展示关卡地图、解锁进度、棋盘尺寸、目标分数、限定步数和障碍规则。",
            ["关卡地图", "解锁进度", "关卡配置", "选择关卡"],
        )
    if any(word in text for word in ["角色", "资产", "道具", "背包", "奖励", "活动", "Reward", "Inventory", "Activity"]):
        return (
            "game_inventory",
            "道具背包界面",
            "展示玩家资产、道具背包、奖励领取、活动道具和资产流水。",
            ["道具卡片", "资产流水", "奖励领取"],
        )
    if any(word in text for word in ["统计", "结算", "对战", "匹配", "排行", "Battle", "Match", "Result"]):
        return (
            "game_statistics",
            "游戏结算统计界面",
            "展示关卡结算、得分、星级、步数奖励、连消奖励和排行榜数据。",
            ["结算指标", "星级评价", "排行榜", "奖励明细"],
        )
    if any(word in text for word in ["充值", "订单", "支付", "商品", "发货", "退款", "Payment", "Goods", "Order"]):
        return (
            "game_shop",
            "游戏商城界面",
            "展示金币礼包、体力补给、道具商品、支付订单和发货状态。",
            ["商品卡片", "支付订单", "发货状态", "退款审核"],
        )
    if any(word in text for word in ["安全", "风控", "外挂", "刷分", "Cheat", "Risk"]):
        return (
            "game_board",
            "对局安全监测",
            "展示消除棋盘、通关目标、剩余步数、得分、道具栏和玩家操作区。",
            ["消除棋盘", "通关目标", "剩余步数", "安全监测"],
        )
    if any(word in text for word in ["玩家", "账号", "Player"]):
        return (
            "game_profile",
            "玩家资料界面",
            "展示玩家等级、星级、通关记录、金币体力和账号状态。",
            ["玩家资料", "等级经验", "通关记录", "账号状态"],
        )
    return (
        "game_board",
        module.title,
        "展示消除棋盘、通关目标、剩余步数、得分、道具栏和玩家操作区。",
        ["消除棋盘", "通关目标", "道具栏", "得分状态"],
    )


def _looks_like_game_board_text(text: str) -> bool:
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
    if any(term in text for term in strong_terms):
        return True
    if "棋盘" in text and any(term in text for term in ["编辑", "绘制", "生成", "掉落", "障碍", "步数", "目标", "糖果"]):
        return True
    return False


def _game_sample_data(view_type: str) -> dict[str, Any]:
    if view_type == "game_level":
        return {"board_size": "8 x 8", "target_score": "12,000", "moves": "24", "obstacles": "冰块 / 木箱"}
    if view_type == "game_inventory":
        return {"items": ["彩虹球", "小木锤", "横向火箭"], "coins": "12,860", "capacity": "42/80"}
    if view_type == "game_statistics":
        return {"score": "18,640", "moves_left": "6", "stars": "★★★", "combo": "7"}
    if view_type == "game_profile":
        return {"player": "玩家A1024", "level": "36", "stars": "86", "status": "正常"}
    if view_type == "game_shop":
        return {"goods": ["金币礼包", "体力补给", "彩虹球礼包"], "order_status": "已发货", "payment": "微信支付"}
    return {"level": "36", "moves_left": "18", "score": "8,420", "targets": ["红色方块", "黄色星星", "冰块障碍"]}
