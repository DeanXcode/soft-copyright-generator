import json
from pathlib import Path
import sys
import tempfile
import unittest

BACKEND_ROOT = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from generate_materials import _confirmed_outline_from_resume_dir, _seed_from_output_dir
from softcopyright.generator import (
    _delivery_zip_path,
    _load_completed_resume_report,
    _resume_failure_progress,
    _resume_failure_stage,
    _resume_blueprint_lock_ready,
    _should_defer_pre_render_similarity_for_resume,
    _stage_precedes,
)


class ResumeConfirmedOutlineTests(unittest.TestCase):
    def test_completed_resume_returns_existing_material_package(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "测试系统-existing"
            output_dir.mkdir()
            deliverable = output_dir / "测试系统软件说明书.docx"
            deliverable.write_bytes(b"docx")
            zip_path = output_dir.parent / f"{output_dir.name}--材料包.zip"
            zip_path.write_bytes(b"zip")
            (output_dir / "generation-state.json").write_text(
                json.dumps(
                    {
                        "status": "success",
                        "stage": "done",
                        "extra": {"zip_path": str(zip_path)},
                    }
                ),
                encoding="utf-8",
            )
            (output_dir / "generation_report.json").write_text(
                json.dumps(
                    {
                        "task": {"output_dir": str(output_dir)},
                        "zip_path": str(zip_path),
                        "files": [str(deliverable)],
                        "checks": {},
                        "warnings": [],
                    }
                ),
                encoding="utf-8",
            )

            report = _load_completed_resume_report(output_dir)

            self.assertIsNotNone(report)
            self.assertEqual(report["zip_path"], str(zip_path))
            self.assertEqual(report["files"], [str(deliverable)])
            self.assertTrue(report["checks"]["completed_resume_reused"])

    def test_success_state_without_material_package_is_not_reused(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "测试系统-missing-package"
            output_dir.mkdir()
            (output_dir / "generation-state.json").write_text(
                json.dumps({"status": "success", "stage": "done"}),
                encoding="utf-8",
            )
            (output_dir / "generation_report.json").write_text(
                json.dumps({"zip_path": "", "files": []}),
                encoding="utf-8",
            )

            self.assertIsNone(_load_completed_resume_report(output_dir))
            self.assertEqual(_resume_failure_stage(output_dir), "")

    def test_delivery_zip_uses_actual_resume_output_directory_name(self):
        output_dir = Path("output") / "测试系统-dialog-theme-v4"

        self.assertEqual(
            _delivery_zip_path(output_dir),
            Path("output") / "测试系统-dialog-theme-v4--材料包.zip",
        )

    def test_recovers_custom_seed_from_generation_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "测试系统-custom-seed-v3"
            root.mkdir()
            (root / "generation-state.json").write_text(
                json.dumps({"task": {"seed": "custom-seed-v3"}}),
                encoding="utf-8",
            )

            self.assertEqual(_seed_from_output_dir(str(root)), "custom-seed-v3")

    def test_falls_back_to_timestamp_seed_in_output_name(self):
        output_dir = Path("测试系统-20260721-020304-1234")

        self.assertEqual(_seed_from_output_dir(str(output_dir)), "20260721-020304-1234")

    def test_loads_confirmed_outline_from_generation_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            expected = {"softwareName": "Test", "modules": [{"title": "Module"}]}
            (root / "generation_report.json").write_text(
                json.dumps({"task": {"confirmed_outline": expected}}),
                encoding="utf-8",
            )

            self.assertEqual(_confirmed_outline_from_resume_dir(root), expected)

    def test_ignores_empty_or_invalid_outline(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "generation_report.json").write_text(
                json.dumps({"task": {"confirmed_outline": {"modules": []}}}),
                encoding="utf-8",
            )

            self.assertEqual(_confirmed_outline_from_resume_dir(root), {})

    def test_recovers_outline_from_generated_product_blueprint(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            blueprint_dir = root / "generated_source"
            blueprint_dir.mkdir(parents=True)
            expected = {
                "software_name": "Test",
                "modules": [
                    {"key": f"module_{index}", "title": f"Module {index}", "description": "完整业务模块说明"}
                    for index in range(1, 7)
                ],
            }
            (blueprint_dir / "product-blueprint.json").write_text(
                json.dumps(expected),
                encoding="utf-8",
            )

            self.assertEqual(_confirmed_outline_from_resume_dir(root), expected)

    def test_resume_checkpoint_starts_at_failed_stage(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "generation-failure.json").write_text(
                json.dumps({"stage": "screenshots", "progress": 50}),
                encoding="utf-8",
            )

            self.assertEqual(_resume_failure_stage(root), "screenshots")
            self.assertEqual(_resume_failure_progress(root), 50)
            self.assertTrue(_stage_precedes("source", "screenshots"))
            self.assertFalse(_stage_precedes("screenshots", "screenshots"))
            self.assertFalse(_stage_precedes("manual", "screenshots"))

    def test_late_stage_resume_locks_the_exact_generated_blueprint(self):
        resume_blueprint = object()

        self.assertTrue(_resume_blueprint_lock_ready(resume_blueprint, resume_blueprint, "screenshots"))
        self.assertTrue(_resume_blueprint_lock_ready(resume_blueprint, resume_blueprint, "done"))
        self.assertFalse(_resume_blueprint_lock_ready(resume_blueprint, object(), "screenshots"))
        self.assertFalse(_resume_blueprint_lock_ready(resume_blueprint, resume_blueprint, "blueprint"))

    def test_screenshot_resume_defers_only_pre_render_similarity_with_ready_image2_reference(self):
        ui_blueprint = object()
        reference = {"ready": True, "source": "gpt-style-reference-prompt+image2"}

        self.assertTrue(
            _should_defer_pre_render_similarity_for_resume(
                resume_stage="screenshots",
                resume_ui_blueprint=ui_blueprint,
                attempt_cached=ui_blueprint,
                visual_reference_report=reference,
            )
        )
        self.assertTrue(
            _should_defer_pre_render_similarity_for_resume(
                resume_stage="done",
                resume_ui_blueprint=ui_blueprint,
                attempt_cached=ui_blueprint,
                visual_reference_report=reference,
            )
        )
        self.assertFalse(
            _should_defer_pre_render_similarity_for_resume(
                resume_stage="visual_reference",
                resume_ui_blueprint=ui_blueprint,
                attempt_cached=ui_blueprint,
                visual_reference_report=reference,
            )
        )
        self.assertFalse(
            _should_defer_pre_render_similarity_for_resume(
                resume_stage="screenshots",
                resume_ui_blueprint=ui_blueprint,
                attempt_cached=ui_blueprint,
                visual_reference_report={"ready": False, "source": "gpt-style-reference-prompt+image2"},
            )
        )


if __name__ == "__main__":
    unittest.main()
