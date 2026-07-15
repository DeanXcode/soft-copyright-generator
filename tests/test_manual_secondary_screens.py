from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from backend.softcopyright.docgen import (
    _add_heading,
    _add_manual_cover,
    _add_manual_paragraph_with_action_images,
    _add_manual_toc,
    _add_ui_figure,
    _configure_application_section,
    _find_manual_action_crop,
    _module_paragraphs_conflict_with_ui,
    _set_default_font,
    analyze_manual_density,
    update_manual_toc_page_numbers,
)
from backend.softcopyright.screenshots import (
    UiScreenshot,
    _build_page_specs,
    _instant_interaction_text_hits,
    _mobile_canvas_width_ready,
    _runtime_layout_guard_style,
)
from backend.softcopyright.ai_frontend_codegen import _operation_prompt_rule, _runtime_guard_style
from backend.softcopyright.interaction_semantics import action_requires_confirmation, mobile_secondary_interaction
from backend.softcopyright.blueprint import FeatureModule, ProductBlueprint
from backend.softcopyright.models import GenerationTask
from backend.softcopyright.ui_blueprint import UiBlueprint, UiScreenBlueprint, complete_ui_blueprint_coverage


class ManualSecondaryScreenTests(unittest.TestCase):
    def test_manual_large_titles_and_header_tables_keep_safe_page_geometry(self):
        from docx import Document
        from docx.oxml.ns import qn

        document = Document()
        _set_default_font(document, "宋体", 10.5, line_spacing_pt=14.5, space_after_pt=2)
        section = document.sections[0]
        _configure_application_section(
            section,
            header_text="道路工程施工进度智能管控系统 V1.0",
            top_margin_pt=54,
            bottom_margin_pt=54,
            left_margin_pt=72,
            right_margin_pt=72,
        )
        _add_manual_cover(document, SimpleNamespace(software_name="道路工程施工进度智能管控系统"))
        _add_manual_toc(document, SimpleNamespace(modules=[SimpleNamespace(title="施工总进度计划")]))

        usable_twips = round((section.page_width - section.left_margin - section.right_margin) / 635)
        header_table = section.header.tables[0]
        header_width = int(header_table._tbl.tblPr.find(qn("w:tblW")).get(qn("w:w")))
        page_margin = header_table.rows[0].cells[1]._tc.get_or_add_tcPr().find(qn("w:tcMar"))
        page_right_margin = int(page_margin.find(qn("w:right")).get(qn("w:w")))
        toc_table = document.tables[0]
        toc_width = int(toc_table._tbl.tblPr.find(qn("w:tblW")).get(qn("w:w")))
        cover_title = next(paragraph for paragraph in document.paragraphs if paragraph.text == "道路工程施工进度智能管控系统")
        cover_subtitle = next(paragraph for paragraph in document.paragraphs if paragraph.text == "操作手册")
        toc_title = next(paragraph for paragraph in document.paragraphs if paragraph.text == "目 录")

        self.assertLess(header_width, usable_twips)
        self.assertGreaterEqual(page_right_margin, 100)
        self.assertLess(toc_width, usable_twips)
        self.assertGreaterEqual(cover_title.paragraph_format.line_spacing.pt, 34)
        self.assertGreaterEqual(cover_subtitle.paragraph_format.line_spacing.pt, 30)
        self.assertGreaterEqual(toc_title.paragraph_format.line_spacing.pt, 30)

    def test_mobile_specs_include_button_triggered_secondary_screen(self):
        task = SimpleNamespace()
        module = SimpleNamespace(key="music_search", title="音乐搜索", operations=["音乐搜索登记"])
        blueprint = SimpleNamespace(modules=[module])
        ui_blueprint = UiBlueprint(
            renderer="mobile_app",
            visual_style="mobile",
            screens=[
                UiScreenBlueprint(
                    key="music_search",
                    title="音乐搜索",
                    caption="搜索歌曲",
                    view_type="mobile_search",
                    module_key="music_search",
                )
            ],
        )
        with TemporaryDirectory() as temp_dir:
            pages = _build_page_specs(task, blueprint, Path(temp_dir), ui_blueprint)

        self.assertEqual(len(pages), 3)
        self.assertEqual(pages[1].page_kind, "operation")
        self.assertEqual(pages[1].module_key, "music_search")
        self.assertEqual(pages[1].key, "music_search_operation_2_2")
        self.assertEqual(pages[2].page_kind, "operation")
        self.assertEqual(pages[2].module_key, "music_search")
        self.assertTrue(pages[1].interaction_action)
        self.assertTrue(pages[2].interaction_action)

    def test_manual_toc_is_detected(self):
        from docx import Document

        blueprint = SimpleNamespace(modules=[SimpleNamespace(title="音乐搜索"), SimpleNamespace(title="歌曲播放")])
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "manual.docx"
            document = Document()
            _add_manual_toc(document, blueprint)
            document.save(path)
            result = analyze_manual_density(path)

        self.assertTrue(result["manual_toc_ready"])

    def test_manual_toc_uses_dot_leaders_and_real_page_numbers(self):
        from docx import Document

        blueprint = SimpleNamespace(modules=[SimpleNamespace(title="音乐搜索")])
        pages = [
            SimpleNamespace(extract_text=lambda: "封面"),
            SimpleNamespace(extract_text=lambda: "目录"),
            SimpleNamespace(extract_text=lambda: "一、软件概述"),
            SimpleNamespace(extract_text=lambda: "二、运行环境"),
            SimpleNamespace(extract_text=lambda: "三、登录与主界面"),
            SimpleNamespace(extract_text=lambda: "四、功能操作说明\n4.1 音乐搜索"),
            SimpleNamespace(extract_text=lambda: "五、统计分析"),
            SimpleNamespace(extract_text=lambda: "六、权限与安全"),
            SimpleNamespace(extract_text=lambda: "七、常见问题处理"),
        ]
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "manual.docx"
            document = Document()
            _add_manual_toc(document, blueprint)
            document.save(path)
            with patch("pypdf.PdfReader", return_value=SimpleNamespace(pages=pages)):
                result = update_manual_toc_page_numbers(path, Path(temp_dir) / "manual.pdf", blueprint)
            updated = Document(path)
            xml = updated.tables[0]._element.xml

        self.assertTrue(result["manual_toc_page_numbers_ready"])
        self.assertIn('w:leader="dot"', xml)
        self.assertIn("4.1 音乐搜索", xml)
        self.assertIn(">6<", xml)
        major = updated.tables[0].rows[0].cells[0].paragraphs[0]
        module = updated.tables[0].rows[4].cells[0].paragraphs[0]
        self.assertAlmostEqual(major.paragraph_format.line_spacing.pt, 20.0, places=1)
        self.assertAlmostEqual(major.paragraph_format.space_after.pt, 4.0, places=1)
        self.assertTrue(major.runs[0].bold)
        self.assertAlmostEqual(module.paragraph_format.left_indent.inches, 0.25, places=2)
        self.assertFalse(module.runs[0].bold)

    def test_action_label_is_replaced_with_inline_button_crop(self):
        from docx import Document
        from PIL import Image, ImageDraw

        with TemporaryDirectory() as temp_dir:
            crop = Path(temp_dir) / "detail.png"
            image = Image.new("RGB", (120, 36), "white")
            ImageDraw.Draw(image).rectangle((0, 0, 119, 35), fill="#d81b60")
            image.save(crop)
            screenshot = UiScreenshot(
                "music",
                "音乐搜索",
                "搜索",
                str(Path(temp_dir) / "music.html"),
                module_key="music",
                action_crops={"查看详情": str(crop)},
            )
            document = Document()
            paragraph = _add_manual_paragraph_with_action_images(
                document,
                "点击卡片底部的【查看详情】后，系统进入详情页。",
                {"music": screenshot},
                "music",
                "music",
            )

        self.assertEqual(len(document.inline_shapes), 1)
        self.assertNotIn("【查看详情】", paragraph.text)
        self.assertIn("点击卡片底部的", paragraph.text)
        self.assertAlmostEqual(paragraph.paragraph_format.line_spacing.pt, 19.0, places=1)

    def test_action_crop_prefers_current_operation_primary_button(self):
        with TemporaryDirectory() as temp_dir:
            main_crop = Path(temp_dir) / "main-add.png"
            operation_crop = Path(temp_dir) / "confirm-register.png"
            main_crop.write_bytes(b"main")
            operation_crop.write_bytes(b"operation")
            screenshots = {
                "music": UiScreenshot(
                    "music", "音乐", "主界面", "music.html", module_key="music", action_crops={"添加收藏": str(main_crop)}
                ),
                "music_operation": UiScreenshot(
                    "music_operation",
                    "音乐登记",
                    "二级界面",
                    "music_operation.html",
                    module_key="music",
                    action_crops={"确认登记并播放全部": str(operation_crop)},
                ),
            }

            result = _find_manual_action_crop(screenshots, "music", "添加", "music_operation")

        self.assertEqual(result, str(operation_crop))

    def test_manual_figure_keeps_image_caption_and_first_step_together(self):
        from docx import Document
        from PIL import Image

        with TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "screen.png"
            Image.new("RGB", (360, 720), "white").save(image_path)
            screenshot = UiScreenshot("screen", "界面", "说明", "screen.html", image_path=str(image_path))
            document = Document()
            _add_heading(document, "4.1 测试模块", level=2)
            _add_ui_figure(
                document,
                {"screen": screenshot},
                "screen",
                "测试界面",
                "用于验证分页组合。",
                ["用户进入页面后选择目标记录。", "系统显示对应处理结果。"],
            )
            docx_path = Path(temp_dir) / "layout-policy.docx"
            document.save(docx_path)
            density = analyze_manual_density(docx_path)

        heading = document.paragraphs[0]
        image_paragraph = next(paragraph for paragraph in document.paragraphs if "w:drawing" in paragraph._p.xml)
        caption = next(paragraph for paragraph in document.paragraphs if paragraph.text.startswith("图："))
        steps = [paragraph for paragraph in document.paragraphs if paragraph.text[:3] in {"1. ", "2. "}]
        first_step, second_step = steps[:2]
        self.assertTrue(heading.paragraph_format.keep_with_next)
        self.assertTrue(image_paragraph.paragraph_format.keep_with_next)
        self.assertTrue(caption.paragraph_format.keep_with_next)
        self.assertTrue(first_step.text.startswith("1. "))
        self.assertTrue(second_step.text.startswith("2. "))
        self.assertAlmostEqual(first_step.paragraph_format.left_indent.pt, 21.0, places=1)
        self.assertAlmostEqual(first_step.paragraph_format.first_line_indent.pt, -21.0, places=1)
        self.assertEqual(density["manual_layout_profile"], "global-adaptive-v1")
        self.assertTrue(density["manual_pagination_constraints_ready"])
        self.assertTrue(density["manual_numbered_steps_ready"])

    def test_global_layout_policy_covers_portrait_and_landscape_screenshots(self):
        from docx import Document
        from PIL import Image

        with TemporaryDirectory() as temp_dir:
            document = Document()
            screenshots = {}
            for key, size in (("portrait", (720, 1280)), ("landscape", (1280, 720))):
                image_path = Path(temp_dir) / f"{key}.png"
                Image.new("RGB", size, "white").save(image_path)
                screenshots[key] = UiScreenshot(key, key, key, f"{key}.html", image_path=str(image_path))
                _add_heading(document, f"4.1 {key}", level=2)
                _add_ui_figure(
                    document,
                    screenshots,
                    key,
                    f"{key}界面",
                    "用于验证全局排版策略。",
                    ["用户选择目标记录后继续操作。", "系统显示对应处理结果。"],
                )
            docx_path = Path(temp_dir) / "global-layout.docx"
            document.save(docx_path)
            density = analyze_manual_density(docx_path)

        self.assertEqual(density["manual_layout_profile"], "global-adaptive-v1")
        self.assertEqual(density["manual_figure_paragraph_count"], 2)
        self.assertEqual(density["manual_guarded_figure_count"], 2)
        self.assertEqual(density["manual_guarded_caption_count"], 2)
        self.assertTrue(density["manual_pagination_constraints_ready"])
        self.assertTrue(density["manual_numbered_steps_ready"])

    def test_operation_dialog_runtime_guards_center_overlays(self):
        for css in (_runtime_layout_guard_style("mobile_app"), _runtime_guard_style("mobile_app")):
            self.assertIn('body[data-renderer="mobile_app"][data-page-kind="operation"]', css)
            self.assertIn("top:50%!important", css)
            self.assertIn("left:50%!important", css)
            self.assertIn("bottom:auto!important", css)
            self.assertIn("width:calc(100vw - 32px)!important", css)

    def test_mobile_canvas_rejects_narrow_phone_mockups(self):
        self.assertFalse(
            _mobile_canvas_width_ready(
                {"width": 430, "left": 145, "right": 575, "viewportWidth": 720}
            )
        )
        self.assertTrue(
            _mobile_canvas_width_ready(
                {"width": 720, "left": 0, "right": 720, "viewportWidth": 720}
            )
        )

    def test_music_mobile_actions_are_natural_and_instant(self):
        expected = {
            "音乐搜索": "查看搜索结果",
            "歌曲播放": "播放歌曲",
            "歌词查看": "查看歌词",
            "歌单收藏": "收藏歌单",
            "歌手浏览": "查看歌手详情",
            "专辑浏览": "查看专辑详情",
            "播放队列": "调整播放顺序",
            "歌曲下载": "下载歌曲",
        }
        for title, action in expected.items():
            interaction = mobile_secondary_interaction(SimpleNamespace(title=title, description=title, pages=[]))
            self.assertEqual(interaction.action, action)
            self.assertFalse(interaction.requires_confirmation)
        playback = mobile_secondary_interaction(
            SimpleNamespace(title="歌曲播放", description="播放结束后可继续进入播放队列", pages=["播放详情页"])
        )
        self.assertEqual(playback.action, "播放歌曲")

    def test_instant_mobile_action_prompt_forbids_confirmation_flow(self):
        screenshot = SimpleNamespace(
            page_kind="operation",
            interaction_action="播放歌曲",
            interaction_surface="player",
            requires_confirmation=False,
        )
        prompt = _operation_prompt_rule(screenshot)

        self.assertIn("禁止确认弹窗", prompt)
        self.assertIn("确认登记", prompt)
        self.assertTrue(action_requires_confirmation("删除下载记录"))
        self.assertFalse(action_requires_confirmation("播放歌曲"))

    def test_mobile_instant_module_rejects_registration_copy(self):
        module = SimpleNamespace(title="歌曲播放", description="播放歌曲", pages=["播放详情页"])
        conflict = _module_paragraphs_conflict_with_ui(
            ["系统在歌曲播放登记时读取歌曲编号并等待用户确认。"],
            {"is_mobile": True, "action_labels": ["播放"], "filter_labels": []},
            module,
        )

        self.assertTrue(conflict)
        self.assertEqual(_instant_interaction_text_hits("播放后立即生效"), [])
        self.assertEqual(_instant_interaction_text_hits("确认播放并登记"), ["登记", "确认播放"])

    def test_old_mobile_blueprint_is_completed_for_all_modules(self):
        task = GenerationTask(software_name="测试音乐软件", product_type="APP", seed="seed")
        modules = [
            FeatureModule(
                key=f"module_{index}",
                title=f"模块{index}",
                description="业务功能",
                entities=["业务记录"],
                operations=["查看详情"],
                pages=["详情页"],
                data_fields=["编号", "状态"],
            )
            for index in range(3)
        ]
        blueprint = ProductBlueprint(
            software_name=task.software_name,
            version="V1.0",
            language="JavaScript",
            product_type="APP",
            industry="音乐服务",
            purpose="播放音乐",
            summary="移动音乐播放软件",
            modules=modules,
            roles=["用户"],
            pages=["首页"],
            dev_environment={"hardware": "PC", "os": "Windows", "tool": "VS Code"},
            runtime_environment={"hardware": "手机", "os": "Android", "support": "移动端"},
        )
        current = UiBlueprint(
            renderer="mobile_app",
            visual_style="mobile",
            screens=[UiScreenBlueprint("module_0", "模块0", "业务功能", "mobile_module", "module_0")],
        )

        completed = complete_ui_blueprint_coverage(task, blueprint, current)

        self.assertEqual({screen.module_key for screen in completed.screens if screen.module_key}, {"module_0", "module_1", "module_2"})


if __name__ == "__main__":
    unittest.main()
