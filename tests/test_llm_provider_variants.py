import threading
import time
import unittest
from unittest.mock import patch

import requests

from backend.softcopyright.llm.provider import (
    AnthropicProvider,
    LLMConfig,
    OpenAICompatibleProvider,
    TextErrorCategory,
    TextProviderError,
    TextRetryPolicy,
    build_provider,
    classify_text_error,
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


class _StatusResponse(_JsonResponse):
    headers = {"content-type": "application/json"}

    def __init__(self, status_code, data=None):
        super().__init__(data or {"choices": [{"message": {"content": "ok"}}]})
        self.status_code = status_code
        self.closed = False

    def raise_for_status(self):
        if self.status_code >= 400:
            error = requests.HTTPError(f"{self.status_code} response")
            error.response = self
            raise error

    def close(self):
        self.closed = True


class _SequenceSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.closed = False

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def close(self):
        self.closed = True


class _BlockingStreamingResponse:
    status_code = 200
    headers = {"content-type": "text/event-stream"}

    def __init__(self):
        self.closed = threading.Event()

    def raise_for_status(self):
        return None

    def iter_lines(self, decode_unicode=False):
        while not self.closed.wait(0.01):
            continue
        return
        yield b""

    def close(self):
        self.closed.set()


class LlmProviderVariantTests(unittest.TestCase):
    def test_text_error_classification_covers_retry_and_configuration_categories(self):
        cases = [
            (_StatusResponse(401), TextErrorCategory.CONFIGURATION),
            (_StatusResponse(429), TextErrorCategory.RATE_LIMIT),
            (_StatusResponse(503), TextErrorCategory.GATEWAY),
            (requests.ConnectionError("connection reset"), TextErrorCategory.CONNECTION),
            (requests.Timeout("read timed out"), TextErrorCategory.TIMEOUT),
            (ValueError("LLM response content is empty"), TextErrorCategory.EMPTY_RESPONSE),
        ]
        for source, expected in cases:
            with self.subTest(expected=expected.value):
                if isinstance(source, _StatusResponse):
                    error = requests.HTTPError(f"{source.status_code} response")
                    error.response = source
                else:
                    error = source
                self.assertEqual(classify_text_error(error), expected)

    def test_empty_response_retries_twice_inside_provider_and_records_trace(self):
        provider = OpenAICompatibleProvider(
            LLMConfig(provider="gpt", base_url="https://gateway.example/v1", api_key="test-key", model="test-model")
        )
        session = _SequenceSession([_StatusResponse(200), _StatusResponse(200), _StatusResponse(200)])
        policy_events = []
        policy = TextRetryPolicy(
            max_retries=2,
            base_delay_seconds=0,
            on_error=lambda *args: policy_events.append(args),
        )
        with patch("backend.softcopyright.llm.provider._new_requests_session", return_value=session), patch(
            "backend.softcopyright.llm.provider._extract_chat_content", side_effect=["", "", "ok"]
        ), patch("backend.softcopyright.llm.provider.trace_event") as trace:
            result = provider.chat([{"role": "user", "content": "test"}], retry_policy=policy)

        self.assertEqual(result, "ok")
        self.assertEqual(len(session.calls), 3)
        self.assertEqual([event[0] for event in policy_events], [TextErrorCategory.EMPTY_RESPONSE] * 2)
        error_traces = [call.kwargs for call in trace.call_args_list if call.args and call.args[0] == "provider_request_error"]
        self.assertEqual(len(error_traces), 2)
        self.assertTrue(all(item["error_category"] == "empty_response" for item in error_traces))
        self.assertTrue(all(item["retry_budget"] == 2 and item["stop_reason"] == "retrying" for item in error_traces))

    def test_rate_limit_retries_but_configuration_error_fails_immediately(self):
        provider = OpenAICompatibleProvider(
            LLMConfig(provider="gpt", base_url="https://gateway.example/v1", api_key="test-key", model="test-model")
        )
        rate_session = _SequenceSession([_StatusResponse(429), _StatusResponse(200)])
        with patch("backend.softcopyright.llm.provider._new_requests_session", return_value=rate_session), patch(
            "backend.softcopyright.llm.provider._extract_chat_content", return_value="ok"
        ):
            result = provider.chat(
                [{"role": "user", "content": "test"}],
                retry_policy=TextRetryPolicy(max_retries=2, base_delay_seconds=0),
            )
        self.assertEqual(result, "ok")
        self.assertEqual(len(rate_session.calls), 2)

        configuration_session = _SequenceSession([_StatusResponse(401), _StatusResponse(200)])
        with patch("backend.softcopyright.llm.provider._new_requests_session", return_value=configuration_session):
            with self.assertRaises(TextProviderError) as raised:
                provider.chat(
                    [{"role": "user", "content": "test"}],
                    retry_policy=TextRetryPolicy(max_retries=2, base_delay_seconds=0),
                )
        self.assertEqual(raised.exception.category, TextErrorCategory.CONFIGURATION)
        self.assertEqual(raised.exception.attempts, 1)
        self.assertEqual(raised.exception.stop_reason, "configuration_error_no_retry")
        self.assertEqual(len(configuration_session.calls), 1)

    def test_cancelling_stream_closes_response_and_session(self):
        provider = OpenAICompatibleProvider(
            LLMConfig(provider="gpt", base_url="https://gateway.example/v1", api_key="test-key", model="test-model")
        )
        response = _BlockingStreamingResponse()
        session = _SequenceSession([response])
        cancel_event = threading.Event()
        outcome = {}

        def run_request():
            try:
                provider.chat(
                    [{"role": "user", "content": "test"}],
                    retry_policy=TextRetryPolicy(max_retries=2, base_delay_seconds=0),
                    cancel_event=cancel_event,
                )
            except Exception as exc:
                outcome["error"] = exc

        with patch("backend.softcopyright.llm.provider._new_requests_session", return_value=session):
            thread = threading.Thread(target=run_request)
            thread.start()
            deadline = time.time() + 1
            while not session.calls and time.time() < deadline:
                time.sleep(0.01)
            cancel_event.set()
            thread.join(timeout=2)

        self.assertFalse(thread.is_alive())
        self.assertTrue(response.closed.is_set())
        self.assertTrue(session.closed)
        self.assertIsInstance(outcome.get("error"), TextProviderError)
        self.assertEqual(outcome["error"].category, TextErrorCategory.CANCELLED)
        self.assertEqual(outcome["error"].stop_reason, "cancelled")

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
