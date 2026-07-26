from types import SimpleNamespace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.softcopyright.operation_coverage import (
    configured_operation_screen_count,
    module_operation_category,
    module_operation_coverage,
    operation_action_label,
    operation_caption,
    operation_page_title,
    OperationCoverageSpec,
    operation_spec,
)
from backend.softcopyright.ai_frontend_codegen import _visual_reference_cache_key
from backend.softcopyright.screenshots import _build_page_specs
from backend.softcopyright.ui_blueprint import UiBlueprint, UiScreenBlueprint


class OperationCoverageTests(unittest.TestCase):
    def test_legacy_domain_actions_do_not_repeat_module_title(self):
        self.assertEqual(operation_action_label("施工工序管理评定"), "评定")
        self.assertEqual(operation_action_label("质量计划管理验收"), "验收")
        self.assertEqual(operation_page_title("施工工序管理", "施工工序管理评定"), "施工工序管理评定界面")
        caption = operation_caption(
            "门店核销管理",
            OperationCoverageSpec(
                action="核验门店核销",
                category="workflow",
                surface="workflow_result",
                mode="workflow",
                role="平台运营",
                trigger="需要核验门店核销时",
            ),
        )
        self.assertIn("需要核验门店核销时发起", caption)
        self.assertNotIn("时时发起", caption)

    def test_style_reference_cache_is_independent_of_manual_page_count(self):
        task = SimpleNamespace(seed="seed-1", software_name="\u751f\u4ea7\u5e73\u53f0", product_type="\u4eba\u5de5\u667a\u80fd\u8f6f\u4ef6")
        ui_blueprint = SimpleNamespace(
            renderer="admin",
            design_brief={
                "visual_identity_spec": {"identity_signature": "factory-green"},
                "product_experience_spec": {"experience_shape": "industrial-console"},
            },
        )

        first = _visual_reference_cache_key(task, ui_blueprint, 27, "1280x720")
        expanded = _visual_reference_cache_key(task, ui_blueprint, 35, "1280x720")

        self.assertEqual(first, expanded)

    def test_admin_module_selects_three_complementary_operation_pages(self):
        module = SimpleNamespace(
            title="\u751f\u4ea7\u8d28\u91cf\u5206\u6790",
            description="\u8d28\u91cf\u770b\u677f\u4e0e\u8d8b\u52bf\u5206\u6790",
            pages=[],
            operations=[
                "\u67e5\u8be2",
                "\u6821\u9a8c",
                "\u5206\u6790",
                "\u786e\u8ba4",
                "\u5f52\u6863",
                "\u7edf\u8ba1",
            ],
        )

        specs = module_operation_coverage(module, renderer="admin", module_index=0)

        self.assertEqual(len(specs), 3)
        self.assertEqual(specs[0].category, "lookup")
        self.assertGreaterEqual(len({item.category for item in specs}), 2)
        self.assertNotIn("\u5220\u9664", {item.action for item in specs})

    def test_read_only_module_uses_detail_or_analysis_instead_of_fake_crud(self):
        module = SimpleNamespace(
            title="\u7cfb\u7edf\u76d1\u63a7\u770b\u677f",
            description="\u5b9e\u65f6\u76d1\u63a7\u9884\u8b66\u548c\u8d8b\u52bf",
            pages=[],
            operations=[],
        )

        specs = module_operation_coverage(module, renderer="admin", module_index=1)

        self.assertEqual(len(specs), configured_operation_screen_count("admin"))
        self.assertIn("\u67e5\u8be2", {item.action for item in specs})
        self.assertIn("\u67e5\u770b\u8be6\u60c5", {item.action for item in specs})
        self.assertFalse({"\u65b0\u589e", "\u7f16\u8f91", "\u5220\u9664"} & {item.action for item in specs})

    def test_structured_operations_drive_page_contract(self):
        module = SimpleNamespace(
            title="生产工单管控",
            description="下达生产工单并跟踪现场执行状态。",
            pages=[],
            operations=["登记", "确认", "统计"],
            operation_specs=[
                {
                    "action_key": "filter_work_orders",
                    "label": "筛选待下达工单",
                    "category": "lookup",
                    "role": "车间主管",
                    "trigger": "需要定位待执行工单",
                    "input_fields": ["工单编号", "目标产线"],
                    "pre_state": "全部工单",
                    "post_state": "显示匹配工单",
                    "result_evidence": "筛选条件、结果数量和工单列表",
                },
                {
                    "action_key": "release_work_order",
                    "label": "下达生产工单",
                    "category": "workflow",
                    "role": "车间主管",
                    "trigger": "物料与工艺路线校验通过",
                    "input_fields": ["工单编号", "计划数量"],
                    "pre_state": "待下达",
                    "post_state": "已下达",
                    "result_evidence": "状态轨迹和下达日志",
                },
                {
                    "action_key": "pause_work_order",
                    "label": "暂停异常工单",
                    "category": "workflow",
                    "role": "车间主管",
                    "trigger": "设备停机或物料短缺",
                    "input_fields": ["暂停原因", "预计恢复时间"],
                    "pre_state": "生产中",
                    "post_state": "已暂停",
                    "result_evidence": "暂停原因和影响范围",
                },
            ],
        )

        specs = module_operation_coverage(module, renderer="admin", module_index=0)

        self.assertEqual(specs[0].action, "筛选待下达工单")
        self.assertEqual(specs[0].source, "blueprint-structured")
        self.assertEqual(specs[0].role, "车间主管")
        self.assertIn("工单编号", specs[0].input_fields)
        self.assertTrue(any(spec.action == "下达生产工单" for spec in specs))

    def test_structured_action_key_preserves_lookup_category_for_non_keyword_label(self):
        module = SimpleNamespace(
            operation_specs=[
                {
                    "action_key": "compare_forecast_scenarios",
                    "label": "对比产能预测方案",
                    "category": "lookup",
                },
                {
                    "action_key": "generate_capacity_forecast",
                    "label": "生成可用产能预测",
                    "category": "workflow",
                },
            ]
        )

        self.assertEqual(
            module_operation_category(module, "对比产能预测方案", "compare_forecast_scenarios"),
            "lookup",
        )
        self.assertEqual(
            module_operation_category(module, "生成可用产能预测", "generate_capacity_forecast"),
            "workflow",
        )
        self.assertEqual(module_operation_category(module, "查看预测详情"), "lookup")

    def test_only_destructive_operations_require_confirmation(self):
        delete_spec = operation_spec("\u5220\u9664")
        query_spec = operation_spec("\u67e5\u8be2")
        play_spec = operation_spec("\u64ad\u653e")

        self.assertTrue(delete_spec.requires_confirmation)
        self.assertEqual(delete_spec.mode, "confirm")
        self.assertFalse(query_spec.requires_confirmation)
        self.assertFalse(play_spec.requires_confirmation)
        self.assertEqual(play_spec.mode, "instant")

    def test_mobile_coverage_does_not_copy_unrelated_registration_action(self):
        module = SimpleNamespace(
            title="\u97f3\u4e50\u641c\u7d22",
            description="\u641c\u7d22\u6b4c\u66f2\u5e76\u67e5\u770b\u6b4c\u8bcd",
            pages=[],
            operations=["\u97f3\u4e50\u641c\u7d22\u767b\u8bb0"],
        )

        specs = module_operation_coverage(module, renderer="mobile_app", module_index=0)

        self.assertEqual(len(specs), configured_operation_screen_count("mobile_app"))
        self.assertNotIn("\u767b\u8bb0", {item.action for item in specs})
        self.assertTrue({"\u641c\u7d22\u4e0e\u7b5b\u9009", "\u67e5\u770b\u6b4c\u8bcd"} & {item.action for item in specs})

    def test_mobile_structured_operations_lead_and_reach_page_metadata(self):
        module = SimpleNamespace(
            key="mobile_inspection",
            title="移动巡检",
            description="巡检员在现场上报设备异常并复核处置结果。",
            pages=["巡检任务", "异常详情"],
            operations=["上报设备异常", "复核处置结果"],
            operation_specs=[
                {
                    "action_key": "report_device_fault",
                    "label": "上报设备异常",
                    "category": "workflow",
                    "role": "巡检员",
                    "trigger": "现场发现设备异常",
                    "input_fields": ["设备编号", "异常现象"],
                    "pre_state": "待巡检",
                    "post_state": "异常待处置",
                    "result_evidence": "异常单号和上报时间",
                },
                {
                    "action_key": "review_fault_resolution",
                    "label": "复核处置结果",
                    "category": "result",
                    "role": "巡检员",
                    "trigger": "维修人员提交处置结果",
                    "input_fields": ["复核结论"],
                    "pre_state": "待复核",
                    "post_state": "已闭环",
                    "result_evidence": "复核结论和状态轨迹",
                },
            ],
        )

        specs = module_operation_coverage(module, renderer="mobile_app", module_index=1)

        self.assertEqual([item.action for item in specs[:2]], ["上报设备异常", "复核处置结果"])
        self.assertTrue(all(item.source == "blueprint-structured" for item in specs[:2]))

        ui_blueprint = UiBlueprint(
            renderer="mobile_app",
            visual_style="mobile",
            screens=[
                UiScreenBlueprint(
                    key="mobile_inspection",
                    title="移动巡检",
                    caption="查看现场巡检任务。",
                    view_type="module",
                    module_key="mobile_inspection",
                )
            ],
        )
        with TemporaryDirectory() as temp_dir:
            pages = _build_page_specs(
                SimpleNamespace(),
                SimpleNamespace(modules=[module]),
                Path(temp_dir),
                ui_blueprint,
            )

        operation_page = next(item for item in pages if item.page_kind == "operation")
        self.assertEqual(operation_page.interaction_action_key, "report_device_fault")
        self.assertEqual(operation_page.interaction_role, "巡检员")
        self.assertEqual(operation_page.interaction_pre_state, "待巡检")
        self.assertIn("设备编号", operation_page.interaction_input_fields)


if __name__ == "__main__":
    unittest.main()
