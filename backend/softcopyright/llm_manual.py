from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import json
import os
import re
import time
from typing import Any

from .blueprint import ProductBlueprint
from .errors import sanitize_error_message
from .llm.provider import LLMProvider, LocalTemplateProvider, TextErrorCategory, TextProviderError, TextRetryPolicy
from .llm.trace import trace_event
from .llm.json_response import parse_json_object
from .models import GenerationTask


def generate_manual_content_with_llm(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    provider: LLMProvider | None,
    emit=None,
    initial_content: dict[str, Any] | None = None,
    save_progress=None,
) -> dict[str, Any] | None:
    if provider is None or isinstance(provider, LocalTemplateProvider):
        return None

    result: dict[str, Any] = {**(initial_content or {}), "modules": dict((initial_content or {}).get("modules") or {})}
    warnings: list[str] = []

    batch_size = 1 if _authenticity_first(task) else 2
    section_batches = list(_chunks([spec for spec in _section_specs() if not result.get(spec[0])], batch_size))
    module_batches = list(_chunks([module for module in blueprint.modules if module.key not in result["modules"]], batch_size))
    workers = 1 if _authenticity_first(task) else _llm_batch_workers()
    jobs = [
        ("section", index, specs) for index, specs in enumerate(section_batches, start=1)
    ] + [
        ("module", index, modules) for index, modules in enumerate(module_batches, start=1)
    ]
    missing_sections = []
    missing_modules = []
    # Both kinds are independent. One bounded queue lets module work start while
    # a slower common-section request is still running. Only the main thread
    # merges results and saves checkpoints.
    executor = ThreadPoolExecutor(max_workers=min(workers, len(jobs) or 1))
    futures = {}
    next_job = 0
    completed_jobs = 0
    try:
        while next_job < len(jobs) or futures:
            while next_job < len(jobs) and len(futures) < workers:
                kind, index, items = jobs[next_job]
                next_job += 1
                fn = _generate_section_batch if kind == "section" else _generate_module_batch
                futures[executor.submit(fn, task, blueprint, provider, items)] = (kind, index, items)
            completed, _ = wait(tuple(futures), return_when=FIRST_COMPLETED)
            # Save successful peers even if this completion set also contains
            # a fatal error, then stop before submitting any more work.
            fatal_error = None
            for future in completed:
                kind, index, items = futures.pop(future)
                error = ""
                try:
                    data = future.result()
                except Exception as exc:
                    if _fatal_provider_error(exc):
                        fatal_error = exc
                        continue
                    data = {}
                    error = f"批次请求失败：{sanitize_error_message(exc)}"
                if kind == "section":
                    for spec in items:
                        key, _title, _hint, min_count, _budget, limit = spec
                        paragraphs = _section_paragraphs_from_data(data, key, min_count, limit)
                        if paragraphs:
                            result[key] = paragraphs
                        else:
                            missing_sections.append((spec, error or "模型生成有效段落不足"))
                else:
                    for module in items:
                        content = _module_content_from_data(data, module)
                        if content:
                            result["modules"][module.key] = content
                        else:
                            missing_modules.append((module, error or "模型生成有效段落不足"))
                completed_jobs += 1
                _emit(emit, 24 + int(6 * completed_jobs / max(len(jobs), 1)),
                      f"说明书章节批次完成 {completed_jobs}/{len(jobs)}")
                if save_progress:
                    save_progress(result)
            if fatal_error is not None:
                raise fatal_error
    finally:
        for future in futures:
            future.cancel()
        executor.shutdown(wait=True, cancel_futures=True)

    _retry_missing_sections(task, blueprint, provider, missing_sections, result, warnings, emit, save_progress)
    _retry_missing_modules(task, blueprint, provider, missing_modules, result, warnings, emit, save_progress)

    generated_section_count = sum(1 for key, *_rest in _section_specs() if result.get(key))
    generated_module_count = len(result["modules"])
    if generated_section_count == 0 and generated_module_count < 2:
        raise ValueError("LLM 说明书分段生成有效内容不足")

    if warnings:
        result["_warnings"] = warnings
    return result


