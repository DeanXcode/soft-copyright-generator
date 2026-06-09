# 当前进度与交付说明

更新日期：2026-06-07

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
- GPT 模式已升级为“产品方案优先”生成：先生成产品身份定位，再生成业务对象、流程、指标、规则和模块明细；说明书、源码工程、界面截图、信息表共享同一份产品方案，减少每次生成像同一套模板的问题。
- Electron 桌面端首页已简化，核心输入在首页，高级项折叠。
- 高级设置展示 GPT 模型套餐、余额、请求地址、模型名称和 API Key；客户预制安装包会预置配置，客户可在 UI 中查看和修改。
- 支持预置配置文件 `config/production.json`。
- 支持 OpenAI-compatible / NewAPI 网关。
- 支持 NewAPI `/api/usage/token` 余额读取。
- 生成完成后自动刷新余额。
- 说明书正文模型生成已拆分为概述、登录主界面、各功能模块、统计、安全、FAQ 等小请求，单个章节失败时由本地模板补齐，降低 NewAPI 大请求 `504 Gateway Time-out` 风险。
- GPT 生成默认策略已切换为质量优先：`SOFT_LLM_BATCH_WORKERS` 默认值为 `1`，按顺序生成产品方案、说明书和截图蓝图；仅在人工设置 `SOFT_LLM_BATCH_WORKERS=2/3` 时启用小批次并发加速。
- 桌面端已开放模型模式切换：`默认模板` 不消耗 token，`GPT` 使用预置配置。普通开发包和客户预制安装包均可在 UI 中查看和修改请求地址、模型名称和 API Key。
- C# 源码生成器已从通用短模板扩展为 ASP.NET Core 风格工程，可生成 Controller、Service、Repository、Model、Query、统计、审计、导出和操作追踪等多文件源码，并满足 3000+ 行源码鉴别材料目标。
- 已支持生成登录页、系统首页、功能模块页和统计页界面截图，并插入软件说明书；Playwright/Chromium 不可用时会使用本地图像渲染生成 PNG 兜底。
- GPT 模式下已支持由模型生成 `ui_blueprint.json`，并由本地强校验保证截图渲染器和 `view_type` 符合软件类型；例如游戏软件只能生成游戏登录、主界面、关卡、棋盘、道具、结算等游戏截图，不会混入后台管理表格页。
- GPT UI 蓝图已从单个长 JSON 请求拆分为“界面风格 + 分批截图内容”小请求，截图 key、renderer、view_type 由本地规则固定，GPT 只补标题、图注、组件和样例数据，降低 504 并减少界面跑偏。
- `generation_report.json` 已新增材料一致性检查，统计产品方案中的模块标题、业务对象、统计指标是否出现在说明书/截图文本中，并检查源码工程是否包含对应模块 key 和 `product-blueprint.json` 索引。
- 已增强 GPT 返回值清洗：当模型把 operations、data_fields、rules 等数组项返回为对象时，会抽取 `name`、`title`、`field`、`rule` 等字段，不再把结构化残片写进说明书或截图。
- 游戏软件截图已切换为手机游戏 9:16 竖屏画幅，输出尺寸为 720×1280；桌面管理类软件仍保持 1280×820 横向桌面画幅。报告会记录每张截图宽高，并增加 `ui_screenshot_aspect_ratio`、`ui_mobile_portrait_match` 检查项。
- 非游戏软件已补齐行业化后台截图画像，覆盖 APP、教育、金融、医疗、地理信息、云计算、信息安全、大数据、人工智能、VR、5G、小程序、物联网、智慧城市 14 类；每类截图会使用对应指标、筛选项、业务对象、状态标签、流程和趋势面板。
- 界面截图原型已并入生成源码项目：截图 HTML、`ui_blueprint.json`、`prototype-manifest.json`、`index.html` 和 `README.md` 会写入 `generated_source/ui-prototype/`，Playwright 从该目录渲染 PNG；PNG 仍输出到 `ui_screenshots/` 供说明书插图使用，最终 ZIP 仍只包含 5 个客户交付文件。
- 生成源码项目已补齐第一版可启动前端入口：Java/Spring Boot 项目会把原型同步到 `src/main/resources/static/ui-prototype/`，C#/ASP.NET Core 项目会同步到 `wwwroot/ui-prototype/`，JavaScript/Python 项目会通过本地静态路由暴露 `/ui-prototype/index.html`；报告会输出 `ui_project_entry_*` 检查项、入口 URL 和启动命令。
- 非游戏软件截图已从单一后台壳扩展为多种布局变体：金融/信息安全走 `risk` 风控控制台，地理信息/物联网/5G/智慧城市走 `map` 地图态势，大数据/人工智能/云计算/VR 走 `pipeline` 链路流程，教育/医疗/APP/小程序走 `workflow` 工单流程。生成报告会记录 `ui_layout_variant`，便于验收不同类型是否真正拉开。
- 已新增 Codex 项目 skill：`C:\Users\15527\.codex\skills\soft-copyright-generator\SKILL.md`。后续会话处理本项目时应同步进度文档、收尾给出下一阶段建议，并避免 PowerShell inline 中文参数导致乱码或 `????`。
- 已新增 Windows 便携交付包脚本 `scripts/package-windows-portable.ps1`，可输出包含 `dist/`、`backend/`、`desktop/`、配置模板、`ms-playwright/` 和 `python-runtime/` 的 zip 包；包内不包含本机真实 `production.json` / `desktop.local.json`。
- 已接入 `electron-builder` Windows NSIS 安装器，`npm run pack:win` 可输出普通安装器和 `win-unpacked` 目录；普通安装器包含 Electron 应用、后端文件、配置模板、`ms-playwright/` 和 `python-runtime/`，不包含真实本机配置。客户正式交付使用 `npm run pack:win:customer`，会从本机 `config/production.json` 注入预置 GPT 配置，并在 UI 中开放查看和修改。
- 已新增 Python embeddable runtime 准备脚本 `scripts/prepare-python-runtime.ps1`，默认准备 Python 3.12.10、pip 和 `requirements.txt` 依赖，并写入 `..\backend` 到 `python312._pth`，保证安装包内置 Python 能导入后端包。
- Electron 主进程已优先使用内置 `python-runtime/python.exe` 启动生成任务；未找到时才回退系统 `python`。

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

