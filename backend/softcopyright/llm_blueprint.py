from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
import re
import time
from typing import Any

from .blueprint import FeatureModule, ProductBlueprint, _environment_for_language, _runtime_for_language
from .llm.provider import LLMProvider, LocalTemplateProvider
from .llm.trace import trace_event
from .models import GenerationTask


def generate_blueprint_with_llm(task: GenerationTask, provider: LLMProvider | None, emit=None) -> ProductBlueprint | None:
    if provider is None or isinstance(provider, LocalTemplateProvider):
        return None

    rejection_reasons: list[str] = []
    last_error: Exception | None = None
    best_blueprint: ProductBlueprint | None = None
    best_score = 0
    quality_floor = _blueprint_quality_floor(task)
    attempt_count = 5 if _authenticity_first(task) else 2
    for _attempt in range(attempt_count):
        started_at = time.perf_counter()
        trace_event(
            "blueprint_attempt_begin",
            attempt=_attempt + 1,
            total_attempts=attempt_count,
            quality_floor=quality_floor,
            profile=_generation_quality_profile(task),
            software_name=task.software_name,
            product_type=task.product_type,
        )
        try:
            _emit(emit, 15, f"生成产品蓝图 {_attempt + 1}/{attempt_count}")
            core_plan = _generate_core_plan(task, provider, rejection_reasons, emit=emit)
            module_plan = _generate_modules(task, provider, core_plan, rejection_reasons, emit=emit)
            data = _merge_plan(core_plan, module_plan)
            blueprint = _blueprint_from_data(task, data)
            score, reasons = _quality_review(task, blueprint)
            blueprint.quality_score = score

            if score < quality_floor:
                try:
                    _emit(emit, 21, f"修复产品蓝图质量，当前评分 {score}/{quality_floor}")
                    repaired_data = _repair_plan(task, provider, data, score, reasons)
                    repaired_blueprint = _blueprint_from_data(task, repaired_data)
                    repaired_score, repaired_reasons = _quality_review(task, repaired_blueprint)
                    repaired_blueprint.quality_score = repaired_score
                    if repaired_score >= score:
                        data = repaired_data
                        blueprint = repaired_blueprint
                        score = repaired_score
                        reasons = repaired_reasons
                except Exception as repair_exc:
                    reasons = reasons + [f"质量修复请求失败：{str(repair_exc)[:120]}"]

            if score > best_score:
                best_blueprint = blueprint
                best_score = score
            if score >= quality_floor:
                trace_event(
                    "blueprint_attempt_success",
                    attempt=_attempt + 1,
                    elapsed_seconds=round(time.perf_counter() - started_at, 3),
                    quality_score=score,
                    quality_floor=quality_floor,
                    module_count=len(blueprint.modules),
                )
                return blueprint
            rejection_reasons = reasons
            last_error = ValueError(f"LLM 产品方案质量分 {score}，未达 {quality_floor}：{'；'.join(reasons[:4])}")
            trace_event(
                "blueprint_attempt_rejected",
                attempt=_attempt + 1,
                elapsed_seconds=round(time.perf_counter() - started_at, 3),
                quality_score=score,
                quality_floor=quality_floor,
                reasons=reasons[:6],
            )
        except Exception as exc:
            last_error = exc
            rejection_reasons = [str(exc)[:180]]
            trace_event(
                "blueprint_attempt_error",
                attempt=_attempt + 1,
                elapsed_seconds=round(time.perf_counter() - started_at, 3),
                error_type=type(exc).__name__,
                error=str(exc)[:500],
            )
    if best_blueprint and not _authenticity_first(task) and best_score >= 72:
        return best_blueprint
    if last_error:
        raise last_error
    return None


def _emit(emit, progress: int, message: str, **extra) -> None:
    if emit:
        emit(progress, message, **extra)


def _system_prompt() -> str:
    return (
        "你是中文软件产品经理、软件架构师和软件著作权材料生成专家。"
        "请先把软件当成真实项目设计，再生成可被说明书、源码工程和界面截图共同使用的产品方案。"
        "只返回 JSON，不要返回 Markdown，不要编造公司主体信息，不要承诺包过。"
    )


def _generate_core_plan(
    task: GenerationTask,
    provider: LLMProvider,
    rejection_reasons: list[str] | None = None,
    emit=None,
) -> dict[str, Any]:
    _emit(emit, 16, "生成产品身份定位")
    identity_plan = _generate_identity_plan(task, provider, rejection_reasons)
    _emit(emit, 17, "生成业务对象、流程和指标")
    business_detail = _generate_business_details(task, provider, identity_plan, rejection_reasons)
    data = dict(identity_plan)
    data.update(business_detail)
    contract_modules = _contract_blueprint_modules(task)
    if contract_modules:
        data["module_outline"] = _outline_from_contract_modules(contract_modules)
    if not isinstance(data.get("module_outline"), list) or len(data.get("module_outline", [])) < 6:
        data["module_outline"] = _module_outline_from_core(data)
    if not isinstance(data.get("pages"), list) or len(data.get("pages", [])) < 8:
        data["pages"] = _pages_from_outline(data.get("module_outline"))
    if not isinstance(data.get("business_objects"), list) or len(data.get("business_objects", [])) < 6:
        raise ValueError("LLM 核心产品方案业务对象不足")
    if not isinstance(data.get("workflows"), list) or len(data.get("workflows", [])) < 3:
        raise ValueError("LLM 核心产品方案业务流程不足")
    return data


def _generate_identity_plan(
    task: GenerationTask,
    provider: LLMProvider,
    rejection_reasons: list[str] | None = None,
) -> dict[str, Any]:
    data = _chat_json(
        provider,
        [
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": _build_core_prompt(task, rejection_reasons)},
        ],
        temperature=_temperature(task.randomness),
        max_tokens=1500,
        label="产品身份定位",
    )
    if not data.get("scenario") or not data.get("positioning"):
        raise ValueError("LLM 产品身份定位不完整")
    return data


def _generate_business_details(
    task: GenerationTask,
    provider: LLMProvider,
    identity_plan: dict[str, Any],
    rejection_reasons: list[str] | None = None,
) -> dict[str, Any]:
    return _chat_json(
        provider,
        [
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": _build_business_detail_prompt(task, identity_plan, rejection_reasons)},
        ],
        temperature=_temperature(task.randomness),
        max_tokens=2100,
        label="业务细节方案",
    )


def _generate_modules(
    task: GenerationTask,
    provider: LLMProvider,
    core_plan: dict[str, Any],
    rejection_reasons: list[str] | None = None,
    emit=None,
) -> dict[str, Any]:
    contract_modules = _modules_from_contract(task, core_plan)
    if contract_modules and not _module_batch_quality_reasons(task, contract_modules, expected_count=min(8, len(contract_modules))):
        trace_event(
            "blueprint_contract_modules_reused",
            module_count=len(contract_modules),
            titles=[str(item.get("title") or "") for item in contract_modules[:8]],
        )
        _emit(emit, 18, f"复用名称理解模块蓝图 {len(contract_modules[:8])} 个")
        return {"modules": contract_modules[:8]}
    modules = _generate_module_batches(task, provider, core_plan, rejection_reasons, "", emit=emit)
    return {"modules": modules}


def _generate_module_batches(
    task: GenerationTask,
    provider: LLMProvider,
    core_plan: dict[str, Any],
    rejection_reasons: list[str] | None,
    first_error: str,
    emit=None,
) -> list[dict[str, Any]]:
    outline = core_plan.get("module_outline")
    if not isinstance(outline, list) or len(outline) < 6:
        outline = _module_outline_from_core(core_plan)
    if len(outline) < 6:
        detail = f"：{first_error[:160]}" if first_error else ""
        raise ValueError(f"LLM 模块轮廓不足，无法分批生成模块{detail}")

    modules: list[dict[str, Any]] = []
    batch_size = 1 if _authenticity_first(task) else 2
    batch_count = (min(len(outline), 8) + batch_size - 1) // batch_size
    batches: list[tuple[int, list[Any]]] = []
    for start in range(0, min(len(outline), 8), batch_size):
        batch = outline[start : start + batch_size]
        batch_index = start // batch_size + 1
        batches.append((batch_index, batch))

    def run_batch(batch_index: int, batch: list[Any]) -> list[dict[str, Any]]:
        title = _batch_title(batch)
        _emit(emit, 17 + batch_index, f"细分功能模块 {batch_index}/{batch_count}：{title}")
        data = _chat_json(
            provider,
            [
                {"role": "system", "content": _system_prompt()},
                {"role": "user", "content": _build_module_batch_prompt(task, core_plan, batch, rejection_reasons, first_error)},
            ],
            temperature=_temperature(task.randomness),
            max_tokens=1500,
            label=f"模块明细批次{batch_index}",
        )
        batch_modules = data.get("modules")
        if not isinstance(batch_modules, list):
            raise ValueError("LLM 分批模块方案不是 modules 数组")
        modules = [item for item in batch_modules if isinstance(item, dict)]
        if _authenticity_first(task):
            reasons = _module_batch_quality_reasons(task, modules, expected_count=len(batch))
            if reasons:
                _emit(emit, 17 + batch_index, f"修复功能模块 {batch_index}/{batch_count}：{title}")
                repair_data = _chat_json(
                    provider,
                    [
                        {"role": "system", "content": _system_prompt()},
                        {"role": "user", "content": _build_module_repair_prompt(task, core_plan, batch, modules, reasons)},
                    ],
                    temperature=min(_temperature(task.randomness) + 0.03, 0.85),
                    max_tokens=1500,
                    label=f"模块明细修复批次{batch_index}",
                )
                repaired_modules = repair_data.get("modules")
                if isinstance(repaired_modules, list):
                    modules = [item for item in repaired_modules if isinstance(item, dict)]
        reasons = _module_batch_quality_reasons(task, modules, expected_count=len(batch))
        if reasons:
            raise ValueError("模块明细质量不足：" + "；".join(reasons[:4]))
        return modules

    batch_results: dict[int, list[dict[str, Any]]] = {}
    workers = 1 if _authenticity_first(task) else _llm_batch_workers()
    if workers <= 1 or len(batches) <= 1:
        for batch_index, batch in batches:
            batch_results[batch_index] = run_batch(batch_index, batch)
    else:
        with ThreadPoolExecutor(max_workers=min(workers, len(batches))) as executor:
            futures = {executor.submit(run_batch, batch_index, batch): batch_index for batch_index, batch in batches}
            for future in as_completed(futures):
                batch_index = futures[future]
                batch_results[batch_index] = future.result()

    for batch_index in sorted(batch_results):
        modules.extend(batch_results[batch_index])
    if len(modules) < 6:
        raise ValueError(f"LLM 分批模块方案数量不足：{len(modules)}")
    return modules[:8]


