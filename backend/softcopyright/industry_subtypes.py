from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import Any

from .design_dna import build_design_dna
from .models import GenerationTask
from .module_keys import semantic_module_key


@dataclass(frozen=True)
class IndustrySubtype:
    key: str
    title: str
    industry: str
    scenario: str
    positioning: str
    roles: tuple[str, ...]
    domain_terms: tuple[str, ...]
    metrics: tuple[str, ...]
    layout_families: tuple[str, ...]
    nav_models: tuple[str, ...]
    visual_moods: tuple[str, ...]
    dashboard_patterns: tuple[str, ...]
    module_patterns: tuple[str, ...]
    secondary_mix: tuple[str, ...]


INDUSTRY_SUBTYPES: dict[str, tuple[IndustrySubtype, ...]] = {
    "APP": (
        IndustrySubtype("community_service", "社区生活服务APP", "移动互联网生活服务", "社区服务预约、订单履约、消息触达和用户留存运营", "面向社区用户、商户和平台运营人员的移动服务协同平台", ("平台运营", "客服专员", "商户管理员", "移动端用户"), ("服务预约", "门店核销", "会员权益", "消息推送", "售后工单", "活动入口", "订单支付"), ("日活用户", "预约转化率", "核销订单数", "推送到达率", "售后响应时长", "用户留存率"), ("workflow", "command", "kanban"), ("top_tabs", "side_menu", "rail"), ("移动运营工作台", "高密度服务调度台", "轻量化订单运营界面"), ("指标总览+服务队列", "运营漏斗+订单提醒", "活动看板+客服待办"), ("主从订单列表", "工单看板", "用户画像侧栏"), ("查询", "审核", "导出", "详情", "配置")),
        IndustrySubtype("commerce_app", "移动电商运营APP", "移动电商与会员运营", "商品推荐、购物车、订单支付、优惠券和售后处理", "面向移动端交易链路的商品、订单和会员运营平台", ("运营管理员", "商品专员", "客服人员", "会员用户"), ("商品上架", "购物车", "支付订单", "优惠券", "会员等级", "售后退款", "推荐位"), ("GMV", "订单转化率", "退款率", "优惠券核销率", "会员复购率", "客诉处理量"), ("command", "workflow", "matrix"), ("top_tabs", "side_menu"), ("电商运营指挥台", "营销活动配置台", "订单履约管理台"), ("销售漏斗+履约提醒", "营销指标+异常订单", "会员分层+活动转化"), ("订单主从详情", "营销配置表单", "售后审批流"), ("查询", "导入", "导出", "审核", "详情")),
        IndustrySubtype("field_service", "外勤服务APP", "移动外勤与任务协同", "工单派发、位置签到、现场照片、服务回访和结算统计", "面向外勤人员和调度中心的移动任务闭环系统", ("调度管理员", "外勤人员", "质检人员", "客户经理"), ("派工任务", "现场签到", "服务照片", "客户回访", "费用结算", "轨迹记录"), ("准时到达率", "工单完成率", "回访满意度", "异常退单数", "外勤在线率", "平均服务时长"), ("map", "kanban", "workflow"), ("side_menu", "top_tabs"), ("外勤调度台", "现场服务闭环界面", "地图化任务运营台"), ("地图派工+工单队列", "人员轨迹+异常提醒", "服务指标+质检任务"), ("地图详情抽屉", "工单流转看板", "回访表单"), ("定位", "审核", "查询", "详情", "统计")),
    ),
    "游戏软件": (
        IndustrySubtype("match_three", "休闲消除游戏", "互动娱乐与休闲游戏", "关卡挑战、消除棋盘、道具背包、活动奖励和结算评分", "面向玩家的移动休闲消除游戏系统", ("玩家用户", "内容策划", "运营管理员", "客服人员"), ("关卡地图", "消除棋盘", "道具背包", "星级结算", "活动礼包", "体力金币"), ("通关率", "平均步数", "道具使用量", "星级达成率", "充值订单数", "活动参与率"), ("game",), ("phone_tabs",), ("明亮休闲游戏界面", "竖屏关卡地图风格", "彩色棋盘操作界面"), ("关卡地图+开始游戏", "棋盘目标+道具栏", "结算奖励+星级评分"), ("棋盘界面", "背包界面", "结算界面"), ("关卡", "道具", "结算", "活动")),
        IndustrySubtype("rpg_ops", "角色养成游戏", "互动娱乐与角色养成", "角色培养、装备背包、副本任务、活动奖励和战力排行", "面向玩家成长和运营活动的角色养成游戏系统", ("玩家用户", "活动运营", "内容策划", "客服人员"), ("角色属性", "装备背包", "副本任务", "战力排行", "活动奖励", "充值订单"), ("角色等级", "装备评分", "副本完成率", "活动参与量", "战力提升", "充值转化率"), ("game",), ("phone_tabs",), ("角色养成竖屏界面", "装备背包运营界面", "副本任务游戏界面"), ("角色卡片+任务入口", "背包资产+活动奖励", "排行结算+副本进度"), ("角色详情", "装备背包", "任务结算"), ("详情", "道具", "结算", "活动")),
    ),
    "教育软件": (
        IndustrySubtype("k12_teaching", "K12在线教学平台", "基础教育在线教学", "课程排课、课堂互动、作业批改、错题分析和家校通知", "面向学校、教师、学生和家长的教学过程管理平台", ("教务管理员", "教师", "学生", "家长"), ("课程章节", "班级课表", "作业批改", "错题本", "课堂互动", "家校通知", "学习报告"), ("课程完成率", "作业提交率", "平均得分", "错题订正率", "直播出勤率", "家长回执率"), ("workflow", "kanban", "matrix"), ("top_tabs", "side_menu"), ("教学闭环工作台", "班级学习过程看板", "教务高密度管理界面"), ("班级指标+教学待办", "学习路径+批改队列", "课程运营+测评趋势"), ("批改工作台", "学生详情侧栏", "课程配置表单"), ("查询", "审核", "统计", "详情", "导出")),
        IndustrySubtype("exam_training", "考试培训题库系统", "考试培训与题库服务", "题库维护、试卷组卷、考试安排、成绩分析和证书发放", "面向培训机构的题库、考试和成绩评估平台", ("考试管理员", "命题教师", "阅卷人员", "学员"), ("题库题目", "试卷模板", "考试批次", "阅卷任务", "成绩档案", "证书记录"), ("题目数量", "组卷完成率", "考试通过率", "阅卷进度", "证书发放数", "错题命中率"), ("command", "workflow", "kanban"), ("side_menu", "top_tabs"), ("考试运营控制台", "题库组卷工作台", "成绩分析界面"), ("考试批次+阅卷队列", "题库质量+组卷进度", "成绩分布+证书待办"), ("组卷配置", "阅卷审批", "成绩详情"), ("导入", "审核", "统计", "导出", "详情")),
    ),
    "金融软件": (
        IndustrySubtype("credit_approval", "小微信贷审批系统", "银行信贷与风险审批", "授信申请、征信核验、额度测算、审批复核和贷后监控", "面向银行小微信贷业务的审批与风险管控系统", ("客户经理", "风控审批员", "复核人员", "贷后管理员"), ("授信申请", "征信报告", "额度测算", "担保资料", "审批意见", "贷后预警", "还款计划"), ("授信通过率", "待复核金额", "逾期预警数", "平均审批时长", "风险命中率", "放款金额"), ("risk", "command", "kanban"), ("side_menu", "top_tabs"), ("信贷风控审批台", "授信复核工作台", "贷后风险监测界面"), ("风险指标+审批队列", "额度测算+贷后预警", "客户画像+复核任务"), ("审批流", "客户详情", "风险规则面板"), ("审核", "复核", "预警", "详情", "导出")),
        IndustrySubtype("payment_clearing", "支付清算风控系统", "支付清算与交易风控", "交易接入、清算批次、异常拦截、对账差错和监管报送", "面向支付机构的交易清算与风险处置平台", ("清算人员", "风控管理员", "财务复核员", "监管报送员"), ("交易流水", "清算批次", "对账差错", "风险拦截", "商户资料", "报送文件"), ("交易笔数", "清算成功率", "差错金额", "风险拦截数", "对账完成率", "报送批次数"), ("risk", "matrix", "command"), ("top_tabs", "side_menu"), ("支付清算监控台", "交易风险指挥台", "对账差错处理界面"), ("交易态势+清算队列", "风险命中+差错处理", "监管报送+批次统计"), ("交易详情", "差错复核", "导出报送"), ("查询", "复核", "导出", "预警", "统计")),
    ),
    "医疗软件": (
        IndustrySubtype("inpatient_monitoring", "住院患者监测护理系统", "院内住院患者监测与护理协同", "在院患者总览、床位状态、生命体征记录、病情观察、异常预警、护理巡视、医嘱关注和班次交接", "面向临床护士、值班医生和护理管理人员的移动化患者监测平台", ("临床护士", "值班医生", "护理管理人员", "病区管理员"), ("在院患者", "床位状态", "生命体征", "病情观察", "异常预警", "护理巡视", "医嘱关注", "班次交接"), ("在院患者数", "异常预警数", "巡视完成率", "体征异常率", "重点医嘱跟进率", "交接确认率"), ("workflow", "kanban", "matrix"), ("phone_tabs", "top_tabs", "side_menu"), ("移动护理监测工作台", "病区患者状态看板", "床旁巡视记录界面"), ("患者状态+预警队列", "床位看板+巡视任务", "体征趋势+交接摘要"), ("患者详情", "床位详情", "预警处理"), ("查询", "录入", "预警", "确认", "交接", "统计")),
        IndustrySubtype("surgery_schedule", "手术排班协同系统", "医疗手术排班与科室协同", "手术申请、术前确认、手术间分配、麻醉协同、排班冲突提醒和术后归档", "面向手术室、麻醉科、临床科室和医务管理人员的手术安排协调平台", ("手术室护士", "麻醉医生", "临床医生", "医务管理员"), ("手术申请单", "患者手术信息", "术式需求", "术前确认清单", "手术间分配", "麻醉需求", "排班冲突提示"), ("今日待受理手术申请数", "今日已排程手术台次", "手术间空闲窗口数量", "排班冲突提示数量", "术前确认完成率", "术后归档完成率"), ("workflow", "kanban", "command"), ("top_tabs", "side_menu"), ("手术排班协调台", "手术室资源分配界面", "术前确认工作台"), ("手术申请+排班提醒", "手术间资源+冲突提示", "术前确认+术后归档"), ("手术申请详情", "排班分配面板", "术前确认清单"), ("查询", "追加", "修改", "查看", "失效", "导出")),
        IndustrySubtype("clinic_emr", "门诊电子病历系统", "医疗门诊诊疗服务", "挂号分诊、病历书写、处方审核、检查申请和随访质控", "面向医院门诊流程的诊疗记录和质控平台", ("医生", "护士", "药师", "质控人员"), ("患者档案", "门诊病历", "处方审核", "检查申请", "药品库存", "随访任务", "质控记录"), ("今日就诊量", "处方通过率", "平均候诊时长", "随访完成率", "库存预警数", "质控问题数"), ("workflow", "command", "matrix"), ("side_menu", "top_tabs"), ("诊疗工作台", "门诊质控看板", "处方审核管理界面"), ("就诊队列+处方待审", "患者轨迹+质控提醒", "药品预警+随访任务"), ("患者详情", "处方审核", "随访记录"), ("查询", "审核", "预警", "详情", "统计")),
        IndustrySubtype("hospital_inventory", "医院耗材库存系统", "医疗耗材与药品供应", "耗材入库、科室领用、效期预警、批次追踪和成本统计", "面向医院物资科和临床科室的耗材库存管理平台", ("库房管理员", "科室护士", "采购人员", "审计人员"), ("耗材批次", "入库单", "领用申请", "效期预警", "供应商", "盘点记录"), ("库存周转率", "近效期数量", "领用完成率", "采购到货率", "盘点差异数", "科室消耗额"), ("matrix", "workflow", "command"), ("side_menu", "rail"), ("医疗库存控制台", "耗材批次追踪界面", "科室领用审批台"), ("库存指标+预警队列", "批次追踪+领用审批", "采购入库+盘点差异"), ("批次详情", "领用审核", "导入盘点"), ("导入", "审核", "预警", "查询", "导出")),
    ),
    "地理信息软件": (
        IndustrySubtype("survey_mapping", "外业采集制图系统", "地理信息采集与制图", "外业任务、轨迹上传、图层质检、专题制图和服务发布", "面向自然资源和测绘单位的空间数据采集制图平台", ("GIS管理员", "外业采集员", "图层审核员", "制图人员"), ("采集任务", "轨迹点位", "图层版本", "空间要素", "专题地图", "瓦片服务"), ("要素入库率", "外业任务数", "图层质检率", "服务调用量", "地址匹配率", "专题图数量"), ("map", "command", "matrix"), ("side_menu", "top_tabs"), ("地图采集态势台", "图层质检工作台", "空间制图发布界面"), ("地图态势+采集队列", "图层质量+发布状态", "专题图+服务调用"), ("点位详情", "图层审核", "服务发布"), ("定位", "审核", "导入", "发布", "统计")),
        IndustrySubtype("city_grid_gis", "城市网格GIS平台", "城市网格与空间治理", "网格事件、设施点位、热力分析、巡查轨迹和区域统计", "面向城市治理部门的地图化网格管理系统", ("网格管理员", "巡查人员", "指挥调度员", "统计人员"), ("网格单元", "设施点位", "巡查轨迹", "事件热力", "区域指标", "处置工单"), ("事件办结率", "网格覆盖率", "巡查里程", "设施在线率", "热力事件数", "派单响应时长"), ("map", "kanban", "command"), ("top_tabs", "side_menu"), ("网格地图指挥台", "城市事件热力界面", "巡查轨迹分析台"), ("地图热力+事件队列", "区域指标+巡查轨迹", "派单看板+处置统计"), ("事件详情", "地图抽屉", "派单审核"), ("定位", "查询", "审核", "统计", "导出")),
    ),
    "云计算软件": (
        IndustrySubtype("cmp_platform", "多云资源管理平台", "多云资源管理与运维", "租户配额、云主机、网络安全组、监控告警、计量账单和自动化运维", "面向企业多云资源池的统一管控平台", ("云平台管理员", "租户管理员", "运维人员", "审计人员"), ("租户配额", "云主机实例", "虚拟网络", "安全组", "对象存储", "资源告警", "计量账单"), ("CPU利用率", "存储容量", "资源告警数", "成本优化率", "租户活跃数", "自动化成功率"), ("pipeline", "command", "matrix"), ("side_menu", "top_tabs"), ("多云资源控制台", "云运维链路看板", "租户资源运营界面"), ("资源池指标+告警队列", "生命周期链路+成本分析", "租户配额+运维待办"), ("资源详情", "扩容审批", "监控曲线"), ("查询", "审核", "预警", "统计", "导出")),
        IndustrySubtype("k8s_ops", "Kubernetes运维平台", "容器云与集群运维", "集群纳管、命名空间、工作负载、镜像发布、弹性伸缩和告警诊断", "面向容器平台运维团队的集群资源与发布管理系统", ("集群管理员", "DevOps人员", "应用负责人", "审计人员"), ("集群节点", "命名空间", "工作负载", "镜像仓库", "发布流水线", "弹性伸缩", "告警事件"), ("Pod健康率", "发布成功率", "节点负载", "镜像扫描数", "告警闭环率", "平均恢复时间"), ("pipeline", "kanban", "command"), ("top_tabs", "rail"), ("容器集群运维台", "发布流水线控制台", "工作负载监控界面"), ("集群健康+发布队列", "流水线阶段+告警诊断", "资源水位+伸缩任务"), ("发布审批", "工作负载详情", "告警诊断"), ("发布", "审核", "预警", "详情", "统计")),
    ),
    "信息安全软件": (
        IndustrySubtype("soc_platform", "安全运营中心SOC", "网络安全运营", "资产风险、告警研判、事件派单、漏洞闭环和合规报表", "面向安全运营团队的威胁监测与事件处置平台", ("安全管理员", "研判人员", "处置人员", "合规审计员"), ("安全资产", "告警事件", "漏洞工单", "攻击源", "处置任务", "合规检查", "风险评分"), ("高危事件数", "漏洞闭环率", "平均研判时长", "资产风险分", "处置完成率", "合规通过率"), ("risk", "command", "kanban"), ("side_menu", "top_tabs"), ("SOC安全态势台", "告警研判工作台", "漏洞闭环看板"), ("风险态势+告警队列", "事件研判+处置派单", "漏洞闭环+合规检查"), ("告警详情", "处置审批", "漏洞复测"), ("预警", "审核", "详情", "统计", "导出")),
        IndustrySubtype("data_security", "数据安全审计平台", "数据安全与合规审计", "敏感数据识别、访问审计、脱敏策略、权限审批和合规报告", "面向数据安全团队的敏感数据治理和访问审计平台", ("数据安全管理员", "审计人员", "权限审批员", "业务负责人"), ("敏感字段", "访问日志", "脱敏策略", "权限申请", "风险用户", "合规报告"), ("敏感数据量", "异常访问数", "脱敏覆盖率", "审批通过率", "审计任务数", "合规评分"), ("risk", "matrix", "command"), ("top_tabs", "side_menu"), ("数据安全审计台", "敏感数据治理界面", "权限审批工作台"), ("敏感分布+访问风险", "审计队列+策略覆盖", "权限审批+合规报告"), ("访问详情", "策略配置", "审批复核"), ("查询", "审核", "配置", "预警", "导出")),
    ),
    "大数据软件": (
        IndustrySubtype("data_governance", "数据治理平台", "数据治理与资产管理", "数据源接入、质量规则、血缘关系、指标目录、敏感标签和权限审批", "面向数据团队的数据资产治理和质量管控平台", ("数据管理员", "数据开发员", "数据分析师", "权限审批员"), ("数据源", "质量规则", "数据血缘", "指标目录", "敏感标签", "数据表", "权限申请"), ("采集成功率", "质量评分", "血缘覆盖率", "敏感标签数", "表资产数量", "权限审批时长"), ("pipeline", "matrix", "command"), ("side_menu", "top_tabs"), ("数据治理控制台", "数据资产目录界面", "质量规则看板"), ("数据链路+质量评分", "资产目录+权限审批", "血缘关系+敏感标签"), ("质量详情", "血缘抽屉", "权限审批"), ("导入", "审核", "统计", "详情", "导出")),
        IndustrySubtype("realtime_warehouse", "实时数仓调度系统", "实时数据仓库与调度", "流式采集、任务编排、作业监控、数据入仓、指标计算和异常重跑", "面向实时数据开发和运维的数据链路调度平台", ("数据开发员", "调度管理员", "运维监控员", "数据分析师"), ("流式任务", "调度队列", "作业实例", "指标宽表", "重跑记录", "延迟告警"), ("任务成功率", "平均延迟", "入仓数据量", "重跑次数", "指标产出数", "链路健康度"), ("pipeline", "kanban", "command"), ("top_tabs", "rail"), ("实时链路调度台", "任务编排看板", "数仓运行监控界面"), ("链路阶段+延迟趋势", "任务队列+异常重跑", "指标产出+质量告警"), ("任务详情", "重跑确认", "链路统计"), ("调度", "预警", "查询", "统计", "详情")),
    ),
    "人工智能软件": (
        IndustrySubtype("smart_manufacturing", "智能制造生产运营平台", "智能制造与生产运营优化", "生产计划协同、生产工单管控、产线智能排程、换线调度、工序节拍监控、在制品流转、设备停机响应和产能预测", "面向制造企业计划、调度、车间执行、设备保障和交付管理人员的智能生产运营平台", ("生产主管", "计划员", "调度员", "车间主管", "设备工程师", "质量管理员"), ("主生产计划", "生产工单", "产线排程", "换线任务", "工序节拍", "在制品", "设备停机", "产能瓶颈"), ("计划达成率", "工单按期完工率", "产线负荷率", "节拍达标率", "在制品周转率", "设备开动率", "产能利用率", "交付达成率"), ("command", "pipeline", "matrix"), ("side_menu", "rail", "top_tabs"), ("智能制造生产指挥台", "产线排程协同界面", "生产运营监控工作台"), ("计划达成+工单队列", "产线负荷+排程冲突", "设备状态+交付风险"), ("排程甘特图", "工单主从详情", "异常处置工作台"), ("查询", "排程", "下达", "调整", "预警", "统计", "导出")),
        IndustrySubtype("mlops_platform", "MLOps模型管理平台", "人工智能模型工程", "数据集、标注任务、训练作业、模型评估、推理服务和漂移监控", "面向算法团队的模型全生命周期管理平台", ("算法管理员", "标注人员", "模型训练员", "业务审核员"), ("数据集", "标注任务", "训练作业", "模型版本", "评估指标", "推理服务", "漂移信号"), ("模型准确率", "训练成功率", "推理延迟", "样本通过率", "漂移告警数", "发布版本数"), ("pipeline", "kanban", "command"), ("side_menu", "top_tabs"), ("模型生命周期控制台", "训练任务看板", "推理服务监控界面"), ("训练链路+评估指标", "模型版本+发布审批", "推理调用+漂移监控"), ("训练详情", "发布审核", "漂移预警"), ("训练", "审核", "发布", "预警", "统计")),
        IndustrySubtype("intelligent_review", "智能审核平台", "智能识别与人工复核", "模型识别、风险标注、人工复核、纠错反馈和审核统计", "面向内容安全或业务审核场景的人机协同审核系统", ("审核管理员", "复核人员", "算法运营", "质检人员"), ("识别任务", "风险标签", "复核队列", "纠错样本", "审核结论", "质检记录"), ("自动通过率", "人工复核量", "误判率", "召回率", "平均审核时长", "纠错样本数"), ("risk", "kanban", "matrix"), ("top_tabs", "side_menu"), ("智能审核工作台", "人机复核队列界面", "模型质检看板"), ("风险标签+复核队列", "识别结果+质检样本", "模型指标+纠错反馈"), ("复核详情", "质检审核", "样本导入"), ("审核", "复核", "导入", "统计", "详情")),
    ),
    "VR软件": (
        IndustrySubtype("vr_training", "VR安全培训系统", "虚拟现实培训", "三维场景、设备校准、训练任务、成绩评分、体验记录和复盘分析", "面向培训机构或企业安全培训的沉浸式训练平台", ("内容管理员", "设备管理员", "培训教师", "体验学员"), ("虚拟场景", "训练任务", "VR设备", "交互脚本", "体验记录", "成绩评分", "复盘报告"), ("场景完成率", "设备在线率", "平均训练时长", "成绩达标率", "异常退出数", "复盘报告数"), ("pipeline", "command", "matrix"), ("side_menu", "top_tabs"), ("VR培训运营台", "沉浸训练任务界面", "设备与体验监控台"), ("场景任务+设备状态", "训练链路+成绩评分", "体验记录+复盘分析"), ("设备详情", "训练发布", "成绩统计"), ("发布", "审核", "统计", "详情", "预警")),
        IndustrySubtype("vr_showroom", "VR展厅内容管理系统", "虚拟展厅与数字内容", "展厅场景、素材资源、路线配置、讲解脚本、设备状态和访问统计", "面向数字展厅运营的VR内容发布与设备管理平台", ("展厅运营", "内容管理员", "设备管理员", "讲解人员"), ("展厅场景", "三维素材", "游览路线", "讲解脚本", "头显设备", "访问记录"), ("场景访问量", "素材审核数", "设备在线率", "平均停留时长", "路线完成率", "讲解触发量"), ("matrix", "pipeline", "command"), ("top_tabs", "side_menu"), ("VR展厅运营界面", "虚拟内容发布台", "设备巡检管理界面"), ("场景访问+素材审核", "路线配置+设备在线", "讲解脚本+访问统计"), ("素材审核", "路线配置", "设备详情"), ("审核", "发布", "查询", "统计", "导出")),
    ),
    "5G软件": (
        IndustrySubtype("private_network", "5G专网运维平台", "5G专网与边缘运维", "基站站点、网络切片、边缘节点、终端接入、QoS监控和告警派单", "面向行业专网运营团队的5G网络保障平台", ("网络管理员", "边缘节点管理员", "业务运营员", "监控人员"), ("基站站点", "网络切片", "边缘节点", "终端接入", "QoS指标", "告警派单", "流量趋势"), ("平均时延", "切片达标率", "边缘负载", "终端在线数", "告警闭环率", "流量峰值"), ("map", "pipeline", "command"), ("side_menu", "top_tabs"), ("5G专网监控台", "边缘节点运维界面", "切片保障工作台"), ("站点地图+切片指标", "边缘节点+告警派单", "QoS趋势+终端接入"), ("站点详情", "切片开通", "告警处置"), ("定位", "发布", "预警", "统计", "详情")),
        IndustrySubtype("edge_app_ops", "5G边缘应用调度系统", "5G边缘应用与低时延服务", "边缘应用部署、资源配额、业务切片、终端会话和低时延质量分析", "面向边缘计算业务的应用调度与质量保障平台", ("边缘应用管理员", "网络保障人员", "业务运营员", "审计人员"), ("边缘应用", "资源配额", "业务切片", "终端会话", "低时延链路", "部署任务"), ("低时延达标率", "应用部署成功率", "节点资源水位", "会话连接数", "切片利用率", "告警恢复时长"), ("pipeline", "map", "kanban"), ("top_tabs", "rail"), ("边缘应用调度台", "低时延保障界面", "应用部署看板"), ("部署链路+节点水位", "会话地图+质量指标", "切片状态+告警恢复"), ("部署详情", "节点预警", "会话查询"), ("调度", "预警", "查询", "统计", "审核")),
    ),
    "小程序": (
        IndustrySubtype("booking_miniapp", "预约服务小程序", "微信轻应用与预约服务", "授权登录、服务预约、订单支付、核销记录、订阅消息和运营统计", "面向微信用户和门店运营的小程序预约服务平台", ("小程序运营", "门店管理员", "客服人员", "审核人员"), ("微信授权", "服务预约", "预约时段", "支付订单", "门店核销", "订阅消息", "优惠券"), ("预约转化率", "核销订单数", "订阅触达率", "退款申请数", "门店完成率", "优惠券使用率"), ("workflow", "command", "kanban"), ("top_tabs", "side_menu"), ("小程序运营台", "预约服务调度界面", "门店核销工作台"), ("预约漏斗+门店待办", "核销订单+订阅触达", "优惠券+退款申请"), ("预约详情", "核销审核", "消息配置"), ("查询", "审核", "配置", "统计", "导出")),
        IndustrySubtype("campus_miniapp", "校园服务小程序", "校园轻应用服务", "学生授权、报修预约、活动报名、通知订阅、缴费订单和服务评价", "面向校园师生的微信服务入口和运营平台", ("平台管理员", "学生用户", "后勤人员", "活动审核员"), ("学生授权", "报修工单", "活动报名", "缴费订单", "通知订阅", "服务评价"), ("报修完成率", "报名人数", "缴费成功率", "通知触达率", "评价满意度", "待审核活动"), ("workflow", "kanban", "matrix"), ("side_menu", "top_tabs"), ("校园服务运营台", "后勤工单看板", "活动报名管理界面"), ("工单队列+活动审核", "缴费订单+通知触达", "服务评价+后勤响应"), ("工单详情", "活动审核", "缴费导出"), ("审核", "查询", "导出", "统计", "详情")),
    ),
    "物联网软件": (
        IndustrySubtype("industrial_iot", "工业设备物联网平台", "工业物联网监测", "设备接入、遥测采集、远程控制、告警派单、巡检维保和健康分析", "面向工业设备运行监测和运维闭环的物联网平台", ("设备管理员", "运维人员", "告警处置员", "业务监控员"), ("设备档案", "网关通道", "遥测数据", "远程指令", "设备告警", "维保工单", "健康评分"), ("设备在线率", "告警闭环率", "数据延迟", "指令成功率", "维保完成率", "健康评分"), ("map", "command", "kanban"), ("side_menu", "top_tabs"), ("工业设备监控台", "IoT告警处置界面", "维保派单工作台"), ("设备地图+告警队列", "遥测指标+指令回执", "维保看板+健康评分"), ("设备详情", "告警派单", "指令确认"), ("定位", "预警", "审核", "详情", "统计")),
        IndustrySubtype("cold_chain_iot", "冷链物联网监管系统", "冷链物流与环境监测", "温湿度采集、车辆定位、箱体告警、运输轨迹、合规报表和远程处置", "面向冷链物流企业的环境监测和合规追踪平台", ("冷链管理员", "运输调度员", "告警处置员", "监管人员"), ("温湿度记录", "车辆轨迹", "冷箱设备", "超温告警", "运输批次", "合规报表"), ("温控达标率", "超温告警数", "车辆在线率", "批次追踪率", "处置响应时长", "合规报告数"), ("map", "risk", "command"), ("top_tabs", "side_menu"), ("冷链态势监管台", "运输轨迹监控界面", "温控告警处置台"), ("车辆地图+温控告警", "批次追踪+合规报表", "处置队列+设备状态"), ("轨迹详情", "告警确认", "报表导出"), ("定位", "预警", "查询", "导出", "详情")),
    ),
    "智慧城市软件": (
        IndustrySubtype("rail_construction_quality", "轨道交通施工质量分析系统", "轨道交通工程施工质量管理", "标段与单位工程维护、施工工序检验、质量计划与检验点、检验批评定、材料进场复检、质量问题整改、验收归档和质量趋势分析", "面向轨道交通建设单位、施工单位、监理单位和质量管理人员的工程施工质量分析检验平台", ("建设单位质量负责人", "施工质量员", "监理工程师", "试验检测人员", "项目管理员"), ("工程结构树", "施工工序", "质量计划", "检验点", "检验批", "材料复检", "质量问题", "整改验收"), ("质量计划执行率", "检验点完成率", "检验批合格率", "主控项目合格率", "材料复检通过率", "质量问题闭环率", "整改平均时长", "验收通过率"), ("pipeline", "command", "matrix"), ("top_tabs", "side_menu", "rail"), ("轨道交通施工质量监控台", "工程质量检验工作台", "标段质量分析界面"), ("工程结构+质量态势", "工序检验+异常整改", "检验批+材料复检"), ("检验批详情", "质量问题整改", "材料复检记录"), ("查询", "检验", "评定", "整改", "验收", "统计", "导出")),
        IndustrySubtype("transport_route", "交通干支线路径适配系统", "智慧交通与运输线路调度", "干线支线维护、路径适配、站点接驳、班次衔接、换乘规则和线路运行统计", "面向交通运输管理单位的干支线路径适配与协同调度平台", ("线路管理员", "调度员", "站点运营员", "统计分析员"), ("干线线路", "支线线路", "站点接驳", "路径适配", "班次计划", "换乘规则", "运行统计"), ("线路覆盖率", "班次准点率", "接驳成功率", "路径匹配率", "换乘耗时", "异常班次数"), ("map", "workflow", "command"), ("side_menu", "top_tabs"), ("交通线路调度台", "干支线路径适配界面", "站点接驳运行看板"), ("线路地图+班次指标", "路径适配+接驳规则", "换乘分析+运行统计"), ("线路详情", "路径适配", "班次调整"), ("定位", "查询", "追加", "调度", "统计", "导出")),
        IndustrySubtype("scenic_ticketing", "景区票务门禁系统", "智慧景区与票务通行", "票务订单、团队预约、闸机核验、年卡会员、客流预警和经营统计", "面向景区运营管理的票务、门禁和客流协同平台", ("景区运营员", "票务管理员", "门禁管理员", "统计分析员"), ("票种配置", "票务订单", "团队预约", "闸机核验", "年卡会员", "客流预警", "经营报表"), ("核验成功率", "票务收入", "客流峰值", "退改审核数", "年卡续费率", "团队预约量"), ("map", "command", "workflow"), ("top_tabs", "side_menu"), ("景区运营态势台", "票务门禁管理界面", "客流预警指挥台"), ("客流地图+票务指标", "闸机核验+退改审核", "团队预约+经营统计"), ("订单详情", "退改审核", "闸机预警"), ("定位", "审核", "预警", "统计", "导出")),
        IndustrySubtype("urban_event", "城市事件协同处置平台", "城市治理与事件协同", "事件上报、网格派单、部门协同、现场核验、结案归档和态势统计", "面向城市治理部门的事件闭环处置平台", ("指挥中心", "网格员", "处置部门", "督办人员"), ("事件上报", "网格派单", "部门协同", "现场核验", "督办任务", "结案归档"), ("事件办结率", "平均响应时长", "超期事件数", "网格覆盖率", "督办完成率", "群众满意度"), ("map", "kanban", "command"), ("side_menu", "top_tabs"), ("城市事件指挥台", "网格派单看板", "部门协同处置界面"), ("事件地图+派单队列", "处置流程+超期预警", "督办任务+办结统计"), ("事件详情", "派单审核", "结案归档"), ("定位", "审核", "预警", "详情", "统计")),
    ),
}


