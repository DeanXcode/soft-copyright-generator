from __future__ import annotations

from hashlib import sha256
import json
import re
from typing import Any

from .page_composition import PAGE_COMPOSITION_VERSION


PAGE_SPEC_SCHEMA_VERSION = "page-spec-v1"
COMPONENT_LIBRARY_VERSION = "page-components-v3"
FRONTEND_ENGINE_VERSION = "pagespec-hybrid-v6"
PAGE_SPEC_MAX_CHARS = 6000

ALLOWED_LAYOUTS = {
    "table_workspace",
    "dashboard_grid",
    "form_detail",
    "workflow_board",
    "timeline_detail",
    "kanban_workspace",
    "chart_analysis",
    "map_workspace",
    "relationship_workspace",
    "mobile_feed",
    "result_confirmation",
    "login_workspace",
}

ALLOWED_REGION_COMPONENTS = {
    "filter_bar",
    "metric_group",
    "data_table",
    "form",
    "detail",
    "workflow",
    "timeline",
    "kanban",
    "chart",
    "map_panel",
    "relationship_graph",
    "mobile_list",
    "operation_result",
}

ALLOWED_DENSITIES = {"compact", "comfortable", "spacious"}
ALLOWED_ACCENTS = {"primary", "secondary", "warning", "success"}
ALLOWED_ACTION_VARIANTS = {"primary", "secondary", "ghost", "danger"}
LOGIN_ALLOWED_REGION_COMPONENTS = {"detail", "form"}
LOGIN_MAX_FIELDS = 4


class PageSpecValidationError(ValueError):
    def __init__(self, reasons: list[str] | str):
        self.reasons = [str(item) for item in reasons] if isinstance(reasons, list) else [str(reasons)]
        super().__init__("；".join(self.reasons))