def _llm_batch_workers() -> int:
    try:
        value = int(os.getenv("SOFT_LLM_BATCH_WORKERS", "1"))
    except ValueError:
        value = 1
    return max(1, min(3, value))


def _generation_quality_profile(task: GenerationTask) -> str:
    value = os.getenv("SOFT_GENERATION_PROFILE", "").strip().lower()
    if value in {"fast", "speed", "batch"}:
        return "fast"
    return "authenticity-first"


def _authenticity_first(task: GenerationTask) -> bool:
    return _generation_quality_profile(task) == "authenticity-first"


def _blueprint_quality_floor(task: GenerationTask) -> int:
    if _authenticity_first(task):
        raw = os.getenv("SOFT_BLUEPRINT_QUALITY_FLOOR", "92").strip() or "92"
        try:
            return max(78, min(95, int(raw)))
        except ValueError:
            return 92
    return 78


def _semantic_contract(task: GenerationTask) -> dict[str, Any]:
    value = getattr(task, "semantic_contract", None)
    return value if isinstance(value, dict) else {}


def _contract_keywords(task: GenerationTask) -> list[str]:
    contract = _semantic_contract(task)
    values: list[str] = []
    for key in ("feature_hint_keywords", "feature_hint_target_users"):
        raw = contract.get(key)
        if isinstance(raw, list):
            values.extend(str(item).strip() for item in raw if str(item).strip())
    for module in _contract_blueprint_modules(task):
        values.append(str(module.get("title") or "").strip())
        values.append(str(module.get("category") or "").strip())
        for key in ("data_objects", "screens"):
            raw = module.get(key)
            if isinstance(raw, list):
                values.extend(str(item).strip() for item in raw if str(item).strip())
    values.extend(term for term in re.split(r"[，,、\s]+", task.feature_hint or "") if len(term) >= 2)
    return list(dict.fromkeys(values))[:28]


def _contract_avoid_terms(task: GenerationTask) -> list[str]:
    contract = _semantic_contract(task)
    raw = contract.get("feature_hint_avoid_terms")
    values = [str(item).strip() for item in raw if str(item).strip()] if isinstance(raw, list) else []
    expanded: list[str] = []
    for item in values:
        expanded.append(item)
        expanded.extend(term for term in re.split(r"[，,、/\s]+", item) if len(term) >= 2)
    return list(dict.fromkeys(expanded))[:36]


def _contract_guidance(task: GenerationTask) -> str:
    contract = _semantic_contract(task)
    keywords = _contract_keywords(task)
    avoid_terms = _contract_avoid_terms(task)
    blueprint_modules = _contract_blueprint_modules(task)
    domain = str(contract.get("feature_hint_domain") or "").strip()
    profile = str(contract.get("feature_hint_profile") or "").strip()
    target_users = contract.get("feature_hint_target_users") or []
    parts: list[str] = []
    if domain or profile:
        parts.append(f"- 名称理解契约：profile={profile or 'unknown'}，domain={domain or '未提供'}。")
    if target_users:
        parts.append(f"- 目标用户必须贴合：{'、'.join(str(item) for item in target_users[:8])}。")
    if keywords:
        parts.append(f"- 模块、对象、流程、字段和页面必须优先命中名称理解关键词：{'、'.join(keywords[:18])}。")
    if blueprint_modules:
        module_notes = []
        for module in blueprint_modules[:10]:
            title = str(module.get("title") or "").strip()
            category = str(module.get("category") or "").strip()
            data_objects = "、".join(str(item) for item in (module.get("data_objects") or [])[:3])
            if title:
                module_notes.append(f"{title}（{category or '未分类'}；对象：{data_objects or '未提供'}）")
        if module_notes:
            parts.append(f"- 名称理解阶段已生成结构化蓝图模块，后续方案必须继承或合理扩展：{'；'.join(module_notes)}。")
    if avoid_terms:
        parts.append(f"- 禁止偏离名称理解契约的方向或词语：{'、'.join(avoid_terms[:18])}。")
    return "\n".join(parts)


def _contract_blueprint_modules(task: GenerationTask) -> list[dict[str, Any]]:
    raw = _semantic_contract(task).get("feature_hint_blueprint_modules")
    if not isinstance(raw, list):
        return []
    modules: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict) and str(item.get("title") or "").strip():
            modules.append(item)
    return modules[:12]


def _outline_from_contract_modules(modules: list[dict[str, Any]]) -> list[dict[str, str]]:
    outline: list[dict[str, str]] = []
    for index, item in enumerate(modules[:8], start=1):
        title = _clean_text(str(item.get("title") or ""), 28)
        if not title:
            continue
        category = _clean_text(str(item.get("category") or ""), 24)
        description = _clean_text(str(item.get("description") or ""), 120)
        outline.append(
            {
                "key": _contract_module_key(item, index),
                "title": title,
                "focus": description or f"围绕{title}组织{category or '业务'}处理、状态跟踪和结果输出",
            }
        )
    return outline


def _modules_from_contract(task: GenerationTask, core_plan: dict[str, Any]) -> list[dict[str, Any]]:
    contract_modules = _contract_blueprint_modules(task)
    if len(contract_modules) < 6:
        return []
    modules: list[dict[str, Any]] = []
    for index, item in enumerate(contract_modules[:8], start=1):
        title = _clean_text(str(item.get("title") or ""), 28)
        if not title:
            continue
        category = _clean_text(str(item.get("category") or ""), 24)
        data_objects = _clean_list(item.get("data_objects"), 6, 26)
        user_flow = _clean_list(item.get("user_flow"), 6, 34)
        screens = _clean_list(item.get("screens"), 5, 28)
        key = _contract_module_key(item, index)
        operations = _ensure_min_strings(
            _clean_list(item.get("operations") or item.get("actions"), 7, 28),
            _contract_operations(title, category, user_flow),
            minimum=5,
            limit=7,
        )
        data_fields = _ensure_min_strings(
            _clean_list(item.get("data_fields") or item.get("dataFields") or item.get("fields"), 10, 24),
            _contract_data_fields(title, category, data_objects),
            minimum=7,
            limit=10,
        )
        pages = _ensure_min_strings(
            _clean_list(item.get("pages") or item.get("screens"), 4, 28),
            _contract_pages(title, screens),
            minimum=2,
            limit=4,
        )
        rules = _ensure_min_strings(
            _clean_list(item.get("rules") or item.get("quality_rules") or item.get("qualityRules"), 5, 80),
            _contract_rules(title, category, data_objects, operations),
            minimum=3,
            limit=5,
        )
        entities = _ensure_min_strings(
            [_safe_entity(_entity_name_from_item(entity)) for entity in (item.get("entities") or [])[:4] if _entity_name_from_item(entity)],
            _contract_entities(key),
            minimum=2,
            limit=4,
        )
        modules.append(
            {
                "key": key,
                "title": title,
                "description": _contract_description(item, title, category, data_objects, operations, pages, core_plan),
                "entities": entities,
                "operations": operations,
                "data_fields": data_fields,
                "pages": pages,
                "rules": rules,
            }
        )
    return modules


