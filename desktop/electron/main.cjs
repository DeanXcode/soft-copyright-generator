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
loadDesktopConfig();

const isDev = process.env.VITE_DEV_SERVER_URL || process.env.NODE_ENV === "development";
let mainWindow;

const modelPlans = {
  gpt: {
    provider: "custom",
    modelName: process.env.SOFT_MODEL_GPT_NAME || process.env.SOFT_MODEL_GATEWAY_MODEL || "gpt-4o-mini",
    apiBaseUrl: process.env.SOFT_MODEL_GPT_BASE_URL || process.env.SOFT_MODEL_GATEWAY_BASE_URL || "",
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
  const explicitUrl = process.env.SOFT_ACCOUNT_BALANCE_URL || "";
  if (explicitUrl) {
    return explicitUrl;
  }
  if ((process.env.SOFT_ACCOUNT_PROVIDER || "").toLowerCase() === "newapi") {
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
  if (app.isPackaged) {
    return path.join(app.getPath("userData"), "config", "production.json");
  }
  return path.join(rootDir, "config", "production.json");
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

function generationOutputRoot() {
  if (app.isPackaged) {
    return path.join(app.getPath("documents"), "SoftCopyrightGenerator", "output");
  }
  return path.join(rootDir, "output");
}

function currentModelMode() {
  return "gpt";
}

function gptConfigError() {
  if (!String(modelPlans.gpt.apiBaseUrl || "").trim()) {
    return "GPT 模式需要填写请求地址";
  }
  if (!String(modelPlans.gpt.apiKey || "").trim()) {
    return "GPT 模式需要填写 API Key";
  }
  return "";
}

function envFlagEnabled(value) {
  return ["1", "true", "yes", "on"].includes(String(value || "").trim().toLowerCase());
}

function applyModelConfig(config) {
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
    return JSON.parse(fs.readFileSync(configPath, "utf8"));
  } catch (_error) {
    return {};
  }
}

function writeJsonConfig(configPath, config) {
  fs.mkdirSync(path.dirname(configPath), { recursive: true });
  fs.writeFileSync(configPath, `${JSON.stringify(config, null, 2)}\n`, "utf8");
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
  const userConfigDir = (() => {
    try {
      return app.isPackaged ? path.join(app.getPath("userData"), "config") : "";
    } catch (_error) {
      return "";
    }
  })();
  const configPaths = [
    ...(externalConfigDir
      ? [
          path.join(externalConfigDir, "production.json"),
          path.join(externalConfigDir, "desktop.local.json")
        ]
      : []),
    path.join(rootDir, "config", "production.json"),
    path.join(rootDir, "config", "desktop.local.json"),
    ...(userConfigDir
      ? [
          path.join(userConfigDir, "production.json"),
          path.join(userConfigDir, "desktop.local.json")
        ]
      : []),
    path.join(exeConfigDir, "production.json"),
    path.join(exeConfigDir, "desktop.local.json")
  ];
  for (const configPath of configPaths) {
    if (!fs.existsSync(configPath)) continue;
    try {
      const config = JSON.parse(fs.readFileSync(configPath, "utf8"));
      for (const [key, value] of Object.entries(config)) {
        if (typeof value === "string" && value && !process.env[key]) {
          process.env[key] = value;
        }
      }
    } catch (error) {
      console.warn(`读取桌面配置失败：${configPath}`, error.message);
    }
  }
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 860,
    minWidth: 1080,
    minHeight: 720,
    backgroundColor: "#f5f7fb",
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false
    }
  });

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

ipcMain.handle("generate-materials", async (_event, payload) => {
  const configError = gptConfigError();
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
      blueprintSource: "gpt",
      manualSource: "gpt"
    };
  }
  const modelPlan = modelPlans.gpt;
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
    modelPlan.modelName || payload.modelName || "gpt-4o-mini",
    "--randomness",
    payload.randomness || "standard",
    "--output-root",
    payload.outputRoot || generationOutputRoot()
  ];

  if (modelPlan.apiBaseUrl) {
    args.push("--api-base-url", modelPlan.apiBaseUrl);
  }
  if (modelPlan.apiKey) {
    args.push("--api-key", modelPlan.apiKey);
  }
  if (payload.seed) {
    args.push("--seed", payload.seed);
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
        PYTHONIOENCODING: "utf-8"
      }
    });
    let stdout = "";
    let stderr = "";
    let stdoutBuffer = "";

    function handleStdoutLine(line) {
      const eventMatch = line.match(/^EVENT_JSON:(\{.+\})$/);
      if (eventMatch) {
        try {
          sender.send("generate-event", JSON.parse(eventMatch[1]));
        } catch (_error) {
          sender.send("generate-event", { stage: "log", progress: 0, message: line });
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
    child.on("close", (code) => {
      if (stdoutBuffer.trim()) {
        handleStdoutLine(stdoutBuffer.trim());
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
      resolve({
        ok: code === 0,
        code,
        stdout,
        stderr,
        zipPath,
        outputDir: outputDir || (zipPath ? path.dirname(zipPath) : ""),
        warnings: parsed.warnings || [],
        checks: parsed.checks || {},
        validation,
        files,
        blueprintSource: parsed.blueprint_source || "gpt",
        manualSource: parsed.manual_source || "gpt",
        technicalArchitecture: parsed.technical_architecture || {},
        featureHint: parsed.feature_hint || payload.featureHint || "",
        featureHintMeta: parsed.feature_hint_meta || {},
        seed: parsed.seed || "",
        randomness: parsed.randomness || payload.randomness || "standard"
      });
    });
  });
});

