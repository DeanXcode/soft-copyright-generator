import unittest

from backend.softcopyright.blueprint import FeatureModule, ProductBlueprint
from backend.softcopyright.docgen import (
    _extend_faq_paragraphs,
    _extend_security_paragraphs,
    _manual_architecture_name,
    _manual_content_for_renderer,
    _manual_deployment_topology,
    _manual_paragraphs_for_renderer,
    _manual_pdf_text_density_page_result,
    _manual_product_type,
    _manual_runtime_environment_value,
    _expand_paragraphs,
    _figure_note_templates,
    _manual_generic_sentence_count,
    _manual_semantic_anchor_count,
    _manual_template_risk_level,
    _start_manual_closing_section,
    _start_manual_security_section,
)


class ManualPdfDensityTests(unittest.TestCase):
    def test_manual_sentence_variants_are_stable_and_contextual(self):
        first = _figure_note_templates("质量策划", "质量策划界面")
        second = _figure_note_templates("质量策划", "质量策划界面")

        self.assertEqual(first, second)
        self.assertTrue(any("质量策划" in item for item in first))
        self.assertNotEqual(first, _figure_note_templates("质量策划", "质量策划导出界面"))

    def test_template_risk_metrics_distinguish_generic_and_business_text(self):
        generic = ["页面展示当前内容和处理入口。"] * 8
        business = ["用户填写设备编号后点击查询，系统更新处理状态并记录结果。"] * 8

        self.assertGreater(_manual_generic_sentence_count(generic), _manual_generic_sentence_count(business))
        self.assertLess(_manual_semantic_anchor_count(generic), _manual_semantic_anchor_count(business))
        self.assertEqual(_manual_template_risk_level(8, 0.8, 0, 10, 0.2), "high")
        self.assertEqual(_manual_template_risk_level(0, 0, 0, 10, 1.0), "low")

    def test_expanded_paragraphs_use_stable_context_variant(self):
        first = _expand_paragraphs([], min_count=2, context="质量策划")
        second = _expand_paragraphs([], min_count=2, context="质量策划")

        self.assertEqual(first, second)
        self.assertEqual(len(first), 2)
        self.assertTrue(any("状态" in item or "记录" in item for item in first))

    def test_operation_manual_cover_is_not_treated_as_body_density_page(self):
        lines = ["客户安装版弹窗主题零令牌验收系统 V1.0 1", "客户安装版弹窗主题零令牌验收系统", "操作手册"]

        result = _manual_pdf_text_density_page_result("\n".join(lines), 1, 22, 30)

        self.assertFalse(result["text_density_page"])
        self.assertTrue(result["ready"])

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

    def test_compact_security_section_with_substantive_controls_is_content_sufficient(self):
        lines = [
            "六、权限与安全",
            "系统通过用户、角色、菜单和数据范围进行权限控制，避免越权访问。",
            "用户登录、数据新增、状态变更和导出下载等关键操作均记录审计日志。",
            "管理员可根据岗位职责配置角色权限，并定期查看异常登录和高风险操作记录。",
            "关键业务操作必须写入审计日志，统计报表必须按当前数据权限过滤。",
            "服务预约管理必须校验状态流转顺序和重复提交。",
            "门店核销管理必须校验状态流转顺序和重复提交。",
            "售后工单管理必须校验状态流转顺序和重复提交。",
            "模块之间通过业务编号和状态字段关联，用于支撑追溯和审计。",
            "无对应菜单权限的用户不能进入受限页面。",
            "高风险操作执行前需要核对当前角色和数据范围。",
            "系统保留登录用户、操作时间、变更原因和处理结果。",
        ]
        text = "\n".join(lines) + " 权限控制和审计记录用于复核用户操作与状态流转。" * 6

        result = _manual_pdf_text_density_page_result(text, 21, 22, 30)

        self.assertGreaterEqual(result["character_count"], 420)
        self.assertTrue(result["ready"])
        self.assertEqual(result["soft_pass_reason"], "security_content_page")

    def test_substantive_final_troubleshooting_page_is_not_blocked_by_30_line_rule(self):
        lines = [
            "用户进入页面后应检查当前状态、查询条件和业务记录，确认无误后重新提交处理结果。"
            for _ in range(14)
        ]

        result = _manual_pdf_text_density_page_result("\n".join(lines), 10, 10, 30)

        self.assertTrue(result["text_density_page"])
        self.assertTrue(result["ready"])
        self.assertEqual(result["soft_pass_reason"], "closing_content_page")

    def test_compact_400_character_final_faq_is_content_sufficient(self):
        lines = [
            "用户在页面提交失败时，应检查必填字段、业务编号、处理人员和时间信息是否完整。",
            "系统按照登录用户权限执行校验，用户应根据页面提示补齐后重新提交处理结果。",
            "状态长时间未更新时，可刷新页面并查看处理轨迹、操作日志和关联任务记录。",
            "若上一步尚未完成，应返回对应详情处理，不能直接跳过既定业务节点。",
            "导入失败时应确认文件格式、字段表头、文件大小和当前账号权限符合页面要求。",
            "修正后重新选择文件，先查看校验结果，再执行正式导入，避免重复写入。",
            "导出结果异常时，应重新确认统计周期、筛选范围和数据版本，并检查下载目录。",
            "重新生成后，页面应显示导出时间、操作人员和结果文件状态。",
            "弱网或服务短暂中断时，不要连续重复提交同一业务操作。",
            "用户可保留当前页面，待连接恢复后刷新处理结果并核对最新状态。",
            "若系统已生成操作记录，应以最新状态和审计日志为准。",
            "检查完成后重新查询页面，确认记录状态、处理结果和后续操作入口均正常。",
        ]
        text = "\n".join(lines)
        text += " 用户应按页面提示复核查询结果、状态记录和系统处理反馈。" * 3

        result = _manual_pdf_text_density_page_result(text, 29, 29, 30)

        self.assertGreaterEqual(result["character_count"], 400)
        self.assertTrue(result["ready"])
        self.assertEqual(result["soft_pass_reason"], "closing_content_page")

    def test_nine_line_300_character_final_faq_is_content_sufficient(self):
        lines = [
            "状态长时间未更新时，用户可刷新当前页面并查看处理轨迹、操作日志和关联任务记录。",
            "若上一步尚未完成，应返回对应详情处理，不能直接跳过既定业务节点。",
            "导入附件失败时，应确认文件格式、字段表头、文件大小和当前账号权限符合要求。",
            "修正后重新选择文件，先查看校验结果，再执行正式导入，避免重复写入。",
            "导出结果异常时，应重新确认统计周期、筛选范围和数据版本，并检查下载目录。",
            "重新生成后，页面应显示导出时间、操作人员和结果文件状态。",
            "弱网或服务中断时，不要连续重复提交同一业务操作。",
            "用户可保留当前页面，待连接恢复后刷新处理结果并确认记录状态。",
            "若系统已生成操作记录，应以最新状态和审计日志为准。",
        ]
        text = "\n".join(lines)
        text += " 用户应复核系统查询结果、页面状态和处理记录。" * 2

        result = _manual_pdf_text_density_page_result(text, 27, 27, 30)

        self.assertGreaterEqual(result["character_count"], 300)
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

    def test_closing_faq_section_starts_on_a_new_page(self):
        from docx import Document
        from docx.oxml.ns import qn

        document = Document()
        _start_manual_closing_section(document, "七、常见问题处理")

        paragraphs = document.paragraphs
        self.assertEqual(paragraphs[-1].text, "七、常见问题处理")
        page_breaks = paragraphs[-2]._p.findall(".//" + qn("w:br"))
        self.assertTrue(any(item.get(qn("w:type")) == "page" for item in page_breaks))

    def test_security_section_starts_on_a_new_page(self):
        from docx import Document
        from docx.oxml.ns import qn

        document = Document()
        _start_manual_security_section(document, "六、权限与安全")

        paragraphs = document.paragraphs
        self.assertEqual(paragraphs[-1].text, "六、权限与安全")
        page_breaks = paragraphs[-2]._p.findall(".//" + qn("w:br"))
        self.assertTrue(any(item.get(qn("w:type")) == "page" for item in page_breaks))

    def test_security_section_is_extended_with_substantive_local_controls(self):
        blueprint = self._desktop_blueprint()
        blueprint.roles = ["质量主管", "巡检员"]
        blueprint.quality_rules = ["质量问题关闭前必须完成复核"]
        blueprint.data_relations = ["质量问题与整改记录关联", "整改记录与审计日志关联"]

        paragraphs = _extend_security_paragraphs(blueprint, ["系统按角色控制页面权限。"])

        self.assertEqual(len(paragraphs), 6)
        self.assertGreater(sum(len(item) for item in paragraphs), 450)
        self.assertTrue(any("审计" in item for item in paragraphs))

    def test_desktop_manual_filters_mobile_only_paragraphs_globally(self):
        manual_content = {
            "overview": ["系统用于桌面端质量管理。"],
            "security": [
                "用户登录移动 App 后进入项目。",
                "系统按角色控制桌面页面权限。",
                "管理员可为移动端用户配置角色权限。",
            ],
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

        self.assertEqual(
            result["security"],
            ["系统按角色控制桌面页面权限。", "管理员可为终端用户配置角色权限。"],
        )
        self.assertEqual(result["faq"], ["用户可刷新当前桌面页面。"])
        self.assertEqual(result["modules"]["quality_plan"]["paragraphs"], ["用户在列表页查看质量计划。"])

    def test_actual_admin_renderer_overrides_stale_mobile_experience_terminal(self):
        paragraphs = ["本页由移动端用户发起筛选。", "用户在桌面列表页查看处理结果。"]
        design_brief = {
            "expected_renderer": "admin",
            "product_experience_spec": {"terminal": "mobile_app"},
        }

        result = _manual_paragraphs_for_renderer(paragraphs, design_brief)

        self.assertEqual(result, ["本页由终端用户发起筛选。", "用户在桌面列表页查看处理结果。"])

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
