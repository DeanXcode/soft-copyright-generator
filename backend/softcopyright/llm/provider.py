from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any

import requests


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
    ) -> str:
        raise NotImplementedError


class LocalTemplateProvider(LLMProvider):
    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        return ""


class OpenAICompatibleProvider(LLMProvider):
    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: dict[str, Any] | None = None,
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
        }
        if response_format:
            payload["response_format"] = response_format

        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        last_error: Exception | None = None
        for _ in range(max(1, self.config.retry_count + 1)):
            try:
                response = requests.post(url, json=payload, headers=headers, timeout=self.config.timeout)
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"]
            except Exception as exc:
                last_error = exc
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

