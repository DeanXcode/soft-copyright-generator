import unittest
from pathlib import Path
from unittest.mock import patch

import requests

from backend.softcopyright.llm import provider as impl


class _Clock:
    now = 0.0

    def advance(self, seconds):
        self.now += seconds


class _Response:
    def __init__(self, status, *, html=False):
        self.status_code = status
        self.headers = {"content-type": "text/html" if html else "application/json"}
        self.text = "upstream timeout" if status >= 400 else ""
        self.closed = False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code), response=self)

    def json(self):
        return {"data": [{"b64_json": "test"}]}

    def close(self):
        self.closed = True


class _Session:
    def __init__(self, clock):
        self.clock = clock
        self.steps = []
        self.calls = []
        self.close_count = 0

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        duration, response = self.steps.pop(0)
        self.clock.advance(duration)
        if isinstance(response, Exception):
            raise response
        return response

    def close(self):
        self.close_count += 1


class ImageProviderReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.clock = _Clock()
        self.session = _Session(self.clock)
        self.provider = impl.OpenAICompatibleProvider(impl.LLMConfig(
            provider="custom", base_url="https://example.invalid/v1", api_key="test-key",
            image_model="test-image", image_retry_count=3,
        ))
        replacements = [
            patch.object(impl, "_new_requests_session", return_value=self.session),
            patch.object(impl.time, "perf_counter", side_effect=lambda: self.clock.now),
            patch.object(impl.time, "sleep", side_effect=self.clock.advance),
            patch.object(impl, "_save_image_response", return_value={"bytes": 2048, "source": "b64_json"}),
            patch.object(impl, "trace_event"),
            patch.dict("os.environ", {"SOFT_LLM_IMAGE_SLOW_FAILURE_LIMIT": "2", "SOFT_LLM_IMAGE_SLOW_FAILURE_SECONDS": "60"}),
        ]
        started = [replacement.start() for replacement in replacements]
        for replacement in replacements:
            self.addCleanup(replacement.stop)
        self.save_image = started[3]
        self.trace = started[4]

    def generate(self):
        return self.provider.generate_image(prompt="business screen", output_path=Path("unused-image.png"), size="1280x720")

    def test_persistent_slow_524_stops_after_two_requests_and_records_outcome(self):
        responses = [_Response(524) for _ in range(4)]
        self.session.steps = [(126, response) for response in responses]
        with self.assertRaises(impl.ImageProviderError) as raised:
            self.generate()
        self.assertEqual(len(self.session.calls), 2)
        self.assertEqual(raised.exception.attempts, 2)
        self.assertEqual(raised.exception.stop_reason, "consecutive_slow_failures")
        self.assertEqual(raised.exception.elapsed_seconds, 253.5)
        self.assertTrue(all(response.closed for response in responses[:2]))
        self.assertEqual(self.session.close_count, 2)
        self.save_image.assert_not_called()
        outcomes = [call.kwargs for call in self.trace.call_args_list if call.args[0] == "provider_image_request_error"]
        self.assertEqual([item["will_retry"] for item in outcomes], [True, False])
        self.assertEqual(outcomes[-1]["stop_reason"], "consecutive_slow_failures")

    def test_single_slow_failure_can_recover_without_shortening_image_read_timeout(self):
        self.session.steps = [(126, _Response(524)), (90, _Response(200))]
        result = self.generate()
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(result["size"], "1280x720")
        self.assertEqual(self.session.calls[0][1]["timeout"], (15, 220))
        self.save_image.assert_called_once()

    def test_fast_gateway_failures_keep_the_configured_retry_budget(self):
        self.session.steps = [(1, _Response(502)) for _ in range(4)]
        with self.assertRaises(impl.ImageProviderError) as raised:
            self.generate()
        self.assertEqual(len(self.session.calls), 4)
        self.assertEqual(raised.exception.stop_reason, "retry_budget_exhausted")

    def test_fast_error_resets_the_consecutive_slow_failure_count(self):
        self.session.steps = [(126, _Response(524)), (1, _Response(502)), (126, _Response(524)), (5, _Response(200))]
        self.assertEqual(self.generate()["attempts"], 4)

    def test_read_timeouts_use_the_same_slow_failure_protection(self):
        self.session.steps = [(220, requests.ReadTimeout("image read timeout")) for _ in range(4)]
        with self.assertRaises(impl.ImageProviderError) as raised:
            self.generate()
        self.assertEqual(raised.exception.attempts, 2)
        self.assertEqual(raised.exception.stop_reason, "consecutive_slow_failures")

    def test_quality_repair_is_not_confused_with_slow_network_failure(self):
        self.session.steps = [(100, _Response(200)) for _ in range(3)]
        self.save_image.side_effect = [impl.GeneratedImageQualityError("placeholder"), impl.GeneratedImageQualityError("placeholder"), {"bytes": 2048}]
        self.assertEqual(self.generate()["attempts"], 3)

    def test_authentication_failure_is_not_retried(self):
        self.session.steps = [(1, _Response(401))]
        with self.assertRaises(impl.ImageProviderError) as raised:
            self.generate()
        self.assertEqual(raised.exception.attempts, 1)
        self.assertEqual(raised.exception.stop_reason, "non_retryable_error")

    def test_root_html_endpoint_fallback_works_with_zero_network_retries(self):
        self.provider.config.base_url = "https://example.invalid"
        self.provider.config.image_retry_count = 0
        self.session.steps = [(1, _Response(200, html=True)), (1, _Response(200))]
        self.generate()
        self.assertEqual([call[0] for call in self.session.calls], [
            "https://example.invalid/images/generations", "https://example.invalid/v1/images/generations",
        ])
        self.assertEqual(self.session.close_count, 2)

    def test_explicit_zero_retries_is_preserved(self):
        self.provider.config.image_retry_count = 0
        self.session.steps = [(126, _Response(524))]
        with self.assertRaises(impl.ImageProviderError) as raised:
            self.generate()
        self.assertEqual(raised.exception.attempts, 1)
        self.assertEqual(raised.exception.stop_reason, "retry_budget_exhausted")


if __name__ == "__main__":
    unittest.main()
