from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any, Iterable


@dataclass(frozen=True)
class OperationCoverageSpec:
    action: str
    category: str
    surface: str
    mode: str
    requires_confirmation: bool = False
    source: str = "module"
    action_key: str = ""
    role: str = ""
    trigger: str = ""
    input_fields: tuple[str, ...] = ()
    pre_state: str = ""
    post_state: str = ""
    result_evidence: str = ""


_ACTION_SUFFIXES = (
    "查看详情",
    "搜索与筛选",
    "下载离线资料包",
    "生成统计快照",
    "重新选择文件",
    "提交版本确认",
    "查询",
    "搜索",
    "筛选",
    "详情",
    "查看",
    "定位",
    "新增",
    "添加",
    "登记",
    "录入",
    "创建",
    "编辑",
    "修改",
    "配置",
    "导入",
    "导出",
    "下载",
    "打印",
    "校验",
    "验证",
    "分析",
    "审核",
    "复核",
    "确认",
    "发布",
    "下发",
    "提交",
    "处置",
    "调度",
    "排程",
    "预警",
    "追踪",
    "跟踪",
    "统计",
    "归档",
    "删除",
    "失效",
    "清空",
    "重置",
    "播放",
    "歌词",
    "收藏",
)


def operation_action_label(value: str) -> str:
    text = str(value or "").strip()
    for suffix in _ACTION_SUFFIXES:
        if suffix in text:
            return suffix
    return text or "处理"


def operation_category(action: str) -> str:
    text = str(action or "")
    if any(term in text for term in ("查询", "搜索", "筛选", "查看", "详情", "定位")):
        return "lookup"
    if any(term in text for term in ("新增", "添加", "登记", "录入", "创建", "编辑", "修改", "配置")):
        return "mutation"
    if any(term in text for term in ("导入", "上传", "读取", "解析")):
        return "import"
    if any(term in text for term in ("导出", "下载", "打印")):
        return "export"
    if any(term in text for term in ("删除", "失效", "清空", "重置", "注销", "覆盖")):
        return "destructive"
    if any(term in text for term in ("统计", "分析", "报表", "快照")):
        return "analysis"
    if any(term in text for term in ("校验", "验证", "审核", "复核", "确认", "发布", "下发", "提交", "处置", "调度", "排程")):
        return "workflow"
    if any(term in text for term in ("预警", "追踪", "跟踪", "归档", "记录")):
        return "result"
    if any(term in text for term in ("播放", "歌词", "收藏")):
        return "instant"
    return "workflow"


def module_operation_category(module: Any, action: str, action_key: str = "") -> str:
    normalized_action = str(action or "").strip()
    normalized_key = str(action_key or "").strip()
    for value in getattr(module, "operation_specs", None) or []:
        if not isinstance(value, dict):
            continue
        value_key = str(value.get("action_key") or value.get("actionKey") or "").strip()
        value_label = str(value.get("label") or value.get("action") or value.get("name") or "").strip()
        if normalized_key:
            if value_key != normalized_key:
                continue
        elif value_label != normalized_action:
            continue
        spec = operation_spec_from_mapping(value)
        if spec is not None:
            return spec.category
    return operation_category(normalized_action)


def operation_spec(action: str, *, source: str = "module") -> OperationCoverageSpec:
    label = operation_action_label(action)
    category = operation_category(label)
    surface_by_category = {
        "lookup": "query_results",
        "mutation": "edit_form",
        "import": "import_workspace",
        "export": "export_result",
        "destructive": "confirmation_dialog",
        "analysis": "analytics_result",
        "workflow": "workflow_result",
        "result": "detail_timeline",
        "instant": "instant_detail",
    }
    mode_by_category = {
        "lookup": "query",
        "mutation": "form",
        "import": "import",
        "export": "export",
        "destructive": "confirm",
        "analysis": "analysis",
        "workflow": "workflow",
        "result": "detail",
        "instant": "instant",
    }
    requires_confirmation = category == "destructive" or any(
        term in label for term in ("正式发布", "覆盖导入", "提交审核")
    )
    return OperationCoverageSpec(
        action=label,
        category=category,
        surface=surface_by_category[category],
        mode="confirm" if requires_confirmation else mode_by_category[category],
        requires_confirmation=requires_confirmation,
        source=source,
    )


