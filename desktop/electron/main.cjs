const { app, BrowserWindow, ipcMain, shell } = require("electron");
const fs = require("fs");
const http = require("http");
const https = require("https");
const path = require("path");
const { spawn } = require("child_process");

const sourceRoot = path.resolve(__dirname, "..", "..");
const appRoot = app.isPackaged ? app.getAppPath() : sourceRoot;
const resourceRoot = app.isPackaged ? process.resourcesPath : sourceRoot;
const rootDir = resourceRoot;
const TEXT_PROVIDER_PRESETS = {
  custom: {
    label: "现有兼容 API",
    provider: "custom",
    defaultBaseUrl: "",
    defaultModel: "gpt-5.5"
  },
  grok: {
    label: "Grok (xAI)",
    provider: "grok",
    defaultBaseUrl: "https://api.x.ai/v1",
    defaultModel: "grok-3-mini"
  },
  claude: {
    label: "Claude (Anthropic)",
    provider: "claude",
    defaultBaseUrl: "https://api.anthropic.com/v1",
    defaultModel: "claude-sonnet-4-20250514"
  },
  gemini: {
    label: "Gemini (Google)",
    provider: "gemini",
    defaultBaseUrl: "https://generativelanguage.googleapis.com/v1beta/openai",
    defaultModel: "gemini-2.5-flash"
  },
  deepseek: {
    label: "DeepSeek",
    provider: "deepseek",
    defaultBaseUrl: "https://api.deepseek.com",
    defaultModel: "deepseek-chat"
  }
};
loadDesktopConfig();

const isDev = process.env.VITE_DEV_SERVER_URL || process.env.NODE_ENV === "development";
let mainWindow;
let activeGenerationTask = null;
let activeOutlineTask = null;
let lastGenerationResult = null;
const RECOVERY_DISMISSED_FILE = "generation-recovery-dismissed.json";

const modelPlans = {
  template: {
    provider: "local-template",
    modelName: "template-v1",
    apiBaseUrl: "",
    apiKey: ""
  },
  gpt: {
    provider: process.env.SOFT_MODEL_PROVIDER || TEXT_PROVIDER_PRESETS[normalizeTextProvider(process.env.SOFT_TEXT_PROVIDER)]?.provider || "custom",
    modelName: process.env.SOFT_MODEL_GPT_NAME || process.env.SOFT_MODEL_GATEWAY_MODEL || activeTextProviderPreset().defaultModel,
    apiBaseUrl: process.env.SOFT_MODEL_GPT_BASE_URL || process.env.SOFT_MODEL_GATEWAY_BASE_URL || activeTextProviderPreset().defaultBaseUrl,
    apiKey: process.env.SOFT_MODEL_GPT_API_KEY || process.env.SOFT_MODEL_GATEWAY_API_KEY || ""
  }
};

function accountApiBaseUrl() {
  return process.env.SOFT_ACCOUNT_API_BASE_URL || process.env.SOFT_MODEL_ACCOUNT_API_BASE_URL || "";
}

function accountAuthToken() {
  return process.env.SOFT_ACCOUNT_AUTH_TOKEN || process.env.SOFT_MODEL_GPT_API_KEY || process.env.SOFT_MODEL_GATEWAY_API_KEY || "";
}

function accountBalanceUrl() {
  const accountProvider = (process.env.SOFT_ACCOUNT_PROVIDER || "").toLowerCase();
  if (["grok", "claude", "gemini", "deepseek"].includes(accountProvider)) {
    return "";
  }
  const explicitUrl = process.env.SOFT_ACCOUNT_BALANCE_URL || "";
  if (explicitUrl) {
    return explicitUrl;
  }
  if (accountProvider === "newapi") {
    const gatewayRoot = rootUrlFromGateway(modelPlans.gpt.apiBaseUrl);
    return gatewayRoot ? `${gatewayRoot}/api/usage/token/` : "";
  }
  const baseUrl = accountApiBaseUrl().replace(/\/+$/, "");
  return baseUrl ? `${baseUrl}/api/v1/account/balance` : "";
}

function defaultConfigPath() {
  const externalConfigDir = process.env.SOFT_DESKTOP_CONFIG_DIR || "";
  if (externalConfigDir) {
    return path.join(externalConfigDir, "production.json");
  }
  return path.join(userConfigDir(), "production.json");
}

function userConfigDir() {
  try {
    return path.join(app.getPath("userData"), "config");
  } catch (_error) {
    return path.join(rootDir, "config");
  }
}

function packagedPlaywrightBrowsersPath() {
  const candidates = [
    path.join(process.resourcesPath || "", "ms-playwright"),
    path.join(path.dirname(process.execPath), "ms-playwright"),
    path.join(rootDir, "ms-playwright")
  ];
  return candidates.find((candidate) => fs.existsSync(candidate)) || "";
}

function bundledPythonExecutable() {
  const candidates = [
    path.join(process.resourcesPath || "", "python-runtime", "python.exe"),
    path.join(path.dirname(process.execPath), "python-runtime", "python.exe"),
    path.join(rootDir, "python-runtime", "python.exe")
  ];
  return candidates.find((candidate) => fs.existsSync(candidate)) || "python";
}

function packagedLibreOfficePath() {
  const candidates = [
    path.join(process.resourcesPath || "", "libreoffice", "program", "soffice.exe"),
    path.join(path.dirname(process.execPath), "libreoffice", "program", "soffice.exe"),
    path.join(rootDir, "libreoffice", "program", "soffice.exe")
  ];
  return candidates.find((candidate) => fs.existsSync(candidate)) || "";
}

function packagedEsbuildBinaryPath() {
  const unpackedAppRoot = String(app.getAppPath() || "").replace(/app\.asar$/i, "app.asar.unpacked");
  const candidates = [
    path.join(process.resourcesPath || "", "app.asar.unpacked", "node_modules", "@esbuild", "win32-x64", "esbuild.exe"),
    path.join(unpackedAppRoot, "node_modules", "@esbuild", "win32-x64", "esbuild.exe"),
    path.join(sourceRoot, "node_modules", "@esbuild", "win32-x64", "esbuild.exe")
  ];
  return candidates.find((candidate) => fs.existsSync(candidate)) || "";
}

function sendGenerateEvent(sender, payload) {
  let sent = false;
  try {
    if (sender && !sender.isDestroyed?.()) {
      sender.send("generate-event", payload);
      sent = true;
    }
  } catch (_error) {
    // The renderer may have been closed while a background process is stopping.
  }
  try {
    const webContents = mainWindow?.webContents;
    if (webContents && !webContents.isDestroyed?.() && webContents !== sender) {
      webContents.send("generate-event", payload);
      sent = true;
    }
  } catch (_error) {
    // Best-effort broadcast for renderer reload recovery.
  }
  return sent;
}

function terminateProcessTree(child) {
  if (!child || !child.pid || child.killed) return;
  if (process.platform === "win32") {
    try {
      const killer = spawn("taskkill", ["/pid", String(child.pid), "/t", "/f"], {
        windowsHide: true,
        stdio: "ignore"
      });
      killer.on("error", () => {
        try {
          child.kill();
        } catch (_error) {
          // Process may already be gone.
        }
      });
      return;
    } catch (_error) {
      // Fall through to the normal kill path.
    }
  }
  try {
    child.kill("SIGTERM");
    const forceKillTimer = setTimeout(() => {
      try {
        if (!child.killed) child.kill("SIGKILL");
      } catch (_error) {
        // Process may already be gone.
      }
    }, 3000);
    forceKillTimer.unref?.();
  } catch (_error) {
    // Process may already be gone.
  }
}

function cancelTask(task, message) {
  if (!task || task.cancelled || task.settled) return false;
  task.cancelled = true;
  writeRuntimeLog(`${task.kind}_cancel_requested`, {
    pid: task.child?.pid || 0,
    stage: task.stage || ""
  });
  sendGenerateEvent(task.sender, {
    stage: task.stage || "start",
    progress: task.progress || 0,
    message
  });
  terminateProcessTree(task.child);
  return true;
}

function generationOutputRoot() {
  if (app.isPackaged) {
    return path.join(app.getPath("documents"), "SoftCopyrightGenerator", "output");
  }
  return path.join(rootDir, "output");
}

function pathInsideGenerationOutput(targetPath) {
  const outputRoot = path.resolve(generationOutputRoot());
  const resolvedTarget = path.resolve(String(targetPath || ""));
  const normalize = (value) => (process.platform === "win32" ? value.toLowerCase() : value);
  const root = normalize(outputRoot);
  const target = normalize(resolvedTarget);
  return target !== root && target.startsWith(root.endsWith(path.sep) ? root : `${root}${path.sep}`);
}

function dismissRecoverableTask(payload = {}) {
  const requestedPath = String(payload.outputDir || "").trim();
  const fallbackId = String(payload.id || "").trim();
  if (!requestedPath && !fallbackId) {
    return { ok: false, message: "恢复记录参数为空" };
  }
  const outputDir = path.resolve(requestedPath || path.join(generationOutputRoot(), fallbackId));
  if (!pathInsideGenerationOutput(outputDir)) {
    return { ok: false, message: "恢复记录路径无效" };
  }
  if (!fs.existsSync(outputDir)) {
    return { ok: true };
  }
  const stat = fs.statSync(outputDir);
  if (!stat.isDirectory()) {
    return { ok: false, message: "恢复记录不是有效目录" };
  }
  const markerPath = path.join(outputDir, RECOVERY_DISMISSED_FILE);
  fs.writeFileSync(
    markerPath,
    JSON.stringify(
      {
        dismissedAt: new Date().toISOString(),
        reason: "user_deleted_recoverable_task"
      },
      null,
      2
    ),
    "utf8"
  );
  return { ok: true };
}

