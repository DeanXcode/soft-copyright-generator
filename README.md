# 软著材料一键生成桌面工具原型

当前仓库已完成 M1 命令行生成闭环原型：输入软件名称、版本号、编程语言、产品类型和业务提示后，生成源码工程、软件说明书、源码鉴别材料、信息表、材料清单和 zip 材料包。

当前工作进度、真实 NewAPI 接入状态、交付配置方式和下一步建议见：

- [当前进度与交付说明](docs/current-progress-and-delivery.md)

当前开发版本：`0.2.0`。

## 安装依赖

```powershell
python -m pip install --require-hashes -r requirements-lock.txt
```

## 生成样例

```powershell
python backend\generate_materials.py `
  --name "景区票务与门禁智能管理系统" `
  --version V1.0 `
  --language Java `
  --product-type 智慧城市软件 `
  --feature-hint "景区票务、闸机核验、团队订单、年卡管理"
```

输出位于 `output/` 目录，生成完成后会打印 zip 路径。

## 首页原型

前端首页已经放在 `desktop/src/`，可用浏览器预览：

```powershell
npm install
npm run dev -- --port 5173
```

打开：

```text
http://127.0.0.1:5173
```

Electron 壳代码位于 `desktop/electron/`。如果 Electron 二进制已下载完成，可运行：

```powershell
npm run build
npm run electron
```

若安装 Electron 时出现网络中断，可重新执行：

```powershell
npm install electron@^39.2.7 --save
```

如果 GitHub 下载 Electron 二进制超时，可使用镜像源重建：

```powershell
$env:ELECTRON_MIRROR="https://npmmirror.com/mirrors/electron/"
npm rebuild electron
```

注意不要直接双击 `node_modules\electron\dist\electron.exe`。那样会打开 Electron 默认欢迎页。请从项目根目录运行：

```powershell
npm run build
npm run electron
```

或者直接双击：

```text
start-desktop.bat
```

## 模型配置

桌面端支持 OpenAI-compatible / NewAPI、Grok（xAI）、Claude（Anthropic）、Gemini（Google）和 DeepSeek 文本供应商。生成流程会完成名称理解、产品蓝图、技术架构选择、说明书正文和界面蓝图生成；任一关键文本阶段失败都会明确提示重试，不再静默切换到默认模板。`Default Template` 是显式选择的零 Token 模式。

从 `0.2.0` 开始，标准后台、移动端和常规操作页默认由模型返回 `page-spec-v1` 结构化页面规范，本地 `PageRenderer` 负责生成 React DOM 与受控 CSS。地图页继续使用 PageSpec；游戏、三维和虚拟仿真等组件库暂时无法表达的页面逐页使用 legacy React fallback。页面缓存写入 `*.page-spec.json` 与 `*.meta.json`，材料内部清单包含 PageSpec schema 和组件库版本，但不会写入客户可见说明书正文。

升级后恢复旧失败任务时会保留产品蓝图、技术架构、说明书内容、源码和 image2 参考图，并从界面阶段重新生成全部页面；已经完成的历史材料包和 ZIP 不会自动迁移或重建。

客户交付版安装包可预置请求地址、模型名称和 API Key。请求地址与已保存 Key 采用只写不回显：高级设置只显示配置状态，只有主动输入新值并保存时才会替换。图片模型可以复用文本 API，也可以使用独立的图片请求地址、API Key 和模型 ID；正式 image2 流程失败时不会使用模板图或静态图兜底。

生成客户交付版安装包：

```powershell
npm run pack:win:customer
```

该命令会从本机忽略文件 `config\production.json` 读取真实配置，临时写入 `build\customer-config\production.json`，并将其打入安装包的 `resources\config\production.json`。临时目录 `build/` 已加入 `.gitignore`，不要提交真实 token。

本机真实配置示例：

```json
{
  "SOFT_ACCOUNT_PROVIDER": "newapi",
  "SOFT_MODEL_GPT_BASE_URL": "https://smoke2.learn-flow.cn/v1",
  "SOFT_MODEL_GPT_API_KEY": "sk-你的NewAPI调用Token",
  "SOFT_MODEL_GPT_NAME": "gpt-5.5",
  "SOFT_MODEL_GPT_IMAGE_NAME": "gpt-image-2",
  "SOFT_MODEL_GPT_OUTLINE_NAME": "gpt-5.5",
  "SOFT_MODEL_GPT_OUTLINE_TIMEOUT_SECONDS": "60",
  "SOFT_LLM_IMAGE_RETRY_COUNT": "3",
  "SOFT_MODEL_MODE": "gpt"
}
```

`config\production.json` 已加入 `.gitignore`，不要提交真实 token。
`SOFT_MODEL_GPT_NAME` 用于正式材料生成，`SOFT_MODEL_GPT_OUTLINE_NAME` 用于桌面端“生成蓝图”阶段，`SOFT_MODEL_GPT_IMAGE_NAME` 用于界面视觉参考稿阶段，当前应配置为 `gpt-image-2`。`SOFT_LLM_IMAGE_RETRY_COUNT` 是图片生成专用重试次数，用来处理图片网关临时 503/504/524/429；重试后仍失败时会保留蓝图并停止，不使用模板或中间图兜底。为了保证蓝图和正式内容的语义质量一致，建议文本生成模型保持同一个高质量模型。

如果不是客户预制安装包，也可以由实施人员把真实配置放在安装目录或 exe 同级目录下的 `config\production.json`：

```text
软件安装目录/
  soft-copyright-generator.exe
  config/
    production.json
