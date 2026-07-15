from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from typing import Any


@dataclass(frozen=True)
class VisualIdentitySpec:
    identity_signature: str
    visual_seed: str
    palette_key: str
    layout_variant: str
    nav_model: str
    workspace_shape: str
    login_pattern: str
    dashboard_composition: str
    module_composition_cycle: tuple[str, ...]
    palette: dict[str, str] = field(default_factory=dict)
    table_density: str = "regular"
    chart_style: str = "bar"
    surface_style: str = "plain"
    component_rhythm: str = "regular"

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity_signature": self.identity_signature,
            "visual_seed": self.visual_seed,
            "palette_key": self.palette_key,
            "palette": dict(self.palette),
            "layout_variant": self.layout_variant,
            "nav_model": self.nav_model,
            "workspace_shape": self.workspace_shape,
            "login_pattern": self.login_pattern,
            "dashboard_composition": self.dashboard_composition,
            "module_composition_cycle": list(self.module_composition_cycle),
            "table_density": self.table_density,
            "chart_style": self.chart_style,
            "surface_style": self.surface_style,
            "component_rhythm": self.component_rhythm,
        }


_PALETTES: dict[str, dict[str, str]] = {
    "harbor_teal": {"accent": "#0f766e", "accent_soft": "#ecfdf5", "sidebar": "#123c40", "canvas": "#f4fbf8"},
    "civic_blue": {"accent": "#2563eb", "accent_soft": "#eff6ff", "sidebar": "#17356f", "canvas": "#f5f8ff"},
    "signal_green": {"accent": "#16a34a", "accent_soft": "#f0fdf4", "sidebar": "#14532d", "canvas": "#f2fbf5"},
    "amber_ops": {"accent": "#d97706", "accent_soft": "#fff7ed", "sidebar": "#4a2c0b", "canvas": "#fffaf0"},
    "slate_cyan": {"accent": "#0891b2", "accent_soft": "#ecfeff", "sidebar": "#164e63", "canvas": "#f2fbfd"},
    "indigo_line": {"accent": "#4f46e5", "accent_soft": "#eef2ff", "sidebar": "#1e1b4b", "canvas": "#f6f7ff"},
    "rose_audit": {"accent": "#be123c", "accent_soft": "#fff1f2", "sidebar": "#4c1d2f", "canvas": "#fff6f7"},
    "graphite_lime": {"accent": "#65a30d", "accent_soft": "#f7fee7", "sidebar": "#25330b", "canvas": "#fbfdf3"},
    "violet_data": {"accent": "#7c3aed", "accent_soft": "#f5f3ff", "sidebar": "#312e81", "canvas": "#f8f7ff"},
    "steel_orange": {"accent": "#ea580c", "accent_soft": "#fff7ed", "sidebar": "#3c2a1d", "canvas": "#fff8f3"},
}

_LAYOUTS = ("classic", "workflow", "map", "pipeline", "risk", "kanban", "matrix", "command")
_NAV_MODELS = ("side_menu", "top_tabs", "rail")
_WORKSPACE_SHAPES = ("ledger_split", "board_columns", "freeform_grid", "process_lane", "case_desk", "triage_console", "monitor_wall")
_LOGIN_PATTERNS = ("split_brand", "center_card", "left_product_panel", "security_console", "mobile_authorize")
_DASHBOARD_COMPOSITIONS = (
    "metrics_then_queue",
    "map_first",
    "pipeline_lanes",
    "case_timeline",
    "matrix_heatmap",
    "command_wall",
    "kanban_overview",
    "chart_focus",
)
_TABLE_DENSITIES = ("compact", "regular", "roomy")
_CHART_STYLES = ("bar", "line", "stacked", "radar", "donut", "spark")
_SURFACE_STYLES = ("plain", "panelled", "outlined", "tinted", "terminal")
_COMPONENT_RHYTHMS = ("compact", "regular", "spacious", "instrumented")

