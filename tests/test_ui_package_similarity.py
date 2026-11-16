import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from PIL import Image, ImageDraw

from backend.softcopyright.ui_similarity import _package_page_similarity


HTML = """<!doctype html><html><body><main class="workspace"><section class="query-grid"><table class="table-frame"></table></section></main></body></html>"""


def _write_page_spec_screen(
    root: Path,
    *,
    key: str,
    page_kind: str,
    layout: str,
    components: list[str],
    action_variants: list[str],
) -> Path:
    html_path = root / f"{key}.html"
    html_path.write_text(
        f'<!doctype html><html><head><meta name="soft-react-screen" content="{key}"></head><body></body></html>',
        encoding="utf-8",
    )
    screens_dir = root / "react-app" / "src" / "screens"
    screens_dir.mkdir(parents=True, exist_ok=True)
    stem = "".join(part.title() for part in key.split("_"))
    (screens_dir / f"{stem}.meta.json").write_text(
        json.dumps({"page_key": key, "engine": "page-spec-v1"}),
        encoding="utf-8",
    )
    (screens_dir / f"{stem}.page-spec.json").write_text(
        json.dumps(
            {
                "schema_version": "page-spec-v1",
                "page_key": key,
                "page_kind": page_kind,
                "layout": layout,
                "regions": [
                    {"id": f"region_{index}", "component": component}
                    for index, component in enumerate(components)
                ],
                "actions": [
                    {"id": f"action_{index}", "variant": variant}
                    for index, variant in enumerate(action_variants)
                ],
                "interaction_contract": {},
            }
        ),
        encoding="utf-8",
    )
    return html_path


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

    def test_pagespec_uses_layout_and_region_order_instead_of_shared_component_css(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            left_path = _write_page_spec_screen(
                root,
                key="publish_validation",
                page_kind="operation",
                layout="result_confirmation",
                components=["metric_group", "detail", "data_table", "workflow", "form", "operation_result"],
                action_variants=["danger"],
            )
            right_path = _write_page_spec_screen(
                root,
                key="execute_recognition",
                page_kind="operation",
                layout="result_confirmation",
                components=["detail", "form", "metric_group", "workflow", "operation_result", "data_table"],
                action_variants=["primary"],
            )
            screenshots = {
                "left": SimpleNamespace(
                    html_path=str(left_path),
                    page_kind="operation",
                    interaction_mode="query",
                    interaction_surface="query_results",
                    requires_confirmation=True,
                ),
                "right": SimpleNamespace(
                    html_path=str(right_path),
                    page_kind="operation",
                    interaction_mode="workflow",
                    interaction_surface="workflow_result",
                    requires_confirmation=False,
                ),
                "module-a": SimpleNamespace(html_path=str(left_path), page_kind="general"),
                "module-b": SimpleNamespace(html_path=str(right_path), page_kind="general"),
            }

            score, reason = _package_page_similarity(screenshots)

        self.assertEqual(reason, "")
        self.assertLess(score, 0.86)

    def test_identical_pagespec_primary_module_pages_still_fail(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            screenshots = {}
            for index in range(4):
                path = _write_page_spec_screen(
                    root,
                    key=f"module_{index}",
                    page_kind="module",
                    layout="table_workspace",
                    components=["filter_bar", "metric_group", "data_table", "detail"],
                    action_variants=["primary"],
                )
                screenshots[str(index)] = SimpleNamespace(
                    html_path=str(path),
                    page_kind="module",
                    interaction_mode="",
                    interaction_surface="",
                    requires_confirmation=False,
                )

            score, reason = _package_page_similarity(screenshots)

        self.assertEqual(reason, "ui_package_pages_too_similar")
        self.assertGreaterEqual(score, 0.86)


if __name__ == "__main__":
    unittest.main()
