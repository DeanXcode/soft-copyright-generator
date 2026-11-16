from copy import deepcopy
from functools import partial
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from unittest.mock import patch

from PIL import Image

from backend.softcopyright.ai_frontend_codegen import generate_ai_frontend_pages, _image_data_url
from backend.softcopyright.blueprint import FeatureModule, ProductBlueprint
from backend.softcopyright.frontend_codegen.reference_style import (
    REFERENCE_STYLE_VERSION, normalize_component_style, resolve_reference_style,
)
from backend.softcopyright.models import GenerationTask
from backend.softcopyright.screenshot_checkpoint import screenshot_input_fingerprint
from backend.softcopyright.screenshots import UiScreenshot
from backend.softcopyright.ui_blueprint import UiBlueprint
from tests.http_test_utils import create_safe_threading_http_server
from tests.test_react_frontend_codegen import _QuietHandler, _ReactProvider


def style_data():
    return {
        "schema_version": REFERENCE_STYLE_VERSION,
        "colors": {"accent": "#be123c", "text": "#172033", "canvas": "#fff7f8",
                   "surface": "#ffffff", "border": "#e7d5d9", "navigation": "#fff7f8",
                   "navigation_text": "#172033"},
        "card_radius": 4, "control_radius": 3, "density": "compact", "shadow": "flat",
    }


class StyleProvider(_ReactProvider):
    def __init__(self, *, failure=False):
        super().__init__()
        self.vision_calls = []
        self.style = style_data()
        self.failure = failure

    def chat(self, messages, **kwargs):
        if kwargs.get("trace_label") == "reference_component_style":
            self.vision_calls.append((messages, kwargs))
            if self.failure:
                raise TimeoutError("vision unavailable")
            return json.dumps(self.style)
        return super().chat(messages, **kwargs)


