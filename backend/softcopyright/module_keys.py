from __future__ import annotations

import re
from typing import Iterable


GENERIC_MODULE_KEYS = {
    "module",
    "business",
    "business_module",
    "data",
    "data_module",
    "manage",
    "management",
    "system",
    "system_module",
    "common",
    "common_module",
    "businessrecord",
}


SUBTYPE_NUMBERED_KEY_PREFIXES = {
    "business_ops",
    "booking_miniapp",
    "campus_miniapp",
    "city_grid_gis",
    "clinic_emr",
    "cold_chain_iot",
    "commerce_app",
    "community_service",
    "cmp_platform",
    "credit_approval",
    "data_governance",
    "data_security",
    "edge_app_ops",
    "exam_training",
    "field_service",
    "hospital_inventory",
    "industrial_iot",
    "intelligent_review",
    "k12_teaching",
    "k8s_ops",
    "match_three",
    "mlops_platform",
    "payment_clearing",
    "private_network",
    "realtime_warehouse",
    "rpg_ops",
    "scenic_ticketing",
    "soc_platform",
    "surgery_schedule",
    "survey_mapping",
    "transport_route",
    "urban_event",
    "vr_showroom",
    "vr_training",
}


KEY_PHRASES: tuple[tuple[str, str], ...] = (
    ("质量缺陷整改复验", "quality_defect_rectification_reinspection"),
    ("缺陷整改复验", "defect_rectification_reinspection"),
    ("构件进场验收", "component_site_acceptance"),
    ("构件安装定位", "component_installation_positioning"),
    ("拼装节点", "assembly_joint"),
    ("连接质量", "connection_quality"),
    ("灌浆质量", "grouting_quality"),
    ("焊接质量", "welding_quality"),
    ("质量缺陷", "quality_defect"),
    ("整改复验", "rectification_reinspection"),
    ("装配式建筑", "prefabricated_building"),
    ("预制构件", "prefabricated_component"),
    ("构件安装", "component_installation"),
    ("进场验收", "site_acceptance"),
    ("整改", "rectification"),
    ("复验", "reinspection"),
    ("缺陷", "defect"),
    ("构件", "component"),
    ("安装", "installation"),
    ("灌浆", "grouting"),
    ("焊接", "welding"),
    ("服务预约", "service_booking"),
    ("门店核销", "store_redemption"),
    ("会员权益", "member_benefit"),
    ("消息推送", "message_delivery"),
    ("售后工单", "aftersales_ticket"),
    ("活动入口", "campaign_entry"),
    ("订单支付", "order_payment"),
    ("客户签收与验收结论", "customer_acceptance_conclusion"),
    ("客户签收", "customer_signoff"),
    ("验收结论", "acceptance_conclusion"),
    ("服务评价采集", "service_evaluation"),
    ("客户咨询", "customer_inquiry"),
    ("问题受理", "issue_intake"),
    ("工单派发", "ticket_dispatch"),
    ("协同处理", "collaborative_resolution"),
    ("客户投诉", "customer_complaint"),
    ("沟通记录", "communication_record"),
    ("服务回访", "service_followup"),
    ("服务评价", "service_evaluation"),
    ("评价采集", "evaluation_collection"),
    ("满意度", "satisfaction"),
    ("时效监控", "sla_monitoring"),
    ("手术申请", "surgery_request"),
    ("申请受理", "request_intake"),
    ("术前确认", "preop_confirmation"),
    ("确认清单", "checklist"),
    ("手术排班", "surgery_schedule"),
    ("排班编排", "schedule_planning"),
    ("术间分配", "operating_room_allocation"),
    ("手术室", "operating_room"),
    ("麻醉安排", "anesthesia_plan"),
    ("麻醉", "anesthesia"),
    ("手术团队", "surgical_team"),
    ("团队协调", "team_coordination"),
    ("器械包", "instrument_pack"),
    ("器械", "instrument"),
    ("准备跟踪", "preparation_tracking"),
    ("患者接台", "patient_turnover"),
    ("患者", "patient"),
    ("接台流转", "turnover_flow"),
    ("术后", "postop"),
    ("术前", "preop"),
    ("临床", "clinical"),
    ("科室", "department"),
    ("医生", "doctor"),
    ("护士", "nurse"),
    ("病历", "medical_record"),
    ("处方", "prescription"),
    ("诊疗", "diagnosis_treatment"),
    ("气道", "airway"),
    ("急救", "emergency"),
    ("演练", "drill"),
    ("考核", "assessment"),
    ("道路中线", "road_centerline"),
    ("中线测量", "centerline_survey"),
    ("中桩采集", "center_stake"),
    ("桩号定位", "stake_position"),
    ("桩号", "stake"),
    ("控制点", "control_point"),
    ("水准测量", "level_survey"),
    ("水准读数", "level_reading"),
    ("导线测量", "traverse_survey"),
    ("导线校核", "traverse_check"),
    ("横断面", "cross_section"),
    ("纵断面", "longitudinal_section"),
    ("放样偏差", "setting_out_deviation"),
    ("放样", "setting_out"),
    ("闭合差", "closure_error"),
    ("测绘成果", "survey_result"),
    ("成果包", "result_package"),
    ("航测", "aerial_survey"),
    ("实景三维", "real_scene_3d"),
    ("三维建模", "three_dimensional_model"),
    ("点云", "point_cloud"),
    ("倾斜摄影", "oblique_photography"),
    ("地图", "map"),
    ("地形", "terrain"),
    ("坐标", "coordinate"),
    ("高程", "elevation"),
    ("干线路径", "trunk_route"),
    ("支线路径", "branch_route"),
    ("路径资源", "route_resource"),
    ("资源编目", "resource_catalog"),
    ("路径特征", "route_profile"),
    ("运输节点", "transport_node"),
    ("节点衔接", "node_link"),
    ("路径匹配", "route_match"),
    ("匹配评估", "match_assessment"),
    ("衔接规则", "connection_rule"),
    ("规则配置", "rule_config"),
    ("适配问题", "adapt_issue"),
    ("跟踪处置", "tracking_resolution"),
    ("方案发布", "plan_publish"),
    ("运营统计", "operation_statistics"),
    ("线路", "route"),
    ("班次", "schedule"),
    ("接驳", "connection"),
    ("电力线路", "power_line"),
    ("线路拓扑", "line_topology"),
    ("设备台账", "asset_catalog"),
    ("运行工况", "operation_condition"),
    ("跳闸事件", "trip_event"),
    ("保护动作", "protection_action"),
    ("故障区段", "fault_section"),
    ("故障原因", "fault_cause"),
    ("巡检影像", "inspection_image"),
    ("停电范围", "outage_scope"),
    ("工业机器人", "industrial_robot"),
    ("机器人路径", "robot_path"),
    ("路径规划", "path_planning"),
    ("路径生成", "path_generation"),
    ("轨迹优化", "trajectory_optimization"),
    ("运动学建模", "kinematic_modeling"),
    ("正向运动学", "forward_kinematics"),
    ("逆向运动学", "inverse_kinematics"),
    ("雅可比", "jacobian"),
    ("碰撞检测", "collision_detection"),
    ("动态环境", "dynamic_environment"),
    ("仿真", "simulation"),
    ("可视化", "visualization"),
    ("任务调度", "task_scheduling"),
    ("接口", "interface"),
    ("设备接入", "device_access"),
    ("设备档案", "device_profile"),
    ("网关通道", "gateway_channel"),
    ("遥测数据", "telemetry_data"),
    ("远程指令", "remote_command"),
    ("设备告警", "device_alarm"),
    ("维保工单", "maintenance_ticket"),
    ("健康评分", "health_score"),
    ("实时数据", "realtime_data"),
    ("数据监控", "data_monitoring"),
    ("故障诊断", "fault_diagnosis"),
    ("故障预测", "fault_prediction"),
    ("运维工单", "maintenance_ticket"),
    ("能效", "energy_efficiency"),
    ("性能分析", "performance_analysis"),
    ("安全权限", "security_access"),
    ("权限管控", "access_control"),
    ("实时预警", "realtime_alert"),
    ("预警触发", "alert_trigger"),
    ("智能决策", "decision_support"),
    ("知识沉淀", "knowledge_base"),
    ("协同优化", "collaborative_optimization"),
    ("智能分析", "intelligent_analysis"),
    ("数据建模", "data_modeling"),
    ("监控看板", "monitor_dashboard"),
    ("设备协议", "device_protocol"),
    ("协议适配", "protocol_adapter"),
    ("边缘数据", "edge_data"),
    ("数据预处理", "data_preprocessing"),
    ("接入网关", "access_gateway"),
    ("数据采集", "data_collection"),
    ("元数据", "metadata"),
    ("数据目录", "data_catalog"),
    ("数据质量", "data_quality"),
    ("主数据", "master_data"),
    ("生产计划", "production_plan"),
    ("生产工单", "production_work_order"),
    ("智能排程", "smart_scheduling"),
    ("换线调度", "changeover_scheduling"),
    ("工序节拍", "process_takt"),
    ("在制品流转", "work_in_process_flow"),
    ("设备停机", "equipment_downtime"),
    ("产能预测", "capacity_forecast"),
    ("瓶颈识别", "bottleneck_detection"),
    ("良率改善", "yield_improvement"),
    ("交付达成", "delivery_performance"),
    ("智能排产", "smart_scheduling"),
    ("排产调度", "production_scheduling"),
    ("设备运维", "equipment_maintenance"),
    ("工艺参数", "process_parameter"),
    ("参数优化", "parameter_optimization"),
    ("质量管控", "quality_control"),
    ("人机协同", "human_machine_collaboration"),
    ("能源精细", "energy_management"),
    ("供应链协同", "supply_chain_collaboration"),
    ("生产效能", "production_efficiency"),
    ("全景看板", "panoramic_dashboard"),
    ("供应商", "supplier"),
    ("资质", "qualification"),
    ("审核", "review"),
    ("归档", "archive"),
    ("合同", "contract"),
    ("发票", "invoice"),
    ("风险", "risk"),
    ("统计", "statistics"),
    ("报表", "report"),
    ("配置", "config"),
    ("发布", "publish"),
    ("跟踪", "tracking"),
    ("受理", "intake"),
    ("维护", "maintenance"),
    ("编排", "planning"),
    ("协同", "coordination"),
    ("协调", "coordination"),
    ("流转", "flow"),
    ("清单", "checklist"),
)