def _contract_module_key(item: dict[str, Any], index: int) -> str:
    raw = str(item.get("key") or item.get("id") or "").strip()
    key = _safe_key(raw)
    generic = {"module", "business", "data", "manage", "management", "system", "common", "businessrecord"}
    if not raw or key in generic or re.fullmatch(r"module_\d+", key or ""):
        title = str(item.get("title") or item.get("category") or index)
        digest = hashlib.md5(title.encode("utf-8", errors="ignore")).hexdigest()[:6]
        key = f"semantic_{index:02d}_{digest}"
    return key


def _contract_operations(title: str, category: str, user_flow: list[str]) -> list[str]:
    operations: list[str] = []
    for step in user_flow:
        cleaned = _operation_label(step)
        if cleaned:
            operations.append(cleaned)
    seed = category or title
    for action in _operation_templates_for(seed, title):
        operations.append(action)
    return _dedupe_strings(operations, 7)


def _operation_label(value: str) -> str:
    value = re.sub(r"^(用户|管理员|人员|系统|平台)?(进行|完成|执行|点击|进入|查看)?", "", value).strip(" ，,、。；;")
    value = re.sub(r"(后|并|，|,|。|；|;).*$", "", value).strip()
    return _clean_text(value, 28)


def _operation_templates_for(seed: str, title: str) -> list[str]:
    templates = [
        ("建档", ["登记建档", "补全档案", "核对参数", "提交复核"]),
        ("档案", ["登记建档", "补全档案", "核对参数", "变更留痕"]),
        ("采集", ["采集接入", "样本校验", "记录同步", "异常标注"]),
        ("接入", ["采集接入", "来源校验", "记录同步", "异常标注"]),
        ("监测", ["实时监测", "阈值比对", "趋势复核", "异常标注"]),
        ("温控", ["温度采集", "阈值比对", "曲线复核", "异常标注"]),
        ("预警", ["阈值预警", "提醒生成", "处置确认", "反馈跟踪"]),
        ("建议", ["建议生成", "规则匹配", "方案确认", "执行推送"]),
        ("养护", ["养护建议生成", "执行确认", "效果记录", "复盘归档"]),
        ("处置", ["处置派发", "反馈记录", "闭环确认", "复盘归档"]),
        ("统计", ["汇总分析", "报表生成", "趋势对比", "摘要输出"]),
        ("分析", ["汇总分析", "趋势对比", "指标钻取", "摘要输出"]),
        ("配置", ["规则维护", "阈值配置", "策略启停", "变更记录"]),
    ]
    for marker, values in templates:
        if marker in seed or marker in title:
            return values
    return [f"{seed}登记", f"{seed}校验", f"{title}跟踪", f"{title}确认"]


def _contract_data_fields(title: str, category: str, data_objects: list[str]) -> list[str]:
    fields: list[str] = []
    for obj in data_objects[:3]:
        fields.extend([f"{obj}编号", f"{obj}名称"])
    seed = category or title
    fields.extend(
        [
            f"{seed}来源",
            f"{seed}状态",
            "采集时间",
            "责任人员",
            "阈值等级",
            "处理结论",
            "更新时间",
            "审计标记",
        ]
    )
    return _dedupe_strings(fields, 10)


def _contract_pages(title: str, screens: list[str]) -> list[str]:
    pages = [screen if screen.endswith("页") or screen.endswith("界面") or screen.endswith("台") else f"{screen}页" for screen in screens]
    pages.extend([f"{title}页", f"{title}明细页", f"{title}记录页"])
    return _dedupe_strings(pages, 4)


def _contract_rules(title: str, category: str, data_objects: list[str], operations: list[str]) -> list[str]:
    subject = "、".join(data_objects[:2]) or title
    action = operations[0] if operations else "业务操作"
    seed = category or title
    return [
        f"{subject}执行{action}前必须校验来源、时间和责任人员完整性。",
        f"{title}仅允许授权角色处理本人职责范围内的{seed}记录。",
        f"{title}状态变更必须写入审计标记，并保留原始值、操作人和更新时间。",
        f"{title}异常结果需进入复核或确认流程后才能形成最终输出。",
    ]


def _contract_entities(key: str) -> list[str]:
    base = _entity_base_from_key(key) or "SemanticModule"
    return [f"{base}Record", f"{base}Trace", f"{base}Rule"]


def _contract_description(
    item: dict[str, Any],
    title: str,
    category: str,
    data_objects: list[str],
    operations: list[str],
    pages: list[str],
    core_plan: dict[str, Any],
) -> str:
    original = _clean_text(str(item.get("description") or ""), 120)
    object_text = "、".join(data_objects[:3]) or "业务对象"
    operation_text = "、".join(operations[:4]) or "采集、校验、确认、输出"
    page_text = "、".join(pages[:2]) or f"{title}页"
    metric = ""
    metrics = core_plan.get("report_metrics")
    if isinstance(metrics, list) and metrics:
        metric = f"，并为{str(metrics[(len(title) + len(category)) % len(metrics)])}提供统计口径"
    supplement = (
        f"模块围绕{object_text}开展{operation_text}，记录状态、责任人、阈值或处理结论，"
        f"通过{page_text}形成可追溯的业务入口和输出结果{metric}。"
    )
    text = f"{original} {supplement}".strip()
    if len(text) < 90:
        text += f" 同时保留校验、权限、状态流转和审计信息，支撑后续说明书、源码实体和界面截图一致呈现。"
    return _clean_text(text, 220)


def _dedupe_strings(values: list[str], limit: int) -> list[str]:
    result: list[str] = []
    for value in values:
        cleaned = _clean_text(str(value or ""), 36).strip(" ，,、。；;")
        if cleaned and cleaned not in result:
            result.append(cleaned)
        if len(result) >= limit:
            break
    return result


def _ensure_min_strings(primary: list[str], fallback: list[str], *, minimum: int, limit: int) -> list[str]:
    values = list(primary)
    if len(values) < minimum:
        values.extend(fallback)
    return _dedupe_strings(values, limit)


def _batch_title(batch: list[Any]) -> str:
    titles: list[str] = []
    for item in batch:
        if isinstance(item, dict):
            titles.append(str(item.get("title") or item.get("key") or "模块").strip())
        else:
            titles.append(str(item).strip())
    return "、".join(title for title in titles if title) or "模块明细"


def _is_music_like_text(text: str) -> bool:
    return any(term in text for term in ["听歌", "音乐", "歌曲", "歌单", "播放器", "歌词", "歌手", "专辑", "电台", "音质", "播放"])


def _is_reading_audio_like_text(text: str) -> bool:
    return any(term in text for term in ["阅读", "听书", "有声", "小说", "书籍", "图书", "朗读", "书城"])


def _is_consumer_app_text(text: str) -> bool:
    if "APP" in text.upper() and not any(term in text for term in ["后台", "管理系统", "OA", "ERP", "CRM"]):
        return True
    return any(
        term in text
        for term in [
            "听歌", "音乐", "歌曲", "歌单", "阅读", "听书", "小说", "短视频", "相册", "拍照", "修图",
            "健身", "打卡", "运动", "日记", "记账", "清单", "便签", "外卖", "商城", "购物",
        ]
    )


def _consumer_app_forbidden_terms() -> list[str]:
    return [
        "风险", "预警", "复核", "审核", "核验", "审批", "工单", "派单", "闭环", "归档", "台账", "留痕",
        "合单", "合演", "点播核验", "点播申请", "登记记录", "电子菜单发布", "批量输出", "发布汇总",
        "质量复盘", "复盘", "质检", "风控", "处置", "监管", "看板", "调度", "业务办理",
    ]


def _domain_terms(task: GenerationTask) -> list[str]:
    text = f"{task.software_name} {task.product_type} {task.feature_hint}"
    contract_terms = _contract_keywords(task)
    if contract_terms:
        return contract_terms
    if _is_music_like_text(text):
        return [
            "听歌", "音乐", "歌曲", "歌单", "播放器", "播放", "暂停", "上一首", "下一首", "歌词", "歌手", "专辑",
            "电台", "音质", "收藏", "下载", "离线", "最近播放", "搜索", "推荐", "会员", "耳机", "循环", "随机",
        ]
    if any(term in text for term in ["阅读", "听书", "有声", "小说", "书籍", "图书", "朗读", "书城"]):
        return [
            "阅读",
            "听书",
            "有声",
            "书籍",
            "图书",
            "小说",
            "章节",
            "书架",
            "书城",
            "音频",
            "播放",
            "朗读",
            "进度",
            "收藏",
            "订阅",
            "会员",
            "推荐",
            "书单",
            "作者",
            "主播",
        ]
    return [term for term in re.split(r"[，,、\s]+", text) if len(term) >= 2]


def _off_domain_terms(task: GenerationTask) -> list[str]:
    text = f"{task.software_name} {task.product_type} {task.feature_hint}"
    contract_terms = _contract_avoid_terms(task)
    if contract_terms:
        return contract_terms
    if _is_music_like_text(text) or _is_consumer_app_text(text):
        return _consumer_app_forbidden_terms()
    if any(term in text for term in ["阅读", "听书", "有声", "小说", "书籍", "图书", "朗读", "书城"]):
        return [
            "风险",
            "预警",
            "复核",
            "审核",
            "核验",
            "审批",
            "工单",
            "派单",
            "闭环",
            "归档",
            "批量输出",
            "发布汇总",
            "质量复盘",
            "复盘",
            "质检",
            "风控",
            "处置",
            "监管",
        ]
    return []


