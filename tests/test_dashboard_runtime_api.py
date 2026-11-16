import json
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest

from backend.softcopyright.generator import _ui_screenshot_realism_checks, _visible_html_text
from backend.softcopyright.screenshots import (
    _auto_repair_page_text_layout,
    _collect_page_text_layout_issues,
    _inject_runtime_script_into_ai_page,
    runtime_api_script,
)
from tests.http_test_utils import create_safe_threading_http_server


PROJECT_ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(PROJECT_ROOT / "ms-playwright"))


class _RuntimeApiHandler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".html": "text/html; charset=utf-8"}

    def do_GET(self):  # noqa: N802 - inherited handler API
        if self.path == "/inventory/":
            payload = json.dumps(
                {
                    "success": True,
                    "data": [
                        {
                            "code": "INV-2026-001",
                            "name": "主粮仓库存记录",
                            "serviceScope": "库存监测",
                            "status": "ENABLED",
                        }
                    ],
                },
                ensure_ascii=False,
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        super().do_GET()

    def log_message(self, format, *args):  # noqa: A002 - inherited handler API
        return


class DashboardRuntimeApiTests(unittest.TestCase):
    def test_runtime_api_probes_candidate_routes_sequentially_and_stops_after_success(self):
        script = runtime_api_script()

        self.assertIn("function apiPathGroups()", script)
        self.assertIn("async function fetchFirstAvailable(paths)", script)
        self.assertIn("if (result.ok) return result", script)
        self.assertIn('window["Abort" + "Controller"]', script)
        self.assertIn("requestOptions.signal = controller.signal", script)
        self.assertNotIn("Promise.all(paths.map", script)

    def test_route_runtime_binding_never_writes_business_text_into_decorative_icon(self):
        script = runtime_api_script()

        self.assertNotIn("pin.childNodes[0]", script)
        self.assertIn("node.nodeType === Node.TEXT_NODE", script)
        self.assertIn(":scope > b, :scope > strong", script)

    def test_chart_context_accepts_business_date_range_and_legends(self):
        checks = _ui_screenshot_realism_checks(
            primary_context="客户服务协同平台",
            html_text=(
                "统计日期 2026-07-17 客户咨询与工单转化趋势 按小时汇总 "
                "08:00 - 18:00 咨询接入量 转服务工单数 首次响应达标率 96.2%"
            ),
            renderer="admin",
        )
        self.assertTrue(checks["ui_chart_context_ready"])

    def test_chart_context_rejects_context_free_chart_placeholders(self):
        checks = _ui_screenshot_realism_checks(
            primary_context="客户服务协同平台",
            html_text="数据趋势 图表一 系列A 系列B",
            renderer="admin",
        )
        self.assertFalse(checks["ui_chart_context_ready"])

    def test_injection_upgrades_cached_runtime_script(self):
        with TemporaryDirectory() as temporary_directory:
            page_path = Path(temporary_directory) / "dashboard.html"
            page_path.write_text(
                """<!doctype html><html><head>
<style id=\"soft-ai-runtime-guard\">body{width:1280px;min-height:820px;overflow:hidden;}</style>
</head><body data-page-kind=\"dashboard\" data-module-key=\"\" data-renderer=\"admin\">
<!-- soft-runtime-api-script:v11 -->
<script>(function () { window.__runtimeApiReady = false; })();</script>
</body></html>""",
                encoding="utf-8",
            )
            _inject_runtime_script_into_ai_page(page_path, module_keys=["inventory"])
            html = page_path.read_text(encoding="utf-8")

        self.assertIn('data-runtime-module-keys="inventory"', html)
        self.assertNotIn("soft-runtime-api-script:v11", html)
        self.assertEqual(html.count("soft-runtime-api-script:v14"), 1)
        self.assertIn("height:720px!important", html)
        self.assertIn("table-layout:fixed!important", html)
        self.assertIn("white-space:nowrap!important", html)
        self.assertNotIn("min-height:820px", html)
        visible = _visible_html_text(html)
        self.assertIn("处理结果", visible)
        self.assertIn("状态与更新时间已保存", visible)
        self.assertNotIn("操作日志", visible)
        self.assertTrue(
            _ui_screenshot_realism_checks(primary_context="", html_text=visible, renderer="admin")[
                "ui_operation_result_evidence_ready"
            ]
        )

    def test_existing_result_text_without_audit_evidence_is_augmented(self):
        with TemporaryDirectory() as temporary_directory:
            page_path = Path(temporary_directory) / "operation.html"
            page_path.write_text(
                """<!doctype html><html><body data-page-kind=\"operation\" data-module-key=\"inventory\" data-renderer=\"admin\">
<section><span class=\"operation-result\">仍需确认下层 2 个测点坐标。</span></section>
</body></html>""",
                encoding="utf-8",
            )
            _inject_runtime_script_into_ai_page(page_path, module_keys=["inventory"])
            html = page_path.read_text(encoding="utf-8")

        self.assertIn("runtime-operation-evidence", html)
        visible = _visible_html_text(html)
        self.assertIn("仍需确认下层 2 个测点坐标", visible)
        self.assertIn("状态与更新时间已同步保存", visible)
        self.assertNotIn("操作日志", visible)
        self.assertTrue(
            _ui_screenshot_realism_checks(primary_context="", html_text=visible, renderer="admin")[
                "ui_operation_result_evidence_ready"
            ]
        )

    def test_complex_operation_result_keeps_layout_and_appends_compact_runtime_evidence(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            page_path = root / "operation.html"
            page_path.write_text(
                """<!doctype html><html><head><style>
body{margin:0;width:1280px;height:720px;overflow:hidden}.operation-result{width:460px;height:180px;padding:16px;border:1px solid #ddd}.operation-result p{margin:8px 0}
</style></head><body data-page-kind="operation" data-module-key="inventory" data-renderer="admin" data-ai-frontend="true">
<section class="effect-panel panel operation-result"><h2>处理成效评估</h2><p>保留原有业务说明和图表结构。</p><div><b>原始指标</b></div></section>
</body></html>""",
                encoding="utf-8",
            )
            _inject_runtime_script_into_ai_page(page_path, module_keys=["inventory"])
            handler = partial(_RuntimeApiHandler, directory=str(root))
            server = create_safe_threading_http_server("127.0.0.1", handler)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                from playwright.sync_api import sync_playwright

                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(headless=True)
                    page = browser.new_page(viewport={"width": 1280, "height": 720})
                    page.goto(f"http://127.0.0.1:{server.server_port}/operation.html", wait_until="networkidle")
                    page.wait_for_function("() => window.__runtimeApiReady === true || window.__runtimeApiError")
                    _auto_repair_page_text_layout(page, "admin")
                    runtime = page.evaluate(
                        """() => ({
                          title: document.querySelector('.operation-result h2')?.textContent || '',
                          description: document.querySelector('.operation-result p')?.textContent || '',
                          evidence: document.querySelector('[data-runtime-operation-result]')?.textContent || '',
                          resultMaxHeight: getComputedStyle(document.querySelector('.operation-result')).maxHeight
                        })"""
                    )
                    issues = _collect_page_text_layout_issues(page, include_overlaps=True)
                    browser.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

        self.assertEqual(runtime["title"], "处理成效评估")
        self.assertIn("保留原有业务说明", runtime["description"])
        self.assertIn("状态与更新时间已同步保存", runtime["evidence"])
        self.assertNotEqual(runtime["resultMaxHeight"], "42px")
        self.assertFalse(issues)

    def test_detail_operation_result_stays_inside_fixed_admin_workspace(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            page_path = root / "operation-detail.html"
            page_path.write_text(
                """<!doctype html><html><head><style>
body{margin:0;width:1280px;height:720px;overflow:hidden}
.shared-app-main{height:654px;margin-top:66px;overflow:hidden}
.screen-root{height:100%;display:flex;flex-direction:column;gap:8px;padding:10px;overflow:hidden}
.query-strip{height:96px;flex:0 0 96px;background:#fff}
.work-area{min-height:0;flex:1;display:grid;grid-template-columns:255px 1fr;gap:8px}
.result-rail,.detail-panel{min-height:0;border:1px solid #ddd}
.detail-panel{display:flex;flex-direction:column;overflow:hidden}
.order-banner{height:67px;flex:0 0 67px;padding:9px 13px;background:#132f49;color:#fff}
.metrics{height:91px;flex:0 0 91px}
.detail-grid{padding:8px;display:grid;grid-template-columns:1.55fr 1fr;grid-template-rows:1.03fr .97fr;gap:8px}
.detail-grid>section{min-height:246px;border:1px solid #ddd;overflow:hidden}
</style></head><body data-page-kind="operation" data-module-key="inventory" data-renderer="admin" data-ai-frontend="true">
<div class="shared-app-main"><div class="screen-root"><section class="query-strip">生产工单查询条件</section>
<div class="work-area"><aside class="result-rail">关联工单</aside><main class="detail-panel operation-result">
<div class="order-banner"><div class="eyebrow">当前生产工单 · 来源 MPS-2026-W29 / V4.1 WO-20260716-0386</div><h2>生产工单详情</h2></div>
<div class="metrics">计划数量、执行进度、计划交期、物料齐套</div>
<div class="detail-grid"><section>工艺路线</section><section>风险提示</section><section>物料需求与齐套快照</section><section>状态时间线</section></div>
</main></div></div></div></body></html>""",
                encoding="utf-8",
            )
            _inject_runtime_script_into_ai_page(page_path, module_keys=["inventory"])
            handler = partial(_RuntimeApiHandler, directory=str(root))
            server = create_safe_threading_http_server("127.0.0.1", handler)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                from playwright.sync_api import sync_playwright

                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(headless=True)
                    page = browser.new_page(viewport={"width": 1280, "height": 720})
                    page.goto(f"http://127.0.0.1:{server.server_port}/operation-detail.html", wait_until="networkidle")
                    page.wait_for_function("() => window.__runtimeApiReady === true || window.__runtimeApiError")
                    _auto_repair_page_text_layout(page, "admin")
                    runtime = page.evaluate(
                        """() => ({
                          sourceText: document.querySelector('.eyebrow')?.textContent || '',
                          detailBottom: document.querySelector('.detail-panel')?.getBoundingClientRect().bottom || 0,
                          gridBottom: document.querySelector('.detail-grid')?.getBoundingClientRect().bottom || 0
                        })"""
                    )
                    issues = _collect_page_text_layout_issues(page, include_overlaps=True)
                    browser.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

        self.assertIn("当前生产工单 · 来源 MPS-2026-W29 / V4.1", runtime["sourceText"])
        self.assertLessEqual(runtime["detailBottom"], 720)
        self.assertLessEqual(runtime["gridBottom"], 720)
        self.assertFalse(issues)

    def test_table_operation_result_resists_cross_screen_metric_flex_rules(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            page_path = root / "operation-comparison.html"
            page_path.write_text(
                """<!doctype html><html><head><style>
body{margin:0;width:1280px;height:720px;overflow:hidden}
.shared-app-main{height:654px;margin-top:66px;overflow:hidden}
.screen-root{height:100%;display:flex;flex-direction:column;gap:8px;padding:10px 14px 12px;overflow:hidden}
.condition-bar{height:110px;flex:0 0 110px;background:#fff}
.metric-strip{display:grid;grid-template-columns:repeat(4,1fr);border:1px solid #ddd}
.workspace{min-height:0;flex:1;display:grid;grid-template-columns:minmax(0,1fr) 252px;gap:8px;overflow:hidden}
.comparison-main{min-width:0;display:grid;grid-template-rows:minmax(205px,1fr) auto;gap:8px}
.trend-panel{min-height:205px;border:1px solid #ddd;overflow:hidden}
.table-panel{min-height:246px;padding:9px 10px;border:1px solid #ddd;overflow:hidden}
.table-panel table{width:100%;border-collapse:collapse;margin-top:7px}
.table-panel th,.table-panel td{padding:6px;border:1px solid #ddd;white-space:nowrap}
.execution-rail{min-height:495px;border:1px solid #ddd;overflow:hidden}
.metric-strip{flex:1}
</style></head><body data-page-kind="operation" data-module-key="inventory" data-renderer="admin" data-ai-frontend="true">
<div class="shared-app-main"><div class="screen-root"><section class="condition-bar">方案对比条件</section>
<section class="metric-strip"><div>最优可用产能</div><div>最小产能缺口</div><div>峰值资源负荷</div><div>预计按期交付</div></section>
<div class="workspace"><main class="comparison-main"><section class="trend-panel">供需与可用产能差异</section>
<section class="table-panel table-frame operation-result"><div class="panel-title"><b>方案结果证据</b><span>统一口径：件 / 日，停机损失已去重</span></div>
<table><thead><tr><th>方案</th><th>可用产能</th><th>产能缺口</th></tr></thead><tbody>
<tr><td>当前计划</td><td>11,510</td><td>-1,590</td></tr><tr><td>加开晚班</td><td>12,480</td><td>-620</td></tr><tr><td>停机压缩</td><td>12,060</td><td>-1,040</td></tr>
</tbody></table></section></main><aside class="execution-rail runtime-record-panel">执行状态与决策摘要</aside></div>
</div></div></body></html>""",
                encoding="utf-8",
            )
            _inject_runtime_script_into_ai_page(page_path, module_keys=["inventory"])
            handler = partial(_RuntimeApiHandler, directory=str(root))
            server = create_safe_threading_http_server("127.0.0.1", handler)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                from playwright.sync_api import sync_playwright

                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(headless=True)
                    page = browser.new_page(viewport={"width": 1280, "height": 720})
                    page.goto(f"http://127.0.0.1:{server.server_port}/operation-comparison.html", wait_until="networkidle")
                    page.wait_for_function("() => window.__runtimeApiReady === true || window.__runtimeApiError")
                    _auto_repair_page_text_layout(page, "admin")
                    runtime = page.evaluate(
                        """() => ({
                          metricHeight: document.querySelector('.metric-strip')?.getBoundingClientRect().height || 0,
                          workspaceBottom: document.querySelector('.workspace')?.getBoundingClientRect().bottom || 0,
                          tableBottom: document.querySelector('.table-panel')?.getBoundingClientRect().bottom || 0,
                          evidence: document.querySelector('.panel-title')?.textContent || ''
                        })"""
                    )
                    issues = _collect_page_text_layout_issues(page, include_overlaps=True)
                    browser.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

        self.assertLessEqual(runtime["metricHeight"], 86)
        self.assertLessEqual(runtime["workspaceBottom"], 720)
        self.assertLessEqual(runtime["tableBottom"], 720)
        self.assertIn("方案结果证据", runtime["evidence"])
        self.assertFalse(issues)

    def test_modal_overlay_keeps_full_canvas_and_does_not_conflict_with_background_tags(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            page_path = root / "operation-modal.html"
            page_path.write_text(
                """<!doctype html><html><head><style>
body{margin:0;width:1280px;height:720px;overflow:hidden}
.screen-root{position:relative;width:1280px;height:720px;overflow:hidden}
.tag{position:absolute;left:340px;top:298px;padding:2px 7px;background:#fce8dc}
.confirm-layer{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;background:rgba(7,25,41,.48);z-index:5}
.confirm-dialog{width:1120px;background:#fff;border:1px solid #83909b}
.confirm-head,.confirm-footer{padding:16px 20px}.confirm-footer{display:flex;justify-content:flex-end;gap:8px}
</style></head><body data-page-kind="operation" data-module-key="inventory" data-renderer="admin" data-ai-frontend="true">
<main class="screen-root"><span class="tag">优先级 P1</span>
<div class="confirm-layer" role="dialog" aria-modal="true" aria-label="确认评估产能改善建议">
<section class="confirm-dialog operation-result"><div class="confirm-head"><h2>确认评估产能改善建议</h2><p>此操作将更新建议状态并建立后续产能验证范围。</p></div>
<div class="confirm-footer"><button>取消</button><button>确认评估产能改善建议</button></div></section>
</div></main></body></html>""",
                encoding="utf-8",
            )
            _inject_runtime_script_into_ai_page(page_path, module_keys=["inventory"])
            handler = partial(_RuntimeApiHandler, directory=str(root))
            server = create_safe_threading_http_server("127.0.0.1", handler)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                from playwright.sync_api import sync_playwright

                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(headless=True)
                    page = browser.new_page(viewport={"width": 1280, "height": 720})
                    page.goto(f"http://127.0.0.1:{server.server_port}/operation-modal.html", wait_until="networkidle")
                    page.wait_for_function("() => window.__runtimeApiReady === true || window.__runtimeApiError")
                    _auto_repair_page_text_layout(page, "admin")
                    runtime = page.evaluate(
                        """() => {
                          const layer = document.querySelector('.confirm-layer');
                          const dialog = document.querySelector('.confirm-dialog');
                          const layerRect = layer.getBoundingClientRect();
                          const dialogRect = dialog.getBoundingClientRect();
                          return {
                            layerPosition: getComputedStyle(layer).position,
                            layerRect: [layerRect.left, layerRect.top, layerRect.right, layerRect.bottom],
                            dialogPosition: getComputedStyle(dialog).position,
                            dialogRect: [dialogRect.left, dialogRect.top, dialogRect.right, dialogRect.bottom],
                            dialogText: dialog.textContent || ''
                          };
                        }"""
                    )
                    issues = _collect_page_text_layout_issues(page, include_overlaps=True)
                    browser.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

        self.assertEqual(runtime["layerPosition"], "absolute")
        self.assertEqual(runtime["layerRect"], [0, 0, 1280, 720])
        self.assertEqual(runtime["dialogPosition"], "fixed")
        self.assertGreater(runtime["dialogRect"][2] - runtime["dialogRect"][0], 600)
        self.assertIn("确认评估产能改善建议", runtime["dialogText"])
        self.assertFalse(issues)

    def test_dashboard_uses_injected_module_keys_and_renders_runtime_data(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            page_path = root / "dashboard.html"
            page_path.write_text(
                """<!doctype html>
<html lang=\"zh-CN\"><body data-page-kind=\"dashboard\" data-module-key=\"\" data-renderer=\"admin\" data-ai-frontend=\"true\">
  <section class=\"runtime-record-panel\">
    <h2>延期风险与异常</h2>
    <div class=\"risk-summary\"><b>5</b><b>3</b><b>4</b><b>待处理</b></div>
  </section>
  <div class=\"map-pin\"></div>
</body></html>""",
                encoding="utf-8",
            )
            _inject_runtime_script_into_ai_page(page_path, module_keys=["inventory"])
            html = page_path.read_text(encoding="utf-8")
            self.assertIn('data-runtime-module-keys="inventory"', html)
            self.assertIn("soft-runtime-api-script:v14", html)
            self.assertNotIn("trunk_route_catalog", html)

            handler = partial(_RuntimeApiHandler, directory=str(root))
            server = create_safe_threading_http_server("127.0.0.1", handler)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                from playwright.sync_api import sync_playwright

                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(headless=True)
                    page = browser.new_page()
                    page.goto(f"http://127.0.0.1:{server.server_port}/dashboard.html", wait_until="networkidle")
                    page.wait_for_function("() => window.__runtimeApiReady === true || window.__runtimeApiError")
                    runtime = page.evaluate(
                        """() => ({
                          error: window.__runtimeApiError,
                          ready: window.__runtimeApiReady,
                          visible: window.__runtimeApiVisibleMatch,
                          fetches: window.__runtimeApiFetches,
                          floatingPanel: Boolean(document.querySelector('.runtime-generated-record')),
                          text: document.body.innerText
                        })"""
                    )
                    browser.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

        self.assertEqual(runtime["error"], "")
        self.assertTrue(runtime["ready"])
        self.assertTrue(runtime["visible"])
        self.assertFalse(runtime["floatingPanel"])
        self.assertTrue(any(item["ok"] and item["url"] == "/inventory/" for item in runtime["fetches"]))
        self.assertIn("INV-2026-001", runtime["text"])

    def test_page_spec_regions_bind_project_api_records_without_table_or_detail(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            page_path = root / "page-spec.html"
            page_path.write_text(
                """<!doctype html><html lang="zh-CN"><body data-page-kind="module" data-module-key="inventory" data-renderer="admin" data-ai-frontend="true">
<section class="page-region region-filter_bar"><div class="filter-bar"><label class="filter-control"><span>编号</span><input placeholder="请输入编号" /></label></div></section>
<section class="page-region region-metric_group"><div class="metric-grid"><article class="metric-card"><span>当前记录</span><strong>0</strong><small>等待加载</small></article></div></section>
<section class="page-region region-kanban"><div class="kanban-board"><section class="kanban-column"><article><strong>待处理</strong><span>等待加载</span></article></section></div></section>
<section class="page-region region-chart"><div class="chart-columns"><div class="chart-column"><span class="chart-value">0</span><i class="chart-bar"></i><small>本期</small></div></div></section>
</body></html>""",
                encoding="utf-8",
            )
            _inject_runtime_script_into_ai_page(page_path, module_keys=["inventory"])
            handler = partial(_RuntimeApiHandler, directory=str(root))
            server = create_safe_threading_http_server("127.0.0.1", handler)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                from playwright.sync_api import sync_playwright

                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(headless=True)
                    page = browser.new_page(viewport={"width": 1280, "height": 720})
                    page.goto(f"http://127.0.0.1:{server.server_port}/page-spec.html", wait_until="networkidle")
                    page.wait_for_function("() => window.__runtimeApiReady === true || window.__runtimeApiError")
                    runtime = page.evaluate(
                        """() => ({
                          error: window.__runtimeApiError,
                          ready: window.__runtimeApiReady,
                          visible: window.__runtimeApiVisibleMatch,
                          inputValue: document.querySelector('.filter-control input')?.value || '',
                          metricMeta: document.querySelector('.metric-card small')?.textContent || '',
                          kanbanText: document.querySelector('.kanban-column article')?.innerText || '',
                          chartLabel: document.querySelector('.chart-column small')?.textContent || ''
                        })"""
                    )
                    browser.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

        self.assertEqual(runtime["error"], "")
        self.assertTrue(runtime["ready"] and runtime["visible"])
        self.assertEqual(runtime["inputValue"], "INV-2026-001")
        self.assertIn("INV-2026-001", runtime["metricMeta"])
        self.assertIn("INV-2026-001", runtime["kanbanText"])
        self.assertIn("主粮仓库存记录", runtime["chartLabel"])

    def test_statistics_binds_plain_table_and_uses_inline_evidence(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            page_path = root / "statistics.html"
            page_path.write_text(
                """<!doctype html><html><head><style>
body{margin:0;width:1280px;height:720px;overflow:hidden}.stable-card{width:900px;margin:30px}.stable-card-h{height:36px;display:flex;align-items:center;gap:12px}.stable-table{width:100%;table-layout:fixed;border-collapse:collapse}.stable-table td,.stable-table th{height:28px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
</style></head><body data-page-kind="statistics" data-module-key="inventory" data-renderer="admin" data-ai-frontend="true">
<section class="stable-card table-frame"><div class="stable-card-h"><b>模块统计明细</b><span>最近更新</span></div>
<table class="stable-table"><thead><tr><th>编号</th><th>模块</th><th>状态</th><th>操作</th></tr></thead>
<tbody><tr><td>KS-2026-1001</td><td>库存统计</td><td><span class="tag">待复核</span></td><td><button>查看</button></td></tr></tbody></table></section>
</body></html>""",
                encoding="utf-8",
            )
            _inject_runtime_script_into_ai_page(page_path, module_keys=["inventory"])
            html = page_path.read_text(encoding="utf-8")
            self.assertIn("soft-runtime-api-script:v14", html)
            self.assertIn('class="runtime-operation-evidence"', html)
            self.assertNotIn("data-runtime-operation-evidence-style", html)

            handler = partial(_RuntimeApiHandler, directory=str(root))
            server = create_safe_threading_http_server("127.0.0.1", handler)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                from playwright.sync_api import sync_playwright

                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(headless=True)
                    page = browser.new_page(viewport={"width": 1280, "height": 720})
                    page.goto(f"http://127.0.0.1:{server.server_port}/statistics.html", wait_until="networkidle")
                    page.wait_for_function("() => window.__runtimeApiReady === true || window.__runtimeApiError")
                    _auto_repair_page_text_layout(page, "admin")
                    runtime = page.evaluate(
                        """() => ({
                          error: window.__runtimeApiError,
                          ready: window.__runtimeApiReady,
                          visible: window.__runtimeApiVisibleMatch,
                          firstCode: document.querySelector('tbody td')?.textContent || '',
                          floatingPanel: Boolean(document.querySelector('.runtime-generated-record')),
                          evidenceText: document.querySelector('.runtime-operation-evidence')?.textContent || ''
                        })"""
                    )
                    issues = _collect_page_text_layout_issues(page, include_overlaps=True)
                    browser.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

        self.assertEqual(runtime["error"], "")
        self.assertTrue(runtime["ready"] and runtime["visible"])
        self.assertEqual(runtime["firstCode"], "INV-2026-001")
        self.assertFalse(runtime["floatingPanel"])
        self.assertIn("状态与更新时间已同步保存", runtime["evidenceText"])
        self.assertFalse(issues)

    def test_layout_repair_moves_overlapping_absolute_controls(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            page_path = root / "overlap.html"
            page_path.write_text(
                """<!doctype html><html><head><style>
body{margin:0;width:1280px;height:720px;overflow:hidden}
button{position:absolute;left:40px;top:40px;width:180px;height:28px}
.second{top:42px}
</style></head><body data-renderer="admin">
<button>查询运行记录</button><button class="second">导出运行记录</button>
</body></html>""",
                encoding="utf-8",
            )
            from playwright.sync_api import sync_playwright

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1280, "height": 720})
                page.goto(page_path.as_uri(), wait_until="load")
                before = _collect_page_text_layout_issues(page, include_overlaps=True)
                _auto_repair_page_text_layout(page, "admin")
                after = _collect_page_text_layout_issues(page, include_overlaps=True)
                browser.close()

        self.assertTrue(any(issue.get("kind") == "overlap" for issue in before))
        self.assertFalse(after)

    def test_layout_repair_hides_empty_visual_bar_occluding_text(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            page_path = root / "occlusion.html"
            page_path.write_text(
                """<!doctype html><html><head><style>
body{margin:0;width:1280px;height:720px;overflow:hidden}.lane{position:relative;width:180px;height:110px;margin:30px;background:#0b1d37;color:#fff}.lane small{position:absolute;left:10px;bottom:10px;font-size:14px}.stack{position:absolute;left:8px;bottom:8px;width:110px;height:38px;background:linear-gradient(#f59e0b,#2563eb)}
</style></head><body data-renderer="admin"><div class="lane"><small>主控项缺少影像</small><span class="stack"></span></div></body></html>""",
                encoding="utf-8",
            )
            from playwright.sync_api import sync_playwright

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1280, "height": 720})
                page.goto(page_path.as_uri(), wait_until="load")
                before = _collect_page_text_layout_issues(page, include_overlaps=True)
                _auto_repair_page_text_layout(page, "admin")
                after = _collect_page_text_layout_issues(page, include_overlaps=True)
                visibility = page.locator(".stack").evaluate("node => getComputedStyle(node).visibility")
                browser.close()

        self.assertTrue(any(issue.get("kind") == "occlusion" for issue in before))
        self.assertEqual(visibility, "hidden")
        self.assertFalse(after)

    def test_layout_repair_scales_fixed_canvas_without_expanding_it_again(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            page_path = root / "outside.html"
            page_path.write_text(
                """<!doctype html><html><head><style>
body{margin:0;width:1280px;height:720px;overflow:hidden}.screen-root{position:relative;width:1286px;height:720px}
.operation-result{position:absolute;left:989px;top:314px;width:297px;height:220px;overflow:hidden}
</style></head><body data-renderer="admin">
<div class="screen-root"><div class="operation-result">纠偏成效评估与运行结果</div></div>
</body></html>""",
                encoding="utf-8",
            )
            from playwright.sync_api import sync_playwright

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1280, "height": 720})
                page.goto(page_path.as_uri(), wait_until="load")
                before = _collect_page_text_layout_issues(page, include_overlaps=True)
                _auto_repair_page_text_layout(page, "admin")
                after = _collect_page_text_layout_issues(page, include_overlaps=True)
                canvas = page.locator(".screen-root").evaluate(
                    "node => ({width: node.style.width, scale: node.dataset.viewportFitScale || ''})"
                )
                browser.close()

        self.assertTrue(any(issue.get("kind") == "outsideViewport" for issue in before))
        self.assertFalse(after)
        self.assertEqual(canvas["width"], "")
        self.assertTrue(canvas["scale"])

    def test_layout_gate_ignores_text_clipped_by_inner_overflow_container(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            page_path = root / "clipped.html"
            page_path.write_text(
                """<!doctype html><html><head><style>
body{margin:0;width:1280px;height:720px;overflow:hidden}.viewport{position:absolute;left:20px;top:650px;width:600px;height:50px;overflow:hidden}.row{position:absolute;left:0;top:30px;width:600px;height:40px}.row td{width:200px;height:40px;white-space:nowrap}
</style></head><body data-renderer="admin"><div class="viewport"><table class="row"><tr><td>已被内部滚动区域裁剪的下一行</td><td>待复核</td></tr></table></div></body></html>""",
                encoding="utf-8",
            )
            from playwright.sync_api import sync_playwright

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1280, "height": 720})
                page.goto(page_path.as_uri(), wait_until="load")
                issues = _collect_page_text_layout_issues(page, include_overlaps=True)
                browser.close()

        self.assertFalse(issues)


if __name__ == "__main__":
    unittest.main()