DEFAULT_SUBTYPES = (
    IndustrySubtype("business_ops", "企业业务协同系统", "企业数字化管理", "业务申请、流程审批、数据统计和日志审计", "面向企业内部业务处理的协同管理平台", ("系统管理员", "业务操作员", "审核人员", "统计人员"), ("业务申请", "审批任务", "基础档案", "统计报表", "审计日志", "系统配置"), ("新增记录数", "待处理数量", "处理完成率", "异常预警数", "平均处理时长", "导出次数"), ("classic", "workflow", "command"), ("side_menu", "top_tabs"), ("企业管理控制台", "业务协同工作台", "流程审批界面"), ("指标总览+待办队列", "流程看板+统计趋势", "模块列表+审计日志"), ("列表详情", "审批流程", "统计报表"), ("查询", "审核", "导出", "详情", "统计")),
)


def select_industry_subtype(task: GenerationTask) -> IndustrySubtype:
    return select_industry_subtype_for_context(task)


def select_industry_subtype_for_context(task: GenerationTask, context_text: str = "") -> IndustrySubtype:
    product_type = _context_product_type(task, context_text)
    choices = INDUSTRY_SUBTYPES.get(product_type, DEFAULT_SUBTYPES)
    matched = _keyword_matched_subtype(task, choices, context_text)
    if matched:
        return matched
    seed = _seed_value(task, "industry-subtype")
    return choices[seed % len(choices)]


