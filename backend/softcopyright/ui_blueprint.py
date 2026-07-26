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
from .product_experience import (
    ProductExperienceSpec,
    build_product_experience_spec,
    design_brief_experience_fields,
    design_brief_matches_experience,
    expected_renderer_for_experience,
    layout_overrides_for_experience,
)
from .ui_visual_identity import (
    build_visual_identity_spec,
    identity_design_brief_fields,
    visual_identity_matches_task,
)
from .ui_roles import screenshot_role_contract


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
    require_llm: bool = False,
    visual_identity_attempt: int = 0,
) -> UiBlueprint:
    fallback = _typed_ui_blueprint(task, blueprint, visual_identity_attempt=visual_identity_attempt)
    if provider is None or isinstance(provider, LocalTemplateProvider):
        if require_llm:
            raise RuntimeError("当前版本要求由 GPT 生成界面蓝图，请配置 GPT/OpenAI-compatible。")
        return fallback

    try:
        llm_blueprint = _generate_ui_blueprint_with_llm(
            task,
            blueprint,
            provider,
            fallback,
            emit=emit,
            require_llm=require_llm,
            visual_identity_attempt=visual_identity_attempt,
        )
    except Exception as exc:
        if require_llm:
            raise RuntimeError(f"GPT 界面蓝图生成失败：{exc}") from exc
        fallback.warnings.append(f"模型界面蓝图生成失败，已回退本地规则：{exc}")
        return fallback
    return llm_blueprint


def _typed_ui_blueprint(task: GenerationTask, blueprint: ProductBlueprint, visual_identity_attempt: int = 0) -> UiBlueprint:
    renderer = _expected_renderer(task, blueprint)
    if renderer == "game":
        return _game_ui_blueprint(task, blueprint, visual_identity_attempt=visual_identity_attempt)
    if renderer == "mobile_app":
        return _mobile_app_ui_blueprint(task, blueprint, visual_identity_attempt=visual_identity_attempt)
    return _admin_ui_blueprint(task, blueprint, visual_identity_attempt=visual_identity_attempt)


def complete_ui_blueprint_coverage(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    current: UiBlueprint,
) -> UiBlueprint:
    fallback = _typed_ui_blueprint(task, blueprint)
    existing_module_keys = {screen.module_key for screen in current.screens if screen.module_key}
    missing = [
        screen
        for screen in fallback.screens
        if screen.module_key and screen.module_key not in existing_module_keys
    ]
    if not missing:
        return current
    statistics = [screen for screen in current.screens if screen.key == "statistics"]
    base = [screen for screen in current.screens if screen.key != "statistics"]
    return UiBlueprint(
        renderer=current.renderer,
        visual_style=current.visual_style,
        screens=base + missing + statistics,
        source=current.source,
        warnings=list(current.warnings),
        design_brief=dict(current.design_brief or fallback.design_brief),
    )


def repair_ui_blueprint_contract(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    current: UiBlueprint,
) -> UiBlueprint | None:
    """Repair polluted metadata while preserving already-correct business screens."""
    expected_experience = build_product_experience_spec(task, blueprint)
    expected_renderer = _expected_renderer(task, blueprint, expected_experience)
    if current.renderer != expected_renderer or not current.screens:
        return None
    ui_text = " ".join(
        [current.visual_style]
        + [
            " ".join(
                [
                    screen.title,
                    screen.caption,
                    " ".join(screen.components),
                    json.dumps(screen.sample_data, ensure_ascii=False),
                ]
            )
            for screen in current.screens
        ]
    )
    subtype_key = expected_experience.industry_subtype_key
    medical_terms = r"手术|麻醉|患者|病历|处方|住院|病区|床位|生命体征|医嘱"
    rail_terms = r"轨道交通|地铁|铁路|施工质量|检验批|材料复检|工程部位|单位工程|标段"
    game_terms = r"消除棋盘|关卡地图|道具背包|剩余步数|玩家战力"
    if subtype_key not in {"inpatient_monitoring", "surgery_schedule", "clinic_emr", "hospital_inventory"} and re.search(medical_terms, ui_text):
        return None
    if subtype_key != "rail_construction_quality" and re.search(rail_terms, ui_text):
        return None
    if expected_renderer != "game" and re.search(game_terms, ui_text):
        return None
    old_brief = current.design_brief if isinstance(current.design_brief, dict) else {}
    attempt = int(old_brief.get("visual_identity_attempt") or 0)
    fresh_brief = _ui_design_brief_with_contract(task, blueprint, expected_renderer, visual_identity_attempt=attempt)
    reference = old_brief.get("pre_source_visual_reference")
    if isinstance(reference, dict) and reference.get("ready"):
        fresh_brief["pre_source_visual_reference"] = reference
    return UiBlueprint(
        renderer=current.renderer,
        visual_style=current.visual_style,
        screens=list(current.screens),
        source=current.source,
        warnings=list(current.warnings) + ["已修复与当前业务领域不一致的界面蓝图元数据。"],
        design_brief=fresh_brief,
    )


