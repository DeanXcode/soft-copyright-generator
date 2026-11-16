import json
from concurrent.futures import ALL_COMPLETED, wait as wait_for_futures
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
from unittest.mock import patch
import unittest

from backend.softcopyright.blueprint import FeatureModule, ProductBlueprint
from backend.softcopyright.llm.provider import LLMConfig, LLMProvider, TextErrorCategory, TextProviderError
from backend.softcopyright.llm_manual import _chat_json, generate_manual_content_with_llm
from backend.softcopyright.models import GenerationTask
from backend.softcopyright.stage_cache import load_partial_manual_content, save_partial_manual_content


class ScriptedProvider(LLMProvider):
    def __init__(self, modules, *, fail_modules=False, short_first=False, error_category=TextErrorCategory.GATEWAY):
        super().__init__(LLMConfig(provider="custom"))
        self.modules = modules
        self.fail_modules = fail_modules
        self.short_first = short_first
        self.error_category = error_category
        self.calls = []

    def chat(self, messages, **kwargs):
        prompt = messages[1]["content"] if messages[0]["role"] == "system" else messages[0]["content"]
        self.calls.append(prompt)
        if self.short_first:
            self.short_first = False
            return "{"
        if "本批公共章节" in prompt or "公共章节正文" in prompt:
            return json.dumps({"sections": {
                key: ["具体业务记录查询、状态核验与保存结果。"] * 2
                for key in ("overview", "login_main", "statistics", "security", "faq")
            }}, ensure_ascii=False)
        if self.fail_modules:
            raise TextProviderError(
                "模块请求失败", category=self.error_category,
                attempts=1, retry_budget=0, stop_reason=self.error_category.value,
            )
        content = {module.key: {
            "title": module.title,
            "paragraphs": [f"{module.title}中查询业务记录并保存状态。"] * 2,
        } for module in self.modules}
        if "本批功能模块" in prompt:
            return json.dumps({"modules": content}, ensure_ascii=False)
        module = next(module for module in self.modules if f"- key: {module.key}" in prompt)
        return json.dumps(content[module.key], ensure_ascii=False)


def make_blueprint(task):
    modules = [FeatureModule(
        key=f"module_{index}", title=f"业务模块{index}", description="处理业务记录。",
        entities=["Record"], operations=["查询", "保存"], data_fields=["编号", "状态"],
    ) for index in range(2)]
    return ProductBlueprint(
        software_name=task.software_name, version=task.version, language="Python",
        product_type=task.product_type, industry="设备运维", purpose="处理业务记录",
        summary="设备记录处理", modules=modules, roles=["管理员"], pages=["首页"],
        dev_environment={}, runtime_environment={}, quality_score=90,
    )


