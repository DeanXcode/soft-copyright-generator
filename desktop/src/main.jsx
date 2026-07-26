import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import appIcon from "../../build/icon.png";
import {
  AlertTriangle,
  Archive,
  CheckCircle2,
  ChevronDown,
  Code2,
  FileCheck2,
  FileText,
  FolderOpen,
  Image as ImageIcon,
  ListOrdered,
  Loader2,
  PackageCheck,
  Plus,
  RefreshCw,
  Save,
  SlidersHorizontal,
  Sparkles,
  Square,
  Trash2
} from "lucide-react";
import "./styles.css";

const modelProviders = [
  {
    value: "template",
    label: "Default Template",
    description: "使用本地模板和规则生成，不调用模型接口。",
    provider: "local-template",
    modelName: "template-v1",
    cost: "不消耗 token"
  },
  {
    value: "gpt",
    label: "多模型 API",
    description: "可选择现有兼容接口、Grok、Claude、Gemini 或 DeepSeek。",
    provider: "custom",
    modelName: "gpt-5.5",
    cost: "按实际消耗"
  }
];

const textProviderChoices = [
  { value: "custom", label: "现有兼容 API", defaultModel: "gpt-5.5", addressMode: "custom" },
  { value: "grok", label: "Grok (xAI)", defaultModel: "grok-3-mini", addressMode: "preset" },
  { value: "claude", label: "Claude (Anthropic)", defaultModel: "claude-sonnet-4-20250514", addressMode: "preset" },
  { value: "gemini", label: "Gemini (Google)", defaultModel: "gemini-2.5-flash", addressMode: "preset" },
  { value: "deepseek", label: "DeepSeek", defaultModel: "deepseek-chat", addressMode: "preset" }
];

const generationStages = [
  ["start", "提交任务"],
  ["prepare", "确认业务蓝图"],
  ["blueprint", "生成产品蓝图"],
  ["manual_content", "生成说明书正文"],
  ["visual_reference", "生成风格参考图"],
  ["source", "业务后端与接口"],
  ["screenshots", "风格图到界面截图"],
  ["manual", "生成文档材料"],
  ["source_doc", "源码鉴别材料"],
  ["pdf", "转换 PDF"],
  ["info", "申请信息表"],
  ["package", "打包与校验"]
];

const modelChoices = ["gpt-5.5", "gpt-5.4", "gpt-5.2", "gpt-5.1", "gpt-4.1"];
const providerModelChoices = {
  custom: modelChoices,
  grok: ["grok-3-mini"],
  claude: ["claude-sonnet-4-20250514"],
  gemini: ["gemini-2.5-flash"],
  deepseek: ["deepseek-chat"]
};
const workflowStages = ["输入名称", "自动规划", "生成材料", "检查交付"];
const reasoningEffortLabels = {
  minimal: "极简",
  low: "低",
  medium: "中",
  high: "高",
  xhigh: "极高"
};

const stagePlannedSteps = {
  visual_reference: [
    { label: "准备视觉参考页面清单", match: ["视觉参考页面清单", "页面清单"] },
    { label: "AI 生成全局风格提示词", match: ["全局视觉风格提示词", "生成视觉提示词"] },
    { label: "gpt-image-2 生成全局风格参考图", match: ["全局视觉风格参考图", "视觉参考稿", "视觉参考图"] }
  ],
  screenshots: [
    { label: "复用风格参考图", match: ["复用全局风格参考图", "根据参考图"] },
    { label: "AI 按风格参考图生成全部界面代码", match: ["全局视觉风格参考图生成界面代码", "生成界面代码"] },
    { label: "运行生成项目并重截手册图", match: ["生成项目服务", "渲染界面截图"] }
  ]
};

const OUTLINE_TIMEOUT_BUFFER_MS = 20000;
const QUEUE_STORAGE_KEY = "soft-copyright-generator.taskQueue.v1";
let cachedQueueState = null;