正式客户包会预置 API Key、模型名和请求地址，同时在 UI 高级设置中开放查看和修改。交付前先在本机忽略文件 `config\production.json` 写入真实 NewAPI 配置：

```json
{
  "SOFT_ACCOUNT_PROVIDER": "newapi",
  "SOFT_MODEL_GPT_BASE_URL": "https://smoke2.learn-flow.cn/v1",
  "SOFT_MODEL_GPT_API_KEY": "sk-你的NewAPI调用Token",
  "SOFT_MODEL_GPT_NAME": "gpt-5.5",
  "SOFT_MODEL_MODE": "gpt"
}
```

然后运行：

```powershell
npm run pack:win:customer
```

客户版安装包会把配置注入到安装包资源目录，并自动设置 `SOFT_CUSTOMER_PRESET_CONFIG=true`。客户界面会展示请求地址、模型名称和 API Key 输入框，支持查看和保存修改。

安装包交付时不要把真实 token 写入 `config/production.example.json`。该文件只作为模板提交到仓库。客户版构建过程中产生的 `build\customer-config\production.json` 属于临时文件，已被 `.gitignore` 忽略。

## 启动方式

首次安装依赖：

```powershell
python -m pip install -r requirements.txt
npm install
npm run prepare:runtime
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
- `python -m py_compile` 关键后端模块通过。
- 本地模板完整材料生成命令已跑通，可生成 Word、简版 PDF 兜底文件和 ZIP。
- 本地模板截图生成验收通过，`ui_screenshot_count: 8`，说明书已可插入界面 PNG。
- Playwright Chromium Headless Shell 已可下载到项目内 `ms-playwright/`，并通过 `PLAYWRIGHT_BROWSERS_PATH=ms-playwright` 验证内置浏览器截图，`ui_screenshot_count: 8`。
- `npm run prepare:python` 已验证通过，输出 `python-runtime/`，内置 Python 3.12.10 可导入 `softcopyright`、`docx`、`reportlab` 和 `playwright`。
- 使用 `python-runtime\python.exe` 跑通本地模板完整材料生成，输出 `output-embedded-python-review\EmbeddedRuntimeAcceptanceSystem-20260606-112739-7944--材料包.zip`，`ui_screenshot_count: 9`。
- 已通过 `winget install --id TheDocumentFoundation.LibreOffice -e --accept-package-agreements --accept-source-agreements` 在本机安装 LibreOffice 26.2.3.2。
- 使用内置 Python + LibreOffice 跑通完整材料生成，输出 `output-libreoffice-review\LibreOfficePdfAcceptanceSystem-20260606-130405-5922--材料包.zip`，`warnings: []`，确认 PDF 转换不再走简版兜底。
- 已新增 LibreOffice 内置运行时准备脚本 `scripts\prepare-libreoffice-runtime.ps1` 和 npm 命令 `npm run prepare:libreoffice`，可从本机 `C:\Program Files\LibreOffice` 复制完整运行时到项目根目录 `libreoffice/`；该目录约 662.67 MB，已加入 `.gitignore`。
- `backend\softcopyright\docgen.py` 已改为优先探测 `SOFT_LIBREOFFICE_PATH`、安装包内置 `resources\libreoffice\program\soffice.exe`、系统安装路径和 PATH；LibreOffice 转换命令改为绝对路径，增加 `--norestore`、`--nolockcheck`，默认超时提高到 360 秒，可通过 `SOFT_LIBREOFFICE_TIMEOUT_SECONDS` 调整。
- 已针对 `游戏软件` 增加游戏化界面截图生成：启动登录、游戏主界面、关卡地图、消除棋盘、道具背包、结算统计等页面不再使用后台管理表格样式。图注会优先使用截图对象中的游戏化标题和说明。
- 使用 `轻松点点消` 消除游戏样例验证截图生成，输出 `output-game-screenshot-review-2\轻松点点消-20260606-133559-1291--材料包.zip`，`ui_screenshot_count: 9`，PDF 转换 `warnings: []`。
- 已新增 UI 蓝图层 `backend/softcopyright/ui_blueprint.py`：截图生成前会先生成结构化 `ui_blueprint.json`，包含 `renderer`、`visual_style`、每张截图的 `view_type`、标题、图注、组件和样例数据。
- `backend/softcopyright/screenshots.py` 已改为基于 UI 蓝图分发渲染，当前支持 `admin` 和 `game` 两类渲染器；游戏类已覆盖登录、主界面、关卡、棋盘、背包、商城、玩家资料、结算统计等 `view_type`。
- 使用 UI 蓝图重构后再次验证 `轻松点点消` 样例，输出 `output-ui-blueprint-full-review\轻松点点消-20260606-140631-2743--材料包.zip`，`ui_screenshot_count: 9`，`warnings: []`，并已确认 `ui_screenshots\ui_blueprint.json` 落盘。
- 最终 zip 已改为白名单打包，仅包含 5 个客户交付文件：说明书 Word、说明书 PDF、申请信息表 TXT、源码材料 Word、源码材料 PDF。`ui_screenshots/`、`generated_source/`、`generation_report.json`、材料清单等只作为内部生成过程产物，不进入 zip。
- 使用 `五文件打包验收系统` 验证最终 zip 内容，输出 `output-five-file-package-review\五文件打包验收系统-20260606-192621-3900--材料包.zip`；压缩包根目录仅包含 `五文件打包验收系统.docx`、`五文件打包验收系统.pdf`、`五文件打包验收系统.txt`、`五文件打包验收系统_代码-(Java).docx`、`五文件打包验收系统_代码-(Java).pdf`。
- `powershell -ExecutionPolicy Bypass -File scripts\package-windows-portable.ps1 -Version 0.1.0` 已验证通过，输出 `release/soft-copyright-generator-0.1.0-portable.zip`，大小约 296 MB，包含 Playwright Chromium Headless Shell，不包含真实本机配置文件。
- `npm run pack:dir` 已验证通过，输出 `release/installer/win-unpacked`；已确认 `resources\python-runtime\python.exe`、`resources\backend\generate_materials.py`、`resources\ms-playwright` 和 `resources\config\production.example.json` 存在，真实 `production.json` / `desktop.local.json` 不在安装目录内。
- `npm run pack:win` 已验证通过，输出 `release/installer/Soft Copyright Generator Setup 0.1.0.exe`，大小约 366 MB；NSIS/electron-builder 二进制下载通过 `ELECTRON_BUILDER_BINARIES_MIRROR` 镜像源解决。
- 已完成 NSIS 本机安装 smoke：安装器静默安装到 `release\nsis-smoke-install` 退出码为 0；安装目录包含 Electron 主程序、`resources\python-runtime\python.exe`、后端脚本、`resources\ms-playwright`、`production.example.json`，不包含真实 `production.json` / `desktop.local.json`。安装后内置 Python 3.12.10 可导入 `softcopyright`、`docx`、`reportlab`、`playwright`。
- 已使用安装目录内置 Python、后端和 Playwright Chromium Headless Shell 跑通完整本地模板生成，输出 `release\nsis-smoke-output\NSISSmokeAcceptanceSystem-20260607-201202-7134--材料包.zip`；`warnings: []`，`ui_screenshot_count: 9`，`source_total_lines: 5956`，`source_selected_pages: 60`，`material_consistency_ready: true`，总耗时 `47.77` 秒。最终 ZIP 根目录已确认正好 5 个客户交付文件：说明书 Word、说明书 PDF、申请信息表 TXT、源码材料 Word、源码材料 PDF。
- 已完成安装后 GUI 拉起和卸载 smoke：`Soft Copyright Generator.exe` 可启动 Electron 主进程、GPU、网络服务和渲染进程；随后静默卸载退出码为 0，`release\nsis-smoke-install` 被清理。
- 已新增客户预制 NSIS 安装器脚本 `scripts\package-customer-nsis.ps1` 和 npm 命令 `npm run pack:win:customer`。该命令从本机忽略文件 `config\production.json` 读取真实 NewAPI 配置，生成临时 `build\customer-config\production.json`，写入 `SOFT_MODEL_MODE=gpt` 和 `SOFT_CUSTOMER_PRESET_CONFIG=true`，再注入安装包资源目录 `resources\config\production.json`；`build/` 已加入 `.gitignore`。
- 客户预制安装器已重新验证通过，输出 `release\customer-installer\Soft Copyright Generator Setup 0.1.0.exe`，大小约 366 MB；`win-unpacked\resources\config\production.json` 存在且为无 BOM UTF-8，包含 GPT 模式、请求地址、API Key、模型 `gpt-5.5` 和 `SOFT_CUSTOMER_PRESET_CONFIG=true`，不再写入 `SOFT_MODEL_CONFIG_LOCKED=true`；`production.example.json` 仍为占位 key，`desktop.local.json` 未进入安装包资源目录。
- 客户预制安装器构建产物已确认前端包含“请求地址”“模型名称”“API Key”三个配置字段，且不再包含“模型配置已预置”的锁定提示。安装后可读取预置配置并在 UI 中展示，保存时会写回请求地址、模型名称和 API Key。
- 客户预制安装器已完成开放配置轻量安装 smoke：静默安装到 `release\customer-ui-config-smoke-install` 退出码为 0，安装后 `mode=gpt`、`SOFT_MODEL_CONFIG_LOCKED` 不存在、请求地址/API Key/模型存在，GUI 可拉起 4 个 Electron 进程，随后静默卸载并清理安装目录。
- 客户预制安装器已内置 LibreOffice 运行时，重新打包后输出 `release\customer-installer\Soft Copyright Generator Setup 0.1.0.exe`，大小约 572.86 MB；`win-unpacked\resources\libreoffice\program\soffice.exe` 存在，`resources\libreoffice` 约 662.67 MB。客户机器不再需要单独安装 LibreOffice、Python、Node、Chromium 或 Playwright。
- 已使用安装目录内置 Python、Playwright 和 LibreOffice 跑通完整本地模板材料生成，输出 `release\customer-libreoffice-smoke-output\CustomerLibreOfficeRuntimeSystem-20260608-084549-6879--材料包.zip`；`warnings: []`，`ui_screenshot_count: 9`，`source_total_lines: 5938`，`source_selected_pages: 60`，总耗时 `37.81` 秒。最终 ZIP 根目录正好 5 个客户交付文件，两个 PDF 均由内置 LibreOffice 转换生成。
- 真实 NewAPI `/v1/chat/completions` 调用成功。
- 真实 NewAPI `/api/usage/token` 余额读取成功。
- 真实 NewAPI 完整材料生成命令已跑通。
- C# 源码生成器扩展后，使用 `轻松点点消` 消除游戏样例验证完整材料生成，输出 `output-csharp-source-review\轻松点点消-20260606-194845-8635--材料包.zip`；`ui_screenshot_count: 9`，`source_total_lines: 3450`，`source_total_pages: 70`，`source_selected_pages: 60`，`source_line_target_met: true`，`warnings: []`。
- 上述 C# 样例最终 zip 已确认只包含 5 个客户交付文件：说明书 Word、说明书 PDF、申请信息表 TXT、源码材料 Word、源码材料 PDF。
- 上述 C# 样例的 `generated_source` 已用本机 .NET SDK 10.0.101 执行 `dotnet build`，结果为 `0 个警告`、`0 个错误`。
- 使用真实 GPT / NewAPI 配置跑通 `轻松点点消` 消除游戏完整材料生成，输出 `output-gpt-ui-blueprint-review\轻松点点消-20260606-200008-6953--材料包.zip`；`blueprint_source: llm`，`manual_source: llm`，`ui_blueprint_source: llm`，`ui_renderer: game`，`ui_software_type_match: true`，`ui_screenshot_count: 9`，`source_total_lines: 3916`，`warnings: []`。
- 已抽验上述 GPT 样例截图：`board_core.png` 为 8x8 消除棋盘、目标/步数/道具栏；`dashboard.png` 为关卡地图和开始游戏入口；`prop_system.png` 为彩虹球、小木锤等道具背包；`settlement.png` 为星级结算统计，均符合游戏软件类型。
- 游戏截图 9:16 改造后，使用本地模板验证 `轻松点点消`，输出 `output-mobile-game-screenshot-review-tight\轻松点点消-20260606-210243-6077--材料包.zip`；`ui_renderer: game`，`ui_screenshot_aspect_ratio: 9:16`，`ui_mobile_portrait_match: true`，9 张截图均为 720×1280。已抽验 `anti_cheat.png`，8×8 棋盘、通关目标、道具列表和底部操作按钮均完整显示在竖屏手机画面中。
- 使用真实 GPT / NewAPI 配置再次验证手机游戏截图链路，输出 `output-gpt-mobile-game-review\轻松点点消-20260606-205114-3469--材料包.zip`；`blueprint_source: llm`，`manual_source: llm`，`ui_blueprint_source: llm`，`ui_renderer: game`，`ui_software_type_match: true`，`ui_screenshot_aspect_ratio: 9:16`，`ui_mobile_portrait_match: true`，`ui_screenshot_count: 9`，所有 PNG 尺寸均为 720×1280。该次说明书中“星级结算模块”模型小章节失败一次，已由本地模板补齐，材料包仍正常输出。
- 已将游戏判定收紧为只依据用户输入的软件类型、软件名称和业务补充，不再读取模型生成蓝图中的 `Level`、`RiskLevel`、`关卡` 等词，避免教育、金融等非游戏软件被 GPT 蓝图误判为游戏。
- 使用本地模板完整生成验证教育、金融两类非游戏材料，输出 `output-industry-profile-review-2\智慧课堂教务管理系统-20260606-214832-1197--材料包.zip` 和 `output-industry-profile-review-2\智能风控交易管理系统-20260606-214908-1385--材料包.zip`；两者均为 `ui_renderer: admin`、`ui_screenshot_aspect_ratio: desktop`、`ui_admin_desktop_match: true`、`ui_screenshot_count: 9`、`warnings: []`。
- 使用本地截图链批量验证全部 14 个非游戏类型，输出根目录 `output-all-nongame-screenshot-chain-2`；APP、教育、金融、医疗、地理信息、云计算、信息安全、大数据、人工智能、VR、5G、小程序、物联网、智慧城市均为 `renderer=admin`、9 张截图、尺寸 1280×820、`type_match=True`、`warnings=0`。
- 已修复模块截图 key 与固定页 key 冲突问题：当业务模块 key 为 `dashboard`、`login`、`statistics` 时会自动落成 `module_dashboard` 等内部文件名，避免覆盖系统首页、登录页或统计页；智慧城市样例已从 8 张恢复为 9 张截图。
- 使用真实 GPT / NewAPI 配置做教育软件截图链定向验证，小请求 smoke 成功；长 JSON/长 UI 蓝图请求出现一次非 JSON/504 波动，系统按设计回退本地规则，最终输出 `output-gpt-education-screenshot-chain\智慧课堂教务管理系统-20260606-215054-6932`，结果为 `ui_renderer: admin`、`ui_type_match: True`、9 张截图、尺寸 1280×820。
- GPT 产品方案生成已拆分为身份定位、业务细节、模块明细分批和质量修复请求。使用真实 NewAPI 配置验证 `智慧课堂教务管理系统` 蓝图生成通过，`quality_score: 88`，包含 12 个业务对象、5 条业务流程、12 个统计指标、10 条质量规则和 8 个细化模块。
- 使用真实 GPT 产品方案做源码/截图定向链路验证，输出 `output-gpt-product-plan-chain-review\智慧课堂教务管理系统-20260606-225016-3827`；`quality_score: 88`，`source_total_lines: 4515`，`ui_screenshot_count: 9`，`ui_renderer: admin`，`ui_type_match: true`。该次 UI 蓝图尚未拆分，出现一次 `504 Gateway Time-out` 后回退本地规则。
- UI 蓝图拆分后，复用上述 GPT 产品方案验证截图链路，输出 `output-gpt-ui-blueprint-split-review-3\智慧课堂教务管理系统-20260606-233316-1022`；`ui_blueprint_source: llm`，`ui_renderer: admin`，`ui_type_match: true`，`ui_screenshot_count: 9`，`warnings: []`。已抽验 `course_resource.png`，课程资源管理页能显示课程资源、班级教学、作业测评、学习进度、家校通知等教育教务对象，未再出现结构化 JSON 残片。
- 使用内置 Python 跑通本地模板完整回归生成，输出 `output-product-plan-local-review-2\产品方案回归验证系统-20260606-233107-7377--材料包.zip`；`blueprint_source: local-template`，`ui_screenshot_count: 9`，`ui_renderer: admin`，`source_total_lines: 3875`，`warnings: []`。
- 已验证 GPT 返回对象数组清洗逻辑：当 `operations`、`data_fields`、`rules` 返回 `{name/title/field/rule: ...}` 结构时，会提取中文业务名称，避免截图表格或说明书出现字典字符串。
- 尝试重新跑“真实 GPT 产品方案 + 源码 + GPT UI 分批截图”完整定向链路时，连续多段 GPT 请求在 15 分钟处超时且未落盘产物；已终止遗留 `python-runtime\python.exe -` 验证进程。随后已收敛蓝图层和 UI 层的重复重试，避免与 provider 自带重试相乘，完整 GPT 端到端仍需下一阶段单独验收。
- 说明书 GPT 正文生成已从“每章/每模块单独请求”改为批次请求：公共章节分 3 批、模块章节每 2 个模块一批；生成器会输出公共章节批次和模块批次进度，单批失败仍由本地模板补齐。
- `generation_report.json` 已新增 `stage_timings` 和 `total_seconds`，可记录蓝图、说明书正文、源码、截图、Word、源码材料、PDF、信息表、打包等阶段耗时；桌面端事件也已增加蓝图子阶段、说明书子阶段、UI 蓝图子阶段和截图渲染子阶段。
- 使用真实 GPT / NewAPI 配置跑通完整端到端生成，输出 `output-gpt-full-acceptance\智慧课堂教务材料验收系统-20260607-112322-7231--材料包.zip`；`blueprint_source: llm`，`manual_source: llm`，`ui_blueprint_source: llm`，`ui_renderer: admin`，`ui_software_type_match: true`，`ui_screenshot_count: 9`，`source_total_lines: 4514`，`blueprint_quality_score: 88`，`warnings: []`。最终 ZIP 已确认仍只包含 5 个客户交付文件。
- 上述完整 GPT 验收总耗时 `674.55` 秒，其中 `blueprint: 353.43` 秒、`manual_content: 227.16` 秒、`screenshots: 81.51` 秒、`pdf: 9.69` 秒。耗时主要集中在 GPT 产品方案和说明书正文请求，后续优化应优先围绕蓝图缓存、模块批次并发或减少蓝图重试。
- 使用本地模板再次验证进度事件和阶段耗时，输出 `output-progress-event-local-review\进度事件回归验证系统-20260607-113709-7030--材料包.zip`；`warnings: []`，`ui_screenshot_count: 9`，`total_seconds: 17.78`，可收到截图页面生成和 9 张截图渲染进度事件。
- 已修复 GPT 蓝图实体名兜底：当模型返回中文 entities 或重复 `BusinessRecord` 时，会按模块 key 派生英文实体名，例如 `course_resource` 可得到 `CourseResourceRecord`、`CourseResourceQuery`，提升后续源码工程真实度。
- 已保留 GPT 小批次并发能力，环境变量 `SOFT_LLM_BATCH_WORKERS` 控制并发数，默认 `1`、上限 `3`；默认按质量优先顺序生成，只有人工设置 `2/3` 时才用于可选加速。该能力覆盖产品模块明细批次、说明书公共章节批次、说明书模块章节批次和 UI 截图蓝图批次，批次结果仍按原顺序合并，单批失败继续走局部回退。
- 使用真实 GPT / NewAPI 配置验证过可选低并发产品蓝图生成，`SOFT_LLM_BATCH_WORKERS=2` 时输出 `quality_score: 88`，8 个模块、11 个业务对象、5 条流程、12 个指标，耗时 `246.75` 秒。该数据仅作为可选加速参考，当前默认策略仍以内容质量和材料一致性为优先。
- 已进一步修复 entities 对象项清洗：当模型返回 `{name/title/entity/className: ...}` 形式时会提取真实实体名，不再将整个对象转成 `NameDescription` 等异常类名。
- 使用本地模板完整回归验证低并发改动，输出 `output-concurrent-batch-local-review\并发批次回归验证系统-20260607-125907-2398--材料包.zip`；`warnings: []`，`ui_screenshot_count: 9`，`source_total_lines: 3875`，`total_seconds: 28.56`。
- 已新增材料一致性检查：报告会输出 `material_manual_text_source`、`material_ui_text_source`、`material_module_title_hits`、`material_business_object_hits`、`material_metric_hits`、`material_source_module_key_hits` 和 `material_consistency_ready`，用于判断说明书、截图和源码是否共同消费同一份产品方案。
- GPT 产品方案提示词已加入确定性的差异化产品策略，会基于软件名、产品类型、业务补充、随机度和 seed 选择产品角度、流程重心、模块组织、数据深度、命名风格和避免套路；质量评分也已加强对泛型模块 key、通用操作四件套和通用字段的扣分，优先解决“每次生成像同一套模板”的核心问题。
- 使用真实 GPT / NewAPI 配置按默认质量优先模式完整验收 `晚自习作业跟踪与学情干预系统`，输出 `output-gpt-quality-first-review\晚自习作业跟踪与学情干预系统-20260607-132613-8577--材料包.zip`；`blueprint_source: llm`，`manual_source: llm`，`ui_blueprint_source: llm`，`ui_renderer: admin`，`ui_software_type_match: true`，`ui_screenshot_count: 9`，`source_total_lines: 4505`，`blueprint_quality_score: 100`，`material_consistency_ready: true`，`warnings: []`，总耗时 `576.54` 秒。最终 ZIP 已确认仍只包含 5 个客户交付文件。
- 上述质量优先 GPT 验收中，产品蓝图生成出 8 个强业务模块：晚自习场次台账采集、签到缺勤匹配清洗、作业收交追踪留痕、批改进度核验归档、学情预警工单核验、班主任干预处置记录、晚自习档案审计追溯、年级学情看板汇总；说明书 DOCX 抽查 146 个段落，8 个模块标题、8 个业务对象和 8 个统计指标均能命中正文。
- 上述质量优先 GPT 验收截图已抽查首页和学情预警工单页，画面为教育晚自习后台业务系统，菜单、指标、待办、规则和表格内容均围绕签到、缺勤、作业收交、批改、预警工单和班主任干预展开，未出现游戏画面或泛型空白后台。
- 使用本地模板验证“源码项目内 UI 原型”链路，输出 `output-project-prototype-local-review\项目内原型截图回归系统-20260607-135831-4065--材料包.zip`；`generated_source\ui-prototype` 存在并包含 HTML、`ui_blueprint.json`、`prototype-manifest.json`，截图 HTML 路径指向该目录，PNG 仍位于 `ui_screenshots`，最终 ZIP 仍为 5 个文件，`ui_screenshot_count: 9`，`source_total_lines: 5456`，`warnings: []`。
- 使用本地模板做 4 类布局抽样，输出根目录 `output-layout-variant-local-review`；金融软件为 `risk`、地理信息软件为 `map`、人工智能软件为 `pipeline`、教育软件为 `workflow`，每类均为 9 张截图、`renderer=admin`、`warnings: []`，已抽查 dashboard PNG，视觉结构已不再是同一个后台壳。
- 使用本地模板完整验证金融布局变体，输出 `output-layout-full-local-review\金融布局变体回归验收系统-20260607-140657-8859--材料包.zip`；最终 ZIP 只包含 5 个客户交付文件，`dashboard_layout: risk`，`ui_screenshot_count: 9`，`ui_admin_desktop_match: true`，`source_total_lines: 5813`，`material_consistency_ready: true`，`warnings: []`。
- `scripts\run_gpt_type_sampling.py` 已支持 `SOFT_GPT_TYPE_SAMPLES` 过滤单类样例，例如设置为 `finance`、`medical` 或 `game`，可避免每次验收都重跑全部类型。
- 使用真实 GPT / NewAPI 配置完成新版类型抽样中的金融、医疗两类验收。金融样例输出 `output-gpt-type-sampling-review\社区小微贷款风险巡检系统-20260607-142113-4492`，`blueprint_quality_score: 100`，`ui_blueprint_source: llm`，`ui_layout_variant: risk`，`ui_screenshot_count: 9`，`source_total_lines: 6512`，`material_consistency_ready: true`，`warnings: []`；已抽查 dashboard PNG，画面为小微贷款风控复核控制台。
- 使用真实 GPT / NewAPI 配置完成医疗样例验收，输出 `output-gpt-type-sampling-review\门诊慢病随访处方核验系统-20260607-142816-2306`，`blueprint_quality_score: 100`，`ui_blueprint_source: llm`，`ui_layout_variant: workflow`，`ui_screenshot_count: 9`，`source_total_lines: 6510`，`material_consistency_ready: true`，`warnings: []`；已抽查 dashboard PNG，画面为慢病随访、复诊提醒和处方核验工单流程。
- 已新增 LLM 诊断 trace：设置 `SOFT_LLM_TRACE_PATH` 后，provider HTTP 尝试、蓝图/UI/说明书 JSON 请求、耗时、状态码和错误摘要会写入 JSONL；`scripts\run_gpt_type_sampling.py` 会为每个样本自动写入 `llm_trace.jsonl`，失败时也会落 `type_sampling_failure.json`，不再出现长时间等待后没有诊断产物的情况。日志不写 API Key 或 Base URL。
- 使用真实 GPT / NewAPI 配置完成游戏单独抽样，输出 `output-gpt-type-sampling-review\星糖岛消除冒险-20260607-151649-6910`；`blueprint_quality_score: 88`，`ui_blueprint_source: llm`，`ui_renderer: game`，`ui_layout_variant: game`，`ui_software_type_match: true`，`ui_screenshot_count: 9`，`ui_mobile_portrait_match: true`，`source_total_lines: 6487`，`material_consistency_ready: true`，`warnings: []`，总耗时 `350.4` 秒。`llm_trace.jsonl` 显示主要耗时集中在产品蓝图模块明细批次：约 `57.8`、`60.1`、`24.5`、`60.0` 秒，UI 蓝图批次约 `16-21` 秒，截图渲染正常。
- 已修复游戏棋盘页分类：当 GPT 或本地模板页面标题/图注/模块 key 命中 `糖果棋盘`、`消除棋盘`、`步数目标`、`障碍格`、`candy_board`、`move_goal`、`board` 等特征时，会强制使用 `game_board` 渲染 8×8 消除棋盘，而不是误走关卡地图。使用本地截图链回归 `output-game-board-regression-2\星糖岛消除棋盘回归-20260607-153021-7960` 验证通过，`renderer: game`，9 张截图均为 720×1280，`custom` 和 `anti_cheat` 均为 `game_board`，已抽查 `custom.png` 为 8×8 棋盘、通关目标、道具栏和“交换相邻棋子”按钮。
- 已新增通用截图链路快速验收脚本 `scripts\run_screenshot_chain_review.py`，支持读取 UTF-8 JSON 任务文件，只生成产品蓝图、源码项目、`generated_source\ui-prototype` 和 PNG 截图，不跑 Word/PDF、不打包 ZIP；便于快速验收截图是否符合软件类型，也避免 PowerShell inline 中文参数乱码。
- `generated_source\ui-prototype` 已补齐可浏览入口和说明文件：`index.html` 可在左侧切换所有截图页面，`README.md` 标明入口、截图尺寸和页面列表，`prototype-manifest.json` 新增 `entry`、`viewport` 和页面文件名。使用本地模板快速验收 `output-screenshot-chain-local-review\Screenshot-Chain-Review-System-20260607-153858-4530` 通过，`ui_screenshot_count: 9`，`ui_software_type_match: true`，`ui_admin_desktop_match: true`，`prototype_index_exists: true`，`prototype_readme_exists: true`，`prototype_manifest_exists: true`，`material_consistency_ready: true`，`warnings: []`，总耗时 `8.1` 秒。
- 使用真实 GPT / NewAPI 配置完成 post-fix 游戏截图链路验收，输出 `output-gpt-screenshot-chain-acceptance\星糖岛消除冒险-20260607-171428-3215`；`blueprint_source: llm`，`blueprint_quality_score: 100`，`ui_blueprint_source: llm`，`ui_renderer: game`，`ui_layout_variant: game`，`ui_software_type_match: true`，`ui_screenshot_count: 9`，`ui_screenshot_aspect_ratio: 9:16`，`ui_mobile_portrait_match: true`，`ui_game_board_screen_count: 6`，`source_total_lines: 6673`，`material_consistency_ready: true`，`warnings: []`，总耗时 `358.79` 秒。已视觉抽验 `dashboard.png` 为关卡地图主界面，`candy_board_match.png` 为 720×1280 的 8×8 三消棋盘、通关目标、道具栏和“交换相邻棋子”按钮，`statistics.png` 为星级结算统计页。
- 已完成可启动源码项目前端入口第一版：Java 生成项目 `pom.xml` 已补齐 Spring Boot Web 依赖和插件，原型会同步到 `src\main\resources\static\ui-prototype`，入口文档为 `UI_PROTOTYPE_ENTRY.md`；使用本地模板验收 `output-project-entry-local-review\Screenshot-Chain-Review-System-20260607-180139-4804` 通过，`ui_project_entry_exists: true`，`ui_project_served_index_exists: true`，`ui_project_entry_url: http://127.0.0.1:8080/ui-prototype/index.html`，`ui_project_run_command: mvn spring-boot:run`，`source_total_lines: 6528`，`warnings: []`。
- 已完成 C#/ASP.NET Core 前端入口验收，输出 `output-project-entry-local-review\源码项目前端入口回归系统-20260607-175846-2594`；原型同步到 `wwwroot\ui-prototype`，入口 URL 为 `http://127.0.0.1:5000/ui-prototype/index.html`，启动命令为 `dotnet run --urls http://127.0.0.1:5000`，`ui_project_served_index_exists: true`，`ui_screenshot_count: 9`，`source_total_lines: 7882`，`warnings: []`。该生成项目已执行 `dotnet build`，结果为 `0 个警告`、`0 个错误`。
- 已完成 JavaScript/Express 和 Python/FastAPI 前端入口验收：JavaScript 输出 `output-project-entry-local-review\前端入口脚本验收系统-20260607-180403-8638`，启动命令 `npm install && npm start`；Python 输出 `output-project-entry-local-review\前端入口接口验收系统-20260607-180404-8147`，启动命令 `uvicorn app.main:app --host 127.0.0.1 --port 8080`。两者均为 `ui_project_served_index_exists: true`、`ui_screenshot_count: 9`、`source_line_target_met: true`、`warnings: []`。
- 已新增 C# 生成项目真实服务截图模式：`scripts\run_screenshot_chain_review.py --project-server` 会启动生成出来的 ASP.NET Core 项目，再从 `http://127.0.0.1:{port}/ui-prototype/*.html` 截图；启动失败时回退本地文件截图并记录 warning。使用本地模板验收 `output-project-entry-local-review\源码项目前端入口回归系统-20260607-195104-3983` 通过，`ui_screenshot_render_mode: project-server`，`ui_screenshot_base_url: http://127.0.0.1:5000/ui-prototype`，`ui_project_server_started: true`，`ui_screenshot_count: 9`，`warnings: []`，总耗时 `42.93` 秒；验收结束后未残留 `dotnet` 进程，已视觉抽验 `dashboard.png` 正常。
- 已新增材料真实性与规范性校验模块 `backend\softcopyright\validator.py`，完整生成后会输出内部 `validation_report.json`，记录源码文件清单和 SHA-256、产品蓝图 hash、交付文件 hash、ZIP 条目、占位符/乱码扫描、第三方源码目录风险、说明书/源码/截图/信息表业务命中情况，并把 `authenticity_score`、`normative_score`、`validation_ready_for_delivery`、`validation_finding_count`、`validation_source_hash`、`validation_zip_entries_match_deliverables` 等字段同步写入 `generation_report.json`。
- 使用本地模板验证真实性/规范性校验链路：Java 样例 `output-validation-local-review\AuthenticityValidationSystem-20260609-102505-2660` 触发源码有效行数 `2961` 行未达 3000 行目标的硬性规范发现；C# 样例 `output-validation-local-review\NormativeAuthenticityAcceptanceSystem-20260609-102851-5097--材料包.zip` 通过，`source_total_lines: 3061`，`source_selected_pages: 60`，`authenticity_score: 97`，`normative_score: 100`，`validation_ready_for_delivery: true`，`validation_finding_count: 0`，最终 ZIP 仍为 5 个客户交付文件。
- 桌面端结果明细已接入真实性/规范性校验展示：后端 `RESULT_JSON` 会返回 `validation` 摘要，Electron 透传到前端，结果明细新增 `真实性评分`、`规范性评分` 和 `交付建议`。使用本地模板验证 `output-validation-ui-review\UiValidationDisplayCheck-20260609-103646-6433--材料包.zip` 通过，`authenticity_score: 97`，`normative_score: 100`，`validation_ready_for_delivery: true`，`validation_finding_count: 0`。
- 桌面端结果文件列表已加入内部 `validation_report.json` 打开入口；Electron 会把校验报告路径解析为绝对路径，前端在 ZIP 之后展示该报告，方便实施人员直接查看完整真实性/规范性证据链。
- 已新增内部 `materials_manifest.json` 证据链清单：记录软件名、版本、语言、产品类型、seed、生成模式、产品蓝图 hash、源码文件清单/行数/hash、源码鉴别材料每页对应的真实源码文件和行号范围、说明书引用映射、PDF 转换信息，以及不含 API Key 的 LLM trace 摘要。Electron 会解析 `validation.manifest_path`，桌面端结果文件列表已提供 `materials_manifest.json` 打开入口；该文件不进入最终客户 ZIP。
- 桌面端生成完成提示下方已新增交付状态条：当 `validation_ready_for_delivery=true` 时显示“校验通过，建议交付”，并展示真实性/规范性分数；当校验未通过时显示“需要复核后再交付”，优先展示 `validation_report.json` 中的前 3 条发现，避免实施人员只看到 ZIP 已生成而忽略硬性规范问题。
- 已将 GPT 生成链路默认调整为“真实性优先”流水线：产品蓝图质量目标从 78 提升为默认 92，最多 5 轮尝试；真实性优先模式下不再接收低于目标分的次优蓝图；功能模块改为逐模块生成和逐模块质量检查，不合格时单模块修复；说明书正文改为逐章/逐模块生成；截图蓝图改为登录页、首页、各模块页、统计页逐页生成，并输出更细的进度提示。`generation_report.json` 会记录 `generation_quality_profile` 和 `blueprint_quality_target`，桌面端结果明细新增“生成策略”项。
- 已新增 GPT 软件名称理解与自动业务补充：后端会在蓝图生成前调用 GPT，根据任意软件名称生成业务说明、关键词、目标用户和应避免方向；当业务补充为空或与软件名称领域不匹配时，会自动替换为 GPT 推断结果，GPT 不可用时回退本地规则。`generation_report.json` 会记录 `auto_feature_hint`、`feature_hint_profile`、`feature_hint_source`、`inferred_feature_hint` 和 `feature_hint_avoid_terms`。桌面端名称变化和“按名称自动匹配”按钮都会优先通过 `infer-feature-hint` 调用 GPT 推断，失败时才回退本地规则。
- 使用本地模板验证新流水线兼容性：`output-authenticity-pipeline-review\AuthenticityFirstPipelineCheck-20260609-125419-6130--材料包.zip` 通过，`generation_quality_profile: authenticity-first`，`source_total_lines: 3061`，`source_selected_pages: 60`，`authenticity_score: 97`，`normative_score: 100`，`validation_ready_for_delivery: true`，`validation_finding_count: 0`，最终 ZIP 仍为 5 个客户交付文件。
- 本阶段最新工程检查：`python -m py_compile backend\generate_materials.py backend\softcopyright\generator.py backend\softcopyright\validator.py backend\softcopyright\screenshots.py backend\softcopyright\sourcegen.py backend\softcopyright\llm\provider.py backend\softcopyright\llm\trace.py backend\softcopyright\llm_blueprint.py backend\softcopyright\ui_blueprint.py backend\softcopyright\llm_manual.py` 通过，`npm run build` 通过，`git diff --check` 仅提示仓库已有 LF/CRLF 换行转换警告。

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

