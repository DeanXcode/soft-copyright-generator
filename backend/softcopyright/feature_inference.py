from __future__ import annotations

import json
import re
import time
from typing import Any

from .llm.provider import LLMProvider, LocalTemplateProvider
from .llm.trace import trace_event


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
        "triggers": ["游戏", "消除", "关卡", "棋盘", "玩家", "道具", "得分", "星级"],
        "keywords": ["玩家账号", "关卡地图", "对局棋盘", "目标得分", "剩余步数", "道具背包", "结算统计", "星级评价"],
    },
    {
        "id": "education",
        "triggers": ["教育", "学习", "课程", "作业", "考试", "题库", "学情", "课堂"],
        "keywords": ["课程资源", "学习任务", "作业收交", "批改进度", "学情分析", "错题记录", "班级管理", "学习报告"],
    },
    {
        "id": "finance",
        "triggers": ["金融", "贷款", "信贷", "支付", "清算", "账单", "授信", "风控"],
        "keywords": ["客户授信", "贷款申请", "额度测算", "还款计划", "交易流水", "清算批次", "风险评级", "账单统计"],
    },
    {
        "id": "medical",
        "triggers": ["医疗", "医院", "诊疗", "处方", "病历", "药品", "随访", "护理"],
        "keywords": ["患者档案", "诊疗记录", "处方管理", "药品库存", "随访计划", "护理任务", "检查报告", "医嘱执行"],
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
) -> tuple[str, dict]:
    llm_result = infer_feature_hint_with_llm(software_name, product_type, provided, provider)
    if llm_result:
        return _harmonize_llm_result(provided, llm_result)

    inferred, profile_id = infer_feature_hint(software_name, product_type)
    provided = _clean_hint(provided)
    if not inferred:
        return provided, {"auto_feature_hint": False, "feature_hint_profile": "", "feature_hint_source": "provided"}

    provided_profile = _profile_id(f"{provided} {product_type}") if provided else ""
    source = "provided"
    if not provided:
        result = inferred
        source = "auto-name"
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
) -> dict[str, Any] | None:
    if provider is None or isinstance(provider, LocalTemplateProvider):
        return None
    started_at = time.perf_counter()
    trace_event(
        "feature_hint_inference_begin",
        software_name=software_name,
        product_type=product_type,
        provided=bool(_clean_hint(provided)),
    )
    try:
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
                    "content": _build_llm_prompt(software_name, product_type, provided),
                },
            ],
            temperature=0.25,
            max_tokens=3600,
            response_format={"type": "json_object"},
            trace_label="feature_hint:infer",
        )
        data = _parse_json(content)
        result = _normalize_llm_result(data)
        if result:
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
            return result
    except Exception as exc:
        trace_event(
            "feature_hint_inference_error",
            elapsed_seconds=round(time.perf_counter() - started_at, 3),
            error_type=type(exc).__name__,
            error=str(exc)[:500],
        )
    return None


def _build_llm_prompt(software_name: str, product_type: str, provided: str) -> str:
    return f"""
请根据软件名称生成“名称理解契约”和“详细业务蓝图”，用于后续生成产品蓝图、源码工程、说明书和界面截图。

软件全称：{software_name}
产品类型：{product_type or "未提供"}
用户已填业务补充：{_clean_hint(provided) or "未填写"}

任务：
1. 识别该软件最可能的真实业务领域和目标用户。
2. 输出 10-16 个适合软著材料的业务关键词/功能关键词。
3. 如果用户已填业务补充与软件名称领域明显不一致，should_replace 返回 true。
4. 输出 6-12 个应避免的偏离方向，防止后续模块跑到错误行业。
5. 输出 8-12 个 blueprint_modules，作为用户可编辑的详细蓝图和后续正式材料的语义约束。

质量要求：
- feature_hint 必须是中文短语，用顿号分隔，长度不超过 120 字。
- 关键词必须像真实软件功能，例如阅读听书类应围绕书城、书架、章节、播放、阅读进度、收藏订阅、会员权益等。
- 不要输出泛型词：数据管理、业务处理、统计分析、系统设置、权限管理。
- 不要把其他行业的审核、风控、工单、复核、批量发布等模块套进不相关软件。
- 如果软件名称很短，也要根据名称含义推断一个具体产品方向。
- blueprint_modules 必须像完整项目计划：覆盖入口/浏览或创建、核心操作、详情/播放/编辑/下单/对局等主流程、记录或进度、个人/配置等真实必要模块。
- 每个模块 description 写 80-140 个中文字符，说明服务对象、关键数据对象、用户动作、状态结果，禁止空泛重复。
- category 要体现真实分类，例如“内容发现、核心交互、订单履约、对局规则、学习过程、账户权益”等；不要全部写“核心模块”。
- data_objects、user_flow、screens 必须与模块标题一致，不能复制同一套通用词。

返回 JSON：
{{
  "profile": "简短英文领域标识，如 reading_audio / office_oa / inventory / name_understood",
  "domain": "中文领域短语",
  "target_users": ["目标用户1", "目标用户2"],
  "keywords": ["关键词1", "关键词2"],
  "feature_hint": "关键词1、关键词2、关键词3",
  "avoid_terms": ["应避免方向1", "应避免方向2"],
  "blueprint_modules": [
    {{
      "category": "模块分类",
      "title": "模块名称",
      "description": "80-140字真实业务说明，说明该模块服务谁、处理什么对象、如何流转、输出什么状态或结果。",
      "data_objects": ["关键数据对象1", "关键数据对象2"],
      "user_flow": ["用户步骤1", "用户步骤2", "用户步骤3"],
      "screens": ["页面/界面1", "页面/界面2"]
    }}
  ],
  "should_replace": true,
  "reason": "为什么这样补充"
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
                "category": category or "业务模块",
                "title": title,
                "description": description,
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
            }
        )
        seen_titles.add(title)
        seen_descriptions.add(normalized_description)
        if len(modules) >= 12:
            break
    return modules


def _keywords_from_modules(modules: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    for module in modules:
        values.append(str(module.get("title") or ""))
        values.extend(str(item) for item in module.get("data_objects") or [])
        values.extend(str(item) for item in module.get("screens") or [])
    return _clean_list(values, 16, 18)


def _parse_json(content: str) -> dict[str, Any]:
    cleaned = str(content or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        cleaned = cleaned[start : end + 1]
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError("feature hint result is not a JSON object")
    return data


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
