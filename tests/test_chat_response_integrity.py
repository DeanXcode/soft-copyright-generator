import json
import unittest
from unittest.mock import patch

from backend.softcopyright.llm import provider as impl


class Response:
    status_code = 200

    def __init__(self, data=None, lines=None):
        self.data = data
        self.lines = lines
        self.headers = {"content-type": "text/event-stream" if lines is not None else "application/json"}

    def json(self):
        return self.data

    def iter_lines(self, **kwargs):
        yield from (line.encode("utf-8") for line in self.lines)

    def raise_for_status(self):
        pass

    def close(self):
        pass


def event(content=None, finish=None, usage=None):
    data = {"choices": [{"delta": {"content": content or ""}, "finish_reason": finish}]}
    if usage:
        data["usage"] = usage
    return "data: " + json.dumps(data)


class ChatResponseIntegrityTests(unittest.TestCase):
    def test_stream_metadata_and_multiline_events_are_retained(self):
        lines = ['data: {"choices": [', 'data: {"delta":{"content":"{}"}}]}', "",
                 event(finish="stop", usage={"completion_tokens": 2, "secret": "never-log"}),
                 "", "data: [DONE]", ""]
        details = {}
        result = impl._extract_chat_content(Response(lines=lines), metadata=details)
        impl._validate_chat_completion(details)
        self.assertEqual(result, "{}")
        self.assertEqual(details["usage"], {"completion_tokens": 2})
        self.assertEqual(details["finish_reason"], "stop")
        self.assertTrue(details["done_marker"])

    def test_gateway_without_blank_separators_is_supported(self):
        details = {}
        result = impl._extract_chat_content(Response(lines=[event("{"), event("}"), event(finish="stop"), "data: [DONE]"]), metadata=details)
        impl._validate_chat_completion(details)
        self.assertEqual(result, "{}")
        self.assertTrue(details["done_marker"])

    def test_finish_reason_is_sufficient_when_gateway_omits_done(self):
        details = {}
        impl._extract_chat_content(Response(lines=[event("{}", "stop")]), metadata=details)
        impl._validate_chat_completion(details)
        self.assertFalse(details["done_marker"])

    def test_missing_end_signal_or_corrupt_event_cannot_succeed(self):
        for lines in ([event("partial")], [event("{}"), "", "data: corrupt", "", "data: [DONE]"]):
            with self.subTest(lines=lines):
                details = {}
                impl._extract_chat_content(Response(lines=lines), metadata=details)
                with self.assertRaises(impl.TextResponseError) as raised:
                    impl._validate_chat_completion(details)
                self.assertEqual(impl.classify_text_error(raised.exception), impl.TextErrorCategory.CONNECTION)

    def test_length_and_filter_finish_reasons_are_format_failures(self):
        for reason in ("length", "content_filter", "tool_calls"):
            for streaming in (True, False):
                details = {}
                response = (Response(lines=[event("{}", reason), "", "data: [DONE]"]) if streaming else
                            Response(data={"choices": [{"message": {"content": "{}"}, "finish_reason": reason}]}))
                impl._extract_chat_content(response, metadata=details)
                with self.assertRaises(impl.TextResponseError) as raised:
                    impl._validate_chat_completion(details)
                self.assertEqual(impl.classify_text_error(raised.exception), impl.TextErrorCategory.FORMAT)

    def test_upstream_error_event_is_not_a_successful_partial_response(self):
        with self.assertRaises(impl.TextResponseError) as raised:
            impl._extract_chat_content(Response(lines=[event("partial"), "", 'data: {"error":{"message":"private gateway error"}}', ""]))
        self.assertEqual(raised.exception.category, impl.TextErrorCategory.GATEWAY)
        self.assertNotIn("private gateway", str(raised.exception))

    def test_provider_traces_usage_and_bounded_retries_for_broken_stream(self):
        from tests.test_llm_provider_variants import _SequenceSession
        provider = impl.OpenAICompatibleProvider(impl.LLMConfig(base_url="https://example.invalid", api_key="test"))
        session = _SequenceSession([
            Response(lines=[event("partial")]),
            Response(lines=[event("{}", "stop", {"completion_tokens": 2}), "", "data: [DONE]"]),
        ])
        with patch.object(impl, "_new_requests_session", return_value=session), patch.object(impl, "trace_event") as trace:
            result = provider.chat([], retry_policy=impl.TextRetryPolicy(max_retries=1, base_delay_seconds=0))
        self.assertEqual(result, "{}")
        self.assertEqual(len(session.calls), 2)
        successes = [c.kwargs for c in trace.call_args_list if c.args[0] == "provider_request_success"]
        self.assertEqual(len(successes), 1)
        self.assertEqual(successes[0]["finish_reason"], "stop")
        self.assertEqual(successes[0]["usage"]["completion_tokens"], 2)

    def test_blueprint_has_one_format_repair_but_no_authentication_retry(self):
        from backend.softcopyright.llm_blueprint import _chat_json
        from types import SimpleNamespace
        for category, expected_calls in ((impl.TextErrorCategory.FORMAT, 2), (impl.TextErrorCategory.CONFIGURATION, 1)):
            failure = impl.TextProviderError("test", category=category, attempts=1, retry_budget=0, stop_reason="test")
            provider = SimpleNamespace()
            with patch.object(provider, "chat", create=True, side_effect=[failure, '{"ok":true}']) as chat:
                if expected_calls == 2:
                    self.assertEqual(_chat_json(provider, [], temperature=0, max_tokens=100, label="test"), {"ok": True})
                else:
                    with self.assertRaises(impl.TextProviderError):
                        _chat_json(provider, [], temperature=0, max_tokens=100, label="test")
                self.assertEqual(chat.call_count, expected_calls)

    def test_provider_grows_output_budget_after_length_finish(self):
        provider = impl.OpenAICompatibleProvider(
            impl.LLMConfig(base_url="https://example.invalid", api_key="test", stream=False)
        )
        first = Response(data={"choices": [{"message": {"content": "{"}, "finish_reason": "length"}]})
        second = Response(data={"choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}]})
        from tests.test_llm_provider_variants import _SequenceSession
        session = _SequenceSession([first, second])
        with patch.object(impl, "_new_requests_session", return_value=session):
            self.assertEqual(
                provider.chat([], max_tokens=1024, retry_policy=impl.TextRetryPolicy(max_retries=0)),
                "{}",
            )
        self.assertEqual(session.calls[0][1]["json"]["max_tokens"], 1024)
        self.assertEqual(session.calls[1][1]["json"]["max_tokens"], 2048)

    def test_length_retries_stop_at_limit_and_report_actual_retry(self):
        from tests.test_llm_provider_variants import _SequenceSession
        from unittest.mock import Mock
        for initial, cap, expected in ((1024, "8192", [1024, 2048, 4096]),
                                       (4096, "6000", [4096, 6000]),
                                       (8192, "8192", [8192])):
            with self.subTest(initial=initial, cap=cap):
                session = _SequenceSession([Response(data={"choices": [
                    {"message": {"content": "{"}, "finish_reason": "length"}
                ]}) for _ in expected])
                on_error = Mock()
                provider = impl.OpenAICompatibleProvider(impl.LLMConfig(
                    base_url="https://example.invalid", api_key="test", stream=False))
                with patch.object(impl, "_new_requests_session", return_value=session), \
                     patch.dict(impl.os.environ, {"SOFT_LLM_MAX_OUTPUT_TOKENS": cap}):
                    with self.assertRaises(impl.TextProviderError):
                        provider.chat([], max_tokens=initial, retry_policy=impl.TextRetryPolicy(
                            max_retries=0, on_error=on_error))
                self.assertEqual([c[1]["json"]["max_tokens"] for c in session.calls], expected)
                self.assertEqual([c.args[3] for c in on_error.call_args_list],
                                 [True] * (len(expected) - 1) + [False])

    def test_filter_does_not_trigger_length_retry(self):
        from tests.test_llm_provider_variants import _SequenceSession
        session = _SequenceSession([Response(data={"choices": [
            {"message": {"content": "{}"}, "finish_reason": "content_filter"}
        ]})])
        provider = impl.OpenAICompatibleProvider(impl.LLMConfig(
            base_url="https://example.invalid", api_key="test", stream=False))
        with patch.object(impl, "_new_requests_session", return_value=session):
            with self.assertRaises(impl.TextProviderError):
                provider.chat([], max_tokens=1024)
        self.assertEqual(len(session.calls), 1)

    def test_length_retry_preserves_network_retry_budget(self):
        from tests.test_llm_provider_variants import _SequenceSession
        session = _SequenceSession([
            Response(data={"choices": [{"message": {"content": "{"}, "finish_reason": "length"}]}),
            impl.requests.ConnectionError("interrupted"),
            Response(data={"choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}]}),
        ])
        provider = impl.OpenAICompatibleProvider(impl.LLMConfig(
            base_url="https://example.invalid", api_key="test", stream=False))
        with patch.object(impl, "_new_requests_session", return_value=session):
            self.assertEqual(provider.chat([], max_tokens=1024, retry_policy=impl.TextRetryPolicy(
                max_retries=1, base_delay_seconds=0)), "{}")
        self.assertEqual([c[1]["json"]["max_tokens"] for c in session.calls], [1024, 2048, 2048])


if __name__ == "__main__":
    unittest.main()
