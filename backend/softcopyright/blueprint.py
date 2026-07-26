from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field

from .industry_subtypes import select_industry_subtype, subtype_module_specs
from .models import GenerationTask


@dataclass
class FeatureModule:
    key: str
    title: str
    description: str
    entities: list[str]
    operations: list[str] = field(default_factory=list)
    data_fields: list[str] = field(default_factory=list)
    pages: list[str] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)
    operation_specs: list[dict[str, object]] = field(default_factory=list)


@dataclass
class ProductBlueprint:
    software_name: str
    version: str
    language: str
    product_type: str
    industry: str
    purpose: str
    summary: str
    modules: list[FeatureModule]
    roles: list[str]
    pages: list[str]
    dev_environment: dict[str, str]
    runtime_environment: dict[str, str]
    scenario: str = ""
    positioning: str = ""
    target_users: list[str] = field(default_factory=list)
    business_objects: list[str] = field(default_factory=list)
    workflows: list[dict[str, list[str] | str]] = field(default_factory=list)
    report_metrics: list[str] = field(default_factory=list)
    technical_features: list[str] = field(default_factory=list)
    quality_rules: list[str] = field(default_factory=list)
    data_relations: list[str] = field(default_factory=list)
    deployment_topology: str = ""
    uniqueness_notes: list[str] = field(default_factory=list)
    generation_fingerprint: str = ""
    quality_score: int = 0
    industry_subtype_key: str = ""
    industry_subtype: str = ""
    technical_architecture: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "software_name": self.software_name,
            "version": self.version,
            "language": self.language,
            "product_type": self.product_type,
            "industry": self.industry,
            "purpose": self.purpose,
            "summary": self.summary,
            "modules": [module.__dict__ for module in self.modules],
            "roles": self.roles,
            "pages": self.pages,
            "dev_environment": self.dev_environment,
            "runtime_environment": self.runtime_environment,
            "scenario": self.scenario,
            "positioning": self.positioning,
            "target_users": self.target_users,
            "business_objects": self.business_objects,
            "workflows": self.workflows,
            "report_metrics": self.report_metrics,
            "technical_features": self.technical_features,
            "quality_rules": self.quality_rules,
            "data_relations": self.data_relations,
            "deployment_topology": self.deployment_topology,
            "uniqueness_notes": self.uniqueness_notes,
            "generation_fingerprint": self.generation_fingerprint,
            "quality_score": self.quality_score,
            "industry_subtype_key": self.industry_subtype_key,
            "industry_subtype": self.industry_subtype,
            "technical_architecture": self.technical_architecture,
        }


