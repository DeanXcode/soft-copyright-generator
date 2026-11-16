from __future__ import annotations

import json
import re
import time
from typing import Any

from .llm.provider import LLMProvider, LocalTemplateProvider, TextRetryPolicy
from .llm.trace import trace_event
from .llm.json_response import parse_json_object


DOMAIN_PROFILES = [
    {
        "id": "music_audio",
        "triggers": ["听歌", "音乐", "歌曲", "歌单", "播放器", "歌词", "歌手", "专辑", "电台", "音质"],
        "keywords": [
            "音乐首页推荐",
            "歌曲播放控制",
            "歌词同步显示",
            "歌单收藏管理",
            "音乐搜索",
            "歌手专辑浏览",
            "最近播放记录",
            "离线下载缓存",
            "会员音质权益",
            "播放偏好设置",
        ],
    },
    {
        "id": "food_ordering",
        "triggers": ["点餐", "订餐", "外卖", "餐饮", "菜单", "菜品", "餐厅", "堂食", "取餐", "下单"],
        "keywords": [
            "菜品浏览",
            "菜单分类",
            "购物车选餐",
            "规格口味选择",
            "订单提交",
            "在线支付",
            "堂食取餐",
            "外卖配送",
            "优惠券使用",
            "订单状态跟踪",
            "历史订单",
            "门店信息",
        ],
    },
    {
        "id": "reading_audio",
        "triggers": ["阅读", "听书", "有声", "小说", "书籍", "图书", "书城", "朗读", "电子书"],
        "keywords": [
            "书城浏览",
            "书架管理",
            "小说阅读",
            "有声听书",
            "章节目录",
            "听书播放",
            "阅读进度",
            "播放进度",
            "离线缓存",
            "收藏订阅",
            "书单推荐",
            "会员权益",
        ],
    },
    {
        "id": "game",
        "triggers": ["游戏", "手游", "小游戏", "消除", "点消", "三消", "连消", "关卡地图", "玩家", "道具背包"],
        "keywords": ["玩家账号", "关卡地图", "对局棋盘", "目标得分", "剩余步数", "道具背包", "结算统计", "星级评价"],
    },
    {
        "id": "education",
        "triggers": ["教育", "学习", "课程", "作业", "考试", "题库", "学情", "课堂", "培训", "实训", "考核"],
        "keywords": ["课程资源", "学习任务", "作业收交", "批改进度", "学情分析", "错题记录", "班级管理", "学习报告"],
    },
    {
        "id": "workforce_attendance",
        "triggers": ["考勤", "打卡", "签到", "签退", "补卡", "请假", "出勤", "迟到", "早退"],
        "keywords": ["员工档案", "班次排班", "上下班打卡", "补卡申请", "请假申请", "出勤统计", "异常考勤", "考勤规则"],
    },
    {
        "id": "finance",
        "triggers": ["金融", "贷款", "信贷", "支付", "清算", "账单", "授信", "风控"],
        "keywords": ["客户授信", "贷款申请", "额度测算", "还款计划", "交易流水", "清算批次", "风险评级", "账单统计"],
    },
    {
        "id": "medical",
        "triggers": ["医疗", "医院", "诊疗", "处方", "病历", "药品", "随访", "护理", "患者", "检验", "手术", "麻醉", "科室", "医生", "排班", "排程", "气道", "插管", "急救", "临床", "医护", "技能演练"],
        "keywords": ["患者档案", "诊疗记录", "气道评估", "插管操作", "急救演练", "技能考核", "手术申请", "手术排班", "术前确认", "麻醉协同", "科室协调", "护理任务", "检查报告", "医嘱执行"],
    },
    {
        "id": "ticketing",
        "triggers": ["票务", "门禁", "闸机", "景区", "门票", "年卡", "订单", "核销"],
        "keywords": ["景区票务", "团队订单", "门票核销", "闸机通行", "年卡管理", "入园记录", "预约时段", "客流统计"],
    },
    {
        "id": "city",
        "triggers": ["城市", "事件", "巡检", "网格", "指挥", "调度", "工单", "处置"],
        "keywords": ["城市事件", "网格巡检", "任务派发", "现场处置", "超期提醒", "地图定位", "协同调度", "事件统计"],
    },
]


def harmonize_feature_hint(
    software_name: str,
    product_type: str,
    provided: str = "",
    provider: LLMProvider | None = None,
    require_llm: bool = False,
    min_blueprint_modules: int = 0,
) -> tuple[str, dict]:
    decisive_contract = decisive_feature_contract(software_name, provided)
    if decisive_contract:
        return decisive_contract
    llm_result, failure_message = infer_feature_hint_with_llm(
        software_name,
        product_type,
        provided,
        provider,
        min_blueprint_modules=min_blueprint_modules,
    )
    if llm_result:
        return _harmonize_llm_result(provided, llm_result)
    if require_llm:
        return "", {
            "auto_feature_hint": False,
            "feature_hint_profile": "",
            "feature_hint_source": "llm-failed",
            "requires_gpt": True,
            "original_feature_hint": _clean_hint(provided),
            "failure_message": failure_message,
        }

    inferred, profile_id = infer_feature_hint(software_name, product_type)
    provided = _clean_hint(provided)
    if not inferred:
        return provided, {"auto_feature_hint": False, "feature_hint_profile": "", "feature_hint_source": "provided"}

    provided_profile = _profile_id(f"{provided} {product_type}") if provided else ""
    source = "provided"
    if not provided:
        result = inferred
        source = "auto-name"
    elif profile_id == "name-derived":
        result = _merge_hints(provided, inferred)
        source = "provided-merged"
    elif profile_id and provided_profile and provided_profile != profile_id:
        result = inferred
        source = "auto-replaced-mismatch"
    elif profile_id and not _has_profile_hit(provided, profile_id):
        result = inferred
        source = "auto-replaced-mismatch"
    else:
        result = _merge_hints(provided, inferred)
        source = "provided-merged"

    return result, {
        "auto_feature_hint": source != "provided",
        "feature_hint_profile": profile_id,
        "feature_hint_source": source,
        "inferred_feature_hint": inferred,
        "original_feature_hint": provided,
    }


