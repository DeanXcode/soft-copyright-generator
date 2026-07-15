from __future__ import annotations

from dataclasses import dataclass
import base64
import io
import json
import os
from pathlib import Path
import re
import time
from typing import Any
import urllib.error
import urllib.request

import requests

from ..errors import sanitize_error_message
from .trace import trace_event


class GeneratedImageQualityError(ValueError):
    """Raised when an image API returns a decodable but unusable placeholder."""


@dataclass
class LLMConfig:
    provider: str = "local-template"
    base_url: str = ""
    api_key: str = ""
    model: str = "template-v1"
    image_base_url: str = ""
    image_api_key: str = ""
    image_model: str = ""
    timeout: int = 120
    image_timeout: int = 220
    retry_count: int = 2
    image_retry_count: int = 3
    stream: bool = True
    reasoning_effort: str = "medium"


class LLMProvider:
    def __init__(self, config: LLMConfig):
        self.config = config

    def chat(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: dict[str, Any] | None = None,
        trace_label: str = "",
        timeout: int | None = None,
    ) -> str:
        raise NotImplementedError

    def generate_image(
        self,
        *,
        prompt: str,
        output_path: Path,
        size: str = "1024x1024",
        trace_label: str = "",
    ) -> dict[str, Any]:
        raise NotImplementedError


class LocalTemplateProvider(LLMProvider):
    def chat(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: dict[str, Any] | None = None,
        trace_label: str = "",
        timeout: int | None = None,
    ) -> str:
        return ""


