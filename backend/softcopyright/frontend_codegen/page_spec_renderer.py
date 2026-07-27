from __future__ import annotations

from html import escape
import re
from typing import Any


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
) -> dict[str, str]:
    module = module if isinstance(module, dict) else {}
    title = _text(screen.get("title") or module.get("title") or spec.get("page_key") or "业务工作台")
    caption = _text(screen.get("caption") or module.get("description") or "查看业务状态并完成当前操作")
    regions = "".join(
        _render_region(region, module=module, screen=screen, index=index)
        for index, region in enumerate(spec.get("regions") or [], start=1)
        if isinstance(region, dict)
    )
    actions = _render_actions(spec.get("actions") or [], screen=screen)
    confirmation = _render_confirmation_source(spec.get("interaction_contract") or {}, screen=screen)
    layout = _token(spec.get("layout") or "table_workspace")
    density = _token((spec.get("theme") or {}).get("density") or "comfortable")
    terminal_class = "page-spec-mobile" if str(renderer or "") in {"mobile_app", "game"} else "page-spec-desktop"
    jsx = (
        f'<div className="screen-root {css_scope} page-spec-root {terminal_class} layout-{layout} density-{density}" '
        f'data-page-structure="{_attr(creative_key)}" data-page-spec="page-spec-v1">'
        '<section className="page-spec-heading">'
        '<div className="page-spec-heading-copy">'
        f'<span className="page-spec-eyebrow">{_jsx_text(_page_kind_label(spec.get("page_kind")))}</span>'
        f'<h1>{_jsx_text(title)}</h1><p>{_jsx_text(caption)}</p>'
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
    )
    return {"jsx": jsx, "css": css}


