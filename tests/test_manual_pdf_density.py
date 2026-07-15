import unittest

from backend.softcopyright.blueprint import FeatureModule, ProductBlueprint
from backend.softcopyright.docgen import (
    _extend_faq_paragraphs,
    _manual_architecture_name,
    _manual_content_for_renderer,
    _manual_deployment_topology,
    _manual_pdf_text_density_page_result,
    _manual_product_type,
    _manual_runtime_environment_value,
)


class ManualPdfDensityTests(unittest.TestCase):
    def test_toc_page_is_not_treated_as_body_density_page(self):
        lines = ["目 录", "一 软件概述", "二 运行环境", "三 登录与主界面", "四 功能操作说明"]

        result = _manual_pdf_text_density_page_result("\n".join(lines), 2, 27, 30)

        self.assertFalse(result["text_density_page"])
        self.assertTrue(result["ready"])

    def test_sub_30_line_operation_page_is_content_sufficient(self):
        lines = [
            f"用户在页面中点击查询并查看记录状态，系统显示第 {index} 项业务处理结果。"
            for index in range(23)
        ]

        result = _manual_pdf_text_density_page_result("\n".join(lines), 6, 17, 30)

        self.assertTrue(result["text_density_page"])
        self.assertTrue(result["ready"])
        self.assertEqual(result["soft_pass_reason"], "content_sufficient_page")

    def test_sparse_text_page_still_fails(self):
        lines = [f"第 {index} 项" for index in range(12)]

        result = _manual_pdf_text_density_page_result("\n".join(lines), 3, 10, 30)

        self.assertTrue(result["text_density_page"])
        self.assertFalse(result["ready"])
        self.assertEqual(result["soft_pass_reason"], "")

    def test_substantive_final_troubleshooting_page_is_not_blocked_by_30_line_rule(self):
        lines = [
            "用户进入页面后应检查当前状态、查询条件和业务记录，确认无误后重新提交处理结果。"
            for _ in range(14)
        ]

        result = _manual_pdf_text_density_page_result("\n".join(lines), 10, 10, 30)

        self.assertTrue(result["text_density_page"])
        self.assertTrue(result["ready"])
        self.assertEqual(result["soft_pass_reason"], "closing_content_page")

    def test_faq_is_extended_to_avoid_sparse_final_orphan_page(self):
        blueprint = ProductBlueprint(
            software_name="轨道交通施工质量分析检验大数据系统",
            version="V1.0",
            language="Java",
            product_type="大数据软件",
            industry="轨道交通工程施工质量管理",
            purpose="质量检验",
            summary="施工质量分析",
            modules=[
                FeatureModule("quality_plan", "质量计划管理", "维护质量计划。", ["QualityPlan"]),
                FeatureModule("inspection_lot", "检验批评定", "维护检验批。", ["InspectionLot"]),
                FeatureModule("rectification", "质量问题整改", "跟踪整改。", ["Rectification"]),
            ],
            roles=["质量员"],
            pages=["质量首页"],
            dev_environment={},
            runtime_environment={},
            quality_rules=["检验批提交前必须完成主控项目和实测项目校验"],
        )

        paragraphs = _extend_faq_paragraphs(blueprint, ["检验批无法报验时，应检查主控项目是否完整。"])

        self.assertEqual(len(paragraphs), 10)
        self.assertGreater(sum(len(item) for item in paragraphs), 700)

    def test_desktop_manual_filters_mobile_only_paragraphs_globally(self):
        manual_content = {
            "overview": ["系统用于桌面端质量管理。"],
            "security": ["用户登录移动 App 后进入项目。", "系统按角色控制桌面页面权限。"],
            "faq": ["在个人中心切换项目身份后重试。", "用户可刷新当前桌面页面。"],
            "modules": {
                "quality_plan": {
                    "title": "质量计划管理",
                    "paragraphs": ["通过底部导航进入项目。", "用户在列表页查看质量计划。"],
                }
            },
        }
        design_brief = {
            "expected_renderer": "react",
            "product_experience_spec": {"terminal": "desktop"},
        }

        result = _manual_content_for_renderer(manual_content, design_brief)

        self.assertEqual(result["security"], ["系统按角色控制桌面页面权限。"])
        self.assertEqual(result["faq"], ["用户可刷新当前桌面页面。"])
        self.assertEqual(result["modules"]["quality_plan"]["paragraphs"], ["用户在列表页查看质量计划。"])

    def test_desktop_manual_rewrites_mobile_architecture_table_fields(self):
        blueprint = self._desktop_blueprint()
        blueprint.technical_architecture = {"name": "移动端与服务端分离架构"}
        blueprint.deployment_topology = "移动 App 部署于施工单位用户终端，通过项目专网访问服务端。"
        design_brief = {
            "expected_renderer": "admin",
            "product_experience_spec": {"terminal": "industrial_touch_panel"},
        }

        architecture = _manual_architecture_name(blueprint, design_brief)
        topology = _manual_deployment_topology(blueprint, design_brief)

        self.assertNotIn("移动端", architecture)
        self.assertIn("桌面 Web 端", architecture)
        self.assertNotIn("移动 App", topology)
        self.assertIn("工业触控终端或桌面浏览器", topology)

        runtime_hardware = _manual_runtime_environment_value("Web 服务器、移动终端或浏览器终端", design_brief)
        runtime_os = _manual_runtime_environment_value("Linux 服务器、Android/iOS 浏览器环境、Windows 客户端浏览器", design_brief)
        self.assertNotIn("移动终端", runtime_hardware)
        self.assertIn("工业触控终端或桌面浏览器终端", runtime_hardware)
        self.assertNotIn("Android/iOS", runtime_os)

    def test_manual_product_type_drops_unrelated_medical_label(self):
        blueprint = self._desktop_blueprint()
        blueprint.industry = "轨道交通工程施工质量管理"
        blueprint.summary = "轨道交通施工质量检验大数据分析"

        class Task:
            software_name = "轨道交通施工质量分析检验大数据系统"
            product_type = "医疗软件"

        self.assertEqual(_manual_product_type(Task(), blueprint), "大数据软件")

    def _desktop_blueprint(self):
        return ProductBlueprint(
            software_name="质量管理系统",
            version="V1.0",
            language="JavaScript",
            product_type="应用软件",
            industry="工程质量管理",
            purpose="质量管理",
            summary="质量管理",
            modules=[FeatureModule("quality_plan", "质量计划管理", "维护质量计划。", ["QualityPlan"])],
            roles=["质量员"],
            pages=["质量首页"],
            dev_environment={},
            runtime_environment={},
        )


if __name__ == "__main__":
    unittest.main()
