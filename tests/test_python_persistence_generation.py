from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from backend.softcopyright.blueprint import FeatureModule
from backend.softcopyright.models import GenerationTask
from backend.softcopyright.sourcegen import (
    _generate_python_project,
    _javascript_seed_records,
    repair_generated_business_record_labels,
    repair_generated_domain_sample_leaks,
)


class PythonPersistenceGenerationTests(unittest.TestCase):
    def test_non_transport_javascript_seeds_do_not_contain_transport_route_samples(self) -> None:
        module = FeatureModule(
            "access",
            "门禁通行授权",
            "维护社区住户的门禁范围和通行时段",
            ["AccessAuthorization"],
            operations=["筛选授权", "配置授权草案", "复核授权范围"],
            data_fields=["授权编号", "授权范围", "授权状态"],
        )

        records = _javascript_seed_records(module, "access")
        encoded = str(records)

        self.assertNotIn("沪杭枢纽", encoded)
        self.assertNotIn("浦东东区至临港片区", encoded)
        self.assertEqual(records[0]["serviceScope"], "门禁通行授权服务区域1")
        self.assertIn("筛选授权", records[0]["nodeSequence"])
        self.assertEqual(records[0]["direction"], "受理方向")

    def test_resume_domain_sample_migration_repairs_cached_non_transport_service(self) -> None:
        module = FeatureModule(
            "access",
            "门禁通行授权",
            "维护社区住户的门禁范围和通行时段",
            ["AccessAuthorization"],
            operations=["筛选授权", "配置授权草案", "复核授权范围"],
            data_fields=["授权编号", "授权范围", "授权状态"],
        )
        blueprint = SimpleNamespace(
            industry="社区及楼宇门禁通行管理",
            summary="管理住户、访客、凭证和门禁点",
            scenario="社区门禁",
            positioning="物业门禁工作台",
            business_objects=["住户", "门禁凭证"],
            industry_subtype_key="",
            modules=[module],
        )
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service_dir = root / "src" / "services"
            service_dir.mkdir(parents=True)
            source = service_dir / "accessService.js"
            source.write_text(
                '"nodeSequence": "沪杭枢纽-浦东东区-临港接驳点",\n'
                '"direction": "北向",\n'
                '"serviceScope": "浦东东区至临港片区",\n'
                'description: payload.description || "门禁通行授权-筛选授权-浦东东区至临港片区-建档",',
                encoding="utf-8",
            )

            changed = repair_generated_domain_sample_leaks(root, blueprint)
            migrated = source.read_text(encoding="utf-8")

        self.assertEqual(changed, 4)
        self.assertNotIn("沪杭枢纽", migrated)
        self.assertNotIn("北向", migrated)
        self.assertNotIn("浦东东区至临港片区", migrated)
        self.assertIn("筛选授权-配置授权草案-复核授权范围", migrated)
        self.assertIn("门禁通行授权服务区域1", migrated)

    def test_resume_label_migration_replaces_generic_seed_names_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "service.js"
            source.write_text(
                'name: payload.name || "生产工单管控业务记录",\n'
                '"生产工单管控记录01",\n'
                'throw new Error("业务记录缺少必要字段");',
                encoding="utf-8",
            )

            changed = repair_generated_business_record_labels(root)
            migrated = source.read_text(encoding="utf-8")

        self.assertEqual(changed, 2)
        self.assertIn('生产工单管控对象', migrated)
        self.assertNotIn('生产工单管控记录01', migrated)
        self.assertIn('业务记录缺少必要字段', migrated)

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
            migration = (root / "migrations/001_initial.sql").read_text(encoding="utf-8")
            self.assertIn("INSERT OR IGNORE INTO equipment_registry_record", migration)
            self.assertIn("设备资产建档待办", migration)

            python_files = [str(path) for path in root.rglob("*.py")]
            compiled = subprocess.run(
                [sys.executable, "-m", "py_compile", *python_files],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(compiled.returncode, 0, compiled.stderr)

            tested = subprocess.run(
                [sys.executable, "-I", "-m", "unittest", "discover", "-s", "tests", "-v"],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(tested.returncode, 0, tested.stderr)
            self.assertIn("test_record_survives_repository_reopen", tested.stderr)


if __name__ == "__main__":
    unittest.main()
