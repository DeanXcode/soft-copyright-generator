from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

from .architecture import normalize_software_category
from .industry_subtypes import select_industry_subtype_for_context


@dataclass(frozen=True)
class ProductExperienceSpec:
    software_category: str
    product_type: str
    industry_subtype_key: str
    industry_subtype: str
    experience_shape: str
    terminal: str
    shell: str
    ui_family: str
    renderer: str
    viewport_mode: str
    layout_family: str = ""
    nav_model: str = ""
    workspace_shape: str = ""
    visual_direction: str = ""
    page_archetypes: tuple[str, ...] = field(default_factory=tuple)
    evidence: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "software_category": self.software_category,
            "product_type": self.product_type,
            "industry_subtype_key": self.industry_subtype_key,
            "industry_subtype": self.industry_subtype,
            "experience_shape": self.experience_shape,
            "terminal": self.terminal,
            "shell": self.shell,
            "ui_family": self.ui_family,
            "renderer": self.renderer,
            "viewport_mode": self.viewport_mode,
            "layout_family": self.layout_family,
            "nav_model": self.nav_model,
            "workspace_shape": self.workspace_shape,
            "visual_direction": self.visual_direction,
            "page_archetypes": list(self.page_archetypes),
            "evidence": list(self.evidence),
        }