class OpenAICompatibleProvider(LLMProvider):
    def chat(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: dict[str, Any] | None = None,
        trace_label: str = "",
        timeout: int | None = None,
    ) -> str:
        base_url = self.config.base_url.rstrip("/")
        if not base_url:
            raise ValueError("LLM base_url 不能为空")
        if not self.config.api_key:
            raise ValueError("LLM api_key 不能为空")

        url = base_url
        if not url.endswith("/chat/completions"):
            url = f"{url}/chat/completions"
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": bool(self.config.stream) and not _messages_include_image(messages),
        }
        reasoning_effort = _normalize_reasoning_effort(self.config.reasoning_effort)
        if reasoning_effort:
            payload["reasoning_effort"] = reasoning_effort
        if response_format:
            payload["response_format"] = response_format

        headers = _auth_headers(self.config.api_key)
        last_error: Exception | None = None
        total_attempts = max(1, self.config.retry_count + 1)
        effective_timeout = max(10, int(timeout or self.config.timeout or 120))
        stream_hard_timeout = _stream_hard_timeout_seconds(effective_timeout) if payload["stream"] else 0
        for attempt in range(1, total_attempts + 1):
            started_at = time.perf_counter()
            trace_event(
                "provider_request_begin",
                label=trace_label,
                attempt=attempt,
                total_attempts=total_attempts,
                provider=self.config.provider,
                model=self.config.model,
                timeout=effective_timeout,
                max_tokens=max_tokens,
                message_count=len(messages),
                response_format=bool(response_format),
                multimodal=_messages_include_image(messages),
                stream_hard_timeout=stream_hard_timeout,
            )
            try:
                session = _new_requests_session()
                try:
                    response = session.post(url, json=payload, headers=headers, timeout=effective_timeout, stream=True)
                    response.raise_for_status()
                    stream_deadline = time.perf_counter() + stream_hard_timeout if stream_hard_timeout else None
                    content = _extract_chat_content(response, deadline=stream_deadline)
                    if not content:
                        raise ValueError("LLM response content is empty")
                finally:
                    session.close()
                trace_event(
                    "provider_request_success",
                    label=trace_label,
                    attempt=attempt,
                    elapsed_seconds=round(time.perf_counter() - started_at, 3),
                    status_code=response.status_code,
                    content_chars=len(content or ""),
                )
                return content
            except Exception as exc:
                last_error = exc
                status_code = getattr(getattr(exc, "response", None), "status_code", None)
                safe_error = sanitize_error_message(exc, limit=500)
                trace_event(
                    "provider_request_error",
                    label=trace_label,
                    attempt=attempt,
                    elapsed_seconds=round(time.perf_counter() - started_at, 3),
                    status_code=status_code,
                    error_type=type(exc).__name__,
                    error=safe_error,
                )
                if attempt < total_attempts and _should_retry_provider_error(exc):
                    time.sleep(_retry_delay_seconds(attempt))
                    continue
                break
        raise RuntimeError(f"LLM 请求失败：{sanitize_error_message(last_error)}")

    def generate_image(
        self,
        *,
        prompt: str,
        output_path: Path,
        size: str = "1024x1024",
        trace_label: str = "",
    ) -> dict[str, Any]:
        base_url = (self.config.image_base_url or self.config.base_url).rstrip("/")
        if not base_url:
            raise ValueError("LLM base_url 不能为空")
        api_key = self.config.image_api_key or self.config.api_key
        if not api_key:
            raise ValueError("LLM api_key 不能为空")
        model = image_model_name(self.config)
        if not model:
            raise ValueError("图片模型名称不能为空")

        url = base_url
        if not url.endswith("/images/generations"):
            url = f"{url}/images/generations"
        payload_base: dict[str, Any] = {
            "model": model,
            "n": 1,
        }
        headers = _auth_headers(api_key)
        last_error: Exception | None = None
        timeout = int(getattr(self.config, "image_timeout", self.config.timeout) or self.config.timeout)
        total_attempts = max(1, getattr(self.config, "image_retry_count", self.config.retry_count) + 1)
        for attempt in range(1, total_attempts + 1):
            started_at = time.perf_counter()
            prompt_for_attempt = _image_prompt_for_attempt(prompt, attempt)
            size_for_attempt = _image_size_for_attempt(size, attempt)
            payload: dict[str, Any] = {**payload_base, "size": size_for_attempt, "prompt": prompt_for_attempt}
            trace_event(
                "provider_image_request_begin",
                label=trace_label,
                attempt=attempt,
                total_attempts=total_attempts,
                provider=self.config.provider,
                model=model,
                timeout=timeout,
                size=size_for_attempt,
                prompt_chars=len(prompt_for_attempt or ""),
            )
            try:
                session = _new_requests_session()
                try:
                    response = session.post(url, json=payload, headers=headers, timeout=timeout)
                    response.raise_for_status()
                    data = response.json()
                finally:
                    session.close()
                saved = _save_image_response(data, output_path, timeout=timeout)
                trace_event(
                    "provider_image_request_success",
                    label=trace_label,
                    attempt=attempt,
                    elapsed_seconds=round(time.perf_counter() - started_at, 3),
                    status_code=response.status_code,
                    model=model,
                    source=saved.get("source", ""),
                    bytes=saved.get("bytes", 0),
                )
                return {
                    "model": model,
                    "path": str(output_path),
                    "size": size_for_attempt,
                    **saved,
                }
            except Exception as exc:
                last_error = exc
                status_code = getattr(getattr(exc, "response", None), "status_code", None)
                safe_error = sanitize_error_message(exc, limit=500)
                trace_event(
                    "provider_image_request_error",
                    label=trace_label,
                    attempt=attempt,
                    elapsed_seconds=round(time.perf_counter() - started_at, 3),
                    status_code=status_code,
                    error_type=type(exc).__name__,
                    error=safe_error,
                )
                if attempt < total_attempts and _should_retry_provider_error(exc):
                    time.sleep(_retry_delay_seconds(attempt))
                    continue
                break
        raise RuntimeError(_image_failure_message(last_error, model=model, attempts=attempt))


def build_provider(config: LLMConfig) -> LLMProvider:
    provider = config.provider.lower()
    if provider in {"local", "local-template", "template", ""}:
        return LocalTemplateProvider(config)
    if provider == "openai":
        normalized = _with_default(config, base_url="https://api.openai.com/v1")
        return OpenAICompatibleProvider(normalized)
    if provider == "deepseek":
        normalized = _with_default(config, base_url="https://api.deepseek.com")
        return OpenAICompatibleProvider(normalized)
    if provider in {"custom", "openai-compatible"}:
        return OpenAICompatibleProvider(config)
    raise ValueError(f"不支持的模型供应商：{config.provider}")