def _domain_guidance(task: GenerationTask) -> str:
    terms = _domain_terms(task)
    blocked = _off_domain_terms(task)
    contract_guidance = _contract_guidance(task)
    text = f"{task.software_name} {task.product_type} {task.feature_hint}"
    if _is_music_like_text(text):
        return (
            (contract_guidance + "\n" if contract_guidance else "")
            +
            f"- 模块、业务对象、流程、字段和页面必须优先围绕：{'、'.join(terms[:24])}。\n"
            f"- 禁止偏离消费级音乐 App 的后台/审核/流程词：{'、'.join(blocked)}。\n"
            "- 如果软件名称包含听歌、音乐、歌曲、歌单或播放器，功能必须围绕首页推荐、音乐搜索、歌曲播放、歌词同步、歌单收藏、歌手专辑、最近播放、离线下载、会员音质和个人中心。\n"
            "- 不得生成点播申请、登记记录、合单、合演、复核、留痕、电子菜单发布、取餐叫号、质量复盘等餐饮/后台/审核模块。\n"
        )
    if _is_consumer_app_text(text):
        return (
            (contract_guidance + "\n" if contract_guidance else "")
            +
            f"- 模块、业务对象、流程、字段和页面必须优先围绕真实用户 App 功能：{'、'.join(terms[:24])}。\n"
            f"- 禁止偏离消费级 App 的后台/审核/流程词：{'、'.join(blocked)}。\n"
            "- 模块应体现用户入口、内容浏览、搜索、详情、收藏、下载/缓存、使用记录、会员/个人中心等面向用户的操作，不得写成后台管理系统。\n"
        )
    if blocked:
        return (
            (contract_guidance + "\n" if contract_guidance else "")
            +
            f"- 模块、业务对象、流程、字段和页面必须优先围绕：{'、'.join(terms[:20])}。\n"
            f"- 禁止偏离软件领域的后台/审核/风控词：{'、'.join(blocked)}。\n"
            "- 如果软件是阅读听书类，功能应围绕书城浏览、书架管理、阅读进度、听书播放、章节目录、书单推荐、收藏订阅、会员权益、播放记录、朗读设置等真实用户功能。"
        )
    base = f"- 模块、业务对象、流程、字段和页面必须命中软件名称、产品类型或业务补充中的领域词：{'、'.join(terms[:20]) or '未提供'}。"
    return (contract_guidance + "\n" if contract_guidance else "") + base


def _domain_action_words(task: GenerationTask) -> list[str]:
    text = f"{task.software_name} {task.product_type} {task.feature_hint}"
    if _is_music_like_text(text):
        return [
            "播放", "暂停", "续播", "切歌", "收藏", "加入歌单", "下载", "缓存", "搜索", "推荐",
            "同步歌词", "切换音质", "查看专辑", "查看歌手", "最近播放", "循环播放", "随机播放",
        ]
    if _is_consumer_app_text(text):
        return ["浏览", "搜索", "查看", "收藏", "使用", "播放", "下载", "缓存", "推荐", "同步", "设置", "分享"]
    if any(term in text for term in ["阅读", "听书", "有声", "小说", "书籍", "图书", "朗读", "书城"]):
        return [
            "阅读",
            "听书",
            "播放",
            "暂停",
            "续播",
            "收藏",
            "订阅",
            "加入书架",
            "下载",
            "缓存",
            "朗读",
            "切换章节",
            "调节语速",
            "推荐",
            "搜索",
            "评论",
            "评分",
        ]
    return []


def _contains_any(text: str, terms: list[str]) -> bool:
    return any(term and term in text for term in terms)


def _module_batch_quality_reasons(task: GenerationTask, modules: list[dict[str, Any]], *, expected_count: int) -> list[str]:
    reasons: list[str] = []
    if len(modules) < expected_count:
        reasons.append(f"模块数量不足，期望 {expected_count} 个，实际 {len(modules)} 个")
    generic_titles = {"数据管理", "业务管理", "统计分析", "系统设置", "权限管理", "信息管理"}
    generic_ops = {"新增", "编辑", "删除", "查询", "导出", "新增记录", "编辑记录", "删除记录", "查询记录", "导出数据"}
    generic_fields = {"名称", "编号", "状态", "备注", "创建时间", "更新时间", "创建人", "修改人"}
    domain_terms = _domain_terms(task)
    off_domain_terms = _off_domain_terms(task)
    for index, module in enumerate(modules, start=1):
        title = str(module.get("title") or "").strip()
        key = str(module.get("key") or "").strip()
        description = str(module.get("description") or "").strip()
        operations = [str(item).strip() for item in module.get("operations") or [] if str(item).strip()]
        fields = [str(item).strip() for item in module.get("data_fields") or [] if str(item).strip()]
        rules = [str(item).strip() for item in module.get("rules") or [] if str(item).strip()]
        module_text = " ".join([title, key, description, " ".join(operations), " ".join(fields), " ".join(rules)])
        if not key or re.fullmatch(r"module_\d+|module|business|data|manage|management", key):
            reasons.append(f"第 {index} 个模块 key 过于泛化")
        if not title or title in generic_titles:
            reasons.append(f"第 {index} 个模块标题过于泛化")
        if domain_terms and not _contains_any(module_text, domain_terms):
            reasons.append(f"{title or key or index} 未命中软件领域词")
        hits = [term for term in off_domain_terms if term in module_text]
        if hits:
            reasons.append(f"{title or key or index} 出现偏离软件领域的词：{'、'.join(hits[:4])}")
        if len(description) < 70:
            reasons.append(f"{title or key or index} 描述不足 70 字")
        if len(set(operations) - generic_ops) < 3:
            reasons.append(f"{title or key or index} 业务操作不够具体")
        if len(set(fields) - generic_fields) < 4:
            reasons.append(f"{title or key or index} 业务字段不够具体")
        if len(rules) < 3:
            reasons.append(f"{title or key or index} 规则少于 3 条")
    return reasons


def _repair_plan(
    task: GenerationTask,
    provider: LLMProvider,
    data: dict[str, Any],
    score: int,
    reasons: list[str],
) -> dict[str, Any]:
    patch_data = _chat_json(
        provider,
        [
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": _build_repair_prompt(task, data, score, reasons)},
        ],
        temperature=min(_temperature(task.randomness) + 0.05, 0.9),
        max_tokens=2200,
        label="产品方案质量修复",
    )
    repaired = dict(data)
    for key, value in patch_data.items():
        if value not in (None, "", []):
            repaired[key] = value
    return repaired


def _merge_plan(core_plan: dict[str, Any], module_plan: dict[str, Any]) -> dict[str, Any]:
    merged = dict(core_plan)
    modules = module_plan.get("modules")
    if not isinstance(modules, list) or len(modules) < 4:
        raise ValueError("LLM 模块方案缺少 modules 数组")
    merged["modules"] = modules
    if not isinstance(merged.get("pages"), list) or len(merged.get("pages", [])) < 8:
        pages = ["登录页", "系统首页"]
        for module in modules[:8]:
            if isinstance(module, dict) and module.get("title"):
                pages.append(f"{module['title']}页")
        pages.extend(["统计报表页", "系统设置页"])
        merged["pages"] = pages[:12]
    return merged


def _build_core_prompt(task: GenerationTask, rejection_reasons: list[str] | None = None) -> str:
    retry_note = ""
    if rejection_reasons:
        retry_note = "\n上一版产品方案被拒绝，原因如下，请逐项修正：\n" + "\n".join(f"- {item}" for item in rejection_reasons[:6])
    variation_strategy = _variation_strategy(task)
    domain_guidance = _domain_guidance(task)
    return f"""
请为以下软件生成软著申请材料用“核心产品方案”。这份 JSON 将驱动说明书正文、源码工程、界面截图和后续模块明细，因此必须像真实可开发的软件项目，而不是通用模板。

软件全称：{task.software_name}
版本号：{task.version}
技术架构要求：{getattr(task, "software_category", "应用软件")}，源码语言由系统根据产品蓝图自动选择，可多语言组合
软件技术特点/产品类型：{task.product_type}
业务补充：{task.feature_hint or "无"}
随机差异要求：{task.randomness}
{retry_note}

本次生成的差异化产品策略：
{variation_strategy}

领域边界要求：
{domain_guidance}

返回 JSON 字段必须包含：
- industry: 面向领域/行业，中文短语
- scenario: 具体使用场景，必须能看出这套软件服务谁、在什么业务环境使用
- positioning: 产品定位，1-2句话，必须区别于同类型通用后台
- purpose: 开发目的，1-2句话
- summary: 软件主要功能概述，160-240字
- roles: 4-6个用户角色，字符串数组
- target_users: 4-6个目标用户或岗位，字符串数组
- deployment_topology: 部署拓扑说明，1句话
- module_outline: 6-8个候选模块轮廓，每个对象只包含 key/title/focus，用于下一步生成模块明细
- pages: 8-12个页面名称，字符串数组

module_outline 规则：
- key 使用小写英文或英文下划线，适合作为源码目录/类名前缀
- title 使用中文模块名
- focus 用一句话说明该模块负责的具体业务对象、动作和输出

质量要求：
- 禁止只写“数据维护、业务处理、统计分析、权限管理”等通用表达
- 禁止所有流程、指标和模块轮廓都使用相同句式
- 至少 70% 模块轮廓和页面必须体现软件名称或业务补充中的具体领域
- 必须按“本次生成的差异化产品策略”组织产品角度、流程重心、模块边界和页面命名
- 同类软件再次生成时也不能复用固定的“首页+数据管理+统计+权限”套壳结构
- 说明书读者应能看出这是一个可申请软著的具体软件，不是泛型后台管理系统

只返回 JSON。
""".strip()