ipcMain.handle("infer-feature-hint", async (_event, payload) => {
  const configError = gptConfigError();
  if (configError) {
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
    modelPlan.modelName || payload.modelName || "gpt-4o-mini",
    "--timeout-seconds",
    "75",
    "--retry-count",
    "0",
    "--require-llm",
    "--min-blueprint-modules",
    "8"
  ];
  if (modelPlan.apiBaseUrl) {
    args.push("--api-base-url", modelPlan.apiBaseUrl);
  }
  if (modelPlan.apiKey) {
    args.push("--api-key", modelPlan.apiKey);
  }

  return new Promise((resolve) => {
    let settled = false;
    const child = spawn(bundledPythonExecutable(), args, {
      cwd: app.isPackaged ? process.resourcesPath : rootDir,
      windowsHide: true,
      env: {
        ...process.env,
        PYTHONIOENCODING: "utf-8"
      }
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString("utf8");
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString("utf8");
    });
    const timeout = setTimeout(() => {
      if (settled) return;
      settled = true;
      child.kill();
      resolve({
        ok: false,
        code: -2,
        stderr,
        message: "GPT 名称理解超时，请稍后重试或检查模型网关响应速度",
        featureHint: "",
        meta: { feature_hint_source: "llm-timeout", requires_gpt: true }
      });
    }, 90000);
    child.on("error", (error) => {
      if (settled) return;
      settled = true;
      clearTimeout(timeout);
      resolve({
        ok: false,
        code: -1,
        stderr: stderr || String(error?.message || error),
        message: "GPT 名称理解进程启动失败",
        featureHint: "",
        meta: { feature_hint_source: "llm-process-error", requires_gpt: true }
      });
    });
    child.on("close", (code) => {
      if (settled) return;
      settled = true;
      clearTimeout(timeout);
      const resultMatch = stdout.match(/RESULT_JSON:(\{.+\})/);
      let parsed = {};
      if (resultMatch) {
        try {
          parsed = JSON.parse(resultMatch[1]);
        } catch (_error) {
          parsed = {};
        }
      }
      resolve({
        ok: code === 0 && Boolean(parsed.feature_hint),
        code,
        stderr,
        message:
          code === 0 && Boolean(parsed.feature_hint)
            ? ""
            : "GPT 名称理解未生成合格蓝图，请重试；要求至少 8 个不重复的业务模块",
        featureHint: parsed.feature_hint || "",
        meta: parsed.meta || {}
      });
    });
  });
});

ipcMain.handle("get-model-config", async () => {
  return {
    mode: currentModelMode(),
    modelName: modelPlans.gpt.modelName || "gpt-4o-mini",
    apiBaseUrl: modelPlans.gpt.apiBaseUrl || "",
    apiKey: modelPlans.gpt.apiKey || "",
    apiKeyConfigured: Boolean(modelPlans.gpt.apiKey),
    provider: process.env.SOFT_ACCOUNT_PROVIDER || "newapi",
    preset: envFlagEnabled(process.env.SOFT_CUSTOMER_PRESET_CONFIG)
  };
});

ipcMain.handle("save-model-config", async (_event, payload) => {
  const mode = "gpt";
  const modelName = String(payload?.modelName || modelPlans.gpt.modelName || "gpt-4o-mini").trim();
  const apiBaseUrl = String(payload?.apiBaseUrl || modelPlans.gpt.apiBaseUrl || "").trim();
  const apiKey = String(payload?.apiKey || "").trim();
  if (!apiBaseUrl) {
    return { ok: false, message: "GPT 模式需要填写请求地址" };
  }
  if (!apiKey) {
    return { ok: false, message: "GPT 模式需要填写 API Key" };
  }

  const configPath = defaultConfigPath();
  const config = {
    ...readJsonConfig(configPath),
    SOFT_ACCOUNT_PROVIDER: "newapi",
    SOFT_MODEL_MODE: mode,
    SOFT_MODEL_GPT_BASE_URL: apiBaseUrl,
    SOFT_MODEL_GPT_NAME: modelName || "gpt-4o-mini",
    SOFT_MODEL_CONFIG_LOCKED: "false"
  };
  config.SOFT_MODEL_GPT_API_KEY = apiKey;
  writeJsonConfig(configPath, config);
  applyModelConfig(config);
  return {
    ok: true,
    mode,
    modelName: config.SOFT_MODEL_GPT_NAME,
    apiBaseUrl: config.SOFT_MODEL_GPT_BASE_URL,
    apiKey: config.SOFT_MODEL_GPT_API_KEY,
    apiKeyConfigured: Boolean(config.SOFT_MODEL_GPT_API_KEY)
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
  if (configError) {
    return {
      status: "unconfigured",
      accountName: "GPT 未配置",
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
    accountName: "GPT 中转站",
    balanceLabel: "待配置",
    updatedAt: ""
  };
});
