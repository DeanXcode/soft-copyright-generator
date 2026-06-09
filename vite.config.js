import react from "@vitejs/plugin-react";
import { spawn } from "node:child_process";
import path from "node:path";
import { defineConfig } from "vite";

export default defineConfig({
  base: "./",
  plugins: [react(), devInferFeatureHintPlugin()]
});

function devInferFeatureHintPlugin() {
  return {
    name: "softcopyright-dev-infer-feature-hint",
    configureServer(server) {
      server.middlewares.use("/api/infer-feature-hint", async (req, res, next) => {
        if (req.method !== "POST") {
          next();
          return;
        }
        try {
          const payload = await readJsonBody(req);
          const apiBaseUrl = String(payload.apiBaseUrl || "").trim();
          const apiKey = String(payload.apiKey || "").trim();
          if (!apiBaseUrl || !apiKey) {
            sendJson(res, {
              ok: false,
              code: -1,
              message: "请先配置 GPT 请求地址和 API Key",
              stderr: "missing GPT config",
              featureHint: "",
              meta: { requires_gpt_config: true }
            });
            return;
          }
          const args = [
            path.join(process.cwd(), "backend", "infer_feature_hint.py"),
            "--name",
            String(payload.name || ""),
            "--product-type",
            String(payload.productType || ""),
            "--feature-hint",
            String(payload.featureHint || ""),
            "--model-provider",
            "custom",
            "--model-name",
            String(payload.modelName || "gpt-4o-mini"),
            "--api-base-url",
            apiBaseUrl,
            "--api-key",
            apiKey
          ];
          const result = await runPython(args);
          sendJson(res, result);
        } catch (error) {
          sendJson(res, {
            ok: false,
            code: -1,
            message: error?.message || "GPT 大纲生成失败",
            stderr: error?.stack || String(error),
            featureHint: "",
            meta: {}
          });
        }
      });
    }
  };
}

function readJsonBody(req) {
  return new Promise((resolve, reject) => {
    let body = "";
    req.setEncoding("utf8");
    req.on("data", (chunk) => {
      body += chunk;
      if (body.length > 1024 * 1024) {
        reject(new Error("request body too large"));
      }
    });
    req.on("end", () => {
      try {
        resolve(body ? JSON.parse(body) : {});
      } catch (error) {
        reject(error);
      }
    });
    req.on("error", reject);
  });
}

function runPython(args) {
  return new Promise((resolve) => {
    const child = spawn("python", args, {
      cwd: process.cwd(),
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
    child.on("close", (code) => {
      const resultMatch = stdout.match(/RESULT_JSON:(\{.+\})/s);
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
        featureHint: parsed.feature_hint || "",
        meta: parsed.meta || {}
      });
    });
  });
}

function sendJson(res, data) {
  res.statusCode = data.ok === false ? 200 : 200;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.end(JSON.stringify(data));
}
