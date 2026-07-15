from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import Any

from .models import GenerationTask


@dataclass(frozen=True)
class ScreenshotRole:
    key: str
    title: str
    purpose: str
    view_types: tuple[str, ...]
    required_components: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "title": self.title,
            "purpose": self.purpose,
            "view_types": list(self.view_types),
            "required_components": list(self.required_components),
        }


COMMON_ADMIN_ROLES = (
    ScreenshotRole("login", "登录/权限入口", "展示系统进入、身份校验、角色入口或运行环境提示。", ("admin_login",), ("账号", "密码", "验证码", "登录按钮")),
    ScreenshotRole("dashboard", "首页/总览工作台", "展示核心指标、待办队列、异常提醒、业务快捷入口。", ("admin_dashboard",), ("指标卡片", "待办队列", "异常提醒", "快捷入口")),
    ScreenshotRole("module_list", "核心业务列表", "展示筛选条件、业务列表、状态标签、主操作按钮。", ("admin_module",), ("筛选条件", "业务列表", "状态标签", "操作按钮")),
    ScreenshotRole("module_detail", "详情/档案页", "展示对象详情、关联材料、处理记录或状态轨迹。", ("admin_module",), ("详情字段", "关联记录", "处理轨迹", "状态标签")),
    ScreenshotRole("workflow_review", "审核/复核/处置页", "展示审批意见、复核依据、处置动作和流转节点。", ("admin_module",), ("流程节点", "处理意见", "依据材料", "提交按钮")),
    ScreenshotRole("statistics", "统计/趋势报表", "展示统计指标、趋势图表、分组明细和导出入口。", ("admin_statistics",), ("统计指标", "趋势图", "分组明细", "导出入口")),
    ScreenshotRole("settings_audit", "配置/日志审计", "展示规则配置、权限范围、操作日志或审计追踪。", ("admin_module", "admin_statistics"), ("规则配置", "权限范围", "操作日志", "审计追踪")),
)

MOBILE_ROLES = (
    ScreenshotRole("login", "移动登录/授权入口", "展示手机号、验证码、隐私协议或第三方授权入口。", ("mobile_login",), ("手机号", "验证码", "隐私协议", "进入应用")),
    ScreenshotRole("dashboard", "移动首页/推荐入口", "展示搜索、推荐内容、快捷入口和底部导航。", ("mobile_home",), ("搜索入口", "推荐内容", "快捷入口", "底部导航")),
    ScreenshotRole("mobile_search", "搜索/发现页", "展示关键词搜索、筛选标签、结果列表和历史记录。", ("mobile_search", "mobile_module"), ("搜索框", "筛选标签", "结果列表", "历史记录")),
    ScreenshotRole("mobile_detail", "内容/服务详情页", "展示详情封面、简介、目录或主操作按钮。", ("mobile_detail", "mobile_module"), ("详情信息", "主操作按钮", "状态提示", "收藏入口")),
    ScreenshotRole("mobile_action", "使用/播放/办理页", "展示用户执行核心操作、进度和结果反馈。", ("mobile_player", "mobile_module"), ("操作区", "进度状态", "结果反馈", "底部导航")),
    ScreenshotRole("statistics", "个人中心/统计页", "展示个人资料、使用历史、收藏记录、会员权益或统计结果。", ("mobile_profile", "mobile_statistics"), ("用户资料", "使用历史", "收藏记录", "设置入口")),
)

GAME_ROLES = (
    ScreenshotRole("login", "游戏启动/登录", "展示账号登录、游客进入、公告、区服或开始入口。", ("game_login",), ("账号登录", "游客进入", "公告入口", "开始入口")),
    ScreenshotRole("dashboard", "游戏主界面/关卡地图", "展示角色状态、体力金币、关卡入口和活动任务。", ("game_home", "game_level"), ("关卡地图", "体力金币", "活动入口", "开始游戏")),
    ScreenshotRole("game_board", "核心玩法界面", "展示棋盘、操作区、目标、步数、得分或战斗反馈。", ("game_board", "game_level"), ("玩法区域", "目标", "剩余次数", "道具栏")),
    ScreenshotRole("game_inventory", "道具/背包/角色页", "展示资产、道具、角色、装备、奖励或活动物品。", ("game_inventory", "game_profile", "game_shop"), ("道具列表", "资产数量", "奖励入口", "状态信息")),
    ScreenshotRole("statistics", "结算/成绩统计", "展示得分、星级、奖励、排行、战绩或结算结果。", ("game_statistics",), ("得分统计", "星级评价", "奖励明细", "下一关入口")),
)


