import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from backend.softcopyright.frontend_codegen.page_composition import (
    PAGE_COMPOSITION_VERSION,
    build_page_composition_contract,
)
from backend.softcopyright.frontend_codegen.page_spec_renderer import render_page_spec
from backend.softcopyright.ui_similarity import evaluate_ui_similarity_gate, page_composition_summary
from backend.softcopyright.screenshots import _collect_page_text_layout_issues


def _spec(*, layout="table_workspace", page_kind="module", components=None):
    components = components or ["filter_bar", "metric_group", "data_table", "detail"]
    return {
        "schema_version": "page-spec-v1",
        "page_key": "records",
        "page_kind": page_kind,
        "layout": layout,
        "theme": {"density": "comfortable", "accent_variant": "primary"},
        "regions": [
            {"id": f"region_{index}", "component": component, "title": component}
            for index, component in enumerate(components, start=1)
        ],
        "actions": [],
        "interaction_contract": {"mode": "browse"},
    }


class PageCompositionContractTests(unittest.TestCase):
    def test_contract_is_deterministic_and_uses_multiple_desktop_compositions(self):
        spec = _spec()
        first = build_page_composition_contract(spec, renderer="admin", creative_key="stable-key")
        second = build_page_composition_contract(spec, renderer="admin", creative_key="stable-key")
        variants = {
            build_page_composition_contract(spec, renderer="admin", creative_key=f"page-{index}")["variant"]
            for index in range(80)
        }

        self.assertEqual(first, second)
        self.assertEqual(first["version"], PAGE_COMPOSITION_VERSION)
        self.assertGreaterEqual(len(variants), 5)

    def test_desktop_variants_assign_real_main_and_rail_slots(self):
        spec = _spec(components=["data_table", "detail", "workflow"])
        contracts = [
            build_page_composition_contract(spec, renderer="admin", creative_key=f"layout-{index}")
            for index in range(100)
        ]
        left = next(item for item in contracts if item["variant"] == "asymmetric-left")
        right = next(item for item in contracts if item["variant"] == "asymmetric-right")

        self.assertEqual(left["region_slots"][0]["slot"], "stage-left")
        self.assertEqual(right["region_slots"][0]["slot"], "stage-right")
        self.assertNotEqual(left["signature"], right["signature"])

    def test_chart_and_table_use_separate_full_width_rows(self):
        spec = _spec(components=["filter_bar", "metric_group", "chart", "data_table", "detail"])
        contract = build_page_composition_contract(spec, renderer="admin", creative_key="submission-tracking")
        slots = {item["component"]: item["slot"] for item in contract["region_slots"]}

        self.assertEqual(slots["chart"], "full-band")
        self.assertEqual(slots["data_table"], "full-band")

    def test_tall_chart_grid_row_does_not_overlap_the_following_table(self):
        rendered = render_page_spec(
            _spec(components=["filter_bar", "metric_group", "chart", "data_table", "detail"]),
            css_scope="screen-layout-regression",
            creative_key="chart-table-overlap",
            renderer="admin",
            module={},
            screen={"title": "作业收交跟踪"},
            visual_identity={},
            color_contract={},
        )
        javascript = """
const fs=require('fs'), esbuild=require('esbuild'), React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const jsx=JSON.parse(fs.readFileSync(0,'utf8'));
const code=esbuild.transformSync('module.exports = ('+jsx+')',{loader:'jsx',format:'cjs'}).code;
const result={exports:{}}; new Function('module','React',code)(result,React);
process.stdout.write(renderToStaticMarkup(result.exports));
"""
        from tests.test_dashboard_runtime_api import PROJECT_ROOT

        html_body = subprocess.run(
            ["node", "-e", javascript],
            input=json.dumps(rendered["jsx"], ensure_ascii=False),
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=PROJECT_ROOT,
            check=True,
        ).stdout
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            page.set_content(
                '<html><head><meta charset="utf-8"><style>body{margin:0;width:1280px;height:720px;}'
                + rendered["css"]
                + '</style></head><body data-renderer="admin" data-ai-frontend="true" '
                'data-page-kind="module">'
                + html_body
                + "</body></html>"
            )
            geometry = page.evaluate(
                """() => {
                  const chart=document.querySelector('.region-chart').getBoundingClientRect();
                  const table=document.querySelector('.region-data_table').getBoundingClientRect();
                  const heading=document.querySelector('.region-data_table h2').getBoundingClientRect();
                  return {gridAutoRows:getComputedStyle(document.querySelector('.page-spec-workspace')).gridAutoRows,
                    chartBottom:chart.bottom,tableTop:table.top,headingTop:heading.top};
                }"""
            )
            self.assertEqual(geometry["gridAutoRows"], "max-content")
            self.assertLessEqual(geometry["chartBottom"], geometry["tableTop"])
            self.assertFalse(_collect_page_text_layout_issues(page, include_overlaps=True))
            browser.close()

    def test_mobile_action_composition_prioritizes_form_and_result(self):
        spec = _spec(
            layout="mobile_feed",
            page_kind="operation",
            components=["metric_group", "mobile_list", "form", "operation_result"],
        )
        spec["interaction_contract"] = {"mode": "workflow"}
        contracts = [
            build_page_composition_contract(spec, renderer="mobile_app", creative_key=f"mobile-{index}")
            for index in range(60)
        ]
        action = next(item for item in contracts if item["variant"] == "mobile-action-focus")
        orders = {slot["component"]: slot["order"] for slot in action["region_slots"]}

        self.assertLess(orders["form"], orders["metric_group"])
        self.assertLess(orders["operation_result"], orders["mobile_list"])

    def test_renderer_emits_contract_attributes_slots_and_composition_css(self):
        rendered = render_page_spec(
            _spec(),
            css_scope="screen-records",
            creative_key="render-key",
            renderer="admin",
            module={},
            screen={"title": "业务台账"},
            visual_identity={},
            color_contract={},
        )

        self.assertIn('data-page-composition-version="page-composition-v2"', rendered["jsx"])
        self.assertIn("data-composition-signature=", rendered["jsx"])
        self.assertIn("data-composition-slot=", rendered["jsx"])
        self.assertNotIn("style=", rendered["jsx"])
        self.assertIn("composition-slot-stage-left", rendered["css"])
        self.assertEqual(rendered["composition_contract"]["version"], PAGE_COMPOSITION_VERSION)

    def test_summary_reports_diverse_contracts_and_duplicate_groups(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            screens_dir = root / "react-app" / "src" / "screens"
            screens_dir.mkdir(parents=True)
            screenshots = {}
            for index in range(6):
                key = f"page_{index}"
                html_path = root / f"{key}.html"
                html_path.write_text(
                    f'<meta name="soft-react-screen" content="{key}">',
                    encoding="utf-8",
                )
                signature = f"signature-{index}" if index < 5 else "signature-4"
                (screens_dir / f"Page{index}.meta.json").write_text(
                    json.dumps(
                        {
                            "page_key": key,
                            "composition_contract": {
                                "version": PAGE_COMPOSITION_VERSION,
                                "family": "records" if index < 3 else "workflow",
                                "variant": ("balanced-grid", "detail-rail", "workflow-focus")[index % 3],
                                "signature": signature,
                            },
                        }
                    ),
                    encoding="utf-8",
                )
                screenshots[key] = SimpleNamespace(key=key, html_path=str(html_path), page_kind="module")

            summary = page_composition_summary(screenshots)

        self.assertTrue(summary["ui_page_composition_ready"])
        self.assertEqual(summary["ui_page_composition_count"], 6)
        self.assertEqual(summary["ui_page_composition_signature_count"], 5)
        self.assertEqual(summary["ui_page_composition_family_count"], 2)
        self.assertEqual(summary["ui_page_composition_duplicate_groups"], [["page_4", "page_5"]])

    def test_formal_gate_rejects_one_composition_but_local_template_only_records_it(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            screens_dir = root / "react-app" / "src" / "screens"
            screens_dir.mkdir(parents=True)
            screenshots = {}
            for index in range(6):
                key = f"duplicate_{index}"
                html_path = root / f"{key}.html"
                html_path.write_text(f'<meta name="soft-react-screen" content="{key}">', encoding="utf-8")
                (screens_dir / f"Duplicate{index}.meta.json").write_text(
                    json.dumps(
                        {
                            "page_key": key,
                            "composition_contract": {
                                "version": PAGE_COMPOSITION_VERSION,
                                "family": "records",
                                "variant": "balanced-grid",
                                "signature": "same-signature",
                            },
                        }
                    ),
                    encoding="utf-8",
                )
                screenshots[key] = SimpleNamespace(key=key, html_path=str(html_path), page_kind="module")
            ui_blueprint = SimpleNamespace(
                renderer="admin",
                source="llm",
                design_brief={"product_type": "管理软件", "experience_shape": "admin"},
                screens=[
                    SimpleNamespace(view_type=f"module_role_{index}", module_key=f"module_{index}", components=[])
                    for index in range(4)
                ],
            )
            formal = evaluate_ui_similarity_gate(
                task=SimpleNamespace(model_provider="gpt", task_id="formal", software_name="正式软件"),
                ui_blueprint=ui_blueprint,
                ui_screenshots=screenshots,
                output_root=root,
                attempt=0,
            )
            local = evaluate_ui_similarity_gate(
                task=SimpleNamespace(model_provider="local-template", task_id="local", software_name="本地软件"),
                ui_blueprint=ui_blueprint,
                ui_screenshots=screenshots,
                output_root=root,
                attempt=0,
            )

        self.assertFalse(formal.ready)
        self.assertEqual(formal.reason, "ui_page_composition_diversity_low")
        self.assertFalse(formal.composition_summary["ui_page_composition_ready"])
        self.assertTrue(local.ready)
        self.assertFalse(local.composition_summary["ui_page_composition_ready"])


if __name__ == "__main__":
    unittest.main()
