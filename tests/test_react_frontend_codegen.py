import json
import base64
from functools import partial
from http.server import SimpleHTTPRequestHandler
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import threading
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from backend.softcopyright.ai_frontend_codegen import (
    MODEL_GENERATED_REACT_VERSION,
    _build_react_vite_bundle,
    _frontend_page_cache_ready,
    _page_spec_renderer_migration_ready,
    _model_react_composition_contract,
    _react_codegen_worker_setting,
    _runtime_guard_style,
    _sanitize_cached_react_component,
    _sanitize_cached_react_css,
    _sanitize_external_css_resources,
    _sanitize_inline_react_styles,
    _sanitize_react_text_operators,
    _react_build_error_detail,
    _scope_react_css,
    _sanitize_react_visible_terms,
    _shared_confirm_dialog_css,
    _shared_app_shell_source,
    _style_reference_prompt_text,
    _validate_model_navigation_markup,
    generate_ai_frontend_pages,
)
from backend.softcopyright.blueprint import FeatureModule, ProductBlueprint
from backend.softcopyright.generator import (
    _ui_placeholder_hits,
    _ui_screenshot_html_quality,
    _ui_screenshot_placeholder_details,
)
from backend.softcopyright.llm.provider import (
    LLMConfig,
    OpenAICompatibleProvider,
    TextErrorCategory,
    TextProviderError,
    TextRetryPolicy,
    _stream_hard_timeout_seconds,
    classify_text_error,
)
from backend.softcopyright.models import GenerationTask
from backend.softcopyright.screenshots import (
    UiScreenshot,
    _capture_visible_action_crops,
    _capture_visible_content_summary,
    _runtime_layout_guard_style,
    runtime_api_script,
)
from backend.softcopyright.ui_blueprint import UiBlueprint, UiScreenBlueprint
from tests.http_test_utils import create_safe_threading_http_server


