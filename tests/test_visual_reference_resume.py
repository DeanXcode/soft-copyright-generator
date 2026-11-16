import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from PIL import Image, ImageDraw

from backend.softcopyright import ai_frontend_codegen as impl
from backend.softcopyright.llm.provider import LLMConfig
from backend.softcopyright.models import GenerationTask


class _Provider:
    config = LLMConfig(provider="custom", image_model="test-image")

    def __init__(self):
        self.chat_calls = 0
        self.image_calls = 0

    def chat(self, *args, **kwargs):
        self.chat_calls += 1
        return json.dumps({
            "visual_prompt": "单张软件运行界面截图：学习进度工作台。" + "左侧课程导航，中间学习记录表格，右侧进度统计面板。" * 12,
            "layout_brief": "课程与进度并列展示",
            "visual_tokens": ["课程表格", "进度统计"],
        }, ensure_ascii=False)

    def generate_image(self, *, output_path, **kwargs):
        self.image_calls += 1
        if self.image_calls == 1:
            raise RuntimeError("524 upstream timeout")
        image = Image.new("RGB", (1280, 720), "white")
        draw = ImageDraw.Draw(image)
        for row in range(20, 720, 30):
            draw.rectangle((20, row, 1240, row + 15), fill=(row % 255, 80, 120))
        image.save(output_path)
        return {"model": "test-image", "size": "1280x720", "attempts": 1, "elapsed_seconds": 3}


class VisualReferenceResumeTests(unittest.TestCase):
    def test_image_failure_keeps_prompt_and_resume_reuses_it_without_another_chat(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            provider = _Provider()
            args = dict(
                task=GenerationTask(software_name="学习进度软件", product_type="教育软件", seed="resume-a"),
                blueprint=SimpleNamespace(business_objects=["课程"], report_metrics=["完成数量"]),
                ui_blueprint=SimpleNamespace(renderer="admin", design_brief={}),
                screenshots=[SimpleNamespace(key="dashboard", title="学习工作台", page_kind="dashboard", module_key="", html_path=str(root / "ui-prototype/dashboard.html"))],
                module_by_key={}, provider=provider, context={}, design_brief={}, emit=None, require_llm=True,
            )
            with self.assertRaisesRegex(RuntimeError, "524"):
                impl._generate_visual_reference_assets(**args)
            self.assertTrue((root / "ui-prototype/visual-references/style_reference.prompt.json").is_file())
            report = impl._generate_visual_reference_assets(**args)
            self.assertTrue(report["ready"])
            self.assertEqual(provider.chat_calls, 1)
            self.assertEqual(provider.image_calls, 2)
            self.assertEqual(report["style_reference"]["image_request_attempts"], 1)
            self.assertEqual(report["style_reference"]["image_request_elapsed_seconds"], 3)

    def test_prompt_reuse_rejects_wrong_identity_size_page_and_corrupt_payload(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "prompt.json"
            valid = {"cache_key": "identity-a", "mode": "style_reference", "reference_page_key": "dashboard", "image_size": "1280x720", "prompt": json.loads(_Provider().chat())}
            def load(payload):
                path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
                return impl._load_reusable_visual_prompt(path, cache_key="identity-a", reference_page_key="dashboard", image_size="1280x720")
            self.assertIsNotNone(load(valid))
            for field, value in [("cache_key", "identity-b"), ("mode", "other"), ("reference_page_key", "login"), ("image_size", "720x1280")]:
                with self.subTest(field=field):
                    self.assertIsNone(load({**valid, field: value}))
            for bad_prompt in [None, {}, {"visual_prompt": "short"}, {"visual_prompt": "x" * 200, "visual_tokens": [42]}, {"visual_prompt": "x" * 200, "visual_tokens": "list expected"}, {"visual_prompt": "?" * 200}]:
                with self.subTest(prompt=bad_prompt):
                    self.assertIsNone(load({**valid, "prompt": bad_prompt}))
            path.write_text("{corrupt", encoding="utf-8")
            self.assertIsNone(impl._load_reusable_visual_prompt(path, cache_key="identity-a", reference_page_key="dashboard", image_size="1280x720"))


if __name__ == "__main__":
    unittest.main()