def config_from_env(provider: str, model: str, base_url: str = "", api_key: str = "") -> LLMConfig:
    provider_key = provider.upper().replace("-", "_")
    env_api_key = (
        api_key
        or os.getenv(f"{provider_key}_API_KEY")
        or os.getenv("SOFT_MODEL_GPT_API_KEY")
        or os.getenv("SOFT_MODEL_GATEWAY_API_KEY")
        or os.getenv("OPENAI_API_KEY", "")
    )
    env_base_url = (
        base_url
        or os.getenv(f"{provider_key}_BASE_URL")
        or os.getenv("SOFT_MODEL_GPT_BASE_URL")
        or os.getenv("SOFT_MODEL_GATEWAY_BASE_URL")
        or ""
    )
    env_model = model or os.getenv(f"{provider_key}_MODEL") or os.getenv("SOFT_MODEL_GPT_NAME") or os.getenv("SOFT_MODEL_GATEWAY_MODEL") or "gpt-5.5"
    retry_count = _env_int("SOFT_LLM_RETRY_COUNT", 3, minimum=0, maximum=5)
    image_retry_count = _env_int("SOFT_LLM_IMAGE_RETRY_COUNT", _env_int("SOFT_IMAGE_RETRY_COUNT", 3, minimum=0, maximum=5), minimum=0, maximum=5)
    return LLMConfig(
        provider=provider,
        base_url=env_base_url,
        api_key=env_api_key,
        model=env_model,
        image_base_url=image_base_url_from_env(provider, env_base_url),
        image_api_key=image_api_key_from_env(provider, env_api_key),
        image_model=image_model_from_env(provider, env_model),
        timeout=_env_int("SOFT_LLM_TIMEOUT_SECONDS", 120, minimum=30, maximum=240),
        image_timeout=_env_int("SOFT_LLM_IMAGE_TIMEOUT_SECONDS", _env_int("SOFT_IMAGE_TIMEOUT_SECONDS", 220, minimum=30, maximum=360), minimum=30, maximum=360),
        retry_count=retry_count,
        image_retry_count=image_retry_count,
        stream=_env_bool("SOFT_LLM_STREAM", True),
        reasoning_effort=_normalize_reasoning_effort(
            os.getenv("SOFT_MODEL_GPT_REASONING_EFFORT")
            or os.getenv("SOFT_LLM_REASONING_EFFORT")
            or "medium"
        ),
    )


def image_base_url_from_env(provider: str, fallback_base_url: str = "") -> str:
    provider_key = provider.upper().replace("-", "_")
    return (
        os.getenv(f"{provider_key}_IMAGE_BASE_URL")
        or os.getenv("SOFT_MODEL_GPT_IMAGE_BASE_URL")
        or os.getenv("SOFT_MODEL_GATEWAY_IMAGE_BASE_URL")
        or os.getenv("SOFT_MODEL_IMAGE_BASE_URL")
        or fallback_base_url
    )


def image_api_key_from_env(provider: str, fallback_api_key: str = "") -> str:
    provider_key = provider.upper().replace("-", "_")
    return (
        os.getenv(f"{provider_key}_IMAGE_API_KEY")
        or os.getenv("SOFT_MODEL_GPT_IMAGE_API_KEY")
        or os.getenv("SOFT_MODEL_GATEWAY_IMAGE_API_KEY")
        or os.getenv("SOFT_MODEL_IMAGE_API_KEY")
        or fallback_api_key
    )