def _build_business_detail_prompt(
    task: GenerationTask,
    identity_plan: dict[str, Any],
    rejection_reasons: list[str] | None = None,
) -> str:
    retry_note = ""
    if rejection_reasons:
        retry_note = "\n上一版产品方案被拒绝，原因如下，请逐项修正：\n" + "\n".join(f"- {item}" for item in rejection_reasons[:5])
    variation_strategy = _variation_strategy(task)
    domain_guidance = _domain_guidance(task)
    return f"""
请基于下面的软件身份定位，补齐软著材料需要的业务细节。只返回 JSON，不要返回 Markdown。

软件全称：{task.software_name}
技术架构要求：{getattr(task, "software_category", "应用软件")}，源码语言由系统根据产品蓝图自动选择，可多语言组合
软件技术特点/产品类型：{task.product_type}
业务补充：{task.feature_hint or "无"}
{retry_note}

本次生成的差异化产品策略：
{variation_strategy}

领域边界要求：
{domain_guidance}

软件身份定位：
{_compact_identity_plan(identity_plan)}

返回 JSON 字段必须包含：
- business_objects: 8-12个核心业务对象，中文字符串数组
- workflows: 3-5个业务流程对象，每个包含 name/trigger/steps/output；steps 为4-6个中文步骤
- report_metrics: 8-12个统计指标，中文字符串数组
- technical_features: 5-8个技术实现特点，中文字符串数组
- quality_rules: 6-10个业务校验、权限、审计、状态流转规则，中文字符串数组
- data_relations: 4-8条数据关系，中文字符串数组
- uniqueness_notes: 5-8条差异化说明，必须解释为什么这不是同类通用模板

质量要求：
- 每一项都要围绕软件名称、使用场景和业务补充，不要写泛型后台词
- workflows 的 steps 必须出现当前软件领域内的具体动作；阅读听书类应使用浏览、加入书架、打开章节、播放、暂停、续播、缓存、订阅、推荐等动作
- report_metrics 必须像真实软件首页或报表页会展示的指标
- business_objects、workflows、report_metrics 和 uniqueness_notes 必须呼应差异化产品策略，避免同类软件每次生成同一组对象和指标

只返回 JSON。
""".strip()


def _build_module_prompt(
    task: GenerationTask,
    core_plan: dict[str, Any],
    rejection_reasons: list[str] | None = None,
) -> str:
    retry_note = ""
    if rejection_reasons:
        retry_note = "\n上一版被拒绝原因：\n" + "\n".join(f"- {item}" for item in rejection_reasons[:6])
    domain_guidance = _domain_guidance(task)
    return f"""
请基于“核心产品方案”为软件生成功能模块明细。只返回 JSON，顶层只需要 modules 字段。

软件全称：{task.software_name}
版本号：{task.version}
技术架构要求：{getattr(task, "software_category", "应用软件")}，源码语言由系统根据产品蓝图自动选择，可多语言组合
软件技术特点/产品类型：{task.product_type}
业务补充：{task.feature_hint or "无"}
{retry_note}

核心产品方案摘要：
{_compact_core_plan(core_plan)}

领域边界要求：
{domain_guidance}

modules 必须包含 6-8 个功能模块，每个对象包含：
- key: 小写英文或英文下划线，适合作为源码目录/类名前缀
- title: 中文模块名，必须贴合软件名称、业务补充和核心场景
- description: 90-180字，具体写出业务对象、业务动作、状态流转、权限/校验点和输出结果
- entities: 2-4个英文实体名，必须能用于源码类名
- operations: 4-7个中文操作名称，必须来自当前软件领域；阅读听书类可使用“打开章节”“加入书架”“播放音频”“同步进度”
- data_fields: 6-10个中文业务字段，必须来自当前软件领域；阅读听书类可使用“书籍名称”“章节标题”“播放进度”“收藏状态”
- pages: 2-4个当前模块相关页面名
- rules: 3-5条当前模块业务规则，包含校验、权限、状态流转或审计要求

质量要求：
- 禁止模块标题只叫“数据管理、业务管理、统计分析、系统设置”
- 禁止各模块 description 使用同一句式
- 每个模块都要能映射到说明书章节、源码包名和至少一张软件截图
- 模块必须体现真实业务，不要输出泛型后台管理系统

只返回 JSON。
""".strip()


def _build_module_batch_prompt(
    task: GenerationTask,
    core_plan: dict[str, Any],
    outline_batch: list[Any],
    rejection_reasons: list[str] | None,
    first_error: str,
) -> str:
    retry_note = ""
    if rejection_reasons:
        retry_note = "\n上一版被拒绝原因：\n" + "\n".join(f"- {item}" for item in rejection_reasons[:4])
    first_error_note = f"上一轮完整模块请求失败：{first_error[:180]}\n" if first_error else ""
    variation_strategy = _variation_strategy(task)
    domain_guidance = _domain_guidance(task)
    return f"""
{first_error_note}请只为下面 {len(outline_batch)} 个模块轮廓补齐模块明细，返回 JSON，顶层只需要 modules。

软件全称：{task.software_name}
产品类型：{task.product_type}
业务补充：{task.feature_hint or "无"}
{retry_note}

核心产品方案摘要：
{_compact_core_plan(core_plan)}

本次生成的差异化产品策略：
{variation_strategy}

领域边界要求：
{domain_guidance}

本批模块轮廓：
{json.dumps(outline_batch, ensure_ascii=False)}

每个模块必须包含 key/title/description/entities/operations/data_fields/pages/rules。
description 90-180字；operations 4-7个；data_fields 6-10个；rules 3-5条。
- 模块边界、操作名、字段名和规则必须符合差异化产品策略，不要复用“新增、编辑、删除、导出”四件套作为主要内容。
只返回 JSON。
""".strip()


def _build_module_repair_prompt(
    task: GenerationTask,
    core_plan: dict[str, Any],
    batch: list[Any],
    modules: list[dict[str, Any]],
    reasons: list[str],
) -> str:
    domain_guidance = _domain_guidance(task)
    return f"""
请修复本批功能模块明细。只返回 JSON，顶层只包含 modules。

软件全称：{task.software_name}
版本号：{task.version}
技术架构要求：{getattr(task, "software_category", "应用软件")}，源码语言由系统根据产品蓝图自动选择，可多语言组合
软件技术特点/产品类型：{task.product_type}
业务补充：{task.feature_hint or "无"}

核心产品方案摘要：
{_compact_core_plan(core_plan)}

领域边界要求：
{domain_guidance}

本批模块轮廓：
{json.dumps(batch, ensure_ascii=False, indent=2)}

上一版模块：
{json.dumps(modules, ensure_ascii=False, indent=2)}

必须修复的问题：
{chr(10).join(f"- {item}" for item in reasons[:8])}

真实性要求：
- 每个模块都必须像真实软件项目中的独立功能边界。
- key 必须可用于源码目录、类名或接口前缀，不能使用 module/data/manage 等泛化命名。
- title、description、operations、data_fields、rules 必须呼应软件名称、业务补充、业务对象、流程和指标。
- description 至少 90 字，写清业务对象、用户动作、状态流转、校验点、输出结果。
- operations 至少 5 个，不能只写新增、编辑、删除、查询、导出。
- data_fields 至少 7 个，不能只写名称、编号、状态、备注、创建时间。
- rules 至少 3 条，必须包含校验、权限、状态流转或审计要求。

返回 JSON 示例：
{{"modules":[{{"key":"domain_task_trace","title":"业务任务追踪","description":"...","entities":["TaskRecord","TaskTrace"],"operations":["..."],"data_fields":["..."],"pages":["..."],"rules":["..."]}}]}}
""".strip()


