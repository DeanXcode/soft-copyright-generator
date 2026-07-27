import json
from types import SimpleNamespace
import unittest

from backend.softcopyright.frontend_codegen.legacy_fallback import requires_legacy_fallback
from backend.softcopyright.frontend_codegen.page_spec import (
    COMPONENT_LIBRARY_VERSION,
    FRONTEND_ENGINE_VERSION,
    PAGE_SPEC_SCHEMA_VERSION,
    PageSpecValidationError,
    normalize_page_spec,
    page_spec_cache_key,
)
from backend.softcopyright.frontend_codegen.page_spec_renderer import render_page_spec
from backend.softcopyright.frontend_codegen.page_spec_request import request_page_spec


def _valid_spec(page_key="quality_task", page_kind="operation"):
    return {
        "schema_version": PAGE_SPEC_SCHEMA_VERSION,
        "page_key": page_key,
        "page_kind": page_kind,
        "layout": "table_workspace",
        "theme": {"density": "comfortable", "accent_variant": "primary"},
        "regions": [
            {"id": "filters", "component": "filter_bar", "title": "质量任务筛选", "fields": [{"label": "任务编号"}]},
            {"id": "metrics", "component": "metric_group", "title": "质量指标", "metrics": [{"label": "合格率", "value": "98.6%"}]},
            {
                "id": "table",
                "component": "data_table",
                "title": "质量任务清单",
                "columns": ["任务编号", "构件名称", "责任岗位", "任务状态"],
                "items": [{"label": "QT-001", "title": "预制墙板", "owner": "质量工程师", "status": "待复核"}],
            },
            {"id": "workflow", "component": "workflow", "title": "复核流程", "steps": ["接收任务", "核验数据", "提交结论"]},
            {"id": "result", "component": "operation_result", "title": "复核结果"},
        ],
        "actions": [{"action_key": "confirm_quality_task", "label": "确认复核", "variant": "primary", "requires_confirmation": True}],
        "interaction_contract": {
            "mode": "workflow",
            "action_key": "confirm_quality_task",
            "role": "质量工程师",
            "trigger": "检测数据和现场记录核验完成",
            "input_fields": ["任务编号", "复核结论"],
            "pre_state": "待复核",
            "post_state": "已复核",
            "result_evidence": "复核结论和审计日志",
            "requires_confirmation": True,
        },
    }


