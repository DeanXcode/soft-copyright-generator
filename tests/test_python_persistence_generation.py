from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from backend.softcopyright.blueprint import FeatureModule
from backend.softcopyright.models import GenerationTask
from backend.softcopyright.sourcegen import _generate_python_project


class PythonPersistenceGenerationTests(unittest.TestCase):
    def test_generated_project_persists_records_and_compiles(self) -> None:
        modules = [
            FeatureModule(
                "equipment_registry",
                "设备资产建档",
                "登记设备与关键部件",
                ["EquipmentRecord"],
                operations=["新增设备档案", "复核设备档案"],
                data_fields=["设备编号", "设备名称", "运行状态"],
            ),
            FeatureModule(
                "maintenance_plan",
                "维保计划编排",
                "编排检修任务",
                ["MaintenancePlan"],
                operations=["创建维保计划", "发布任务"],
                data_fields=["计划编号", "负责人", "计划状态"],
            ),
        ]
        blueprint = SimpleNamespace(modules=modules)
        task = GenerationTask(software_name="Persistence Acceptance", language="Python")
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _generate_python_project(task, blueprint, root, include_readme=False)

            repository = (root / "app/repositories/equipment_registry_repository.py").read_text(encoding="utf-8")
            service = (root / "app/services/equipment_registry_service.py").read_text(encoding="utf-8")
            self.assertIn("INSERT INTO equipment_registry_record", repository)
            self.assertIn("EquipmentRegistryRepository", service)
            self.assertTrue((root / "migrations/001_initial.sql").exists())

            python_files = [str(path) for path in root.rglob("*.py")]
            compiled = subprocess.run(
                [sys.executable, "-m", "py_compile", *python_files],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(compiled.returncode, 0, compiled.stderr)

            tested = subprocess.run(
                [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(tested.returncode, 0, tested.stderr)
            self.assertIn("test_record_survives_repository_reopen", tested.stderr)


if __name__ == "__main__":
    unittest.main()