_SHAPE_PROFILES: dict[str, dict[str, Any]] = {
    "mobile_game": {
        "terminal": "smartphone_portrait",
        "shell": "mobile_game_scene",
        "ui_family": "gameplay",
        "renderer": "game",
        "viewport_mode": "portrait_9_16",
        "layout_family": "game",
        "nav_model": "phone_tabs",
        "workspace_shape": "game_scene",
        "visual_direction": "手机游戏竖屏界面，突出关卡、玩法区域、玩家资源、道具和结算反馈。",
        "page_archetypes": ("启动/登录", "主界面/关卡", "核心玩法", "道具/角色", "结算统计"),
    },
    "mobile_app": {
        "terminal": "smartphone_portrait",
        "shell": "native_like_mobile_app",
        "ui_family": "consumer_mobile",
        "renderer": "mobile_app",
        "viewport_mode": "portrait_9_16",
        "nav_model": "phone_tabs",
        "workspace_shape": "mobile_flow",
        "visual_direction": "面向最终用户的手机 App 竖屏界面，突出首页、搜索、详情、办理动作和个人中心。",
        "page_archetypes": ("授权/登录", "首页", "搜索/发现", "详情/办理", "个人中心"),
    },
    "mini_program": {
        "terminal": "wechat_mini_program",
        "shell": "mini_program_shell",
        "ui_family": "lightweight_mobile_service",
        "renderer": "mobile_app",
        "viewport_mode": "portrait_9_16",
        "nav_model": "phone_tabs",
        "workspace_shape": "mini_program_flow",
        "visual_direction": "微信小程序式轻应用界面，突出授权、服务卡片、预约/核销/支付和订阅消息。",
        "page_archetypes": ("微信授权", "服务首页", "预约/报名", "订单/核销", "我的"),
    },
    "h5_mobile": {
        "terminal": "mobile_browser",
        "shell": "h5_mobile_shell",
        "ui_family": "mobile_web",
        "renderer": "mobile_app",
        "viewport_mode": "portrait_9_16",
        "nav_model": "phone_tabs",
        "workspace_shape": "h5_flow",
        "visual_direction": "手机浏览器 H5 界面，突出轻量入口、表单流程、状态反馈和分享访问。",
        "page_archetypes": ("H5入口", "移动首页", "表单办理", "结果反馈", "个人记录"),
    },
    "desktop_web": {
        "terminal": "desktop_browser",
        "shell": "web_admin_console",
        "ui_family": "enterprise_web",
        "renderer": "admin",
        "viewport_mode": "landscape_1280x820",
        "visual_direction": "桌面 Web 业务系统界面，突出导航、筛选、台账、流程和统计。",
        "page_archetypes": ("登录", "首页", "业务列表", "详情/流程", "统计报表"),
    },
    "web_command_center": {
        "terminal": "large_screen_browser",
        "shell": "command_center",
        "ui_family": "command_ops",
        "renderer": "admin",
        "viewport_mode": "landscape_1280x820",
        "layout_family": "command",
        "nav_model": "top_tabs",
        "workspace_shape": "monitor_wall",
        "visual_direction": "指挥中心式桌面界面，突出态势总览、告警队列、调度动作和多区块监控。",
        "page_archetypes": ("指挥登录", "态势首页", "调度看板", "事件处置", "态势统计"),
    },
    "legacy_windows": {
        "terminal": "windows_desktop_client",
        "shell": "classic_windows_client",
        "ui_family": "desktop_client",
        "renderer": "admin",
        "viewport_mode": "landscape_1280x820",
        "layout_family": "classic",
        "nav_model": "side_menu",
        "workspace_shape": "ledger_split",
        "visual_direction": "传统 Windows/C/S 客户端风格，突出菜单树、工具栏、台账表格和属性面板。",
        "page_archetypes": ("客户端登录", "菜单工作台", "台账维护", "属性详情", "报表输出"),
    },
    "gis_map": {
        "terminal": "gis_workstation",
        "shell": "map_workspace",
        "ui_family": "geospatial",
        "renderer": "admin",
        "viewport_mode": "landscape_1280x820",
        "layout_family": "map",
        "nav_model": "side_menu",
        "workspace_shape": "freeform_grid",
        "visual_direction": "GIS/地图工作台，突出地图画布、图层、点位详情、空间筛选和轨迹/热力分析。",
        "page_archetypes": ("地图登录", "地图态势", "图层管理", "点位/轨迹详情", "空间统计"),
    },
    "industrial_hmi": {
        "terminal": "industrial_touch_panel",
        "shell": "industrial_hmi_panel",
        "ui_family": "industrial_monitoring",
        "renderer": "admin",
        "viewport_mode": "landscape_1280x820",
        "layout_family": "command",
        "nav_model": "top_tabs",
        "workspace_shape": "monitor_wall",
        "visual_direction": "工业 HMI/监控台界面，突出设备状态、遥测指标、告警、远程控制和巡检闭环。",
        "page_archetypes": ("设备登录", "监控首页", "设备详情", "告警处置", "运行统计"),
    },
    "data_dashboard": {
        "terminal": "data_workstation",
        "shell": "analytics_dashboard",
        "ui_family": "data_ops",
        "renderer": "admin",
        "viewport_mode": "landscape_1280x820",
        "layout_family": "matrix",
        "nav_model": "top_tabs",
        "workspace_shape": "freeform_grid",
        "visual_direction": "数据分析/治理驾驶舱，突出指标矩阵、数据血缘、质量规则、趋势和导出。",
        "page_archetypes": ("数据登录", "指标驾驶舱", "资产/血缘", "质量规则", "趋势报表"),
    },
    "cloud_ops_console": {
        "terminal": "ops_workstation",
        "shell": "cloud_ops_console",
        "ui_family": "cloud_operations",
        "renderer": "admin",
        "viewport_mode": "landscape_1280x820",
        "layout_family": "pipeline",
        "nav_model": "rail",
        "workspace_shape": "process_lane",
        "visual_direction": "云资源/运维控制台，突出资源池、集群、发布流水线、告警诊断和容量趋势。",
        "page_archetypes": ("运维登录", "资源总览", "集群/实例", "发布/调度", "监控报表"),
    },
    "ai_pipeline": {
        "terminal": "ml_workstation",
        "shell": "ai_pipeline_console",
        "ui_family": "ai_model_ops",
        "renderer": "admin",
        "viewport_mode": "landscape_1280x820",
        "layout_family": "pipeline",
        "nav_model": "side_menu",
        "workspace_shape": "process_lane",
        "visual_direction": "AI/MLOps 链路界面，突出数据集、标注、训练、评估、发布和漂移监控。",
        "page_archetypes": ("算法登录", "模型总览", "训练链路", "评估发布", "推理统计"),
    },
    "vr_3d": {
        "terminal": "3d_workstation",
        "shell": "immersive_scene_console",
        "ui_family": "spatial_3d",
        "renderer": "admin",
        "viewport_mode": "landscape_1280x820",
        "layout_family": "pipeline",
        "nav_model": "top_tabs",
        "workspace_shape": "freeform_grid",
        "visual_direction": "三维/VR 工作台，突出场景与模型列表、设备或作业状态、空间操作流程、质量结果和分析记录。",
        "page_archetypes": ("场景登录", "三维总览", "场景/模型流程", "对象详情", "质量与分析统计"),
    },
    "embedded_panel": {
        "terminal": "embedded_device_panel",
        "shell": "device_panel_console",
        "ui_family": "embedded_control",
        "renderer": "admin",
        "viewport_mode": "landscape_1280x820",
        "layout_family": "command",
        "nav_model": "rail",
        "workspace_shape": "monitor_wall",
        "visual_direction": "嵌入式设备面板，突出设备参数、运行状态、指令下发、日志和固件/配置。",
        "page_archetypes": ("设备入口", "状态首页", "参数配置", "指令控制", "日志统计"),
    },
    "middleware_console": {
        "terminal": "integration_ops_console",
        "shell": "middleware_gateway_console",
        "ui_family": "integration_middleware",
        "renderer": "admin",
        "viewport_mode": "landscape_1280x820",
        "layout_family": "pipeline",
        "nav_model": "rail",
        "workspace_shape": "process_lane",
        "visual_direction": "中间件/网关控制台，突出服务路由、连接器、消息链路、重试队列和运行监控。",
        "page_archetypes": ("控制台登录", "链路总览", "连接器配置", "消息/任务队列", "运行报表"),
    },
    "os_console": {
        "terminal": "system_management_console",
        "shell": "os_management_console",
        "ui_family": "system_software",
        "renderer": "admin",
        "viewport_mode": "landscape_1280x820",
        "layout_family": "matrix",
        "nav_model": "side_menu",
        "workspace_shape": "ledger_split",
        "visual_direction": "操作系统管理控制台，突出资源、进程、服务、权限、日志和系统状态。",
        "page_archetypes": ("系统登录", "资源总览", "服务/进程", "策略配置", "系统报表"),
    },
    "security_soc": {
        "terminal": "security_workstation",
        "shell": "soc_console",
        "ui_family": "security_operations",
        "renderer": "admin",
        "viewport_mode": "landscape_1280x820",
        "layout_family": "risk",
        "nav_model": "side_menu",
        "workspace_shape": "triage_console",
        "visual_direction": "安全运营中心界面，突出风险态势、告警研判、资产风险、处置队列和审计报告。",
        "page_archetypes": ("安全登录", "风险态势", "告警研判", "处置工单", "合规报表"),
    },
    "finance_risk_console": {
        "terminal": "risk_workstation",
        "shell": "finance_risk_console",
        "ui_family": "finance_risk",
        "renderer": "admin",
        "viewport_mode": "landscape_1280x820",
        "layout_family": "risk",
        "nav_model": "top_tabs",
        "workspace_shape": "triage_console",
        "visual_direction": "金融风控/清算界面，突出授信、交易、风险命中、复核队列和监管报送。",
        "page_archetypes": ("风控登录", "风险首页", "审批/清算", "客户/交易详情", "监管统计"),
    },
    "medical_workstation": {
        "terminal": "clinical_workstation",
        "shell": "medical_workstation",
        "ui_family": "clinical_workflow",
        "renderer": "admin",
        "viewport_mode": "landscape_1280x820",
        "layout_family": "workflow",
        "nav_model": "top_tabs",
        "workspace_shape": "case_desk",
        "visual_direction": "医疗工作站界面，突出患者/申请详情、排班或诊疗流程、医嘱/处方、质控和归档。",
        "page_archetypes": ("医护登录", "诊疗/排班首页", "患者/申请详情", "审核确认", "质控统计"),
    },
    "education_lms": {
        "terminal": "teaching_workstation",
        "shell": "education_lms_console",
        "ui_family": "education_workflow",
        "renderer": "admin",
        "viewport_mode": "landscape_1280x820",
        "layout_family": "workflow",
        "nav_model": "top_tabs",
        "workspace_shape": "board_columns",
        "visual_direction": "教学/培训管理界面，突出课程、班级、作业/考试、学习过程和成绩分析。",
        "page_archetypes": ("教务登录", "教学首页", "课程/班级", "作业/考试处理", "学习统计"),
    },
}