def is_placeholder_module_key(value: str) -> bool:
    key = _ascii_key(value)
    if not key:
        return True
    if key in GENERIC_MODULE_KEYS:
        return True
    subtype_prefix_match = re.fullmatch(r"([a-z][a-z0-9_]*?)_(\d{1,2})", key)
    if subtype_prefix_match and subtype_prefix_match.group(1) in SUBTYPE_NUMBERED_KEY_PREFIXES:
        return True
    return bool(
        re.fullmatch(r"(?:confirmed|semantic|module)(?:_\d+.*|\d*)", key)
        or re.fullmatch(r"domain_(?:\d+_)?[0-9a-f]{4,}", key)
        or re.fullmatch(r"(?:business|data|system|common)_module(?:_\d+)?", key)
        or re.fullmatch(r"business_process(?:_\d+|\d+)?", key)
        or re.fullmatch(r"(?:route|maintenance|checklist)(?:_\d+|\d{2,})", key)
    )


def semantic_module_key(
    title: str,
    index: int,
    *,
    raw_key: str = "",
    used: Iterable[str] | None = None,
    context_terms: Iterable[str] | None = None,
) -> str:
    used_keys = {_ascii_key(item) for item in (used or []) if _ascii_key(item)}
    candidate = _ascii_key(raw_key)
    if candidate and not is_placeholder_module_key(candidate) and candidate not in used_keys:
        return _reserved_safe(candidate)

    title_tokens = _phrase_tokens(str(title or ""))
    tokens: list[str] = list(title_tokens)
    if len(tokens) < 2:
        context_text = " ".join(str(item or "") for item in (context_terms or []))
        tokens.extend(part for part in _phrase_tokens(context_text) if part not in tokens)
    if not tokens:
        tokens = ["business", "module"]
    key = _compact_tokens(tokens[:4])
    if key in GENERIC_MODULE_KEYS or is_placeholder_module_key(key):
        digest = _title_digest(str(title or "") or "business", index)
        key = f"capability_{digest}"
    key = _reserved_safe(key[:48])
    if key not in used_keys:
        return key
    base = key[:42].rstrip("_") or "business_module"
    suffix_index = max(1, int(index or 1))
    while True:
        candidate = f"{base}_{suffix_index:02d}"
        if candidate not in used_keys:
            return candidate[:48]
        suffix_index += 1