def _context_product_type(task: GenerationTask, context_text: str = "") -> str:
    primary_text = f"{task.software_name} {task.product_type} {task.feature_hint}"
    domain_text = f"{task.software_name} {task.feature_hint} {context_text}"
    full_text = f"{primary_text} {context_text}"
    if _has_rail_construction_quality_signal(domain_text):
        return "智慧城市软件"
    if _has_transport_domain_signal(domain_text):
        return "智慧城市软件" if task.product_type not in {"地理信息软件", "物联网软件"} else task.product_type
    if re.search(r"医疗|医院|诊疗|处方|病历|药品|随访|护理|患者|手术|麻醉|科室|医生|住院|病区|床位|生命体征|医嘱", full_text):
        return "医疗软件"
    if re.search(r"云计算|云资源|云主机|云平台|容器|集群|Kubernetes|K8S|k8s|资源编排|弹性伸缩|租户|SaaS", full_text):
        return "云计算软件"
    if task.product_type in INDUSTRY_SUBTYPES and _strong_product_type_signal(task.product_type, primary_text):
        return task.product_type
    if _has_transport_domain_signal(primary_text):
        return "智慧城市软件" if task.product_type == "智慧城市软件" else task.product_type
    return task.product_type


def _strong_product_type_signal(product_type: str, text: str) -> bool:
    if product_type in {"APP", "小程序"}:
        return False
    if product_type == "智慧城市软件":
        return bool(re.search(r"智慧城市|交通|运输|城市|网格|事件|线路|路径|站点|接驳", text))
    if product_type == "医疗软件":
        return bool(re.search(r"医疗|医院|诊疗|处方|病历|药品|随访|护理|患者|检验|手术|麻醉|科室|医生", text))
    if product_type == "云计算软件":
        return bool(re.search(r"云计算|云资源|云主机|容器|集群|Kubernetes|K8S|k8s|租户", text))
    return bool(product_type and product_type in text)