def build_product_experience_spec(task: Any, blueprint: Any | None = None) -> ProductExperienceSpec:
    category = normalize_software_category(getattr(task, "software_category", "应用软件"))
    product_type = str(getattr(task, "product_type", "") or "").strip() or "应用软件"
    context = _context_text(task, blueprint)
    user_context = _task_context_text(task)
    subtype = select_industry_subtype_for_context(task, context)
    shape, evidence = _infer_experience_shape(category, product_type, context, str(getattr(subtype, "key", "") or ""), user_context)
    profile = _SHAPE_PROFILES.get(shape, _SHAPE_PROFILES["desktop_web"])
    return ProductExperienceSpec(
        software_category=category,
        product_type=product_type,
        industry_subtype_key=str(getattr(subtype, "key", "") or ""),
        industry_subtype=str(getattr(subtype, "title", "") or ""),
        experience_shape=shape,
        terminal=str(profile.get("terminal") or ""),
        shell=str(profile.get("shell") or ""),
        ui_family=str(profile.get("ui_family") or ""),
        renderer=str(profile.get("renderer") or "admin"),
        viewport_mode=str(profile.get("viewport_mode") or "landscape_1280x820"),
        layout_family=str(profile.get("layout_family") or ""),
        nav_model=str(profile.get("nav_model") or ""),
        workspace_shape=str(profile.get("workspace_shape") or ""),
        visual_direction=str(profile.get("visual_direction") or ""),
        page_archetypes=tuple(str(item) for item in profile.get("page_archetypes", ()) if str(item).strip()),
        evidence=tuple(evidence),
    )


