from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN_CJS = ROOT / "desktop" / "electron" / "main.cjs"
MAIN_JSX = ROOT / "desktop" / "src" / "main.jsx"


class DesktopModelConfigSecretTests(unittest.TestCase):
    def test_desktop_error_sanitizer_hides_connection_pool_host_and_model_path(self):
        source = MAIN_CJS.read_text(encoding="utf-8")

        self.assertIn("ConnectionPool\\(host=", source)
        self.assertIn("chat\\/completions", source)
        self.assertIn("模型网关连接", source)
        self.assertIn("[模型接口]", source)

    def test_ipc_model_config_responses_do_not_echo_secrets(self):
        source = MAIN_CJS.read_text(encoding="utf-8")
        get_block = source.split('ipcMain.handle("get-model-config"', 1)[1].split('ipcMain.handle("list-recoverable-tasks"', 1)[0]
        save_block = source.split('ipcMain.handle("save-model-config"', 1)[1].split('ipcMain.handle("open-path"', 1)[0]

        self.assertIn('apiBaseUrl: ""', get_block)
        self.assertIn('apiKey: ""', get_block)
        self.assertIn('imageApiBaseUrl: ""', get_block)
        self.assertIn('imageApiKey: ""', get_block)
        self.assertNotIn('apiBaseUrl: modelPlans.gpt.apiBaseUrl', get_block)
        self.assertNotIn('apiKey: modelPlans.gpt.apiKey', get_block)

        self.assertIn('apiBaseUrl: ""', save_block)
        self.assertIn('apiKey: ""', save_block)
        self.assertIn('imageApiBaseUrl: ""', save_block)
        self.assertIn('imageApiKey: ""', save_block)
        self.assertNotIn('apiBaseUrl: config.SOFT_MODEL_GPT_BASE_URL', save_block)
        self.assertNotIn('apiKey: config.SOFT_MODEL_GPT_API_KEY', save_block)

    def test_desktop_uses_write_only_secret_inputs(self):
        source = MAIN_JSX.read_text(encoding="utf-8")

        self.assertIn("更换请求地址（留空则保持不变）", source)
        self.assertIn("请求地址状态", source)
        self.assertIn("OpenAI 兼容请求地址", source)
        self.assertIn("更换 API Key（留空则保持不变）", source)
        self.assertIn('type="password"', source)
        self.assertIn('apiBaseUrl: ""', source)
        self.assertIn('apiKey: ""', source)
        self.assertIn("图片模型 API", source)
        self.assertIn("使用独立图片 API", source)
        self.assertIn("更换图片请求地址（留空则保持不变）", source)
        self.assertIn("更换图片 API Key（留空则保持不变）", source)
        self.assertIn('imageApiBaseUrl: ""', source)
        self.assertIn('imageApiKey: ""', source)

    def test_separate_image_api_config_is_saved_without_echoing_secrets(self):
        main_source = MAIN_CJS.read_text(encoding="utf-8")
        save_block = main_source.split('ipcMain.handle("save-model-config"', 1)[1].split('ipcMain.handle("open-path"', 1)[0]

        self.assertIn("SOFT_MODEL_GPT_IMAGE_NAME: imageModel", save_block)
        self.assertIn("SOFT_MODEL_GPT_IMAGE_BASE_URL: imageApiBaseUrl", save_block)
        self.assertIn("SOFT_MODEL_GPT_IMAGE_API_KEY: imageApiKey", save_block)
        self.assertIn('imageApiBaseUrl: ""', save_block)
        self.assertIn('imageApiKey: ""', save_block)

    def test_multiple_text_providers_have_separate_secret_slots_and_hidden_presets(self):
        main_source = MAIN_CJS.read_text(encoding="utf-8")
        renderer_source = MAIN_JSX.read_text(encoding="utf-8")
        save_block = main_source.split('ipcMain.handle("save-model-config"', 1)[1].split('ipcMain.handle("open-path"', 1)[0]

        for provider in ("grok", "claude", "gemini", "deepseek"):
            self.assertIn(f'{provider}: {{', main_source)
            self.assertIn(f'value: "{provider}"', renderer_source)
        self.assertIn('SOFT_TEXT_PROVIDER: textProvider', save_block)
        self.assertIn('SOFT_MODEL_PROVIDER: preset.provider', save_block)
        self.assertIn('config[`SOFT_PROVIDER_${providerPrefix}_API_KEY`] = apiKey', save_block)
        self.assertIn('providerProfiles: providerProfilesForUi()', save_block)
        self.assertIn('官方预设（地址已隐藏）', renderer_source)
        self.assertIn('各文本供应商的 API Key 独立保存且不回显', renderer_source)
        self.assertIn('SOFT_LLM_AI_FRONTEND_WORKERS: String(frontendWorkers)', save_block)
        self.assertIn('界面并发数', renderer_source)
        self.assertIn('自动（推荐，初始 2，遇限流降为 1）', renderer_source)
        self.assertIn('["grok", "claude", "gemini", "deepseek"].includes(accountProvider)', main_source)

    def test_recovery_is_attempt_isolated_and_marks_orphaned_running_tasks_interrupted(self):
        source = MAIN_CJS.read_text(encoding="utf-8")

        self.assertIn('const latestAttemptId = String(generationState.attempt_id || "").trim();', source)
        self.assertIn('const failureMatchesAttempt = !latestAttemptId || !generationFailure.attempt_id || String(generationFailure.attempt_id) === latestAttemptId;', source)
        self.assertIn('const interrupted = stateStatus === "running" && !hasActiveChild;', source)
        self.assertIn('检测到上次运行中断，当前没有活动生成进程', source)
        self.assertIn('上次任务标记完成，但材料包文件不存在', source)

    def test_default_name_only_flow_auto_confirms_blueprint_and_keeps_review_option(self):
        renderer_source = MAIN_JSX.read_text(encoding="utf-8")

        self.assertIn('blueprintReviewBeforeGeneration: false', renderer_source)
        self.assertIn('enqueueQuickTask(currentPromptText)', renderer_source)
        self.assertIn('autoPlan: true', renderer_source)
        self.assertIn('自动确认并直接生成（推荐）', renderer_source)
        self.assertIn('生成后先人工审阅', renderer_source)
        self.assertIn('return blueprintReviewBeforeGeneration ? "生成蓝图" : "开始生成"', renderer_source)
        self.assertNotIn('"确认模块"', renderer_source)

    def test_name_inference_operation_contract_is_preserved_for_backend_reuse(self):
        renderer_source = MAIN_JSX.read_text(encoding="utf-8")

        self.assertIn('operationSpecs: normalizeOperationSpecs', renderer_source)
        self.assertIn('operationSpecs: module.operationSpecs', renderer_source)
        self.assertIn('resultEvidence:', renderer_source)

    def test_default_template_is_visible_and_clears_model_credentials_for_generation(self):
        renderer_source = MAIN_JSX.read_text(encoding="utf-8")
        main_source = MAIN_CJS.read_text(encoding="utf-8")
        generate_block = main_source.split('ipcMain.handle("generate-materials"', 1)[1].split(
            'ipcMain.handle("infer-feature-hint"', 1
        )[0]

        self.assertIn('label: "Default Template"', renderer_source)
        self.assertIn('provider: "local-template"', renderer_source)
        self.assertIn('cost: "不消耗 token"', renderer_source)
        self.assertIn('payload?.modelPlan === "template"', generate_block)
        self.assertIn('SOFT_MODEL_GPT_API_KEY: templateMode ? ""', generate_block)
        self.assertIn('SOFT_MODEL_GPT_BASE_URL: templateMode ? ""', generate_block)
        self.assertIn('SOFT_MODEL_GPT_IMAGE_API_KEY: templateMode ? ""', generate_block)
        self.assertIn('SOFT_MODEL_IMAGE_API_KEY: templateMode ? ""', generate_block)

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

    def test_model_fallback_choices_are_scoped_to_selected_provider(self):
        renderer_source = MAIN_JSX.read_text(encoding="utf-8")

        self.assertIn("const providerModelChoices =", renderer_source)
        self.assertIn('grok: ["grok-3-mini"]', renderer_source)
        self.assertIn('claude: ["claude-sonnet-4-20250514"]', renderer_source)
        self.assertIn('gemini: ["gemini-2.5-flash"]', renderer_source)
        self.assertIn('deepseek: ["deepseek-chat"]', renderer_source)
        self.assertIn('modelCatalog.provider === selectedTextProvider.value', renderer_source)
        self.assertNotIn('...modelChoices].filter(Boolean))];', renderer_source)

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

    def test_progress_done_event_cannot_create_an_empty_success_result(self):
        renderer_source = MAIN_JSX.read_text(encoding="utf-8")
        result_block = renderer_source.split("function resultFromGenerationEvent", 1)[1].split("function seedFromOutputDir", 1)[0]

        self.assertIn('if (!event.result || typeof event.result !== "object") return null;', result_block)
        self.assertNotIn('ok: event.stage === "done"', result_block)

    def test_material_generation_success_requires_result_json_and_existing_zip(self):
        main_source = MAIN_CJS.read_text(encoding="utf-8")
        generate_block = main_source.split('ipcMain.handle("generate-materials"', 1)[1].split(
            'ipcMain.handle("infer-feature-hint"', 1
        )[0]

        self.assertIn("const resultJsonReady = Boolean(resultMatch);", generate_block)
        self.assertIn("const zipReady = Boolean(zipPath && fs.existsSync(zipPath)", generate_block)
        self.assertIn("ok: code === 0 && resultJsonReady && zipReady", generate_block)
        self.assertIn("files: Array.isArray(result.files) ? result.files : []", main_source)


if __name__ == "__main__":
    unittest.main()
