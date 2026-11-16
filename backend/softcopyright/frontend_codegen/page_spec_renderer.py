from __future__ import annotations

import colorsys
from html import escape
import math
import re
from typing import Any

from .page_composition import build_page_composition_contract
from .page_spec_semantics import page_spec_semantic_profile, sanitize_page_spec_semantics
from .reference_style import component_style_css


def render_page_spec(
    spec: dict[str, Any],
    *,
    css_scope: str,
    creative_key: str,
    renderer: str,
    module: dict[str, Any] | None,
    screen: dict[str, Any],
    visual_identity: dict[str, Any] | None,
    color_contract: dict[str, Any] | None,
) -> dict[str, Any]:
    module = module if isinstance(module, dict) else {}
    spec, _semantic_replacements = sanitize_page_spec_semantics(spec, module=module, screen=screen)
    title = _text(screen.get("title") or module.get("title") or spec.get("page_key") or "业务工作台")
    composition = build_page_composition_contract(
        spec,
        renderer=renderer,
        creative_key=creative_key,
        screen=screen,
    )
    design_viewer = _is_design_viewer_screen(screen, module, visual_identity or {})
    if design_viewer and str(renderer or "") == "admin" and str(spec.get("page_kind") or "") != "login":
        jsx = _render_design_viewer_page_spec(
            spec,
            css_scope=css_scope,
            creative_key=creative_key,
            module=module,
            screen=screen,
            title=title,
            composition=composition,
        )
        css = _page_spec_css(
            css_scope=css_scope,
            renderer=renderer,
            visual_identity=visual_identity or {},
            color_contract=color_contract or {},
            design_viewer=True,
        )
        return {"jsx": jsx, "css": css, "composition_contract": composition}
    if str(spec.get("page_kind") or "") == "login":
        jsx = _render_login_page_spec(
            spec,
            css_scope=css_scope,
            creative_key=creative_key,
            renderer=renderer,
            screen=screen,
            title=title,
            composition=composition,
        )
        css = _page_spec_css(
            css_scope=css_scope,
            renderer=renderer,
            visual_identity=visual_identity or {},
            color_contract=color_contract or {},
            design_viewer=False,
        )
        return {"jsx": jsx, "css": css, "composition_contract": composition}
    composition_slots = {
        str(item.get("region_id") or ""): item
        for item in composition.get("region_slots") or []
        if isinstance(item, dict)
    }
    regions = "".join(
        _render_region(
            region,
            module=module,
            screen=screen,
            index=index,
            composition_slot=composition_slots.get(str(region.get("id") or ""), {}),
        )
        for index, region in enumerate(spec.get("regions") or [], start=1)
        if isinstance(region, dict)
    )
    actions = _render_actions(spec.get("actions") or [], screen=screen)
    confirmation = _render_confirmation_source(spec.get("interaction_contract") or {}, screen=screen, module=module)
    layout = _token(spec.get("layout") or "table_workspace")
    density = _token((spec.get("theme") or {}).get("density") or "comfortable")
    terminal_class = "page-spec-mobile" if str(renderer or "") in {"mobile_app", "game"} else "page-spec-desktop"
    composition_variant = _token(composition.get("variant") or "balanced-grid")
    page_kind_class = f"page-kind-{_token(spec.get('page_kind') or 'module')}"
    jsx = (
        f'<div className="screen-root {css_scope} page-spec-root {terminal_class} {page_kind_class} layout-{layout} density-{density} composition-{composition_variant}" '
        f'data-page-structure="{_attr(creative_key)}" data-page-spec="page-spec-v1" '
        f'data-page-composition-version="{_attr(composition.get("version"))}" '
        f'data-page-composition="{_attr(composition_variant)}" '
        f'data-composition-signature="{_attr(composition.get("signature"))}">'
        '<section className="page-spec-heading">'
        '<div className="page-spec-heading-copy">'
        f'<h1>{_jsx_text(title)}</h1>'
        '<div className="page-spec-data-source runtime-record-panel"><span>关联记录：</span>'
        '<span data-runtime-field="code">等待加载</span><span data-runtime-field="name"></span></div>'
        '</div>'
        f'{actions}</section>'
        f'<main className="page-spec-workspace">{regions}</main>'
        f'{confirmation}</div>'
    )
    css = _page_spec_css(
        css_scope=css_scope,
        renderer=renderer,
        visual_identity=visual_identity or {},
        color_contract=color_contract or {},
        design_viewer=False,
    )
    return {"jsx": jsx, "css": css, "composition_contract": composition}


def _is_design_viewer_screen(
    screen: dict[str, Any],
    module: dict[str, Any],
    visual_identity: dict[str, Any],
) -> bool:
    if str(screen.get("industry_subtype_key") or "") == "design_viewer":
        return True
    text = " ".join(
        [
            _text(screen.get("software_name") or ""),
            _text(screen.get("title") or ""),
            _text(module.get("title") or ""),
            _text(module.get("description") or ""),
            _text(visual_identity.get("identity_signature") or ""),
        ]
    )
    return "Figma" in text or sum(term in text for term in ("设计文件", "页面画板", "图层组件", "设计评审")) >= 2


def _render_design_viewer_page_spec(
    spec: dict[str, Any],
    *,
    css_scope: str,
    creative_key: str,
    module: dict[str, Any],
    screen: dict[str, Any],
    title: str,
    composition: dict[str, Any],
) -> str:
    regions = [item for item in spec.get("regions") or [] if isinstance(item, dict)]
    resource_names = _design_viewer_resource_names(regions, module, title)
    resource_rows = "".join(
        f'<button className="design-resource-row{" active" if index == 0 else ""}" title="{_attr(name)}">'
        f'<span>{"◆" if index == 0 else "▱"}</span><b>{_jsx_text(name)}</b></button>'
        for index, name in enumerate(resource_names[:8])
    )
    artboard_names = resource_names[:4] or [title]
    artboards = "".join(
        '<article className="design-artboard">'
        f'<header><span>{_jsx_text(name)}</span><b>{1280 - (index * 80)} x {720 - (index * 40)}</b></header>'
        '<div className="design-artboard-preview">'
        '<i className="preview-nav"></i><i className="preview-hero"></i>'
        '<span></span><span></span><span></span><em></em><em></em>'
        '</div></article>'
        for index, name in enumerate(artboard_names)
    )
    actions = _render_actions(spec.get("actions") or [], screen=screen)
    module_title = _text(module.get("title") or title)
    action_name = _text(screen.get("interaction_action") or "")
    inspector_rows = [
        ("页面", title),
        ("模块", module_title),
        ("状态", _text(screen.get("interaction_post_state") or "可评审")),
    ]
    if action_name:
        inspector_rows.append(("当前操作", action_name))
    properties = "".join(
        f'<div className="design-property"><span>{_jsx_text(label)}</span><strong>{_jsx_text(value)}</strong></div>'
        for label, value in inspector_rows
        if value
    )
    confirmation = _render_confirmation_source(spec.get("interaction_contract") or {}, screen=screen, module=module)
    variant = _token(composition.get("variant") or "balanced-grid")
    return (
        f'<div className="screen-root {css_scope} page-spec-root page-spec-desktop design-viewer-screen composition-{variant}" '
        f'data-page-structure="{_attr(creative_key)}" data-page-spec="page-spec-v1" '
        'data-design-viewer-workspace="true">'
        '<aside className="design-resource-panel">'
        '<header><strong>资源</strong><button title="新建资源" aria-label="新建资源">+</button></header>'
        '<label className="design-resource-search"><span>⌕</span><input placeholder="搜索文件或页面" /></label>'
        '<nav><small>团队空间</small>'
        f'{resource_rows}</nav></aside>'
        '<main className="design-canvas-panel">'
        '<header className="design-canvas-toolbar"><div>'
        '<button title="选择工具" aria-label="选择工具">↖</button><button title="框架工具" aria-label="框架工具">#</button>'
        f'<h1>{_jsx_text(title)}</h1></div>{actions}</header>'
        f'<section className="design-canvas-stage">{artboards}</section>'
        '<footer><span>画布</span><span>100%</span><button title="缩小" aria-label="缩小">−</button><button title="放大" aria-label="放大">+</button></footer>'
        '</main>'
        '<aside className="design-inspector-panel">'
        '<nav><button className="active">设计</button><button>原型</button><button>检查</button></nav>'
        '<section><h2>属性</h2>'
        f'{properties}</section>'
        '<section><h2>评审</h2><div className="design-review-state"><span></span><strong>待处理评论</strong><b>3</b></div></section>'
        '</aside>'
        f'{confirmation}</div>'
    )


def _design_viewer_resource_names(
    regions: list[dict[str, Any]],
    module: dict[str, Any],
    title: str,
) -> list[str]:
    candidates = [title]
    candidates.extend(_text(item.get("title") or "") for item in regions)
    candidates.extend(_text(item) for item in list(module.get("pages") or [])[:5])
    result: list[str] = []
    for value in candidates:
        cleaned = value.strip()
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return result


