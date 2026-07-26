from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from PIL import Image, ImageDraw

from backend.softcopyright.ui_similarity import _package_page_similarity


HTML = """<!doctype html><html><body><main class="workspace"><section class="query-grid"><table class="table-frame"></table></section></main></body></html>"""


class UiPackageSimilarityTests(unittest.TestCase):
    def test_same_operation_component_may_be_reused_across_modules(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            screenshots = {}
            for index in range(4):
                path = root / f"query-{index}.html"
                path.write_text(HTML, encoding="utf-8")
                screenshots[str(index)] = SimpleNamespace(
                    html_path=str(path),
                    page_kind="operation",
                    interaction_mode="query",
                    interaction_surface="query_results",
                )

            score, reason = _package_page_similarity(screenshots)

        self.assertEqual(reason, "")
        self.assertEqual(score, 0.0)

    def test_identical_primary_module_pages_still_fail_similarity_gate(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            screenshots = {}
            for index in range(4):
                path = root / f"module-{index}.html"
                path.write_text(HTML, encoding="utf-8")
                screenshots[str(index)] = SimpleNamespace(
                    html_path=str(path),
                    page_kind="module",
                    interaction_mode="",
                    interaction_surface="",
                )

            score, reason = _package_page_similarity(screenshots)

        self.assertEqual(reason, "ui_package_pages_too_similar")
        self.assertGreaterEqual(score, 0.86)

    def test_near_identical_operation_screenshots_fail_even_for_shared_surface(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            screenshots = {}
            for index in range(4):
                path = root / f"operation-{index}.html"
                image_path = root / f"operation-{index}.png"
                path.write_text(HTML, encoding="utf-8")
                image = Image.new("RGB", (640, 360), "white")
                draw = ImageDraw.Draw(image)
                draw.rectangle((80, 45, 560, 315), fill="#f4f6f8", outline="#9aa6b2")
                draw.rectangle((110, 80, 500, 104), fill="#334155")
                draw.rectangle((110, 132, 520, 270), fill="#dbe3ea")
                draw.rectangle((450, 282, 520, 304), fill="#ea580c")
                draw.rectangle((112 + index, 282, 180 + index, 304), fill="#cbd5e1")
                image.save(image_path)
                screenshots[str(index)] = SimpleNamespace(
                    html_path=str(path),
                    image_path=str(image_path),
                    page_kind="operation",
                    interaction_mode="detail",
                    interaction_surface="detail_timeline",
                    requires_confirmation=False,
                )

            score, reason = _package_page_similarity(screenshots)

        self.assertEqual(reason, "ui_package_pages_too_similar")
        self.assertGreaterEqual(score, 0.97)

    def test_shared_confirmation_dialogs_are_not_treated_as_duplicate_pages(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            screenshots = {}
            for index in range(4):
                path = root / f"confirmation-{index}.html"
                image_path = root / f"confirmation-{index}.png"
                path.write_text(HTML, encoding="utf-8")
                image = Image.new("RGB", (640, 360), "white")
                draw = ImageDraw.Draw(image)
                draw.rectangle((80, 45, 560, 315), fill="#f4f6f8", outline="#9aa6b2")
                draw.rectangle((110, 80, 500, 104), fill="#334155")
                draw.rectangle((110, 132, 520, 270), fill="#dbe3ea")
                draw.text((120, 150), f"confirmation business result {index}", fill="#0f172a")
                draw.rectangle((450, 282, 520, 304), fill="#ea580c")
                image.save(image_path)
                screenshots[str(index)] = SimpleNamespace(
                    html_path=str(path),
                    image_path=str(image_path),
                    page_kind="operation",
                    interaction_mode="workflow",
                    interaction_surface="result_confirmation",
                    requires_confirmation=True,
                )

            score, reason = _package_page_similarity(screenshots)

        self.assertEqual(reason, "")
        self.assertEqual(score, 0.0)


if __name__ == "__main__":
    unittest.main()
