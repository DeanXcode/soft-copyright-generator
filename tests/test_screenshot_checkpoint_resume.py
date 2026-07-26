from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.softcopyright.screenshots import (
    ADMIN_VIEWPORT,
    SCREENSHOT_CHECKPOINT_VERSION,
    UiScreenshot,
    _normalize_visible_content_summary,
    _restore_screenshot_checkpoint_prefix,
    _save_screenshot_checkpoint_page,
)


class ScreenshotCheckpointResumeTests(unittest.TestCase):
    def test_confirmation_summary_does_not_invent_contract_fields(self):
        item = UiScreenshot(
            "confirm",
            "确认结果",
            "确认结果。",
            "confirm.html",
            page_kind="operation",
            requires_confirmation=True,
            interaction_action="确认结果",
            interaction_input_fields=["未显示的内部字段", "任务编号"],
        )

        summary = _normalize_visible_content_summary(
            {
                "visible_text": "确认结果 任务 2026-0718 状态影响 确认结果 取消",
                "headings": ["确认结果"],
                "fields": ["任务", "状态影响"],
                "actions": ["取消", "确认结果"],
            },
            item,
        )

        self.assertEqual(summary["fields"], ["任务", "状态影响"])
        self.assertNotIn("未显示的内部字段", summary["semantic_terms"])
    def test_resume_restores_only_the_contiguous_valid_prefix(self):
        with TemporaryDirectory() as temporary_directory:
            ui_dir = Path(temporary_directory)
            items = []
            checkpoint = {"version": SCREENSHOT_CHECKPOINT_VERSION, "pages": {}}
            for index in range(1, 4):
                html_path = ui_dir / f"page-{index}.html"
                html_path.write_text(f"<html><body>page {index}</body></html>", encoding="utf-8")
                image_path = ui_dir / f"page-{index}.png"
                image_path.write_bytes(b"png")
                item = UiScreenshot(
                    key=f"page-{index}",
                    title=f"Page {index}",
                    caption="",
                    html_path=str(html_path),
                    image_path=str(image_path),
                    width=ADMIN_VIEWPORT["width"],
                    height=ADMIN_VIEWPORT["height"],
                runtime_fetches=[{"url": f"/api/page-{index}", "ok": True}],
                visible_content_summary={
                    "ready": True,
                    "headings": [f"Page {index} summary"],
                    "visible_text": f"Page {index} summary",
                },
                )
                items.append(item)
                _save_screenshot_checkpoint_page(ui_dir, checkpoint, item, "admin", ADMIN_VIEWPORT)

            (ui_dir / "page-2.html").write_text("<html><body>changed</body></html>", encoding="utf-8")
            resumed_items = [
                UiScreenshot(item.key, item.title, item.caption, item.html_path)
                for item in items
            ]
            restored_checkpoint, restored_count = _restore_screenshot_checkpoint_prefix(
                ui_dir,
                resumed_items,
                "admin",
                ADMIN_VIEWPORT,
            )

        self.assertEqual(restored_count, 1)
        self.assertTrue(resumed_items[0].image_path)
        self.assertEqual(resumed_items[0].runtime_fetches[0]["url"], "/api/page-1")
        self.assertEqual(resumed_items[0].visible_content_summary["headings"], ["Page 1 summary"])
        self.assertIsNone(resumed_items[1].image_path)
        self.assertEqual(list(restored_checkpoint["pages"]), ["page-1"])

    def test_shared_react_bundle_change_invalidates_cached_screenshots(self):
        with TemporaryDirectory() as temporary_directory:
            ui_dir = Path(temporary_directory)
            assets_dir = ui_dir / "assets"
            assets_dir.mkdir()
            (assets_dir / "app.js").write_text("export const version = 1;", encoding="utf-8")
            (assets_dir / "index.css").write_text("body{color:#123}", encoding="utf-8")
            html_path = ui_dir / "page.html"
            html_path.write_text("<html><body><script src='./assets/app.js'></script></body></html>", encoding="utf-8")
            image_path = ui_dir / "page.png"
            image_path.write_bytes(b"png")
            item = UiScreenshot(
                key="page",
                title="Page",
                caption="",
                html_path=str(html_path),
                image_path=str(image_path),
                width=ADMIN_VIEWPORT["width"],
                height=ADMIN_VIEWPORT["height"],
            )
            checkpoint = {"version": SCREENSHOT_CHECKPOINT_VERSION, "pages": {}}
            _save_screenshot_checkpoint_page(ui_dir, checkpoint, item, "admin", ADMIN_VIEWPORT)

            (assets_dir / "app.js").write_text("export const version = 2;", encoding="utf-8")
            resumed = [UiScreenshot("page", "Page", "", str(html_path))]
            restored_checkpoint, restored_count = _restore_screenshot_checkpoint_prefix(
                ui_dir,
                resumed,
                "admin",
                ADMIN_VIEWPORT,
            )

        self.assertEqual(restored_count, 0)
        self.assertEqual(restored_checkpoint["pages"], {})

    def test_visible_content_summary_normalizes_dom_payload(self):
        item = UiScreenshot(
            "statistics",
            "统计报表界面",
            "",
            "statistics.html",
            action_crops={"导出质量月报": "export.png"},
        )

        summary = _normalize_visible_content_summary(
            {
                "visible_text": "统计报表 质量计划执行率 94.8% 导出质量月报",
                "headings": ["统计报表", "统计报表", ""],
                "metrics": ["质量计划执行率", "94.8%"],
                "fields": ["工程部位"],
                "statuses": ["已完成"],
                "filters": ["本月", "TJ04"],
                "actions": ["7 K 4 M", "导出质量月报 →", "◉"],
            },
            item,
        )

        self.assertTrue(summary["ready"])
        self.assertEqual(summary["headings"], ["统计报表"])
        self.assertEqual(summary["metrics"], ["质量计划执行率"])
        self.assertIn("导出质量月报", summary["actions"])
        self.assertNotIn("7 K 4 M", summary["actions"])
        self.assertNotIn("◉", summary["actions"])
        self.assertIn("工程部位", summary["semantic_terms"])
        self.assertNotIn("TJ04", summary["filters"])

    def test_visible_content_summary_keeps_semantic_icon_actions(self):
        item = UiScreenshot(
            "login",
            "登录界面",
            "",
            "login.html",
            action_crops={"刷新验证码": "captcha.png", "显示密码": "password.png"},
        )

        summary = _normalize_visible_content_summary(
            {
                "visible_text": "登录密码 图形验证码 进入生产指挥台",
                "headings": ["生产运营安全登录"],
                "actions": ["刷新验证码", "显示密码", "进入生产指挥台 →"],
            },
            item,
        )

        self.assertEqual(summary["actions"], ["刷新验证码", "显示密码", "进入生产指挥台"])

    def test_visible_content_summary_uses_screen_contract_for_plain_template_dom(self):
        item = UiScreenshot(
            "service_operation_2_2",
            "服务预约管理查询界面",
            "",
            "service_operation_2_2.html",
            page_kind="operation",
            module_key="service_booking",
            interaction_action="查询服务预约",
            interaction_input_fields=["预约编号", "服务日期"],
        )

        summary = _normalize_visible_content_summary(
            {
                "visible_text": "服务预约管理 查询服务预约 预约编号 服务日期 待处理记录 12 条",
                "headings": [],
                "metrics": [],
                "fields": [],
                "actions": [],
            },
            item,
        )

        self.assertTrue(summary["ready"])
        self.assertIn("服务预约管理查询界面", summary["headings"])
        self.assertIn("预约编号", summary["fields"])
        self.assertIn("查询服务预约", summary["actions"])


if __name__ == "__main__":
    unittest.main()