def _generate_ui_blueprint_with_llm(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    provider: LLMProvider,
    fallback: UiBlueprint,
    emit=None,
    require_llm: bool = False,
    visual_identity_attempt: int = 0,
) -> UiBlueprint:
    expected_renderer = _expected_renderer(task, blueprint)
    warnings: list[str] = []
    try:
        _emit(emit, 41, "生成界面风格")
        style_data = _chat_json(
            provider,
            [
                {"role": "system", "content": _ui_system_prompt()},
                {"role": "user", "content": _build_ui_style_prompt(task, blueprint, expected_renderer, visual_identity_attempt)},
            ],
            max_tokens=700,
            label="界面风格蓝图",
        )
        visual_style = str(style_data.get("visual_style") or fallback.visual_style)
    except Exception as exc:
        if require_llm:
            raise RuntimeError(f"界面风格生成失败：{exc}") from exc
        visual_style = fallback.visual_style
        warnings.append(f"模型界面风格生成失败，已沿用本地风格：{exc}")

    screens: list[dict[str, Any]] = []
    batches = _screen_batches(fallback.screens, 1 if _authenticity_first(task) else 3)
    screen_results: dict[int, list[dict[str, Any]]] = {}

    def run_batch(index: int, batch: list[UiScreenBlueprint]) -> list[dict[str, Any]]:
        _emit(emit, 41 + index, f"生成{_screen_batch_title(batch)}设计图 {index}/{len(batches)}")
        data = _chat_json(
            provider,
            [
                {"role": "system", "content": _ui_system_prompt()},
                {"role": "user", "content": _build_ui_screen_batch_prompt(task, blueprint, expected_renderer, batch, visual_identity_attempt)},
            ],
            max_tokens=1200,
            label=f"界面截图蓝图批次{index}",
        )
        batch_screens = data.get("screens")
        if not isinstance(batch_screens, list):
            raise ValueError("模型界面批次缺少 screens 数组")
        screens = [item for item in batch_screens if isinstance(item, dict)]
        if _authenticity_first(task):
            reasons = _screen_batch_quality_reasons(screens, batch)
            if reasons:
                raise ValueError("界面蓝图质量不足：" + "；".join(reasons[:4]))
        return screens

    workers = 1 if _authenticity_first(task) else _llm_batch_workers()
    if workers <= 1 or len(batches) <= 1:
        for index, batch in enumerate(batches, start=1):
            try:
                screen_results[index] = run_batch(index, batch)
            except Exception as exc:
                if require_llm:
                    raise RuntimeError(f"界面截图批次 {index} 生成失败：{exc}") from exc
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
                    if require_llm:
                        raise RuntimeError(f"界面截图批次 {index} 生成失败：{exc}") from exc
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
    candidate = _ui_blueprint_from_data(data, fallback, expected_renderer, require_complete_model=require_llm)
    candidate.source = "llm"
    candidate.warnings.extend(warnings)
    return candidate


def _emit(emit, progress: int, message: str, **extra) -> None:
    if emit:
        emit(progress, message, **extra)


def _llm_batch_workers() -> int:
    try:
        value = int(os.getenv("SOFT_LLM_BATCH_WORKERS", "2"))
    except ValueError:
        value = 2
    return max(1, min(3, value))


def _generation_quality_profile(task: GenerationTask) -> str:
    value = os.getenv("SOFT_GENERATION_PROFILE", "").strip().lower()
    if value in {"fast", "speed", "batch"}:
        return "fast"
    if value in {"authenticity-first", "authenticity", "quality", "strict"}:
        return "authenticity-first"
    return "balanced"


def _authenticity_first(task: GenerationTask) -> bool:
    return _generation_quality_profile(task) == "authenticity-first"


def _screen_batch_title(batch: list[UiScreenBlueprint]) -> str:
    if not batch:
        return "界面"
    screen = batch[0]
    if screen.key == "login":
        return "登录页"
    if screen.key == "dashboard":
        return "系统首页"
    if screen.key == "statistics":
        return "统计页"
    return screen.title or screen.module_key or "模块页"


def _screen_batch_quality_reasons(screens: list[dict[str, Any]], fallback_batch: list[UiScreenBlueprint]) -> list[str]:
    reasons: list[str] = []
    if len(screens) < len(fallback_batch):
        reasons.append(f"截图数量不足，期望 {len(fallback_batch)} 张，实际 {len(screens)} 张")
    by_key = {str(item.get("key") or "").strip(): item for item in screens if isinstance(item, dict)}
    generic_terms = {"通用系统", "管理列表", "数据维护", "统计分析", "系统管理"}
    for fallback in fallback_batch:
        item = by_key.get(fallback.key)
        if not item:
            reasons.append(f"{fallback.key} 未按原 key 返回")
            continue
        title = str(item.get("title") or "").strip()
        caption = str(item.get("caption") or "").strip()
        components = [str(value).strip() for value in item.get("components") or [] if str(value).strip()]
        sample_data = item.get("sample_data") if isinstance(item.get("sample_data"), dict) else {}
        joined = " ".join([title, caption, " ".join(components), json.dumps(sample_data, ensure_ascii=False)])
        if not title or title in generic_terms:
            reasons.append(f"{fallback.key} 标题过于泛化")
        if len(caption) < 28:
            reasons.append(f"{fallback.key} 图注过短")
        if len(components) < 4:
            reasons.append(f"{fallback.key} 组件少于 4 个")
        if len(sample_data) < 3:
            reasons.append(f"{fallback.key} 样例数据少于 3 项")
        if sum(1 for term in generic_terms if term in joined) >= 2:
            reasons.append(f"{fallback.key} 存在泛化界面描述")
    return reasons


def _ui_system_prompt() -> str:
    return (
        "你是中文软件产品经理和 UI 信息架构专家。"
        "请为软件著作权说明书截图生成结构化界面蓝图，只返回 JSON，不要返回 Markdown。"
        "界面必须和软件类型、软件名称、功能模块严格匹配。"
    )


def _build_ui_style_prompt(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    expected_renderer: str,
    visual_identity_attempt: int = 0,
) -> str:
    design_brief = _ui_design_brief_with_contract(task, blueprint, expected_renderer, visual_identity_attempt)
    if expected_renderer == "mobile_app":
        renderer_note = _renderer_note(expected_renderer, design_brief)
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
本次界面设计 brief：{json.dumps(design_brief, ensure_ascii=False, indent=2)}