class _ReactProvider:
    def __init__(self):
        self.messages = []

    def chat(self, messages, **kwargs):
        self.messages.append(messages)
        content = messages[-1]["content"]
        prompt = content if isinstance(content, str) else content[0]["text"]
        if "结构化 PageSpec" in prompt or "受控 PageSpec" in prompt:
            page_key_match = re.search(r'page_key 固定为 "([^"]+)"', prompt)
            page_kind_match = re.search(r'page_kind 固定为 "([^"]+)"', prompt)
            action_key_match = re.search(r'"interaction_action_key":\s*"([^"]*)"', prompt)
            action_match = re.search(r'"interaction_action":\s*"([^"]*)"', prompt)
            page_key = page_key_match.group(1) if page_key_match else "tasks"
            page_kind = page_kind_match.group(1) if page_kind_match else "module"
            action_key = action_key_match.group(1) if action_key_match else ""
            action_label = action_match.group(1) if action_match and action_match.group(1) else "提交处理"
            mobile = '"renderer": "mobile_app"' in prompt or "720x1280" in prompt
            regions = [
                {
                    "id": "filters",
                    "component": "filter_bar",
                    "title": "任务筛选",
                    "fields": [{"label": "任务编号", "value": "请输入任务编号"}, {"label": "任务状态", "value": "全部状态"}],
                },
                {
                    "id": "tasks",
                    "component": "mobile_list" if mobile else "data_table",
                    "title": "巡检任务清单",
                    "columns": ["任务编号", "设备名称", "责任班组", "任务状态"],
                    "items": [
                        {"label": f"巡检任务 {index}", "value": f"WO-202607-{index:03d}", "owner": "东区巡检组", "status": "进行中"}
                        for index in range(1, 6)
                    ],
                },
                {
                    "id": "metrics",
                    "component": "metric_group",
                    "title": "任务指标",
                    "metrics": [{"label": "今日任务", "value": "28"}, {"label": "完成率", "value": "96.4%"}],
                },
            ]
            actions = []
            contract = {"mode": "browse", "requires_confirmation": False}
            if action_key:
                actions = [{"action_key": action_key, "label": action_label, "variant": "primary", "requires_confirmation": '"requires_confirmation": true' in prompt}]
                contract = {
                    "mode": "workflow",
                    "action_key": action_key,
                    "role": "巡检主管",
                    "trigger": "任务信息与执行条件核验通过",
                    "input_fields": ["任务编号", "责任班组"],
                    "pre_state": "待处理",
                    "post_state": "已提交",
                    "result_evidence": "任务状态和操作日志",
                    "requires_confirmation": '"requires_confirmation": true' in prompt,
                }
                regions.append({"id": "result", "component": "operation_result", "title": "操作结果"})
            return json.dumps(
                {
                    "schema_version": "page-spec-v1",
                    "page_key": page_key,
                    "page_kind": page_kind,
                    "layout": "mobile_feed" if mobile else "table_workspace",
                    "theme": {"density": "comfortable", "accent_variant": "primary"},
                    "regions": regions,
                    "actions": actions,
                    "interaction_contract": contract,
                },
                ensure_ascii=False,
            )
        scope = re.search(r'className="screen-root ([^"]+)"', prompt).group(1)
        creative_key = re.search(r'data-page-structure="([^"]+)"', prompt).group(1)
        if "横屏桌面设计文件浏览器" in prompt:
            rows = "".join(
                f'<button className="design-file-row" data-navigation-secondary-item="file-{index}" data-navigation-page-key="design_resources"><span>◇</span><b>设计文件 {index}</b><small>刚刚更新</small></button>'
                for index in range(1, 9)
            )
            jsx = (
                f'<div className="screen-root {scope} generated-design-browser" data-page-structure="{creative_key}">'
                '<header className="browser-tabs"><button data-navigation-primary-item="dashboard" data-navigation-page-key="dashboard">☰</button><div className="active-tab" data-navigation-primary-item="design_resources" data-navigation-page-key="design_resources"><b>Figma浏览器</b><span>×</span></div><button data-navigation-primary-item="statistics" data-navigation-page-key="statistics">+</button></header>'
                '<nav className="browser-toolbar"><button data-navigation-back-target="dashboard">←</button><button data-navigation-breadcrumb-item="software" data-navigation-page-key="dashboard">团队</button><button data-navigation-breadcrumb-item="project" data-navigation-page-key="design_resources">项目</button><label><span>⌕</span><input placeholder="搜索设计资源" /></label><button>⋯</button></nav>'
                '<main className="design-browser-workspace"><aside className="design-file-tree"><h2>团队资源</h2>'
                f'{rows}</aside><section className="design-canvas"><header><h1>设计资源导航</h1><button>打开设计文件</button></header>'
                '<div className="canvas-board"><article><i></i><strong>会员中心</strong><span>1280 × 720</span></article>'
                '<article><i></i><strong>订单工作台</strong><span>1440 × 900</span></article></div><footer>画布 · 100%</footer></section>'
                '<aside className="design-inspector"><nav><b>设计</b><span>原型</span><span>检查</span></nav>'
                '<section className="runtime-record-panel"><h2>属性</h2><p>文件状态 <strong>可评审</strong></p><p>待处理评论 <strong>3</strong></p></section></aside></main></div>'
            )
            css = (
                f'.{scope}{{height:100%;display:grid;grid-template-rows:36px 42px minmax(0,1fr);background:#e7e8ea;color:#25272b;overflow:hidden;}}'
                f'.{scope} *{{box-sizing:border-box;min-width:0;}}.{scope} button,.{scope} input{{font:inherit;}}'
                f'.{scope} .browser-tabs{{display:grid;grid-template-columns:38px minmax(180px,260px) 38px;align-items:center;background:#e8eaed;border-bottom:1px solid #d1d4d8;}}'
                f'.{scope} .browser-tabs button,.{scope} .browser-toolbar button{{height:100%;border:0;background:transparent;}}'
                f'.{scope} .active-tab{{height:31px;margin-top:5px;padding:0 10px;display:flex;align-items:center;justify-content:space-between;border-radius:6px 6px 0 0;background:#fff;font-size:11px;overflow:hidden;}}'
                f'.{scope} .browser-toolbar{{display:grid;grid-template-columns:34px 34px 34px minmax(0,1fr) 34px;gap:2px;padding:5px 8px;background:#fff;border-bottom:1px solid #d7d9dc;}}'
                f'.{scope} .browser-toolbar label{{display:grid;grid-template-columns:24px minmax(0,1fr);align-items:center;border-radius:6px;background:#f1f3f4;overflow:hidden;}}.{scope} .browser-toolbar input{{height:30px;border:0;background:transparent;}}'
                f'.{scope} .design-browser-workspace{{min-height:0;display:grid;grid-template-columns:210px minmax(0,1fr) 238px;overflow:hidden;}}'
                f'.{scope} .design-file-tree,.{scope} .design-inspector{{padding:12px;background:#fff;overflow:hidden auto;}}.{scope} .design-file-tree{{border-right:1px solid #d5d7da;}}.{scope} .design-inspector{{border-left:1px solid #d5d7da;}}'
                f'.{scope} .design-file-tree h2,.{scope} .design-inspector h2{{font-size:12px;}}.{scope} .design-file-row{{width:100%;padding:8px;display:grid;grid-template-columns:18px minmax(0,1fr);border:0;border-radius:4px;background:transparent;text-align:left;}}'
                f'.{scope} .design-file-row small{{grid-column:2;color:#777;font-size:9px;}}.{scope} .design-canvas{{min-height:0;display:grid;grid-template-rows:48px minmax(0,1fr) 30px;overflow:hidden;}}'
                f'.{scope} .design-canvas>header{{padding:0 14px;display:flex;align-items:center;justify-content:space-between;background:#fff;}}.{scope} .design-canvas h1{{font-size:13px;overflow-wrap:anywhere;}}'
                f'.{scope} .canvas-board{{padding:28px;display:grid;grid-template-columns:1fr 1fr;gap:26px;overflow:auto;}}.{scope} .canvas-board article{{min-height:180px;padding:12px;display:grid;grid-template-rows:1fr auto auto;background:#fff;box-shadow:0 2px 8px rgba(0,0,0,.14);}}'
                f'.{scope} .canvas-board i{{background:#e9f2ff;}}.{scope} .design-canvas footer{{padding:7px 12px;background:#fff;text-align:right;font-size:9px;}}.{scope} .design-inspector nav{{display:flex;gap:18px;border-bottom:1px solid #ddd;padding-bottom:10px;font-size:10px;}}'
                f'.{scope} .runtime-record-panel p{{display:flex;justify-content:space-between;gap:8px;font-size:10px;overflow-wrap:anywhere;}}'
            )
            return json.dumps(
                {
                    "jsx": jsx,
                    "css": css,
                    "composition_family": "design-browser",
                    "composition_variant": "file-tree-canvas-inspector",
                },
                ensure_ascii=False,
            )
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
    def test_old_pagespec_cache_is_renderer_migratable_without_being_current(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            component_path = root / "Screen.jsx"
            css_path = root / "Screen.css"
            spec_path = root / "Screen.page-spec.json"
            meta_path = root / "Screen.meta.json"
            creative_key = "cached-creative-key"
            component_path.write_text("x" * 1000, encoding="utf-8")
            css_path.write_text("x" * 600, encoding="utf-8")
            spec_path.write_text(
                json.dumps({"schema_version": "page-spec-v1", "page_key": "screen"}),
                encoding="utf-8",
            )
            meta_path.write_text(
                json.dumps(
                    {
                        "creative_key": creative_key,
                        "page_key": "screen",
                        "engine": "page-spec-v1",
                        "cache_key": "old-renderer-cache-key",
                        "page_spec_schema_version": "page-spec-v1",
                        "component_library_version": "page-components-v1",
                    }
                ),
                encoding="utf-8",
            )

            self.assertFalse(
                _frontend_page_cache_ready(
                    component_path=component_path,
                    css_path=css_path,
                    spec_path=spec_path,
                    meta_path=meta_path,
                    creative_key=creative_key,
                    legacy=False,
                )
            )
            self.assertTrue(
                _page_spec_renderer_migration_ready(
                    spec_path=spec_path,
                    meta_path=meta_path,
                    creative_key=creative_key,
                )
            )

    def test_frontend_worker_setting_defaults_to_auto_two_and_keeps_legacy_numbers(self):
        with patch.dict("os.environ", {}, clear=False):
            with patch("os.getenv", return_value="auto"):
                self.assertEqual(_react_codegen_worker_setting(35), ("auto", 2))
            with patch("os.getenv", return_value="3"):
                self.assertEqual(_react_codegen_worker_setting(35), ("fixed", 3))

    def test_windows_invalid_argument_is_retryable_for_current_page(self):
        error = OSError(22, "Invalid argument")

        self.assertEqual(classify_text_error(error), TextErrorCategory.CONNECTION)

    def test_ssl_eof_is_a_fast_transient_error_with_two_page_retries(self):
        error = RuntimeError(
            "LLM 请求失败：HTTPSConnectionPool(host='gateway.example', port=443): "
            "Max retries exceeded with url: /v1/chat/completions "
            "(Caused by SSLError(SSLEOFError(8, 'EOF occurred in violation of protocol')))"
        )

        self.assertEqual(classify_text_error(error), TextErrorCategory.CONNECTION)

    def test_read_timeout_keeps_one_current_page_retry(self):
        error = RuntimeError("LLM 请求失败：Read timed out. (read timeout=120)")

        self.assertEqual(classify_text_error(error), TextErrorCategory.TIMEOUT)

    def test_empty_model_response_is_transient_with_two_current_page_retries(self):
        error = ValueError("LLM 请求失败：LLM response content is empty")

        self.assertEqual(classify_text_error(error), TextErrorCategory.EMPTY_RESPONSE)

    def test_unfinished_placeholder_phrases_are_replaced_with_business_state(self):
        source = "<div><p>备注说明待补充：异常原因为空</p><span>资料待完善</span><b>产线智能排程记录01</b></div>"
        sanitized = _sanitize_react_visible_terms(source)
        self.assertNotIn("待补充", sanitized)
        self.assertNotIn("待完善", sanitized)
        self.assertNotIn("记录01", sanitized)
        self.assertIn("对象01", sanitized)
        self.assertIn("相关信息已核验", sanitized)


class SharedConfirmDialogThemeTests(unittest.TestCase):
    def test_shared_dialog_inherits_shell_visual_tokens(self):
        css = _shared_confirm_dialog_css()

        self.assertIn("var(--shell-accent", css)
        self.assertIn("var(--shell-accent-soft", css)
        self.assertIn("var(--shell-sidebar", css)
        self.assertIn("var(--shell-canvas", css)
        self.assertNotIn("#ea580c", css.lower())
        self.assertNotIn("#d94f08", css.lower())
        self.assertNotIn("#eef8f3", css.lower())
        self.assertIn("width:min(720px", css)
        self.assertIn("height:390px", css)
        self.assertIn("white-space:nowrap", css)


class UiVisibleLeakDetectionTests(unittest.TestCase):
    def test_runtime_record_name_fallback_is_not_generic_business_record(self):
        script = runtime_api_script()
        self.assertNotIn('"当前业务记录"', script)
        self.assertIn('"当前对象"', script)

    def test_business_role_key_is_rejected(self):
        item = UiScreenshot(
            key="role-leak",
            title="角色泄漏",
            caption="角色泄漏",
            html_path="",
            visible_content_summary={"visible_text": "当前处理角色 business_operator"},
        )
        with TemporaryDirectory() as temp_dir:
            html_path = Path(temp_dir) / "role-leak.html"
            html_path.write_text("<main>当前处理角色 business_operator</main>", encoding="utf-8")
            item.html_path = str(html_path)
            _, hits = _ui_screenshot_html_quality({item.key: item})

        self.assertIn("role-leak:内部角色标识", hits)
        self.assertIn("内部角色标识", _ui_placeholder_hits("当前处理角色 business_operator"))

    def test_business_manifest_filename_is_allowed(self):
        item = UiScreenshot(
            key="manifest",
            title="成果清单",
            caption="成果清单",
            html_path="",
            visible_content_summary={"visible_text": "成果文件 texture_manifest.json 已校验"},
        )
        with TemporaryDirectory() as temp_dir:
            html_path = Path(temp_dir) / "manifest.html"
            html_path.write_text("<main>成果文件 texture_manifest.json 已校验</main>", encoding="utf-8")
            item.html_path = str(html_path)
            _, hits = _ui_screenshot_html_quality({item.key: item})

        self.assertEqual(hits, [])
        self.assertNotIn("内部角色标识", _ui_placeholder_hits("成果文件 texture_manifest.json 已校验"))

    def test_legitimate_business_record_reference_is_not_a_generic_record_name(self):
        text = "记录撤销前后状态、影响门禁点、阻断生效时间、操作主体和关联业务记录"

        self.assertNotIn("泛化记录名", _ui_placeholder_hits(text))

    def test_generic_record_name_reports_page_and_matched_text(self):
        item = UiScreenshot(
            key="generic-record",
            title="记录列表",
            caption="记录列表",
            html_path="",
            visible_content_summary={"visible_text": "当前对象 业务记录1 待处理"},
        )
        with TemporaryDirectory() as temp_dir:
            html_path = Path(temp_dir) / "generic-record.html"
            html_path.write_text("<main>当前对象 业务记录1 待处理</main>", encoding="utf-8")
            item.html_path = str(html_path)
            details = _ui_screenshot_placeholder_details({item.key: item})

        self.assertIn("泛化记录名", _ui_placeholder_hits("业务记录1"))
        self.assertIn("generic-record:泛化记录名:业务记录1", details)


def _mock_provider_chat(operation, kwargs):
    """Exercise the provider-owned retry contract without test-time sleeps."""
    policy = kwargs.get("retry_policy") or TextRetryPolicy()
    retry_budget = policy.normalized_retries()
    total_attempts = retry_budget + 1
    cancel_event = kwargs.get("cancel_event")
    for attempt in range(1, total_attempts + 1):
        if cancel_event is not None and cancel_event.is_set():
            raise TextProviderError(
                "文本请求已取消",
                category=TextErrorCategory.CANCELLED,
                attempts=attempt,
                retry_budget=retry_budget,
                stop_reason="cancelled",
            )
        if callable(policy.on_attempt):
            policy.on_attempt(attempt, retry_budget)
        try:
            value = operation()
        except Exception as exc:
            category = classify_text_error(exc)
            will_retry = attempt < total_attempts and policy.should_retry(category)
            if will_retry:
                stop_reason = "retrying"
            elif category is TextErrorCategory.CONFIGURATION:
                stop_reason = "configuration_error_no_retry"
            elif attempt >= total_attempts:
                stop_reason = "retry_budget_exhausted"
            else:
                stop_reason = "non_retryable_error"
            if callable(policy.on_error):
                policy.on_error(category, attempt, retry_budget, will_retry, stop_reason)
            if will_retry:
                continue
            raise TextProviderError(
                str(exc),
                category=category,
                attempts=attempt,
                retry_budget=retry_budget,
                stop_reason=stop_reason,
            ) from exc
        if callable(policy.on_success):
            policy.on_success(attempt, retry_budget)
        return value
    raise AssertionError("mock retry loop exhausted without a result")


class _FailingReactProvider:
    def __init__(self):
        self.config = LLMConfig(provider="custom", model="slow-model", retry_count=3, timeout=220)
        self.call_events = []
        self.page_calls = {}
        self.lock = threading.Lock()

    @property
    def calls(self):
        return len(self.call_events)

    def chat(self, _messages, **kwargs):
        trace_label = str(kwargs.get("trace_label") or "unknown")

        def fail():
            with self.lock:
                self.call_events.append(1)
                self.page_calls[trace_label] = self.page_calls.get(trace_label, 0) + 1
            raise RuntimeError("LLM 请求失败：524 Server Error")

        return _mock_provider_chat(fail, kwargs)


class _TransientReactProvider(_ReactProvider):
    def __init__(self):
        super().__init__()
        self.calls = 0

    def chat(self, messages, **kwargs):
        def operation():
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("LLM 请求失败：Read timed out. (read timeout=90)")
            return super(_TransientReactProvider, self).chat(messages, **kwargs)

        return _mock_provider_chat(operation, kwargs)


class _EmptyThenSuccessReactProvider(_ReactProvider):
    def __init__(self):
        super().__init__()
        self.calls = 0

    def chat(self, messages, **kwargs):
        def operation():
            self.calls += 1
            if self.calls <= 2:
                raise ValueError("LLM 请求失败：LLM response content is empty")
            return super(_EmptyThenSuccessReactProvider, self).chat(messages, **kwargs)

        return _mock_provider_chat(operation, kwargs)


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
    def test_model_generated_react_has_independent_cache_and_composition_contract(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            component_path = root / "Screen.jsx"
            css_path = root / "Screen.css"
            spec_path = root / "Screen.page-spec.json"
            meta_path = root / "Screen.meta.json"
            component_path.write_text("x" * 1000, encoding="utf-8")
            css_path.write_text("x" * 600, encoding="utf-8")
            spec_path.write_text(json.dumps({"schema_version": "page-spec-v1", "page_key": "screen"}), encoding="utf-8")
            meta_path.write_text(
                json.dumps({"creative_key": "same-key", "page_key": "screen", "engine": "page-spec-v1"}),
                encoding="utf-8",
            )

            self.assertFalse(
                _frontend_page_cache_ready(
                    component_path=component_path,
                    css_path=css_path,
                    spec_path=spec_path,
                    meta_path=meta_path,
                    creative_key="same-key",
                    legacy=True,
                    react_engine=MODEL_GENERATED_REACT_VERSION,
                )
            )

        first = _model_react_composition_contract(
            {"composition_family": "design-browser", "composition_variant": "file-grid"},
            screenshot=SimpleNamespace(page_kind="module", interaction_surface="workspace", interaction_mode="browse"),
            creative_key="page-a",
        )
        second = _model_react_composition_contract(
            {"composition_family": "design-browser", "composition_variant": "canvas-review"},
            screenshot=SimpleNamespace(page_kind="operation", interaction_surface="canvas", interaction_mode="workflow"),
            creative_key="page-b",
        )
        self.assertEqual(first["version"], "model-react-composition-v1")
        self.assertNotEqual(first["variant"], second["variant"])
        self.assertNotEqual(first["signature"], second["signature"])

    def test_model_generated_navigation_requires_visible_contract_nodes(self):
        contract = {
            "primary_items": [{"key": "a"}, {"key": "b"}],
            "secondary_items": [{"key": "c"}, {"key": "d"}],
            "breadcrumb": [{"key": "home"}, {"key": "current"}],
            "back_target": {"page_key": "home"},
        }
        incomplete = '<div data-navigation-primary-item="a"></div>'
        with self.assertRaisesRegex(ValueError, "导航契约节点"):
            _validate_model_navigation_markup(incomplete, contract)

    def test_shared_shell_has_design_viewer_browser_chrome(self):
        source = _shared_app_shell_source()

        self.assertIn('if (config?.industry_subtype_key === "design_viewer") return <div className="model-react-contract"', source)
        self.assertIn("data-navigation-contract", source)
        self.assertNotIn('data-browser-workspace="true"', source)
        self.assertNotIn("shared-browser-tabs", source)

    def test_design_viewer_image2_prompt_requires_desktop_browser_workspace(self):
        task = GenerationTask(
            software_name="Figma浏览器",
            product_type="APP",
            feature_hint="设计文件、页面画板、图层组件和设计评审",
            seed="figma-image2-desktop",
        )
        module = SimpleNamespace(
            title="设计资源导航",
            description="浏览设计文件和页面画板",
            operations=["打开设计文件", "查询访问状态"],
            data_fields=["文件名称", "访问状态"],
        )
        blueprint = SimpleNamespace(
            business_objects=["设计文件", "页面画板", "图层组件"],
            report_metrics=["可访问文件数"],
        )
        ui_blueprint = SimpleNamespace(renderer="admin")
        design_brief = {
            "industry_subtype_key": "design_viewer",
            "product_experience_spec": {"terminal": "桌面设计资源工作区"},
        }
        prompt = _style_reference_prompt_text(
            {"layout_brief": "桌面设计资源工作区", "visual_prompt": "紧凑专业", "visual_tokens": ["文件树", "画布"]},
            task=task,
            blueprint=blueprint,
            ui_blueprint=ui_blueprint,
            screenshot=SimpleNamespace(title="设计资源导航", key="design_resources"),
            module=module,
            design_brief=design_brief,
        )

        self.assertIn("横向桌面设计文件浏览器", prompt)
        self.assertIn("文档标签栏", prompt)
        self.assertIn("资源路径/搜索栏", prompt)
        self.assertIn("右侧属性评论版本检查器", prompt)
        self.assertIn("禁止手机底部导航", prompt)
        self.assertNotIn("浏览器地址栏、代码窗口", prompt)

    def test_design_viewer_build_renders_browser_workspace_without_overflow(self):
        temp_root = Path("tmp")
        temp_root.mkdir(exist_ok=True)
        with patch.dict("os.environ", {"SOFT_AI_FRONTEND_MODE": "react-vite"}), TemporaryDirectory(dir=temp_root) as temporary_directory:
            root = Path(temporary_directory)
            task = GenerationTask(
                software_name="Figma浏览器",
                product_type="APP",
                feature_hint="设计文件、页面画板、图层组件、原型演示和设计评审",
                seed="figma-browser-workspace",
            )
            module = FeatureModule(
                key="design_resources",
                title="设计资源导航",
                description="浏览团队项目、设计文件、页面画板和图层组件。",
                entities=["设计文件", "页面画板", "图层组件"],
                operations=["查询文件访问状态", "打开设计文件", "切换文件版本"],
                data_fields=["文件名称", "所属项目", "更新时间", "访问状态"],
                pages=["移动端设计系统升级", "会员中心设计评审", "订单履约工作台"],
            )
            blueprint = ProductBlueprint(
                software_name=task.software_name,
                version=task.version,
                language="JavaScript",
                product_type=task.product_type,
                industry="设计协作",
                purpose="支持设计资源浏览与评审。",
                summary="桌面设计文件浏览与协作评审工作台。",
                modules=[module],
                roles=["UI/UX设计师"],
                pages=["设计资源导航"],
                dev_environment={},
                runtime_environment={},
                report_metrics=["可访问文件数"],
                industry_subtype_key="design_viewer",
            )
            ui_blueprint = UiBlueprint(
                renderer="admin",
                visual_style="桌面设计资源浏览器",
                source="llm",
                screens=[UiScreenBlueprint("design_resources", "设计资源导航", "浏览设计文件", "admin_table")],
                design_brief={
                    "industry_subtype_key": "design_viewer",
                    "visual_identity_spec": {
                        "identity_signature": "figma-browser-workspace",
                        "nav_model": "top_tabs",
                        "workspace_shape": "design_viewer",
                    },
                },
            )
            screenshots = [
                UiScreenshot(
                    "design_resources",
                    "Figma文件接入-查询名称非常长的文件访问状态",
                    "浏览设计文件",
                    str(root / "design_resources.html"),
                    page_kind="module",
                    module_key="design_resources",
                )
            ]
            reference_path = root / "style_reference.png"
            reference_path.write_bytes(
                base64.b64decode(
                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
                )
            )
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
                    "style_reference": {"ready": True, "image_path": str(reference_path)},
                },
            )
            self.assertTrue(report["ready"])
            self.assertEqual(report["frontend_generation_mode"], "model-generated-react")
            self.assertEqual(report["model_generated_react_page_count"], 1)
            self.assertEqual(report["page_spec_count"], 0)
            self.assertEqual(report["legacy_react_page_count"], 0)
            self.assertEqual(report["pages"][0]["engine"], MODEL_GENERATED_REACT_VERSION)
            self.assertEqual(report["pages"][0]["composition_contract"]["family"], "design-browser")
            self.assertEqual(report["pages"][0]["composition_contract"]["variant"], "file-tree-canvas-inspector")
            self.assertEqual(report["source"], "gpt-image2-to-model-generated-react-vite")
            frontend_engine = json.loads((root / "react-app" / ".frontend-engine.json").read_text(encoding="utf-8"))
            self.assertEqual(frontend_engine["frontend_generation_mode"], "model-generated-react")
            self.assertEqual(frontend_engine["react_engine_version"], MODEL_GENERATED_REACT_VERSION)
            self.assertEqual(frontend_engine["page_spec_schema_version"], "")
            self.assertEqual(len(list((root / "react-app" / "src" / "screens").glob("*.page-spec.json"))), 0)
            self.assertEqual(len(provider.messages), 1)
            model_content = provider.messages[0][-1]["content"]
            self.assertIsInstance(model_content, list)
            self.assertEqual(model_content[0]["type"], "text")
            self.assertEqual(model_content[1]["type"], "image_url")
            self.assertTrue(model_content[1]["image_url"]["url"].startswith("data:image/"))
            handler = partial(_QuietHandler, directory=str(root))
            server = create_safe_threading_http_server("127.0.0.1", handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                from playwright.sync_api import sync_playwright

                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(headless=True)
                    page = browser.new_page(viewport={"width": 1360, "height": 820})
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.goto(f"http://127.0.0.1:{server.server_port}/design_resources.html", wait_until="networkidle")
                    self.assertEqual(page.locator(".generated-design-browser:visible").count(), 1, errors)
                    self.assertTrue(page.locator(".browser-tabs").is_visible())
                    self.assertTrue(page.locator(".browser-toolbar").is_visible())
                    self.assertTrue(page.locator(".design-file-tree").is_visible())
                    self.assertTrue(page.locator(".design-canvas").is_visible())
                    self.assertTrue(page.locator(".design-inspector").is_visible())
                    self.assertEqual(page.locator('[data-navigation-contract="navigation-contract-v1"]').count(), 1)
                    self.assertGreaterEqual(page.locator("[data-navigation-primary-item]:visible").count(), 2)
                    self.assertGreaterEqual(page.locator("[data-navigation-secondary-item]:visible").count(), 2)
                    self.assertGreaterEqual(page.locator("[data-navigation-breadcrumb-item]:visible").count(), 2)
                    self.assertEqual(page.locator(".shared-app-mobile-nav:visible").count(), 0)
                    body_text = page.locator("body").inner_text()
                    for decorative in ("模块工作台", "业务操作", "较上一周期保持稳定", "按计划完成现场处理"):
                        self.assertNotIn(decorative, body_text)
                    self.assertEqual(
                        page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"),
                        True,
                    )
                    browser.close()
            finally:
                server.shutdown()
                server.server_close()

    def test_react_page_css_selectors_are_fully_scoped_and_idempotent(self):
        source = """.screen-page{display:grid}.metric-card,.table td{color:#123}
        @media(max-width:900px){.metric-card{font-size:12px}}
        @keyframes pulse{0%{opacity:.5}100%{opacity:1}}"""

        scoped = _scope_react_css(source, "screen-page")
        self.assertIn(".screen-page{display:grid}", scoped)
        self.assertIn(".screen-page .metric-card,.screen-page .table td{color:#123}", scoped)
        self.assertIn("@media(max-width:900px){.screen-page .metric-card{font-size:12px}}", scoped)
        self.assertIn("@keyframes pulse{0%{opacity:.5}100%{opacity:1}}", scoped)
        self.assertEqual(_scope_react_css(scoped, "screen-page"), scoped)

    def test_react_build_error_detail_keeps_file_and_syntax_line(self):
        detail = _react_build_error_detail(
            """vite v7 building\n✗ Build failed\nerror during build:\nERROR: Expected identifier but found \"0\"\nfile: src/screens/Bad.jsx:36:120\n36 | P 值 < 0.05\n at responseCallbacks"""
        )

        self.assertIn("Expected identifier", detail)
        self.assertIn("src/screens/Bad.jsx:36:120", detail)
        self.assertNotIn("responseCallbacks", detail)

    def test_jsx_numeric_less_than_text_is_escaped_for_esbuild(self):
        jsx, escaped_count = _sanitize_react_text_operators(
            "<div><span>校正后 P 值 < 0.05</span><b>低于 <LOD</b><i>正常标签</i></div>"
        )

        self.assertEqual(escaped_count, 2)
        self.assertIn("P 值 &lt; 0.05", jsx)
        self.assertIn("低于 &lt;LOD", jsx)
        self.assertIn("<span>", jsx)
        self.assertIn("<i>", jsx)

    def test_inline_react_styles_are_removed_without_dropping_business_content(self):
        jsx, removed_count = _sanitize_inline_react_styles(
            '''<div className="screen-page" style={{ display: "grid", gap: 12 }}>
              <span style={progressStyle}>完成率 72%</span>
              <i style="width:72%;background:#0f766e">进度</i>
            </div>'''
        )

        self.assertEqual(removed_count, 3)
        self.assertNotRegex(jsx, r"(?i)\sstyle\s*=")
        self.assertIn("完成率 72%", jsx)
        self.assertIn("进度", jsx)

    def test_external_css_resources_are_removed_without_rejecting_the_page(self):
        css, removed_count = _sanitize_external_css_resources(
            '''@import url("https://fonts.example/font.css");
            @font-face{font-family:Remote;src:url("https://cdn.example/font.woff2") format("woff2")}
            .screen-page{background-image:url("https://cdn.example/hero.png");color:#123}
            .screen-page .icon{mask-image:url(data:image/svg+xml;base64,abc);display:block}'''
        )

        self.assertGreaterEqual(removed_count, 4)
        self.assertNotRegex(css, r"(?i)@import|@font-face|url\s*\(|https?://|data:image")
        self.assertIn(".screen-page", css)
        self.assertIn("color:#123", css)
        self.assertIn("background-image:none", css)

    def test_cached_css_external_resources_are_sanitized_for_resume(self):
        with TemporaryDirectory() as temporary_directory:
            css_path = Path(temporary_directory) / "screen.css"
            css_path.write_text(
                '.screen-page{display:grid;background:url("https://cdn.example/bg.png") center/cover;color:#123}',
                encoding="utf-8",
            )
            _sanitize_cached_react_css(css_path)
            sanitized = css_path.read_text(encoding="utf-8")
            self.assertNotIn("url(", sanitized)
            self.assertNotIn("https://", sanitized)
            self.assertIn("color:#123", sanitized)

    def test_cached_component_inline_styles_are_sanitized_for_resume(self):
        with TemporaryDirectory() as temporary_directory:
            component_path = Path(temporary_directory) / "Screen.jsx"
            component_path.write_text(
                '<div className="screen-page" style={{ width: "72%" }}><span style="color:red">完成率</span></div>',
                encoding="utf-8",
            )
            _sanitize_cached_react_component(component_path)
            sanitized = component_path.read_text(encoding="utf-8")
            self.assertNotRegex(sanitized, r"(?i)\sstyle\s*=")
            self.assertIn("完成率", sanitized)

    def test_admin_runtime_guard_prevents_vertical_map_labels_and_login_title_wrap(self):
        styles = [_runtime_guard_style("admin"), _runtime_layout_guard_style("admin")]

        for style in styles:
            self.assertIn(".map-pin,.map-node,.relation-node,.flow-node", style)
            self.assertIn('data-page-kind="login"', style)
            self.assertIn("white-space:nowrap!important", style)
            self.assertIn("word-break:keep-all!important", style)

    def test_cached_css_trims_an_incomplete_trailing_rule(self):
        temp_root = Path("tmp")
        temp_root.mkdir(exist_ok=True)
        with TemporaryDirectory(dir=temp_root) as temporary_directory:
            css_path = Path(temporary_directory) / "screen.css"
            css_path.write_text(
                '.screen-page{display:grid}.screen-page .label{content:"{"}.screen-page .broken{width:calc(100% - 12px)',
                encoding="utf-8",
            )
            _sanitize_cached_react_css(css_path)
            self.assertEqual(
                css_path.read_text(encoding="utf-8"),
                '.screen-page{display:grid}.screen-page .label{content:"{"}',
            )

    def test_packaged_vite_build_prefers_electron_as_node(self):
        electron_node = r"C:\Program Files\Soft Copyright Generator\Soft Copyright Generator.exe"
        system_node = r"C:\Program Files\nodejs\node.exe"
        with patch.dict(
            "os.environ",
            {
                "SOFT_ELECTRON_NODE": electron_node,
                "SOFT_NODE_MODULE_ROOT": r"C:\Program Files\Soft Copyright Generator\resources\app.asar\node_modules",
            },
        ), patch("backend.softcopyright.frontend_codegen.vite_build.shutil.which", return_value=system_node), patch(
            "backend.softcopyright.frontend_codegen.vite_build.subprocess.run"
        ) as run:
            run.return_value.returncode = 0
            run.return_value.stdout = ""
            _build_react_vite_bundle(Path("react-app"))

        command = run.call_args.args[0]
        self.assertEqual(command[0], electron_node)
        self.assertEqual(run.call_args.kwargs["env"]["ELECTRON_RUN_AS_NODE"], "1")

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
            with self.assertRaisesRegex(RuntimeError, "停止剩余页面") as raised:
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
            self.assertLessEqual(provider.calls, 6)
            self.assertLessEqual(len(provider.page_calls), 2)
            self.assertTrue(all(count <= 3 for count in provider.page_calls.values()))
            stats = getattr(raised.exception, "frontend_stats")
            # An immediate failure may stop submission before worker two is
            # scheduled. This metric records observed, not configured, work.
            self.assertIn(stats["frontend_effective_workers"], (1, 2))
            self.assertTrue(stats["frontend_concurrency_degraded"])
            self.assertEqual(stats["frontend_concurrency_degrade_reason"], "gateway_error")
            self.assertGreaterEqual(stats["frontend_cancelled_page_count"], 4)
            self.assertLessEqual(stats["provider_retry_summary"]["logical_requests"], 2)

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

    def test_empty_model_response_retries_current_page_twice_before_success(self):
        temp_root = Path("tmp")
        temp_root.mkdir(exist_ok=True)
        with patch.dict(
            "os.environ",
            {"SOFT_AI_FRONTEND_MODE": "react-vite", "SOFT_LLM_AI_FRONTEND_WORKERS": "1"},
        ), TemporaryDirectory(dir=temp_root) as temporary_directory:
            root = Path(temporary_directory)
            task = GenerationTask(software_name="空响应恢复测试系统", product_type="APP", seed="empty-retry-seed")
            module = FeatureModule(key="tasks", title="任务管理", description="管理任务。", entities=["Task"])
            blueprint = ProductBlueprint(
                software_name=task.software_name,
                version=task.version,
                language="JavaScript",
                product_type=task.product_type,
                industry="测试",
                purpose="验证模型空响应恢复。",
                summary="验证当前页面可在两次空响应后继续生成。",
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
            provider = _EmptyThenSuccessReactProvider()
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
            self.assertEqual(provider.calls, 3)

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
                    "visual_identity_spec": {"identity_signature": "mobile-identity", "workspace_shape": "case_desk"},
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
            self.assertEqual(report["page_spec_count"], 3)
            self.assertEqual(report["legacy_react_page_count"], 0)
            self.assertTrue(provider.messages)
            self.assertTrue(all(isinstance(messages[-1]["content"], str) for messages in provider.messages))
            prompts = [messages[-1]["content"] for messages in provider.messages]
            self.assertTrue(all("结构化 PageSpec" in prompt for prompt in prompts))
            self.assertTrue(all("不要生成 JSX、CSS、HTML" in prompt for prompt in prompts))
            self.assertTrue(all("allowed_region_components" in prompt for prompt in prompts))
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
            self.assertIn("复用全部 PageSpec/React 页面缓存 3/3", resumed_messages)
            self.assertFalse(any("生成 PageSpec 页面" in message for message in resumed_messages))
            self.assertTrue((root / "react-app" / "src" / "App.jsx").exists())
            self.assertTrue((root / "react-app" / "src" / "SharedAppShell.jsx").exists())
            self.assertTrue((root / "react-app" / "src" / "SharedConfirmDialog.jsx").exists())
            self.assertEqual(len(list((root / "react-app" / "src" / "screens").glob("*.page-spec.json"))), 3)
            app_source = (root / "react-app" / "src" / "App.jsx").read_text(encoding="utf-8")
            self.assertIn("SharedAppShell", app_source)
            self.assertIn("SharedConfirmDialog", app_source)
            self.assertIn('data-shared-confirmation-contract="v1"', app_source)
            self.assertIn('"navigation_contract"', app_source)
            self.assertIn('"schema_version": "navigation-contract-v1"', app_source)
            self.assertIn("任务首页", app_source)
            self.assertIn("现场巡检任务", app_source)
            self.assertIn('"nav_model": "top_tabs"', app_source)
            self.assertEqual(report["shared_confirmation_contract"], "shared-confirm-dialog-v1")
            self.assertEqual(report["shared_confirmation_page_count"], 1)
            self.assertTrue(report["shared_confirmation_ready"])
            self.assertEqual(report["navigation_contract_version"], "navigation-contract-v1")
            self.assertEqual(report["navigation_contract_count"], 3)
            self.assertTrue(report["navigation_contract_ready"])
            shell_source = (root / "react-app" / "src" / "SharedAppShell.jsx").read_text(encoding="utf-8")
            self.assertIn("data-navigation-contract", shell_source)
            self.assertIn("data-navigation-secondary-item", shell_source)
            self.assertIn("data-navigation-back-target", shell_source)
            self.assertIn("navigateToPage", shell_source)
            self.assertIn("config?.page_files?.[pageKey]", shell_source)
            self.assertIn("window.location.assign(target)", shell_source)
            self.assertIn('"page_files":', app_source)
            theme_source = (root / "react-app" / "src" / "theme.css").read_text(encoding="utf-8")
            self.assertIn("grid-template-columns:minmax(260px,340px) minmax(0,1fr) minmax(160px,220px)", theme_source)
            self.assertIn(".shared-app-context em{display:none}", theme_source)
            self.assertTrue((root / "assets" / "app.js").exists())
            self.assertIn("soft-react-screen", (root / "home.html").read_text(encoding="utf-8"))
            self.assertIn('data-renderer="mobile_app"', (root / "home.html").read_text(encoding="utf-8"))
            self.assertNotIn("stable-app", (root / "home.html").read_text(encoding="utf-8"))
            quality_text, quality_hits = _ui_screenshot_html_quality({item.key: item for item in screenshots})
            self.assertIn("巡检任务清单", quality_text)
            self.assertIn("东区巡检组", quality_text)
            self.assertNotIn("EquipmentAssetRecord", quality_text)
            self.assertNotIn("FaultDiagnosisQuery", quality_text)
            self.assertNotIn("DiagnosisEvidenceTrace", quality_text)
            self.assertNotIn("待填写", quality_text)
            self.assertEqual(quality_hits, [])
            handler = partial(_QuietHandler, directory=str(root))
            server = create_safe_threading_http_server("127.0.0.1", handler)
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
                    self.assertIn("巡检任务清单", page.locator("body").inner_text())
                    self.assertNotIn("case_desk", page.locator("body").inner_text())
                    self.assertEqual(page.locator(".shared-app-nav").count(), 1)
                    page.goto(
                        f"http://127.0.0.1:{server.server_port}/field_task_operation_1_1.html",
                        wait_until="networkidle",
                    )
                    self.assertEqual(page.locator('[data-shared-confirm-dialog="true"]:visible').count(), 1, page_errors)
                    self.assertEqual(page.locator('.screen-root [role="dialog"]:visible').count(), 0, page_errors)
                    self.assertIn("确认下达巡检工单", page.locator(".shared-confirm-dialog").inner_text())
                    self.assertIn("责任班组", page.locator(".shared-confirm-dialog").inner_text())
                    self.assertIn("确认下达", page.locator(".shared-confirm-primary").inner_text())
                    confirmation_summary = _capture_visible_content_summary(page, screenshots[2])
                    confirmation_crops = _capture_visible_action_crops(page, screenshots[2], root / "capture-review")
                    self.assertNotIn("巡检任务清单", confirmation_summary["visible_text"])
                    self.assertIn("取消", confirmation_crops)
                    self.assertTrue(any(label.startswith("确认") for label in confirmation_crops))
                    self.assertFalse(any("任务首页" in label for label in confirmation_crops))
                    browser.close()
            finally:
                server.shutdown()
                server.server_close()

    def test_admin_side_menu_shell_renders_business_navigation(self):
        temp_root = Path("tmp")
        temp_root.mkdir(exist_ok=True)
        with patch.dict("os.environ", {"SOFT_AI_FRONTEND_MODE": "react-vite"}), TemporaryDirectory(dir=temp_root) as temporary_directory:
            root = Path(temporary_directory)
            task = GenerationTask(software_name="工程质量协同平台", product_type="智慧城市软件", seed="react-side-menu-seed")
            modules = [
                FeatureModule(
                    key="quality_plan",
                    title="质量策划",
                    description="编制并审核项目质量策划。",
                    entities=["QualityPlan"],
                    operations=["查询", "审核"],
                    data_fields=["策划编号", "策划状态"],
                ),
                FeatureModule(
                    key="inspection_task",
                    title="巡检任务",
                    description="跟踪现场巡检任务。",
                    entities=["InspectionTask"],
                    operations=["查询", "分派"],
                    data_fields=["任务编号", "责任班组"],
                ),
            ]
            blueprint = ProductBlueprint(
                software_name=task.software_name,
                version=task.version,
                language="JavaScript",
                product_type=task.product_type,
                industry="工程质量管理",
                purpose="支持工程质量协同。",
                summary="面向项目团队的工程质量管理平台。",
                modules=modules,
                roles=["质量主管"],
                pages=["项目质量总览", "质量策划", "巡检任务"],
                dev_environment={},
                runtime_environment={},
                report_metrics=["待审核策划", "待巡检任务"],
            )
            ui_blueprint = UiBlueprint(
                renderer="admin",
                visual_style="工程质量侧栏工作台",
                source="llm",
                screens=[UiScreenBlueprint("dashboard", "项目质量总览", "项目质量总览", "dashboard")],
                design_brief={
                    "visual_identity_spec": {
                        "identity_signature": "engineering-quality-side-menu",
                        "nav_model": "side_menu",
                        "workspace_shape": "ledger_split",
                        "palette": {
                            "accent": "#b45309",
                            "accent_soft": "#fff7ed",
                            "sidebar": "#263238",
                            "canvas": "#f7f8f8",
                        },
                    }
                },
            )
            screenshots = [
                UiScreenshot("dashboard", "项目质量总览", "总览", str(root / "dashboard.html"), page_kind="dashboard"),
                UiScreenshot(
                    "quality_plan",
                    "质量策划界面",
                    "质量策划",
                    str(root / "quality_plan.html"),
                    page_kind="module",
                    module_key="quality_plan",
                ),
            ]
            report = generate_ai_frontend_pages(
                task=task,
                blueprint=blueprint,
                ui_blueprint=ui_blueprint,
                screenshots=screenshots,
                provider=_ReactProvider(),
                require_llm=True,
                visual_reference_report={"ready": True, "style_reference": {"ready": True}},
            )

            self.assertTrue(report["ready"])
            app_source = (root / "react-app" / "src" / "App.jsx").read_text(encoding="utf-8")
            self.assertIn('"nav_model": "side_menu"', app_source)
            handler = partial(_QuietHandler, directory=str(root))
            server = create_safe_threading_http_server("127.0.0.1", handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                from playwright.sync_api import sync_playwright

                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(headless=True)
                    page = browser.new_page(viewport={"width": 1360, "height": 820})
                    page.goto(f"http://127.0.0.1:{server.server_port}/quality_plan.html", wait_until="networkidle")
                    sidebar = page.locator('.shared-app-shell[data-nav-model="side_menu"] .shared-app-sidebar')
                    self.assertEqual(sidebar.count(), 1)
                    self.assertTrue(sidebar.is_visible())
                    self.assertEqual(page.locator(".shared-app-header").count(), 0)
                    self.assertIn("质量策划", sidebar.inner_text())
                    self.assertIn("巡检任务", sidebar.inner_text())
                    self.assertNotIn("工作首页", sidebar.inner_text())
                    self.assertNotIn("功能办理", sidebar.inner_text())
                    main_box = page.locator(".shared-app-main").bounding_box()
                    self.assertIsNotNone(main_box)
                    self.assertGreaterEqual(main_box["x"], 188)
                    browser.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
