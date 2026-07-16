from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.softcopyright.blueprint import FeatureModule, ProductBlueprint
from backend.softcopyright.models import GenerationTask
from backend.softcopyright.generator import _semantic_contract_from_cached_blueprint
from backend.softcopyright.stage_cache import (
    build_stage_cache_context,
    find_resume_stage_cache_context,
    load_cached_blueprint,
    save_cached_blueprint,
)


def _blueprint(task: GenerationTask) -> ProductBlueprint:
    modules = [
        FeatureModule(
            key=f"module_{index}",
            title=f"业务模块{index}",
            description="处理真实业务流程。",
            entities=[f"Record{index}"],
            operations=["登记", "核验", "处理", "归档"],
            data_fields=["业务编号", "状态", "责任人", "更新时间"],
            operation_specs=[
                {
                    "action_key": f"query_module_{index}",
                    "label": f"查询业务模块{index}",
                    "category": "lookup",
                    "role": "业务人员",
                    "trigger": "需要定位业务记录",
                    "input_fields": ["业务编号"],
                    "pre_state": "全部记录",
                    "post_state": "显示匹配记录",
                    "result_evidence": "查询条件和结果数量",
                    "requires_confirmation": False,
                }
            ],
        )
        for index in range(1, 7)
    ]
    return ProductBlueprint(
        software_name=task.software_name,
        version=task.version,
        language="Python",
        product_type=task.product_type,
        industry="设备运维",
        purpose="验证阶段缓存。",
        summary="验证任务 seed 对阶段缓存的隔离和复用。",
        modules=modules,
        roles=["管理员"],
        pages=["首页"],
        dev_environment={},
        runtime_environment={},
        quality_score=90,
    )


class StageCacheSeedTests(unittest.TestCase):
    def test_new_seed_is_isolated_and_same_seed_is_reused(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            first = GenerationTask(software_name="缓存种子验证系统", product_type="人工智能软件", seed="seed-a", output_root=root)
            second = GenerationTask(software_name=first.software_name, product_type=first.product_type, seed="seed-b", output_root=root)
            meta = {"feature_hint_blueprint_modules": [{"title": f"业务模块{index}"} for index in range(1, 7)]}
            first_context = build_stage_cache_context(first, meta)
            second_context = build_stage_cache_context(second, meta)
            changed_inference = {"feature_hint_blueprint_modules": [{"title": f"另一种模块{index}"} for index in range(1, 7)]}
            repeated_context = build_stage_cache_context(first, changed_inference)
            self.assertNotEqual(first_context["key"], second_context["key"])
            self.assertEqual(first_context["key"], repeated_context["key"])
            save_cached_blueprint(first_context, _blueprint(first))
            cached = load_cached_blueprint(first_context)
            self.assertIsNotNone(cached)
            self.assertEqual(cached.modules[0].operation_specs[0]["action_key"], "query_module_1")
            self.assertIsNone(load_cached_blueprint(second_context))

    def test_resume_finds_same_seed_cache_without_repeating_feature_inference(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            task = GenerationTask(
                software_name="断点缓存恢复系统",
                product_type="人工智能软件",
                seed="resume-seed",
                output_root=root,
                resume_output_dir=str(root / "断点缓存恢复系统-resume-seed"),
                resume_existing_output=True,
            )
            original_meta = {"feature_hint_blueprint_modules": [{"title": f"业务模块{index}"} for index in range(1, 9)]}
            original_context = build_stage_cache_context(task, original_meta)
            blueprint = _blueprint(task)
            blueprint.modules.extend(
                [
                    FeatureModule(
                        key=f"extra_{index}",
                        title=f"扩展模块{index}",
                        description="处理断点恢复所需的完整业务流程和数据状态。",
                        entities=[f"ExtraRecord{index}"],
                        operations=["查询", "处理", "确认", "归档"],
                        data_fields=["编号", "状态", "责任人", "更新时间"],
                    )
                    for index in range(7, 9)
                ]
            )
            save_cached_blueprint(original_context, blueprint)

            recovered_context = find_resume_stage_cache_context(task)
            self.assertIsNotNone(recovered_context)
            self.assertEqual(recovered_context["key"], original_context["key"])
            recovered_blueprint = load_cached_blueprint(recovered_context)
            contract = _semantic_contract_from_cached_blueprint(recovered_blueprint)
            self.assertEqual(contract["feature_hint_source"], "resume-stage-cache")
            self.assertGreaterEqual(len(contract["feature_hint_blueprint_modules"]), 8)


if __name__ == "__main__":
    unittest.main()
