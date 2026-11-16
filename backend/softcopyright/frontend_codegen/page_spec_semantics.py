from __future__ import annotations

from copy import deepcopy
import re
from typing import Any


_CONTROLLED_PROCESS_TERMS = (
    "待复核",
    "待处理",
    "操作日志",
    "当前记录",
    "业务记录",
    "台账",
    "复核",
    "审核",
    "归档",
)

_GENERIC_ROLE_TERMS = ("审核人员", "业务专员", "主管人员", "系统管理员")

_ACTION_VERBS = (
    "查询",
    "筛选",
    "搜索",
    "查看",
    "监测",
    "采集",
    "分析",
    "研判",
    "登记",
    "录入",
    "创建",
    "新增",
    "编辑",
    "更新",
    "维护",
    "提交",
    "确认",
    "下达",
    "调度",
    "处置",
    "整改",
    "验收",
    "复验",
    "统计",
    "导入",
    "导出",
    "播放",
    "收藏",
    "下载",
    "打卡",
    "排班",
    "预约",
    "核销",
    "发布",
)

_SUBJECT_SUFFIXES = (
    "智能管理平台",
    "管理平台",
    "管理系统",
    "信息系统",
    "软件系统",
    "工作平台",
    "业务平台",
    "工作台",
    "管理",
    "平台",
    "系统",
    "模块",
    "页面",
    "界面",
)


def page_spec_semantic_profile(module: dict[str, Any] | None, screen: dict[str, Any] | None) -> dict[str, Any]:
    module = module if isinstance(module, dict) else {}
    screen = screen if isinstance(screen, dict) else {}
    operation_specs = [item for item in module.get("operation_specs") or [] if isinstance(item, dict)]
    actions = _unique(
        [
            screen.get("interaction_action"),
            *(item.get("label") or item.get("action") or item.get("name") for item in operation_specs),
            *(module.get("operations") or []),
        ]
    )
    states = _unique(
        [
            screen.get("interaction_pre_state"),
            screen.get("interaction_post_state"),
            *(item.get("pre_state") or item.get("preState") for item in operation_specs),
            *(item.get("post_state") or item.get("postState") for item in operation_specs),
        ]
    )
    roles = _unique(
        [
            screen.get("interaction_role"),
            *(item.get("role") for item in operation_specs),
        ]
    )
    evidence = _unique(
        [
            screen.get("interaction_result_evidence"),
            *(item.get("result_evidence") or item.get("resultEvidence") for item in operation_specs),
        ]
    )
    fields = _unique(
        [
            *(screen.get("interaction_input_fields") or []),
            *(module.get("data_fields") or []),
            *(
                field
                for item in operation_specs
                for field in (item.get("input_fields") or item.get("inputFields") or [])
            ),
        ]
    )
    entities = _unique(module.get("entities") or [])
    title = _clean(module.get("title") or screen.get("title") or "")
    subject = _subject(title, entities=entities, fields=fields)
    action_verb = _action_verb(actions, subject=subject)
    explicit_process_text = "\n".join([title, *actions, *states, *fields, *evidence])
    allowed_terms = {
        term
        for term in _CONTROLLED_PROCESS_TERMS
        if term not in {"当前记录", "业务记录"} and term in explicit_process_text
    }
    preferred_state = next((value for value in states if _usable_state(value)), "")
    pending_state = preferred_state or (f"待{action_verb}" if action_verb else "待更新")
    if len(pending_state) > 14 or any(term in pending_state for term in ("全部", "列表", "范围")):
        pending_state = f"待{action_verb}" if action_verb else "待更新"
    result_evidence = next((value for value in evidence if _usable_evidence(value)), "")
    role = roles[0] if roles else "责任人员"
    replacements = {
        "待复核": pending_state,
        "待处理": pending_state,
        "操作日志": result_evidence or f"{subject}更新记录",
        "当前记录": f"当前{subject}",
        "业务记录": subject,
        "台账": "清单",
        "复核": action_verb or "处理",
        "审核": action_verb or "处理",
        "归档": "完成",
        "审核人员": role,
        "业务专员": role,
        "主管人员": role,
        "系统管理员": role,
    }
    return {
        "subject": subject,
        "actions": actions,
        "action_verb": action_verb or "处理",
        "states": states,
        "fields": fields,
        "roles": roles,
        "role": role,
        "evidence": evidence,
        "result_evidence": result_evidence or f"{subject}更新结果",
        "entities": entities,
        "allowed_process_terms": sorted(allowed_terms),
        "forbidden_process_terms": [term for term in _CONTROLLED_PROCESS_TERMS if term not in allowed_terms],
        "replacements": replacements,
    }


