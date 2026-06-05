from __future__ import annotations

import json
import re
from typing import Any

from .blueprint import ProductBlueprint
from .llm.provider import LLMProvider, LocalTemplateProvider
from .models import GenerationTask


def generate_manual_content_with_llm(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    provider: LLMProvider | None,
) -> dict[str, Any] | None:
    if provider is None or isinstance(provider, LocalTemplateProvider):
        return None

    messages = [
        {
            "role": "system",
            "content": (
                "你是中文软件著作权软件说明书撰写专家。请根据产品蓝图生成可直接写入 Word 的说明书正文。"
                "只返回 JSON，不要返回 Markdown，不要编造申请主体信息，不要承诺包过。"
            ),
        },
        {
            "role": "user",
            "content": _build_prompt(task, blueprint),
        },
    ]
    content = provider.chat(
        messages,
        temperature=_temperature(task.randomness),
        max_tokens=6000,
        response_format={"type": "json_object"},
    )
    data = _parse_json(content)
    return _normalize_manual_content(blueprint, data)


def _build_prompt(task: GenerationTask, blueprint: ProductBlueprint) -> str:
    modules = "\n".join(
        f"- key: {module.key}; title: {module.title}; description: {module.description}"
        for module in blueprint.modules
    )
    return f"""
请生成《{task.software_name}软件说明书》的正文内容。

基础信息：
- 版本号：{task.version}
- 编程语言：{task.language}
- 产品类型：{task.product_type}
- 行业领域：{blueprint.industry}
- 开发目的：{blueprint.purpose}
- 软件概述：{blueprint.summary}
- 业务补充：{task.feature_hint or "无"}

功能模块：
{modules}

返回 JSON 字段：
- overview: 6-8个段落，说明软件定位、业务目标、适用场景、整体能力
- login_main: 6-8个段落，说明登录、首页、菜单、角色权限、基础操作
- modules: 数组，每个模块包含 key/title/paragraphs；paragraphs 为8-10个段落
- statistics: 6-8个段落，说明统计分析、查询、导出、报表
- security: 6-8个段落，说明权限、日志、安全、数据校验
- faq: 4-6个常见问题处理段落

要求：
- 内容必须和软件名称、业务补充、功能模块一致
- 段落写成说明书口吻，避免营销话术
- 不要出现“AI”“模板”“示例”“假设”等字样
- 不要写申请主体、公司名称、联系人、费用、包过承诺
- 只返回 JSON
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
        raise ValueError("LLM 说明书不是 JSON 对象")
    return data


def _normalize_manual_content(blueprint: ProductBlueprint, data: dict[str, Any]) -> dict[str, Any]:
    modules_by_key = {}
    modules = data.get("modules")
    if isinstance(modules, list):
        for item in modules:
            if not isinstance(item, dict):
                continue
            key = _clean_key(str(item.get("key") or ""))
            paragraphs = _paragraphs(item.get("paragraphs"), min_count=4, limit=220)
            if key and paragraphs:
                modules_by_key[key] = {
                    "title": _clean_text(str(item.get("title") or key), 40),
                    "paragraphs": paragraphs,
                }

    normalized = {
        "overview": _paragraphs(data.get("overview"), min_count=4, limit=220),
        "login_main": _paragraphs(data.get("login_main"), min_count=4, limit=220),
        "statistics": _paragraphs(data.get("statistics"), min_count=4, limit=220),
        "security": _paragraphs(data.get("security"), min_count=4, limit=220),
        "faq": _paragraphs(data.get("faq"), min_count=3, limit=180),
        "modules": modules_by_key,
    }
    if len(normalized["modules"]) < max(2, min(4, len(blueprint.modules))):
        raise ValueError("LLM 说明书模块正文不足")
    return normalized


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


def _clean_key(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]+", "_", value).strip("_").lower()


def _clean_text(value: str, limit: int) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    return value[:limit]
