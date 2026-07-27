from __future__ import annotations

from hashlib import sha256
import json
import re
from typing import Any


PAGE_SPEC_SCHEMA_VERSION = "page-spec-v1"
COMPONENT_LIBRARY_VERSION = "page-components-v1"
FRONTEND_ENGINE_VERSION = "pagespec-hybrid-v1"
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
            reasons.append("操作页至少需要 1 个 action")

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
    }


def _normalize_region(raw: dict[str, Any], *, component: str, region_id: str) -> dict[str, Any]:
    region = {
        "id": region_id,
        "component": component,
        "title": _text(raw.get("title"), 36),
        "subtitle": _text(raw.get("subtitle"), 72),
        "columns": _string_list(raw.get("columns"), limit=7, text_limit=18),
        "fields": _normalize_named_items(raw.get("fields"), limit=8),
        "items": _normalize_items(raw.get("items"), limit=8),
        "metrics": _normalize_items(raw.get("metrics"), limit=4),
        "steps": _normalize_items(raw.get("steps"), limit=7),
        "series": _normalize_items(raw.get("series"), limit=6),
        "points": _normalize_items(raw.get("points"), limit=7),
    }
    return region


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


def _normalize_items(value: Any, *, limit: int) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, str]] = []
    for raw in value[:limit]:
        if isinstance(raw, dict):
            item: dict[str, str] = {}
            for key in ("label", "name", "title", "value", "status", "description", "meta", "category", "owner", "time"):
                text = _text(raw.get(key), 48 if key not in {"description"} else 90)
                if text:
                    item[key] = text
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


def _text(value: Any, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


def _token(value: Any, limit: int) -> str:
    return re.sub(r"[^a-z0-9_-]+", "_", str(value or "").strip().lower()).strip("_")[:limit]