def infer_feature_hint_with_llm(
    software_name: str,
    product_type: str = "",
    provided: str = "",
    provider: LLMProvider | None = None,
    min_blueprint_modules: int = 0,
) -> tuple[dict[str, Any] | None, str]:
    if provider is None or isinstance(provider, LocalTemplateProvider):
        return None, "未配置 GPT 模型服务"
    started_at = time.perf_counter()
    trace_event(
        "feature_hint_inference_begin",
        software_name=software_name,
        product_type=product_type,
        provided=bool(_clean_hint(provided)),
    )
    try:
        detailed_modules = min_blueprint_modules >= 8
        if detailed_modules:
            result = _infer_detailed_feature_hint_with_llm(provider, software_name, product_type, provided)
        else:
            result = _infer_lightweight_feature_hint_two_step(provider, software_name, product_type, provided)
        if result and _llm_result_meets_blueprint_floor(result, software_name, min_blueprint_modules):
            elapsed_seconds = round(time.perf_counter() - started_at, 3)
            result["elapsed_seconds"] = elapsed_seconds
            trace_event(
                "feature_hint_inference_success",
                elapsed_seconds=elapsed_seconds,
                feature_hint=result.get("feature_hint", ""),
                profile=result.get("profile", ""),
                should_replace=bool(result.get("should_replace")),
                blueprint_module_count=len(result.get("blueprint_modules") or []),
            )
            return result, ""
        if result:
            failure_message = "GPT 返回的蓝图模块不符合质量要求，请重试。"
        else:
            failure_message = "GPT 返回内容为空或不是可解析的 JSON 蓝图。"
    except FeatureHintStageError as exc:
        failure_message = str(exc)
        trace_event(
            "feature_hint_inference_error",
            elapsed_seconds=round(time.perf_counter() - started_at, 3),
            error_type=type(exc).__name__,
            stage=exc.stage,
            error=str(exc)[:500],
        )
    except Exception as exc:
        failure_message = _safe_llm_error_message(exc)
        trace_event(
            "feature_hint_inference_error",
            elapsed_seconds=round(time.perf_counter() - started_at, 3),
            error_type=type(exc).__name__,
            error=str(exc)[:500],
        )
    return None, failure_message


class FeatureHintStageError(RuntimeError):
    def __init__(self, stage: str, message: str):
        super().__init__(message)
        self.stage = stage


def _infer_detailed_feature_hint_with_llm(
    provider: LLMProvider,
    software_name: str,
    product_type: str,
    provided: str,
) -> dict[str, Any] | None:
    content = provider.chat(
        [
            {
                "role": "system",
                "content": (
                    "你是中文软件产品经理和软著材料业务分析专家。"
                    "请根据软件名称推断真实软件业务边界，生成可用于软著材料的结构化产品蓝图。"
                    "只返回 JSON，不要 Markdown，不要编造公司主体信息。"
                ),
            },
            {
                "role": "user",
                "content": _build_llm_prompt(
                    software_name,
                    product_type,
                    provided,
                    detailed_modules=True,
                ),
            },
        ],
        temperature=0.25,
        max_tokens=6000,
        response_format={"type": "json_object"},
        trace_label="feature_hint:infer_full",
        retry_policy=TextRetryPolicy(max_retries=1),
    )
    return _normalize_llm_result(_parse_json(content))