def _generate_manual_content_with_llm_sequential(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    provider: LLMProvider,
    emit=None,
) -> dict[str, Any]:
    result: dict[str, Any] = {"modules": {}}
    warnings: list[str] = []

    batch_size = 1 if _authenticity_first(task) else 2
    section_batches = list(_chunks(_section_specs(), batch_size))
    for batch_index, specs in enumerate(section_batches, start=1):
        _emit(emit, 24 + batch_index, f"生成说明书公共章节 {batch_index}/{len(section_batches)}")
        try:
            batch_data = _generate_section_batch(
                task=task,
                blueprint=blueprint,
                provider=provider,
                specs=specs,
            )
        except Exception as exc:
            _retry_missing_sections(
                task,
                blueprint,
                provider,
                [(spec, f"批次请求失败：{sanitize_error_message(exc)}") for spec in specs],
                result,
                warnings,
                emit,
            )
            continue
        for key, title, _count_hint, min_count, _max_tokens, limit in specs:
            paragraphs = _section_paragraphs_from_data(batch_data, key, min_count, limit)
            if paragraphs:
                result[key] = paragraphs
            else:
                _retry_missing_sections(
                    task,
                    blueprint,
                    provider,
                    [((key, title, _count_hint, min_count, _max_tokens, limit), "模型生成有效段落不足")],
                    result,
                    warnings,
                    emit,
                )

    module_batches = list(_chunks(blueprint.modules, batch_size))
    for batch_index, modules in enumerate(module_batches, start=1):
        _emit(emit, 27 + batch_index, f"生成说明书模块章节 {batch_index}/{len(module_batches)}")
        try:
            batch_data = _generate_module_batch(task, blueprint, provider, modules)
        except Exception as exc:
            _retry_missing_modules(
                task,
                blueprint,
                provider,
                [(module, f"批次请求失败：{sanitize_error_message(exc)}") for module in modules],
                result,
                warnings,
                emit,
            )
            continue
        for module in modules:
            module_content = _module_content_from_data(batch_data, module)
            if module_content:
                result["modules"][module.key] = module_content
            else:
                _retry_missing_modules(
                    task,
                    blueprint,
                    provider,
                    [(module, "模型生成有效段落不足")],
                    result,
                    warnings,
                    emit,
                )

    generated_section_count = sum(1 for key, *_rest in _section_specs() if result.get(key))
    generated_module_count = len(result["modules"])
    if generated_section_count == 0 and generated_module_count < 2:
        raise ValueError("LLM 说明书分段生成有效内容不足")

    if warnings:
        result["_warnings"] = warnings
    return result


def _emit(emit, progress: int, message: str, **extra) -> None:
    if emit:
        emit(progress, message, **extra)


def _retry_missing_sections(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    provider: LLMProvider,
    missing_sections: list[tuple[tuple[str, str, str, int, int, int], str]],
    result: dict[str, Any],
    warnings: list[str],
    emit=None,
    save_progress=None,
) -> None:
    seen: set[str] = set()
    for spec, reason in missing_sections:
        key, title, count_hint, min_count, max_tokens, limit = spec
        if result.get(key) or key in seen:
            continue
        seen.add(key)
        _emit(emit, 30, f"拆分重试说明书公共章节：{title}", material_type="GPT 拆分重试")
        try:
            paragraphs = _generate_section(task, blueprint, provider, key, title, count_hint, min_count, max_tokens, limit)
            if paragraphs:
                result[key] = paragraphs
        except Exception as exc:
            if _fatal_provider_error(exc):
                raise
            reason = f"{reason}；拆分重试失败：{sanitize_error_message(exc)}"
        if result.get(key):
            if save_progress:
                save_progress(result)
            continue
        warnings.append(f"{title}模型生成失败，需重试：{sanitize_error_message(reason)}")