PRODUCT_PRESETS: dict[str, dict] = {
    "智慧城市软件": {
        "industry": "城市治理与公共服务",
        "roles": ["系统管理员", "业务审核员", "运营人员", "统计分析员"],
        "modules": [
            ("dashboard", "综合态势看板", "汇总业务运行、预警事件、处理进度和统计指标。", ["OverviewMetric", "WarningEvent"]),
            ("resource", "公共资源管理", "维护区域、设备、服务网点和基础档案。", ["ResourceProfile", "AreaNode"]),
            ("ticketing", "票务订单管理", "支持票种配置、订单查询、退改审核和核验记录。", ["TicketProduct", "TicketOrder"]),
            ("access", "门禁通行管理", "管理闸机设备、通行策略、核验流水和异常放行。", ["GateDevice", "AccessRecord"]),
            ("member", "游客会员管理", "维护游客资料、年卡信息、团队预约和身份核验。", ["VisitorProfile", "MemberCard"]),
            ("report", "统计报表分析", "按时间、区域、渠道和设备生成经营统计报表。", ["ReportQuery", "ReportResult"]),
            ("permission", "权限与日志审计", "管理用户角色、菜单权限、登录日志和操作审计。", ["UserAccount", "AuditLog"]),
        ],
    },
    "APP": {
        "industry": "移动互联网服务",
        "roles": ["平台管理员", "移动端用户", "运营人员", "客服人员"],
        "modules": [
            ("account", "账号与认证", "提供注册、登录、实名认证、设备绑定和安全校验。", ["UserAccount", "AuthToken"]),
            ("home", "移动首页服务", "聚合推荐内容、快捷入口、消息提醒和活动信息。", ["HomeCard", "NoticeItem"]),
            ("order", "订单业务管理", "处理提交、支付、取消、售后和进度跟踪。", ["ServiceOrder", "OrderStatus"]),
            ("message", "消息通知中心", "管理站内信、推送通知、订阅提醒和已读状态。", ["MessageRecord", "PushTask"]),
            ("profile", "个人中心管理", "维护用户资料、地址、偏好设置和隐私配置。", ["UserProfile", "PreferenceSetting"]),
            ("analytics", "运营数据分析", "统计访问、转化、活跃和留存等移动端指标。", ["AppMetric", "RetentionData"]),
        ],
    },
    "金融软件": {
        "industry": "金融服务",
        "roles": ["风控管理员", "业务经办员", "复核人员", "财务人员"],
        "modules": [
            ("customer", "客户资料管理", "维护客户基础资料、认证信息和风险等级。", ["CustomerProfile", "RiskLevel"]),
            ("product", "金融产品管理", "配置产品要素、费率规则、额度策略和上下架状态。", ["FinanceProduct", "RateRule"]),
            ("transaction", "交易流水管理", "记录交易申请、资金流向、清算状态和异常处理。", ["TransactionRecord", "SettlementBatch"]),
            ("risk", "风险控制管理", "执行黑名单、限额、反欺诈和规则命中分析。", ["RiskRule", "RiskHit"]),
            ("audit", "审批复核管理", "处理业务审批、复核意见、授权流程和留痕记录。", ["ApprovalTask", "ReviewOpinion"]),
            ("report", "监管报表管理", "生成业务规模、风险暴露和资金统计报表。", ["RegulatoryReport", "FinanceMetric"]),
        ],
    },
    "医疗软件": {
        "industry": "医疗卫生",
        "roles": ["医生", "护士", "医务管理员", "统计人员"],
        "modules": [
            ("patient", "患者档案管理", "维护患者基本信息、就诊记录、过敏史和联系信息。", ["PatientProfile", "VisitRecord"]),
            ("appointment", "预约排班管理", "支持科室排班、医生号源、预约登记和取消处理。", ["SchedulePlan", "AppointmentOrder"]),
            ("clinic", "诊疗业务管理", "记录主诉、诊断、处方、医嘱和检查申请。", ["ClinicRecord", "Prescription"]),
            ("medicine", "药品库存管理", "维护药品目录、库存批次、出入库和效期预警。", ["DrugCatalog", "InventoryBatch"]),
            ("quality", "质控与随访", "跟踪诊疗质量、随访计划、回访结果和异常提醒。", ["FollowUpTask", "QualityCheck"]),
            ("report", "医疗统计报表", "统计门诊量、处方量、药品使用和科室工作量。", ["MedicalReport", "DepartmentMetric"]),
        ],
    },
    "教育软件": {
        "industry": "教育培训",
        "roles": ["教务管理员", "教师", "学生", "家长"],
        "modules": [
            ("course", "课程资源管理", "维护课程目录、章节内容、课件资料和学习目标。", ["Course", "Lesson"]),
            ("classroom", "班级教学管理", "管理班级、学员、授课计划和课堂记录。", ["ClassGroup", "TeachingPlan"]),
            ("homework", "作业测评管理", "发布作业、批改结果、错题统计和成绩分析。", ["Homework", "ScoreRecord"]),
            ("learning", "学习过程跟踪", "记录学习进度、观看时长、测验结果和行为轨迹。", ["LearningProgress", "StudyTrace"]),
            ("notice", "通知沟通管理", "发送班级通知、家校消息、课程提醒和回执。", ["Notice", "ReplyReceipt"]),
            ("report", "教学质量分析", "统计学习效果、课程完成率和班级综合表现。", ["TeachingReport", "LearningMetric"]),
        ],
    },
    "游戏软件": {
        "industry": "互动娱乐与数字内容",
        "roles": ["运营管理员", "内容策划", "玩家用户", "客服人员"],
        "modules": [
            ("player", "玩家账号管理", "维护玩家资料、登录状态、等级经验、封禁记录和实名认证信息。", ["PlayerProfile", "PlayerStatus"]),
            ("character", "角色资产管理", "管理角色属性、装备背包、技能等级、道具流水和资产变更记录。", ["GameCharacter", "InventoryItem"]),
            ("level", "关卡任务管理", "配置关卡章节、任务目标、奖励规则、通关条件和进度记录。", ["LevelConfig", "QuestProgress"]),
            ("match", "匹配对战管理", "处理房间创建、队伍匹配、对战结果、积分排名和异常结算。", ["MatchRoom", "BattleResult"]),
            ("activity", "运营活动管理", "配置签到、礼包、限时活动、公告推送和奖励发放策略。", ["GameActivity", "RewardRule"]),
            ("payment", "充值订单管理", "记录商品配置、支付订单、发货状态、退款审核和对账结果。", ["PaymentOrder", "GoodsPackage"]),
            ("anti_cheat", "安全风控管理", "识别异常登录、外挂行为、刷分风险和敏感操作审计。", ["CheatSignal", "RiskDecision"]),
        ],
    },
    "地理信息软件": {
        "industry": "地理信息与空间数据服务",
        "roles": ["GIS管理员", "数据采集员", "地图审核员", "业务分析员"],
        "modules": [
            ("map_layer", "地图图层管理", "维护基础底图、业务图层、图层样式、显示顺序和可见范围。", ["MapLayer", "LayerStyle"]),
            ("spatial_data", "空间数据管理", "管理点线面要素、坐标信息、属性字段、版本记录和数据质量。", ["SpatialFeature", "GeoAttribute"]),
            ("survey", "外业采集管理", "支持采集任务、轨迹上传、照片附件、位置校验和审核入库。", ["SurveyTask", "TrackPoint"]),
            ("geocoding", "地址解析管理", "提供地址匹配、坐标转换、行政区划归属和异常地址处理。", ["GeoCodingJob", "AddressMatch"]),
            ("analysis", "空间分析管理", "执行缓冲区、叠加分析、范围查询、热力统计和结果输出。", ["SpatialAnalysis", "AnalysisResult"]),
            ("thematic", "专题图管理", "生成专题地图、图例配置、指标渲染、标注规则和地图导出。", ["ThematicMap", "LegendConfig"]),
            ("publish", "地图服务发布", "管理服务目录、访问权限、瓦片缓存、服务状态和调用日志。", ["MapService", "TileCache"]),
        ],
    },
    "云计算软件": {
        "industry": "云资源管理与运维服务",
        "roles": ["云平台管理员", "租户管理员", "运维人员", "审计人员"],
        "modules": [
            ("tenant", "租户组织管理", "维护租户、项目、配额、成员、角色授权和资源归属关系。", ["CloudTenant", "ProjectQuota"]),
            ("compute", "计算资源管理", "管理云主机、镜像、规格、启动策略、重启回收和运行状态。", ["ComputeInstance", "ImageProfile"]),
            ("storage", "存储资源管理", "维护云硬盘、对象存储、快照备份、容量统计和生命周期策略。", ["StorageVolume", "SnapshotPolicy"]),
            ("network", "网络资源管理", "配置虚拟网络、子网、安全组、负载均衡和访问控制规则。", ["VirtualNetwork", "SecurityRule"]),
            ("monitor", "云监控告警", "采集CPU、内存、磁盘、流量等指标并触发阈值告警。", ["MetricSample", "AlarmRule"]),
            ("billing", "计量计费管理", "统计资源用量、账单明细、费用分摊、余额预警和导出报表。", ["UsageBill", "CostAllocation"]),
            ("automation", "自动化运维", "编排巡检任务、批量脚本、故障自愈、操作审批和执行日志。", ["OpsTask", "RunbookLog"]),
        ],
    },
    "信息安全软件": {
        "industry": "网络安全与数据安全",
        "roles": ["安全管理员", "策略审核员", "事件处置员", "合规审计员"],
        "modules": [
            ("asset", "安全资产管理", "维护主机、应用、数据库、账号、端口和责任人信息。", ["SecurityAsset", "AssetOwner"]),
            ("policy", "安全策略管理", "配置访问控制、密码策略、基线规则、白名单和例外审批。", ["SecurityPolicy", "PolicyException"]),
            ("vulnerability", "漏洞风险管理", "记录漏洞扫描、风险等级、修复状态、复测结果和处置闭环。", ["VulnerabilityItem", "FixTask"]),
            ("event", "安全事件管理", "汇聚告警事件、攻击来源、影响范围、处置步骤和事件结论。", ["SecurityEvent", "IncidentAction"]),
            ("audit", "日志审计管理", "采集登录、操作、访问、变更和导出日志并支持检索追踪。", ["AuditRecord", "LogQuery"]),
            ("compliance", "合规检查管理", "执行等保、内控、数据安全检查项、整改任务和报告生成。", ["ComplianceCheck", "RectifyTask"]),
            ("risk", "风险态势分析", "统计资产风险、事件趋势、漏洞分布、处置效率和风险评分。", ["RiskMetric", "ThreatTrend"]),
        ],
    },
    "大数据软件": {
        "industry": "数据治理与分析服务",
        "roles": ["数据管理员", "数据开发员", "数据分析师", "运维监控员"],
        "modules": [
            ("source", "数据源管理", "维护数据库、接口、文件、消息队列等数据源连接和权限配置。", ["DataSource", "ConnectionConfig"]),
            ("ingestion", "数据采集管理", "配置采集任务、调度周期、增量规则、失败重试和采集日志。", ["IngestionJob", "CollectLog"]),
            ("quality", "数据质量管理", "执行完整性、唯一性、准确性、及时性校验并生成质量报告。", ["QualityRule", "QualityReport"]),
            ("warehouse", "数据仓库管理", "管理主题域、数据表、字段血缘、分层模型和生命周期。", ["WarehouseTable", "DataLineage"]),
            ("analysis", "数据分析管理", "支持指标定义、查询任务、多维分析、结果缓存和数据导出。", ["AnalysisQuery", "MetricDefinition"]),
            ("visualization", "可视化看板", "配置图表组件、看板布局、数据刷新、权限发布和订阅提醒。", ["DashboardView", "ChartWidget"]),
            ("governance", "数据治理管理", "维护数据目录、标签、标准、权限审批和敏感数据识别。", ["DataCatalog", "SensitiveTag"]),
        ],
    },
    "人工智能软件": {
        "industry": "人工智能算法应用",
        "roles": ["算法管理员", "标注人员", "模型训练员", "业务审核员"],
        "modules": [
            ("dataset", "数据集管理", "维护训练数据、标注结果、样本分组、版本记录和质量状态。", ["DatasetProfile", "SampleItem"]),
            ("annotation", "数据标注管理", "支持文本、图片、语音等标注任务分配、审核和返工处理。", ["AnnotationTask", "LabelResult"]),
            ("training", "模型训练管理", "配置训练参数、算法版本、训练任务、资源占用和训练日志。", ["TrainingJob", "ModelParam"]),
            ("model", "模型版本管理", "管理模型文件、版本对比、评估指标、发布状态和回滚记录。", ["ModelVersion", "EvaluationMetric"]),
            ("inference", "推理服务管理", "提供模型部署、接口调用、批量预测、结果解释和调用日志。", ["InferenceService", "PredictRecord"]),
            ("review", "智能审核管理", "对模型结果进行人工复核、风险标注、结论确认和纠错反馈。", ["ReviewTask", "AuditConclusion"]),
            ("monitor", "模型监控分析", "监控准确率、召回率、漂移情况、延迟性能和异常告警。", ["ModelMonitor", "DriftSignal"]),
        ],
    },
    "VR软件": {
        "industry": "虚拟现实与沉浸式交互",
        "roles": ["内容管理员", "设备管理员", "体验用户", "运营人员"],
        "modules": [
            ("scene", "虚拟场景管理", "维护三维场景、空间节点、材质资源、灯光配置和场景版本。", ["VrScene", "SceneAsset"]),
            ("device", "VR设备管理", "管理头显、手柄、定位器、设备状态、固件版本和故障记录。", ["VrDevice", "DeviceStatus"]),
            ("interaction", "交互脚本管理", "配置触发区域、交互动作、手势识别、反馈效果和脚本流程。", ["InteractionScript", "GestureRule"]),
            ("training", "沉浸培训管理", "维护课程章节、训练任务、评分规则、操作步骤和学习进度。", ["VrTraining", "TrainingScore"]),
            ("experience", "体验记录管理", "记录用户进入场景、停留时长、操作轨迹、完成结果和异常退出。", ["ExperienceRecord", "MotionTrace"]),
            ("content", "资源素材管理", "管理模型、贴图、音频、视频、动画和资源审核状态。", ["MediaAsset", "AssetReview"]),
            ("statistics", "体验统计分析", "统计设备使用率、场景热度、训练成绩、异常次数和用户反馈。", ["VrMetric", "FeedbackRecord"]),
        ],
    },
    "5G软件": {
        "industry": "5G网络与边缘应用",
        "roles": ["网络管理员", "边缘节点管理员", "业务运营员", "监控人员"],
        "modules": [
            ("site", "基站站点管理", "维护站点位置、设备编号、覆盖范围、运行状态和维护记录。", ["BaseStation", "SiteCoverage"]),
            ("slice", "网络切片管理", "配置切片模板、带宽策略、业务等级、资源隔离和开通状态。", ["NetworkSlice", "SlicePolicy"]),
            ("edge", "边缘节点管理", "管理边缘服务器、应用实例、资源配额、部署状态和健康检查。", ["EdgeNode", "EdgeApp"]),
            ("terminal", "终端接入管理", "记录终端设备、SIM信息、接入状态、流量使用和异常离线。", ["TerminalDevice", "AccessSession"]),
            ("qos", "服务质量管理", "监控时延、丢包、吞吐、连接数和业务质量评分。", ["QosMetric", "QualityScore"]),
            ("alarm", "网络告警管理", "汇总站点、链路、设备、应用告警并跟踪处置进度。", ["NetworkAlarm", "AlarmProcess"]),
            ("traffic", "流量分析管理", "统计区域流量、业务流量、终端排行、趋势预测和报表导出。", ["TrafficSample", "TrafficReport"]),
        ],
    },
    "小程序": {
        "industry": "轻应用与线上服务",
        "roles": ["平台管理员", "小程序用户", "运营人员", "审核人员"],
        "modules": [
            ("user", "用户授权管理", "处理微信授权、手机号绑定、用户资料、会话状态和隐私设置。", ["MiniUser", "AuthSession"]),
            ("home", "首页内容管理", "配置轮播图、快捷入口、公告资讯、推荐内容和展示排序。", ["HomeBanner", "QuickEntry"]),
            ("service", "服务预约管理", "支持服务分类、预约下单、时间选择、取消变更和状态跟踪。", ["ServiceBooking", "TimeSlot"]),
            ("order", "订单支付管理", "管理订单创建、支付回调、退款申请、核销记录和对账明细。", ["MiniOrder", "PaymentCallback"]),
            ("coupon", "营销优惠管理", "配置优惠券、活动规则、领取记录、使用限制和过期提醒。", ["CouponRule", "CouponRecord"]),
            ("message", "订阅消息管理", "维护消息模板、触发场景、发送记录、失败重试和已读状态。", ["SubscribeMessage", "SendRecord"]),
            ("operation", "运营数据分析", "统计访问量、转化率、订单量、用户留存和渠道来源。", ["MiniMetric", "ChannelSource"]),
        ],
    },
    "物联网软件": {
        "industry": "物联网设备管理与数据监测",
        "roles": ["设备管理员", "运维人员", "业务监控员", "告警处置员"],
        "modules": [
            ("device", "设备档案管理", "维护设备编号、型号、位置、协议、状态、责任人和安装记录。", ["IotDevice", "DeviceProfile"]),
            ("gateway", "网关接入管理", "管理网关配置、协议适配、连接状态、通道映射和转发规则。", ["IotGateway", "ProtocolChannel"]),
            ("telemetry", "数据采集管理", "采集温度、湿度、电量、压力、位置等指标并记录上报时间。", ["TelemetryData", "MetricPoint"]),
            ("command", "远程控制管理", "支持指令下发、参数设置、批量控制、执行回执和失败重试。", ["DeviceCommand", "CommandReceipt"]),
            ("alarm", "设备告警管理", "配置阈值规则、离线告警、异常数据、处置流程和告警通知。", ["DeviceAlarm", "AlarmRule"]),
            ("maintenance", "巡检维保管理", "维护巡检计划、维保任务、故障工单、处理结果和备件记录。", ["MaintenanceTask", "RepairOrder"]),
            ("analysis", "设备运行分析", "统计在线率、告警率、能耗趋势、设备健康度和区域分布。", ["IotAnalysis", "HealthScore"]),
        ],
    },
}

