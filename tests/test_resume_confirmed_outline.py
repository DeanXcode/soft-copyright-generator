import json
from pathlib import Path
import sys
import tempfile
import unittest

BACKEND_ROOT = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from generate_materials import _confirmed_outline_from_resume_dir, _seed_from_output_dir
from softcopyright.generator import (
    _begin_generation_attempt,
    _delivery_zip_path,
    _invalidate_legacy_frontend_cache_for_pagespec,
    _load_completed_resume_report,
    _load_resume_ui_blueprint_from_prototype_manifest,
    _resume_failure_payload,
    _resume_failure_progress,
    _resume_failure_progress_from_payload,
    _resume_failure_stage,
    _resume_blueprint_lock_ready,
    _should_defer_pre_render_similarity_for_resume,
    _stage_precedes,
    _write_generation_failure,
    _write_generation_state,
)
from softcopyright.models import GenerationTask
from softcopyright.blueprint import FeatureModule, ProductBlueprint
from softcopyright.packager import write_json
from softcopyright.frontend_codegen.page_spec import FRONTEND_ENGINE_VERSION


class ResumeConfirmedOutlineTests(unittest.TestCase):
    def test_generation_state_persists_confirmed_outline_before_blueprint_exists(self):
        outline = {
            "softwareName": "Figma浏览器",
            "productType": "APP",
            "domain": "Figma设计文件浏览与预览",
            "modules": [{"title": "设计资源导航", "description": "浏览团队、项目和设计文件资源。"}],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "early-blueprint-failure"
            task = GenerationTask(
                software_name="Figma浏览器",
                product_type="APP",
                feature_hint="设计文件、页面画板和图层组件",
                confirmed_outline=outline,
            )

            _write_generation_state(output_dir, task, "running", "blueprint", 21, "生成产品蓝图", {})
            state = json.loads((output_dir / "generation-state.json").read_text(encoding="utf-8"))

        self.assertEqual(state["task"]["confirmed_outline"], outline)
        self.assertEqual(state["task"]["feature_hint"], task.feature_hint)

    def test_late_resume_recovers_visual_identity_from_published_frontend(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "resume-identity"
            prototype_dir = output_dir / "generated_source" / "ui-prototype"
            frontend_src = output_dir / "generated_source" / "frontend-app" / "src"
            prototype_dir.mkdir(parents=True)
            frontend_src.mkdir(parents=True)
            module = FeatureModule("access", "门禁管理", "维护门禁记录。", ["AccessRecord"])
            blueprint = ProductBlueprint(
                software_name="门禁系统",
                version="V1.0",
                language="JavaScript",
                product_type="应用软件",
                industry="社区门禁",
                purpose="门禁管理",
                summary="门禁管理",
                modules=[module],
                roles=["管理员"],
                pages=["系统首页"],
                dev_environment={},
                runtime_environment={},
            )
            pages = [
                {"key": "login", "title": "登录", "caption": "登录", "file": "login.html"},
                {"key": "dashboard", "title": "系统首页", "caption": "首页", "file": "dashboard.html"},
                {"key": "access", "title": "门禁管理", "caption": "门禁", "file": "access.html"},
                {"key": "statistics", "title": "统计报表", "caption": "统计", "file": "statistics.html"},
            ]
            write_json(
                prototype_dir / "prototype-manifest.json",
                {
                    "renderer": "admin",
                    "source": "llm",
                    "visual_style": "石墨绿门禁工作台",
                    "product_experience_spec": {"experience_shape": "desktop_web", "terminal": "desktop_browser"},
                    "pages": pages,
                },
            )
            (frontend_src / "App.jsx").write_text(
                'const shellConfig = {\n'
                '  "nav_model": "rail",\n'
                '  "layout_variant": "kanban",\n'
                '  "workspace_shape": "triage_console",\n'
                '  "identity_signature": "identity-from-built-app",\n'
                '  "palette": {"accent": "#65a30d", "sidebar": "#25330b"}\n'
                '};\n\nexport default function App() { return null; }\n',
                encoding="utf-8",
            )

            recovered = _load_resume_ui_blueprint_from_prototype_manifest(output_dir, blueprint)

        self.assertIsNotNone(recovered)
        identity = recovered.design_brief["visual_identity_spec"]
        self.assertEqual(identity["identity_signature"], "identity-from-built-app")
        self.assertEqual(identity["nav_model"], "rail")
        self.assertEqual(recovered.design_brief["layout_variant"], "kanban")

    def test_late_resume_recovers_visual_identity_from_published_static_pages(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "resume-static-identity"
            prototype_dir = output_dir / "generated_source" / "ui-prototype"
            prototype_dir.mkdir(parents=True)
            module = FeatureModule("records", "档案管理", "维护档案记录。", ["Record"])
            blueprint = ProductBlueprint(
                software_name="档案系统",
                version="V1.0",
                language="Python",
                product_type="应用软件",
                industry="企业服务",
                purpose="档案管理",
                summary="档案管理",
                modules=[module],
                roles=["管理员"],
                pages=["系统首页"],
                dev_environment={},
                runtime_environment={},
            )
            pages = [
                {"key": "login", "title": "登录", "caption": "登录", "file": "login.html"},
                {"key": "dashboard", "title": "系统首页", "caption": "首页", "file": "dashboard.html"},
                {"key": "records", "title": "档案管理", "caption": "档案", "file": "records.html"},
                {"key": "statistics", "title": "统计报表", "caption": "统计", "file": "statistics.html"},
            ]
            write_json(
                prototype_dir / "prototype-manifest.json",
                {
                    "renderer": "admin",
                    "source": "local-template",
                    "visual_style": "蓝灰档案工作台",
                    "experience_shape": "desktop_web",
                    "pages": pages,
                },
            )
            for page in pages:
                (prototype_dir / page["file"]).write_text(
                    f"<html><body data-page='{page['key']}'>{page['title']}</body></html>",
                    encoding="utf-8",
                )

            recovered = _load_resume_ui_blueprint_from_prototype_manifest(output_dir, blueprint)

        self.assertIsNotNone(recovered)
        identity = recovered.design_brief["visual_identity_spec"]
        self.assertTrue(identity["identity_signature"].startswith("static-"))
        self.assertEqual(identity["palette_key"], "published-static")
        self.assertEqual(recovered.design_brief["layout_variant"], "published-static")

    def test_generation_state_v2_and_failure_share_one_attempt(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "state-v2"
            task = GenerationTask(software_name="状态恢复测试系统", product_type="APP", seed="state-v2")

            _begin_generation_attempt(output_dir, task, resume_source="new-task")
            state = json.loads((output_dir / "generation-state.json").read_text(encoding="utf-8"))
            _write_generation_failure(
                output_dir,
                task,
                stage="screenshots",
                progress=58,
                message="模拟界面生成中断",
            )
            failure = json.loads((output_dir / "generation-failure.json").read_text(encoding="utf-8"))
            final_state = json.loads((output_dir / "generation-state.json").read_text(encoding="utf-8"))

        self.assertEqual(state["schema_version"], 2)
        self.assertTrue(state["attempt_id"])
        self.assertTrue(state["started_at"])
        self.assertTrue(state["updated_at"])
        self.assertEqual(state["resume_source"], "new-task")
        self.assertEqual(failure["attempt_id"], state["attempt_id"])
        self.assertEqual(final_state["attempt_id"], state["attempt_id"])
        self.assertEqual(final_state["status"], "error")

    def test_new_attempt_archives_previous_failure_and_isolates_resume_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "attempt-isolation"
            output_dir.mkdir()
            write_json(
                output_dir / "generation-failure.json",
                {"schema_version": 2, "attempt_id": "old-attempt", "status": "error", "stage": "screenshots", "progress": 52},
            )
            task = GenerationTask(software_name="尝试隔离测试系统", product_type="APP", seed="attempt-isolation")

            _begin_generation_attempt(output_dir, task, resume_source="failure-state")
            state = json.loads((output_dir / "generation-state.json").read_text(encoding="utf-8"))
            history = list((output_dir / "attempt-history").glob("generation-failure-old-attempt-*.json"))
            failure_exists = (output_dir / "generation-failure.json").exists()

        self.assertNotEqual(state["attempt_id"], "old-attempt")
        self.assertEqual(state["resume_source"], "failure-state")
        self.assertEqual(len(history), 1)
        self.assertFalse(failure_exists)

    def test_late_resume_attempt_starts_at_failed_stage_instead_of_prepare(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "late-stage-resume"
            output_dir.mkdir()
            write_json(
                output_dir / "generation-failure.json",
                {"schema_version": 2, "attempt_id": "old-attempt", "status": "error", "stage": "validate", "progress": 99},
            )
            task = GenerationTask(software_name="晚阶段恢复测试系统", product_type="APP", seed="late-stage-resume")
            task.resume_stage = "validate"
            task.resume_progress = 99

            _begin_generation_attempt(output_dir, task, resume_source="failure-state")
            state = json.loads((output_dir / "generation-state.json").read_text(encoding="utf-8"))

        self.assertEqual(state["stage"], "validate")
        self.assertEqual(state["progress"], 99)
        self.assertIn("材料校验", state["message"])

    def test_stale_failure_file_does_not_override_latest_attempt(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "stale-failure"
            output_dir.mkdir()
            write_json(
                output_dir / "generation-state.json",
                {"schema_version": 2, "attempt_id": "latest", "status": "running", "stage": "manual", "progress": 72},
            )
            write_json(
                output_dir / "generation-failure.json",
                {"schema_version": 2, "attempt_id": "old", "status": "error", "stage": "screenshots", "progress": 50},
            )

            payload = _resume_failure_payload(output_dir)

        self.assertEqual(payload["attempt_id"], "latest")
        self.assertEqual(payload["stage"], "manual")
        self.assertEqual(_resume_failure_progress_from_payload(payload), 72)

    def test_atomic_json_write_leaves_no_partial_temp_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "generation-state.json"
            for index in range(10):
                write_json(path, {"schema_version": 2, "attempt_id": f"attempt-{index}", "value": "界面状态" * 200})

            payload = json.loads(path.read_text(encoding="utf-8"))
            leftovers = list(path.parent.glob(f".{path.name}.*.tmp"))

        self.assertEqual(payload["attempt_id"], "attempt-9")
        self.assertEqual(leftovers, [])

    def test_pagespec_upgrade_invalidates_only_legacy_page_and_screenshot_caches(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            source_dir = output_dir / "generated_source"
            screens_dir = source_dir / "ui-prototype" / "react-app" / "src" / "screens"
            screens_dir.mkdir(parents=True)
            for name in ("ScreenA.jsx", "ScreenA.css", "ScreenA.meta.json"):
                (screens_dir / name).write_text("legacy", encoding="utf-8")
            blueprint_path = source_dir / "product-blueprint.json"
            blueprint_path.write_text('{"modules":[]}', encoding="utf-8")
            reference_path = source_dir / "ui-prototype" / "visual-references" / "style_reference.png"
            reference_path.parent.mkdir(parents=True)
            reference_path.write_bytes(b"image2")
            ui_dir = output_dir / "ui_screenshots"
            ui_dir.mkdir()
            (ui_dir / "screen.png").write_bytes(b"old-shot")
            (ui_dir / "ui_blueprint.json").write_text("{}", encoding="utf-8")
            (ui_dir / "screenshot-checkpoint.json").write_text("{}", encoding="utf-8")

            result = _invalidate_legacy_frontend_cache_for_pagespec(output_dir)

            self.assertTrue(result["migrated"])
            self.assertEqual(result["previous_version"], "legacy-react-cache")
            self.assertFalse(any(screens_dir.iterdir()))
            self.assertFalse((ui_dir / "screen.png").exists())
            self.assertFalse((ui_dir / "screenshot-checkpoint.json").exists())
            self.assertTrue((ui_dir / "ui_blueprint.json").exists())
            self.assertTrue(blueprint_path.exists())
            self.assertEqual(reference_path.read_bytes(), b"image2")

    def test_current_pagespec_attempt_keeps_partial_page_cache_for_resume(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            react_dir = output_dir / "generated_source" / "ui-prototype" / "react-app"
            screens_dir = react_dir / "src" / "screens"
            screens_dir.mkdir(parents=True)
            (screens_dir / "ScreenA.page-spec.json").write_text('{"schema_version":"page-spec-v1"}', encoding="utf-8")
            (react_dir / ".frontend-engine.json").write_text(
                json.dumps({"frontend_engine_version": FRONTEND_ENGINE_VERSION}),
                encoding="utf-8",
            )

            result = _invalidate_legacy_frontend_cache_for_pagespec(output_dir)

            self.assertFalse(result["migrated"])
            self.assertTrue((screens_dir / "ScreenA.page-spec.json").exists())

    def test_renderer_upgrade_preserves_pagespec_and_meta_for_local_rerender(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            react_dir = output_dir / "generated_source" / "ui-prototype" / "react-app"
            screens_dir = react_dir / "src" / "screens"
            screens_dir.mkdir(parents=True)
            spec_path = screens_dir / "ScreenA.page-spec.json"
            meta_path = screens_dir / "ScreenA.meta.json"
            jsx_path = screens_dir / "ScreenA.jsx"
            css_path = screens_dir / "ScreenA.css"
            spec_path.write_text('{"schema_version":"page-spec-v1","page_key":"screen_a"}', encoding="utf-8")
            meta_path.write_text('{"engine":"page-spec-v1","page_key":"screen_a"}', encoding="utf-8")
            jsx_path.write_text("old jsx", encoding="utf-8")
            css_path.write_text("old css", encoding="utf-8")
            (react_dir / ".frontend-engine.json").write_text(
                '{"frontend_engine_version":"pagespec-hybrid-v1"}',
                encoding="utf-8",
            )

            result = _invalidate_legacy_frontend_cache_for_pagespec(output_dir)

            self.assertTrue(result["migrated"])
            self.assertEqual(result["previous_version"], "pagespec-hybrid-v1")
            self.assertTrue(spec_path.exists())
            self.assertTrue(meta_path.exists())
            self.assertFalse(jsx_path.exists())
            self.assertFalse(css_path.exists())
            self.assertIn("page-spec-json", result["preserved"])

    def test_completed_resume_returns_existing_material_package(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "测试系统-existing"
            output_dir.mkdir()
            deliverable = output_dir / "测试系统软件说明书.docx"
            deliverable.write_bytes(b"docx")
            zip_path = output_dir.parent / f"{output_dir.name}--材料包.zip"
            zip_path.write_bytes(b"zip")
            (output_dir / "generation-state.json").write_text(
                json.dumps(
                    {
                        "status": "success",
                        "stage": "done",
                        "extra": {"zip_path": str(zip_path)},
                    }
                ),
                encoding="utf-8",
            )
            (output_dir / "generation_report.json").write_text(
                json.dumps(
                    {
                        "task": {"output_dir": str(output_dir)},
                        "zip_path": str(zip_path),
                        "files": [str(deliverable)],
                        "checks": {},
                        "warnings": [],
                    }
                ),
                encoding="utf-8",
            )

            report = _load_completed_resume_report(output_dir)

            self.assertIsNotNone(report)
            self.assertEqual(report["zip_path"], str(zip_path))
            self.assertEqual(report["files"], [str(deliverable)])
            self.assertTrue(report["checks"]["completed_resume_reused"])

    def test_success_state_without_material_package_is_not_reused(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "测试系统-missing-package"
            output_dir.mkdir()
            (output_dir / "generation-state.json").write_text(
                json.dumps({"status": "success", "stage": "done"}),
                encoding="utf-8",
            )
            (output_dir / "generation_report.json").write_text(
                json.dumps({"zip_path": "", "files": []}),
                encoding="utf-8",
            )

            self.assertIsNone(_load_completed_resume_report(output_dir))
            self.assertEqual(_resume_failure_stage(output_dir), "")

    def test_delivery_zip_uses_actual_resume_output_directory_name(self):
        output_dir = Path("output") / "测试系统-dialog-theme-v4"

        self.assertEqual(
            _delivery_zip_path(output_dir),
            Path("output") / "测试系统-dialog-theme-v4--材料包.zip",
        )

    def test_recovers_custom_seed_from_generation_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "测试系统-custom-seed-v3"
            root.mkdir()
            (root / "generation-state.json").write_text(
                json.dumps({"task": {"seed": "custom-seed-v3"}}),
                encoding="utf-8",
            )

            self.assertEqual(_seed_from_output_dir(str(root)), "custom-seed-v3")

    def test_falls_back_to_timestamp_seed_in_output_name(self):
        output_dir = Path("测试系统-20260721-020304-1234")

        self.assertEqual(_seed_from_output_dir(str(output_dir)), "20260721-020304-1234")

    def test_loads_confirmed_outline_from_generation_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            expected = {"softwareName": "Test", "modules": [{"title": "Module"}]}
            (root / "generation_report.json").write_text(
                json.dumps({"task": {"confirmed_outline": expected}}),
                encoding="utf-8",
            )

            self.assertEqual(_confirmed_outline_from_resume_dir(root), expected)

    def test_ignores_empty_or_invalid_outline(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "generation_report.json").write_text(
                json.dumps({"task": {"confirmed_outline": {"modules": []}}}),
                encoding="utf-8",
            )

            self.assertEqual(_confirmed_outline_from_resume_dir(root), {})

    def test_recovers_outline_from_generated_product_blueprint(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            blueprint_dir = root / "generated_source"
            blueprint_dir.mkdir(parents=True)
            expected = {
                "software_name": "Test",
                "modules": [
                    {"key": f"module_{index}", "title": f"Module {index}", "description": "完整业务模块说明"}
                    for index in range(1, 7)
                ],
            }
            (blueprint_dir / "product-blueprint.json").write_text(
                json.dumps(expected),
                encoding="utf-8",
            )

            self.assertEqual(_confirmed_outline_from_resume_dir(root), expected)

    def test_resume_checkpoint_starts_at_failed_stage(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "generation-failure.json").write_text(
                json.dumps({"stage": "screenshots", "progress": 50}),
                encoding="utf-8",
            )

            self.assertEqual(_resume_failure_stage(root), "screenshots")
            self.assertEqual(_resume_failure_progress(root), 50)
            self.assertTrue(_stage_precedes("source", "screenshots"))
            self.assertFalse(_stage_precedes("screenshots", "screenshots"))
            self.assertFalse(_stage_precedes("manual", "screenshots"))

    def test_late_stage_resume_locks_the_exact_generated_blueprint(self):
        resume_blueprint = object()

        self.assertTrue(_resume_blueprint_lock_ready(resume_blueprint, resume_blueprint, "screenshots"))
        self.assertTrue(_resume_blueprint_lock_ready(resume_blueprint, resume_blueprint, "done"))
        self.assertFalse(_resume_blueprint_lock_ready(resume_blueprint, object(), "screenshots"))
        self.assertFalse(_resume_blueprint_lock_ready(resume_blueprint, resume_blueprint, "blueprint"))

    def test_screenshot_resume_defers_only_pre_render_similarity_with_ready_image2_reference(self):
        ui_blueprint = object()
        reference = {"ready": True, "source": "gpt-style-reference-prompt+image2"}

        self.assertTrue(
            _should_defer_pre_render_similarity_for_resume(
                resume_stage="screenshots",
                resume_ui_blueprint=ui_blueprint,
                attempt_cached=ui_blueprint,
                visual_reference_report=reference,
            )
        )
        self.assertTrue(
            _should_defer_pre_render_similarity_for_resume(
                resume_stage="done",
                resume_ui_blueprint=ui_blueprint,
                attempt_cached=ui_blueprint,
                visual_reference_report=reference,
            )
        )
        self.assertTrue(
            _should_defer_pre_render_similarity_for_resume(
                resume_stage="manual",
                resume_ui_blueprint=ui_blueprint,
                attempt_cached=ui_blueprint,
                visual_reference_report=reference,
            )
        )
        self.assertFalse(
            _should_defer_pre_render_similarity_for_resume(
                resume_stage="visual_reference",
                resume_ui_blueprint=ui_blueprint,
                attempt_cached=ui_blueprint,
                visual_reference_report=reference,
            )
        )
        self.assertFalse(
            _should_defer_pre_render_similarity_for_resume(
                resume_stage="screenshots",
                resume_ui_blueprint=ui_blueprint,
                attempt_cached=ui_blueprint,
                visual_reference_report={"ready": False, "source": "gpt-style-reference-prompt+image2"},
            )
        )


if __name__ == "__main__":
    unittest.main()
