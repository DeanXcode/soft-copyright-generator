const { app, BrowserWindow, ipcMain, shell } = require("electron");
const fs = require("fs");
const http = require("http");
const https = require("https");
const path = require("path");
const { spawn } = require("child_process");

const rootDir = path.resolve(__dirname, "..", "..");
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
    return gatewayRoot ? `${gatewayRoot}/api/usage/token` : "";
  }
  const baseUrl = accountApiBaseUrl().replace(/\/+$/, "");
  return baseUrl ? `${baseUrl}/api/v1/account/balance` : "";
}

function fetchJson(url, token) {
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
  const configPaths = [
    path.join(rootDir, "config", "production.json"),
    path.join(rootDir, "config", "desktop.local.json")
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
    mainWindow.loadFile(path.join(rootDir, "dist", "index.html"));
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
  const modelPlan = modelPlans[payload.modelPlan] || modelPlans.gpt;
  const args = [
    path.join(rootDir, "backend", "generate_materials.py"),
    "--name",
    payload.name,
    "--version",
    payload.version || "V1.0",
    "--language",
    payload.language || "Java",
    "--product-type",
    payload.productType || "智慧城市软件",
    "--feature-hint",
    payload.featureHint || "",
    "--model-provider",
    modelPlan.provider || payload.modelProvider || "local-template",
    "--model-name",
    modelPlan.modelName || payload.modelName || "template-v1",
    "--randomness",
    payload.randomness || "standard"
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
    const child = spawn("python", args, {
      cwd: rootDir,
      windowsHide: true,
      env: {
        ...process.env,
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
      resolve({
        ok: code === 0,
        code,
        stdout,
        stderr,
        zipPath,
        outputDir: outputDir || (zipPath ? path.dirname(zipPath) : ""),
        warnings: parsed.warnings || [],
        checks: parsed.checks || {},
        files,
        blueprintSource: parsed.blueprint_source || "local-template",
        manualSource: parsed.manual_source || "local-template",
        seed: parsed.seed || "",
        randomness: parsed.randomness || payload.randomness || "standard"
      });
    });
  });
});

ipcMain.handle("open-path", async (_event, targetPath) => {
  if (!targetPath) {
    return { ok: false, message: "路径为空" };
  }
  const result = await shell.openPath(targetPath);
  return { ok: !result, message: result };
});

ipcMain.handle("get-model-account", async () => {
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
