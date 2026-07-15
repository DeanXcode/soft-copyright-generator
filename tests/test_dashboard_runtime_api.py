import json
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest

from backend.softcopyright.generator import _ui_screenshot_realism_checks, _visible_html_text
from backend.softcopyright.screenshots import (
    _auto_repair_page_text_layout,
    _collect_page_text_layout_issues,
    _inject_runtime_script_into_ai_page,
)


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
    def test_injection_upgrades_cached_runtime_script(self):
        with TemporaryDirectory() as temporary_directory:
            page_path = Path(temporary_directory) / "dashboard.html"
            page_path.write_text(
                """<!doctype html><html><head>
<style id=\"soft-ai-runtime-guard\">body{width:1280px;min-height:820px;overflow:hidden;}</style>
</head><body data-page-kind=\"dashboard\" data-module-key=\"\" data-renderer=\"admin\">
<!-- soft-runtime-api-script:v4 -->
<script>(function () { window.__runtimeApiReady = false; })();</script>
</body></html>""",
                encoding="utf-8",
            )
            _inject_runtime_script_into_ai_page(page_path, module_keys=["inventory"])
            html = page_path.read_text(encoding="utf-8")

        self.assertIn('data-runtime-module-keys="inventory"', html)
        self.assertNotIn("soft-runtime-api-script:v4", html)
        self.assertEqual(html.count("soft-runtime-api-script:v10"), 1)
        self.assertIn("height:720px!important", html)
        self.assertIn("table-layout:fixed!important", html)
        self.assertIn("white-space:nowrap!important", html)
        self.assertNotIn("min-height:820px", html)
        visible = _visible_html_text(html)
        self.assertIn("处理结果", visible)
        self.assertIn("操作日志", visible)
        self.assertIn("刷新统计口径", visible)
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
        self.assertIn("操作日志", visible)
        self.assertIn("刷新统计口径", visible)
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
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
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
        self.assertIn("操作日志", runtime["evidence"])
        self.assertNotEqual(runtime["resultMaxHeight"], "42px")
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
            self.assertIn("soft-runtime-api-script:v10", html)
            self.assertNotIn("trunk_route_catalog", html)

            handler = partial(_RuntimeApiHandler, directory=str(root))
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
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
            self.assertIn("soft-runtime-api-script:v10", html)
            self.assertIn('class="runtime-operation-evidence"', html)
            self.assertNotIn("data-runtime-operation-evidence-style", html)

            handler = partial(_RuntimeApiHandler, directory=str(root))
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
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
        self.assertIn("操作日志", runtime["evidenceText"])
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


if __name__ == "__main__":
    unittest.main()