def _infer_lightweight_feature_hint_two_step(
    provider: LLMProvider,
    software_name: str,
    product_type: str,
    provided: str,
) -> dict[str, Any] | None:
    # The desktop outline timeout is applied to each of the two lightweight
    # requests.  Keep retries at the operation layer (the user can retry the
    # outline) so a slow gateway response does not multiply into an opaque
    # queue timeout.
    step_timeout = _lightweight_step_timeout(provider)
    step_retry_policy = TextRetryPolicy(max_retries=0)
    try:
        profile_content = provider.chat(
            [
                {
                    "role": "system",
                    "content": (
                        "你是中文软件产品经理。请只根据软件名称判断真实业务领域和关键词。"
                        "只返回 JSON，不要 Markdown，不要编造公司主体信息。"
                    ),
                },
                {
                    "role": "user",
                    "content": _build_domain_profile_prompt(software_name, product_type, provided),
                },
            ],
            temperature=0.15,
            max_tokens=700,
            response_format={"type": "json_object"},
            trace_label="feature_hint:profile",
            timeout=step_timeout,
            retry_policy=step_retry_policy,
        )
        profile = _normalize_domain_profile(_parse_json(profile_content))
    except Exception as exc:
        raise FeatureHintStageError("profile", _stage_failure_message("名称理解", exc)) from exc
    if not profile.get("feature_hint"):
        raise FeatureHintStageError("profile", "GPT 名称理解失败：模型未返回可用关键词。")

    try:
        modules_content = provider.chat(
            [
                {
                    "role": "system",
                    "content": (
                        "你是中文软件产品经理。请基于已识别的业务领域生成可编辑模块草案。"
                        "只返回 JSON，不要 Markdown，不要编造公司主体信息。"
                    ),
                },
                {
                    "role": "user",
                    "content": _build_outline_modules_prompt(software_name, product_type, provided, profile),
                },
            ],
            temperature=0.25,
            max_tokens=1400,
            response_format={"type": "json_object"},
            trace_label="feature_hint:modules",
            timeout=step_timeout,
            retry_policy=step_retry_policy,
        )
        modules_data = _parse_json(modules_content)
    except Exception as exc:
        raise FeatureHintStageError("modules", _stage_failure_message("模块草案生成", exc)) from exc
    combined = {
        **profile,
        "blueprint_modules": modules_data.get("blueprint_modules") or modules_data.get("modules") or [],
        "reason": _clean_hint(str(modules_data.get("reason") or profile.get("reason") or "")),
        "should_replace": True,
    }
    return _normalize_llm_result(combined)


def _lightweight_step_timeout(provider: LLMProvider) -> int:
    configured = getattr(getattr(provider, "config", None), "timeout", 60)
    try:
        configured_seconds = int(configured or 60)
    except (TypeError, ValueError):
        configured_seconds = 60
    return max(30, min(120, configured_seconds))


def _safe_llm_error_message(exc: Exception) -> str:
    raw = str(exc or "")
    lowered = raw.lower()
    if "timeout" in lowered or "timed out" in lowered or "read timed out" in lowered:
        return "GPT 蓝图请求超时：模型网关响应过慢，请稍后重试或检查网关状态。"
    status_match = re.search(r"(?:HTTP\s+|status(?:_code)?[=:]\s*|([45]\d{2})\s+Server Error)", raw, re.IGNORECASE)
    if status_match:
        status = status_match.group(1) or status_match.group(2)
        if status == "503":
            return "GPT 蓝图请求失败：模型网关返回 503 服务不可用，请稍后重试或切换可用模型。"
        if status == "429":
            return "GPT 蓝图请求失败：模型网关限流或额度不足，请稍后重试或检查账户额度。"
        if status in {"401", "403"}:
            return "GPT 蓝图请求失败：API Key 无效或无模型访问权限，请检查 GPT 配置。"
        return f"GPT 蓝图请求失败：模型网关返回 HTTP {status}，请检查模型服务状态。"
    if "json" in lowered:
        return "GPT 蓝图请求失败：模型返回内容不是有效 JSON，请重试。"
    if raw:
        return f"GPT 蓝图请求失败：{raw[:120]}"
    return "GPT 蓝图请求失败：模型服务未返回可用结果。"


def _stage_failure_message(stage_label: str, exc: Exception) -> str:
    message = _safe_llm_error_message(exc)
    message = re.sub(r"^GPT 蓝图请求失败：", "", message)
    message = re.sub(r"^GPT 蓝图请求超时：", "请求超时：", message)
    return f"GPT {stage_label}失败：{message}"


def _build_llm_prompt(software_name: str, product_type: str, provided: str, detailed_modules: bool = True) -> str:
    if not detailed_modules:
        return _build_lightweight_llm_prompt(software_name, product_type, provided)
    return f"""
请只返回 JSON，不要 Markdown。根据软件名称推断真实产品边界，并生成可用于软著材料的业务蓝图。

软件名称：{software_name}
产品类型：{product_type or "未提供"}
用户补充：{_clean_hint(provided) or "未填写"}

硬性要求：
1. blueprint_modules 必须 8-10 个，少于 8 个不合格。
2. 模块必须覆盖不同业务环节，不能只重复软件名或只写“录入/查询/统计”。
3. title 为 6-16 字具体功能名，禁止包含完整软件名称。
4. 至少 4 个不同 category，例如建档、采集、监测、预警、建议、处置、统计、配置等。
5. description 80-140 个中文字符，写清对象、动作、状态、校验点或输出。
6. 禁止泛型模块：数据管理、业务处理、统计分析、系统设置、权限管理、核心模块。
7. 如果名称包含“监测、建议、平台、系统”，要拆出对象/项目建档、采集接入、过程监测、阈值预警、建议生成、处置闭环、记录追溯、报表分析等环节。
8. 每个模块需要直接给出后续软著材料可用的 key、entities、operations、operation_specs、data_fields、pages、rules，避免后续再次请求模型补模块明细。
9. operation_specs 至少 3 个，必须覆盖查询和业务处理/结果类动作；动作需要写明角色、触发条件、输入字段、前后状态和结果证据，不能只把模块名拼接“登记/校验/分析/确认/归档”。

返回 JSON 结构：
{{
  "profile": "简短英文领域标识",
  "domain": "中文领域短语",
  "target_users": ["目标用户1", "目标用户2"],
  "keywords": ["关键词1", "关键词2"],
  "feature_hint": "关键词1、关键词2、关键词3",
  "avoid_terms": ["应避免方向1", "应避免方向2"],
  "blueprint_modules": [
    {{
      "key": "lowercase_domain_key",
      "category": "模块分类",
      "title": "模块名称",
      "description": "80-140字真实业务说明，说明对象、动作、流转、校验点和输出。",
      "entities": ["EnglishEntityRecord", "EnglishEntityTrace"],
      "operations": ["具体操作1", "具体操作2", "具体操作3", "具体操作4", "具体操作5"],
      "operation_specs": [
        {{
          "action_key": "domain_action_key",
          "label": "领域动作名称",
          "category": "lookup|mutation|import|export|analysis|workflow|result|instant|destructive",
          "role": "执行角色",
          "trigger": "触发条件",
          "input_fields": ["输入字段1", "输入字段2"],
          "pre_state": "操作前状态",
          "post_state": "操作后状态",
          "result_evidence": "页面可见的结果、日志或状态证据",
          "requires_confirmation": false
        }}
      ],
      "data_fields": ["业务字段1", "业务字段2", "业务字段3", "业务字段4", "业务字段5", "业务字段6"],
      "data_objects": ["关键数据对象1", "关键数据对象2"],
      "user_flow": ["用户步骤1", "用户步骤2", "用户步骤3"],
      "screens": ["页面/界面1", "页面/界面2"],
      "pages": ["页面1", "页面2"],
      "rules": ["校验/权限/状态规则1", "校验/权限/状态规则2", "校验/权限/状态规则3"]
    }}
  ],
  "should_replace": true,
  "reason": "为什么这样补充"
}}
""".strip()


