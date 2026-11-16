from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any


_TRANSPORT_EXPLICIT_TERMS = (
    "交通",
    "运输",
    "公交",
    "客运",
    "干线",
    "支线",
    "接驳",
    "换乘",
    "车次",
    "发车",
    "运力",
    "客流",
    "票务",
)
_TRANSPORT_ROUTE_DECISIVE_TERMS = (
    "干线",
    "支线",
    "接驳",
    "换乘",
    "公交",
    "客运",
    "线路调度",
    "交通线路",
    "运输线路",
    "车次",
    "发车",
)
_TRANSPORT_WEAK_TERMS = ("班次", "线路", "路径", "节点", "站点", "车站", "枢纽", "调度")
_ATTENDANCE_TERMS = ("考勤", "打卡", "排班", "补卡", "请假", "加班", "员工", "人力资源")
_AGENCY_ACCOUNTING_TERMS = ("代理记账", "代账", "财税代办", "核算账套", "税务申报", "记账凭证")
_MEDICAL_TERMS = ("医疗", "医院", "诊疗", "护理", "患者", "病区", "床位", "住院", "生命体征", "医嘱", "护士", "医生", "病历")
_SURVEYING_TERMS = ("测绘", "测量", "桩号", "断面", "高程", "水准", "导线", "放样", "控制点", "坐标", "外业", "道路", "道路工程")
_MANUFACTURING_TERMS = ("制造", "生产", "产线", "工单", "工序", "排程", "换线", "节拍", "在制品")
_RAIL_TERMS = ("轨道交通", "地铁", "铁路", "轨道工程", "隧道工程", "车站工程")
_CONSTRUCTION_QUALITY_TERMS = ("施工质量", "工程质量", "检验批", "检验点", "质量计划", "材料复检", "整改验收", "工程部位", "单位工程", "标段")
_DESIGN_VIEWER_TERMS = ("Figma", "设计文件", "设计资源", "画板", "画布", "图层", "组件实例", "原型演示", "设计评审")
_DOWNLOAD_MANAGER_TERMS = ("下载链接", "下载任务", "下载队列", "后台下载", "下载进度", "断点续传", "已下载文件", "下载记录")


@dataclass(frozen=True)
class DomainProfile:
    key: str
    confidence: float
    source: str
    transport_related: bool
    requires_route_topology: bool
    evidence: tuple[str, ...] = ()
    weak_evidence: tuple[str, ...] = ()
    excluded_evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "enabled_gate_keys": self.enabled_gate_keys,
            "gate_reasons": self.gate_reasons,
        }

    @property
    def enabled_gate_keys(self) -> tuple[str, ...]:
        if self.requires_route_topology:
            return ("ui_route_topology",)
        return ()

    @property
    def gate_reasons(self) -> tuple[str, ...]:
        if self.requires_route_topology:
            evidence = "、".join(self.evidence) or "交通线路子类型"
            return (f"识别为交通线路类（{evidence}），要求截图包含干线、支线接驳和服务时窗。",)
        if self.excluded_evidence:
            return tuple(f"未启用交通线路拓扑门禁：{reason}" for reason in self.excluded_evidence)
        return ("未启用交通线路拓扑门禁：当前领域不要求干线、支线接驳和服务时窗证据。",)