def normalize_page_spec(
    payload: dict[str, Any],
    *,
    expected_page_key: str,
    expected_page_kind: str,
    expected_interaction: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise PageSpecValidationError("PageSpec 必须是 JSON 对象")
    reasons: list[str] = []
    if str(payload.get("schema_version") or "").strip() != PAGE_SPEC_SCHEMA_VERSION:
        reasons.append(f"schema_version 必须为 {PAGE_SPEC_SCHEMA_VERSION}")
    page_key = _text(payload.get("page_key"), 80)
    if page_key != expected_page_key:
        reasons.append(f"page_key 必须为 {expected_page_key}")
    page_kind = _text(payload.get("page_kind"), 40)
    if page_kind != expected_page_kind:
        reasons.append(f"page_kind 必须为 {expected_page_kind}")
    layout = _token(payload.get("layout"), 48)
    if layout not in ALLOWED_LAYOUTS:
        reasons.append(f"未知布局 {layout or '<empty>'}")

    raw_theme = payload.get("theme")
    theme = raw_theme if isinstance(raw_theme, dict) else {}
    density = _token(theme.get("density"), 24) or "comfortable"
    accent_variant = _token(theme.get("accent_variant"), 24) or "primary"
    if density not in ALLOWED_DENSITIES:
        reasons.append(f"未知密度 {density}")
    if accent_variant not in ALLOWED_ACCENTS:
        reasons.append(f"未知强调色变体 {accent_variant}")

    raw_regions = payload.get("regions")
    if not isinstance(raw_regions, list) or not raw_regions:
        reasons.append("regions 至少需要 1 个受控组件")
        raw_regions = []
    if len(raw_regions) > 7:
        reasons.append("regions 不能超过 7 个")
    regions: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw_region in enumerate(raw_regions[:7], start=1):
        if not isinstance(raw_region, dict):
            reasons.append(f"第 {index} 个 region 必须是对象")
            continue
        component = _token(raw_region.get("component") or raw_region.get("type"), 40)
        if component not in ALLOWED_REGION_COMPONENTS:
            reasons.append(f"第 {index} 个 region 使用未知组件 {component or '<empty>'}")
            continue
        region_id = _token(raw_region.get("id"), 48) or f"region_{index}"
        if region_id in seen_ids:
            reasons.append(f"region id 重复：{region_id}")
            region_id = f"{region_id}_{index}"
        seen_ids.add(region_id)
        regions.append(_normalize_region(raw_region, component=component, region_id=region_id))

    if page_kind == "login":
        layout = "login_workspace"
        regions = _normalize_login_regions(regions)
        login_form = next((region for region in regions if region.get("component") == "form"), None)
        if login_form is None:
            reasons.append("登录页必须包含一个 form 登录卡")
        else:
            labels = [str(item.get("label") or "") for item in login_form.get("fields") or []]
            if not any(_login_field_matches(label, "account") for label in labels):
                reasons.append("登录页缺少账号或用户名字段")
            if not any(_login_field_matches(label, "password") for label in labels):
                reasons.append("登录页缺少密码字段")

    raw_actions = payload.get("actions")
    if raw_actions is None:
        raw_actions = []
    if not isinstance(raw_actions, list):
        reasons.append("actions 必须是数组")
        raw_actions = []
    actions: list[dict[str, Any]] = []
    for index, raw_action in enumerate(raw_actions[:6], start=1):
        if not isinstance(raw_action, dict):
            reasons.append(f"第 {index} 个 action 必须是对象")
            continue
        action_key = _token(raw_action.get("action_key") or raw_action.get("key"), 64)
        label = _text(raw_action.get("label"), 24)
        if not action_key or not label:
            reasons.append(f"第 {index} 个 action 缺少 action_key 或 label")
            continue
        variant = _token(raw_action.get("variant"), 24) or ("primary" if index == 1 else "secondary")
        if variant not in ALLOWED_ACTION_VARIANTS:
            variant = "secondary"
        actions.append(
            {
                "action_key": action_key,
                "label": label,
                "variant": variant,
                "requires_confirmation": bool(raw_action.get("requires_confirmation")),
            }
        )
    if page_kind == "login":
        actions = actions[:1]
        if actions:
            actions[0]["variant"] = "primary"
            actions[0]["requires_confirmation"] = False

    raw_contract = payload.get("interaction_contract")
    if not isinstance(raw_contract, dict) or not raw_contract:
        reasons.append("缺少 interaction_contract")
        raw_contract = {}
    interaction_contract = _normalize_interaction_contract(raw_contract)
    if not interaction_contract.get("mode"):
        reasons.append("interaction_contract 缺少 mode")

    expected = expected_interaction if isinstance(expected_interaction, dict) else {}
    expected_action = _token(expected.get("action_key"), 64)
    if expected_action:
        if not interaction_contract.get("action_key"):
            reasons.append("操作页 interaction_contract 缺少 action_key")
        if not interaction_contract.get("trigger"):
            reasons.append("操作页 interaction_contract 缺少 trigger")
        if not interaction_contract.get("post_state"):
            reasons.append("操作页 interaction_contract 缺少 post_state")
        if not interaction_contract.get("result_evidence"):
            reasons.append("操作页 interaction_contract 缺少 result_evidence")
        if not actions:
            # The action is already part of the confirmed screen contract;
            # fill the minimal primary button locally instead of spending a
            # second model request on a recoverable omission.
            fallback_label = _text(expected.get("action") or expected_action, 24) or "执行操作"
            actions.append(
                {
                    "action_key": expected_action,
                    "label": fallback_label,
                    "variant": "primary",
                    "requires_confirmation": bool(expected.get("requires_confirmation")),
                }
            )

    normalized = {
        "schema_version": PAGE_SPEC_SCHEMA_VERSION,
        "page_key": page_key or expected_page_key,
        "page_kind": page_kind or expected_page_kind,
        "layout": layout or "table_workspace",
        "theme": {"density": density, "accent_variant": accent_variant},
        "regions": regions,
        "actions": actions,
        "interaction_contract": interaction_contract,
    }
    encoded = json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))
    if len(encoded) > PAGE_SPEC_MAX_CHARS:
        reasons.append(f"PageSpec 超过 {PAGE_SPEC_MAX_CHARS} 字符")
    if reasons:
        raise PageSpecValidationError(reasons)
    return normalized