DEFAULT_PRESET = {
    "industry": "企业数字化管理",
    "roles": ["系统管理员", "业务操作员", "审核人员", "统计人员"],
    "modules": [
        ("dashboard", "业务首页看板", "展示核心指标、待办事项、业务趋势和异常提醒。", ["DashboardMetric", "TodoItem"]),
        ("archive", "基础档案管理", "维护业务对象、分类字典、区域组织和基础资料。", ["ArchiveRecord", "DictionaryItem"]),
        ("workflow", "业务流程管理", "支持业务申请、处理、审核、归档和状态跟踪。", ["WorkflowCase", "ProcessNode"]),
        ("query", "综合查询管理", "按条件检索业务数据、导出结果和查看详情。", ["QueryCondition", "QueryResult"]),
        ("report", "统计分析管理", "生成日常统计、趋势分析、分类汇总和业务报表。", ["ReportDefinition", "ReportData"]),
        ("system", "系统配置管理", "管理用户、角色、参数、日志和安全策略。", ["SystemUser", "SystemLog"]),
    ],
}


def generate_blueprint(task: GenerationTask) -> ProductBlueprint:
    preset = PRODUCT_PRESETS.get(task.product_type, DEFAULT_PRESET)
    seed_input = f"{task.software_name}|{task.version}|{task.language}|{task.product_type}|{task.feature_hint}|{task.seed}"
    seed_value = int(hashlib.sha256(seed_input.encode("utf-8")).hexdigest()[:12], 16)
    rng = random.Random(seed_value)
    subtype = select_industry_subtype(task)

    module_specs = subtype_module_specs(subtype, list(preset["modules"]))
    selected = _select_local_module_specs(task, module_specs, rng)

    modules = [
        FeatureModule(
            key=key,
            title=title,
            description=description,
            entities=entities,
            operations=_module_operations(title, rng, subtype.secondary_mix),
            data_fields=_module_data_fields(title, entities),
            pages=[f"{title}列表页", f"{title}详情页", f"{title}处理页"],
            rules=_module_rules(title),
        )
        for key, title, description, entities in selected
    ]
    for module_index, module in enumerate(modules):
        module.operation_specs = _local_operation_specs(
            module,
            roles=list(subtype.roles or tuple(preset["roles"])),
            module_index=module_index,
        )
        module.operations = [str(spec["label"]) for spec in module.operation_specs]
        module.description = _local_module_description(module)
    pages = ["登录页", "系统首页"] + [module.title for module in modules] + ["统计报表页", "系统设置页"]
    industry = subtype.industry or preset["industry"]
    scenario = _scenario_for_task(task, industry, modules, subtype.scenario)
    purpose = f"用于{industry}中的{subtype.scenario}，支撑{subtype.title}相关数据、流程、监控和统计分析。"
    summary = (
        f"{task.software_name}是一套面向{industry}的{subtype.title}，"
        f"围绕{', '.join(module.title for module in modules[:4])}等模块，"
        "提供真实业务对象维护、流程处理、权限控制、日志审计和报表分析能力。"
    )

    dev_environment = _environment_for_language(task.language)
    runtime_environment = _runtime_for_language(task.language)

    blueprint = ProductBlueprint(
        software_name=task.software_name,
        version=task.version,
        language=task.language,
        product_type=task.product_type,
        industry=industry,
        purpose=purpose,
        summary=summary,
        modules=modules,
        roles=list(subtype.roles or tuple(preset["roles"])),
        pages=pages,
        dev_environment=dev_environment,
        runtime_environment=runtime_environment,
        scenario=scenario,
        positioning=f"{subtype.positioning}，用于支撑{scenario}中的日常业务处理和数据留痕。",
        target_users=list(subtype.roles or tuple(preset["roles"])),
        business_objects=_merge_unique(list(subtype.domain_terms), _business_objects_from_modules(modules)),
        workflows=_workflow_cards(modules),
        report_metrics=_merge_unique(list(subtype.metrics), _report_metrics(modules)),
        technical_features=_technical_features(task),
        quality_rules=_quality_rules(modules),
        data_relations=_data_relations(modules),
        deployment_topology=_deployment_topology(task),
        uniqueness_notes=_uniqueness_notes(task, modules, subtype.title),
        generation_fingerprint=hashlib.sha256(seed_input.encode("utf-8")).hexdigest()[:16],
        industry_subtype_key=subtype.key,
        industry_subtype=subtype.title,
    )
    blueprint.quality_score = _local_quality_score(blueprint)
    return blueprint


