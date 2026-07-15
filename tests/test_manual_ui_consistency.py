import unittest
import base64
from pathlib import Path
from tempfile import TemporaryDirectory

from docx import Document

from backend.softcopyright.blueprint import FeatureModule, ProductBlueprint
from backend.softcopyright.docgen import (
    _actual_screenshot_action_labels,
    _actual_screenshot_operation_notes,
    analyze_manual_ui_consistency,
)
from backend.softcopyright.screenshots import UiScreenshot


class ManualUiConsistencyTests(unittest.TestCase):
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