def page_spec_cache_key(creative_key: str) -> str:
    source = f"{creative_key}|{PAGE_SPEC_SCHEMA_VERSION}|{COMPONENT_LIBRARY_VERSION}|{FRONTEND_ENGINE_VERSION}"
    return sha256(source.encode("utf-8")).hexdigest()


def page_spec_manifest() -> dict[str, str]:
    return {
        "frontend_engine_version": FRONTEND_ENGINE_VERSION,
        "page_spec_schema_version": PAGE_SPEC_SCHEMA_VERSION,
        "component_library_version": COMPONENT_LIBRARY_VERSION,
        "page_composition_version": PAGE_COMPOSITION_VERSION,
    }


def _normalize_region(raw: dict[str, Any], *, component: str, region_id: str) -> dict[str, Any]:
    title = _text(raw.get("title"), 36)
    region = {
        "id": region_id,
        "component": component,
        "title": title,
        "subtitle": _text(raw.get("subtitle"), 72),
        "columns": _column_list(raw.get("columns"), limit=7, text_limit=18, region_title=title),
        "fields": _normalize_named_items(raw.get("fields"), limit=8),
        "items": _normalize_items(raw.get("items"), limit=8),
        "metrics": _normalize_items(raw.get("metrics"), limit=4),
        "steps": _normalize_items(raw.get("steps"), limit=7),
        "series": _normalize_items(raw.get("series"), limit=6),
        "points": _normalize_items(raw.get("points"), limit=7),
    }
    # Keep labels compatible with v1 caches, while preserving explicit field bindings.
    column_keys = dict(raw.get("column_keys") or {}) if isinstance(raw.get("column_keys"), dict) else {}
    for column in raw.get("columns") or []:
        if isinstance(column, dict) and column.get("key"):
            label = _text(column.get("label") or column.get("title") or column.get("name") or column["key"], 18)
            column_keys[label] = _text(column["key"], 36)
    if column_keys:
        region["column_keys"] = {label: _text(column_keys[label], 36) for label in region["columns"] if label in column_keys}
    return region


