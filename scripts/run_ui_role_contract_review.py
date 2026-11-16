from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str((ROOT / "backend").resolve()))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from softcopyright.blueprint import FeatureModule, ProductBlueprint  # noqa: E402
from softcopyright.models import GenerationTask  # noqa: E402
from softcopyright.ui_blueprint import build_ui_blueprint, is_mobile_app_like, ui_matches_software_type  # noqa: E402
from softcopyright.ui_roles import role_coverage_summary  # noqa: E402


SAMPLES = [
    {
        "key": "finance_admin",
        "software_name": "社区小微贷款风险巡检系统",
        "product_type": "金融软件",
        "feature_hint": "商户授信、贷后走访、还款异常、风险预警、复核处置",
        "scenario": "社区银行小微商户贷后巡检与风险复核场景",
        "expected_renderer": "admin",
    },
    {
        "key": "consumer_app",
        "software_name": "轻听书架阅读 APP",
        "product_type": "APP",
        "feature_hint": "书城搜索、章节阅读、离线下载、书签收藏、个人中心",
        "scenario": "移动端用户阅读和收藏管理场景",
        "expected_renderer": "mobile_app",
    },
    {
        "key": "game",
        "software_name": "星糖岛消除冒险",
        "product_type": "游戏软件",
        "feature_hint": "三消关卡、糖果棋盘、步数目标、道具背包、星级结算",
        "scenario": "移动端三消闯关和道具结算场景",
        "expected_renderer": "game",
    },
    {
        "key": "iot_admin",
        "software_name": "泵站物联网巡检调度系统",
        "product_type": "物联网软件",
        "feature_hint": "设备台账、遥测告警、巡检工单、远程控制、趋势报表",
        "scenario": "泵站设备远程监测、告警处置和巡检派单场景",
        "expected_renderer": "admin",
    },
]


