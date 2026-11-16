import json
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from backend.softcopyright.blueprint import FeatureModule, ProductBlueprint, generate_blueprint
from backend.softcopyright.industry_subtypes import INDUSTRY_SUBTYPES
from backend.softcopyright.llm_blueprint import (
    blueprint_contract_review,
    _clean_workflows,
    _generate_modules,
    _generate_module_batches,
    generate_blueprint_with_llm,
    _expected_plan_terminal,
    _feature_term_matches_plan,
    _normalize_plan_terminal_semantics,
    _quality_review,
    _reconcile_plan_with_contract,
    _select_contract_modules,
    blueprint_contract_issues,
    normalize_cached_blueprint_candidate,
    repair_blueprint_contract,
)
from backend.softcopyright.models import GenerationTask
from backend.softcopyright.module_keys import is_placeholder_module_key, semantic_module_key
from backend.softcopyright.product_experience import build_product_experience_spec
from backend.softcopyright.generator import _load_accepted_product_blueprint
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
    def test_download_manager_app_stays_mobile_despite_queue_scheduling_terms(self):
        task = GenerationTask(
            software_name="疾风下载",
            product_type="APP",
            feature_hint="下载链接解析、下载任务创建、下载队列调度、后台下载和断点续传",
        )

        self.assertEqual(_expected_plan_terminal(task), "mobile_app")

    def test_download_manager_experience_ignores_background_download_as_admin_signal(self):
        task = GenerationTask(
            software_name="疾风下载",
            product_type="APP",
            feature_hint="下载链接、下载任务、下载队列调度、后台下载、下载进度和断点续传",
        )
        blueprint = _valid_blueprint(task)
        blueprint.modules = [deepcopy(blueprint.modules[index % 2]) for index in range(4)]
        for index, module in enumerate(blueprint.modules, start=1):
            module.key = f"download_experience_{index}"
        blueprint.industry = "移动文件下载与传输管理"
        blueprint.summary = "用户可在手机 App 的个人中心查看会员状态和会员并发权益，并持续执行后台下载。"

        experience = build_product_experience_spec(task, blueprint)
        normalized = normalize_cached_blueprint_candidate(task, blueprint)
        joined = json.dumps(normalized.to_dict(), ensure_ascii=False)

        self.assertEqual(experience.industry_subtype_key, "download_manager")
        self.assertEqual(experience.renderer, "mobile_app")
        self.assertNotIn("会员状态", joined)
        self.assertNotIn("会员权益", joined)
        self.assertNotIn("个人中心", joined)

    def test_download_manager_cached_generic_operations_are_repaired_locally(self):
        task = GenerationTask(
            software_name="疾风下载",
            product_type="APP",
            feature_hint="下载链接解析、下载任务、下载队列、后台下载和断点续传",
        )
        blueprint = _valid_blueprint(task)
        blueprint.modules = [deepcopy(blueprint.modules[index % 2]) for index in range(4)]
        for index, (module, title) in enumerate(
            zip(
                blueprint.modules,
                ("下载链接解析", "新建下载任务", "下载队列编排", "加速与后台下载"),
            ),
            start=1,
        ):
            module.key = f"download_module_{index}"
            module.title = title
            module.operation_specs = [
                _operation(f"{module.key}_{index}", label, category, "当前用户", "需要处理下载任务", ["任务编号", "任务状态"], "待处理", "已更新", "页面结果和更新时间")
                for index, (label, category) in enumerate(
                    [
                        (f"筛选{module.title}记录", "lookup"),
                        (f"{module.title}登记", "mutation"),
                        (f"{module.title}校验", "workflow"),
                    ],
                    start=1,
                )
            ]
            module.operations = [spec["label"] for spec in module.operation_specs]

        normalized = normalize_cached_blueprint_candidate(task, blueprint)
        labels = {module.title: [spec["label"] for spec in module.operation_specs] for module in normalized.modules}

        self.assertIn("解析下载链接", labels["下载链接解析"])
        self.assertIn("调整任务优先级", labels["下载队列编排"])
        self.assertNotIn("下载队列编排登记", labels["下载队列编排"])

    def test_generic_lookup_record_suffix_does_not_trigger_cross_module_duplication(self):
        task = GenerationTask(software_name="下载任务工具", product_type="APP")
        blueprint = _valid_blueprint(task)
        titles = ["链接解析", "任务创建", "队列编排", "传输执行", "异常恢复", "文件交付"]
        verbs = ["解析", "创建", "调序", "传输", "续传", "交付"]
        blueprint.modules = []
        for index, (title, verb) in enumerate(zip(titles, verbs), start=1):
            operations = [
                _operation(f"lookup_{index}", f"筛选{title}记录", "lookup", "当前用户", f"需要定位{title}", [f"{title}编号", f"{title}状态"], "未筛选", "显示匹配结果", "筛选条件和结果数量"),
                _operation(f"action_{index}", f"{verb}目标对象", "workflow", "当前用户", f"需要执行{verb}", [f"{title}编号", "执行参数"], "待执行", f"已完成{verb}", f"{verb}结果和状态轨迹"),
                _operation(f"result_{index}", f"查看{verb}结果", "result", "当前用户", f"{verb}完成后", [f"{title}编号", "完成时间"], f"已完成{verb}", "结果已展示", f"{verb}结果和完成时间"),
            ]
            module = _module(f"download_{index}", title, operations)
            module.description = f"围绕{title}执行{verb}处理，核对输入参数、状态变化和结果证据。"
            blueprint.modules.append(module)

        issues = blueprint_contract_issues(task, blueprint)

        self.assertFalse(any("跨模块操作重复度过高" in issue for issue in issues), issues)

    def test_agency_accounting_app_uses_admin_terminal(self):
        task = GenerationTask(
            software_name="风灵月影代账",
            product_type="APP",
            feature_hint="企业客户建档、核算账套、税务申报、财务报表",
            model_provider="custom",
        )
        self.assertEqual(_expected_plan_terminal(task), "admin")

    def test_figma_design_viewer_app_uses_desktop_terminal(self):
        task = GenerationTask(
            software_name="Figma浏览器",
            product_type="APP",
            feature_hint="设计文件、页面画板、图层组件、原型演示和设计评审",
            model_provider="custom",
        )

        self.assertEqual(_expected_plan_terminal(task), "admin")

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

    def test_feature_hint_semantic_phrases_match_equivalent_business_actions(self):
        joined = "移动现场点检执行、消防设施档案、隐患整改复验闭环、异常告警联动处置"

        self.assertTrue(_feature_term_matches_plan("移动巡检", joined))
        self.assertTrue(_feature_term_matches_plan("消防设施台账", joined))
        self.assertTrue(_feature_term_matches_plan("隐患闭环", joined))
        self.assertFalse(_feature_term_matches_plan("会员积分兑换", joined))

    def test_real_business_action_descriptions_are_not_penalized_as_generic(self):
        task = GenerationTask(
            software_name="智慧园区消防设施巡检与隐患闭环平台",
            product_type="物联网软件",
            feature_hint="消防设施台账、移动巡检、隐患闭环",
            seed="fire-blueprint-quality",
        )
        blueprint = _valid_blueprint(task)
        blueprint.summary = (
            "面向园区消防安全管理岗位，围绕消防设施档案、移动现场点检、告警联动、隐患上报、整改复验和闭环统计，"
            "形成从对象建档到结果追溯的完整流程；系统按设施位置和责任范围组织任务，记录每次采集、处置和复验结果，"
            "为日常巡检、隐患治理、管理复盘和审计追踪提供统一且可核验的业务依据。"
        )
        descriptions = [
            "围绕消防设施档案执行对象建档、二维码绑定和停用恢复，记录设施位置、责任单位和有效期限。",
            "按责任区域编排巡检计划并下达现场点检任务，记录执行人员、计划时间和任务状态。",
            "采集消防设施状态并监测异常阈值，生成告警后联动派发处置任务并保留反馈证据。",
            "接收隐患上报并生成整改要求，责任人员提交结果后由复验人员关闭或退回隐患。",
        ]
        blueprint.modules = [deepcopy(blueprint.modules[index % 2]) for index in range(4)]
        for index, module in enumerate(blueprint.modules):
            module.key = f"fire_module_{index}"
            module.title = ["消防设施对象建档", "巡检计划任务编排", "状态监测告警联动", "隐患整改复验闭环"][index]
            module.description = descriptions[index] + "系统同步保存前后状态、责任岗位与结果依据，支持后续查询和追溯。"
            module.data_fields = ["设施编号", "安装位置", "责任单位", "当前状态", "更新时间", "结果证据"]
            module.operations = ["查询消防设施", "执行现场点检", "上报告警隐患", "提交整改结果", "复验关闭隐患"]
        blueprint.business_objects = ["消防设施档案", "巡检计划", "点检任务", "告警事件", "隐患单", "整改任务"]
        blueprint.workflows = blueprint.workflows * 3
        blueprint.report_metrics = ["巡检完成率", "告警处置率", "隐患闭环率", "平均整改时长", "复验通过率", "逾期数量"]
        blueprint.quality_rules = ["设施编号唯一", "任务按责任区域下达", "隐患关闭必须复验", "关键动作记录人员", "导出受权限控制"]
        blueprint.uniqueness_notes = ["设施到隐患可追溯", "点检证据关联任务", "整改与复验岗位分离", "闭环指标可下钻"]

        score, reasons = _quality_review(task, blueprint)

        self.assertNotIn("多个模块描述缺少具体业务动作", reasons)
        self.assertNotIn("产品方案与业务补充关键词关联不足", reasons)

    def test_local_template_subtype_modules_keep_unique_keys(self):
        task = GenerationTask(
            software_name="零令牌模板安装验收系统",
            product_type="APP",
            feature_hint="用户入口、首页导航、核心工作台、业务表单处理、记录查询、统计分析、消息提醒、系统设置",
            model_provider="local-template",
            seed="local-template-key-smoke",
        )

        blueprint = generate_blueprint(task)
        keys = [module.key for module in blueprint.modules]

        self.assertEqual(len(keys), len(set(keys)))
        self.assertGreaterEqual(len(keys), 6)
        self.assertTrue(all(len(module.operation_specs) >= 3 for module in blueprint.modules))
        self.assertGreaterEqual(blueprint.quality_score, 86)
        self.assertEqual(blueprint_contract_issues(task, blueprint), [])
        self.assertNotIn("业务记录", json.dumps(blueprint.to_dict(), ensure_ascii=False))

    def test_local_community_modules_use_distinct_domain_operations_and_workflows(self):
        task = GenerationTask(
            software_name="社区生活预约服务平台",
            product_type="APP",
            feature_hint="社区预约、门店核销、会员权益、消息推送、售后工单、活动运营和订单支付",
            model_provider="local-template",
            seed="community-semantic-diversity",
        )

        blueprint = generate_blueprint(task)
        operation_signatures = {
            tuple((operation["category"], operation["label"]) for operation in module.operation_specs)
            for module in blueprint.modules
        }
        normalized_descriptions = {
            module.description.replace(module.title, "{模块}").replace(module.title.removesuffix("管理"), "{对象}")
            for module in blueprint.modules
        }
        workflow_steps = {
            tuple(workflow["steps"])
            for workflow in blueprint.workflows
        }

        self.assertEqual(blueprint.industry_subtype_key, "community_service")
        self.assertEqual(
            [module.title for module in blueprint.modules],
            ["服务预约管理", "门店核销管理", "会员权益管理", "消息推送管理", "售后工单管理", "活动入口管理", "订单支付管理"],
        )
        expected_keys = {
            "服务预约管理": "service_booking",
            "门店核销管理": "store_redemption",
            "会员权益管理": "member_benefit",
            "消息推送管理": "message_delivery",
            "售后工单管理": "aftersales_ticket",
            "活动入口管理": "campaign_entry",
            "订单支付管理": "order_payment",
        }
        self.assertTrue(all(module.key == expected_keys[module.title] for module in blueprint.modules))
        self.assertGreaterEqual(len(operation_signatures), 4)
        self.assertGreaterEqual(len(normalized_descriptions), 4)
        self.assertTrue(any("创建服务预约" in operation["label"] for module in blueprint.modules for operation in module.operation_specs))
        self.assertTrue(any("执行门店核销" in operation["label"] for module in blueprint.modules for operation in module.operation_specs))
        self.assertTrue(any("发布活动入口" in operation["label"] for module in blueprint.modules for operation in module.operation_specs))
        self.assertEqual(len(workflow_steps), 3)
        self.assertFalse(any(str(workflow["name"]).endswith("闭环流程") for workflow in blueprint.workflows))
        self.assertGreaterEqual(blueprint.quality_score, 86)
        self.assertEqual(blueprint_contract_issues(task, blueprint), [])

    def test_contract_review_rejects_noun_substituted_operation_templates(self):
        blueprint = _valid_blueprint(self.task)
        blueprint.modules = []
        for index in range(1, 7):
            title = f"生产对象{index}管理"
            subject = title.removesuffix("管理")
            operations = [
                _operation(f"object_{index}_query", f"筛选{subject}", "lookup", "操作员", "需要定位对象", [f"{subject}编号", "业务状态"], "未应用查询条件", "显示匹配业务对象", "筛选条件和结果数量"),
                _operation(f"object_{index}_verify", f"核验{subject}", "workflow", "操作员", "对象待处理", [f"{subject}编号", "业务状态"], "记录处于待处理状态", "记录更新为已核验", "核验结论和操作日志"),
                _operation(f"object_{index}_archive", f"归档{subject}结果", "result", "操作员", "对象已完成核验", [f"{subject}编号", "业务状态"], "记录已完成核验", "记录更新为已归档", "归档编号和完成时间"),
            ]
            module = _module(f"production_object_{index}", title, operations)
            module.description = f"围绕{subject}提供业务录入、状态跟踪、异常处理和统计分析。"
            blueprint.modules.append(module)

        issues = blueprint_contract_issues(self.task, blueprint)
        review = blueprint_contract_review(self.task, blueprint)

        self.assertTrue(any("结构化操作缺少语义差异" in issue for issue in issues))
        self.assertTrue(any("说明仅替换业务对象" in issue for issue in issues))
        self.assertEqual(review.blocking_issues, ())
        self.assertTrue(review.quality_warnings)

    def test_unknown_industry_generic_contract_is_repaired_without_subtype_rules(self):
        task = GenerationTask(
            software_name="量子态熵谱跃迁实验分析系统",
            product_type="人工智能软件",
            feature_hint="量子样本接入、熵谱参数标定、跃迁特征计算、态矢异常识别、标定结果复核、实验批次归档",
            seed="unknown-domain-contract-repair",
        )
        blueprint = _valid_blueprint(task)
        module_data = [
            ("量子样本接入", ["量子样本编号", "接入通道", "采集状态"]),
            ("熵谱参数标定", ["熵谱参数编号", "标定区间", "标定偏差"]),
            ("跃迁特征计算", ["跃迁特征编号", "跃迁频率", "计算结果"]),
            ("态矢异常识别", ["态矢记录编号", "异常阈值", "识别结论"]),
            ("标定结果复核", ["复核任务编号", "结果版本", "复核结论"]),
            ("实验批次归档", ["实验批次编号", "归档目录", "归档状态"]),
        ]
        blueprint.modules = [deepcopy(blueprint.modules[index % 2]) for index in range(len(module_data))]
        for index, (module, (title, fields)) in enumerate(zip(blueprint.modules, module_data), start=1):
            module.key = f"domain_{index:02d}_98765"
            module.title = title
            module.description = f"围绕{title}提供业务录入、状态跟踪、异常处理和统计分析。"
            module.data_fields = fields + ["处理人员", "更新时间", "备注说明"]
            module.operations = [f"筛选{title}记录", f"{title}登记", f"{title}校验", f"{title}跟踪"]
            module.operation_specs = [
                _operation(
                    f"generic_{index}_{spec_index}",
                    label,
                    category,
                    "业务人员",
                    "需要处理实验数据",
                    fields[:2],
                    "待处理",
                    "已更新",
                    "页面结果和更新时间",
                )
                for spec_index, (label, category) in enumerate(
                    (
                        (f"筛选{title}记录", "lookup"),
                        (f"{title}登记", "mutation"),
                        (f"{title}校验", "workflow"),
                    ),
                    start=1,
                )
            ]

        before = blueprint_contract_review(task, blueprint)
        repaired = repair_blueprint_contract(task, blueprint)
        after = blueprint_contract_review(task, repaired)
        labels = [[str(spec.get("label") or "") for spec in module.operation_specs] for module in repaired.modules]

        self.assertTrue(before.quality_warnings)
        self.assertEqual(after.blocking_issues, ())
        self.assertEqual(after.quality_warnings, ())
        self.assertTrue(all(not is_placeholder_module_key(module.key) for module in repaired.modules))
        self.assertEqual(len({tuple(items) for items in labels}), len(module_data))
        self.assertTrue(any("接入量子样本" in label for label in labels[0]))
        self.assertIn("计算跃迁特征", labels[2])

    def test_all_local_subtypes_pass_semantic_contract_review(self):
        checked = 0
        for product_type, subtypes in INDUSTRY_SUBTYPES.items():
            for subtype in subtypes:
                task = GenerationTask(
                    software_name=subtype.title,
                    product_type=product_type,
                    feature_hint="、".join(subtype.domain_terms),
                    model_provider="local-template",
                    seed=f"semantic-audit-{subtype.key}",
                )

                blueprint = generate_blueprint(task)
                checked += 1

                self.assertEqual(blueprint.industry_subtype_key, subtype.key)
                self.assertGreaterEqual(blueprint.quality_score, 86)
                self.assertEqual(blueprint_contract_issues(task, blueprint), [])

        self.assertGreaterEqual(checked, 37)

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

    def test_prefabricated_building_quality_keys_are_repaired_locally(self):
        cases = {
            "构件进场验收": "component_site_acceptance",
            "预制构件安装定位校验": "component_installation_positioning_prefabricated",
            "拼装节点与连接质量检查": "assembly_joint_connection_quality",
            "灌浆与焊接质量检验": "welding_quality_grouting",
            "质量缺陷整改复验": "quality_defect_rectification_reinspection",
        }

        for index, (title, expected) in enumerate(cases.items(), start=1):
            key = semantic_module_key(title, index, raw_key=f"domain_{index:02d}_24005")
            self.assertEqual(key, expected)
            self.assertFalse(is_placeholder_module_key(key))

    def test_unknown_chinese_title_fallback_never_creates_a_forbidden_domain_hash(self):
        key = semantic_module_key("量子态熵谱跃迁", 6, raw_key="domain_06_24005")

        self.assertTrue(key.startswith("capability_06_"))
        self.assertFalse(is_placeholder_module_key(key))

    def test_prefabricated_quality_candidate_passes_weak_key_gate_after_local_normalization(self):
        task = GenerationTask(
            software_name="装配式建筑构件安装质量智能校验与管理平台",
            product_type="人工智能软件",
        )
        blueprint = generate_blueprint(task)
        blueprint.modules[-1].title = "质量缺陷整改复验"
        blueprint.modules[-1].key = "domain_06_24005"

        normalized = normalize_cached_blueprint_candidate(task, blueprint)
        issues = blueprint_contract_issues(task, normalized)

        self.assertEqual(normalized.modules[-1].key, "quality_defect_rectification_reinspection")
        self.assertFalse(any("弱语义模块 key" in issue for issue in issues))

    def test_admin_blueprint_terminal_semantics_are_normalized_without_touching_mobile_apps(self):
        polluted = {
            "summary": "生产主管登录移动 App，移动端会员状态通过底部导航进入个人中心，并收藏计划和离线缓存甘特图。",
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
        self.assertNotIn("移动端", normalized_text)
        self.assertNotIn("会员状态", normalized_text)
        self.assertNotIn("底部导航", normalized_text)
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
        self.assertEqual(
            _expected_plan_terminal(
                GenerationTask(
                    software_name="客户服务协同平台",
                    product_type="APP",
                    feature_hint="客户咨询、客服工单、投诉处理和服务回访",
                )
            ),
            "admin",
        )

    def test_customer_service_modules_receive_stable_semantic_keys(self):
        cases = {
            "客户咨询接入": "customer_inquiry",
            "工单派发调度": "ticket_dispatch",
            "客户投诉闭环": "customer_complaint",
            "服务回访安排": "service_followup",
            "服务评价采集": "service_evaluation",
            "客户签收与验收结论": "customer_acceptance_conclusion",
        }

        for index, (title, expected) in enumerate(cases.items(), start=1):
            key = semantic_module_key(title, index, raw_key=f"domain_{index:02d}_75070")
            self.assertEqual(key, expected)
            self.assertFalse(is_placeholder_module_key(key))

    def test_cached_admin_candidate_is_normalized_and_rescored_without_model_call(self):
        blueprint = generate_blueprint(self.task)
        blueprint.quality_score = 80
        blueprint.summary += " 生产主管通过手机 App 和移动端进入个人中心，并使用离线缓存。"
        blueprint.workflows[0]["trigger"] += "，随后从手机 App 进入个人中心"
        blueprint.modules[-1].title = "客户签收与验收结论"
        blueprint.modules[-1].key = "domain_08_72556"

        normalized = normalize_cached_blueprint_candidate(self.task, blueprint)
        normalized_text = json.dumps(normalized.to_dict(), ensure_ascii=False)

        self.assertEqual(normalized.quality_score, _quality_review(self.task, normalized)[0])
        self.assertEqual(normalized.modules[-1].key, "customer_acceptance_conclusion")
        self.assertEqual(blueprint_contract_issues(self.task, normalized), [])
        for term in ("移动端", "手机 App", "个人中心", "离线缓存"):
            self.assertNotIn(term, normalized_text)

    def test_accepted_blueprint_loader_requires_matching_identity_and_quality(self):
        blueprint = _valid_blueprint(self.task)
        source_modules = list(blueprint.modules)
        blueprint.modules = [deepcopy(source_modules[index % len(source_modules)]) for index in range(6)]
        for index, module in enumerate(blueprint.modules, start=1):
            module.key = f"accepted_module_{index}"
            module.title = f"批准业务模块{index}"
        blueprint.quality_score = 100
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "accepted-blueprint.json"
            path.write_text(json.dumps(blueprint.to_dict(), ensure_ascii=False), encoding="utf-8")
            task = GenerationTask(
                software_name=self.task.software_name,
                version=blueprint.version,
                product_type=self.task.product_type,
                accepted_blueprint_path=str(path),
            )

            loaded = _load_accepted_product_blueprint(task)
            self.assertEqual(loaded.quality_score, 100)
            self.assertEqual([module.key for module in loaded.modules], [module.key for module in blueprint.modules])

            task.software_name = "其他软件"
            with self.assertRaisesRegex(RuntimeError, "软件名称"):
                _load_accepted_product_blueprint(task)

            task.software_name = self.task.software_name
            blueprint.quality_score = 82
            path.write_text(json.dumps(blueprint.to_dict(), ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "未达到当前阈值"):
                _load_accepted_product_blueprint(task)

    def test_workflow_cleanup_preserves_complete_long_steps(self):
        step = "读取生产工单、工艺路线、设备负荷和物料齐套状态后生成可执行排程方案并记录冲突原因"

        workflows = _clean_workflows([{"name": "排程流程", "trigger": "计划生效", "steps": [step, "校验资源冲突并输出结果", "采用目标排程方案并记录版本"], "output": "排程版本"}])

        self.assertEqual(workflows[0]["steps"][0], step)
        self.assertGreater(len(workflows[0]["steps"][0]), 32)

    def test_workflow_cleanup_completes_exactly_32_character_truncated_steps(self):
        step = "读取客户工单与服务记录并核对当前处理状态后提交协同人员继续跟进并反馈客户处理结果"
        step = step[:32]

        workflows = _clean_workflows(
            [{"name": "协同流程", "trigger": "工单提交", "steps": [step, "校验处理状态并输出结果", "记录协同结论并归档"], "output": "处理记录"}]
        )

        self.assertEqual(len(step), 32)
        self.assertGreater(len(workflows[0]["steps"][0]), 32)
        self.assertTrue(workflows[0]["steps"][0].endswith("系统记录处理结果。"))

    def test_final_validator_requires_contract_for_all_generation_modes(self):
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
                    "blueprint_task_domain_ready": True,
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
                checks={"blueprint_operation_contract_ready": False, "blueprint_task_domain_ready": True},
            )

        gpt_codes = {item["code"] for item in gpt_validation["findings"]}
        local_codes = {item["code"] for item in local_validation["findings"]}
        self.assertTrue(gpt_validation["authenticity"]["blueprint_operation_contract_required"])
        self.assertFalse(gpt_validation["authenticity"]["blueprint_operation_contract_ready"])
        self.assertIn("blueprint_operation_contract_not_ready", gpt_codes)
        self.assertTrue(local_validation["authenticity"]["blueprint_operation_contract_required"])
        self.assertFalse(local_validation["authenticity"]["blueprint_operation_contract_ready"])
        self.assertIn("blueprint_operation_contract_not_ready", local_codes)

    def test_normal_blueprint_module_path_uses_four_batches_and_six_total_requests(self):
        outline = [
            {"key": f"manufacturing_module_{index}", "title": f"生产执行模块{index}", "focus": "制造现场业务"}
            for index in range(1, 9)
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

        self.assertEqual(len(modules), 8)
        self.assertEqual(call_labels, [f"模块明细批次{index}" for index in range(1, 5)])
        self.assertEqual(2 + len(call_labels), 6)
        self.assertEqual([item["key"] for item in modules], [item["key"] for item in outline])
        self.assertEqual([item["title"] for item in modules], [item["title"] for item in outline])

    def test_failed_module_batches_are_combined_into_one_repair_request(self):
        outline = [
            {"key": f"manufacturing_module_{index}", "title": f"生产执行模块{index}", "focus": "制造现场业务"}
            for index in range(1, 9)
        ]
        call_labels = []

        def valid_module(index):
            title = f"生产执行模块{index}"
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
            if label == "模块明细聚合修复":
                return {"modules": [valid_module(index) for index in range(1, 9)]}
            batch_index = int(label[-1])
            return {"modules": [valid_module(batch_index * 2 - 1), valid_module(batch_index * 2)]}

        quality_calls = {"batch": 0}

        def quality_reasons(_task, _modules, *, expected_count):
            if expected_count == 2:
                quality_calls["batch"] += 1
                return ["模拟模块仍不合格"]
            return []

        with patch.dict("os.environ", {"SOFT_GENERATION_PROFILE": "balanced", "SOFT_LLM_BATCH_WORKERS": "1"}), patch(
            "backend.softcopyright.llm_blueprint._chat_json",
            side_effect=chat_json,
        ), patch(
            "backend.softcopyright.llm_blueprint._module_batch_quality_reasons",
            side_effect=quality_reasons,
        ):
            modules = _generate_module_batches(self.task, object(), {"module_outline": outline}, [], "")

        self.assertEqual(len(modules), 8)
        self.assertEqual(quality_calls["batch"], 4)
        self.assertEqual(call_labels.count("模块明细聚合修复"), 1)
        self.assertEqual(len(call_labels), 5)
        self.assertEqual(2 + len(call_labels) + 1, 8)

    def test_confirmed_operation_contract_skips_all_module_detail_requests(self):
        task = GenerationTask(
            software_name=self.task.software_name,
            product_type=self.task.product_type,
            feature_hint=self.task.feature_hint,
            seed="confirmed-contract-zero-module-requests",
        )
        contract_blueprint = _valid_blueprint(task)
        task.semantic_contract = {
            "feature_hint_blueprint_modules": [
                {
                    "key": module.key,
                    "title": module.title,
                    "category": "生产执行",
                    "description": module.description,
                    "data_objects": module.entities,
                    "entities": module.entities,
                    "operations": module.operations,
                    "operation_specs": module.operation_specs,
                    "data_fields": module.data_fields,
                    "pages": module.pages,
                    "rules": module.rules,
                }
                for module in (contract_blueprint.modules * 3)[:6]
            ]
        }
        for index, module in enumerate(task.semantic_contract["feature_hint_blueprint_modules"], start=1):
            module["key"] = f"confirmed_module_{index}"
            module["title"] = f"确认生产模块{index}"

        with patch("backend.softcopyright.llm_blueprint._generate_module_batches") as batch_generation:
            result = _generate_modules(task, object(), {}, [])

        batch_generation.assert_not_called()
        self.assertEqual(len(result["modules"]), 6)

    def test_confirmed_outline_without_operation_specs_is_completed_locally(self):
        task = GenerationTask(
            software_name="Figma浏览器",
            product_type="APP",
            feature_hint="设计文件浏览、画板预览、图层检查、原型演示",
            seed="confirmed-outline-local-completion",
        )
        task.semantic_contract = {
            "feature_hint_domain": "Figma设计文件浏览与预览",
            "feature_hint_keywords": ["设计文件", "画板", "图层", "组件", "原型"],
            "feature_hint_avoid_terms": ["通用网页浏览器", "搜索引擎"],
            "feature_hint_blueprint_modules": [
                {
                    "key": f"figma_module_{index}",
                    "category": "设计预览",
                    "title": f"设计资源模块{index}",
                    "description": "围绕设计文件、页面画板和图层对象提供浏览、定位、查看与结果反馈，保留访问状态和操作记录。",
                    "data_objects": ["设计文件", "页面画板", "图层对象"],
                    "screens": ["设计资源页", "画板详情页"],
                }
                for index in range(1, 9)
            ],
        }

        with patch("backend.softcopyright.llm_blueprint._generate_module_batches") as batch_generation:
            result = _generate_modules(task, object(), {}, [])

        batch_generation.assert_not_called()
        self.assertEqual(len(result["modules"]), 8)
        self.assertTrue(all(len(module["operation_specs"]) >= 3 for module in result["modules"]))
        self.assertTrue(all(len(module["data_fields"]) >= 7 for module in result["modules"]))

    def test_approved_contract_removes_exact_off_domain_phrases_before_review(self):
        task = GenerationTask(software_name="Figma浏览器", product_type="APP")
        task.semantic_contract = {
            "feature_hint_domain": "Figma设计文件浏览与预览",
            "feature_hint_keywords": ["设计文件", "画板预览"],
            "feature_hint_avoid_terms": ["通用网页浏览器", "搜索引擎"],
        }
        plan = {
            "positioning": "面向设计评审的通用网页浏览器",
            "summary": "使用搜索引擎定位设计文件",
            "business_objects": ["搜索引擎索引", "设计文件"],
        }

        reconciled = _reconcile_plan_with_contract(task, plan)
        joined = json.dumps(reconciled, ensure_ascii=False)

        self.assertNotIn("搜索引擎", joined)
        self.assertNotIn("通用网页浏览器", joined)
        self.assertIn("设计资源检索", joined)

    def test_confirmed_figma_outline_passes_with_two_core_requests(self):
        titles_and_objects = [
            ("Figma文件接入", "文件链接"),
            ("设计资源导航", "项目资源"),
            ("页面与画板预览", "页面画板"),
            ("图层与组件检查", "图层组件"),
            ("原型流程演示", "原型流程"),
            ("评论与评审查看", "评审评论"),
            ("设计版本追踪", "设计版本"),
            ("浏览记录与收藏", "收藏记录"),
        ]
        task = GenerationTask(
            software_name="Figma浏览器",
            product_type="APP",
            feature_hint="、".join(title for title, _object in titles_and_objects),
            seed="figma-two-request-contract",
        )
        task.semantic_contract = {
            "feature_hint_profile": "confirmed-outline",
            "feature_hint_domain": "Figma设计文件浏览与预览",
            "feature_hint_keywords": ["设计文件", "页面画板", "图层组件", "原型流程", "评审评论", "设计版本"],
            "feature_hint_target_users": ["UI/UX设计师", "产品经理", "设计评审参与者"],
            "feature_hint_avoid_terms": ["通用网页浏览器", "搜索引擎"],
            "feature_hint_blueprint_modules": [
                {
                    "key": f"figma_contract_{index}",
                    "category": "设计浏览",
                    "title": title,
                    "description": f"围绕{data_object}执行访问、定位、状态反馈和结果追踪，保留与设计文件关联的操作上下文和可见证据。",
                    "data_objects": [data_object, "设计文件", f"{data_object}状态"],
                    "screens": [f"{title}页", f"{data_object}详情页"],
                }
                for index, (title, data_object) in enumerate(titles_and_objects, start=1)
            ],
        }
        identity = {
            "industry": "Figma设计文件浏览与预览",
            "scenario": "设计团队文件预览与评审协作场景",
            "positioning": "使用搜索引擎的通用网页浏览器",
            "purpose": "支持设计资源浏览、画板预览和评审协作",
            "summary": "面向设计团队集中浏览文件、检查图层并跟踪评审结果。",
        }
        workflows = [
            {
                "name": f"{title}协作流程",
                "trigger": f"用户进入{title}工作区",
                "steps": [f"选择{data_object}", f"核对{data_object}访问状态", f"执行{title}操作", f"记录{data_object}结果"],
                "output": f"形成{data_object}结果记录",
            }
            for title, data_object in titles_and_objects[:3]
        ]
        business = {
            "business_objects": [data_object for _title, data_object in titles_and_objects],
            "workflows": workflows,
            "report_metrics": [],
            "quality_rules": [],
            "uniqueness_notes": [],
            "data_relations": ["项目资源包含设计文件", "设计文件包含页面画板", "评审评论关联画板锚点"],
            "deployment_topology": "桌面工作区访问设计文件服务并保存浏览状态。",
            "pages": [],
        }

        class Provider:
            def __init__(self):
                self.responses = iter((identity, business))

            def chat(self, *_args, **_kwargs):
                return json.dumps(next(self.responses), ensure_ascii=False)

        blueprint = generate_blueprint_with_llm(task, Provider())
        joined = json.dumps(blueprint.to_dict(), ensure_ascii=False)

        self.assertGreaterEqual(blueprint.quality_score, 86)
        self.assertEqual(blueprint.request_count, 2)
        self.assertEqual(len(blueprint.modules), 8)
        self.assertNotIn("搜索引擎", joined)
        self.assertNotIn("通用网页浏览器", joined)


if __name__ == "__main__":
    unittest.main()
