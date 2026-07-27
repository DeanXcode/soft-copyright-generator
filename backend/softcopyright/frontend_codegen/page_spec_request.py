from __future__ import annotations

import json
import re
from typing import Any

from ..llm.provider import LLMProvider, TextRetryPolicy
from .page_spec import (
    ALLOWED_LAYOUTS,
    ALLOWED_REGION_COMPONENTS,
    PAGE_SPEC_MAX_CHARS,
    PAGE_SPEC_SCHEMA_VERSION,
    PageSpecValidationError,
    normalize_page_spec,
)


def request_page_spec(
    *,
    provider: LLMProvider,
    software_context: dict[str, Any],
    screen: dict[str, Any],
    module: dict[str, Any],
    visual_identity: dict[str, Any],
    color_contract: dict[str, Any],
    validation_feedback: str = "",
    retry_policy: TextRetryPolicy | None = None,
    cancel_event: Any | None = None,
) -> dict[str, Any]:
    page_key = str(screen.get("key") or "page")
    page_kind = str(screen.get("page_kind") or "general")
    interaction = {
        "action_key": str(screen.get("interaction_action_key") or ""),
        "action": str(screen.get("interaction_action") or ""),
        "mode": str(screen.get("interaction_mode") or "browse"),
        "surface": str(screen.get("interaction_surface") or "workspace"),
        "role": str(screen.get("interaction_role") or ""),
        "trigger": str(screen.get("interaction_trigger") or ""),
        "input_fields": list(screen.get("interaction_input_fields") or []),
        "pre_state": str(screen.get("interaction_pre_state") or ""),
        "post_state": str(screen.get("interaction_post_state") or ""),
        "result_evidence": str(screen.get("interaction_result_evidence") or ""),
        "requires_confirmation": bool(screen.get("requires_confirmation")),
    }
    payload = {
        "software_context": software_context,
        "screen": screen,
        "module": module,
        "interaction": interaction,
        "visual_identity": visual_identity,
        "image2_color_contract": color_contract,
        "allowed_layouts": sorted(ALLOWED_LAYOUTS),
        "allowed_region_components": sorted(ALLOWED_REGION_COMPONENTS),
    }
    repair_rule = (
        f"\n上一次 PageSpec 未通过本地校验：{validation_feedback[:360]}。只修复这些问题，不得改 page_key/page_kind。"
        if validation_feedback
        else ""
    )
    prompt = f"""
为软件页面生成结构化 PageSpec，不要生成 JSX、CSS、HTML、Markdown 或解释。

{json.dumps(payload, ensure_ascii=False, indent=2)}

只返回一个 JSON 对象，严格满足：
- schema_version 固定为 "{PAGE_SPEC_SCHEMA_VERSION}"，page_key 固定为 "{page_key}"，page_kind 固定为 "{page_kind}"。
- layout 只能从 allowed_layouts 选择；regions 只能使用 allowed_region_components，最多 7 个区域。
- 每个 region 使用 component/id/title，并按需要提供 columns、fields、items、metrics、steps、series 或 points；表格最多 5 行，指标最多 4 个，操作按钮最多 6 个。
- actions 必须包含 action_key、label、variant；操作页至少有 1 个 action，并与 interaction 的动作语义一致。
- interaction_contract 必须存在，至少包含 mode；操作页还必须包含 action_key、role、trigger、input_fields、pre_state、post_state、result_evidence、requires_confirmation。
- 使用真实中文业务数据，不得出现“待填写、示例内容、业务记录、AI、GPT、image2、API Key、Base URL”。
- JSON 总字符数不得超过 {PAGE_SPEC_MAX_CHARS}，不要输出未知字段中的自由 CSS 或脚本。{repair_rule}
""".strip()
    content = provider.chat(
        [
            {
                "role": "system",
                "content": "你是软件产品界面信息架构师，只输出受控 PageSpec JSON；页面视觉由本地组件库渲染。",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.42,
        max_tokens=1600,
        response_format={"type": "json_object"},
        trace_label=f"page_spec:{page_key}",
        retry_policy=retry_policy or TextRetryPolicy(max_retries=2),
        cancel_event=cancel_event,
    )
    if len(content or "") > PAGE_SPEC_MAX_CHARS:
        raise PageSpecValidationError(f"模型返回超过 {PAGE_SPEC_MAX_CHARS} 字符")
    data = _parse_json_object(content)
    return normalize_page_spec(
        data,
        expected_page_key=page_key,
        expected_page_kind=page_kind,
        expected_interaction=interaction,
    )


def _parse_json_object(content: str) -> dict[str, Any]:
    cleaned = str(content or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.I).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        cleaned = cleaned[start : end + 1]
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise PageSpecValidationError(f"PageSpec JSON 无法解析：{exc.msg}") from exc
    if not isinstance(data, dict):
        raise PageSpecValidationError("PageSpec 必须是 JSON 对象")
    return data
