import unittest
from unittest.mock import patch

from backend.softcopyright.llm.provider import (
    AnthropicProvider,
    LLMConfig,
    OpenAICompatibleProvider,
    build_provider,
)


class _JsonResponse:
    status_code = 200

    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self._data


class _CaptureSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response

    def close(self):
        return None


class LlmProviderVariantTests(unittest.TestCase):
    def test_official_provider_presets_use_expected_adapters(self):
        cases = [
            ("grok", "https://api.x.ai/v1", OpenAICompatibleProvider),
            ("gemini", "https://generativelanguage.googleapis.com/v1beta/openai", OpenAICompatibleProvider),
            ("deepseek", "https://api.deepseek.com", OpenAICompatibleProvider),
            ("claude", "https://api.anthropic.com/v1", AnthropicProvider),
        ]
        for provider_name, expected_base, expected_type in cases:
            with self.subTest(provider=provider_name):
                provider = build_provider(LLMConfig(provider=provider_name, api_key="test-key", model="test-model"))
                self.assertIsInstance(provider, expected_type)
                self.assertEqual(provider.config.base_url, expected_base)

    def test_claude_uses_messages_api_and_anthropic_headers(self):
        provider = build_provider(
            LLMConfig(provider="claude", api_key="claude-key", model="claude-test", retry_count=0)
        )
        session = _CaptureSession(_JsonResponse({"content": [{"type": "text", "text": '{"ok":true}'}]}))
        with patch("backend.softcopyright.llm.provider._new_requests_session", return_value=session):
            result = provider.chat(
                [
                    {"role": "system", "content": "只输出 JSON"},
                    {"role": "user", "content": "生成界面"},
                ],
                max_tokens=800,
                response_format={"type": "json_object"},
            )

        self.assertEqual(result, '{"ok":true}')
        url, request = session.calls[0]
        self.assertEqual(url, "https://api.anthropic.com/v1/messages")
        self.assertEqual(request["headers"]["x-api-key"], "claude-key")
        self.assertEqual(request["headers"]["anthropic-version"], "2023-06-01")
        self.assertEqual(request["json"]["system"], "只输出 JSON")
        self.assertEqual(request["json"]["messages"], [{"role": "user", "content": "生成界面"}])
        self.assertNotIn("response_format", request["json"])

    def test_gemini_and_deepseek_do_not_receive_openai_reasoning_effort(self):
        for provider_name in ("gemini", "deepseek", "grok"):
            with self.subTest(provider=provider_name):
                provider = build_provider(
                    LLMConfig(provider=provider_name, api_key="test-key", model="test-model", retry_count=0)
                )
                response = _JsonResponse({"choices": [{"message": {"content": "ok"}}]})
                session = _CaptureSession(response)
                with patch("backend.softcopyright.llm.provider._new_requests_session", return_value=session), patch(
                    "backend.softcopyright.llm.provider._extract_chat_content", return_value="ok"
                ):
                    provider.chat([{"role": "user", "content": "test"}])
                self.assertNotIn("reasoning_effort", session.calls[0][1]["json"])


if __name__ == "__main__":
    unittest.main()