function listRecoverableTasks(limit = 5) {
  const outputRoot = generationOutputRoot();
  if (!fs.existsSync(outputRoot)) return [];
  let entries = [];
  try {
    entries = fs
      .readdirSync(outputRoot, { withFileTypes: true })
      .filter((entry) => entry.isDirectory() && !entry.name.startsWith("."))
      .map((entry) => {
        const outputDir = path.join(outputRoot, entry.name);
        let mtimeMs = 0;
        try {
          mtimeMs = fs.statSync(outputDir).mtimeMs || 0;
        } catch (_error) {
          // Ignore unreadable folders.
        }
        return { outputDir, mtimeMs };
      })
      .sort((left, right) => right.mtimeMs - left.mtimeMs);
  } catch (_error) {
    return [];
  }
  const recovered = [];
  for (const entry of entries) {
    const task = recoverTaskFromOutputDir(entry.outputDir, entry.mtimeMs);
    if (task) recovered.push(task);
    if (recovered.length >= limit) break;
  }
  return recovered;
}

function recoverTaskFromOutputDir(outputDir, mtimeMs = 0) {
  if (fs.existsSync(path.join(outputDir, RECOVERY_DISMISSED_FILE))) return null;
  const blueprintPath = path.join(outputDir, "generated_source", "product-blueprint.json");
  const tracePath = path.join(outputDir, "llm_trace.jsonl");
  if (!fs.existsSync(blueprintPath) || !fs.existsSync(tracePath)) return null;
  const generationState = readJsonConfig(path.join(outputDir, "generation-state.json"));
  const generationFailure = readJsonConfig(path.join(outputDir, "generation-failure.json"));
  const generationReport = readJsonConfig(path.join(outputDir, "generation_report.json"));
  const validationReport = readJsonConfig(path.join(outputDir, "validation_report.json"));
  const latestAttemptId = String(generationState.attempt_id || "").trim();
  const failureMatchesAttempt = !latestAttemptId || !generationFailure.attempt_id || String(generationFailure.attempt_id) === latestAttemptId;
  const effectiveFailure = failureMatchesAttempt ? generationFailure : {};
  const hasActiveChild = Boolean(
    activeGenerationTask &&
    !activeGenerationTask.settled &&
    path.resolve(String(activeGenerationTask.outputDir || "")) === path.resolve(outputDir)
  );
  const stateStatus = String(generationState.status || effectiveFailure.status || "").toLowerCase();
  const reportedZipPath = String(
    generationReport.zip_path || generationState.extra?.zip_path || `${outputDir}--材料包.zip`
  ).trim();
  const completedZipReady = Boolean(reportedZipPath && fs.existsSync(reportedZipPath) && fs.statSync(reportedZipPath).isFile());
  if ((stateStatus === "success" || validationReport.ready_for_delivery === true) && completedZipReady) return null;
  const blueprint = readJsonConfig(blueprintPath);
  const businessPlan = businessPlanFromProductBlueprint(blueprint);
  if (!businessPlan.modules.length) return null;
  const trace = latestTraceFailure(tracePath);
  const visualReferencePath = path.join(outputDir, "generated_source", "ui-prototype", "visual-references", "style_reference.png");
  const seed = seedFromOutputDir(outputDir);
  const validationFinding = Array.isArray(validationReport.findings)
    ? validationReport.findings.find((item) => item && item.level === "error")
    : null;
  const interrupted = stateStatus === "running" && !hasActiveChild;
  const failedStage = String(
    effectiveFailure.stage || (stateStatus === "success" && !completedZipReady ? "package" : generationState.stage) || trace.stage || trace.label || ""
  );
  const errorSummary = sanitizeErrorMessage(
    (interrupted ? "检测到上次运行中断，当前没有活动生成进程。可从已确认蓝图和现有参考图继续。" : "") ||
      effectiveFailure.message ||
      (stateStatus === "success" && !completedZipReady
        ? "上次任务标记完成，但材料包文件不存在，可从已确认蓝图重新生成。"
        : "") ||
      validationFinding?.message ||
      generationState.message ||
      trace.error ||
      "上次生成未完成，可恢复已确认蓝图后重试。"
  );
  return {
    id: path.basename(outputDir),
    title: businessPlan.softwareName,
    outputDir,
    seed,
    recoveredAt: new Date().toLocaleString("zh-CN", { hour12: false }),
    updatedAtMs: mtimeMs,
    attemptId: latestAttemptId,
    resumeSource: String(generationState.resume_source || effectiveFailure.resume_source || ""),
    interrupted,
    failedStage,
    errorSummary,
    visualReferenceReady: fs.existsSync(visualReferencePath),
    promptText: businessPlan.softwareName,
    formSnapshot: {
      name: businessPlan.softwareName,
      version: String(blueprint.version || "V1.0"),
      language: "自动选择",
      productType: businessPlan.productType || "APP",
      softwareCategory: String(blueprint.software_category || "应用软件"),
      featureHint: "",
      modelPlan: "gpt",
      modelProvider: "custom",
      modelName: modelPlans.gpt.modelName || "gpt-5.5",
      randomness: "standard"
    },
    businessPlan
  };
}

function seedFromOutputDir(outputDir) {
  const match = String(path.basename(outputDir || "")).match(/(\d{8}-\d{6}-\d{4})$/);
  return match ? match[1] : "";
}

function businessPlanFromProductBlueprint(blueprint = {}) {
  const modules = Array.isArray(blueprint.modules)
    ? blueprint.modules
        .map((module, index) => {
          const title = String(module.title || module.name || "").trim();
          if (!title) return null;
          return {
            id: `recovered_${index + 1}`,
            category: String(module.category || module.group || "业务模块").trim(),
            title,
            description: String(module.description || module.summary || "").trim(),
            dataObjects: normalizeRecoveryList(module.data_objects || module.dataObjects || module.entities),
            userFlow: normalizeRecoveryList(module.user_flow || module.userFlow || module.operations),
            screens: normalizeRecoveryList(module.pages || module.screens),
            operations: normalizeRecoveryList(module.operations),
            dataFields: normalizeRecoveryList(module.data_fields || module.dataFields),
            rules: normalizeRecoveryList(module.rules),
            entities: normalizeRecoveryList(module.entities),
            children: []
          };
        })
        .filter(Boolean)
    : [];
  return {
    softwareName: String(blueprint.software_name || blueprint.softwareName || blueprint.name || "").trim(),
    productType: String(blueprint.product_type || blueprint.productType || "APP").trim(),
    domain: String(blueprint.industry || blueprint.domain || "").trim(),
    profile: String(blueprint.summary || blueprint.purpose || "").trim(),
    targetUsers: normalizeRecoveryList(blueprint.target_users || blueprint.targetUsers),
    avoidTerms: normalizeRecoveryList(blueprint.avoid_terms || blueprint.avoidTerms),
    modules
  };
}

function normalizeRecoveryList(value) {
  if (!Array.isArray(value)) return [];
  return [...new Set(value.map((item) => String(item || "").trim()).filter(Boolean))].slice(0, 12);
}

function latestTraceFailure(tracePath) {
  try {
    const lines = fs.readFileSync(tracePath, "utf8").trim().split(/\r?\n/).filter(Boolean).slice(-120).reverse();
    for (const line of lines) {
      try {
        const item = JSON.parse(line);
        const event = String(item.event || "");
        if (event.endsWith("_error") || item.error) {
          return {
            stage: String(item.layer || item.event || ""),
            label: String(item.label || ""),
            error: sanitizeErrorMessage(item.error || item.message || "")
          };
        }
      } catch (_error) {
        // Ignore malformed trace rows.
      }
    }
  } catch (_error) {
    // Ignore missing or unreadable trace.
  }
  return { stage: "", label: "", error: "" };
}

function currentModelMode() {
  return String(process.env.SOFT_MODEL_MODE || "gpt").toLowerCase() === "template" ? "template" : "gpt";
}

function normalizeTextProvider(value) {
  const normalized = String(value || "custom").trim().toLowerCase();
  return Object.prototype.hasOwnProperty.call(TEXT_PROVIDER_PRESETS, normalized) ? normalized : "custom";
}

function activeTextProviderId() {
  return normalizeTextProvider(process.env.SOFT_TEXT_PROVIDER || "custom");
}

function activeTextProviderPreset() {
  return TEXT_PROVIDER_PRESETS[activeTextProviderId()] || TEXT_PROVIDER_PRESETS.custom;
}

function providerEnvPrefix(providerId) {
  return normalizeTextProvider(providerId).toUpperCase();
}

