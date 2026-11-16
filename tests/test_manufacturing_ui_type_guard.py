import json
import unittest

from backend.softcopyright.architecture import (
    create_technical_architecture,
    normalize_technical_architecture_for_experience,
    select_technical_architecture,
)
from backend.softcopyright.blueprint import FeatureModule, ProductBlueprint, generate_blueprint
from backend.softcopyright.industry_subtypes import build_ui_design_brief, select_industry_subtype_for_context
from backend.softcopyright.generator import _is_transport_operation_context
from backend.softcopyright.models import GenerationTask
from backend.softcopyright.product_experience import build_product_experience_spec
from backend.softcopyright.screenshots import _is_transport_route_context
from backend.softcopyright.ui_blueprint import build_ui_blueprint, repair_ui_blueprint_contract, ui_matches_software_type


def _manufacturing_blueprint(task: GenerationTask) -> ProductBlueprint:
    module_titles = [
        "生产计划协同",
        "生产工单管控",
        "产线智能排程",
        "换线调度优化",
        "工序节拍监控",
        "在制品流转追踪",
        "设备停机响应",
        "产能预测与瓶颈识别",
    ]
    modules = [
        FeatureModule(
            key=f"manufacturing_{index}",
            title=title,
            description=f"围绕{title}维护生产数据、处理异常并跟踪执行结果。",
            entities=[f"ProductionRecord{index}"],
            operations=["查询", "调整", "确认", "导出"],
            data_fields=["生产编号", "产线", "状态", "更新时间"],
        )
        for index, title in enumerate(module_titles, start=1)
    ]
    return ProductBlueprint(
        software_name=task.software_name,
        version=task.version,
        language="Java",
        product_type=task.product_type,
        industry="智能制造与工业生产管理",
        purpose="提升生产计划、排程、现场执行和交付协同效率。",
        summary="结合订单、工单、产线、设备和质量检验数据优化生产路径与产能配置。",
        modules=modules,
        roles=["生产主管", "计划员", "调度员", "设备工程师"],
        pages=["生产首页", "排程甘特图", "工单详情"],
        dev_environment={},
        runtime_environment={},
        scenario="制造企业生产计划、车间执行、设备保障和交付监控",
        positioning="智能制造生产运营平台",
        business_objects=["主生产计划", "生产工单", "产线资源", "设备停机事件"],
        report_metrics=["计划达成率", "工单按期完工率", "产能利用率", "交付达成率"],
        quality_score=100,
    )


