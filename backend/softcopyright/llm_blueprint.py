from __future__ import annotations

import json
import re
from typing import Any

from .blueprint import FeatureModule, ProductBlueprint, _environment_for_language, _runtime_for_language
from .llm.provider import LLMProvider, LocalTemplateProvider
from .models import GenerationTask


def generate_blueprint_with_llm(task: GenerationTask, provider: LLMProvider | None) -> ProductBlueprint | None:
    if provider is None or isinstance(provider, LocalTemplateProvider):
        return None

    messages = [
        {
            "role": "system",
            "content": (
                "你是中文软件著作权材料生成专家。请根据用户输入生成真实、具体、可落到源码工程的产品蓝图。"
                "只返回 JSON，不要返回 Markdown，不要编造公司主体信息，不要承诺包过。"
            ),
        },
        {
            "role": "user",
            "content": _build_prompt(task),
        },
    ]
    content = provider.chat(
        messages,
        temperature=_temperature(task.randomness),
        max_tokens=3500,
        response_format={"type": "json_object"},
    )
    data = _parse_json(content)
    return _blueprint_from_data(task, data)


def _build_prompt(task: GenerationTask) -> str:
    return f"""
请为以下软件生成软著材料用产品蓝图：

软件全称：{task.software_name}
版本号：{task.version}
编程语言：{task.language}
软件技术特点/产品类型：{task.product_type}
业务补充：{task.feature_hint or "无"}

返回 JSON 字段必须包含：
- industry: 面向领域/行业，中文短语
- purpose: 开发目的，一句话
- summary: 软件主要功能概述，150-300字
- roles: 4-6个用户角色，字符串数组
- modules: 6-8个功能模块，每个对象包含 key/title/description/entities
- pages: 8-12个页面名称，字符串数组

modules 规则：
- key 使用小写英文或英文下划线，适合作为源码目录/类名前缀
- title 使用中文模块名
- description 要具体写出业务动作，不能空泛
- entities 是2-4个英文实体名
- 模块必须与软件名称和业务补充高度相关

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
        description = _clean_text(str(item.get("description") or f"{title}用于业务数据维护和流程处理。"), 160)
        entities = item.get("entities")
        if not isinstance(entities, list):
            entities = [f"Module{index}Record", f"Module{index}Query"]
        safe_entities = [_safe_entity(str(entity)) for entity in entities[:4] if str(entity).strip()]
        if len(safe_entities) < 2:
            safe_entities = [f"Module{index}Record", f"Module{index}Query"]
        modules.append(FeatureModule(key=key, title=title, description=description, entities=safe_entities))

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
    purpose = _clean_text(str(data.get("purpose") or f"用于{industry}场景下的业务管理和数据分析。"), 120)
    summary = _clean_text(str(data.get("summary") or _fallback_summary(task, industry, modules)), 360)

    return ProductBlueprint(
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
    )


def _temperature(randomness: str) -> float:
    if randomness == "保守":
        return 0.35
    if randomness == "高差异":
        return 0.9
    return 0.65


def _safe_key(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_]+", "_", value).strip("_").lower()
    return value or "business"


def _safe_entity(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", " ", value)
    parts = [part for part in value.split() if part]
    entity = "".join(part[:1].upper() + part[1:] for part in parts)
    return entity or "BusinessRecord"


def _clean_text(value: str, limit: int) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    return value[:limit]


def _fallback_summary(task: GenerationTask, industry: str, modules: list[FeatureModule]) -> str:
    titles = "、".join(module.title for module in modules[:4])
    return f"{task.software_name}是一套面向{industry}的{task.product_type}，围绕{titles}等模块提供业务管理、流程协同、统计分析和权限审计能力。"
