from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from backend.softcopyright.blueprint import FeatureModule, ProductBlueprint
from backend.softcopyright.llm_blueprint import (
    _clean_workflows,
    _generate_module_batches,
    _expected_plan_terminal,
    _normalize_plan_terminal_semantics,
    _quality_review,
    _select_contract_modules,
    blueprint_contract_issues,
)
from backend.softcopyright.models import GenerationTask
from backend.softcopyright.module_keys import is_placeholder_module_key, semantic_module_key
from backend.softcopyright.validator import validate_materials


def _operation(action_key, label, category, role, trigger, fields, pre_state, post_state, evidence):
    return {
        "action_key": action_key,
        "label": label,
        "category": category,
        "role": role,
        "trigger": trigger,
        "input_fields": fields,
        "pre_state": pre_state,
        "post_state": post_state,
        "result_evidence": evidence,
        "requires_confirmation": False,
    }


def _module(key, title, operations):
    return FeatureModule(
        key=key,
        title=title,
        description=f"围绕{title}处理制造现场对象、状态变化、业务校验和结果追踪，形成可核验的执行记录。",
        entities=[f"{key.title().replace('_', '')}Record", f"{key.title().replace('_', '')}Trace"],
        operations=[item["label"] for item in operations],
        data_fields=["业务编号", "目标产线", "责任岗位", "当前状态", "计划时间", "实际时间", "处理结论"],
        pages=[f"{title}工作台", f"{title}详情"],
        rules=["仅授权岗位可操作", "状态必须按业务顺序流转", "关键动作写入审计日志"],
        operation_specs=operations,
    )


def _valid_blueprint(task):
    plan_operations = [
        _operation("filter_plan_versions", "筛选待确认计划版本", "lookup", "计划员", "需要定位待确认计划", ["计划版本", "目标产线"], "全部计划", "显示匹配计划", "筛选条件和结果数量"),
        _operation("compare_plan_capacity", "比对计划产能约束", "analysis", "计划员", "计划版本提交确认前", ["计划版本", "产能上限"], "待校验", "约束已核验", "冲突项和产能差额"),
        _operation("confirm_plan_version", "采用主生产计划版本", "workflow", "计划主管", "约束校验通过", ["计划版本", "采用原因"], "待确认", "已生效", "版本状态和采用日志"),
    ]
    work_order_operations = [
        _operation("filter_work_orders", "筛选待下达生产工单", "lookup", "车间主管", "需要定位待执行工单", ["工单编号", "目标产线"], "全部工单", "显示匹配工单", "筛选条件和工单数量"),
        _operation("release_work_order", "下达生产工单", "workflow", "车间主管", "物料与工艺路线校验通过", ["工单编号", "计划数量"], "待下达", "已下达", "状态轨迹和下达日志"),
        _operation("pause_work_order", "暂停异常生产工单", "workflow", "车间主管", "设备停机或物料短缺", ["暂停原因", "预计恢复时间"], "生产中", "已暂停", "暂停原因和影响范围"),
    ]
    return ProductBlueprint(
        software_name=task.software_name,
        version="V1.0",
        language="Java",
        product_type=task.product_type,
        industry="智能制造",
        purpose="支撑生产计划与现场执行协同。",
        summary="面向制造企业生产计划、工单执行和产线协同场景，提供计划约束校验、生产工单下达、异常暂停和结果追踪能力。",
        modules=[
            _module("production_plan", "生产计划协同", plan_operations),
            _module("work_order_control", "生产工单管控", work_order_operations),
        ],
        roles=["计划员", "车间主管"],
        pages=["登录页", "系统首页", "生产计划工作台", "生产工单工作台"],
        dev_environment={},
        runtime_environment={},
        scenario="制造企业生产运营工作台",
        positioning="面向计划与现场执行岗位的工业生产协同平台",
        target_users=["计划员", "车间主管"],
        business_objects=["主生产计划", "计划版本", "生产工单", "产线", "工艺路线", "物料需求"],
        workflows=[
            {
                "name": "计划下达到现场执行",
                "trigger": "计划版本通过约束校验",
                "steps": ["确认主生产计划版本", "分解并生成生产工单", "校验物料和工艺路线", "下达工单并记录执行日志"],
                "output": "形成已下达生产工单和状态轨迹",
            }
        ],
        report_metrics=["计划达成率", "工单按期完工率"],
        quality_rules=["状态按顺序流转"],
        data_relations=["计划版本分解为生产工单"],
        deployment_topology="浏览器访问生产运营服务，服务端连接制造业务数据库。",
        uniqueness_notes=["计划约束与工单执行形成闭环"],
    )