def image_model_from_env(provider: str, fallback_model: str = "") -> str:
    provider_key = provider.upper().replace("-", "_")
    return (
        os.getenv(f"{provider_key}_IMAGE_MODEL")
        or os.getenv(f"{provider_key}_IMAGE_NAME")
        or os.getenv("SOFT_MODEL_GPT_IMAGE_NAME")
        or os.getenv("SOFT_MODEL_GPT_IMAGE_MODEL")
        or os.getenv("SOFT_MODEL_GATEWAY_IMAGE_MODEL")
        or os.getenv("SOFT_MODEL_IMAGE_NAME")
        or os.getenv("SOFT_MODEL_IMAGE_MODEL")
        or "gpt-image-2"
        or fallback_model
    )


def image_model_name(config: LLMConfig) -> str:
    return str(config.image_model or image_model_from_env(config.provider, config.model) or config.model).strip()


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def _with_default(config: LLMConfig, base_url: str) -> LLMConfig:
    if config.base_url:
        return config
    return LLMConfig(
        provider=config.provider,
        base_url=base_url,
        api_key=config.api_key,
        model=config.model,
        image_base_url=config.image_base_url,
        image_api_key=config.image_api_key,
        image_model=config.image_model,
        timeout=config.timeout,
        image_timeout=getattr(config, "image_timeout", config.timeout),
        retry_count=config.retry_count,
        image_retry_count=getattr(config, "image_retry_count", 3),
        stream=config.stream,
        reasoning_effort=config.reasoning_effort,
    )


def _normalize_reasoning_effort(value: str) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in {"minimal", "low", "medium", "high", "xhigh"} else "medium"


def _auth_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _new_requests_session() -> requests.Session:
    session = requests.Session()
    session.trust_env = _env_bool("SOFT_LLM_USE_SYSTEM_PROXY", False)
    return session


def _messages_include_image(messages: list[dict[str, Any]]) -> bool:
    for message in messages:
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and (
                    item.get("type") == "image_url" or "image_url" in item
                ):
                    return True
    return False


def _should_retry_provider_error(exc: Exception) -> bool:
    status_code = getattr(getattr(exc, "response", None), "status_code", None)
    if status_code is not None:
        return int(status_code) in {408, 409, 425, 429, 500, 502, 503, 504, 520, 522, 523, 524}
    return isinstance(
        exc,
        (
            GeneratedImageQualityError,
            requests.Timeout,
            requests.ConnectionError,
            TimeoutError,
            urllib.error.URLError,
        ),
    )


def _retry_delay_seconds(attempt: int) -> float:
    return min(12.0, 1.5 * (2 ** max(0, attempt - 1)))


def _stream_hard_timeout_seconds(effective_timeout: int) -> int:
    raw = os.getenv("SOFT_LLM_STREAM_HARD_TIMEOUT_SECONDS", "").strip()
    default = max(600, int(effective_timeout or 120) * 3)
    if raw:
        try:
            default = int(raw)
        except ValueError:
            pass
    return max(120, min(1800, default))


def _image_prompt_for_attempt(prompt: str, attempt: int) -> str:
    text = " ".join(str(prompt or "").split())
    if attempt <= 1:
        return text
    retry_limits = {2: 620, 3: 520, 4: 460}
    limit = retry_limits.get(attempt, 480)
    if "竖屏" in text or "手机" in text or "小程序" in text:
        required_tail = (
            "单张真实手机软件运行界面截图，顶部导航、业务卡片、列表、按钮、状态标签清晰可见，"
            "只呈现该软件正在使用的移动端业务页面。"
        )
    elif "游戏" in text:
        required_tail = (
            "单张真实游戏运行界面截图，主界面、菜单按钮、关卡信息、状态数值和操作控件清晰可见，"
            "只呈现该游戏正在运行的画面。"
        )
    else:
        required_tail = (
            "单张真实桌面业务软件运行界面截图，软件 UI 控件占画面主体：顶部栏、左侧导航、筛选工具栏、表格、卡片、图表、按钮、状态标签和分页器清晰可见，"
            "地图或三维视图只能放在带边框标题栏的业务面板内且不超过画面三分之一，必须有大量矩形控件边界。"
        )
    head_limit = max(180, limit - len(required_tail) - 1)
    return f"{text[:head_limit].rstrip()} {required_tail}"