def _normalize_login_regions(regions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    brand = next((dict(region) for region in regions if region.get("component") == "detail"), None)
    form = next((dict(region) for region in regions if region.get("component") == "form"), None)
    result: list[dict[str, Any]] = []
    if brand is not None:
        brand_items = list(brand.get("items") or [])
        preferred_items = [
            item
            for item in brand_items
            if any(term in str(item.get("label") or "") for term in ("名称", "版本"))
        ]
        brand["items"] = (preferred_items or brand_items)[:2]
        brand["fields"] = []
        brand["metrics"] = []
        brand["steps"] = []
        brand["series"] = []
        brand["points"] = []
        result.append(brand)
    if form is not None:
        form["fields"] = _normalize_login_fields(list(form.get("fields") or []))
        form["items"] = []
        form["metrics"] = []
        form["steps"] = []
        form["series"] = []
        form["points"] = []
        result.append(form)
    return result


def _normalize_login_fields(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    used_indexes: set[int] = set()
    for group in ("account", "password", "captcha", "context"):
        for index, field in enumerate(fields):
            if index in used_indexes:
                continue
            label = str(field.get("label") or "")
            if _login_field_matches(label, group):
                cleaned = dict(field)
                if group == "password":
                    cleaned["value"] = ""
                    cleaned["type"] = "password"
                selected.append(cleaned)
                used_indexes.add(index)
                break
    for index, field in enumerate(fields):
        if len(selected) >= LOGIN_MAX_FIELDS:
            break
        if index in used_indexes:
            continue
        label = str(field.get("label") or "")
        if any(term in label for term in ("记住", "忘记", "协议", "提示")):
            continue
        selected.append(dict(field))
    return selected[:LOGIN_MAX_FIELDS]


def _login_field_matches(label: str, group: str) -> bool:
    text = str(label or "").lower()
    terms = {
        "account": ("账号", "账户", "用户名", "手机号", "工号", "邮箱", "user", "account", "phone", "email"),
        "password": ("密码", "口令", "password", "passcode"),
        "captcha": ("验证码", "校验码", "captcha", "verification"),
        "context": ("角色", "岗位", "项目", "租户", "环境", "组织", "单位"),
    }
    return any(term in text for term in terms.get(group, ()))


def _normalize_interaction_contract(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "mode": _token(raw.get("mode"), 32),
        "action_key": _token(raw.get("action_key"), 64),
        "role": _text(raw.get("role"), 24),
        "trigger": _text(raw.get("trigger"), 72),
        "input_fields": _string_list(raw.get("input_fields"), limit=8, text_limit=24),
        "pre_state": _text(raw.get("pre_state"), 56),
        "post_state": _text(raw.get("post_state"), 56),
        "result_evidence": _text(raw.get("result_evidence"), 80),
        "requires_confirmation": bool(raw.get("requires_confirmation")),
    }


def _normalize_named_items(value: Any, *, limit: int) -> list[dict[str, str]]:
    items = _normalize_items(value, limit=limit)
    result: list[dict[str, str]] = []
    for index, item in enumerate(items, start=1):
        result.append(
            {
                "label": _text(item.get("label") or item.get("name") or item.get("title"), 24) or f"字段{index}",
                "value": _text(item.get("value") or item.get("placeholder"), 36),
                "type": _token(item.get("type"), 20) or "text",
            }
        )
    return result


def _normalize_items(value: Any, *, limit: int) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, str]] = []
    for raw in value[:limit]:
        if isinstance(raw, dict):
            item: dict[str, Any] = {}
            for key in ("label", "name", "title", "value", "status", "description", "meta", "category", "owner", "time"):
                text = _text(raw.get(key), 48 if key not in {"description"} else 90)
                if text:
                    item[key] = text
            for raw_key, raw_value in list(raw.items())[:16]:
                key = str(raw_key or "").strip()
                if not key or key in item or key in {"id", "component", "type"}:
                    continue
                if key == "points" and isinstance(raw_value, list):
                    item[key] = _normalize_items(raw_value, limit=7)
                    continue
                text = _text(raw_value, 64)
                if text:
                    item[key[:36]] = text
            if item:
                result.append(item)
        else:
            text = _text(raw, 48)
            if text:
                result.append({"label": text})
    return result