def _build_domain_profile_prompt(software_name: str, product_type: str, provided: str) -> str:
    return f"""
请只返回 JSON，不要 Markdown。根据软件名称快速识别真实产品领域，输出后续软著材料蓝图会用到的业务语义。

软件名称：{software_name}
产品类型：{product_type or "未提供"}
用户补充：{_clean_hint(provided) or "未填写"}

要求：
1. 不生成模块明细，只判断领域、对象、用户和关键词。
2. keywords 8-14 个，必须是业务对象或业务动作，不要写“数据管理、系统设置、统计分析”。
3. feature_hint 用 keywords 串联，长度不超过 120 字。
4. avoid_terms 写 3-6 个容易跑偏的方向。

返回 JSON 结构：
{{
  "profile": "简短英文领域标识",
  "domain": "中文领域短语",
  "target_users": ["目标用户1", "目标用户2"],
  "keywords": ["业务关键词1", "业务关键词2"],
  "feature_hint": "业务关键词1、业务关键词2、业务关键词3",
  "avoid_terms": ["应避免方向1", "应避免方向2"],
  "should_replace": true,
  "reason": "为什么这样理解"
}}
""".strip()


def _build_outline_modules_prompt(
    software_name: str,
    product_type: str,
    provided: str,
    profile: dict[str, Any],
) -> str:
    profile_json = json.dumps(
        {
            "domain": profile.get("domain") or "",
            "target_users": profile.get("target_users") or [],
            "keywords": profile.get("keywords") or [],
            "feature_hint": profile.get("feature_hint") or "",
            "avoid_terms": profile.get("avoid_terms") or [],
        },
        ensure_ascii=False,
    )
    return f"""
请只返回 JSON，不要 Markdown。基于已识别的业务语义生成可编辑的蓝图模块草案。

软件名称：{software_name}
产品类型：{product_type or "未提供"}
用户补充：{_clean_hint(provided) or "未填写"}
已识别业务语义：{profile_json}

要求：
1. 生成 8-10 个候选业务模块，用于前端可编辑蓝图。
2. 每个模块只需要 key、category、title、description、data_objects、screens。
3. description 40-90 个中文字符，说明业务对象、动作、状态或输出。
4. 至少 4 个不同 category，避免泛型模块名称。
5. 模块应覆盖完整业务链路，不要只围绕同一个关键词换说法。
6. 禁止模块标题：数据管理、业务处理、统计分析、系统设置、权限管理、核心模块。

返回 JSON 结构：
{{
  "blueprint_modules": [
    {{
      "key": "lowercase_domain_key",
      "category": "模块分类",
      "title": "模块名称",
      "description": "40-90字业务说明，说明对象、动作、状态或输出。",
      "data_objects": ["关键数据对象1", "关键数据对象2"],
      "screens": ["页面/界面1", "页面/界面2"]
    }}
  ],
  "reason": "模块这样拆分的原因"
}}
""".strip()


def _build_lightweight_llm_prompt(software_name: str, product_type: str, provided: str) -> str:
    return f"""
请只返回 JSON，不要 Markdown。根据软件名称推断真实产品边界，生成可编辑的业务蓝图。

软件名称：{software_name}
产品类型：{product_type or "未提供"}
用户补充：{_clean_hint(provided) or "未填写"}

要求：
1. 快速生成 8-10 个候选业务模块，用于前端可编辑蓝图。
2. 每个模块只需要 key、category、title、description、data_objects、screens。
3. description 40-90 个中文字符，说明业务对象、动作和输出结果。
4. 至少 4 个不同 category，避免泛型模块名称。
5. feature_hint 用 8-14 个关键词串联，后续正式生成会再次生成完整产品蓝图。

返回 JSON 结构：
{{
  "profile": "简短英文领域标识",
  "domain": "中文领域短语",
  "target_users": ["目标用户1", "目标用户2"],
  "keywords": ["关键词1", "关键词2"],
  "feature_hint": "关键词1、关键词2、关键词3",
  "avoid_terms": ["应避免方向1", "应避免方向2"],
  "blueprint_modules": [
    {{
      "key": "lowercase_domain_key",
      "category": "模块分类",
      "title": "模块名称",
      "description": "40-90字业务说明，说明对象、动作、状态或输出。",
      "data_objects": ["关键数据对象1", "关键数据对象2"],
      "screens": ["页面/界面1", "页面/界面2"]
    }}
  ],
  "should_replace": true,
  "reason": "为什么这样补全"
}}
""".strip()