def _render_login_page_spec(
    spec: dict[str, Any],
    *,
    css_scope: str,
    creative_key: str,
    renderer: str,
    screen: dict[str, Any],
    title: str,
    composition: dict[str, Any],
) -> str:
    regions = [region for region in spec.get("regions") or [] if isinstance(region, dict)]
    brand_region = next((region for region in regions if _token(region.get("component")) == "detail"), {})
    form_region = next((region for region in regions if _token(region.get("component")) == "form"), {})
    brand_items = list(brand_region.get("items") or [])
    product_name = _login_item_value(brand_items, ("平台名称", "软件名称", "系统名称", "产品名称"))
    if not product_name:
        brand_title = _text(brand_region.get("title") or "")
        product_name = brand_title if brand_title and "登录" not in brand_title else title
    version = _login_item_value(brand_items, ("当前版本", "软件版本", "版本"))
    fields = _login_fields_for_render(list(form_region.get("fields") or []))
    if not fields:
        fields = [
            {"label": "账号", "value": "", "type": "text"},
            {"label": "密码", "value": "", "type": "password"},
            {"label": "图形验证码", "value": "7K4P", "type": "text"},
        ]
    form_fields = "".join(_render_login_field(field, index=index) for index, field in enumerate(fields, start=1))
    action = next((item for item in spec.get("actions") or [] if isinstance(item, dict)), {})
    action_key = _text(action.get("action_key") or screen.get("interaction_action_key") or "submit_login")
    action_label = _login_action_label(action.get("label") or screen.get("interaction_action") or "登录系统")
    terminal_class = "page-spec-mobile" if str(renderer or "") in {"mobile_app", "game"} else "page-spec-desktop"
    composition_variant = _token(composition.get("variant") or "detail-rail")
    version_badge = f'<span className="login-version">{_jsx_text(version)}</span>' if version else ""
    return (
        f'<div className="screen-root {css_scope} page-spec-root page-spec-login {terminal_class} layout-login_workspace composition-{composition_variant}" '
        f'data-page-structure="{_attr(creative_key)}" data-page-spec="page-spec-v1" '
        f'data-page-composition-version="{_attr(composition.get("version"))}" '
        f'data-page-composition="{_attr(composition_variant)}" '
        f'data-composition-signature="{_attr(composition.get("signature"))}">'
        '<main className="login-shell">'
        '<section className="login-brand-panel">'
        '<div className="login-brand-mark">软</div>'
        '<div className="login-brand-copy">'
        f'<h1>{_jsx_text(product_name)}</h1>'
        f'{version_badge}</div></section>'
        '<section className="login-card">'
        '<header><h2>用户登录</h2></header>'
        f'<div className="login-form">{form_fields}'
        '<div className="login-assistance"><label><input type="checkbox" />记住账号</label><button type="button">忘记密码</button></div>'
        f'<button className="login-submit" data-action="{_attr(action_key)}">{_jsx_text(action_label)}</button>'
        '</div>'
        '</section></main></div>'
    )


def _login_fields_for_render(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    used_indexes: set[int] = set()
    groups = (
        ("account", ("账号", "账户", "用户名", "手机号", "工号", "邮箱", "user", "account", "phone", "email")),
        ("password", ("密码", "口令", "password", "passcode")),
        ("captcha", ("验证码", "校验码", "captcha", "verification")),
        ("context", ("角色", "岗位", "项目", "租户", "环境", "组织", "单位")),
    )
    for group, terms in groups:
        for index, field in enumerate(fields):
            if index in used_indexes:
                continue
            label = _text(field.get("label") or "")
            if any(term in label.lower() for term in terms):
                cleaned = dict(field)
                cleaned["login_group"] = group
                if group == "password":
                    cleaned["value"] = ""
                    cleaned["type"] = "password"
                selected.append(cleaned)
                used_indexes.add(index)
                break
    for index, field in enumerate(fields):
        if len(selected) >= 4:
            break
        if index in used_indexes:
            continue
        label = _text(field.get("label") or "")
        if any(term in label for term in ("记住", "忘记", "协议", "提示")):
            continue
        selected.append(dict(field))
    return selected[:4]


def _render_login_field(field: dict[str, Any], *, index: int) -> str:
    label = _text(field.get("label") or f"登录字段{index}")
    group = str(field.get("login_group") or "")
    value = _text(field.get("value") or "")
    if group == "password" or "密码" in label:
        input_type = "password"
        placeholder = "请输入密码"
    elif group == "account" or any(term in label for term in ("账号", "用户名", "手机号", "工号", "邮箱")):
        input_type = "text"
        placeholder = f"请输入{label}"
    elif group == "captcha" or "验证码" in label or "校验码" in label:
        code = value or "7K4P"
        return (
            '<label className="login-field login-captcha">'
            f'<span>{_jsx_text(label)}</span><div><input type="text" placeholder="请输入验证码" />'
            f'<button type="button" aria-label="刷新验证码">{_jsx_text(code)}</button></div></label>'
        )
    elif group == "context" or any(term in label for term in ("角色", "岗位", "项目", "租户", "环境", "组织", "单位")):
        option = value or f"请选择{label}"
        return (
            '<label className="login-field">'
            f'<span>{_jsx_text(label)}</span><select><option>{_jsx_text(option)}</option></select></label>'
        )
    else:
        input_type = _token(field.get("type") or "text") or "text"
        placeholder = f"请输入{label}"
    return (
        '<label className="login-field">'
        f'<span>{_jsx_text(label)}</span><input type="{_attr(input_type)}" placeholder="{_attr(placeholder)}" /></label>'
    )


def _login_item_value(items: list[dict[str, Any]], labels: tuple[str, ...]) -> str:
    for item in items:
        label = _text(item.get("label") or item.get("name") or "")
        if any(term in label for term in labels):
            return _text(item.get("value") or item.get("title") or "")
    return ""


def _login_action_label(value: Any) -> str:
    label = _text(value)
    if label in {"登录", "登录系统", "进入系统", "进入应用", "提交登录"}:
        return label
    return "登录系统"


def _render_region(
    region: dict[str, Any],
    *,
    module: dict[str, Any],
    screen: dict[str, Any],
    index: int,
    composition_slot: dict[str, Any],
) -> str:
    component = _token(region.get("component"))
    title = _text(region.get("title") or _component_title(component, module, screen))
    heading = (
        '<header className="region-heading">'
        f'<div><h2>{_jsx_text(title)}</h2></div>'
        '</header>'
    )
    body_renderer = {
        "filter_bar": _render_filter_bar,
        "metric_group": _render_metric_group,
        "data_table": _render_data_table,
        "form": _render_form,
        "detail": _render_detail,
        "workflow": _render_workflow,
        "timeline": _render_timeline,
        "kanban": _render_kanban,
        "chart": _render_chart,
        "map_panel": _render_map,
        "relationship_graph": _render_relationship_graph,
        "mobile_list": _render_mobile_list,
        "operation_result": _render_operation_result,
    }.get(component, _render_detail)
    body = body_renderer(region, module=module, screen=screen)
    slot = _token(composition_slot.get("slot") or "secondary-four")
    order = int(composition_slot.get("order") or index * 10)
    return (
        f'<section className="page-region region-{component} composition-slot-{slot}" '
        'data-page-data="spec" '
        f'data-region-id="{_attr(region.get("id") or component)}" data-composition-slot="{_attr(slot)}" '
        f'data-composition-order="{order}">{heading}{body}</section>'
    )


def _render_filter_bar(region: dict[str, Any], *, module: dict[str, Any], screen: dict[str, Any]) -> str:
    fields = region.get("fields") or _default_fields(module, screen=screen, limit=4)
    controls = "".join(
        '<label className="filter-control">'
        f'<span>{_jsx_text(item.get("label") or f"条件{index}")}</span>'
        f'<input placeholder="{_attr(item.get("value") or _sample_value(item.get("label"), index, module=module, screen=screen))}" />'
        '</label>'
        for index, item in enumerate(fields[:8], start=1)
    )
    return (
        '<div className="filter-bar">'
        f'{controls}'
        '<button className="filter-submit" type="button" title="筛选" aria-label="筛选">'
        '<span className="page-action-icon" data-icon="⌕" aria-hidden="true"></span><span className="page-action-label">筛选</span>'
        '</button>'
        '<button className="filter-reset" type="button" title="重置" aria-label="重置">'
        '<span className="page-action-icon" data-icon="↻" aria-hidden="true"></span><span className="page-action-label">重置</span>'
        '</button>'
        '</div>'
    )


def _render_metric_group(region: dict[str, Any], *, module: dict[str, Any], screen: dict[str, Any]) -> str:
    metrics = region.get("metrics") or region.get("items") or _default_metrics(module, screen)
    cards = "".join(
        '<article className="metric-card">'
        f'<span>{_jsx_text(item.get("label") or item.get("title") or f"指标{index}")}</span>'
        f'<strong>{_jsx_text(item.get("value") if item.get("value") not in (None, "") else "—")}</strong>'
        f'{_optional_element("small", item.get("description") or item.get("status") or item.get("meta"))}'
        '</article>'
        for index, item in enumerate(metrics[:4], start=1)
    )
    return f'<div className="metric-grid">{cards}</div>'


def _render_data_table(region: dict[str, Any], *, module: dict[str, Any], screen: dict[str, Any]) -> str:
    columns = list(region.get("columns") or [])[:7] or _default_columns(module, screen=screen)
    items = list(region.get("items") or [])[:5]
    if not items:
        items = _default_rows(module, columns, screen=screen)
    head = "".join(f'<th>{_jsx_text(column)}</th>' for column in columns)
    rows = "".join(
        '<tr>'
        + "".join(
            f'<td>{_jsx_text(_row_value(item, column, row_index, column_index, module=module, screen=screen, column_key=(region.get("column_keys") or {}).get(column)))}</td>'
            for column_index, column in enumerate(columns)
        )
        + '</tr>'
        for row_index, item in enumerate(items, start=1)
    )
    return f'<div className="table-frame"><table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table></div>'


def _render_form(region: dict[str, Any], *, module: dict[str, Any], screen: dict[str, Any]) -> str:
    fields = region.get("fields") or _default_fields(module, screen=screen, limit=6)
    form_fields = "".join(
        '<label className="form-field">'
        f'<span>{_jsx_text(item.get("label") or f"业务字段{index}")}</span>'
        f'<input placeholder="{_attr(item.get("value") or _sample_value(item.get("label"), index, module=module, screen=screen))}" />'
        '</label>'
        for index, item in enumerate(fields[:6], start=1)
    )
    return f'<div className="business-form">{form_fields}</div>'


def _render_detail(region: dict[str, Any], *, module: dict[str, Any], screen: dict[str, Any]) -> str:
    items = region.get("items") or _default_detail_items(module, screen=screen)
    details = "".join(
        '<div className="detail-item">'
        f'<span>{_jsx_text(item.get("label") or item.get("name") or f"属性{index}")}</span>'
        f'<strong>{_jsx_text(item.get("value") or item.get("status") or _sample_value(item.get("label"), index, module=module, screen=screen))}</strong>'
        '</div>'
        for index, item in enumerate(items[:8], start=1)
    )
    return f'<div className="runtime-record-panel">{details}</div>'


def _render_workflow(region: dict[str, Any], *, module: dict[str, Any], screen: dict[str, Any]) -> str:
    steps = region.get("steps") or _default_workflow_steps(module, screen)
    nodes = "".join(
        '<article className="workflow-step">'
        f'<span>{index}</span><div><strong>{_jsx_text(item.get("label") or item.get("title") or f"步骤{index}")}</strong>'
        f'<small>{_jsx_text(item.get("status") or item.get("description") or "按流程执行")}</small></div></article>'
        for index, item in enumerate(steps[:7], start=1)
    )
    return f'<div className="workflow-board">{nodes}</div>'


def _render_timeline(region: dict[str, Any], *, module: dict[str, Any], screen: dict[str, Any]) -> str:
    items = region.get("items") or region.get("steps") or _default_timeline_items(module, screen)
    nodes = "".join(
        '<article className="timeline-item">'
        f'<time>{_jsx_text(item.get("time") or f"{8 + index:02d}:00")}</time>'
        f'<div><strong>{_jsx_text(item.get("label") or item.get("title") or f"状态节点{index}")}</strong>'
        f'<p>{_jsx_text(item.get("description") or item.get("status") or "状态变化已记录")}</p></div></article>'
        for index, item in enumerate(items[:6], start=1)
    )
    return f'<div className="timeline">{nodes}</div>'


def _render_kanban(region: dict[str, Any], *, module: dict[str, Any], screen: dict[str, Any]) -> str:
    items = region.get("items") or _default_kanban_items(module, screen)
    columns: dict[str, list[dict[str, str]]] = {}
    for item in items[:8]:
        columns.setdefault(item.get("category") or item.get("status") or "处理中", []).append(item)
    html = ""
    for category, values in list(columns.items())[:4]:
        cards = "".join(
            f'<article><strong>{_jsx_text(item.get("label") or item.get("title") or "业务任务")}</strong><span>{_jsx_text(item.get("owner") or item.get("meta") or "责任岗位")}</span></article>'
            for item in values[:3]
        )
        html += f'<section className="kanban-column"><header><span>{_jsx_text(category)}</span><b>{len(values)}</b></header>{cards}</section>'
    return f'<div className="kanban-board">{html}</div>'


def _render_chart(region: dict[str, Any], *, module: dict[str, Any], screen: dict[str, Any]) -> str:
    series = region.get("series") or region.get("points") or region.get("items") or []
    groups = series if any("points" in item for item in series) else [{"points": series}]
    panels = []
    for group in groups[:6]:
        raw_points = group.get("points") or []
        incomplete = False
        if isinstance(raw_points, str):
            # Old caches flattened and truncated point objects. Recover only complete
            # label/number pairs; never infer a missing final value.
            parsed = []
            for fragment in raw_points.split("、"):
                pair = fragment.rsplit(" / ", 1)
                if len(pair) == 2 and _chart_number(pair[1]) is not None:
                    parsed.append({"label": pair[0], "value": pair[1]})
                else:
                    incomplete = True
            raw_points = parsed
        values = []
        for point in raw_points[:7] if isinstance(raw_points, list) else []:
            if not isinstance(point, dict):
                incomplete = True
                continue
            value = _chart_number(point.get("value"))
            if value is None:
                incomplete = True
                continue
            values.append((point, value))
        low = min([0.0] + [value for _, value in values])
        high = max([0.0] + [value for _, value in values])
        extent = high - low or 1.0
        zero = -low / extent * 100
        bars = ""
        for point, value in values:
            height = abs(value) / extent * 100
            bottom = (min(0, value) - low) / extent * 100
            bars += (
                '<div className="chart-column">'
                f'<span className="chart-value">{_jsx_text(point["value"])}</span>'
                f'<div className="chart-bar-track" style={{{{backgroundPosition:"0 {100-zero:.4f}%"}}}}>'
                f'<i className="chart-bar" data-chart-value="{value:g}" '
                f'style={{{{height:"{height:.4f}%",bottom:"{bottom:.4f}%"}}}}></i></div>'
                f'<small>{_jsx_text(point.get("label") or point.get("name") or "未标注")}</small></div>'
            )
        note = "暂无有效数值" if not values else ("历史数据不完整，仅展示可识别数据" if incomplete else "")
        panels.append(
            '<section className="chart-series">'
            f'{_optional_element("h3", group.get("name") or group.get("label"))}'
            f'{_optional_element("p", note)}'
            f'<div className="chart-panel"><div className="chart-grid-lines"></div><div className="chart-columns">{bars}</div></div></section>'
        )
    return '<div className="chart-series-list">' + "".join(panels) + '</div>'


def _chart_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)%?", text):
        return None
    number = float(text.rstrip("%"))
    return number if math.isfinite(number) else None


