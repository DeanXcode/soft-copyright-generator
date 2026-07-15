from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

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


if __name__ == "__main__":
    unittest.main()