说明：产品蓝图、说明书正文和 UI 蓝图均已在真实 GPT / NewAPI 配置下跑通过。当前优化方向已从继续堆本地模板，转为让 GPT 先生成可复用的真实产品方案，再由说明书、源码、截图共同消费这份方案；默认模板仍保留为不消耗 token 的兜底路径。

## 已知问题

1. Windows PowerShell inline / pipeline 传中文参数时可能把中文变成 `????`，长验证命令应使用 UTF-8 文件、JSON 配置、Node/Python 内部构造 Unicode 字符串，或使用 `\u...` 转义。
2. 客户登录、充值、激活码绑定还没有产品化，目前通过 NewAPI token 配置实现。
3. 客户预制安装包已在客户环境验证通过；后续重点从安装可用性转为材料真实性、规范性和业务差异化。
4. 内置 LibreOffice 后安装包体积从约 366 MB 增至约 573 MB，安装解压时间明显变长；客户已验证可用，但仍需在后续版本中关注包体体积和安装体验。
5. GPT 完整端到端已跑通；当前策略明确以生成内容质量、真实性和材料一致性为第一优先，耗时不作为降级理由。
6. 默认截图仍由 Playwright 直接截取源码工程内 `ui-prototype` HTML；C# 已支持可选启动生成项目后从真实服务 URL 截图。Java/JS/Python 的真实服务截图模式尚未接入。
7. 真实 GPT 游戏单独抽样已跑通；后续优化必须以不降低材料真实性、一致性和可申请性为前提。

## 下一步建议

优先级从高到低：

1. 用真实 GPT/NewAPI 跑一组“真实性优先”端到端样例，重点观察逐模块、逐页生成后的蓝图质量分、真实性评分、规范性评分和截图/说明书/源码同源性。
2. 继续扩展真实服务 URL 截图模式到 Java/Spring Boot；本机当前未安装 Maven，需先补 Maven 或使用可用的 Java 构建环境。
3. 做 GPT 蓝图缓存/复用策略：只缓存已通过高质量阈值和真实性校验的蓝图，避免同一软件反复验收时引入低质量复用。
