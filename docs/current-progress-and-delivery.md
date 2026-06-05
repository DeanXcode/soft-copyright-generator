# 当前进度与交付说明

更新日期：2026-06-05

## 当前状态

本项目已经完成软著材料一键生成桌面工具的本地可运行原型，支持在首页填写软件名称、版本、源码语言、软件类型和业务补充后，一键生成材料包。

已完成能力：

- 生成真实源码工程目录，而不是直接拼接 Word 代码页。
- 从源码工程提取源码鉴别材料。
- 生成软件说明书、源码材料、信息表、材料清单和生成报告。
- 生成 Word、PDF 和 ZIP 材料包。
- 支持 Java、JavaScript、Python、PHP、C#、C++、HTML 等语言入口。
- 支持 15 类产品类型。
- 支持模型生成产品蓝图，并在模型失败时回退本地模板。
- Electron 桌面端首页已简化，核心输入在首页，高级项折叠。
- 高级设置仅展示 GPT 模型套餐和余额，客户界面不暴露 API 配置。
- 支持隐藏配置文件 `config/production.json`。
- 支持 OpenAI-compatible / NewAPI 网关。
- 支持 NewAPI `/api/usage/token` 余额读取。
- 生成完成后自动刷新余额。

## 真实 NewAPI 接入状态

线上业务后台地址：

```text
https://smoke2.learn-flow.cn/
```

当前确认该地址已提供 NewAPI / OpenAI-compatible 接口：

```text
https://smoke2.learn-flow.cn/v1
```

已在 NewAPI 中创建桌面工具专用 token：

```text
softcopyright-desktop
```

安全说明：

- token 已写入本机 `config/production.json`。
- `config/production.json` 已加入 `.gitignore`，不会提交到 GitHub。
- GitHub 只提交 `config/production.example.json` 模板。
- 线上 NewAPI 数据库在创建 token 前已备份：

```text
/home/ubuntu/cipher-customer-smoke2/backups/one-api-before-softcopyright-20260605-213447.db
```

真实接口验证结果：

- `/v1/models` 可正常返回模型列表。
- `/v1/chat/completions` 可正常调用。
- `/api/usage/token` 可正常读取 token 额度。
- 测试调用后额度从 `1,000,000` 变为 `999,955`，说明扣费链路有效。

## 本机交付配置

推荐交付时复制模板：

```powershell
Copy-Item config\production.example.json config\production.json
```

然后填入真实 NewAPI token：

```json
{
  "SOFT_ACCOUNT_PROVIDER": "newapi",
  "SOFT_MODEL_GPT_BASE_URL": "https://smoke2.learn-flow.cn/v1",
  "SOFT_MODEL_GPT_API_KEY": "sk-你的NewAPI调用Token",
  "SOFT_MODEL_GPT_NAME": "gpt-5.4"
}
```

客户界面只看到 GPT 和余额，不看到 API Base URL 和 API Key。

## 启动方式

首次安装依赖：

```powershell
python -m pip install -r requirements.txt
npm install
```

启动桌面端：

```powershell
npm run build
npm run electron
```

也可以双击：

```text
start-desktop.bat
```

注意不要直接双击 `node_modules\electron\dist\electron.exe`，那会打开 Electron 默认欢迎页。

## 验证记录

本阶段已验证：

- `npm run build` 通过。
- `node --check desktop\electron\main.cjs` 通过。
- 真实 NewAPI `/v1/chat/completions` 调用成功。
- 真实 NewAPI `/api/usage/token` 余额读取成功。
- 真实 NewAPI 完整材料生成命令已跑通。

完整生成样例：

```text
景区票务与门禁智能管理系统-real-newapi-002--材料包.zip
```

生成检查摘要：

```text
blueprint_source: llm
manual_source: local-template
source_total_lines: 3458
source_total_pages: 70
source_selected_pages: 60
source_line_target_met: true
```

说明：产品蓝图已由真实模型生成；说明书正文模型请求出现一次 `504 Gateway Time-out`，系统按设计回退本地模板，材料包仍正常输出。

## 已知问题

1. 说明书正文一次性模型请求偏大，真实 NewAPI 可能返回 `504 Gateway Time-out`。
2. Windows PowerShell inline / pipeline 传中文参数时可能把中文变成 `????`，长验证命令应使用 UTF-8 文件、JSON 配置、Node/Python 内部构造 Unicode 字符串，或使用 `\u...` 转义。
3. 当前还没有 Windows 安装包，仍以源码目录运行。
4. 客户登录、充值、激活码绑定还没有产品化，目前通过 NewAPI token 配置实现。

## 下一步建议

优先级从高到低：

1. 拆分说明书正文模型生成，把一次大请求拆成概述、模块、统计、安全、FAQ 等小请求，解决 504。
2. 做桌面端真实配置下的 UI 验收，确认余额显示、生成按钮、输出目录打开体验。
3. 增加激活码或登录绑定流程，让客户 token 由你的后台下发，不再手工写 `config/production.json`。
4. 使用 `electron-builder` 打包 Windows 安装包。
5. 增加生成历史和客户任务记录，方便补正和重新生成。