def expected_renderer_for_experience(spec: ProductExperienceSpec) -> str:
    if spec.renderer in {"game", "mobile_app", "admin"}:
        return spec.renderer
    return "admin"


def design_brief_experience_fields(spec: ProductExperienceSpec) -> dict[str, Any]:
    data = spec.to_dict()
    return {
        "product_experience_spec": data,
        "software_category": spec.software_category,
        "product_type": spec.product_type,
        "experience_shape": spec.experience_shape,
        "experience_terminal": spec.terminal,
        "experience_shell": spec.shell,
        "ui_family": spec.ui_family,
        "viewport_mode": spec.viewport_mode,
        "visual_direction": spec.visual_direction,
        "page_archetypes": list(spec.page_archetypes),
        "experience_evidence": list(spec.evidence),
    }


def design_brief_matches_experience(design_brief: dict[str, Any] | None, expected: ProductExperienceSpec) -> bool:
    if not isinstance(design_brief, dict):
        return False
    actual = design_brief.get("product_experience_spec")
    if not isinstance(actual, dict):
        return False
    return (
        str(actual.get("software_category") or "") == expected.software_category
        and str(actual.get("product_type") or "") == expected.product_type
        and str(actual.get("industry_subtype_key") or "") == expected.industry_subtype_key
        and str(actual.get("industry_subtype") or "") == expected.industry_subtype
        and str(actual.get("experience_shape") or "") == expected.experience_shape
        and str(actual.get("renderer") or "") == expected.renderer
    )


def layout_overrides_for_experience(spec: ProductExperienceSpec) -> dict[str, str]:
    if spec.experience_shape in {"desktop_web", "mobile_app", "mini_program", "h5_mobile", "mobile_game"}:
        return {}
    return {
        key: value
        for key, value in {
            "layout_family": spec.layout_family,
            "nav_model": spec.nav_model,
            "workspace_shape": spec.workspace_shape,
        }.items()
        if value
    }


