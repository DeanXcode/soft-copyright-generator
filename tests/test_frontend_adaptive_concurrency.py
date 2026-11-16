from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch

from backend.softcopyright.ai_frontend_codegen import _generate_react_frontend_pages
from backend.softcopyright.frontend_codegen.page_spec import normalize_page_spec
from backend.softcopyright.llm.provider import TextErrorCategory
from backend.softcopyright.models import GenerationTask
from backend.softcopyright.screenshots import UiScreenshot
from backend.softcopyright.ui_blueprint import UiBlueprint
from tests.test_llm_manual_resume import make_blueprint
from tests.test_page_spec import _valid_spec


class AdaptiveConcurrencyTests(unittest.TestCase):
    def test_timeout_degrades_clean_successes_recover_and_next_timeout_degrades_again(self):
        with TemporaryDirectory() as directory:
            task = GenerationTask(software_name="并发恢复验证软件")
            blueprint = make_blueprint(task)
            ui = UiBlueprint(renderer="admin", visual_style="", screens=[])
            screenshots = [UiScreenshot(f"page_{i}", "设备信息", "", str(Path(directory) / f"p{i}.html"),
                                        page_kind="module", module_key=blueprint.modules[0].key) for i in range(12)]
            lock = threading.Lock()
            logical_requests = 0
            def request(**kwargs):
                nonlocal logical_requests
                with lock:
                    logical_requests += 1
                    number = logical_requests
                policy = kwargs["retry_policy"]
                policy.on_attempt(1, 2)
                if number in (1, 7):
                    policy.on_error(TextErrorCategory.TIMEOUT, 1, 2, True, "retrying")
                    policy.on_attempt(2, 2)
                    policy.on_success(2, 2)
                else:
                    policy.on_success(1, 2)
                spec = deepcopy(_valid_spec(page_kind="module"))
                spec["page_key"] = kwargs["screen"]["key"]
                return normalize_page_spec(spec, expected_page_key=spec["page_key"], expected_page_kind="module")
            with patch.dict("os.environ", {"SOFT_LLM_AI_FRONTEND_WORKERS": "auto"}), patch(
                "backend.softcopyright.ai_frontend_codegen.request_page_spec", side_effect=request
            ), patch("backend.softcopyright.ai_frontend_codegen._build_react_vite_bundle"), patch(
                "backend.softcopyright.ai_frontend_codegen._publish_react_page_entries"
            ), patch("backend.softcopyright.ai_frontend_codegen.trace_event") as trace:
                report = _generate_react_frontend_pages(
                    task=task, blueprint=blueprint, ui_blueprint=ui, screenshots=screenshots,
                    module_by_key={m.key: m for m in blueprint.modules}, provider=object(),
                    visual_reference_report={}, style_reference={},
                )
            self.assertTrue(report["ready"])
            self.assertEqual(report["provider_retry_summary"]["request_attempts"], 14)
            self.assertEqual(report["frontend_concurrency_recoveries"], 2)
            self.assertEqual(report["frontend_final_worker_limit"], 2)
            self.assertEqual(sum(call.args[0] == "ai_frontend_concurrency_degraded" for call in trace.call_args_list), 2)


if __name__ == "__main__":
    unittest.main()