function providerProfile(providerId) {
  const id = normalizeTextProvider(providerId);
  const preset = TEXT_PROVIDER_PRESETS[id];
  const prefix = providerEnvPrefix(id);
  const isCustom = id === "custom";
  const activeProvider = activeTextProviderId();
  const baseUrl = isCustom
    ? process.env.SOFT_PROVIDER_CUSTOM_BASE_URL || (activeProvider === "custom" ? process.env.SOFT_MODEL_GPT_BASE_URL || process.env.SOFT_MODEL_GATEWAY_BASE_URL || "" : "")
    : process.env[`SOFT_PROVIDER_${prefix}_BASE_URL`] || preset.defaultBaseUrl;
  const apiKey = isCustom
    ? process.env.SOFT_PROVIDER_CUSTOM_API_KEY || (activeProvider === "custom" ? process.env.SOFT_MODEL_GPT_API_KEY || process.env.SOFT_MODEL_GATEWAY_API_KEY || "" : "")
    : process.env[`SOFT_PROVIDER_${prefix}_API_KEY`] || "";
  const modelName = isCustom
    ? process.env.SOFT_PROVIDER_CUSTOM_MODEL || (activeProvider === "custom" ? process.env.SOFT_MODEL_GPT_NAME || process.env.SOFT_MODEL_GATEWAY_MODEL : "") || preset.defaultModel
    : process.env[`SOFT_PROVIDER_${prefix}_MODEL`] || preset.defaultModel;
  const outlineModelName = isCustom
    ? process.env.SOFT_PROVIDER_CUSTOM_OUTLINE_MODEL || (activeProvider === "custom" ? process.env.SOFT_MODEL_GPT_OUTLINE_NAME : "") || modelName
    : process.env[`SOFT_PROVIDER_${prefix}_OUTLINE_MODEL`] || modelName;
  const frontendModelName = isCustom
    ? process.env.SOFT_PROVIDER_CUSTOM_FRONTEND_MODEL || (activeProvider === "custom" ? process.env.SOFT_MODEL_GPT_FRONTEND_NAME : "") || modelName
    : process.env[`SOFT_PROVIDER_${prefix}_FRONTEND_MODEL`] || modelName;
  return {
    id,
    label: preset.label,
    provider: preset.provider,
    baseUrl,
    apiKey,
    modelName,
    outlineModelName,
    frontendModelName,
    baseUrlConfigured: Boolean(baseUrl),
    apiKeyConfigured: Boolean(apiKey)
  };
}

function providerProfilesForUi() {
  return Object.keys(TEXT_PROVIDER_PRESETS).reduce((result, id) => {
    const profile = providerProfile(id);
    result[id] = {
      label: profile.label,
      modelName: profile.modelName,
      outlineModelName: profile.outlineModelName,
      frontendModelName: profile.frontendModelName,
      baseUrlConfigured: profile.baseUrlConfigured,
      apiKeyConfigured: profile.apiKeyConfigured
    };
    return result;
  }, {});
}

function hiddenConfigStatus(value, configuredLabel = "已配置（内容已隐藏）") {
  return String(value || "").trim() ? configuredLabel : "未配置";
}

function gptConfigError() {
  if (!String(modelPlans.gpt.apiBaseUrl || "").trim()) {
    return "文本模型服务未配置";
  }
  if (!String(modelPlans.gpt.apiKey || "").trim()) {
    return `${activeTextProviderPreset().label} 需要填写 API Key`;
  }
  return "";
}

function activeGenerationStatus() {
  if (activeGenerationTask && !activeGenerationTask.settled) {
    return {
      running: true,
      kind: activeGenerationTask.kind || "materials_generation",
      stage: activeGenerationTask.stage || "start",
      progress: Number(activeGenerationTask.progress || 0),
      message: activeGenerationTask.lastMessage || "后台材料生成任务仍在运行",
      pid: activeGenerationTask.child?.pid || 0,
      title: activeGenerationTask.title || "",
      outputDir: activeGenerationTask.outputDir || "",
      startedAt: activeGenerationTask.startedAt || 0
    };
  }
  return {
    running: false,
    lastResult: lastGenerationResult
  };
}

function rememberGenerationResult(result) {
  lastGenerationResult = compactGenerationResult(result);
  return result;
}

function compactGenerationResult(result) {
  if (!result || typeof result !== "object") return null;
  return {
    ok: Boolean(result.ok),
    cancelled: Boolean(result.cancelled),
    code: Number(result.code || 0),
    stderr: sanitizeErrorMessage(result.stderr || ""),
    zipPath: result.zipPath || "",
    outputDir: result.outputDir || "",
    files: Array.isArray(result.files) ? result.files : [],
    warnings: Array.isArray(result.warnings) ? result.warnings.map((item) => sanitizeErrorMessage(item)) : [],
    checks: result.checks || {},
    validation: result.validation && typeof result.validation === "object" ? result.validation : {},
    seed: result.seed || "",
    randomness: result.randomness || "",
    finishedAt: Date.now()
  };
}

function outlineModelName() {
  return (
    process.env.SOFT_MODEL_GPT_OUTLINE_NAME ||
    process.env.SOFT_MODEL_GPT_OUTLINE_MODEL ||
    process.env.SOFT_MODEL_GATEWAY_OUTLINE_MODEL ||
    modelPlans.gpt.modelName ||
    "gpt-5.5"
  );
}

function frontendModelName() {
  return (
    process.env.SOFT_MODEL_GPT_FRONTEND_NAME ||
    process.env.SOFT_MODEL_GPT_FRONTEND_MODEL ||
    process.env.SOFT_MODEL_GATEWAY_FRONTEND_MODEL ||
    modelPlans.gpt.modelName ||
    "gpt-5.5"
  );
}

function imageModelName() {
  return (
    process.env.SOFT_MODEL_GPT_IMAGE_NAME ||
    process.env.SOFT_MODEL_IMAGE_NAME ||
    process.env.SOFT_MODEL_GPT_IMAGE_MODEL ||
    process.env.SOFT_MODEL_IMAGE_MODEL ||
    "gpt-image-2"
  );
}

function configuredImageApiBaseUrl() {
  return process.env.SOFT_MODEL_GPT_IMAGE_BASE_URL || process.env.SOFT_MODEL_IMAGE_BASE_URL || "";
}

function configuredImageApiKey() {
  return process.env.SOFT_MODEL_GPT_IMAGE_API_KEY || process.env.SOFT_MODEL_IMAGE_API_KEY || "";
}

function outlineTimeoutSeconds() {
  const raw =
    process.env.SOFT_MODEL_GPT_OUTLINE_TIMEOUT_SECONDS ||
    process.env.SOFT_MODEL_GATEWAY_OUTLINE_TIMEOUT_SECONDS ||
    "60";
  const value = Number.parseInt(raw, 10);
  if (!Number.isFinite(value)) return 60;
  return Math.min(120, Math.max(10, value));
}

function frontendWorkerCount() {
  const raw = String(process.env.SOFT_LLM_AI_FRONTEND_WORKERS || "auto").trim().toLowerCase();
  if (!raw || raw === "auto") return "auto";
  const value = Number.parseInt(raw, 10);
  if (!Number.isFinite(value)) return "auto";
  return String(Math.min(3, Math.max(1, value)));
}

function normalizeReasoningEffort(value) {
  const normalized = String(value || "medium").trim().toLowerCase();
  return ["minimal", "low", "medium", "high", "xhigh"].includes(normalized) ? normalized : "medium";
}

function envFlagEnabled(value) {
  return ["1", "true", "yes", "on"].includes(String(value || "").trim().toLowerCase());
}