def operation_spec_from_mapping(value: dict[str, Any], *, source: str = "blueprint-structured") -> OperationCoverageSpec | None:
    label = str(value.get("label") or value.get("action") or value.get("name") or "").strip()
    if not label:
        return None
    inferred = operation_spec(label, source=source)
    category = str(value.get("category") or "").strip().lower()
    if category not in {"lookup", "mutation", "import", "export", "destructive", "analysis", "workflow", "result", "instant"}:
        category = inferred.category
    input_fields = value.get("input_fields") or value.get("inputFields") or []
    if not isinstance(input_fields, list):
        input_fields = []
    explicit_confirmation = value.get("requires_confirmation")
    if explicit_confirmation is None:
        explicit_confirmation = value.get("requiresConfirmation")
    return OperationCoverageSpec(
        action=label,
        category=category,
        surface=str(value.get("surface") or inferred.surface).strip() or inferred.surface,
        mode=str(value.get("mode") or inferred.mode).strip() or inferred.mode,
        requires_confirmation=(
            bool(explicit_confirmation)
            if explicit_confirmation is not None
            else inferred.requires_confirmation
        ),
        source=source,
        action_key=str(value.get("action_key") or value.get("actionKey") or "").strip(),
        role=str(value.get("role") or "").strip(),
        trigger=str(value.get("trigger") or "").strip(),
        input_fields=tuple(str(item).strip() for item in input_fields if str(item).strip()),
        pre_state=str(value.get("pre_state") or value.get("preState") or "").strip(),
        post_state=str(value.get("post_state") or value.get("postState") or "").strip(),
        result_evidence=str(value.get("result_evidence") or value.get("resultEvidence") or "").strip(),
    )


def configured_operation_screen_count(renderer: str = "admin") -> int:
    default = 3 if renderer == "admin" else 2 if renderer == "mobile_app" else 0
    raw = os.getenv("SOFT_MODULE_OPERATION_SCREEN_COUNT", str(default)).strip()
    try:
        value = int(raw)
    except ValueError:
        value = default
    maximum = 5 if renderer == "admin" else 3 if renderer == "mobile_app" else 0
    return max(0, min(maximum, value))


def module_operation_coverage(
    module: Any,
    *,
    renderer: str = "admin",
    module_index: int = 0,
    limit: int | None = None,
) -> list[OperationCoverageSpec]:
    target = configured_operation_screen_count(renderer) if limit is None else max(0, int(limit))
    if target <= 0:
        return []
    structured_values = getattr(module, "operation_specs", None) or []
    structured_specs = [
        spec
        for item in structured_values
        if isinstance(item, dict)
        for spec in [operation_spec_from_mapping(item)]
        if spec is not None
    ]
    raw_operations = [str(item).strip() for item in (getattr(module, "operations", None) or []) if str(item).strip()]
    actual_specs = _unique_specs(structured_specs)
    if len(actual_specs) < target:
        actual_specs = _unique_specs([
            *actual_specs,
            *(operation_spec(value) for value in raw_operations),
        ])
    if renderer == "mobile_app":
        return _mobile_coverage(module, actual_specs, module_index=module_index, target=target)
    return _admin_coverage(module, actual_specs, module_index=module_index, target=target)


def operation_coverage_categories(specs: Iterable[OperationCoverageSpec]) -> list[str]:
    return list(dict.fromkeys(spec.category for spec in specs if spec.category))


def operation_caption(module_title: str, spec: OperationCoverageSpec) -> str:
    subject = f"{module_title}{spec.action}"
    role_note = f"由{spec.role}在{spec.trigger}时发起，" if spec.role and spec.trigger else ""
    evidence_note = f"，完成后形成{spec.result_evidence}" if spec.result_evidence else ""
    templates = {
        "lookup": f"{subject}页面展示查询条件、结果列表、筛选状态和可用操作。",
        "mutation": f"{subject}页面展示待维护字段、校验提示、保存入口和处理结果。",
        "import": f"{subject}页面展示文件选择、字段映射、校验结果和导入状态。",
        "export": f"{subject}页面展示导出范围、文件格式、生成进度和下载结果。",
        "destructive": f"{subject}页面展示影响范围、风险提示以及取消和确认入口。",
        "analysis": f"{subject}页面展示指标、趋势、分组结果和当前统计范围。",
        "workflow": f"{subject}页面展示当前记录、处理条件、流程状态和执行结果。",
        "result": f"{subject}页面展示当前记录详情、状态轨迹和关联处理结果。",
        "instant": f"{subject}页面直接展示操作结果和可继续使用的入口。",
    }
    caption = templates.get(spec.category, f"{subject}页面展示当前业务信息和处理结果。")
    return f"{role_note}{caption.rstrip('。')}{evidence_note}。"


