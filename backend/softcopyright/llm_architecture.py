from __future__ import annotations

import json
import re
import time
from typing import Any

from .architecture import (
    ARCHITECTURE_CATALOG,
    TechnicalArchitecture,
    architecture_catalog_for_prompt,
    create_technical_architecture,
    normalize_technical_architecture_for_experience,
    select_technical_architecture,
)
from .blueprint import ProductBlueprint
from .llm.provider import LLMProvider, LocalTemplateProvider, TextProviderError, TextRetryPolicy
from .llm.trace import trace_event
from .models import GenerationTask


def select_technical_architecture_with_llm(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    provider: LLMProvider | None,
    emit=None,
    require_llm: bool = False,
) -> TechnicalArchitecture:
    fallback = select_technical_architecture(task, blueprint)
    if provider is None or isinstance(provider, LocalTemplateProvider):
        return fallback

    if emit:
        emit(22, "由 GPT 选择真实项目技术架构")
    try:
        data = _chat_json(
            provider,
            [
                {"role": "system", "content": _system_prompt()},
                {"role": "user", "content": _build_prompt(task, blueprint, fallback)},
            ],
            temperature=0.28,
            max_tokens=1400,
            label="技术架构选择",
        )
        architecture = normalize_technical_architecture_for_experience(
            task,
            blueprint,
            _architecture_from_data(data, fallback),
        )
        trace_event(
            "architecture_selection_success",
            layer="architecture",
            selected_key=architecture.key,
            source_strategy=architecture.source_strategy,
            source_language=architecture.source_language,
        )
        return architecture
    except Exception as exc:
        trace_event(
            "architecture_selection_fallback",
            layer="architecture",
            fallback_key=fallback.key,
            error_type=type(exc).__name__,
            error=str(exc)[:500],
        )
        if require_llm:
            raise RuntimeError(f"GPT 技术架构选择失败：{str(exc)[:180]}") from exc
        fallback.source = "local-rule-fallback"
        fallback.rationale = f"GPT 技术架构选择失败，使用本地规则：{str(exc)[:160]}"
        return fallback


def _system_prompt() -> str:
    return (
        "你是严谨的软件架构师和软件著作权源码工程设计专家。"
        "你必须从给定架构目录中选择一个最适合本软件的真实项目架构，"
        "让后续源码工程、说明书、截图和校验报告围绕同一个技术架构生成。"
        "只返回 JSON 对象，不要 Markdown，不要解释文字。"
    )


def _build_prompt(task: GenerationTask, blueprint: ProductBlueprint, fallback: TechnicalArchitecture) -> str:
    compact_blueprint = {
        "software_name": blueprint.software_name,
        "version": blueprint.version,
        "product_type": blueprint.product_type,
        "software_category": task.software_category,
        "industry": blueprint.industry,
        "industry_subtype": blueprint.industry_subtype,
        "scenario": blueprint.scenario,
        "positioning": blueprint.positioning,
        "target_users": blueprint.target_users or blueprint.roles,
        "business_objects": blueprint.business_objects[:12],
        "workflows": blueprint.workflows[:4],
        "report_metrics": blueprint.report_metrics[:10],
        "modules": [
            {
                "key": module.key,
                "title": module.title,
                "description": module.description,
                "entities": module.entities[:4],
                "operations": module.operations[:6],
                "data_fields": module.data_fields[:8],
            }
            for module in blueprint.modules[:8]
        ],
    }
    return f"""
请为本软件自动选择技术架构，并给出后续真实源码工程生成所需的结构化决策。

硬性要求：
- 必须从 architecture_catalog 的 key 中选择，不能自创 key。
- source_strategy 必须与所选 key 的目录定义一致。
- 选择理由必须贴合软件名称、产品类型、软件分类、模块和业务对象。
- 如果用户输入语言为“自动选择”，优先按产品真实形态选择；如果用户输入了具体语言，也可以在理由中说明为何采用更完整的多语言架构。
- 不要选择当前源码生成器不支持的框架或语言。
- 输出 JSON 字段：selected_key, rationale, project_layout, run_commands, quality_checks。

用户输入语言：{task.language}
本地规则建议：{json.dumps(fallback.to_dict(), ensure_ascii=False)}

architecture_catalog:
{json.dumps(architecture_catalog_for_prompt(), ensure_ascii=False, indent=2)}

product_blueprint:
{json.dumps(compact_blueprint, ensure_ascii=False, indent=2)}
""".strip()


def _architecture_from_data(data: dict[str, Any], fallback: TechnicalArchitecture) -> TechnicalArchitecture:
    key = str(data.get("selected_key") or data.get("key") or "").strip()
    if key not in ARCHITECTURE_CATALOG:
        raise ValueError(f"GPT 选择了不支持的技术架构：{key or '-'}")
    item = ARCHITECTURE_CATALOG[key]
    source_strategy = str(data.get("source_strategy") or item.get("source_strategy") or "").strip()
    if source_strategy != item["source_strategy"]:
        raise ValueError(f"GPT 架构 source_strategy 不匹配：{source_strategy}")

    rationale = _clean_text(str(data.get("rationale") or ""), 220)
    if len(rationale) < 16:
        raise ValueError("GPT 技术架构选择理由过短")
    project_layout = _clean_list(data.get("project_layout"), 8, 42)
    run_commands = _clean_list(data.get("run_commands"), 6, 80)
    quality_checks = _clean_list(data.get("quality_checks"), 8, 70)
    return create_technical_architecture(
        key,
        source="llm",
        rationale=rationale,
        project_layout=project_layout,
        run_commands=run_commands,
        quality_checks=quality_checks,
    )


def _chat_json(
    provider: LLMProvider,
    messages: list[dict[str, str]],
    *,
    temperature: float,
    max_tokens: int,
    label: str,
) -> dict[str, Any]:
    last_error: Exception | None = None
    current_messages = messages
    total_attempts = 2
    for attempt in range(total_attempts):
        started_at = time.perf_counter()
        trace_event(
            "chat_json_begin",
            layer="architecture",
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
                trace_label=f"architecture:{label}",
                retry_policy=TextRetryPolicy(max_retries=1),
            )
            data = _parse_json(content)
            trace_event(
                "chat_json_success",
                layer="architecture",
                label=label,
                attempt=attempt + 1,
                elapsed_seconds=round(time.perf_counter() - started_at, 3),
                content_chars=len(content or ""),
            )
            return data
        except TextProviderError:
            raise
        except Exception as exc:
            last_error = exc
            trace_event(
                "chat_json_error",
                layer="architecture",
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
                            f"上一次{label}没有得到合法 JSON，错误摘要：{str(exc)[:120]}。"
                            "请重新输出严格 JSON 对象，只能选择 architecture_catalog 中的 selected_key。"
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
        raise ValueError("技术架构响应不是 JSON 对象")
    return data


def _clean_text(value: str, limit: int) -> str:
    return re.sub(r"\s+", " ", value).strip()[:limit]


def _clean_list(value: Any, max_count: int, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value[:max_count]:
        text = _clean_text(str(item or ""), limit)
        if text and text not in result:
            result.append(text)
    return result
