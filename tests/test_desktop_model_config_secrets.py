from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN_CJS = ROOT / "desktop" / "electron" / "main.cjs"
MAIN_JSX = ROOT / "desktop" / "src" / "main.jsx"


class DesktopModelConfigSecretTests(unittest.TestCase):
    def test_ipc_model_config_responses_do_not_echo_secrets(self):
        source = MAIN_CJS.read_text(encoding="utf-8")
        get_block = source.split('ipcMain.handle("get-model-config"', 1)[1].split('ipcMain.handle("list-recoverable-tasks"', 1)[0]
        save_block = source.split('ipcMain.handle("save-model-config"', 1)[1].split('ipcMain.handle("open-path"', 1)[0]

        self.assertIn('apiBaseUrl: ""', get_block)
        self.assertIn('apiKey: ""', get_block)
        self.assertNotIn('apiBaseUrl: modelPlans.gpt.apiBaseUrl', get_block)
        self.assertNotIn('apiKey: modelPlans.gpt.apiKey', get_block)

        self.assertIn('apiBaseUrl: ""', save_block)
        self.assertIn('apiKey: ""', save_block)
        self.assertNotIn('apiBaseUrl: config.SOFT_MODEL_GPT_BASE_URL', save_block)
        self.assertNotIn('apiKey: config.SOFT_MODEL_GPT_API_KEY', save_block)

    def test_desktop_uses_write_only_secret_inputs(self):
        source = MAIN_JSX.read_text(encoding="utf-8")

        self.assertIn("更换请求地址（留空则保持不变）", source)
        self.assertIn("更换 API Key（留空则保持不变）", source)
        self.assertIn('type="password"', source)
        self.assertIn('apiBaseUrl: ""', source)
        self.assertIn('apiKey: ""', source)

    def test_model_catalog_is_loaded_in_main_process(self):
        main_source = MAIN_CJS.read_text(encoding="utf-8")
        preload_source = (ROOT / "desktop" / "electron" / "preload.cjs").read_text(encoding="utf-8")
        renderer_source = MAIN_JSX.read_text(encoding="utf-8")

        self.assertIn('ipcMain.handle("list-available-models"', main_source)
        self.assertIn('Authorization: `Bearer ${apiKey}`', main_source)
        self.assertIn('"x-api-key": apiKey', main_source)
        self.assertIn('listAvailableModels: () => ipcRenderer.invoke("list-available-models")', preload_source)
        self.assertIn("catalogModels.map((model) => <option", renderer_source)
        self.assertIn("自定义模型 ID（列表中没有时填写）", renderer_source)
        self.assertNotIn('<datalist id="available-model-catalog">', renderer_source)
        self.assertIn("refreshAvailableModels", renderer_source)

    def test_settings_has_single_animated_header_entry(self):
        renderer_source = MAIN_JSX.read_text(encoding="utf-8")
        style_source = (ROOT / "desktop" / "src" / "styles.css").read_text(encoding="utf-8")

        self.assertNotIn("<Settings2", renderer_source)
        self.assertEqual(renderer_source.count('className="model-summary-button"'), 1)
        self.assertIn('className={`drawer-backdrop ${open ? "open" : ""}`}', renderer_source)
        self.assertIn("transform: translateX(100%);", style_source)
        self.assertIn(".drawer-backdrop.open .settings-drawer", style_source)

    def test_brand_refresh_has_workflow_and_result_hero(self):
        renderer_source = MAIN_JSX.read_text(encoding="utf-8")
        style_source = (ROOT / "desktop" / "src" / "styles.css").read_text(encoding="utf-8")

        self.assertIn('import appIcon from "../../build/icon.png"', renderer_source)
        self.assertIn("<WorkflowNavigator", renderer_source)
        self.assertIn("创建软著材料任务", renderer_source)
        self.assertIn("软著材料包已准备完成", renderer_source)
        self.assertIn(".workflow-nav", style_source)
        self.assertIn(".result-hero", style_source)

    def test_brand_refresh_phase_two_hierarchy(self):
        renderer_source = MAIN_JSX.read_text(encoding="utf-8")
        style_source = (ROOT / "desktop" / "src" / "styles.css").read_text(encoding="utf-8")

        self.assertIn('className="queue-brand-mark"', renderer_source)
        self.assertIn('className="settings-scroll-content"', renderer_source)
        self.assertIn('className="settings-save-dock"', renderer_source)
        self.assertIn("<SettingsSectionHeading", renderer_source)
        self.assertIn(".module-node:hover", style_source)
        self.assertIn("@keyframes detailReveal", style_source)
        self.assertIn("@keyframes brandPulse", style_source)

    def test_semantic_icons_replace_repeated_brand_marks(self):
        renderer_source = MAIN_JSX.read_text(encoding="utf-8")
        style_source = (ROOT / "desktop" / "src" / "styles.css").read_text(encoding="utf-8")

        self.assertEqual(renderer_source.count("<img src={appIcon}"), 1)
        self.assertIn("<ListOrdered", renderer_source)
        self.assertIn("<SlidersHorizontal", renderer_source)
        self.assertIn("processStatusIcon(status, latest?.event?.stage)", renderer_source)
        self.assertIn("grid-template-columns: 40px minmax(0, 1fr) 50px 70px;", style_source)
        self.assertNotIn(".primary-action svg,", style_source)

    def test_packaged_frontend_runtime_uses_unpacked_esbuild_and_separate_model(self):
        main_source = MAIN_CJS.read_text(encoding="utf-8")
        renderer_source = MAIN_JSX.read_text(encoding="utf-8")

        self.assertIn('function packagedEsbuildBinaryPath()', main_source)
        self.assertIn('"app.asar.unpacked", "node_modules", "@esbuild", "win32-x64", "esbuild.exe"', main_source)
        self.assertIn('{ ESBUILD_BINARY_PATH: packagedEsbuildBinaryPath() }', main_source)
        self.assertIn('SOFT_LLM_AI_FRONTEND_TIMEOUT_SECONDS', main_source)
        self.assertIn('SOFT_LLM_AI_FRONTEND_RETRY_COUNT', main_source)
        self.assertIn('frontendModelName: frontendModelName()', main_source)
        self.assertIn("界面生成模型", renderer_source)
        self.assertIn('onUpdateModelConfig("frontendModelName"', renderer_source)

    def test_process_detail_nodes_have_completed_and_in_progress_states(self):
        renderer_source = MAIN_JSX.read_text(encoding="utf-8")
        style_source = (ROOT / "desktop" / "src" / "styles.css").read_text(encoding="utf-8")

        self.assertIn('const rowState = latestRow && ["planning", "running"].includes(status) ? "in-progress" : "completed";', renderer_source)
        self.assertIn('title={rowState === "completed" ? "已完成" : "进行中"}', renderer_source)
        self.assertIn('<CheckCircle2 size={15} /> : <Loader2 size={15} />', renderer_source)
        self.assertIn(".process-text-node.completed", style_source)
        self.assertIn(".process-text-node.in-progress", style_source)
        self.assertNotIn(".process-text-dot.plan", style_source)

    def test_process_detail_does_not_expose_raw_runtime_log(self):
        renderer_source = MAIN_JSX.read_text(encoding="utf-8")
        style_source = (ROOT / "desktop" / "src" / "styles.css").read_text(encoding="utf-8")

        self.assertNotIn("原始运行日志", renderer_source)
        self.assertNotIn("raw-log-details", renderer_source)
        self.assertNotIn("raw-log-details", style_source)
        self.assertNotIn(".log-view", style_source)


if __name__ == "__main__":
    unittest.main()
