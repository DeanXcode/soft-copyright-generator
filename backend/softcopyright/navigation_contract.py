from __future__ import annotations

from hashlib import sha256
import re
from typing import Any


NAVIGATION_CONTRACT_VERSION = "navigation-contract-v1"


def build_navigation_contracts(
    task: Any,
    blueprint: Any,
    pages: list[dict[str, Any]],
    *,
    renderer: str,
    nav_model: str = "",
) -> dict[str, dict[str, Any]]:
    normalized_pages = [_page_payload(page) for page in pages if isinstance(page, dict) and _text(page.get("key"))]
    modules = [_module_payload(module) for module in (getattr(blueprint, "modules", []) or [])]
    module_by_key = {module["key"]: module for module in modules if module["key"]}
    page_by_key = {page["key"]: page for page in normalized_pages}
    main_page_by_module: dict[str, dict[str, Any]] = {}
    operations_by_module: dict[str, list[dict[str, Any]]] = {}
    for page in normalized_pages:
        module_key = page["module_key"]
        if not module_key:
            continue
        if page["page_kind"] == "module" and module_key not in main_page_by_module:
            main_page_by_module[module_key] = page
        elif page["page_kind"] == "operation":
            operations_by_module.setdefault(module_key, []).append(page)
    for module in modules:
        operations_by_module[module["key"]] = _merge_operation_pages(
            operations_by_module.get(module["key"], []),
            module,
        )

    dashboard_page = next((page for page in normalized_pages if page["page_kind"] == "dashboard"), None)
    statistics_page = next((page for page in normalized_pages if page["page_kind"] == "statistics"), None)
    primary_base, module_primary_keys = _primary_navigation(
        task,
        blueprint,
        modules,
        main_page_by_module,
        dashboard_page,
        statistics_page,
        renderer=renderer,
        nav_model=nav_model,
    )
    result: dict[str, dict[str, Any]] = {}
    for page in normalized_pages:
        module = module_by_key.get(page["module_key"], {})
        primary_items = [dict(item) for item in primary_base]
        active_primary_key = _active_primary_key(page, module_primary_keys, statistics_page)
        if active_primary_key and active_primary_key not in {item["key"] for item in primary_items} and module:
            module_page = main_page_by_module.get(module["key"], {})
            insert_at = max(1, len(primary_items) - (1 if statistics_page else 0))
            primary_items.insert(
                insert_at,
                {
                    "key": active_primary_key,
                    "label": _short_label(module["title"], 8),
                    "page_key": module_page.get("key") or module["key"],
                    "relation": "module",
                },
            )
        secondary_items = _secondary_navigation(
            page,
            module,
            operations_by_module.get(page["module_key"], []),
            dashboard_page=dashboard_page,
            statistics_page=statistics_page,
            blueprint=blueprint,
            renderer=renderer,
        )
        active_secondary_key = _active_secondary_key(page, secondary_items)
        breadcrumb = _breadcrumb(task, blueprint, page, module, primary_items, active_primary_key)
        back_target = _back_target(page, module, main_page_by_module, dashboard_page)
        level = _navigation_level(page)
        secondary_style = _secondary_style(page, renderer=renderer, nav_model=nav_model, module_key=page["module_key"])
        contract = {
            "schema_version": NAVIGATION_CONTRACT_VERSION,
            "page_key": page["key"],
            "level": level,
            "nav_model": _text(nav_model) or ("phone_tabs" if renderer in {"mobile_app", "game"} else "side_menu"),
            "primary_items": primary_items,
            "active_primary_key": active_primary_key,
            "secondary_items": secondary_items,
            "active_secondary_key": active_secondary_key,
            "secondary_style": secondary_style,
            "breadcrumb": breadcrumb,
            "back_target": back_target,
            "parent_page_key": _text(back_target.get("page_key")) if back_target else "",
            "ready": _contract_ready(level, primary_items, secondary_items, breadcrumb, back_target),
        }
        contract["hierarchy_signature"] = _hierarchy_signature(contract)
        result[page["key"]] = contract
    return result