def _has_transport_domain_signal(text: str) -> bool:
    value = str(text or "")
    # “路径、线路、班次、调度”等词也广泛存在于制造、医疗和工作流软件中，
    # 不能凭单个弱词把整个产品改写成交通领域。至少要求一个明确的交通业务词。
    explicit_terms = r"交通|运输|公交|客运|干线|支线|接驳|换乘|站点|车次|发车|运力|客流"
    if not re.search(explicit_terms, value):
        return False
    medical_terms = r"医疗|医院|诊疗|护理|患者|病区|床位|住院|生命体征|医嘱|护士|医生|病历"
    return not re.search(medical_terms, value)


def _has_rail_construction_quality_signal(text: str) -> bool:
    value = str(text or "")
    rail_signal = bool(re.search(r"轨道交通|地铁|铁路|轨道工程|隧道工程|车站工程", value))
    quality_signal = bool(re.search(r"施工质量|工程质量|检验批|检验点|质量计划|材料复检|整改验收|工程部位|单位工程|标段", value))
    return rail_signal and quality_signal


def _keyword_matched_subtype(task: GenerationTask, choices: tuple[IndustrySubtype, ...], context_text: str = "") -> IndustrySubtype | None:
    query_text = f"{task.software_name} {task.feature_hint} {task.product_type} {context_text}".lower()
    best: tuple[int, IndustrySubtype] | None = None
    for subtype in choices:
        score = 0
        for keyword in _explicit_subtype_keywords(subtype):
            if keyword.lower() in query_text:
                score += 3
        subtype_text = " ".join(
            [
                subtype.title,
                subtype.industry,
                subtype.scenario,
                subtype.positioning,
                " ".join(subtype.domain_terms),
                " ".join(subtype.metrics),
            ]
        ).lower()
        for keyword in _task_match_keywords(task, context_text):
            if keyword in subtype_text:
                score += 1
        if score and (best is None or score > best[0]):
            best = (score, subtype)
    return best[1] if best else None