def _harmonize_llm_result(provided: str, result: dict[str, Any]) -> tuple[str, dict]:
    provided = _clean_hint(provided)
    inferred = _limit_hint(str(result.get("feature_hint") or ""))
    if not inferred:
        return provided, {"auto_feature_hint": False, "feature_hint_profile": "", "feature_hint_source": "provided"}
    if not provided:
        final = inferred
        source = "llm-name"
    elif bool(result.get("should_replace")):
        final = inferred
        source = "llm-replaced-mismatch"
    else:
        final = _merge_hints(provided, inferred)
        source = "llm-merged"
    return final, {
        "auto_feature_hint": source != "provided",
        "feature_hint_profile": str(result.get("profile") or "llm"),
        "feature_hint_source": source,
        "inferred_feature_hint": inferred,
        "original_feature_hint": provided,
        "feature_hint_domain": str(result.get("domain") or ""),
        "feature_hint_reason": str(result.get("reason") or "")[:300],
        "feature_hint_keywords": result.get("keywords") or [],
        "feature_hint_avoid_terms": result.get("avoid_terms") or [],
        "feature_hint_target_users": result.get("target_users") or [],
        "feature_hint_blueprint_modules": result.get("blueprint_modules") or [],
        "feature_hint_elapsed_seconds": result.get("elapsed_seconds", 0),
    }


def decisive_feature_contract(software_name: str, provided: str = "") -> tuple[str, dict] | None:
    """Return a deterministic semantic contract for an unambiguous software name."""
    contract = _decisive_name_contract(software_name)
    return _harmonize_llm_result(provided, contract) if contract else None


