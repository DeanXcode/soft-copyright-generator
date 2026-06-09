from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import re
import time
from typing import Any

from .blueprint import ProductBlueprint
from .llm.provider import LLMProvider, LocalTemplateProvider
from .llm.trace import trace_event
from .models import GenerationTask


def generate_manual_content_with_llm(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    provider: LLMProvider | None,
    emit=None,
) -> dict[str, Any] | None:
    if provider is None or isinstance(provider, LocalTemplateProvider):
        return None

    result: dict[str, Any] = {"modules": {}}
    warnings: list[str] = []

    batch_size = 1 if _authenticity_first(task) else 2
    section_batches = list(_chunks(_section_specs(), batch_size))
    section_results: dict[int, dict[str, Any]] = {}
    workers = 1 if _authenticity_first(task) else _llm_batch_workers()
    with ThreadPoolExecutor(max_workers=min(workers, len(section_batches) or 1)) as executor:
        futures = {}
        for batch_index, specs in enumerate(section_batches, start=1):
            _emit(emit, 24 + batch_index, f"生成说明书公共章节 {batch_index}/{len(section_batches)}")
            futures[executor.submit(_generate_section_batch, task, blueprint, provider, specs)] = (batch_index, specs)
        for future in as_completed(futures):
            batch_index, specs = futures[future]
            try:
                section_results[batch_index] = future.result()
            except Exception as exc:
                titles = "、".join(title for _key, title, *_rest in specs)
                warnings.append(f"{titles}模型生成失败，已由本地模板补齐：{exc}")

    for batch_index, specs in enumerate(section_batches, start=1):
        batch_data = section_results.get(batch_index)
        if not batch_data:
            continue
        for key, title, _count_hint, min_count, _max_tokens, limit in specs:
            paragraphs = _section_paragraphs_from_data(batch_data, key, min_count, limit)
            if paragraphs:
                result[key] = paragraphs
            else:
                warnings.append(f"{title}模型生成有效段落不足，已由本地模板补齐")

    module_batches = list(_chunks(blueprint.modules, batch_size))
    module_results: dict[int, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=min(workers, len(module_batches) or 1)) as executor:
        futures = {}
        for batch_index, modules in enumerate(module_batches, start=1):
            _emit(emit, 27 + batch_index, f"生成说明书模块章节 {batch_index}/{len(module_batches)}")
            futures[executor.submit(_generate_module_batch, task, blueprint, provider, modules)] = (batch_index, modules)
        for future in as_completed(futures):
            batch_index, modules = futures[future]
            try:
                module_results[batch_index] = future.result()
            except Exception as exc:
                titles = "、".join(module.title for module in modules)
                warnings.append(f"{titles}模型生成失败，已由本地模板补齐：{exc}")

    for batch_index, modules in enumerate(module_batches, start=1):
        batch_data = module_results.get(batch_index)
        if not batch_data:
            continue
        for module in modules:
            module_content = _module_content_from_data(batch_data, module)
            if module_content:
                result["modules"][module.key] = module_content
            else:
                warnings.append(f"{module.title}模型生成有效段落不足，已由本地模板补齐")

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
            titles = "、".join(title for _key, title, *_rest in specs)
            warnings.append(f"{titles}模型生成失败，已由本地模板补齐：{exc}")
            continue
        for key, title, _count_hint, min_count, _max_tokens, limit in specs:
            paragraphs = _section_paragraphs_from_data(batch_data, key, min_count, limit)
            if paragraphs:
                result[key] = paragraphs
            else:
                warnings.append(f"{title}模型生成有效段落不足，已由本地模板补齐")

    module_batches = list(_chunks(blueprint.modules, batch_size))
    for batch_index, modules in enumerate(module_batches, start=1):
        _emit(emit, 27 + batch_index, f"生成说明书模块章节 {batch_index}/{len(module_batches)}")
        try:
            batch_data = _generate_module_batch(task, blueprint, provider, modules)
        except Exception as exc:
            titles = "、".join(module.title for module in modules)
            warnings.append(f"{titles}模型生成失败，已由本地模板补齐：{exc}")
            continue
        for module in modules:
            module_content = _module_content_from_data(batch_data, module)
            if module_content:
                result["modules"][module.key] = module_content
            else:
                warnings.append(f"{module.title}模型生成有效段落不足，已由本地模板补齐")

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