def _build_repair_prompt(task: GenerationTask, data: dict[str, Any], score: int, reasons: list[str]) -> str:
    variation_strategy = _variation_strategy(task)
    domain_guidance = _domain_guidance(task)
    return f"""
请修复下面的软件产品方案，使质量分达到 78 分以上。只返回需要替换或补充的 JSON 字段；如果模块问题较多，可以返回完整 modules 数组。

软件全称：{task.software_name}
产品类型：{task.product_type}
业务补充：{task.feature_hint or "无"}
当前质量分：{score}
扣分原因：
{chr(10).join(f"- {item}" for item in reasons[:8])}

本次生成的差异化产品策略：
{variation_strategy}

领域边界要求：
{domain_guidance}

当前方案压缩快照：
{_compact_full_plan(data)}

修复要求：
- 保持同一个产品方向，不要改成另一个软件
- 补齐 business_objects、workflows、report_metrics、quality_rules、uniqueness_notes 等不足字段
- 如果模块描述空泛，返回完整 modules，并让每个模块包含具体操作、字段、页面和规则
- 如果方案像泛型后台模板，必须按差异化产品策略重写模块边界、业务对象、流程和指标
- 不要返回 Markdown
""".strip()


def _compact_core_plan(data: dict[str, Any]) -> str:
    keys = [
        "industry",
        "scenario",
        "positioning",
        "purpose",
        "summary",
        "roles",
        "target_users",
        "business_objects",
        "workflows",
        "report_metrics",
        "technical_features",
        "quality_rules",
        "data_relations",
        "deployment_topology",
        "uniqueness_notes",
        "module_outline",
        "pages",
    ]
    compact = {key: data.get(key) for key in keys if data.get(key)}
    return json.dumps(compact, ensure_ascii=False, indent=2)[:4200]


def _compact_identity_plan(data: dict[str, Any]) -> str:
    keys = [
        "industry",
        "scenario",
        "positioning",
        "purpose",
        "summary",
        "roles",
        "target_users",
        "deployment_topology",
        "module_outline",
        "pages",
    ]
    compact = {key: data.get(key) for key in keys if data.get(key)}
    return json.dumps(compact, ensure_ascii=False, indent=2)[:3200]


def _compact_full_plan(data: dict[str, Any]) -> str:
    compact = {
        "scenario": data.get("scenario"),
        "positioning": data.get("positioning"),
        "summary": data.get("summary"),
        "business_objects": data.get("business_objects"),
        "workflows": data.get("workflows"),
        "report_metrics": data.get("report_metrics"),
        "quality_rules": data.get("quality_rules"),
        "uniqueness_notes": data.get("uniqueness_notes"),
        "deployment_topology": data.get("deployment_topology"),
        "modules": _compact_modules(data.get("modules")),
    }
    return json.dumps({key: value for key, value in compact.items() if value}, ensure_ascii=False, indent=2)[:5200]


def _compact_modules(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    modules: list[dict[str, Any]] = []
    for item in value[:8]:
        if not isinstance(item, dict):
            continue
        modules.append(
            {
                "key": item.get("key"),
                "title": item.get("title"),
                "description": item.get("description"),
                "operations": item.get("operations"),
                "data_fields": item.get("data_fields"),
                "pages": item.get("pages"),
                "rules": item.get("rules"),
            }
        )
    return modules


def _module_outline_from_core(core_plan: dict[str, Any]) -> list[dict[str, str]]:
    outline: list[dict[str, str]] = []
    plan_text = json.dumps(core_plan, ensure_ascii=False)
    consumer_app = _is_consumer_app_text(plan_text)
    pages = core_plan.get("pages")
    if isinstance(pages, list):
        for index, page in enumerate(pages[:8], start=1):
            title = str(page).replace("页面", "").replace("页", "").strip()
            if title and title not in {"登录", "系统首页", "首页", "统计报表", "系统设置"}:
                outline.append(
                    {
                        "key": f"module_{index}",
                        "title": title if consumer_app else title if title.endswith("管理") or title.endswith("分析") else f"{title}管理",
                        "focus": (
                            f"围绕{title}提供用户入口、内容展示、交互操作和个性化状态"
                            if consumer_app
                            else f"围绕{title}处理核心业务记录、状态流转和统计输出"
                        ),
                    }
                )
            if len(outline) >= 8:
                break

    objects = core_plan.get("business_objects")
    if isinstance(objects, list):
        for index, item in enumerate(objects, start=len(outline) + 1):
            if len(outline) >= 8:
                break
            label = str(item).strip()
            if not label:
                continue
            title = label if consumer_app else label if label.endswith("管理") or label.endswith("分析") else f"{label}管理"
            if title in {entry["title"] for entry in outline}:
                continue
            outline.append(
                {
                    "key": f"module_{index}",
                    "title": title,
                    "focus": (
                        f"围绕{label}建立用户可见的浏览、搜索、使用、收藏或设置能力"
                        if consumer_app
                        else f"围绕{label}建立业务台账、处理流程和结果留痕"
                    ),
                }
            )
    return outline[:8]


def _pages_from_outline(value: Any) -> list[str]:
    pages = ["登录页", "系统首页"]
    if isinstance(value, list):
        for item in value[:8]:
            if isinstance(item, dict):
                title = str(item.get("title") or "").strip()
            else:
                title = str(item).strip()
            if title:
                pages.append(f"{title}页")
    pages.extend(["统计报表页", "系统设置页"])
    return pages[:12]


def _chat_json(
    provider: LLMProvider,
    messages: list[dict[str, str]],
    *,
    temperature: float,
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
            layer="blueprint",
            label=label,
            attempt=attempt + 1,
            total_attempts=total_attempts,
            max_tokens=max_tokens,
            temperature=temperature,
            message_count=len(current_messages),
        )
        try:
            content = provider.chat(
                current_messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
                trace_label=f"blueprint:{label}",
            )
            data = _parse_json(content)
            trace_event(
                "chat_json_success",
                layer="blueprint",
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
                layer="blueprint",
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
                            f"上一次{label}请求没有得到可解析 JSON，错误摘要：{str(exc)[:120]}。"
                            "请重新输出严格 JSON 对象，不要 Markdown，不要解释文字。"
                        ),
                    }
                ]
    raise RuntimeError(f"{label}请求失败：{last_error}")


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
        raise ValueError("LLM 蓝图不是 JSON 对象")
    return data


def _blueprint_from_data(task: GenerationTask, data: dict[str, Any]) -> ProductBlueprint:
    modules_data = data.get("modules")
    if not isinstance(modules_data, list) or len(modules_data) < 4:
        raise ValueError("LLM 蓝图模块数量不足")

    modules: list[FeatureModule] = []
    for index, item in enumerate(modules_data[:8], start=1):
        if not isinstance(item, dict):
            continue
        key = _safe_key(str(item.get("key") or f"module_{index}"))
        title = _clean_text(str(item.get("title") or f"业务模块{index}"), 24)
        description = _clean_text(str(item.get("description") or f"{title}用于业务数据维护和流程处理。"), 220)
        entities = item.get("entities")
        if not isinstance(entities, list):
            entities = [f"Module{index}Record", f"Module{index}Query"]
        safe_entities = [
            _safe_entity(_entity_name_from_item(entity))
            for entity in entities[:4]
            if _entity_name_from_item(entity)
        ]
        safe_entities = _normalize_entities(safe_entities, key, index)
        modules.append(
            FeatureModule(
                key=key,
                title=title,
                description=description,
                entities=safe_entities,
                operations=_clean_list(item.get("operations"), 7, 28),
                data_fields=_clean_list(item.get("data_fields"), 10, 24),
                pages=_clean_list(item.get("pages"), 4, 28),
                rules=_clean_list(item.get("rules"), 5, 80),
            )
        )

    if len(modules) < 4:
        raise ValueError("LLM 蓝图有效模块数量不足")

    roles = data.get("roles")
    if not isinstance(roles, list) or not roles:
        roles = ["系统管理员", "业务操作员", "审核人员", "统计人员"]
    roles = [_clean_text(str(role), 20) for role in roles[:6]]

    pages = data.get("pages")
    if not isinstance(pages, list) or len(pages) < 4:
        pages = ["登录页", "系统首页"] + [module.title for module in modules] + ["统计报表页", "系统设置页"]
    pages = [_clean_text(str(page), 26) for page in pages[:12]]

    industry = _clean_text(str(data.get("industry") or task.product_type), 40)
    scenario = _clean_text(str(data.get("scenario") or f"{industry}业务协同场景"), 120)
    positioning = _clean_text(str(data.get("positioning") or f"面向{scenario}的业务处理软件。"), 180)
    purpose = _clean_text(str(data.get("purpose") or f"用于{industry}场景下的业务管理和数据分析。"), 180)
    summary = _clean_text(str(data.get("summary") or _fallback_summary(task, industry, modules)), 480)
    target_users = _clean_list(data.get("target_users"), 6, 24) or roles
    business_objects = _clean_list(data.get("business_objects"), 12, 28)
    workflows = _clean_workflows(data.get("workflows"))
    report_metrics = _clean_list(data.get("report_metrics"), 12, 32)
    technical_features = _clean_list(data.get("technical_features"), 8, 60)
    quality_rules = _clean_list(data.get("quality_rules"), 10, 90)
    data_relations = _clean_list(data.get("data_relations"), 8, 80)
    deployment_topology = _clean_text(str(data.get("deployment_topology") or ""), 160)
    uniqueness_notes = _clean_list(data.get("uniqueness_notes"), 8, 90)

    fingerprint_source = json.dumps(data, ensure_ascii=False, sort_keys=True) + task.seed
    blueprint = ProductBlueprint(
        software_name=task.software_name,
        version=task.version,
        language=task.language,
        product_type=task.product_type,
        industry=industry,
        purpose=purpose,
        summary=summary,
        modules=modules,
        roles=roles,
        pages=pages,
        dev_environment=_environment_for_language(task.language),
        runtime_environment=_runtime_for_language(task.language),
        scenario=scenario,
        positioning=positioning,
        target_users=target_users,
        business_objects=business_objects,
        workflows=workflows,
        report_metrics=report_metrics,
        technical_features=technical_features,
        quality_rules=quality_rules,
        data_relations=data_relations,
        deployment_topology=deployment_topology,
        uniqueness_notes=uniqueness_notes,
        generation_fingerprint=hashlib.sha256(fingerprint_source.encode("utf-8")).hexdigest()[:16],
    )
    return blueprint