def _render_map(region: dict[str, Any], *, module: dict[str, Any], screen: dict[str, Any]) -> str:
    points = region.get("points") or region.get("items") or _default_map_points(module, screen)
    pins = "".join(
        f'<button className="map-pin map-pin-{min(index, 7)}"><span>{index}</span><b>{_jsx_text(item.get("label") or f"业务点位{index}")}</b><small>{_jsx_text(item.get("status") or "在线")}</small></button>'
        for index, item in enumerate(points[:7], start=1)
    )
    return f'<div className="map-workspace"><div className="map-grid"></div>{pins}<aside><strong>区域状态</strong><span>在线点位 {len(points[:7])}</span><span>数据同步正常</span></aside></div>'


def _render_relationship_graph(region: dict[str, Any], *, module: dict[str, Any], screen: dict[str, Any]) -> str:
    items = region.get("items") or _default_relationship_items(module, screen)
    nodes = "".join(
        f'<article className="graph-node graph-node-{min(index, 6)}"><span>{_jsx_text(item.get("category") or "对象")}</span><strong>{_jsx_text(item.get("label") or item.get("title") or f"关联对象{index}")}</strong></article>'
        for index, item in enumerate(items[:6], start=1)
    )
    return f'<div className="relationship-graph"><div className="graph-links"></div>{nodes}</div>'


def _render_mobile_list(region: dict[str, Any], *, module: dict[str, Any], screen: dict[str, Any]) -> str:
    items = region.get("items") or _default_rows(module, ["任务", "状态", "责任人"], screen=screen)
    cards = "".join(
        '<article className="mobile-list-item">'
        f'<div><strong>{_jsx_text(item.get("label") or item.get("title") or f"现场任务{index}")}</strong>'
        f'{_optional_element("span", item.get("description") or item.get("owner"))}</div>'
        f'<b>{_jsx_text(item.get("status") or "进行中")}</b></article>'
        for index, item in enumerate(items[:7], start=1)
    )
    return f'<div className="mobile-list">{cards}</div>'


def _render_operation_result(region: dict[str, Any], *, module: dict[str, Any], screen: dict[str, Any]) -> str:
    profile = page_spec_semantic_profile(module, screen)
    items = region.get("items") or _default_operation_result_items(module, screen)
    content = "".join(
        f'<div><span>{_jsx_text(item.get("label") or f"结果{index}")}</span><strong>{_jsx_text(item.get("value") or item.get("status") or "已记录")}</strong></div>'
        for index, item in enumerate(items[:6], start=1)
    )
    action_value = screen.get("interaction_action") or (profile["actions"][0] if profile["actions"] else profile["action_verb"])
    action = _text(action_value)
    return f'<div className="operation-result"><header><span>✓</span><div><strong>{_jsx_text(action)}已完成</strong></div></header><section>{content}</section></div>'


def _render_actions(actions: list[dict[str, Any]], *, screen: dict[str, Any]) -> str:
    if not actions:
        return ""
    buttons = "".join(_render_action_button(item, index=index) for index, item in enumerate(actions[:6], start=1))
    return f'<div className="page-spec-actions">{buttons}</div>'


def _render_action_button(item: dict[str, Any], *, index: int) -> str:
    full_label = _text(item.get("label") or f"操作{index}")
    action_key = _text(item.get("action_key") or f"action_{index}")
    short_label = _action_short_label(full_label, action_key)
    icon = _action_icon(full_label, action_key)
    variant = _token(item.get("variant") or "secondary")
    return (
        f'<button type="button" className="page-action action-{variant}" data-action="{_attr(action_key)}" '
        f'title="{_attr(full_label)}" aria-label="{_attr(full_label)}">'
        f'<span className="page-action-icon" data-icon="{_attr(icon)}" aria-hidden="true"></span>'
        f'<span className="page-action-label">{_jsx_text(short_label)}</span>'
        '</button>'
    )


def _action_short_label(label: str, action_key: str = "") -> str:
    """Keep visible actions scannable while retaining the full semantic label in title/aria-label."""
    normalized = re.sub(r"\s+", "", _text(label))
    known = {
        "筛选待创建任务的资源": "筛选",
        "调整目标文件名称": "改名",
        "选择并检查保存位置": "保存位置",
        "配置任务执行参数": "参数",
        "确认创建单个或批量任务": "创建任务",
        "打开当前团队中名称非常长的设计文件并进入评审": "打开文件",
        "查询文件访问状态": "查询",
        "返回上级": "返回",
    }
    if normalized in known:
        return known[normalized]
    if len(normalized) <= 7:
        return normalized or "操作"
    for prefix, short in (("确认", "确认"), ("提交", "提交"), ("创建", "创建"), ("新增", "新增"), ("打开", "打开"), ("查看", "查看"), ("编辑", "编辑"), ("删除", "删除"), ("导出", "导出"), ("下载", "下载"), ("刷新", "刷新"), ("重试", "重试")):
        if normalized.startswith(prefix):
            remainder = normalized[len(prefix):]
            return f"{prefix}{remainder[:4]}" if remainder else prefix
    key_hint = re.sub(r"[_-]+", " ", action_key).strip()
    return key_hint[:7] or normalized[:7] or "操作"


def _action_icon(label: str, action_key: str = "") -> str:
    text = f"{_text(action_key)} {_text(label)}".lower()
    icon_rules = (
        (("筛选", "查询", "search", "filter"), "⌕"),
        (("刷新", "重试", "refresh", "retry"), "↻"),
        (("创建", "新增", "添加", "新建", "create", "add"), "＋"),
        (("保存", "导出", "下载", "save", "export", "download"), "↓"),
        (("删除", "移除", "delete", "remove"), "×"),
        (("编辑", "修改", "改名", "edit", "rename"), "✎"),
        (("设置", "参数", "配置", "setting", "config"), "⚙"),
        (("返回", "back"), "←"),
        (("登录", "进入", "login"), "→"),
        (("确认", "提交", "完成", "confirm", "submit"), "✓"),
    )
    for terms, icon in icon_rules:
        if any(term in text for term in terms):
            return icon
    return "•"