def _image_size_for_attempt(size: str, attempt: int) -> str:
    text = str(size or "").strip().lower()
    if attempt <= 1:
        return text or "1280x720"
    if not re.fullmatch(r"\d+x\d+", text):
        return "1024x576"
    width_text, height_text = text.split("x", 1)
    try:
        width = int(width_text)
        height = int(height_text)
    except ValueError:
        return "1024x576"
    if width >= height:
        retry_sizes = ["1024x576", "768x432", "640x360"]
    else:
        retry_sizes = ["576x1024", "432x768", "360x640"]
    index = min(max(attempt - 2, 0), len(retry_sizes) - 1)
    candidate = retry_sizes[index]
    cand_width, cand_height = (int(part) for part in candidate.split("x", 1))
    if max(width, height) <= max(cand_width, cand_height):
        return text
    return candidate


def _image_failure_message(exc: Exception | None, *, model: str, attempts: int) -> str:
    status_code = getattr(getattr(exc, "response", None), "status_code", None)
    detail = sanitize_error_message(exc)
    retry_text = f"，已请求 {attempts} 次" if attempts > 1 else ""
    if status_code in {429, 500, 502, 503, 504, 520, 522, 523, 524}:
        return (
            f"图片生成请求失败：图片模型 {model} 当前返回 {status_code} 临时不可用{retry_text}。"
            "正式流程不会使用模板或中间图兜底；请稍后保留蓝图重试，或检查图片模型配置 "
            "SOFT_MODEL_GPT_IMAGE_NAME / SOFT_MODEL_GPT_IMAGE_BASE_URL 是否指向可用的 gpt-image-2 图片服务；"
            "如果连续返回 502/524，通常需要更换、充值或修复 NewAPI 图片上游渠道。"
            f" 原始摘要：{detail}"
        )
    if status_code in {400, 401, 403, 404}:
        return (
            f"图片生成请求失败：图片模型 {model} 的接口或权限配置不可用，状态码 {status_code}。"
            "请检查图片模型名称、图片网关权限和 API Key；正式流程不能跳过 image2 视觉参考稿。"
            f" 原始摘要：{detail}"
        )
    return f"图片生成请求失败：图片模型 {model} 未返回可用图片{retry_text}。原始摘要：{detail}"


def _save_image_response(data: Any, output_path: Path, *, timeout: int) -> dict[str, Any]:
    image_item = _first_image_item(data)
    if not image_item:
        raise ValueError("图片生成响应缺少 data[0]")
    if isinstance(image_item.get("b64_json"), str) and image_item.get("b64_json"):
        raw = base64.b64decode(str(image_item["b64_json"]))
        source = "b64_json"
    elif isinstance(image_item.get("url"), str) and image_item.get("url"):
        raw, source = _read_image_url(str(image_item["url"]), timeout=timeout)
    else:
        raise ValueError("图片生成响应缺少 b64_json 或 url")
    if len(raw) < 1024:
        raise GeneratedImageQualityError("图片生成响应内容过小，疑似无效占位图")
    try:
        quality = _inspect_generated_image(raw)
    except GeneratedImageQualityError:
        _write_rejected_image(output_path, raw)
        raise
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(raw)
    return {"source": source, "bytes": len(raw), **quality}