class ManufacturingUiTypeGuardTests(unittest.TestCase):
    def test_customer_service_installation_acceptance_app_uses_admin_workstation(self):
        task = GenerationTask(
            software_name="客户服务协同平台正式安装验收系统",
            product_type="APP",
            feature_hint="",
            seed="customer-service-installation-acceptance",
        )
        setattr(task, "input_feature_hint", "")

        experience = build_product_experience_spec(task)

        self.assertEqual(experience.experience_shape, "desktop_web")
        self.assertEqual(experience.renderer, "admin")
        self.assertEqual(select_technical_architecture(task).key, "web_service_console")
        normalized = normalize_technical_architecture_for_experience(
            task,
            None,
            create_technical_architecture("web_mobile_app"),
        )
        self.assertEqual(normalized.key, "web_service_console")
        self.assertEqual(normalized.source_strategy, "javascript_with_java_api")
        self.assertNotIn("移动端", json.dumps(normalized.to_dict(), ensure_ascii=False))

    def test_vr_mapping_product_does_not_use_training_identity(self):
        task = GenerationTask(
            software_name="测绘空间三维模型编辑平台",
            product_type="VR软件",
            feature_hint="空间模型导入、倾斜摄影、坐标配准、控制点、模型分块、纹理贴合和测绘成果导出",
            seed="vr-spatial-modeling-regression",
        )

        subtype = select_industry_subtype_for_context(task)
        experience = build_product_experience_spec(task)
        brief = build_ui_design_brief(task)
        serialized = json.dumps({"experience": experience.to_dict(), "brief": brief}, ensure_ascii=False)

        self.assertEqual(subtype.key, "vr_spatial_modeling")
        self.assertEqual(experience.industry_subtype_key, "vr_spatial_modeling")
        self.assertEqual(brief["industry_subtype_key"], "vr_spatial_modeling")
        for expected in ["空间模型", "坐标配准", "模型分块", "测绘成果"]:
            self.assertIn(expected, serialized)
        for forbidden in ["安全培训", "训练任务", "成绩评分", "体验学员"]:
            self.assertNotIn(forbidden, serialized)

    def test_community_booking_app_does_not_fall_back_to_rail_admin(self):
        task = GenerationTask(
            software_name="社区预约服务App二期",
            product_type="智慧城市软件",
            feature_hint="",
            model_provider="local-template",
            seed="community-booking-regression",
        )
        setattr(task, "input_feature_hint", "")

        subtype = select_industry_subtype_for_context(task)
        blueprint = generate_blueprint(task)
        experience = build_product_experience_spec(task, blueprint)
        ui_blueprint = build_ui_blueprint(task, blueprint)

        self.assertEqual(subtype.key, "community_service")
        self.assertEqual(blueprint.industry_subtype_key, "community_service")
        self.assertEqual(experience.renderer, "mobile_app")
        self.assertTrue(ui_matches_software_type(task, blueprint, ui_blueprint))
        self.assertIn("售后工单", json.dumps(ui_blueprint.to_dict(), ensure_ascii=False))
        self.assertNotIn("轨道交通", json.dumps(blueprint.to_dict(), ensure_ascii=False))

    def test_generic_smart_city_acceptance_name_does_not_select_rail_quality(self):
        task = GenerationTask(
            software_name="安装版零令牌验收系统",
            product_type="智慧城市软件",
            feature_hint="用户入口、首页导航、核心工作台、业务表单处理、记录查询、统计分析、消息提醒、系统设置",
            model_provider="local-template",
            seed="generic-smart-city-acceptance",
        )

        subtype = select_industry_subtype_for_context(task)
        blueprint = generate_blueprint(task)

        self.assertEqual(subtype.key, "business_ops")
        self.assertEqual(blueprint.industry_subtype_key, "business_ops")
        self.assertNotIn("轨道交通", json.dumps(blueprint.to_dict(), ensure_ascii=False))

    def test_ai_production_platform_uses_consistent_manufacturing_subtype(self):
        task = GenerationTask(
            software_name="智能生产效率提升平台",
            product_type="人工智能软件",
            software_category="应用软件",
            feature_hint="生产计划、工单、产线排程、节拍、在制品、设备停机、产能预测和良率改善",
            seed="manufacturing-regression",
        )
        blueprint = _manufacturing_blueprint(task)
        context = " ".join([blueprint.industry, blueprint.purpose, blueprint.summary] + [module.title for module in blueprint.modules])

        subtype = select_industry_subtype_for_context(task, context)
        experience = build_product_experience_spec(task, blueprint)
        brief = build_ui_design_brief(task, blueprint)
        ui_blueprint = build_ui_blueprint(task, blueprint)
        serialized = json.dumps(ui_blueprint.design_brief, ensure_ascii=False)

        self.assertEqual(subtype.key, "smart_manufacturing")
        self.assertEqual(experience.industry_subtype_key, "smart_manufacturing")
        self.assertEqual(experience.experience_shape, "industrial_hmi")
        self.assertEqual(brief["industry_subtype_key"], "smart_manufacturing")
        self.assertEqual(brief["industry_subtype"], "智能制造生产运营平台")
        self.assertEqual(ui_blueprint.design_brief["industry_subtype_key"], "smart_manufacturing")
        self.assertEqual(ui_blueprint.design_brief["industry_subtype"], "智能制造生产运营平台")
        self.assertEqual(
            ui_blueprint.design_brief["product_experience_spec"]["industry_subtype_key"],
            "smart_manufacturing",
        )
        self.assertTrue(ui_matches_software_type(task, blueprint, ui_blueprint))
        for forbidden in ["surgery_schedule", "transport_route", "手术", "患者", "麻醉", "干线", "支线", "站点接驳"]:
            self.assertNotIn(forbidden, serialized)
        for expected in ["生产", "工单", "产线", "排程", "节拍", "在制品"]:
            self.assertIn(expected, serialized)

    def test_production_scheduling_and_optimization_path_are_not_medical_or_transport(self):
        task = GenerationTask(
            software_name="生产排程路径优化系统",
            product_type="人工智能软件",
            feature_hint="依据工单和产线约束优化生产路径、换线顺序与设备负荷",
            seed="manufacturing-weak-terms",
        )
        subtype = select_industry_subtype_for_context(task, "生产排程、工艺路线、换线调度、设备负荷")
        self.assertEqual(subtype.key, "smart_manufacturing")

    def test_rail_construction_quality_name_overrides_conflicting_medical_ui_domain(self):
        task = GenerationTask(
            software_name="轨道交通施工质量分析检验大数据系统",
            product_type="医疗软件",
            feature_hint="标段、单位工程、施工工序、检验批、材料复检、质量问题整改与验收",
            seed="rail-quality-conflict",
        )
        modules = [
            FeatureModule(
                key=f"rail_quality_{index}",
                title=title,
                description=f"围绕{title}维护轨道交通工程施工质量数据并跟踪处理结果。",
                entities=[f"RailQualityRecord{index}"],
                operations=["查询", "检验", "整改", "验收"],
                data_fields=["标段编号", "工程部位", "检验状态", "责任人员"],
            )
            for index, title in enumerate(
                ["工程结构管理", "质量计划管理", "施工工序检验", "检验批评定", "材料进场复检", "质量问题整改", "验收归档", "质量趋势分析"],
                start=1,
            )
        ]
        blueprint = ProductBlueprint(
            software_name=task.software_name,
            version=task.version,
            language="Java",
            product_type=task.product_type,
            industry="轨道交通工程施工质量管理",
            purpose="对轨道交通标段和单位工程开展施工质量检验分析。",
            summary="覆盖质量计划、检验点、检验批、材料复检、问题整改和验收归档。",
            modules=modules,
            roles=["施工质量员", "监理工程师", "试验检测人员"],
            pages=["质量监控首页", "检验批详情", "整改验收"],
            dev_environment={},
            runtime_environment={},
            scenario="轨道交通施工现场质量检验与整改闭环",
            positioning="工程施工质量分析检验平台",
            quality_score=100,
        )

        subtype = select_industry_subtype_for_context(task, blueprint.summary)
        experience = build_product_experience_spec(task, blueprint)
        ui_blueprint = build_ui_blueprint(task, blueprint)
        serialized = json.dumps(ui_blueprint.design_brief, ensure_ascii=False)

        self.assertEqual(subtype.key, "rail_construction_quality")
        self.assertEqual(experience.industry_subtype_key, "rail_construction_quality")
        self.assertEqual(experience.experience_shape, "industrial_hmi")
        self.assertEqual(ui_blueprint.design_brief["industry_subtype"], "轨道交通施工质量分析系统")
        self.assertTrue(ui_matches_software_type(task, blueprint, ui_blueprint))
        self.assertFalse(_is_transport_operation_context(" ".join([task.software_name, blueprint.industry, blueprint.summary])))
        self.assertFalse(_is_transport_route_context(blueprint))
        for forbidden in ["inpatient_monitoring", "surgery_schedule", "住院患者", "手术", "麻醉", "病历"]:
            self.assertNotIn(forbidden, serialized)

        ui_blueprint.design_brief["industry_subtype_key"] = "inpatient_monitoring"
        ui_blueprint.design_brief["industry_subtype"] = "住院患者监测护理系统"
        ui_blueprint.design_brief["product_experience_spec"]["industry_subtype_key"] = "inpatient_monitoring"
        ui_blueprint.design_brief["product_experience_spec"]["industry_subtype"] = "住院患者监测护理系统"
        repaired = repair_ui_blueprint_contract(task, blueprint, ui_blueprint)
        self.assertIsNotNone(repaired)
        self.assertEqual(repaired.design_brief["industry_subtype_key"], "rail_construction_quality")
        self.assertTrue(ui_matches_software_type(task, blueprint, repaired))


if __name__ == "__main__":
    unittest.main()