def _optional_element(tag: str, value: Any) -> str:
    text = _text(value)
    return f'<{tag}>{_jsx_text(text)}</{tag}>' if text else ""


def _render_confirmation_source(contract: dict[str, Any], *, screen: dict[str, Any], module: dict[str, Any]) -> str:
    requires_confirmation = bool(contract.get("requires_confirmation") or screen.get("requires_confirmation"))
    if not requires_confirmation:
        return ""
    action = _text(screen.get("interaction_action") or "提交当前操作")
    fields = list(contract.get("input_fields") or screen.get("interaction_input_fields") or [])[:5]
    items = "".join(
        f'<div data-confirm-item data-label="{_attr(field)}" data-value="{_attr(_sample_value(field, index, module=module, screen=screen))}"></div>'
        for index, field in enumerate(fields, start=1)
    )
    return (
        '<section hidden data-shared-confirm-source="true">'
        f'<h2 data-confirm-title>确认{_jsx_text(action)}</h2>'
        f'<p data-confirm-description>{_jsx_text(contract.get("trigger") or "请核对当前业务信息后继续。")}</p>'
        f'{items}'
        f'<p data-confirm-note>{_jsx_text(contract.get("post_state") or "操作完成后状态将同步更新。")}</p>'
        f'<span data-confirm-action>确认{_jsx_text(action)}</span></section>'
    )


