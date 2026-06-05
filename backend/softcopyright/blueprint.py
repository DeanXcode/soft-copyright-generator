from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass

from .models import GenerationTask


@dataclass
class FeatureModule:
    key: str
    title: str
    description: str
    entities: list[str]


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

    module_specs = list(preset["modules"])
    rng.shuffle(module_specs)
    selected_count = min(len(module_specs), 6 + (1 if task.randomness == "高差异" else 0))
    selected = module_specs[:selected_count]

    if task.feature_hint:
        selected.insert(
            0,
            (
                "custom",
                "特色业务管理",
                f"围绕{task.feature_hint}提供参数配置、业务处理、数据追踪和统计分析。",
                ["CustomBusiness", "CustomRecord"],
            ),
        )

    modules = [
        FeatureModule(key=key, title=title, description=description, entities=entities)
        for key, title, description, entities in selected
    ]
    pages = ["登录页", "系统首页"] + [module.title for module in modules] + ["统计报表页", "系统设置页"]
    industry = preset["industry"]
    purpose = f"用于{industry}场景下的业务数据管理、流程协同、运行监控和统计分析。"
    summary = (
        f"{task.software_name}是一套面向{industry}的{task.product_type}，"
        f"围绕{', '.join(module.title for module in modules[:4])}等模块，"
        "提供数据维护、业务处理、权限控制、日志审计和报表分析能力。"
    )

    dev_environment = _environment_for_language(task.language)
    runtime_environment = _runtime_for_language(task.language)

    return ProductBlueprint(
        software_name=task.software_name,
        version=task.version,
        language=task.language,
        product_type=task.product_type,
        industry=industry,
        purpose=purpose,
        summary=summary,
        modules=modules,
        roles=list(preset["roles"]),
        pages=pages,
        dev_environment=dev_environment,
        runtime_environment=runtime_environment,
    )


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