```

也可以通过环境变量指定外部配置目录：

```powershell
$env:SOFT_DESKTOP_CONFIG_DIR="D:\SoftCopyrightConfig"
```

程序会优先读取 `SOFT_DESKTOP_CONFIG_DIR` 指向目录中的 `production.json` / `desktop.local.json`，其次读取安装包资源目录内的预置配置，再读取用户配置和 exe 同级 `config` 目录。不要把真实 key 写入 `production.example.json`，它只作为模板提交到仓库。

也可以临时使用环境变量：

```powershell
$env:SOFT_MODEL_GPT_BASE_URL="https://your-newapi.example.com/v1"
$env:SOFT_MODEL_GPT_API_KEY="你的NEWAPI_KEY"
$env:SOFT_MODEL_GPT_NAME="gpt-5.5"
$env:SOFT_MODEL_GPT_IMAGE_NAME="gpt-image-2"
$env:SOFT_MODEL_GPT_OUTLINE_NAME="gpt-5.5"
$env:SOFT_MODEL_GPT_OUTLINE_TIMEOUT_SECONDS="60"
$env:SOFT_LLM_IMAGE_RETRY_COUNT="3"
$env:SOFT_MODEL_BALANCE_LABEL="100000 tokens"
$env:SOFT_MODEL_ACCOUNT_NAME="客户账户"
npm run build
npm run electron
```

也可以使用通用网关变量：

```powershell
$env:SOFT_MODEL_GATEWAY_BASE_URL="https://your-newapi.example.com/v1"
$env:SOFT_MODEL_GATEWAY_API_KEY="你的NEWAPI_KEY"
$env:SOFT_MODEL_GATEWAY_MODEL="gpt-5.5"
$env:SOFT_MODEL_GATEWAY_IMAGE_MODEL="gpt-image-2"
```

当前模型会参与“名称理解、产品蓝图、技术架构选择、说明书正文、界面蓝图、全局视觉风格提示词、gpt-image-2 风格参考图、按图生成业务工程和按图生成界面代码”生成。正式 GPT 流程只生成 1 张全局风格参考图，随后根据参考图生成业务工程源码与运行接口，再按参考图生成全部可运行 HTML/CSS，最后启动生成项目服务重新截图并写入手册；失败会明确提示重试，不使用模板或中间图片兜底。

## 业务后台余额接口

如果 `SOFT_ACCOUNT_PROVIDER` 设置为 `newapi`，桌面端会根据 `SOFT_MODEL_GPT_BASE_URL` 自动读取 NewAPI 额度接口：

```http
GET /api/usage/token/
Authorization: Bearer sk-你的NewAPI调用Token
```

兼容的 NewAPI 返回格式示例：

```json
{
  "code": true,
  "message": "ok",
  "data": {
    "name": "softcopyright-desktop",
    "total_available": 999955,
    "total_used": 45,
    "unlimited_quota": false
  }
}
```

桌面端会优先读取 NewAPI 余额接口。若需要使用业务后台自定义余额接口，也可以配置：

```powershell
$env:SOFT_ACCOUNT_API_BASE_URL="https://your-domain.com"
$env:SOFT_ACCOUNT_AUTH_TOKEN="客户授权Token"
```

默认请求：

```http
GET /api/v1/account/balance
Authorization: Bearer 客户授权Token
```

接口返回示例：

```json
{
  "ok": true,
  "accountName": "某某客户",
  "balanceTokens": 100000,
  "balanceLabel": "100,000 tokens",
  "expiresAt": "2026-12-31"
}
```

也可以直接指定完整余额接口地址：

```powershell
$env:SOFT_ACCOUNT_BALANCE_URL="https://your-domain.com/api/v1/account/balance"
```

本地 mock 业务后台网关同时提供余额接口和 OpenAI-compatible 生成接口：

```powershell
$env:MOCK_ACCOUNT_TOKEN="demo-token"
npm run mock:gateway
```

mock 网关会按请求内容估算 token 消耗，并在余额接口中模拟扣减。

另开一个终端启动桌面端：

```powershell
$env:SOFT_ACCOUNT_API_BASE_URL="http://127.0.0.1:8787"
$env:SOFT_ACCOUNT_AUTH_TOKEN="demo-token"
$env:SOFT_MODEL_GPT_BASE_URL="http://127.0.0.1:8787/v1"
$env:SOFT_MODEL_GPT_API_KEY="demo-token"
$env:SOFT_MODEL_GPT_NAME="mock-gpt"
npm run build
npm run electron
```

## 当前能力

- 生成真实源码工程目录。
- Java 默认生成 Controller、Service、Repository、DTO、Domain、XML Mapper、审计、统计、导入导出、校验和 SQL 脚本。
- C# 默认生成 ASP.NET Core 风格工程，包含 Controller、Service、Repository、Model、Query、统计、审计、导出和操作追踪等源码文件，可满足 3000+ 行源码鉴别材料目标。
- 自动提取源码生成源码鉴别材料。
- 超过 60 页时采用前 30 页 + 后 30 页。
- 生成软件说明书、源码文档、申请信息表和最终 zip 材料包。
- 自动生成登录页、系统首页、功能模块页和统计页界面截图，并插入软件说明书。
- GPT 模式下优先由模型生成 `ui_blueprint.json`，本地再强校验截图渲染器和视图类型，保证游戏软件生成手机 9:16 竖屏的关卡、棋盘、道具、结算等游戏截图，非游戏软件不混入游戏界面。
- 非游戏软件截图已按 APP、教育、金融、医疗、GIS、云计算、信息安全、大数据、人工智能、VR、5G、小程序、物联网、智慧城市等类型配置行业指标、业务对象、状态和流程面板。
- 截图 HTML 已并入生成源码项目的 `generated_source/ui-prototype/`，并自动生成 `index.html`、`README.md` 和 `prototype-manifest.json`，便于直接浏览和验收每张界面原型。
- 生成源码项目已补齐第一版可启动前端入口：Java/Spring Boot 会同步到 `src/main/resources/static/ui-prototype/`，C#/ASP.NET Core 会同步到 `wwwroot/ui-prototype/`，JavaScript/Python 项目会通过本地静态路由暴露 `/ui-prototype/index.html`。
- 桌面端仅展示 GPT 套餐；底层可通过 NewAPI / OpenAI-compatible 中转站接入真实模型。
- 已支持 LibreOffice 高保真 PDF 转换；未检测到 LibreOffice 时会自动生成简版 PDF 占位文件。

## 界面截图

程序会为说明书生成业务相关界面图：

- 登录界面
- 系统首页
- 功能模块页面
- 统计报表界面

正式 GPT 流程会先生成 `ui_blueprint.json` 和页面清单，再生成 1 张 gpt-image-2 全局视觉风格参考图；参考图成功后才生成业务工程源码、运行接口和 `ui-visual-reference-contract.json`，随后 GPT 根据同一张参考图为全部页面生成可运行 HTML/CSS，最后启动生成源码项目服务并由 Playwright/Chromium 对运行页面重新截图。正式 GPT 模式在参考图生成前只会建立页面清单和文件名，不提前写入业务工程源码或占位界面 HTML/CSS；业务工程和界面代码都必须在全局风格参考图之后落地。桌面软件输出 1280×720 的 16:9 横向截图；手机 APP、小程序和手机游戏输出 720×1280 的 9:16 竖屏截图，并按产品类型、体验形态和视觉身份规格拉开界面差异。`local-template` 仅作为显式开发/无 token 模式保留；正式 GPT 模式下全局风格参考图、按图生成页面或项目服务截图任一缺失都会失败，不使用模板或中间图片兜底。截图 PNG 会保存在输出目录的 `ui_screenshots/` 中；对应 HTML、原型入口、蓝图、视觉参考图和清单会保存在源码工程的 `generated_source/ui-prototype/` 中，作为内部生成过程文件保留；最终 zip 只包含客户交付所需的 5 个文件，不包含截图源文件、源码工程、生成报告或材料清单。

快速验收截图链路可以只生成源码项目、UI 原型和 PNG，不生成 Word/PDF，也不打包：

```powershell
.\python-runtime\python.exe scripts\run_screenshot_chain_review.py --output-root output-screenshot-chain-local-review
```

含中文任务时建议使用 UTF-8 JSON 文件传参，避免 PowerShell 把中文参数转成 `????`：

```json
{
  "software_name": "星糖岛消除冒险",
  "version": "V1.0",
  "language": "C#",
  "product_type": "游戏软件",
  "feature_hint": "三消关卡、糖果棋盘、步数目标、道具背包、星级结算",
  "model_provider": "custom",
  "output_root": "output-screenshot-chain-local-review"
}
```

```powershell
.\python-runtime\python.exe scripts\run_screenshot_chain_review.py --task-file .\your-task.json
```

脚本会输出 `screenshot_chain_report.json`，重点检查 `ui_screenshot_count`、`ui_software_type_match`、`ui_mobile_portrait_match` / `ui_admin_desktop_match`、`prototype_index_exists`、`ui_project_entry_exists`、`ui_project_served_index_exists` 和 `material_consistency_ready`。

生成后的源码工程会包含 `UI_PROTOTYPE_ENTRY.md`。Java 项目可通过 `mvn spring-boot:run` 访问：

```text
http://127.0.0.1:8080/ui-prototype/index.html
```

C# 项目可通过以下命令访问：

```powershell
dotnet run --urls http://127.0.0.1:5000
```

```text
http://127.0.0.1:5000/ui-prototype/index.html
```

内部验收 C# 项目真实服务截图时，可让脚本启动生成项目后从 HTTP URL 截图：

```powershell
.\python-runtime\python.exe scripts\run_screenshot_chain_review.py --task-file .\your-csharp-task.json --project-server
```

报告中 `ui_screenshot_render_mode` 为 `project-server` 时，表示截图来自生成项目服务 URL；启动失败时会回退本地文件截图并写入 warning。

最终 zip 只包含：

- `软件名称.docx`
- `软件名称.pdf`
- `软件名称.txt`
- `软件名称_代码-(语言).docx`
- `软件名称_代码-(语言).pdf`

## 真实性与规范性校验

每次完整生成都会额外输出内部校验报告：

```text
输出目录/generation_report.json
输出目录/validation_report.json
输出目录/materials_manifest.json
```

`validation_report.json` 不进入最终客户 ZIP，只作为交付前验收和问题诊断材料。报告会记录源码文件清单、每个源码文件的 SHA-256、产品蓝图 hash、交付文件 hash、ZIP 文件条目、占位符/乱码扫描、第三方源码目录风险，以及说明书、源码、截图、信息表之间的业务命中情况。
`materials_manifest.json` 同样是内部证据链文件，不进入最终客户 ZIP。它会记录软件名、版本、语言、产品类型、seed、生成模式、产品蓝图 hash、源码文件清单/行数/hash、源码鉴别材料每页对应的真实源码文件和行号范围、说明书引用映射、PDF 转换信息，以及不含 API Key 的 LLM trace 摘要。

核心检查字段会同步写入 `generation_report.json` 的 `checks`：

- `authenticity_score` / `authenticity_ready`
- `normative_score` / `normative_ready`
- `validation_ready_for_delivery`
- `validation_finding_count`
- `validation_source_hash`
- `validation_zip_entries_match_deliverables`
- `validation_placeholder_hit_count`

其中规范性校验会把源码有效行数低于 3000、ZIP 内容偏离 5 文件白名单、材料中出现占位符或乱码标记视为交付前必须处理的问题。

桌面端生成完成后，`结果明细` 会展示真实性评分、规范性评分和交付建议，并提供 `validation_report.json` 与 `materials_manifest.json` 的打开入口，便于实施人员查看完整校验证据链。

GPT 生成默认采用“真实性优先”流水线，优先保证材料可申请性而不是速度：

- 当业务补充为空，或业务补充与软件名称识别出的领域明显不匹配时，系统会先调用 GPT 根据软件名称生成业务说明、关键词和应避免方向；GPT 不可用时才回退本地规则。例如“阅读听书软件”会自动补充书城浏览、书架管理、有声听书、章节目录、听书播放、阅读进度、收藏订阅、会员权益等关键词。桌面端“按名称自动匹配”按钮也会优先调用 GPT，不再只依赖本地关键词表。
- 产品蓝图默认质量目标为 `92` 分，最多尝试 5 轮；可通过 `SOFT_BLUEPRINT_QUALITY_FLOOR` 调整目标分。
- 功能模块默认逐个生成、逐个校验，模块 key、标题、描述、操作、字段、规则过于泛化时会触发单模块修复。
- 说明书正文默认逐章、逐模块生成，避免一次性上下文过大导致正文变成通用模板。
- 截图蓝图默认逐页生成，进度会显示登录页、首页、各模块页和统计页设计图阶段。
- `generation_report.json` 的 `checks.generation_quality_profile` 会记录本次策略；默认不为 token 成本牺牲蓝图、说明书、源码和截图的一致性。

安装包交付会内置 Playwright Chromium Headless Shell，避免客户机器首次运行时下载浏览器：

```powershell
python -m pip install -r requirements.txt
npm install
npm run prepare:runtime
```

该命令会把浏览器运行时下载到项目根目录的 `ms-playwright/`，并准备内置 Python 运行时 `python-runtime/`。这两个目录不提交到 Git，但打包 Windows 安装包时会作为额外资源复制到安装包资源目录：

```text
软件安装目录/
  soft-copyright-generator.exe
  resources/
    ms-playwright/
      chromium_headless_shell-*/
    python-runtime/
      python.exe