def build_domain_profile(
    task: Any | None = None,
    blueprint: Any | None = None,
    *,
    context_text: str = "",
) -> DomainProfile:
    text = _context_text(task, blueprint, context_text)
    subtype_key = str(getattr(blueprint, "industry_subtype_key", "") or "").strip()
    explicit_transport = _matched_terms(text, _TRANSPORT_EXPLICIT_TERMS)
    decisive_route = _matched_terms(text, _TRANSPORT_ROUTE_DECISIVE_TERMS)
    weak_transport = _matched_terms(text, _TRANSPORT_WEAK_TERMS)
    attendance = _matched_terms(text, _ATTENDANCE_TERMS)
    agency_accounting = _matched_terms(text, _AGENCY_ACCOUNTING_TERMS)
    medical = _matched_terms(text, _MEDICAL_TERMS)
    surveying = _matched_terms(text, _SURVEYING_TERMS)
    manufacturing = _matched_terms(text, _MANUFACTURING_TERMS)
    rail = _matched_terms(text, _RAIL_TERMS)
    construction_quality = _matched_terms(text, _CONSTRUCTION_QUALITY_TERMS)
    design_viewer = _matched_terms(text, _DESIGN_VIEWER_TERMS)
    download_manager = _matched_terms(text, _DOWNLOAD_MANAGER_TERMS)

    if subtype_key:
        requires_route_topology = subtype_key == "transport_route"
        evidence = decisive_route or explicit_transport
        exclusions = _context_exclusions(attendance, medical, surveying, manufacturing, rail, construction_quality)
        return DomainProfile(
            key=subtype_key,
            confidence=0.99,
            source="blueprint-industry-subtype",
            transport_related=requires_route_topology or bool(explicit_transport),
            requires_route_topology=requires_route_topology,
            evidence=evidence,
            weak_evidence=weak_transport,
            excluded_evidence=exclusions if not requires_route_topology else (),
        )

    if design_viewer and ("Figma" in design_viewer or len(design_viewer) >= 2):
        return DomainProfile(
            key="design_viewer",
            confidence=0.97,
            source="design-viewer-evidence",
            transport_related=False,
            requires_route_topology=False,
            evidence=design_viewer,
            weak_evidence=weak_transport,
            excluded_evidence=("设计文件浏览语境",),
        )

    if len(download_manager) >= 2:
        return DomainProfile(
            key="download_manager",
            confidence=0.96,
            source="download-manager-evidence",
            transport_related=False,
            requires_route_topology=False,
            evidence=download_manager,
            weak_evidence=weak_transport,
            excluded_evidence=("文件下载任务调度不是交通线路调度",),
        )

    if rail and construction_quality:
        return DomainProfile(
            key="rail_construction_quality",
            confidence=0.97,
            source="rail-quality-evidence",
            transport_related=False,
            requires_route_topology=False,
            evidence=rail + construction_quality,
            weak_evidence=weak_transport,
            excluded_evidence=("轨道施工质量不启用交通线路拓扑门禁",),
        )

    route_evidence = decisive_route
    route_topology = bool(route_evidence)
    if not route_topology and explicit_transport:
        route_topology = bool(set(weak_transport) & {"线路", "站点", "车站", "枢纽", "班次", "调度"})
        if route_topology:
            route_evidence = explicit_transport + weak_transport
    if route_topology and not decisive_route and (attendance or medical or surveying or manufacturing):
        route_topology = False
        route_evidence = ()
    if route_topology:
        return DomainProfile(
            key="transport_route",
            confidence=0.92 if decisive_route else 0.84,
            source="explicit-transport-route-evidence",
            transport_related=True,
            requires_route_topology=True,
            evidence=route_evidence,
            weak_evidence=weak_transport,
        )

    excluded = _context_exclusions(attendance, medical, surveying, manufacturing, rail, construction_quality)
    if agency_accounting:
        key = "agency_accounting"
        confidence = 0.98
        source = "agency-accounting-evidence"
        evidence = agency_accounting
    elif attendance:
        key = "workforce_attendance"
        confidence = 0.93
        source = "attendance-evidence"
        evidence = attendance
    elif medical:
        key = "medical"
        confidence = 0.9
        source = "medical-evidence"
        evidence = medical
    elif surveying:
        key = "survey_mapping"
        confidence = 0.9
        source = "surveying-evidence"
        evidence = surveying
    elif manufacturing:
        key = "smart_manufacturing"
        confidence = 0.88
        source = "manufacturing-evidence"
        evidence = manufacturing
    else:
        key = "general_business"
        confidence = 0.6
        source = "generic-fallback"
        evidence = ()
    if weak_transport:
        excluded += tuple(f"弱词不触发交通门禁:{term}" for term in weak_transport)
    return DomainProfile(
        key=key,
        confidence=confidence,
        source=source,
        transport_related=bool(explicit_transport) and not bool(attendance or medical or surveying or manufacturing),
        requires_route_topology=False,
        evidence=evidence,
        weak_evidence=weak_transport,
        excluded_evidence=_unique(excluded),
    )


def has_transport_domain_signal(text: str) -> bool:
    return build_domain_profile(context_text=text).transport_related


def requires_transport_route_topology(text: str) -> bool:
    return build_domain_profile(context_text=text).requires_route_topology


def _context_text(task: Any | None, blueprint: Any | None, context_text: str) -> str:
    values = [context_text]
    if task is not None:
        values.extend(
            [
                getattr(task, "software_name", ""),
                getattr(task, "product_type", ""),
                getattr(task, "feature_hint", ""),
            ]
        )
    if blueprint is not None:
        values.extend(
            [
                getattr(blueprint, "industry", ""),
                getattr(blueprint, "summary", ""),
                getattr(blueprint, "scenario", ""),
                getattr(blueprint, "positioning", ""),
                " ".join(str(item) for item in (getattr(blueprint, "business_objects", []) or [])[:16]),
                " ".join(str(getattr(item, "title", "") or "") for item in (getattr(blueprint, "modules", []) or [])[:16]),
            ]
        )
    return " ".join(str(value or "").strip() for value in values if str(value or "").strip())


def _matched_terms(text: str, terms: tuple[str, ...]) -> tuple[str, ...]:
    value = str(text or "")
    return tuple(term for term in terms if term in value)


def _context_exclusions(
    attendance: tuple[str, ...],
    medical: tuple[str, ...],
    surveying: tuple[str, ...],
    manufacturing: tuple[str, ...],
    rail: tuple[str, ...],
    construction_quality: tuple[str, ...],
) -> tuple[str, ...]:
    values: list[str] = []
    if attendance:
        values.append("考勤/人力资源语境")
    if medical:
        values.append("医疗语境")
    if surveying:
        values.append("测绘语境")
    if manufacturing:
        values.append("制造语境")
    if rail and construction_quality:
        values.append("轨道施工质量语境")
    return tuple(values)


def _unique(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value))