def build_local_navigation_contract(
    task: Any,
    blueprint: Any,
    *,
    page_key: str,
    title: str,
    page_kind: str,
    module: Any | None = None,
    interaction_action: str = "",
    interaction_action_key: str = "",
    renderer: str = "admin",
    nav_model: str = "",
) -> dict[str, Any]:
    pages = navigation_page_catalog(blueprint, renderer=renderer)
    module_key = _text(getattr(module, "key", "")) if module is not None else ""
    current = {
        "key": page_key,
        "title": title,
        "page_kind": page_kind,
        "module_key": module_key,
        "interaction_action": interaction_action,
        "interaction_action_key": interaction_action_key,
    }
    pages = [page for page in pages if page["key"] != page_key]
    pages.append(current)
    return build_navigation_contracts(
        task,
        blueprint,
        pages,
        renderer=renderer,
        nav_model=nav_model,
    ).get(page_key, {})


def navigation_page_catalog(blueprint: Any, *, renderer: str = "admin") -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = [
        {"key": "dashboard", "title": "业务总览", "page_kind": "dashboard", "module_key": ""}
    ]
    operation_limit = 2 if renderer == "mobile_app" else 3
    for module_index, raw_module in enumerate((getattr(blueprint, "modules", []) or []), start=1):
        module = _module_payload(raw_module)
        if not module["key"]:
            continue
        pages.append(
            {
                "key": module["key"],
                "title": module["title"],
                "page_kind": "module",
                "module_key": module["key"],
            }
        )
        for operation_index, operation in enumerate(module["operations"][:operation_limit], start=1):
            action_key = _text(operation.get("action_key")) or f"operation_{operation_index}"
            action = _text(operation.get("label")) or f"功能{operation_index}"
            pages.append(
                {
                    "key": f"{module['key']}__{action_key}",
                    "title": f"{module['title']}-{action}",
                    "page_kind": "operation",
                    "module_key": module["key"],
                    "interaction_action": action,
                    "interaction_action_key": action_key,
                }
            )
    pages.append({"key": "statistics", "title": "统计分析", "page_kind": "statistics", "module_key": ""})
    return pages