```

桌面端启动生成任务时会优先使用内置 `python-runtime/python.exe`，并自动设置 `PLAYWRIGHT_BROWSERS_PATH` 指向内置 `ms-playwright/`，客户机器无需单独安装 Python 或 Chromium。

## LibreOffice

客户预制安装器会内置 LibreOffice 运行时，客户机器不需要单独安装 LibreOffice。构建客户包前可用以下命令把本机 LibreOffice 复制到项目根目录的 `libreoffice/`：

```powershell
npm run prepare:libreoffice
```

客户版安装包会把该目录复制到：

```text
resources/libreoffice/program/soffice.exe
```

PDF 转换探测优先级：

```text
1. SOFT_LIBREOFFICE_PATH
2. 安装包内置 resources/libreoffice/program/soffice.exe
3. 系统安装路径 C:\Program Files\LibreOffice\program\soffice.exe
4. PATH 中的 soffice/libreoffice
5. 简版 PDF 兜底
```

## Windows 便携交付包

当前提供便携 zip 打包脚本：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\package-windows-portable.ps1 -Version 0.2.0
```

输出：

```text
release/soft-copyright-generator-0.2.0-portable.zip
```

包内包含：

- 前端构建产物 `dist/`
- Electron 主进程和界面源码 `desktop/`
- Python 后端 `backend/`
- 配置模板 `config/production.example.json`
- Playwright Chromium Headless Shell 运行时 `ms-playwright/`
- Python embeddable runtime `python-runtime/`