class BlueprintOperationContractTests(unittest.TestCase):
    def setUp(self):
        self.task = GenerationTask(
            software_name="智能生产效率提升平台",
            product_type="人工智能软件",
            feature_hint="生产计划、生产工单、产线排程、工序节拍和设备停机响应",
            seed="operation-contract-test",
        )

    def test_valid_structured_blueprint_passes_contract_review(self):
        blueprint = _valid_blueprint(self.task)

        self.assertEqual(blueprint_contract_issues(self.task, blueprint), [])

    def test_missing_specs_and_mobile_pollution_fail_contract_review(self):
        blueprint = _valid_blueprint(self.task)
        blueprint.modules[0].operation_specs = []
        blueprint.workflows[0]["trigger"] = "生产人员登录移动 App 并查看会员权益和个人中心"

        issues = blueprint_contract_issues(self.task, blueprint)

        self.assertTrue(any("缺少至少 3 个结构化操作契约" in issue for issue in issues))
        self.assertTrue(any("移动消费端语义" in issue for issue in issues))
        score, reasons = _quality_review(self.task, blueprint)
        self.assertLess(score, 92)
        self.assertTrue(reasons)

    def test_candidate_selection_prefers_category_coverage(self):
        candidates = [
            {"key": f"module_{index}", "title": f"执行模块{index}", "category": "执行", "data_objects": ["记录"], "screens": ["列表"]}
            for index in range(1, 9)
        ]
        candidates.extend(
            [
                {"key": "risk_alert", "title": "风险预警", "category": "预警", "data_objects": ["预警"], "screens": ["预警台"]},
                {"key": "audit_trace", "title": "审计追溯", "category": "审计", "data_objects": ["日志"], "screens": ["审计页"]},
            ]
        )

        selected = _select_contract_modules(candidates, limit=8)
        titles = {item["title"] for item in selected}

        self.assertIn("风险预警", titles)
        self.assertIn("审计追溯", titles)
        self.assertEqual(len(selected), 8)

    def test_legacy_domain_hash_keys_are_replaced_with_manufacturing_semantics(self):
        cases = {
            "产线智能排程": "smart_scheduling",
            "工序节拍监控": "process_takt",
            "设备停机响应": "equipment_downtime",
            "产能预测与瓶颈识别": "capacity_forecast_bottleneck_detection",
            "良率改善闭环": "yield_improvement",
            "交付达成监控": "delivery_performance",
        }

        self.assertTrue(is_placeholder_module_key("domain_03_10723"))
        for index, (title, expected) in enumerate(cases.items(), start=1):
            key = semantic_module_key(title, index, raw_key=f"domain_{index:02d}_10723")
            self.assertEqual(key, expected)
            self.assertFalse(is_placeholder_module_key(key))

    def test_admin_blueprint_terminal_semantics_are_normalized_without_touching_mobile_apps(self):
        polluted = {
            "summary": "生产主管登录移动 App，在个人中心收藏计划并离线缓存甘特图。",
            "workflows": [
                {
                    "name": "首页推荐",
                    "steps": ["接收推荐提醒", "订阅设备并在弱网环境离线查看"],
                }
            ],
            "modules": [
                {
                    "operation_specs": [
                        {"label": "收藏与离线查看", "result_evidence": "个人关注和使用记录"}
                    ]
                }
            ],
        }

        normalized = _normalize_plan_terminal_semantics(self.task, polluted)
        normalized_text = str(normalized)

        self.assertNotIn("移动 App", normalized_text)
        self.assertNotIn("个人中心", normalized_text)
        self.assertNotIn("离线查看", normalized_text)
        self.assertIn("工业生产运营工作台", normalized_text)
        self.assertIn("重点标记", normalized_text)
        self.assertIn("权限与审计中心", normalized_text)

        mobile_task = GenerationTask(software_name="小艾听歌软件", product_type="APP", feature_hint="音乐搜索和歌曲播放")
        self.assertEqual(_normalize_plan_terminal_semantics(mobile_task, polluted), polluted)

    def test_industrial_risk_list_does_not_turn_the_product_into_a_consumer_app(self):
        task = GenerationTask(
            software_name="智能生产效率提升平台",
            product_type="人工智能软件",
            feature_hint="生产计划、生产工单、设备停机响应和延期风险清单",
        )

        self.assertEqual(_expected_plan_terminal(task), "admin")
        self.assertEqual(
            _expected_plan_terminal(GenerationTask(software_name="个人待办清单", product_type="APP")),
            "mobile_app",
        )

    def test_workflow_cleanup_preserves_complete_long_steps(self):
        step = "读取生产工单、工艺路线、设备负荷和物料齐套状态后生成可执行排程方案并记录冲突原因"

        workflows = _clean_workflows([{"name": "排程流程", "trigger": "计划生效", "steps": [step, "校验资源冲突并输出结果", "采用目标排程方案并记录版本"], "output": "排程版本"}])

        self.assertEqual(workflows[0]["steps"][0], step)
        self.assertGreater(len(workflows[0]["steps"][0]), 32)

    def test_final_validator_requires_contract_only_for_formal_gpt_mode(self):
        blueprint = _valid_blueprint(self.task)
        with TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            gpt_validation = validate_materials(
                task=self.task,
                blueprint=blueprint,
                output_dir=output_dir,
                source_info={"source_dir": str(output_dir / "generated_source")},
                ui_blueprint=None,
                ui_screenshots={},
                deliverable_files=[],
                checks={
                    "blueprint_operation_contract_ready": False,
                    "blueprint_operation_contract_issues": ["生产计划协同缺少至少 3 个结构化操作契约"],
                },
            )
            local_task = GenerationTask(
                software_name=self.task.software_name,
                product_type=self.task.product_type,
                model_provider="local-template",
                seed="local-contract-test",
            )
            local_validation = validate_materials(
                task=local_task,
                blueprint=blueprint,
                output_dir=output_dir,
                source_info={"source_dir": str(output_dir / "generated_source")},
                ui_blueprint=None,
                ui_screenshots={},
                deliverable_files=[],
                checks={"blueprint_operation_contract_ready": False},
            )

        gpt_codes = {item["code"] for item in gpt_validation["findings"]}
        local_codes = {item["code"] for item in local_validation["findings"]}
        self.assertTrue(gpt_validation["authenticity"]["blueprint_operation_contract_required"])
        self.assertFalse(gpt_validation["authenticity"]["blueprint_operation_contract_ready"])
        self.assertIn("blueprint_operation_contract_not_ready", gpt_codes)
        self.assertFalse(local_validation["authenticity"]["blueprint_operation_contract_required"])
        self.assertTrue(local_validation["authenticity"]["blueprint_operation_contract_ready"])
        self.assertNotIn("blueprint_operation_contract_not_ready", local_codes)

    def test_balanced_module_batches_repair_only_the_failed_batch(self):
        outline = [
            {"key": f"manufacturing_module_{index}", "title": f"生产执行模块{index}", "focus": "制造现场业务"}
            for index in range(1, 7)
        ]
        call_labels = []

        def valid_module(index):
            title = f"模型漂移标题{index}"
            return {
                "key": f"module_{index}",
                "title": title,
                "description": "围绕生产计划、生产工单、产线资源和制造现场状态组织业务处理，校验责任岗位、执行条件和状态流转，完成后输出可核验的任务轨迹、统计结果和审计记录。",
                "entities": ["ProductionRecord", "ProductionTrace"],
                "operations": ["筛选生产任务", "下达生产工单", "暂停异常任务", "分析执行偏差", "追踪处理结果"],
                "operation_specs": [
                    _operation("filter_production_tasks", "筛选生产任务", "lookup", "计划员", "需要定位待执行任务", ["任务编号", "目标产线"], "全部任务", "显示匹配任务", "筛选条件和结果数量"),
                    _operation("release_production_order", "下达生产工单", "workflow", "车间主管", "物料和工艺校验通过", ["工单编号", "计划数量"], "待下达", "已下达", "工单状态和下达日志"),
                    _operation("analyze_execution_gap", "分析执行偏差", "analysis", "生产主管", "实际进度偏离计划", ["计划版本", "统计周期"], "待分析", "已形成偏差结论", "偏差指标和影响范围"),
                ],
                "data_fields": ["生产任务编号", "目标产线", "计划数量", "实际数量", "责任岗位", "执行状态", "偏差原因"],
                "pages": ["生产任务工作台", "执行结果详情"],
                "rules": ["仅授权岗位可下达任务", "工单状态必须按顺序流转", "关键动作必须写入审计日志"],
            }

        def chat_json(_provider, _messages, *, temperature, max_tokens, label):
            call_labels.append(label)
            batch_index = int(label[-1])
            if "修复" not in label:
                invalid = valid_module(batch_index * 2 - 1)
                invalid["operation_specs"] = []
                return {"modules": [invalid, invalid]}
            return {"modules": [valid_module(batch_index * 2 - 1), valid_module(batch_index * 2)]}

        with patch.dict("os.environ", {"SOFT_GENERATION_PROFILE": "balanced", "SOFT_LLM_BATCH_WORKERS": "1"}), patch(
            "backend.softcopyright.llm_blueprint._chat_json",
            side_effect=chat_json,
        ):
            modules = _generate_module_batches(
                self.task,
                object(),
                {"module_outline": outline},
                [],
                "",
            )

        self.assertEqual(len(modules), 6)
        self.assertEqual(call_labels.count("模块明细修复批次1"), 1)
        self.assertEqual(call_labels.count("模块明细修复批次2"), 1)
        self.assertEqual(call_labels.count("模块明细修复批次3"), 1)
        self.assertEqual([item["key"] for item in modules], [item["key"] for item in outline])
        self.assertEqual([item["title"] for item in modules], [item["title"] for item in outline])


if __name__ == "__main__":
    unittest.main()
