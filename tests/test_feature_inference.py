import unittest

from backend.softcopyright.blueprint import generate_blueprint
from backend.softcopyright.feature_inference import decisive_feature_contract, harmonize_feature_hint
from backend.softcopyright.industry_subtypes import select_industry_subtype
from backend.softcopyright.models import GenerationTask
from backend.softcopyright.ui_blueprint import build_ui_blueprint


class FeatureInferenceTests(unittest.TestCase):
    def test_agency_accounting_name_uses_decisive_enterprise_contract(self):
        hint, meta = harmonize_feature_hint("风灵月影代账", "APP", "")
        task = GenerationTask(
            software_name="风灵月影代账",
            product_type="APP",
            feature_hint=hint,
            model_provider="local-template",
            seed="agency-accounting-test",
        )

        self.assertEqual(meta["feature_hint_profile"], "agency_accounting")
        self.assertEqual(meta["feature_hint_domain"], "企业代理记账与财税服务")
        self.assertEqual(len(meta["feature_hint_blueprint_modules"]), 8)
        self.assertIn("税务申报", hint)
        self.assertIn("个人消费记账", meta["feature_hint_avoid_terms"])
        self.assertEqual(select_industry_subtype(task).key, "agency_accounting")
        for module in meta["feature_hint_blueprint_modules"]:
            self.assertGreaterEqual(len(module["operation_specs"]), 3)
            self.assertGreaterEqual(len(module["data_fields"]), 5)
            self.assertGreaterEqual(len(module["pages"]), 2)

    def test_agency_accounting_decisive_contract_replaces_stale_consumer_hint(self):
        contract = decisive_feature_contract(
            "风灵月影代账",
            "个人消费记账、移动 App、个人中心、离线查看",
        )

        self.assertIsNotNone(contract)
        hint, meta = contract
        self.assertEqual(meta["feature_hint_source"], "llm-replaced-mismatch")
        self.assertNotIn("个人消费记账", hint)
        self.assertIn("核算账套", hint)

    def test_figma_design_viewer_selects_design_subtype(self):
        task = GenerationTask(
            software_name="Figma浏览器",
            product_type="APP",
            feature_hint="设计文件、页面画板、图层组件、原型演示和设计评审",
            model_provider="local-template",
        )

        self.assertEqual(select_industry_subtype(task).key, "design_viewer")

    def test_download_app_selects_download_manager_subtype(self):
        task = GenerationTask(
            software_name="疾风下载",
            product_type="APP",
            feature_hint="下载链接解析、下载任务创建、下载队列调度、后台下载、进度跟踪和断点续传",
            model_provider="local-template",
        )

        self.assertEqual(select_industry_subtype(task).key, "download_manager")

    def test_name_derived_hint_does_not_replace_explicit_business_description(self):
        provided = "员工上下班打卡、考勤记录查询、请假申请和出勤统计"

        hint, meta = harmonize_feature_hint("员工考勤打卡助手", "APP", provided)

        self.assertEqual(meta["feature_hint_source"], "provided-merged")
        self.assertIn("上下班打卡", hint)
        self.assertIn("请假申请", hint)

    def test_attendance_app_uses_workforce_subtype_and_attendance_modules(self):
        provided = "员工上下班打卡、考勤记录查询、请假申请和出勤统计"
        hint, _meta = harmonize_feature_hint("员工考勤打卡助手", "APP", provided)
        task = GenerationTask(
            software_name="员工考勤打卡助手",
            product_type="APP",
            feature_hint=hint,
            model_provider="local-template",
            seed="attendance-test",
        )
        task.input_feature_hint = provided

        subtype = select_industry_subtype(task)
        blueprint = generate_blueprint(task)
        titles = " ".join(module.title for module in blueprint.modules)
        keys = {module.key for module in blueprint.modules}
        clock_module = next(module for module in blueprint.modules if "上下班打卡" in module.title)
        statistics_module = next(module for module in blueprint.modules if "出勤统计" in module.title)
        schedule_module = next(module for module in blueprint.modules if "班次排班" in module.title)
        ui_blueprint = build_ui_blueprint(task, blueprint)
        dashboard_screen = next(screen for screen in ui_blueprint.screens if screen.key == "dashboard")
        profile_screen = next(screen for screen in ui_blueprint.screens if screen.key == "statistics")
        clock_actions = [str(spec.get("label") or "") for spec in clock_module.operation_specs]

        self.assertEqual(subtype.key, "workforce_attendance")
        self.assertEqual(blueprint.industry_subtype_key, "workforce_attendance")
        self.assertIn("上下班打卡", titles)
        self.assertIn("班次排班", titles)
        self.assertNotIn("订单支付", titles)
        self.assertNotIn("会员权益", titles)
        self.assertIn("clock_in_out", keys)
        self.assertIn("shift_schedule", keys)
        self.assertIn("上班打卡", clock_actions)
        self.assertIn("下班打卡", clock_actions)
        self.assertNotIn("校核上下班打卡", clock_actions)
        self.assertIn("正常打卡率", statistics_module.data_fields)
        self.assertIn("员工范围", statistics_module.data_fields)
        self.assertIn("排班日期", schedule_module.data_fields)
        self.assertIn("班次名称", schedule_module.data_fields)
        self.assertNotIn("计划版本", schedule_module.data_fields)
        self.assertNotIn("资源范围", schedule_module.data_fields)
        self.assertIn("今日班次", dashboard_screen.caption)
        self.assertIn("打卡记录", profile_screen.components)
        self.assertIn("考勤设置", profile_screen.components)
        self.assertNotIn("会员权益", profile_screen.components)
        self.assertNotIn("收藏记录", profile_screen.components)


if __name__ == "__main__":
    unittest.main()