def _task_match_keywords(task: GenerationTask, context_text: str = "") -> list[str]:
    text = f"{task.software_name} {task.feature_hint} {task.product_type} {context_text}"
    return [item.lower() for item in re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]{2,}", text) if len(item.strip()) >= 2]


def _explicit_subtype_keywords(subtype: IndustrySubtype) -> tuple[str, ...]:
    if subtype.key == "rail_construction_quality":
        return ("轨道交通", "地铁", "铁路", "施工质量", "工程质量", "检验批", "检验点", "质量计划", "材料复检", "整改", "验收", "标段", "单位工程", "工程部位")
    if subtype.key == "smart_manufacturing":
        return ("智能制造", "生产", "制造", "产线", "工单", "工序", "排程", "换线", "节拍", "在制品", "停机", "产能", "良率", "交付")
    if subtype.key == "inpatient_monitoring":
        return ("在院", "住院", "病区", "床位", "生命体征", "体征", "护理", "患者", "医嘱", "巡视", "交接", "预警")
    if subtype.key == "surgery_schedule":
        return ("手术", "手术室", "术前", "术后", "术式", "麻醉", "科室", "医生", "护士")
    if subtype.key == "transport_route":
        return ("交通", "运输", "干线", "支线", "线路", "路径", "班次", "接驳", "换乘", "站点", "公交", "客运")
    return ()