class ManualResumeTests(unittest.TestCase):
    def test_module_batches_start_before_slow_common_batch_finishes(self):
        task = GenerationTask(software_name="队列验证软件")
        blueprint = make_blueprint(task)
        module_started = threading.Event()
        lock = threading.Lock()
        active = 0
        peak = 0
        def sections(*args):
            nonlocal active, peak
            specs = args[-1]
            with lock:
                active += 1
                peak = max(peak, active)
            try:
                if specs[0][0] == "overview":
                    self.assertTrue(module_started.wait(5), "module queue is blocked by common-section barrier")
                return {"sections": {spec[0]: ["查询设备状态并保存处理结果。"] * 2 for spec in specs}}
            finally:
                with lock:
                    active -= 1
        def modules(*args):
            module_started.set()
            return {"modules": {m.key: {"paragraphs": ["查询设备状态并保存处理结果。"] * 2} for m in args[-1]}}
        with patch.dict("os.environ", {"SOFT_GENERATION_PROFILE": "balanced", "SOFT_LLM_BATCH_WORKERS": "2"}), patch(
            "backend.softcopyright.llm_manual._generate_section_batch", side_effect=sections
        ), patch("backend.softcopyright.llm_manual._generate_module_batch", side_effect=modules):
            result = generate_manual_content_with_llm(task, blueprint, ScriptedProvider(blueprint.modules))
        self.assertTrue(module_started.is_set())
        self.assertLessEqual(peak, 2)
        self.assertEqual(len(result["modules"]), 2)
        self.assertFalse(result.get("_warnings"))

    def test_fatal_error_does_not_submit_entire_manual_queue(self):
        task = GenerationTask(software_name="鉴权失败验证软件")
        blueprint = make_blueprint(task)
        error = TextProviderError("鉴权失败", category=TextErrorCategory.CONFIGURATION,
                                  attempts=1, retry_budget=0, stop_reason="configuration_error_no_retry")
        with patch.dict("os.environ", {"SOFT_LLM_BATCH_WORKERS": "1"}), patch(
            "backend.softcopyright.llm_manual._generate_section_batch", side_effect=error
        ) as sections, patch("backend.softcopyright.llm_manual._generate_module_batch") as modules:
            with self.assertRaises(TextProviderError):
                generate_manual_content_with_llm(task, blueprint, ScriptedProvider(blueprint.modules))
        self.assertEqual(sections.call_count, 1)
        modules.assert_not_called()

    def test_successful_peer_is_checkpointed_before_fatal_batch_stops_queue(self):
        task = GenerationTask(software_name="并发断点验证软件")
        blueprint = make_blueprint(task)
        error = TextProviderError("鉴权失败", category=TextErrorCategory.CONFIGURATION,
                                  attempts=1, retry_budget=0, stop_reason="configuration_error_no_retry")
        snapshots = []

        def sections(*args):
            specs = args[-1]
            if specs[0][0] != "overview":
                raise error
            return {"sections": {spec[0]: ["查询设备状态并保存处理结果。"] * 2 for spec in specs}}

        def finish_together(futures, **kwargs):
            done, pending = wait_for_futures(futures, return_when=ALL_COMPLETED, timeout=5)
            self.assertFalse(pending)
            # Process the failure first to exercise checkpoint preservation.
            return sorted(done, key=lambda f: f.exception() is None), pending

        with patch.dict("os.environ", {"SOFT_GENERATION_PROFILE": "balanced", "SOFT_LLM_BATCH_WORKERS": "2"}), patch(
            "backend.softcopyright.llm_manual.wait", side_effect=finish_together
        ), patch("backend.softcopyright.llm_manual._generate_section_batch", side_effect=sections) as batches, patch(
            "backend.softcopyright.llm_manual._generate_module_batch"
        ) as modules:
            with self.assertRaises(TextProviderError):
                generate_manual_content_with_llm(
                    task, blueprint, ScriptedProvider(blueprint.modules),
                    save_progress=lambda result: snapshots.append(json.loads(json.dumps(result))),
                )
        self.assertEqual(batches.call_count, 2)
        modules.assert_not_called()
        self.assertEqual(len(snapshots), 1)
        self.assertTrue(snapshots[0]["overview"])
        self.assertTrue(snapshots[0]["login_main"])

    def test_short_json_is_retried_with_clear_failure(self):
        provider = ScriptedProvider([], short_first=True)
        result = _chat_json(provider, [{"role": "user", "content": "本批公共章节正文"}],
                            temperature=0.5, max_tokens=100, label="测试")
        self.assertIn("sections", result)
        self.assertEqual(len(provider.calls), 2)

        provider = ScriptedProvider([], short_first=True)
        provider.chat = lambda *args, **kwargs: "{"
        with self.assertRaisesRegex(RuntimeError, "模型返回内容为空或被截断"):
            _chat_json(provider, [{"role": "user", "content": "测试"}],
                       temperature=0.5, max_tokens=100, label="测试")

    def test_partial_content_survives_failure_and_skips_completed_sections(self):
        with TemporaryDirectory() as directory:
            task = GenerationTask(software_name="续跑验证软件", output_root=Path(directory))
            blueprint = make_blueprint(task)
            context = {"enabled": True, "dir": Path(directory) / "cache", "manifest": {}}
            save = lambda content: save_partial_manual_content(context, blueprint, content)
            failing = ScriptedProvider(blueprint.modules, fail_modules=True)
            first = generate_manual_content_with_llm(task, blueprint, failing, save_progress=save)
            self.assertTrue(first.get("_warnings"))
            cached = load_partial_manual_content(context, blueprint)
            self.assertEqual(len([key for key in ("overview", "login_main", "statistics", "security", "faq") if key in cached]), 5)
            self.assertFalse(cached["modules"])

            working = ScriptedProvider(blueprint.modules)
            second = generate_manual_content_with_llm(
                task, blueprint, working, initial_content=cached, save_progress=save,
            )
            self.assertFalse(second.get("_warnings"))
            self.assertEqual(len(second["modules"]), 2)
            self.assertTrue(all("本批公共章节" not in call for call in working.calls))

            blueprint.modules[0].title = "已变更模块"
            self.assertEqual(load_partial_manual_content(context, blueprint), {"modules": {}})

    def test_configuration_error_does_not_retry_same_request(self):
        provider = ScriptedProvider([], fail_modules=True, error_category=TextErrorCategory.CONFIGURATION)
        with self.assertRaises(TextProviderError):
            _chat_json(provider, [{"role": "user", "content": "模块"}],
                       temperature=0.5, max_tokens=100, label="测试")
        self.assertEqual(len(provider.calls), 1)

    def test_configuration_error_skips_per_module_retries(self):
        task = GenerationTask(software_name="配置失败验证软件")
        blueprint = make_blueprint(task)
        provider = ScriptedProvider(
            blueprint.modules, fail_modules=True, error_category=TextErrorCategory.CONFIGURATION,
        )
        with self.assertRaises(TextProviderError):
            generate_manual_content_with_llm(task, blueprint, provider)
        self.assertEqual(sum("本批功能模块" in call for call in provider.calls), 1)
        self.assertFalse(any("当前模块：" in call for call in provider.calls))


if __name__ == "__main__":
    unittest.main()