def _chunks(items, size: int):
    items = list(items)
    for index in range(0, len(items), size):
        yield items[index : index + size]


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


def _section_specs() -> list[tuple[str, str, str, int, int, int]]:
    return [
        ("overview", "软件概述", "6-8个段落", 4, 1300, 220),
        ("login_main", "登录与主界面", "6-8个段落", 4, 1300, 220),
        ("statistics", "统计分析", "6-8个段落", 4, 1300, 220),
        ("security", "权限与安全", "6-8个段落", 4, 1300, 220),
        ("faq", "常见问题处理", "4-6个段落", 3, 900, 180),
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
- 段落写成软件说明书口吻，描述具体操作、界面、规则或业务能力
- 内容必须贴合产品方案中的具体场景、业务对象、流程、指标和规则
- 不要只写通用后台能力，每段至少包含一个具体业务对象、页面、指标、状态或操作
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
- 段落写成软件说明书口吻，描述具体操作、界面、规则或业务能力
- 内容必须贴合产品方案中的具体场景、业务对象、流程、指标和规则
- 不要只写通用后台能力，每段至少包含一个具体业务对象、页面、指标、状态或操作
- 只返回 JSON，格式为：{{"paragraphs":["段落1","段落2"]}}

禁止：
- 不要出现“AI”“模板”“示例”“假设”等字样
- 不要写申请主体、公司名称、联系人、费用、包过承诺
""".strip(),
        },
    ]
    content = provider.chat(
        messages,
        temperature=_temperature(task.randomness),
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
        trace_label=f"manual:{title}",
    )
    data = _parse_json(content)
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

{_build_context(task, blueprint)}

本批模块：
{json.dumps(module_payload, ensure_ascii=False, indent=2)}

返回 JSON 字段：
- modules: 对象，key 为模块 key，值包含 title 和 paragraphs
- 每个模块 paragraphs 生成 6-8 个段落，说明入口、查询、新增、编辑、审核、导出、日志、校验、权限联动等操作

要求：
- 每个模块内容必须只围绕该模块展开
- 必须使用该模块的 operations、data_fields、pages、rules 中的具体词语
- 段落写成用户手册/操作手册口吻
- 不要出现“AI”“模板”“示例”“假设”等字样
- 不要写申请主体、公司名称、联系人、费用、包过承诺
- 只返回 JSON

返回 JSON 示例：
{{"modules":{{"course_resource":{{"title":"课程资源管理","paragraphs":["段落1"]}}}}}}
""".strip(),
            },
        ],
        temperature=_temperature(task.randomness),
        max_tokens=2600,
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
    paragraphs = _paragraphs(value.get("paragraphs"), min_count=4, limit=220)
    if not paragraphs:
        return None
    return {
        "title": _clean_text(str(value.get("title") or module.title), 40),
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

{_build_context(task, blueprint)}

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
- paragraphs: 8-10个段落，说明入口、查询、新增、编辑、审核、导出、日志、校验、权限联动等操作

要求：
- 内容必须只围绕当前模块展开
- 必须使用当前模块的 operations、data_fields、pages、rules 中的具体词语
- 段落写成用户手册/操作手册口吻
- 不要出现“AI”“模板”“示例”“假设”等字样
- 不要写申请主体、公司名称、联系人、费用、包过承诺
- 只返回 JSON
""".strip(),
        },
    ]
    content = provider.chat(
        messages,
        temperature=_temperature(task.randomness),
        max_tokens=1600,
        response_format={"type": "json_object"},
        trace_label=f"manual:{module.title}",
    )
    data = _parse_json(content)
    paragraphs = _paragraphs(data.get("paragraphs"), min_count=4, limit=220)
    if not paragraphs:
        raise ValueError("模块有效段落不足")
    return {
        "title": _clean_text(str(data.get("title") or module.title), 40),
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


def _system_prompt() -> str:
    return (
        "你是中文软件著作权软件说明书撰写专家。请根据产品蓝图生成可直接写入 Word 的说明书正文。"
        "只返回 JSON，不要返回 Markdown，不要编造申请主体信息，不要承诺包过。"
    )


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
        raise ValueError("LLM 说明书不是 JSON 对象")
    return data


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
    provider_retries = int(getattr(getattr(provider, "config", None), "retry_count", 0) or 0)
    total_attempts = 1 if provider_retries > 0 else max(1, attempts)
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
            last_error = exc
            trace_event(
                "chat_json_error",
                layer="manual",
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