def _select_local_module_specs(
    task: GenerationTask,
    module_specs: list[tuple[str, str, str, list[str]]],
    rng: random.Random,
) -> list[tuple[str, str, str, list[str]]]:
    input_hint = getattr(task, "input_feature_hint", None)
    input_text = f"{task.software_name} {input_hint if input_hint is not None else task.feature_hint}".strip()
    matched = [
        spec
        for spec in module_specs
        if _local_module_matches_input(spec[1], input_text)
    ]
    remaining = [spec for spec in module_specs if spec not in matched]
    rng.shuffle(remaining)
    base_count = 6 + (1 if task.randomness == "高差异" else 0)
    selected_count = min(len(module_specs), max(base_count, len(matched)))
    return [*matched, *remaining][:selected_count]


def _local_module_matches_input(title: str, input_text: str) -> bool:
    subject = _module_subject(title)
    terms = {str(title or ""), subject}
    if len(subject) >= 2:
        terms.update({subject[:2], subject[-2:]})
    return any(term and term in input_text for term in terms)


def _scenario_for_task(task: GenerationTask, industry: str, modules: list[FeatureModule], subtype_scenario: str = "") -> str:
    if task.feature_hint:
        return f"{industry}下的{subtype_scenario or task.feature_hint}协同场景"
    if subtype_scenario:
        return subtype_scenario
    if modules:
        return f"{industry}下的{modules[0].title}和{modules[min(1, len(modules) - 1)].title}协同场景"
    return f"{industry}下的业务协同场景"


def _module_operations(title: str, rng: random.Random, preferred_actions: tuple[str, ...] | None = None) -> list[str]:
    pool = ["登记", "查询", "编辑", "审核", "发布", "归档", "导入", "导出", "预警", "复核", "统计", "追踪"]
    preferred = [str(item).strip() for item in (preferred_actions or ()) if str(item).strip()]
    extras = [operation for operation in pool if operation not in preferred]
    rng.shuffle(extras)
    ordered = _merge_unique(preferred, extras)
    return [f"{title}{operation}" for operation in ordered[:5]]


def _module_data_fields(title: str, entities: list[str]) -> list[str]:
    subject = _module_subject(title)
    fields = [f"{subject}编号", *_semantic_fields(subject), "责任角色", "更新时间", "处理备注"]
    return _merge_unique(fields, [f"{entity}标识" for entity in entities[:2]])[:10]


def _module_rules(title: str) -> list[str]:
    return [
        f"{title}保存前必须校验必填字段和业务编码唯一性。",
        f"{title}状态变更必须记录操作人、操作时间和变更原因。",
        f"{title}导出和删除操作必须受角色权限控制。",
    ]


def _local_operation_specs(module: FeatureModule, *, roles: list[str], module_index: int) -> list[dict[str, object]]:
    subject = _module_subject(module.title)
    fields = [str(item) for item in (module.data_fields or []) if str(item).strip()]
    role = roles[module_index % len(roles)] if roles else "业务操作员"
    definitions = _semantic_operation_definitions(subject, module.key)
    return [
        {
            "action_key": f"{module.key}_{definition['action_key']}",
            "label": definition["label"],
            "category": definition["category"],
            "role": role,
            "trigger": definition["trigger"],
            "input_fields": _merge_unique(definition["input_fields"], fields)[:4],
            "pre_state": definition["pre_state"],
            "post_state": definition["post_state"],
            "result_evidence": definition["result_evidence"],
            "requires_confirmation": definition["requires_confirmation"],
        }
        for definition in definitions
    ]


def _module_subject(title: str) -> str:
    subject = str(title or "业务对象").strip()
    for suffix in ("管理", "系统", "平台", "中心"):
        subject = subject.removesuffix(suffix)
    return subject or str(title or "业务对象")


def _semantic_fields(subject: str) -> list[str]:
    profiles = [
        (("预约",), ["预约日期", "可用时段", "服务网点", "履约状态"]),
        (("排班", "排程", "计划"), ["计划版本", "执行周期", "资源范围", "冲突状态"]),
        (("核销",), ["核销码", "凭证类型", "有效期限", "核销状态"]),
        (("工单", "任务", "投诉", "售后", "处置"), ["受理渠道", "问题级别", "处理岗位", "处理时限"]),
        (("消息", "推送", "通知"), ["消息模板", "目标受众", "发送批次", "送达状态"]),
        (("活动", "推荐位", "专题"), ["活动周期", "参与范围", "发布状态", "报名人数"]),
        (("权益", "会员", "优惠券", "礼包"), ["权益类型", "适用人群", "有效期限", "发放状态"]),
        (("支付", "订单", "交易", "退款", "结算", "清算", "账单"), ["订单金额", "支付渠道", "回执编号", "对账状态"]),
        (("预警", "告警", "风险", "监测", "体征", "节拍"), ["监测指标", "阈值等级", "发生时间", "处置状态"]),
        (("设备", "网关", "主机", "节点", "实例", "终端"), ["设备型号", "接入位置", "在线状态", "最近心跳"]),
        (("库存", "批次", "耗材", "药品", "物料", "领用", "在制品"), ["物料批次", "可用数量", "库位", "效期日期"]),
        (("数据", "采集", "轨迹", "点位", "图层", "样本", "素材", "文件"), ["数据来源", "采集批次", "质量状态", "异常数量"]),
        (("模型", "训练", "推理", "算法"), ["模型版本", "数据集版本", "运行状态", "评估指标"]),
        (("审核", "审批", "复核", "质检", "检查", "验收"), ["申请编号", "提交人员", "审核状态", "结论时间"]),
        (("统计", "分析", "指标", "报表", "预测", "评分"), ["统计周期", "统计口径", "对比范围", "生成状态"]),
    ]
    for markers, fields in profiles:
        if any(marker in subject for marker in markers):
            return fields
    return [f"{subject}类型", f"{subject}状态", "生效时间", "责任岗位"]


def _operation_definition(
    action_key: str,
    label: str,
    category: str,
    input_fields: list[str],
    pre_state: str,
    post_state: str,
    result_evidence: str,
    *,
    confirmation: bool = False,
    trigger: str = "",
) -> dict[str, object]:
    return {
        "action_key": action_key,
        "label": label,
        "category": category,
        "trigger": trigger or f"需要{label}",
        "input_fields": input_fields,
        "pre_state": pre_state,
        "post_state": post_state,
        "result_evidence": result_evidence,
        "requires_confirmation": confirmation,
    }


