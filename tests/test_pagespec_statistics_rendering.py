import json
from functools import partial
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from threading import Thread
import unittest

from backend.softcopyright.frontend_codegen.page_spec import normalize_page_spec
from backend.softcopyright.frontend_codegen.page_spec_renderer import render_page_spec
from backend.softcopyright.screenshots import _collect_page_text_layout_issues, _inject_runtime_script_into_ai_page
from tests.http_test_utils import create_safe_threading_http_server
from tests.test_dashboard_runtime_api import PROJECT_ROOT, _RuntimeApiHandler


def statistics_spec():
    return {
        "schema_version": "page-spec-v1", "page_key": "statistics", "page_kind": "statistics",
        "layout": "chart_analysis", "theme": {}, "actions": [], "interaction_contract": {"mode": "browse"},
        "regions": [
            {"id": "scope", "component": "filter_bar", "fields": [{"label": f"条件{i}", "value": str(i)} for i in range(6)]},
            {"id": "metrics", "component": "metric_group", "metrics": [
                {"label": "按时提交率", "value": "90.0%", "description": "按时提交36人／应交40人"},
                {"label": "成绩发布覆盖率", "value": "90.0%"},
                {"label": "待订正数", "value": 0},
            ]},
            {"id": "trend", "component": "chart", "title": "统计趋势", "series": [
                {"name": "净变化", "points": [{"label": "第一周", "value": 0}, {"label": "第二周", "value": 25},
                                               {"label": "第三周", "value": 50}, {"label": "第四周", "value": -25}]},
            ]},
            {"id": "legacy", "component": "chart", "title": "历史趋势", "series": [
                {"name": "提交率", "points": "第一周 / 82.5、第二周 / 90、第三周"},
            ]},
            {"id": "table", "component": "data_table", "columns": [
                {"key": "knowledge", "label": "知识点"}, {"key": "score", "label": "得分率"},
            ], "items": [{"knowledge": "去括号与符号变换", "score": "66.7%"}]},
        ],
    }


class PageSpecStatisticsTests(unittest.TestCase):
    def test_normalization_preserves_points_zero_and_explicit_column_keys(self):
        spec = normalize_page_spec(statistics_spec(), expected_page_key="statistics", expected_page_kind="statistics")
        self.assertEqual(spec["regions"][2]["series"][0]["points"][0], {"label": "第一周", "value": "0"})
        self.assertEqual(spec["regions"][4]["column_keys"], {"知识点": "knowledge", "得分率": "score"})
        self.assertEqual(spec["regions"][1]["metrics"][2]["value"], "0")

    def test_invalid_chart_values_are_not_replaced_with_invented_numbers(self):
        spec = statistics_spec()
        spec["regions"] = [{"component": "chart", "series": [{"label": "坏值", "value": value} for value in (None, "NaN", "inf", True)]}]
        rendered = render_page_spec(spec, css_scope="statistics-test", creative_key="invalid", renderer="admin",
                                    module={}, screen={}, visual_identity={}, color_contract={})
        self.assertIn("暂无有效数值", rendered["jsx"])
        self.assertNotIn("data-chart-value=", rendered["jsx"])

    def test_statistics_retains_business_data_and_scrolls_without_occlusion_after_api_binding(self):
        spec = normalize_page_spec(statistics_spec(), expected_page_key="statistics", expected_page_kind="statistics")
        rendered = render_page_spec(spec, css_scope="statistics-test", creative_key="education", renderer="admin",
                                    module={}, screen={"title": "学情分析"}, visual_identity={}, color_contract={})
        # Compile the real renderer output through React, including JSX style objects.
        javascript = """
const fs=require('fs'), esbuild=require('esbuild'), React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const jsx=JSON.parse(fs.readFileSync(0,'utf8'));
const code=esbuild.transformSync('module.exports = ('+jsx+')',{loader:'jsx',format:'cjs'}).code;
const result={exports:{}}; new Function('module','React',code)(result,React);
process.stdout.write(renderToStaticMarkup(result.exports));
"""
        html_body = subprocess.run(["node", "-e", javascript], input=json.dumps(rendered["jsx"]),
                                   capture_output=True, text=True, encoding="utf-8", cwd=PROJECT_ROOT, check=True).stdout
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            path = root / "statistics.html"
            path.write_text('<html><head><meta charset="utf-8"><style>body{margin:0;width:1280px;height:720px;}'
                            + rendered["css"] + '</style></head><body data-renderer="admin" data-ai-frontend="true" '
                            'data-page-kind="statistics" data-module-key="inventory">' + html_body + '</body></html>', encoding="utf-8")
            _inject_runtime_script_into_ai_page(path, module_keys=["inventory"])
            server = create_safe_threading_http_server("127.0.0.1", partial(_RuntimeApiHandler, directory=str(root)))
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                from playwright.sync_api import sync_playwright
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(headless=True)
                    page = browser.new_page(viewport={"width": 1280, "height": 720})
                    page.goto(f"http://127.0.0.1:{server.server_port}/statistics.html", wait_until="networkidle")
                    page.wait_for_function("() => window.__runtimeApiReady || window.__runtimeApiError")
                    self.assertEqual(page.evaluate("window.__runtimeApiError"), "")
                    self.assertTrue(page.evaluate("window.__runtimeApiVisibleMatch"))
                    self.assertEqual(page.locator('.metric-card strong').all_text_contents(), ["90.0%", "90.0%", "0"])
                    self.assertIn("按时提交36人／应交40人", page.locator('.metric-card small').inner_text())
                    self.assertEqual(page.locator('tbody td').all_text_contents(), ["去括号与符号变换", "66.7%"])
                    self.assertEqual(page.locator('.filter-control').count(), 6)
                    self.assertIn("历史数据不完整", page.locator('.chart-series p').inner_text())
                    self.assertEqual(page.locator('.chart-bar').evaluate_all("nodes=>nodes.map(n=>Number(n.dataset.chartValue))"), [0, 25, 50, -25, 82.5, 90])
                    self.assertIn("第一周", page.locator('.chart-column small').first.inner_text())
                    geometry = page.locator('.region-metric_group').evaluate("""n => ({bottom:n.getBoundingClientRect().bottom,
                      cards:Array.from(n.querySelectorAll('.metric-card')).map(c=>c.getBoundingClientRect().bottom)})""")
                    self.assertLessEqual(max(geometry["cards"]), geometry["bottom"])
                    self.assertFalse(_collect_page_text_layout_issues(page, include_overlaps=True), page.locator('.page-region,.chart-panel').evaluate_all('nodes=>nodes.map(n=>({class:n.className,rect:n.getBoundingClientRect().toJSON(),height:getComputedStyle(n).minHeight,scroll:n.scrollHeight}))'))
                    page.locator('tbody td').first.scroll_into_view_if_needed()
                    self.assertFalse(_collect_page_text_layout_issues(page, include_overlaps=True))
                    heights = page.locator('.chart-bar').evaluate_all('nodes=>nodes.slice(0,4).map(n=>n.getBoundingClientRect().height)')
                    self.assertEqual(heights[0], 0)
                    self.assertAlmostEqual(heights[2] / heights[1], 2, places=1)
                    self.assertAlmostEqual(heights[3], heights[1], places=1)
                    browser.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