class ReferenceComponentStyleTests(unittest.TestCase):
    def test_only_bounded_tokens_reach_css_and_low_contrast_is_corrected(self):
        raw = style_data()
        raw["css"] = "body{display:none}"
        normalized = normalize_component_style(raw)
        self.assertNotIn("css", normalized)
        for field, value in (("card_radius", 100), ("control_radius", True),
                             ("density", "url(bad)"), ("shadow", "<script>")):
            with self.subTest(field=field):
                bad = deepcopy(raw)
                bad[field] = value
                with self.assertRaises(ValueError):
                    normalize_component_style(bad)
        raw["colors"]["accent"] = "#fff;display:none"
        with self.assertRaises(ValueError):
            normalize_component_style(raw)
        raw = style_data()
        raw["colors"].update(canvas="#000000", surface="#111111", text="#ffffff",
                             accent="#eeeeee", navigation="#ffffff", navigation_text="#ffffff")
        normalized = normalize_component_style(raw)
        self.assertEqual(normalized["colors"]["text"], "#172033")
        self.assertEqual(normalized["colors"]["navigation_text"], "#172033")
        self.assertEqual(normalized["colors"]["surface"], "#ffffff")

    def test_image_hash_controls_reuse_and_invalid_cache_is_replaced(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            image = root / "reference.png"
            Image.new("RGB", (128, 72), "red").save(image)
            reference = {"ready": True, "image_path": str(image), "image_sha256": "stale-report-hash"}
            provider = StyleProvider()
            kwargs = dict(provider=provider, reference=reference, base_contract={"ready": True},
                          cache_path=root / "style.json", image_data_url=_image_data_url)
            first = resolve_reference_style(**kwargs)
            second = resolve_reference_style(**kwargs)
            self.assertEqual(first["component_style_status"], "extracted")
            self.assertTrue(second["component_style_reused"])
            self.assertEqual(len(provider.vision_calls), 1)
            messages, options = provider.vision_calls[0]
            self.assertEqual(options["retry_policy"].max_retries, 0)
            self.assertTrue(messages[-1]["content"][1]["image_url"]["url"].startswith("data:image/"))
            Image.new("RGB", (128, 72), "blue").save(image)
            third = resolve_reference_style(**kwargs)
            self.assertNotEqual(first["component_style_image_sha256"], third["component_style_image_sha256"])
            self.assertEqual(len(provider.vision_calls), 2)
            (root / "style.json").write_text("[]", encoding="utf-8")
            resolve_reference_style(**kwargs)
            self.assertEqual(len(provider.vision_calls), 3)

    def test_optional_failure_is_cached_without_stopping_generation(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            image = root / "reference.png"
            Image.new("RGB", (128, 72), "red").save(image)
            provider = StyleProvider(failure=True)
            kwargs = dict(provider=provider, reference={"ready": True, "image_path": str(image)},
                          base_contract={"dominant_colors": ["#be123c"]}, cache_path=root / "style.json",
                          image_data_url=_image_data_url)
            for _ in range(2):
                contract = resolve_reference_style(**kwargs)
                self.assertEqual(contract["component_style_status"], "fallback")
                self.assertNotIn("component_style", contract)
                self.assertEqual(contract["dominant_colors"], ["#be123c"])
            self.assertEqual(len(provider.vision_calls), 1)
            # No reference: no API request and no accidental directory reads.
            kwargs["reference"] = {"ready": True}
            self.assertEqual(resolve_reference_style(**kwargs)["component_style_status"], "no-reference-image")
            self.assertEqual(len(provider.vision_calls), 1)

    def test_all_pages_share_image_style_and_restyle_cached_specs_without_page_requests(self):
        with TemporaryDirectory(dir="tmp") as temporary, patch.dict("os.environ", {"SOFT_AI_FRONTEND_MODE": "react-vite"}):
            root = Path(temporary)
            image = root / "reference.png"
            Image.new("RGB", (128, 72), "red").save(image)
            task = GenerationTask(software_name="设备巡检平台", product_type="管理软件", seed="reference-style")
            module = FeatureModule(key="tasks", title="巡检任务", description="巡检任务查询与分派",
                                   entities=["InspectionTask"], operations=["查询"], data_fields=["任务编号", "责任班组"])
            blueprint = ProductBlueprint(software_name=task.software_name, version=task.version,
                language="JavaScript", product_type=task.product_type, industry="设备巡检", purpose="巡检任务协同",
                summary="设备巡检任务协同", modules=[module], roles=["巡检主管"], pages=["巡检总览", "巡检任务"],
                dev_environment={}, runtime_environment={}, report_metrics=["今日任务"])
            ui = UiBlueprint(renderer="admin", visual_style="巡检工作台", source="llm", screens=[],
                             design_brief={"visual_identity_spec": {"nav_model": "side_menu"}})
            screens = [UiScreenshot("dashboard", "巡检总览", "总览", str(root / "dashboard.html"), page_kind="dashboard"),
                       UiScreenshot("tasks", "巡检任务", "任务", str(root / "tasks.html"), page_kind="module", module_key="tasks")]
            provider = StyleProvider()
            kwargs = dict(task=task, blueprint=blueprint, ui_blueprint=ui, screenshots=screens, provider=provider,
                          require_llm=True, visual_reference_report={"ready": True,
                              "style_reference": {"ready": True, "image_path": str(image)}})
            report = generate_ai_frontend_pages(**kwargs)
            self.assertTrue(report["ready"])
            self.assertTrue(report["reference_component_style"]["applied"])
            self.assertEqual(len(provider.vision_calls), 1)
            page_requests = len(provider.messages)
            self.assertEqual(page_requests, 2)
            self.assertTrue(all(isinstance(message[-1]["content"], str) for message in provider.messages))
            fingerprint = screenshot_input_fingerprint(screens[0], "admin", {"width": 1280, "height": 720})
            resumed = generate_ai_frontend_pages(**kwargs)
            self.assertTrue(resumed["reference_component_style"]["reused"])
            self.assertEqual(len(provider.messages), page_requests)
            self.assertEqual(len(provider.vision_calls), 1)
            # A new image restyles cached PageSpecs locally, including screenshot invalidation.
            Image.new("RGB", (128, 72), "blue").save(image)
            provider.style["card_radius"] = 6
            generate_ai_frontend_pages(**kwargs)
            self.assertEqual(len(provider.messages), page_requests)
            self.assertEqual(len(provider.vision_calls), 2)
            self.assertNotEqual(fingerprint, screenshot_input_fingerprint(screens[0], "admin", {"width": 1280, "height": 720}))
            server = create_safe_threading_http_server("127.0.0.1", partial(_QuietHandler, directory=str(root)))
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                from playwright.sync_api import sync_playwright
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(headless=True)
                    page = browser.new_page(viewport={"width": 1280, "height": 720})
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    for screen in screens:
                        page.goto(f"http://127.0.0.1:{server.server_port}/{Path(screen.html_path).name}", wait_until="networkidle")
                        actual = page.locator(".page-region").first.evaluate("e => {const s=getComputedStyle(e);return [s.borderRadius,s.boxShadow,s.padding]}")
                        self.assertEqual(actual, ["6px", "none", "12px"])
                        self.assertEqual(page.locator("input").first.evaluate("e=>getComputedStyle(e).borderRadius"), "3px")
                        self.assertEqual(page.locator(".shared-app-sidebar").evaluate("e=>getComputedStyle(e).backgroundColor"), "rgb(255, 247, 248)")
                        self.assertEqual(page.locator(".shared-app-sidebar .shared-app-nav span:not(.active)").first.evaluate("e=>getComputedStyle(e).color"), "rgb(23, 32, 51)")
                    self.assertEqual(errors, [])
                    browser.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
