import unittest
import base64
from pathlib import Path
from tempfile import TemporaryDirectory

from docx import Document

from backend.softcopyright.blueprint import FeatureModule, ProductBlueprint
from backend.softcopyright.docgen import (
    _actual_screenshot_action_labels,
    _actual_screenshot_operation_notes,
    _manual_ui_button_label_match,
    _visible_content_caption,
    _visible_content_intro_paragraphs,
    analyze_manual_ui_consistency,
)
from backend.softcopyright.screenshots import UiScreenshot


class ManualUiConsistencyTests(unittest.TestCase):
    def test_symbol_only_button_labels_match_exact_screenshot_actions(self):
        self.assertTrue(_manual_ui_button_label_match("↻", ["查询计划", "↻"]))
        self.assertTrue(_manual_ui_button_label_match(" ◉ ", ["◉"]))
        self.assertFalse(_manual_ui_button_label_match("!", ["确认"]))

    def _blueprint(self):
        return ProductBlueprint(
            software_name="质量管理系统",
            version="V1.0",
            language="JavaScript",
            product_type="应用软件",
            industry="工程质量管理",
            purpose="质量管理",
            summary="质量管理",
            modules=[
                FeatureModule(
                    "quality_plan",
                    "质量策划",
                    "维护质量策划。",
                    ["QualityPlan"],
                    data_fields=["策划编号", "策划名称", "策划状态"],
                )
            ],
            roles=["质量员"],
            pages=["质量策划"],
            dev_environment={},
            runtime_environment={},
        )

    def test_titles_and_buttons_match_actual_screenshot_metadata(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            image = root / "page.png"
            image.write_bytes(b"png")
            screenshots = {
                "quality_plan": UiScreenshot(
                    "quality_plan",
                    "质量策划",
                    "质量策划页面。",
                    str(root / "main.html"),
                    page_kind="module",
                    module_key="quality_plan",
                    image_path=str(image),
                    action_crops={"保存策划": str(root / "save.png")},
                ),
                "quality_plan_operation_2_2": UiScreenshot(
                    "quality_plan_operation_2_2",
                    "质量策划导出界面",
                    "导出质量策划。",
                    str(root / "export.html"),
                    page_kind="operation",
                    module_key="quality_plan",
                    image_path=str(image),
                    action_crops={"导出当前视图": str(root / "export.png")},
                ),
            }
            document = Document()
            document.add_paragraph("图：质量策划，质量策划页面。")
            document.add_paragraph("1. 页面提供【保存策划】入口。")
            document.add_paragraph("图：质量策划导出界面，导出质量策划。")
            document.add_paragraph("1. 页面提供【导出当前视图】入口。")
            path = root / "manual.docx"
            document.save(path)

            result = analyze_manual_ui_consistency(path, self._blueprint(), screenshots)

            self.assertTrue(result["manual_ui_consistency_ready"])
            self.assertEqual(result["manual_ui_title_mismatch_count"], 0)
            self.assertEqual(result["manual_ui_button_mismatch_count"], 0)

    def test_mismatched_title_and_button_fail_delivery_gate(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            image = root / "page.png"
            image.write_bytes(b"png")
            screenshots = {
                "quality_plan": UiScreenshot(
                    "quality_plan",
                    "质量策划",
                    "质量策划页面。",
                    str(root / "main.html"),
                    page_kind="module",
                    module_key="quality_plan",
                    image_path=str(image),
                    action_crops={"保存策划": str(root / "save.png")},
                )
            }
            document = Document()
            document.add_paragraph("图：质量策划统计界面，展示统计结果。")
            document.add_paragraph("1. 点击【删除记录】完成处理。")
            path = root / "manual.docx"
            document.save(path)

            result = analyze_manual_ui_consistency(path, self._blueprint(), screenshots)

            self.assertFalse(result["manual_ui_consistency_ready"])
            self.assertEqual(result["manual_ui_title_mismatch_count"], 1)
            self.assertEqual(result["manual_ui_button_mismatch_count"], 1)

    def test_button_image_alt_text_counts_as_button_coverage(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            image = root / "page.png"
            image.write_bytes(b"png")
            button = root / "save.png"
            button.write_bytes(
                base64.b64decode(
                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
                )
            )
            screenshots = {
                "quality_plan": UiScreenshot(
                    "quality_plan",
                    "质量策划",
                    "质量策划页面。",
                    str(root / "main.html"),
                    page_kind="module",
                    module_key="quality_plan",
                    image_path=str(image),
                    action_crops={"保存策划": str(button)},
                )
            }
            document = Document()
            document.add_paragraph("图：质量策划，质量策划页面。")
            paragraph = document.add_paragraph("1. 页面提供")
            shape = paragraph.add_run().add_picture(str(button))
            shape._inline.docPr.set("descr", "保存策划")
            shape._inline.docPr.set("title", "保存策划")
            paragraph.add_run("入口。")
            path = root / "manual.docx"
            document.save(path)

            result = analyze_manual_ui_consistency(path, self._blueprint(), screenshots)

            self.assertTrue(result["manual_ui_consistency_ready"])
            self.assertEqual(result["manual_ui_missing_button_coverage_count"], 0)

    def test_action_notes_prioritize_real_actions_and_skip_record_badges(self):
        screenshot = UiScreenshot(
            "measurement_warning",
            "施工测量记录预警界面",
            "预警处理。",
            "warning.html",
            page_kind="operation",
            module_key="measurement",
            action_crops={
                "施工测量记录记录01": "record-1.png",
                "施工测量记录记录02": "record-2.png",
                "控制点复测": "tab.png",
                "下发复测指令": "issue.png",
                "打开原始成果": "open.png",
                "下载测量包": "download.png",
                "追加复核说明": "append.png",
            },
        )

        labels = _actual_screenshot_action_labels(screenshot)

        self.assertEqual(labels, ["下发复测指令", "打开原始成果", "下载测量包", "追加复核说明"])

    def test_login_notes_skip_captcha_codes_and_symbol_only_controls(self):
        screenshot = UiScreenshot(
            "login",
            "登录界面",
            "用户输入账号、密码和验证码后进入系统。",
            "login.html",
            page_kind="login",
            action_crops={"7K4M": "captcha.png", "◉": "password.png"},
            visible_content_summary={
                "ready": True,
                "visible_text": "生产运营安全登录 登录密码 图形验证码 7 K 4 M 进入生产指挥台",
                "headings": ["生产运营安全登录"],
                "metrics": [],
                "fields": ["生产运营账号", "登录密码", "图形验证码"],
                "statuses": [],
                "filters": [],
                "actions": ["7 K 4 M", "进入生产指挥台 →", "7K4M", "◉"],
            },
        )

        labels = _actual_screenshot_action_labels(screenshot)
        notes = _actual_screenshot_operation_notes(screenshot, self._blueprint().modules[0])
        text = "\n".join(notes)

        self.assertEqual(labels, ["进入生产指挥台"])
        self.assertIn("【进入生产指挥台】", text)
        self.assertNotIn("【7K4M】", text)
        self.assertNotIn("【◉】", text)

    def test_login_notes_explain_semantic_auxiliary_controls(self):
        screenshot = UiScreenshot(
            "login",
            "登录界面",
            "用户输入账号、密码和验证码后进入系统。",
            "login.html",
            page_kind="login",
            action_crops={"刷新验证码": "captcha.png", "显示密码": "password.png"},
            visible_content_summary={
                "ready": True,
                "visible_text": "生产运营安全登录 登录密码 图形验证码 进入生产指挥台",
                "headings": ["生产运营安全登录"],
                "metrics": [],
                "fields": ["生产运营账号", "登录密码", "图形验证码"],
                "statuses": [],
                "filters": [],
                "actions": ["刷新验证码", "进入生产指挥台", "显示密码"],
            },
        )

        labels = _actual_screenshot_action_labels(screenshot)
        notes = _actual_screenshot_operation_notes(screenshot, self._blueprint().modules[0])
        text = "\n".join(notes)

        self.assertEqual(labels, ["进入生产指挥台", "刷新验证码", "显示密码"])
        self.assertIn("点击【进入生产指挥台】完成登录校验", text)
        self.assertIn("验证码不清晰时使用【刷新验证码】重新获取", text)
        self.assertIn("核对密码输入时使用【显示密码】", text)

    def test_login_intro_does_not_treat_captcha_placeholder_as_filter(self):
        screenshot = UiScreenshot(
            "login",
            "登录界面",
            "",
            "login.html",
            page_kind="login",
            visible_content_summary={
                "ready": True,
                "visible_text": "生产运营安全登录 生产运营账号 登录密码 图形验证码 输入右侧字符 工厂运行环境 岗位身份 进入生产指挥台",
                "headings": ["生产运营安全登录", "岗位身份", "运行与访问状态"],
                "metrics": ["当前工单"],
                "fields": ["生产运营账号", "登录密码", "图形验证码"],
                "statuses": [],
                "filters": ["输入右侧字符", "华东二厂 · 生产环境"],
                "actions": ["进入生产指挥台", "刷新验证码", "显示密码"],
            },
        )

        paragraphs = _visible_content_intro_paragraphs(screenshot, "登录界面")
        caption = _visible_content_caption(screenshot)
        notes = _actual_screenshot_operation_notes(screenshot, self._blueprint().modules[0])
        text = "\n".join(paragraphs)
        note_text = "\n".join(notes)

        self.assertIn("生产运营账号、登录密码、图形验证码", text)
        self.assertIn("通过【进入生产指挥台】完成登录校验", text)
        self.assertNotIn("调整查看范围", text)
        self.assertNotIn("通过输入右侧字符", text)
        self.assertIn("生产运营账号、登录密码、图形验证码、工厂运行环境、岗位身份", caption)
        self.assertNotIn("当前工单", caption)
        self.assertIn("依次填写生产运营账号、登录密码、图形验证码，再选择工厂运行环境、岗位身份", note_text)
        self.assertNotIn("调整当前查看范围", note_text)
        self.assertNotIn("当前可见的指标", note_text)

    def test_operation_notes_use_page_visible_content_instead_of_module_blueprint_fields(self):
        module = self._blueprint().modules[0]
        screenshot = UiScreenshot(
            "quality_plan",
            "质量策划",
            "泛化说明。",
            "quality-plan.html",
            page_kind="module",
            module_key="quality_plan",
            action_crops={"保存策划": "save.png"},
            visible_content_summary={
                "ready": True,
                "visible_text": "质量策划结果详情 关联完整性与执行条件 计划执行率 检验点完成率 保存策划",
                "headings": ["质量策划结果详情", "关联完整性与执行条件"],
                "metrics": ["计划执行率", "检验点完成率"],
                "fields": ["工程结构树编号"],
                "statuses": ["当前状态：可执行"],
                "filters": [],
                "actions": ["保存策划"],
            },
        )

        notes = _actual_screenshot_operation_notes(screenshot, module, main_page=True)
        text = "\n".join(notes)

        self.assertIn("质量策划结果详情", text)
        self.assertIn("计划执行率", text)
        self.assertNotIn("策划状态", text)

    def test_semantic_gate_rejects_blueprint_field_missing_from_visible_page(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            image = root / "page.png"
            image.write_bytes(b"png")
            screenshots = {
                "quality_plan": UiScreenshot(
                    "quality_plan",
                    "质量策划",
                    "质量策划页面。",
                    str(root / "main.html"),
                    page_kind="module",
                    module_key="quality_plan",
                    image_path=str(image),
                    action_crops={"保存策划": str(root / "save.png")},
                    visible_content_summary={
                        "ready": True,
                        "visible_text": "质量策划结果详情 计划执行率 保存策划",
                        "headings": ["质量策划结果详情"],
                        "metrics": ["计划执行率"],
                        "fields": [],
                        "statuses": [],
                        "filters": [],
                        "actions": ["保存策划"],
                    },
                )
            }
            document = Document()
            document.add_paragraph("图：质量策划，页面展示质量策划结果详情和计划执行率。")
            document.add_paragraph("1. 页面可查看策划状态，并提供【保存策划】入口。")
            path = root / "manual.docx"
            document.save(path)

            result = analyze_manual_ui_consistency(path, self._blueprint(), screenshots)

            self.assertFalse(result["manual_ui_consistency_ready"])
            self.assertEqual(result["manual_ui_semantic_mismatch_count"], 1)
            self.assertIn("策划状态", result["manual_ui_semantic_mismatches"][0]["references"])

    def test_semantic_gate_accepts_visible_page_terms(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            image = root / "page.png"
            image.write_bytes(b"png")
            screenshots = {
                "quality_plan": UiScreenshot(
                    "quality_plan",
                    "质量策划",
                    "质量策划页面。",
                    str(root / "main.html"),
                    page_kind="module",
                    module_key="quality_plan",
                    image_path=str(image),
                    action_crops={"保存策划": str(root / "save.png")},
                    visible_content_summary={
                        "ready": True,
                        "visible_text": "质量策划结果详情 计划执行率 保存策划",
                        "headings": ["质量策划结果详情"],
                        "metrics": ["计划执行率"],
                        "fields": [],
                        "statuses": [],
                        "filters": [],
                        "actions": ["保存策划"],
                    },
                )
            }
            document = Document()
            document.add_paragraph("图：质量策划，页面展示质量策划结果详情和计划执行率。")
            document.add_paragraph("1. 页面可查看质量策划结果详情和计划执行率，并提供【保存策划】入口。")
            path = root / "manual.docx"
            document.save(path)

            result = analyze_manual_ui_consistency(path, self._blueprint(), screenshots)

            self.assertTrue(result["manual_ui_consistency_ready"])
            self.assertTrue(result["manual_ui_semantic_ready"])

    def test_desktop_screenshots_reject_mobile_terminal_description_anywhere_in_manual(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            image = root / "page.png"
            image.write_bytes(b"png")
            screenshots = {
                "quality_plan": UiScreenshot(
                    "quality_plan",
                    "质量策划",
                    "质量策划页面。",
                    str(root / "main.html"),
                    page_kind="module",
                    module_key="quality_plan",
                    image_path=str(image),
                    width=1280,
                    height=720,
                )
            }
            document = Document()
            document.add_paragraph("本软件提供移动端质量工作入口。")
            document.add_paragraph("图：质量策划，质量策划页面。")
            path = root / "manual.docx"
            document.save(path)

            result = analyze_manual_ui_consistency(path, self._blueprint(), screenshots)

            self.assertFalse(result["manual_ui_consistency_ready"])
            self.assertEqual(result["manual_ui_expected_renderer"], "admin")
            self.assertIn("移动端", result["manual_ui_renderer_mismatches"])


if __name__ == "__main__":
    unittest.main()