def _retry_missing_modules(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    provider: LLMProvider,
    missing_modules: list[tuple[Any, str]],
    result: dict[str, Any],
    warnings: list[str],
    emit=None,
    save_progress=None,
) -> None:
    seen: set[str] = set()
    modules_result = result.setdefault("modules", {})
    for module, reason in missing_modules:
        module_key = str(getattr(module, "key", "") or "")
        module_title = str(getattr(module, "title", "") or module_key or "功能模块")
        if not module_key or module_key in modules_result or module_key in seen:
            continue
        seen.add(module_key)
        _emit(emit, 31, f"拆分重试说明书模块章节：{module_title}", material_type="GPT 拆分重试")
        try:
            module_content = _generate_module_section(task, blueprint, provider, module)
            if module_content:
                modules_result[module_key] = module_content
        except Exception as exc:
            if _fatal_provider_error(exc):
                raise
            reason = f"{reason}；拆分重试失败：{sanitize_error_message(exc)}"
        if module_key in modules_result:
            if save_progress:
                save_progress(result)
            continue
        warnings.append(f"{module_title}模型生成失败，需重试：{sanitize_error_message(reason)}")


def _chunks(items, size: int):
    items = list(items)
    for index in range(0, len(items), size):
        yield items[index : index + size]


def _fatal_provider_error(exc: Exception) -> bool:
    return isinstance(exc, TextProviderError) and exc.category in {
        TextErrorCategory.CONFIGURATION, TextErrorCategory.CANCELLED,
    }


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


def _section_specs() -> list[tuple[str, str, str, int, int, int]]:
    return [
        ("overview", "软件概述", "2-3个段落", 2, 850, 150),
        ("login_main", "登录与主界面", "2-3个段落", 2, 850, 150),
        ("statistics", "统计分析", "2-3个段落", 2, 850, 150),
        ("security", "权限与安全", "2-3个段落", 2, 850, 150),
        ("faq", "常见问题处理", "3个段落", 2, 700, 130),
    ]


def _generate_section_batch(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    provider: LLMProvider,
    specs: list[tuple[str, str, str, int, int, int]],
) -> dict[str, Any]:
    sections = [
        {
            "key": key,
            "title": title,
            "count_hint": count_hint,
            "min_count": min_count,
        }
        for key, title, count_hint, min_count, _max_tokens, _limit in specs
    ]
    content = _chat_json(
        provider,
        [
            {"role": "system", "content": _system_prompt()},
            {
                "role": "user",
                "content": f"""
请为《{task.software_name}软件说明书》生成本批公共章节正文。

{_build_context(task, blueprint)}

本批章节：
{json.dumps(sections, ensure_ascii=False, indent=2)}

要求：
- 每个章节按 count_hint 生成段落，至少达到 min_count
- 段落写成真实软件用户手册口吻，像人工编写的操作指南，描述具体入口、页面、数据项、按钮和保存后的变化
- 每段控制在 80-140 个中文字符，避免长报告式堆叠
- 内容必须贴合产品方案中的具体场景、业务对象、流程、指标和规则
- 不要只写通用后台能力，每段至少包含一个具体业务对象、页面、指标、状态或操作
- 不要使用“操作说明：”“字段说明：”“处理结果：”“业务一致性：”“界面说明：”这类固定标签
- 避免每章都重复“登记、校验、分析、确认”的同一组动作，按当前模块实际 operations 改写
- 不要出现“AI”“模板”“示例”“假设”等字样
- 不要写申请主体、公司名称、联系人、费用、包过承诺
- 只返回 JSON

返回 JSON 格式：
{{"sections":{{"overview":["段落1"],"login_main":["段落1"]}}}}
""".strip(),
            },
        ],
        temperature=_temperature(task.randomness),
        max_tokens=min(sum(max_tokens for *_prefix, max_tokens, _limit in specs), 2800),
        label="说明书公共章节批次",
    )
    return content


def _section_paragraphs_from_data(data: dict[str, Any], key: str, min_count: int, limit: int) -> list[str]:
    value: Any = None
    sections = data.get("sections")
    if isinstance(sections, dict):
        value = sections.get(key)
    if value is None:
        value = data.get(key)
    if isinstance(value, dict):
        value = value.get("paragraphs")
    return _paragraphs(value, min_count=min_count, limit=limit)


