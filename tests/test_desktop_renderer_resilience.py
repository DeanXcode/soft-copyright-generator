import json
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
STATE_MODULE = ROOT / "desktop" / "src" / "stateNormalization.js"
MAIN_JSX = ROOT / "desktop" / "src" / "main.jsx"
BOUNDARY = ROOT / "desktop" / "src" / "components" / "RendererErrorBoundary.jsx"
ELECTRON_MAIN = ROOT / "desktop" / "electron" / "main.cjs"
PRELOAD = ROOT / "desktop" / "electron" / "preload.cjs"


class DesktopRendererResilienceTests(unittest.TestCase):
    def run_state_normalizer(self, expression: str):
        script = f"""
import {{ enqueueOrReplaceRetryTask, normalizeBusinessPlanState, normalizeModelCatalogState, normalizeQueueState }} from {json.dumps(STATE_MODULE.as_uri())};
const value = {expression};
console.log(JSON.stringify(value));
"""
        completed = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        return json.loads(completed.stdout)

    def test_malformed_persisted_state_is_normalized_before_render(self):
        value = self.run_state_normalizer(
            "({ queue: normalizeQueueState({tasks: {bad: true}, paused: 1}), "
            "plan: normalizeBusinessPlanState({modules: {bad: true}}), "
            "catalog: normalizeModelCatalogState({models: null, provider: 42}) })"
        )

        self.assertEqual(value["queue"], {"tasks": [], "paused": True})
        self.assertEqual(value["plan"]["modules"], [])
        self.assertEqual(value["catalog"]["models"], [])
        self.assertEqual(value["catalog"]["provider"], "42")

    def test_queue_tasks_and_blueprint_modules_drop_invalid_rows(self):
        value = self.run_state_normalizer(
            "({ queue: normalizeQueueState({tasks: [null, 'bad', {title: '有效任务', events: 'bad'}]}), "
            "plan: normalizeBusinessPlanState({softwareName: '测试', modules: [null, {title: '模块A', description: '说明'}]}) })"
        )

        self.assertEqual(len(value["queue"]["tasks"]), 1)
        self.assertEqual(value["queue"]["tasks"][0]["events"], [])
        self.assertEqual(len(value["plan"]["modules"]), 1)
        self.assertEqual(value["plan"]["modules"][0]["title"], "模块A")

    def test_confirmed_outline_retry_replaces_failed_queue_row_for_same_output(self):
        value = self.run_state_normalizer(
            "enqueueOrReplaceRetryTask(["
            "{id: 'failed-1', title: '失败任务', status: 'error', createdAt: 10, result: {outputDir: 'D:\\\\output\\\\task-a'}}, "
            "{id: 'other-1', title: '其他任务', status: 'queued', overrides: {resumeOutputDir: 'D:\\\\output\\\\task-b'}}"
            "], {id: 'retry-1', title: '失败任务', status: 'queued', createdAt: 20, overrides: {resumeOutputDir: 'd:/output/task-a/'}}, {retry: true})"
        )

        self.assertEqual(len(value), 2)
        self.assertEqual(value[0]["id"], "failed-1")
        self.assertEqual(value[0]["status"], "queued")
        self.assertEqual(value[0]["createdAt"], 10)
        self.assertEqual(value[1]["id"], "other-1")

    def test_persisted_queue_drops_older_duplicate_for_same_output(self):
        value = self.run_state_normalizer(
            "normalizeQueueState({tasks: ["
            "{id: 'failed-1', status: 'error', result: {outputDir: 'D:\\\\output\\\\task-a'}}, "
            "{id: 'retry-1', status: 'running', overrides: {resumeOutputDir: 'd:/output/task-a/'}}"
            "]})"
        )

        self.assertEqual(len(value["tasks"]), 1)
        self.assertEqual(value["tasks"][0]["id"], "retry-1")

    def test_react_tree_has_visible_recovery_boundary_and_renderer_logging(self):
        main_source = MAIN_JSX.read_text(encoding="utf-8")
        boundary_source = BOUNDARY.read_text(encoding="utf-8")
        electron_source = ELECTRON_MAIN.read_text(encoding="utf-8")
        preload_source = PRELOAD.read_text(encoding="utf-8")

        self.assertIn("<RendererErrorBoundary>", main_source)
        self.assertIn('const generationStages = [', main_source)
        self.assertIn('["visual_reference", "生成风格参考图"]', main_source)
        self.assertIn('status === "planning" ? null : planReady', main_source)
        self.assertIn("检测到应用重启前遗留的队列状态", main_source)
        self.assertIn("刷新界面并恢复状态", boundary_source)
        self.assertIn("后台生成任务仍在运行", boundary_source)
        self.assertIn('ipcMain.handle("report-renderer-error"', electron_source)
        self.assertIn('webContents.on("console-message"', electron_source)
        self.assertIn('webContents.on("render-process-gone"', electron_source)
        self.assertIn('reportRendererError: (payload) => ipcRenderer.invoke("report-renderer-error", payload)', preload_source)
        self.assertIn("<DomainProfileDiagnostic checks={result.checks} />", main_source)
        self.assertIn('label: "领域门禁"', main_source)
        self.assertIn("domainProfileFromChecks", electron_source)
        self.assertIn("generationState.task?.confirmed_outline", electron_source)
        self.assertIn("confirmedOutlineReady", electron_source)
        self.assertIn("task.domainProfile?.key", (ROOT / "desktop" / "src" / "components" / "QueuePanel.jsx").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
