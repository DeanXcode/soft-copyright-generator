from types import SimpleNamespace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.softcopyright.ai_frontend_codegen import _stable_module_body, _stable_operation_body
from backend.softcopyright.blueprint import FeatureModule, generate_blueprint
from backend.softcopyright.models import GenerationTask
from backend.softcopyright.screenshots import (
    _detail_dialog,
    _inject_prototype_page_navigation,
    _module_operation_body,
    _mobile_login_body,
    _mobile_profile_body,
    _mini_chart,
    _operation_result_bar,
    _operation_sample_value,
    _query_dialog,
    _sanitize_profile_process_vocabulary,
    _statistics_dialog,
)


def _attendance_module() -> FeatureModule:
    return FeatureModule(
        key="attendance",
        title="员工考勤",
        description="员工上下班打卡与考勤状态查询",
        entities=["AttendanceRecord"],
        operations=["上班打卡", "下班打卡", "查看考勤"],
        data_fields=["员工编号", "员工姓名", "打卡时间", "打卡位置", "考勤状态"],
        operation_specs=[
            {
                "label": "上班打卡",
                "role": "员工",
                "pre_state": "未打卡",
                "post_state": "已打卡",
                "result_evidence": "打卡时间和位置",
            }
        ],
    )


class ScreenshotSemanticTests(unittest.TestCase):
    def test_static_prototype_navigation_maps_known_pages_and_ignores_unknown_targets(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pages = [
                {"key": "dashboard", "file": "dashboard.html"},
                {"key": "task_detail", "file": "task_detail.html"},
            ]
            for page in pages:
                (root / page["file"]).write_text(
                    '<!doctype html><body><span data-navigation-page-key="task_detail">任务详情</span>'
                    '<span data-navigation-back-target="dashboard">返回</span>'
                    '<span data-navigation-page-key="unknown">未知</span></body>',
                    encoding="utf-8",
                )

            injected = _inject_prototype_page_navigation(pages, prototype_dir=root)
            _inject_prototype_page_navigation(pages, prototype_dir=root)
            html = (root / "dashboard.html").read_text(encoding="utf-8")

            self.assertEqual(injected, 2)
            self.assertEqual(html.count('data-prototype-navigation="v1"'), 1)
            self.assertIn('"task_detail": "task_detail.html"', html)
            self.assertIn('"dashboard": "dashboard.html"', html)
            self.assertIn("if (!target) return", html)
            self.assertIn("window.location.assign(destination.href)", html)

    def test_mini_chart_keeps_date_range_in_footer_without_overlapping_bar_labels(self):
        html = _mini_chart({"chart_values": [88, 82, 64, 76, 92, 70], "metrics": [("设备在线率", "98%") ]})

        self.assertIn("设备在线率 · 06-24 至 06-29", html)
        self.assertNotIn("data-label=", html)
        self.assertEqual(html.count("aria-label="), 6)

    def test_local_template_dialogs_use_operation_contract_instead_of_review_ledger_terms(self):
        module = _attendance_module()
        html = "\n".join(
            [
                _query_dialog(module, "考勤查询", module.data_fields),
                _statistics_dialog(module, "考勤统计"),
                _detail_dialog(module, "查看", "考勤详情", module.data_fields),
                _operation_result_bar(module, "上班打卡"),
            ]
        )

        self.assertIn("未打卡", html)
        self.assertIn("已打卡", html)
        self.assertIn("打卡时间和位置", html)
        self.assertIn("员工考勤编号", html)
        for term in ("台账", "待复核", "操作日志", "系统管理员", "已归档"):
            self.assertNotIn(term, html)

    def test_explicit_review_operation_keeps_review_language(self):
        module = FeatureModule(
            key="quality_review",
            title="构件质量",
            description="构件质量复核",
            entities=["QualityTask"],
            operations=["确认复核"],
            data_fields=["任务编号", "构件名称", "复核结论"],
            operation_specs=[
                {
                    "label": "确认复核",
                    "role": "质量工程师",
                    "pre_state": "待复核",
                    "post_state": "已复核",
                    "result_evidence": "复核结论和操作日志",
                }
            ],
        )

        html = _operation_result_bar(module, "确认复核")

        self.assertIn("确认复核结果", html)
        self.assertIn("已复核", html)
        self.assertIn("复核结论和操作日志", html)

    def test_stable_fallback_is_derived_from_current_module(self):
        module = _attendance_module()
        blueprint = SimpleNamespace(modules=[module], report_metrics=["打卡人数", "正常出勤率"])
        task = SimpleNamespace(software_name="员工考勤助手")
        screen = SimpleNamespace(interaction_action="上班打卡", interaction_mode="workflow")

        html = _stable_module_body(task, blueprint, module, "员工考勤", {}) + _stable_operation_body(
            task,
            blueprint,
            module,
            "上班打卡",
            {},
            screenshot=screen,
        )

        self.assertIn("上班打卡", html)
        self.assertIn("已打卡", html)
        self.assertIn("打卡时间和位置", html)
        for term in ("主井", "矿区", "皮带运输", "KS-2026", "待复核", "操作日志"):
            self.assertNotIn(term, html)

    def test_product_profile_removes_unlicensed_review_workflow_terms(self):
        module = _attendance_module()
        blueprint = SimpleNamespace(
            modules=[module],
            workflows=[],
            target_users=["员工"],
            business_objects=["考勤记录"],
            industry="企业办公",
            scenario="员工考勤",
            summary="记录上下班打卡信息",
        )
        profile = {
            "metrics": [("待复核", "18")],
            "states": ["待审核", "已归档"],
            "todo_title": "考勤复核台账",
            "user_label": "当前用户：系统管理员",
            "focus_cards": [("操作日志", "8", "待处理")],
        }

        _sanitize_profile_process_vocabulary(blueprint, profile)
        text = str(profile)

        self.assertIn("未打卡", text)
        self.assertIn("员工", text)
        for term in ("待复核", "待审核", "已归档", "台账", "操作日志", "系统管理员"):
            self.assertNotIn(term, text)

    def test_attendance_sample_values_do_not_reuse_transport_or_generic_planning_copy(self):
        statistics = FeatureModule(
            key="attendance_statistics",
            title="出勤统计",
            description="统计员工出勤情况",
            entities=["AttendanceReport"],
            data_fields=["统计周期", "统计口径", "对比范围"],
        )
        schedule = FeatureModule(
            key="shift_schedule",
            title="班次排班管理",
            description="安排员工班次",
            entities=["ShiftSchedule"],
            data_fields=["员工编号", "班次名称", "排班日期"],
        )

        self.assertEqual(_operation_sample_value(statistics, "统计周期", 0), "2026年6月")
        self.assertEqual(_operation_sample_value(statistics, "统计口径", 1), "按员工与班次统计")
        self.assertEqual(_operation_sample_value(statistics, "对比范围", 2), "本月与上月")
        self.assertEqual(_operation_sample_value(schedule, "员工编号", 0), "EMP-1001")
        self.assertIn("班", _operation_sample_value(schedule, "班次名称", 1))
        self.assertNotIn("区域衔接", _operation_sample_value(statistics, "统计周期", 0))

    def test_attendance_login_and_profile_do_not_show_consumer_template_navigation(self):
        task = GenerationTask(
            software_name="员工考勤助手",
            product_type="APP",
            feature_hint="员工考勤打卡",
            model_provider="local-template",
            seed="attendance-ui",
        )
        blueprint = generate_blueprint(task)
        login_screen = SimpleNamespace(title="员工考勤助手登录界面", caption="员工使用手机号和验证码登录")
        profile_screen = SimpleNamespace(
            title="员工考勤助手个人中心界面",
            components=["用户资料", "收藏记录", "使用历史", "会员权益", "应用设置"],
        )

        login_html = _mobile_login_body(task, blueprint, login_screen)
        profile_html = _mobile_profile_body(task, blueprint, profile_screen)

        self.assertNotIn('class="mobile-nav"', login_html)
        self.assertNotIn('class="mobile-header"', login_html)
        self.assertIn("员工资料", profile_html)
        self.assertIn("考勤设置", profile_html)
        self.assertNotIn("会员权益", profile_html)
        self.assertNotIn("收藏记录", profile_html)
        self.assertIn('data-navigation-contract="navigation-contract-v1"', profile_html)
        self.assertIn("打卡", profile_html)
        self.assertIn("申请", profile_html)

    def test_local_operation_page_has_secondary_navigation_and_back_target(self):
        task = GenerationTask(
            software_name="员工考勤助手",
            product_type="APP",
            feature_hint="员工考勤打卡",
            model_provider="local-template",
            seed="attendance-navigation",
        )
        blueprint = generate_blueprint(task)
        module = next(module for module in blueprint.modules if "考勤" in module.title or "打卡" in module.title)

        html = _module_operation_body(
            task,
            blueprint,
            module,
            str(module.operation_specs[0].get("label") or module.operations[0]),
            page_key=f"{module.key}_operation",
            interaction_action_key=str(module.operation_specs[0].get("action_key") or "operation_1"),
        )

        self.assertIn('data-navigation-level="action"', html)
        self.assertIn(f'data-navigation-back-target="{module.key}"', html)
        self.assertGreaterEqual(html.count("data-navigation-secondary-item="), 2)


if __name__ == "__main__":
    unittest.main()