def subtype_module_specs(subtype: IndustrySubtype, fallback_specs: list[tuple[str, str, str, list[str]]]) -> list[tuple[str, str, str, list[str]]]:
    specs: list[tuple[str, str, str, list[str]]] = []
    for index, term in enumerate(subtype.domain_terms[:7], start=1):
        title = _module_title(term)
        key = semantic_module_key(
            title,
            index,
            raw_key="",
            context_terms=[term, subtype.title, subtype.scenario, subtype.positioning],
        )
        desc = f"围绕{subtype.title}中的{term}提供业务录入、状态跟踪、异常处理和统计分析。"
        entities = [f"{_ascii_prefix(subtype.key)}Record{index}", f"{_ascii_prefix(subtype.key)}Flow{index}"]
        specs.append((key, title, desc, entities))
    return specs or fallback_specs


def build_ui_design_brief(task: GenerationTask, blueprint: Any | None = None) -> dict[str, Any]:
    subtype = select_industry_subtype_for_context(task, _blueprint_context_text(blueprint))
    design_dna = build_design_dna(task, subtype)
    structure_seed = _seed_value(task, f"ui-combo|{subtype.key}")
    visual_seed = _seed_value(task, f"ui-visual|{subtype.key}")
    dashboard_seed = _seed_value(task, f"ui-dashboard|{subtype.key}")
    module_seed = _seed_value(task, f"ui-module|{subtype.key}")
    secondary_seed = _seed_value(task, f"ui-secondary|{subtype.key}")
    palette_seed = _seed_value(task, f"ui-palette|{subtype.key}")
    workspace_seed = _seed_value(task, f"ui-workspace|{subtype.key}")
    login_seed = _seed_value(task, f"ui-login|{subtype.key}")
    combo_count = max(1, len(subtype.layout_families) * len(subtype.nav_models))
    combo_index = structure_seed % combo_count
    layout_family = _choose(subtype.layout_families, combo_index)
    nav_model = _choose(subtype.nav_models, combo_index // max(1, len(subtype.layout_families)))
    visual_mood = _choose(subtype.visual_moods, visual_seed)
    dashboard_pattern = _choose(subtype.dashboard_patterns, dashboard_seed)
    module_pattern = _choose(subtype.module_patterns, module_seed)
    secondary_mix = _rotate(list(subtype.secondary_mix), secondary_seed)
    workspace_shape = design_dna.workspace_shape or _choose(("triage_console", "ledger_split", "monitor_wall", "process_lane", "case_desk", "board_columns"), workspace_seed)
    login_pattern = design_dna.login_pattern or _choose(("split_brand", "center_card", "console_gate", "portal_grid", "side_preview"), login_seed)
    palette = _palette_for(layout_family, palette_seed)
    layout_signature = ":".join(
        item
        for item in [
            subtype.key,
            layout_family,
            nav_model,
            workspace_shape,
            login_pattern,
            dashboard_pattern,
            module_pattern,
            secondary_mix[0] if secondary_mix else "",
        ]
        if item
    )
    return {
        "industry_subtype_key": subtype.key,
        "industry_subtype": subtype.title,
        "real_scenario": subtype.scenario,
        "product_positioning": subtype.positioning,
        "layout_family": layout_family,
        "nav_model": nav_model,
        "visual_mood": visual_mood,
        "dashboard_pattern": dashboard_pattern,
        "module_pattern": module_pattern,
        "workspace_shape": workspace_shape,
        "login_pattern": login_pattern,
        "design_dna": design_dna.to_dict(),
        "optimized_prompt": design_dna.optimized_prompt,
        "semantic_terms": design_dna.semantic_terms,
        "structure_blueprint": design_dna.structure_blueprint,
        "secondary_mix": secondary_mix,
        "layout_signature": layout_signature,
        "domain_terms": list(subtype.domain_terms[:8]),
        "metrics": list(subtype.metrics[:8]),
        "accent": palette["accent"],
        "accent_soft": palette["accent_soft"],
        "sidebar": palette["sidebar"],
    }


def _blueprint_context_text(blueprint: Any | None) -> str:
    if blueprint is None:
        return ""
    parts: list[str] = []
    for attr in ["software_name", "product_type", "industry", "purpose", "summary", "scenario", "positioning", "industry_subtype"]:
        value = getattr(blueprint, attr, "")
        if value:
            parts.append(str(value))
    for attr in ["target_users", "roles", "business_objects", "report_metrics", "quality_rules", "technical_features"]:
        values = getattr(blueprint, attr, []) or []
        if isinstance(values, (list, tuple)):
            parts.extend(str(item) for item in values[:12] if str(item).strip())
    for module in getattr(blueprint, "modules", []) or []:
        parts.extend(
            [
                str(getattr(module, "title", "") or ""),
                str(getattr(module, "description", "") or ""),
                " ".join(str(item) for item in (getattr(module, "operations", []) or [])[:5]),
                " ".join(str(item) for item in (getattr(module, "data_fields", []) or [])[:5]),
            ]
        )
    return " ".join(part for part in parts if part)


def _seed_value(task: GenerationTask, salt: str) -> int:
    text = f"{salt}|{task.software_name}|{task.version}|{task.language}|{task.product_type}|{task.feature_hint}|{task.seed}"
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:12], 16)