def unauthorized_page_spec_terms(
    page_spec: dict[str, Any],
    *,
    module: dict[str, Any] | None,
    screen: dict[str, Any] | None,
) -> list[str]:
    profile = page_spec_semantic_profile(module, screen)
    text = "\n".join(_walk_strings(page_spec))
    return [term for term in profile["forbidden_process_terms"] if term in text]


def sanitize_page_spec_semantics(
    page_spec: dict[str, Any],
    *,
    module: dict[str, Any] | None,
    screen: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[str]]:
    profile = page_spec_semantic_profile(module, screen)
    forbidden = set(profile["forbidden_process_terms"])
    replacements = dict(profile["replacements"])
    replaced: set[str] = set()

    def visit(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: visit(item) for key, item in value.items()}
        if isinstance(value, list):
            return [visit(item) for item in value]
        if not isinstance(value, str):
            return value
        result = value
        for term in _CONTROLLED_PROCESS_TERMS:
            if term not in forbidden or term not in result:
                continue
            replacement = str(replacements.get(term) or "").strip()
            if replacement and replacement != term:
                result = result.replace(term, replacement)
                replaced.add(term)
        for term in _GENERIC_ROLE_TERMS:
            if term in result and str(replacements.get(term) or term) != term:
                result = result.replace(term, str(replacements[term]))
                replaced.add(term)
        return re.sub(r"(.)\1{2,}", r"\1\1", result)

    return visit(deepcopy(page_spec)), sorted(replaced)


def _subject(title: str, *, entities: list[str], fields: list[str]) -> str:
    value = _clean(title)
    for suffix in _SUBJECT_SUFFIXES:
        if value.endswith(suffix) and len(value) > len(suffix) + 1:
            value = value[: -len(suffix)].strip()
            break
    value = re.sub(r"(?:查询|筛选|统计|分析|监测|校验|维护)$", "", value).strip()
    if value:
        return value[:14]
    if entities:
        return _humanize_entity(entities[0])[:14]
    if fields:
        field = re.sub(r"(?:编号|编码|名称|状态|时间|日期)$", "", fields[0]).strip()
        if field:
            return field[:14]
    return "当前事项"


def _humanize_entity(value: str) -> str:
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(value or ""))
    text = re.sub(r"[_\-]+", " ", text).strip()
    return text or "当前事项"


def _action_verb(actions: list[str], *, subject: str) -> str:
    for action in actions:
        for verb in _ACTION_VERBS:
            if verb in action:
                return verb
        stripped = str(action or "").replace(subject, "").strip()
        if 1 < len(stripped) <= 4:
            return stripped
    return ""


def _usable_state(value: str) -> bool:
    text = _clean(value)
    return bool(text) and len(text) <= 14 and not any(term in text for term in ("未选择", "未应用", "全部", "列表"))


def _usable_evidence(value: str) -> bool:
    text = _clean(value)
    return bool(text) and len(text) <= 18 and "操作日志" not in text


def _walk_strings(value: Any):
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_strings(item)
    elif isinstance(value, str):
        yield value


def _unique(values: Any) -> list[str]:
    result: list[str] = []
    for value in values or []:
        text = _clean(value)
        if text and text not in result:
            result.append(text)
    return result


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()
