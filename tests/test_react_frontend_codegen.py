import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import threading
from unittest.mock import patch
import unittest

from backend.softcopyright.ai_frontend_codegen import _sanitize_react_visible_terms, generate_ai_frontend_pages
from backend.softcopyright.blueprint import FeatureModule, ProductBlueprint
from backend.softcopyright.generator import _ui_screenshot_html_quality
from backend.softcopyright.llm.provider import LLMConfig, OpenAICompatibleProvider, _stream_hard_timeout_seconds
from backend.softcopyright.models import GenerationTask
from backend.softcopyright.screenshots import UiScreenshot
from backend.softcopyright.ui_blueprint import UiBlueprint, UiScreenBlueprint


class _ReactProvider:
    def __init__(self):
        self.messages = []

    def chat(self, messages, **kwargs):
        self.messages.append(messages)
        content = messages[-1]["content"]
        prompt = content if isinstance(content, str) else content[0]["text"]
        scope = re.search(r'className="screen-root ([^"]+)"', prompt).group(1)
        creative_key = re.search(r'data-page-structure="([^"]+)"', prompt).group(1)
        cards = "".join(
            f'<article className="work-card card-{index}"><strong>巡检任务 {index}</strong><span>设备状态正常</span><button>查看记录</button></article>'
            for index in range(1, 9)
        )
        confirmation_source = (
            '<section hidden data-shared-confirm-source="true">'
            '<h2 data-confirm-title>确认下达巡检工单</h2>'
            '<p data-confirm-description>下达后任务将进入待执行状态并通知责任班组。</p>'
            '<div data-confirm-item data-label="工单编号" data-value="WO-20260717-018"></div>'
            '<div data-confirm-item data-label="责任班组" data-value="东区设备巡检组"></div>'
            '<p data-confirm-note>工单状态将由草稿变为待执行，并写入操作日志。</p>'
            '<span data-confirm-action>确认下达</span></section>'
            if '"requires_confirmation": true' in prompt
            else ""
        )
        jsx = (
            f'<div className="screen-root {scope}" data-page-structure="{creative_key}">'
            '<header className="mobile-header"><b>设备巡检移动端</b><button data-action="import">导入任务</button></header>'
            '<main className="mobile-workspace"><section className="runtime-record-panel"><span>EquipmentAssetRecord</span>'
            '<h1>今日现场任务</h1><p>按区域查看待执行、异常和已完成巡检。</p></section>'
            f'<section className="task-stream">{cards}</section></main>'
            '<nav className="mobile-tabs"><button>首页</button><button>任务</button><button>我的</button></nav>'
            f'{confirmation_source}</div>'
        )
        css = (
            f'.{scope}{{height:100%;display:grid;grid-template-rows:72px 1fr 78px;background:#f3f7fa;color:#18324a;overflow:hidden;}}'
            f'.{scope} .mobile-header{{display:flex;align-items:center;justify-content:space-between;padding:0 28px;background:#0d4f5c;color:white;}}'
            f'.{scope} .mobile-workspace{{padding:24px;overflow:hidden;display:grid;grid-template-rows:auto 1fr;gap:18px;}}'
            f'.{scope} .runtime-record-panel{{background:white;border-radius:22px;padding:22px;box-shadow:0 8px 28px rgba(10,50,70,.12);}}'
            f'.{scope} .task-stream{{display:grid;grid-template-columns:1fr 1fr;gap:14px;overflow:hidden;}}'
            f'.{scope} .work-card{{background:white;border:1px solid #d9e5ea;border-radius:18px;padding:18px;display:flex;flex-direction:column;gap:10px;min-width:0;}}'
            f'.{scope} button{{border:0;border-radius:12px;padding:10px 16px;background:#168779;color:white;white-space:nowrap;}}'
            f'.{scope} .mobile-tabs{{display:flex;align-items:center;justify-content:space-around;background:white;border-top:1px solid #d9e5ea;}}'
            f'.{scope} h1,.{scope} p{{margin:0 0 8px;overflow:hidden;text-overflow:ellipsis;}}'
        )
        return json.dumps({"jsx": jsx, "css": css}, ensure_ascii=False)


class ReactVisibleTermSanitizerTests(unittest.TestCase):
    def test_unfinished_placeholder_phrases_are_replaced_with_business_state(self):
        source = "<div><p>备注说明待补充：异常原因为空</p><span>资料待完善</span></div>"
        sanitized = _sanitize_react_visible_terms(source)
        self.assertNotIn("待补充", sanitized)
        self.assertNotIn("待完善", sanitized)
        self.assertIn("相关信息已核验", sanitized)