def _choose(items: tuple[str, ...], seed: int) -> str:
    if not items:
        return ""
    return items[seed % len(items)]


def _rotate(items: list[str], seed: int) -> list[str]:
    if not items:
        return []
    offset = seed % len(items)
    return items[offset:] + items[:offset]


def _module_title(term: str) -> str:
    if any(term.endswith(suffix) for suffix in ("管理", "分析", "监控", "审批", "统计", "报表", "看板", "调度")):
        return term
    if any(keyword in term for keyword in ("告警", "预警", "风险", "态势", "趋势")):
        return f"{term}监控"
    if any(keyword in term for keyword in ("报表", "指标", "评分")):
        return f"{term}分析"
    return f"{term}管理"


def _ascii_prefix(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "", value.title())
    return cleaned or "Biz"


def _palette_for(layout_family: str, seed: int) -> dict[str, str]:
    palettes = {
        "risk": [("#0f766e", "#ecfdf5", "#123c40"), ("#b91c1c", "#fef2f2", "#3f1717")],
        "map": [("#16a34a", "#f0fdf4", "#14532d"), ("#0d9488", "#f0fdfa", "#134e4a")],
        "pipeline": [("#4f46e5", "#eef2ff", "#1e1b4b"), ("#0284c7", "#f0f9ff", "#0c4a6e")],
        "workflow": [("#2563eb", "#eff6ff", "#17356f"), ("#be185d", "#fdf2f8", "#4a1230")],
        "command": [("#334155", "#f1f5f9", "#111827"), ("#7c3aed", "#f5f3ff", "#312e81")],
        "kanban": [("#ca8a04", "#fefce8", "#422006"), ("#0f766e", "#ecfdf5", "#123c40")],
        "matrix": [("#9333ea", "#faf5ff", "#3b0764"), ("#1d4ed8", "#eff6ff", "#172554")],
    }
    choices = palettes.get(layout_family, [("#2f6fed", "#eef6ff", "#1f314f")])
    accent, accent_soft, sidebar = choices[seed % len(choices)]
    return {"accent": accent, "accent_soft": accent_soft, "sidebar": sidebar}
