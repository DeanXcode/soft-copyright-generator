import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  AlertTriangle,
  Archive,
  CheckCircle2,
  Code2,
  FileCheck2,
  FileText,
  FolderOpen,
  ListChecks,
  Loader2,
  PackageCheck,
  RefreshCw,
  Save,
  Settings2,
  Sparkles,
  TerminalSquare
} from "lucide-react";
import "./styles.css";

const supportedLanguages = new Set(["Java", "JavaScript", "Python", "PHP", "C#", "C++", "HTML"]);

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
    value: "template",
    label: "默认模板",
    description: "使用本地模板生成，不调用模型接口。",
    provider: "local-template",
    modelName: "template-v1",
    cost: "不消耗 token"
  },
  {
    value: "gpt",
    label: "GPT",
    description: "通过服务端中转生成产品蓝图和说明书正文。",
    provider: "custom",
    modelName: "gpt",
    cost: "按实际消耗"
  }
];

function App() {
  const [form, setForm] = useState({
    name: "景区票务与门禁智能管理系统",
    version: "V1.0",
    language: "Java",
    productType: "智慧城市软件",
    featureHint: "景区票务、闸机核验、团队订单、年卡管理",
    modelPlan: "gpt",
    modelProvider: "custom",
    modelName: "gpt-4o-mini",
    randomness: "standard"
  });
  const [modelConfig, setModelConfig] = useState({
    mode: "template",
    modelName: "gpt-4o-mini",
    apiBaseUrl: "",
    apiKey: "",
    apiKeyConfigured: false,
    preset: false
  });
  const [configStatus, setConfigStatus] = useState("");
  const [status, setStatus] = useState("idle");
  const [result, setResult] = useState(null);
  const [progress, setProgress] = useState(0);
  const [events, setEvents] = useState([]);
  const [account, setAccount] = useState({
    status: "unknown",
    accountName: "未连接",
    balanceLabel: "待配置",
    updatedAt: ""
  });

  const canGenerate = form.name.trim().length > 0 && supportedLanguages.has(form.language);
  const bridgeAvailable = typeof window !== "undefined" && window.softCopyright;
  const qualityItems = useMemo(() => buildQualityItems(result), [result]);
  const generatedFiles = useMemo(() => buildGeneratedFiles(result), [result]);
  const metrics = useMemo(() => {
    if (result?.checks) {
      const checks = result.checks;
      return [
        ["源码行数", `${checks.source_total_lines || 0} 行`],
        ["源码页数", `${checks.source_total_pages || 0} 页`],
        ["材料页数", `${checks.source_selected_pages || 0} 页`],
        ["说明书", result.manualSource === "llm" ? "模型正文" : "模板正文"]
      ];
    }
    return [
      ["默认源码", "3000+ 行"],
      ["源码材料", "60 页规则"],
      ["输出结构", "样例包格式"],
      ["PDF转换", "LibreOffice"]
    ];
  }, [result]);

  useEffect(() => {
    if (!bridgeAvailable) return undefined;
    return window.softCopyright.onGenerateEvent((event) => {
      setProgress(event.progress || 0);
      setEvents((current) => [...current.slice(-20), event]);
    });
  }, [bridgeAvailable]);

  useEffect(() => {
    if (!bridgeAvailable || !window.softCopyright.getModelAccount) return undefined;
    let cancelled = false;
    fetchModelAccount().then((response) => {
      if (!cancelled && response) {
        setAccount(response);
      }
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
        mode: config.mode || "template",
        modelName: config.modelName || "gpt-4o-mini",
        apiBaseUrl: config.apiBaseUrl || "",
        apiKey: config.apiKey || "",
        apiKeyConfigured: Boolean(config.apiKeyConfigured || config.apiKey),
        preset: Boolean(config.preset)
      });
      const plan = modelProviders.find((item) => item.value === (config.mode || "template")) || modelProviders[0];
      setForm((current) => ({
        ...current,
        modelPlan: plan.value,
        modelProvider: plan.provider,
        modelName: config.modelName || plan.modelName
      }));
    });
    return () => {
      cancelled = true;
    };
  }, [bridgeAvailable]);

  function updateField(key, value) {
    setForm((current) => ({ ...current, [key]: value }));
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
  }

  function updateModelConfig(key, value) {
    setConfigStatus("");
    setModelConfig((current) => ({ ...current, [key]: value }));
    if (key === "modelName") {
      setForm((current) => ({ ...current, modelName: value }));
    }
  }

  async function saveModelConfig() {
    if (!bridgeAvailable || !window.softCopyright.saveModelConfig) return;
    setConfigStatus("saving");
    const response = await window.softCopyright.saveModelConfig({
      mode: modelConfig.mode,
      modelName: modelConfig.modelName,
      apiBaseUrl: modelConfig.apiBaseUrl,
      apiKey: modelConfig.apiKey
    });
    if (!response?.ok) {
      setConfigStatus(response?.message || "保存失败");
      return;
    }
    setConfigStatus("saved");
    const plan = modelProviders.find((item) => item.value === response.mode) || modelProviders[0];
    setForm((current) => ({
      ...current,
      modelPlan: plan.value,
      modelProvider: plan.provider,
      modelName: response.mode === "gpt" ? response.modelName : plan.modelName
    }));
    setModelConfig((current) => ({
      ...current,
      mode: response.mode || current.mode,
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
    if (response) {
      setAccount(response);
    }
  }

  async function handleGenerate(overrides = {}, submitMessage = "任务已提交") {
    if (!canGenerate) return;
    const payload = { ...form, ...overrides };
    setStatus("running");
    setResult(null);
    setProgress(3);
    setEvents([{ stage: "start", progress: 3, message: submitMessage }]);
    if (!bridgeAvailable) {
      await new Promise((resolve) => setTimeout(resolve, 800));
      setResult({
        ok: true,
        zipPath: "浏览器预览模式：请在 Electron 中运行以调用本地生成器。",
        checks: null,
        warnings: [],
        stdout: buildCommandPreview(payload),
        stderr: "",
        seed: payload.seed || "preview-seed",
        randomness: payload.randomness
      });
      setProgress(100);
      setStatus("success");
      return;
    }
    try {
      const response = await window.softCopyright.generateMaterials(payload);
      setResult(response);
      setProgress((current) => (response.ok ? 100 : current));
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
      setStatus("error");
    } finally {
      await refreshModelAccount();
    }
  }

  async function openZip() {
    if (bridgeAvailable && result?.zipPath) {
      await window.softCopyright.openPath(result.zipPath);
    }
  }

  async function openOutputDir() {
    if (bridgeAvailable && result?.outputDir) {
      await window.softCopyright.openPath(result.outputDir);
    }
  }

  async function openGeneratedFile(file) {
    if (bridgeAvailable && file?.path) {
      await window.softCopyright.openPath(file.path);
    }
  }

  return (
    <main className="app-shell">
      <section className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">Soft Copyright Generator</p>
            <h1>生成软著材料包</h1>
            <p className="topbar-copy">填写软件名称和类型，直接生成说明书、源码材料、清单和 ZIP。</p>
          </div>
        </header>

        <div className="main-grid">
          <section className="input-panel">
            <div className="section-title">
              <FileText size={18} />
              <span>生成参数</span>
            </div>
            <div className="field-grid">
              <label>
                <span>软件全称</span>
                <input value={form.name} onChange={(event) => updateField("name", event.target.value)} />
              </label>
              <label>
                <span>版本号</span>
                <input value={form.version} onChange={(event) => updateField("version", event.target.value)} />
              </label>
            </div>

            <div className="field-grid">
              <label>
                <span>源码语言</span>
                <select value={form.language} onChange={(event) => updateField("language", event.target.value)}>
                  {[...supportedLanguages].map((item) => (
                    <option key={item} value={item}>
                      {item}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>软件类型</span>
                <select value={form.productType} onChange={(event) => updateField("productType", event.target.value)}>
                  {productTypes.map((item) => (
                    <option key={item} value={item}>
                      {item}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <label className="wide-field">
              <span>业务补充</span>
              <textarea
                maxLength={100}
                value={form.featureHint}
                onChange={(event) => updateField("featureHint", event.target.value)}
              />
              <small>{form.featureHint.length}/100</small>
            </label>

            <button className="primary-action inline-primary" disabled={!canGenerate || status === "running"} onClick={() => handleGenerate()}>
              {status === "running" ? <Loader2 size={18} /> : <Sparkles size={18} />}
              <span>{status === "running" ? "生成中" : "生成材料包"}</span>
            </button>

            <details className="secondary-panel">
              <summary>
                <Settings2 size={16} />
                <span>高级设置</span>
              </summary>
              <div className="secondary-body">
                <div className="model-option-grid">
                  {modelProviders.map((item) => (
                    <button
                      key={item.value}
                      className={form.modelPlan === item.value ? "model-option selected" : "model-option"}
                      onClick={() => updateModelPlan(item.value)}
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
                  {account.status === "refreshing" || account.status === "loading" ? (
                    <RefreshCw className="spin-icon" size={18} />
                  ) : (
                    <PackageCheck size={18} />
                  )}
                  <div>
                    <span>{account.accountName || "未连接"}</span>
                    <strong>{account.balanceLabel || "待配置"}</strong>
                    <small>{balanceHint(account)}</small>
                  </div>
                </div>
                <div className="model-config-form">
                  <div className="field-grid config-field-grid">
                    <label className="config-wide-field">
                      <span>请求地址</span>
                      <input
                        value={modelConfig.apiBaseUrl}
                        disabled={modelConfig.mode === "template"}
                        onChange={(event) => updateModelConfig("apiBaseUrl", event.target.value)}
                      />
                    </label>
                    <label>
                      <span>模型名称</span>
                      <input
                        value={modelConfig.modelName}
                        disabled={modelConfig.mode === "template"}
                        onChange={(event) => updateModelConfig("modelName", event.target.value)}
                      />
                    </label>
                    <label>
                      <span>API Key</span>
                      <input
                        value={modelConfig.apiKey}
                        disabled={modelConfig.mode === "template"}
                        onChange={(event) => updateModelConfig("apiKey", event.target.value)}
                      />
                    </label>
                  </div>
                  <button
                    type="button"
                    className="config-save-button"
                    onClick={saveModelConfig}
                    disabled={
                      !bridgeAvailable ||
                      configStatus === "saving" ||
                      (modelConfig.mode === "gpt" && (!modelConfig.apiBaseUrl.trim() || !modelConfig.apiKey.trim()))
                    }
                  >
                    {configStatus === "saving" ? <Loader2 size={16} /> : <Save size={16} />}
                    <span>{configStatus === "saving" ? "保存中" : "保存模型配置"}</span>
                  </button>
                  <small className={configStatus && configStatus !== "saved" && configStatus !== "saving" ? "config-message error" : "config-message"}>
                    {configStatus === "saved"
                      ? "模型配置已保存"
                      : configStatus === "saving"
                        ? "正在写入本地配置"
                        : modelConfig.mode === "template"
                          ? "默认模板不会调用模型接口。"
                          : modelConfig.preset
                            ? "当前显示的是交付包预置配置，可按需修改并保存。"
                            : "请确认请求地址、模型名称和 API Key 后保存。"}
                  </small>
                </div>
              </div>
            </details>
          </section>

          <aside className="output-panel">
            <div className="status-block">
              <div className={`status-icon ${status}`}>
                {status === "running" ? <Loader2 size={28} /> : status === "success" ? <CheckCircle2 size={28} /> : <PackageCheck size={28} />}
              </div>
              <div>
                <p className="eyebrow">生成状态</p>
                <h2>{statusLabel(status)}</h2>
                <p className="status-text">{statusText(status, bridgeAvailable)}</p>
              </div>
            </div>

            <div className="progress-block">
              <div className="progress-head">
                <span>{currentEvent(events)?.message || "等待任务"}</span>
                <strong>{progress}%</strong>
              </div>
              <div className="progress-track">
                <div style={{ width: `${Math.min(100, progress)}%` }} />
              </div>
            </div>

            <div className="secondary-actions">
              <button type="button" onClick={openZip} disabled={!result?.zipPath || !bridgeAvailable}>
                <FolderOpen size={16} />
                <span>打开材料包</span>
              </button>
              <button type="button" onClick={openOutputDir} disabled={!result?.outputDir || !bridgeAvailable}>
                <FolderOpen size={16} />
                <span>输出目录</span>
              </button>
            </div>

            {result && (
              <div className={`result-box ${result.ok ? "success" : "error"}`}>
                <span>{result.ok ? "生成完成" : "生成失败"}</span>
                <p>{result.zipPath || result.stderr || "请查看日志。"}</p>
                {result.warnings?.length > 0 && (
                  <ul>
                    {result.warnings.map((warning) => (
                      <li key={warning}>{warning}</li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            <div className="summary-list">
              {metrics.map(([label, value]) => (
                <div key={label}>
                  <span>{label}</span>
                  <strong>{value}</strong>
                </div>
              ))}
            </div>

            <details className="secondary-panel">
              <summary>
                <RefreshCw size={16} />
                <span>重新生成</span>
              </summary>
              <div className="regen-actions secondary-body">
                <button
                  type="button"
                  onClick={() => handleGenerate({}, "任务已提交：全量重生成")}
                  disabled={!canGenerate || status === "running"}
                  title="使用当前首页参数生成新的材料包"
                >
                  <RefreshCw size={16} />
                  <span>新随机版</span>
                </button>
                <button
                  type="button"
                  onClick={() => handleGenerate({ randomness: "高差异" }, "任务已提交：高差异版本")}
                  disabled={!canGenerate || status === "running"}
                  title="提高模块排序和内容组织的差异化程度"
                >
                  <Sparkles size={16} />
                  <span>高差异版</span>
                </button>
                <button
                  type="button"
                  onClick={() =>
                    handleGenerate(
                      { seed: result?.seed, randomness: result?.randomness || form.randomness },
                      "任务已提交：复现本次版本"
                    )
                  }
                  disabled={!canGenerate || status === "running" || !result?.seed}
                  title="沿用本次 seed 复现同一版输出"
                >
                  <FileCheck2 size={16} />
                  <span>复现本次</span>
                </button>
              </div>
            </details>

            <details className="secondary-panel">
              <summary>
                <ListChecks size={16} />
                <span>结果明细</span>
              </summary>
              <div className="secondary-body">
                {qualityItems.length > 0 && (
                  <div className="quality-list compact">
                    {qualityItems.map((item) => (
                      <div className={`quality-item ${item.state}`} key={item.label}>
                        <span className="quality-state">{qualityIcon(item.state)}</span>
                        <div>
                          <strong>{item.label}</strong>
                          <p>{item.value}</p>
                          {item.detail && <small>{item.detail}</small>}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                <div className="output-list">
                  {generatedFiles.length ? (
                    generatedFiles.slice(0, 8).map((file) => (
                      <button
                        className="file-row"
                        key={file.path || file.name}
                        type="button"
                        title={bridgeAvailable ? file.path : "Electron 中可打开文件"}
                        disabled={!bridgeAvailable}
                        onClick={() => openGeneratedFile(file)}
                      >
                        {file.icon}
                        <span>{file.name}</span>
                      </button>
                    ))
                  ) : (
                    <>
                      <div>
                        <FileText size={16} />
                        <span>软件说明书 docx/pdf</span>
                      </div>
                      <div>
                        <Code2 size={16} />
                        <span>源码鉴别材料 docx/pdf</span>
                      </div>
                      <div>
                        <Archive size={16} />
                        <span>信息表、材料清单、源码工程</span>
                      </div>
                    </>
                  )}
                </div>
              </div>
            </details>

            <details className="secondary-panel">
              <summary>
                <TerminalSquare size={16} />
                <span>运行日志</span>
              </summary>
              <pre className="log-view">
                {events.map((event) => `[${event.progress || 0}%] ${event.message}`).join("\n") ||
                  [result?.stdout, result?.stderr].filter(Boolean).join("\n") ||
                  buildCommandPreview(form)}
              </pre>
            </details>
          </aside>
        </div>
      </section>
    </main>
  );
}

function statusLabel(status) {
  if (status === "running") return "正在生成";
  if (status === "success") return "材料包已完成";
  if (status === "error") return "生成失败";
  return "等待生成";
}

function statusText(status, bridgeAvailable) {
  if (!bridgeAvailable) return "当前是浏览器预览模式，Electron 中会调用本地 Python 生成器。";
  if (status === "running") return "正在生成源码工程、说明书、源码材料、PDF 和 zip。";
  if (status === "success") return "已输出完整材料包，可打开 zip 或输出目录查看。";
  if (status === "error") return "生成任务异常，请展开日志定位问题。";
  return "填写首页参数后直接生成，无需进入多步骤向导。";
}

function buildCommandPreview(form) {
  return [
    "python backend\\generate_materials.py",
    `  --name "${form.name}"`,
    `  --version ${form.version}`,
    `  --language ${form.language}`,
    `  --product-type ${form.productType}`,
    `  --feature-hint "${form.featureHint}"`,
    `  --model-plan ${form.modelPlan}`,
    `  --model-provider ${form.modelProvider}`,
    `  --model-name ${form.modelName}`
  ].join(" `\n");
}

function currentEvent(events) {
  return events.length ? events[events.length - 1] : null;
}

function buildQualityItems(result) {
  if (!result?.checks) return [];
  const checks = result.checks;
  const warnings = result.warnings || [];
  const files = result.files || [];
  const pdfCount = files.filter((file) => String(file).toLowerCase().endsWith(".pdf")).length;
  const docxCount = files.filter((file) => String(file).toLowerCase().endsWith(".docx")).length;
  const sourceLines = Number(checks.source_total_lines || 0);
  const sourcePages = Number(checks.source_total_pages || 0);
  const selectedPages = Number(checks.source_selected_pages || 0);
  const fullSelection = checks.selection_mode === "all";
  const consistencyReady = checks.material_consistency_ready;
  const consistencyDetail = materialConsistencyDetail(checks);

  return [
    {
      label: "源码行数",
      value: `${sourceLines} 行`,
      detail: "目标不少于 3000 行",
      state: checks.source_line_target_met ? "pass" : "fail"
    },
    {
      label: "源码材料页数",
      value: selectedPages ? `${selectedPages} 页` : "未生成",
      detail: fullSelection ? "源码不足 60 页时使用全部源码页" : "按前 30 页 + 后 30 页规则整理",
      state: selectedPages >= 60 || (fullSelection && selectedPages > 0) ? "pass" : "warn"
    },
    {
      label: "源码总页数",
      value: sourcePages ? `${sourcePages} 页` : "未统计",
      detail: "用于判断源码鉴别材料抽取范围",
      state: sourcePages >= selectedPages && sourcePages > 0 ? "pass" : "warn"
    },
    {
      label: "PDF 转换",
      value: pdfCount ? `${pdfCount} 个 PDF` : "未发现 PDF",
      detail: docxCount ? `已生成 ${docxCount} 个 Word 文档` : "请确认 python-docx 与 LibreOffice 状态",
      state: pdfCount > 0 ? "pass" : "warn"
    },
    {
      label: "材料打包",
      value: result.zipPath ? "ZIP 已生成" : "未生成 ZIP",
      detail: result.zipPath || "",
      state: result.ok && result.zipPath ? "pass" : "fail"
    },
    {
      label: "内容一致性",
      value: checks.software_name_consistent && checks.version_consistent ? "软件名与版本一致" : "需要复核",
      detail: `蓝图：${sourceLabel(result.blueprintSource)}；说明书：${sourceLabel(result.manualSource)}`,
      state: checks.software_name_consistent && checks.version_consistent ? "pass" : "warn"
    },
    {
      label: "产品方案一致性",
      value: consistencyReady ? "说明书/截图/源码已匹配" : "需要复核材料同源性",
      detail: consistencyDetail,
      state: consistencyReady ? "pass" : "warn"
    },
    {
      label: "生成警告",
      value: warnings.length ? `${warnings.length} 条警告` : "无警告",
      detail: warnings[0] || "生成链路未返回异常提示",
      state: warnings.length ? "warn" : "pass"
    }
  ];
}

function materialConsistencyDetail(checks) {
  if (!Object.prototype.hasOwnProperty.call(checks, "material_consistency_ready")) {
    return "本次报告未返回材料一致性检查";
  }
  const moduleHits = Number(checks.material_module_title_hits || 0);
  const objectHits = Number(checks.material_business_object_hits || 0);
  const metricHits = Number(checks.material_metric_hits || 0);
  const sourceHits = Number(checks.material_source_module_key_hits || 0);
  const manualSource = checks.material_manual_text_source || "unknown";
  const uiSource = checks.material_ui_text_source || "unknown";
  return `模块 ${moduleHits}；对象 ${objectHits}；指标 ${metricHits}；源码 ${sourceHits}；说明书 ${materialSourceLabel(manualSource)}；截图 ${sourceLabel(uiSource)}`;
}

function materialSourceLabel(source) {
  if (source === "llm-content") return "模型正文";
  if (source === "local-template-derived") return "模板派生";
  return sourceLabel(source);
}

function buildGeneratedFiles(result) {
  if (!result) return [];
  const items = [];
  if (result.zipPath) {
    items.push({ name: fileName(result.zipPath), path: result.zipPath, icon: <Archive size={16} /> });
  }
  for (const path of result.files || []) {
    items.push({
      name: fileName(path),
      path,
      icon: fileIcon(path)
    });
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

function sourceLabel(source) {
  if (source === "llm") return "模型生成";
  return "本地模板";
}

function balanceHint(account) {
  if (account.status === "refreshing") return "余额正在刷新...";
  if (account.status === "loading") return "正在读取余额...";
  if (account.status === "connected") return `余额更新时间：${account.updatedAt || "刚刚"}`;
  if (account.status === "error") return account.message || "余额接口读取失败，请检查中转站配置。";
  if (account.status === "local") return "当前未连接中转站，生成时会自动回退本地模板。";
  return "余额与扣费由服务端中转站管理。";
}

createRoot(document.getElementById("root")).render(<App />);