_SHAPE_HINTS: dict[str, dict[str, Any]] = {
    "mini_program": {
        "layouts": ("workflow", "kanban", "classic"),
        "navs": ("top_tabs", "side_menu"),
        "workspaces": ("board_columns", "case_desk", "ledger_split"),
        "login": ("mobile_authorize", "center_card"),
        "dashboard": ("kanban_overview", "chart_focus", "metrics_then_queue"),
    },
    "mobile_app": {
        "layouts": ("workflow", "kanban", "classic"),
        "navs": ("top_tabs", "side_menu"),
        "workspaces": ("case_desk", "board_columns", "ledger_split"),
        "login": ("mobile_authorize", "center_card"),
        "dashboard": ("kanban_overview", "chart_focus", "metrics_then_queue"),
    },
    "gis_map": {
        "layouts": ("map", "command", "matrix"),
        "navs": ("side_menu", "top_tabs", "rail"),
        "workspaces": ("freeform_grid", "monitor_wall", "ledger_split"),
        "login": ("left_product_panel", "split_brand"),
        "dashboard": ("map_first", "command_wall", "matrix_heatmap"),
    },
    "industrial_hmi": {
        "layouts": ("command", "matrix", "pipeline"),
        "navs": ("top_tabs", "rail", "side_menu"),
        "workspaces": ("monitor_wall", "process_lane", "freeform_grid"),
        "login": ("security_console", "split_brand"),
        "dashboard": ("command_wall", "chart_focus", "pipeline_lanes"),
    },
    "cloud_ops_console": {
        "layouts": ("pipeline", "matrix", "command"),
        "navs": ("rail", "top_tabs", "side_menu"),
        "workspaces": ("process_lane", "monitor_wall", "freeform_grid"),
        "login": ("security_console", "split_brand"),
        "dashboard": ("pipeline_lanes", "chart_focus", "matrix_heatmap"),
    },
    "ai_pipeline": {
        "layouts": ("pipeline", "matrix", "workflow"),
        "navs": ("side_menu", "rail", "top_tabs"),
        "workspaces": ("process_lane", "freeform_grid", "case_desk"),
        "login": ("security_console", "split_brand"),
        "dashboard": ("pipeline_lanes", "matrix_heatmap", "chart_focus"),
    },
    "legacy_windows": {
        "layouts": ("classic", "matrix", "workflow"),
        "navs": ("side_menu", "top_tabs"),
        "workspaces": ("ledger_split", "case_desk", "board_columns"),
        "login": ("center_card", "split_brand"),
        "dashboard": ("metrics_then_queue", "matrix_heatmap", "case_timeline"),
    },
    "medical_workstation": {
        "layouts": ("workflow", "kanban", "matrix"),
        "navs": ("top_tabs", "side_menu", "rail"),
        "workspaces": ("case_desk", "board_columns", "ledger_split"),
        "login": ("center_card", "split_brand"),
        "dashboard": ("case_timeline", "metrics_then_queue", "chart_focus"),
    },
    "web_command_center": {
        "layouts": ("command", "map", "matrix"),
        "navs": ("top_tabs", "side_menu", "rail"),
        "workspaces": ("monitor_wall", "freeform_grid", "triage_console"),
        "login": ("security_console", "left_product_panel"),
        "dashboard": ("command_wall", "map_first", "matrix_heatmap"),
    },
}

_SHAPE_CYCLES: dict[str, tuple[str, ...]] = {
    "gis_map": ("admin_map", "admin_board", "admin_table", "admin_risk", "admin_form", "admin_matrix"),
    "industrial_hmi": ("admin_risk", "admin_pipeline", "admin_matrix", "admin_table", "admin_board", "admin_form"),
    "cloud_ops_console": ("admin_pipeline", "admin_risk", "admin_table", "admin_board", "admin_matrix", "admin_form"),
    "ai_pipeline": ("admin_pipeline", "admin_matrix", "admin_table", "admin_form", "admin_risk", "admin_board"),
    "legacy_windows": ("admin_table", "admin_form", "admin_case", "admin_matrix", "admin_board", "admin_risk"),
    "medical_workstation": ("admin_case", "admin_board", "admin_form", "admin_table", "admin_risk", "admin_matrix"),
    "web_command_center": ("admin_risk", "admin_map", "admin_board", "admin_pipeline", "admin_table", "admin_matrix"),
    "desktop_web": ("admin_table", "admin_board", "admin_form", "admin_case", "admin_pipeline", "admin_risk"),
}


