export const modelProviders = [
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

export const textProviderChoices = [
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
export const providerModelChoices = {
  custom: modelChoices,
  grok: ["grok-3-mini"],
  claude: ["claude-sonnet-4-20250514"],
  gemini: ["gemini-2.5-flash"],
  deepseek: ["deepseek-chat"]
};