def _decisive_name_contract(software_name: str) -> dict[str, Any] | None:
    text = _clean_hint(software_name)
    if not any(term in text for term in ("代理记账", "代账", "财税代办")):
        return None

    module_specs = (
        ("client_ledger_setup", "客户建档", "客户与账套建档", "维护企业客户、服务合同、会计制度、纳税人资格和账套期间，校验统一社会信用代码与服务范围后启用账套，为后续票据、凭证、申报和报表建立唯一核算边界。", ["企业客户", "服务合同", "核算账套"], ["查询客户账套", "登记企业客户", "启用核算账套", "变更服务范围", "导出客户清单"], ["客户编码", "企业名称", "统一社会信用代码", "纳税人资格", "会计制度", "账套期间", "服务状态"], ["客户账套台", "客户建档详情"]),
        ("invoice_document_intake", "票据采集", "票据与原始凭证采集", "接收客户提交的销项发票、进项发票、费用单据和银行回单，完成来源登记、影像关联、期间归属、重复票据校验与缺件标记，形成待制证原始凭证清单。", ["票据批次", "发票记录", "原始凭证"], ["查询票据批次", "导入票据影像", "校验重复票据", "标记缺失附件", "提交待制证清单"], ["票据编号", "票据类型", "开票日期", "含税金额", "税额", "所属期间", "附件状态"], ["票据采集台", "票据校验详情"]),
        ("voucher_preparation_review", "会计核算", "记账凭证编制复核", "依据已验收票据和业务性质编制会计分录，维护摘要、科目、借贷金额和辅助核算项，通过借贷平衡与期间规则校验后提交复核并形成可追溯凭证。", ["记账凭证", "会计分录", "科目余额"], ["查询待制凭证", "编制会计分录", "校验借贷平衡", "提交凭证复核", "退回异常凭证"], ["凭证字号", "凭证日期", "会计科目", "摘要", "借方金额", "贷方金额", "复核状态"], ["凭证编制台", "凭证复核详情"]),
        ("bank_reconciliation", "资金核对", "银行流水与账务对账", "导入客户银行流水并按金额、日期、对方户名和摘要匹配账务记录，对未达账项进行认领、调整或挂起，输出对账差异与处理结果。", ["银行流水", "账务记录", "未达账项"], ["查询对账批次", "导入银行流水", "匹配账务记录", "认领未达账项", "生成差异清单"], ["银行账号", "交易日期", "交易金额", "对方户名", "交易摘要", "匹配状态", "差异原因"], ["银行对账台", "未达账项详情"]),
        ("period_close", "期末处理", "月末结转与关账", "在凭证复核、银行对账和税费计提完成后执行损益结转、余额试算和期间完整性检查，对异常科目退回调整，确认无误后关闭会计期间并保留关账证据。", ["会计期间", "结转任务", "试算平衡表"], ["查询期末任务", "执行损益结转", "检查试算平衡", "退回期末异常", "确认期间关账"], ["会计期间", "结转批次", "借方合计", "贷方合计", "异常科目数", "关账状态", "关账时间"], ["期末结账台", "试算平衡详情"]),
        ("tax_declaration", "税务申报", "税费测算与申报管理", "按客户税种认定和申报周期汇总销项、进项、收入、成本及优惠数据，完成税额测算、申报表复核、申报回执登记和异常更正，跟踪各税种申报状态。", ["税种认定", "申报任务", "申报回执"], ["查询申报任务", "测算应纳税额", "复核申报表", "登记申报回执", "发起申报更正"], ["税款所属期", "税种", "计税依据", "应纳税额", "优惠金额", "申报状态", "回执编号"], ["税务申报台", "申报任务详情"]),
        ("financial_reporting", "财务报告", "财务报表出具", "从已关账期间汇总资产负债、利润和现金流数据，执行报表勾稽与期初期末校验，生成客户财务报表、科目余额表及经营摘要并记录交付版本。", ["财务报表", "科目余额表", "报表版本"], ["查询报表期间", "生成财务报表", "校验报表勾稽", "发布报表版本", "导出客户报表"], ["报表期间", "资产总额", "负债总额", "营业收入", "利润总额", "勾稽状态", "版本号"], ["财务报表台", "报表校验详情"]),
        ("service_delivery_archive", "服务交付", "代账任务交付归档", "汇总代账周期内的票据接收、凭证复核、对账、关账、申报和报表成果，核对服务清单与缺失事项，向客户交付结果并按账套和期间归档审计记录。", ["服务周期", "交付清单", "归档记录"], ["查询交付周期", "核对服务清单", "确认客户交付", "归档账务材料", "导出交付目录"], ["服务期间", "客户名称", "凭证数量", "申报完成数", "报表版本", "缺失事项", "归档状态"], ["服务交付台", "材料归档详情"]),
    )
    modules: list[dict[str, Any]] = []
    for key, category, title, description, objects, operations, fields, pages in module_specs:
        modules.append(
            {
                "key": key,
                "category": category,
                "title": title,
                "description": description,
                "entities": [f"{''.join(part.title() for part in key.split('_'))}Record", f"{''.join(part.title() for part in key.split('_'))}Trace"],
                "operations": operations,
                "operation_specs": _decisive_operation_specs(key, title, operations, fields),
                "data_fields": fields,
                "data_objects": objects,
                "user_flow": [f"进入{pages[0]}", operations[0], operations[1], operations[2], f"查看{title}处理结果"],
                "screens": pages,
                "pages": pages,
                "rules": [f"{title}数据必须归属于唯一企业客户和会计期间", f"{operations[1]}前必须通过必填字段与状态校验", f"{operations[2]}结果必须记录经办人、时间和审计证据"],
            }
        )
    keywords = ["企业客户建档", "核算账套", "票据采集", "记账凭证", "银行对账", "月末结账", "税务申报", "财务报表", "服务交付", "材料归档"]
    return {
        "profile": "agency_accounting",
        "domain": "企业代理记账与财税服务",
        "target_users": ["代账会计", "复核会计", "税务专员", "财务主管", "客户对接人员"],
        "keywords": keywords,
        "feature_hint": "、".join(keywords),
        "avoid_terms": ["个人消费记账", "个人账本", "游戏修改器", "游戏辅助工具", "月影题材内容", "消费级移动应用"],
        "blueprint_modules": modules,
        "should_replace": True,
        "reason": "软件名称中的“代账”按企业代理记账和财税服务解释，品牌词不得改变核心业务领域。",
        "elapsed_seconds": 0,
    }


def _decisive_operation_specs(key: str, title: str, operations: list[str], fields: list[str]) -> list[dict[str, Any]]:
    categories = ("lookup", "mutation", "workflow")
    return [
        {
            "action_key": f"{key}_{index}",
            "label": label,
            "category": categories[index - 1],
            "role": "代账业务人员" if index < 3 else "复核会计",
            "trigger": f"需要执行{label}时",
            "input_fields": fields[:3],
            "pre_state": f"{title}处于待处理状态",
            "post_state": f"{label}已完成并更新业务状态",
            "result_evidence": f"页面显示{label}结果、处理人、处理时间和审计记录",
            "requires_confirmation": index == 3,
        }
        for index, label in enumerate(operations[:3], start=1)
    ]


def _normalize_llm_result(data: dict[str, Any]) -> dict[str, Any] | None:
    blueprint_modules = _normalize_blueprint_modules(data.get("blueprint_modules"))
    keywords = _clean_list(data.get("keywords"), 16, 18)
    if not keywords and blueprint_modules:
        keywords = _keywords_from_modules(blueprint_modules)
    feature_hint = _clean_hint(str(data.get("feature_hint") or ""))
    if not feature_hint and keywords:
        feature_hint = "、".join(keywords)
    feature_hint = _limit_hint(feature_hint)
    if not feature_hint:
        return None
    return {
        "profile": _safe_id(str(data.get("profile") or "llm")),
        "domain": _clean_hint(str(data.get("domain") or ""))[:40],
        "target_users": _clean_list(data.get("target_users"), 8, 20),
        "keywords": keywords or [part for part in re.split(r"[，,、\s]+", feature_hint) if part],
        "feature_hint": feature_hint,
        "avoid_terms": _clean_list(data.get("avoid_terms"), 12, 24),
        "blueprint_modules": blueprint_modules,
        "should_replace": bool(data.get("should_replace")),
        "reason": _clean_hint(str(data.get("reason") or "")),
    }


