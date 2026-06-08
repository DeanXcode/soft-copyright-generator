from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import random
import re
from typing import Any

from .models import GenerationTask


@dataclass(frozen=True)
class DesignDna:
    source_text: str
    optimized_prompt: str
    semantic_terms: list[str]
    domain_bias: str
    structure_id: str
    workspace_shape: str
    login_pattern: str
    structure_blueprint: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


DOMAIN_SLOT_POOLS: dict[str, tuple[str, ...]] = {
    "risk_review": ("risk_tiles", "queue", "timeline", "table", "focus", "chart", "case"),
    "transaction": ("ledger", "table", "metrics", "chart", "queue", "case", "focus"),
    "geo_monitor": ("map", "queue", "metrics", "table", "chart", "focus", "timeline"),
    "device_ops": ("map", "monitor", "queue", "chart", "table", "timeline", "focus"),
    "data_pipeline": ("pipeline", "timeline", "chart", "table", "metrics", "queue", "matrix"),
    "learning": ("timeline", "queue", "chart", "table", "case", "metrics", "focus"),
    "clinical": ("case", "queue", "table", "timeline", "focus", "metrics", "chart"),
    "content_ops": ("board", "queue", "metrics", "chart", "table", "focus", "case"),
    "general": ("metrics", "queue", "table", "chart", "timeline", "focus", "case", "board"),
}


GENERIC_TERMS = {
    "系统",
    "平台",
    "软件",
    "管理",
    "业务",
    "功能",
    "模块",
    "数据",
    "用户",
    "操作",
    "信息",
    "界面",
    "生成",
}


def build_design_dna(task: GenerationTask, subtype: Any | None = None) -> DesignDna:
    source_text = _source_text(task)
    semantic_terms = _semantic_terms(source_text)
    if subtype:
        semantic_terms = _merge_unique(semantic_terms, list(getattr(subtype, "domain_terms", ())[:6]))
    domain_bias = _domain_bias(source_text, semantic_terms)
    seed = _seed_value(task, f"design-dna|{domain_bias}|{'|'.join(semantic_terms[:8])}")
    rng = random.Random(seed)
    structure_id = hashlib.sha256(f"{source_text}|{domain_bias}|{task.seed}".encode("utf-8")).hexdigest()[:16]
    workspace_shape = "freeform_grid"
    login_pattern = rng.choice(_login_patterns_for(domain_bias))
    structure_blueprint = {
        "id": structure_id,
        "grammar": "freeform_grid",
        "domain_bias": domain_bias,
        "dashboard": _page_blueprint(rng, "dashboard", domain_bias, semantic_terms),
        "module": _page_blueprint(rng, "module", domain_bias, semantic_terms),
        "statistics": _page_blueprint(rng, "statistics", domain_bias, semantic_terms),
    }
    optimized_prompt = _optimized_prompt(task, subtype, semantic_terms, domain_bias, structure_blueprint)
    return DesignDna(
        source_text=source_text,
        optimized_prompt=optimized_prompt,
        semantic_terms=semantic_terms[:12],
        domain_bias=domain_bias,
        structure_id=structure_id,
        workspace_shape=workspace_shape,
        login_pattern=login_pattern,
        structure_blueprint=structure_blueprint,
    )


def _source_text(task: GenerationTask) -> str:
    return " ".join(
        value
        for value in [task.software_name, task.product_type, task.feature_hint, task.randomness]
        if str(value).strip()
    )


def _semantic_terms(text: str) -> list[str]:
    chunks = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,}", text)
    terms: list[str] = []
    for chunk in chunks:
        for token in re.split(r"[，,、\s]+", chunk):
            value = token.strip()
            if len(value) < 2 or value in GENERIC_TERMS:
                continue
            if value.endswith(("系统", "平台", "软件")) and len(value) > 4:
                value = value[:-2]
            if value and value not in terms:
                terms.append(value)
    return terms[:16] or ["业务对象", "流程任务", "统计指标"]


def _domain_bias(text: str, terms: list[str]) -> str:
    content = text + " " + " ".join(terms)
    rules = [
        ("geo_monitor", ("地图", "定位", "轨迹", "区域", "网格", "站点", "点位", "空间")),
        ("device_ops", ("设备", "传感", "网关", "遥测", "温湿度", "超温", "温控", "车辆", "基站", "节点")),
        ("transaction", ("交易", "订单", "支付", "清算", "对账", "账单", "票务", "结算", "费用")),
        ("data_pipeline", ("数据", "调度", "任务", "流水线", "模型", "训练", "发布", "资源", "云")),
        ("learning", ("课程", "教学", "考试", "题库", "作业", "学生", "学员", "班级")),
        ("clinical", ("患者", "病历", "处方", "门诊", "药品", "耗材", "科室", "随访")),
        ("content_ops", ("内容", "活动", "会员", "推荐", "消息", "素材", "展厅", "小程序", "APP")),
        ("risk_review", ("风控", "风险", "审核", "审批", "复核", "监管", "预警", "合规", "安全", "告警")),
    ]
    scored: list[tuple[int, int, str]] = []
    for key, keywords in rules:
        score = sum(content.count(keyword) for keyword in keywords)
        if score:
            scored.append((score, -rules.index((key, keywords)), key))
    if not scored:
        return "general"
    scored.sort(reverse=True)
    return scored[0][2]