def _generate_section(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    provider: LLMProvider,
    key: str,
    title: str,
    count_hint: str,
    min_count: int,
    max_tokens: int,
    limit: int,
) -> list[str]:
    messages = [
        {
            "role": "system",
            "content": _system_prompt(),
        },
        {
            "role": "user",
            "content": f"""
请为《{task.software_name}软件说明书》生成“{title}”章节正文。

{_build_context(task, blueprint)}

章节要求：
- 生成 {count_hint}
- 段落写成真实软件用户手册口吻，像人工编写的操作指南，描述具体入口、页面、数据项、按钮和保存后的变化
- 每段控制在 80-140 个中文字符，避免长报告式堆叠
- 内容必须贴合产品方案中的具体场景、业务对象、流程、指标和规则
- 不要只写通用后台能力，每段至少包含一个具体业务对象、页面、指标、状态或操作
- 不要使用“操作说明：”“字段说明：”“处理结果：”“业务一致性：”“界面说明：”这类固定标签
- 避免每章都重复“登记、校验、分析、确认”的同一组动作，按当前章节实际业务改写
- 只返回 JSON，格式为：{{"paragraphs":["段落1","段落2"]}}

禁止：
- 不要出现“AI”“模板”“示例”“假设”等字样
- 不要写申请主体、公司名称、联系人、费用、包过承诺
""".strip(),
        },
    ]
    data = _chat_json(
        provider,
        messages,
        temperature=_temperature(task.randomness),
        max_tokens=max_tokens,
        label=title,
    )
    paragraphs = _paragraphs(data.get("paragraphs"), min_count=min_count, limit=limit)
    if not paragraphs:
        raise ValueError(f"{title}有效段落不足")
    return paragraphs


def _generate_module_batch(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    provider: LLMProvider,
    modules,
) -> dict[str, Any]:
    module_payload = [
        {
            "key": module.key,
            "title": module.title,
            "description": module.description,
            "entities": module.entities,
            "operations": module.operations or [],
            "data_fields": module.data_fields or [],
            "pages": module.pages or [],
            "rules": module.rules or [],
        }
        for module in modules
    ]
    return _chat_json(
        provider,
        [
            {"role": "system", "content": _system_prompt()},
            {
                "role": "user",
                "content": f"""
请为《{task.software_name}软件说明书》的本批功能模块生成正文。

{_build_module_context(task, blueprint)}

本批模块：
{json.dumps(module_payload, ensure_ascii=False, indent=2)}

返回 JSON 字段：
- modules: 对象，key 为模块 key，值包含 title 和 paragraphs
- 每个模块 paragraphs 生成 2-3 个段落，说明入口、查询、新增、编辑、审核、导出、日志、校验、权限联动等操作

要求：
- 每个模块内容必须只围绕该模块展开
- 必须使用该模块的 operations、data_fields、pages、rules 中的具体词语
- 段落写成真实软件用户手册口吻，像人工编写的模块使用指南
- 每段控制在 80-140 个中文字符，避免长报告式堆叠
- 不要使用“操作说明：”“字段说明：”“处理结果：”“业务一致性：”“界面说明：”这类固定标签
- 不要把所有模块都写成同一套“查询、新增、编辑、审核、导出、日志、校验、权限联动”；应按当前模块 operations 选择不同动作顺序和句式
- 不要出现“AI”“模板”“示例”“假设”等字样
- 不要写申请主体、公司名称、联系人、费用、包过承诺
- 只返回 JSON

返回 JSON 示例：
{{"modules":{{"course_resource":{{"title":"课程资源管理","paragraphs":["段落1"]}}}}}}
""".strip(),
            },
        ],
        temperature=_temperature(task.randomness),
        max_tokens=3600,
        label="说明书模块章节批次",
    )