def _page_spec_css(
    *,
    css_scope: str,
    renderer: str,
    visual_identity: dict[str, Any],
    color_contract: dict[str, Any],
    design_viewer: bool = False,
) -> str:
    accent, ink, canvas = _resolve_page_spec_palette(visual_identity, color_contract)
    scope = f".{css_scope}"
    mobile = str(renderer or "") in {"mobile_app", "game"}
    terminal_rules = (
        f"{scope}{{grid-template-rows:auto minmax(0,1fr);padding:26px 24px 28px;gap:20px;}}"
        f"{scope} .page-spec-heading{{align-items:flex-start;}}{scope} .page-spec-workspace{{grid-template-columns:1fr;grid-auto-rows:minmax(0,auto);overflow:auto;padding-right:4px;}}"
        f"{scope} .page-region{{min-height:0;}}{scope} .metric-grid{{grid-template-columns:repeat(2,minmax(0,1fr));}}"
        f"{scope} .business-form{{grid-template-columns:1fr 1fr;}}{scope} .table-frame{{max-height:420px;}}"
        f"{scope} .composition-slot-mobile-priority{{order:1;}}{scope} .composition-slot-mobile-flow{{order:2;}}"
        f"{scope}.composition-mobile-summary .composition-slot-mobile-priority{{border-left:3px solid var(--ps-accent);}}"
        f"{scope}.composition-mobile-task-flow .composition-slot-mobile-priority{{background:color-mix(in srgb,var(--ps-accent) 5%,#fff);}}"
        f"{scope}.composition-mobile-action-focus .composition-slot-mobile-priority{{box-shadow:0 10px 28px color-mix(in srgb,var(--ps-accent) 14%,transparent);}}"
    ) if mobile else (
        f"{scope}{{grid-template-rows:94px minmax(0,1fr);padding:24px 28px 28px;gap:18px;}}"
        # Use content-sized implicit rows. A fixed 112px minimum lets tall
        # regions (notably charts with absolutely positioned plot layers) paint
        # into the next row and cover its headings or controls.
        f"{scope} .page-spec-workspace{{grid-template-columns:repeat(12,minmax(0,1fr));grid-auto-rows:max-content;}}"
        f"{scope} .composition-slot-full-band{{grid-column:1/-1;}}"
        f"{scope} .composition-slot-primary-eight{{grid-column:span 8;}}{scope} .composition-slot-secondary-four{{grid-column:span 4;}}"
        f"{scope} .composition-slot-stage-left{{grid-column:1/span 9;}}{scope} .composition-slot-rail-right{{grid-column:10/span 3;}}"
        f"{scope} .composition-slot-stage-right{{grid-column:4/span 9;}}{scope} .composition-slot-rail-left{{grid-column:1/span 3;}}"
        f"{scope} .composition-slot-matrix-wide{{grid-column:1/-1;}}{scope} .composition-slot-matrix-half{{grid-column:span 6;}}"
        f"{scope} .composition-slot-workflow-stage{{grid-column:span 8;}}{scope} .composition-slot-workflow-support{{grid-column:span 4;}}"
        f"{scope} .composition-slot-detail-stage{{grid-column:span 9;}}{scope} .composition-slot-detail-rail{{grid-column:span 3;}}"
        f"{scope}.composition-asymmetric-right .page-spec-heading-copy{{order:2;}}{scope}.composition-asymmetric-right .page-spec-actions{{order:1;justify-content:flex-start;}}"
        f"{scope}.composition-analysis-matrix .page-spec-workspace{{gap:12px 16px;}}"
        f"{scope}.composition-workflow-focus .composition-slot-workflow-stage{{border-top:3px solid var(--ps-accent);}}"
        f"{scope}.composition-detail-rail .composition-slot-detail-rail{{background:color-mix(in srgb,var(--ps-accent) 5%,#fff);}}"
        f"{scope} .page-region:only-child{{grid-column:span 12;}}"
    )
    design_viewer_rules = _design_viewer_css(scope) if design_viewer else ""
    return f"""
{scope}{{--ps-accent:{accent};--ps-ink:{ink};--ps-canvas:{canvas};height:100%;min-height:0;box-sizing:border-box;display:grid;background:linear-gradient(145deg,color-mix(in srgb,var(--ps-canvas) 88%,#fff),#f8fbfb 60%,color-mix(in srgb,var(--ps-accent) 7%,#fff));color:color-mix(in srgb,var(--ps-ink) 88%,#111827);overflow:hidden;font-family:"Microsoft YaHei UI","PingFang SC",sans-serif;}}
{scope} *{{box-sizing:border-box;min-width:0;}}
{scope} button,{scope} input{{font:inherit;}}
{scope} .page-spec-heading{{display:flex;justify-content:space-between;gap:24px;min-height:0;overflow:visible;}}
{scope} .page-spec-heading-copy{{min-width:0;display:flex;flex-direction:column;justify-content:center;}}
{scope} h1,{scope} h2,{scope} p{{margin:0;}}
{scope} .page-spec-heading h1{{max-width:760px;font-size:24px;line-height:1.25;overflow-wrap:anywhere;}}
{scope} .page-spec-actions{{display:flex;align-items:center;justify-content:flex-end;gap:9px;flex-wrap:wrap;align-content:center;}}
{scope} .page-action{{min-height:34px;max-width:150px;display:inline-flex;align-items:center;justify-content:center;gap:6px;padding:7px 11px;border:1px solid color-mix(in srgb,var(--ps-ink) 18%,#fff);border-radius:7px;background:#fff;color:color-mix(in srgb,var(--ps-ink) 78%,#111827);font-size:11px;font-weight:750;line-height:1.25;white-space:normal;overflow-wrap:anywhere;}}
{scope} .page-action-icon{{width:16px;height:16px;flex:0 0 16px;display:grid;place-items:center;font-size:14px;line-height:1;font-weight:900;}}
{scope} .page-action-icon::before{{content:attr(data-icon);}}
{scope} .page-action-label{{min-width:0;display:block;overflow-wrap:anywhere;}}
{scope} .action-primary{{border-color:var(--ps-accent);background:var(--ps-accent);color:#fff;box-shadow:0 7px 18px color-mix(in srgb,var(--ps-accent) 24%,transparent);}}
{scope} .action-danger{{border-color:#c94242;background:#c94242;color:#fff;}}
{scope} .page-spec-workspace{{min-height:0;display:grid;gap:14px;overflow:auto;align-content:start;}}
{scope}.page-kind-statistics .page-spec-workspace{{display:flex;flex-direction:column;align-items:stretch;}}
{scope}.page-kind-statistics .page-region{{width:100%;flex:0 0 auto;}}
{scope}.page-kind-statistics .metric-grid{{grid-template-columns:repeat(3,minmax(0,1fr));}}
{scope}.page-kind-statistics .chart-series .chart-panel{{height:210px;min-height:210px;flex:0 0 210px;}}
{scope} .page-region{{min-height:min-content;padding:15px 16px;border:1px solid color-mix(in srgb,var(--ps-ink) 14%,#fff);border-radius:14px;background:rgba(255,255,255,.94);box-shadow:0 8px 24px color-mix(in srgb,var(--ps-ink) 8%,transparent);overflow:visible;display:flex;flex-direction:column;gap:12px;}}
{scope} .region-heading{{display:flex;align-items:flex-start;justify-content:space-between;gap:14px;flex:0 0 auto;overflow:visible;}}
{scope} .region-heading>div{{display:flex;align-items:center;gap:8px;min-width:0;}}
{scope} .region-heading h2{{font-size:13px;line-height:1.35;overflow-wrap:anywhere;}}
{scope} .filter-bar{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr)) auto auto;gap:10px;align-items:end;}}
{scope} .filter-control,{scope} .form-field{{display:flex;flex-direction:column;gap:5px;min-width:0;}}
{scope} .filter-control span,{scope} .form-field span{{color:color-mix(in srgb,var(--ps-ink) 62%,#fff);font-size:10px;font-weight:700;white-space:normal;overflow-wrap:anywhere;}}
{scope} input{{height:33px;width:100%;padding:0 10px;border:1px solid color-mix(in srgb,var(--ps-ink) 16%,#fff);border-radius:7px;background:#fff;color:var(--ps-ink);font-size:10px;outline:none;}}
{scope} .filter-submit,{scope} .filter-reset{{height:33px;min-width:58px;padding:0 10px;display:inline-flex;align-items:center;justify-content:center;gap:5px;border-radius:7px;font-size:10px;font-weight:800;white-space:normal;}}
{scope} .filter-submit{{border:1px solid var(--ps-accent);background:var(--ps-accent);color:#fff;}}{scope} .filter-reset{{border:1px solid color-mix(in srgb,var(--ps-ink) 18%,#fff);background:#fff;color:var(--ps-ink);}}
{scope} .metric-grid{{flex:0 0 auto;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;}}
{scope} .metric-card{{min-height:78px;padding:12px;border:1px solid color-mix(in srgb,var(--ps-accent) 14%,#fff);border-radius:10px;background:linear-gradient(145deg,#fff,color-mix(in srgb,var(--ps-accent) 6%,#fff));display:flex;flex-direction:column;justify-content:center;overflow:visible;}}
{scope} .metric-card span,{scope} .metric-card small{{font-size:9px;overflow-wrap:anywhere;}}{scope} .metric-card span{{color:color-mix(in srgb,var(--ps-ink) 58%,#fff);}}{scope} .metric-card strong{{margin:5px 0 3px;color:var(--ps-accent);font-size:clamp(14px,2.4vw,22px);line-height:1.1;overflow-wrap:anywhere;}}{scope} .metric-card small{{color:color-mix(in srgb,var(--ps-ink) 48%,#fff);}}
{scope} .table-frame{{min-height:0;overflow:auto;border:1px solid color-mix(in srgb,var(--ps-ink) 12%,#fff);border-radius:9px;}}
{scope} table{{width:100%;border-collapse:collapse;table-layout:fixed;font-size:10px;}}{scope} th{{min-height:34px;padding:8px 9px;background:color-mix(in srgb,var(--ps-accent) 9%,#fff);color:color-mix(in srgb,var(--ps-ink) 74%,#111827);text-align:left;white-space:normal;overflow-wrap:anywhere;}}{scope} td{{min-height:38px;padding:8px 9px;border-top:1px solid color-mix(in srgb,var(--ps-ink) 9%,#fff);white-space:normal;overflow-wrap:anywhere;word-break:break-word;vertical-align:top;}}{scope} tbody tr:nth-child(even){{background:#fbfdfd;}}
{scope} .business-form{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;overflow:visible;}}
{scope} .runtime-record-panel{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;min-height:0;overflow:visible;}}
{scope} .detail-item{{padding:9px 10px;border-radius:8px;background:color-mix(in srgb,var(--ps-canvas) 60%,#fff);overflow:visible;}}{scope} .detail-item span,{scope} .detail-item strong{{display:block;white-space:normal;overflow-wrap:anywhere;word-break:break-word;}}{scope} .detail-item span{{color:color-mix(in srgb,var(--ps-ink) 52%,#fff);font-size:9px;}}{scope} .detail-item strong{{margin-top:4px;font-size:11px;}}
{scope} .workflow-board{{display:flex;flex-direction:column;gap:8px;min-height:0;overflow:visible;}}{scope} .workflow-step{{display:grid;grid-template-columns:24px minmax(0,1fr);gap:9px;align-items:start;padding:8px;border-radius:9px;background:color-mix(in srgb,var(--ps-canvas) 58%,#fff);overflow:visible;}}{scope} .workflow-step>span{{width:24px;height:24px;border-radius:50%;display:grid;place-items:center;background:var(--ps-accent);color:#fff;font-size:9px;font-weight:900;}}{scope} .workflow-step strong,{scope} .workflow-step small{{display:block;white-space:normal;overflow-wrap:anywhere;word-break:break-word;}}{scope} .workflow-step strong{{font-size:10px;}}{scope} .workflow-step small{{margin-top:3px;color:color-mix(in srgb,var(--ps-ink) 48%,#fff);font-size:9px;}}
{scope} .timeline{{min-height:0;display:flex;flex-direction:column;gap:8px;overflow:visible;}}{scope} .timeline-item{{display:grid;grid-template-columns:46px minmax(0,1fr);gap:10px;position:relative;}}{scope} .timeline-item time{{padding-top:2px;color:var(--ps-accent);font-size:9px;font-weight:850;}}{scope} .timeline-item div{{padding:0 0 9px 12px;border-left:2px solid color-mix(in srgb,var(--ps-accent) 28%,#fff);overflow:visible;}}{scope} .timeline-item strong,{scope} .timeline-item p{{display:block;white-space:normal;overflow-wrap:anywhere;word-break:break-word;}}{scope} .timeline-item strong{{font-size:10px;}}{scope} .timeline-item p{{margin-top:3px;color:color-mix(in srgb,var(--ps-ink) 50%,#fff);font-size:9px;}}
{scope} .kanban-board{{min-height:0;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;overflow:visible;}}{scope} .kanban-column{{min-height:0;padding:9px;border-radius:10px;background:color-mix(in srgb,var(--ps-canvas) 64%,#fff);overflow:visible;}}{scope} .kanban-column header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;font-size:10px;font-weight:800;}}{scope} .kanban-column header b{{min-width:20px;height:20px;padding:0 6px;border-radius:10px;background:color-mix(in srgb,var(--ps-accent) 14%,#fff);color:var(--ps-accent);display:grid;place-items:center;font-size:9px;}}{scope} .kanban-column article{{margin-top:7px;padding:9px;border:1px solid color-mix(in srgb,var(--ps-ink) 10%,#fff);border-radius:8px;background:#fff;overflow:visible;}}{scope} .kanban-column strong,{scope} .kanban-column article span{{display:block;white-space:normal;overflow-wrap:anywhere;word-break:break-word;}}{scope} .kanban-column strong{{font-size:10px;}}{scope} .kanban-column article span{{margin-top:5px;color:color-mix(in srgb,var(--ps-ink) 50%,#fff);font-size:9px;}}
{scope} .chart-panel{{position:relative;min-height:0;flex:1;border-radius:10px;background:linear-gradient(to top,color-mix(in srgb,var(--ps-accent) 5%,#fff),#fff);overflow:hidden;}}{scope} .chart-grid-lines{{position:absolute;inset:12px 10px 28px;background:repeating-linear-gradient(to top,transparent 0,transparent 24px,color-mix(in srgb,var(--ps-ink) 8%,#fff) 25px);}}{scope} .chart-columns{{position:absolute;inset:18px 12px 10px;display:flex;align-items:flex-end;justify-content:space-around;gap:8px;}}{scope} .chart-column{{height:100%;flex:1;display:grid;grid-template-rows:auto 1fr auto;justify-items:center;align-items:end;}}{scope} .chart-value,{scope} .chart-column small{{font-size:8px;white-space:normal;overflow-wrap:anywhere;text-align:center;max-width:100%;}}{scope} .chart-bar{{width:min(28px,70%);border-radius:6px 6px 2px 2px;background:linear-gradient(to top,var(--ps-accent),color-mix(in srgb,var(--ps-accent) 48%,#fff));}}{scope} .chart-bar-1{{height:42%;}}{scope} .chart-bar-2{{height:61%;}}{scope} .chart-bar-3{{height:52%;}}{scope} .chart-bar-4{{height:78%;}}{scope} .chart-bar-5{{height:68%;}}{scope} .chart-bar-6{{height:86%;}}
{scope} .map-workspace{{position:relative;min-height:190px;flex:1;border-radius:10px;background:linear-gradient(135deg,color-mix(in srgb,var(--ps-accent) 8%,#fff),#eef5f4);overflow:hidden;}}{scope} .map-grid{{position:absolute;inset:0;background-image:linear-gradient(color-mix(in srgb,var(--ps-ink) 7%,transparent) 1px,transparent 1px),linear-gradient(90deg,color-mix(in srgb,var(--ps-ink) 7%,transparent) 1px,transparent 1px);background-size:34px 34px;transform:rotate(-5deg) scale(1.1);}}{scope} .map-pin{{position:absolute;width:112px;padding:7px 8px;border:1px solid color-mix(in srgb,var(--ps-accent) 28%,#fff);border-radius:9px;background:#fff;color:var(--ps-ink);box-shadow:0 6px 16px color-mix(in srgb,var(--ps-ink) 12%,transparent);display:grid;grid-template-columns:20px minmax(0,1fr);grid-template-rows:auto auto;column-gap:6px;text-align:left;overflow:visible;}}{scope} .map-pin span{{grid-row:span 2;width:20px;height:20px;border-radius:50%;display:grid;place-items:center;background:var(--ps-accent);color:#fff;font-size:8px;font-weight:900;}}{scope} .map-pin b,{scope} .map-pin small{{white-space:normal;overflow-wrap:anywhere;word-break:break-word;}}{scope} .map-pin b{{font-size:9px;}}{scope} .map-pin small{{font-size:8px;color:color-mix(in srgb,var(--ps-ink) 48%,#fff);}}{scope} .map-pin-1{{left:8%;top:18%;}}{scope} .map-pin-2{{left:38%;top:38%;}}{scope} .map-pin-3{{left:66%;top:16%;}}{scope} .map-pin-4{{left:20%;top:66%;}}{scope} .map-pin-5{{left:58%;top:68%;}}{scope} .map-pin-6{{left:76%;top:46%;}}{scope} .map-pin-7{{left:43%;top:10%;}}{scope} .map-workspace aside{{position:absolute;right:10px;bottom:10px;width:128px;padding:9px;border-radius:8px;background:rgba(255,255,255,.92);display:flex;flex-direction:column;gap:4px;}}{scope} .map-workspace aside strong{{font-size:9px;}}{scope} .map-workspace aside span{{font-size:8px;color:color-mix(in srgb,var(--ps-ink) 52%,#fff);}}
{scope} .relationship-graph{{position:relative;min-height:190px;flex:1;border-radius:10px;background:radial-gradient(circle at center,color-mix(in srgb,var(--ps-accent) 10%,#fff),#fff 58%);overflow:hidden;}}{scope} .graph-links{{position:absolute;inset:50%;width:1px;height:1px;box-shadow:-150px -55px 0 1px color-mix(in srgb,var(--ps-accent) 24%,#fff),145px -52px 0 1px color-mix(in srgb,var(--ps-accent) 24%,#fff),-130px 60px 0 1px color-mix(in srgb,var(--ps-accent) 24%,#fff),135px 62px 0 1px color-mix(in srgb,var(--ps-accent) 24%,#fff);}}{scope} .graph-node{{position:absolute;width:116px;padding:9px;border:1px solid color-mix(in srgb,var(--ps-accent) 22%,#fff);border-radius:10px;background:#fff;color:var(--ps-ink);box-shadow:0 7px 18px color-mix(in srgb,var(--ps-ink) 10%,transparent);overflow:visible;}}{scope} .graph-node span,{scope} .graph-node strong{{display:block;white-space:normal;overflow-wrap:anywhere;word-break:break-word;}}{scope} .graph-node span{{color:var(--ps-accent);font-size:8px;}}{scope} .graph-node strong{{margin-top:4px;font-size:10px;}}{scope} .graph-node-1{{left:calc(50% - 58px);top:calc(50% - 29px);background:color-mix(in srgb,var(--ps-accent) 12%,#fff);}}{scope} .graph-node-2{{left:5%;top:12%;}}{scope} .graph-node-3{{right:5%;top:14%;}}{scope} .graph-node-4{{left:8%;bottom:10%;}}{scope} .graph-node-5{{right:8%;bottom:10%;}}{scope} .graph-node-6{{right:6%;top:45%;}}
{scope} .mobile-list{{display:flex;flex-direction:column;gap:9px;min-height:0;overflow:visible;}}{scope} .mobile-list-item{{min-height:58px;padding:11px 12px;border:1px solid color-mix(in srgb,var(--ps-ink) 11%,#fff);border-radius:11px;background:#fff;display:flex;align-items:flex-start;justify-content:space-between;gap:12px;overflow:visible;}}{scope} .mobile-list-item div{{min-width:0;}}{scope} .mobile-list-item strong,{scope} .mobile-list-item span{{display:block;white-space:normal;overflow-wrap:anywhere;word-break:break-word;}}{scope} .mobile-list-item strong{{font-size:11px;}}{scope} .mobile-list-item span{{margin-top:5px;color:color-mix(in srgb,var(--ps-ink) 50%,#fff);font-size:9px;}}{scope} .mobile-list-item b{{flex:0 0 auto;padding:5px 8px;border-radius:999px;background:color-mix(in srgb,var(--ps-accent) 12%,#fff);color:var(--ps-accent);font-size:9px;}}
{scope} .operation-result{{display:grid;grid-template-columns:minmax(220px,.85fr) 1.4fr;gap:14px;align-items:stretch;overflow:visible;}}{scope} .operation-result>header{{padding:12px;border-radius:10px;background:linear-gradient(135deg,var(--ps-accent),color-mix(in srgb,var(--ps-accent) 70%,var(--ps-ink)));color:#fff;display:flex;align-items:flex-start;gap:10px;overflow:visible;}}{scope} .operation-result>header>span{{flex:0 0 auto;width:30px;height:30px;border-radius:50%;display:grid;place-items:center;background:rgba(255,255,255,.2);font-weight:900;}}{scope} .operation-result>header strong,{scope} .operation-result>header p{{display:block;white-space:normal;overflow-wrap:anywhere;word-break:break-word;}}{scope} .operation-result>header strong{{font-size:11px;}}{scope} .operation-result>header p{{margin-top:4px;font-size:9px;opacity:.82;}}{scope} .operation-result>section{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;}}{scope} .operation-result>section>div{{padding:10px;border-radius:9px;background:color-mix(in srgb,var(--ps-canvas) 62%,#fff);overflow:visible;}}{scope} .operation-result>section span,{scope} .operation-result>section strong{{display:block;white-space:normal;overflow-wrap:anywhere;word-break:break-word;}}{scope} .operation-result>section span{{font-size:8px;color:color-mix(in srgb,var(--ps-ink) 48%,#fff);}}{scope} .operation-result>section strong{{margin-top:5px;font-size:10px;}}
{scope}.page-spec-login{{display:grid;grid-template-rows:minmax(0,1fr);place-items:center;padding:34px;overflow:hidden;}}
{scope} .login-shell{{width:min(1080px,100%);height:min(560px,100%);min-height:500px;display:grid;grid-template-columns:minmax(0,1.08fr) minmax(390px,.92fr);border:1px solid color-mix(in srgb,var(--ps-ink) 13%,#fff);border-radius:24px;background:#fff;box-shadow:0 24px 70px color-mix(in srgb,var(--ps-ink) 16%,transparent);overflow:hidden;}}
{scope} .login-brand-panel{{position:relative;padding:56px;display:flex;flex-direction:column;justify-content:center;background:linear-gradient(145deg,var(--ps-ink),color-mix(in srgb,var(--ps-accent) 72%,var(--ps-ink)));color:#fff;overflow:hidden;}}
{scope} .login-brand-mark{{width:46px;height:46px;margin-bottom:28px;border-radius:14px;background:var(--ps-accent);display:grid;place-items:center;color:#fff;font-size:20px;font-weight:900;box-shadow:0 12px 28px rgba(0,0,0,.18);}}
{scope} .login-brand-copy{{position:relative;z-index:1;max-width:500px;}}
{scope} .login-brand-copy h1{{font-size:31px;line-height:1.35;letter-spacing:.01em;display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:3;overflow:hidden;}}
{scope} .login-version{{display:inline-flex;width:max-content;margin-top:24px;padding:6px 10px;border:1px solid rgba(255,255,255,.22);border-radius:999px;color:rgba(255,255,255,.82);font-size:10px;font-weight:750;}}
{scope} .login-card{{padding:48px 52px 38px;display:flex;flex-direction:column;justify-content:center;background:#fff;overflow:hidden;}}
{scope} .login-card>header h2{{font-size:25px;line-height:1.3;}}
{scope} .login-form{{margin-top:26px;display:flex;flex-direction:column;gap:14px;}}
{scope} .login-field{{display:flex;flex-direction:column;gap:7px;}}
{scope} .login-field>span{{color:color-mix(in srgb,var(--ps-ink) 68%,#fff);font-size:10px;font-weight:750;}}
{scope} .login-field input,{scope} .login-field select{{width:100%;height:39px;padding:0 12px;border:1px solid color-mix(in srgb,var(--ps-ink) 16%,#fff);border-radius:9px;background:#fff;color:var(--ps-ink);font-size:11px;outline:none;}}
{scope} .login-field input:focus,{scope} .login-field select:focus{{border-color:var(--ps-accent);box-shadow:0 0 0 3px color-mix(in srgb,var(--ps-accent) 10%,transparent);}}
{scope} .login-captcha>div{{display:grid;grid-template-columns:minmax(0,1fr) 92px;gap:9px;}}
{scope} .login-captcha button{{height:39px;border:1px solid color-mix(in srgb,var(--ps-accent) 22%,#fff);border-radius:9px;background:color-mix(in srgb,var(--ps-accent) 8%,#fff);color:var(--ps-accent);font-size:13px;font-weight:900;letter-spacing:.12em;}}
{scope} .login-assistance{{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:1px;color:color-mix(in srgb,var(--ps-ink) 56%,#fff);font-size:10px;}}
{scope} .login-assistance label{{display:flex;align-items:center;gap:7px;}}
{scope} .login-assistance input{{width:14px;height:14px;margin:0;accent-color:var(--ps-accent);}}
{scope} .login-assistance button{{padding:0;border:0;background:transparent;color:var(--ps-accent);font-size:10px;}}
{scope} .login-submit{{height:42px;margin-top:3px;border:1px solid var(--ps-accent);border-radius:9px;background:var(--ps-accent);color:#fff;font-size:12px;font-weight:850;box-shadow:0 10px 24px color-mix(in srgb,var(--ps-accent) 22%,transparent);}}
{scope}.page-spec-mobile{{padding:24px 18px;}}{scope}.page-spec-mobile .login-shell{{height:100%;min-height:0;grid-template-columns:1fr;grid-template-rows:auto minmax(0,1fr);border-radius:20px;}}{scope}.page-spec-mobile .login-brand-panel{{padding:25px 28px;}}{scope}.page-spec-mobile .login-brand-mark{{width:38px;height:38px;margin-bottom:14px;font-size:16px;}}{scope}.page-spec-mobile .login-brand-copy h1{{font-size:21px;-webkit-line-clamp:2;}}{scope}.page-spec-mobile .login-version{{display:none;}}{scope}.page-spec-mobile .login-card{{padding:28px;justify-content:flex-start;overflow:auto;}}
{terminal_rules}
{scope} .page-region>div{{flex-shrink:0;}}
{scope} .page-spec-data-source{{display:flex;gap:6px;margin-top:7px;font-size:9px;color:color-mix(in srgb,var(--ps-ink) 60%,#fff);}}
{scope} .chart-series-list{{display:grid;gap:14px;}}
{scope} .chart-series h3{{margin:0 0 6px;font-size:10px;overflow-wrap:anywhere;}}
{scope} .chart-series p{{margin:0 0 6px;font-size:9px;color:#946200;}}
{scope} .chart-series .chart-panel{{height:170px;min-height:170px;}}
{scope} .chart-columns{{inset:12px;}}
{scope} .chart-column{{grid-template-rows:16px minmax(0,1fr) 36px;gap:4px;align-items:stretch;}}
{scope} .chart-bar-track{{position:relative;width:100%;background-image:linear-gradient(color-mix(in srgb,var(--ps-ink) 25%,#fff),color-mix(in srgb,var(--ps-ink) 25%,#fff));background-size:100% 1px;background-repeat:no-repeat;}}
{scope} .chart-bar{{position:absolute;left:50%;transform:translateX(-50%);display:block;}}
{design_viewer_rules}
""".strip() + (component_style_css(color_contract, scope=scope) if not design_viewer else "")


