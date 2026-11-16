import unittest

from backend.softcopyright.blueprint import FeatureModule, ProductBlueprint
from backend.softcopyright.models import GenerationTask
from backend.softcopyright.navigation_contract import (
    NAVIGATION_CONTRACT_VERSION,
    build_local_navigation_contract,
    build_navigation_contracts,
    navigation_contract_summary,
)


def _module(key: str, title: str, operations: list[tuple[str, str]]) -> FeatureModule:
    return FeatureModule(
        key=key,
        title=title,
        description=f"{title}业务处理",
        entities=[f"{key.title()}Record"],
        operations=[label for _, label in operations],
        data_fields=["业务编号", "处理状态"],
        operation_specs=[
            {
                "action_key": action_key,
                "label": label,
                "role": "业务人员",
                "pre_state": "待处理",
                "post_state": "已完成",
                "result_evidence": "业务状态和处理结果",
            }
            for action_key, label in operations
        ],
    )


def _blueprint(*, attendance: bool = False) -> ProductBlueprint:
    modules = [
        _module("attendance", "员工考勤", [("clock_in", "上班打卡"), ("query", "考勤查询")]),
        _module("request", "请假补卡申请", [("leave", "提交请假"), ("repair", "补卡申请")]),
    ]
    return ProductBlueprint(
        software_name="员工考勤助手" if attendance else "业务协同平台",
        version="V1.0",
        language="Java",
        product_type="APP" if attendance else "智慧城市软件",
        industry="企业办公",
        purpose="处理业务流程",
        summary="提供业务办理、查询和统计。",
        modules=modules,
        roles=["员工", "主管"],
        pages=[],
        dev_environment={},
        runtime_environment={},
        workflows=[{"name": "申请处理流程", "steps": ["提交", "处理", "完成"]}],
        report_metrics=["出勤率", "申请完成率"],
        industry_subtype_key="workforce_attendance" if attendance else "",
    )


def _pages() -> list[dict]:
    return [
        {"key": "login", "title": "登录界面", "page_kind": "login", "module_key": ""},
        {"key": "dashboard", "title": "业务总览", "page_kind": "dashboard", "module_key": ""},
        {"key": "attendance", "title": "员工考勤", "page_kind": "module", "module_key": "attendance"},
        {
            "key": "attendance_clock_in",
            "title": "员工考勤-上班打卡",
            "page_kind": "operation",
            "module_key": "attendance",
            "interaction_action": "上班打卡",
            "interaction_action_key": "clock_in",
        },
        {"key": "request", "title": "请假补卡申请", "page_kind": "module", "module_key": "request"},
        {
            "key": "request_leave",
            "title": "请假补卡申请-提交请假",
            "page_kind": "operation",
            "module_key": "request",
            "interaction_action": "提交请假",
            "interaction_action_key": "leave",
        },
        {"key": "statistics", "title": "统计分析", "page_kind": "statistics", "module_key": ""},
    ]


class NavigationContractTests(unittest.TestCase):
    def test_admin_page_hierarchy_secondary_navigation_and_back_target(self):
        task = GenerationTask(software_name="业务协同平台", model_provider="local-template")
        contracts = build_navigation_contracts(
            task,
            _blueprint(),
            _pages(),
            renderer="admin",
            nav_model="side_menu",
        )

        self.assertEqual(contracts["login"]["level"], "auth")
        self.assertEqual(contracts["dashboard"]["level"], "root")
        self.assertEqual(contracts["attendance"]["level"], "module")
        self.assertEqual(contracts["attendance_clock_in"]["level"], "action")
        self.assertEqual(contracts["statistics"]["level"], "analysis")
        self.assertEqual(contracts["attendance_clock_in"]["back_target"]["page_key"], "attendance")
        self.assertGreaterEqual(len(contracts["attendance_clock_in"]["secondary_items"]), 2)
        self.assertIn("上班打卡", [item["label"] for item in contracts["attendance"]["secondary_items"]])
        self.assertTrue(all(contract["ready"] for contract in contracts.values()))
        self.assertTrue(navigation_contract_summary(contracts)["navigation_contract_ready"])

    def test_modules_have_distinct_secondary_content_and_hierarchy_signatures(self):
        task = GenerationTask(software_name="业务协同平台", model_provider="local-template")
        contracts = build_navigation_contracts(task, _blueprint(), _pages(), renderer="admin", nav_model="top_tabs")

        attendance_labels = [item["label"] for item in contracts["attendance"]["secondary_items"]]
        request_labels = [item["label"] for item in contracts["request"]["secondary_items"]]
        self.assertNotEqual(attendance_labels, request_labels)
        self.assertNotEqual(contracts["attendance"]["hierarchy_signature"], contracts["request"]["hierarchy_signature"])

    def test_attendance_mobile_primary_navigation_is_home_clock_request_profile(self):
        task = GenerationTask(software_name="员工考勤助手", product_type="APP", model_provider="local-template")
        contracts = build_navigation_contracts(
            task,
            _blueprint(attendance=True),
            _pages(),
            renderer="mobile_app",
            nav_model="phone_tabs",
        )

        labels = [item["label"] for item in contracts["attendance"]["primary_items"]]
        self.assertEqual(labels, ["首页", "打卡", "申请", "我的"])
        self.assertEqual(contracts["attendance_clock_in"]["secondary_style"], "segmented")

    def test_module_without_operations_still_gets_safe_ready_contract(self):
        blueprint = _blueprint()
        blueprint.modules = [_module("archive", "档案中心", [])]
        task = GenerationTask(software_name="档案服务平台", model_provider="local-template")

        contract = build_local_navigation_contract(
            task,
            blueprint,
            page_key="archive",
            title="档案中心",
            page_kind="module",
            module=blueprint.modules[0],
            renderer="admin",
            nav_model="side_menu",
        )

        self.assertEqual(contract["schema_version"], NAVIGATION_CONTRACT_VERSION)
        self.assertEqual([item["label"] for item in contract["secondary_items"]], ["概览", "业务明细"])
        self.assertTrue(contract["ready"])


if __name__ == "__main__":
    unittest.main()