def navigation_contract_summary(contracts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    values = [item for item in contracts.values() if isinstance(item, dict)]
    non_login = [item for item in values if item.get("level") != "auth"]
    action_pages = [item for item in values if item.get("level") == "action"]
    secondary_pages = [item for item in non_login if len(item.get("secondary_items") or []) >= 2]
    back_pages = [item for item in action_pages if isinstance(item.get("back_target"), dict) and item["back_target"].get("page_key")]
    return {
        "navigation_contract_version": NAVIGATION_CONTRACT_VERSION,
        "navigation_contract_count": len(values),
        "navigation_contract_ready_count": sum(1 for item in values if bool(item.get("ready"))),
        "navigation_contract_ready": bool(values) and all(bool(item.get("ready")) for item in values),
        "navigation_level_count": len({_text(item.get("level")) for item in values if _text(item.get("level"))}),
        "secondary_navigation_page_count": len(secondary_pages),
        "back_navigation_page_count": len(back_pages),
        "action_navigation_page_count": len(action_pages),
    }


def _page_payload(page: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": _text(page.get("key")),
        "title": _text(page.get("title")) or _text(page.get("key")),
        "page_kind": _text(page.get("page_kind")) or "general",
        "module_key": _text(page.get("module_key")),
        "interaction_action": _text(page.get("interaction_action")),
        "interaction_action_key": _text(page.get("interaction_action_key")),
        "interaction_mode": _text(page.get("interaction_mode")),
    }


def _module_payload(module: Any) -> dict[str, Any]:
    if isinstance(module, dict):
        get = module.get
    else:
        get = lambda name, default=None: getattr(module, name, default)
    operations: list[dict[str, str]] = []
    for index, raw in enumerate(get("operation_specs", []) or [], start=1):
        if not isinstance(raw, dict):
            continue
        label = _text(raw.get("label") or raw.get("action") or raw.get("name"))
        if not label:
            continue
        operations.append(
            {
                "action_key": _text(raw.get("action_key") or raw.get("key")) or f"operation_{index}",
                "label": label,
            }
        )
    if not operations:
        for index, raw in enumerate(get("operations", []) or [], start=1):
            label = _text(raw)
            if label:
                operations.append({"action_key": f"operation_{index}", "label": label})
    return {
        "key": _text(get("key", "")),
        "title": _text(get("title", "")) or "业务模块",
        "operations": operations,
    }


def _merge_operation_pages(pages: list[dict[str, Any]], module: dict[str, Any]) -> list[dict[str, Any]]:
    result = [dict(page) for page in pages]
    known_actions = {
        _text(page.get("interaction_action_key")) or _text(page.get("interaction_action"))
        for page in result
    }
    for operation in module.get("operations") or []:
        identity = _text(operation.get("action_key")) or _text(operation.get("label"))
        if not identity or identity in known_actions:
            continue
        result.append(
            {
                "key": f"{module['key']}__{identity}",
                "title": f"{module['title']}-{operation['label']}",
                "page_kind": "operation",
                "module_key": module["key"],
                "interaction_action": operation["label"],
                "interaction_action_key": operation["action_key"],
                "interaction_mode": "",
            }
        )
        known_actions.add(identity)
    return result


def _primary_navigation(
    task: Any,
    blueprint: Any,
    modules: list[dict[str, Any]],
    main_page_by_module: dict[str, dict[str, Any]],
    dashboard_page: dict[str, Any] | None,
    statistics_page: dict[str, Any] | None,
    *,
    renderer: str,
    nav_model: str,
) -> tuple[list[dict[str, str]], dict[str, str]]:
    dashboard_key = _text((dashboard_page or {}).get("key")) or "dashboard"
    items: list[dict[str, str]] = [
        {"key": "dashboard", "label": "首页" if renderer in {"mobile_app", "game"} else "业务总览", "page_key": dashboard_key, "relation": "root"}
    ]
    module_primary_keys: dict[str, str] = {}
    if renderer in {"mobile_app", "game"}:
        attendance_app = _text(getattr(blueprint, "industry_subtype_key", "")) == "workforce_attendance"
        group_order: list[str] = []
        group_labels: dict[str, str] = {}
        group_pages: dict[str, str] = {}
        for module in modules:
            group_key, group_label = _mobile_group(module)
            module_primary_keys[module["key"]] = group_key
            if group_key not in group_order:
                group_order.append(group_key)
                group_labels[group_key] = group_label
                group_pages[group_key] = _text(main_page_by_module.get(module["key"], {}).get("key")) or module["key"]
        if attendance_app:
            priority = ["group_action", "group_request"]
            group_order = [key for key in priority if key in group_order] + [key for key in group_order if key not in priority]
        for group_key in group_order[:2]:
            items.append({"key": group_key, "label": group_labels[group_key], "page_key": group_pages[group_key], "relation": "group"})
        if statistics_page:
            statistics_title = _text(statistics_page.get("title"))
            items.append(
                {
                    "key": "statistics",
                    "label": "我的" if attendance_app or re.search(r"个人|我的|设置", statistics_title) else "统计",
                    "page_key": _text(statistics_page.get("key")) or "statistics",
                    "relation": "analysis",
                }
            )
        return items[:4], module_primary_keys

    module_limit = 7 if nav_model == "side_menu" else 5
    for module in modules[:module_limit]:
        module_primary_keys[module["key"]] = module["key"]
        items.append(
            {
                "key": module["key"],
                "label": _short_label(module["title"], 8),
                "page_key": _text(main_page_by_module.get(module["key"], {}).get("key")) or module["key"],
                "relation": "module",
            }
        )
    if statistics_page:
        items.append(
            {
                "key": "statistics",
                "label": "统计分析",
                "page_key": _text(statistics_page.get("key")) or "statistics",
                "relation": "analysis",
            }
        )
    return items, module_primary_keys


def _mobile_group(module: dict[str, Any]) -> tuple[str, str]:
    text = f"{module['key']} {module['title']} {' '.join(item['label'] for item in module.get('operations') or [])}"
    profiles = [
        (r"补卡|请假|申请|审批|报销|工单|反馈", "group_request", "申请"),
        (r"打卡|考勤|排班|签到|巡检|采集", "group_action", "办理"),
        (r"地图|线路|导航|点位|定位|GIS", "group_map", "地图"),
        (r"课程|学习|歌曲|音乐|视频|内容|商品|服务", "group_content", "内容"),
        (r"统计|分析|报表|趋势|看板", "group_analysis", "分析"),
        (r"任务|流程|处置|整改|跟踪", "group_task", "任务"),
    ]
    for pattern, key, label in profiles:
        if re.search(pattern, text, flags=re.I):
            if key == "group_action" and re.search(r"打卡|考勤|排班|签到", text):
                label = "打卡"
            return key, label
    return "group_feature", "功能"


def _secondary_navigation(
    page: dict[str, Any],
    module: dict[str, Any],
    operations: list[dict[str, Any]],
    *,
    dashboard_page: dict[str, Any] | None,
    statistics_page: dict[str, Any] | None,
    blueprint: Any,
    renderer: str,
) -> list[dict[str, str]]:
    level = _navigation_level(page)
    if level in {"module", "action"} and module:
        items = [
            {
                "key": f"{module['key']}__overview",
                "label": "概览",
                "page_key": module["key"],
                "relation": "overview",
            }
        ]
        for operation in operations[: (3 if renderer in {"mobile_app", "game"} else 5)]:
            action_key = _text(operation.get("interaction_action_key")) or _text(operation.get("interaction_action")) or _text(operation.get("key"))
            label = _operation_label(operation, module["title"])
            items.append(
                {
                    "key": action_key,
                    "label": _short_label(label, 8),
                    "page_key": _text(operation.get("key")) or module["key"],
                    "relation": "operation",
                }
            )
        if len(items) < 2:
            items.append(
                {
                    "key": f"{module['key']}__detail",
                    "label": "业务明细",
                    "page_key": module["key"],
                    "relation": "detail",
                }
            )
        return _unique_navigation_items(items, limit=4 if renderer in {"mobile_app", "game"} else 6)
    if level == "root":
        workflow_label = "流程进度"
        workflows = getattr(blueprint, "workflows", []) or []
        if workflows and isinstance(workflows[0], dict):
            workflow_label = _short_label(_text(workflows[0].get("name")) or workflow_label, 8)
        metric_label = "指标概览"
        metrics = getattr(blueprint, "report_metrics", []) or []
        if metrics:
            metric_label = _short_label(_text(metrics[0]), 6) + "概览"
        return [
            {"key": "overview", "label": "业务总览", "page_key": _text((dashboard_page or {}).get("key")) or "dashboard", "relation": "view"},
            {"key": "workflow", "label": workflow_label, "page_key": _text((dashboard_page or {}).get("key")) or "dashboard", "relation": "view"},
            {"key": "metrics", "label": metric_label, "page_key": _text((dashboard_page or {}).get("key")) or "dashboard", "relation": "view"},
        ]
    if level == "analysis":
        return [
            {"key": "analysis_overview", "label": "指标总览", "page_key": _text((statistics_page or {}).get("key")) or "statistics", "relation": "view"},
            {"key": "analysis_trend", "label": "趋势对比", "page_key": _text((statistics_page or {}).get("key")) or "statistics", "relation": "view"},
            {"key": "analysis_detail", "label": "明细查询", "page_key": _text((statistics_page or {}).get("key")) or "statistics", "relation": "view"},
        ]
    return []


def _active_primary_key(page: dict[str, Any], module_primary_keys: dict[str, str], statistics_page: dict[str, Any] | None) -> str:
    if page["page_kind"] == "dashboard":
        return "dashboard"
    if page["page_kind"] == "statistics" or (statistics_page and page["key"] == statistics_page.get("key")):
        return "statistics"
    return module_primary_keys.get(page["module_key"], page["module_key"])


def _active_secondary_key(page: dict[str, Any], items: list[dict[str, str]]) -> str:
    if not items:
        return ""
    if page["page_kind"] == "module":
        return items[0]["key"]
    if page["page_kind"] == "operation":
        candidates = [page["interaction_action_key"], page["interaction_action"], page["key"]]
        for candidate in candidates:
            if candidate and any(item["key"] == candidate for item in items):
                return candidate
        action_token = _token(page["interaction_action"])
        for item in items:
            if action_token and action_token in _token(item["label"]):
                return item["key"]
    return items[0]["key"]


def _breadcrumb(
    task: Any,
    blueprint: Any,
    page: dict[str, Any],
    module: dict[str, Any],
    primary_items: list[dict[str, str]],
    active_primary_key: str,
) -> list[dict[str, str]]:
    software_name = _text(getattr(task, "software_name", "")) or _text(getattr(blueprint, "software_name", "")) or "软件首页"
    crumbs = [{"key": "software", "label": _short_label(software_name, 16), "page_key": "dashboard"}]
    primary_label = next((item["label"] for item in primary_items if item["key"] == active_primary_key), "")
    if page["page_kind"] == "dashboard":
        crumbs.append({"key": "dashboard", "label": "业务总览", "page_key": page["key"]})
    elif page["page_kind"] == "statistics":
        crumbs.append({"key": "statistics", "label": primary_label or "统计分析", "page_key": page["key"]})
    elif module:
        if primary_label and _token(primary_label) != _token(module["title"]):
            crumbs.append({"key": active_primary_key, "label": primary_label, "page_key": module["key"]})
        crumbs.append({"key": module["key"], "label": _short_label(module["title"], 14), "page_key": module["key"]})
        if page["page_kind"] == "operation":
            action = page["interaction_action"] or _operation_label(page, module["title"])
            crumbs.append({"key": page["key"], "label": _short_label(action, 12), "page_key": page["key"]})
    return _unique_navigation_items(crumbs, limit=4)


def _back_target(
    page: dict[str, Any],
    module: dict[str, Any],
    main_page_by_module: dict[str, dict[str, Any]],
    dashboard_page: dict[str, Any] | None,
) -> dict[str, str]:
    if page["page_kind"] == "operation" and module:
        module_page = main_page_by_module.get(module["key"], {})
        return {
            "page_key": _text(module_page.get("key")) or module["key"],
            "label": f"返回{_short_label(module['title'], 10)}",
        }
    if page["page_kind"] in {"module", "detail", "statistics"}:
        return {
            "page_key": _text((dashboard_page or {}).get("key")) or "dashboard",
            "label": "返回业务总览",
        }
    return {}


def _navigation_level(page: dict[str, Any]) -> str:
    level = {
        "login": "auth",
        "dashboard": "root",
        "module": "module",
        "operation": "action",
        "statistics": "analysis",
        "detail": "module",
    }.get(page["page_kind"])
    if level:
        return level
    return "module" if page.get("module_key") else "root"


def _secondary_style(page: dict[str, Any], *, renderer: str, nav_model: str, module_key: str) -> str:
    if renderer in {"mobile_app", "game"}:
        return "segmented" if page["page_kind"] in {"module", "operation"} else "tabs"
    options = ["tabs", "rail", "segmented"]
    seed = int(sha256(f"{module_key}|{page['page_kind']}|{nav_model}".encode("utf-8")).hexdigest()[:4], 16)
    return options[seed % len(options)]


def _operation_label(page: dict[str, Any], module_title: str) -> str:
    action = _text(page.get("interaction_action"))
    if action:
        return action
    title = _text(page.get("title"))
    if module_title and title.startswith(module_title):
        title = title[len(module_title) :].strip(" -—：:")
    return title or "功能操作"


def _contract_ready(
    level: str,
    primary_items: list[dict[str, str]],
    secondary_items: list[dict[str, str]],
    breadcrumb: list[dict[str, str]],
    back_target: dict[str, str],
) -> bool:
    if level == "auth":
        return True
    if len(primary_items) < 2 or len(breadcrumb) < 2:
        return False
    if level in {"root", "module", "analysis"} and len(secondary_items) < 2:
        return False
    if level == "action" and (len(secondary_items) < 2 or not back_target.get("page_key")):
        return False
    return True


def _hierarchy_signature(contract: dict[str, Any]) -> str:
    source = "|".join(
        [
            _text(contract.get("level")),
            _text(contract.get("active_primary_key")),
            _text(contract.get("active_secondary_key")),
            _text(contract.get("secondary_style")),
            ">".join(_text(item.get("key")) for item in contract.get("breadcrumb") or []),
        ]
    )
    return sha256(source.encode("utf-8")).hexdigest()[:16]


def _unique_navigation_items(items: list[dict[str, str]], *, limit: int) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in items:
        key = _text(item.get("key"))
        label = _text(item.get("label"))
        identity = key or _token(label)
        if not identity or not label or identity in seen:
            continue
        seen.add(identity)
        result.append({key_name: _text(value) for key_name, value in item.items() if _text(value)})
        if len(result) >= limit:
            break
    return result


def _short_label(value: Any, limit: int) -> str:
    text = re.sub(r"\s+", "", _text(value))
    text = re.sub(r"(?:智能管理平台|管理平台|管理系统|信息系统|工作台|界面|页面)$", "", text)
    return (text or "功能")[: max(2, limit)]


def _token(value: Any) -> str:
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", _text(value)).lower()


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()