def _design_viewer_css(scope: str) -> str:
    return f"""
{scope}.design-viewer-screen{{grid-template-columns:210px minmax(0,1fr) 244px;grid-template-rows:minmax(0,1fr);padding:0;gap:0;background:#e5e7eb;color:#222;border:0;}}
{scope} .design-resource-panel,{scope} .design-inspector-panel{{min-height:0;background:#fff;overflow:hidden;}}
{scope} .design-resource-panel{{display:grid;grid-template-rows:46px 48px minmax(0,1fr);border-right:1px solid #d6d8dc;}}
{scope} .design-resource-panel>header{{display:flex;align-items:center;justify-content:space-between;padding:0 12px;border-bottom:1px solid #e5e7eb;}}
{scope} .design-resource-panel>header strong{{font-size:12px;}}{scope} .design-resource-panel>header button{{width:26px;height:26px;border:0;border-radius:4px;background:#f0f1f2;font-size:17px;}}
{scope} .design-resource-search{{height:32px;margin:8px 10px;display:grid;grid-template-columns:22px minmax(0,1fr);align-items:center;border:1px solid #d6d8dc;border-radius:5px;background:#f8f8f9;overflow:hidden;}}
{scope} .design-resource-search span{{text-align:center;color:#70747b;}}{scope} .design-resource-search input{{height:30px;padding:0 6px;border:0;background:transparent;font-size:10px;}}
{scope} .design-resource-panel nav{{min-height:0;padding:8px;overflow:hidden auto;}}{scope} .design-resource-panel nav>small{{display:block;padding:4px 7px 7px;color:#777;font-size:9px;font-weight:700;}}
{scope} .design-resource-row{{width:100%;min-height:31px;padding:5px 7px;display:grid;grid-template-columns:20px minmax(0,1fr);align-items:center;gap:4px;border:0;border-radius:4px;background:transparent;text-align:left;color:#32343a;}}
{scope} .design-resource-row.active{{background:#e8f2ff;color:#1467c9;}}{scope} .design-resource-row span{{font-size:10px;}}{scope} .design-resource-row b{{font-size:10px;line-height:1.25;overflow-wrap:anywhere;}}
{scope} .design-canvas-panel{{min-width:0;min-height:0;display:grid;grid-template-rows:46px minmax(0,1fr) 32px;background:#e7e8ea;overflow:hidden;}}
{scope} .design-canvas-toolbar{{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:0 10px;border-bottom:1px solid #cfd2d6;background:#fff;overflow:hidden;}}
{scope} .design-canvas-toolbar>div{{min-width:0;display:flex;align-items:center;gap:6px;}}{scope} .design-canvas-toolbar button{{min-width:27px;height:27px;padding:0 7px;border:1px solid transparent;border-radius:4px;background:#f3f4f5;color:#34363a;}}
{scope} .design-canvas-toolbar h1{{margin-left:7px;font-size:12px;line-height:1.25;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}}
{scope} .design-canvas-toolbar .page-spec-actions{{flex-wrap:nowrap;overflow:visible;}}{scope} .design-canvas-toolbar .page-action{{min-height:28px;max-width:150px;padding:5px 9px;border-radius:4px;font-size:10px;overflow:visible;white-space:normal;}}
{scope} .design-canvas-stage{{min-height:0;padding:32px;display:grid;grid-template-columns:repeat(2,minmax(220px,1fr));grid-auto-rows:minmax(180px,1fr);gap:30px;overflow:auto;align-content:start;}}
{scope} .design-artboard{{min-width:0;display:grid;grid-template-rows:23px minmax(0,1fr);filter:drop-shadow(0 2px 5px rgba(0,0,0,.12));}}
{scope} .design-artboard>header{{display:flex;align-items:center;justify-content:space-between;gap:9px;color:#555;font-size:9px;overflow:hidden;}}{scope} .design-artboard>header span{{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}}{scope} .design-artboard>header b{{flex:0 0 auto;font-weight:500;}}
{scope} .design-artboard-preview{{min-height:150px;padding:14px;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));grid-template-rows:18px 48px minmax(38px,1fr);gap:9px;background:#fff;border:1px solid #d9dadd;overflow:hidden;}}
{scope} .design-artboard-preview i,{scope} .design-artboard-preview span,{scope} .design-artboard-preview em{{display:block;border-radius:3px;background:#eef1f3;}}
{scope} .design-artboard-preview .preview-nav{{grid-column:1/-1;background:#25272b;}}{scope} .design-artboard-preview .preview-hero{{grid-column:1/-1;background:color-mix(in srgb,var(--ps-accent) 18%,#f4f5f6);}}
{scope} .design-artboard-preview span{{border:1px solid #e1e3e5;background:#fff;}}{scope} .design-artboard-preview em{{grid-column:span 1;background:color-mix(in srgb,var(--ps-accent) 10%,#f4f5f6);}}
{scope} .design-canvas-panel>footer{{display:flex;align-items:center;justify-content:flex-end;gap:4px;padding:0 9px;border-top:1px solid #d2d4d8;background:#fff;color:#555;font-size:9px;}}{scope} .design-canvas-panel>footer button{{width:23px;height:22px;border:1px solid #ddd;background:#fff;border-radius:3px;}}
{scope} .design-inspector-panel{{display:grid;grid-template-rows:42px auto auto 1fr;border-left:1px solid #d6d8dc;}}
{scope} .design-inspector-panel>nav{{display:grid;grid-template-columns:repeat(3,1fr);border-bottom:1px solid #e1e3e5;}}{scope} .design-inspector-panel>nav button{{border:0;border-bottom:2px solid transparent;background:#fff;font-size:10px;}}{scope} .design-inspector-panel>nav button.active{{border-color:var(--ps-accent);font-weight:800;}}
{scope} .design-inspector-panel>section{{padding:13px;border-bottom:1px solid #e6e7e9;}}{scope} .design-inspector-panel h2{{margin-bottom:11px;font-size:11px;}}
{scope} .design-property{{display:grid;grid-template-columns:54px minmax(0,1fr);gap:8px;padding:6px 0;font-size:9px;}}{scope} .design-property span{{color:#74777c;}}{scope} .design-property strong{{line-height:1.35;overflow-wrap:anywhere;}}
{scope} .design-review-state{{display:grid;grid-template-columns:8px minmax(0,1fr) auto;align-items:center;gap:7px;padding:9px;border-radius:4px;background:#f5f6f7;font-size:9px;}}{scope} .design-review-state>span{{width:8px;height:8px;border-radius:50%;background:#f59e0b;}}{scope} .design-review-state b{{color:var(--ps-accent);}}
""".strip()


