from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from docx import Document
from docx.oxml.ns import qn

from backend.softcopyright.docgen import (
    _fit_source_line_to_page_width,
    _select_source_material_pages,
    _source_material_quality,
    _source_indent_width_pt,
    _source_line_indent,
)
from backend.softcopyright.blueprint import FeatureModule
from backend.softcopyright.models import GenerationTask
from backend.softcopyright.sourcegen import _write_generic_workflow_shards


class SourceMaterialPaginationTests(unittest.TestCase):
    def test_more_than_sixty_pages_selects_first_and_last_thirty(self) -> None:
        entries = [{"text": f"line-{index:04d}", "file": "service.py"} for index in range(7101)]

        pages, total_pages, mode, quality = _select_source_material_pages(entries, 50)

        self.assertEqual(total_pages, 143)
        self.assertEqual(len(pages), 60)
        self.assertTrue(all(len(page) == 50 for page in pages))
        self.assertEqual(mode, "first_30_last_30_continuous")
        self.assertEqual(pages[0][0]["text"], "line-0000")
        self.assertEqual(pages[29][-1]["text"], "line-1499")
        self.assertEqual(pages[30][0]["text"], "line-5601")
        self.assertEqual(pages[-1][-1]["text"], "line-7100")
        self.assertTrue(quality["source_continuous_selection"])

    def test_long_source_line_is_condensed_instead_of_wrapping(self) -> None:
        document = Document()
        run = document.add_paragraph().add_run("const result = " + "businessValue + " * 20)

        scale = _fit_source_line_to_page_width(run, run.text, 9)

        self.assertLess(scale, 100)
        width = run._r.get_or_add_rPr().find(qn("w:w"))
        self.assertIsNotNone(width)
        self.assertEqual(int(width.get(qn("w:val"))), scale)

    def test_source_indent_becomes_stable_paragraph_indent(self) -> None:
        columns, content = _source_line_indent("\t    return service.save(record)")

        self.assertEqual(columns, 8)
        self.assertEqual(content, "return service.save(record)")
        self.assertEqual(_source_indent_width_pt(columns), 37.6)

    def test_python_line_target_is_split_across_module_shards(self) -> None:
        modules = [
            FeatureModule(f"module_{index}", f"业务模块{index}", "业务处理", ["BusinessRecord"], operations=["登记", "审核"])
            for index in range(8)
        ]
        blueprint = SimpleNamespace(modules=modules)
        task = GenerationTask(software_name="Source Diversity Test", language="Python")
        with TemporaryDirectory() as temp_dir:
            paths = _write_generic_workflow_shards(
                target_dir=Path(temp_dir),
                task=task,
                blueprint=blueprint,
                missing_lines=2700,
                extension=".py",
            )

            line_counts = [len(path.read_text(encoding="utf-8").splitlines()) for path in paths]
            self.assertGreaterEqual(len(paths), 8)
            self.assertEqual(len({path.name for path in paths}), len(paths))
            self.assertLessEqual(max(line_counts), 420)
            self.assertTrue(all("WorkflowOrchestrator" in path.read_text(encoding="utf-8") for path in paths))

    def test_material_diversity_rejects_single_file_dominance(self) -> None:
        dominated = [{"file": "huge_service.py", "text": f"value = {index % 10}"} for index in range(3000)]
        diversified = [
            {"file": f"module_{index // 375}.py", "text": f"module_{index // 375}_value_{index}"}
            for index in range(3000)
        ]

        self.assertFalse(_source_material_quality(dominated, dominated)["source_material_diversity_ready"])
        self.assertTrue(_source_material_quality(diversified, diversified)["source_material_diversity_ready"])


if __name__ == "__main__":
    unittest.main()
