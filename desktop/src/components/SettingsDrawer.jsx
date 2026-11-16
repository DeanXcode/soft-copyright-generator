import React from "react";
import { Code2, FileText, Image as ImageIcon, Loader2, PackageCheck, RefreshCw, Save, SlidersHorizontal, Sparkles } from "lucide-react";
import { modelProviders, providerModelChoices, textProviderChoices } from "../modelOptions";

export default function SettingsDrawer({
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
  modelConfig = normalizeSettingsModelConfig(modelConfig);
  modelCatalog = normalizeSettingsModelCatalog(modelCatalog);
  const selectedTextProvider = textProviderChoices.find((item) => item.value === modelConfig.textProvider) || textProviderChoices[0];
  const providerFallbackModels = providerModelChoices[selectedTextProvider.value] || [selectedTextProvider.defaultModel];
  const availableModels = modelCatalog.models;
  const catalogModels = modelCatalog.provider === selectedTextProvider.value && availableModels.length
    ? availableModels
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

function normalizeSettingsModelConfig(value) {
  const source = value && typeof value === "object" ? value : {};
  return {
    ...source,
    mode: String(source.mode || "gpt"),
    textProvider: String(source.textProvider || "custom"),
    modelName: String(source.modelName || ""),
    outlineModelName: String(source.outlineModelName || ""),
    frontendModelName: String(source.frontendModelName || ""),
    frontendWorkers: String(source.frontendWorkers || "auto"),
    apiBaseUrl: String(source.apiBaseUrl || ""),
    apiKey: String(source.apiKey || ""),
    imageModelName: String(source.imageModelName || "gpt-image-2"),
    imageApiBaseUrl: String(source.imageApiBaseUrl || ""),
    imageApiKey: String(source.imageApiKey || "")
  };
}

function normalizeSettingsModelCatalog(value) {
  const source = value && typeof value === "object" ? value : {};
  return {
    ...source,
    status: String(source.status || "idle"),
    provider: String(source.provider || ""),
    models: Array.isArray(source.models) ? source.models.map((model) => String(model || "").trim()).filter(Boolean) : [],
    message: String(source.message || "")
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

function balanceHint(account) {
  if (account.status === "local") return account.message || "本地生成模式，不消耗 token";
  if (account.status === "connected") return account.updatedAt ? `更新于 ${account.updatedAt}` : "模型账户可用";
  if (account.status === "unconfigured") return account.message || "请先选择文本模型供应商并配置 API Key";
  if (account.status === "error") return account.message || "账户接口异常";
  return "保存文本模型配置后可读取账户状态";
}
