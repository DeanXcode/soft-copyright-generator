# DeepSeek 真实接口验证

日期：2026-11-14

本次读取用户指定的 DP.txt，以隔离进程配置调用现有 OpenAI-compatible provider。项目原本已包含 DeepSeek provider 和桌面配置项，无需修改软件代码或覆盖现有 API 配置。

## 结果

- 网关模型列表接口返回 HTTP 200，列出 `deepseek-v4-1-flash-260910` 和 `deepseek-v4.1-flash`。
- 首次以 `deepseek-chat` 请求得到 HTTP 404，网关错误说明该账户组未开放此模型。该结果表示模型路由不匹配，不能据此判定 API 密钥无效。
- 改用列表中的 `deepseek-v4.1-flash` 后，最小真实文本请求 **5.61 秒**成功，并准确返回约定文本。
- DeepSeek provider 预设适配器单测通过。项目没有需要新增的渠道实现。

## 整单成功率状态

渠道分工已确认：文本由 DeepSeek 生成，参考图片继续使用现有 GPT 图片 API；项目现有配置支持两条渠道独立。由于本轮配置检查的工具输出意外包含 GPT 图片 API 凭据，暂停调用该凭据，因此没有使用 DeepSeek 跑完整生成。已有上一轮三类首次整单历史为 **1/3**，不可与本次单条文本请求混为一谈。

检查图片渠道配置时，工具输出意外包含了本机图片 API 凭据。因此暂停依赖该图片渠道的整单测试，并建议立即轮换该凭据；恢复整单回归前，在忽略的本地配置中更新轮换后的值并先做图片冒烟测试。DeepSeek API token 未写入配置文件、trace 或报告；本报告不包含任何密钥或完整请求地址。

脱敏证据：`tmp/deepseek-api-smoke.json`、`tmp/deepseek-model-catalog.json`、`tmp/deepseek-api-smoke-trace.jsonl`。没有修改 API 文件，没有更新安装包。

## 下一阶段建议

1. 轮换图片 API 凭据，更新本地配置并验证图片渠道。
2. 再以隔离的 DeepSeek V4 Flash 文本配置跑同一组三类全新整单，记录首次成功率及图片/文本渠道边界。