def _semantic_operation_definitions(subject: str, module_key: str) -> list[dict[str, object]]:
    fields = _semantic_fields(subject)
    specialized = _specialized_operation_definitions(subject, fields)
    if specialized:
        return specialized
    profiles: list[tuple[tuple[str, ...], list[dict[str, object]]]] = [
        (("预约",), [
            _operation_definition("find_slot", f"查询{subject}可用安排", "lookup", fields[:3], "尚未选择安排范围", "显示可用时段与资源", "查询条件、可用时段和资源余量"),
            _operation_definition("create_booking", f"创建{subject}", "mutation", fields[:3], "安排尚未建立", "形成待确认安排", "安排编号、服务时段和责任岗位"),
            _operation_definition("adjust_slot", f"调整{subject}时段", "workflow", fields[:3], "安排时间存在冲突", "安排更新为待履约", "调整前后时段、冲突校验和操作日志"),
            _operation_definition("confirm_fulfillment", f"确认{subject}履约", "result", fields[:2], "服务已到达约定时点", "安排更新为已履约", "履约时间、确认人员和服务结果"),
        ]),
        (("排班", "排程", "计划"), [
            _operation_definition("find_version", f"查询{subject}版本", "lookup", fields[:3], "尚未选择计划周期", "显示匹配版本与资源负荷", "计划版本、执行周期和资源余量"),
            _operation_definition("check_constraints", f"校验{subject}资源约束", "analysis", fields[:3], "候选计划尚未完成约束检查", "形成冲突项与可执行判断", "资源冲突、产能差额和影响任务"),
            _operation_definition("release_plan", f"下达{subject}", "workflow", fields[:3], "计划版本已通过约束校验", "计划更新为已下达", "生效版本、下达岗位和执行范围", confirmation=True),
            _operation_definition("adjust_conflict", f"调整{subject}冲突", "result", fields[:3], "执行资源或时间发生冲突", "形成新的可执行计划版本", "调整前后版本、冲突消解结果和变更原因"),
        ]),
        (("核销",), [
            _operation_definition("find_voucher", f"查询待{subject}凭证", "lookup", fields[:3], "尚未定位有效凭证", "显示匹配的待核销凭证", "核销码、有效期限和凭证状态"),
            _operation_definition("verify_code", f"校验{subject}码", "workflow", fields[:3], "凭证尚未校验", "凭证通过有效性校验", "校验结果、适用门店和剩余次数"),
            _operation_definition("redeem", f"执行{subject}", "mutation", fields[:3], "凭证有效且尚未使用", "凭证更新为已核销", "核销流水、核销时间和操作门店", confirmation=True),
            _operation_definition("reverse_exception", f"冲正异常{subject}", "result", fields[:3], "核销流水存在业务差错", "异常流水更新为已冲正", "原流水、冲正原因和复核记录", confirmation=True),
        ]),
        (("工单", "任务", "投诉", "售后", "处置"), [
            _operation_definition("find_queue", f"查询{subject}队列", "lookup", fields[:3], "尚未筛选待办队列", "显示符合条件的待办事项", "优先级、处理时限和队列数量"),
            _operation_definition("accept", f"受理{subject}", "workflow", fields[:3], "事项处于待受理状态", "事项更新为已受理", "受理人员、受理时间和响应时限"),
            _operation_definition("assign", f"分派{subject}", "workflow", fields[:4], "事项已受理且责任岗位未确定", "事项更新为处理中", "处理岗位、分派时间和协同要求"),
            _operation_definition("record_resolution", f"登记{subject}处理结论", "result", fields[:3], "处理人员已完成处置", "事项更新为已解决", "处理结论、完成时间和客户反馈"),
        ]),
        (("消息", "推送", "通知"), [
            _operation_definition("find_send_task", f"查询{subject}任务", "lookup", fields[:3], "尚未选择发送批次", "显示匹配的发送任务", "模板名称、目标人数和发送状态"),
            _operation_definition("configure_audience", f"配置{subject}受众", "mutation", fields[:3], "发送范围尚未确定", "形成可预览的目标受众", "受众规则、预计人数和排除条件"),
            _operation_definition("publish", f"发布{subject}", "workflow", fields[:3], "内容和受众已通过校验", "发送任务进入执行状态", "发布批次、发布时间和送达进度", confirmation=True),
            _operation_definition("retry_failed", f"重试失败{subject}", "result", fields[:3], "发送批次存在失败记录", "失败记录进入重试队列", "失败原因、重试数量和最新状态"),
        ]),
        (("活动", "推荐位", "专题"), [
            _operation_definition("find_campaign", f"查询{subject}", "lookup", fields[:3], "尚未选择活动范围", "显示匹配活动及当前状态", "活动周期、参与范围和报名人数"),
            _operation_definition("configure_rules", f"配置{subject}规则", "mutation", fields[:3], "活动规则尚未完善", "活动更新为待发布", "参与规则、时间范围和权益配置"),
            _operation_definition("publish_campaign", f"发布{subject}", "workflow", fields[:3], "活动内容已通过预览校验", "活动更新为进行中", "发布版本、生效时间和发布人员", confirmation=True),
            _operation_definition("review_participation", f"查看{subject}报名签到", "analysis", fields[:3], "活动已产生参与记录", "形成参与效果分析", "报名人数、签到人数和转化率"),
        ]),
        (("权益", "会员", "优惠券", "礼包"), [
            _operation_definition("find_eligibility", f"查询{subject}资格", "lookup", fields[:3], "尚未核对用户适用条件", "显示可用权益与限制", "适用人群、有效期限和剩余数量"),
            _operation_definition("grant", f"发放{subject}", "mutation", fields[:3], "用户满足发放条件", "权益更新为已发放", "发放批次、领取用户和生效时间"),
            _operation_definition("freeze", f"冻结异常{subject}", "workflow", fields[:3], "权益存在异常使用风险", "权益更新为已冻结", "冻结原因、影响用户和操作日志", confirmation=True),
            _operation_definition("reconcile_expiry", f"核对{subject}到期状态", "result", fields[:3], "权益接近或超过有效期限", "形成到期处置清单", "到期数量、失效状态和通知结果"),
        ]),
        (("支付", "订单", "交易", "退款", "结算", "清算", "账单"), [
            _operation_definition("find_payment", f"查询{subject}记录", "lookup", fields[:3], "尚未定位交易记录", "显示匹配订单及支付状态", "订单金额、支付渠道和交易时间"),
            _operation_definition("verify_receipt", f"核对{subject}回执", "workflow", fields[:3], "渠道回执尚未核对", "交易状态与渠道回执一致", "回执编号、渠道状态和差异原因"),
            _operation_definition("handle_refund", f"发起{subject}退款", "mutation", fields[:3], "订单满足退款条件", "退款申请更新为处理中", "退款金额、申请原因和受理编号", confirmation=True),
            _operation_definition("build_reconciliation", f"生成{subject}对账批次", "result", fields[:3], "当前账期交易已汇总", "形成可复核的对账批次", "批次编号、差异笔数和账期金额"),
        ]),
        (("预警", "告警", "风险", "监测", "体征", "节拍"), [
            _operation_definition("find_signal", f"查询{subject}信号", "lookup", fields[:3], "尚未选择监测范围", "显示匹配指标与异常信号", "指标值、阈值等级和发生时间"),
            _operation_definition("configure_threshold", f"配置{subject}阈值", "mutation", fields[:3], "监测规则尚未生效", "阈值规则更新为已启用", "规则版本、阈值区间和适用范围"),
            _operation_definition("acknowledge", f"确认{subject}处置", "workflow", fields[:3], "异常信号处于待响应状态", "信号更新为处置中或已解除", "处置人员、响应时间和处置说明"),
            _operation_definition("analyze_trend", f"分析{subject}趋势", "analysis", fields[:3], "已积累连续监测数据", "形成趋势与影响判断", "趋势区间、峰值时点和关联对象"),
        ]),
        (("设备", "网关", "主机", "节点", "实例", "终端"), [
            _operation_definition("find_status", f"查询{subject}运行状态", "lookup", fields[:3], "尚未选择设备范围", "显示在线状态和资源指标", "在线状态、最近心跳和告警数量"),
            _operation_definition("register", f"纳管{subject}", "mutation", fields[:3], "设备尚未纳入平台", "设备更新为已接入", "设备标识、接入位置和协议参数"),
            _operation_definition("apply_config", f"下发{subject}配置", "workflow", fields[:3], "配置版本已通过校验", "设备进入配置应用状态", "配置版本、下发批次和执行回执", confirmation=True),
            _operation_definition("recover", f"恢复异常{subject}", "result", fields[:3], "设备处于离线或故障状态", "设备恢复在线或转入检修", "恢复时间、处理措施和最新心跳"),
        ]),
        (("库存", "批次", "耗材", "药品", "物料", "领用", "在制品"), [
            _operation_definition("find_stock", f"查询{subject}库存", "lookup", fields[:3], "尚未选择库存范围", "显示可用数量与批次", "可用数量、库位和效期日期"),
            _operation_definition("receive", f"办理{subject}入库", "mutation", fields[:3], "到货批次待验收入库", "库存数量完成增加", "入库单号、批次数量和验收结果"),
            _operation_definition("allocate", f"分配{subject}", "workflow", fields[:3], "领用或出库申请已通过", "库存转入预占或已出库", "分配数量、目标科室和出库流水"),
            _operation_definition("count_variance", f"盘点{subject}差异", "result", fields[:3], "当前盘点批次已完成实盘", "形成库存差异记录", "账面数量、实盘数量和差异原因"),
        ]),
        (("模型", "训练", "推理", "算法"), [
            _operation_definition("find_version", f"查询{subject}版本", "lookup", fields[:3], "尚未选择模型范围", "显示版本、指标和运行状态", "模型版本、评估指标和部署状态"),
            _operation_definition("start_job", f"启动{subject}作业", "workflow", fields[:3], "数据集和参数已通过校验", "作业更新为运行中", "作业编号、参数快照和运行进度"),
            _operation_definition("evaluate", f"评估{subject}结果", "analysis", fields[:3], "作业已产出候选版本", "形成可比较的评估结论", "指标对比、样本范围和风险提示"),
            _operation_definition("publish_version", f"发布{subject}版本", "result", fields[:3], "候选版本已通过评估", "版本更新为已发布", "发布版本、服务地址标识和审批记录", confirmation=True),
        ]),
        (("审核", "审批", "复核", "质检", "检查", "验收"), [
            _operation_definition("find_pending", f"查询待{subject}事项", "lookup", fields[:3], "尚未筛选待办事项", "显示符合条件的待审事项", "申请编号、提交人员和等待时长"),
            _operation_definition("verify_evidence", f"核查{subject}依据", "workflow", fields[:3], "事项资料已提交待核查", "核查项形成逐项结论", "核查清单、缺失资料和风险项"),
            _operation_definition("record_decision", f"登记{subject}结论", "mutation", fields[:3], "核查项均已完成", "事项更新为通过或退回", "审核意见、结论时间和退回原因", confirmation=True),
            _operation_definition("issue_result", f"出具{subject}结果", "result", fields[:3], "审核结论已经生效", "形成可追溯结果文件", "结果编号、签发人员和生效时间"),
        ]),
        (("统计", "分析", "指标", "报表", "预测", "评分"), [
            _operation_definition("select_scope", f"选择{subject}统计范围", "lookup", fields[:3], "尚未确定统计范围", "显示符合口径的数据范围", "统计周期、统计口径和样本数量"),
            _operation_definition("calculate", f"计算{subject}结果", "analysis", fields[:3], "统计范围和口径已确定", "形成指标计算结果", "指标值、计算时间和数据版本"),
            _operation_definition("compare", f"对比{subject}趋势", "analysis", fields[:3], "已存在两个以上对比范围", "形成差异与变化判断", "对比基线、变化幅度和异常项"),
            _operation_definition("publish_report", f"发布{subject}报告", "export", fields[:3], "指标结果已完成复核", "生成可查阅的报告版本", "报告编号、生成时间和统计口径"),
        ]),
        (("数据", "采集", "轨迹", "点位", "图层", "样本", "素材", "文件"), [
            _operation_definition("find_batch", f"查询{subject}批次", "lookup", fields[:3], "尚未选择数据批次", "显示批次质量与处理状态", "数据来源、记录数量和质量状态"),
            _operation_definition("ingest", f"接入{subject}", "import", fields[:3], "数据尚未进入处理队列", "数据更新为校验中", "接入批次、来源标识和记录数量"),
            _operation_definition("validate", f"校验{subject}质量", "workflow", fields[:3], "数据接入已经完成", "形成通过项和异常项", "质量规则、异常数量和校验明细"),
            _operation_definition("mark_exception", f"标注{subject}异常", "result", fields[:3], "质量校验发现异常记录", "异常记录进入修正队列", "异常类型、影响范围和责任人员"),
        ]),
    ]
    for markers, definitions in profiles:
        if any(marker in subject for marker in markers):
            return definitions

    fallback_profiles = (
        ("登记", "校核", "提交", "追踪"),
        ("采集", "比对", "确认", "汇总"),
        ("录入", "复核", "转交", "反馈"),
        ("维护", "验证", "启用", "查看"),
    )
    verbs = fallback_profiles[int(hashlib.sha256(module_key.encode("utf-8")).hexdigest()[:4], 16) % len(fallback_profiles)]
    focus = f"{subject[:2]}相关{subject[2:]}" if len(subject) > 2 else f"{subject}相关事项"
    categories = ("lookup", "workflow", "mutation", "result")
    states = (
        (f"尚未建立{focus}对象", f"显示匹配的{focus}对象"),
        (f"{focus}内容待核对", f"{focus}内容完成校核"),
        (f"{focus}事项待处理", f"{focus}事项进入处理中"),
        (f"{focus}处理已完成", f"形成{focus}可追溯结果"),
    )
    return [
        _operation_definition(
            f"semantic_{index + 1}",
            f"{verb}{subject}",
            categories[index],
            fields[:3],
            states[index][0],
            states[index][1],
            f"{focus}编号、{verb}结果和操作时间",
        )
        for index, verb in enumerate(verbs)
    ]