function App() {
  const bridgeAvailable = typeof window !== "undefined" && window.softCopyright;
  const [form, setForm] = useState({
    name: "",
    version: "V1.0",
    language: "自动选择",
    productType: "APP",
    softwareCategory: "应用软件",
    featureHint: "",
    modelPlan: "gpt",
    modelProvider: "custom",
    modelName: "gpt-5.5",
    randomness: "standard",
    blueprintReviewBeforeGeneration: false
  });
  const [modelConfig, setModelConfig] = useState({
    mode: "gpt",
    textProvider: "custom",
    providerProfiles: {},
    modelName: "gpt-5.5",
    outlineModelName: "gpt-5.5",
    frontendModelName: "gpt-5.5",
    frontendWorkers: "auto",
    outlineTimeoutSeconds: 60,
    reasoningEffort: "medium",
    apiBaseUrl: "",
    apiBaseUrlMasked: "未配置",
    apiBaseUrlConfigured: false,
    apiKey: "",
    apiKeyConfigured: false,
    imageModelName: "gpt-image-2",
    imageUseTextApi: true,
    imageApiBaseUrl: "",
    imageApiBaseUrlMasked: "未单独配置，将复用文本请求地址",
    imageApiBaseUrlConfigured: false,
    imageApiKey: "",
    imageApiKeyConfigured: false,
    preset: false
  });
  const [account, setAccount] = useState({
    status: "unknown",
    accountName: "未连接",
    balanceLabel: "待配置",
    updatedAt: ""
  });
  const [modelCatalog, setModelCatalog] = useState({ status: "idle", provider: "", models: [], message: "" });
  const [status, setStatus] = useState("idle");
  const [result, setResult] = useState(null);
  const [progress, setProgress] = useState(0);
  const [events, setEvents] = useState([]);
  const [processClock, setProcessClock] = useState({ mode: "idle", startedAt: 0, elapsedMs: 0 });
  const [businessPlan, setBusinessPlan] = useState(createEmptyPlan());
  const [featureHintMeta, setFeatureHintMeta] = useState({});
  const [inputText, setInputText] = useState("");
  const [outlineState, setOutlineState] = useState("empty");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [configStatus, setConfigStatus] = useState("");
  const [cancelRequested, setCancelRequested] = useState(false);
  const [taskQueue, setTaskQueue] = useState(() => loadPersistedQueueState().tasks);
  const [queuePaused, setQueuePaused] = useState(() => loadPersistedQueueState().paused);
  const [recoverableTasks, setRecoverableTasks] = useState([]);
  const [recoveryStatus, setRecoveryStatus] = useState("");
  const [activeQueueTaskId, setActiveQueueTaskId] = useState("");
  const taskQueueRef = useRef(taskQueue);
  const activeQueueTaskIdRef = useRef(activeQueueTaskId);
  const queueRunningRef = useRef(false);

  const gptConfigured =
    form.modelPlan === "template" ||
    Boolean(
      (modelConfig.apiBaseUrlConfigured || modelConfig.apiBaseUrl.trim()) &&
        (modelConfig.apiKey.trim() || (bridgeAvailable && modelConfig.apiKeyConfigured))
    );
  const isGeneratingStatus = status === "running" || status === "planning";
  const currentPromptText = isGeneratingStatus ? inputText : inputText || form.name;
  const currentSoftwareName = extractSoftwareName(currentPromptText);
  const canPlan = currentSoftwareName.length > 0;
  const planReady = businessPlan.modules.length > 0;
  const canRetryFromConfirmedOutline = (status === "error" || status === "cancelled") && canPlan && planReady && outlineState === "confirmed" && gptConfigured;
  const canGenerate = canPlan && planReady && outlineState === "confirmed" && status !== "running" && status !== "planning" && gptConfigured;
  const canCancelTask = isGeneratingStatus && bridgeAvailable && Boolean(window.softCopyright.cancelGeneration) && !cancelRequested;
  const canQueueQuickTask = isGeneratingStatus && !cancelRequested && Boolean(extractSoftwareName(inputText)) && gptConfigured;
  const canPrimaryAction = isGeneratingStatus ? canQueueQuickTask || canCancelTask : canPlan;
  const queueSummary = useMemo(() => summarizeQueue(taskQueue), [taskQueue]);
  const promptTextareaValue = isGeneratingStatus ? inputText : currentPromptText;
  const promptPlaceholder = isGeneratingStatus
    ? "输入下一个软件名可加入队列；留空则可中止当前生成。"
    : "输入软件名称，例如：小风点餐。也可以写补充要求。";
  const primaryActionLabel = isGeneratingStatus
    ? canQueueQuickTask
      ? "加入队列"
      : cancelRequested
        ? "正在中止..."
        : "中止生成"
    : primaryButtonLabel(
        status,
        outlineState,
        planReady,
        gptConfigured,
        canRetryFromConfirmedOutline,
        form.blueprintReviewBeforeGeneration
      );
  const hasOutlineError = canPlan && Boolean(configStatus) && configStatus !== "saved" && configStatus !== "saving";
  const taskStatusText = statusLabel(status, { canPlan, hasOutlineError });
  const generatedFiles = useMemo(() => buildGeneratedFiles(result), [result]);
  const qualityItems = useMemo(() => buildQualityItems(result), [result]);
  const activeEvent = currentEvent(events);

  useEffect(() => {
    taskQueueRef.current = taskQueue;
  }, [taskQueue]);

  useEffect(() => {
    persistQueueState(taskQueue, queuePaused);
  }, [taskQueue, queuePaused]);

  useEffect(() => {
    activeQueueTaskIdRef.current = activeQueueTaskId;
  }, [activeQueueTaskId]);

  useEffect(() => {
    if (!bridgeAvailable || !window.softCopyright.listRecoverableTasks) return undefined;
    let cancelled = false;
    window.softCopyright
      .listRecoverableTasks()
      .then((response) => {
        if (cancelled) return;
        const tasks = Array.isArray(response?.tasks) ? response.tasks : [];
        setRecoverableTasks(tasks);
        setRecoveryStatus(tasks.length ? `发现 ${tasks.length} 个可恢复的未完成任务` : "");
      })
      .catch((error) => {
        if (!cancelled) setRecoveryStatus(sanitizeErrorMessage(error?.message || "恢复任务扫描失败"));
      });
    return () => {
      cancelled = true;
    };
  }, [bridgeAvailable, form.modelPlan]);

  useEffect(() => {
    if (!bridgeAvailable) return undefined;
    return window.softCopyright.onGenerateEvent((event) => {
      const enrichedEvent = {
        ...event,
        at: new Date().toLocaleTimeString(),
        elapsedMs: processClock.startedAt ? Date.now() - processClock.startedAt : 0
      };
      setProgress(enrichedEvent.progress || 0);
      setEvents((current) => [...current, enrichedEvent].slice(-500));
      const taskId = activeQueueTaskIdRef.current;
      const terminalResult = resultFromGenerationEvent(enrichedEvent);
      if (taskId) {
        updateQueueTask(taskId, (task) => ({
          ...task,
          status: terminalResult ? (terminalResult.cancelled ? "cancelled" : terminalResult.ok ? "success" : "error") : task.status,
          phase: terminalResult?.ok ? "done" : task.phase,
          progress: terminalResult?.ok ? 100 : enrichedEvent.progress || task.progress || 0,
          events: [...(task.events || []), enrichedEvent].slice(-500),
          result: terminalResult || task.result,
          finishedAt: terminalResult ? Date.now() : task.finishedAt
        }));
      }
      if (terminalResult) {
        setResult(terminalResult);
        setStatus(terminalResult.cancelled ? "cancelled" : terminalResult.ok ? "success" : "error");
        setProcessClock((current) => ({ ...current, elapsedMs: Date.now() - (current.startedAt || Date.now()) }));
        if (!terminalResult.ok || terminalResult.cancelled) setQueuePaused(true);
      }
    });
  }, [bridgeAvailable, processClock.startedAt]);

  useEffect(() => {
    if (!bridgeAvailable || !window.softCopyright.getGenerationStatus) return undefined;
    let cancelled = false;
    const syncActiveGeneration = () => {
      window.softCopyright
        .getGenerationStatus()
        .then((response) => {
          if (cancelled || !response?.running) return;
          const startedAt = Number(response.startedAt || Date.now());
          const event = createProcessEvent(
            response.stage || "start",
            Number(response.progress || 0),
            response.message || "后台材料生成任务仍在运行，已重新连接状态",
            startedAt
          );
          setStatus("running");
          setProgress(event.progress || 0);
          setProcessClock({ mode: "materials", startedAt, elapsedMs: Math.max(0, Date.now() - startedAt) });
          setEvents((current) => {
            const latest = current[current.length - 1];
            if (latest?.message === event.message && latest?.stage === event.stage) return current;
            return [...current, event].slice(-500);
          });
          setQueuePaused(true);
          setRecoveryStatus(`后台任务仍在运行：${response.title || "材料生成"}`);
        })
        .catch((error) => {
          if (!cancelled) setRecoveryStatus(sanitizeErrorMessage(error?.message || "后台任务状态同步失败"));
        });
    };
    syncActiveGeneration();
    const timer = window.setInterval(syncActiveGeneration, 4000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [bridgeAvailable]);

  useEffect(() => {
    if (queuePaused || queueRunningRef.current || status === "planning" || status === "running") return;
    const nextTask = taskQueue.find((item) => item.status === "queued");
    if (!nextTask) return;
    runQueuedTask(nextTask.id);
  }, [taskQueue, queuePaused, status]);

  useEffect(() => {
    if (status !== "planning" && status !== "running") return undefined;
    const tick = () => {
      setProcessClock((current) =>
        current.startedAt ? { ...current, elapsedMs: Math.max(0, Date.now() - current.startedAt) } : current
      );
    };
    tick();
    const timer = window.setInterval(tick, 500);
    return () => window.clearInterval(timer);
  }, [status]);

  useEffect(() => {
    if (!bridgeAvailable || !window.softCopyright.getModelAccount) return undefined;
    let cancelled = false;
    fetchModelAccount().then((response) => {
      if (!cancelled && response) setAccount(response);
    });
    return () => {
      cancelled = true;
    };
  }, [bridgeAvailable]);

  useEffect(() => {
    if (!bridgeAvailable || !window.softCopyright.getModelConfig) return undefined;
    let cancelled = false;
    window.softCopyright.getModelConfig().then((config) => {
      if (cancelled || !config) return;
      const plan = modelProviders.find((item) => item.value === config.mode) || modelProviders.find((item) => item.value === "gpt");
      setModelConfig({
        mode: plan.value,
        textProvider: config.textProvider || "custom",
        providerProfiles: config.providerProfiles || {},
        modelName: config.modelName || "gpt-5.5",
        outlineModelName: config.outlineModelName || config.modelName || "gpt-5.5",
        frontendModelName: config.frontendModelName || config.modelName || "gpt-5.5",
        frontendWorkers: String(config.frontendWorkers || "auto"),
        outlineTimeoutSeconds: Number(config.outlineTimeoutSeconds || 60),
        reasoningEffort: config.reasoningEffort || "medium",
        apiBaseUrl: "",
        apiBaseUrlMasked: config.apiBaseUrlMasked || (config.apiBaseUrlConfigured ? "已配置（地址已隐藏）" : "未配置"),
        apiBaseUrlConfigured: Boolean(config.apiBaseUrlConfigured),
        apiKey: "",
        apiKeyConfigured: Boolean(config.apiKeyConfigured),
        imageModelName: config.imageModelName || "gpt-image-2",
        imageUseTextApi: config.imageUseTextApi !== false,
        imageApiBaseUrl: "",
        imageApiBaseUrlMasked:
          config.imageApiBaseUrlMasked ||
          (config.imageApiBaseUrlConfigured ? "已单独配置（地址已隐藏）" : "未单独配置，将复用文本请求地址"),
        imageApiBaseUrlConfigured: Boolean(config.imageApiBaseUrlConfigured),
        imageApiKey: "",
        imageApiKeyConfigured: Boolean(config.imageApiKeyConfigured),
        preset: Boolean(config.preset)
      });
      setForm((current) => ({
        ...current,
        modelPlan: plan.value,
        modelProvider: plan.provider,
        modelName: plan.value === "gpt" ? config.modelName || plan.modelName : plan.modelName
      }));
    });
    return () => {
      cancelled = true;
    };
  }, [bridgeAvailable]);

  useEffect(() => {
    if (!settingsOpen || form.modelPlan !== "gpt" || !bridgeAvailable || !window.softCopyright.listAvailableModels) return;
    refreshAvailableModels();
  }, [settingsOpen, bridgeAvailable, form.modelPlan]);

  function updateField(key, value) {
    setResult(null);
    if (key === "name") {
      setInputText(value);
    }
    setForm((current) => ({ ...current, [key]: value }));
    if (key === "name" || key === "productType" || key === "softwareCategory") {
      setOutlineState("empty");
      setBusinessPlan(createEmptyPlan());
      setFeatureHintMeta({});
      setEvents([]);
      setStatus("idle");
      setProgress(0);
      setCancelRequested(false);
      setProcessClock({ mode: "idle", startedAt: 0, elapsedMs: 0 });
    }
  }

  function handlePromptTextChange(value) {
    if (isGeneratingStatus) {
      setInputText(value);
      return;
    }
    updateField("name", value);
  }

  async function inferBusinessPlan(payload, startedAt = Date.now()) {
    if (!payload.name.trim()) return null;
    const inferredProductType = inferProductType(payload.name, payload.featureHint || "");
    const templateMode = form.modelPlan === "template";
    let featureHint = "";
    let meta = {};
    if (!templateMode && !(modelConfig.apiBaseUrlConfigured || modelConfig.apiBaseUrl.trim())) {
      setConfigStatus("请先配置文本模型请求地址");
      setSettingsOpen(true);
      return null;
    }
    if (!templateMode && !(modelConfig.apiKey.trim() || (bridgeAvailable && modelConfig.apiKeyConfigured))) {
      setConfigStatus("请先配置文本模型 API Key");
      setSettingsOpen(true);
      return null;
    }
    setStatus("planning");
    try {
      if (templateMode) {
        featureHint = [inferFeatureHint(payload.name, inferredProductType), payload.featureHint || ""].filter(Boolean).join("、");
        meta = {
          feature_hint_source: "local-template",
          feature_hint_keywords: splitTerms(featureHint),
          no_token_consumption: true
        };
      } else {
        const request =
          bridgeAvailable && window.softCopyright.inferFeatureHint
            ? window.softCopyright.inferFeatureHint({
                ...payload,
                productType: inferredProductType,
                modelPlan: "gpt",
                modelProvider: "custom",
                modelName: modelConfig.outlineModelName || modelConfig.modelName,
                timeoutSeconds: modelConfig.outlineTimeoutSeconds || 60
              })
            : inferFeatureHintThroughDevApi({
                ...payload,
                productType: inferredProductType,
                modelName: modelConfig.outlineModelName || modelConfig.modelName,
                timeoutSeconds: modelConfig.outlineTimeoutSeconds || 60,
                apiBaseUrl: modelConfig.apiBaseUrl,
                apiKey: modelConfig.apiKey
              });
        const outlineTimeoutMs = normalizeOutlineTimeout(modelConfig.outlineTimeoutSeconds || 60) * 1000 + OUTLINE_TIMEOUT_BUFFER_MS;
        const response = await withTimeout(request, outlineTimeoutMs, "GPT 蓝图生成超时，请稍后重试或检查模型网关响应速度");
        if (response?.cancelled) {
          return { cancelled: true };
        }
        if (response?.ok && response.featureHint) {
          featureHint = response.featureHint;
          meta = response.meta || {};
        } else {
          const message = sanitizeErrorMessage(response?.message || response?.stderr || "GPT 蓝图生成失败，请检查服务配置");
          setConfigStatus(message);
          setEvents((current) => [...current, createProcessEvent("outline", 0, message, startedAt)]);
          if (response?.meta?.requires_gpt_config) {
            setSettingsOpen(true);
          }
          return null;
        }
      }
    } catch (error) {
      const message = sanitizeErrorMessage(error?.message || "GPT 蓝图生成失败，请检查服务配置");
      setConfigStatus(message);
      setEvents((current) => [...current, createProcessEvent("outline", 0, message, startedAt)]);
      return null;
    }
    return {
      hint: featureHint,
      meta,
      plan: buildBusinessPlan(payload.name, inferredProductType, featureHint, meta)
    };
  }

  async function regeneratePlan() {
    const promptText = inputText || form.name;
    const name = extractSoftwareName(promptText);
    if (!name || status === "running") return;
    const startedAt = Date.now();
    setResult(null);
    setCancelRequested(false);
    setProgress(6);
    setStatus("planning");
    setProcessClock({ mode: "outline", startedAt, elapsedMs: 0 });
    const templateMode = form.modelPlan === "template";
    setEvents([createProcessEvent("outline", 6, `正在读取软件名称「${name}」和产品类型`, startedAt)]);
    await wait(180);
    setProgress(18);
    setEvents((current) => [
      ...current,
      createProcessEvent("outline", 18, templateMode ? "正在使用本地规则构建零 token 模块草案" : "正在构建两段式 GPT 蓝图请求，先识别名称语义，再生成模块草案", startedAt)
    ]);
    await wait(180);
    setProgress(32);
    setEvents((current) => [
      ...current,
      createProcessEvent("outline", 32, templateMode ? "Default Template 正在生成可编辑模块，不调用模型接口" : "正在调用 GPT 识别名称语义，随后会基于关键词生成可编辑模块", startedAt)
    ]);
    const response = await inferBusinessPlan({ ...form, name, featureHint: extractInputSupplement(promptText) }, startedAt);
    if (response?.cancelled) {
      setResult({
        ok: false,
        cancelled: true,
        zipPath: "",
        outputDir: "",
        checks: {},
        warnings: [],
        stdout: "",
        stderr: "已中止蓝图生成"
      });
      setStatus("cancelled");
      setCancelRequested(false);
      setProcessClock((current) => ({ ...current, elapsedMs: Date.now() - startedAt }));
      return;
    }
    if (!response) {
      setProgress(0);
      setStatus(businessPlan.modules.length ? "editing" : "idle");
      setCancelRequested(false);
      setProcessClock({ mode: "idle", startedAt: 0, elapsedMs: 0 });
      return;
    }
    setProgress(72);
    setEvents((current) => [
      ...current,
      createProcessEvent(
        "outline",
        72,
        `${templateMode ? "已生成本地模板结果" : "已收到 GPT 结构化结果"}，正在校验 ${response.plan.modules.length} 个模块的重复度和领域一致性`,
        startedAt
      )
    ]);
    await wait(180);
    setProgress(88);
    setEvents((current) => [
      ...current,
      createProcessEvent("outline", 88, templateMode ? "正在整理本地模板蓝图，确认本次不消耗 token" : "正在整理为可编辑蓝图，保留 GPT 的分类、模块说明、流程和页面信息", startedAt)
    ]);
    await wait(180);
    setFeatureHintMeta({ ...(response.meta || {}), _plannedAt: new Date().toLocaleTimeString() });
    setBusinessPlan(response.plan);
    setForm((current) => ({
      ...current,
      productType: response.plan.productType || inferProductType(name, response.hint),
      softwareCategory: inferSoftwareCategory(name, response.hint),
      language: "自动选择",
      featureHint: serializePlan(response.plan)
    }));
    setOutlineState("draft");
    setProgress(100);
    setEvents((current) => [
      ...current,
      createProcessEvent(
        "outline",
        100,
        `已生成 ${response.plan.modules.length} 个可申请材料使用的蓝图模块，可编辑后确认生成材料包`,
        startedAt
      )
    ]);
    setProcessClock((current) => ({ ...current, elapsedMs: Date.now() - startedAt }));
    setCancelRequested(false);
    setStatus("editing");
  }

  function updateModule(moduleId, key, value) {
    setOutlineState("draft");
    setBusinessPlan((current) => {
      const next = {
        ...current,
        modules: current.modules.map((module) => (module.id === moduleId ? { ...module, [key]: value } : module))
      };
      setForm((formState) => ({ ...formState, featureHint: serializePlan(next) }));
      return next;
    });
  }

  async function regenerateModule(moduleId) {
    const moduleIndex = businessPlan.modules.findIndex((module) => module.id === moduleId);
    if (moduleIndex < 0) return;
    if (form.modelPlan === "template") {
      const targetModule = businessPlan.modules[moduleIndex];
      const next = {
        ...businessPlan,
        modules: businessPlan.modules.map((module, index) =>
          module.id === moduleId ? regenerateModuleBlueprint(module, businessPlan, index) : module
        )
      };
      setBusinessPlan(next);
      setForm((formState) => ({ ...formState, featureHint: serializePlan(next) }));
      setFeatureHintMeta((current) => ({ ...current, feature_hint_source: "local-template", no_token_consumption: true }));
      setEvents((current) => [
        ...current,
        createProcessEvent("outline", 100, `已用本地规则刷新「${targetModule.title}」，未调用模型接口`)
      ]);
      setStatus("editing");
      return;
    }
    if (bridgeAvailable && !gptConfigured) {
      setConfigStatus("请先选择文本模型供应商并配置 API Key");
      setSettingsOpen(true);
      return;
    }
    if (bridgeAvailable && window.softCopyright.inferFeatureHint && status !== "planning") {
      const startedAt = Date.now();
      const targetModule = businessPlan.modules[moduleIndex];
      setOutlineState("draft");
      setCancelRequested(false);
      setStatus("planning");
      setProgress(26);
      setProcessClock({ mode: "outline", startedAt, elapsedMs: 0 });
      setEvents((current) => [
        ...current,
        createProcessEvent("outline", 26, `正在调用 GPT 重新生成「${targetModule.title}」模块说明`, startedAt)
      ]);
      const response = await inferBusinessPlan({
        ...form,
        name: businessPlan.softwareName || form.name,
        featureHint: `请基于当前蓝图重新生成第 ${moduleIndex + 1} 个模块，保持软件名称语义一致。当前模块：${targetModule.title}。当前蓝图：${serializePlan(businessPlan)}`
      });
      if (response?.cancelled) {
        setResult({
          ok: false,
          cancelled: true,
          zipPath: "",
          outputDir: "",
          checks: {},
          warnings: [],
          stdout: "",
          stderr: "已中止蓝图生成"
        });
        setStatus("cancelled");
        setCancelRequested(false);
        setProcessClock((current) => ({ ...current, elapsedMs: Date.now() - startedAt }));
        return;
      }
      if (response?.plan?.modules?.length) {
        const replacement = response.plan.modules[moduleIndex] || response.plan.modules[0];
        const next = {
          ...businessPlan,
          domain: response.plan.domain || businessPlan.domain,
          targetUsers: response.plan.targetUsers?.length ? response.plan.targetUsers : businessPlan.targetUsers,
          modules: businessPlan.modules.map((module) =>
            module.id === moduleId ? { ...replacement, id: module.id } : module
          )
        };
        setBusinessPlan(next);
        setForm((formState) => ({ ...formState, featureHint: serializePlan(next) }));
        setFeatureHintMeta((current) => ({ ...current, ...(response.meta || {}) }));
        setEvents((current) => [
          ...current,
          createProcessEvent("outline", 100, `已完成「${targetModule.title}」的 GPT 单条刷新`, startedAt)
        ]);
      }
      setProgress(0);
      setProcessClock((current) => ({ ...current, elapsedMs: Date.now() - startedAt }));
      setCancelRequested(false);
      setStatus("editing");
      return;
    }
    setOutlineState("draft");
    setBusinessPlan((current) => {
      const next = {
        ...current,
        modules: current.modules.map((module, index) => {
          if (module.id !== moduleId) return module;
          return regenerateModuleBlueprint(module, current, index);
        })
      };
      setForm((formState) => ({ ...formState, featureHint: serializePlan(next) }));
      return next;
    });
  }

  function updateChild(moduleId, childId, value) {
    setOutlineState("draft");
    setBusinessPlan((current) => {
      const next = {
        ...current,
        modules: current.modules.map((module) =>
          module.id === moduleId
            ? {
                ...module,
                children: (module.children || []).map((child) => (child.id === childId ? { ...child, title: value } : child))
              }
            : module
        )
      };
      setForm((formState) => ({ ...formState, featureHint: serializePlan(next) }));
      return next;
    });
  }

  function addModule() {
    setOutlineState("draft");
    setBusinessPlan((current) => {
      const index = current.modules.length + 1;
      const next = {
        ...current,
        modules: [
          ...current.modules,
          {
            id: createId("module"),
            category: "补充模块",
            title: `新增业务补充 ${index}`,
            description: "说明这个功能面向谁、解决什么业务动作、会记录哪些关键结果。",
            children: []
          }
        ]
      };
      setForm((formState) => ({ ...formState, featureHint: serializePlan(next) }));
      return next;
    });
  }

  function removeModule(moduleId) {
    setOutlineState("draft");
    setBusinessPlan((current) => {
      const next = { ...current, modules: current.modules.filter((module) => module.id !== moduleId) };
      setForm((formState) => ({ ...formState, featureHint: serializePlan(next) }));
      return next;
    });
  }

  function addChild(moduleId) {
    setOutlineState("draft");
    setBusinessPlan((current) => {
      const next = {
        ...current,
        modules: current.modules.map((module) =>
          module.id === moduleId
            ? { ...module, children: [...(module.children || []), { id: createId("child"), title: "新增细分功能" }] }
            : module
        )
      };
      setForm((formState) => ({ ...formState, featureHint: serializePlan(next) }));
      return next;
    });
  }

  function removeChild(moduleId, childId) {
    setOutlineState("draft");
    setBusinessPlan((current) => {
      const next = {
        ...current,
        modules: current.modules.map((module) =>
          module.id === moduleId
            ? { ...module, children: module.children.filter((child) => child.id !== childId) }
            : module
        )
      };
      setForm((formState) => ({ ...formState, featureHint: serializePlan(next) }));
      return next;
    });
  }

  function updateModelPlan(planValue) {
    const plan = modelProviders.find((item) => item.value === planValue) || modelProviders[0];
    setModelConfig((current) => ({ ...current, mode: plan.value }));
    setForm((current) => ({
      ...current,
      modelPlan: plan.value,
      modelProvider: plan.provider,
      modelName: plan.value === "gpt" ? modelConfig.modelName || plan.modelName : plan.modelName
    }));
    setAccount(
      plan.value === "template"
        ? { status: "local", accountName: "Default Template", balanceLabel: "不消耗 token", updatedAt: "", message: "本地生成模式" }
        : { status: "loading", accountName: "AI 账户", balanceLabel: "读取中", updatedAt: "", message: "" }
    );
  }

  function updateModelConfig(key, value) {
    setConfigStatus("");
    setModelConfig((current) => {
      if (key === "textProvider") {
        const choice = textProviderChoices.find((item) => item.value === value) || textProviderChoices[0];
        const savedProfile = current.providerProfiles?.[choice.value] || {};
        const nextModel = savedProfile.modelName || choice.defaultModel;
        return {
          ...current,
          textProvider: choice.value,
          modelName: nextModel,
          outlineModelName: savedProfile.outlineModelName || nextModel,
          frontendModelName: savedProfile.frontendModelName || nextModel,
          apiBaseUrl: "",
          apiBaseUrlMasked: choice.addressMode === "preset" ? "官方预设（地址已隐藏）" : savedProfile.baseUrlConfigured ? "已配置（地址已隐藏）" : "未配置",
          apiBaseUrlConfigured: choice.addressMode === "preset" || Boolean(savedProfile.baseUrlConfigured),
          apiKey: "",
          apiKeyConfigured: Boolean(savedProfile.apiKeyConfigured),
          imageUseTextApi: choice.value === "custom" ? current.imageUseTextApi : false
        };
      }
      const nextValue = key === "outlineTimeoutSeconds" ? normalizeOutlineTimeout(value) : value;
      const next = { ...current, [key]: nextValue };
      if (key === "modelName" && (!current.outlineModelName || current.outlineModelName === current.modelName)) {
        next.outlineModelName = value;
      }
      if (key === "modelName" && (!current.frontendModelName || current.frontendModelName === current.modelName)) {
        next.frontendModelName = value;
      }
      return next;
    });
    if (key === "modelName") {
      setForm((current) => ({ ...current, modelName: value }));
    }
    if (key === "textProvider") {
      const choice = textProviderChoices.find((item) => item.value === value) || textProviderChoices[0];
      setForm((current) => ({ ...current, modelName: choice.defaultModel }));
      setModelCatalog({ status: "idle", provider: choice.value, models: [], message: "保存供应商配置后可刷新该供应商的模型列表。" });
    }
  }

  async function saveModelConfig() {
    const separateImageApiReady =
      modelConfig.imageUseTextApi ||
      (Boolean(modelConfig.imageApiBaseUrlConfigured || modelConfig.imageApiBaseUrl.trim()) &&
        Boolean(modelConfig.imageApiKeyConfigured || modelConfig.imageApiKey.trim()));
    if (!bridgeAvailable || !window.softCopyright.saveModelConfig) {
      if (modelConfig.mode === "gpt" && ((!modelConfig.apiBaseUrlConfigured && !modelConfig.apiBaseUrl.trim()) || (!modelConfig.apiKeyConfigured && !modelConfig.apiKey.trim()))) {
        setConfigStatus("请填写文本模型请求地址和 API Key");
        return;
      }
      if (modelConfig.mode === "gpt" && !separateImageApiReady) {
        setConfigStatus("请填写独立图片 API 请求地址和 API Key，或选择复用文本 API");
        return;
      }
      setModelConfig((current) => ({
        ...current,
        mode: current.mode === "template" ? "template" : "gpt",
        apiBaseUrlMasked: current.apiBaseUrl.trim() ? "已配置（地址已隐藏）" : current.apiBaseUrlMasked,
        apiBaseUrlConfigured: Boolean(current.apiBaseUrlConfigured || current.apiBaseUrl.trim()),
        apiKeyConfigured: Boolean(current.apiKeyConfigured || current.apiKey.trim()),
        imageApiBaseUrlMasked: current.imageUseTextApi
          ? "未单独配置，将复用文本请求地址"
          : current.imageApiBaseUrl.trim()
            ? "已单独配置（地址已隐藏）"
            : current.imageApiBaseUrlMasked,
        imageApiBaseUrlConfigured: current.imageUseTextApi
          ? false
          : Boolean(current.imageApiBaseUrlConfigured || current.imageApiBaseUrl.trim()),
        imageApiKeyConfigured: current.imageUseTextApi
          ? false
          : Boolean(current.imageApiKeyConfigured || current.imageApiKey.trim())
      }));
      setConfigStatus("saved");
      return;
    }
    setConfigStatus("saving");
    const response = await window.softCopyright.saveModelConfig({
      mode: modelConfig.mode,
      textProvider: modelConfig.textProvider || "custom",
      modelName: modelConfig.modelName,
      outlineModelName: modelConfig.outlineModelName || modelConfig.modelName,
      frontendModelName: modelConfig.frontendModelName || modelConfig.modelName,
      frontendWorkers: modelConfig.frontendWorkers || "auto",
      outlineTimeoutSeconds: modelConfig.outlineTimeoutSeconds || 60,
      reasoningEffort: modelConfig.reasoningEffort || "medium",
      apiBaseUrl: modelConfig.apiBaseUrl,
      apiKey: modelConfig.apiKey,
      imageModelName: modelConfig.imageModelName || "gpt-image-2",
      imageUseTextApi: modelConfig.imageUseTextApi,
      imageApiBaseUrl: modelConfig.imageApiBaseUrl,
      imageApiKey: modelConfig.imageApiKey
    });
    if (!response?.ok) {
      setConfigStatus(response?.message || "保存失败");
      return;
    }
    setConfigStatus("saved");
    const plan = modelProviders.find((item) => item.value === response.mode) || modelProviders.find((item) => item.value === "gpt");
    setForm((current) => ({
      ...current,
      modelPlan: plan.value,
      modelProvider: plan.provider,
      modelName: plan.value === "gpt" ? response.modelName || plan.modelName : plan.modelName
    }));
    setModelConfig((current) => ({
      ...current,
      mode: plan.value,
      textProvider: response.textProvider || current.textProvider || "custom",
      providerProfiles: response.providerProfiles || current.providerProfiles || {},
      modelName: response.modelName || current.modelName,
      outlineModelName: response.outlineModelName || current.outlineModelName || response.modelName || current.modelName,
      frontendModelName: response.frontendModelName || current.frontendModelName || response.modelName || current.modelName,
      frontendWorkers: String(response.frontendWorkers || current.frontendWorkers || "auto"),
      outlineTimeoutSeconds: Number(response.outlineTimeoutSeconds || current.outlineTimeoutSeconds || 60),
      reasoningEffort: response.reasoningEffort || current.reasoningEffort || "medium",
      apiBaseUrl: "",
      apiBaseUrlMasked: response.apiBaseUrlMasked || (response.apiBaseUrlConfigured ? "已配置（地址已隐藏）" : "未配置"),
      apiBaseUrlConfigured: Boolean(response.apiBaseUrlConfigured),
      apiKey: "",
      apiKeyConfigured: Boolean(response.apiKeyConfigured),
      imageModelName: response.imageModelName || current.imageModelName || "gpt-image-2",
      imageUseTextApi: response.imageUseTextApi !== false,
      imageApiBaseUrl: "",
      imageApiBaseUrlMasked:
        response.imageApiBaseUrlMasked ||
        (response.imageApiBaseUrlConfigured ? "已单独配置（地址已隐藏）" : "未单独配置，将复用文本请求地址"),
      imageApiBaseUrlConfigured: Boolean(response.imageApiBaseUrlConfigured),
      imageApiKey: "",
      imageApiKeyConfigured: Boolean(response.imageApiKeyConfigured)
    }));
    await refreshModelAccount();
    if (plan.value === "gpt") await refreshAvailableModels(response.textProvider || modelConfig.textProvider || "custom");
  }

  async function refreshAvailableModels(providerOverride = "") {
    const requestedProvider = providerOverride || modelConfig.textProvider || "custom";
    if (form.modelPlan !== "gpt") {
      setModelCatalog({ status: "idle", provider: requestedProvider, models: [], message: "Default Template 使用本地规则，不读取模型目录" });
      return null;
    }
    if (!bridgeAvailable || !window.softCopyright.listAvailableModels) {
      setModelCatalog({ status: "unavailable", provider: requestedProvider, models: [], message: "当前环境不支持自动拉取模型" });
      return null;
    }
    setModelCatalog({ status: "loading", provider: requestedProvider, models: [], message: "" });
    try {
      const response = await window.softCopyright.listAvailableModels();
      const models = Array.isArray(response?.models) ? response.models.filter(Boolean) : [];
      if (!response?.ok) {
        setModelCatalog((current) => current.provider === requestedProvider
          ? { status: "error", provider: requestedProvider, models: [], message: response?.message || "模型列表拉取失败" }
          : current);
        return response;
      }
      setModelCatalog((current) => current.provider === requestedProvider
        ? { status: "loaded", provider: requestedProvider, models, message: `已读取 ${models.length} 个可用模型` }
        : current);
      return response;
    } catch (error) {
      setModelCatalog((current) => current.provider === requestedProvider
        ? { status: "error", provider: requestedProvider, models: [], message: sanitizeErrorMessage(error?.message || "模型列表拉取失败") }
        : current);
      return null;
    }
  }

  async function fetchModelAccount() {
    if (form.modelPlan === "template") {
      return {
        status: "local",
        accountName: "Default Template",
        balanceLabel: "不消耗 token",
        updatedAt: "",
        message: "本地生成模式"
      };
    }
    if (!bridgeAvailable || !window.softCopyright.getModelAccount) return null;
    try {
      return await window.softCopyright.getModelAccount();
    } catch (error) {
      return {
        status: "error",
        accountName: "余额接口异常",
        balanceLabel: "读取失败",
        updatedAt: "",
        message: error?.message || "余额接口请求失败"
      };
    }
  }

  async function refreshModelAccount() {
    setAccount((current) => ({
      ...current,
      status: current.status === "connected" ? "refreshing" : "loading",
      message: ""
    }));
    const response = await fetchModelAccount();
    if (response) setAccount(response);
  }

  function updateQueueTask(taskId, updater) {
    if (!taskId) return;
    setTaskQueue((current) =>
      current.map((task) => {
        if (task.id !== taskId) return task;
        return typeof updater === "function" ? updater(task) : { ...task, ...updater };
      })
    );
  }

  function appendQueueAndGlobalEvent(taskId, event) {
    setEvents((current) => [...current, event].slice(-500));
    if (taskId) {
      updateQueueTask(taskId, (task) => ({
        ...task,
        progress: event.progress || task.progress || 0,
        events: [...(task.events || []), event].slice(-500)
      }));
    }
  }

  function buildGenerationPayloadFromSnapshot(formSnapshot, planSnapshot, promptText, overrides = {}) {
    const cleanName = planSnapshot.softwareName || extractSoftwareName(promptText) || formSnapshot.name;
    const extraInputHint = extractInputSupplement(promptText);
    const planHint = serializePlan(planSnapshot);
    const hintText = [planHint, extraInputHint].filter(Boolean).join(" ");
    const inferredProductType = planSnapshot.productType || formSnapshot.productType || inferProductType(cleanName, hintText);
    return {
      ...formSnapshot,
      ...overrides,
      name: cleanName,
      productType: inferredProductType,
      softwareCategory: formSnapshot.softwareCategory || inferSoftwareCategory(cleanName, hintText),
      language: "自动选择",
      featureHint: [planHint, extraInputHint].filter(Boolean).join("；"),
      businessPlan: planSnapshot
    };
  }

  function resumeOverridesForTask(task) {
    const outputDir = String(task?.recovery?.outputDir || task?.result?.outputDir || "").trim();
    if (!outputDir) return {};
    return {
      resumeOutputDir: outputDir,
      seed: task?.result?.seed || seedFromOutputDir(outputDir) || task?.overrides?.seed || ""
    };
  }

  function createQueuedTaskFromCurrent(overrides = {}, submitMessage = "已加入生成队列", options = {}) {
    const promptText = currentPromptText;
    const planSnapshot = clonePlainObject(options.businessPlanOverride || businessPlan);
    if (!planSnapshot.modules?.length) return null;
    const formSnapshot = clonePlainObject(form);
    const payload = buildGenerationPayloadFromSnapshot(formSnapshot, planSnapshot, promptText, overrides);
    return {
      id: createId("queue"),
      title: payload.name,
      promptText,
      formSnapshot,
      businessPlan: planSnapshot,
      overrides: clonePlainObject(overrides),
      submitMessage,
      autoPlan: false,
      status: "queued",
      phase: "queued",
      progress: 0,
      events: [],
      result: null,
      createdAt: Date.now(),
      startedAt: 0,
      finishedAt: 0
    };
  }

  function enqueueCurrentGeneration(overrides = {}, submitMessage = "已加入生成队列", options = {}) {
    if (!options.force && !canGenerate) return false;
    if (!gptConfigured) {
      setConfigStatus("请先选择文本模型供应商并配置 API Key");
      setSettingsOpen(true);
      return false;
    }
    const task = createQueuedTaskFromCurrent(overrides, submitMessage, options);
    if (!task) return false;
    setTaskQueue((current) => [...current, task]);
    setInputText("");
    setQueuePaused(false);
    setConfigStatus("");
    return true;
  }

  function enqueueQuickTask(promptOverride = "") {
    const promptText = String(promptOverride || inputText).trim();
    const name = extractSoftwareName(promptText);
    if (!name) return;
    if (!gptConfigured) {
      setConfigStatus("请先选择文本模型供应商并配置 API Key");
      setSettingsOpen(true);
      return;
    }
    const extraInputHint = extractInputSupplement(promptText);
    const inferredProductType = inferProductType(name, extraInputHint);
    const formSnapshot = {
      ...clonePlainObject(form),
      name,
      productType: inferredProductType,
      softwareCategory: inferSoftwareCategory(name, extraInputHint),
      language: "自动选择",
      featureHint: extraInputHint
    };
    setTaskQueue((current) => [
      ...current,
      {
        id: createId("queue"),
        title: name,
        promptText,
        formSnapshot,
        businessPlan: null,
        overrides: {},
        submitMessage: `队列任务「${name}」开始生成材料包`,
        autoPlan: true,
        status: "queued",
        phase: "queued",
        progress: 0,
        events: [],
        result: null,
        createdAt: Date.now(),
        startedAt: 0,
        finishedAt: 0
      }
    ]);
    setInputText("");
    setQueuePaused(false);
    setConfigStatus("");
  }

  function removeQueueTask(taskId) {
    const target = taskQueueRef.current.find((task) => task.id === taskId);
    if (target?.status === "running" || target?.status === "planning") return;
    setTaskQueue((current) => current.filter((task) => task.id !== taskId));
  }

  function retryQueueTask(taskId) {
    updateQueueTask(taskId, (task) => {
      const outputDir = String(task.recovery?.outputDir || task.result?.outputDir || "").trim();
      const seed = task.recovery?.seed || task.result?.seed || seedFromOutputDir(outputDir);
      return {
        ...task,
        status: "queued",
        phase: "queued",
        progress: 0,
        events: [],
        result: null,
        startedAt: 0,
        finishedAt: 0,
        autoPlan: !task.businessPlan?.modules?.length,
        recovery: outputDir
          ? {
              ...(task.recovery || {}),
              outputDir,
              seed,
              failedStage: task.phase || task.recovery?.failedStage || ""
            }
          : task.recovery,
        submitMessage: outputDir ? `续跑队列任务「${task.title}」` : `重试队列任务「${task.title}」`
      };
    });
    setQueuePaused(false);
  }

  function restoreRecoverableTask(recoverableTask) {
    if (!recoverableTask?.businessPlan?.modules?.length) {
      setRecoveryStatus("未找到可恢复的确认蓝图");
      return;
    }
    const title = recoverableTask.title || recoverableTask.businessPlan.softwareName || "恢复任务";
    const startedAt = Date.now();
    const restoreEvent = createProcessEvent(
      "start",
      0,
      `已从上次失败输出恢复「${title}」，将复用确认蓝图重新生成材料包`,
      startedAt
    );
    const formSnapshot = {
      ...clonePlainObject(form),
      ...(clonePlainObject(recoverableTask.formSnapshot) || {}),
      name: title,
      featureHint: serializePlan(recoverableTask.businessPlan),
      language: "自动选择"
    };
    const queueTask = {
      id: createId("queue_recovered"),
      title,
      promptText: recoverableTask.promptText || title,
      formSnapshot,
      businessPlan: clonePlainObject(recoverableTask.businessPlan),
      overrides: {},
      submitMessage: `恢复失败任务「${title}」，复用已确认蓝图继续生成材料包`,
      autoPlan: false,
      status: "queued",
      phase: "queued",
      progress: 0,
      events: [restoreEvent],
      result: recoverableTask.errorSummary
        ? {
            ok: false,
            zipPath: "",
            outputDir: recoverableTask.outputDir || "",
            checks: {},
            warnings: [],
            stdout: "",
            stderr: recoverableTask.errorSummary
          }
        : null,
      createdAt: startedAt,
      startedAt: 0,
      finishedAt: 0,
      recovery: {
        outputDir: recoverableTask.outputDir || "",
        seed: recoverableTask.seed || seedFromOutputDir(recoverableTask.outputDir || ""),
        failedStage: recoverableTask.failedStage || "",
        visualReferenceReady: Boolean(recoverableTask.visualReferenceReady)
      }
    };
    setTaskQueue((current) => [...current, queueTask]);
    setRecoverableTasks((current) => current.filter((item) => item.id !== recoverableTask.id));
    setRecoveryStatus(`已恢复「${title}」，任务已加入队列`);
    setQueuePaused(false);
    setBusinessPlan(queueTask.businessPlan);
    setForm((current) => ({ ...current, ...formSnapshot }));
    setOutlineState("confirmed");
    setStatus("editing");
  }

  async function deleteRecoverableTask(recoverableTask) {
    if (!recoverableTask) return;
    const removeKey = String(recoverableTask.id || recoverableTask.outputDir || recoverableTask.title || "");
    const isSameRecoverableTask = (item) => {
      if (recoverableTask.id && item.id === recoverableTask.id) return true;
      if (recoverableTask.outputDir && item.outputDir === recoverableTask.outputDir) return true;
      return Boolean(removeKey) && String(item.id || item.outputDir || item.title || "") === removeKey;
    };
    setRecoverableTasks((current) => current.filter((item) => !isSameRecoverableTask(item)));
    setRecoveryStatus("已删除恢复记录");
    if (!bridgeAvailable || !window.softCopyright.deleteRecoverableTask) return;
    try {
      const response = await window.softCopyright.deleteRecoverableTask({
        id: recoverableTask.id || "",
        outputDir: recoverableTask.outputDir || ""
      });
      if (!response?.ok) {
        throw new Error(response?.message || "删除恢复记录失败");
      }
    } catch (error) {
      setRecoveryStatus(sanitizeErrorMessage(error?.message || "删除恢复记录失败"));
      if (!window.softCopyright.listRecoverableTasks) return;
      try {
        const response = await window.softCopyright.listRecoverableTasks();
        const tasks = Array.isArray(response?.tasks) ? response.tasks : [];
        setRecoverableTasks(tasks);
        if (tasks.length) setRecoveryStatus(`发现 ${tasks.length} 个可恢复的未完成任务`);
      } catch (_refreshError) {
        // Keep the visible error from the delete attempt.
      }
    }
  }

  async function openQueueTaskOutput(taskId, kind = "output") {
    const target = taskQueueRef.current.find((task) => task.id === taskId);
    if (!bridgeAvailable || !target?.result) return;
    const openPath = kind === "zip" ? target.result.zipPath : target.result.outputDir;
    if (openPath) await window.softCopyright.openPath(openPath);
  }

  function toggleQueuePaused() {
    setQueuePaused((current) => !current);
  }

  async function runQueuedTask(taskId) {
    if (queueRunningRef.current) return;
    const initialTask = taskQueueRef.current.find((task) => task.id === taskId);
    if (!initialTask || initialTask.status !== "queued") return;
    queueRunningRef.current = true;
    activeQueueTaskIdRef.current = taskId;
    setActiveQueueTaskId(taskId);
    setCancelRequested(false);
    setResult(null);
    const startedAt = Date.now();
    let task = initialTask;
    let planSnapshot = task.businessPlan ? clonePlainObject(task.businessPlan) : null;
    let formSnapshot = clonePlainObject(task.formSnapshot || {});
    const needsPlan = task.autoPlan || !planSnapshot?.modules?.length;

    try {
      if (needsPlan) {
        const firstEvent = createProcessEvent("outline", 6, `队列任务「${task.title}」开始生成蓝图`, startedAt);
        setStatus("planning");
        setProgress(6);
        setProcessClock({ mode: "outline", startedAt, elapsedMs: 0 });
        setEvents([firstEvent]);
        updateQueueTask(taskId, {
          status: "planning",
          phase: "outline",
          progress: 6,
          events: [firstEvent],
          result: null,
          startedAt,
          finishedAt: 0
        });
        const outlineResponse = await inferBusinessPlan(
          {
            ...formSnapshot,
            name: task.title,
            featureHint: extractInputSupplement(task.promptText)
          },
          startedAt
        );
        if (outlineResponse?.cancelled) {
          const cancelledResult = buildCancelledResult("已中止蓝图生成");
          setResult(cancelledResult);
          setStatus("cancelled");
          setCancelRequested(false);
          setQueuePaused(true);
          updateQueueTask(taskId, {
            status: "cancelled",
            phase: "outline",
            result: cancelledResult,
            finishedAt: Date.now()
          });
          return;
        }
        if (!outlineResponse?.plan?.modules?.length) {
          throw new Error(configStatus || "队列任务蓝图生成失败，请检查文本模型配置或稍后重试");
        }
        planSnapshot = clonePlainObject(outlineResponse.plan);
        formSnapshot = {
          ...formSnapshot,
          productType: planSnapshot.productType || inferProductType(task.title, outlineResponse.hint || ""),
          softwareCategory: inferSoftwareCategory(task.title, outlineResponse.hint || serializePlan(planSnapshot)),
          language: "自动选择",
          featureHint: serializePlan(planSnapshot)
        };
        setBusinessPlan(planSnapshot);
        setFeatureHintMeta({ ...(outlineResponse.meta || {}), _plannedAt: new Date().toLocaleTimeString() });
        setForm((current) => ({
          ...current,
          ...formSnapshot,
          name: task.title,
          featureHint: serializePlan(planSnapshot)
        }));
        setOutlineState("confirmed");
        const readyEvent = createProcessEvent("outline", 100, `队列任务「${task.title}」蓝图完成，准备生成材料包`, startedAt);
        setProgress(100);
        appendQueueAndGlobalEvent(taskId, readyEvent);
        updateQueueTask(taskId, (current) => ({
          ...current,
          businessPlan: planSnapshot,
          formSnapshot,
          autoPlan: false
        }));
      } else {
        setBusinessPlan(planSnapshot);
        setForm((current) => ({
          ...current,
          ...formSnapshot,
          name: task.title,
          featureHint: serializePlan(planSnapshot)
        }));
        setOutlineState("confirmed");
      }

      task = taskQueueRef.current.find((item) => item.id === taskId) || task;
      const payload = buildGenerationPayloadFromSnapshot(
        formSnapshot,
        planSnapshot,
        task.promptText || task.title,
        {
          ...(task.overrides || {}),
          ...resumeOverridesForTask(task)
        }
      );
      await runGenerationPayload(payload, task.submitMessage || `队列任务「${task.title}」开始生成材料包`, {
        queueTaskId: taskId,
        startedAt,
        preserveEvents: needsPlan
      });
    } catch (error) {
      const failedResult = {
        ok: false,
        zipPath: "",
        outputDir: "",
        checks: {},
        warnings: [],
        stdout: "",
        stderr: sanitizeErrorMessage(error?.message || "队列任务异常")
      };
      const failedEvent = createProcessEvent("start", progress || 0, failedResult.stderr, startedAt);
      setResult(failedResult);
      setStatus("error");
      setProcessClock((current) => ({ ...current, elapsedMs: Date.now() - startedAt }));
      appendQueueAndGlobalEvent(taskId, failedEvent);
      updateQueueTask(taskId, {
        status: "error",
        result: failedResult,
        finishedAt: Date.now()
      });
      setQueuePaused(true);
    } finally {
      queueRunningRef.current = false;
      activeQueueTaskIdRef.current = "";
      setActiveQueueTaskId("");
    }
  }

  async function runGenerationPayload(payload, submitMessage = "任务已提交", options = {}) {
    const startedAt = options.startedAt || Date.now();
    const queueTaskId = options.queueTaskId || "";
    const startEvent = createProcessEvent("start", 3, submitMessage, startedAt);
    setStatus("running");
    setResult(null);
    setCancelRequested(false);
    setProgress(3);
    setProcessClock({ mode: "materials", startedAt, elapsedMs: Math.max(0, Date.now() - startedAt) });
    if (options.preserveEvents) {
      appendQueueAndGlobalEvent(queueTaskId, startEvent);
    } else {
      setEvents([startEvent]);
      if (queueTaskId) {
        updateQueueTask(queueTaskId, (task) => ({
          ...task,
          events: [startEvent],
          progress: 3
        }));
      }
    }
    if (queueTaskId) {
      updateQueueTask(queueTaskId, {
        status: "running",
        phase: "materials",
        progress: 3,
        result: null,
        startedAt
      });
    }
    if (!bridgeAvailable) {
      await new Promise((resolve) => setTimeout(resolve, 700));
      const previewResult = {
        ok: true,
        zipPath: "浏览器预览模式：请在 Electron 中运行以调用本地生成器。",
        outputDir: "",
        checks: {},
        warnings: [],
        stdout: buildCommandPreview(payload),
        stderr: "",
        seed: payload.seed || "preview-seed",
        randomness: payload.randomness
      };
      setResult(previewResult);
      setProgress(100);
      setProcessClock((current) => ({ ...current, elapsedMs: Date.now() - startedAt }));
      setStatus("success");
      if (queueTaskId) {
        updateQueueTask(queueTaskId, {
          status: "success",
          phase: "done",
          progress: 100,
          result: previewResult,
          finishedAt: Date.now()
        });
      }
      return previewResult;
    }
    try {
      const rawResponse = await window.softCopyright.generateMaterials(payload);
      const response =
        rawResponse && typeof rawResponse === "object"
          ? rawResponse
          : {
              ok: false,
              zipPath: "",
              outputDir: "",
              checks: {},
              warnings: [],
              stdout: "",
              stderr: "生成任务未返回有效结果"
            };
      const cleanResult = sanitizeResult(response);
      if (response.busy) {
        const active = response.activeStatus || {};
        const busyEvent = createProcessEvent(
          active.stage || "start",
          Number(active.progress || progress || 0),
          active.message || "已有后台材料生成任务正在运行，队列已暂停等待",
          Number(active.startedAt || startedAt)
        );
        setResult(cleanResult);
        setStatus("running");
        setProgress(busyEvent.progress || 0);
        setProcessClock({
          mode: "materials",
          startedAt: Number(active.startedAt || startedAt),
          elapsedMs: Math.max(0, Date.now() - Number(active.startedAt || startedAt))
        });
        appendQueueAndGlobalEvent(queueTaskId, busyEvent);
        if (queueTaskId) {
          updateQueueTask(queueTaskId, (task) => ({
            ...task,
            status: "queued",
            phase: "queued",
            progress: busyEvent.progress || task.progress || 0,
            result: cleanResult,
            finishedAt: 0
          }));
        }
        setQueuePaused(true);
        return cleanResult;
      }
      const finalStatus = response.cancelled ? "cancelled" : response.ok ? "success" : "error";
      setResult(cleanResult);
      setProgress((current) => (response.ok ? 100 : current));
      setProcessClock((current) => ({ ...current, elapsedMs: Date.now() - startedAt }));
      setStatus(finalStatus);
      if (queueTaskId) {
        updateQueueTask(queueTaskId, (task) => ({
          ...task,
          status: finalStatus,
          phase: response.ok ? "done" : task.phase || "materials",
          progress: response.ok ? 100 : task.progress,
          result: cleanResult,
          finishedAt: Date.now()
        }));
        if (!response.ok || response.cancelled) setQueuePaused(true);
      }
      return cleanResult;
    } catch (error) {
      const failedResult = {
        ok: false,
        zipPath: "",
        outputDir: "",
        checks: {},
        warnings: [],
        stdout: "",
        stderr: sanitizeErrorMessage(error?.message || "生成任务异常")
      };
      setResult(failedResult);
      setProcessClock((current) => ({ ...current, elapsedMs: Date.now() - startedAt }));
      setStatus("error");
      if (queueTaskId) {
        updateQueueTask(queueTaskId, {
          status: "error",
          result: failedResult,
          finishedAt: Date.now()
        });
        setQueuePaused(true);
      }
      return failedResult;
    } finally {
      setCancelRequested(false);
      await refreshModelAccount();
    }
  }

  async function handleCancelGeneration() {
    if (!canCancelTask) return;
    const cancelStage = status === "planning" ? "outline" : activeEvent?.stage || "start";
    const startedAt = processClock.startedAt || Date.now();
    setCancelRequested(true);
    setEvents((current) => [
      ...current,
      createProcessEvent(cancelStage, progress || activeEvent?.progress || 0, "已请求中止生成任务，正在停止后台进程", startedAt)
    ]);
    try {
      const response = await window.softCopyright.cancelGeneration();
      if (!response?.ok) {
        setCancelRequested(false);
        setEvents((current) => [
          ...current,
          createProcessEvent(cancelStage, progress || activeEvent?.progress || 0, response?.message || "当前没有可中止的生成任务", startedAt)
        ]);
      }
    } catch (error) {
      setCancelRequested(false);
      setEvents((current) => [
        ...current,
        createProcessEvent(cancelStage, progress || activeEvent?.progress || 0, sanitizeErrorMessage(error?.message || "中止请求发送失败"), startedAt)
      ]);
    }
  }

  async function handlePrimaryAction() {
    if (isGeneratingStatus) {
      if (canQueueQuickTask) {
        enqueueQuickTask();
        return;
      }
      await handleCancelGeneration();
      return;
    }
    if (!canPrimaryAction) return;
    if (!gptConfigured) {
      setConfigStatus("请先选择文本模型供应商并配置 API Key");
      setSettingsOpen(true);
      return;
    }
    if (canRetryFromConfirmedOutline) {
      await retryFromConfirmedOutline();
      return;
    }
    if (outlineState !== "draft" && outlineState !== "confirmed") {
      if (form.blueprintReviewBeforeGeneration) {
        await regeneratePlan();
      } else {
        enqueueQuickTask(currentPromptText);
      }
      return;
    }
    if (outlineState === "draft") {
      setOutlineState("confirmed");
      await handleGenerate({}, "蓝图已确认，开始生成材料包", { force: true });
      return;
    }
    await handleGenerate({}, "蓝图已确认，开始生成材料包");
  }

  async function retryFromConfirmedOutline() {
    const outputDir = String(result?.outputDir || "").trim();
    await handleGenerate(
      outputDir
        ? { resumeOutputDir: outputDir, seed: result?.seed || seedFromOutputDir(outputDir) }
        : result?.seed
          ? { seed: result.seed }
          : {},
      outputDir ? "保留已确认蓝图，从失败阶段续跑材料包" : "保留已确认蓝图，从失败阶段重新生成材料包",
      { force: true, retry: true }
    );
  }

  async function handleGenerate(overrides = {}, submitMessage = "任务已提交", options = {}) {
    enqueueCurrentGeneration(overrides, submitMessage, options);
  }

  async function openZip() {
    if (bridgeAvailable && result?.zipPath) await window.softCopyright.openPath(result.zipPath);
  }

  async function openOutputDir() {
    if (bridgeAvailable && result?.outputDir) await window.softCopyright.openPath(result.outputDir);
  }

  async function openGeneratedFile(file) {
    if (bridgeAvailable && file?.path) await window.softCopyright.openPath(file.path);
  }

  function continueEditing() {
    setStatus("editing");
    setResult(null);
    setProgress(100);
    setCancelRequested(false);
  }

  function newTask() {
    setForm((current) => ({
      ...current,
      name: "",
      productType: "APP",
      softwareCategory: "应用软件",
      language: "自动选择",
      featureHint: "",
      version: "V1.0"
    }));
    setInputText("");
    setBusinessPlan(createEmptyPlan());
    setFeatureHintMeta({});
    setOutlineState("empty");
    setEvents([]);
    setResult(null);
    setProgress(0);
    setCancelRequested(false);
    setProcessClock({ mode: "idle", startedAt: 0, elapsedMs: 0 });
    setStatus("idle");
  }

  return (
    <main className="workbench">
      <header className="top-shell">
        <div className="top-strip">
          <div className="brand-lockup">
            <img src={appIcon} alt="" className="brand-icon" />
            <div>
              <p className="eyebrow">Soft Copyright AI Workbench</p>
              <h1>软著材料 AI 工作台</h1>
            </div>
          </div>
          <div className="top-actions">
            <span className={`task-pill ${status}`}>{taskStatusText}</span>
            <button className="model-summary-button" type="button" onClick={() => setSettingsOpen(true)} title="选择模型和推理强度">
              <Sparkles size={16} />
              <span>{modelConfig.modelName || "选择模型"}</span>
              <em>{reasoningEffortLabels[modelConfig.reasoningEffort] || "中"}</em>
              <ChevronDown size={15} />
            </button>
          </div>
        </div>
        <WorkflowNavigator status={status} outlineState={outlineState} planReady={planReady} />
      </header>

      <section className="workspace-stage">
        <TaskTranscript
          status={status}
          form={form}
          businessPlan={businessPlan}
          outlineState={outlineState}
          featureHintMeta={featureHintMeta}
          progress={progress}
          events={events}
          processClock={processClock}
          activeEvent={activeEvent}
          result={result}
          qualityItems={qualityItems}
          generatedFiles={generatedFiles}
          taskQueue={taskQueue}
          activeQueueTaskId={activeQueueTaskId}
          queuePaused={queuePaused}
          queueSummary={queueSummary}
          recoverableTasks={recoverableTasks}
          recoveryStatus={recoveryStatus}
          bridgeAvailable={bridgeAvailable}
          canPlan={canPlan}
          configStatus={configStatus}
          onRegeneratePlan={regeneratePlan}
          onAddModule={addModule}
          onRemoveModule={removeModule}
          onUpdateModule={updateModule}
          onRegenerateModule={regenerateModule}
          onAddChild={addChild}
          onRemoveChild={removeChild}
          onUpdateChild={updateChild}
          onOpenFile={openGeneratedFile}
          onToggleQueuePaused={toggleQueuePaused}
          onRemoveQueueTask={removeQueueTask}
          onRetryQueueTask={retryQueueTask}
          onOpenQueueTaskOutput={openQueueTaskOutput}
          onRestoreRecoverableTask={restoreRecoverableTask}
          onDeleteRecoverableTask={deleteRecoverableTask}
          canRetryGenerate={canRetryFromConfirmedOutline}
        />
      </section>

      <footer className={`command-bar ${status === "success" ? "completed" : ""}`}>
        {status === "success" && result?.ok ? (
          <div className="result-command-row">
            <button type="button" className="primary-result" onClick={openZip} disabled={!result?.zipPath || !bridgeAvailable}>
              <Archive size={18} />
              <span>打开材料包</span>
            </button>
            <button type="button" onClick={openOutputDir} disabled={!result?.outputDir || !bridgeAvailable}>
              <FolderOpen size={18} />
              <span>打开输出目录</span>
            </button>
            <button type="button" onClick={() => handleGenerate({}, "基于当前模块重新生成")} disabled={!canGenerate}>
              <RefreshCw size={18} />
              <span>基于当前加入队列</span>
            </button>
            <button type="button" onClick={continueEditing}>
              <FileText size={18} />
              <span>继续修改模块</span>
            </button>
            <button type="button" className="quiet-button" onClick={newTask}>
              <Plus size={18} />
              <span>新建任务</span>
            </button>
          </div>
        ) : status === "error" && result && !result.ok ? (
          <div className="result-command-row failure-actions">
            <button
              type="button"
              className="primary-result"
              onClick={retryFromConfirmedOutline}
              disabled={!canRetryFromConfirmedOutline}
              title={result?.outputDir ? "保留已确认蓝图，从失败阶段续跑材料包" : "保留已确认蓝图，重新生成材料包"}
            >
              <RefreshCw size={18} />
              <span>保留蓝图重试</span>
            </button>
            <button type="button" onClick={continueEditing} disabled={!planReady}>
              <FileText size={18} />
              <span>继续修改蓝图</span>
            </button>
            <button type="button" className="quiet-button" onClick={newTask}>
              <Plus size={18} />
              <span>新建任务</span>
            </button>
          </div>
        ) : (
          <div className="prompt-dock">
            <div className="prompt-caption">
              <span className="prompt-caption-icon">{isGeneratingStatus ? <Plus size={16} /> : <FileText size={16} />}</span>
              <div>
                <strong>{isGeneratingStatus ? "继续添加任务" : "创建软著材料任务"}</strong>
                <small>{isGeneratingStatus ? "当前任务生成期间，新任务会进入顺序队列" : "只需输入软件名称，系统会自动规划并生成完整材料包"}</small>
              </div>
            </div>
            <div className="prompt-row">
              <textarea
                value={promptTextareaValue}
                onChange={(event) => handlePromptTextChange(event.target.value)}
                placeholder={promptPlaceholder}
              />
              <button className={`primary-action ${isGeneratingStatus && !canQueueQuickTask ? "danger" : ""} ${cancelRequested ? "loading" : ""}`} type="button" disabled={!canPrimaryAction} onClick={handlePrimaryAction}>
                {isGeneratingStatus ? canQueueQuickTask ? <Plus size={20} /> : cancelRequested ? <Loader2 size={20} /> : <Square size={20} /> : <Sparkles size={20} />}
                <span>{primaryActionLabel}</span>
              </button>
            </div>
          </div>
        )}
      </footer>

      <SettingsDrawer
        open={settingsOpen}
        form={form}
        modelConfig={modelConfig}
        account={account}
        modelCatalog={modelCatalog}
        configStatus={configStatus}
        bridgeAvailable={bridgeAvailable}
        onClose={() => setSettingsOpen(false)}
        onUpdateField={updateField}
        onUpdateModelPlan={updateModelPlan}
        onUpdateModelConfig={updateModelConfig}
        onSaveModelConfig={saveModelConfig}
        onRefreshAccount={refreshModelAccount}
        onRefreshModels={refreshAvailableModels}
      />
    </main>
  );
}

function WorkflowNavigator({ status, outlineState, planReady }) {
  const activeIndex = workflowStageIndex(status, outlineState, planReady);
  return (
    <nav className="workflow-nav" aria-label="材料生成流程">
      {workflowStages.map((label, index) => {
        const done = index < activeIndex || status === "success";
        const active = index === activeIndex && status !== "success";
        return (
          <div className={`workflow-step ${done ? "done" : ""} ${active ? "active" : ""}`} key={label}>
            <span className="workflow-index">{done ? <CheckCircle2 size={15} /> : index + 1}</span>
            <b>{label}</b>
            {index < workflowStages.length - 1 && <i />}
          </div>
        );
      })}
    </nav>
  );
}

function TaskTranscript({
  status,
  form,
  businessPlan,
  outlineState,
  featureHintMeta,
  progress,
  events,
  processClock,
  activeEvent,
  result,
  qualityItems,
  generatedFiles,
  taskQueue,
  activeQueueTaskId,
  queuePaused,
  queueSummary,
  recoverableTasks,
  recoveryStatus,
  bridgeAvailable,
  canPlan,
  configStatus,
  onRegeneratePlan,
  onAddModule,
  onRemoveModule,
  onUpdateModule,
  onRegenerateModule,
  onAddChild,
  onRemoveChild,
  onUpdateChild,
  onOpenFile,
  onToggleQueuePaused,
  onRemoveQueueTask,
  onRetryQueueTask,
  onOpenQueueTaskOutput,
  onRestoreRecoverableTask,
  onDeleteRecoverableTask,
  canRetryGenerate
}) {
  const planReady = businessPlan.modules.length > 0;
  const elapsedLabel = processClock.elapsedMs ? `已用 ${formatElapsed(processClock.elapsedMs)}` : "";

  return (
    <div className="transcript">
      <QueuePanel
        taskQueue={taskQueue}
        activeQueueTaskId={activeQueueTaskId}
        queuePaused={queuePaused}
        queueSummary={queueSummary}
        recoverableTasks={recoverableTasks}
        recoveryStatus={recoveryStatus}
        bridgeAvailable={bridgeAvailable}
        onToggleQueuePaused={onToggleQueuePaused}
        onRemoveQueueTask={onRemoveQueueTask}
        onRetryQueueTask={onRetryQueueTask}
        onOpenQueueTaskOutput={onOpenQueueTaskOutput}
        onRestoreRecoverableTask={onRestoreRecoverableTask}
        onDeleteRecoverableTask={onDeleteRecoverableTask}
      />

      {(status === "planning" || status === "editing" || status === "idle") &&
        (form.blueprintReviewBeforeGeneration || status === "planning" || planReady) && (
        <section className="work-section editor-section">
          <div className="section-toolbar">
            <div>
              <strong>详细蓝图</strong>
              <span>
                {status === "planning" && elapsedLabel
                  ? `AI 生成中 · ${elapsedLabel}`
                  : planReady
                    ? `${businessPlan.modules.length} 个模块 · ${outlineStatusLabel(outlineState, planReady)}`
                    : form.blueprintReviewBeforeGeneration
                      ? "点击生成蓝图后开始审阅"
                      : "系统会自动规划后直接生成材料"}
              </span>
            </div>
            <button type="button" onClick={onRegeneratePlan} disabled={!canPlan || status === "planning"}>
              <RefreshCw size={15} />
              <span>{status === "planning" ? "生成中" : "重新生成蓝图"}</span>
            </button>
          </div>
          {status === "planning" && <OutlineProgress progress={progress} events={events} elapsedMs={processClock.elapsedMs} />}
          {planReady ? (
            <ModuleTreeEditor
              plan={businessPlan}
              onAddModule={onAddModule}
              onRemoveModule={onRemoveModule}
              onUpdateModule={onUpdateModule}
              onRegenerateModule={onRegenerateModule}
            />
          ) : status === "planning" ? null : (
            <div className="empty-plan compact-empty brand-empty">
              <div className="empty-brand-visual">
                <FileCheck2 size={42} />
                <Sparkles size={20} />
              </div>
              <strong>
                {canPlan && configStatus && configStatus !== "saved" && configStatus !== "saving"
                  ? "蓝图生成未完成"
                  : canPlan
                    ? form.blueprintReviewBeforeGeneration
                      ? "等待生成蓝图"
                      : "等待开始生成"
                    : "等待输入软件名称"}
              </strong>
              <p>
                {canPlan && configStatus && configStatus !== "saved" && configStatus !== "saving"
                  ? configStatus
                  : canPlan
                    ? form.blueprintReviewBeforeGeneration
                      ? "点击底部“生成蓝图”后，这里会显示生成进度和可编辑的详细蓝图。"
                      : "点击底部“开始生成”后，系统会自动完成规划、确认和材料生成。"
                    : "输入软件名称后，点击底部按钮生成详细蓝图。"}
              </p>
              <div className="empty-feature-list">
                <span>AI 业务蓝图</span>
                <span>界面与手册</span>
                <span>源码与材料包</span>
              </div>
            </div>
          )}
        </section>
      )}

      {(status === "running" || status === "success" || status === "error" || status === "cancelled") && (
        <section className="work-section log-section">
          <div className="section-toolbar">
            <div>
              <strong>生成过程</strong>
              <span>{Math.min(100, progress)}%{elapsedLabel ? ` · ${elapsedLabel}` : ""}</span>
            </div>
          </div>
          <div className="progress-track large">
            <div style={{ width: `${Math.min(100, progress)}%` }} />
          </div>
          <GenerationProcessBoard events={events} status={status} progress={progress} elapsedMs={processClock.elapsedMs} result={result} />
        </section>
      )}

      {result && (
        <section className={`work-section result-message ${result.ok ? "success" : result.cancelled ? "cancelled" : "error"}`}>
          <div className="section-toolbar">
            <div>
              <strong>{result.ok ? "结果报告" : result.cancelled ? "中止报告" : "失败报告"}</strong>
              <span>{result.ok ? "已完成" : result.cancelled ? "已中止" : "需要处理"}</span>
            </div>
          </div>
          {result.ok ? (
            <ResultReport
              result={result}
              qualityItems={qualityItems}
              generatedFiles={generatedFiles}
              bridgeAvailable={bridgeAvailable}
              onOpenFile={onOpenFile}
            />
          ) : (
            <div className="error-report">
              {result.cancelled ? <Square size={22} /> : <AlertTriangle size={22} />}
              <div>
                <p>{result.stderr || (result.cancelled ? "生成任务已中止。" : "生成任务异常，请查看运行日志定位问题。")}</p>
                <VisualReferenceFailureHint result={result} />
                {canRetryGenerate ? (
                  <small>已保留当前确认的蓝图，重试会直接复用蓝图并继续生成材料包。</small>
                ) : (
                  <small>请先返回蓝图检查软件名称、模块和文本模型配置，再重新提交。</small>
                )}
              </div>
            </div>
          )}
        </section>
      )}
    </div>
  );
}

function QueuePanel({
  taskQueue,
  activeQueueTaskId,
  queuePaused,
  queueSummary,
  recoverableTasks,
  recoveryStatus,
  bridgeAvailable,
  onToggleQueuePaused,
  onRemoveQueueTask,
  onRetryQueueTask,
  onOpenQueueTaskOutput,
  onRestoreRecoverableTask,
  onDeleteRecoverableTask
}) {
  const visibleTasks = taskQueue.slice(-8);
  const hasTasks = taskQueue.length > 0;
  const runningTask = taskQueue.find((task) => task.status === "running" || task.status === "planning");
  const canToggleQueue = hasTasks && (queuePaused ? queueSummary.queued > 0 : queueSummary.queued > 0);
  const recoverableVisible = (recoverableTasks || []).slice(0, 3);
  const summaryText = hasTasks
    ? `${queueSummary.total} 项 · ${queueSummary.queued} 等待 · ${queueSummary.running} 运行 · ${queueSummary.success} 完成`
    : "可在底部输入框追加任务，队列会按顺序一个一个生成";
  return (
    <section className="work-section queue-section">
      <div className="queue-compact-head">
        <div className="queue-title-group">
          <span className="queue-brand-mark"><ListOrdered size={18} /></span>
          <div>
            <strong>顺序队列</strong>
            <span>{queuePaused ? "已暂停后续任务" : runningTask ? `正在处理：${runningTask.title}` : summaryText}</span>
          </div>
        </div>
        <button type="button" onClick={onToggleQueuePaused} disabled={!canToggleQueue}>
          {queuePaused ? <RefreshCw size={15} /> : <Square size={15} />}
          <span>{queuePaused ? "继续队列" : "暂停后续"}</span>
        </button>
      </div>
      {recoverableVisible.length > 0 && (
        <div className="queue-recovery-strip">
          <span className="queue-recovery-label">{recoveryStatus || "发现上次未完成任务"}</span>
          {recoverableVisible.map((task) => (
            <span className="queue-recovery-item" key={task.id || task.outputDir || task.title}>
              <button type="button" className="queue-recovery-action" onClick={() => onRestoreRecoverableTask(task)} title={`恢复 ${task.title || "任务"}`}>
                <RefreshCw size={15} />
                <span>恢复 {task.title}</span>
              </button>
              <button
                type="button"
                className="queue-recovery-delete"
                onClick={() => onDeleteRecoverableTask(task)}
                aria-label={`删除恢复记录 ${task.title || ""}`}
                title="删除恢复记录"
              >
                <Trash2 size={14} />
              </button>
            </span>
          ))}
        </div>
      )}
      {hasTasks && (
        <div className="queue-list">
          {visibleTasks.map((task) => {
            const active = task.id === activeQueueTaskId;
            const latestEvent = task.events?.length ? task.events[task.events.length - 1] : null;
            const canRetry = task.status === "error" || task.status === "cancelled";
            const canRemove = task.status !== "running" && task.status !== "planning";
            return (
              <div className={`queue-row ${task.status} ${active ? "active" : ""}`} key={task.id}>
                <span className="queue-status-dot" />
                <div className="queue-row-main">
                  <p>
                    <strong>{task.title}</strong>
                    <em>{queueTaskStatusLabel(task)}</em>
                  </p>
                  <small>{latestEvent?.message || queueTaskMeta(task)}</small>
                  <div className="queue-row-progress">
                    <span style={{ width: `${Math.min(100, task.progress || 0)}%` }} />
                  </div>
                </div>
                <div className="queue-row-actions">
                  {task.result?.ok && (
                    <button
                      type="button"
                      title="打开输出目录"
                      disabled={!bridgeAvailable || !task.result?.outputDir}
                      onClick={() => onOpenQueueTaskOutput(task.id, "output")}
                    >
                      <FolderOpen size={15} />
                    </button>
                  )}
                  {canRetry && (
                    <button
                      type="button"
                      title={task.recovery?.outputDir || task.result?.outputDir ? "保留蓝图并从失败阶段续跑" : "重试该任务"}
                      onClick={() => onRetryQueueTask(task.id)}
                    >
                      <RefreshCw size={15} />
                    </button>
                  )}
                  <button type="button" title="移除任务" disabled={!canRemove} onClick={() => onRemoveQueueTask(task.id)}>
                    <Trash2 size={15} />
                  </button>
                </div>
              </div>
            );
          })}
          {taskQueue.length > visibleTasks.length && <small className="queue-more">仅显示最近 {visibleTasks.length} 项，共 {taskQueue.length} 项</small>}
        </div>
      )}
    </section>
  );
}

function ModuleTreeEditor({ plan, onAddModule, onRemoveModule, onUpdateModule, onRegenerateModule }) {
  const categories = plan.modules.map((module) => (module.category || "").trim()).filter(Boolean);
  const showCategory = categories.length > 0 && !(categories.every((item) => item === "核心模块") || new Set(categories).size === 1);
  return (
    <div className={`module-tree ${showCategory ? "" : "no-category"}`}>
      <div className="tree-root">
        <b>{plan.softwareName || "当前软件"}</b>
        <span>{plan.domain || "业务域自动识别"} · {plan.modules.length} 个蓝图模块</span>
      </div>
      <div className="module-table-head">
        <span>序号</span>
        {showCategory && <span>分类</span>}
        <span>模块</span>
        <span>蓝图说明</span>
        <span />
      </div>
      {plan.modules.map((module, index) => (
        <div className="module-node" key={module.id}>
          <div className="module-index">{String(index + 1).padStart(2, "0")}</div>
          {showCategory && (
            <input
              className="module-category-input"
              aria-label={`模块分类 ${index + 1}`}
              value={module.category || ""}
              onChange={(event) => onUpdateModule(module.id, "category", event.target.value)}
            />
          )}
          <input
            className="module-title-input"
            aria-label={`蓝图模块 ${index + 1}`}
            value={module.title}
            onChange={(event) => onUpdateModule(module.id, "title", event.target.value)}
          />
          <div className="module-detail-cell">
            <textarea
              className="module-desc-input"
              aria-label={`业务说明 ${index + 1}`}
              value={module.description || ""}
              onChange={(event) => onUpdateModule(module.id, "description", event.target.value)}
            />
            {moduleHasDetails(module) && (
              <div className="module-meta-line">
                {module.dataObjects?.length ? <span>对象：{module.dataObjects.slice(0, 3).join("、")}</span> : null}
                {module.userFlow?.length ? <span>流程：{module.userFlow.slice(0, 3).join(" / ")}</span> : null}
                {module.screens?.length ? <span>页面：{module.screens.slice(0, 3).join("、")}</span> : null}
              </div>
            )}
          </div>
          <div className="module-actions">
            <button type="button" className="regenerate-module" onClick={() => onRegenerateModule(module.id)} title="重新生成该模块">
              <RefreshCw size={15} />
            </button>
            <button type="button" className="delete-module" onClick={() => onRemoveModule(module.id)} title="删除蓝图模块">
              <Trash2 size={16} />
            </button>
          </div>
        </div>
      ))}
      <button type="button" className="add-module" onClick={onAddModule}>
        <Plus size={16} />
        <span>新增业务补充</span>
      </button>
    </div>
  );
}

function OutlineProgress({ progress, events, elapsedMs }) {
  const latest = events.length ? events[events.length - 1] : null;
  return (
    <div className="outline-progress">
      <div className="outline-progress-head">
        <div>
          <strong>AI 正在生成蓝图</strong>
          <span>{latest?.message || "正在生成详细蓝图"}</span>
        </div>
        <b>{formatElapsed(elapsedMs || latest?.elapsedMs || 0)}</b>
      </div>
      <div className="progress-track large">
        <div style={{ width: `${Math.min(100, progress || 6)}%` }} />
      </div>
      <div className="outline-log">
        {events.slice(-8).map((event, index) => {
          const isLatest = index === events.slice(-8).length - 1;
          return (
            <div className={`outline-log-row ${isLatest ? "typing" : ""}`} key={`${event.at}-${index}-${event.progress}`}>
              <small>{event.at || "--:--:--"} · {formatElapsed(event.elapsedMs || 0)}</small>
              <span>{event.message}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function GenerationProcessBoard({ events, status, progress, elapsedMs, result }) {
  const latest = events.length ? events[events.length - 1] : null;
  const visibleEvents = events.length ? events : fallbackResultEvents(result);
  return (
    <div className="process-board compact">
      <ProcessTextStream
        events={visibleEvents}
        status={status}
        progress={progress}
        elapsedMs={elapsedMs || latest?.elapsedMs || 0}
      />
    </div>
  );
}

function ProcessTextStream({ events, status, progress, elapsedMs }) {
  const messages = buildProcessConversation(events, status);
  const latest = messages.length ? messages[messages.length - 1] : null;
  const compactStages = compactStageStatus(events, status);
  const currentProgress = Math.min(100, progress || latest?.event?.progress || 0);
  const currentElapsed = formatElapsed(elapsedMs || latest?.event?.elapsedMs || 0);
  return (
    <section className="process-compact-panel">
      <div className={`process-current ${status}`}>
        <span className="process-current-icon">{processStatusIcon(status, latest?.event?.stage)}</span>
        <div>
          <strong>{latest?.event?.stage ? stageLabel(latest.event.stage) : processTitle(status)}</strong>
          <p>{latest?.message || "等待生成过程开始"}</p>
        </div>
        <b>{currentProgress}%</b>
        <small>{currentElapsed}</small>
      </div>

      <details className="process-detail-details">
        <summary>
          <span>过程详情</span>
          <b>{messages.length} 条</b>
          <ChevronDown size={15} />
        </summary>
        <div className="process-stage-strip">
          {compactStages.map((item) => (
            <span className={item.state} key={item.key}>{item.label}</span>
          ))}
        </div>
        <div className="process-text-list">
          {messages.map((item, index) => {
            const latestRow = index === messages.length - 1;
            const rowState = latestRow && ["planning", "running"].includes(status) ? "in-progress" : "completed";
            const rowMeta = processRowMeta(item);
            return (
              <div className={`process-text-row ${rowState}`} key={`${item.event.at}-${item.event.stage}-${index}`}>
                <span className={`process-text-node ${rowState}`} title={rowState === "completed" ? "已完成" : "进行中"}>
                  {rowState === "completed" ? <CheckCircle2 size={15} /> : <Loader2 size={15} />}
                </span>
                <div>
                  <p>
                    <b>{item.actor}</b>
                    <span>{item.message}</span>
                  </p>
                  {rowMeta && <small>{rowMeta}</small>}
                </div>
              </div>
            );
          })}
        </div>
      </details>
    </section>
  );
}

function ProcessConversation({ events, status }) {
  const messages = buildProcessConversation(events, status);
  return (
    <section className="process-conversation">
      <div className="process-conversation-head">
        <div>
          <strong>过程对话</strong>
          <span>{conversationStatusLabel(status, messages)}</span>
        </div>
        <b>{messages.length} 条</b>
      </div>
      <div className="process-conversation-list">
        {messages.map((item, index) => {
          const latest = index === messages.length - 1;
          return (
            <article className={`process-message ${latest ? "latest" : ""}`} key={`${item.event.at}-${item.event.stage}-${index}`}>
              <span className={`process-avatar ${item.tone}`}>{item.avatar}</span>
              <div className="process-bubble">
                <div className="process-bubble-meta">
                  <strong>{item.actor}</strong>
                  <span>{item.event.at || "--:--:--"} · {stageLabel(item.event.stage)} · {item.event.progress || 0}%</span>
                </div>
                <p>{item.message}</p>
                {item.detail && <small>{item.detail}</small>}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function StageDetailGrid({ events, status }) {
  const groups = groupEventsByStage(events);
  const latestStage = events.length ? events[events.length - 1].stage : "";
  return (
    <div className="stage-detail-grid">
      {generationStages.map(([key, label]) => {
        const stageEvents = groups.get(key) || [];
        const state = stageState(key, stageEvents, latestStage, status);
        const last = stageEvents.length ? stageEvents[stageEvents.length - 1] : null;
        const plannedSteps = stagePlannedSteps[key] || [];
        return (
          <div className={`stage-detail ${state}`} key={key}>
            <div className="stage-detail-head">
              <span>{stageStateIcon(state)}</span>
              <strong>{label}</strong>
              <em>{stageCountLabel(key, stageEvents)}</em>
            </div>
            <p>{stageSummary(key, last)}</p>
            {plannedSteps.length > 0 ? (
              <div className="stage-mini-events planned">
                {plannedSteps.map((step, index) => (
                  <span className={plannedStepState(key, stageEvents, step)} key={`${key}-planned-${index}`}>
                    {step.label}
                  </span>
                ))}
              </div>
            ) : (
              stageEvents.length > 1 && (
                <div className="stage-mini-events">
                  {stageEvents.slice(-3).map((event, index) => (
                    <span key={`${key}-${index}-${event.progress}`}>{event.message}</span>
                  ))}
                </div>
              )
            )}
          </div>
        );
      })}
    </div>
  );
}

function ProcessEventFeed({ events }) {
  return (
    <div className="process-feed">
      <div className="process-feed-head">
        <strong>实时步骤</strong>
        <span>{events.length} 条事件</span>
      </div>
      <div className="process-feed-list">
        {events.slice(-180).map((event, index) => {
          const latest = index === events.slice(-180).length - 1;
          return (
            <div className={`process-event ${latest ? "latest" : ""}`} key={`${event.at}-${event.stage}-${event.progress}-${index}`}>
              <span className="process-event-dot">{String(index + 1).padStart(2, "0")}</span>
              <div>
                <small>
                  {event.at || "--:--:--"} · {stageLabel(event.stage)} · {event.progress || 0}%{event.elapsedMs ? ` · ${formatElapsed(event.elapsedMs)}` : ""}
                </small>
                <strong>{event.message}</strong>
                {processEventDetail(event) && <p>{processEventDetail(event)}</p>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function StageTimeline({ events, status }) {
  const stageProgress = new Map();
  for (const event of events) {
    if (event.stage) stageProgress.set(event.stage, event.progress || 0);
  }
  const currentStage = events.length ? events[events.length - 1].stage : "";
  return (
    <div className="stage-timeline">
      {generationStages.map(([key, label]) => {
        const seen = stageProgress.has(key);
        const done = status === "success" || (seen && (stageProgress.get(key) || 0) < (events[events.length - 1]?.progress || 0));
        const active = currentStage === key && status === "running";
        return (
          <div className={`stage-step ${done ? "done" : ""} ${active ? "active" : ""}`} key={key}>
            <span>{done ? <CheckCircle2 size={14} /> : active ? <Loader2 size={14} /> : null}</span>
            <b>{label}</b>
          </div>
        );
      })}
    </div>
  );
}

function ResultReport({ result, qualityItems, generatedFiles, bridgeAvailable, onOpenFile }) {
  return (
    <div className="result-report">
      <div className="result-hero">
        <span className="result-hero-icon"><CheckCircle2 size={30} /></span>
        <div>
          <small>DELIVERY READY</small>
          <strong>软著材料包已准备完成</strong>
          <p>说明书、源码鉴别材料、申请信息与校验报告已完成汇总。</p>
        </div>
        <em>{generatedFiles.length || 0} 个文件</em>
      </div>
      <div className="report-paths">
        <div>
          <small>输出目录</small>
          <b>{result.outputDir || "未返回"}</b>
        </div>
        <div>
          <small>材料包</small>
          <b>{result.zipPath || "未返回"}</b>
        </div>
      </div>
      <DeliveryStatus result={result} />
      <div className="quality-grid">
        {qualityItems.slice(0, 6).map((item) => (
          <div className={`quality-item ${item.state}`} key={item.label}>
            <span>{qualityIcon(item.state)}</span>
            <div>
              <strong>{item.label}</strong>
              <p>{item.value}</p>
              {item.detail && <small>{item.detail}</small>}
            </div>
          </div>
        ))}
      </div>
      <details className="report-details">
        <summary>
          <FileCheck2 size={16} />
          <span>文件与校验详情</span>
          <ChevronDown size={16} />
        </summary>
        <div className="file-list">
          {generatedFiles.length ? (
            generatedFiles.slice(0, 12).map((file) => (
              <button
                className="file-row"
                key={file.path || file.name}
                type="button"
                title={bridgeAvailable ? file.path : "Electron 中可打开文件"}
                disabled={!bridgeAvailable}
                onClick={() => onOpenFile(file)}
              >
                {file.icon}
                <span>{file.name}</span>
              </button>
            ))
          ) : (
            <p>本次未返回文件列表。</p>
          )}
        </div>
      </details>
    </div>
  );
}

function SettingsDrawer({
  open,
  form,
  modelConfig,
  account,
  modelCatalog,
  configStatus,
  bridgeAvailable,
  onClose,
  onUpdateField,
  onUpdateModelPlan,
  onUpdateModelConfig,
  onSaveModelConfig,
  onRefreshAccount,
  onRefreshModels
}) {
  const selectedTextProvider = textProviderChoices.find((item) => item.value === modelConfig.textProvider) || textProviderChoices[0];
  const providerFallbackModels = providerModelChoices[selectedTextProvider.value] || [selectedTextProvider.defaultModel];
  const catalogModels = modelCatalog.provider === selectedTextProvider.value && modelCatalog.models.length
    ? modelCatalog.models
    : [...new Set([modelConfig.modelName, modelConfig.outlineModelName, modelConfig.frontendModelName, ...providerFallbackModels].filter(Boolean))];
  return (
    <div
      className={`drawer-backdrop ${open ? "open" : ""}`}
      onClick={(event) => {
        if (open && event.target === event.currentTarget) onClose();
      }}
      aria-hidden={!open}
    >
      <aside className="settings-drawer" aria-label="高级设置" onClick={(event) => event.stopPropagation()}>
        <header>
          <div className="settings-brand-lockup">
            <span className="settings-brand-symbol"><SlidersHorizontal size={21} /></span>
            <div>
              <p className="eyebrow">Advanced</p>
              <h2>高级设置</h2>
            </div>
          </div>
          <button className="icon-button" type="button" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="settings-scroll-content">
        <section>
          <SettingsSectionHeading icon={<FileText size={17} />} title="生成参数" description="控制版本与内容差异度" />
          <div className="drawer-grid">
            <label>
              <span>版本号</span>
              <input value={form.version} onChange={(event) => onUpdateField("version", event.target.value)} />
            </label>
            <label>
              <span>随机性</span>
              <select value={form.randomness} onChange={(event) => onUpdateField("randomness", event.target.value)}>
                <option value="conservative">保守</option>
                <option value="standard">标准</option>
                <option value="high-variance">高差异</option>
              </select>
            </label>
          </div>
        </section>
        <section>
          <SettingsSectionHeading icon={<Sparkles size={17} />} title="AI 配置" description="账户连接和生成模式" />
          <div className="model-option-grid">
            {modelProviders.map((item) => (
              <button
                key={item.value}
                className={form.modelPlan === item.value ? "model-option selected" : "model-option"}
                onClick={() => onUpdateModelPlan(item.value)}
                type="button"
              >
                <span>
                  <strong>{item.label}</strong>
                  <small>{item.description}</small>
                </span>
                <em>{item.cost}</em>
              </button>
            ))}
          </div>
          <div className={`balance-card ${account.status || ""}`}>
            {account.status === "refreshing" || account.status === "loading" ? <RefreshCw size={18} /> : <PackageCheck size={18} />}
            <div>
              <span>{account.accountName || "未连接"}</span>
              <strong>{account.balanceLabel || "待配置"}</strong>
              <small>{balanceHint(account)}</small>
            </div>
            <button type="button" onClick={onRefreshAccount} disabled={!bridgeAvailable}>
              刷新
            </button>
          </div>
        </section>
        <section>
          <SettingsSectionHeading icon={<Code2 size={17} />} title="模型配置" description="模型目录、推理强度与认证信息" />
          <div className="drawer-grid">
            <label>
              <span>文本 API 供应商</span>
              <select
                value={modelConfig.textProvider || "custom"}
                onChange={(event) => onUpdateModelConfig("textProvider", event.target.value)}
              >
                {textProviderChoices.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
              </select>
            </label>
            <label>
              <span>正式生成模型</span>
              <select
                value={modelConfig.modelName}
                onChange={(event) => onUpdateModelConfig("modelName", event.target.value)}
              >
                {catalogModels.map((model) => <option key={model} value={model}>{model}</option>)}
              </select>
            </label>
            <label>
              <span>蓝图处理方式</span>
              <select
                value={form.blueprintReviewBeforeGeneration ? "review" : "auto"}
                onChange={(event) => onUpdateField("blueprintReviewBeforeGeneration", event.target.value === "review")}
              >
                <option value="auto">自动确认并直接生成（推荐）</option>
                <option value="review">生成后先人工审阅</option>
              </select>
            </label>
            <label>
              <span>推理强度</span>
              <select
                value={modelConfig.reasoningEffort || "medium"}
                onChange={(event) => onUpdateModelConfig("reasoningEffort", event.target.value)}
              >
                <option value="minimal">极简（最快）</option>
                <option value="low">低</option>
                <option value="medium">中（推荐）</option>
                <option value="high">高</option>
                <option value="xhigh">极高（最慢）</option>
              </select>
            </label>
            <label>
              <span>生成蓝图模型</span>
              <select
                value={modelConfig.outlineModelName || ""}
                onChange={(event) => onUpdateModelConfig("outlineModelName", event.target.value)}
              >
                {catalogModels.map((model) => <option key={model} value={model}>{model}</option>)}
              </select>
            </label>
            <label>
              <span>界面生成模型</span>
              <select
                value={modelConfig.frontendModelName || modelConfig.modelName || ""}
                onChange={(event) => onUpdateModelConfig("frontendModelName", event.target.value)}
              >
                {catalogModels.map((model) => <option key={model} value={model}>{model}</option>)}
              </select>
            </label>
            <label>
              <span>界面并发数</span>
              <select
                value={String(modelConfig.frontendWorkers || "auto")}
                onChange={(event) => onUpdateModelConfig("frontendWorkers", event.target.value)}
              >
                <option value="auto">自动（推荐，初始 2，遇限流降为 1）</option>
                <option value="1">1（最稳）</option>
                <option value="2">2（固定并发）</option>
                <option value="3">3（需要较高限流额度）</option>
              </select>
            </label>
            <label>
              <span>蓝图超时秒数</span>
              <input
                type="number"
                min="10"
                max="120"
                value={modelConfig.outlineTimeoutSeconds || 60}
                onChange={(event) => onUpdateModelConfig("outlineTimeoutSeconds", event.target.value)}
              />
            </label>
            <label>
              <span>请求地址状态</span>
              <input
                value={selectedTextProvider.addressMode === "preset" ? "官方预设（地址已隐藏）" : modelConfig.apiBaseUrlMasked || (modelConfig.apiBaseUrlConfigured ? "已配置（地址已隐藏）" : "未配置")}
                readOnly
                aria-label="请求地址配置状态"
              />
            </label>
            {selectedTextProvider.addressMode === "custom" ? (
              <label>
                <span>更换请求地址（留空则保持不变）</span>
                <input
                  type="password"
                  value={modelConfig.apiBaseUrl}
                  onChange={(event) => onUpdateModelConfig("apiBaseUrl", event.target.value)}
                  placeholder={modelConfig.apiBaseUrlConfigured ? "已配置，输入新地址可替换" : "请输入 OpenAI 兼容请求地址"}
                  autoComplete="off"
                />
              </label>
            ) : (
              <label>
                <span>供应商接口</span>
                <input value={`${selectedTextProvider.label} 官方接口`} readOnly />
              </label>
            )}
            <label className="full">
              <span>自定义模型 ID（列表中没有时填写）</span>
              <input
                value={modelConfig.modelName || ""}
                onChange={(event) => onUpdateModelConfig("modelName", event.target.value)}
                placeholder="例如供应商自定义的模型 ID"
              />
            </label>
            <label className="full">
              <span>{modelConfig.apiKeyConfigured ? "更换 API Key（留空则保持不变）" : `填写 ${selectedTextProvider.label} API Key`}</span>
              <input
                type="password"
                value={modelConfig.apiKey}
                onChange={(event) => onUpdateModelConfig("apiKey", event.target.value)}
                placeholder={modelConfig.apiKeyConfigured ? "已配置，输入新密钥可替换" : "请输入 API Key"}
                autoComplete="new-password"
              />
            </label>
          </div>
          <div className={`model-catalog-status ${modelCatalog.status || "idle"}`}>
            <small>
              {modelCatalog.status === "loading"
                ? "正在读取模型列表…"
                : modelCatalog.message || "打开高级设置后会自动读取模型列表；也可以手动填写模型 ID。"}
            </small>
            <button type="button" onClick={() => onRefreshModels()} disabled={!bridgeAvailable || modelCatalog.status === "loading"}>
              {modelCatalog.status === "loading" ? <Loader2 size={14} /> : <RefreshCw size={14} />}
              <span>刷新模型</span>
            </button>
          </div>
        </section>
        <section>
          <SettingsSectionHeading icon={<ImageIcon size={17} />} title="图片模型 API" description="为视觉参考图单独指定图片模型服务" />
          <div className="drawer-grid">
            <label>
              <span>图片接口来源</span>
              <select
                value={modelConfig.imageUseTextApi ? "text" : "separate"}
                onChange={(event) => onUpdateModelConfig("imageUseTextApi", event.target.value === "text")}
              >
                <option value="text">复用文本 API</option>
                <option value="separate">使用独立图片 API</option>
              </select>
            </label>
            <label>
              <span>图片模型 ID</span>
              <input
                value={modelConfig.imageModelName || ""}
                onChange={(event) => onUpdateModelConfig("imageModelName", event.target.value)}
                placeholder="例如 gpt-image-2"
              />
            </label>
            {!modelConfig.imageUseTextApi ? (
              <>
                <label>
                  <span>图片请求地址状态</span>
                  <input
                    value={modelConfig.imageApiBaseUrlMasked || (modelConfig.imageApiBaseUrlConfigured ? "已单独配置（地址已隐藏）" : "未配置")}
                    readOnly
                    aria-label="图片请求地址配置状态"
                  />
                </label>
                <label>
                  <span>更换图片请求地址（留空则保持不变）</span>
                  <input
                    type="password"
                    value={modelConfig.imageApiBaseUrl}
                    onChange={(event) => onUpdateModelConfig("imageApiBaseUrl", event.target.value)}
                    placeholder={modelConfig.imageApiBaseUrlConfigured ? "已配置，输入新地址可替换" : "请输入图片生成 API 地址"}
                    autoComplete="off"
                  />
                </label>
                <label className="full">
                  <span>更换图片 API Key（留空则保持不变）</span>
                  <input
                    type="password"
                    value={modelConfig.imageApiKey}
                    onChange={(event) => onUpdateModelConfig("imageApiKey", event.target.value)}
                    placeholder={modelConfig.imageApiKeyConfigured ? "已配置，输入新密钥可替换" : "请输入图片 API Key"}
                    autoComplete="new-password"
                  />
                </label>
              </>
            ) : null}
          </div>
          <div className="model-catalog-status">
            <small>
              {modelConfig.imageUseTextApi
                ? `图片阶段将使用文本 API 的地址和 Key，并请求 ${modelConfig.imageModelName || "gpt-image-2"}。`
                : "独立图片地址和 API Key 保存后不会回显；模型目录没有列出图片模型时，可直接填写供应商提供的模型 ID。"}
            </small>
          </div>
        </section>
        </div>
        <div className="settings-save-dock">
          <button
            type="button"
            className={`config-save-button ${configStatus === "saving" ? "loading" : ""}`}
            onClick={onSaveModelConfig}
            disabled={
              configStatus === "saving" ||
              (modelConfig.mode === "gpt" &&
                ((!modelConfig.apiBaseUrl.trim() && !(bridgeAvailable && modelConfig.apiBaseUrlConfigured)) ||
                  (!modelConfig.apiKey.trim() && !(bridgeAvailable && modelConfig.apiKeyConfigured)) ||
                  (!modelConfig.imageUseTextApi &&
                    ((!modelConfig.imageApiBaseUrl.trim() && !(bridgeAvailable && modelConfig.imageApiBaseUrlConfigured)) ||
                      (!modelConfig.imageApiKey.trim() && !(bridgeAvailable && modelConfig.imageApiKeyConfigured))))))
            }
          >
            {configStatus === "saving" ? <Loader2 size={16} /> : <Save size={16} />}
            <span>{configStatus === "saving" ? "保存中" : bridgeAvailable ? "保存配置" : "应用配置"}</span>
          </button>
          <small className={configStatus && configStatus !== "saved" && configStatus !== "saving" ? "config-message error" : "config-message"}>
            {configStatus === "saved"
              ? "模型配置已保存"
              : configStatus === "saving"
                ? "正在写入本地配置"
                : modelConfig.mode === "template"
                  ? "Default Template 使用本地规则生成，不调用模型接口，不消耗 token。"
                  : "各文本供应商的 API Key 独立保存且不回显；图片模型仍可使用独立的 gpt-image-2 API。"}
          </small>
        </div>
      </aside>
    </div>
  );
}

function wait(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function createProcessEvent(stage, progressValue, message, startedAt = Date.now()) {
  const now = Date.now();
  return {
    stage,
    progress: progressValue,
    message: sanitizeErrorMessage(message),
    at: new Date(now).toLocaleTimeString(),
    elapsedMs: Math.max(0, now - startedAt)
  };
}

function SettingsSectionHeading({ icon, title, description }) {
  return (
    <div className="settings-section-heading">
      <span>{icon}</span>
      <div>
        <h3>{title}</h3>
        <p>{description}</p>
      </div>
    </div>
  );
}

function sanitizeErrorMessage(value) {
  return String(value || "")
    .replace(/(Bearer\s+)[A-Za-z0-9._~+/=-]+/gi, "$1[已隐藏]")
    .replace(/\b(api[_-]?key|token|secret|authorization)(\s*[:=]\s*['"]?)[^'"\s,;，；)）\]}]+/gi, "$1$2[已隐藏]")
    .replace(/(for url:\s*)https?:\/\/[^\s"'<>，。；;、)）\]}]+/gi, "$1[模型网关]")
    .replace(/https?:\/\/[^\s"'<>，。；;、)）\]}]+/gi, "[模型网关]")
    .replace(/\s+/g, " ")
    .trim();
}

function sanitizeResult(result) {
  if (!result || typeof result !== "object") return result;
  return {
    ...result,
    stdout: sanitizeErrorMessage(result.stdout || ""),
    stderr: sanitizeErrorMessage(result.stderr || ""),
    warnings: Array.isArray(result.warnings) ? result.warnings.map((item) => sanitizeErrorMessage(item)) : []
  };
}

function resultFromGenerationEvent(event) {
  if (!event || !["done", "error", "cancelled"].includes(String(event.stage || ""))) return null;
  if (!event.result || typeof event.result !== "object") return null;
  return sanitizeResult(event.result);
}

function seedFromOutputDir(outputDir) {
  const name = fileName(outputDir || "");
  const match = name.match(/(\d{8}-\d{6}-\d{4})$/);
  return match ? match[1] : "";
}

function clonePlainObject(value) {
  if (value == null) return value;
  try {
    return JSON.parse(JSON.stringify(value));
  } catch (_error) {
    return value;
  }
}

function loadPersistedQueueState() {
  if (cachedQueueState) return cachedQueueState;
  const empty = { tasks: [], paused: false };
  if (typeof window === "undefined" || !window.localStorage) {
    cachedQueueState = empty;
    return cachedQueueState;
  }
  try {
    const raw = window.localStorage.getItem(QUEUE_STORAGE_KEY);
    if (!raw) {
      cachedQueueState = empty;
      return cachedQueueState;
    }
    const parsed = JSON.parse(raw);
    const tasks = Array.isArray(parsed?.tasks) ? parsed.tasks.map(normalizePersistedQueueTask).filter(Boolean).slice(-30) : [];
    const recoveredRunning = tasks.some((task) => task._restoredFromRunning);
    cachedQueueState = {
      tasks: tasks.map((task) => {
        const next = { ...task };
        delete next._restoredFromRunning;
        return next;
      }),
      paused: Boolean(parsed?.paused || recoveredRunning || tasks.some((task) => task.status === "queued"))
    };
    return cachedQueueState;
  } catch (_error) {
    cachedQueueState = empty;
    return cachedQueueState;
  }
}

function normalizePersistedQueueTask(task) {
  if (!task || typeof task !== "object") return null;
  const status = ["queued", "success", "error", "cancelled"].includes(task.status) ? task.status : "queued";
  const restoredFromRunning = task.status === "running" || task.status === "planning";
  const events = Array.isArray(task.events) ? task.events.slice(-80) : [];
  const restoreEvent = restoredFromRunning
    ? createProcessEvent("start", 0, "应用重启后已恢复为等待中，请确认后继续队列", Date.now())
    : null;
  return {
    id: String(task.id || createId("queue_restored")),
    title: String(task.title || task.formSnapshot?.name || task.businessPlan?.softwareName || "恢复任务"),
    promptText: String(task.promptText || task.title || ""),
    formSnapshot: clonePlainObject(task.formSnapshot || {}),
    businessPlan: task.businessPlan?.modules?.length ? clonePlainObject(task.businessPlan) : null,
    overrides: clonePlainObject(task.overrides || {}),
    submitMessage: String(task.submitMessage || "恢复队列任务，继续生成材料包"),
    autoPlan: Boolean(task.autoPlan || !task.businessPlan?.modules?.length),
    status: restoredFromRunning ? "queued" : status,
    phase: restoredFromRunning ? "queued" : String(task.phase || "queued"),
    progress: restoredFromRunning ? 0 : Number(task.progress || 0),
    events: restoreEvent ? [...events, restoreEvent].slice(-80) : events,
    result: task.result ? sanitizeResult(task.result) : null,
    createdAt: Number(task.createdAt || Date.now()),
    startedAt: 0,
    finishedAt: status === "queued" ? 0 : Number(task.finishedAt || 0),
    recovery: clonePlainObject(task.recovery || {}),
    _restoredFromRunning: restoredFromRunning
  };
}

function persistQueueState(tasks, paused) {
  if (typeof window === "undefined" || !window.localStorage) return;
  try {
    const compactTasks = (tasks || []).slice(-30).map(compactQueueTaskForStorage);
    window.localStorage.setItem(
      QUEUE_STORAGE_KEY,
      JSON.stringify({
        version: 1,
        savedAt: new Date().toISOString(),
        paused: Boolean(paused),
        tasks: compactTasks
      })
    );
  } catch (_error) {
    // Queue persistence is helpful, but must not block generation.
  }
}

function compactQueueTaskForStorage(task) {
  return {
    id: task.id,
    title: task.title,
    promptText: task.promptText,
    formSnapshot: compactFormSnapshot(task.formSnapshot || {}),
    businessPlan: task.businessPlan ? clonePlainObject(task.businessPlan) : null,
    overrides: clonePlainObject(task.overrides || {}),
    submitMessage: task.submitMessage,
    autoPlan: Boolean(task.autoPlan),
    status: task.status,
    phase: task.phase,
    progress: Number(task.progress || 0),
    events: Array.isArray(task.events) ? task.events.slice(-80).map(compactProcessEvent) : [],
    result: task.result ? compactResultForStorage(task.result) : null,
    createdAt: Number(task.createdAt || Date.now()),
    startedAt: Number(task.startedAt || 0),
    finishedAt: Number(task.finishedAt || 0),
    recovery: clonePlainObject(task.recovery || {})
  };
}

function compactFormSnapshot(formSnapshot) {
  const templateMode = formSnapshot.modelPlan === "template";
  return {
    name: formSnapshot.name || "",
    version: formSnapshot.version || "V1.0",
    language: formSnapshot.language || "自动选择",
    productType: formSnapshot.productType || "APP",
    softwareCategory: formSnapshot.softwareCategory || "应用软件",
    featureHint: formSnapshot.featureHint || "",
    modelPlan: templateMode ? "template" : "gpt",
    modelProvider: templateMode ? "local-template" : "custom",
    modelName: templateMode ? "template-v1" : formSnapshot.modelName || "gpt-5.5",
    randomness: formSnapshot.randomness || "standard"
  };
}

function compactProcessEvent(event) {
  return {
    stage: event.stage || "start",
    progress: Number(event.progress || 0),
    message: sanitizeErrorMessage(event.message || ""),
    at: event.at || "",
    elapsedMs: Number(event.elapsedMs || 0)
  };
}

function compactResultForStorage(result) {
  return {
    ok: Boolean(result.ok),
    cancelled: Boolean(result.cancelled),
    zipPath: result.zipPath || "",
    outputDir: result.outputDir || "",
    checks: result.checks || {},
    warnings: Array.isArray(result.warnings) ? result.warnings.slice(0, 20).map((item) => sanitizeErrorMessage(item)) : [],
    stdout: sanitizeErrorMessage(result.stdout || "").slice(0, 1200),
    stderr: sanitizeErrorMessage(result.stderr || "").slice(0, 1200),
    seed: result.seed || "",
    randomness: result.randomness || ""
  };
}

function buildCancelledResult(message = "已中止生成任务") {
  return {
    ok: false,
    cancelled: true,
    zipPath: "",
    outputDir: "",
    checks: {},
    warnings: [],
    stdout: "",
    stderr: message
  };
}

function summarizeQueue(tasks = []) {
  return tasks.reduce(
    (summary, task) => {
      summary.total += 1;
      if (task.status === "queued") summary.queued += 1;
      else if (task.status === "running" || task.status === "planning") summary.running += 1;
      else if (task.status === "success") summary.success += 1;
      else if (task.status === "error") summary.error += 1;
      else if (task.status === "cancelled") summary.cancelled += 1;
      return summary;
    },
    { total: 0, queued: 0, running: 0, success: 0, error: 0, cancelled: 0 }
  );
}

function queueTaskStatusLabel(task) {
  if (task.status === "queued") return "等待中";
  if (task.status === "planning") return "生成蓝图";
  if (task.status === "running") return "生成材料";
  if (task.status === "success") return "已完成";
  if (task.status === "error") return "失败";
  if (task.status === "cancelled") return "已中止";
  return "待处理";
}

function queueTaskMeta(task) {
  if (task.recovery?.outputDir && task.status === "queued") return "从上次失败输出恢复，等待继续生成";
  if (task.status === "queued") return task.autoPlan ? "等待自动生成蓝图后进入材料生成" : "等待使用已确认蓝图生成";
  if (task.status === "success") return task.result?.zipPath ? "材料包已生成，可打开输出目录" : "任务已完成";
  if (task.status === "error") return task.result?.stderr || "任务失败，队列已暂停";
  if (task.status === "cancelled") return "任务已中止，队列已暂停";
  if (task.phase === "outline") return "正在生成产品蓝图";
  if (task.phase === "materials") return "正在生成源码、截图、手册和材料包";
  return "正在处理";
}

function extractSoftwareName(value) {
  return (
    String(value || "")
      .split(/\r?\n/)
      .map((line) => line.trim())
      .find(Boolean) || ""
  );
}

function extractInputSupplement(value) {
  const lines = String(value || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  return lines.slice(1).join("；");
}

async function inferFeatureHintThroughDevApi(payload) {
  const response = await fetch("/api/infer-feature-hint", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ...payload,
      modelName: payload.modelName || "gpt-5.5",
      timeoutSeconds: payload.timeoutSeconds || 60,
      apiBaseUrl: payload.apiBaseUrl || "",
      apiKey: payload.apiKey || ""
    })
  });
  if (!response.ok) {
    return {
      ok: false,
      message: `GPT 蓝图生成失败：HTTP ${response.status}`,
      featureHint: "",
      meta: {}
    };
  }
  return response.json();
}

function withTimeout(promise, timeoutMs, message) {
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = window.setTimeout(() => reject(new Error(message)), timeoutMs);
  });
  return Promise.race([promise, timeout]).finally(() => window.clearTimeout(timer));
}

function normalizeOutlineTimeout(value) {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed)) return 60;
  return Math.min(120, Math.max(10, parsed));
}

function formatElapsed(ms) {
  const totalSeconds = Math.max(0, Math.floor(Number(ms || 0) / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes <= 0) return `${seconds}秒`;
  return `${minutes}分${String(seconds).padStart(2, "0")}秒`;
}

function createEmptyPlan() {
  return {
    softwareName: "",
    domain: "",
    profile: "",
    targetUsers: [],
    avoidTerms: [],
    modules: []
  };
}

function buildBusinessPlan(name, productType, featureHint, meta = {}) {
  const domain = meta.feature_hint_domain || guessDomain(name, productType, featureHint);
  const targetUsers = normalizeList(meta.feature_hint_target_users).slice(0, 4);
  const structuredModules = normalizeBlueprintModules(meta.feature_hint_blueprint_modules || meta.blueprint_modules);
  const keywords = normalizeList(meta.feature_hint_keywords || meta.keywords || splitTerms(featureHint)).slice(0, 10);
  const modules = structuredModules.length
    ? structuredModules.map((module, index) => ({
        id: createId(`module_${index}`),
        category: module.category || "业务模块",
        title: module.title,
        description: module.description,
        dataObjects: module.dataObjects,
        userFlow: module.userFlow,
        screens: module.screens,
        operations: module.operations,
        operationSpecs: module.operationSpecs,
        dataFields: module.dataFields,
        rules: module.rules,
        entities: module.entities,
        children: buildChildren(module.title)
      }))
    : (keywords.length ? keywords : splitTerms(featureHint)).slice(0, 10).map((keyword, index) => ({
        id: createId(`module_${index}`),
        category: categorizeModule(keyword, domain),
        title: keyword,
        description: buildBusinessDescription(name, domain, keyword, targetUsers),
        children: buildChildren(keyword)
      }));
  return {
    softwareName: name,
    productType,
    domain,
    profile: meta.feature_hint_profile || "",
    targetUsers,
    avoidTerms: normalizeList(meta.feature_hint_avoid_terms).slice(0, 8),
    modules
  };
}

function normalizeBlueprintModules(value) {
  if (!Array.isArray(value)) return [];
  const seen = new Set();
  return value
    .map((item) => normalizeBlueprintModule(item))
    .filter((item) => {
      if (!item || seen.has(item.title)) return false;
      seen.add(item.title);
      return true;
    })
    .slice(0, 12);
}

function normalizeBlueprintModule(item) {
  if (!item || typeof item !== "object") return null;
  const title = String(item.title || item.name || "").trim();
  const description = String(item.description || item.focus || "").trim();
  if (title.length < 2 || description.length < 12) return null;
  const category = String(item.category || item.group || "业务模块").trim();
  return {
    key: String(item.key || item.module_key || item.moduleKey || "").trim(),
    category: category && category !== "核心模块" ? category : "业务模块",
    title,
    description,
    dataObjects: normalizeDetailList(item.data_objects || item.dataObjects || item.objects, 6),
    userFlow: normalizeDetailList(item.user_flow || item.userFlow || item.flow || item.steps, 6),
    screens: normalizeDetailList(item.screens || item.pages, 5),
    operations: normalizeDetailList(item.operations || item.actions, 7),
    operationSpecs: normalizeOperationSpecs(item.operation_specs || item.operationSpecs),
    dataFields: normalizeDetailList(item.data_fields || item.dataFields || item.fields, 10),
    rules: normalizeDetailList(item.rules || item.quality_rules || item.qualityRules, 5),
    entities: normalizeDetailList(item.entities, 4)
  };
}

function normalizeOperationSpecs(value) {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => {
      if (!item || typeof item !== "object") return null;
      const label = String(item.label || item.action || item.name || "").trim();
      if (!label) return null;
      return {
        actionKey: String(item.action_key || item.actionKey || "").trim(),
        label,
        category: String(item.category || "").trim(),
        role: String(item.role || "").trim(),
        trigger: String(item.trigger || "").trim(),
        inputFields: normalizeDetailList(item.input_fields || item.inputFields, 8),
        preState: String(item.pre_state || item.preState || "").trim(),
        postState: String(item.post_state || item.postState || "").trim(),
        resultEvidence: String(item.result_evidence || item.resultEvidence || "").trim(),
        requiresConfirmation: Boolean(
          item.requires_confirmation !== undefined ? item.requires_confirmation : item.requiresConfirmation
        )
      };
    })
    .filter(Boolean)
    .slice(0, 7);
}

function normalizeDetailList(value, maxCount) {
  if (!Array.isArray(value)) return [];
  return [...new Set(value.map((item) => String(item).trim()).filter(Boolean))].slice(0, maxCount);
}

function moduleHasDetails(module) {
  return Boolean(module.dataObjects?.length || module.userFlow?.length || module.screens?.length);
}

function buildChildren(_keyword) {
  return [];
}

function categorizeModule(keyword, domain) {
  const text = `${keyword} ${domain}`;
  if (/玩家|账号|登录/.test(keyword)) return "用户与权限";
  if (/房间|匹配|邀请/.test(keyword)) return "房间匹配";
  if (/题目|题库|词库|抽取/.test(keyword)) return "题库回合";
  if (/猜词|答案|提交|判定/.test(keyword)) return "猜词判定";
  if (/排行|战绩|成就排行/.test(keyword)) return "数据排行";
  if (/历史|记录|统计|通关记录/.test(keyword)) return "记录统计";
  if (/连线|路径|轨迹|规划/.test(keyword)) return "核心玩法";
  if (/画板|绘制|画笔|颜色/.test(keyword)) return "画板互动";
  if (/关卡|挑战|解谜|通关/.test(keyword)) return "关卡体系";
  if (/难度|进阶|等级/.test(keyword)) return "难度成长";
  if (/提示|道具|撤销|重置/.test(keyword)) return "辅助工具";
  if (/步数|限制|剩余/.test(keyword)) return "规则约束";
  if (/星级|评价|成就/.test(keyword)) return "成就评价";
  if (/计时|回合/.test(keyword)) return "回合控制";
  if (/积分|结算|得分/.test(keyword)) return "积分结算";
  if (/登录|账号|用户|会员|身份|权限/.test(text)) return "用户与权限";
  if (/首页|导航|入口|搜索|浏览|书城|菜单|分类/.test(text)) return "内容浏览";
  if (/房间|匹配|组队|邀请|门店|地址/.test(text)) return "场景配置";
  if (/题目|题库|章节|目录|菜品|歌曲|专辑/.test(text)) return "内容管理";
  if (/画板|绘制|播放|阅读|听书|选餐|购物车|规格|口味/.test(text)) return "核心交互";
  if (/猜词|提交|订单|支付|优惠|取餐|配送|评论/.test(text)) return "业务处理";
  if (/计时|积分|结算|排行榜|状态|历史|记录|进度|统计/.test(text)) return "记录统计";
  if (/设置|偏好|通知|缓存|下载/.test(text)) return "系统设置";
  return "核心模块";
}

function buildBusinessDescription(name, domain, keyword, targetUsers = []) {
  const userText = targetUsers.length ? targetUsers.slice(0, 2).join("、") : "目标用户";
  const text = `${name} ${domain} ${keyword}`;
  if (/一笔连线|一笔画|连线|路径|迷宫|益智|解谜|关卡/.test(text)) {
    if (/历史|记录|统计|通关记录/.test(keyword)) return "统计玩家通关历史、最佳步数、最快用时和关卡完成率，用于后续复盘和进度展示。";
    if (/排行|战绩|成就排行/.test(keyword)) return "展示累计星级、通关数量、最佳成绩和排行榜名次，用于激励玩家持续挑战高难度关卡。";
    if (/关卡|挑战|解谜|通关/.test(keyword)) return "组织关卡编号、目标图形、通关条件和解锁状态，支撑玩家从入门关卡逐步进入更复杂的解谜挑战。";
    if (/连线|一笔|路径|轨迹/.test(keyword)) return "记录玩家触点顺序、连线路径、已连接节点和断线状态，用于判断是否按规则完成一笔连线。";
    if (/图形|节点|路线|规划/.test(keyword)) return "维护每关的节点位置、可连接边、禁用路径和目标图形结构，为画布渲染和规则判定提供数据基础。";
    if (/难度|进阶|等级/.test(keyword)) return "根据节点数量、分支复杂度、干扰路径和步数要求划分难度，控制关卡解锁节奏和训练梯度。";
    if (/提示|道具|撤销|重置/.test(keyword)) return "提供提示下一步、撤销最近连线、重置关卡等辅助操作，记录道具消耗和使用次数。";
    if (/步数|限制|剩余/.test(keyword)) return "计算已用步数、剩余步数和超限状态，确保玩家在约束条件内完成路径连接。";
    if (/星级|评价|结算|成就/.test(keyword)) return "根据完成时间、步数消耗、提示使用情况生成星级评价，并写入关卡结算和成就进度。";
  }
  if (/你画我猜|画画|绘画|猜词|画板|房间匹配|回合/.test(text)) {
    if (/账号|登录|玩家/.test(keyword)) return "管理玩家昵称、头像、登录状态和基础资料，为创建房间、加入对局和积分统计提供身份依据。";
    if (/房间|匹配|邀请/.test(keyword)) return "支持创建房间、输入房间号加入、随机匹配和好友邀请，记录房主、人数上限、对局模式和准备状态。";
    if (/题目|题库|词库|抽取/.test(keyword)) return "维护绘画题目、难度、分类和随机抽题规则，保证每回合的作画目标可控且不重复。";
    if (/画板|绘制|画笔|颜色/.test(keyword)) return "提供画笔、颜色、橡皮、撤销和清空画布等绘制能力，实时保存当前回合的绘画轨迹和画布状态。";
    if (/猜词|答案|提交|判定/.test(keyword)) return "接收玩家输入的猜测答案，校验正确性、相似词和提交时间，并把判定结果同步到当前回合。";
    if (/计时|回合/.test(keyword)) return "控制每轮作画与猜词倒计时，记录回合开始、结束、跳过和超时状态，推动对局自动流转。";
    if (/积分|结算|得分/.test(keyword)) return "根据答对时间、作画者奖励和参与情况计算积分，形成单局结算结果。";
    if (/排行|战绩|统计/.test(keyword)) return "展示玩家历史对局、胜率、累计得分和排行榜名次，用于持续记录游戏表现。";
  }
  if (/点餐|订餐|外卖|餐饮|菜单|菜品|购物车|口味|支付|取餐|配送|门店/.test(text)) {
    if (/菜单|分类/.test(keyword)) return `按套餐、热销、主食、饮品等维度组织菜单，记录分类排序、上下架状态和适用门店，方便用户快速定位可点菜品。`;
    if (/菜品|浏览/.test(keyword)) return `展示菜品名称、图片、价格、销量、库存和售卖状态，帮助用户在点餐前完成筛选、比较和选择。`;
    if (/购物车|选餐/.test(keyword)) return `汇总用户已选菜品、数量、单价、小计和备注信息，支持继续加菜、减少数量和进入订单确认。`;
    if (/规格|口味/.test(keyword)) return `记录份量、辣度、做法、加料和忌口备注等个性化选择，保证厨房或门店能按用户要求处理菜品。`;
    if (/提交|订单/.test(keyword)) return `生成订单编号并固化菜品明细、取餐方式、联系人、金额和备注，作为商家接单与用户追踪的核心凭证。`;
    if (/支付/.test(keyword)) return `处理应付金额、支付渠道、支付结果和异常重试状态，确保点餐交易过程完整可追溯。`;
    if (/优惠|券/.test(keyword)) return `校验优惠券适用门店、满减条件和抵扣金额，并将优惠结果写入订单费用明细。`;
    if (/取餐|堂食/.test(keyword)) return `管理堂食桌号、取餐码、制作进度和取餐提醒，帮助用户及时完成到店取餐或堂食核对。`;
    if (/配送|外卖/.test(keyword)) return `维护配送地址、联系人、预计送达时间和配送状态，支撑外卖履约与异常联系。`;
    if (/门店/.test(keyword)) return `展示门店地址、营业时间、联系电话和可服务范围，为点餐前的门店选择提供依据。`;
  }
  if (/听歌|音乐|歌曲|歌单|歌词|播放|音质/.test(text)) {
    if (/播放/.test(keyword)) return `支撑播放、暂停、切歌、进度拖动和循环模式，记录当前歌曲、播放位置和播放队列状态。`;
    if (/歌词/.test(keyword)) return `按歌曲时间轴同步展示歌词内容，支持当前歌词定位和播放进度联动。`;
    if (/歌单|收藏/.test(keyword)) return `管理用户自建歌单、收藏歌曲和批量移除操作，用于沉淀个人音乐内容。`;
    if (/最近/.test(keyword)) return `记录最近播放歌曲、播放时间和来源入口，方便用户恢复未听完内容。`;
    if (/搜索|歌手|专辑/.test(keyword)) return `提供歌曲、歌手和专辑检索入口，帮助用户按关键词快速定位音乐内容。`;
  }
  if (/阅读|听书|小说|书城|书架|章节/.test(text)) {
    if (/书城/.test(keyword)) return `展示书籍分类、榜单、封面、作者和简介信息，帮助用户发现可阅读或可收听内容。`;
    if (/书架|收藏|订阅/.test(keyword)) return `管理已加入书架的书籍、订阅状态和更新提醒，帮助用户维护持续阅读列表。`;
    if (/章节|目录/.test(keyword)) return `维护章节标题、排序、更新状态和阅读入口，为正文阅读和听书播放提供导航。`;
    if (/阅读|进度/.test(keyword)) return `记录阅读页码、章节位置、字体设置和阅读时长，支撑用户跨次继续阅读。`;
    if (/听书|播放/.test(keyword)) return `记录音频章节、播放进度、倍速和暂停位置，支撑用户连续收听。`;
  }
  return buildGenericBlueprintDescription(name, domain, keyword, userText);
}

function buildGenericBlueprintDescription(name, domain, keyword, userText) {
  if (/入口|首页|导航/.test(keyword)) return `作为${name}的主入口，承载常用功能导航、任务状态提示和最近操作入口，帮助${userText}快速进入核心流程。`;
  if (/工作台|看板|中心/.test(keyword)) return `汇总${domain || "软件"}的待办事项、关键指标和快捷操作，作为日常处理业务的集中工作区。`;
  if (/表单|提交|录入|处理/.test(keyword)) return `处理${keyword}相关的数据录入、字段校验、状态流转和结果提交，保证业务过程可追踪。`;
  if (/查询|搜索|筛选|列表/.test(keyword)) return `提供关键词检索、条件筛选、列表查看和详情跳转，帮助用户快速定位历史记录或业务对象。`;
  if (/统计|报表|分析/.test(keyword)) return `统计${keyword}相关数量、趋势、分布和异常情况，为后续材料生成图表、字段和报表说明提供依据。`;
  if (/消息|通知|提醒/.test(keyword)) return `管理业务提醒、系统通知和处理反馈，记录消息状态、触达时间和用户确认结果。`;
  if (/设置|配置|偏好/.test(keyword)) return `维护系统参数、用户偏好和基础配置，支撑不同使用场景下的软件个性化运行。`;
  return `围绕${name}的“${keyword}”能力设计独立页面、数据字段和操作流程，记录输入信息、处理状态和结果数据，支撑${domain || "软件"}材料中的功能描述、源码模块和界面截图。`;
}

function regenerateModuleBlueprint(module, plan, index) {
  const category = categorizeModule(module.title, plan.domain);
  return {
    ...module,
    category,
    description: buildRegeneratedDescription(plan.softwareName, plan.domain, module.title, plan.targetUsers || [], index)
  };
}

function buildRegeneratedDescription(name, domain, keyword, targetUsers, index) {
  const base = buildBusinessDescription(name, domain, keyword, targetUsers);
  const extras = [
    "重新生成后会优先补充页面入口、关键字段和状态结果，便于后续源码与说明书共用。",
    "该模块会作为独立业务单元参与材料生成，重点体现输入、处理、输出之间的闭环。",
    "后续生成会围绕该模块补齐界面操作、数据对象、异常提示和记录留存。"
  ];
  return `${base}${extras[index % extras.length]}`;
}

function serializePlan(plan) {
  const moduleTerms = plan.modules.flatMap((module) => {
    const details = [
      module.dataObjects?.length ? `数据对象：${module.dataObjects.join("、")}` : "",
      module.userFlow?.length ? `用户流程：${module.userFlow.join("、")}` : "",
      module.screens?.length ? `页面入口：${module.screens.join("、")}` : ""
    ].filter(Boolean);
    const description = module.description ? `${module.category || "模块"}-${module.title}：${module.description}` : module.title;
    return [
      details.length ? `${description}（${details.join("；")}）` : description,
      ...(module.children || []).map((child) => child.title)
    ];
  });
  return normalizeList(moduleTerms).slice(0, 24).join("；");
}

function normalizeList(value) {
  if (!value) return [];
  const items = Array.isArray(value) ? value : splitTerms(String(value));
  return [...new Set(items.map((item) => String(item).trim()).filter(Boolean))];
}

function splitTerms(value) {
  return String(value || "")
    .split(/[，,、\s\n]+/)
    .map((item) => item.trim())
    .filter((item) => item.length >= 2);
}

function createId(prefix) {
  return `${prefix}_${Math.random().toString(36).slice(2, 9)}`;
}

function guessDomain(name, productType, hint) {
  const text = `${name} ${productType} ${hint}`;
  if (/点餐|订餐|外卖|餐饮|菜单|菜品/.test(text)) return "餐饮点餐服务";
  if (/听歌|音乐|歌曲|歌单|歌词/.test(text)) return "音乐播放服务";
  if (/阅读|听书|小说|书城/.test(text)) return "阅读听书服务";
  if (/一笔连线|一笔画|连线|路径|迷宫|益智|解谜|关卡/.test(text)) return "休闲益智解谜游戏";
  if (/你画我猜|画画|绘画|猜词|涂鸦|画板/.test(text)) return "绘画猜词互动游戏";
  return productType || "软件服务";
}

function inferProductType(name, hint = "") {
  const text = `${name} ${hint}`;
  if (/医疗|医院|诊疗|处方|病历|药品|随访|护理|患者|检验|手术|手术室|术前|术后|麻醉|科室|医生|排班|排程|气道|插管|急救|临床|医护/.test(text)) return "医疗软件";
  if (/VR|虚拟现实|三维|沉浸|仿真/.test(text)) return "VR软件";
  if (/教育|学习|课程|作业|考试|题库|学情|课堂|教务|培训/.test(text)) return "教育软件";
  if (/游戏|手游|小游戏|消除|点消|三消|连消|糖果|玩家|道具背包|关卡地图|对局|一笔画|猜词|涂鸦/.test(text)) return "游戏软件";
  if (/金融|贷款|信贷|支付|清算|账单|授信|风控|银行|保险|理财/.test(text)) return "金融软件";
  if (/地图|地理|GIS|定位|测绘|轨迹|空间|坐标/.test(text)) return "地理信息软件";
  if (/云计算|云资源|云主机|云平台|容器|集群|Kubernetes|K8S|k8s|资源编排|弹性伸缩|租户|SaaS/.test(text)) return "云计算软件";
  if (/安全|漏洞|审计|加密|防护|入侵|认证|权限|风控/.test(text)) return "信息安全软件";
  if (/大数据|数据湖|数仓|实时计算|指标|画像|趋势|分析/.test(text)) return "大数据软件";
  if (/人工智能|AI|模型|识别|预测|推荐|训练|智能/.test(text)) return "人工智能软件";
  if (/5G|基站|切片|边缘网络|通信/.test(text)) return "5G软件";
  if (/小程序|微信|公众号|轻应用/.test(text)) return "小程序";
  if (/物联网|IoT|传感器|设备接入|边缘|网关|采集/.test(text)) return "物联网软件";
  if (/城市|园区|社区|政务|网格|指挥|水文|河流|电力|线路|巡检|运维|调度/.test(text)) return "智慧城市软件";
  return "APP";
}

function inferSoftwareCategory(name, hint = "") {
  const text = `${name} ${hint}`;
  if (/嵌入式|固件|边缘设备|单片机|控制器|工控|采集终端/.test(text)) return "嵌入式软件";
  if (/中间件|网关|消息队列|接口服务|服务总线|调度引擎/.test(text)) return "中间件";
  if (/操作系统|内核|驱动|文件系统|桌面环境/.test(text)) return "操作系统";
  return "应用软件";
}

function statusLabel(status, context = {}) {
  if (status === "planning") return "理解中";
  if (status === "editing") return "可编辑";
  if (status === "running") return "生成中";
  if (status === "success") return "已完成";
  if (status === "error") return "失败";
  if (status === "cancelled") return "已中止";
  if (context.hasOutlineError) return "待重试";
  if (context.canPlan) return "待生成";
  return "待输入";
}

function outlineStatusLabel(outlineState, planReady) {
  if (!planReady || outlineState === "empty") return "未生成蓝图";
  if (outlineState === "draft") return "蓝图待确认";
  if (outlineState === "confirmed") return "蓝图已确认";
  return "未生成蓝图";
}

function workflowStageIndex(status, outlineState, planReady) {
  if (status === "success") return 3;
  if (["running", "error", "cancelled"].includes(status)) return 2;
  if (status === "planning" || planReady || outlineState === "draft" || outlineState === "confirmed" || status === "editing") return 1;
  return 0;
}

function primaryButtonLabel(
  status,
  outlineState,
  planReady,
  gptConfigured,
  canRetryFromConfirmedOutline = false,
  blueprintReviewBeforeGeneration = false
) {
  if (status === "running") return "生成中";
  if (status === "planning") return "自动规划中";
  if (canRetryFromConfirmedOutline) return "保留蓝图重试";
  if (!gptConfigured) return "配置 AI";
  if (!planReady || outlineState === "empty") return blueprintReviewBeforeGeneration ? "生成蓝图" : "开始生成";
  if (outlineState === "draft") return "确认并开始生成";
  return "加入生成队列";
}

function currentEvent(events) {
  return events.length ? events[events.length - 1] : null;
}

function processTitle(status) {
  if (status === "success") return "材料包生成完成";
  if (status === "error") return "生成失败，等待处理";
  if (status === "cancelled") return "生成已中止";
  return "AI 正在生成材料包";
}

function processStatusIcon(status, stage = "") {
  if (status === "success") return <CheckCircle2 size={15} />;
  if (status === "cancelled") return <Square size={15} />;
  if (status === "error") return <AlertTriangle size={15} />;
  if (["visual_reference", "screenshots"].includes(stage)) return <ImageIcon size={17} />;
  if (stage === "source") return <Code2 size={17} />;
  if (["manual_content", "manual", "source_doc", "pdf", "info"].includes(stage)) return <FileText size={17} />;
  if (stage === "package") return <PackageCheck size={17} />;
  return <Sparkles size={17} />;
}

function compactStageStatus(events, status) {
  const seen = new Set(events.map((event) => event.stage).filter(Boolean));
  const latestStage = events.length ? events[events.length - 1].stage : "";
  return generationStages.map(([key, label]) => {
    let state = "pending";
    if (status === "success" && seen.has(key)) state = "done";
    else if ((status === "error" || status === "cancelled") && latestStage === key) state = "error";
    else if (latestStage === key && status === "running") state = "active";
    else if (seen.has(key)) state = "done";
    return { key, label, state };
  });
}

function fallbackResultEvents(result) {
  if (!result) return [];
  const text = [result.stdout, result.stderr].filter(Boolean).join("\n");
  if (!text) return [];
  return text
    .split(/\r?\n/)
    .map((message, index) => ({
      stage: result.ok ? "package" : "start",
      progress: result.ok ? 100 : 0,
      message,
      at: "",
      elapsedMs: index
    }))
    .filter((event) => event.message.trim());
}

function buildProcessConversation(events, status) {
  const source = events.length
    ? events
    : [
        {
          stage: "start",
          progress: status === "success" ? 100 : 0,
          message: status === "success" ? "材料包生成完成" : "等待生成过程开始",
          at: "",
          elapsedMs: 0
        }
      ];
  return source.slice(-36).map((event) => {
    const actor = processActor(event);
    const detailParts = [];
    const detail = processEventDetail(event);
    if (detail) detailParts.push(detail);
    return {
      event,
      actor: actor.name,
      avatar: actor.avatar,
      tone: actor.tone,
      message: conversationMessage(event),
      detail: detailParts.join(" · ")
    };
  });
}

function processRowMeta(item) {
  const time = item?.event?.at || "";
  const detail = String(item?.detail || "").trim();
  if (time && detail) return `${time} · ${detail}`;
  if (time) return time;
  return detail;
}

function processActor(event) {
  const stage = String(event.stage || "");
  const message = String(event.message || "");
  if (stage === "visual_reference") {
    if (message.includes("暂不写入界面代码") || message.includes("页面清单")) return { name: "页面规划", avatar: "单", tone: "plan" };
    if (message.includes("视觉提示词")) return { name: "视觉设计", avatar: "视", tone: "design" };
    if (message.includes("gpt-image-2") || message.includes("视觉参考")) return { name: "图片模型", avatar: "图", tone: "image" };
    return { name: "视觉参考", avatar: "图", tone: "image" };
  }
  if (stage === "screenshots") {
    if (message.includes("复用") || message.includes("参考图")) return { name: "前端生成", avatar: "码", tone: "code" };
    if (message.includes("界面代码")) return { name: "前端生成", avatar: "码", tone: "code" };
    if (message.includes("运行截图") || message.includes("渲染界面截图") || message.includes("生成项目服务")) {
      return { name: "截图运行", avatar: "截", tone: "run" };
    }
    return { name: "界面链路", avatar: "界", tone: "design" };
  }
  if (stage === "prepare") return { name: "业务分析", avatar: "析", tone: "plan" };
  if (stage === "blueprint") return { name: "产品规划", avatar: "蓝", tone: "plan" };
  if (stage === "manual_content" || stage === "manual") return { name: "文档撰写", avatar: "文", tone: "doc" };
  if (stage === "source") return { name: "业务工程", avatar: "源", tone: "code" };
  if (stage === "source_doc") return { name: "源码材料", avatar: "材", tone: "code" };
  if (stage === "pdf" || stage === "info" || stage === "package") return { name: "校验打包", avatar: "验", tone: "check" };
  return { name: "任务调度", avatar: "启", tone: "plan" };
}

function conversationMessage(event) {
  const message = String(event.message || "");
  if (message.includes("先生成全局风格参考图")) {
    return "先生成一张 gpt-image-2 全局风格参考图；后面的业务工程源码和界面代码都会沿用这张图的视觉方向。";
  }
  if (message.includes("先生成参考图，暂不写入源码工程")) {
    return "正在整理视觉参考需要的页面角色；此时还没有生成业务工程源码。";
  }
  if (
    message.includes("生成业务后端与运行接口")
    || message.includes("生成业务源码与运行接口")
    || message.includes("生成真实源码工程")
  ) {
    return "正在根据已生成的全局风格参考图准备业务工程源码、本地接口服务和视觉契约文件。";
  }
  if (message.includes("根据参考图生成界面代码并运行源码截图")) {
    return "参考图和业务工程已准备好，正在按图生成可运行界面代码，并从源码工程服务重新截图。";
  }
  if (message.includes("复用全局风格参考图")) {
    return "正在复用前面生成的风格参考图，下一步按图写界面 HTML/CSS。";
  }
  if (message.includes("生成风格参考图、界面代码与运行截图") || message.includes("生成视觉参考稿与运行截图")) {
    return "进入截图链路：按全局风格参考图写全部界面代码，最后运行页面重新截图。";
  }
  if (message.includes("暂不写入界面代码")) {
    return "正在整理截图页面清单；此时只确定页面角色和文件名，暂不写入界面 HTML/CSS。";
  }
  if (message.includes("准备截图页面清单")) {
    return "正在整理本次需要截图的页面清单，后面会生成一张全局风格参考图并逐页运行截图。";
  }
  if (message.includes("全局视觉风格提示词") || message.includes("生成视觉提示词")) {
    return "正在把产品壳、配色、导航和控件密度整理成全局风格提示词。";
  }
  if (message.includes("gpt-image-2") && (message.includes("视觉参考稿") || message.includes("视觉风格参考图"))) {
    return "正在请求 gpt-image-2 生成一张全局视觉风格参考图。";
  }
  if (message.includes("生成界面代码")) {
    return "正在读取全局风格参考图，并生成当前页面的可运行 HTML/CSS 代码。";
  }
  if (message.includes("启动生成项目服务")) {
    return "正在启动本次生成的源码项目，准备从真实运行页面重新截图。";
  }
  if (message.includes("渲染界面截图")) {
    return "正在用 Playwright 截取最终写入手册的运行截图。";
  }
  return message || "正在处理当前步骤";
}

function conversationStatusLabel(status, messages) {
  if (status === "success") return "已完成";
  if (status === "error") return "已停止在异常步骤";
  if (status === "cancelled") return "已中止";
  return messages.length ? "实时更新" : "等待事件";
}

function groupEventsByStage(events) {
  const groups = new Map(generationStages.map(([key]) => [key, []]));
  for (const event of events) {
    const key = groups.has(event.stage) ? event.stage : "start";
    groups.get(key).push(event);
  }
  return groups;
}

function stageState(stage, stageEvents, latestStage, status) {
  if (status === "success" && stageEvents.length) return "done";
  if (status === "error" && latestStage === stage) return "error";
  if (status === "cancelled" && latestStage === stage) return "error";
  if (latestStage === stage && status === "running") return "active";
  if (stageEvents.length) return "done";
  return "pending";
}

function stageStateIcon(state) {
  if (state === "active") return <Loader2 size={14} />;
  if (state === "done") return <CheckCircle2 size={14} />;
  if (state === "error") return <AlertTriangle size={14} />;
  return null;
}

function stageCountLabel(stage, stageEvents) {
  if (stageEvents.length) return `${stageEvents.length} 步`;
  const planned = stagePlannedSteps[stage] || [];
  if (planned.length) return `${planned.length} 子步骤`;
  return "待开始";
}

function stageSummary(stage, last) {
  if (last?.message) return last.message;
  if (stage === "visual_reference") {
    return "等待先生成全局风格参考图";
  }
  if (stage === "screenshots") {
    return "等待复用风格参考图、按图生成代码和运行截图";
  }
  return "等待上一阶段完成后自动进入";
}

function plannedStepState(stage, stageEvents, step) {
  const matchedIndex = stageEvents.findIndex((event) =>
    (step.match || []).some((pattern) => String(event.message || "").includes(pattern))
  );
  if (matchedIndex >= 0) return "done";
  if (!stageEvents.length) return "";
  const previousSteps = stagePlannedSteps[stage] || [];
  const stepIndex = previousSteps.findIndex((item) => item.label === step.label);
  const previousDone = stepIndex <= 0 || previousSteps
    .slice(0, stepIndex)
    .every((item) => plannedStepState(stage, stageEvents, item) === "done");
  return previousDone ? "active" : "";
}

function stageLabel(stage) {
  return generationStages.find(([key]) => key === stage)?.[1] || "运行步骤";
}

function processEventDetail(event) {
  const path = event.file_path || event.output_path || event.docx_path || event.pdf_path || event.zip_path || "";
  const parts = [];
  if (path) parts.push(path);
  if (event.page && event.total_pages) parts.push(`第 ${event.page}/${event.total_pages} 页`);
  if (event.line_count) parts.push(`${event.line_count} 行`);
  if (event.file_count) parts.push(`${event.file_count} 个文件`);
  if (event.width && event.height) parts.push(`${event.width}x${event.height}`);
  if (event.material_type) parts.push(event.material_type);
  return parts.join(" · ");
}

function buildCommandPreview(form) {
  return [
    "python backend\\generate_materials.py",
    `  --name "${form.name}"`,
    `  --version ${form.version}`,
    `  --language ${form.language}`,
    `  --product-type ${form.productType}`,
    `  --software-category ${form.softwareCategory}`,
    `  --feature-hint "${form.featureHint}"`,
    `  --model-plan ${form.modelPlan}`,
    `  --model-provider ${form.modelProvider}`,
    `  --model-name ${form.modelName}`
  ].join(" `\n");
}

function DeliveryStatus({ result }) {
  const status = deliveryStatus(result);
  return (
    <div className={`delivery-status ${status.state}`}>
      <span className="quality-state">{qualityIcon(status.state)}</span>
      <div>
        <strong>{status.title}</strong>
        <p>{status.detail}</p>
      </div>
    </div>
  );
}

function VisualReferenceFailureHint({ result }) {
  const checks = result?.checks || {};
  if (checks.ui_visual_reference_ready || !checks.ui_visual_reference_image_model && !checks.ui_visual_reference_error) {
    return null;
  }
  const model = checks.ui_visual_reference_image_model || "gpt-image-2";
  const failedPage = checks.ui_visual_reference_failed_page || "当前页面";
  const retryCount = Number(checks.ui_visual_reference_retry_count || 0);
  const referenceCount = Number(checks.ui_visual_reference_count || 0);
  const pageCount = Number(checks.ui_visual_reference_page_count || 0);
  const source = String(checks.ui_visual_reference_source || "");
  const isStyleReference = checks.ui_visual_reference_mode === "style_reference"
    || failedPage === "style_reference"
    || source.includes("style-reference")
    || source.includes("style_reference")
    || source.includes("gpt-style-reference");
  const mode = isStyleReference ? "style_reference" : (checks.ui_visual_reference_mode || "per_page");
  const targetCount = Number(checks.ui_visual_reference_target_count || (mode === "style_reference" ? 1 : pageCount));
  const appliesToPageCount = Number(checks.ui_visual_reference_applies_to_page_count || pageCount || 0);
  const failedPageLabel = mode === "style_reference" && failedPage === "style_reference" ? "全局风格参考图" : failedPage;
  const retryLabel = retryCount > 0 ? `已按图片链路重试 ${retryCount} 次` : "图片链路未配置额外重试";
  const countLabel = mode === "style_reference"
    ? referenceCount > 0
      ? `全局风格参考图已生成（${referenceCount}/${targetCount || 1}），将覆盖 ${appliesToPageCount || "全部"} 个页面`
      : `全局风格参考图未完成（${referenceCount}/${targetCount || 1}），该图将覆盖 ${appliesToPageCount || "全部"} 个页面`
    : pageCount
      ? `已完成 ${referenceCount}/${pageCount} 张参考稿`
      : "参考稿未完成";
  return (
    <small>
      视觉参考稿阶段未完成：失败项 {failedPageLabel}，图片模型 {model}，{retryLabel}，{countLabel}。
      {checks.ui_visual_reference_directory ? ` 参考稿目录：${checks.ui_visual_reference_directory}` : ""}
    </small>
  );
}

function deliveryStatus(result) {
  const checks = result?.checks || {};
  const findings = Array.isArray(result?.validation?.findings) ? result.validation.findings : [];
  if (!Object.prototype.hasOwnProperty.call(checks, "validation_ready_for_delivery")) {
    return {
      state: "warn",
      title: "交付状态待确认",
      detail: "本次结果未返回真实性/规范性校验摘要，请打开 generation_report.json 查看。"
    };
  }
  if (checks.validation_ready_for_delivery) {
    return {
      state: "pass",
      title: "校验通过，建议交付",
      detail: `真实性 ${scoreLabel(checks.authenticity_score)}，规范性 ${scoreLabel(checks.normative_score)}，未发现硬性阻断项。`
    };
  }
  return {
    state: "fail",
    title: "需要复核后再交付",
    detail: findings.length ? findingSummary(findings) : "真实性或规范性校验未通过，请打开 validation_report.json 查看完整原因。"
  };
}

function buildQualityItems(result) {
  if (!result?.checks) return [];
  const checks = result.checks;
  const warnings = result.warnings || [];
  const files = result.files || [];
  const validation = result.validation || {};
  const validationFindings = Array.isArray(validation.findings) ? validation.findings : [];
  const pdfCount = files.filter((file) => String(file).toLowerCase().endsWith(".pdf")).length;
  const docxCount = files.filter((file) => String(file).toLowerCase().endsWith(".docx")).length;
  const sourceLines = Number(checks.source_total_lines || 0);
  const selectedPages = Number(checks.source_selected_pages || 0);
  return [
    {
      label: "生成策略",
      value: generationProfileLabel(checks.generation_quality_profile),
      detail: `蓝图目标 ${checks.blueprint_quality_target || 78}，实际 ${checks.blueprint_quality_score || 0}`,
      state: checks.generation_quality_profile === "fast" ? "warn" : "pass"
    },
    {
      label: "阶段复用",
      value: stageCacheHitValue(checks.stage_cache_hits),
      detail: checks.stage_cache_enabled
        ? `缓存键 ${String(checks.stage_cache_key || "").slice(0, 8) || "已启用"}`
        : "阶段缓存未启用",
      state: Array.isArray(checks.stage_cache_hits) && checks.stage_cache_hits.length ? "pass" : "warn"
    },
    {
      label: "技术架构",
      value: checks.technical_architecture || "自动选择",
      detail: `${checks.technical_architecture_source === "llm" ? "GPT选择" : "规则选择"} / ${checks.source_strategy || "源码策略"} / ${checks.source_language || "多语言源码"}`,
      state: checks.technical_architecture_source === "llm" || checks.technical_architecture ? "pass" : "warn"
    },
    {
      label: "真实性评分",
      value: scoreLabel(checks.authenticity_score),
      detail: validationDetail(validation, "authenticity"),
      state: checks.authenticity_ready ? "pass" : "warn"
    },
    {
      label: "规范性评分",
      value: scoreLabel(checks.normative_score),
      detail: validationDetail(validation, "normative"),
      state: checks.normative_ready ? "pass" : "fail"
    },
    {
      label: "交付建议",
      value: checks.validation_ready_for_delivery ? "建议交付" : "需要复核",
      detail: validationFindings.length ? findingSummary(validationFindings) : "ZIP 内容与交付白名单一致。",
      state: checks.validation_ready_for_delivery ? "pass" : "fail"
    },
    {
      label: "源码行数",
      value: `${sourceLines} 行`,
      detail: "目标不少于 3000 行",
      state: checks.source_line_target_met ? "pass" : "fail"
    },
    {
      label: "源码材料页数",
      value: selectedPages ? `${selectedPages} 页` : "未生成",
      detail: "按源码鉴别材料规则抽取",
      state: selectedPages >= 60 || selectedPages > 0 ? "pass" : "warn"
    },
    {
      label: "PDF 转换",
      value: pdfCount ? `${pdfCount} 个 PDF` : "未发现 PDF",
      detail: docxCount ? `已生成 ${docxCount} 个 Word 文档` : "请确认 python-docx 与 LibreOffice 状态",
      state: pdfCount > 0 ? "pass" : "warn"
    },
    {
      label: "生成警告",
      value: warnings.length ? `${warnings.length} 条警告` : "无警告",
      detail: warnings[0] || "生成链路未返回异常提示。",
      state: warnings.length ? "warn" : "pass"
    }
  ];
}

function scoreLabel(value) {
  const score = Number(value);
  return Number.isFinite(score) && score > 0 ? `${score} 分` : "未评分";
}

function validationDetail(validation, kind) {
  const section = validation?.[kind] || {};
  if (kind === "authenticity") {
    return `源码文件 ${section.source_file_count || 0}；说明书模块命中 ${section.manual_module_title_hits || 0}；截图模块命中 ${section.ui_module_title_hits || 0}`;
  }
  return `交付文件 ${section.deliverable_count || 0}；ZIP 条目 ${section.zip_entry_count || 0}；占位/乱码 ${(section.placeholder_hits || []).length}`;
}

function findingSummary(findings) {
  return findings
    .slice(0, 3)
    .map((item) => item.suggestion || item.message || item.code || "校验发现")
    .join("；");
}

function generationProfileLabel(profile) {
  if (profile === "authenticity-first") return "真实性优先";
  if (profile === "fast") return "快速批量";
  return "平衡加速";
}

function stageCacheHitValue(hits) {
  if (!Array.isArray(hits) || !hits.length) return "未复用";
  const labels = {
    blueprint: "产品蓝图",
    technical_architecture: "技术架构",
    manual_content: "说明书正文",
    ui_blueprint: "界面蓝图"
  };
  return hits.map((item) => labels[item] || item).join("、");
}

function buildGeneratedFiles(result) {
  if (!result) return [];
  const items = [];
  if (result.zipPath) items.push({ name: fileName(result.zipPath), path: result.zipPath, icon: <Archive size={16} /> });
  if (result.validation?.path) items.push({ name: "validation_report.json", path: result.validation.path, icon: <FileCheck2 size={16} /> });
  if (result.validation?.manifest_path) {
    items.push({ name: "materials_manifest.json", path: result.validation.manifest_path, icon: <FileCheck2 size={16} /> });
  }
  for (const path of result.files || []) {
    items.push({ name: fileName(path), path, icon: fileIcon(path) });
  }
  return items;
}

function fileIcon(path) {
  const lower = String(path).toLowerCase();
  if (lower.endsWith(".zip")) return <Archive size={16} />;
  if (lower.endsWith(".pdf") || lower.endsWith(".docx") || lower.endsWith(".txt")) return <FileText size={16} />;
  if (lower.endsWith(".json")) return <FileCheck2 size={16} />;
  return <Code2 size={16} />;
}

function fileName(path) {
  return String(path).split(/[\\/]/).filter(Boolean).pop() || String(path);
}

function qualityIcon(state) {
  if (state === "pass") return <CheckCircle2 size={15} />;
  if (state === "fail") return <AlertTriangle size={15} />;
  return <AlertTriangle size={15} />;
}

function balanceHint(account) {
  if (account.status === "local") return account.message || "本地生成模式，不消耗 token";
  if (account.status === "connected") return account.updatedAt ? `更新于 ${account.updatedAt}` : "模型账户可用";
  if (account.status === "unconfigured") return account.message || "请先选择文本模型供应商并配置 API Key";
  if (account.status === "error") return account.message || "账户接口异常";
  return "保存文本模型配置后可读取账户状态";
}

function inferFeatureHint(name, productType = "") {
  const text = `${name} ${productType}`;
  if (/点餐|订餐|外卖|餐饮|菜单|菜品/.test(text)) {
    return "菜品浏览、菜单分类、购物车选餐、规格口味选择、订单提交、在线支付、堂食取餐、外卖配送、优惠券使用、订单状态跟踪、历史订单、门店信息";
  }
  if (/听歌|音乐|歌曲|歌单/.test(text)) {
    return "音乐首页推荐、歌曲播放控制、歌词同步显示、歌单收藏管理、音乐搜索、歌手专辑浏览、最近播放记录、离线下载缓存、会员音质权益";
  }
  if (/阅读|听书|小说|书城/.test(text)) {
    return "书城浏览、书架管理、小说阅读、有声听书、章节目录、听书播放、阅读进度、收藏订阅、会员权益";
  }
  if (/一笔连线|一笔画|连线|路径|迷宫|益智|解谜|关卡/.test(text)) {
    return "关卡挑战、连线路径绘制、图形节点规划、难度进阶、提示道具、步数限制、星级评价、通关记录、成就排行";
  }
  if (/你画我猜|画画|绘画|猜词|涂鸦|画板/.test(text)) {
    return "玩家账号、房间匹配、题目抽取、画板绘制、猜词提交、回合计时、积分结算、排行榜统计";
  }
  const terms = splitTerms(name).slice(0, 4);
  return terms.length
    ? ["用户入口", "首页导航", "核心工作台", "业务表单处理", "记录查询", "统计分析", "消息提醒", "系统设置"].join("、")
    : "用户入口、首页导航、核心工作台、业务表单处理、记录查询、统计分析、消息提醒、系统设置";
}

createRoot(document.getElementById("root")).render(<App />);
