import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  AlertTriangle,
  Archive,
  CheckCircle2,
  ChevronDown,
  Code2,
  FileCheck2,
  FileText,
  FolderOpen,
  Loader2,
  PackageCheck,
  Plus,
  RefreshCw,
  Save,
  Settings2,
  Sparkles,
  TerminalSquare,
  Trash2,
  Wand2
} from "lucide-react";
import "./styles.css";

const softwareCategories = ["应用软件", "嵌入式软件", "中间件", "操作系统"];

const productTypes = [
  "APP",
  "游戏软件",
  "教育软件",
  "金融软件",
  "医疗软件",
  "地理信息软件",
  "云计算软件",
  "信息安全软件",
  "大数据软件",
  "人工智能软件",
  "VR软件",
  "5G软件",
  "小程序",
  "物联网软件",
  "智慧城市软件"
];

const modelProviders = [
  {
    value: "gpt",
    label: "GPT",
    description: "仅使用 GPT 生成大纲、蓝图、说明书正文和界面内容。",
    provider: "custom",
    modelName: "gpt",
    cost: "唯一模式"
  }
];

const generationStages = [
  ["start", "提交任务"],
  ["prepare", "理解软件名称"],
  ["blueprint", "生成产品蓝图"],
  ["manual_content", "生成说明书正文"],
  ["source", "生成源码工程"],
  ["source_doc", "源码鉴别材料"],
  ["manual", "生成文档材料"],
  ["screenshots", "生成界面截图"],
  ["pdf", "转换 PDF"],
  ["info", "申请信息表"],
  ["package", "打包与校验"]
];

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
    modelName: "gpt-4o-mini",
    randomness: "standard"
  });
  const [modelConfig, setModelConfig] = useState({
    mode: "gpt",
    modelName: "gpt-4o-mini",
    apiBaseUrl: "",
    apiKey: "",
    apiKeyConfigured: false,
    preset: false
  });
  const [account, setAccount] = useState({
    status: "unknown",
    accountName: "未连接",
    balanceLabel: "待配置",
    updatedAt: ""
  });
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

  const canPlan = extractSoftwareName(form.name).length > 0;
  const planReady = businessPlan.modules.length > 0;
  const gptConfigured = Boolean(
    modelConfig.apiBaseUrl.trim() && (modelConfig.apiKey.trim() || (bridgeAvailable && modelConfig.apiKeyConfigured))
  );
  const canGenerate = canPlan && planReady && outlineState === "confirmed" && status !== "running" && status !== "planning" && gptConfigured;
  const canPrimaryAction = canPlan && status !== "running" && status !== "planning";
  const primaryActionLabel = primaryButtonLabel(status, outlineState, planReady, gptConfigured);
  const generatedFiles = useMemo(() => buildGeneratedFiles(result), [result]);
  const qualityItems = useMemo(() => buildQualityItems(result), [result]);
  const activeEvent = currentEvent(events);

  useEffect(() => {
    if (!bridgeAvailable) return undefined;
    return window.softCopyright.onGenerateEvent((event) => {
      setProgress(event.progress || 0);
      setEvents((current) => [
        ...current,
        {
          ...event,
          at: new Date().toLocaleTimeString(),
          elapsedMs: processClock.startedAt ? Date.now() - processClock.startedAt : 0
        }
      ].slice(-500));
    });
  }, [bridgeAvailable, processClock.startedAt]);

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
      setModelConfig({
        mode: "gpt",
        modelName: config.modelName || "gpt-4o-mini",
        apiBaseUrl: config.apiBaseUrl || "",
        apiKey: config.apiKey || "",
        apiKeyConfigured: Boolean(config.apiKeyConfigured || config.apiKey),
        preset: Boolean(config.preset)
      });
      const plan = modelProviders[0];
      setForm((current) => ({
        ...current,
        modelPlan: "gpt",
        modelProvider: plan.provider,
        modelName: config.modelName || plan.modelName
      }));
    });
    return () => {
      cancelled = true;
    };
  }, [bridgeAvailable]);

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
      setProcessClock({ mode: "idle", startedAt: 0, elapsedMs: 0 });
    }
  }

  async function inferBusinessPlan(payload) {
    if (!payload.name.trim()) return null;
    let featureHint = "";
    let meta = {};
    if (!modelConfig.apiBaseUrl.trim() || !(modelConfig.apiKey.trim() || (bridgeAvailable && modelConfig.apiKeyConfigured))) {
      setConfigStatus("请先配置 GPT 请求地址和 API Key");
      setSettingsOpen(true);
      return null;
    }
    setStatus("planning");
    try {
      const response =
        bridgeAvailable && window.softCopyright.inferFeatureHint
          ? await window.softCopyright.inferFeatureHint({ ...payload, modelPlan: "gpt", modelProvider: "custom" })
          : await inferFeatureHintThroughDevApi({
              ...payload,
              modelName: modelConfig.modelName,
              apiBaseUrl: modelConfig.apiBaseUrl,
              apiKey: modelConfig.apiKey
            });
      if (response?.ok && response.featureHint) {
        featureHint = response.featureHint;
        meta = response.meta || {};
      } else {
        setConfigStatus(response?.message || response?.stderr || "GPT 大纲生成失败，请检查接口配置");
        setSettingsOpen(true);
        return null;
      }
    } catch (_error) {
      setConfigStatus("GPT 大纲生成失败，请检查接口配置");
      setSettingsOpen(true);
      return null;
    }
    return {
      hint: featureHint,
      meta,
      plan: buildBusinessPlan(payload.name, payload.productType, featureHint, meta)
    };
  }

  async function regeneratePlan() {
    const name = extractSoftwareName(form.name || inputText);
    if (!name || status === "running") return;
    const startedAt = Date.now();
    setResult(null);
    setProgress(6);
    setStatus("planning");
    setProcessClock({ mode: "outline", startedAt, elapsedMs: 0 });
    setEvents([createProcessEvent("outline", 6, `正在读取软件名称「${name}」和产品类型`, startedAt)]);
    await wait(180);
    setProgress(18);
    setEvents((current) => [
      ...current,
      createProcessEvent("outline", 18, "正在构建 GPT 结构化蓝图请求，要求返回模块分类、说明、数据对象和页面入口", startedAt)
    ]);
    await wait(180);
    setProgress(32);
    setEvents((current) => [
      ...current,
      createProcessEvent("outline", 32, "正在调用 GPT 识别名称语义，当前等待模型返回 JSON 蓝图", startedAt)
    ]);
    const response = await inferBusinessPlan({ ...form, name, featureHint: extractInputSupplement(form.name || inputText) });
    if (!response) {
      setProgress(0);
      setStatus(businessPlan.modules.length ? "editing" : "idle");
      setProcessClock({ mode: "idle", startedAt: 0, elapsedMs: 0 });
      return;
    }
    setProgress(72);
    setEvents((current) => [
      ...current,
      createProcessEvent(
        "outline",
        72,
        `已收到 GPT 结构化结果，正在校验 ${response.plan.modules.length} 个模块的重复度和领域一致性`,
        startedAt
      )
    ]);
    await wait(180);
    setProgress(88);
    setEvents((current) => [
      ...current,
      createProcessEvent("outline", 88, "正在整理为可编辑蓝图，保留 GPT 的分类、模块说明、流程和页面信息", startedAt)
    ]);
    await wait(180);
    setFeatureHintMeta({ ...(response.meta || {}), _plannedAt: new Date().toLocaleTimeString() });
    setBusinessPlan(response.plan);
    setForm((current) => ({ ...current, featureHint: serializePlan(response.plan) }));
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
    if (bridgeAvailable && !gptConfigured) {
      setConfigStatus("请先配置 GPT 请求地址和 API Key");
      setSettingsOpen(true);
      return;
    }
    if (bridgeAvailable && window.softCopyright.inferFeatureHint && status !== "planning") {
      const startedAt = Date.now();
      const targetModule = businessPlan.modules[moduleIndex];
      setOutlineState("draft");
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
    setModelConfig((current) => ({ ...current, mode: "gpt" }));
    setForm((current) => ({
      ...current,
      modelPlan: "gpt",
      modelProvider: plan.provider,
      modelName: modelConfig.modelName || plan.modelName
    }));
  }

  function updateModelConfig(key, value) {
    setConfigStatus("");
    setModelConfig((current) => ({ ...current, [key]: value }));
    if (key === "modelName") {
      setForm((current) => ({ ...current, modelName: value }));
    }
  }

  async function saveModelConfig() {
    if (!bridgeAvailable || !window.softCopyright.saveModelConfig) {
      if (!modelConfig.apiBaseUrl.trim() || !modelConfig.apiKey.trim()) {
        setConfigStatus("请填写 GPT 请求地址和 API Key");
        return;
      }
      setModelConfig((current) => ({ ...current, mode: "gpt", apiKeyConfigured: Boolean(current.apiKey.trim()) }));
      setConfigStatus("saved");
      return;
    }
    setConfigStatus("saving");
    const response = await window.softCopyright.saveModelConfig({
      mode: "gpt",
      modelName: modelConfig.modelName,
      apiBaseUrl: modelConfig.apiBaseUrl,
      apiKey: modelConfig.apiKey
    });
    if (!response?.ok) {
      setConfigStatus(response?.message || "保存失败");
      return;
    }
    setConfigStatus("saved");
    const plan = modelProviders[0];
    setForm((current) => ({
      ...current,
      modelPlan: "gpt",
      modelProvider: plan.provider,
      modelName: response.modelName || plan.modelName
    }));
    setModelConfig((current) => ({
      ...current,
      mode: "gpt",
      modelName: response.modelName || current.modelName,
      apiBaseUrl: response.apiBaseUrl || current.apiBaseUrl,
      apiKey: response.apiKey || current.apiKey,
      apiKeyConfigured: Boolean(response.apiKeyConfigured || response.apiKey || current.apiKey)
    }));
    await refreshModelAccount();
  }

  async function fetchModelAccount() {
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

  async function handlePrimaryAction() {
    if (!canPrimaryAction) return;
    if (!gptConfigured) {
      setConfigStatus("请先配置 GPT 请求地址和 API Key");
      setSettingsOpen(true);
      return;
    }
    if (outlineState !== "draft" && outlineState !== "confirmed") {
      await regeneratePlan();
      return;
    }
    if (outlineState === "draft") {
      setOutlineState("confirmed");
      await handleGenerate({}, "大纲已确认，开始生成材料包", { force: true });
      return;
    }
    await handleGenerate({}, "大纲已确认，开始生成材料包");
  }

  async function handleGenerate(overrides = {}, submitMessage = "任务已提交", options = {}) {
    if (!options.force && !canGenerate) return;
    if (!gptConfigured || status === "running" || status === "planning" || !canPlan || !planReady) return;
    const startedAt = Date.now();
    const cleanName = businessPlan.softwareName || extractSoftwareName(form.name);
    const extraInputHint = extractInputSupplement(form.name);
    const planHint = serializePlan(businessPlan);
    const payload = {
      ...form,
      ...overrides,
      name: cleanName,
      featureHint: [planHint, extraInputHint].filter(Boolean).join("；"),
      businessPlan
    };
    setStatus("running");
    setResult(null);
    setProgress(3);
    setProcessClock({ mode: "materials", startedAt, elapsedMs: 0 });
    setEvents([createProcessEvent("start", 3, submitMessage, startedAt)]);
    if (!bridgeAvailable) {
      await new Promise((resolve) => setTimeout(resolve, 700));
      setResult({
        ok: true,
        zipPath: "浏览器预览模式：请在 Electron 中运行以调用本地生成器。",
        outputDir: "",
        checks: {},
        warnings: [],
        stdout: buildCommandPreview(payload),
        stderr: "",
        seed: payload.seed || "preview-seed",
        randomness: payload.randomness
      });
      setProgress(100);
      setProcessClock((current) => ({ ...current, elapsedMs: Date.now() - startedAt }));
      setStatus("success");
      return;
    }
    try {
      const response = await window.softCopyright.generateMaterials(payload);
      setResult(response);
      setProgress((current) => (response.ok ? 100 : current));
      setProcessClock((current) => ({ ...current, elapsedMs: Date.now() - startedAt }));
      setStatus(response.ok ? "success" : "error");
    } catch (error) {
      setResult({
        ok: false,
        zipPath: "",
        outputDir: "",
        checks: {},
        warnings: [],
        stdout: "",
        stderr: error?.message || "生成任务异常"
      });
      setProcessClock((current) => ({ ...current, elapsedMs: Date.now() - startedAt }));
      setStatus("error");
    } finally {
      await refreshModelAccount();
    }
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
  }

  function newTask() {
    setForm((current) => ({
      ...current,
      name: "",
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
    setProcessClock({ mode: "idle", startedAt: 0, elapsedMs: 0 });
    setStatus("idle");
  }

  return (
    <main className="workbench">
      <header className="top-strip">
        <div>
          <p className="eyebrow">Soft Copyright AI Workbench</p>
          <h1>软著材料 AI 工作台</h1>
        </div>
        <div className="top-actions">
          <span className={`task-pill ${status}`}>{statusLabel(status)}</span>
          <button className="icon-button" type="button" onClick={() => setSettingsOpen(true)} title="高级设置">
            <Settings2 size={19} />
          </button>
        </div>
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
          bridgeAvailable={bridgeAvailable}
          onRegeneratePlan={regeneratePlan}
          onAddModule={addModule}
          onRemoveModule={removeModule}
          onUpdateModule={updateModule}
          onRegenerateModule={regenerateModule}
          onAddChild={addChild}
          onRemoveChild={removeChild}
          onUpdateChild={updateChild}
          onOpenFile={openGeneratedFile}
        />
      </section>

      <footer className="command-bar">
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
              <span>基于当前重新生成</span>
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
        ) : (
          <>
            <div className="prompt-row">
              <textarea
                value={inputText || form.name}
                onChange={(event) => updateField("name", event.target.value)}
                placeholder="输入软件名称，例如：小风点餐。也可以写补充要求。"
              />
              <button className="primary-action" type="button" disabled={!canPrimaryAction} onClick={handlePrimaryAction}>
                {status === "running" || status === "planning" ? <Loader2 size={20} /> : <Sparkles size={20} />}
                <span>{primaryActionLabel}</span>
              </button>
            </div>
            <div className="parameter-row">
              <label>
                <span>软件大类</span>
                <select value={form.softwareCategory} onChange={(event) => updateField("softwareCategory", event.target.value)}>
                  {softwareCategories.map((item) => (
                    <option key={item} value={item}>
                      {item}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>技术特点</span>
                <select value={form.productType} onChange={(event) => updateField("productType", event.target.value)}>
                  {productTypes.map((item) => (
                    <option key={item} value={item}>
                      {item}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>源码架构</span>
                <input value="自动选择技术架构，可多语言生成" readOnly />
              </label>
            </div>
          </>
        )}
      </footer>

      {settingsOpen && (
        <SettingsDrawer
          form={form}
          modelConfig={modelConfig}
          account={account}
          configStatus={configStatus}
          bridgeAvailable={bridgeAvailable}
          onClose={() => setSettingsOpen(false)}
          onUpdateField={updateField}
          onUpdateModelPlan={updateModelPlan}
          onUpdateModelConfig={updateModelConfig}
          onSaveModelConfig={saveModelConfig}
          onRefreshAccount={refreshModelAccount}
        />
      )}
    </main>
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
  bridgeAvailable,
  onRegeneratePlan,
  onAddModule,
  onRemoveModule,
  onUpdateModule,
  onRegenerateModule,
  onAddChild,
  onRemoveChild,
  onUpdateChild,
  onOpenFile
}) {
  const planReady = businessPlan.modules.length > 0;
  const elapsedLabel = processClock.elapsedMs ? `已用 ${formatElapsed(processClock.elapsedMs)}` : "";

  return (
    <div className="transcript">
      {(status === "planning" || status === "editing" || status === "idle") && (
        <section className="work-section editor-section">
          <div className="section-toolbar">
            <div>
              <strong>详细蓝图</strong>
              <span>
                {status === "planning" && elapsedLabel
                  ? `GPT 生成中 · ${elapsedLabel}`
                  : planReady
                    ? `${businessPlan.modules.length} 个模块 · ${outlineStatusLabel(outlineState, planReady)}`
                    : "点击生成大纲后开始生成"}
              </span>
            </div>
            <button type="button" onClick={onRegeneratePlan} disabled={!extractSoftwareName(form.name) || status === "planning"}>
              <RefreshCw size={15} />
              <span>{status === "planning" ? "生成中" : "重新生成大纲"}</span>
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
            <div className="empty-plan compact-empty">
              <Wand2 size={24} />
              <strong>{form.name.trim() ? "等待生成大纲" : "等待输入软件名称"}</strong>
              <p>{form.name.trim() ? "点击底部“生成大纲”后，这里会显示生成进度和可编辑的详细蓝图。" : "输入软件名称后，点击底部按钮生成详细蓝图。"}</p>
            </div>
          )}
        </section>
      )}

      {(status === "running" || status === "success" || status === "error") && (
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
        <section className={`work-section result-message ${result.ok ? "success" : "error"}`}>
          <div className="section-toolbar">
            <div>
              <strong>{result.ok ? "结果报告" : "失败报告"}</strong>
              <span>{result.ok ? "已完成" : "需要处理"}</span>
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
              <AlertTriangle size={22} />
              <p>{result.stderr || "生成任务异常，请查看运行日志定位问题。"}</p>
            </div>
          )}
        </section>
      )}
    </div>
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
    <div className="process-board">
      <div className={`process-current ${status}`}>
        <span className="process-current-icon">
          {status === "running" ? <Loader2 size={16} /> : status === "success" ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
        </span>
        <div>
          <strong>{processTitle(status)}</strong>
          <p>{latest?.message || (status === "success" ? "材料包生成完成" : status === "error" ? "生成过程出现异常" : "正在等待生成事件")}</p>
        </div>
        <b>{Math.min(100, progress || latest?.progress || 0)}%</b>
        <small>{formatElapsed(elapsedMs || latest?.elapsedMs || 0)}</small>
      </div>

      <StageDetailGrid events={events} status={status} />
      <ProcessEventFeed events={visibleEvents} />

      <details className="raw-log-details">
        <summary>
          <TerminalSquare size={15} />
          <span>原始运行日志</span>
          <ChevronDown size={15} />
        </summary>
        <pre className="log-view">
          {events.map((event) => `[${event.progress || 0}%] ${event.message}`).join("\n") ||
            [result?.stdout, result?.stderr].filter(Boolean).join("\n") ||
            "等待运行日志"}
        </pre>
      </details>
    </div>
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
        return (
          <div className={`stage-detail ${state}`} key={key}>
            <div className="stage-detail-head">
              <span>{stageStateIcon(state)}</span>
              <strong>{label}</strong>
              <em>{stageEvents.length ? `${stageEvents.length} 步` : "待开始"}</em>
            </div>
            <p>{last?.message || "等待上一阶段完成后自动进入"}</p>
            {stageEvents.length > 1 && (
              <div className="stage-mini-events">
                {stageEvents.slice(-3).map((event, index) => (
                  <span key={`${key}-${index}-${event.progress}`}>{event.message}</span>
                ))}
              </div>
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
  form,
  modelConfig,
  account,
  configStatus,
  bridgeAvailable,
  onClose,
  onUpdateField,
  onUpdateModelPlan,
  onUpdateModelConfig,
  onSaveModelConfig,
  onRefreshAccount
}) {
  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <aside className="settings-drawer" onClick={(event) => event.stopPropagation()}>
        <header>
          <div>
            <p className="eyebrow">Advanced</p>
            <h2>高级设置</h2>
          </div>
          <button className="icon-button" type="button" onClick={onClose}>
            ×
          </button>
        </header>
        <section>
          <h3>生成参数</h3>
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
          <h3>模型模式</h3>
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
          <h3>接口配置</h3>
          <div className="drawer-grid">
            <label className="full">
              <span>请求地址</span>
              <input
                value={modelConfig.apiBaseUrl}
                onChange={(event) => onUpdateModelConfig("apiBaseUrl", event.target.value)}
              />
            </label>
            <label>
              <span>模型名称</span>
              <input
                value={modelConfig.modelName}
                onChange={(event) => onUpdateModelConfig("modelName", event.target.value)}
              />
            </label>
            <label>
              <span>API Key</span>
              <input
                value={modelConfig.apiKey}
                onChange={(event) => onUpdateModelConfig("apiKey", event.target.value)}
              />
            </label>
          </div>
          <button
            type="button"
            className="config-save-button"
            onClick={onSaveModelConfig}
            disabled={
              configStatus === "saving" ||
              (modelConfig.mode === "gpt" && (!modelConfig.apiBaseUrl.trim() || !modelConfig.apiKey.trim()))
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
                : "当前仅支持 GPT，请确认请求地址、模型名称和 API Key。"}
          </small>
        </section>
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
    message,
    at: new Date(now).toLocaleTimeString(),
    elapsedMs: Math.max(0, now - startedAt)
  };
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
      modelName: payload.modelName || "gpt-4o-mini",
      apiBaseUrl: payload.apiBaseUrl || "",
      apiKey: payload.apiKey || ""
    })
  });
  if (!response.ok) {
    return {
      ok: false,
      message: `GPT 大纲生成失败：HTTP ${response.status}`,
      featureHint: "",
      meta: {}
    };
  }
  return response.json();
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
    category: category && category !== "核心模块" ? category : "业务模块",
    title,
    description,
    dataObjects: normalizeDetailList(item.data_objects || item.dataObjects || item.objects, 6),
    userFlow: normalizeDetailList(item.user_flow || item.userFlow || item.flow || item.steps, 6),
    screens: normalizeDetailList(item.screens || item.pages, 5)
  };
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

function statusLabel(status) {
  if (status === "planning") return "理解中";
  if (status === "editing") return "可编辑";
  if (status === "running") return "生成中";
  if (status === "success") return "已完成";
  if (status === "error") return "失败";
  return "待输入";
}

function outlineStatusLabel(outlineState, planReady) {
  if (!planReady || outlineState === "empty") return "未生成大纲";
  if (outlineState === "draft") return "大纲待确认";
  if (outlineState === "confirmed") return "大纲已确认";
  return "未生成大纲";
}

function primaryButtonLabel(status, outlineState, planReady, gptConfigured) {
  if (status === "running") return "生成中";
  if (status === "planning") return "生成大纲中";
  if (!gptConfigured) return "配置 GPT";
  if (!planReady || outlineState === "empty") return "生成大纲";
  if (outlineState === "draft") return "确认大纲并生成";
  return "确认生成";
}

function currentEvent(events) {
  return events.length ? events[events.length - 1] : null;
}

function processTitle(status) {
  if (status === "success") return "材料包生成完成";
  if (status === "error") return "生成失败，等待处理";
  return "AI 正在生成材料包";
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
      value: checks.generation_quality_profile === "authenticity-first" ? "真实性优先" : "快速批量",
      detail: `蓝图目标 ${checks.blueprint_quality_target || 78}，实际 ${checks.blueprint_quality_score || 0}`,
      state: checks.generation_quality_profile === "authenticity-first" ? "pass" : "warn"
    },
    {
      label: "技术架构",
      value: checks.technical_architecture || "自动选择",
      detail: `${checks.software_category || "应用软件"} / ${checks.source_language || "多语言源码"}`,
      state: checks.technical_architecture ? "pass" : "warn"
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
  if (account.status === "connected") return account.updatedAt ? `更新于 ${account.updatedAt}` : "模型账户可用";
  if (account.status === "unconfigured") return account.message || "请先配置 GPT 请求地址和 API Key";
  if (account.status === "error") return account.message || "账户接口异常";
  return "保存 GPT 配置后可读取账户状态";
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