def main() -> int:
    results = [_review_sample(sample) for sample in SAMPLES]
    summary = {
        "passed": all(item["passed"] for item in results),
        "sample_count": len(results),
        "results": results,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["passed"] else 1


def _review_sample(sample: dict) -> dict:
    task = GenerationTask(
        software_name=sample["software_name"],
        version="V1.0",
        language="Java",
        product_type=sample["product_type"],
        feature_hint=sample["feature_hint"],
        model_provider="custom",
        seed=f"ui-role-review-{sample['key']}",
    )
    blueprint = _blueprint_for(task, sample["scenario"])
    ui_blueprint = build_ui_blueprint(task, blueprint)
    role_summary = role_coverage_summary(ui_blueprint)
    expected_renderer = sample["expected_renderer"]
    checks = {
        "renderer_match": ui_blueprint.renderer == expected_renderer,
        "software_type_match": ui_matches_software_type(task, blueprint, ui_blueprint),
        "role_signature_present": bool(role_summary.get("signature")),
        "role_count_enough": int(role_summary.get("expected_role_count") or 0) >= 5,
        "screen_count_enough": int(role_summary.get("screen_count") or 0) >= 7 if expected_renderer != "game" else int(role_summary.get("screen_count") or 0) >= 5,
        "has_login": bool(role_summary.get("has_login")),
        "has_dashboard": bool(role_summary.get("has_dashboard")),
        "has_statistics": bool(role_summary.get("has_statistics")),
        "module_coverage_enough": int(role_summary.get("module_screen_count") or 0) >= 4 if expected_renderer != "mobile_app" else int(role_summary.get("module_screen_count") or 0) >= 3,
    }
    return {
        "key": sample["key"],
        "software_name": task.software_name,
        "product_type": task.product_type,
        "mobile_like": is_mobile_app_like(task, blueprint),
        "expected_renderer": expected_renderer,
        "actual_renderer": ui_blueprint.renderer,
        "role_signature": role_summary.get("signature", ""),
        "screen_count": role_summary.get("screen_count", 0),
        "view_types": role_summary.get("view_types", []),
        "checks": checks,
        "passed": all(checks.values()),
    }


def _blueprint_for(task: GenerationTask, scenario: str) -> ProductBlueprint:
    modules = [
        FeatureModule(
            key="risk",
            title="风险预警处置",
            description="维护风险事件、预警等级、处置意见和复核记录。",
            entities=["RiskEvent", "ReviewRecord"],
            operations=["登记", "查询", "复核", "归档", "导出"],
            data_fields=["事件编号", "风险等级", "责任人", "处置状态", "更新时间"],
            rules=["高风险事件必须提交复核意见。"],
        ),
        FeatureModule(
            key="archive",
            title="业务档案管理",
            description="维护对象档案、附件材料、状态轨迹和关联记录。",
            entities=["BusinessProfile", "AttachmentItem"],
            operations=["新增", "编辑", "审核", "追踪"],
            data_fields=["档案编号", "对象名称", "状态", "经办人"],
            rules=["档案变更必须记录审计日志。"],
        ),
        FeatureModule(
            key="workflow",
            title="流程工单办理",
            description="支持派单、处理、复核、退回和闭环归档。",
            entities=["WorkflowCase", "ProcessNode"],
            operations=["派单", "处理", "复核", "归档"],
            data_fields=["工单编号", "节点状态", "处理意见", "完成时间"],
            rules=["流程节点必须按顺序流转。"],
        ),
        FeatureModule(
            key="statistics",
            title="统计趋势分析",
            description="按日期、区域、状态和角色输出统计趋势。",
            entities=["MetricSnapshot", "TrendReport"],
            operations=["统计", "筛选", "导出", "对比"],
            data_fields=["统计日期", "指标名称", "指标值", "同比变化"],
            rules=["报表导出必须受数据权限控制。"],
        ),
        FeatureModule(
            key="settings",
            title="规则权限配置",
            description="配置阈值规则、角色权限、操作日志和审计追踪。",
            entities=["RuleConfig", "AuditLog"],
            operations=["配置", "授权", "审计", "启停"],
            data_fields=["规则编号", "启用状态", "适用范围", "更新人"],
            rules=["关键规则启停必须二次确认。"],
        ),
    ]
    if task.product_type == "APP":
        modules = [
            FeatureModule("home", "首页内容推荐", "展示搜索、推荐内容、快捷入口和消息提醒。", ["HomeCard", "NoticeItem"]),
            FeatureModule("search", "搜索发现服务", "支持关键词检索、筛选标签和历史记录。", ["SearchResult", "FilterTag"]),
            FeatureModule("detail", "内容详情阅读", "展示详情介绍、章节目录、收藏和继续阅读。", ["ContentItem", "Chapter"]),
            FeatureModule("download", "离线下载管理", "维护下载进度、缓存状态和本地阅读记录。", ["DownloadTask", "CacheRecord"]),
            FeatureModule("profile", "个人中心统计", "展示个人资料、阅读历史、收藏记录和设置入口。", ["UserProfile", "ReadHistory"]),
        ]
    if task.product_type == "游戏软件":
        modules = [
            FeatureModule("level", "关卡地图", "展示关卡入口、体力、金币和活动任务。", ["LevelNode", "EnergyWallet"]),
            FeatureModule("board", "糖果棋盘", "展示棋盘、步数目标、道具栏和消除得分。", ["BoardCell", "MoveGoal"]),
            FeatureModule("inventory", "道具背包", "展示道具、奖励、资产数量和使用入口。", ["PropItem", "RewardItem"]),
            FeatureModule("settlement", "星级结算", "展示得分、星级、奖励和下一关入口。", ["ScoreResult", "StarRating"]),
            FeatureModule("profile", "玩家资料", "维护玩家等级、成就、排行榜和设置。", ["PlayerProfile", "Achievement"]),
        ]
    return ProductBlueprint(
        software_name=task.software_name,
        version=task.version,
        language=task.language,
        product_type=task.product_type,
        industry=task.product_type,
        purpose=f"用于{scenario}。",
        summary=f"{task.software_name}面向{scenario}，提供业务处理、数据追踪和统计分析能力。",
        modules=modules,
        roles=["系统管理员", "业务操作员", "复核人员", "统计人员"],
        pages=["登录页", "系统首页"] + [module.title for module in modules] + ["统计报表页"],
        dev_environment={"tool": "JDK 17 / Maven"},
        runtime_environment={"support": "JDK 17 / MySQL 8"},
        scenario=scenario,
        positioning=f"面向{scenario}的业务操作系统。",
        target_users=["系统管理员", "业务操作员", "复核人员", "统计人员"],
        business_objects=[module.title for module in modules],
        report_metrics=["新增数量", "待处理数量", "完成率", "异常数量"],
        quality_score=100,
        generation_fingerprint=sample_fingerprint(task.software_name, task.product_type),
    )


def sample_fingerprint(software_name: str, product_type: str) -> str:
    import hashlib

    return hashlib.sha256(f"{software_name}|{product_type}".encode("utf-8")).hexdigest()[:16]


if __name__ == "__main__":
    raise SystemExit(main())