def screenshot_role_contract(task: GenerationTask, blueprint: Any, renderer: str) -> dict[str, Any]:
    roles = _role_pool(renderer)
    seed = _seed(task, blueprint, renderer)
    selected = _select_roles(roles, seed, _module_count(blueprint))
    return {
        "strategy": "quality-guardrails-with-variable-content",
        "renderer": renderer,
        "role_signature": _role_signature(task, blueprint, renderer, selected),
        "role_count": len(selected),
        "roles": [role.to_dict() for role in selected],
        "variation_rules": [
            "页面角色只约束截图用途，不固定页面标题、业务数据和模块内容。",
            "GPT 必须根据软件名称、产品类型、模块、字段、指标和流程生成每次不同的截图文本。",
            "同一批截图需覆盖入口、首页、核心业务、处理动作、统计或配置审计，不允许全是列表页。",
            "每张图必须有具体业务动作、业务字段、样例数据和可截图的界面组件。",
        ],
    }


def role_coverage_summary(ui_blueprint: Any) -> dict[str, Any]:
    design_brief = getattr(ui_blueprint, "design_brief", {}) or {}
    contract = design_brief.get("screenshot_role_contract") or {}
    expected = [str(item.get("key") or "") for item in contract.get("roles", []) if isinstance(item, dict)]
    screens = getattr(ui_blueprint, "screens", []) or []
    view_types = [getattr(screen, "view_type", "") for screen in screens]
    keys = [getattr(screen, "key", "") for screen in screens]
    return {
        "signature": contract.get("role_signature", ""),
        "expected_role_count": len(expected),
        "screen_count": len(screens),
        "screen_keys": keys,
        "view_types": view_types,
        "has_login": any("login" in value for value in view_types),
        "has_dashboard": any("dashboard" in value or "home" in value for value in view_types),
        "has_statistics": any("statistics" in value or "profile" in value for value in view_types),
        "module_screen_count": sum(1 for value in view_types if _is_core_work_screen(value)),
    }


def _is_core_work_screen(view_type: str) -> bool:
    value = str(view_type or "")
    markers = [
        "module",
        "board",
        "detail",
        "level",
        "search",
        "player",
        "inventory",
        "shop",
    ]
    return any(marker in value for marker in markers)


def _role_pool(renderer: str) -> tuple[ScreenshotRole, ...]:
    if renderer == "game":
        return GAME_ROLES
    if renderer == "mobile_app":
        return MOBILE_ROLES
    return COMMON_ADMIN_ROLES


def _select_roles(roles: tuple[ScreenshotRole, ...], seed: int, module_count: int) -> list[ScreenshotRole]:
    if not roles:
        return []
    required_keys = {"login", "dashboard", "statistics"}
    selected = [role for role in roles if role.key in required_keys]
    optional = [role for role in roles if role.key not in required_keys]
    if optional:
        offset = seed % len(optional)
        optional = optional[offset:] + optional[:offset]
    target = min(len(roles), max(5, min(8, module_count + 2)))
    for role in optional:
        if len(selected) >= target:
            break
        selected.append(role)
    return selected


def _role_signature(task: GenerationTask, blueprint: Any, renderer: str, roles: list[ScreenshotRole]) -> str:
    source = "|".join(
        [
            task.software_name,
            task.version,
            task.product_type,
            task.feature_hint,
            renderer,
            ",".join(role.key for role in roles),
            ",".join(_module_titles(blueprint)[:8]),
        ]
    )
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]


def _seed(task: GenerationTask, blueprint: Any, renderer: str) -> int:
    source = f"{task.software_name}|{task.version}|{task.product_type}|{task.feature_hint}|{task.seed}|{renderer}|{','.join(_module_titles(blueprint)[:8])}"
    return int(hashlib.sha256(source.encode("utf-8")).hexdigest()[:12], 16)


def _module_titles(blueprint: Any) -> list[str]:
    return [str(getattr(module, "title", "")).strip() for module in getattr(blueprint, "modules", []) or [] if str(getattr(module, "title", "")).strip()]


def _module_count(blueprint: Any) -> int:
    return len(getattr(blueprint, "modules", []) or [])


def has_admin_workflow_terms(text: str) -> bool:
    admin_terms = [
        "管理系统",
        "后台",
        "工作台",
        "控制台",
        "平台",
        "风控",
        "授信",
        "贷后",
        "审批",
        "复核",
        "审核",
        "工单",
        "台账",
        "监管",
        "调度",
        "质控",
        "预警",
        "审计",
        "归档",
        "派单",
        "清算",
        "报送",
        "库存",
        "运维",
        "告警",
    ]
    return any(term in text for term in admin_terms)


def has_explicit_mobile_product_type(product_type: str) -> bool:
    value = re.sub(r"\s+", "", str(product_type or "")).upper()
    return value in {"APP", "MOBILE", "ANDROID", "IOS"} or "APP" in value or "小程序" in value