便携包默认不会包含本机真实配置 `config/production.json` 或 `config/desktop.local.json`，主要用于开发验收和备用交付。当前客户正式交付优先使用下方客户预制 NSIS 安装器。

## Windows 安装器

当前已接入 `electron-builder`，普通安装器可用：

```powershell
npm run prepare:runtime
npm run pack:win
```

输出：

```text
release/installer/Soft Copyright Generator Setup 0.2.0.exe
release/installer/win-unpacked/
```

安装器包含 Electron 应用、Python 后端文件、配置模板、`ms-playwright/` 和 `python-runtime/`。安装器不会包含真实本机配置，客户机器无需单独安装 Python、pip、项目 Python 包或 Chromium。

客户预制安装器使用：

```powershell
npm run pack:win:customer
```

输出：

```text
release/customer-installer/Soft Copyright Generator Setup 0.2.0.exe
release/customer-installer/win-unpacked/
```

客户预制安装器会把本机 `config/production.json` 注入到安装包资源目录，并写入 `SOFT_MODEL_MODE=gpt` 和 `SOFT_CUSTOMER_PRESET_CONFIG=true`。同时会内置 LibreOffice 运行时。客户安装后可在界面高级设置里用只写方式替换请求地址和 API Key、修改模型名称，并可直接生成高保真 PDF。

构建客户安装器前会自动执行 `npm run verify:release`。Python 回归、核心模块编译、Electron 检查、Vite 构建、npm 安全审计、示例配置密钥扫描或安装包资源/版本一致性检查任一失败时都会停止打包。

## 后续开发

统一文本重试、自适应页面并发、状态恢复和混合 PageSpec 页面引擎已在 `0.1.11` / `0.2.0` 落地。下一阶段重点是使用同一供应商、同一 35 页样本完成耗时基准对比，在干净 Windows 用户或快照环境验证最终 NSIS 安装器，并继续扩大 PageSpec 在游戏、三维、嵌入式和少见行业页面上的组件覆盖。