class _FailingReactProvider:
    def __init__(self):
        self.config = LLMConfig(provider="custom", model="slow-model", retry_count=3, timeout=220)
        self.call_events = []
        self.lock = threading.Lock()

    @property
    def calls(self):
        return len(self.call_events)

    def chat(self, _messages, **_kwargs):
        with self.lock:
            self.call_events.append(1)
        raise RuntimeError("LLM 请求失败：524 Server Error")


class _TransientReactProvider(_ReactProvider):
    def __init__(self):
        super().__init__()
        self.calls = 0

    def chat(self, messages, **kwargs):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("LLM 请求失败：Read timed out. (read timeout=90)")
        return super().chat(messages, **kwargs)


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format, *args):
        return


class _StreamingResponse:
    headers = {"content-type": "text/event-stream"}
    status_code = 200

    def raise_for_status(self):
        return None


class _StreamingSession:
    def __init__(self, response):
        self.response = response

    def post(self, *_args, **_kwargs):
        return self.response

    def close(self):
        return None


class ReactFrontendCodegenTests(unittest.TestCase):
    def test_streaming_uses_separate_hard_deadline(self):
        provider = OpenAICompatibleProvider(
            LLMConfig(provider="custom", base_url="https://gateway.example/v1", api_key="test-key", model="test-model", retry_count=0)
        )
        response = _StreamingResponse()
        with patch("backend.softcopyright.llm.provider._new_requests_session", return_value=_StreamingSession(response)), patch(
            "backend.softcopyright.llm.provider._extract_chat_content", return_value='{"ok":true}'
        ) as extract_content, patch.dict("os.environ", {"SOFT_LLM_STREAM_HARD_TIMEOUT_SECONDS": "600"}):
            started = __import__("time").perf_counter()
            result = provider.chat([{"role": "user", "content": "test"}], timeout=120)
        self.assertEqual(result, '{"ok":true}')
        deadline = extract_content.call_args.kwargs["deadline"]
        self.assertGreaterEqual(deadline - started, 599)
        self.assertEqual(_stream_hard_timeout_seconds(120), 600)

    def test_gateway_failure_opens_circuit_and_cancels_pending_pages(self):
        temp_root = Path("tmp")
        temp_root.mkdir(exist_ok=True)
        with patch.dict(
            "os.environ",
            {
                "SOFT_AI_FRONTEND_MODE": "react-vite",
                "SOFT_LLM_BATCH_WORKERS": "2",
                "SOFT_LLM_AI_FRONTEND_RETRY_COUNT": "0",
                "SOFT_LLM_AI_FRONTEND_TIMEOUT_SECONDS": "90",
                "SOFT_MODEL_GPT_FRONTEND_NAME": "fast-frontend-model",
            },
        ), TemporaryDirectory(dir=temp_root) as temporary_directory:
            root = Path(temporary_directory)
            task = GenerationTask(software_name="前端熔断测试系统", product_type="APP", seed="circuit-seed")
            module = FeatureModule(key="tasks", title="任务管理", description="管理任务。", entities=["Task"])
            blueprint = ProductBlueprint(
                software_name=task.software_name,
                version=task.version,
                language="JavaScript",
                product_type=task.product_type,
                industry="测试",
                purpose="验证网关熔断。",
                summary="验证前端生成快速停止。",
                modules=[module],
                roles=["管理员"],
                pages=["任务页"],
                dev_environment={},
                runtime_environment={},
                report_metrics=["任务数"],
            )
            ui_blueprint = UiBlueprint(
                renderer="mobile_app",
                visual_style="测试",
                source="llm",
                screens=[UiScreenBlueprint("screen_1", "任务页", "任务页", "mobile_home")],
                design_brief={},
            )
            screenshots = [
                UiScreenshot(
                    f"screen_{index}",
                    f"任务页{index}",
                    "任务",
                    str(root / f"screen_{index}.html"),
                    page_kind="module",
                    module_key="tasks",
                )
                for index in range(1, 7)
            ]
            provider = _FailingReactProvider()
            with self.assertRaisesRegex(RuntimeError, "停止剩余页面"):
                generate_ai_frontend_pages(
                    task=task,
                    blueprint=blueprint,
                    ui_blueprint=ui_blueprint,
                    screenshots=screenshots,
                    provider=provider,
                    require_llm=True,
                    visual_reference_report={
                        "ready": True,
                        "mode": "style_reference",
                        "reference_count": 1,
                        "page_count": len(screenshots),
                        "style_reference_ready": True,
                        "style_reference": {"ready": True},
                    },
                )
            self.assertEqual(provider.calls, 2)

    def test_transient_frontend_timeout_retries_only_current_page(self):
        temp_root = Path("tmp")
        temp_root.mkdir(exist_ok=True)
        with patch.dict(
            "os.environ",
            {"SOFT_AI_FRONTEND_MODE": "react-vite", "SOFT_LLM_AI_FRONTEND_WORKERS": "1"},
        ), TemporaryDirectory(dir=temp_root) as temporary_directory:
            root = Path(temporary_directory)
            task = GenerationTask(software_name="前端恢复测试系统", product_type="APP", seed="retry-seed")
            module = FeatureModule(key="tasks", title="任务管理", description="管理任务。", entities=["Task"])
            blueprint = ProductBlueprint(
                software_name=task.software_name,
                version=task.version,
                language="JavaScript",
                product_type=task.product_type,
                industry="测试",
                purpose="验证前端超时恢复。",
                summary="验证单页请求能够恢复。",
                modules=[module],
                roles=["管理员"],
                pages=["任务页"],
                dev_environment={},
                runtime_environment={},
                report_metrics=["任务数"],
            )
            ui_blueprint = UiBlueprint(
                renderer="mobile_app",
                visual_style="测试",
                source="llm",
                screens=[UiScreenBlueprint("tasks", "任务页", "任务页", "mobile_home")],
                design_brief={},
            )
            screenshots = [
                UiScreenshot("tasks", "任务页", "任务", str(root / "tasks.html"), page_kind="module", module_key="tasks")
            ]
            provider = _TransientReactProvider()
            report = generate_ai_frontend_pages(
                task=task,
                blueprint=blueprint,
                ui_blueprint=ui_blueprint,
                screenshots=screenshots,
                provider=provider,
                require_llm=True,
                visual_reference_report={"ready": True, "style_reference": {"ready": True}},
            )
            self.assertTrue(report["ready"])
            self.assertEqual(provider.calls, 2)

    def test_mobile_app_generates_buildable_react_vite_project(self):
        temp_root = Path("tmp")
        temp_root.mkdir(exist_ok=True)
        with patch.dict("os.environ", {"SOFT_AI_FRONTEND_MODE": "react-vite"}), TemporaryDirectory(dir=temp_root) as temporary_directory:
            root = Path(temporary_directory)
            task = GenerationTask(software_name="设备巡检移动端", product_type="APP", seed="react-mobile-seed")
            module = FeatureModule(
                key="field_task",
                title="现场巡检任务",
                description="执行设备巡检并记录异常。",
                entities=["FieldTask"],
                operations=["接单", "巡检", "上报", "完成"],
                data_fields=["任务编号", "设备名称", "巡检区域", "任务状态"],
            )
            blueprint = ProductBlueprint(
                software_name=task.software_name,
                version=task.version,
                language="JavaScript",
                product_type=task.product_type,
                industry="设备运维",
                purpose="支持移动巡检。",
                summary="面向现场人员的移动设备巡检应用。",
                modules=[module],
                roles=["巡检员"],
                pages=["任务首页", "巡检任务"],
                dev_environment={},
                runtime_environment={},
                report_metrics=["待巡检数", "异常设备数"],
            )
            ui_blueprint = UiBlueprint(
                renderer="mobile_app",
                visual_style="移动巡检",
                source="llm",
                screens=[UiScreenBlueprint("home", "任务首页", "移动首页", "mobile_home")],
                design_brief={
                    "visual_identity_spec": {"identity_signature": "mobile-identity"},
                    "product_experience_spec": {"experience_shape": "mobile_app"},
                },
            )
            screenshots = [
                UiScreenshot("home", "任务首页", "首页", str(root / "home.html"), page_kind="dashboard"),
                UiScreenshot("field_task", "巡检任务", "任务", str(root / "field_task.html"), page_kind="module", module_key="field_task"),
                UiScreenshot(
                    "field_task_operation_1_1",
                    "巡检工单下达",
                    "下达巡检工单",
                    str(root / "field_task_operation_1_1.html"),
                    page_kind="operation",
                    module_key="field_task",
                    interaction_action="下达巡检工单",
                    interaction_mode="workflow",
                    interaction_surface="workflow_result",
                    requires_confirmation=True,
                    interaction_role="巡检主管",
                    interaction_trigger="工单内容复核完成",
                    interaction_input_fields=["责任班组", "计划时间"],
                    interaction_pre_state="草稿",
                    interaction_post_state="待执行",
                    interaction_result_evidence="工单状态和操作日志",
                ),
            ]
            provider = _ReactProvider()
            report = generate_ai_frontend_pages(
                task=task,
                blueprint=blueprint,
                ui_blueprint=ui_blueprint,
                screenshots=screenshots,
                provider=provider,
                require_llm=True,
                visual_reference_report={
                    "ready": True,
                    "mode": "style_reference",
                    "reference_count": 1,
                    "page_count": 3,
                    "style_reference_ready": True,
                    "style_reference": {"ready": True},
                },
            )
            self.assertTrue(report["ready"])
            self.assertEqual(report["framework"], "react")
            self.assertEqual(report["renderer"], "mobile_app")
            self.assertTrue(provider.messages)
            self.assertTrue(all(isinstance(messages[-1]["content"], str) for messages in provider.messages))
            prompts = [messages[-1]["content"] for messages in provider.messages]
            self.assertTrue(all("统一渲染共享品牌栏、主导航和当前功能标题" in prompt for prompt in prompts))
            self.assertTrue(all("一个主要工作区和不超过两个辅助区域" in prompt for prompt in prompts))
            initial_request_count = len(provider.messages)
            resumed_messages = []
            resumed_report = generate_ai_frontend_pages(
                task=task,
                blueprint=blueprint,
                ui_blueprint=ui_blueprint,
                screenshots=screenshots,
                provider=provider,
                emit=lambda progress, message, **_extra: resumed_messages.append(message),
                require_llm=True,
                visual_reference_report={
                    "ready": True,
                    "mode": "style_reference",
                    "reference_count": 1,
                    "page_count": 2,
                    "style_reference_ready": True,
                    "style_reference": {"ready": True},
                },
            )
            self.assertTrue(resumed_report["ready"])
            self.assertEqual(len(provider.messages), initial_request_count)
            self.assertIn("复用全部 React 页面组件 3/3", resumed_messages)
            self.assertFalse(any("生成 React 界面组件" in message for message in resumed_messages))
            self.assertTrue((root / "react-app" / "src" / "App.jsx").exists())
            self.assertTrue((root / "react-app" / "src" / "SharedAppShell.jsx").exists())
            self.assertTrue((root / "react-app" / "src" / "SharedConfirmDialog.jsx").exists())
            app_source = (root / "react-app" / "src" / "App.jsx").read_text(encoding="utf-8")
            self.assertIn("SharedAppShell", app_source)
            self.assertIn("SharedConfirmDialog", app_source)
            self.assertIn('data-shared-confirmation-contract="v1"', app_source)
            self.assertIn("工作首页", app_source)
            self.assertIn("功能办理", app_source)
            self.assertEqual(report["shared_confirmation_contract"], "shared-confirm-dialog-v1")
            self.assertEqual(report["shared_confirmation_page_count"], 1)
            self.assertTrue(report["shared_confirmation_ready"])
            self.assertTrue((root / "assets" / "app.js").exists())
            self.assertIn("soft-react-screen", (root / "home.html").read_text(encoding="utf-8"))
            self.assertIn('data-renderer="mobile_app"', (root / "home.html").read_text(encoding="utf-8"))
            self.assertNotIn("stable-app", (root / "home.html").read_text(encoding="utf-8"))
            quality_text, quality_hits = _ui_screenshot_html_quality({item.key: item for item in screenshots})
            self.assertIn("今日现场任务", quality_text)
            self.assertIn("业务对象", quality_text)
            self.assertNotIn("EquipmentAssetRecord", quality_text)
            self.assertNotIn("FaultDiagnosisQuery", quality_text)
            self.assertNotIn("DiagnosisEvidenceTrace", quality_text)
            self.assertNotIn("待填写", quality_text)
            self.assertEqual(quality_hits, [])
            handler = partial(_QuietHandler, directory=str(root))
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                from playwright.sync_api import sync_playwright

                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(headless=True)
                    page = browser.new_page(viewport={"width": 720, "height": 1280}, is_mobile=True)
                    page_errors = []
                    page.on("pageerror", lambda error: page_errors.append(str(error)))
                    page.goto(f"http://127.0.0.1:{server.server_port}/home.html", wait_until="networkidle")
                    self.assertEqual(page.locator(".screen-root").count(), 1, page_errors)
                    self.assertEqual(page.locator(".shared-app-header").count(), 1, page_errors)
                    self.assertTrue(page.locator(".shared-app-header").is_visible())
                    self.assertFalse(page.locator(".mobile-header").is_visible())
                    self.assertIn("今日现场任务", page.locator("body").inner_text())
                    self.assertEqual(page.locator(".mobile-tabs").count(), 1)
                    page.goto(
                        f"http://127.0.0.1:{server.server_port}/field_task_operation_1_1.html",
                        wait_until="networkidle",
                    )
                    self.assertEqual(page.locator('[data-shared-confirm-dialog="true"]:visible').count(), 1, page_errors)
                    self.assertEqual(page.locator('.screen-root [role="dialog"]:visible').count(), 0, page_errors)
                    self.assertIn("确认下达巡检工单", page.locator(".shared-confirm-dialog").inner_text())
                    self.assertIn("东区设备巡检组", page.locator(".shared-confirm-dialog").inner_text())
                    self.assertIn("确认下达", page.locator(".shared-confirm-primary").inner_text())
                    browser.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