def _specialized_operation_definitions(subject: str, fields: list[str]) -> list[dict[str, object]]:
    if "边缘应用" in subject:
        return [
            _operation_definition("find_edge_app", f"查询{subject}版本", "lookup", fields[:3], "尚未选择应用范围", "显示版本与节点部署状态", "应用版本、目标节点和实例数量"),
            _operation_definition("deploy_edge_app", f"部署{subject}", "workflow", fields[:3], "应用包和目标节点校验通过", "部署任务更新为执行中", "部署批次、节点清单和执行进度", confirmation=True),
            _operation_definition("scale_edge_app", f"调整{subject}资源", "mutation", fields[:3], "应用实例达到资源水位", "形成新的实例与配额配置", "实例数量、资源配额和生效时间"),
            _operation_definition("rollback_edge_app", f"回滚异常{subject}", "result", fields[:3], "新版本健康检查未通过", "应用恢复到稳定版本", "原版本、回滚版本和恢复时间", confirmation=True),
        ]
    if "切片" in subject:
        return [
            _operation_definition("find_slice", f"查询{subject}状态", "lookup", fields[:3], "尚未选择切片范围", "显示切片资源与SLA状态", "切片标识、资源占用和达标率"),
            _operation_definition("configure_slice", f"配置{subject}SLA", "mutation", fields[:3], "业务保障目标尚未确定", "形成待生效的切片策略", "带宽上限、时延目标和优先级"),
            _operation_definition("activate_slice", f"启用{subject}", "workflow", fields[:3], "切片策略已通过资源校验", "切片更新为已启用", "生效时间、承载业务和网络范围", confirmation=True),
            _operation_definition("analyze_slice", f"分析{subject}质量", "analysis", fields[:3], "切片已产生连续运行指标", "形成SLA达标结论", "平均时延、丢包率和达标时段"),
        ]
    if "配额" in subject:
        return [
            _operation_definition("find_quota", f"查询{subject}水位", "lookup", fields[:3], "尚未选择租户或资源范围", "显示已用量与剩余额度", "配额上限、已用量和使用比例"),
            _operation_definition("allocate_quota", f"分配{subject}", "mutation", fields[:3], "租户或应用已提交资源申请", "额度更新为已分配", "分配数量、资源类型和使用期限"),
            _operation_definition("adjust_quota", f"调整{subject}上限", "workflow", fields[:3], "当前水位或业务规模发生变化", "形成新的额度上限", "原上限、新上限和调整原因", confirmation=True),
            _operation_definition("warn_quota", f"处理{subject}超限", "result", fields[:3], "资源用量接近或超过阈值", "形成扩容或限流处置结果", "超限资源、影响应用和处置措施"),
        ]
    if "数据源" in subject:
        return [
            _operation_definition("find_source", f"查询{subject}连接", "lookup", fields[:3], "尚未选择数据来源", "显示连接状态与同步范围", "来源类型、连接状态和最近同步时间"),
            _operation_definition("test_connection", f"测试{subject}连通性", "workflow", fields[:3], "连接参数已填写", "形成连通性测试结果", "网络耗时、鉴权结果和失败原因"),
            _operation_definition("configure_sync", f"配置{subject}同步任务", "mutation", fields[:3], "连通性测试已经通过", "同步任务更新为已启用", "同步周期、目标库表和增量字段"),
            _operation_definition("review_ingestion", f"查看{subject}入湖结果", "result", fields[:3], "同步任务已完成至少一个批次", "形成批次接入结论", "接入行数、失败行数和数据延迟"),
        ]
    if "数据表" in subject:
        return [
            _operation_definition("find_table", f"查询{subject}资产", "lookup", fields[:3], "尚未选择资产范围", "显示表资产与负责人", "库表名称、数据规模和责任人员"),
            _operation_definition("collect_metadata", f"采集{subject}元数据", "import", fields[:3], "表结构尚未进入资产目录", "元数据更新为已采集", "字段数量、主键定义和分区信息"),
            _operation_definition("classify_table", f"标注{subject}分类", "mutation", fields[:3], "表资产尚未完成分类", "表资产更新为已分类", "业务主题、敏感级别和标签结果"),
            _operation_definition("review_usage", f"分析{subject}使用情况", "analysis", fields[:3], "表资产已产生访问记录", "形成使用热度与闲置判断", "访问次数、下游任务和最近使用时间"),
        ]
    if "血缘" in subject:
        return [
            _operation_definition("find_lineage", f"查询{subject}关系", "lookup", fields[:3], "尚未选择分析对象", "显示上下游依赖关系", "来源节点、目标节点和链路层级"),
            _operation_definition("parse_lineage", f"解析{subject}链路", "workflow", fields[:3], "任务脚本或查询记录已接入", "形成可视化血缘链路", "解析任务、关系数量和失败节点"),
            _operation_definition("assess_impact", f"评估{subject}变更影响", "analysis", fields[:3], "上游对象计划发生变更", "形成下游影响清单", "影响任务、影响报表和责任人员"),
            _operation_definition("confirm_relation", f"确认{subject}关系", "result", fields[:3], "自动解析关系等待人工核对", "血缘关系更新为已确认", "确认人员、关系版本和证据来源"),
        ]
    if "训练" in subject:
        return [
            _operation_definition("find_training", f"查询{subject}", "lookup", fields[:3], "尚未选择训练范围", "显示作业状态与资源占用", "作业编号、数据集版本和运行进度"),
            _operation_definition("start_training", f"启动{subject}", "workflow", fields[:3], "数据集和参数校验通过", "训练作业更新为运行中", "参数快照、资源规格和启动时间"),
            _operation_definition("compare_metrics", f"对比{subject}指标", "analysis", fields[:3], "作业已产出候选模型", "形成候选模型评估结论", "指标差异、基线版本和样本范围"),
            _operation_definition("stop_training", f"停止异常{subject}", "result", fields[:3], "作业出现异常或资源超限", "作业更新为已停止", "停止原因、资源消耗和日志位置", confirmation=True),
        ]
    if "推理" in subject:
        return [
            _operation_definition("find_endpoint", f"查询{subject}", "lookup", fields[:3], "尚未选择服务实例", "显示端点状态与调用指标", "服务版本、实例数量和平均延迟"),
            _operation_definition("configure_traffic", f"配置{subject}流量", "mutation", fields[:3], "新旧服务版本同时在线", "形成新的流量分配方案", "版本权重、灰度范围和生效时间"),
            _operation_definition("test_endpoint", f"验证{subject}结果", "analysis", fields[:3], "测试样本和服务端点已就绪", "形成响应质量结论", "响应结果、推理耗时和错误码"),
            _operation_definition("restart_endpoint", f"重启异常{subject}实例", "workflow", fields[:3], "实例健康检查连续失败", "实例进入重启并恢复检查", "实例编号、重启时间和健康状态", confirmation=True),
        ]
    if "模型版本" in subject:
        return [
            _operation_definition("find_model_version", f"查询{subject}", "lookup", fields[:3], "尚未选择模型系列", "显示候选版本与评估指标", "版本编号、训练批次和当前阶段"),
            _operation_definition("compare_model", f"对比{subject}表现", "analysis", fields[:3], "存在两个以上候选版本", "形成版本优劣判断", "评估指标、基线版本和差异样本"),
            _operation_definition("approve_model", f"审核{subject}", "workflow", fields[:3], "候选版本已通过离线评估", "版本更新为待发布或已退回", "审核意见、风险项和审批人员"),
            _operation_definition("publish_model", f"发布{subject}", "result", fields[:3], "版本审核已经通过", "版本更新为已发布", "发布批次、服务范围和回滚版本", confirmation=True),
        ]
    if "队列" in subject:
        return [
            _operation_definition("find_queue_item", f"查询{subject}待办", "lookup", fields[:3], "尚未选择队列范围", "显示待办优先级与等待时长", "队列数量、优先级和最早进入时间"),
            _operation_definition("claim_queue_item", f"领取{subject}任务", "workflow", fields[:3], "任务尚未分配处理人员", "任务更新为处理中", "领取人员、领取时间和处理时限"),
            _operation_definition("transfer_queue_item", f"转派{subject}任务", "mutation", fields[:3], "当前岗位无法继续处理", "任务更新到目标处理岗位", "原处理人、目标岗位和转派原因"),
            _operation_definition("track_queue_sla", f"跟踪{subject}时效", "analysis", fields[:3], "队列存在处理中的任务", "形成超时与即将超时清单", "等待时长、剩余时限和超时数量"),
        ]
    if "结论" in subject:
        return [
            _operation_definition("find_decision", f"查询{subject}", "lookup", fields[:3], "尚未选择结论范围", "显示结论及关联依据", "结论状态、形成时间和审核人员"),
            _operation_definition("record_decision", f"登记{subject}", "mutation", fields[:3], "核查依据已经齐备", "形成待签发结论", "结论内容、依据清单和经办人员"),
            _operation_definition("revise_decision", f"修订{subject}", "workflow", fields[:3], "待签发结论存在补充意见", "形成新的结论版本", "原结论、修订内容和修订原因"),
            _operation_definition("issue_decision", f"签发{subject}", "result", fields[:3], "结论内容已完成复核", "结论更新为已生效", "签发人员、生效时间和结论版本", confirmation=True),
        ]
    if "质检" in subject or "检验批" in subject:
        return [
            _operation_definition("find_inspection", f"查询{subject}记录", "lookup", fields[:3], "尚未选择检查范围", "显示检查项与当前结论", "检查批次、抽样数量和问题数量"),
            _operation_definition("sample_inspection", f"抽取{subject}样本", "workflow", fields[:3], "检查范围与抽样规则已确定", "形成待核查样本清单", "抽样规则、样本数量和覆盖范围"),
            _operation_definition("mark_defect", f"标记{subject}问题", "mutation", fields[:3], "样本核查发现不符合项", "问题进入整改或复核状态", "问题等级、问题位置和责任岗位"),
            _operation_definition("issue_inspection", f"出具{subject}报告", "result", fields[:3], "全部样本已完成核查", "形成正式检查报告", "通过率、问题清单和报告编号"),
        ]
    if "检验点" in subject:
        return [
            _operation_definition("find_checkpoint", f"查询{subject}", "lookup", fields[:3], "尚未选择工程部位", "显示检验点状态与责任人员", "点位编号、工程部位和计划时间"),
            _operation_definition("record_measurement", f"记录{subject}实测值", "mutation", fields[:3], "检验点已到达检查时点", "实测数据更新为待判定", "实测值、允许偏差和采集人员"),
            _operation_definition("judge_checkpoint", f"判定{subject}结果", "workflow", fields[:3], "实测数据与附件已经齐备", "检验点更新为合格或待整改", "判定结论、超差项和依据附件"),
            _operation_definition("review_checkpoint", f"复核异常{subject}", "result", fields[:3], "检验点存在超差或缺项", "形成复核结论与处置要求", "复核人员、整改时限和复测要求"),
        ]
    if "工序" in subject:
        return [
            _operation_definition("find_process", f"查询{subject}进度", "lookup", fields[:3], "尚未选择施工或生产范围", "显示工序进度与前置条件", "工序编号、计划时间和完成比例"),
            _operation_definition("check_prerequisite", f"核对{subject}前置条件", "workflow", fields[:3], "工序准备进入执行阶段", "形成可开工或待补充判断", "前置工序、材料状态和人员资质"),
            _operation_definition("record_execution", f"登记{subject}执行记录", "mutation", fields[:3], "工序已经开始执行", "工序进度与实测结果已更新", "执行班组、实际时间和过程附件"),
            _operation_definition("handoff_process", f"移交{subject}结果", "result", fields[:3], "工序执行和自检已经完成", "下道工序获得可接收结果", "移交人员、自检结论和接收状态"),
        ]
    return []