def normalize_entity_names(entities: list[str], key: str, index: int, *, old_key: str = "") -> list[str]:
    old_base = _entity_base(old_key)
    base = _entity_base(key) or f"Module{index}"
    result: list[str] = []
    for entity in entities:
        text = _safe_entity(entity)
        if not text or text == "BusinessRecord":
            continue
        if old_base and text.lower().startswith(old_base.lower()):
            continue
        if text not in result:
            result.append(text)
    while len(result) < 2:
        suffix = "Record" if not result else "Query"
        candidate = f"{base}{suffix}"
        if candidate not in result:
            result.append(candidate)
        else:
            result.append(f"{base}Detail")
    return result[:4]


def _ascii_key(value: str) -> str:
    key = str(value or "").strip()
    key = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key)
    key = re.sub(r"[^A-Za-z0-9_]+", "_", key).strip("_").lower()
    return re.sub(r"_+", "_", key)


def _compact_tokens(tokens: list[str]) -> str:
    result: list[str] = []
    for token in tokens:
        for part in str(token).split("_"):
            part = _ascii_key(part)
            if part and part not in result:
                result.append(part)
    return "_".join(result) or "business_module"


def _phrase_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for phrase, mapped in KEY_PHRASES:
        if phrase in text:
            tokens.extend(part for part in mapped.split("_") if part)
        if len(tokens) >= 4:
            break
    return tokens


def _reserved_safe(key: str) -> str:
    if key in {"login", "dashboard", "statistics", "index"}:
        return f"{key}_module"
    if key and key[0].isdigit():
        return f"module_{key}"
    return key or "business_module"


def _title_digest(title: str, index: int) -> str:
    value = str(title or "").strip() or f"module-{index}"
    checksum = sum((position + 1) * ord(char) for position, char in enumerate(value))
    return f"{max(1, int(index or 1)):02d}_{checksum % 100000:05d}"


def _entity_base(key: str) -> str:
    parts = [part for part in re.split(r"[_\W]+", _ascii_key(key)) if part]
    return "".join(part[:1].upper() + part[1:] for part in parts)


def _safe_entity(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", " ", str(value or ""))
    parts = [part for part in text.split() if part]
    return "".join(part[:1].upper() + part[1:] for part in parts)