def build_visual_identity_spec(
    task: Any,
    blueprint: Any,
    product_experience_spec: Any,
    attempt: int = 0,
) -> VisualIdentitySpec:
    seed_payload = _seed_payload(task, blueprint, product_experience_spec, attempt)
    seed_text = json.dumps(seed_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = sha256(seed_text.encode("utf-8")).hexdigest()
    shape = str(getattr(product_experience_spec, "experience_shape", "") or seed_payload.get("experience_shape") or "desktop_web")
    profile = _SHAPE_HINTS.get(shape, {})
    layout_variant = _pick(profile.get("layouts") or _LAYOUTS, digest, 0)
    nav_model = _pick(profile.get("navs") or _NAV_MODELS, digest, 1)
    workspace_shape = _pick(profile.get("workspaces") or _WORKSPACE_SHAPES, digest, 2)
    login_pattern = _pick(profile.get("login") or _LOGIN_PATTERNS, digest, 3)
    dashboard_composition = _pick(profile.get("dashboard") or _DASHBOARD_COMPOSITIONS, digest, 4)
    palette_key = _pick(tuple(_PALETTES), digest, 5)
    table_density = _pick(_TABLE_DENSITIES, digest, 6)
    chart_style = _pick(_CHART_STYLES, digest, 7)
    surface_style = _pick(_SURFACE_STYLES, digest, 8)
    component_rhythm = _pick(_COMPONENT_RHYTHMS, digest, 9)
    cycle = _module_cycle(shape, layout_variant, digest)
    signature_payload = {
        "seed": seed_payload,
        "palette_key": palette_key,
        "layout_variant": layout_variant,
        "nav_model": nav_model,
        "workspace_shape": workspace_shape,
        "login_pattern": login_pattern,
        "dashboard_composition": dashboard_composition,
        "module_composition_cycle": cycle,
        "table_density": table_density,
        "chart_style": chart_style,
        "surface_style": surface_style,
        "component_rhythm": component_rhythm,
    }
    signature = sha256(
        json.dumps(signature_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:20]
    return VisualIdentitySpec(
        identity_signature=signature,
        visual_seed=digest[:24],
        palette_key=palette_key,
        palette=dict(_PALETTES[palette_key]),
        layout_variant=str(layout_variant),
        nav_model=str(nav_model),
        workspace_shape=str(workspace_shape),
        login_pattern=str(login_pattern),
        dashboard_composition=str(dashboard_composition),
        module_composition_cycle=tuple(str(item) for item in cycle),
        table_density=str(table_density),
        chart_style=str(chart_style),
        surface_style=str(surface_style),
        component_rhythm=str(component_rhythm),
    )


def visual_identity_matches_task(
    data: dict[str, Any] | None,
    task: Any,
    blueprint: Any,
    product_experience_spec: Any,
) -> bool:
    if not isinstance(data, dict):
        return False
    expected = build_visual_identity_spec(task, blueprint, product_experience_spec, attempt=int(data.get("attempt") or 0))
    return (
        str(data.get("identity_signature") or "") == expected.identity_signature
        and str(data.get("palette_key") or "") == expected.palette_key
        and str(data.get("layout_variant") or "") == expected.layout_variant
        and str(data.get("nav_model") or "") == expected.nav_model
        and str(data.get("workspace_shape") or "") == expected.workspace_shape
    )


def identity_design_brief_fields(spec: VisualIdentitySpec) -> dict[str, Any]:
    data = spec.to_dict()
    palette = data.get("palette") if isinstance(data.get("palette"), dict) else {}
    return {
        "visual_identity_spec": data,
        "identity_signature": spec.identity_signature,
        "visual_seed": spec.visual_seed,
        "palette_key": spec.palette_key,
        "layout_family": spec.layout_variant,
        "layout_variant": spec.layout_variant,
        "nav_model": spec.nav_model,
        "workspace_shape": spec.workspace_shape,
        "login_pattern": spec.login_pattern,
        "dashboard_composition": spec.dashboard_composition,
        "dashboard_pattern": _dashboard_composition_label(spec.dashboard_composition),
        "module_pattern": _module_cycle_label(spec.module_composition_cycle),
        "module_composition_cycle": list(spec.module_composition_cycle),
        "table_density": spec.table_density,
        "chart_style": spec.chart_style,
        "surface_style": spec.surface_style,
        "component_rhythm": spec.component_rhythm,
        "accent": str(palette.get("accent") or ""),
        "accent_soft": str(palette.get("accent_soft") or ""),
        "sidebar": str(palette.get("sidebar") or ""),
        "canvas": str(palette.get("canvas") or ""),
    }


def reroll_ui_visual_identity(ui_blueprint: Any, attempt: int) -> Any:
    brief = dict(getattr(ui_blueprint, "design_brief", {}) or {})
    brief["visual_identity_attempt"] = attempt
    setattr(ui_blueprint, "design_brief", brief)
    return ui_blueprint


def _seed_payload(task: Any, blueprint: Any, product_experience_spec: Any, attempt: int) -> dict[str, Any]:
    modules = list(getattr(blueprint, "modules", []) or [])
    return {
        "creative_seed": str(getattr(task, "seed", "") or ""),
        "software_name": str(getattr(task, "software_name", "") or ""),
        "software_category": str(getattr(task, "software_category", "") or ""),
        "product_type": str(getattr(task, "product_type", "") or ""),
        "experience_shape": str(getattr(product_experience_spec, "experience_shape", "") or ""),
        "feature_hint": str(getattr(task, "input_feature_hint", getattr(task, "feature_hint", "")) or ""),
        "model_provider": str(getattr(task, "model_provider", "") or ""),
        "model_name": str(getattr(task, "model_name", "") or ""),
        "randomness": str(getattr(task, "randomness", "") or ""),
        "industry": str(getattr(blueprint, "industry", "") or ""),
        "scenario": str(getattr(blueprint, "scenario", "") or ""),
        "technical_architecture": _stable_architecture_hint(getattr(blueprint, "technical_architecture", {}) or {}),
        "module_titles": [str(getattr(module, "title", "") or "") for module in modules[:10]],
        "business_objects": [str(item) for item in (getattr(blueprint, "business_objects", []) or [])[:12]],
        "report_metrics": [str(item) for item in (getattr(blueprint, "report_metrics", []) or [])[:12]],
        "attempt": int(attempt),
    }


def _module_cycle(shape: str, layout_variant: str, digest: str) -> tuple[str, ...]:
    base = list(
        _SHAPE_CYCLES.get(shape)
        or _SHAPE_CYCLES.get(layout_variant)
        or {
            "map": _SHAPE_CYCLES["gis_map"],
            "pipeline": _SHAPE_CYCLES["cloud_ops_console"],
            "risk": ("admin_risk", "admin_case", "admin_board", "admin_table", "admin_form", "admin_matrix"),
            "workflow": ("admin_board", "admin_form", "admin_case", "admin_table", "admin_risk", "admin_matrix"),
            "kanban": ("admin_board", "admin_case", "admin_table", "admin_form", "admin_risk", "admin_matrix"),
            "matrix": ("admin_matrix", "admin_table", "admin_case", "admin_form", "admin_board", "admin_risk"),
            "command": ("admin_risk", "admin_table", "admin_pipeline", "admin_board", "admin_form", "admin_case"),
        }.get(layout_variant)
        or _SHAPE_CYCLES["desktop_web"]
    )
    shuffled = _shuffle_by_digest(base, digest)
    return tuple(shuffled)


def _shuffle_by_digest(values: list[str], digest: str) -> list[str]:
    result = list(values)
    entropy = digest
    cursor = 0
    for index in range(len(result) - 1, 0, -1):
        if cursor + 2 > len(entropy):
            entropy += sha256(entropy.encode("utf-8")).hexdigest()
        swap_index = int(entropy[cursor : cursor + 2], 16) % (index + 1)
        cursor += 2
        result[index], result[swap_index] = result[swap_index], result[index]
    return result


def _pick(values: Any, digest: str, slot: int) -> str:
    values_tuple = tuple(str(value) for value in values if str(value).strip())
    if not values_tuple:
        return ""
    start = (slot * 2) % max(len(digest) - 2, 1)
    number = int(digest[start : start + 2], 16)
    return values_tuple[number % len(values_tuple)]


def _dashboard_composition_label(value: str) -> str:
    labels = {
        "metrics_then_queue": "指标总览与待办队列",
        "map_first": "空间态势与区域分布",
        "pipeline_lanes": "链路阶段与任务调度",
        "case_timeline": "业务档案与处理时间线",
        "matrix_heatmap": "指标矩阵与趋势研判",
        "command_wall": "指挥态势与实时监控",
        "kanban_overview": "流程看板与状态泳道",
        "chart_focus": "专题图表与关键指标",
    }
    return labels.get(value, "业务指标总览")


def _module_cycle_label(values: tuple[str, ...]) -> str:
    labels = {
        "admin_map": "地图态势",
        "admin_board": "任务看板",
        "admin_table": "业务台账",
        "admin_risk": "风险研判",
        "admin_form": "配置表单",
        "admin_matrix": "指标矩阵",
        "admin_pipeline": "链路调度",
        "admin_case": "档案详情",
    }
    selected = [labels.get(value, value) for value in values[:3]]
    return " / ".join(selected) or "业务台账"


def _stable_architecture_hint(value: Any) -> Any:
    if not isinstance(value, dict):
        return {}
    return {
        "key": str(value.get("key") or ""),
        "name": str(value.get("name") or ""),
        "source_strategy": str(value.get("source_strategy") or ""),
        "languages": [str(item) for item in value.get("languages", [])[:4]] if isinstance(value.get("languages"), list) else [],
        "stack": [str(item) for item in value.get("stack", [])[:6]] if isinstance(value.get("stack"), list) else [],
    }