def _local_module_description(module: FeatureModule) -> str:
    specs = list(module.operation_specs or [])
    labels = "、".join(str(spec.get("label") or "") for spec in specs[:3])
    evidence = "、".join(str(spec.get("result_evidence") or "") for spec in specs[1:3])
    fields = "、".join(str(item) for item in module.data_fields[:4])
    return (
        f"{module.title}围绕{fields}组织日常业务，由责任岗位完成{labels}等操作；"
        f"系统同步记录前后状态，并以{evidence}作为结果依据，便于后续查询、协同和审计追踪。"
    )


def _business_objects_from_modules(modules: list[FeatureModule]) -> list[str]:
    objects: list[str] = []
    for module in modules[:8]:
        label = module.title.replace("管理", "").replace("分析", "").replace("统计", "")
        if label and label not in objects:
            objects.append(label)
    return objects or ["业务对象", "流程任务", "统计指标", "审计日志"]


def _workflow_cards(modules: list[FeatureModule]) -> list[dict[str, list[str] | str]]:
    if not modules:
        return []
    result: list[dict[str, list[str] | str]] = []
    starts = (0, max(1, len(modules) // 3), max(2, (len(modules) * 2) // 3))
    names = ("业务发起与协同处理", "异常响应与状态追踪", "结果核对与运营分析")
    for workflow_index, start in enumerate(starts):
        chain = [modules[(start + offset) % len(modules)] for offset in range(min(3, len(modules)))]
        steps: list[str] = []
        for offset, module in enumerate(chain):
            specs = list(module.operation_specs or [])
            candidates = [spec for spec in specs if str(spec.get("category") or "") != "lookup"] or specs
            spec = candidates[min(offset, len(candidates) - 1)] if candidates else {}
            label = str(spec.get("label") or f"处理{module.title}")
            evidence = str(spec.get("result_evidence") or "状态轨迹和操作日志")
            steps.append(f"在{module.title}中{label}，系统记录{evidence}。")
        result.append(
            {
                "name": names[workflow_index],
                "trigger": f"{_module_subject(chain[0].title)}进入可处理状态",
                "steps": steps,
                "output": f"形成{_module_subject(chain[-1].title)}结果、跨模块状态轨迹和责任岗位记录",
            }
        )
    return result


def _local_quality_score(blueprint: ProductBlueprint) -> int:
    modules = list(blueprint.modules or [])
    score = 68
    if len(modules) >= 6:
        score += 5
    if all(len(module.operation_specs or []) >= 4 for module in modules):
        score += 5
    operation_signatures = {_local_operation_signature(module) for module in modules}
    required_unique = max(3, (len(modules) + 1) // 2) if modules else 0
    if len(operation_signatures) >= required_unique:
        score += 6
    else:
        score -= 8
    field_signatures = {tuple(module.data_fields[:5]) for module in modules}
    if len(field_signatures) >= min(4, len(modules)):
        score += 4
    description_signatures = {
        _local_text_shape(module.description, module.title)
        for module in modules
    }
    if len(description_signatures) >= required_unique:
        score += 4
    else:
        score -= 4
    workflow_signatures = {
        tuple(str(step) for step in (workflow.get("steps") or []))
        for workflow in blueprint.workflows
        if isinstance(workflow, dict)
    }
    if len(workflow_signatures) >= 3:
        score += 4
    if len(blueprint.report_metrics) >= 6:
        score += 2
    return min(score, 96)


def _local_text_shape(value: str, title: str) -> str:
    text = str(value or "").replace(str(title or ""), "{对象}")
    subject = _module_subject(title)
    if subject:
        text = text.replace(subject, "{对象}")
    return "".join(text.split())


def _local_operation_signature(module: FeatureModule) -> tuple:
    return tuple(
        (
            str(spec.get("category") or ""),
            _local_text_shape(str(spec.get("label") or ""), module.title),
            _local_text_shape(str(spec.get("pre_state") or ""), module.title),
            _local_text_shape(str(spec.get("post_state") or ""), module.title),
            _local_text_shape(str(spec.get("result_evidence") or ""), module.title),
        )
        for spec in module.operation_specs
    )


def _report_metrics(modules: list[FeatureModule]) -> list[str]:
    metrics = ["新增记录数", "待处理数量", "处理完成率", "异常预警数", "导出次数", "平均处理时长"]
    return [f"{module.title}{metrics[index % len(metrics)]}" for index, module in enumerate(modules[:6])]


def _technical_features(task: GenerationTask) -> list[str]:
    language = task.language if task.language != "自动选择" else "自动选择的多语言技术架构"
    return [
        f"采用{language}实现分层业务模块",
        "支持角色权限、操作日志和数据范围控制",
        "支持条件查询、分页列表、状态流转和报表导出",
        "支持运行环境参数化配置和模块化扩展",
    ]


def _quality_rules(modules: list[FeatureModule]) -> list[str]:
    rules = ["登录用户必须拥有对应菜单权限", "关键业务操作必须写入审计日志", "统计报表必须按当前数据权限过滤"]
    for module in modules[:3]:
        rules.append(f"{module.title}必须校验状态流转顺序和重复提交。")
    return rules


def _data_relations(modules: list[FeatureModule]) -> list[str]:
    if not modules:
        return ["业务对象与操作日志按对象编号关联"]
    return [
        f"{modules[index].title}与{modules[(index + 1) % len(modules)].title}通过业务编号和状态字段关联"
        for index in range(min(4, len(modules)))
    ]


def _deployment_topology(task: GenerationTask) -> str:
    if task.language in {"Java", "C#"}:
        return "客户端浏览器访问业务服务，服务端连接关系型数据库并输出 Word/PDF 材料。"
    if task.language == "JavaScript":
        return "前端页面调用 Node.js 服务接口，服务端负责数据处理、权限校验和报表导出。"
    return "应用服务、数据存储和文件导出组件部署在同一业务网络环境中。"


def _uniqueness_notes(task: GenerationTask, modules: list[FeatureModule], subtype_title: str = "") -> list[str]:
    module_names = "、".join(module.title for module in modules[:3])
    return [
        f"围绕{task.software_name}的名称、{subtype_title or task.product_type}和业务补充组织{module_names}等核心模块。",
        "每个模块均包含独立的业务字段、操作流程、状态规则和审计记录。",
        "说明书、源码工程和界面截图共享同一套产品蓝图，避免内容互相脱节。",
        "本地模板按软件名称、产品类型和原始业务补充确定行业，不使用随机行业回退。",
    ]


def _merge_unique(primary: list[str], secondary: list[str]) -> list[str]:
    result: list[str] = []
    for item in primary + secondary:
        value = str(item).strip()
        if value and value not in result:
            result.append(value)
    return result


def _environment_for_language(language: str) -> dict[str, str]:
    table = {
        "Java": {
            "hardware": "CPU：Intel Core i5，内存：8GB，硬盘：500GB",
            "os": "Windows 10 64位",
            "tool": "IntelliJ IDEA / JDK 17 / Maven",
        },
        "JavaScript": {
            "hardware": "CPU：Intel Core i5，内存：8GB，硬盘：500GB",
            "os": "Windows 10 64位",
            "tool": "Visual Studio Code / Node.js / npm",
        },
        "Python": {
            "hardware": "CPU：Intel Core i5，内存：8GB，硬盘：500GB",
            "os": "Windows 10 64位",
            "tool": "PyCharm / Python 3.11 / pip",
        },
        "PHP": {
            "hardware": "CPU：Intel Core i5，内存：8GB，硬盘：500GB",
            "os": "Windows 10 64位",
            "tool": "PhpStorm / PHP 8 / Composer",
        },
    }
    return table.get(
        language,
        {
            "hardware": "CPU：Intel Core i5，内存：8GB，硬盘：500GB",
            "os": "Windows 10 64位",
            "tool": "Visual Studio Code / 通用开发工具",
        },
    )


def _runtime_for_language(language: str) -> dict[str, str]:
    table = {
        "Java": {
            "hardware": "CPU：Intel Core i3 及以上，内存：4GB 及以上，硬盘：100GB",
            "os": "Windows Server / Linux",
            "support": "JDK 17 / MySQL 8.0 / Nginx",
        },
        "JavaScript": {
            "hardware": "CPU：Intel Core i3 及以上，内存：4GB 及以上，硬盘：100GB",
            "os": "Windows Server / Linux",
            "support": "Node.js / Express / SQLite",
        },
        "Python": {
            "hardware": "CPU：Intel Core i3 及以上，内存：4GB 及以上，硬盘：100GB",
            "os": "Windows Server / Linux",
            "support": "Python 3.11 / FastAPI / SQLite",
        },
        "PHP": {
            "hardware": "CPU：Intel Core i3 及以上，内存：4GB 及以上，硬盘：100GB",
            "os": "Windows Server / Linux",
            "support": "PHP 8 / MySQL 8.0 / Nginx",
        },
    }
    return table.get(
        language,
        {
            "hardware": "CPU：Intel Core i3 及以上，内存：4GB 及以上，硬盘：100GB",
            "os": "Windows / Linux",
            "support": "通用运行环境",
        },
    )