def _inspect_generated_image(raw: bytes) -> dict[str, Any]:
    try:
        from PIL import Image, ImageStat
    except ImportError as exc:
        raise GeneratedImageQualityError("图片质量检查依赖 Pillow 缺失，无法确认 image2 返回图是否可用") from exc
    try:
        with Image.open(io.BytesIO(raw)) as image:
            rgb = image.convert("RGB")
            width, height = rgb.size
            sample = rgb.copy()
            sample.thumbnail((96, 96))
            pixels = list(sample.getdata())
            if not pixels:
                raise GeneratedImageQualityError("图片生成响应为空白图像")
            total = len(pixels)
            buckets: dict[tuple[int, int, int], int] = {}
            for red, green, blue in pixels:
                key = (red // 24, green // 24, blue // 24)
                buckets[key] = buckets.get(key, 0) + 1
            dominant_bucket, dominant_count = max(buckets.items(), key=lambda item: item[1])
            dominant_center = tuple(min(255, channel * 24 + 12) for channel in dominant_bucket)
            off_background: list[tuple[int, int]] = []
            sample_width, sample_height = sample.size
            for index, (red, green, blue) in enumerate(pixels):
                distance = (
                    abs(red - dominant_center[0])
                    + abs(green - dominant_center[1])
                    + abs(blue - dominant_center[2])
                )
                if distance > 54:
                    off_background.append((index % sample_width, index // sample_width))
            if off_background:
                left = min(point[0] for point in off_background)
                right = max(point[0] for point in off_background) + 1
                top = min(point[1] for point in off_background)
                bottom = max(point[1] for point in off_background) + 1
                content_width_ratio = (right - left) / max(sample_width, 1)
                content_height_ratio = (bottom - top) / max(sample_height, 1)
            else:
                content_width_ratio = 0.0
                content_height_ratio = 0.0
            dominant_ratio = dominant_count / max(total, 1)
            content_area_ratio = content_width_ratio * content_height_ratio
            ink_ratio = len(off_background) / max(total, 1)
            luminance_stddev = float(ImageStat.Stat(sample.convert("L")).stddev[0])
            active_bucket_count = sum(1 for count in buckets.values() if count / max(total, 1) >= 0.002)
            ui_edge_metrics = _ui_axis_edge_metrics(sample)
    except GeneratedImageQualityError:
        raise
    except Exception as exc:
        raise GeneratedImageQualityError(f"图片生成响应无法解码为有效图像：{exc}") from exc

    if min(width, height) < 320 or max(width, height) < 512:
        raise GeneratedImageQualityError(f"图片尺寸过小，无法作为界面参考稿：{width}x{height}")
    if active_bucket_count <= 3 and luminance_stddev < 8:
        raise GeneratedImageQualityError("图片几乎为空白，疑似 image2 占位图")
    if dominant_ratio >= 0.975 and ink_ratio < 0.04:
        raise GeneratedImageQualityError("图片主体内容过少，疑似空白或问号占位图")
    if dominant_ratio >= 0.92 and active_bucket_count <= 6 and content_area_ratio < 0.2:
        raise GeneratedImageQualityError("图片颜色和结构过于单一，疑似 image2 问号占位图")
    complex_ui_soft_pass = (
        content_area_ratio >= 0.68
        and ink_ratio >= 0.12
        and active_bucket_count >= 12
        and luminance_stddev >= 24
        and int(ui_edge_metrics["axis_edge_total"]) >= 80
    )
    dense_dark_ui_soft_pass = (
        content_area_ratio >= 0.78
        and 0.14 <= ink_ratio <= 0.82
        and active_bucket_count >= 16
        and luminance_stddev >= 12
        and dominant_ratio <= 0.78
    )
    if (
        not (complex_ui_soft_pass or dense_dark_ui_soft_pass)
        and int(ui_edge_metrics["axis_edge_score"]) < 8
        and int(ui_edge_metrics["axis_edge_total"]) < 260
    ):
        raise GeneratedImageQualityError("图片缺少软件界面控件边界，疑似问号占位图或非软件界面图片")

    return {
        "image_width": width,
        "image_height": height,
        "image_quality": {
            "dominant_ratio": round(dominant_ratio, 4),
            "content_area_ratio": round(content_area_ratio, 4),
            "ink_ratio": round(ink_ratio, 4),
            "active_bucket_count": int(active_bucket_count),
            "luminance_stddev": round(luminance_stddev, 3),
            "complex_ui_soft_pass": bool(complex_ui_soft_pass),
            "dense_dark_ui_soft_pass": bool(dense_dark_ui_soft_pass),
            **ui_edge_metrics,
        },
    }


def _ui_axis_edge_metrics(image: Any) -> dict[str, int]:
    gray = image.convert("L")
    pixels = gray.load()
    width, height = gray.size
    horizontal_min = max(18, int(width * 0.12))
    vertical_min = max(18, int(height * 0.08))
    horizontal_runs = 0
    vertical_runs = 0
    horizontal_total = 0
    vertical_total = 0
    for y in range(max(0, height - 1)):
        current = 0
        for x in range(width):
            if abs(int(pixels[x, y]) - int(pixels[x, y + 1])) > 28:
                current += 1
            else:
                if current >= horizontal_min:
                    horizontal_runs += 1
                    horizontal_total += current
                current = 0
        if current >= horizontal_min:
            horizontal_runs += 1
            horizontal_total += current
    for x in range(max(0, width - 1)):
        current = 0
        for y in range(height):
            if abs(int(pixels[x, y]) - int(pixels[x + 1, y])) > 28:
                current += 1
            else:
                if current >= vertical_min:
                    vertical_runs += 1
                    vertical_total += current
                current = 0
        if current >= vertical_min:
            vertical_runs += 1
            vertical_total += current
    return {
        "axis_edge_score": int(horizontal_runs + vertical_runs),
        "axis_edge_total": int(horizontal_total + vertical_total),
        "horizontal_edge_runs": int(horizontal_runs),
        "vertical_edge_runs": int(vertical_runs),
    }


def _first_image_item(data: Any) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None
    items = data.get("data")
    if not isinstance(items, list) or not items:
        return None
    item = items[0]
    return item if isinstance(item, dict) else None


def _read_image_url(value: str, *, timeout: int) -> tuple[bytes, str]:
    if value.startswith("data:image/") and ";base64," in value:
        raw = value.split(";base64,", 1)[1]
        return base64.b64decode(raw), "data_url"
    with urllib.request.urlopen(value, timeout=timeout) as response:
        return response.read(), "url"


def _write_rejected_image(output_path: Path, raw: bytes) -> None:
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        rejected_path = output_path.with_name(f"{output_path.stem}.rejected{output_path.suffix or '.png'}")
        rejected_path.write_bytes(raw)
        trace_event(
            "provider_image_rejected_saved",
            output_path=str(rejected_path),
            bytes=len(raw),
        )
    except Exception:
        return


def _extract_chat_content(response: requests.Response, deadline: float | None = None) -> str:
    content_type = str(response.headers.get("content-type", "")).lower()
    if "text/event-stream" in content_type:
        return _extract_sse_content(response, deadline=deadline)
    data = response.json()
    return _extract_message_content(data)


def _extract_sse_content(response: requests.Response, deadline: float | None = None) -> str:
    pieces: list[str] = []
    for raw_line in response.iter_lines(decode_unicode=False):
        if deadline is not None and time.perf_counter() > deadline:
            raise TimeoutError("LLM streaming response exceeded configured timeout")
        if isinstance(raw_line, bytes):
            line = raw_line.decode("utf-8", errors="replace").strip()
        else:
            line = str(raw_line or "").strip()
        if not line:
            continue
        if line.startswith("data:"):
            data_text = line[5:].strip()
            if not data_text or data_text == "[DONE]":
                if data_text == "[DONE]":
                    break
                continue
            try:
                chunk = json.loads(data_text)
            except json.JSONDecodeError:
                continue
            piece = _extract_message_content(chunk, allow_delta=True)
            if piece:
                pieces.append(piece)
    return "".join(pieces)


def _extract_message_content(data: Any, allow_delta: bool = False) -> str:
    if not isinstance(data, dict):
        return ""
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    choice = choices[0]
    if not isinstance(choice, dict):
        return ""
    message = choice.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content
    if allow_delta:
        delta = choice.get("delta")
        if isinstance(delta, dict):
            content = delta.get("content")
            if isinstance(content, str):
                return content
    content = choice.get("content")
    if isinstance(content, str):
        return content
    return ""