def _page_blueprint(rng: random.Random, page_kind: str, domain_bias: str, terms: list[str]) -> dict[str, Any]:
    pool = list(DOMAIN_SLOT_POOLS.get(domain_bias, DOMAIN_SLOT_POOLS["general"]))
    rng.shuffle(pool)
    required = {
        "dashboard": ("identity", "primary", "support", "evidence"),
        "module": ("filters", "primary", "detail", "actions"),
        "statistics": ("summary", "trend", "breakdown", "evidence"),
    }[page_kind]
    slot_count = rng.randint(4, 6)
    kinds = _merge_unique(list(pool[:slot_count]), list(pool))[:slot_count]
    spans = _span_pattern(rng, slot_count)
    slots = []
    for index, kind in enumerate(kinds):
        term = terms[(index + rng.randint(0, max(0, len(terms) - 1))) % len(terms)] if terms else "业务"
        role = required[index % len(required)]
        slots.append(
            {
                "kind": _slot_kind(kind),
                "title": _slot_title(page_kind, role, term, kind),
                "span": spans[index],
                "role": role,
            }
        )
    return {
        "layout": rng.choice(("asymmetric_grid", "dense_console", "document_desk", "wide_board")),
        "slots": slots,
    }


def _slot_kind(kind: str) -> str:
    mapping = {
        "risk_tiles": "metrics",
        "monitor": "chart",
        "pipeline": "timeline",
        "ledger": "ledger",
        "board": "kanban",
    }
    return mapping.get(kind, kind)


def _slot_title(page_kind: str, role: str, term: str, kind: str) -> str:
    prefixes = {
        "dashboard": {"identity": "态势", "primary": "核心", "support": "协同", "evidence": "留痕"},
        "module": {"filters": "筛选", "primary": "处理", "detail": "详情", "actions": "操作"},
        "statistics": {"summary": "汇总", "trend": "趋势", "breakdown": "分解", "evidence": "依据"},
    }
    label = prefixes.get(page_kind, {}).get(role, "业务")
    suffix = {
        "metrics": "指标",
        "queue": "队列",
        "table": "清单",
        "chart": "趋势",
        "timeline": "流程",
        "focus": "规则",
        "case": "档案",
        "map": "分布",
        "matrix": "矩阵",
        "ledger": "账务",
        "kanban": "看板",
    }.get(_slot_kind(kind), "区")
    return f"{label}{term}{suffix}"


def _span_pattern(rng: random.Random, count: int) -> list[int]:
    patterns = {
        4: [(7, 5, 6, 6), (4, 8, 8, 4), (12, 4, 4, 4)],
        5: [(4, 8, 4, 4, 4), (6, 6, 3, 5, 4), (8, 4, 4, 4, 4)],
        6: [(4, 4, 4, 6, 3, 3), (3, 6, 3, 4, 4, 4), (8, 4, 3, 3, 3, 3)],
    }
    return list(rng.choice(patterns.get(count, [(12,)])))


def _login_patterns_for(domain_bias: str) -> tuple[str, ...]:
    if domain_bias in {"risk_review", "device_ops", "data_pipeline"}:
        return ("console_gate", "side_preview", "split_brand", "portal_grid")
    if domain_bias in {"transaction", "content_ops"}:
        return ("portal_grid", "center_card", "side_preview", "split_brand")
    if domain_bias in {"geo_monitor", "clinical"}:
        return ("side_preview", "split_brand", "portal_grid")
    return ("split_brand", "center_card", "portal_grid", "side_preview", "console_gate")


def _optimized_prompt(task: GenerationTask, subtype: Any | None, terms: list[str], domain_bias: str, structure: dict[str, Any]) -> str:
    subtype_title = str(getattr(subtype, "title", "") or task.product_type)
    slot_words = []
    for page in ("dashboard", "module", "statistics"):
        slot_words.extend(slot.get("title", "") for slot in structure.get(page, {}).get("slots", []))
    return (
        f"围绕用户输入“{task.software_name} {task.feature_hint or task.product_type}”生成{subtype_title}，"
        f"优先体现{_join_terms(terms[:8])}，界面语义偏向{domain_bias}；"
        f"页面结构不要套用固定后台模板，按{structure.get('grammar')}组织{_join_terms(slot_words[:10])}等区域。"
    )


def _join_terms(items: list[str]) -> str:
    return "、".join(str(item) for item in items if str(item).strip()) or "业务对象"


def _merge_unique(primary: list[str], secondary: list[str]) -> list[str]:
    result: list[str] = []
    for item in primary + secondary:
        value = str(item).strip()
        if value and value not in result:
            result.append(value)
    return result


def _seed_value(task: GenerationTask, salt: str) -> int:
    text = f"{salt}|{task.software_name}|{task.version}|{task.language}|{task.product_type}|{task.feature_hint}|{task.seed}"
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:12], 16)