def _admin_coverage(
    module: Any,
    actual_specs: list[OperationCoverageSpec],
    *,
    module_index: int,
    target: int,
) -> list[OperationCoverageSpec]:
    selected: list[OperationCoverageSpec] = []
    groups = (
        ("lookup",),
        ("mutation", "workflow"),
        ("import", "export", "analysis", "result", "destructive", "workflow"),
    )
    for group_index, categories in enumerate(groups):
        candidates = [spec for spec in actual_specs if spec.category in categories and spec.action not in {item.action for item in selected}]
        if candidates:
            selected.append(candidates[(module_index + group_index) % len(candidates)])
        elif group_index == 0:
            selected.append(operation_spec("查询", source="coverage-fallback"))
    for spec in actual_specs:
        if spec.action not in {item.action for item in selected}:
            selected.append(spec)
        if len(selected) >= target:
            break
    fallback_actions = _admin_fallback_actions(module, module_index)
    for action in fallback_actions:
        spec = operation_spec(action, source="coverage-fallback")
        if spec.action not in {item.action for item in selected}:
            selected.append(spec)
        if len(selected) >= target:
            break
    return selected[:target]


def _admin_fallback_actions(module: Any, module_index: int) -> list[str]:
    text = " ".join(
        str(value or "")
        for value in (
            getattr(module, "title", ""),
            getattr(module, "description", ""),
            " ".join(str(item) for item in (getattr(module, "pages", None) or [])),
        )
    )
    read_only = any(term in text for term in ("看板", "统计", "分析", "监控", "预警", "报表"))
    mutation = "查看详情" if read_only else "新增"
    outputs = ["统计", "导出", "归档"]
    return ["查询", mutation, outputs[module_index % len(outputs)], "编辑", "删除"]


def _mobile_coverage(
    module: Any,
    actual_specs: list[OperationCoverageSpec],
    *,
    module_index: int,
    target: int,
) -> list[OperationCoverageSpec]:
    text = " ".join(
        str(value or "")
        for value in (
            getattr(module, "title", ""),
            getattr(module, "description", ""),
            " ".join(str(item) for item in (getattr(module, "pages", None) or [])),
            " ".join(str(item) for item in (getattr(module, "operations", None) or [])),
        )
    )
    detected: list[str] = []
    for term, action in (
        ("搜索", "搜索与筛选"),
        ("播放", "播放"),
        ("歌词", "查看歌词"),
        ("下载", "下载"),
        ("收藏", "收藏"),
        ("详情", "查看详情"),
        ("记录", "查看详情"),
    ):
        if term in text and action not in detected:
            detected.append(action)
    inferred_specs = [operation_spec(action, source="coverage-inferred") for action in detected]
    structured_specs = [
        spec
        for spec in actual_specs
        if spec.source == "blueprint-structured"
    ]
    allowed_legacy = [
        spec
        for spec in actual_specs
        if spec.source != "blueprint-structured"
        and spec.category in {"lookup", "instant", "export"}
        and spec.action in text
    ]
    candidates = _unique_specs([*structured_specs, *inferred_specs, *allowed_legacy])
    if not candidates:
        candidates = [operation_spec("查看详情", source="coverage-fallback")]
    if structured_specs:
        selected = list(candidates)
    else:
        selected = candidates[module_index % len(candidates) :] + candidates[: module_index % len(candidates)]
    if len(selected) < target and not any(spec.category == "lookup" for spec in selected):
        selected.append(operation_spec("搜索与筛选", source="coverage-fallback"))
    if len(selected) < target:
        selected.append(operation_spec("查看详情", source="coverage-fallback"))
    return _unique_specs(selected)[:target]


def _unique_specs(specs: Iterable[OperationCoverageSpec]) -> list[OperationCoverageSpec]:
    result: list[OperationCoverageSpec] = []
    seen: set[str] = set()
    for spec in specs:
        if not spec.action or spec.action in seen:
            continue
        seen.add(spec.action)
        result.append(spec)
    return result
