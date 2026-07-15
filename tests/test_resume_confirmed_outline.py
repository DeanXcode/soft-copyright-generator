import json
from pathlib import Path
import sys
import tempfile
import unittest

BACKEND_ROOT = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from generate_materials import _confirmed_outline_from_resume_dir
from softcopyright.generator import _resume_failure_progress, _resume_failure_stage, _stage_precedes


class ResumeConfirmedOutlineTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
