from __future__ import annotations

from dataclasses import dataclass
import json
import os
import time
from typing import Any

import requests

from .trace import trace_event


@dataclass
class LLMConfig:
    provider: str = "local-template"
    base_url: str = ""
    api_key: str = ""
    model: str = "template-v1"
    timeout: int = 120
    retry_count: int = 2


class LLMProvider:
    def __init__(self, config: LLMConfig):
        self.config = config

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: dict[str, Any] | None = None,
        trace_label: str = "",
    ) -> str:
        raise NotImplementedError


class LocalTemplateProvider(LLMProvider):
    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: dict[str, Any] | None = None,
        trace_label: str = "",
    ) -> str:
        return ""


class OpenAICompatibleProvider(LLMProvider):
    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: dict[str, Any] | None = None,
        trace_label: str = "",
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
            "stream": True,
        }
        if response_format:
            payload["response_format"] = response_format

        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        last_error: Exception | None = None
        total_attempts = max(1, self.config.retry_count + 1)
        for attempt in range(1, total_attempts + 1):
            started_at = time.perf_counter()
            trace_event(
                "provider_request_begin",
                label=trace_label,
                attempt=attempt,
                total_attempts=total_attempts,
                provider=self.config.provider,
                model=self.config.model,
                timeout=self.config.timeout,
                max_tokens=max_tokens,
                message_count=len(messages),
                response_format=bool(response_format),
            )
            try:
                response = requests.post(url, json=payload, headers=headers, timeout=self.config.timeout, stream=True)
                response.raise_for_status()
                content = _extract_chat_content(response)
                if not content:
                    raise ValueError("LLM response content is empty")
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
                trace_event(
                    "provider_request_error",
                    label=trace_label,
                    attempt=attempt,
                    elapsed_seconds=round(time.perf_counter() - started_at, 3),
                    status_code=status_code,
                    error_type=type(exc).__name__,
                    error=str(exc)[:500],
                )
        raise RuntimeError(f"LLM 请求失败：{last_error}")


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
    env_api_key = api_key or os.getenv(f"{provider_key}_API_KEY") or os.getenv("OPENAI_API_KEY", "")
    env_base_url = base_url or os.getenv(f"{provider_key}_BASE_URL", "")
    return LLMConfig(provider=provider, base_url=env_base_url, api_key=env_api_key, model=model)


def _with_default(config: LLMConfig, base_url: str) -> LLMConfig:
    if config.base_url:
        return config
    return LLMConfig(
        provider=config.provider,
        base_url=base_url,
        api_key=config.api_key,
        model=config.model,
        timeout=config.timeout,
        retry_count=config.retry_count,
    )


def _extract_chat_content(response: requests.Response) -> str:
    content_type = str(response.headers.get("content-type", "")).lower()
    if "text/event-stream" in content_type:
        return _extract_sse_content(response)
    data = response.json()
    return _extract_message_content(data)


def _extract_sse_content(response: requests.Response) -> str:
    pieces: list[str] = []
    for raw_line in response.iter_lines(decode_unicode=False):
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