class _SpecProvider:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def chat(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return self.payload if isinstance(self.payload, str) else json.dumps(self.payload, ensure_ascii=False)


class PageSpecTests(unittest.TestCase):
    def test_backend_operation_spec_normalizes_and_renders_controlled_components(self):
        spec = normalize_page_spec(
            _valid_spec(),
            expected_page_key="quality_task",
            expected_page_kind="operation",
            expected_interaction={"action_key": "confirm_quality_task"},
        )
        rendered = render_page_spec(
            spec,
            css_scope="screen-quality-task",
            creative_key="quality-task-seed",
            renderer="admin",
            module={"title": "构件质量复核", "data_fields": ["任务编号", "构件名称", "复核结论"]},
            screen={"title": "构件质量任务复核", "requires_confirmation": True, "interaction_action": "确认复核"},
            visual_identity={"accent": "#0f766e"},
            color_contract={"dominant_colors": ["#173f48", "#168779", "#f3f7f7"]},
        )

        self.assertIn('data-page-spec="page-spec-v1"', rendered["jsx"])
        for class_name in ("filter-bar", "metric-grid", "table-frame", "workflow-board", "operation-result"):
            self.assertIn(class_name, rendered["jsx"])
        self.assertIn('data-shared-confirm-source="true"', rendered["jsx"])
        self.assertIn(".screen-quality-task", rendered["css"])
        self.assertNotIn("http://", rendered["css"])
        self.assertNotIn("style=", rendered["jsx"])

    def test_mobile_map_chart_relationship_and_list_components_render_without_legacy_css(self):
        spec = _valid_spec(page_key="mobile_map", page_kind="module")
        spec["layout"] = "mobile_feed"
        spec["actions"] = []
        spec["interaction_contract"] = {"mode": "browse"}
        spec["regions"] = [
            {"id": "map", "component": "map_panel", "title": "服务点位", "points": ["东区服务点", "西区服务点"]},
            {"id": "chart", "component": "chart", "title": "服务趋势", "series": [{"label": "周一", "value": "72"}]},
            {"id": "graph", "component": "relationship_graph", "title": "对象关系", "items": ["服务订单", "服务人员"]},
            {"id": "list", "component": "mobile_list", "title": "移动任务", "items": [{"label": "上门服务", "status": "进行中"}]},
        ]
        normalized = normalize_page_spec(
            spec,
            expected_page_key="mobile_map",
            expected_page_kind="module",
            expected_interaction={},
        )
        rendered = render_page_spec(
            normalized,
            css_scope="screen-mobile-map",
            creative_key="mobile-map-seed",
            renderer="mobile_app",
            module={},
            screen={"title": "移动服务地图"},
            visual_identity={},
            color_contract={},
        )

        for class_name in ("map-workspace", "chart-panel", "relationship-graph", "mobile-list"):
            self.assertIn(class_name, rendered["jsx"])
        self.assertIn("page-spec-mobile", rendered["jsx"])

    def test_unknown_component_and_missing_interaction_contract_are_rejected(self):
        spec = _valid_spec(page_kind="module")
        spec["regions"] = [{"id": "custom", "component": "freeform_canvas", "title": "未知画布"}]
        spec.pop("interaction_contract")

        with self.assertRaises(PageSpecValidationError) as raised:
            normalize_page_spec(
                spec,
                expected_page_key="quality_task",
                expected_page_kind="module",
                expected_interaction={},
            )

        self.assertIn("未知组件", str(raised.exception))
        self.assertIn("interaction_contract", str(raised.exception))

    def test_page_spec_request_uses_1600_token_limit_and_rejects_oversized_output(self):
        provider = _SpecProvider(_valid_spec())
        result = request_page_spec(
            provider=provider,
            software_context={"renderer": "admin"},
            screen={"key": "quality_task", "page_kind": "operation", "interaction_action_key": "confirm_quality_task"},
            module={"title": "质量任务"},
            visual_identity={},
            color_contract={},
        )

        self.assertEqual(result["schema_version"], PAGE_SPEC_SCHEMA_VERSION)
        self.assertEqual(provider.calls[0][1]["max_tokens"], 1600)
        self.assertIn("不要生成 JSX、CSS、HTML", provider.calls[0][0][-1]["content"])

        oversized = _SpecProvider("{" + '"padding":"' + ("x" * 6100) + '"}')
        with self.assertRaises(PageSpecValidationError):
            request_page_spec(
                provider=oversized,
                software_context={},
                screen={"key": "quality_task", "page_kind": "module"},
                module={},
                visual_identity={},
                color_contract={},
            )

    def test_cache_key_includes_schema_component_library_and_engine_versions(self):
        key = page_spec_cache_key("creative-key")

        self.assertEqual(len(key), 64)
        self.assertEqual(PAGE_SPEC_SCHEMA_VERSION, "page-spec-v1")
        self.assertEqual(COMPONENT_LIBRARY_VERSION, "page-components-v1")
        self.assertEqual(FRONTEND_ENGINE_VERSION, "pagespec-hybrid-v1")

    def test_game_and_three_dimensional_pages_use_legacy_fallback_but_maps_do_not(self):
        self.assertTrue(requires_legacy_fallback("game", SimpleNamespace(title="关卡大厅", caption="", interaction_action="")))
        self.assertTrue(requires_legacy_fallback("admin", SimpleNamespace(title="三维装配仿真", caption="", interaction_action="")))
        self.assertFalse(requires_legacy_fallback("admin", SimpleNamespace(title="区域地图监控", caption="地图点位", interaction_action="")))


if __name__ == "__main__":
    unittest.main()
