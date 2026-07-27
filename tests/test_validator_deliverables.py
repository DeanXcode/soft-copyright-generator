from pathlib import Path
import unittest

from backend.softcopyright.models import GenerationTask
from backend.softcopyright.validator import _deliverable_kind, _find_deliverable


class ValidatorDeliverableTests(unittest.TestCase):
    def test_slugged_english_name_is_recognized_as_manual_material(self):
        task = GenerationTask(software_name="PageSpec Zero Token Acceptance System")

        self.assertEqual(
            _deliverable_kind(task, Path("PageSpec-Zero-Token-Acceptance-System.docx")),
            "manual_docx",
        )
        self.assertEqual(
            _deliverable_kind(task, Path("PageSpec-Zero-Token-Acceptance-System.pdf")),
            "manual_pdf",
        )

    def test_slugged_english_name_finds_manual_docx_and_info_text(self):
        task = GenerationTask(software_name="PageSpec Zero Token Acceptance System")
        files = [
            Path("PageSpec-Zero-Token-Acceptance-System.docx"),
            Path("PageSpec-Zero-Token-Acceptance-System.txt"),
            Path("PageSpec-Zero-Token-Acceptance-System_代码-(Java).docx"),
        ]

        self.assertEqual(
            _find_deliverable(files, task.safe_name, ".docx", source=False),
            files[0],
        )
        self.assertEqual(
            _find_deliverable(files, task.safe_name, ".txt", source=False),
            files[1],
        )


if __name__ == "__main__":
    unittest.main()