def _default_columns(module: dict[str, Any], *, screen: dict[str, Any]) -> list[str]:
    profile = page_spec_semantic_profile(module, screen)
    fields = list(profile["fields"])
    subject = str(profile["subject"])
    return fields[:5] or [f"{subject}编号", f"{subject}名称", "当前状态", "更新时间"]


def _default_rows(module: dict[str, Any], columns: list[str], *, screen: dict[str, Any]) -> list[dict[str, str]]:
    profile = page_spec_semantic_profile(module, screen)
    subject = str(profile["subject"])
    states = list(profile["states"]) or ["正常", "进行中", "已完成", "已更新"]
    roles = list(profile["roles"]) or [str(profile["role"])]
    return [
        {
            "label": f"{subject}{index}",
            "title": f"{subject}{index}",
            "status": states[(index - 1) % len(states)],
            "owner": roles[(index - 1) % len(roles)],
            "value": f"{_identifier_prefix(subject, module=module)}-{202600 + index}",
        }
        for index in range(1, 6)
    ]


def _default_fields(module: dict[str, Any], *, screen: dict[str, Any], limit: int) -> list[dict[str, str]]:
    profile = page_spec_semantic_profile(module, screen)
    fields = list(profile["fields"])
    subject = str(profile["subject"])
    if not fields:
        fields = [f"{subject}编号", f"{subject}名称", "当前状态", "更新时间"]
    return [
        {"label": field, "value": _sample_value(field, index, module=module, screen=screen)}
        for index, field in enumerate(fields[:limit], start=1)
    ]


def _default_detail_items(module: dict[str, Any], *, screen: dict[str, Any]) -> list[dict[str, str]]:
    return _default_fields(module, screen=screen, limit=8)


def _default_metrics(module: dict[str, Any], screen: dict[str, Any]) -> list[dict[str, str]]:
    profile = page_spec_semantic_profile(module, screen)
    subject = str(profile["subject"])
    action = str(profile["action_verb"])
    return [
        {"label": f"{subject}数量", "value": "28", "status": "当前统计范围"},
        {"label": f"{action}完成率", "value": "96.4%", "status": "较上一周期稳定"},
        {"label": "今日更新", "value": "12", "status": "数据已同步"},
        {"label": "正常状态占比", "value": "92.8%", "status": "运行状态正常"},
    ]


def _default_workflow_steps(module: dict[str, Any], screen: dict[str, Any]) -> list[dict[str, str]]:
    profile = page_spec_semantic_profile(module, screen)
    subject = str(profile["subject"])
    actions = list(profile["actions"])
    states = list(profile["states"])
    if actions:
        return [
            {
                "label": action,
                "status": states[index % len(states)] if states else ("已完成" if index == 0 else "进行中"),
            }
            for index, action in enumerate(actions[:4])
        ]
    fields = list(profile["fields"])
    return [
        {"label": f"选择{subject}", "status": "已完成"},
        {"label": f"填写{fields[0] if fields else subject + '信息'}", "status": "已完成"},
        {"label": f"更新{subject}", "status": "进行中"},
        {"label": f"查看{subject}结果", "status": "未开始"},
    ]


def _default_timeline_items(module: dict[str, Any], screen: dict[str, Any]) -> list[dict[str, str]]:
    profile = page_spec_semantic_profile(module, screen)
    subject = str(profile["subject"])
    actions = list(profile["actions"])
    states = list(profile["states"])
    labels = actions[:3] or [f"{subject}已创建", f"{subject}信息已更新", f"{subject}结果已生成"]
    return [
        {
            "time": ("09:10", "10:25", "11:40")[index % 3],
            "label": label,
            "description": states[index % len(states)] if states else f"{subject}状态已更新",
        }
        for index, label in enumerate(labels[:3])
    ]


def _default_kanban_items(module: dict[str, Any], screen: dict[str, Any]) -> list[dict[str, str]]:
    profile = page_spec_semantic_profile(module, screen)
    subject = str(profile["subject"])
    actions = list(profile["actions"]) or [f"查看{subject}", f"更新{subject}", f"完成{subject}"]
    states = list(profile["states"]) or ["计划中", "进行中", "已完成"]
    roles = list(profile["roles"]) or [str(profile["role"])]
    return [
        {
            "category": states[index % len(states)],
            "label": action,
            "owner": roles[index % len(roles)],
        }
        for index, action in enumerate(actions[:6])
    ]


def _default_map_points(module: dict[str, Any], screen: dict[str, Any]) -> list[dict[str, str]]:
    profile = page_spec_semantic_profile(module, screen)
    subject = str(profile["subject"])
    states = list(profile["states"]) or ["正常", "在线", "监测中", "已同步"]
    directions = ("东区", "中心区", "西区", "北区")
    return [
        {"label": f"{direction}{subject}点位", "status": states[index % len(states)]}
        for index, direction in enumerate(directions)
    ]