def _infer_experience_shape(category: str, product_type: str, text: str, subtype_key: str, user_text: str = "") -> tuple[str, list[str]]:
    evidence: list[str] = []
    admin_context = _has_admin_context(text)
    mobile_backend_context = _has_mobile_backend_context(user_text or text)
    non_game_context = _has_non_game_training_or_business_context(text)
    explicit_game = _has_explicit_game_terms(_remove_product_type_hint(text, product_type))

    if category == "操作系统":
        return _shape("os_console", evidence, "软件大类=操作系统")
    if category == "中间件":
        return _shape("middleware_console", evidence, "软件大类=中间件")
    if category == "嵌入式软件":
        if _match(text, r"工业|设备|传感|采集|遥测|PLC|HMI|边缘|网关|终端|控制器|仪表"):
            return _shape("industrial_hmi", evidence, "软件大类=嵌入式软件且包含设备/工业/边缘信号")
        return _shape("embedded_panel", evidence, "软件大类=嵌入式软件")

    if product_type == "游戏软件":
        if explicit_game or not non_game_context:
            return _shape("mobile_game", evidence, "产品小类=游戏软件且未被业务/培训上下文纠偏")
    if explicit_game and not non_game_context:
        return _shape("mobile_game", evidence, "命中显式游戏体验信号")

    if _match(text, r"Windows客户端|桌面客户端|C/S|CS架构|WinForm|WPF|本地客户端|传统客户端"):
        return _shape("legacy_windows", evidence, "命中传统桌面客户端信号")

    if product_type == "小程序" or _match(user_text or text, r"小程序|微信授权|订阅消息"):
        if mobile_backend_context:
            return _shape("desktop_web", evidence, "产品小类=小程序且用户输入明确为后台/控制台")
        return _shape("mini_program", evidence, "产品小类=小程序且不是后台工作流")
    if _match(user_text or text, r"H5|移动网页|手机网页|Mobile\s*Web") and not mobile_backend_context and not admin_context:
        return _shape("h5_mobile", evidence, "命中移动 H5 信号且不是后台工作流")
    if product_type == "APP" or _match(user_text or text, r"APP|移动端|手机端|Android|iOS"):
        if mobile_backend_context:
            return _shape("desktop_web", evidence, "产品小类=APP/移动端但用户输入明确为后台/控制台")
        if not admin_context:
            return _shape("mobile_app", evidence, "产品小类=APP/移动端且不是后台工作流")
        return _shape("mobile_app", evidence, "产品小类=APP/移动端且不是后台工作流")

    if product_type == "VR软件" or _match(text, r"VR|虚拟现实|三维|3D|BIM|数字孪生|仿真|沉浸式"):
        return _shape("vr_3d", evidence, "命中 VR/三维/仿真体验信号")
    if product_type in {"物联网软件", "5G软件"} or _match(text, r"物联网|IoT|5G|基站|设备|传感|遥测|边缘|网关|终端|低时延"):
        return _shape("industrial_hmi", evidence, "命中 IoT/5G/设备监控信号")
    if subtype_key == "smart_manufacturing":
        return _shape("industrial_hmi", evidence, "行业子类型=smart_manufacturing")
    if subtype_key == "rail_construction_quality":
        return _shape("industrial_hmi", evidence, "行业子类型=rail_construction_quality")
    if product_type == "信息安全软件":
        return _shape("security_soc", evidence, "命中安全运营/风险研判信号")
    if product_type == "金融软件":
        return _shape("finance_risk_console", evidence, "命中金融风控/清算信号")
    if product_type == "医疗软件":
        return _shape("medical_workstation", evidence, "命中医疗工作站信号")
    if product_type == "教育软件":
        return _shape("education_lms", evidence, "命中教育教学工作流信号")
    if product_type == "云计算软件":
        return _shape("cloud_ops_console", evidence, "命中云资源/运维控制台信号")
    if product_type == "人工智能软件":
        return _shape("ai_pipeline", evidence, "命中 AI/MLOps 链路信号")
    if product_type == "大数据软件":
        return _shape("data_dashboard", evidence, "命中大数据/指标驾驶舱信号")
    if product_type == "地理信息软件" or _match(text, r"GIS|地理|地图|图层|空间|点位|轨迹|热力|网格|坐标|路径|线路|站点"):
        return _shape("gis_map", evidence, "命中 GIS/地图体验信号")
    if _match(text, r"安全|SOC|威胁|漏洞|告警|审计|合规|风控|风险|权限|攻击"):
        return _shape("security_soc", evidence, "命中安全运营/风险研判信号")
    if _match(text, r"金融|信贷|授信|清算|支付|交易|征信|反欺诈|监管报送|贷后"):
        return _shape("finance_risk_console", evidence, "命中金融风控/清算信号")
    if _match(text, r"医疗|医院|诊疗|患者|病历|处方|手术|麻醉|科室|医生|护士|随访"):
        return _shape("medical_workstation", evidence, "命中医疗工作站信号")
    if _match(text, r"教育|教学|课程|班级|作业|考试|题库|阅卷|学习|培训"):
        return _shape("education_lms", evidence, "命中教育教学工作流信号")
    if _match(text, r"云|云主机|容器|集群|Kubernetes|K8S|租户|资源池|运维|发布|弹性伸缩"):
        return _shape("cloud_ops_console", evidence, "命中云资源/运维控制台信号")
    if _match(text, r"人工智能|AI|算法|模型|训练|标注|推理|MLOps|漂移|样本"):
        return _shape("ai_pipeline", evidence, "命中 AI/MLOps 链路信号")
    if _match(text, r"大数据|数据治理|数仓|数据湖|血缘|指标|数据源|入仓|质量规则"):
        return _shape("data_dashboard", evidence, "命中大数据/指标驾驶舱信号")
    if product_type == "智慧城市软件" or _match(text, r"智慧城市|指挥|调度|态势|城市治理|景区|票务|门禁|客流|事件处置"):
        if _match(text, r"地图|线路|路径|站点|网格|轨迹|客流|区域|空间"):
            return _shape("gis_map", evidence, "智慧城市场景命中地图/线路/空间信号")
        return _shape("web_command_center", evidence, "命中智慧城市/指挥调度信号")
    if subtype_key in {"city_grid_gis", "transport_route", "survey_mapping", "field_service", "cold_chain_iot"}:
        return _shape("gis_map", evidence, f"行业子类型={subtype_key}")
    if _match(text, r"控制台|指挥台|态势|调度中心|监控中心|运营中心"):
        return _shape("web_command_center", evidence, "命中指挥/态势/控制台信号")
    return _shape("desktop_web", evidence, "默认桌面 Web 业务系统")


