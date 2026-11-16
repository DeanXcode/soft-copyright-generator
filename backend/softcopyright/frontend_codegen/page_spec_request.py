from __future__ import annotations

import json
from typing import Any

from ..llm.provider import LLMProvider, TextRetryPolicy
from ..llm.json_response import parse_json_object
from ..llm.trace import trace_event
from .page_spec import (
    ALLOWED_LAYOUTS,
    ALLOWED_REGION_COMPONENTS,
    LOGIN_ALLOWED_REGION_COMPONENTS,
    LOGIN_MAX_FIELDS,
    PAGE_SPEC_MAX_CHARS,
    PAGE_SPEC_SCHEMA_VERSION,
    PageSpecValidationError,
    normalize_page_spec,
)
from .page_spec_semantics import (
    page_spec_semantic_profile,
    sanitize_page_spec_semantics,
    unauthorized_page_spec_terms,
)


def _page_software_context(context: dict[str, Any]) -> dict[str, Any]:
    # The current module is sent separately, in full. Other modules only need
    # identities for navigation; repeating their operation contracts on every
    # page costs tokens and makes unrelated instructions compete with this page.
    compact = {key: value for key, value in context.items() if key not in {"modules", "feature_hint"}}
    compact["modules"] = [
        {key: item[key] for key in ("key", "title") if key in item}
        for item in context.get("modules", []) if isinstance(item, dict)
    ]
    # The accepted blueprint and current module already contain the detailed
    # requirements. Keep a bounded reminder of the original freeform input.
    if context.get("feature_hint"):
        compact["feature_hint"] = str(context["feature_hint"])[:1200]
    return compact


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
    semantic_profile = page_spec_semantic_profile(module, screen)
    local_interaction = not interaction["action_key"] or all(
        interaction[key] for key in ("trigger", "post_state", "result_evidence")
    )
    payload = {
        "software_context": _page_software_context(software_context),
        "screen": screen,
        "module": module,
        "interaction": interaction,
        "visual_identity": visual_identity,
        "image2_color_contract": color_contract,
        "business_vocabulary_contract": {
            "subject": semantic_profile["subject"],
            "actions": semantic_profile["actions"][:7],
            "states": semantic_profile["states"][:7],
            "fields": semantic_profile["fields"][:10],
            "roles": semantic_profile["roles"][:5],
            "result_evidence": semantic_profile["evidence"][:5],
            "allowed_process_terms": semantic_profile["allowed_process_terms"],
            "forbidden_uncontracted_terms": semantic_profile["forbidden_process_terms"],
        },
        "allowed_layouts": sorted(ALLOWED_LAYOUTS),
        "allowed_region_components": sorted(
            LOGIN_ALLOWED_REGION_COMPONENTS if page_kind == "login" else ALLOWED_REGION_COMPONENTS
        ),
    }
    repair_mode = bool(validation_feedback)
    repair_rule = (
        f"\n上一次 PageSpec 未通过本地校验：{validation_feedback[:360]}。只修复这些问题，不得改 page_key/page_kind。"
        "这是唯一修复轮：最多保留 4 个 regions，表格最多 3 行、指标最多 3 个、每个文字字段不超过 48 个字符，"
        "保留必需的交互契约和业务证据；优先删除重复说明和装饰区，不得截断 JSON。"
        f"完整 JSON 必须明显短于 {PAGE_SPEC_MAX_CHARS} 字符。"
        if repair_mode
        else ""
    )
    page_kind_rule = (
        f"""
- 当前是登录页：layout 必须为 login_workspace，regions 只能包含一个可选 detail 品牌区和一个必需 form 登录卡，总数最多 2 个。
- detail 只保留软件名称和可选版本；不得罗列核心链路、服务对象、数据安全、审计记录、业务指标或项目介绍。
- form 最多 {LOGIN_MAX_FIELDS} 个主要字段，优先为账号、密码、验证码，确有必要时只增加一个角色/项目/租户选择；“记住账号”和“忘记密码”不要作为 fields。
- 禁止 operation_result、filter_bar、metric_group、data_table、workflow、timeline、kanban、chart、map_panel、relationship_graph 和 mobile_list。
- actions 只返回一个主登录动作，建议标签为“登录系统”，不得要求确认；未登录状态不得描述为操作已完成或结果已记录。
""".strip()
        if page_kind == "login"
        else ""
    )
    interaction_rule = (
        "- interaction_contract 由本地依据已确认的 interaction 原样注入，可省略；"
        "主操作按钮缺失时也由本地补齐，不要重复输出上述已知契约。"
        if local_interaction else
        "- interaction_contract 必须存在，至少包含 mode；操作页还必须包含 action_key、role、trigger、input_fields、pre_state、post_state、result_evidence、requires_confirmation。"
    )
    serialized_payload = json.dumps(payload, ensure_ascii=False, separators=(",", ": "))
    original_payload = {**payload, "software_context": software_context}
    trace_event(
        "page_spec_request_context",
        page_key=page_key,
        original_payload_chars=len(json.dumps(original_payload, ensure_ascii=False, indent=2)),
        payload_chars=len(serialized_payload),
        repair_mode=repair_mode,
    )
    prompt = f"""
为软件页面生成结构化 PageSpec，不要生成 JSX、CSS、HTML、Markdown 或解释。

{serialized_payload}

只返回一个 JSON 对象，严格满足：
- schema_version 固定为 "{PAGE_SPEC_SCHEMA_VERSION}"，page_key 固定为 "{page_key}"，page_kind 固定为 "{page_kind}"。
- layout 只能从 allowed_layouts 选择；regions 只能使用 allowed_region_components，最多 7 个区域。
- 每个 region 使用 component/id/title，并按组件实际需要提供 columns、fields、items、metrics、steps、series 或 points，不得同时填充不使用的字段。
- data_table 的 columns 使用 key/label 对象，items 用对应 key 存放单元格值；chart 的 series 使用 name/points，points 为 label/value 对象数组，value 为数值或百分比，不要将 points 写成字符串；metric 的 value 保留原值，description 说明统计口径。
- 优先 3–5 个有业务用途的区域；表格最多 3 行、6 列，指标最多 3 个，操作按钮最多 4 个；不要重复输出 module、screen、配色契约或请求上下文。
- actions 必须包含 action_key、label、variant；操作页至少有 1 个 action，并与 interaction 的动作语义一致。
{interaction_rule}
- 页面业务名词、动作、状态、岗位和结果证据必须来自 business_vocabulary_contract 或 module；禁止自行补造 forbidden_uncontracted_terms 中的通用后台词。
- “台账、复核、审核、归档、待处理、待复核、操作日志”只有出现在 allowed_process_terms 时才能使用；否则应使用当前软件真实对象、动作和状态，不得把不同软件都写成审核台账系统。
- 使用真实中文业务数据，不得出现“待填写、示例内容、业务记录、AI、GPT、image2、API Key、Base URL”。
- 输出紧凑 JSON，不要缩进或换行；目标不超过 4500 字符，硬上限 {PAGE_SPEC_MAX_CHARS}。文字字段尽量短，保留业务名词、关键字段和结果证据；不要输出未知字段中的自由 CSS 或脚本。
{page_kind_rule}{repair_rule}
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
        max_tokens=2400,
        response_format={"type": "json_object"},
        trace_label=f"page_spec:{page_key}",
        retry_policy=retry_policy or TextRetryPolicy(max_retries=2),
        cancel_event=cancel_event,
    )
    # Formatting whitespace is not page content. Keep a separate raw-response
    # ceiling, then apply the existing content limit BEFORE normalization so
    # dropping unknown fields cannot silently turn an oversized page valid.
    if len(content or "") > PAGE_SPEC_MAX_CHARS * 4:
        raise PageSpecValidationError(f"模型原始返回超过 {PAGE_SPEC_MAX_CHARS * 4} 字符")
    data = _parse_json_object(content)
    compact_chars = len(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    if compact_chars > PAGE_SPEC_MAX_CHARS:
        raise PageSpecValidationError(f"模型返回超过 {PAGE_SPEC_MAX_CHARS} 字符（紧凑 JSON {compact_chars} 字符）")
    if local_interaction:
        # These facts are already confirmed upstream. Requiring the model to
        # echo them wastes output and creates avoidable missing-field failures.
        data["interaction_contract"] = interaction
    normalized = normalize_page_spec(
        data,
        expected_page_key=page_key,
        expected_page_kind=page_kind,
        expected_interaction=interaction,
    )
    unauthorized_terms = unauthorized_page_spec_terms(normalized, module=module, screen=screen)
    if unauthorized_terms:
        normalized, _replaced_terms = sanitize_page_spec_semantics(normalized, module=module, screen=screen)
    return normalized


def _parse_json_object(content: str) -> dict[str, Any]:
    try:
        return parse_json_object(content, label="page_spec")
    except json.JSONDecodeError as exc:
        raise PageSpecValidationError(f"PageSpec JSON 无法解析：{exc.msg}（第 {exc.lineno} 行，第 {exc.colno} 列）") from exc
    except ValueError as exc:
        raise PageSpecValidationError(str(exc)) from exc