def _render_region(region: dict[str, Any], *, module: dict[str, Any], screen: dict[str, Any], index: int) -> str:
    component = _token(region.get("component"))
    title = _text(region.get("title") or _component_title(component, module, screen))
    subtitle = _text(region.get("subtitle") or "")
    heading = (
        '<header className="region-heading">'
        f'<div><span>{index:02d}</span><h2>{_jsx_text(title)}</h2></div>'
        f'{f"<p>{_jsx_text(subtitle)}</p>" if subtitle else ""}</header>'
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
    return f'<section className="page-region region-{component}" data-region-id="{_attr(region.get("id") or component)}">{heading}{body}</section>'


def _render_filter_bar(region: dict[str, Any], *, module: dict[str, Any], screen: dict[str, Any]) -> str:
    fields = region.get("fields") or _default_fields(module, limit=4)
    controls = "".join(
        '<label className="filter-control">'
        f'<span>{_jsx_text(item.get("label") or f"条件{index}")}</span>'
        f'<input placeholder="{_attr(item.get("value") or _sample_value(item.get("label"), index))}" />'
        '</label>'
        for index, item in enumerate(fields[:4], start=1)
    )
    return f'<div className="filter-bar">{controls}<button className="filter-submit">筛选</button><button className="filter-reset">重置</button></div>'


def _render_metric_group(region: dict[str, Any], *, module: dict[str, Any], screen: dict[str, Any]) -> str:
    metrics = region.get("metrics") or region.get("items") or [
        {"label": "当前任务", "value": "28"},
        {"label": "按期完成率", "value": "96.4%"},
        {"label": "待处理异常", "value": "3"},
        {"label": "今日更新", "value": "12"},
    ]
    cards = "".join(
        '<article className="metric-card">'
        f'<span>{_jsx_text(item.get("label") or item.get("title") or f"指标{index}")}</span>'
        f'<strong>{_jsx_text(item.get("value") or _metric_value(index))}</strong>'
        f'<small>{_jsx_text(item.get("status") or item.get("meta") or "较上一周期保持稳定")}</small>'
        '</article>'
        for index, item in enumerate(metrics[:4], start=1)
    )
    return f'<div className="metric-grid">{cards}</div>'


def _render_data_table(region: dict[str, Any], *, module: dict[str, Any], screen: dict[str, Any]) -> str:
    columns = list(region.get("columns") or [])[:7] or _default_columns(module)
    items = list(region.get("items") or [])[:5]
    if not items:
        items = _default_rows(module, columns)
    head = "".join(f'<th>{_jsx_text(column)}</th>' for column in columns)
    rows = "".join(
        '<tr>'
        + "".join(f'<td>{_jsx_text(_row_value(item, column, row_index, column_index))}</td>' for column_index, column in enumerate(columns))
        + '</tr>'
        for row_index, item in enumerate(items, start=1)
    )
    return f'<div className="table-frame"><table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table></div>'


def _render_form(region: dict[str, Any], *, module: dict[str, Any], screen: dict[str, Any]) -> str:
    fields = region.get("fields") or _default_fields(module, limit=6)
    form_fields = "".join(
        '<label className="form-field">'
        f'<span>{_jsx_text(item.get("label") or f"业务字段{index}")}</span>'
        f'<input placeholder="{_attr(item.get("value") or _sample_value(item.get("label"), index))}" />'
        '</label>'
        for index, item in enumerate(fields[:6], start=1)
    )
    return f'<div className="business-form">{form_fields}</div>'


def _render_detail(region: dict[str, Any], *, module: dict[str, Any], screen: dict[str, Any]) -> str:
    items = region.get("items") or _default_detail_items(module)
    details = "".join(
        '<div className="detail-item">'
        f'<span>{_jsx_text(item.get("label") or item.get("name") or f"属性{index}")}</span>'
        f'<strong>{_jsx_text(item.get("value") or item.get("status") or _sample_value(item.get("label"), index))}</strong>'
        '</div>'
        for index, item in enumerate(items[:8], start=1)
    )
    return f'<div className="runtime-record-panel">{details}</div>'


def _render_workflow(region: dict[str, Any], *, module: dict[str, Any], screen: dict[str, Any]) -> str:
    steps = region.get("steps") or [
        {"label": "接收任务", "status": "已完成"},
        {"label": "核验业务条件", "status": "处理中"},
        {"label": "提交处理结论", "status": "待执行"},
        {"label": "归档结果证据", "status": "待执行"},
    ]
    nodes = "".join(
        '<article className="workflow-step">'
        f'<span>{index}</span><div><strong>{_jsx_text(item.get("label") or item.get("title") or f"步骤{index}")}</strong>'
        f'<small>{_jsx_text(item.get("status") or item.get("description") or "按流程执行")}</small></div></article>'
        for index, item in enumerate(steps[:7], start=1)
    )
    return f'<div className="workflow-board">{nodes}</div>'


def _render_timeline(region: dict[str, Any], *, module: dict[str, Any], screen: dict[str, Any]) -> str:
    items = region.get("items") or region.get("steps") or [
        {"time": "09:10", "label": "业务任务已创建", "description": "系统记录创建人和初始状态"},
        {"time": "10:25", "label": "责任岗位完成核验", "description": "业务条件与输入信息校验通过"},
        {"time": "11:40", "label": "处理结论已提交", "description": "结果证据同步写入审计轨迹"},
    ]
    nodes = "".join(
        '<article className="timeline-item">'
        f'<time>{_jsx_text(item.get("time") or f"{8 + index:02d}:00")}</time>'
        f'<div><strong>{_jsx_text(item.get("label") or item.get("title") or f"状态节点{index}")}</strong>'
        f'<p>{_jsx_text(item.get("description") or item.get("status") or "状态变化已记录")}</p></div></article>'
        for index, item in enumerate(items[:6], start=1)
    )
    return f'<div className="timeline">{nodes}</div>'


def _render_kanban(region: dict[str, Any], *, module: dict[str, Any], screen: dict[str, Any]) -> str:
    items = region.get("items") or [
        {"category": "待处理", "label": "核验业务输入", "owner": "业务专员"},
        {"category": "处理中", "label": "分析状态差异", "owner": "审核人员"},
        {"category": "已完成", "label": "归档处理结论", "owner": "系统管理员"},
    ]
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
    series = region.get("series") or region.get("items") or [
        {"label": "周一", "value": "68"},
        {"label": "周二", "value": "82"},
        {"label": "周三", "value": "74"},
        {"label": "周四", "value": "91"},
        {"label": "周五", "value": "86"},
    ]
    bars = "".join(
        '<div className="chart-column">'
        f'<span className="chart-value">{_jsx_text(item.get("value") or str(60 + index * 6))}</span>'
        f'<i className="chart-bar chart-bar-{min(index, 6)}"></i>'
        f'<small>{_jsx_text(item.get("label") or item.get("name") or f"周期{index}")}</small></div>'
        for index, item in enumerate(series[:6], start=1)
    )
    return f'<div className="chart-panel"><div className="chart-grid-lines"></div><div className="chart-columns">{bars}</div></div>'


def _render_map(region: dict[str, Any], *, module: dict[str, Any], screen: dict[str, Any]) -> str:
    points = region.get("points") or region.get("items") or [
        {"label": "东区作业点", "status": "正常"},
        {"label": "中心控制点", "status": "处理中"},
        {"label": "西区复核点", "status": "待复核"},
        {"label": "北区采集点", "status": "正常"},
    ]
    pins = "".join(
        f'<button className="map-pin map-pin-{min(index, 7)}"><span>{index}</span><b>{_jsx_text(item.get("label") or f"业务点位{index}")}</b><small>{_jsx_text(item.get("status") or "在线")}</small></button>'
        for index, item in enumerate(points[:7], start=1)
    )
    return f'<div className="map-workspace"><div className="map-grid"></div>{pins}<aside><strong>区域状态</strong><span>在线点位 {len(points[:7])}</span><span>数据同步正常</span></aside></div>'


def _render_relationship_graph(region: dict[str, Any], *, module: dict[str, Any], screen: dict[str, Any]) -> str:
    items = region.get("items") or [
        {"label": "主业务对象", "category": "核心"},
        {"label": "执行任务", "category": "过程"},
        {"label": "状态轨迹", "category": "证据"},
        {"label": "分析结论", "category": "结果"},
    ]
    nodes = "".join(
        f'<article className="graph-node graph-node-{min(index, 6)}"><span>{_jsx_text(item.get("category") or "对象")}</span><strong>{_jsx_text(item.get("label") or item.get("title") or f"关联对象{index}")}</strong></article>'
        for index, item in enumerate(items[:6], start=1)
    )
    return f'<div className="relationship-graph"><div className="graph-links"></div>{nodes}</div>'


def _render_mobile_list(region: dict[str, Any], *, module: dict[str, Any], screen: dict[str, Any]) -> str:
    items = region.get("items") or _default_rows(module, ["任务", "状态", "责任人"])
    cards = "".join(
        '<article className="mobile-list-item">'
        f'<div><strong>{_jsx_text(item.get("label") or item.get("title") or f"现场任务{index}")}</strong>'
        f'<span>{_jsx_text(item.get("description") or item.get("owner") or "按计划完成现场处理")}</span></div>'
        f'<b>{_jsx_text(item.get("status") or "进行中")}</b></article>'
        for index, item in enumerate(items[:7], start=1)
    )
    return f'<div className="mobile-list">{cards}</div>'


def _render_operation_result(region: dict[str, Any], *, module: dict[str, Any], screen: dict[str, Any]) -> str:
    items = region.get("items") or [
        {"label": "处理状态", "value": screen.get("interaction_post_state") or "已完成"},
        {"label": "结果证据", "value": screen.get("interaction_result_evidence") or "状态轨迹和操作日志"},
        {"label": "责任岗位", "value": screen.get("interaction_role") or "业务操作员"},
    ]
    content = "".join(
        f'<div><span>{_jsx_text(item.get("label") or f"结果{index}")}</span><strong>{_jsx_text(item.get("value") or item.get("status") or "已记录")}</strong></div>'
        for index, item in enumerate(items[:6], start=1)
    )
    return f'<div className="operation-result"><header><span>✓</span><div><strong>操作结果已记录</strong><p>当前页面状态与审计证据已同步更新</p></div></header><section>{content}</section></div>'


def _render_actions(actions: list[dict[str, Any]], *, screen: dict[str, Any]) -> str:
    if not actions:
        return ""
    buttons = "".join(
        f'<button className="page-action action-{_token(item.get("variant") or "secondary")}" data-action="{_attr(item.get("action_key") or f"action_{index}")}">{_jsx_text(item.get("label") or f"操作{index}")}</button>'
        for index, item in enumerate(actions[:6], start=1)
    )
    return f'<div className="page-spec-actions">{buttons}</div>'


def _render_confirmation_source(contract: dict[str, Any], *, screen: dict[str, Any]) -> str:
    requires_confirmation = bool(contract.get("requires_confirmation") or screen.get("requires_confirmation"))
    if not requires_confirmation:
        return ""
    action = _text(screen.get("interaction_action") or "提交当前操作")
    fields = list(contract.get("input_fields") or screen.get("interaction_input_fields") or [])[:5]
    items = "".join(
        f'<div data-confirm-item data-label="{_attr(field)}" data-value="{_attr(_sample_value(field, index))}"></div>'
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
) -> str:
    palette = color_contract.get("dominant_colors") if isinstance(color_contract, dict) else []
    palette = palette if isinstance(palette, list) else []
    palette = [str(item) for item in palette if re.fullmatch(r"#[0-9a-fA-F]{6}", str(item))]
    accent = palette[1] if len(palette) > 1 else _identity_color(visual_identity, "accent", "#168779")
    ink = palette[0] if palette else _identity_color(visual_identity, "sidebar", "#173f48")
    canvas = palette[2] if len(palette) > 2 else "#f3f7f7"
    scope = f".{css_scope}"
    mobile = str(renderer or "") in {"mobile_app", "game"}
    terminal_rules = (
        f"{scope}{{grid-template-rows:auto minmax(0,1fr);padding:26px 24px 28px;gap:20px;}}"
        f"{scope} .page-spec-heading{{align-items:flex-start;}}{scope} .page-spec-workspace{{grid-template-columns:1fr;grid-auto-rows:minmax(0,auto);overflow:hidden auto;padding-right:4px;}}"
        f"{scope} .page-region{{min-height:0;}}{scope} .metric-grid{{grid-template-columns:repeat(2,minmax(0,1fr));}}"
        f"{scope} .business-form{{grid-template-columns:1fr 1fr;}}{scope} .table-frame{{max-height:420px;}}"
    ) if mobile else (
        f"{scope}{{grid-template-rows:94px minmax(0,1fr);padding:24px 28px 28px;gap:18px;}}"
        f"{scope} .page-spec-workspace{{grid-template-columns:repeat(12,minmax(0,1fr));grid-auto-rows:minmax(112px,auto);}}"
        f"{scope} .region-filter_bar,{scope} .region-operation_result{{grid-column:span 12;}}"
        f"{scope} .region-data_table,{scope} .region-kanban,{scope} .region-chart,{scope} .region-map_panel,{scope} .region-relationship_graph{{grid-column:span 8;}}"
        f"{scope} .region-metric_group,{scope} .region-form,{scope} .region-detail,{scope} .region-workflow,{scope} .region-timeline{{grid-column:span 4;}}"
        f"{scope} .page-region:only-child{{grid-column:span 12;}}"
    )
    return f"""
{scope}{{--ps-accent:{accent};--ps-ink:{ink};--ps-canvas:{canvas};height:100%;min-height:0;box-sizing:border-box;display:grid;background:linear-gradient(145deg,color-mix(in srgb,var(--ps-canvas) 88%,#fff),#f8fbfb 60%,color-mix(in srgb,var(--ps-accent) 7%,#fff));color:color-mix(in srgb,var(--ps-ink) 88%,#111827);overflow:hidden;font-family:"Microsoft YaHei UI","PingFang SC",sans-serif;}}
{scope} *{{box-sizing:border-box;min-width:0;}}
{scope} button,{scope} input{{font:inherit;}}
{scope} .page-spec-heading{{display:flex;justify-content:space-between;gap:24px;min-height:0;overflow:hidden;}}
{scope} .page-spec-heading-copy{{min-width:0;display:flex;flex-direction:column;justify-content:center;}}
{scope} .page-spec-eyebrow{{width:max-content;max-width:100%;margin-bottom:6px;padding:4px 9px;border-radius:999px;background:color-mix(in srgb,var(--ps-accent) 13%,#fff);color:var(--ps-accent);font-size:10px;font-weight:800;letter-spacing:.12em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
{scope} h1,{scope} h2,{scope} p{{margin:0;}}
{scope} .page-spec-heading h1{{max-width:760px;font-size:24px;line-height:1.2;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}}
{scope} .page-spec-heading p{{max-width:760px;margin-top:7px;color:color-mix(in srgb,var(--ps-ink) 58%,#fff);font-size:12px;line-height:1.5;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}}
{scope} .page-spec-actions{{display:flex;align-items:center;justify-content:flex-end;gap:9px;flex-wrap:wrap;align-content:center;}}
{scope} .page-action{{height:34px;padding:0 15px;border:1px solid color-mix(in srgb,var(--ps-ink) 18%,#fff);border-radius:8px;background:#fff;color:color-mix(in srgb,var(--ps-ink) 78%,#111827);font-size:11px;font-weight:750;white-space:nowrap;}}
{scope} .action-primary{{border-color:var(--ps-accent);background:var(--ps-accent);color:#fff;box-shadow:0 7px 18px color-mix(in srgb,var(--ps-accent) 24%,transparent);}}
{scope} .action-danger{{border-color:#c94242;background:#c94242;color:#fff;}}
{scope} .page-spec-workspace{{min-height:0;display:grid;gap:14px;overflow:hidden;}}
{scope} .page-region{{min-height:0;padding:15px 16px;border:1px solid color-mix(in srgb,var(--ps-ink) 14%,#fff);border-radius:14px;background:rgba(255,255,255,.94);box-shadow:0 8px 24px color-mix(in srgb,var(--ps-ink) 8%,transparent);overflow:hidden;display:flex;flex-direction:column;gap:12px;}}
{scope} .region-heading{{display:flex;align-items:flex-start;justify-content:space-between;gap:14px;flex:0 0 auto;overflow:hidden;}}
{scope} .region-heading>div{{display:flex;align-items:center;gap:8px;min-width:0;}}
{scope} .region-heading>div>span{{flex:0 0 auto;color:var(--ps-accent);font-size:9px;font-weight:900;}}
{scope} .region-heading h2{{font-size:13px;line-height:1.35;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
{scope} .region-heading p{{max-width:52%;color:color-mix(in srgb,var(--ps-ink) 50%,#fff);font-size:10px;line-height:1.4;text-align:right;display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;overflow:hidden;}}
{scope} .filter-bar{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr)) auto auto;gap:10px;align-items:end;}}
{scope} .filter-control,{scope} .form-field{{display:flex;flex-direction:column;gap:5px;min-width:0;}}
{scope} .filter-control span,{scope} .form-field span{{color:color-mix(in srgb,var(--ps-ink) 62%,#fff);font-size:10px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
{scope} input{{height:33px;width:100%;padding:0 10px;border:1px solid color-mix(in srgb,var(--ps-ink) 16%,#fff);border-radius:7px;background:#fff;color:var(--ps-ink);font-size:10px;outline:none;}}
{scope} .filter-submit,{scope} .filter-reset{{height:33px;padding:0 14px;border-radius:7px;font-size:10px;font-weight:800;white-space:nowrap;}}
{scope} .filter-submit{{border:1px solid var(--ps-accent);background:var(--ps-accent);color:#fff;}}{scope} .filter-reset{{border:1px solid color-mix(in srgb,var(--ps-ink) 18%,#fff);background:#fff;color:var(--ps-ink);}}
{scope} .metric-grid{{min-height:0;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;}}
{scope} .metric-card{{min-height:78px;padding:12px;border:1px solid color-mix(in srgb,var(--ps-accent) 14%,#fff);border-radius:10px;background:linear-gradient(145deg,#fff,color-mix(in srgb,var(--ps-accent) 6%,#fff));display:flex;flex-direction:column;justify-content:center;overflow:hidden;}}
{scope} .metric-card span,{scope} .metric-card small{{font-size:9px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}{scope} .metric-card span{{color:color-mix(in srgb,var(--ps-ink) 58%,#fff);}}{scope} .metric-card strong{{margin:5px 0 3px;color:var(--ps-accent);font-size:22px;line-height:1;}}{scope} .metric-card small{{color:color-mix(in srgb,var(--ps-ink) 48%,#fff);}}
{scope} .table-frame{{min-height:0;overflow:auto;border:1px solid color-mix(in srgb,var(--ps-ink) 12%,#fff);border-radius:9px;}}
{scope} table{{width:100%;border-collapse:collapse;table-layout:fixed;font-size:10px;}}{scope} th{{height:34px;padding:0 9px;background:color-mix(in srgb,var(--ps-accent) 9%,#fff);color:color-mix(in srgb,var(--ps-ink) 74%,#111827);text-align:left;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}{scope} td{{height:38px;padding:0 9px;border-top:1px solid color-mix(in srgb,var(--ps-ink) 9%,#fff);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}{scope} tbody tr:nth-child(even){{background:#fbfdfd;}}
{scope} .business-form{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;overflow:hidden;}}
{scope} .runtime-record-panel{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;min-height:0;overflow:hidden;}}
{scope} .detail-item{{padding:9px 10px;border-radius:8px;background:color-mix(in srgb,var(--ps-canvas) 60%,#fff);overflow:hidden;}}{scope} .detail-item span,{scope} .detail-item strong{{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}{scope} .detail-item span{{color:color-mix(in srgb,var(--ps-ink) 52%,#fff);font-size:9px;}}{scope} .detail-item strong{{margin-top:4px;font-size:11px;}}
{scope} .workflow-board{{display:flex;flex-direction:column;gap:8px;min-height:0;overflow:hidden;}}{scope} .workflow-step{{display:grid;grid-template-columns:24px minmax(0,1fr);gap:9px;align-items:center;padding:8px;border-radius:9px;background:color-mix(in srgb,var(--ps-canvas) 58%,#fff);overflow:hidden;}}{scope} .workflow-step>span{{width:24px;height:24px;border-radius:50%;display:grid;place-items:center;background:var(--ps-accent);color:#fff;font-size:9px;font-weight:900;}}{scope} .workflow-step strong,{scope} .workflow-step small{{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}{scope} .workflow-step strong{{font-size:10px;}}{scope} .workflow-step small{{margin-top:3px;color:color-mix(in srgb,var(--ps-ink) 48%,#fff);font-size:9px;}}
{scope} .timeline{{min-height:0;display:flex;flex-direction:column;gap:8px;overflow:hidden;}}{scope} .timeline-item{{display:grid;grid-template-columns:46px minmax(0,1fr);gap:10px;position:relative;}}{scope} .timeline-item time{{padding-top:2px;color:var(--ps-accent);font-size:9px;font-weight:850;}}{scope} .timeline-item div{{padding:0 0 9px 12px;border-left:2px solid color-mix(in srgb,var(--ps-accent) 28%,#fff);overflow:hidden;}}{scope} .timeline-item strong,{scope} .timeline-item p{{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}{scope} .timeline-item strong{{font-size:10px;}}{scope} .timeline-item p{{margin-top:3px;color:color-mix(in srgb,var(--ps-ink) 50%,#fff);font-size:9px;}}
{scope} .kanban-board{{min-height:0;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;overflow:hidden;}}{scope} .kanban-column{{min-height:0;padding:9px;border-radius:10px;background:color-mix(in srgb,var(--ps-canvas) 64%,#fff);overflow:hidden;}}{scope} .kanban-column header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;font-size:10px;font-weight:800;}}{scope} .kanban-column header b{{min-width:20px;height:20px;padding:0 6px;border-radius:10px;background:color-mix(in srgb,var(--ps-accent) 14%,#fff);color:var(--ps-accent);display:grid;place-items:center;font-size:9px;}}{scope} .kanban-column article{{margin-top:7px;padding:9px;border:1px solid color-mix(in srgb,var(--ps-ink) 10%,#fff);border-radius:8px;background:#fff;overflow:hidden;}}{scope} .kanban-column strong,{scope} .kanban-column article span{{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}{scope} .kanban-column strong{{font-size:10px;}}{scope} .kanban-column article span{{margin-top:5px;color:color-mix(in srgb,var(--ps-ink) 50%,#fff);font-size:9px;}}
{scope} .chart-panel{{position:relative;min-height:0;flex:1;border-radius:10px;background:linear-gradient(to top,color-mix(in srgb,var(--ps-accent) 5%,#fff),#fff);overflow:hidden;}}{scope} .chart-grid-lines{{position:absolute;inset:12px 10px 28px;background:repeating-linear-gradient(to top,transparent 0,transparent 24px,color-mix(in srgb,var(--ps-ink) 8%,#fff) 25px);}}{scope} .chart-columns{{position:absolute;inset:18px 12px 10px;display:flex;align-items:flex-end;justify-content:space-around;gap:8px;}}{scope} .chart-column{{height:100%;flex:1;display:grid;grid-template-rows:18px 1fr 18px;justify-items:center;align-items:end;}}{scope} .chart-value,{scope} .chart-column small{{font-size:8px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%;}}{scope} .chart-bar{{width:min(28px,70%);border-radius:6px 6px 2px 2px;background:linear-gradient(to top,var(--ps-accent),color-mix(in srgb,var(--ps-accent) 48%,#fff));}}{scope} .chart-bar-1{{height:42%;}}{scope} .chart-bar-2{{height:61%;}}{scope} .chart-bar-3{{height:52%;}}{scope} .chart-bar-4{{height:78%;}}{scope} .chart-bar-5{{height:68%;}}{scope} .chart-bar-6{{height:86%;}}
{scope} .map-workspace{{position:relative;min-height:190px;flex:1;border-radius:10px;background:linear-gradient(135deg,color-mix(in srgb,var(--ps-accent) 8%,#fff),#eef5f4);overflow:hidden;}}{scope} .map-grid{{position:absolute;inset:0;background-image:linear-gradient(color-mix(in srgb,var(--ps-ink) 7%,transparent) 1px,transparent 1px),linear-gradient(90deg,color-mix(in srgb,var(--ps-ink) 7%,transparent) 1px,transparent 1px);background-size:34px 34px;transform:rotate(-5deg) scale(1.1);}}{scope} .map-pin{{position:absolute;width:112px;padding:7px 8px;border:1px solid color-mix(in srgb,var(--ps-accent) 28%,#fff);border-radius:9px;background:#fff;color:var(--ps-ink);box-shadow:0 6px 16px color-mix(in srgb,var(--ps-ink) 12%,transparent);display:grid;grid-template-columns:20px minmax(0,1fr);grid-template-rows:auto auto;column-gap:6px;text-align:left;overflow:hidden;}}{scope} .map-pin span{{grid-row:span 2;width:20px;height:20px;border-radius:50%;display:grid;place-items:center;background:var(--ps-accent);color:#fff;font-size:8px;font-weight:900;}}{scope} .map-pin b,{scope} .map-pin small{{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}{scope} .map-pin b{{font-size:9px;}}{scope} .map-pin small{{font-size:8px;color:color-mix(in srgb,var(--ps-ink) 48%,#fff);}}{scope} .map-pin-1{{left:8%;top:18%;}}{scope} .map-pin-2{{left:38%;top:38%;}}{scope} .map-pin-3{{left:66%;top:16%;}}{scope} .map-pin-4{{left:20%;top:66%;}}{scope} .map-pin-5{{left:58%;top:68%;}}{scope} .map-pin-6{{left:76%;top:46%;}}{scope} .map-pin-7{{left:43%;top:10%;}}{scope} .map-workspace aside{{position:absolute;right:10px;bottom:10px;width:128px;padding:9px;border-radius:8px;background:rgba(255,255,255,.92);display:flex;flex-direction:column;gap:4px;}}{scope} .map-workspace aside strong{{font-size:9px;}}{scope} .map-workspace aside span{{font-size:8px;color:color-mix(in srgb,var(--ps-ink) 52%,#fff);}}
{scope} .relationship-graph{{position:relative;min-height:190px;flex:1;border-radius:10px;background:radial-gradient(circle at center,color-mix(in srgb,var(--ps-accent) 10%,#fff),#fff 58%);overflow:hidden;}}{scope} .graph-links{{position:absolute;inset:50%;width:1px;height:1px;box-shadow:-150px -55px 0 1px color-mix(in srgb,var(--ps-accent) 24%,#fff),145px -52px 0 1px color-mix(in srgb,var(--ps-accent) 24%,#fff),-130px 60px 0 1px color-mix(in srgb,var(--ps-accent) 24%,#fff),135px 62px 0 1px color-mix(in srgb,var(--ps-accent) 24%,#fff);}}{scope} .graph-node{{position:absolute;width:116px;padding:9px;border:1px solid color-mix(in srgb,var(--ps-accent) 22%,#fff);border-radius:10px;background:#fff;box-shadow:0 7px 18px color-mix(in srgb,var(--ps-ink) 10%,transparent);overflow:hidden;}}{scope} .graph-node span,{scope} .graph-node strong{{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}{scope} .graph-node span{{color:var(--ps-accent);font-size:8px;}}{scope} .graph-node strong{{margin-top:4px;font-size:10px;}}{scope} .graph-node-1{{left:calc(50% - 58px);top:calc(50% - 29px);background:color-mix(in srgb,var(--ps-accent) 12%,#fff);}}{scope} .graph-node-2{{left:5%;top:12%;}}{scope} .graph-node-3{{right:5%;top:14%;}}{scope} .graph-node-4{{left:8%;bottom:10%;}}{scope} .graph-node-5{{right:8%;bottom:10%;}}{scope} .graph-node-6{{right:6%;top:45%;}}
{scope} .mobile-list{{display:flex;flex-direction:column;gap:9px;min-height:0;overflow:hidden;}}{scope} .mobile-list-item{{min-height:58px;padding:11px 12px;border:1px solid color-mix(in srgb,var(--ps-ink) 11%,#fff);border-radius:11px;background:#fff;display:flex;align-items:center;justify-content:space-between;gap:12px;overflow:hidden;}}{scope} .mobile-list-item div{{min-width:0;}}{scope} .mobile-list-item strong,{scope} .mobile-list-item span{{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}{scope} .mobile-list-item strong{{font-size:11px;}}{scope} .mobile-list-item span{{margin-top:5px;color:color-mix(in srgb,var(--ps-ink) 50%,#fff);font-size:9px;}}{scope} .mobile-list-item b{{flex:0 0 auto;padding:5px 8px;border-radius:999px;background:color-mix(in srgb,var(--ps-accent) 12%,#fff);color:var(--ps-accent);font-size:9px;}}
{scope} .operation-result{{display:grid;grid-template-columns:minmax(220px,.85fr) 1.4fr;gap:14px;align-items:stretch;overflow:hidden;}}{scope} .operation-result>header{{padding:12px;border-radius:10px;background:linear-gradient(135deg,var(--ps-accent),color-mix(in srgb,var(--ps-accent) 70%,var(--ps-ink)));color:#fff;display:flex;align-items:center;gap:10px;overflow:hidden;}}{scope} .operation-result>header>span{{flex:0 0 auto;width:30px;height:30px;border-radius:50%;display:grid;place-items:center;background:rgba(255,255,255,.2);font-weight:900;}}{scope} .operation-result>header strong,{scope} .operation-result>header p{{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}{scope} .operation-result>header strong{{font-size:11px;}}{scope} .operation-result>header p{{margin-top:4px;font-size:9px;opacity:.82;}}{scope} .operation-result>section{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;}}{scope} .operation-result>section>div{{padding:10px;border-radius:9px;background:color-mix(in srgb,var(--ps-canvas) 62%,#fff);overflow:hidden;}}{scope} .operation-result>section span,{scope} .operation-result>section strong{{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}{scope} .operation-result>section span{{font-size:8px;color:color-mix(in srgb,var(--ps-ink) 48%,#fff);}}{scope} .operation-result>section strong{{margin-top:5px;font-size:10px;}}
{terminal_rules}
""".strip()


def _default_columns(module: dict[str, Any]) -> list[str]:
    fields = [str(item) for item in (module.get("data_fields") or []) if str(item).strip()]
    return (fields[:5] or ["业务编号", "业务对象", "责任岗位", "当前状态", "更新时间"])


def _default_rows(module: dict[str, Any], columns: list[str]) -> list[dict[str, str]]:
    title = _text(module.get("title") or "业务任务")
    return [
        {
            "label": f"{title}{index}",
            "title": f"{title}{index}",
            "status": ("处理中", "已完成", "待复核", "正常流转", "已归档")[(index - 1) % 5],
            "owner": ("业务专员", "审核人员", "主管人员", "系统管理员")[(index - 1) % 4],
            "value": f"{title[:4]}-{202600 + index}",
        }
        for index in range(1, 6)
    ]


def _default_fields(module: dict[str, Any], *, limit: int) -> list[dict[str, str]]:
    fields = [str(item) for item in (module.get("data_fields") or []) if str(item).strip()]
    if not fields:
        fields = ["业务编号", "业务对象", "责任岗位", "当前状态", "计划时间", "处理结论"]
    return [{"label": field, "value": _sample_value(field, index)} for index, field in enumerate(fields[:limit], start=1)]


def _default_detail_items(module: dict[str, Any]) -> list[dict[str, str]]:
    return _default_fields(module, limit=8)


def _row_value(item: dict[str, Any], column: str, row_index: int, column_index: int) -> str:
    direct = item.get(column)
    if direct:
        return str(direct)
    keys = ("label", "title", "value", "owner", "status", "time", "meta")
    value = item.get(keys[column_index % len(keys)])
    if value:
        return str(value)
    return _sample_value(column, row_index)


def _sample_value(label: Any, index: int) -> str:
    text = str(label or "")
    if any(term in text for term in ("状态", "结论")):
        return ("处理中", "已完成", "待复核", "正常流转")[(index - 1) % 4]
    if any(term in text for term in ("时间", "日期")):
        return f"2026-07-{18 + index:02d}"
    if any(term in text for term in ("岗位", "人员", "责任")):
        return ("业务专员", "审核人员", "主管人员")[(index - 1) % 3]
    if any(term in text for term in ("编号", "编码", "ID")):
        return f"NO-202607-{index:03d}"
    return f"已核验{text or '业务信息'}"


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


def _page_kind_label(value: Any) -> str:
    labels = {
        "login": "安全登录",
        "dashboard": "业务总览",
        "module": "模块工作台",
        "operation": "业务操作",
        "statistics": "统计分析",
        "general": "业务页面",
    }
    return labels.get(str(value or "general"), "业务页面")


def _identity_color(identity: dict[str, Any], key: str, fallback: str) -> str:
    for container_key in ("colors", "palette", "tokens"):
        container = identity.get(container_key)
        if isinstance(container, dict):
            value = str(container.get(key) or "")
            if re.fullmatch(r"#[0-9a-fA-F]{6}", value):
                return value
    value = str(identity.get(key) or "")
    return value if re.fullmatch(r"#[0-9a-fA-F]{6}", value) else fallback


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _token(value: Any) -> str:
    return re.sub(r"[^a-z0-9_-]+", "_", str(value or "").strip().lower()).strip("_")


def _jsx_text(value: Any) -> str:
    return escape(_text(value), quote=False).replace("{", "&#123;").replace("}", "&#125;")


def _attr(value: Any) -> str:
    return escape(_text(value), quote=True).replace("{", "&#123;").replace("}", "&#125;")