强制要求：
- renderer 必须为 "{expected_renderer}"
- 风格应符合：{renderer_note}
- 必须严格执行 visual_identity_spec；同产品小类也要根据 identity_signature 改变导航、布局、密度、图表和模块角色
- visual_style 用中文短语，体现软件名称和真实业务领域，不要写通用风格

返回 JSON：
{{"renderer":"{expected_renderer}","visual_style":"中文短语"}}
""".strip()
    renderer_note = (
        _renderer_note("game", design_brief)
        if expected_renderer == "game"
        else _renderer_note("admin", design_brief)
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
{json.dumps(design_brief, ensure_ascii=False, indent=2)}

强制要求：
- renderer 必须为 "{expected_renderer}"
- 风格应符合：{renderer_note}
- 必须严格执行 visual_identity_spec；同产品小类也要根据 identity_signature 改变导航、布局、密度、图表和模块角色
- visual_style 用中文短语，体现软件业务领域，不要写通用风格

返回 JSON：
{{"renderer":"{expected_renderer}","visual_style":"中文短语"}}
""".strip()


def _build_ui_screen_batch_prompt(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    expected_renderer: str,
    screens: list[UiScreenBlueprint],
    visual_identity_attempt: int = 0,
) -> str:
    design_brief = _ui_design_brief_with_contract(task, blueprint, expected_renderer, visual_identity_attempt)
    if expected_renderer == "mobile_app":
        renderer_note = _renderer_note(expected_renderer, design_brief)
        return f"""
请为本批软著说明书截图补齐内容。只返回 JSON。

软件上下文：
{_compact_ui_context(task, blueprint)}

本次界面设计 brief：{json.dumps(design_brief, ensure_ascii=False, indent=2)}

本批截图固定结构：{json.dumps(_screen_batch_payload(screens, blueprint), ensure_ascii=False, indent=2)}

强制要求：
- renderer 必须为 "{expected_renderer}"
- 本批截图必须保持{renderer_note}，不能出现后台侧边栏、审批流、表格台账、复核发布、工单看板或质量复盘。
- 必须执行 visual_identity_spec：导航模型、页面结构、图表风格、表格密度和模块 view_type 不得泛化成同一套模板。
- 截图角色合同只约束用途，不固定文案；title/caption/components/sample_data 必须每次根据当前软件重写，不能照抄合同文本。
- 每个 screen 的 key、view_type、module_key 必须原样返回，不能新增或改名。
- title/caption/components/sample_data 必须来自软件名称、用户任务、内容对象、交互动作和真实 App 页面。
- caption 要像说明书图注，说明这张截图展示了什么用户功能。
- components 返回 4-7 个具体 App 组件或内容区域。
- sample_data 返回 3-6 个字段和值，字段必须有业务含义。
- 禁止只写“通用系统、数据维护、管理列表、统计分析”。

返回 JSON：
{{"renderer":"{expected_renderer}","screens":[{{"key":"...","title":"...","caption":"...","view_type":"...","module_key":"...","components":["..."],"sample_data":{{"字段":"值"}}}}]}}
""".strip()
    if expected_renderer == "game":
        renderer_note = f"本批截图必须保持{_renderer_note('game', design_brief)}，不能出现后台管理表格。"
    else:
        renderer_note = f"本批截图必须保持{_renderer_note('admin', design_brief)}，不能出现游戏棋盘、道具背包或关卡画面。"
    return f"""
请为本批软著说明书截图补齐内容。只返回 JSON。

软件上下文：
{_compact_ui_context(task, blueprint)}

本次界面设计 brief：
{json.dumps(design_brief, ensure_ascii=False, indent=2)}

本批截图固定结构：
{json.dumps(_screen_batch_payload(screens, blueprint), ensure_ascii=False, indent=2)}

强制要求：
- renderer 必须为 "{expected_renderer}"
- {renderer_note}
- 必须执行 visual_identity_spec：导航模型、页面结构、图表风格、表格密度和模块 view_type 不得泛化成同一套模板。
- 截图角色合同只约束用途，不固定文案；title/caption/components/sample_data 必须每次根据当前软件重写，不能照抄合同文本。
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
        "software_category": getattr(task, "software_category", "应用软件"),
        "product_type": task.product_type,
        "product_experience_spec": build_product_experience_spec(task, blueprint).to_dict(),
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


def _ui_design_brief_with_contract(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    expected_renderer: str,
    visual_identity_attempt: int = 0,
) -> dict[str, Any]:
    design_brief = dict(build_ui_design_brief(task, blueprint))
    _sanitize_design_brief_for_task(task, blueprint, design_brief)
    experience_spec = build_product_experience_spec(task, blueprint)
    design_brief.update(design_brief_experience_fields(experience_spec))
    # 顶层行业标识与产品体验规格必须来自同一次推断，避免出现
    # “surgery_schedule key + 交通标题 + 制造业页面”这类合并污染。
    design_brief["industry_subtype_key"] = experience_spec.industry_subtype_key
    design_brief["industry_subtype"] = experience_spec.industry_subtype
    design_brief.update(layout_overrides_for_experience(experience_spec))
    visual_identity = build_visual_identity_spec(task, blueprint, experience_spec, attempt=visual_identity_attempt)
    identity_fields = identity_design_brief_fields(visual_identity)
    identity_spec = identity_fields.get("visual_identity_spec")
    if isinstance(identity_spec, dict):
        identity_spec["attempt"] = int(visual_identity_attempt)
        identity_spec["creative_seed"] = str(getattr(task, "seed", "") or "")
    design_brief.update(identity_fields)
    design_brief["creative_seed"] = str(getattr(task, "seed", "") or "")
    design_brief["frontend_framework"] = "react-vite"
    design_brief["visual_identity_attempt"] = int(visual_identity_attempt)
    design_brief["expected_renderer"] = expected_renderer
    design_brief["screenshot_role_contract"] = screenshot_role_contract(task, blueprint, expected_renderer)
    return design_brief


def _sanitize_design_brief_for_task(task: GenerationTask, blueprint: ProductBlueprint, design_brief: dict[str, Any]) -> None:
    primary_text = " ".join(
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
    if not _has_transport_domain_signal(primary_text):
        return
    banned = ("医疗", "医院", "手术", "手术室", "术前", "术后", "术式", "麻醉", "科室", "医生", "护士", "患者", "病历", "处方", "诊疗", "排班", "排程")
    replacement = {
        "industry_subtype_key": "transport_route",
        "industry_subtype": "交通干支线路径适配系统",
        "real_scenario": "干线支线维护、路径适配、站点接驳、班次衔接、换乘规则和线路运行统计",
        "product_positioning": "面向交通运输管理单位的干支线路径适配与协同调度平台",
        "visual_mood": "交通线路调度台",
        "dashboard_pattern": "线路地图+班次指标",
        "module_pattern": "路径适配",
        "domain_terms": ["干线线路", "支线线路", "站点接驳", "路径适配", "班次计划", "换乘规则", "运行统计"],
        "metrics": ["线路覆盖率", "班次准点率", "接驳成功率", "路径匹配率", "换乘耗时", "异常班次数"],
        "layout_signature": "transport_route:map:side_menu:freeform_grid:split_brand:线路地图+班次指标:路径适配",
    }
    for key, value in replacement.items():
        if key in {"industry_subtype_key", "industry_subtype"} or key not in design_brief or _contains_banned_text(design_brief.get(key), banned):
            design_brief[key] = value
    for key in ["optimized_prompt", "visual_style"]:
        if _contains_banned_text(design_brief.get(key), banned):
            design_brief[key] = "围绕交通运输干线支线路径适配管理组织线路、节点、接驳、匹配评估、规则发布和运行统计界面。"
    dna = design_brief.get("design_dna")
    if isinstance(dna, dict):
        if _contains_banned_text(dna, banned):
            dna["optimized_prompt"] = "围绕交通运输干线支线路径适配管理生成真实交通线路调度界面，体现干线、支线、节点、接驳、匹配评估和运行统计。"
            dna["semantic_terms"] = ["交通运输干线支线路径适配管理", "干线线路", "支线线路", "运输节点", "路径匹配评估", "衔接规则", "适配问题处置", "方案发布"]
            dna["domain_bias"] = "geo_monitor"
    structure = design_brief.get("structure_blueprint")
    if isinstance(structure, dict) and _contains_banned_text(structure, banned):
        design_brief["structure_blueprint"] = _transport_structure_blueprint(structure)


def _contains_banned_text(value: Any, banned: tuple[str, ...]) -> bool:
    return any(term in json.dumps(value, ensure_ascii=False) for term in banned)


def _transport_structure_blueprint(previous: dict[str, Any] | None = None) -> dict[str, Any]:
    base_id = str((previous or {}).get("id") or "transport_route_ui")
    return {
        "id": base_id,
        "grammar": "freeform_grid",
        "domain_bias": "geo_monitor",
        "dashboard": {
            "layout": "dense_console",
            "slots": [
                {"kind": "map", "title": "干支线路径分布", "span": 7, "role": "identity"},
                {"kind": "metrics", "title": "接驳运行指标", "span": 5, "role": "primary"},
                {"kind": "queue", "title": "路径匹配待办", "span": 6, "role": "support"},
                {"kind": "focus", "title": "衔接规则看板", "span": 6, "role": "evidence"},
            ],
        },
        "module": {
            "layout": "document_desk",
            "slots": [
                {"kind": "map", "title": "线路节点定位", "span": 4, "role": "filters"},
                {"kind": "table", "title": "路径适配清单", "span": 5, "role": "primary"},
                {"kind": "queue", "title": "问题处置队列", "span": 3, "role": "actions"},
                {"kind": "timeline", "title": "评估发布流程", "span": 6, "role": "detail"},
                {"kind": "focus", "title": "衔接规则依据", "span": 6, "role": "primary"},
            ],
        },
        "statistics": {
            "layout": "wide_board",
            "slots": [
                {"kind": "map", "title": "区域适配分布", "span": 6, "role": "summary"},
                {"kind": "chart", "title": "准点衔接趋势", "span": 6, "role": "trend"},
                {"kind": "table", "title": "线路运行统计", "span": 6, "role": "breakdown"},
                {"kind": "timeline", "title": "问题闭环流程", "span": 6, "role": "evidence"},
            ],
        },
    }


def screenshot_role_contract_from_fallback(fallback: UiBlueprint, expected_renderer: str) -> dict[str, Any]:
    design_brief = getattr(fallback, "design_brief", {}) or {}
    contract = design_brief.get("screenshot_role_contract")
    if isinstance(contract, dict):
        return contract
    return {
        "strategy": "quality-guardrails-with-variable-content",
        "renderer": expected_renderer,
        "role_signature": "",
        "roles": [],
        "variation_rules": [],
    }


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
        view_types = ", ".join(sorted(_admin_allowed_view_types()))
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


def _ui_blueprint_from_data(
    data: dict[str, Any],
    fallback: UiBlueprint,
    expected_renderer: str,
    *,
    require_complete_model: bool = False,
) -> UiBlueprint:
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
            if require_complete_model:
                raise ValueError(f"模型界面蓝图缺少截图 key={fallback_screen.key}")
            screens.append(fallback_screen)
            continue
        if require_complete_model:
            _ensure_model_screen_complete(item, fallback_screen)
        view_type = _normalize_view_type(
            expected_renderer,
            fallback_screen.key,
            str(item.get("view_type") or ""),
            fallback_screen.view_type,
        )
        title = _normalize_screen_title(
            str(item.get("title") or fallback_screen.title),
            fallback_screen,
            fallback_screen.title,
        )
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
    design_brief = dict(getattr(fallback, "design_brief", {}) or {})
    design_brief.setdefault("screenshot_role_contract", screenshot_role_contract_from_fallback(fallback, expected_renderer))
    return UiBlueprint(
        renderer=expected_renderer,
        visual_style=visual_style,
        screens=screens,
        design_brief=design_brief,
    )


def _ensure_model_screen_complete(item: dict[str, Any], fallback_screen: UiScreenBlueprint) -> None:
    if not str(item.get("title") or "").strip() or not str(item.get("caption") or "").strip():
        raise ValueError(f"模型界面蓝图 {fallback_screen.key} 缺少标题或图注")
    components = item.get("components")
    if not isinstance(components, list) or len([value for value in components if str(value).strip()]) < 4:
        raise ValueError(f"模型界面蓝图 {fallback_screen.key} 组件不足")
    sample_data = item.get("sample_data")
    if not isinstance(sample_data, dict) or len([key for key, value in sample_data.items() if str(key).strip() and str(value).strip()]) < 3:
        raise ValueError(f"模型界面蓝图 {fallback_screen.key} 样例数据不足")


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


def _normalize_screen_title(value: str, fallback_screen: UiScreenBlueprint, fallback: str) -> str:
    title = _clean_text(value, fallback, 32)
    if fallback_screen.key == "login":
        return fallback
    if fallback_screen.key == "dashboard":
        return fallback
    if fallback_screen.key == "statistics":
        return fallback
    if fallback_screen.module_key:
        return fallback
    return title


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
    elif renderer == "mobile_app":
        forced = {"login": "mobile_login", "dashboard": "mobile_home", "statistics": "mobile_statistics"}
        allowed = {"mobile_login", "mobile_home", "mobile_module", "mobile_search", "mobile_detail", "mobile_player", "mobile_profile", "mobile_statistics"}
    else:
        forced = {"login": "admin_login", "dashboard": "admin_dashboard", "statistics": "admin_statistics"}
        allowed = _admin_allowed_view_types()
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


def _expected_renderer(task: GenerationTask, blueprint: ProductBlueprint, experience_spec: ProductExperienceSpec | None = None) -> str:
    spec = experience_spec or build_product_experience_spec(task, blueprint)
    spec_renderer = expected_renderer_for_experience(spec)
    if spec_renderer == "game":
        return "game"
    if spec_renderer == "mobile_app":
        return "mobile_app"
    return "admin"


def _admin_allowed_view_types() -> set[str]:
    return {
        "admin_login",
        "admin_dashboard",
        "admin_module",
        "admin_table",
        "admin_map",
        "admin_pipeline",
        "admin_board",
        "admin_case",
        "admin_risk",
        "admin_form",
        "admin_matrix",
        "admin_statistics",
    }


def _renderer_note(renderer: str, design_brief: dict[str, Any] | None = None) -> str:
    if design_brief and design_brief.get("visual_direction"):
        return str(design_brief.get("visual_direction") or "")
    if renderer == "game":
        return "手机游戏 9:16 竖屏界面，强调玩家、关卡、棋盘、道具、结算等游戏元素。"
    if renderer == "mobile_app":
        return "面向普通用户的手机 App 9:16 竖屏界面，强调首页内容、搜索、详情、播放/使用/收藏、个人中心等真实用户操作。"
    return "桌面业务系统界面，强调业务看板、表格列表、筛选、流程状态和统计报表。"


def is_game_like(task: GenerationTask, blueprint: ProductBlueprint) -> bool:
    text = _game_detection_text(task, blueprint)
    explicit_text = _game_detection_text(task, blueprint, include_product_type=False)
    if task.product_type == "游戏软件":
        if _has_non_game_training_or_business_context(explicit_text):
            return _has_explicit_game_terms(explicit_text) or _looks_like_game_board_text(explicit_text)
        return True
    if _has_non_game_training_or_business_context(text):
        return False
    if _has_explicit_game_terms(text):
        return True
    return _looks_like_game_board_text(text)


def _has_explicit_game_terms(text: str) -> bool:
    strong_keywords = [
        "游戏",
        "手游",
        "小游戏",
        "消除",
        "点消",
        "三消",
        "连消",
        "糖果",
        "对局",
        "玩家",
        "道具背包",
        "关卡地图",
        "排行榜",
    ]
    return any(keyword in text for keyword in strong_keywords)


def _game_detection_text(task: GenerationTask, blueprint: ProductBlueprint, include_product_type: bool = True) -> str:
    parts = [
        task.software_name,
        task.feature_hint,
        getattr(blueprint, "industry", ""),
        getattr(blueprint, "scenario", ""),
        getattr(blueprint, "positioning", ""),
        getattr(blueprint, "summary", ""),
        " ".join(getattr(blueprint, "roles", []) or []),
        " ".join(getattr(blueprint, "target_users", []) or []),
        " ".join(getattr(blueprint, "business_objects", []) or []),
    ]
    if include_product_type:
        parts.insert(1, task.product_type)
    for module in getattr(blueprint, "modules", []) or []:
        parts.extend(
            [
                str(getattr(module, "title", "") or ""),
                str(getattr(module, "description", "") or ""),
                " ".join(str(item) for item in (getattr(module, "operations", []) or [])[:5]),
                " ".join(str(item) for item in (getattr(module, "data_fields", []) or [])[:5]),
            ]
        )
    return " ".join(part for part in parts if str(part).strip())


def _has_non_game_training_or_business_context(text: str) -> bool:
    return bool(
        re.search(
            r"医疗|医院|诊疗|护理|患者|气道|插管|急救|培训|实训|演练|考核|评分|技能|仿真|VR|虚拟现实|管理|平台|系统|后台|审批|审核|工单|台账|归档|质控|统计报表",
            text,
            flags=re.IGNORECASE,
        )
    )


def is_mobile_app_like(task: GenerationTask, blueprint: ProductBlueprint) -> bool:
    spec = build_product_experience_spec(task, blueprint)
    return expected_renderer_for_experience(spec) == "mobile_app"


def ui_matches_software_type(task: GenerationTask, blueprint: ProductBlueprint, ui_blueprint: UiBlueprint) -> bool:
    if _contains_off_domain_ui_terms(task, blueprint, ui_blueprint):
        return False
    expected_experience = build_product_experience_spec(task, blueprint)
    design_brief = getattr(ui_blueprint, "design_brief", {}) or {}
    if not design_brief_matches_experience(design_brief, expected_experience):
        return False
    if (
        str(design_brief.get("industry_subtype_key") or "") != expected_experience.industry_subtype_key
        or str(design_brief.get("industry_subtype") or "") != expected_experience.industry_subtype
    ):
        return False
    identity_data = design_brief.get("visual_identity_spec") if isinstance(design_brief, dict) else None
    cached_seed = str(design_brief.get("creative_seed") or "") if isinstance(design_brief, dict) else ""
    identity_matches = visual_identity_matches_task(identity_data, task, blueprint, expected_experience)
    if not identity_matches and not (
        bool(getattr(task, "resume_existing_output", False))
        and cached_seed
        and cached_seed == str(getattr(task, "seed", "") or "")
    ):
        return False
    expected_renderer = _expected_renderer(task, blueprint, expected_experience)
    if ui_blueprint.renderer != expected_renderer:
        return False
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

    if is_mobile_app_like(task, blueprint):
        allowed = {"mobile_login", "mobile_home", "mobile_module", "mobile_search", "mobile_detail", "mobile_player", "mobile_profile", "mobile_statistics"}
        view_types = {screen.view_type for screen in ui_blueprint.screens}
        text = " ".join(
            [ui_blueprint.visual_style]
            + [screen.title + screen.caption + " ".join(screen.components) for screen in ui_blueprint.screens]
        )
        forbidden = [
            "管理后台", "运营后台", "审核台", "审批台", "风控控制台", "批量输出",
            "质量复盘", "桌面控制台", "PC端工作台",
        ]
        return (
            ui_blueprint.renderer == "mobile_app"
            and bool(view_types)
            and view_types.issubset(allowed)
            and not any(view_type.startswith("admin_") or view_type.startswith("game_") for view_type in view_types)
            and not any(term in text for term in forbidden)
        )

    view_types = {screen.view_type for screen in ui_blueprint.screens}
    return ui_blueprint.renderer == "admin" and not any(view_type.startswith("game_") for view_type in view_types)


def _contains_off_domain_ui_terms(task: GenerationTask, blueprint: ProductBlueprint, ui_blueprint: UiBlueprint) -> bool:
    text = " ".join(
        [
            task.software_name,
            task.product_type,
            task.feature_hint,
            getattr(blueprint, "industry", ""),
            getattr(blueprint, "summary", ""),
        ]
    )
    ui_text = json.dumps(ui_blueprint.to_dict(), ensure_ascii=False)
    if _has_transport_domain_signal(text):
        medical_context = r"医疗系统|医院管理|手术|手术室|术前|术后|术式|麻醉|科室|医生|护士|患者|病历|处方|诊疗"
        game_context = r"消除棋盘|剩余步数|道具背包|关卡地图"
        return bool(re.search(medical_context, ui_text) or re.search(game_context, ui_text))
    return False


def _has_transport_domain_signal(text: str) -> bool:
    value = str(text or "")
    explicit_terms = r"交通|运输|公交|客运|干线|支线|接驳|换乘|站点|车次|发车|运力|客流"
    if not re.search(explicit_terms, value):
        return False
    medical_terms = r"医疗|医院|诊疗|护理|患者|病区|床位|住院|在院|生命体征|医嘱|护士|医生|病历|班次交接"
    return not re.search(medical_terms, value)


def _game_ui_blueprint(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    visual_identity_attempt: int = 0,
) -> UiBlueprint:
    design_brief = _ui_design_brief_with_contract(task, blueprint, "game", visual_identity_attempt)
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
    for module in blueprint.modules[:10]:
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


def _mobile_app_ui_blueprint(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    visual_identity_attempt: int = 0,
) -> UiBlueprint:
    design_brief = _ui_design_brief_with_contract(task, blueprint, "mobile_app", visual_identity_attempt)
    screens = [
        UiScreenBlueprint(
            key="login",
            title=f"{task.software_name}登录界面",
            caption="用户通过手机号、验证码或第三方账号进入应用，完成个人服务入口初始化。",
            view_type="mobile_login",
            components=["应用标识", "手机号输入", "验证码登录", "隐私协议", "快速体验入口"],
            sample_data={"登录方式": "手机号验证码", "状态": "可进入应用"},
        ),
        UiScreenBlueprint(
            key="dashboard",
            title=f"{task.software_name}首页",
            caption="首页根据软件名称和业务场景展示推荐内容、常用功能入口、搜索入口和个人使用进度。",
            view_type="mobile_home",
            components=["顶部搜索", "推荐内容", "快捷入口", "最近使用", "底部导航"],
            sample_data={"推荐": blueprint.modules[0].title if blueprint.modules else task.software_name, "入口": "首页"},
        ),
    ]
    for module in blueprint.modules[:10]:
        view_type = _mobile_module_view_type(module)
        screens.append(
            UiScreenBlueprint(
                key=_module_screen_key(module.key),
                title=module.title,
                caption=module.description,
                view_type=view_type,
                module_key=module.key,
                components=_mobile_components_for_module(module, view_type),
                sample_data=_mobile_sample_data(task, module, view_type),
            )
        )
    screens.append(
        UiScreenBlueprint(
            key="statistics",
            title=f"{task.software_name}个人中心界面",
            caption="个人中心展示用户资料、收藏记录、使用历史、会员权益和应用设置。",
            view_type="mobile_profile",
            components=["用户资料", "收藏记录", "使用历史", "会员权益", "应用设置"],
            sample_data={"收藏": "28项", "最近使用": "12次", "会员": "有效"},
        )
    )
    visual_style = str(design_brief.get("visual_mood") or "mobile-consumer-app")
    return UiBlueprint(renderer="mobile_app", visual_style=visual_style, screens=screens, design_brief=design_brief)


def _mobile_module_view_type(module) -> str:
    text = f"{module.key} {module.title} {module.description} {' '.join(module.operations)} {' '.join(module.pages)}"
    if any(term in text for term in ["播放", "听歌", "音乐", "歌曲", "听书", "朗读", "视频", "音频"]):
        return "mobile_player"
    if any(term in text for term in ["搜索", "检索", "查找", "发现"]):
        return "mobile_search"
    if any(term in text for term in ["详情", "章节", "专辑", "课程", "商品", "内容"]):
        return "mobile_detail"
    if any(term in text for term in ["我的", "个人", "会员", "收藏", "下载", "缓存", "记录"]):
        return "mobile_profile"
    return "mobile_module"


def _mobile_components_for_module(module, view_type: str) -> list[str]:
    if view_type == "mobile_player":
        return ["内容封面", "标题信息", "播放控制", "进度条", "收藏下载", "相关推荐"]
    if view_type == "mobile_search":
        return ["搜索框", "筛选标签", "结果列表", "历史记录", "热门推荐"]
    if view_type == "mobile_detail":
        return ["详情封面", "简介信息", "目录列表", "主操作按钮", "用户收藏"]
    if view_type == "mobile_profile":
        return ["用户资料", "收藏列表", "下载缓存", "会员权益", "设置入口"]
    return ["内容列表", "分类标签", "操作按钮", "状态提示", "底部导航"]


def _mobile_sample_data(task: GenerationTask, module, view_type: str) -> dict[str, Any]:
    if view_type == "mobile_player":
        return {"当前内容": module.title, "播放进度": "03:28 / 04:52", "播放状态": "播放中", "收藏": "已收藏"}
    if view_type == "mobile_search":
        return {"关键词": task.software_name.replace("软件", ""), "结果数": "36", "排序": "综合推荐"}
    if view_type == "mobile_detail":
        return {"内容名称": module.title, "更新状态": "已同步", "用户操作": "继续使用"}
    if view_type == "mobile_profile":
        return {"收藏数量": "28", "下载缓存": "12项", "会员状态": "有效"}
    return {"模块": module.title, "状态": "可用", "最近使用": "今天"}


def _admin_ui_blueprint(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    visual_identity_attempt: int = 0,
) -> UiBlueprint:
    design_brief = _ui_design_brief_with_contract(task, blueprint, "admin", visual_identity_attempt)
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
    for index, module in enumerate(blueprint.modules[:10]):
        view_type = _admin_module_view_type(task, blueprint, module, index, design_brief)
        screens.append(
            UiScreenBlueprint(
                key=_module_screen_key(module.key),
                title=module.title,
                caption=module.description,
                view_type=view_type,
                module_key=module.key,
                components=_admin_components_for_module(module, view_type),
                sample_data=_admin_sample_data_for_module(module, view_type),
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


def _admin_module_view_type(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    module,
    index: int,
    design_brief: dict[str, Any] | None = None,
) -> str:
    title_text = " ".join(
        str(item)
        for item in [
            getattr(module, "key", ""),
            getattr(module, "title", ""),
        ]
        if str(item).strip()
    )
    description_text = str(getattr(module, "description", "") or "")
    strong_text = f"{title_text} {description_text}"
    operation_text = " ".join(str(item) for item in (getattr(module, "operations", []) or []) if str(item).strip())
    layout_family = str((design_brief or {}).get("layout_family") or "")
    module_pattern = str((design_brief or {}).get("module_pattern") or "")
    context_text = f"{task.software_name} {task.product_type} {task.feature_hint} {getattr(blueprint, 'industry', '')} {getattr(blueprint, 'scenario', '')} {getattr(blueprint, 'positioning', '')} {layout_family} {module_pattern}"
    identity_cycle = _visual_identity_module_cycle(design_brief)
    if identity_cycle:
        return identity_cycle[index % len(identity_cycle)]

    if re.search(r"风险|风控|安全|告警|漏洞|审计|合规|征信|授信|反欺诈|预警|权限|监管", strong_text, re.IGNORECASE):
        return "admin_risk"
    if re.search(r"地图|图层|地理|GIS|定位|轨迹|点位|区域|网格|站点|车辆|基站|线路|路径|接驳|换乘|门禁|客流", title_text, re.IGNORECASE) or ("空间" in title_text and "命名空间" not in title_text):
        return "admin_map"
    if re.search(r"配置|规则|模板|参数|策略|排班|预约|上架", title_text, re.IGNORECASE) or re.search(r"配置|登记|新增|编辑|申请", operation_text, re.IGNORECASE):
        return "admin_form"
    if re.search(r"患者|病历|档案|客户|会员|资料|角色|账号|画像|处方|随访|门诊|科室|资产", title_text, re.IGNORECASE):
        return "admin_case"
    if re.search(r"看板|工单|派单|作业|批改|测评|课堂|班级|课程|通知|事件|处置|售后|回访", title_text, re.IGNORECASE) or re.search(r"分派|处置|批改|确认|归档", operation_text, re.IGNORECASE):
        return "admin_board"
    if re.search(r"流水线|链路|调度|任务编排|训练|模型|部署|资源|集群|容器|云主机|数据源|入仓|血缘|作业实例|作业调度|边缘|计划|班次|命名空间", title_text, re.IGNORECASE) or re.search(r"调度|训练|重跑|部署", operation_text, re.IGNORECASE):
        return "admin_pipeline"
    if re.search(r"统计|报表|指标|分析|矩阵|质量|评分|趋势", title_text, re.IGNORECASE) or re.search(r"统计|分析|导出图表", operation_text, re.IGNORECASE):
        return "admin_matrix"
    family_cycles = {
        "map": ["admin_map", "admin_board", "admin_table", "admin_risk", "admin_form", "admin_matrix"],
        "risk": ["admin_risk", "admin_case", "admin_board", "admin_table", "admin_form", "admin_matrix"],
        "pipeline": ["admin_pipeline", "admin_board", "admin_table", "admin_risk", "admin_form", "admin_matrix"],
        "workflow": ["admin_board", "admin_form", "admin_case", "admin_table", "admin_risk", "admin_matrix"],
        "kanban": ["admin_board", "admin_case", "admin_table", "admin_form", "admin_risk", "admin_matrix"],
        "matrix": ["admin_matrix", "admin_table", "admin_case", "admin_form", "admin_board", "admin_risk"],
        "command": ["admin_risk", "admin_table", "admin_pipeline", "admin_board", "admin_form", "admin_case"],
    }
    if layout_family in family_cycles:
        return family_cycles[layout_family][index % len(family_cycles[layout_family])]
    if re.search(r"地图|GIS|空间|线路|路径|物联网|基站|车辆|站点", context_text, re.IGNORECASE):
        cycle = ["admin_map", "admin_table", "admin_board", "admin_form", "admin_risk", "admin_matrix"]
        return cycle[index % len(cycle)]
    if re.search(r"云|数据|算法|模型|训练|调度|5G|边缘", context_text, re.IGNORECASE):
        cycle = ["admin_pipeline", "admin_table", "admin_board", "admin_risk", "admin_form", "admin_matrix"]
        return cycle[index % len(cycle)]
    cycle = ["admin_table", "admin_board", "admin_form", "admin_case", "admin_pipeline", "admin_risk"]
    return cycle[index % len(cycle)]


def _visual_identity_module_cycle(design_brief: dict[str, Any] | None) -> list[str]:
    if not isinstance(design_brief, dict):
        return []
    values = design_brief.get("module_composition_cycle")
    if not isinstance(values, list):
        identity = design_brief.get("visual_identity_spec")
        values = identity.get("module_composition_cycle") if isinstance(identity, dict) else []
    allowed = _admin_allowed_view_types() - {"admin_login", "admin_dashboard", "admin_statistics"}
    cycle = [str(value).strip() for value in values if str(value).strip() in allowed]
    return cycle


def _admin_components_for_module(module, view_type: str) -> list[str]:
    fields = [str(field) for field in (getattr(module, "data_fields", []) or [])[:4] if str(field).strip()]
    operations = [str(operation) for operation in (getattr(module, "operations", []) or [])[:3] if str(operation).strip()]
    if view_type == "admin_map":
        base = ["空间/区域画布", "点位详情抽屉", "状态图例", "区域筛选", "业务列表"]
    elif view_type == "admin_pipeline":
        base = ["阶段链路", "任务队列", "执行日志", "指标趋势", "发布操作"]
    elif view_type == "admin_risk":
        base = ["风险指标", "复核队列", "规则命中", "处置时间线", "导出留痕"]
    elif view_type == "admin_case":
        base = ["档案摘要", "字段详情", "关联记录", "处理轨迹", "附件留痕"]
    elif view_type == "admin_board":
        base = ["流程看板", "待办卡片", "状态泳道", "任务筛选", "批量操作"]
    elif view_type == "admin_form":
        base = ["参数表单", "字段校验", "预览结果", "保存操作", "操作日志"]
    elif view_type == "admin_matrix":
        base = ["指标矩阵", "趋势图", "分组明细", "统计口径", "导出按钮"]
    else:
        base = ["条件筛选", "业务列表", "详情侧栏", "状态标签", "操作按钮"]
    return _merge_ui_items(base, fields + operations, 7)


def _admin_sample_data_for_module(module, view_type: str) -> dict[str, Any]:
    fields = [str(field) for field in (getattr(module, "data_fields", []) or [])[:4] if str(field).strip()]
    sample: dict[str, Any] = {
        "模块": getattr(module, "title", "") or "业务模块",
        "状态": "处理中" if view_type in {"admin_pipeline", "admin_board"} else "已启用",
        "记录数": "128",
    }
    for index, field in enumerate(fields[:3], start=1):
        sample[field] = f"{getattr(module, 'title', '业务')}{index:02d}"
    if view_type == "admin_map":
        sample["区域"] = "核心服务区"
        sample["点位"] = "A-102"
    elif view_type == "admin_risk":
        sample["风险等级"] = "中风险"
        sample["处置结论"] = "待复核"
    elif view_type == "admin_pipeline":
        sample["当前阶段"] = "校验通过"
        sample["执行批次"] = "B20260629"
    elif view_type == "admin_case":
        sample["档案编号"] = "DA-20260629-001"
    elif view_type == "admin_form":
        sample["校验结果"] = "通过"
    return sample


def _merge_ui_items(primary: list[str], secondary: list[str], limit: int) -> list[str]:
    result: list[str] = []
    for item in primary + secondary:
        value = str(item).strip()
        if value and value not in result:
            result.append(value)
    return result[:limit] or primary[:limit]


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