def _temperature(randomness: str) -> float:
    if randomness == "保守":
        return 0.35
    if randomness == "高差异":
        return 0.9
    return 0.65


def _variation_strategy(task: GenerationTask) -> str:
    seed_text = "|".join(
        [
            task.software_name,
            task.product_type,
            task.feature_hint,
            task.randomness,
            task.seed,
        ]
    )
    digest = hashlib.sha256(seed_text.encode("utf-8")).digest()
    product_text = f"{task.software_name} {task.product_type} {task.feature_hint}"
    if _is_music_like_text(product_text):
        return "\n".join(
            [
                "- 产品角度：以用户听歌、找歌、收藏歌单、查看歌词和管理播放偏好为中心。",
                "- 流程重心：重点体现首页推荐、音乐搜索、歌曲详情、播放控制、歌词同步、歌单收藏、最近播放、离线下载和会员音质链路。",
                "- 模块组织：模块标题必须使用音乐领域名词和用户动作，例如“音乐首页推荐”“歌曲播放控制”“歌词同步显示”“歌单收藏管理”“歌手专辑浏览”。",
                "- 数据深度：字段应体现歌曲、歌手、专辑、歌单、播放进度、歌词时间轴、音质、收藏状态、下载状态和会员权益。",
                "- 命名风格：英文 key 使用 song、music、playlist、player、lyric、artist、album、favorite、download 等领域词。",
                "- 避免套路：不要生成点播申请、点播核验、合单、合演、留痕、复核、电子菜单发布、取餐叫号、工单闭环、质量复盘等后台或餐饮模块。",
            ]
        )
    if _is_consumer_app_text(product_text):
        return "\n".join(
            [
                "- 产品角度：以普通用户在手机 App 内的浏览、搜索、使用、收藏、个人设置和会员权益为中心。",
                "- 流程重心：重点体现用户入口、首页推荐、内容详情、核心操作、收藏/下载、使用记录和个人中心链路。",
                "- 模块组织：模块标题必须是用户可见功能，不得写成后台管理、审批流、台账流转或复核追踪。",
                "- 数据深度：字段应体现内容对象、用户偏好、使用进度、收藏状态、下载状态、会员状态和推荐来源。",
                "- 命名风格：英文 key 使用 home、search、detail、favorite、profile、download、history、recommendation 等用户功能词。",
                "- 避免套路：不要生成审核、复核、工单、闭环、台账、留痕、合单、批量输出、质量复盘等后台业务系统模块。",
            ]
        )
    if any(term in product_text for term in ["阅读", "听书", "有声", "小说", "书籍", "图书", "朗读", "书城"]):
        return "\n".join(
            [
                "- 产品角度：以读者的找书、阅读、听书、续播、收藏、订阅和会员权益体验为中心。",
                "- 流程重心：重点体现书城浏览、书籍详情、章节目录、阅读进度、音频播放、书架收藏、离线缓存和推荐续读链路。",
                "- 模块组织：模块标题必须使用阅读听书领域名词和用户动作，例如“书城分类浏览”“书架收藏同步”“听书播放控制”“章节进度续读”。",
                "- 数据深度：字段应体现书籍、章节、作者、主播、播放进度、阅读时长、收藏状态、订阅状态、缓存状态和会员权益。",
                "- 命名风格：英文 key 使用 book、chapter、audio、shelf、playback、reading、subscription、recommendation 等领域词。",
                "- 避免套路：不要生成内容风险预警、复核追踪、批量输出、质量复盘、审批核验、工单闭环、监管处置等后台审核或风控模块。",
            ]
        )
    product_angles = [
        "以一线操作员的高频办理流程为中心，模块按日常任务闭环拆分",
        "以管理者的监管、复核和异常处置为中心，模块按状态流转拆分",
        "以数据采集、校验、归档和追溯为中心，模块按数据生命周期拆分",
        "以多角色协同和跨部门交接为中心，模块按角色责任边界拆分",
        "以移动/现场/边缘场景的快速处理为中心，模块按场景入口拆分",
        "以风险预警、质量控制和复盘分析为中心，模块按风控闭环拆分",
    ]
    workflow_focuses = [
        "重点体现提交、校验、审核、归档和回访/复盘链路",
        "重点体现采集、清洗、匹配、预警和处置闭环",
        "重点体现预约/申请、分派、执行、确认和结算/评价链路",
        "重点体现配置、发布、监控、异常处理和审计追踪链路",
        "重点体现导入、解析、比对、复核和批量输出链路",
        "重点体现计划、执行、反馈、统计和持续改进链路",
    ]
    module_styles = [
        "模块标题优先使用业务名词加动作，例如“课程排课调度”“作业批改追踪”，少用“管理”后缀",
        "模块标题优先使用对象台账加流程结果，例如“风险工单核验”“资源发布留痕”，避免纯名词堆叠",
        "模块边界按页面和角色动作拆开，不把所有对象塞进一个综合管理模块",
        "模块边界按核心对象、异常对象、统计对象分层，避免每个模块都长得一样",
        "模块标题可以使用“看板、调度、复核、归档、追踪、预警、核验、发布”等业务动词",
        "模块之间要形成上下游关系，每个模块至少有一个独有字段、状态或规则",
    ]
    data_depths = [
        "字段要包含编号、状态、责任人、时间、来源、校验结果和处理结论",
        "字段要体现业务对象的生命周期，不只写名称、备注、创建时间",
        "指标要同时包含数量、完成率、异常率、时效和趋势类指标",
        "规则要体现权限范围、状态流转、重复校验、阈值预警和审计留痕",
        "对象要拆成主业务对象、过程记录、异常记录、统计结果和配置规则",
        "示例对象和指标要能直接进入截图表格、说明书段落和源码实体类",
    ]
    naming_styles = [
        "英文 key 使用具体领域词，避免 module_1、business、data、manage",
        "英文实体名使用 Record、Task、Rule、Trace、Summary、Snapshot 等后缀区分职责",
        "页面名称使用业务入口名，例如“课程编排台”“异常复核页”，避免全部叫列表页",
        "操作名使用领域动作，例如核验、派发、批改、发布、归档、回溯、同步、结算",
        "状态名要贴近业务，如待复核、已派发、处理中、待归档、异常退回、已闭环",
        "统计指标名称要像产品首页真实指标，不使用“数据量、业务量、完成量”空泛词",
    ]
    avoidances = [
        "不要把模块固定成登录、首页、数据管理、统计分析、权限管理",
        "不要让所有模块操作都是新增、编辑、删除、查询、导出",
        "不要让所有字段都是名称、编号、状态、备注、创建时间",
        "不要让流程只停留在提交、审核、完成三步",
        "不要在不同模块重复同一套规则句式",
        "不要把软件写成任何行业都能套用的通用后台",
    ]

    def pick(items: list[str], offset: int) -> str:
        return items[digest[offset] % len(items)]

    lines = [
        f"- 产品角度：{pick(product_angles, 0)}",
        f"- 流程重心：{pick(workflow_focuses, 1)}",
        f"- 模块组织：{pick(module_styles, 2)}",
        f"- 数据深度：{pick(data_depths, 3)}",
        f"- 命名风格：{pick(naming_styles, 4)}",
        f"- 避免套路：{pick(avoidances, 5)}",
    ]
    if task.randomness == "高差异":
        lines.append("- 高差异要求：允许采用更细的模块边界和更有行业特征的页面名称，但不能偏离软件名称和业务补充。")
    elif task.randomness == "保守":
        lines.append("- 保守要求：保持常规业务系统结构，但模块标题、字段、流程和指标仍必须体现具体行业差异。")
    return "\n".join(lines)


def _safe_key(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_]+", "_", value).strip("_").lower()
    return value or "business"