def _shape(name: str, evidence: list[str], reason: str) -> tuple[str, list[str]]:
    return name, evidence + [reason]


def _task_context_text(task: Any) -> str:
    feature_hint = getattr(task, "input_feature_hint", None)
    if feature_hint is None:
        feature_hint = getattr(task, "feature_hint", "")
    parts = [
        str(getattr(task, "software_name", "") or ""),
        str(getattr(task, "product_type", "") or ""),
        str(getattr(task, "software_category", "") or ""),
        str(feature_hint or ""),
    ]
    return " ".join(part for part in parts if part.strip())


def _context_text(task: Any, blueprint: Any | None) -> str:
    parts: list[str] = [
        str(getattr(task, "software_name", "") or ""),
        str(getattr(task, "product_type", "") or ""),
        str(getattr(task, "software_category", "") or ""),
        str(getattr(task, "feature_hint", "") or ""),
    ]
    if blueprint is not None:
        for attr in ["industry", "purpose", "summary", "scenario", "positioning", "industry_subtype"]:
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
    return " ".join(part for part in parts if part.strip())


def _has_admin_context(text: str) -> bool:
    return _match(
        text,
        r"管理系统|后台|工作台|控制台|运营台|指挥台|审批|审核|复核|工单|台账|监管|调度|质控|预警|审计|归档|派单|清算|运维|告警|报表",
    )


def _has_mobile_backend_context(text: str) -> bool:
    return _match(
        text,
        r"后台|管理后台|运营后台|控制台|工作台|运营台|管理端|商家端|门店端|平台端|PC端|Web端|报表中心|数据看板|审核台|客服|客户服务|工单|派单|投诉|协同处理|协同平台|安装验收|验收系统|服务回访|SLA",
    )


def _has_explicit_game_terms(text: str) -> bool:
    return _match(text, r"游戏|手游|小游戏|消除|点消|三消|连消|糖果|对局|玩家|道具背包|关卡地图|排行榜|装备|副本")


def _has_non_game_training_or_business_context(text: str) -> bool:
    return _match(
        text,
        r"医疗|医院|诊疗|护理|患者|气道|插管|急救|培训|实训|演练|考核|评分|技能|仿真|VR|虚拟现实|管理|平台|系统|后台|审批|审核|工单|台账|归档|质控|统计报表",
    )


def _remove_product_type_hint(text: str, product_type: str) -> str:
    if not product_type:
        return text
    return text.replace(product_type, " ")


def _match(text: str, pattern: str) -> bool:
    return bool(re.search(pattern, text, flags=re.IGNORECASE))
