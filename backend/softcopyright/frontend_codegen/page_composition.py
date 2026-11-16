from __future__ import annotations

from hashlib import sha256
import json
from typing import Any


PAGE_COMPOSITION_VERSION = "page-composition-v2"

DESKTOP_VARIANTS = (
    "balanced-grid",
    "asymmetric-left",
    "asymmetric-right",
    "analysis-matrix",
    "workflow-focus",
    "detail-rail",
)
MOBILE_VARIANTS = (
    "mobile-summary",
    "mobile-task-flow",
    "mobile-action-focus",
    "mobile-feed",
)

_FULL_WIDTH_COMPONENTS = {"filter_bar", "operation_result"}
_WIDE_COMPONENTS = {"data_table", "kanban", "chart", "map_panel", "relationship_graph"}
_SUMMARY_COMPONENTS = {"metric_group", "chart", "detail"}
_TASK_COMPONENTS = {"workflow", "timeline", "mobile_list", "data_table", "kanban"}
_ACTION_COMPONENTS = {"form", "operation_result", "detail"}


def build_page_composition_contract(
    spec: dict[str, Any],
    *,
    renderer: str,
    creative_key: str,
    screen: dict[str, Any] | None = None,
) -> dict[str, Any]:
    screen = screen if isinstance(screen, dict) else {}
    terminal = "mobile" if str(renderer or "") in {"mobile_app", "game"} else "desktop"
    page_kind = str(spec.get("page_kind") or screen.get("page_kind") or "module")
    layout = str(spec.get("layout") or "table_workspace")
    regions = [item for item in spec.get("regions") or [] if isinstance(item, dict)]
    components = [str(item.get("component") or "detail") for item in regions]
    interaction = spec.get("interaction_contract") if isinstance(spec.get("interaction_contract"), dict) else {}
    interaction_mode = str(interaction.get("mode") or screen.get("interaction_mode") or "browse")
    interaction_surface = str(screen.get("interaction_surface") or interaction.get("result_evidence") or "")
    family = _composition_family(layout, components, page_kind)

    if page_kind == "login":
        variant = "mobile-action-focus" if terminal == "mobile" else "detail-rail"
    else:
        variants = _variant_candidates(terminal, layout, components, interaction_mode)
        seed = "|".join(
            [
                terminal,
                page_kind,
                layout,
                ",".join(components),
                creative_key,
                interaction_mode,
                interaction_surface,
            ]
        )
        variant = variants[int(sha256(seed.encode("utf-8")).hexdigest()[:8], 16) % len(variants)]

    slots = _region_slots(regions, variant=variant, terminal=terminal)
    signature_payload = {
        "version": PAGE_COMPOSITION_VERSION,
        "terminal": terminal,
        "family": family,
        "variant": variant,
        "layout": layout,
        "slots": [f"{item['component']}:{item['slot']}:{item['order']}" for item in slots],
    }
    signature = sha256(
        json.dumps(signature_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:20]
    return {
        "version": PAGE_COMPOSITION_VERSION,
        "terminal": terminal,
        "family": family,
        "variant": variant,
        "workspace_mode": "single-column" if terminal == "mobile" else "twelve-column",
        "region_slots": slots,
        "signature": signature,
        "density": str((spec.get("theme") or {}).get("density") or "comfortable"),
    }


def _variant_candidates(terminal: str, layout: str, components: list[str], interaction_mode: str) -> tuple[str, ...]:
    if terminal == "mobile":
        if interaction_mode in {"create", "edit", "import", "export", "review", "approve", "workflow"}:
            return ("mobile-action-focus", "mobile-task-flow", "mobile-feed")
        if any(component in _SUMMARY_COMPONENTS for component in components):
            return MOBILE_VARIANTS
        return ("mobile-task-flow", "mobile-feed", "mobile-summary")
    if layout in {"chart_analysis", "dashboard_grid"}:
        return ("analysis-matrix", "balanced-grid", "asymmetric-left", "asymmetric-right")
    if layout in {"workflow_board", "result_confirmation"}:
        return ("workflow-focus", "detail-rail", "asymmetric-left", "asymmetric-right")
    if layout in {"form_detail", "timeline_detail", "map_workspace", "relationship_workspace"}:
        return ("detail-rail", "asymmetric-left", "asymmetric-right", "balanced-grid")
    if layout == "kanban_workspace":
        return ("balanced-grid", "analysis-matrix", "asymmetric-left", "asymmetric-right")
    return DESKTOP_VARIANTS


def _composition_family(layout: str, components: list[str], page_kind: str) -> str:
    if page_kind == "login":
        return "authentication"
    families = {
        "dashboard_grid": "overview",
        "table_workspace": "records",
        "form_detail": "entry-detail",
        "workflow_board": "workflow",
        "timeline_detail": "timeline",
        "kanban_workspace": "kanban",
        "chart_analysis": "analysis",
        "map_workspace": "spatial",
        "relationship_workspace": "relationship",
        "mobile_feed": "mobile-feed",
        "result_confirmation": "result",
    }
    if layout in families:
        return families[layout]
    for component, family in (
        ("map_panel", "spatial"),
        ("relationship_graph", "relationship"),
        ("workflow", "workflow"),
        ("chart", "analysis"),
        ("data_table", "records"),
    ):
        if component in components:
            return family
    return "workspace"


def _region_slots(regions: list[dict[str, Any]], *, variant: str, terminal: str) -> list[dict[str, Any]]:
    slots: list[dict[str, Any]] = []
    components = {str(region.get("component") or "detail") for region in regions}
    # Charts need a stable, meaningful height and tables need the full reading
    # width. Placing both in the same twelve-column grid can make CSS Grid put
    # them side by side in a row whose height is driven by the shorter region;
    # the chart's absolutely positioned plot then paints over the next row.
    # Give both regions their own full-width rows when they coexist.
    chart_and_table = terminal == "desktop" and {"chart", "data_table"}.issubset(components)
    for index, region in enumerate(regions):
        component = str(region.get("component") or "detail")
        region_id = str(region.get("id") or f"region_{index + 1}")
        if terminal == "mobile":
            order = _mobile_order(component, index, variant)
            slot = "mobile-priority" if order < 20 else "mobile-flow"
        elif chart_and_table and component in {"chart", "data_table"}:
            slot, order = "full-band", index * 10
        else:
            slot, order = _desktop_slot(component, index, variant)
        slots.append(
            {
                "region_id": region_id,
                "component": component,
                "slot": slot,
                "order": order,
            }
        )
    return slots


def _desktop_slot(component: str, index: int, variant: str) -> tuple[str, int]:
    if component in _FULL_WIDTH_COMPONENTS:
        return "full-band", index * 10
    if variant == "balanced-grid":
        return ("primary-eight" if component in _WIDE_COMPONENTS else "secondary-four", index * 10)
    if variant == "asymmetric-left":
        return ("stage-left" if component in _WIDE_COMPONENTS or index == 0 else "rail-right", index * 10)
    if variant == "asymmetric-right":
        return ("stage-right" if component in _WIDE_COMPONENTS or index == 0 else "rail-left", index * 10)
    if variant == "analysis-matrix":
        return ("matrix-wide" if component in {"data_table", "map_panel", "relationship_graph"} else "matrix-half", index * 10)
    if variant == "workflow-focus":
        return ("workflow-stage" if component in _TASK_COMPONENTS else "workflow-support", index * 10)
    return ("detail-stage" if component in _WIDE_COMPONENTS or component == "form" else "detail-rail", index * 10)


def _mobile_order(component: str, index: int, variant: str) -> int:
    if variant == "mobile-summary":
        priority = 0 if component in _SUMMARY_COMPONENTS else 1
    elif variant == "mobile-task-flow":
        priority = 0 if component in _TASK_COMPONENTS else 1
    elif variant == "mobile-action-focus":
        priority = 0 if component in _ACTION_COMPONENTS else 1
    else:
        priority = 1
    return (priority * 100) + (index * 10)