def _module_content_from_data(data: dict[str, Any], module) -> dict[str, Any] | None:
    value: Any = None
    modules = data.get("modules")
    if isinstance(modules, dict):
        value = modules.get(module.key)
    elif isinstance(modules, list):
        for item in modules:
            if isinstance(item, dict) and str(item.get("key") or "") == module.key:
                value = item
                break
    if value is None:
        value = data.get(module.key)
    if not isinstance(value, dict):
        return None
    paragraphs = _paragraphs(value.get("paragraphs"), min_count=2, limit=150)
    if not paragraphs:
        return None
    return {
        "title": module.title,
        "paragraphs": paragraphs,
    }


def _generate_module_section(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    provider: LLMProvider,
    module,
) -> dict[str, Any] | None:
    messages = [
        {
            "role": "system",
            "content": _system_prompt(),
        },
        {
            "role": "user",
            "content": f"""
请为《{task.software_name}软件说明书》的功能模块章节生成正文。

{_build_module_context(task, blueprint)}

当前模块：
- key: {module.key}
- title: {module.title}
- description: {module.description}
- entities: {", ".join(module.entities)}
- operations: {", ".join(module.operations or [])}
- data_fields: {", ".join(module.data_fields or [])}
- pages: {", ".join(module.pages or [])}
- rules: {"；".join(module.rules or [])}

返回 JSON 字段：
- key: 必须为 "{module.key}"
- title: 模块中文标题
- paragraphs: 2-3个段落，说明入口、查询、新增、编辑、审核、导出、日志、校验、权限联动等操作

要求：
- 内容必须只围绕当前模块展开
- 必须使用当前模块的 operations、data_fields、pages、rules 中的具体词语
- 段落写成真实软件用户手册口吻，像人工编写的模块使用指南
- 每段控制在 80-140 个中文字符，避免长报告式堆叠
- 不要使用“操作说明：”“字段说明：”“处理结果：”“业务一致性：”“界面说明：”这类固定标签
- 不要把所有模块都写成同一套“查询、新增、编辑、审核、导出、日志、校验、权限联动”；应按当前模块 operations 选择不同动作顺序和句式
- 不要出现“AI”“模板”“示例”“假设”等字样
- 不要写申请主体、公司名称、联系人、费用、包过承诺
- 只返回 JSON
""".strip(),
        },
    ]
    data = _chat_json(
        provider,
        messages,
        temperature=_temperature(task.randomness),
        max_tokens=2200,
        label=module.title,
    )
    paragraphs = _paragraphs(data.get("paragraphs"), min_count=2, limit=150)
    if not paragraphs:
        raise ValueError("模块有效段落不足")
    return {
        "title": module.title,
        "paragraphs": paragraphs,
    }


def _build_context(task: GenerationTask, blueprint: ProductBlueprint) -> str:
    modules = "\n".join(
        f"- {module.title}：{module.description}；操作：{'、'.join(module.operations[:5]) or '查询、保存、审核'}；字段：{'、'.join(module.data_fields[:6]) or '编码、名称、状态'}"
        for module in blueprint.modules
    )
    workflows = "\n".join(
        f"- {item.get('name', '业务流程')}：{item.get('trigger', '')}；步骤：{'、'.join(item.get('steps', []))}；输出：{item.get('output', '')}"
        for item in blueprint.workflows[:5]
        if isinstance(item, dict)
    )
    return f"""
基础信息：
- 软件全称：{task.software_name}
- 版本号：{task.version}
- 编程语言：{task.language}
- 产品类型：{task.product_type}
- 行业领域：{blueprint.industry}
- 具体场景：{blueprint.scenario or "未提供"}
- 产品定位：{blueprint.positioning or "未提供"}
- 开发目的：{blueprint.purpose}
- 软件概述：{blueprint.summary}
- 业务补充：{task.feature_hint or "无"}
- 目标用户：{"、".join(blueprint.target_users or blueprint.roles)}
- 核心业务对象：{"、".join(blueprint.business_objects[:12])}
- 统计指标：{"、".join(blueprint.report_metrics[:12])}
- 技术特点：{"、".join(blueprint.technical_features[:8])}
- 质量规则：{"；".join(blueprint.quality_rules[:8])}
- 数据关系：{"；".join(blueprint.data_relations[:6])}
- 部署拓扑：{blueprint.deployment_topology or "未提供"}

功能模块：
{modules}

业务流程：
{workflows or "无"}
""".strip()