def _default_relationship_items(module: dict[str, Any], screen: dict[str, Any]) -> list[dict[str, str]]:
    profile = page_spec_semantic_profile(module, screen)
    subject = str(profile["subject"])
    entities = list(profile["entities"])
    fields = list(profile["fields"])
    labels = [subject, *entities, *fields]
    unique_labels: list[str] = []
    for label in labels:
        text = _text(label)
        if text and text not in unique_labels:
            unique_labels.append(text)
    categories = ("核心对象", "关联对象", "关键字段", "结果信息")
    return [
        {"label": label, "category": categories[index % len(categories)]}
        for index, label in enumerate((unique_labels or [subject])[:6])
    ]


def _default_operation_result_items(module: dict[str, Any], screen: dict[str, Any]) -> list[dict[str, str]]:
    profile = page_spec_semantic_profile(module, screen)
    states = list(profile["states"])
    return [
        {"label": "当前状态", "value": screen.get("interaction_post_state") or (states[-1] if states else "已完成")},
        {"label": "结果信息", "value": profile["result_evidence"]},
        {"label": "责任岗位", "value": profile["role"]},
    ]


def _row_value(
    item: dict[str, Any],
    column: str,
    row_index: int,
    column_index: int,
    *,
    module: dict[str, Any],
    screen: dict[str, Any],
    column_key: str | None = None,
) -> str:
    if column_key:
        return _visible_scalar(item[column_key]) if item.get(column_key) not in (None, "") else "—"
    direct = item.get(column)
    if direct is not None and direct != "":
        return _visible_scalar(direct)
    # Explicit aliases for v1 caches which retained labels but lost column keys.
    aliases = {
        "知识点": "knowledge", "有效学生数": "sample", "分摊得分／满分": "weighted_score",
        "知识点得分率": "score_rate", "订正通过／需订正": "correction", "来源成绩版本": "source",
    }
    alias = aliases.get(column)
    if alias and item.get(alias) not in (None, ""):
        return _visible_scalar(item[alias])
    keys = ("label", "title", "value", "owner", "status", "time", "meta")
    value = item.get(keys[column_index % len(keys)])
    if value is not None and value != "":
        return _visible_scalar(value)
    return "—"


def _sample_value(
    label: Any,
    index: int,
    *,
    module: dict[str, Any] | None = None,
    screen: dict[str, Any] | None = None,
) -> str:
    text = str(label or "")
    profile = page_spec_semantic_profile(module, screen)
    states = list(profile["states"]) or ["正常", "进行中", "已完成", "已更新"]
    roles = list(profile["roles"]) or [str(profile["role"])]
    subject = str(profile["subject"])
    if any(term in text for term in ("状态", "结论")):
        return states[(index - 1) % len(states)]
    if any(term in text for term in ("时间", "日期")):
        return f"2026-07-{18 + index:02d}"
    if any(term in text for term in ("岗位", "人员", "责任")):
        return roles[(index - 1) % len(roles)]
    if any(term in text for term in ("编号", "编码", "ID")):
        return f"{_identifier_prefix(subject, module=module)}-202607-{index:03d}"
    if any(term in text for term in ("数量", "次数", "总数")):
        return str(8 + index * 3)
    if any(term in text for term in ("名称", "对象", "任务", "事项")):
        return f"{subject}{index}"
    return f"{subject}{index}"


def _identifier_prefix(subject: str, *, module: dict[str, Any] | None = None) -> str:
    module_key = str((module or {}).get("key") or "")
    key_letters = "".join(character for character in module_key if character.isascii() and character.isalnum())
    if key_letters:
        return key_letters[:6].upper()
    ascii_letters = "".join(character for character in str(subject or "") if character.isascii() and character.isalnum())
    if ascii_letters:
        return ascii_letters[:6].upper()
    checksum = sum((index + 1) * ord(character) for index, character in enumerate(str(subject or "事项"))) % 997
    return f"B{checksum:03d}"


def _metric_value(index: int) -> str:
    return ("28", "96.4%", "3", "12")[(index - 1) % 4]


def _component_title(component: str, module: dict[str, Any], screen: dict[str, Any]) -> str:
    labels = {
        "filter_bar": "业务筛选",
        "metric_group": "核心指标",
        "data_table": "业务清单",
        "form": "信息录入",
        "detail": "业务详情",
        "workflow": "处理流程",
        "timeline": "状态轨迹",
        "kanban": "任务看板",
        "chart": "趋势分析",
        "map_panel": "区域工作区",
        "relationship_graph": "对象关系",
        "mobile_list": "现场任务",
        "operation_result": "操作结果",
    }
    return labels.get(component, _text(module.get("title") or screen.get("title") or "业务区域"))


def _identity_color(identity: dict[str, Any], key: str, fallback: str) -> str:
    for container_key in ("colors", "palette", "tokens"):
        container = identity.get(container_key)
        if isinstance(container, dict):
            value = str(container.get(key) or "")
            if re.fullmatch(r"#[0-9a-fA-F]{6}", value):
                return value
    value = str(identity.get(key) or "")
    return value if re.fullmatch(r"#[0-9a-fA-F]{6}", value) else fallback


def _resolve_page_spec_palette(
    visual_identity: dict[str, Any] | None,
    color_contract: dict[str, Any] | None,
) -> tuple[str, str, str]:
    identity = visual_identity if isinstance(visual_identity, dict) else {}
    raw_palette = color_contract.get("dominant_colors") if isinstance(color_contract, dict) else []
    reference_palette = raw_palette if isinstance(raw_palette, list) else []
    reference_palette = [
        str(item).lower()
        for item in reference_palette
        if re.fullmatch(r"#[0-9a-fA-F]{6}", str(item))
    ]

    identity_accent = _identity_color(identity, "accent", "")
    identity_ink = _identity_color(identity, "sidebar", "")
    identity_canvas = _identity_color(identity, "canvas", "")

    canvas = identity_canvas or _light_reference_color(reference_palette) or "#f3f7f7"
    if _relative_luminance(canvas) < 0.82:
        canvas = "#f3f7f7"

    ink = identity_ink or _dark_reference_color(reference_palette, canvas) or "#173f48"
    if _contrast_ratio(ink, canvas) < 4.5:
        ink = "#173f48"

    accent = identity_accent or _accent_reference_color(reference_palette) or "#168779"
    if _contrast_ratio(accent, "#ffffff") < 3.0:
        accent = _darken_until_contrast(accent, "#ffffff", 3.0)
    if _contrast_ratio(accent, "#ffffff") < 3.0:
        accent = "#168779"
    return accent.lower(), ink.lower(), canvas.lower()


def _accent_reference_color(palette: list[str]) -> str:
    candidates: list[tuple[float, str]] = []
    for color in palette:
        red, green, blue = _hex_rgb(color)
        _hue, _lightness, saturation = colorsys.rgb_to_hls(red / 255, green / 255, blue / 255)
        luminance = _relative_luminance(color)
        contrast = _contrast_ratio(color, "#ffffff")
        if saturation < 0.18 or not 0.035 <= luminance <= 0.58 or contrast < 3.0:
            continue
        candidates.append(((saturation * 2.0) + contrast - abs(luminance - 0.22), color))
    return max(candidates, default=(0.0, ""))[1]


def _dark_reference_color(palette: list[str], canvas: str) -> str:
    candidates = [color for color in palette if _contrast_ratio(color, canvas) >= 4.5]
    return min(candidates, key=_relative_luminance, default="")


def _light_reference_color(palette: list[str]) -> str:
    candidates = [color for color in palette if _relative_luminance(color) >= 0.82]
    return max(candidates, key=_relative_luminance, default="")


def _darken_until_contrast(color: str, background: str, minimum: float) -> str:
    red, green, blue = _hex_rgb(color)
    for step in range(1, 9):
        factor = 1.0 - (step * 0.08)
        candidate = f"#{round(red * factor):02x}{round(green * factor):02x}{round(blue * factor):02x}"
        if _contrast_ratio(candidate, background) >= minimum:
            return candidate
    return color


def _contrast_ratio(left: str, right: str) -> float:
    left_luminance = _relative_luminance(left)
    right_luminance = _relative_luminance(right)
    lighter = max(left_luminance, right_luminance)
    darker = min(left_luminance, right_luminance)
    return (lighter + 0.05) / (darker + 0.05)


def _relative_luminance(color: str) -> float:
    channels = []
    for value in _hex_rgb(color):
        normalized = value / 255
        channels.append(normalized / 12.92 if normalized <= 0.04045 else ((normalized + 0.055) / 1.055) ** 2.4)
    return (0.2126 * channels[0]) + (0.7152 * channels[1]) + (0.0722 * channels[2])


def _hex_rgb(color: str) -> tuple[int, int, int]:
    value = str(color or "").lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", value):
        return 0, 0, 0
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _visible_scalar(value: Any, *, limit: int = 96, _depth: int = 0) -> str:
    """Return customer-facing text without leaking object representations."""
    if value is None or _depth > 4:
        return ""
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, dict):
        for key in ("label", "title", "name", "value", "status", "code", "key"):
            candidate = value.get(key)
            if candidate is not None and candidate != "":
                text = _visible_scalar(candidate, limit=limit, _depth=_depth + 1)
                if text:
                    return text
        values = [
            _visible_scalar(candidate, limit=limit, _depth=_depth + 1)
            for candidate in value.values()
            if candidate is not None and candidate != ""
        ]
        return (" / ".join(candidate for candidate in values if candidate) or "业务数据")[:limit]
    if isinstance(value, (list, tuple, set)):
        values = [
            _visible_scalar(candidate, limit=limit, _depth=_depth + 1)
            for candidate in list(value)[:4]
        ]
        text = "、".join(candidate for candidate in values if candidate)
        if len(value) > 4 and text:
            text += f"等{len(value)}项"
        return text[:limit]
    return re.sub(r"\s+", " ", str(value)).strip()[:limit]


def _text(value: Any) -> str:
    return _visible_scalar(value)


def _token(value: Any) -> str:
    return re.sub(r"[^a-z0-9_-]+", "_", str(value or "").strip().lower()).strip("_")


def _jsx_text(value: Any) -> str:
    return escape(_text(value), quote=False).replace("{", "&#123;").replace("}", "&#125;")


def _attr(value: Any) -> str:
    return escape(_text(value), quote=True).replace("{", "&#123;").replace("}", "&#125;")