def _string_list(value: Any, *, limit: int, text_limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value[:limit]:
        text = _text(item, text_limit)
        if text and text not in result:
            result.append(text)
    return result


_COLUMN_KEY_LABELS = {
    "resident": "住户编号",
    "space": "关联房屋",
    "verify": "认证状态",
    "period": "有效期",
    "risk": "风险标记",
    "application": "申领编号",
    "holder": "持有人",
    "credential": "凭证类型",
    "lifecycle": "生命周期状态",
    "access_point": "适用门禁点",
    "validity": "有效期",
    "time": "通行时间",
    "occurred_at": "通行时间",
    "point": "门禁点",
    "method": "开门方式",
    "result": "开门结果",
    "device": "设备编号",
    "trace_id": "追踪号",
    "appointment": "预约编号",
    "visitor": "访客",
    "visit_time": "到访时段",
    "status": "状态",
    "draft": "草案编号",
    "conflict": "冲突标记",
    "review": "复核状态",
    "active": "生效状态",
}


def _column_list(
    value: Any,
    *,
    limit: int,
    text_limit: int,
    region_title: str = "",
) -> list[str]:
    """Normalize table columns without leaking Python dict representations.

    Older PageSpec caches were produced by calling ``str(dict)`` on column
    objects.  Those strings are incomplete (the value was truncated), so a
    title-based fallback is safer than rendering them as visible UI text.
    """
    if not isinstance(value, list):
        return []
    result: list[str] = []
    saw_corrupt_object = False
    for item in value[:limit]:
        if isinstance(item, dict):
            candidate = next(
                (item.get(key) for key in ("label", "title", "name", "key") if item.get(key)),
                "",
            )
            text = _text(candidate, text_limit)
        else:
            raw_text = _text(item, text_limit)
            if raw_text.startswith("{'key':") or raw_text.startswith('{\"key\":'):
                saw_corrupt_object = True
                key_match = re.search(r"key['\"]?\s*:\s*['\"]([^'\"]+)", str(item))
                key = key_match.group(1) if key_match else ""
                text = _COLUMN_KEY_LABELS.get(key, "")
            else:
                text = raw_text
        if text and text not in result:
            result.append(text)
    if saw_corrupt_object:
        fallback = _fallback_columns(region_title)
        if fallback:
            return fallback[:limit]
    return result


def repair_cached_page_spec_columns(page_spec: dict[str, Any]) -> int:
    """Repair columns in a cached PageSpec in place; return changed region count."""
    if not isinstance(page_spec, dict):
        return 0
    changed = 0
    for region in page_spec.get("regions") or []:
        if not isinstance(region, dict) or "columns" not in region:
            continue
        before = region.get("columns")
        after = _column_list(
            before,
            limit=7,
            text_limit=18,
            region_title=_text(region.get("title"), 36),
        )
        if before != after:
            bindings = {
                _text(col.get("label") or col.get("title") or col.get("name") or col.get("key"), 18): _text(col["key"], 36)
                for col in before or [] if isinstance(col, dict) and col.get("key")
            }
            if bindings:
                region["column_keys"] = bindings
            region["columns"] = after
            changed += 1
    return changed


def _fallback_columns(region_title: str) -> list[str]:
    title = str(region_title or "")
    if any(term in title for term in ("住户", "房屋", "居住")):
        return ["住户编号", "住户姓名", "关联房屋", "认证状态", "有效期"]
    if any(term in title for term in ("凭证", "申领")):
        return ["申领编号", "持有人", "凭证类型", "生命周期状态", "适用门禁点", "有效期"]
    if any(term in title for term in ("通行记录", "通行记录列表", "通行摘要")):
        return ["通行时间", "人员", "门禁点", "开门方式", "结果", "设备编号", "追踪号"]
    if any(term in title for term in ("访客", "预约")):
        return ["预约编号", "访客", "受访住户", "到访时段", "门禁点", "状态"]
    if any(term in title for term in ("授权", "审核看板")):
        return ["授权编号", "授权对象", "门禁范围", "通行时段", "授权状态", "有效期"]
    if any(term in title for term in ("门禁点", "设备")):
        return ["门禁点编号", "门禁点名称", "所属区域", "设备状态", "更新时间"]
    if any(term in title for term in ("告警", "异常")):
        return ["告警编号", "异常类型", "告警级别", "责任岗位", "处理状态", "触发时间"]
    return ["业务编号", "业务名称", "处理状态", "责任岗位", "更新时间"]


def _text(value: Any, limit: int, _depth: int = 0) -> str:
    if value is None or _depth > 4:
        return ""
    if isinstance(value, bool):
        return ("是" if value else "否")[:limit]
    if isinstance(value, dict):
        for key in ("label", "title", "name", "value", "status", "code", "key"):
            candidate = value.get(key)
            if candidate is not None and candidate != "":
                text = _text(candidate, limit, _depth + 1)
                if text:
                    return text
        values = [_text(candidate, limit, _depth + 1) for candidate in list(value.values())[:4]]
        return (" / ".join(candidate for candidate in values if candidate) or "业务数据")[:limit]
    if isinstance(value, (list, tuple, set)):
        values = [_text(candidate, limit, _depth + 1) for candidate in list(value)[:4]]
        text = "、".join(candidate for candidate in values if candidate)
        if len(value) > 4 and text:
            text += f"等{len(value)}项"
        return text[:limit]
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text[:limit]


def _token(value: Any, limit: int) -> str:
    return re.sub(r"[^a-z0-9_-]+", "_", str(value or "").strip().lower()).strip("_")[:limit]