function sanitizeErrorMessage(value) {
  return String(value || "")
    .replace(/(Bearer\s+)[A-Za-z0-9._~+/=-]+/gi, "$1[已隐藏]")
    .replace(/\b(api[_-]?key|token|secret|authorization)(\s*[:=]\s*['"]?)[^'"\s,;，；)）\]}]+/gi, "$1$2[已隐藏]")
    .replace(/(?:HTTPS?|HTTP)ConnectionPool\(host=['"][^'"]+['"],\s*port=\d+\)/gi, "模型网关连接")
    .replace(/(\b(?:for|with)\s+url:\s*)\/(?:v\d+\/)?(?:chat\/completions|messages|images\/generations)\b[^\s"'<>，。；;、)）\]}]*/gi, "$1[模型接口]")
    .replace(/(for url:\s*)https?:\/\/[^\s"'<>，。；;、)）\]}]+/gi, "$1[模型网关]")
    .replace(/https?:\/\/[^\s"'<>，。；;、)）\]}]+/gi, "[模型网关]")
    .replace(/\s+/g, " ")
    .trim();
}

function applyModelConfig(config) {
  for (const [key, value] of Object.entries(config || {})) {
    if (key.startsWith("SOFT_PROVIDER_") && typeof value === "string") {
      process.env[key] = value;
    }
  }
  if (typeof config.SOFT_MODEL_MODE === "string") {
    process.env.SOFT_MODEL_MODE = config.SOFT_MODEL_MODE;
  }
  if (typeof config.SOFT_MODEL_GPT_API_KEY === "string") {
    process.env.SOFT_MODEL_GPT_API_KEY = config.SOFT_MODEL_GPT_API_KEY;
    modelPlans.gpt.apiKey = config.SOFT_MODEL_GPT_API_KEY;
  }
  if (typeof config.SOFT_MODEL_GPT_NAME === "string" && config.SOFT_MODEL_GPT_NAME) {
    process.env.SOFT_MODEL_GPT_NAME = config.SOFT_MODEL_GPT_NAME;
    modelPlans.gpt.modelName = config.SOFT_MODEL_GPT_NAME;
  }
  if (typeof config.SOFT_MODEL_GPT_BASE_URL === "string") {
    process.env.SOFT_MODEL_GPT_BASE_URL = config.SOFT_MODEL_GPT_BASE_URL;
    modelPlans.gpt.apiBaseUrl = config.SOFT_MODEL_GPT_BASE_URL;
  }
  if (typeof config.SOFT_TEXT_PROVIDER === "string") {
    process.env.SOFT_TEXT_PROVIDER = normalizeTextProvider(config.SOFT_TEXT_PROVIDER);
  }
  if (typeof config.SOFT_MODEL_PROVIDER === "string") {
    process.env.SOFT_MODEL_PROVIDER = config.SOFT_MODEL_PROVIDER;
    modelPlans.gpt.provider = config.SOFT_MODEL_PROVIDER || "custom";
  }
  if (typeof config.SOFT_MODEL_GPT_OUTLINE_NAME === "string") {
    process.env.SOFT_MODEL_GPT_OUTLINE_NAME = config.SOFT_MODEL_GPT_OUTLINE_NAME;
  }
  if (typeof config.SOFT_MODEL_GPT_FRONTEND_NAME === "string") {
    process.env.SOFT_MODEL_GPT_FRONTEND_NAME = config.SOFT_MODEL_GPT_FRONTEND_NAME;
  }
  if (typeof config.SOFT_MODEL_GPT_OUTLINE_TIMEOUT_SECONDS === "string" || typeof config.SOFT_MODEL_GPT_OUTLINE_TIMEOUT_SECONDS === "number") {
    process.env.SOFT_MODEL_GPT_OUTLINE_TIMEOUT_SECONDS = String(config.SOFT_MODEL_GPT_OUTLINE_TIMEOUT_SECONDS);
  }
  if (typeof config.SOFT_MODEL_GPT_REASONING_EFFORT === "string") {
    process.env.SOFT_MODEL_GPT_REASONING_EFFORT = normalizeReasoningEffort(config.SOFT_MODEL_GPT_REASONING_EFFORT);
  }
  if (typeof config.SOFT_LLM_AI_FRONTEND_WORKERS === "string" || typeof config.SOFT_LLM_AI_FRONTEND_WORKERS === "number") {
    process.env.SOFT_LLM_AI_FRONTEND_WORKERS = String(config.SOFT_LLM_AI_FRONTEND_WORKERS);
  }
  if (typeof config.SOFT_MODEL_GPT_IMAGE_NAME === "string") {
    process.env.SOFT_MODEL_GPT_IMAGE_NAME = config.SOFT_MODEL_GPT_IMAGE_NAME;
  }
  if (typeof config.SOFT_MODEL_GPT_IMAGE_BASE_URL === "string") {
    process.env.SOFT_MODEL_GPT_IMAGE_BASE_URL = config.SOFT_MODEL_GPT_IMAGE_BASE_URL;
  }
  if (typeof config.SOFT_MODEL_GPT_IMAGE_API_KEY === "string") {
    process.env.SOFT_MODEL_GPT_IMAGE_API_KEY = config.SOFT_MODEL_GPT_IMAGE_API_KEY;
  }
  if (typeof config.SOFT_MODEL_IMAGE_NAME === "string") {
    process.env.SOFT_MODEL_IMAGE_NAME = config.SOFT_MODEL_IMAGE_NAME;
  }
  if (typeof config.SOFT_MODEL_IMAGE_BASE_URL === "string") {
    process.env.SOFT_MODEL_IMAGE_BASE_URL = config.SOFT_MODEL_IMAGE_BASE_URL;
  }
  if (typeof config.SOFT_MODEL_IMAGE_API_KEY === "string") {
    process.env.SOFT_MODEL_IMAGE_API_KEY = config.SOFT_MODEL_IMAGE_API_KEY;
  }
  if (typeof config.SOFT_ACCOUNT_PROVIDER === "string") {
    process.env.SOFT_ACCOUNT_PROVIDER = config.SOFT_ACCOUNT_PROVIDER;
  }
  if (typeof config.SOFT_MODEL_CONFIG_LOCKED === "string" || typeof config.SOFT_MODEL_CONFIG_LOCKED === "boolean") {
    process.env.SOFT_MODEL_CONFIG_LOCKED = String(config.SOFT_MODEL_CONFIG_LOCKED);
  }
  if (typeof config.SOFT_CUSTOMER_PRESET_CONFIG === "string" || typeof config.SOFT_CUSTOMER_PRESET_CONFIG === "boolean") {
    process.env.SOFT_CUSTOMER_PRESET_CONFIG = String(config.SOFT_CUSTOMER_PRESET_CONFIG);
  }
}

function readJsonConfig(configPath) {
  if (!fs.existsSync(configPath)) return {};
  try {
    return JSON.parse(readUtf8JsonText(configPath));
  } catch (_error) {
    return {};
  }
}

function readUtf8JsonText(configPath) {
  return fs.readFileSync(configPath, "utf8").replace(/^\uFEFF/, "");
}

function writeJsonConfig(configPath, config) {
  fs.mkdirSync(path.dirname(configPath), { recursive: true });
  fs.writeFileSync(configPath, `${JSON.stringify(config, null, 2)}\n`, "utf8");
}

function orderedConfigPaths(configDir) {
  if (!configDir) return [];
  return [
    path.join(configDir, "production.json"),
    path.join(configDir, "desktop.local.json")
  ].sort((left, right) => configMtime(left) - configMtime(right));
}

function configMtime(configPath) {
  try {
    return fs.statSync(configPath).mtimeMs || 0;
  } catch (_error) {
    return 0;
  }
}

function writeRuntimeLog(event, payload = {}) {
  if (!envFlagEnabled(process.env.SOFT_DESKTOP_DEBUG_LOG || "1")) return;
  try {
    const logPath = path.join(app.getPath("userData"), "runtime-events.jsonl");
    const safePayload = {};
    for (const [key, value] of Object.entries(payload || {})) {
      if (/key|token|secret|baseurl|url/i.test(key)) continue;
      safePayload[key] = typeof value === "string" ? value.slice(0, 500) : value;
    }
    fs.appendFileSync(
      logPath,
      `${JSON.stringify({ ts: new Date().toISOString(), event, ...safePayload }, null, 0)}\n`,
      "utf8"
    );
  } catch (_error) {
    // Debug logging must never block generation.
  }
}

function fetchJson(url, token, redirectCount = 0) {
  return new Promise((resolve, reject) => {
    const client = url.startsWith("https:") ? https : http;
    const request = client.request(
      url,
      {
        method: "GET",
        headers: {
          Accept: "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {})
        },
        timeout: 10000
      },
      (response) => {
        let body = "";
        response.setEncoding("utf8");
        if ([301, 302, 303, 307, 308].includes(response.statusCode) && response.headers.location) {
          response.resume();
          if (redirectCount >= 4) {
            reject(new Error(`HTTP ${response.statusCode}: 余额接口重定向次数过多`));
            return;
          }
          try {
            const nextUrl = new URL(response.headers.location, url).toString();
            resolve(fetchJson(nextUrl, token, redirectCount + 1));
          } catch (error) {
            reject(error);
          }
          return;
        }
        response.on("data", (chunk) => {
          body += chunk;
        });
        response.on("end", () => {
          if (response.statusCode < 200 || response.statusCode >= 300) {
            reject(new Error(`HTTP ${response.statusCode}: ${body.slice(0, 200)}`));
            return;
          }
          try {
            resolve(JSON.parse(body));
          } catch (error) {
            reject(error);
          }
        });
      }
    );
    request.on("timeout", () => {
      request.destroy(new Error("请求余额接口超时"));
    });
    request.on("error", reject);
    request.end();
  });
}

function normalizeBalanceResponse(data) {
  if (data?.success === false || data?.code === false || data?.error) {
    const message = data?.message || data?.error?.message || "余额接口返回失败";
    throw new Error(message);
  }
  const payload = data && typeof data === "object" && data.data && typeof data.data === "object" ? data.data : data;
  const balanceLabel =
    payload.balanceLabel ||
    payload.balance_label ||
    (typeof payload.balanceTokens === "number" ? `${payload.balanceTokens.toLocaleString("zh-CN")} tokens` : "") ||
    (typeof payload.balance_tokens === "number" ? `${payload.balance_tokens.toLocaleString("zh-CN")} tokens` : "") ||
    (payload.unlimited_quota ? "不限额度" : "") ||
    (typeof payload.total_available === "number" ? `${payload.total_available.toLocaleString("zh-CN")} 额度` : "") ||
    (typeof payload.remain_quota === "number" ? `${payload.remain_quota.toLocaleString("zh-CN")} 额度` : "") ||
    (typeof payload.quota === "number" && typeof payload.used_quota === "number"
      ? `${Math.max(0, payload.quota - payload.used_quota).toLocaleString("zh-CN")} 额度`
      : "") ||
    "";
  return {
    status: "connected",
    accountName: payload.accountName || payload.account_name || payload.name || "模型账户",
    balanceLabel: balanceLabel || "余额已连接",
    updatedAt: payload.updatedAt || payload.updated_at || new Date().toLocaleString("zh-CN", { hour12: false }),
    expiresAt: payload.expiresAt || payload.expires_at || ""
  };
}

function rootUrlFromGateway(baseUrl) {
  if (!baseUrl) return "";
  try {
    const url = new URL(baseUrl);
    url.pathname = url.pathname.replace(/\/v1\/?$/, "").replace(/\/+$/, "");
    url.search = "";
    url.hash = "";
    return url.toString().replace(/\/+$/, "");
  } catch (_error) {
    return "";
  }
}

function loadDesktopConfig() {
  const exeConfigDir = path.join(path.dirname(process.execPath), "config");
  const externalConfigDir = process.env.SOFT_DESKTOP_CONFIG_DIR || "";
  const savedConfigDir = externalConfigDir || userConfigDir();
  const initialEnv = { ...process.env };
  const loadedConfigKeys = new Set();
  const configPaths = [
    ...orderedConfigPaths(path.join(rootDir, "config")),
    ...orderedConfigPaths(exeConfigDir),
    ...orderedConfigPaths(savedConfigDir)
  ];
  for (const configPath of configPaths) {
    if (!fs.existsSync(configPath)) {
      writeRuntimeLog("desktop_config_missing", { configPath });
      continue;
    }
    try {
      const config = JSON.parse(readUtf8JsonText(configPath));
      writeRuntimeLog("desktop_config_loaded", {
        configPath,
        modelName: config.SOFT_MODEL_GPT_NAME || "",
        outlineModelName: config.SOFT_MODEL_GPT_OUTLINE_NAME || "",
        frontendModelName: config.SOFT_MODEL_GPT_FRONTEND_NAME || "",
        outlineTimeoutSeconds: config.SOFT_MODEL_GPT_OUTLINE_TIMEOUT_SECONDS || ""
      });
      for (const [key, value] of Object.entries(config)) {
        if (typeof value === "string" && value) {
          process.env[key] = value;
          loadedConfigKeys.add(key);
        }
      }
    } catch (error) {
      console.warn(`读取桌面配置失败：${configPath}`, error.message);
      writeRuntimeLog("desktop_config_failed", { configPath, message: error.message });
    }
  }
  for (const [key, value] of Object.entries(initialEnv)) {
    if (!loadedConfigKeys.has(key)) {
      process.env[key] = value;
    }
  }
  writeRuntimeLog("desktop_config_final", {
    modelName: process.env.SOFT_MODEL_GPT_NAME || "",
    outlineModelName: process.env.SOFT_MODEL_GPT_OUTLINE_NAME || "",
    frontendModelName: process.env.SOFT_MODEL_GPT_FRONTEND_NAME || "",
    outlineTimeoutSeconds: process.env.SOFT_MODEL_GPT_OUTLINE_TIMEOUT_SECONDS || ""
  });
}

function modelCatalogUrls(baseUrl) {
  if (!String(baseUrl || "").trim()) return [];
  try {
    const parsed = new URL(String(baseUrl).trim());
    parsed.search = "";
    parsed.hash = "";
    parsed.pathname = parsed.pathname
      .replace(/\/(chat\/completions|messages|models)\/?$/i, "")
      .replace(/\/+$/, "");
    const urls = [`${parsed.toString().replace(/\/+$/, "")}/models`];
    if (!/\/v1$/i.test(parsed.pathname)) {
      const v1 = new URL(parsed.toString());
      v1.pathname = `${v1.pathname.replace(/\/+$/, "")}/v1/models`.replace(/\/+/g, "/");
      urls.push(v1.toString());
    }
    return [...new Set(urls)];
  } catch (_error) {
    return [];
  }
}

function fetchCatalogJson(url, headers, redirectCount = 0, allowedOrigin = "") {
  return new Promise((resolve, reject) => {
    let parsedUrl;
    try {
      parsedUrl = new URL(url);
    } catch (error) {
      reject(error);
      return;
    }
    const origin = allowedOrigin || parsedUrl.origin;
    if (parsedUrl.origin !== origin) {
      reject(new Error("模型目录重定向到其他站点，已停止发送认证信息"));
      return;
    }
    const client = parsedUrl.protocol === "https:" ? https : http;
    const request = client.request(
      parsedUrl,
      {
        method: "GET",
        headers: {
          Accept: "application/json",
          "User-Agent": "soft-copyright-generator-model-catalog/1.0",
          ...headers
        },
        timeout: 15000
      },
      (response) => {
        let body = "";
        response.setEncoding("utf8");
        if ([301, 302, 303, 307, 308].includes(response.statusCode) && response.headers.location) {
          response.resume();
          if (redirectCount >= 4) {
            const error = new Error("模型目录重定向次数过多");
            error.statusCode = response.statusCode;
            reject(error);
            return;
          }
          try {
            const nextUrl = new URL(response.headers.location, parsedUrl).toString();
            resolve(fetchCatalogJson(nextUrl, headers, redirectCount + 1, origin));
          } catch (error) {
            reject(error);
          }
          return;
        }
        response.on("data", (chunk) => {
          body += chunk;
        });
        response.on("end", () => {
          if (response.statusCode < 200 || response.statusCode >= 300) {
            const error = new Error(`模型目录返回 HTTP ${response.statusCode}`);
            error.statusCode = response.statusCode;
            reject(error);
            return;
          }
          try {
            resolve(JSON.parse(body));
          } catch (_error) {
            reject(new Error("模型目录没有返回有效 JSON"));
          }
        });
      }
    );
    request.on("timeout", () => request.destroy(new Error("模型目录请求超时")));
    request.on("error", reject);
    request.end();
  });
}

function normalizeModelCatalog(data) {
  const rows = Array.isArray(data)
    ? data
    : Array.isArray(data?.data)
      ? data.data
      : Array.isArray(data?.models)
        ? data.models
        : [];
  return [...new Set(rows.map((item) => String(typeof item === "string" ? item : item?.id || item?.name || "").trim()).filter(Boolean))]
    .sort((left, right) => left.localeCompare(right, "en", { numeric: true }));
}

async function fetchAvailableModels(baseUrl, apiKey) {
  const urls = modelCatalogUrls(baseUrl);
  if (!urls.length || !String(apiKey || "").trim()) {
    throw new Error("文本模型服务或 API Key 未配置");
  }
  const authProfiles = [
    { Authorization: `Bearer ${apiKey}` },
    { "x-api-key": apiKey, "anthropic-version": "2023-06-01" }
  ];
  let lastError = null;
  for (const url of urls) {
    for (const headers of authProfiles) {
      try {
        const models = normalizeModelCatalog(await fetchCatalogJson(url, headers));
        if (models.length) return models;
        lastError = new Error("模型目录为空");
      } catch (error) {
        lastError = error;
      }
    }
  }
  throw lastError || new Error("未能读取模型目录");
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 860,
    minWidth: 1080,
    minHeight: 720,
    autoHideMenuBar: true,
    backgroundColor: "#f5f7fb",
    icon: app.isPackaged ? path.join(resourceRoot, "icon.png") : path.join(sourceRoot, "build", "icon.png"),
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false
    }
  });
  mainWindow.setMenu(null);

  mainWindow.on("closed", () => {
    mainWindow = null;
  });

  if (isDev) {
    mainWindow.loadURL(process.env.VITE_DEV_SERVER_URL || "http://127.0.0.1:5173");
  } else {
    mainWindow.loadFile(path.join(appRoot, "dist", "index.html"));
  }
}

app.whenReady().then(createWindow);

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});

ipcMain.handle("cancel-generation", async () => {
  if (cancelTask(activeGenerationTask, "已请求中止材料包生成，正在停止后台进程")) {
    return { ok: true, target: "materials" };
  }
  if (cancelTask(activeOutlineTask, "已请求中止蓝图生成，正在停止后台进程")) {
    return { ok: true, target: "outline" };
  }
  return { ok: false, message: "当前没有正在生成的任务" };
});

ipcMain.handle("get-generation-status", async (_event) => {
  if (activeGenerationTask && !activeGenerationTask.settled) {
    activeGenerationTask.sender = _event.sender;
  }
  return activeGenerationStatus();
});

ipcMain.handle("generate-materials", async (_event, payload) => {
  const requestedMode = payload?.modelPlan === "template" ? "template" : "gpt";
  const templateMode = requestedMode === "template";
  if (activeGenerationTask && !activeGenerationTask.settled) {
    return {
      ok: false,
      busy: true,
      code: -4,
      stdout: "",
      stderr: "已有材料包生成任务正在运行，请先中止当前任务。",
      zipPath: "",
      outputDir: activeGenerationTask.outputDir || "",
      warnings: [],
      checks: {},
      files: [],
      blueprintSource: templateMode ? "local-template" : "gpt",
      manualSource: templateMode ? "local-template" : "gpt",
      activeStatus: activeGenerationStatus()
    };
  }
  const configError = templateMode ? "" : gptConfigError();
  if (configError) {
    return {
      ok: false,
      zipPath: "",
      outputDir: "",
      warnings: [],
      checks: {},
      stdout: "",
      stderr: configError,
      files: [],
      blueprintSource: templateMode ? "local-template" : "gpt",
      manualSource: templateMode ? "local-template" : "gpt"
    };
  }
  const modelPlan = modelPlans[requestedMode];
  const args = [
    path.join(rootDir, "backend", "generate_materials.py"),
    "--name",
    payload.name,
    "--version",
    payload.version || "V1.0",
    "--language",
    payload.language || "自动选择",
    "--product-type",
    payload.productType || "智慧城市软件",
    "--software-category",
    payload.softwareCategory || "应用软件",
    "--feature-hint",
    payload.featureHint || "",
    "--model-provider",
    modelPlan.provider || "custom",
    "--model-name",
    modelPlan.modelName || payload.modelName || "gpt-5.5",
    "--randomness",
    payload.randomness || "standard",
    "--output-root",
    payload.outputRoot || generationOutputRoot()
  ];
  if (payload.businessPlan && Array.isArray(payload.businessPlan.modules) && payload.businessPlan.modules.length) {
    const outlinePath = path.join(app.getPath("temp"), `soft-confirmed-outline-${Date.now()}-${Math.random().toString(36).slice(2)}.json`);
    fs.writeFileSync(outlinePath, JSON.stringify(payload.businessPlan, null, 2), "utf8");
    args.push("--confirmed-outline-json", outlinePath);
  }

  if (payload.seed) {
    args.push("--seed", payload.seed);
  }
  if (payload.resumeOutputDir) {
    args.push("--resume-output-dir", payload.resumeOutputDir);
  }

  return new Promise((resolve) => {
    const sender = _event.sender;
    const child = spawn(bundledPythonExecutable(), args, {
      cwd: app.isPackaged ? process.resourcesPath : rootDir,
      windowsHide: true,
      env: {
        ...process.env,
        ...(packagedPlaywrightBrowsersPath() ? { PLAYWRIGHT_BROWSERS_PATH: packagedPlaywrightBrowsersPath() } : {}),
        ...(packagedLibreOfficePath() ? { SOFT_LIBREOFFICE_PATH: packagedLibreOfficePath() } : {}),
        SOFT_MODEL_GPT_BASE_URL: templateMode ? "" : modelPlan.apiBaseUrl || process.env.SOFT_MODEL_GPT_BASE_URL || "",
        SOFT_MODEL_GPT_API_KEY: templateMode ? "" : modelPlan.apiKey || process.env.SOFT_MODEL_GPT_API_KEY || "",
        SOFT_MODEL_GPT_FRONTEND_NAME: frontendModelName(),
        SOFT_MODEL_GPT_IMAGE_BASE_URL: templateMode ? "" : process.env.SOFT_MODEL_GPT_IMAGE_BASE_URL || process.env.SOFT_MODEL_IMAGE_BASE_URL || "",
        SOFT_MODEL_GPT_IMAGE_API_KEY: templateMode ? "" : process.env.SOFT_MODEL_GPT_IMAGE_API_KEY || process.env.SOFT_MODEL_IMAGE_API_KEY || "",
        SOFT_MODEL_GPT_IMAGE_NAME: process.env.SOFT_MODEL_GPT_IMAGE_NAME || process.env.SOFT_MODEL_IMAGE_NAME || "gpt-image-2",
        SOFT_MODEL_IMAGE_BASE_URL: templateMode ? "" : process.env.SOFT_MODEL_IMAGE_BASE_URL || process.env.SOFT_MODEL_GPT_IMAGE_BASE_URL || "",
        SOFT_MODEL_IMAGE_API_KEY: templateMode ? "" : process.env.SOFT_MODEL_IMAGE_API_KEY || process.env.SOFT_MODEL_GPT_IMAGE_API_KEY || "",
        SOFT_MODEL_IMAGE_NAME: process.env.SOFT_MODEL_IMAGE_NAME || process.env.SOFT_MODEL_GPT_IMAGE_NAME || "gpt-image-2",
        SOFT_GENERATION_PROFILE: process.env.SOFT_GENERATION_PROFILE || "balanced",
        SOFT_LLM_BATCH_WORKERS: process.env.SOFT_LLM_BATCH_WORKERS || "2",
        SOFT_LLM_AI_FRONTEND_WORKERS: process.env.SOFT_LLM_AI_FRONTEND_WORKERS || "auto",
        SOFT_LLM_RETRY_COUNT: process.env.SOFT_LLM_RETRY_COUNT || "3",
        SOFT_LLM_IMAGE_RETRY_COUNT: process.env.SOFT_LLM_IMAGE_RETRY_COUNT || process.env.SOFT_IMAGE_RETRY_COUNT || "3",
        SOFT_LLM_IMAGE_TIMEOUT_SECONDS: process.env.SOFT_LLM_IMAGE_TIMEOUT_SECONDS || process.env.SOFT_IMAGE_TIMEOUT_SECONDS || "220",
        SOFT_LLM_AI_FRONTEND_TIMEOUT_SECONDS: process.env.SOFT_LLM_AI_FRONTEND_TIMEOUT_SECONDS || process.env.SOFT_LLM_CODEGEN_TIMEOUT_SECONDS || "120",
        SOFT_LLM_STREAM_HARD_TIMEOUT_SECONDS: process.env.SOFT_LLM_STREAM_HARD_TIMEOUT_SECONDS || "600",
        SOFT_LLM_AI_FRONTEND_RETRY_COUNT: process.env.SOFT_LLM_AI_FRONTEND_RETRY_COUNT || "0",
        SOFT_ELECTRON_NODE: process.execPath,
        SOFT_NODE_MODULE_ROOT: path.join(app.getAppPath(), "node_modules"),
        ...(packagedEsbuildBinaryPath() ? { ESBUILD_BINARY_PATH: packagedEsbuildBinaryPath() } : {}),
        PYTHONIOENCODING: "utf-8"
      }
    });
    const task = {
      kind: "materials_generation",
      child,
      sender,
      title: payload.name || "",
      outputDir: payload.resumeOutputDir || "",
      startedAt: Date.now(),
      stage: "start",
      progress: 0,
      lastMessage: "材料包生成已启动",
      cancelled: false,
      settled: false
    };
    activeGenerationTask = task;
    let stdout = "";
    let stderr = "";
    let stdoutBuffer = "";

    function handleStdoutLine(line) {
      const eventMatch = line.match(/^EVENT_JSON:(\{.+\})$/);
      if (eventMatch) {
        try {
          const event = JSON.parse(eventMatch[1]);
          task.stage = event.stage || task.stage;
          task.progress = Number(event.progress || task.progress || 0);
          task.lastMessage = event.message || task.lastMessage;
          if (event.output_dir || event.outputDir) task.outputDir = event.output_dir || event.outputDir;
          sendGenerateEvent(sender, event);
        } catch (_error) {
          sendGenerateEvent(sender, { stage: "log", progress: 0, message: line });
        }
      }
    }

    child.stdout.on("data", (chunk) => {
      const text = chunk.toString("utf8");
      stdout += text;
      stdoutBuffer += text;
      const lines = stdoutBuffer.split(/\r?\n/);
      stdoutBuffer = lines.pop() || "";
      for (const line of lines) {
        handleStdoutLine(line.trim());
      }
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString("utf8");
    });
    child.on("error", (error) => {
      if (task.settled) return;
      task.settled = true;
      if (activeGenerationTask === task) activeGenerationTask = null;
      const result = rememberGenerationResult({
        ok: false,
        code: -1,
        stdout,
        stderr: sanitizeErrorMessage(stderr || String(error?.message || error)),
        zipPath: "",
        outputDir: task.outputDir || payload.resumeOutputDir || "",
        warnings: [],
        checks: {},
        files: [],
        blueprintSource: templateMode ? "local-template" : "gpt",
        manualSource: templateMode ? "local-template" : "gpt"
      });
      sendGenerateEvent(task.sender, {
        stage: "error",
        progress: task.progress || 0,
        message: result.stderr || "材料生成进程启动失败",
        result: compactGenerationResult(result)
      });
      resolve(result);
    });
    child.on("close", (code) => {
      if (task.settled) return;
      task.settled = true;
      if (activeGenerationTask === task) activeGenerationTask = null;
      if (stdoutBuffer.trim()) {
        handleStdoutLine(stdoutBuffer.trim());
      }
      if (task.cancelled) {
        const result = rememberGenerationResult({
          ok: false,
          cancelled: true,
          code: -15,
          stdout,
          stderr: "已中止生成任务",
          zipPath: "",
          outputDir: task.outputDir || payload.resumeOutputDir || "",
          warnings: [],
          checks: {},
          files: [],
          blueprintSource: templateMode ? "local-template" : "gpt",
          manualSource: templateMode ? "local-template" : "gpt",
          featureHint: payload.featureHint || "",
          featureHintMeta: { cancelled: true },
          seed: "",
          randomness: payload.randomness || "standard"
        });
        sendGenerateEvent(task.sender, {
          stage: "cancelled",
          progress: task.progress || 0,
          message: "已中止生成任务",
          result: compactGenerationResult(result)
        });
        resolve(result);
        return;
      }
      const resultMatch = stdout.match(/RESULT_JSON:(\{.+\})/);
      let parsed = {};
      if (resultMatch) {
        try {
          parsed = JSON.parse(resultMatch[1]);
        } catch (_error) {
          parsed = {};
        }
      }
      const zipPath = parsed.zip_path ? path.resolve(rootDir, parsed.zip_path) : "";
      const outputDir = parsed.output_dir ? path.resolve(rootDir, parsed.output_dir) : "";
      const files = Array.isArray(parsed.files)
        ? parsed.files.map((filePath) => path.resolve(rootDir, filePath))
        : [];
      const validation = parsed.validation && typeof parsed.validation === "object" ? { ...parsed.validation } : {};
      if (validation.path) {
        validation.path = path.resolve(rootDir, validation.path);
      }
      if (validation.manifest_path) {
        validation.manifest_path = path.resolve(rootDir, validation.manifest_path);
      }
      const resultJsonReady = Boolean(resultMatch);
      const zipReady = Boolean(zipPath && fs.existsSync(zipPath) && fs.statSync(zipPath).isFile());
      const completionError =
        code === 0 && !resultJsonReady
          ? "生成进程已结束，但未返回最终结果，未确认材料包完成。"
          : code === 0 && !zipReady
            ? "生成进程已结束，但未返回可用材料包文件。"
            : "";
      const result = rememberGenerationResult({
        ok: code === 0 && resultJsonReady && zipReady,
        code,
        stdout,
        stderr: sanitizeErrorMessage(parsed.message || stderr || completionError || (code === 0 ? "" : "材料生成失败")),
        zipPath,
        outputDir: outputDir || task.outputDir || payload.resumeOutputDir || (zipPath ? path.dirname(zipPath) : ""),
        warnings: parsed.warnings || [],
        checks: parsed.checks || {},
        validation,
        files,
        blueprintSource: parsed.blueprint_source || (templateMode ? "local-template" : "gpt"),
        manualSource: parsed.manual_source || (templateMode ? "local-template" : "gpt"),
        technicalArchitecture: parsed.technical_architecture || {},
        featureHint: parsed.feature_hint || payload.featureHint || "",
        featureHintMeta: parsed.feature_hint_meta || {},
        seed: parsed.seed || "",
        randomness: parsed.randomness || payload.randomness || "standard"
      });
      sendGenerateEvent(task.sender, {
        stage: result.ok ? "done" : "error",
        progress: result.ok ? 100 : task.progress || 0,
        message: result.ok ? "生成完成" : result.stderr || "材料生成失败",
        output_dir: result.outputDir || "",
        zip_path: result.zipPath || "",
        checks: result.checks || {},
        warnings: result.warnings || [],
        result: compactGenerationResult(result)
      });
      resolve(result);
    });
  });
});

ipcMain.handle("infer-feature-hint", async (_event, payload) => {
  if (activeOutlineTask && !activeOutlineTask.settled) {
    return {
      ok: false,
      code: -4,
      stderr: "已有蓝图生成任务正在运行，请先中止当前任务。",
      message: "已有蓝图生成任务正在运行，请先中止当前任务。",
      featureHint: "",
      meta: { feature_hint_source: "llm-busy", requires_gpt: true }
    };
  }
  writeRuntimeLog("outline_request_received", {
    nameLength: String(payload?.name || "").length,
    productType: payload?.productType || "",
    hasFeatureHint: Boolean(payload?.featureHint)
  });
  const configError = gptConfigError();
  if (configError) {
    writeRuntimeLog("outline_request_config_error", { message: configError });
    return {
      ok: false,
      code: -1,
      stderr: configError,
      message: configError,
      featureHint: "",
      meta: { requires_gpt_config: true }
    };
  }
  const modelPlan = modelPlans.gpt;
  const outlineModel = String(payload?.modelName || "").trim() || outlineModelName();
  const requestTimeoutSeconds = payload?.timeoutSeconds
    ? Math.min(120, Math.max(10, Number.parseInt(payload.timeoutSeconds, 10) || outlineTimeoutSeconds()))
    : outlineTimeoutSeconds();
  writeRuntimeLog("outline_request_start", {
    outlineModel,
    requestTimeoutSeconds,
    nameLength: String(payload?.name || "").length
  });
  const args = [
    path.join(rootDir, "backend", "infer_feature_hint.py"),
    "--name",
    payload.name || "",
    "--product-type",
    payload.productType || "",
    "--feature-hint",
    payload.featureHint || "",
    "--model-provider",
    modelPlan.provider || "custom",
    "--model-name",
    outlineModel || payload.modelName || "gpt-5.5",
    "--timeout-seconds",
    String(requestTimeoutSeconds),
    "--retry-count",
    "0",
    "--require-llm",
    "--min-blueprint-modules",
    "0"
  ];
  return new Promise((resolve) => {
    const sender = _event.sender;
    let settled = false;
    const startedAt = Date.now();
    const child = spawn(bundledPythonExecutable(), args, {
      cwd: app.isPackaged ? process.resourcesPath : rootDir,
      windowsHide: true,
      env: {
        ...process.env,
        SOFT_MODEL_GPT_BASE_URL: modelPlan.apiBaseUrl || process.env.SOFT_MODEL_GPT_BASE_URL || "",
        SOFT_MODEL_GPT_API_KEY: modelPlan.apiKey || process.env.SOFT_MODEL_GPT_API_KEY || "",
        PYTHONIOENCODING: "utf-8"
      }
    });
    const task = {
      kind: "outline_generation",
      child,
      sender,
      stage: "outline",
      progress: 36,
      cancelled: false,
      settled: false
    };
    activeOutlineTask = task;
    let stdout = "";
    let stderr = "";
    sendGenerateEvent(sender, {
      stage: "outline",
      progress: 36,
      message: `已启动 GPT 蓝图生成进程，使用蓝图模型 ${outlineModel} 先识别名称语义，再生成模块草案`
    });
    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString("utf8");
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString("utf8");
    });
    const timeout = setTimeout(() => {
      if (settled) return;
      settled = true;
      task.settled = true;
      if (activeOutlineTask === task) activeOutlineTask = null;
      child.kill();
      writeRuntimeLog("outline_request_timeout", { outlineModel, requestTimeoutSeconds });
      sendGenerateEvent(sender, {
        stage: "outline",
        progress: 0,
        message: "GPT 蓝图生成超时，已停止本次请求"
      });
      resolve({
        ok: false,
        code: -2,
        stderr: sanitizeErrorMessage(stderr),
        message: "GPT 名称理解超时，请稍后重试或检查模型网关响应速度",
        featureHint: "",
        meta: { feature_hint_source: "llm-timeout", requires_gpt: true }
      });
    }, (requestTimeoutSeconds + 15) * 1000);
    child.on("error", (error) => {
      if (settled) return;
      settled = true;
      task.settled = true;
      if (activeOutlineTask === task) activeOutlineTask = null;
      clearTimeout(timeout);
      writeRuntimeLog("outline_process_error", { message: String(error?.message || error) });
      sendGenerateEvent(sender, {
        stage: "outline",
        progress: 0,
        message: "GPT 蓝图生成进程启动失败"
      });
      resolve({
        ok: false,
        code: -1,
        stderr: sanitizeErrorMessage(stderr || String(error?.message || error)),
        message: "GPT 名称理解进程启动失败",
        featureHint: "",
        meta: { feature_hint_source: "llm-process-error", requires_gpt: true }
      });
    });
    child.on("close", (code) => {
      if (settled) return;
      settled = true;
      task.settled = true;
      if (activeOutlineTask === task) activeOutlineTask = null;
      clearTimeout(timeout);
      if (task.cancelled) {
        sendGenerateEvent(sender, {
          stage: "outline",
          progress: task.progress || 0,
          message: "已中止蓝图生成"
        });
        resolve({
          ok: false,
          cancelled: true,
          code: -15,
          stderr: sanitizeErrorMessage(stderr),
          message: "已中止蓝图生成",
          featureHint: "",
          meta: { feature_hint_source: "llm-cancelled", requires_gpt: true, cancelled: true }
        });
        return;
      }
      const resultMatch = stdout.match(/RESULT_JSON:(\{.+\})/);
      let parsed = {};
      if (resultMatch) {
        try {
          parsed = JSON.parse(resultMatch[1]);
        } catch (_error) {
          parsed = {};
        }
      }
      sendGenerateEvent(sender, {
        stage: "outline",
        progress: code === 0 && Boolean(parsed.feature_hint) ? 68 : 0,
        message:
          code === 0 && Boolean(parsed.feature_hint)
            ? `GPT 两段式蓝图已返回，耗时 ${Math.round((Date.now() - startedAt) / 1000)} 秒`
            : "GPT 蓝图生成未返回合格模块，请重试或检查模型响应"
      });
      writeRuntimeLog("outline_process_close", {
        code,
        ok: code === 0 && Boolean(parsed.feature_hint),
        message: parsed.message || "",
        hasFeatureHint: Boolean(parsed.feature_hint)
      });
      resolve({
        ok: code === 0 && Boolean(parsed.feature_hint),
        code,
        stderr: sanitizeErrorMessage(stderr),
        message:
          code === 0 && Boolean(parsed.feature_hint)
            ? ""
            : parsed.message || "GPT 名称理解未生成合格蓝图，请重试；要求至少 8 个不重复的业务模块",
        featureHint: parsed.feature_hint || "",
        meta: parsed.meta || {}
      });
    });
  });
});

ipcMain.handle("get-model-config", async () => {
  const imageApiBaseUrl = configuredImageApiBaseUrl();
  const imageApiKey = configuredImageApiKey();
  const textProvider = activeTextProviderId();
  return {
    mode: currentModelMode(),
    textProvider,
    providerProfiles: providerProfilesForUi(),
    modelName: modelPlans.gpt.modelName || "gpt-5.5",
    outlineModelName: outlineModelName(),
    frontendModelName: frontendModelName(),
    frontendWorkers: frontendWorkerCount(),
    outlineTimeoutSeconds: outlineTimeoutSeconds(),
    reasoningEffort: normalizeReasoningEffort(process.env.SOFT_MODEL_GPT_REASONING_EFFORT),
    apiBaseUrl: "",
    apiBaseUrlMasked: hiddenConfigStatus(modelPlans.gpt.apiBaseUrl, "已配置（地址已隐藏）"),
    apiBaseUrlConfigured: Boolean(modelPlans.gpt.apiBaseUrl),
    apiKey: "",
    apiKeyConfigured: Boolean(modelPlans.gpt.apiKey),
    imageModelName: imageModelName(),
    imageUseTextApi: !imageApiBaseUrl && !imageApiKey,
    imageApiBaseUrl: "",
    imageApiBaseUrlMasked: hiddenConfigStatus(imageApiBaseUrl, "已单独配置（地址已隐藏）"),
    imageApiBaseUrlConfigured: Boolean(imageApiBaseUrl),
    imageApiKey: "",
    imageApiKeyConfigured: Boolean(imageApiKey),
    provider: process.env.SOFT_ACCOUNT_PROVIDER || "newapi",
    preset: envFlagEnabled(process.env.SOFT_CUSTOMER_PRESET_CONFIG)
  };
});

ipcMain.handle("list-available-models", async () => {
  const configError = gptConfigError();
  if (configError) {
    return { ok: false, models: [], message: configError };
  }
  try {
    const models = await fetchAvailableModels(modelPlans.gpt.apiBaseUrl, modelPlans.gpt.apiKey);
    writeRuntimeLog("model_catalog_loaded", { count: models.length, provider: activeTextProviderId() });
    return { ok: true, models, count: models.length };
  } catch (error) {
    writeRuntimeLog("model_catalog_error", { message: sanitizeErrorMessage(error?.message || "") });
    return {
      ok: false,
      models: [],
      message: sanitizeErrorMessage(error?.message || "模型列表拉取失败")
    };
  }
});

ipcMain.handle("list-recoverable-tasks", async () => {
  return {
    ok: true,
    tasks: listRecoverableTasks()
  };
});

ipcMain.handle("delete-recoverable-task", async (_event, payload) => {
  try {
    return dismissRecoverableTask(payload);
  } catch (error) {
    return {
      ok: false,
      message: sanitizeErrorMessage(error?.message || "删除恢复记录失败")
    };
  }
});

ipcMain.handle("save-model-config", async (_event, payload) => {
  const mode = payload?.mode === "template" ? "template" : "gpt";
  const previousTextProvider = activeTextProviderId();
  const previousProviderProfile = providerProfile(previousTextProvider);
  const textProvider = normalizeTextProvider(payload?.textProvider || activeTextProviderId());
  const preset = TEXT_PROVIDER_PRESETS[textProvider];
  const existingProvider = providerProfile(textProvider);
  const modelName = String(payload?.modelName || existingProvider.modelName || preset.defaultModel).trim();
  const outlineModel = String(payload?.outlineModelName || payload?.outlineModel || "").trim();
  const frontendModel = String(payload?.frontendModelName || payload?.frontendModel || "").trim();
  const frontendWorkersRaw = String(payload?.frontendWorkers || "auto").trim().toLowerCase();
  const frontendWorkers = frontendWorkersRaw === "auto"
    ? "auto"
    : String(Math.min(3, Math.max(1, Number.parseInt(frontendWorkersRaw, 10) || 1)));
  const outlineTimeout = Math.min(120, Math.max(10, Number.parseInt(payload?.outlineTimeoutSeconds || "60", 10) || 60));
  const reasoningEffort = normalizeReasoningEffort(payload?.reasoningEffort);
  const apiBaseUrl = String(
    textProvider === "custom"
      ? payload?.apiBaseUrl || existingProvider.baseUrl || ""
      : existingProvider.baseUrl || preset.defaultBaseUrl
  ).trim();
  const apiKey = String(payload?.apiKey || existingProvider.apiKey || "").trim();
  const existingImageApiBaseUrl = configuredImageApiBaseUrl();
  const existingImageApiKey = configuredImageApiKey();
  const imageModel = String(payload?.imageModelName || imageModelName() || "gpt-image-2").trim();
  const imageUseTextApi =
    typeof payload?.imageUseTextApi === "boolean"
      ? payload.imageUseTextApi
      : !existingImageApiBaseUrl && !existingImageApiKey;
  const imageApiBaseUrl = imageUseTextApi
    ? ""
    : String(payload?.imageApiBaseUrl || existingImageApiBaseUrl || "").trim();
  const imageApiKey = imageUseTextApi
    ? ""
    : String(payload?.imageApiKey || existingImageApiKey || "").trim();
  if (mode === "gpt" && !apiBaseUrl) {
    return { ok: false, message: "文本模型服务未配置" };
  }
  if (mode === "gpt" && !apiKey) {
    return { ok: false, message: `${preset.label} 需要填写 API Key` };
  }
  if (mode === "gpt" && textProvider !== "custom" && imageUseTextApi) {
    return { ok: false, message: `${preset.label} 不提供本流程要求的 gpt-image-2，请使用独立图片 API` };
  }
  if (mode === "gpt" && !imageUseTextApi && !imageApiBaseUrl) {
    return { ok: false, message: "独立图片模型需要填写图片 API 请求地址" };
  }
  if (mode === "gpt" && !imageUseTextApi && !imageApiKey) {
    return { ok: false, message: "独立图片模型需要填写图片 API Key" };
  }

  const configPath = defaultConfigPath();
  const providerPrefix = providerEnvPrefix(textProvider);
  const config = {
    ...readJsonConfig(configPath),
    SOFT_ACCOUNT_PROVIDER: textProvider === "custom" ? "newapi" : textProvider,
    SOFT_MODEL_MODE: mode,
    SOFT_TEXT_PROVIDER: textProvider,
    SOFT_MODEL_PROVIDER: preset.provider,
    SOFT_MODEL_GPT_BASE_URL: apiBaseUrl,
    SOFT_MODEL_GPT_NAME: modelName || "gpt-5.5",
    SOFT_MODEL_GPT_OUTLINE_NAME: outlineModel || modelName || "gpt-5.5",
    SOFT_MODEL_GPT_FRONTEND_NAME: frontendModel || modelName || "gpt-5.5",
    SOFT_LLM_AI_FRONTEND_WORKERS: String(frontendWorkers),
    SOFT_MODEL_GPT_OUTLINE_TIMEOUT_SECONDS: String(outlineTimeout),
    SOFT_MODEL_GPT_REASONING_EFFORT: reasoningEffort,
    SOFT_MODEL_GPT_IMAGE_NAME: imageModel || "gpt-image-2",
    SOFT_MODEL_GPT_IMAGE_BASE_URL: imageApiBaseUrl,
    SOFT_MODEL_GPT_IMAGE_API_KEY: imageApiKey,
    SOFT_MODEL_IMAGE_NAME: imageModel || "gpt-image-2",
    SOFT_MODEL_IMAGE_BASE_URL: imageApiBaseUrl,
    SOFT_MODEL_IMAGE_API_KEY: imageApiKey,
    SOFT_MODEL_CONFIG_LOCKED: "false",
    SOFT_USER_SAVED_CONFIG: "true",
    SOFT_USER_SAVED_AT: new Date().toISOString()
  };
  const previousProviderPrefix = providerEnvPrefix(previousTextProvider);
  config[`SOFT_PROVIDER_${previousProviderPrefix}_BASE_URL`] = previousProviderProfile.baseUrl;
  config[`SOFT_PROVIDER_${previousProviderPrefix}_MODEL`] = previousProviderProfile.modelName;
  config[`SOFT_PROVIDER_${previousProviderPrefix}_OUTLINE_MODEL`] = previousProviderProfile.outlineModelName;
  config[`SOFT_PROVIDER_${previousProviderPrefix}_FRONTEND_MODEL`] = previousProviderProfile.frontendModelName;
  if (previousProviderProfile.apiKey) config[`SOFT_PROVIDER_${previousProviderPrefix}_API_KEY`] = previousProviderProfile.apiKey;
  config[`SOFT_PROVIDER_${providerPrefix}_BASE_URL`] = apiBaseUrl;
  config[`SOFT_PROVIDER_${providerPrefix}_MODEL`] = modelName || preset.defaultModel;
  config[`SOFT_PROVIDER_${providerPrefix}_OUTLINE_MODEL`] = outlineModel || modelName || preset.defaultModel;
  config[`SOFT_PROVIDER_${providerPrefix}_FRONTEND_MODEL`] = frontendModel || modelName || preset.defaultModel;
  if (apiKey) config[`SOFT_PROVIDER_${providerPrefix}_API_KEY`] = apiKey;
  if (apiKey) config.SOFT_MODEL_GPT_API_KEY = apiKey;
  writeJsonConfig(configPath, config);
  applyModelConfig(config);
  return {
    ok: true,
    mode,
    textProvider,
    providerProfiles: providerProfilesForUi(),
    modelName: config.SOFT_MODEL_GPT_NAME,
    outlineModelName: config.SOFT_MODEL_GPT_OUTLINE_NAME,
    frontendModelName: config.SOFT_MODEL_GPT_FRONTEND_NAME,
    frontendWorkers,
    outlineTimeoutSeconds: outlineTimeout,
    reasoningEffort,
    apiBaseUrl: "",
    apiBaseUrlMasked: hiddenConfigStatus(config.SOFT_MODEL_GPT_BASE_URL, "已配置（地址已隐藏）"),
    apiBaseUrlConfigured: Boolean(config.SOFT_MODEL_GPT_BASE_URL),
    apiKey: "",
    apiKeyConfigured: Boolean(config.SOFT_MODEL_GPT_API_KEY),
    imageModelName: config.SOFT_MODEL_GPT_IMAGE_NAME,
    imageUseTextApi,
    imageApiBaseUrl: "",
    imageApiBaseUrlMasked: hiddenConfigStatus(config.SOFT_MODEL_GPT_IMAGE_BASE_URL, "已单独配置（地址已隐藏）"),
    imageApiBaseUrlConfigured: Boolean(config.SOFT_MODEL_GPT_IMAGE_BASE_URL),
    imageApiKey: "",
    imageApiKeyConfigured: Boolean(config.SOFT_MODEL_GPT_IMAGE_API_KEY)
  };
});

ipcMain.handle("open-path", async (_event, targetPath) => {
  if (!targetPath) {
    return { ok: false, message: "路径为空" };
  }
  const result = await shell.openPath(targetPath);
  return { ok: !result, message: result };
});

ipcMain.handle("get-model-account", async () => {
  const configError = gptConfigError();
  const providerLabel = activeTextProviderPreset().label;
  if (configError) {
    return {
      status: "unconfigured",
      accountName: `${providerLabel} 未配置`,
      balanceLabel: "需要配置 API",
      updatedAt: "",
      message: configError
    };
  }
  const url = accountBalanceUrl();
  if (url) {
    try {
      return normalizeBalanceResponse(await fetchJson(url, accountAuthToken()));
    } catch (error) {
      return {
        status: "error",
        accountName: "余额接口异常",
        balanceLabel: "读取失败",
        updatedAt: "",
        message: error.message
      };
    }
  }
  const balanceLabel = process.env.SOFT_MODEL_BALANCE_LABEL || "";
  if (balanceLabel) {
    return {
      status: "connected",
      accountName: process.env.SOFT_MODEL_ACCOUNT_NAME || "模型账户",
      balanceLabel,
      updatedAt: new Date().toLocaleString("zh-CN", { hour12: false })
    };
  }
  return {
    status: "unknown",
    accountName: providerLabel,
    balanceLabel: activeTextProviderId() === "custom" ? "待配置" : "余额请查看供应商控制台",
    updatedAt: ""
  };
});