def _safe_entity(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", " ", value)
    parts = [part for part in value.split() if part]
    entity = "".join(part[:1].upper() + part[1:] for part in parts)
    return entity or "BusinessRecord"


def _entity_name_from_item(item: Any) -> str:
    if isinstance(item, dict):
        for key in ("entity", "className", "class_name", "name", "title", "value", "text"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return ""
    return str(item).strip()


def _normalize_entities(entities: list[str], key: str, index: int) -> list[str]:
    base = _entity_base_from_key(key) or f"Module{index}"
    cleaned: list[str] = []
    for entity in entities:
        if not entity or entity == "BusinessRecord" or entity in cleaned:
            continue
        cleaned.append(entity)
    while len(cleaned) < 2:
        suffix = "Record" if len(cleaned) == 0 else "Query"
        candidate = f"{base}{suffix}"
        if candidate not in cleaned:
            cleaned.append(candidate)
        else:
            cleaned.append(f"{base}Detail")
    return cleaned[:4]


def _entity_base_from_key(key: str) -> str:
    parts = [part for part in re.split(r"[_\W]+", key) if part]
    return "".join(part[:1].upper() + part[1:] for part in parts)


def _clean_list(value: Any, max_count: int, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value[:max_count]:
        text = _clean_text(_string_from_list_item(item), limit)
        if text and text not in result:
            result.append(text)
    return result


def _string_from_list_item(item: Any) -> str:
    if isinstance(item, dict):
        for key in ("name", "title", "operation", "field", "rule", "label", "value", "text"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value
        for value in item.values():
            if isinstance(value, str) and value.strip():
                return value
        return ""
    return str(item)


def _clean_workflows(value: Any) -> list[dict[str, list[str] | str]]:
    if not isinstance(value, list):
        return []
    workflows: list[dict[str, list[str] | str]] = []
    for index, item in enumerate(value[:5], start=1):
        if not isinstance(item, dict):
            continue
        steps = _clean_list(item.get("steps"), 7, 32)
        if len(steps) < 3:
            steps = ["创建记录", "字段校验", "提交处理", "生成结果"]
        workflows.append(
            {
                "name": _clean_text(str(item.get("name") or f"业务流程{index}"), 36),
                "trigger": _clean_text(str(item.get("trigger") or "用户提交业务记录"), 80),
                "steps": steps,
                "output": _clean_text(str(item.get("output") or "形成处理结果和操作日志"), 90),
            }
        )
    return workflows


def _clean_text(value: str, limit: int) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    return value[:limit]


def _fallback_summary(task: GenerationTask, industry: str, modules: list[FeatureModule]) -> str:
    titles = "、".join(module.title for module in modules[:4])
    return f"{task.software_name}是一套面向{industry}的{task.product_type}，围绕{titles}等模块提供业务管理、流程协同、统计分析和权限审计能力。"


def _quality_review(task: GenerationTask, blueprint: ProductBlueprint) -> tuple[int, list[str]]:
    score = 100
    reasons: list[str] = []
    generic_words = ["业务管理", "数据维护", "流程处理", "统计分析", "系统配置", "通用", "管理列表", "基础档案", "数据管理", "信息管理"]
    generic_keys = {"module", "module_1", "module_2", "business", "data", "manage", "management", "system", "common"}
    generic_operations = {"新增", "编辑", "删除", "查询", "导出", "新增记录", "编辑记录", "删除记录", "查询记录", "导出数据"}
    generic_fields = {"名称", "编号", "状态", "备注", "创建时间", "更新时间", "创建人", "修改人"}
    action_words = [
        "审核",
        "复核",
        "发布",
        "归档",
        "预警",
        "调度",
        "派单",
        "核验",
        "结算",
        "采集",
        "训练",
        "诊疗",
        "排班",
        "核销",
        "同步",
        "推送",
        "批改",
        "闭环",
        "回溯",
        "确认",
        "配置",
    ]
    action_words.extend(_domain_action_words(task))
    domain_terms = _domain_terms(task)
    off_domain_terms = _off_domain_terms(task)

    if len(blueprint.summary) < 180:
        score -= 12
        reasons.append("summary 过短，无法支撑真实说明书")
    if len(blueprint.business_objects) < 6:
        score -= 12
        reasons.append("business_objects 少于 6 个，业务对象不足")
    if len(blueprint.workflows) < 3:
        score -= 10
        reasons.append("workflows 少于 3 个，业务流程不足")
    if len(blueprint.report_metrics) < 6:
        score -= 8
        reasons.append("report_metrics 少于 6 个，统计指标不足")
    if len(blueprint.quality_rules) < 5:
        score -= 8
        reasons.append("quality_rules 少于 5 条，校验/权限/审计规则不足")
    if len(blueprint.uniqueness_notes) < 4:
        score -= 8
        reasons.append("uniqueness_notes 少于 4 条，差异化说明不足")

    module_titles = [module.title for module in blueprint.modules]
    if len(set(module_titles)) != len(module_titles):
        score -= 10
        reasons.append("模块标题存在重复")
    generic_module_count = sum(1 for module in blueprint.modules if any(word == module.title or word in module.title for word in generic_words))
    if generic_module_count >= 2:
        score -= 12
        reasons.append("模块标题过于通用")
    generic_key_count = sum(1 for module in blueprint.modules if module.key in generic_keys or re.fullmatch(r"module_\d+", module.key or ""))
    if generic_key_count >= 2:
        score -= 8
        reasons.append("多个模块 key 仍是泛型命名")
    domain_miss_count = 0
    off_domain_module_count = 0
    for module in blueprint.modules:
        module_text = json.dumps(
            {
                "key": module.key,
                "title": module.title,
                "description": module.description,
                "operations": module.operations,
                "data_fields": module.data_fields,
                "pages": module.pages,
                "rules": module.rules,
            },
            ensure_ascii=False,
        )
        if domain_terms and not _contains_any(module_text, domain_terms):
            domain_miss_count += 1
        if off_domain_terms and _contains_any(module_text, off_domain_terms):
            off_domain_module_count += 1
    if domain_terms and domain_miss_count >= max(1, len(blueprint.modules) // 3):
        score -= 18
        reasons.append("多个模块未命中软件领域词，存在领域偏移")
    if off_domain_module_count:
        score -= min(30, 15 + off_domain_module_count * 5)
        reasons.append("模块出现与软件领域不匹配的后台/审核/风控词")
    weak_description_count = sum(
        1
        for module in blueprint.modules
        if len(module.description) < 45 or not any(word in module.description for word in action_words)
    )
    if weak_description_count >= 2:
        score -= 12
        reasons.append("多个模块描述缺少具体业务动作")
    generic_operation_modules = sum(
        1
        for module in blueprint.modules
        if len(set(module.operations) - generic_operations) < 3
    )
    if generic_operation_modules >= 2:
        score -= 10
        reasons.append("多个模块操作仍停留在新增/编辑/删除/查询/导出")
    generic_field_modules = sum(
        1
        for module in blueprint.modules
        if len(set(module.data_fields) - generic_fields) < 4
    )
    if generic_field_modules >= 2:
        score -= 8
        reasons.append("多个模块字段过于通用，缺少行业字段")

    feature_terms = [term for term in re.split(r"[，,、\s]+", task.feature_hint) if len(term) >= 2]
    if feature_terms:
        joined = json.dumps(blueprint.to_dict(), ensure_ascii=False)
        hit_count = sum(1 for term in feature_terms if term in joined)
        if hit_count < max(1, min(3, len(feature_terms))):
            score -= 10
            reasons.append("产品方案与业务补充关键词关联不足")

    joined_plan = json.dumps(blueprint.to_dict(), ensure_ascii=False)
    contract_keywords = _contract_keywords(task)
    if contract_keywords:
        contract_hit_count = sum(1 for term in contract_keywords[:16] if term in joined_plan)
        required_hits = max(3, min(7, len(contract_keywords[:16]) // 2))
        if contract_hit_count < required_hits:
            score -= 24
            reasons.append(f"产品方案未充分履行名称理解契约，关键词命中 {contract_hit_count}/{required_hits}")
    contract_avoid_hits = [term for term in _contract_avoid_terms(task) if term in joined_plan]
    if contract_avoid_hits:
        score -= min(40, 18 + len(contract_avoid_hits) * 4)
        reasons.append(f"产品方案违背名称理解契约，包含应避免方向：{'、'.join(contract_avoid_hits[:8])}")
    if sum(1 for word in generic_words if word in joined_plan) >= 8:
        score -= 6
        reasons.append("方案中泛型后台表达偏多")
    off_domain_hits = [term for term in off_domain_terms if term in joined_plan]
    if off_domain_hits:
        score -= min(25, 10 + len(off_domain_hits) * 3)
        reasons.append(f"方案包含偏离软件领域的词：{'、'.join(off_domain_hits[:6])}")

    if not blueprint.scenario or len(blueprint.scenario) < 12:
        score -= 8
        reasons.append("scenario 不够具体")
    if not blueprint.deployment_topology:
        score -= 5
        reasons.append("缺少部署拓扑说明")

    return max(score, 0), reasons