def _build_module_context(task: GenerationTask, blueprint: ProductBlueprint) -> str:
    return f"""
软件：{task.software_name}（{task.version}）
行业与场景：{blueprint.industry}；{blueprint.scenario or blueprint.positioning}
目标用户：{"、".join((blueprint.target_users or blueprint.roles)[:5])}
业务对象：{"、".join(blueprint.business_objects[:8])}
业务补充：{(task.feature_hint or "无")[:300]}
""".strip()


def _system_prompt() -> str:
    return (
        "你是中文软件著作权软件说明书撰写专家。请根据产品蓝图生成可直接写入 Word 的说明书正文。"
        "文字应接近客户提交材料中的传统用户手册，不要写成模板字段说明，也不要出现内部生成流程。"
        "只返回 JSON，不要返回 Markdown，不要编造申请主体信息，不要承诺包过。"
    )


def _parse_json(content: str) -> dict[str, Any]:
    cleaned = str(content or "").strip()
    if len(cleaned) < 2:
        raise ValueError("模型返回内容为空或被截断，未收到完整 JSON")
    try:
        return parse_json_object(cleaned, label="manual")
    except json.JSONDecodeError as exc:
        raise ValueError(f"模型返回不完整或无效 JSON（{len(cleaned)} 字符，第 {exc.lineno} 行，第 {exc.colno} 列）") from exc


def _chat_json(
    provider: LLMProvider,
    messages: list[dict[str, str]],
    *,
    temperature: float,
    max_tokens: int,
    label: str,
    attempts: int = 2,
) -> dict[str, Any]:
    last_error: Exception | None = None
    current_messages = messages
    total_attempts = max(1, min(2, attempts))
    for attempt in range(total_attempts):
        started_at = time.perf_counter()
        trace_event(
            "chat_json_begin",
            layer="manual",
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
                trace_label=f"manual:{label}",
                retry_policy=TextRetryPolicy(max_retries=1),
            )
            data = _parse_json(content)
            trace_event(
                "chat_json_success",
                layer="manual",
                label=label,
                attempt=attempt + 1,
                elapsed_seconds=round(time.perf_counter() - started_at, 3),
                content_chars=len(content or ""),
            )
            return data
        except Exception as exc:
            if isinstance(exc, TextProviderError) and exc.category != TextErrorCategory.FORMAT:
                raise
            last_error = exc
            safe_error = sanitize_error_message(exc, limit=500)
            trace_event(
                "chat_json_error",
                layer="manual",
                label=label,
                attempt=attempt + 1,
                elapsed_seconds=round(time.perf_counter() - started_at, 3),
                error_type=type(exc).__name__,
                error=safe_error,
            )
            if attempt < total_attempts - 1:
                current_messages = messages + [
                    {
                        "role": "user",
                        "content": (
                            f"上一次{label}没有得到可解析 JSON，错误摘要：{sanitize_error_message(exc, limit=120)}。"
                            "请重新输出严格 JSON 对象，不要 Markdown，不要解释文字。"
                        ),
                    }
                ]
    raise RuntimeError(f"{label}请求失败：{sanitize_error_message(last_error)}")


def _paragraphs(value: Any, min_count: int, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    result = []
    blocked = ("AI", "模板", "示例", "假设", "包过")
    for item in value:
        text = _clean_text(str(item), limit)
        if not text or any(word in text for word in blocked):
            continue
        result.append(text)
    if len(result) < min_count:
        return []
    return result


def _temperature(randomness: str) -> float:
    if randomness == "保守":
        return 0.35
    if randomness == "高差异":
        return 0.85
    return 0.6


def _clean_text(value: str, limit: int) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    return value[:limit]