def _normalize_domain_profile(data: dict[str, Any]) -> dict[str, Any]:
    blueprint_free = dict(data)
    blueprint_free.pop("blueprint_modules", None)
    keywords = _clean_list(blueprint_free.get("keywords"), 16, 18)
    feature_hint = _clean_hint(str(blueprint_free.get("feature_hint") or ""))
    if not feature_hint and keywords:
        feature_hint = "、".join(keywords)
    return {
        "profile": _safe_id(str(blueprint_free.get("profile") or "llm")),
        "domain": _clean_hint(str(blueprint_free.get("domain") or ""))[:40],
        "target_users": _clean_list(blueprint_free.get("target_users"), 8, 20),
        "keywords": keywords or [part for part in re.split(r"[，,、\s]+", feature_hint) if part],
        "feature_hint": _limit_hint(feature_hint),
        "avoid_terms": _clean_list(blueprint_free.get("avoid_terms"), 12, 24),
        "blueprint_modules": [],
        "should_replace": bool(blueprint_free.get("should_replace", True)),
        "reason": _clean_hint(str(blueprint_free.get("reason") or "")),
    }


def _normalize_blueprint_modules(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    modules: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    seen_descriptions: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        title = _clean_hint(str(item.get("title") or item.get("name") or ""))[:32]
        description = _clean_hint(str(item.get("description") or item.get("focus") or ""))[:180]
        if len(title) < 2 or len(description) < 24:
            continue
        normalized_description = re.sub(r"\W+", "", description)
        if title in seen_titles or normalized_description in seen_descriptions:
            continue
        category = _clean_hint(str(item.get("category") or item.get("group") or ""))[:24]
        if category in {"核心模块", "功能模块", "业务处理", "数据管理"}:
            category = ""
        modules.append(
            {
                "key": _safe_id(str(item.get("key") or item.get("id") or title)),
                "category": category or "业务模块",
                "title": title,
                "description": description,
                "entities": _clean_entities(item.get("entities"), 4),
                "operations": _clean_list(item.get("operations") or item.get("actions"), 7, 28),
                "operation_specs": _normalize_operation_specs(
                    item.get("operation_specs") or item.get("operationSpecs")
                ),
                "data_fields": _clean_list(
                    item.get("data_fields") or item.get("dataFields") or item.get("fields"),
                    10,
                    24,
                ),
                "data_objects": _clean_list(
                    item.get("data_objects") or item.get("dataObjects") or item.get("objects"),
                    6,
                    26,
                ),
                "user_flow": _clean_list(
                    item.get("user_flow") or item.get("userFlow") or item.get("flow") or item.get("steps"),
                    6,
                    42,
                ),
                "screens": _clean_list(item.get("screens") or item.get("pages"), 5, 28),
                "pages": _clean_list(item.get("pages") or item.get("screens"), 4, 28),
                "rules": _clean_list(item.get("rules") or item.get("quality_rules") or item.get("qualityRules"), 5, 80),
            }
        )
        seen_titles.add(title)
        seen_descriptions.add(normalized_description)
        if len(modules) >= 12:
            break
    return modules


def _normalize_operation_specs(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        label = _clean_hint(str(item.get("label") or item.get("action") or item.get("name") or ""))[:28]
        if not label or label in seen:
            continue
        seen.add(label)
        result.append(
            {
                "action_key": _safe_id(str(item.get("action_key") or item.get("actionKey") or label)),
                "label": label,
                "category": _clean_hint(str(item.get("category") or ""))[:20],
                "role": _clean_hint(str(item.get("role") or ""))[:24],
                "trigger": _clean_hint(str(item.get("trigger") or ""))[:80],
                "input_fields": _clean_list(item.get("input_fields") or item.get("inputFields"), 8, 24),
                "pre_state": _clean_hint(str(item.get("pre_state") or item.get("preState") or ""))[:32],
                "post_state": _clean_hint(str(item.get("post_state") or item.get("postState") or ""))[:32],
                "result_evidence": _clean_hint(
                    str(item.get("result_evidence") or item.get("resultEvidence") or "")
                )[:90],
                "requires_confirmation": bool(
                    item.get("requires_confirmation")
                    if item.get("requires_confirmation") is not None
                    else item.get("requiresConfirmation", False)
                ),
            }
        )
        if len(result) >= 7:
            break
    return result


def _llm_result_meets_blueprint_floor(result: dict[str, Any], software_name: str, min_count: int) -> bool:
    modules = result.get("blueprint_modules") or []
    if min_count and len(modules) < min_count:
        trace_event(
            "feature_hint_inference_rejected",
            reason="blueprint_module_count_low",
            expected=min_count,
            actual=len(modules),
        )
        return False
    if not modules:
        return True

    titles = [str(module.get("title") or "").strip() for module in modules]
    generic_titles = sum(1 for title in titles if _is_generic_module_title(title, software_name))
    if generic_titles > max(1, len(titles) // 4):
        trace_event(
            "feature_hint_inference_rejected",
            reason="generic_module_titles",
            generic_titles=generic_titles,
            total=len(titles),
        )
        return False

    categories = {str(module.get("category") or "").strip() for module in modules if str(module.get("category") or "").strip()}
    if min_count >= 8 and len(categories) < 4:
        trace_event(
            "feature_hint_inference_rejected",
            reason="category_diversity_low",
            category_count=len(categories),
        )
        return False
    if min_count >= 8:
        weak_detail_count = 0
        for module in modules:
            operations = module.get("operations") if isinstance(module, dict) else []
            operation_specs = module.get("operation_specs") if isinstance(module, dict) else []
            data_fields = module.get("data_fields") if isinstance(module, dict) else []
            pages = module.get("pages") if isinstance(module, dict) else []
            rules = module.get("rules") if isinstance(module, dict) else []
            if (
                not isinstance(operations, list)
                or len(operations) < 4
                or not isinstance(operation_specs, list)
                or len(operation_specs) < 3
                or any(
                    not isinstance(spec, dict)
                    or not str(spec.get("label") or "").strip()
                    or not str(spec.get("role") or "").strip()
                    or not str(spec.get("trigger") or "").strip()
                    or not isinstance(spec.get("input_fields"), list)
                    or not spec.get("input_fields")
                    or not str(spec.get("post_state") or "").strip()
                    or not str(spec.get("result_evidence") or "").strip()
                    for spec in operation_specs
                )
                or not isinstance(data_fields, list)
                or len(data_fields) < 5
                or not isinstance(pages, list)
                or len(pages) < 2
                or not isinstance(rules, list)
                or len(rules) < 2
            ):
                weak_detail_count += 1
        if weak_detail_count:
            trace_event(
                "feature_hint_inference_rejected",
                reason="blueprint_module_detail_incomplete",
                weak_detail_count=weak_detail_count,
                total=len(modules),
            )
            return False
    return True


def _is_generic_module_title(title: str, software_name: str) -> bool:
    title = _clean_hint(title)
    if not title:
        return True
    normalized_title = re.sub(r"\W+", "", title)
    normalized_name = re.sub(r"\W+", "", _clean_hint(software_name))
    if normalized_name and (normalized_name in normalized_title or normalized_title in normalized_name):
        return True
    generic_terms = {
        "核心模块",
        "业务处理",
        "数据管理",
        "统计分析",
        "系统设置",
        "权限管理",
        "记录统计",
    }
    if title in generic_terms:
        return True
    return False


def _keywords_from_modules(modules: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    for module in modules:
        values.append(str(module.get("title") or ""))
        values.extend(str(item) for item in module.get("data_objects") or [])
        values.extend(str(item) for item in module.get("screens") or [])
    return _clean_list(values, 16, 18)


def _parse_json(content: str) -> dict[str, Any]:
    return parse_json_object(content, label="feature_inference")


def infer_feature_hint(software_name: str, product_type: str = "") -> tuple[str, str]:
    text = f"{software_name} {product_type}"
    profile = _profile(text)
    if profile:
        return _limit_hint("、".join(profile["keywords"])), str(profile["id"])

    terms = _name_terms(software_name)
    if not terms:
        return "", ""
    generic = []
    for term in terms[:4]:
        generic.extend([f"{term}台账", f"{term}处理", f"{term}查询", f"{term}统计"])
    return _limit_hint("、".join(dict.fromkeys(generic))), "name-derived"


def _profile(text: str) -> dict | None:
    best = None
    best_hits = 0
    for item in DOMAIN_PROFILES:
        hits = sum(1 for trigger in item["triggers"] if trigger in text)
        if hits > best_hits:
            best = item
            best_hits = hits
    return best if best_hits else None


def _profile_id(text: str) -> str:
    item = _profile(text)
    return str(item["id"]) if item else ""


def _has_profile_hit(text: str, profile_id: str) -> bool:
    item = next((profile for profile in DOMAIN_PROFILES if profile["id"] == profile_id), None)
    if not item:
        return False
    terms = list(item["triggers"]) + list(item["keywords"])
    return any(term in text for term in terms)


def _name_terms(value: str) -> list[str]:
    cleaned = re.sub(r"(软件|系统|平台|APP|小程序|管理|智能|智慧|V\d+(?:\.\d+)*)", " ", value, flags=re.IGNORECASE)
    chunks = [chunk.strip() for chunk in re.split(r"[，,、\s\-_/]+", cleaned) if chunk.strip()]
    result: list[str] = []
    for chunk in chunks:
        if len(chunk) >= 2 and chunk not in result:
            result.append(chunk)
    return result


def _clean_list(value: Any, max_count: int, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value[:max_count]:
        text = _clean_hint(str(item))[:limit].strip(" 、,，")
        if text and text not in result:
            result.append(text)
    return result


def _clean_entities(value: Any, max_count: int) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value[:max_count]:
        text = re.sub(r"[^a-zA-Z0-9]+", " ", str(item or "")).strip()
        if not text:
            continue
        entity = "".join(part[:1].upper() + part[1:] for part in text.split() if part)
        if entity and entity not in result:
            result.append(entity[:40])
    return result


def _safe_id(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_\\-]+", "_", value).strip("_").lower()
    return value or "llm"


def _merge_hints(provided: str, inferred: str) -> str:
    parts = [part.strip() for part in re.split(r"[，,、\s]+", provided) if part.strip()]
    for part in re.split(r"[，,、\s]+", inferred):
        part = part.strip()
        if part and part not in parts:
            parts.append(part)
    return _limit_hint("、".join(parts))


def _clean_hint(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip(" 、,，")


def _limit_hint(value: str, limit: int = 120) -> str:
    value = _clean_hint(value)
    return value[:limit].rstrip("、,， ")
