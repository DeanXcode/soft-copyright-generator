# 当前进度与交付说明

更新日期：2026-07-17

## 当前状态

本项目已经完成软著材料一键生成桌面工具的本地可运行原型，支持在首页填写软件名称、版本、源码语言、软件类型和业务补充后，一键生成材料包。

当前开发源码已进入 `0.1.8` 之后的未发布质量升级阶段，正式界面默认使用 React + Vite，并完成截图级 DOM 语义提取、结构化操作蓝图、模块操作覆盖矩阵、操作手册图文语义校验、终端类型一致性校验和截图检查点 v6。后台 8 模块样本的目标页面结构仍为 35 张截图，其中 24 张为互补操作页；这是当前后台验收结构，不是所有软件固定页数。移动端按实际模块数量生成页面，每模块默认补充 2 张符合终端语义的操作页。

截至 2026-07-17，当前源码的完整回归、Python 编译、Electron 主进程检查和 Vite 构建全部通过。智能生产正式任务已经使用 100 分已批准蓝图完成 35 张真实 React 截图，其中 24 张为操作页；修正版 36 页 A4 操作手册、60 页源码鉴别材料、申请信息和最终 ZIP 均已生成并通过交付门禁。

当前最新正式可交付样本为 `output-formal-35-action-label-fix\智能生产效率提升平台-20260716-160500-3501--材料包.zip`，`generation-state.json=success/done/100`、`validation_report.ready_for_delivery=true`、`findings=[]`，SHA-256 为 `2E7E8300B84595B3F48346320B3C4E0497E46DA57DEEBF4150AC9BB5BBDA1F58`。最新客户安装器仍为 2026-07-14 构建的 `0.1.8`，尚未包含 2026-07-15 至 2026-07-17 的图文语义、结构化操作覆盖、布局和登录动作语义修复，下一阶段应提升版本并重新打包。

## 2026-07-17 登录页动作语义修复与材料重建

- 修复登录页把随机验证码 `7K4M` 和密码显隐符号 `◉` 当作手册操作名称的问题。Playwright 动作采集现在优先读取 `aria-label/title`，随机字母数字验证码、纯符号和按钮尾部装饰箭头会在截图摘要和手册动作列表中被过滤；截图检查点提升为 v6，旧动作元数据会自动失效并重采。
- 登录页不再复用筛选页、指标页的通用图注和步骤模板。图注明确列出账号、密码、图形验证码、运行环境和岗位身份；4 条步骤依次说明环境核对、凭据填写、验证码/密码辅助控件和主登录校验，避免“输入右侧字符调整查看范围”“当前可见指标”等错误表述。
- 使用原 100 分批准蓝图、原 35 个 React 页面和全局视觉参考图，在独立目录从截图节点续跑。最终 35 张截图、24 张操作页、35 个可见内容摘要和 81/81 次运行时接口请求通过；操作手册 36 页、源码 PDF 60 页，`ready_for_delivery=true`、`findings=[]`。DOCX/PDF 文本扫描确认旧 `【7K4M】/【◉】` 为 0，PDF 第 4 页渲染复核无裁切、重叠、乱码或不可读控件。

## 2026-07-16 正式 35 页 React 材料包验收完成

- 正式任务使用 `tmp\formal-blueprint-acceptance-v3-20260716-152727\product-blueprint.accepted.json` 作为唯一已批准蓝图输入，未重新生成产品蓝图。运行配置按桌面端规则合并仓库配置和用户配置，文本模型为 `gpt-5.6-sol`，图片模型为 `gpt-image-2`；续跑期间 35/35 个 React 组件、全局风格参考图、源码和阶段缓存均被复用，没有新增页面模型请求。
- 修复大型详情面板误用 `operation-result` 后超出固定画布的问题：后台单行工作区和详情网格现在使用可收缩网格行，失败页 `production_work_order_operation_2_2` 从底边 888px 收敛至 710px，原始长文本“当前生产工单 · 来源 MPS-2026-W29 / V4.1”保留且布局问题为 0。
- 修复生成组件普通 CSS 类跨页面污染的问题：根级指标条不再继承其他页面的 `flex:1`，趋势与证据表格工作区使用稳定行高；`capacity_forecast_bottleneck_detection_operation_2_2` 的指标条固定在 86px，工作区和表格底边均为 708px。确认弹窗保护规则不再同时压缩外层遮罩和内层面板，弹窗与背景之间的预期覆盖不再误判为控件重叠，但弹窗内部控件仍继续接受重叠检查。
- 模块操作覆盖门禁改为优先使用结构化操作契约中的 `action_key/category`，不再把“浏览产线排程甘特图、对比产能预测方案”等非旧关键词标签误归为同一流程类别。8 个模块均达到每模块 3 张操作页且至少覆盖查询与流程两类；底层一致性校验仍支持纯符号按钮精确匹配，但正文动作列表会过滤无语义纯符号并优先使用可访问名称。
- 最终报告记录 35 个 AI React 页面、35 个可见内容摘要、8/8 个模块操作覆盖、81/81 次运行时业务接口请求、56 个结构化操作和 239 个生成源码文件。36 页说明书包含 35 个图注，标题、按钮、可见语义和终端类型差异均为 0；源码 PDF 为 60 页，抽取自 72 个不同源码文件，业务逻辑行占比 0.53。
- `validation_report.json` 为 `ready_for_delivery=true`、`findings=[]`。唯一警告是 6 个说明书正文页的 PDF 可提取行数略低于 30，但字符数和业务操作内容充足，已按 `near_threshold` 软通过；使用 Poppler 独立渲染抽查说明书封面、目录、业务截图页、弹窗页、末页和源码首中末页，未发现裁切、重叠、乱码、黑块或页码问题。
- 正式 ZIP 大小 `8,166,438` 字节，包含规定的 5 个交付文件，SHA-256 为 `C79F913C06CEE9742BE283D1FCE7F880B7A008C4CF87B364CC95DAF31B08FE44`。本轮 99 项完整回归、Python 编译、Electron 主进程检查和 Vite 构建全部通过。

## 2026-07-16 产品蓝图结构化操作契约与正式交付门禁

- `FeatureModule` 新增向后兼容的 `operation_specs`。GPT 详细蓝图现在必须为每个模块给出至少 3 个结构化操作，包含稳定动作 key、执行角色、触发条件、输入字段、操作前状态、操作后状态、结果证据和确认要求；React 操作页提示词直接消费这些字段，不再只依赖“登记、校验、分析、确认、归档”等泛化动作名。
- 已确认的轻量模块提纲只有在自身已经包含完整 `operation_specs` 时才允许跳过详细蓝图生成；旧缓存若缺少新版契约会自动失效并重建明细。阶段缓存 schema 提升为 v2，可完整往返保存结构化操作；截图检查点提升为 v5，并把结构化交互元数据纳入页面指纹。
- 蓝图候选模块不再机械截取前 8 个，而是优先保留不同业务类别和细节完整度；工作流步骤保留长度由 32 字提升到 80 字。新增蓝图契约检查会拒绝弱语义 `domain_XX_XXXXX` key、重复泛化动作、缺失状态变化/结果证据、工作流截断，以及工业后台混入“移动 App、会员权益、收藏、个人中心”等消费端语义。
- 后台和移动端操作页均以结构化契约为第一来源，旧 `operations` 和终端推断仅在结构化覆盖不足时补缺。移动端不再把旧 secondary interaction 强行放在前两页，并已完整传递角色、触发条件、输入字段、前后状态和结果证据。
- 最终 `validation_report.json` 新增 `blueprint_operation_contract_required/ready/issues` 和结构化操作数量。GPT 正式模式未通过契约时会产生 `blueprint_operation_contract_not_ready` 并阻止交付；`Default Template` 明确不要求 GPT 结构化契约，继续保持零 token 可生成和可交付。
- 旧样本 `output\智能生产效率提升平台-20260715-110913-5222\generated_source\product-blueprint.json` 复审确认存在 14 项契约问题：8 个模块缺少结构化操作、4 个模块使用弱 key、业务工作流疑似被 32 字截断，以及后台蓝图混入移动消费端语义。简化上下文审计曾得到 12 分；按原 `generation_report.json` 完整任务上下文复审为 0 分，均属于必须重建、不能继续扩页的蓝图。
- 新增蓝图契约、候选模块覆盖、长工作流、移动端结构化操作优先、页面元数据传播、阶段缓存往返和正式/模板校验差异回归；当前 93 项完整测试通过。正式 35 页 GPT React 验收仍未启动，避免在蓝图不合格时消耗页面生成 token。

## 2026-07-16 正式 GPT 蓝图验收与批次修复优化

- 使用桌面端当前配置的 `gpt-5.6-sol` 对“智能生产效率提升平台”执行正式蓝图单独验收，模型目录健康检查为 HTTP 200。验收仅生成产品蓝图、审计和 trace，没有调用 image2，也没有启动源码、React 或 Playwright 阶段。
- 实际模型运行暴露出三个全局问题并已修复：平衡模式原先遇到一个模块字段缺失会放弃整轮、重做全部 8 模块；旧 `domain_XX_XXXXX` key 没有被 `semantic_module_key()` 当成占位 key；消费 App 判定把制造业“延期风险清单”中的“清单”误认为消费端信号。
- 模块生成现在对所有正式质量模式启用批次级定向修复，失败时只修复当前 2 个模块；模块顺序、key 和 title 强制对齐已确认轮廓。制造业语义 key 增加 `production_plan_coordination / smart_scheduling / process_takt / equipment_downtime / capacity_forecast_bottleneck_detection / yield_improvement / delivery_performance` 等稳定映射。
- 蓝图核心方案和全局质量修复后统一执行终端语义归一化。后台/工业软件会把移动 App、个人中心、收藏、离线缓存、岗位偏好等消费端措辞转换为工业生产运营工作台、权限审计、重点标记、导出留存和岗位权限；消费级 APP、音乐软件和游戏不执行该转换。提示词同步新增终端边界，减少模型源头污染。
- 最终候选位于 `tmp\formal-blueprint-acceptance-v3-20260716-152727`。原始模型候选为 82 分，仅剩移动端措辞问题；确定性终端归一化后 `product-blueprint.accepted.json` 和 `blueprint-audit.accepted.json` 复审为 100 分、问题 0、8 个业务模块、56 个结构化操作。
- `blueprint-page-plan.json` 验证后台页面计划为 35 页，其中 24 张操作页全部来自 `blueprint-structured`，`coverage-fallback=0`；选中操作包含 8 个查询类、14 个流程类和 2 个结果类动作，action key 全局唯一，角色、触发条件、状态和结果证据完整。93 项完整回归、Python/Electron 检查和 Vite 构建通过。

## 2026-07-15 操作手册图文一致性与按钮说明全局门禁

- 操作手册不再按模块操作顺序猜测截图标题和动作名称，主界面、二级界面标题、图注及按钮说明统一直接读取对应 `UiScreenshot` 元数据；查询、导入、导出、复核、预警、追踪等实际页面不会再被写成通用“统计/添加”。
- 按钮裁剪图写入 Word 时同步保存按钮名称到图片 `docPr` 的 `descr/title` 属性；交付校验会同时读取正文 `【按钮】` 与按钮图片辅助文本，避免图片替换文字后被误判为“缺少按钮覆盖”。
- 新增 `manual_ui_consistency_ready` 硬门禁，逐图核对截图数量、标题顺序、按钮来源和模块/操作页按钮覆盖；标题、按钮或配图顺序不一致时在生成阶段停止交付。
- 操作说明默认只展示 4 个明确动作按钮，并优先选择查看、打开、下载、导出、提交、复核、下发等动作；`记录01` 等状态徽标和组合型重复裁剪不会再挤占按钮说明。
- 截图几何门禁从“文字与文字重叠”扩展到“无文字图形遮挡文字”：会识别带背景色/渐变的 absolute/fixed 空元素是否实际绘制在指标、状态或说明文字上，命中后隐藏装饰遮挡物并再次复检；首页指标卡中的竖向装饰柱不再穿过数字和辅助说明。
- React 生成约束新增面板标题覆盖规则：标题必须概括全部子项，跨检验批、材料、试验、测量和隐蔽验收时使用“综合质量任务进度”等上位名称，不再用一两个子模块命名整个面板。
- 运行时业务数据脚本升级到 `v10`：先等待 React 业务 DOM 完成渲染，再把真实接口编号写入已有标题辅助区或记录区；取消固定在页面底部的白色浮动证据条，找不到安全承载位置时直接停止截图，不允许用覆盖层满足接口可见门禁。
- 桌面端说明书会在概述、登录、模块、统计、权限和 FAQ 全局过滤“移动 App、小程序、底部导航、进入项目、个人中心”等终端冲突段落，运行环境表中的移动架构和部署拓扑也会按实际终端改写为桌面 Web/工业触控表述；安全说明与常见问题采用自然连续分页，避免与统计截图同页过度拥挤或形成孤页。
- “轨道交通施工质量分析检验大数据系统”已从失败节点完成重建：23 页说明书包含 27 张真实截图，`manual_ui_actual_figure_count=27/27`、标题错误 0、按钮错误 0、按钮覆盖缺失 0、低密度正文页 0、目录页码完整，最终 `ready_for_delivery=true`。人工渲染抽检系统首页、统计分析、项目质量策划查询/导入、检验批导出/复核、施工测量预警/追踪及末页通过；首页和统计页均无图形遮字或浮动层覆盖。
- 最新材料包为 `output/轨道交通施工质量分析检验大数据系统-20260715-121646-5899--材料包-20260715-201901-568971.zip`，大小 `13,671,352` 字节，SHA-256 为 `E41D98C74C2314FE19CFE7E3B1BD159278D0F87C90197604D2B3524FB53846AA`。69 项完整回归、Python 编译、Electron 主进程/预加载脚本检查和 Vite 构建全部通过。

## 2026-07-15 智能制造蓝图类型误判与断点续跑修复

- 修复“智能生产效率提升平台”被错误判为医疗手术排班、随后又被交通干支线路径清洗覆盖的问题：医疗领域判断不再把通用的“排程、排班、质量检验”当作单独医疗证据，交通判断不再因通用“路径、线路”触发。
- 人工智能软件新增 `smart_manufacturing / 智能制造生产运营平台` 行业子类型，覆盖生产计划、生产工单、产线排程、换线调度、工序节拍、在制品、设备停机、产能瓶颈、良率和交付等制造业语义；产品体验稳定为 `industrial_hmi`。
- UI 顶层行业 key、行业名称和 `product_experience_spec` 统一由同一次推断写入，类型门禁同时校验行业 key/名称，拒绝“手术 key + 交通标题 + 制造业页面”这类缓存合并污染。
- 断点续跑会优先按软件名、版本、软件类型和原 seed 查找本地阶段缓存，直接恢复产品蓝图与 8 个业务模块；模型网关临时 502/503 时不再先重复调用名称理解并丢失失败节点。
- React 可见文字清洗新增“待补充、待完善、示例内容、业务记录、记录01”等未完成占位文案处理；截图检查点指纹升级为同时包含共享 `app.js/index.css`，组件或样式变化后旧 PNG 会自动失效并重渲染。
- 真实失败任务 `output/智能生产效率提升平台-20260715-110913-5222` 已从 40% 断点完成：27/27 个 React 页面、27 张 1280×720 截图、说明书 Word/PDF、源码材料 Word/PDF、申请信息 TXT 和最终 ZIP 均已生成；`ui_software_type_match=true`、`ui_visible_text_clean=true`、`ready_for_delivery=true`。材料包为 `output/智能生产效率提升平台-20260715-110913-5222--材料包.zip`。

## 2026-07-11 参考手册目录与二级操作截图对齐

- 对照用户提供的 37 页《智能生产效率提升平台-用户手册》逐页检查：参考手册第 1 页为目录，业务章节普遍同时展示模块列表、按钮局部和添加/编辑/删除等二级表单或确认弹窗；当前 17 页手册仅有 9 张主界面图，缺少按钮触发后的界面证据。
- 新手册在封面后增加独立目录页，列出软件概述、运行环境、登录与主界面、全部业务模块、统计分析、权限安全和常见问题。
- PDF 密度检查将前 3 页内标题为“目录”的页面识别为结构页，不按普通正文字符/行数阈值处理；目录存在性仍由 Word 结构门禁独立校验。
- 手机 APP 界面蓝图从最多 6 个模块扩展到最多 10 个模块，并为每个模块增加至少一张按钮触发的二级操作页；桌面管理软件继续保留每模块两张操作页。
- React/HTML 页面提示强制二级操作页显示按钮激活状态、详情/编辑表单/抽屉/确认弹窗、取消或返回、主确认和处理结果，禁止把主列表换标题后冒充操作页。
- 生成门禁新增 `ui_secondary_screenshot_ready` 和 `manual_toc_ready`：非游戏手册未覆盖全部业务模块的二级截图，或 Word 手册没有目录页时停止交付。
- ZIP 改为先写临时文件再原子替换；若用户或资源管理器正在打开旧材料包导致目标被锁定，自动输出带时间戳的新 ZIP，不再让已经完成的截图、文档和校验在最终打包阶段整体失败。
- `小艾听歌软件` 真实断点重建后，说明书由 17 页增至 27 页，截图由 9 张增至 19 张，其中 8 张二级操作截图覆盖全部 8 个实际蓝图模块；目录页及第 7、14、22 页添加/登记表单已渲染抽检，能看到按钮激活、业务表单、返回/取消、主确认和处理结果。最终进度 100%、`ready_for_delivery=true`、`findings=[]`，新版材料包为 `output/小艾听歌软件-20260711-215258-5900--材料包.zip`。

## 2026-07-11 说明书 PDF 密度门禁修正

- 对照用户提供的 21 页已交付操作手册复核：PDF 文本提取没有任何一页达到 30 行，普通正文页多为 19-23 行，说明 PDF 提取行数不能直接等同于法规所述版面行数。
- 说明书门禁改为综合正文充分性判断：少于 30 个可提取行但具备至少 18 行、280 字和明确业务操作语义的正文页可以交付；真正稀疏页或无法完成检查仍会硬失败。
- 报告继续保留 `manual_pdf_line_requirement_risk_pages` 和风险提示，便于人工按《计算机软件著作权登记办法》第十二条复核，不再因提取器行数差异在 99% 误停交付。
- 命令行断点恢复会自动从原 `generation_report.json`、`generation-state.json` 或 `generation-failure.json` 读取已确认蓝图；清空模型配置后仍可复用阶段缓存重建文档、校验和 ZIP，不再回到 GPT 名称理解阶段。
- 原失败任务 `output/小艾听歌软件-20260711-215258-5900` 已在清空模型地址与密钥的环境下断点重跑成功，复用 `blueprint/technical_architecture/manual_content/ui_blueprint` 缓存和既有 image2 参考图；最终 `generation-state=success`、进度 100%、`ready_for_delivery=true`、`findings=[]`、低密度正文页 0，材料包为 `output/小艾听歌软件-20260711-215258-5900--材料包.zip`。

## 2026-07-11 模型与推理强度选择

- 顶部状态区新增当前文本模型与推理强度入口，用户无需先猜测“高级设置”位置，点击即可打开配置。
- 模型配置新增常用 GPT 模型下拉选择和“极简、低、中、高、极高”推理强度选择；默认使用“中”，已存在的自定义模型名称仍可正常显示和保留。
- 切换正式生成模型时，若蓝图模型此前未单独定制，会同步切换蓝图模型；客户界面不再显示或编辑模型请求地址，继续使用安装预置地址。
- 推理强度保存到本地 `SOFT_MODEL_GPT_REASONING_EFFORT`，Electron 启动的蓝图与正式材料生成进程会继承配置，所有 OpenAI-compatible 文本请求会传递标准 `reasoning_effort` 参数；图片模型请求不受影响。
- 验证通过：Python 核心模块编译、Electron 主进程语法检查、`npm run build`、推理强度环境配置与请求载荷检查；Playwright 在 `1280x860` 视口确认设置抽屉无溢出，模型/强度切换后顶部状态会立即同步。验证截图保存在 `output/playwright/model-controls.png`。

## 2026-07-11 客户安装包打包

- 已在模型选择、说明书密度、目录和二级操作截图功能完成后重新执行 `npm run pack:win:customer`，成功生成客户版 NSIS 安装器，输出为 `release/customer-installer/Soft Copyright Generator Setup 0.1.0.exe`，大小 `602,696,241` 字节（约 `574.78 MB`），SHA-256 为 `214265D5D62BDE3657A035AFDB03147E79AFE9EA789C99173B313BA5EF915A74`。
- 打包前验证通过：`python -m py_compile backend\generate_materials.py backend\softcopyright\generator.py backend\softcopyright\docgen.py backend\softcopyright\screenshots.py backend\softcopyright\llm_manual.py`、`node --check desktop\electron\main.cjs`、`node --check desktop\electron\preload.cjs`、`npm run build`。
- 安装器解包资源核对通过，包含 `backend\generate_materials.py`、客户预置 `config\production.json`、`config\production.example.json`、`ms-playwright`（含 `chromium`、`chromium_headless_shell`、`ffmpeg`、`winldd`）、`python-runtime\python.exe`、`libreoffice\program\soffice.exe` 和 `requirements.txt`。
- 客户预置配置检查为 `SOFT_MODEL_MODE=gpt`、`SOFT_ACCOUNT_PROVIDER=newapi`、文本模型 `gpt-5.5`、`SOFT_CUSTOMER_PRESET_CONFIG=true`；推理强度未显式配置时由应用默认使用 `medium`。仅确认 API Key/Base URL 字段存在，未输出真实密钥或请求地址。
- 打包日志仅出现 `package.json` 缺少 description/author、默认 Electron 图标、重复 dependency 引用和 Node `DEP0190` 提示，均未影响安装器生成。

## 2026-07-11 React 真实模型全链路验收

- 已使用真实 `gpt-5.5`、`gpt-image-2`、React、Vite、生成项目服务和 Playwright 跑通桌面工业监控项目，输出目录为 `output-react-real-acceptance/矿山机械设备运行状态监测与智能维护管理系统-20260711-113606-2401`，最终进度到达 100%，无 warnings，`validation.ready_for_delivery=true`。
- 27 个页面全部由独立 React JSX/CSS 组件构建并通过真实 Chromium 截图，截图尺寸均为 `1280x720`；运行时业务接口共成功请求 `65/65` 次，`ui_runtime_api_ready=true`，前端源码保存在 `generated_source/frontend-app`。
- 包内页面最高结构相似度为 `0.359`，没有触发重复页面门禁；说明书共 29 页并包含 27 张界面图，源码 PDF 共 119 页，最终 ZIP 包含规定的 5 个交付文件。
- 修正深色高密度 image2 界面被旧图像门禁误拒的问题，同时继续拒绝纯色和低信息量占位图；真实生成的深色矿山监控参考图已通过质量复核。
- 阶段缓存现已把 creative seed 纳入隔离键，同一 seed 可复用产品蓝图、技术架构、说明书、UI 蓝图和 React 页面缓存，不同 seed 不会串用旧项目；旧缓存只在显式恢复时兼容迁移。
- React 页面生成改为受控并行并逐组件缓存；单个 JSX 失败、超时或构建不通过时只重试对应组件，不再整包回退到固定 HTML 骨架。
- 浏览器自动布局修复只移动绝对定位或固定定位的重叠控件，页面缩放改为累计收敛，避免表头被误推移和缩放来回振荡；真实 27 页截图均通过布局检查。
- 截图质量检查改为读取 React JSX 可见业务文本和真实运行接口证据，并清理 `Record/Query/Trace/Service` 等开发者类型名以及“待填写”“业务记录”等模板化文案，防止内部命名进入交付截图。
- 本阶段回归命令 `python -m unittest tests.test_react_frontend_codegen tests.test_dashboard_runtime_api tests.test_stage_cache_seed tests.test_image_quality_gate -v` 共 9 项通过；真实验收的真实性与规范性评分均为 100。

## 2026-07-11 源码材料严格 60 页修复

- 修复源码鉴别材料逻辑页为 60 页、LibreOffice 实际却转换成 119 页的问题。原因是原 15.2pt 行距几乎占满 A4 正文高度，长代码行换行后会把第 50 行推到下一张近空白页，显式分页符随后又继续新建页面。
- 源码材料改用 9pt 字号、14pt 固定行距，并对超宽代码行使用 Word 字符宽度缩放，确保一个真实源码行只占一个物理行；最终仍保持每页严格 50 行且不截断源码内容。
- 超过 60 页时不再直接拼接“最后 30 个原始分页块”，而是严格取最前 1500 行和最后 1500 行，再分别按每页 50 行分页，避免原源码末页不足 50 行造成第 60 页大面积空白。
- 规范性门禁新增 `source_pdf_page_count_match`：PDF 实际物理页数必须等于选定源码页数；超过 60 页时还必须满足 `source_selected_pages=60` 和 `selection_mode=first_30_last_30_continuous`，否则停止交付。
- 使用真实矿山项目的 7101 行源码复测：逻辑页 60、PDF 物理页 60、每页 50 行，第 2 页与第 60 页渲染抽检无空白页、文字裁切或重叠；修正版校验 `ready_for_delivery=true`、`findings=[]`。
- 根据客户要求继续把 50 行纵向铺满正文区：对 LibreOffice 分页阈值实测 `14.2/14.4/14.6/14.8/15.0/15.05/15.10/15.15pt`，确认 `15.10pt` 是保持 60 个物理页的最大稳定行距，`15.15pt` 已会溢出；最终采用 9pt 字号、15.10pt 行距、无源码行号，第 3、30、60 页渲染抽检均铺到页面底部安全边界附近。
- 修复源码缩进在 Word 中视觉弱且会被长行压缩的问题：读取阶段继续保留原始 4/8/12 空格语法层级，写入材料时将行首空白转换为固定的 Word 段落左缩进，正文 run 不再携带行首空格；长行宽度压缩只作用于代码正文，不再改变缩进宽度。真实项目第 3 页 Python 和第 60 页 JavaScript 渲染抽检层级稳定，仍为 60 页、每页 50 行、无源码行号。

## 2026-07-11 源码工程真实性与多样性升级

- 修复补足 3000 行源码时一次性生成超大 `business_workflow_service` 的问题。Python、JavaScript、C# 的补足逻辑现在按业务模块生成多个独立 Workflow Orchestrator，单个文件目标约 180–420 行，不再由一个 2000 行以上文件垄断前 30 页。
- 场景方法不再只复制同一段状态赋值模板，而是按模块交替生成查询筛选、审核分支、状态统计、逾期聚合、CSV 导出和状态流转等不同控制流；生成后的 Python 文件已通过 `py_compile`，JavaScript 文件全部通过 `node --check`。
- `.source-material-order.json` 现在是源码鉴别材料的权威读取清单；React 截图工程和后生成的超长单行 CSS/JSX 不再被自动追加到后 30 页，避免视觉资产混入业务源码材料并造成分页溢出。
- 新增源码多样性硬门禁 `source_material_diversity_ready`：前 30 页和后 30 页必须分别覆盖至少 4 个源码文件，单文件占选定 3000 行的比例不得超过 35%，唯一代码行比例不得低于 16%；不满足时停止交付。
- 矿山项目重建结果：源码总有效行 7300，前 30 页覆盖 8 个文件，后 30 页覆盖 23 个文件，最大单文件占比 11.47%，唯一代码行比例 25.50%，PDF 仍为 60 页且每页 50 行；第 1、10、30、31、45、60 页渲染抽检通过，最终 `ready_for_delivery=true`、`findings=[]`。

## 2026-07-11 SQLite 持久化与生成项目测试

- Python 生成工程已从进程内列表升级为 SQLite 持久化：新增统一数据库连接、事务提交/回滚、迁移执行器和 `migrations/001_initial.sql`，数据在 Repository 重新实例化后仍可读取。
- 每个业务模块生成独立 Repository，Service 负责字段校验、重复编码拦截和业务汇总，Repository 负责参数化 SQL、行对象映射和增删改查，避免路由、业务规则与数据库访问混在同一文件。
- 生成工程随包生成 `tests/test_persistence.py`，覆盖数据写入后重新打开 Repository 仍可查询、重复业务编码被 Service 拒绝；矿山项目生成测试 2 项通过，FastAPI TestClient 对 `/health`、新增设备和关键字查询的接口 smoke 均返回 HTTP 200。
- 生成器新增持久化硬门禁及报告字段：任务声明需要持久化时，数据库、Repository、迁移脚本或自动化测试任一缺失都会触发 `source_persistence_not_ready` 并停止交付；`materials_manifest.json` 同步记录引擎和文件数量。
- 修复源码对齐补行可能截断多行 Python 函数的问题，改为始终可独立编译的单行对齐片段；生成后的全部 Python 源码已通过编译检查。
- 矿山项目最终源码共 7250 行，源码材料仍为严格 60 个物理页、每页 50 行；前后 30 页分别覆盖 12/29 个文件，最大单文件占比 8.90%，唯一行比例 27.57%。第 1、50、55、60 页已渲染抽检，后段能看到真实 SQLite `INSERT`、`UPDATE`、连接事务和 Repository 映射代码；最终 `ready_for_delivery=true`、`findings=[]`。

## 2026-07-10 至 2026-07-11 本次修复记录

- 已按最新要求把正式 GPT 界面链路从“逐页独立 HTML”升级为“React + Vite 可运行前端工程”。默认 `SOFT_AI_FRONTEND_MODE=react-vite`：GPT 按全局 image2 风格参考图为每个截图路由生成独立 JSX/CSS 组件，本地 Vite 构建为真实运行资产，再由生成项目服务和 Playwright 打开各路由截图。旧 `stable-component-shell` 只保留为显式开发模式，不再是正式生成默认值；`llm-html/freeform-html` 也只作为兼容开关保留。
- React 工程已按终端类型分流：桌面/后台/GIS/工业控制台继续使用 `1280x720` 横屏工作区；手机 APP、小程序和手机游戏使用 `720x1280` 竖屏，提示词强制触控尺寸、移动导航和单手操作动线，禁止把桌面侧栏后台压缩成手机页面。生成后的 JSX/CSS、`App.jsx`、`package.json` 和 Vite 配置会复制到 `generated_source/frontend-app/`，构建资产仍发布到项目的 `/ui-prototype/` 供真实接口运行截图。
- 已把任务 seed 贯通产品蓝图、`visual_identity_spec`、image2 缓存键/最终提示词和每页 React `page_structure_seed`。新任务会得到新的产品角度、信息架构、视觉构图和页面主体拓扑；“保留蓝图重试”继续沿用原 seed，保证同一材料包风格一致且可断点续跑。旧视觉身份缓存因缺少当前 seed 会自动失效。
- 已移除 image2 全局参考提示中的固定“侧栏 + 指标卡 + 筛选 + 表格”骨架要求，改为按业务和 seed 在双栏工作台、监测墙、流程台、档案台、任务板、地图联动、卡片流等构图中自主选择。React 页面提示同时要求相邻路由至少在主内容拓扑、首屏焦点、工具区位置、数据呈现和操作路径中有两项明显不同。
- 已修正重复度门禁时机：蓝图阶段只检查视觉身份历史相似度和页面角色覆盖，不再读取失败输出目录中的旧 HTML；React 组件全部生成并构建后，再读取对应 JSX/CSS 计算材料包内部结构相似度，避免“重抽视觉身份但一直比较旧页面”的死循环。
- Electron 生成子进程会传入内置 Electron/Node 和打包后的 `node_modules` 位置，React/Vite 构建不要求客户另装 Node。新增 `tests/test_react_frontend_codegen.py`，已验证手机 APP 可生成两个独立 React 组件、完成 Vite 构建、输出共享运行资产和带移动 renderer 的路由入口。
- 已修复正式截图链路中首页和统计页可能在 `module_key` 为空时请求过期示例接口的问题。AI 生成页面现在会注入本次确认蓝图的前四个实际模块 key；当前运行脚本升级为 `v5`，会据此请求生成项目的真实业务接口，不再回退到固定的交通样例路由。对 AI 页面可能生成的空地图标记节点也增加了保护，不会因尝试写入不存在的子节点而中断截图。没有可用模块 key 时会给出明确错误，而不会伪装成接口无数据。
- 已确认此前失败的“智能粮食库监测系统”并非模型或项目服务异常：其真实 `config_maintenance` 接口返回 HTTP 200，而旧首页脚本请求的示例接口均为 404。修复后用该任务生成的 Node 项目和 Playwright 实测，首页可以命中真实接口并将返回记录写入可见页面区域。
- 已修复 2026-07-10 继续失败的 `ui_operation_result_evidence_missing` 门禁误杀：正式 AI 页面现在注入运行脚本时，会同步写入客户可见的“处理结果 / 操作日志 / 刷新统计口径”证据条；浏览器截图阶段若真实业务接口返回记录，会继续用接口编号和状态覆盖该证据。二次复查发现部分 AI 页面已有 `.operation-result` 但只是“仍需确认测点”等不完整结果文本，现已改为只有静态可见文本同时包含操作结果、操作日志和刷新统计证据时才跳过补块。最终质检读取静态 HTML 时不再漏掉运行时才生成或不完整的操作结果证据。
- 已修复客户反馈的“界面风格不统一、文字超出和重叠”问题：AI 页面生成提示词现在要求同一材料包共用同一套字体、主色、侧栏/顶栏外壳、按钮、状态标签和表格密度；截图注入阶段会替换旧 `soft-ai-runtime-guard`，把后台页面统一约束到 `1280x720`，并对按钮、状态标签、表格单元格、长编号、指标数字、当前记录卡等加入 `nowrap + ellipsis + 固定行高` 防溢出规则。Playwright 截图前新增可见文字布局门禁，发现按钮/标签/表格/长编号等可见文字越界或可见溢出会直接失败，避免坏图进入手册。
- 已修复上述布局门禁对 1-2px 底部亚像素越界过严导致的误杀：`矿山机械设备运行状态监测与智能维护管理系统` 的 dashboard 页中 `span.tag red: 未开始` 实际文字宽高未溢出，仅标签底边落在 720px 视口外约 2px；现已将视口越界容差调整为 4px，继续拦截明显裁切，但不再因边框/亚像素舍入中断生成。已用该失败 dashboard HTML 复测布局门禁通过。
- 已修复同一任务 `device_profile` 页底部 `.opbtn` 操作按钮被 720px 截图裁切的问题：`加入关注 / 缓存摘要 / 审计记录` 原始按钮高度 28px，位于 700-728px 区间，确实会被截掉；运行保护样式现已对 `.opbtn` 单独压缩为 20px 紧凑按钮。已用失败页副本复测，三枚按钮位置调整为 684-704px，布局门禁通过。
- 已修复 2026-07-11 `statistics` 页因运行证据固定浮层覆盖原统计表格而失败的问题：运行脚本 `v5` 会清除旧版固定证据条，把操作结果嵌入现有卡片标题或既有结果区域；无 `data-field` 的普通表格也会按表头绑定接口编号、状态和更新时间。接口数据或操作结果已经可见时不再追加底部浮动记录卡。已用本次失败的真实 `statistics.html`、生成项目 Node 服务和 Chromium 复验，6 个接口成功、首列显示 `DE-YW-1001`、浮动卡数量为 0、操作证据为普通文档流定位，最终布局问题为 0。
- 已对该失败任务现有 27 张缓存页面执行不调用 GPT 的完整浏览器扫检：全部页面自动升级到运行脚本 `v5`，`runtime_api_ready` 27/27、接口数据可见 27/27、布局问题页面 0、浮动记录卡页面 0，累计命中 61 个真实业务接口。
- 已修复源码鉴别材料“代码页没有排满”的观感问题：源码材料仍保持每页严格 50 行、A4、页眉右上页码和无空源码行，但正文行距从 `14.2pt` 调整为 `15.2pt`，报告新增 `source_font_size_pt`、`source_line_spacing_pt`，填充策略更新为 `exact-50-lines-tight-a4-fill-no-blank-source-lines`，让 50 行更接近铺满版心。
- 已移除失败报告内重复渲染的“保留蓝图重试 / 继续修改蓝图 / 新建任务”按钮，失败状态下仅保留底部固定操作栏，避免重复语义和重复焦点。
- 已新增 `tests/test_dashboard_runtime_api.py`：以空 `module_key`、空地图标记、已有但不完整的 `.operation-result`、普通统计表格和临时业务接口进行浏览器回归，断言缓存脚本会升级到 `v5`、真实模块 key 已注入、接口成功、业务记录可见、没有浮动记录卡，且静态 HTML 可被最终质检识别为具备操作结果证据。
- 已用此前失败任务的 `config_maintenance_operation_2_2` 原始页面、其真实 Node 服务和 Playwright 复验：旧缓存页面可自动升级到当前脚本，存在 3 个空地图标记时仍有 2 个业务接口成功且数据可见。

本次验证：`python -m py_compile backend\\generate_materials.py backend\\softcopyright\\generator.py backend\\softcopyright\\docgen.py backend\\softcopyright\\screenshots.py backend\\softcopyright\\llm_manual.py backend\\softcopyright\\ai_frontend_codegen.py`、`python -m unittest discover -s tests -p "test_*.py"`（7 项通过，包含 React/Vite 手机端构建回归）、真实失败 HTML 副本升级后的 Chromium 布局门禁、源码 DOCX 临时生成行距检查、`node --check desktop\\electron\\main.cjs` 和 `npm.cmd run build` 均已通过。未重新发起完整 GPT/image2 任务，避免额外消耗模型额度；下次新建任务或“保留蓝图重试”会使用 React 界面链路。

下一步：重启桌面应用后建议先新建一个任务验证全随机 React 链路；若要保留已确认业务蓝图，可对失败任务执行“保留蓝图重试”，旧固定壳页面不会被 React 组件缓存复用。若仍失败，请保留新的 `generation-failure.json` 和 `generated_source/frontend-app/`，错误会对应 React 组件生成、Vite 构建、真实接口或截图质量的具体阶段。

已完成能力：

- 生成真实源码工程目录，而不是直接拼接 Word 代码页。
- 从源码工程提取源码鉴别材料。
- 生成软件说明书、源码材料、信息表、材料清单和生成报告。
- 生成 Word、PDF 和 ZIP 材料包。
- 支持 Java、JavaScript、Python、PHP、C#、C++、HTML 等语言入口。
- 支持 15 类产品类型。
- 当前正式生成只支持 GPT / OpenAI-compatible 模式；名称理解、产品蓝图、技术架构、说明书正文和界面蓝图均要求由 GPT 成功生成，关键阶段失败时明确报错重试，不再切换到默认模板生成。
- GPT 模式已升级为“产品方案优先”生成：先生成产品身份定位，再生成业务对象、流程、指标、规则和模块明细；说明书、源码工程、界面截图、信息表共享同一份产品方案，减少每次生成像同一套模板的问题。
- GPT 模式已新增自动技术架构选择：产品蓝图完成后由 GPT 从受支持的真实项目架构目录中选择 Spring Boot + Web 控制台、ASP.NET Core、移动端前后端分离、FastAPI 数据分析、中间件网关、嵌入式边缘或系统服务等架构；本地强校验 `selected_key` 和 `source_strategy`，通过后再驱动源码工程生成。
- 2026-06-29 针对“风月听歌”生成耗时长且失败的问题完成一轮加速与诊断优化：默认生成策略从极保守串行切换为 `balanced` 平衡加速，仍使用 `gpt-5.5`，但产品蓝图、说明书正文和 UI 蓝图分批默认启用 2 路并发；蓝图质量目标默认调整为 86 分，保留 `SOFT_GENERATION_PROFILE=authenticity-first` 可切回最高保守质量档。
- 正式生成现在默认设置 `SOFT_LLM_BATCH_WORKERS=2`、`SOFT_LLM_RETRY_COUNT=1`，并为 image2 图片生成单独设置 `SOFT_LLM_IMAGE_RETRY_COUNT=3`；文本请求避免长时间重复阻塞，图片请求遇到 429/5xx/超时会短暂重试。每次任务会在输出目录内写入 `llm_trace.jsonl`，即使早期 GPT 或 image2 阶段失败也能定位具体请求耗时、状态码和错误摘要。
- 2026-06-29 已修复“生成说明书模块章节 4/4”阶段因 NewAPI/GPT `504 Gateway Time-out` 直接失败的问题：说明书公共章节或模块批次失败、批次返回缺少有效段落时，会自动拆分为单章节/单模块 GPT 请求继续补齐；仍为 GPT-only 生成，不回退默认模板。客户界面、后端 trace 和 Electron 主进程已统一脱敏错误文本，不再暴露 GPT Base URL、`/chat/completions` 请求地址或 token。
- 2026-06-29 已新增 GPT 阶段缓存/断点续跑基础能力：产品蓝图、技术架构、说明书正文和 UI 蓝图成功后写入 `output/.stage-cache/{cache_key}`；失败后点击“保留蓝图重试”会复用同一确认蓝图、模型、生成策略对应的缓存阶段，跳过已成功的 GPT 蓝图/架构/说明书正文/UI 蓝图请求。缓存不进入客户材料包，不包含 API Key 或 Base URL。
- 2026-07-02 已修复“保留蓝图重试”后仍提示“源码和截图模块 key 仍为占位命名”的问题：确认蓝图和旧阶段缓存中的 `confirmed_*`、`semantic_*`、`business_module_*` 会统一重写为业务语义 key；说明书正文缓存和 UI 蓝图缓存会按模块标题同步迁移到新 key，避免源码工程、接口路径、截图文件名继续沿用占位命名。
- 桌面端结果明细已新增“阶段复用”卡片，会显示本次命中的缓存阶段，例如“产品蓝图、技术架构、说明书正文、界面蓝图”，并展示短缓存键，便于客户知道重试时省掉了哪些耗时步骤。
- Electron 正式生成和蓝图生成已改为通过子进程环境变量传递 GPT API Key / Base URL，不再拼接到 Python 命令行参数，避免进程诊断时泄露敏感配置；客户 UI 按当前需求常驻展示并允许修改 GPT 请求地址，日志和失败报告仍保持脱敏。
- Electron 桌面端首页已简化，核心输入在首页，高级项折叠。
- 高级设置展示 GPT 请求地址、模型套餐、余额、模型名称和 API Key；客户预制安装包会预置网关地址，客户也可以直接查看和修改。
- 支持预置配置文件 `config/production.json`。
- 支持 OpenAI-compatible / NewAPI 网关。
- 支持 NewAPI `/api/usage/token` 余额读取。
- 生成完成后自动刷新余额。
- 说明书正文模型生成已拆分为概述、登录主界面、各功能模块、统计、安全、FAQ 等小请求，降低 NewAPI 大请求 `504 Gateway Time-out` 风险；当前 GPT-only 模式下批次失败会自动缩小到单章节/单模块继续生成，只有拆分重试仍失败时才提示保留蓝图重试。
- GPT 生成默认策略已切换为平衡加速：`SOFT_LLM_BATCH_WORKERS` 默认值为 `2`，产品方案、说明书和截图蓝图使用小批次并发；如需最高保守质量档，可设置 `SOFT_GENERATION_PROFILE=authenticity-first` 和 `SOFT_LLM_BATCH_WORKERS=1`。
- 桌面端已收敛为 GPT 唯一生成模式。普通开发包和客户预制安装包均可在 UI 中查看和修改请求地址、模型名称和 API Key，网关地址可由本机配置或交付包预置。
- C# 源码生成器已从通用短模板扩展为 ASP.NET Core 风格工程，可生成 Controller、Service、Repository、Model、Query、统计、审计、导出和操作追踪等多文件源码，并满足 3000+ 行源码鉴别材料目标。
- 已支持生成登录页、系统首页、功能模块页和统计页界面截图，并插入软件说明书；正式 GPT 模式必须经 gpt-image-2 全局视觉风格参考图、按图生成可运行页面代码、生成项目服务运行截图三段链路，Playwright/Chromium 或项目服务不可用时会失败，不再使用本地图像兜底。
- GPT 模式下已支持由模型生成 `ui_blueprint.json`，并由本地强校验保证截图渲染器和 `view_type` 符合软件类型；例如游戏软件只能生成游戏登录、主界面、关卡、棋盘、道具、结算等游戏截图，不会混入后台管理表格页。
- GPT UI 蓝图已从单个长 JSON 请求拆分为“界面风格 + 分批截图内容”小请求，截图 key、renderer、view_type 由本地规则固定，GPT 只补标题、图注、组件和样例数据，降低 504 并减少界面跑偏。
- `generation_report.json` 已新增材料一致性检查，统计产品方案中的模块标题、业务对象、统计指标是否出现在说明书/截图文本中，并检查源码工程是否包含对应模块 key 和 `product-blueprint.json` 索引。
- 已增强 GPT 返回值清洗：当模型把 operations、data_fields、rules 等数组项返回为对象时，会抽取 `name`、`title`、`field`、`rule` 等字段，不再把结构化残片写进说明书或截图。
- 手机 APP、小程序和手机游戏统一使用 9:16 竖屏画幅，输出尺寸为 720×1280；桌面软件、后台系统、GIS、云平台和 Windows 客户端统一使用 16:9 横向画幅，输出尺寸为 1280×720。报告会记录每张截图宽高，并增加 `ui_screenshot_aspect_ratio`、`ui_mobile_portrait_match` 检查项。
- 非游戏软件已补齐行业化后台截图画像，覆盖 APP、教育、金融、医疗、地理信息、云计算、信息安全、大数据、人工智能、VR、5G、小程序、物联网、智慧城市 14 类；每类截图会使用对应指标、筛选项、业务对象、状态标签、流程和趋势面板。
- 界面截图原型已并入生成源码项目：正式 GPT 模式会把 React JSX/CSS 工程写入 `generated_source/frontend-app/`，把 Vite 构建资产、路由入口、`ui_blueprint.json`、`prototype-manifest.json`、`index.html` 和 `README.md` 发布到 `generated_source/ui-prototype/`；Playwright 从项目服务渲染 PNG，PNG 仍输出到 `ui_screenshots/` 供说明书插图使用，最终 ZIP 仍只包含 5 个客户交付文件。
- 生成源码项目已补齐第一版可启动前端入口：Java/Spring Boot 项目会把原型同步到 `src/main/resources/static/ui-prototype/`，C#/ASP.NET Core 项目会同步到 `wwwroot/ui-prototype/`，JavaScript/Python 项目会通过本地静态路由暴露 `/ui-prototype/index.html`；报告会输出 `ui_project_entry_*` 检查项、入口 URL 和启动命令。
- 非游戏软件截图已从单一后台壳扩展为多种布局变体：金融/信息安全走 `risk` 风控控制台，地理信息/物联网/5G/智慧城市走 `map` 地图态势，大数据/人工智能/云计算/VR 走 `pipeline` 链路流程，教育/医疗/APP/小程序走 `workflow` 工单流程。生成报告会记录 `ui_layout_variant`，便于验收不同类型是否真正拉开。
- 2026-06-29 已完成“正式软件感截图”渲染层升级：桌面管理类截图增加真实应用外框、面包屑、顶部用户区、通知/刷新/环境状态、工作区标签、表格复选框、业务编号、分页、行内操作、选中记录详情、处理轨迹、附件与导出状态等正式业务系统细节；同时继续使用行业化 `design_dna` / `layout_signature` 驱动布局差异，避免所有软件截图像同一套模板。
- 2026-07-05 针对客户反馈“手册截图仍模板化、不同软件名界面一样、二级界面类似”完成后台模块截图差异化升级：UI 蓝图不再把所有模块页固定为 `admin_module`，而是按软件名称、产品类型、行业 brief、模块标题、字段和操作分配 `admin_map`、`admin_pipeline`、`admin_board`、`admin_case`、`admin_risk`、`admin_form`、`admin_matrix`、`admin_table` 等细分页面角色；截图渲染器也按角色生成地图态势、流程链路、看板、档案台、风险复核、配置表单、指标矩阵和台账详情等不同二级界面，减少不同类型软件共用同一套后台布局的问题。
- 2026-07-05 进一步查看客户参考文件和现有下拉分类后确认：仅靠后台模块 `view_type` 分流仍不足以达到客户样本真实感，而且不能把“产品形态”固定理解为四类。后续应拆成三层：软著软件大类（应用软件、嵌入式软件、中间件、操作系统）、产品/行业小类（APP、游戏、教育、金融、医疗、GIS、云计算、信息安全、大数据、人工智能、VR、5G、小程序、物联网、智慧城市等）和体验形态/终端范式（移动端、小程序/H5、桌面 Web、传统 Windows、专业指挥台、工业 HMI、GIS/地图、三维/BIM/VR、数据驾驶舱、运维控制台等，可扩展）。已更新 `docs\customer-reference-sample-analysis-20260705.md`，建议后续切换为“产品文档/体验规格 -> 视觉稿规格 -> 可运行 UI 原型 -> 截图 -> 手册反写”的链路。
- 2026-07-05 下一阶段已先落地“产品体验规格”基础层：新增 `backend/softcopyright/product_experience.py`，按软著软件大类、产品/行业小类、软件名称、业务补充、产品蓝图和行业子类型推断 `product_experience_spec`，覆盖 `mobile_app`、`mini_program`、`h5_mobile`、`mobile_game`、`desktop_web`、`legacy_windows`、`gis_map`、`industrial_hmi`、`data_dashboard`、`cloud_ops_console`、`ai_pipeline`、`vr_3d`、`embedded_panel`、`middleware_console`、`os_console`、`security_soc`、`finance_risk_console`、`medical_workstation`、`education_lms` 等可扩展体验形态。UI 蓝图会把该规格写入 `design_brief.product_experience_spec`，并据此决定 `renderer`、`layout_family`、`nav_model`、`workspace_shape`、目标终端和视觉方向；旧缓存若缺少或不匹配该规格会被拒绝复用。`generation_report.json` 已新增 `ui_software_category`、`ui_product_type`、`ui_experience_shape`、`ui_terminal`、`ui_experience_shell`、`ui_family`、`ui_viewport_mode`、`ui_experience_match_ready` 等检查项，原型 `prototype-manifest.json` / `README.md` / `project-entry.json` 也会记录体验形态和目标终端。
- 2026-07-05 已继续落地“同类型软件界面差异化保障计划”：新增 `backend/softcopyright/ui_visual_identity.py` 和 `backend/softcopyright/ui_similarity.py`，为每次 UI 生成建立 `visual_identity_spec`，字段包含 `identity_signature`、`visual_seed`、`palette_key`、`layout_variant`、`nav_model`、`workspace_shape`、`login_pattern`、`dashboard_composition`、`module_composition_cycle`、`table_density`、`chart_style`、`surface_style`、`component_rhythm`。种子固定吸收软件名称、软件大类、产品小类、体验形态、业务补充、模型供应商/模型名、技术架构、模块标题、业务对象和统计指标，同一产品小类只要名称/业务不同，也会稳定生成不同视觉身份。
- 2026-07-05 UI 渲染端已开始消费视觉身份规格：后台 renderer 会按身份规格改变导航位置、工作区结构、表格密度、卡片表面、图表风格、页面 CSS class 和模块 view_type 轮换顺序；小程序/移动端、GIS 地图、工业 HMI/嵌入式、云运维/AI 链路、传统 Windows 客户端等壳体已加入差异化 CSS 与布局信号。`generation_report.json` 会写入 `ui_blueprint.visual_identity_spec`、`ui_visual_identity_signature`、`ui_visual_seed`、`ui_palette_key`、`ui_table_density`、`ui_chart_style`、`ui_surface_style`、`ui_component_rhythm` 等检查项。
- 2026-07-05 已新增 UI 相似度硬门禁：生成本地 UI 指纹，比较 `renderer`、`experience_shape`、`layout_variant`、`nav_model`、`workspace_shape`、模块 `view_type` 序列、页面角色、组件 token、配色族和图表类型；与同 `product_type + experience_shape` 最近 50 个成功样本比较，`max_similarity >= 0.78` 时自动换视觉身份重生成，最多 3 次，仍不达标则失败。无历史样本时也会检查当前包内后台模块页面角色数量，模块少于 4 个要求至少 3 种角色，否则报 `ui_layout_role_count_low`。仅在材料最终校验成功后写入 `output/.ui-fingerprint-history/index.json`，失败样本不会污染基线，历史文件不进入客户 ZIP。
- 2026-07-05 已把 GPT/NewAPI 正式流程和显式本地模板流程分清：GPT 模式下名称理解、产品蓝图、技术架构、说明书正文和 UI 蓝图均要求模型成功返回，失败直接报错，不回退默认模板；`local-template` 仅作为用户明确选择的无 token/开发验证模式保留，不作为 GPT 失败兜底。旧 UI 缓存缺少 `visual_identity_spec.identity_signature` 时会被拒绝复用。
- 2026-07-06 已按客户反馈接入 image2 视觉参考稿阶段，后续在 2026-07-08 调整为更稳定的“全局风格参考图”模式，并在 2026-07-11 将页面实现升级为 React：正式 GPT 流程现在变为“GPT 生成产品/界面蓝图 -> GPT 生成全局视觉风格提示词 -> gpt-image-2 生成 1 张内部风格参考图 -> 根据参考图生成业务工程源码与运行接口 -> GPT 读取同一张参考图生成各路由 JSX/CSS -> Vite 构建 React 工程 -> 启动生成源码项目服务 -> Playwright 对运行路由重新截图 -> 手册插入最终运行截图”。参考图只作为视觉依据，不能直接进入手册，也不能被页面直接嵌入为背景图或 `<img>`。
- 2026-07-06 GPT 正式流程新增视觉参考硬门禁，2026-07-08 已从逐页参考图改为全局风格参考图并前移到源码工程之前：`prepare_ui_visual_reference()` 会先在 `generated_source/ui-prototype/visual-references/` 下写入 `style_reference.prompt.json`、`style_reference.png` 和 `visual-reference-manifest.json`；缺少全局风格提示词、缺少 gpt-image-2 参考图、或 HTML 未按参考图生成时会直接失败。生成业务工程时会写入 `ui-visual-reference-contract.json`，`generation_report.json` 新增 `ui_visual_reference_before_source_ready` 和 `source_visual_reference_contract`，同时继续保留 `ui_visual_reference_mode`、`ui_visual_prompt_ready`、`ui_visual_reference_ready`、`ui_visual_style_reference_ready`、`ui_visual_reference_count`、`ui_visual_reference_source`、`ui_visual_reference_image_model`、`ui_visual_reference_retry_count`、`ui_visual_reference_failed_page`、`ui_visual_reference_to_code_ready` 等检查项，并新增 `ui_visual_reference_missing`、`ui_visual_reference_to_code_missing` 校验发现。
- 2026-07-06 模型配置已支持独立图片模型/API：默认图片模型名为 `gpt-image-2`，可通过 `SOFT_MODEL_GPT_IMAGE_NAME` 或 `SOFT_MODEL_IMAGE_NAME` 配置；如需与文本 GPT 使用不同网关，可配置 `SOFT_MODEL_GPT_IMAGE_BASE_URL` / `SOFT_MODEL_GPT_IMAGE_API_KEY` 或通用 `SOFT_MODEL_IMAGE_BASE_URL` / `SOFT_MODEL_IMAGE_API_KEY`。桌面端只透传这些配置，不在客户 UI 暴露图片网关地址；`config/production.example.json` 已加入占位 `SOFT_MODEL_GPT_IMAGE_NAME: gpt-image-2` 和 `SOFT_LLM_IMAGE_RETRY_COUNT: 3`。
- 2026-07-07 针对客户现场 image2 返回 `503 Service Unavailable` 的失败，已补强严格 AI 流程下的图片阶段诊断：图片生成请求改为独立重试计数 `SOFT_LLM_IMAGE_RETRY_COUNT`，仅对 429/5xx/超时类临时错误等待重试；400/401/403/404 等配置或权限错误会快速失败。失败时仍不走模板兜底，会把 GPT 视觉提示词、失败页、图片模型名、重试次数、脱敏错误和 `visual-reference-manifest.json` 写入 `generated_source/ui-prototype/visual-references/`，并通过桌面失败报告展示“保留蓝图重试”的可操作原因。
- 2026-07-07 服务器诊断确认：现场 image2 阶段 503 的直接原因是 NewAPI `default` 分组没有可用 `image2` 渠道，启用渠道实际开放的图片模型名为 `gpt-image-2`；本机真实配置 `config/production.json` 与 `config/desktop.local.json` 已补充 `SOFT_MODEL_GPT_IMAGE_NAME=gpt-image-2`，并将 outline 文本模型保持为 `gpt-5.5`。后续如仍失败，优先排查渠道 1 上游 502/超时，而不是回退模板兜底。
- 2026-07-07 已做真实图片接口 smoke test：原始 `image2` 请求仍返回 `model_not_found / No available channel`；当前配置模型 `gpt-image-2` 请求成功返回 PNG，耗时约 56 秒，测试图保存到 `output-image-smoke/gpt-image-2-smoke.png`。这说明图片生成链路本身已通，后续生成应使用 `gpt-image-2` 或在 NewAPI 中配置 `image2 -> gpt-image-2` 模型映射。
- 2026-07-07 桌面端新增生成任务中止能力：点击生成后底部主按钮会切换为“中止生成”，再次点击会通过 `cancel-generation` IPC 停止正在运行的蓝图或材料包生成任务；Windows 下使用 `taskkill /T /F` 结束 Python 进程树，避免 Playwright、项目服务等子进程残留。中止结果会以 `cancelled=true` 返回，界面显示“已中止”状态并保留当前蓝图，可继续修改或重新生成。
- 2026-07-08 桌面端新增第一版顺序生成队列：渲染层负责排队和串行调度，Electron 主进程仍保持单 `activeGenerationTask`，避免并发任务抢占同一个 Python/Playwright 生成链路。队列支持两种入队方式：已确认蓝图会快照当前表单和蓝图后入队，快速追加的软件名称会在轮到该任务时先生成 GPT 蓝图再生成材料包；运行中可继续追加后续任务。队列 UI 改为紧凑文字流/行列表，展示等待、蓝图生成、材料生成、完成、失败和中止状态；当前任务失败或被中止时会暂停后续队列，用户确认后再继续，防止配置或网关异常导致后续任务连续失败。
- 2026-07-08 针对“重启软件后没有上一次失败任务信息，无法重试”的问题补齐队列持久化和失败任务恢复：桌面端会把队列任务快照写入本机 `localStorage`，仅保存软件名、已确认蓝图、队列状态、最近过程日志、输出路径和脱敏错误摘要，不保存 API Key 或请求地址；应用重启后，等待/失败/中止/成功任务会恢复显示，重启前正在运行的任务会恢复为“等待中”并暂停队列，避免自动消耗模型额度。Electron 主进程新增 `list-recoverable-tasks`，会扫描最近输出目录中有 `generated_source/product-blueprint.json` 和 `llm_trace.jsonl`、但没有最终 `generation_report.json` 的未完成任务，在 UI 中显示“恢复最近失败任务”。当前失败样本 `测绘空间三维模型编辑平台-20260708-055437-5090` 已验证可恢复：识别到 `VR软件`、8 个模块、失败阶段 `ai_frontend:dashboard`，且全局风格参考图已生成。
- 2026-07-09 恢复任务条新增删除入口：每个“恢复最近失败任务”旁增加紧凑删除图标，点击后不会删除输出目录和诊断材料，而是在对应输出目录写入 `generation-recovery-dismissed.json`，后续重启或重新扫描时自动隐藏该恢复记录。
- 2026-07-09 修复恢复/重试旧任务时偶发 `statistics_module.html` 缺失导致 AI 界面代码生成失败的问题：`generate_ai_frontend_pages()` 现在会在写入每个 GPT 生成 HTML 页面前强制创建 `generated_source/ui-prototype` 父目录，并在 `html_path` 缺失时给出明确错误，避免旧恢复状态或中间目录被清理后直接抛 `[Errno 2] No such file or directory`。
- 2026-07-09 桌面端队列追加入口已合并到底部主输入框：队列面板不再额外显示“追加下一个软件名”输入行；生成中底部输入框为空时按钮为“中止生成”，输入新软件名或补充要求后按钮自动切换为“加入队列”，避免同屏两个输入框造成理解负担。
- 2026-07-09 修复“禾马兔在院病人监测系统”失败率高的问题：根因是 APP 产品类型被当成强业务类型，医疗护理语义被误分到“社区生活服务APP”；同时“班次交接”中的“班次”误触发交通运输领域检查，导致移动医疗 UI 蓝图被判为软件类型不匹配。现已让医疗/云等业务语义优先于 APP/小程序终端形态，新增“住院患者监测护理系统”医疗子类，交通运输判断不再因单独“班次”命中；并把 UI 类型不匹配前移到视觉参考阶段自动重生成，坏的恢复 UI 蓝图会被丢弃，只复用产品蓝图。
- 2026-07-08 针对 `测绘道路工程测量管控APP-20260708-062503-9835` 继续失败完成复盘和修复：本次不是 `gpt-image-2` 或界面截图失败，实际链路已生成全局风格参考图、9 个 AI HTML 页面和 9 张运行截图，最终停在 `manual_pdf_text_density_not_ready`，原因是 `pypdf` 抽取第 2 页 29 行、第 19 页 28 行，但两页正文字符数分别为 682/698，属于近阈值高文本页。`analyze_manual_pdf_text_density()` 已增加“差 1-2 行且字符数充足”的软通过记录，报告写入 `manual_pdf_text_density_soft_pass_count/pages`，真实低密度页仍会失败；`validation_report.json` 和 `materials_manifest.json` 已同步该字段。断点重试同时修复两个状态问题：最终校验失败会写 `generation-failure.json` 和 `generation-state.json status=error`，成功后清理旧失败文件；桌面端恢复扫描不再因存在 `generation_report.json` 直接跳过未交付目录，只跳过 `ready_for_delivery=true` 或 `status=success` 的目录。UI 相似度门禁在 `--resume-output-dir` 场景会忽略当前任务自己的历史指纹，避免同一输出目录重试时把自己判为高度相似并强制重新生成视觉身份。已用同一输出目录无 GPT 环境变量断点复跑验证：阶段缓存命中 `blueprint/technical_architecture/manual_content/ui_blueprint`，`generation-state.json=success/done/100`，`validation_report.ready_for_delivery=true`，`findings=[]`，最终材料包为 `output\测绘道路工程测量管控APP-20260708-062503-9835--材料包.zip`。
- 2026-07-08 已重新打包客户版 NSIS 安装器：执行 `npm run pack:win:customer` 成功，流程包含 `prepare:runtime`、`prepare:playwright`、`prepare:python`、`prepare:libreoffice`、`vite build` 和 `electron-builder --win nsis`。新安装器为 `release\customer-installer\Soft Copyright Generator Setup 0.1.0.exe`，大小约 601.75 MB，生成时间 2026-07-08 16:49:39；安装包资源已包含 `backend`、`config/production.example.json`、客户预置 `config/production.json`、`ms-playwright`、`python-runtime`、`libreoffice` 和 `requirements.txt`。同目录下旧的 `Soft Copyright Generator Setup 0.1.0.zip` 时间戳为 2026-06-08，不作为本次最新交付物。
- 2026-07-08 修复 AI 页面代码已生成后、注入运行数据脚本时报 `bad escape \d` 的本地处理错误：运行数据脚本中包含 JavaScript 正则 `\d{3,}`，原先用 `re.sub(..., script + "</body>", html)` 会让 Python 正则替换字符串二次解释反斜杠，从而在截图阶段失败。现已把运行脚本、AI HTML `<title>` 和 runtime guard 的动态注入改为 lambda replacement，保留原始反斜杠内容。已用临时 HTML 直接调用 `_inject_runtime_script_into_ai_page()` 验证，注入后保留 `\d{3,}` 且不再报错。
- 2026-07-08 针对“风格图到界面截图”阶段偶发 `ProxyError / Unable to connect to proxy` 失败完成修复：`OpenAICompatibleProvider` 的文本和图片请求默认使用 `requests.Session(trust_env=False)`，不再继承父进程或系统会话中的 `HTTP_PROXY` / `HTTPS_PROXY`；如现场确实必须走代理，可显式设置 `SOFT_LLM_USE_SYSTEM_PROXY=true`。文本 GPT 请求遇到连接、代理、超时或 5xx/429 类临时错误时会按退避等待后重试，桌面正式生成默认 `SOFT_LLM_RETRY_COUNT` 从 1 提高到 3；仍保持 GPT-only，不回退模板。已用坏代理环境变量做最小 GPT smoke，验证 provider 会忽略坏代理并直连成功。
- 2026-07-07 针对最新现场 `504 Gateway Time-out` 继续排查到外层 Nginx 默认 `proxy_read_timeout=60s`：NewAPI 容器内多次 image2/gpt-image-2 请求实际在 79-94 秒返回 200，但客户端已被 Nginx 截断。服务器 `smoke2.learn-flow.cn` 已把图片生成相关反向代理超时调整为 300 秒并 reload；同一失败登录页视觉提示词复测成功，参考图保存到 `output-image-smoke/login-after-nginx-timeout-fix.png`。本地生成端同步新增 `SOFT_LLM_IMAGE_TIMEOUT_SECONDS`，默认 220 秒、上限 360 秒，Electron 会传入子进程，`config/production.example.json` 已给出占位配置。
- 2026-07-07 新增 image2 图片有效性门禁：`generate_image()` 保存 PNG 前会用 Pillow 检查尺寸、主色占比、有效内容面积、颜色层次、亮度方差，以及横/竖软件控件边界数量；HTTP 200 但返回空白、问号占位图或非软件界面图片时抛出 `GeneratedImageQualityError` 并按图片重试次数重新请求，仍不合格则失败，不插入模板或中间图。合格参考图的 `image_quality` 会写入 `visual-reference-manifest.json`，便于后续排查图片通道质量。
- 2026-07-07 追加真实烟测发现：`gpt-image-2` 链路在网络层可用，但上游仍可能以 HTTP 200 返回“问号占位图”；已用该坏图反测新门禁，结果会被判定为“缺少软件界面控件边界”并拒绝保存。真实医疗登录参考图 `output-image-smoke/login-after-nginx-timeout-fix.png` 通过同一门禁，质量摘要约为 `axis_edge_score=8`、`axis_edge_total=269`。
- 2026-07-07 针对继续失败的 `dashboard` 视觉参考稿，确认失败码为上游图片通道 `524`，本地之前未把 `524` 纳入临时错误重试，导致虽然配置了图片重试次数，但该页实际只请求 1 次即停止。已把 `520/522/523/524` 加入图片生成临时错误重试集合，并对发给 image2 的视觉提示词做长度控制；若首轮图片请求仍因上游超时失败，后续重试会逐步使用更短的同一业务提示词版本，以降低首页/看板类长提示词触发上游超时的概率；仍不使用模板或中间图兜底。
- 2026-07-07 服务器继续诊断确认：当前 NewAPI 可用图片渠道实际不足。渠道 #1 `maitokens` 对 `/v1/images/generations` 连续返回 Cloudflare `524` 或 `502`；临时启用备用渠道 #4 `MUSK` 后，NewAPI 能尝试该渠道，但上游返回 `403 Insufficient account balance`，随后回退 #1 仍失败。已将 #4 恢复禁用，避免每次图片请求多一次无效 403。结论：代码侧已经完成 524 重试、prompt 压缩和占位图门禁；若要完整跑通正式 GPT/image2 链路，需要修复 #1 上游或给 #4/其它图片渠道配置可用额度。
- 2026-07-07 根据上游透传配置再次实测：直接请求模型名 `image2` 仍返回 `503 / No available channel for model image2 under group default`；按正确模型名 `gpt-image-2` 请求能进入图片渠道，但渠道 #1 `maitokens` 连续两次返回 Cloudflare `524`。项目默认图片模型名、桌面端子进程默认值、README 与 `config/production.example.json` 已统一改为 `gpt-image-2`，避免无显式配置时误走 `image2`。
- 2026-07-07 已按服务器侧最小改法调整 NewAPI 图片路由：备份 `/home/ubuntu/cipher-customer-smoke2/data/one-api.db` 后，将 #4 `MUSK` 渠道启用并作为 `gpt-image-2` 主图片渠道，同时关闭 #1 `maitokens` 的 `gpt-image-2` 能力，保留 #1 的文本模型能力不动。修改后烟测不再等待 #1 的 524，而是直接命中 #4 并返回 `403 Insufficient account balance`；因此路由已生效，下一步需要给 #4 上游充值/恢复图片权限。
- 2026-07-07 因 #4 上游余额不足，服务器已恢复为 #1 `maitokens` 启用 `gpt-image-2` 能力、#4 `MUSK` 禁用图片能力；数据库 `channels` 与 `abilities` 均确认 #1 可路由。继续实测 #1 可返回 HTTP 200 图片数据，但原始返回分别出现“App 与 Tab 的区别”说明图和浅色纹理空白图，均不是软件界面视觉稿，当前 Pillow 图片有效性门禁会正确拒绝。结论：#1 不是没打开，而是该上游对 `gpt-image-2` 图片生成质量不稳定/疑似映射异常；正式流程应继续硬失败并提示修复或更换图片上游，不能用模板、废图或中间图兜底。
- 2026-07-07 根据客户指出“已生成图片，只是提示词不对”修正 image2 视觉提示链路：最终发给图片模型的提示词不再直接裸用 GPT 返回的 `visual_prompt`，而是本地强制包裹为“单张软件运行界面截图：软件名 - 页面名 / 模块名”，并注入目标终端、业务词、真实控件边界、表格/图表/地图/面板等正向要求；同时清洗 `App/Tab/image2` 等容易诱导说明图或内部词的表达，避免把负面词反复塞给生图模型。若最终提示词出现 `????` 乱码或仍包含 App/Tab 对比语义，会在请求图片模型前失败。使用 UTF-8 转义 smoke 确认新提示词有效且无乱码，随后真实请求 #1 返回 `524`，说明提示词跑题问题已处理，当前剩余风险仍是图片上游超时/质量波动。
- 2026-07-07 继续收紧图片提示词：最终发给图片模型的文本改为正向画面描述，不再把“说明图、海报、教程、概念对比”等负面词直接送入生图请求，防止图片模型反向抓关键词；图片重试阶段也会压缩为“单张真实软件运行界面截图”短提示，不再原样重发长提示。桌面视觉参考稿后续按客户要求统一为 16:9，手机 APP/小程序/游戏统一为 9:16；正式截图尺寸仍由运行后的 HTML/项目服务决定。实际 UTF-8 正向提示词 smoke 保存到 `output-image-smoke/positive-only-ui-prompt-utf8.txt`，内容无乱码；连续请求 #1 仍可能出现 `524` / 远端断连，说明当前阻塞主要在图片上游可用性。
- 2026-07-08 已把桌面端生成过程展示同步到当前严格截图链路：新增独立“生成风格参考图”阶段，阶段顺序变为“生成风格参考图 -> 业务后端与接口 -> 风格图到界面截图”，并展示“准备视觉参考页面清单 -> GPT 生成视觉提示词 -> gpt-image-2 生成视觉参考图 -> 根据参考图生成业务工程源码 -> GPT 按参考图生成界面代码 -> 运行生成项目并重截手册图”；后端事件进度同步调整为视觉参考 40/41/42/43、源码 44/45-49、界面代码与截图 50-60。因此界面上能明确看出参考图先于业务工程源码，最终手册截图来自生成代码运行后的 Playwright 截图。
- 2026-07-08 桌面端新增“过程对话”视图：把原始生成事件按角色翻译成更直观的气泡流，例如“业务分析、产品规划、文档撰写、工程生成、视觉设计、图片模型、前端生成、截图运行、校验打包”。该视图只展示可验证的执行动作、进度、耗时和产物路径，不展示模型隐含推理链；下方仍保留详细事件流和原始运行日志用于排错。
- 2026-07-08 针对“测绘实景三维建模系统”在第 3 张 `business_process_01` 视觉参考稿失败的问题完成诊断和修正：`llm_trace.jsonl` 显示该页前 3 次图片请求均为上游 `524`，第 4 次返回图片但被 Pillow 门禁判定为“缺少软件界面控件边界”，属于图片上游超时与非软件界面图混合失败。已将模块页图片提示改为 UI 骨架优先，默认压到约 720 字，并明确要求顶部栏、左侧导航、筛选工具栏、表格、卡片、图表、按钮和状态标签可见，地图/三维场景只能作为卡片内视窗；图片重试提示也改为更短的 620/520/460 字并强化软件控件边界，减少纯三维场景或纯地图跑偏。
- 2026-07-08 已按最新要求调整截图和视觉参考图尺寸规则：桌面软件、后台系统、GIS、云平台和 Windows 客户端统一使用 16:9，参考图默认 `1280x720`，Playwright 最终截图 `1280x720`；手机 APP、小程序和手机游戏统一使用 9:16，参考图默认 `720x1280`，最终截图 `720x1280`。图片请求重试时也保持比例，桌面依次降为 `1024x576`、`768x432`、`640x360`，手机依次降为 `576x1024`、`432x768`、`360x640`，不再退回方图。
- 2026-07-08 根据“像 Codex 一样展示文字执行过程”的反馈，桌面端生成过程默认视图从阶段大卡片、气泡卡片和事件卡片改为紧凑文字执行流：顶部一行显示当前状态、进度和耗时，下面用小字号阶段状态和逐行执行记录展示正在做什么；原始技术日志仍保留为折叠项，仅在排错时展开，减少生成区域占用。
- 2026-07-08 已按最新反馈调整生成顺序：不再先生成业务工程源码再生成参考图，而是先生成全局风格参考图，再根据参考图生成业务后端与接口，并在源码工程中写入视觉契约文件；正式 GPT 截图链路只先生成页面清单，不提前写业务工程源码或占位页面，真正的业务工程和 React JSX/CSS 都会在 gpt-image-2 全局风格参考图之后生成，并通过运行项目重新截图写入手册。
- 2026-07-08 针对“测绘无人机航测建模软件。”仍失败完成诊断：本次不是流程顺序问题，`visual-reference-manifest.json` 显示全局风格提示词已生成，但 image2 前 3 次请求均为上游 `524`，第 4 次返回内容被图片质量门禁判定为“缺少软件界面控件边界”，因此没有写出 `style_reference.png`，也不会继续生成业务工程源码。已将全局风格参考图提示改为“软件 UI 骨架优先”，强制顶部栏、导航、工具栏、筛选区、指标卡、表格、图表、按钮、状态标签和分页器占主体；GIS/三维/遥感视图只能在带边框标题栏的工作区面板内且面积不超过 35%。图片重试短提示同步强化“控件主体 + 地图面板限制”，并在图片质量门禁拒绝返回图时保存 `style_reference.rejected.png` 作为内部诊断文件，方便直接查看上游到底返回了什么；该 rejected 图不作为参考图、不进入正式 ZIP。
- 2026-07-09 针对“智能粮食库监测系统”视觉参考阶段误报失败完成修复：本次 `visual-reference-manifest.json` 仍是 `mode=style_reference`，流程没有退回逐页生图；桌面端显示的 `0/27 张参考稿` 是失败报告缺少 `ui_visual_reference_mode` / `ui_visual_reference_target_count` 后被前端按旧逐页模式误读，实际含义是 1 张全局风格参考图覆盖 27 个后续页面。被保存为 `style_reference.rejected.png` 的图片经复查是完整粮库监测软件看板，旧 Pillow 门禁因轴向边界阈值过严误判为非软件界面；现已加入复杂软件 UI 软通过条件，并支持在重试时恢复通过新门禁的 `.rejected.png` 为正式 `style_reference.png`，避免重复消耗 image2。失败报告和桌面提示已补齐 `ui_visual_reference_mode`、`ui_visual_reference_target_count`、`ui_visual_reference_applies_to_page_count` 和 `ui_visual_style_reference_ready`，全局参考图失败会显示为 `0/1`，并单独说明该图覆盖的页面数。
- 2026-07-10 修复失败后底部固定操作栏文案不一致的问题：失败报告卡片内已有“保留蓝图重试”，但页面底部固定按钮仍显示“加入重试队列”，容易让用户误以为会重新排队从头生成。现已统一为“保留蓝图重试”，并为按钮增加提示：有失败输出目录时会保留已确认蓝图、携带 `resumeOutputDir` 和 seed 从失败阶段续跑；队列行内重试图标也会提示“保留蓝图并从失败阶段续跑”。
- 2026-07-10 针对同一“智能粮食库监测系统”续跑后卡在 `dashboard AI 界面代码生成失败：Read timed out (read timeout=120)` 完成修复：这次已不是全局参考图失败，`visual-reference-manifest.json` 显示参考图已恢复并 ready，而是“按参考图生成 HTML 页面代码”的多模态 GPT 请求 4 次均在 120 秒读超时。现已给 AI 前端页面代码生成阶段新增独立超时 `SOFT_LLM_AI_FRONTEND_TIMEOUT_SECONDS`，默认 220 秒、可配置到 360 秒；同时发送给 GPT 的全局风格参考图会先压缩为仅供视觉理解的小尺寸 JPEG，不改变原始 `style_reference.png`。本次失败图从 1,462,443 字节 PNG 压到约 132,659 字符 data URL，可显著降低多模态请求体积。失败报告写入时也改为优先使用最新 `generation-state.json` 阶段，避免旧失败文件把后续 AI 前端失败误标成 `visual_reference`。
- 2026-07-08 已将桌面端生成过程展示从大卡片改为“单行当前状态 + 可展开过程详情”：默认只显示当前阶段、当前动作、进度和耗时，点击“过程详情”后再展开阶段条、最近执行流和原始运行日志，减少主工作区占用；原始日志仍保留在折叠详情内，便于失败时诊断。
- 2026-07-08 修复桌面端 GPT 配置保存后被还原的问题：保存配置现在写入用户配置目录（或显式 `SOFT_DESKTOP_CONFIG_DIR`），启动加载时安装包/仓库预置配置只作为默认值，用户保存目录最后加载；同一目录内按文件修改时间加载，较新的 `production.json` / `desktop.local.json` 最后生效。保存时会写入 `SOFT_USER_SAVED_CONFIG=true` 和保存时间标记，避免用户手动保存的请求地址、模型名和 API Key 被旧预置配置覆盖；真实 key 仍只保存在被忽略的本地配置文件中。
- 2026-07-08 参考客户补正案例完成说明书和源码鉴别材料风格对齐：说明书截图说明不再输出“操作说明/字段说明/处理结果/业务一致性”等固定标签，改为接近真实操作手册的自然步骤、字段核对和保存结果描述；客户可见正文继续拦截 `GPT`、`image2`、`视觉参考`、`generated_source`、`ui-prototype` 等内部生成词，并修复 `FastAPI` 被误清洗为“Fast业务接口”、截图说明出现“24类界面/线路节点”等机械表述的问题。源码鉴别材料页眉改为更接近案例的 `软件名 V1.0 页码` 样式，继续保持 A4、页眉右上角页码、50 行/页、超过 60 页时前 30 后 30 连续抽取。
- 2026-07-08 已补强工业/物联网/测绘/运输等客户案例常见模块命名：新增 `设备档案 -> device_profile`、`网关通道 -> gateway_channel`、`遥测数据 -> telemetry_data`、`远程指令 -> remote_command`、`设备告警 -> device_alarm`、`维保工单 -> maintenance_ticket`、`健康评分 -> health_score` 等语义 key；旧阶段缓存中的 `industrial_iot_01`、`transport_route_03` 等“行业子类型前缀 + 序号”会被视为旧模板占位并按模块标题迁移，避免源码文件名、接口名和截图 key 继续像模板编号。
- 2026-07-06 已补强内部生成说明泄露过滤：界面 HTML、说明书和校验扫描会拦截或清洗 `image2`、`视觉参考`、`参考稿` 等内部阶段词，客户可见材料只保留业务操作语言。`local-template` 仍作为显式开发/无 token 模式保留；正式 GPT 模式不允许无图生成截图，也不允许用模板或中间图片替代最终运行截图。
- 2026-07-05 修复“生成到 99% 后因说明书 PDF 正文文本行数校验失败”的假失败：根因是桌面端内置 `python-runtime` 漏装 `pypdf`，导致 `manual_pdf_text_density_checked=false`，并非说明书正文页真实行数不足。已补装当前内置运行时依赖，`scripts/prepare-python-runtime.ps1` 的就绪检查和最终校验也已加入 `pypdf`；`docgen.analyze_manual_pdf_text_density` 增加 `pdftotext` 兜底路径。已对本次 `测绘三维地形构建平台-20260705-181954-9960` 输出重新复测，说明书 PDF 24 个正文页最低 31 行、平均 32.33 行，`validation_report.json` 已更新为 `ready_for_delivery=true`。
- 已新增 Codex 项目 skill：`C:\Users\15527\.codex\skills\soft-copyright-generator\SKILL.md`。后续会话处理本项目时应同步进度文档、收尾给出下一阶段建议，并避免 PowerShell inline 中文参数导致乱码或 `????`。
- 已新增 Windows 便携交付包脚本 `scripts/package-windows-portable.ps1`，可输出包含 `dist/`、`backend/`、`desktop/`、配置模板、`ms-playwright/` 和 `python-runtime/` 的 zip 包；包内不包含本机真实 `production.json` / `desktop.local.json`。
- 已接入 `electron-builder` Windows NSIS 安装器，`npm run pack:win` 可输出普通安装器和 `win-unpacked` 目录；普通安装器包含 Electron 应用、后端文件、配置模板、`ms-playwright/` 和 `python-runtime/`，不包含真实本机配置。客户正式交付使用 `npm run pack:win:customer`，会从本机 `config/production.json` 注入预置 GPT 配置，并在 UI 中开放查看和修改。
- 已新增 Python embeddable runtime 准备脚本 `scripts/prepare-python-runtime.ps1`，默认准备 Python 3.12.10、pip 和 `requirements.txt` 依赖，并写入 `..\backend` 到 `python312._pth`，保证安装包内置 Python 能导入后端包。
- Electron 主进程已优先使用内置 `python-runtime/python.exe` 启动生成任务；未找到时才回退系统 `python`。
- `generation_report.json` / 桌面端结果明细已记录 `technical_architecture_source`、`technical_architecture_key`、`source_strategy` 和 `source_language`；GPT 模式可直接验收技术架构是否为 `llm` 选择。

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

正式客户包会预置 API Key、模型名和请求地址；UI 高级设置会常驻显示并允许修改请求地址、模型名称和 API Key。交付前先在本机忽略文件 `config\production.json` 写入真实 NewAPI 配置：

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
- 客户预制安装器当前开放“请求地址”“模型名称”“API Key”三个配置字段；桌面端会从配置文件读取请求地址并在高级设置中常驻显示，保存后写回本地配置。
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
- 说明书 GPT 正文生成已从“每章/每模块单独请求”改为批次请求：公共章节分 3 批、模块章节每 2 个模块一批；生成器会输出公共章节批次和模块批次进度，当前 GPT-only 模式下单批失败会终止本次生成并提示重试。
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
- 使用真实 GPT / NewAPI 配置完成 GPT-only 端到端验收，输出 `output-gpt-only-acceptance\社区小微贷款风险巡检系统-20260625-031207-6830--材料包.zip`；`blueprint_source: llm`，`manual_source: llm`，`technical_architecture_source: llm`，`technical_architecture_key: enterprise_web`，`source_strategy: java_with_web_console`，`source_language: Java/JavaScript/SQL`，`ui_blueprint_source: llm`，`ui_screenshot_count: 9`，`source_total_lines: 7211`，`authenticity_score: 96`，`normative_score: 100`，`validation_ready_for_delivery: true`，`validation_finding_count: 0`，最终 ZIP 根目录正好 5 个客户交付文件。
- 上述 GPT-only 验收总耗时 `809.74` 秒，其中 `blueprint: 373.13` 秒、`manual_content: 301.56` 秒、`screenshots: 123.01` 秒、`pdf: 8.88` 秒。耗时主要集中在 GPT 产品蓝图、说明书正文和逐页 UI 蓝图/截图链路，后续优化应在不降低真实性和一致性的前提下做阶段可视化、可恢复和高质量缓存。
- 已修复桌面端“生成蓝图”长时间停在等待态的问题：蓝图阶段改为轻量 GPT 蓝图请求，Electron 子进程增加启动、超时、失败、成功进度事件，前端增加 UI 超时保护，Python CLI 失败时统一输出 `RESULT_JSON.message`。使用真实 NewAPI 配置验证 `电力线路故障分析集成软件` / `APP`：当前配置模型 `gpt-5.5`，点击后界面进入“理解中”，runtime 日志记录 `outlineModel=gpt-5.5`、`requestTimeoutSeconds=60`，约 `65` 秒返回 10 个电力线路故障分析模块并进入可编辑蓝图；失败时会显示超时、503、鉴权或 JSON 错误等可读原因，不再无限卡住。
- 已修复“确认生成”后在第 2 步再次失败的问题：正式生成现在会把桌面端已确认的 `businessPlan` 写入临时 JSON，并通过 `--confirmed-outline-json` 传给后端；后端转换为 `feature_hint_source=confirmed-outline` 的语义契约，复用用户已确认/编辑的蓝图模块，跳过重复 GPT 名称理解。Playwright Electron 回归验证：点击“确认蓝图并生成”后第 2 步显示“复用已确认蓝图，准备生成产品蓝图”，随后进入 `生成产品蓝图 1/5` 和“生成产品身份定位”，不再停在“理解软件名称并补充业务关键词”。
- 已新增正式生成失败后的恢复入口：当材料生成失败且已有确认蓝图时，底部操作区和失败报告都会显示“保留蓝图重试”“继续修改蓝图”“新建任务”。`保留蓝图重试` 会复用当前 `confirmed-outline`，不会要求用户重新生成蓝图；Playwright Electron 使用模拟蓝图失败完成 UI smoke，确认失败报告显示“已保留当前确认的蓝图，重试会直接复用蓝图并继续生成材料包”。
- 已新增桌面端“蓝图模型/超时”配置：配置文件支持 `SOFT_MODEL_GPT_OUTLINE_NAME` 和 `SOFT_MODEL_GPT_OUTLINE_TIMEOUT_SECONDS`，高级设置新增“正式生成模型”“生成蓝图模型”“蓝图超时秒数”。用户已明确要求蓝图和正式内容都使用 `gpt-5.5`，本机忽略配置已设为正式模型 `gpt-5.5`、蓝图模型 `gpt-5.5`、蓝图超时 `60` 秒。
- 已将蓝图生成升级为两段式 GPT 请求：第一段 `feature_hint:profile` 只做名称理解、领域、目标用户、关键词和避免方向；第二段 `feature_hint:modules` 基于第一段语义生成 8-10 个可编辑模块草案。失败时会明确显示“名称理解失败”或“模块草案生成失败”，trace 也能定位到具体阶段。当前策略不使用低配模型替代蓝图模型，避免蓝图和正式内容质量不一致。
- 已修复桌面端输入框与业务状态分叉：底部输入框显示值、`canPlan`、主按钮、顶部空态和重新生成按钮统一使用同一份当前输入文本，避免出现输入框已有软件名但右上角仍显示“待输入”、蓝图区仍显示“等待输入软件名称”的情况。Electron 蓝图 IPC 还新增 `runtime-events.jsonl` 运行日志，记录收到请求、启动蓝图模型、超时、关闭结果等非敏感事件，便于定位点击是否进入主进程。
- 已简化桌面端底部输入区：移除“软件大类”“技术特点”“源码架构”三个手动控件，用户只输入软件名称/补充说明并点击生成；桌面端会根据名称和补充说明自动判断 `productType` 和 `softwareCategory`，后端继续由 GPT 自动选择技术架构和源码语言。Playwright Electron smoke 已确认首页不再出现“软件大类 / 技术特点 / 源码架构”，底部只保留软件名称输入框和主按钮。
- 本次 UI smoke 发现并修复两个真实卡点：`desktop.local.json` 由 Windows PowerShell 写入 UTF-8 BOM，导致 Node `JSON.parse` 失败；同时配置合并曾把初始环境变量重新盖回文件配置。Electron 配置读取现已自动去 BOM，并且只有配置文件未提供的键才保留初始环境变量。Playwright Electron 验证结果：填入 `电力线路故障分析集成软件` 后状态从“待输入”变为“待生成”，点击后进入“理解中”，可从 runtime 日志确认实际使用的蓝图模型。
- 已按当前使用需求重新开放客户 UI 中的 GPT 请求地址：主进程从 `config/production.json` / `config/desktop.local.json` 读取请求地址用于调用和余额查询，`get-model-config` 会把当前地址回传给渲染层；高级设置常驻展示请求地址、正式生成模型、生成蓝图模型、蓝图超时和 API Key，保存后写回本地配置。错误日志和失败报告仍保持脱敏，不直接输出完整网关地址或 token。
- 2026-06-29 使用截图渲染函数级 smoke 验证“正式软件感截图”升级，输出 `output-realistic-screenshot-render-smoke-final\Realistic-Screenshot-Acceptance-System-20260629-095437-1266`；`renderer: admin`，`screen_count: 43`，`png_count: 43`，`warnings: []`，已视觉抽查 `dashboard.png` 和 `custom.png`，确认顶部应用框架、工作区标签、业务队列、状态卡片、选中记录详情、处理轨迹和附件导出浮层正常。该 smoke 只验证渲染层，不走正式 GPT-only 生成，不消耗 GPT token。
- 2026-07-05 使用函数级本地 smoke 验证后台模块截图差异化，不消耗 GPT token，输出根目录 `output-ui-differentiation-smoke`。交通样例 `城市交通接驳线路运行调度系统-UI-DIFF-FINAL-1` 命中 `transport_route`，模块页分配 `admin_map`、`admin_pipeline`，生成 `27/27` 张 PNG；教育样例 `校园晚自习作业跟踪与干预系统-UI-DIFF-FINAL-2` 模块页分配 `admin_case`、`admin_form`、`admin_matrix`、`admin_risk`，生成 `24/24` 张 PNG；云运维样例 `多云资源发布与告警诊断平台-UI-DIFF-FINAL-3` 模块页分配 `admin_matrix`、`admin_pipeline`、`admin_risk`，生成 `27/27` 张 PNG；三组 `warnings: []`。已视觉抽查交通 `custom.png` 为线路拓扑/点位详情页，教育 `exam_training_02.png` 为配置表单页，云运维 `k8s_ops_03.png` 为指标矩阵/控制页。
- 2026-07-05 最新工程检查：`python -m py_compile backend\generate_materials.py backend\softcopyright\generator.py backend\softcopyright\docgen.py backend\softcopyright\screenshots.py backend\softcopyright\llm_manual.py backend\softcopyright\ui_blueprint.py` 通过，`node --check desktop\electron\main.cjs` 通过，`npm run build` 通过；`git diff --check` 未发现空白错误，仅输出当前工作区已有 LF/CRLF 换行提示。
- 2026-06-29 针对客户侧“生成说明书模块章节 4/4”失败完成本地模拟验收：mock provider 让“说明书模块章节批次”抛出带真实网关 URL 的 `504 Gateway Time-out`，系统自动触发 2 次单模块 GPT 拆分重试，最终 `module_count: 2`、`warnings: []`，脱敏结果为 `504 Server Error: Gateway Time-out for url: [模型网关]`。本阶段工程检查同步更新为：`python -m py_compile backend\generate_materials.py backend\softcopyright\generator.py backend\softcopyright\docgen.py backend\softcopyright\screenshots.py backend\softcopyright\llm_manual.py backend\softcopyright\llm\provider.py backend\softcopyright\llm\trace.py backend\softcopyright\errors.py` 通过，`node --check desktop\electron\main.cjs` 通过，`npm run build` 通过，`git diff --check` 仅有既有 LF/CRLF warning。
- 2026-06-29 阶段缓存本地模拟验收通过：同一 `confirmed-outline` + `gpt-5.5` + 生成策略写入后，可恢复 8 个产品蓝图模块、`web_mobile_app` 技术架构和 8 个模块的说明书正文；修改业务补充后缓存 key 会变化，避免误用旧项目内容。失败时后端 CLI 现在也会输出脱敏 `RESULT_JSON`，包含 `seed`、`output_dir` 和 `message`，Electron 可在“保留蓝图重试”中继续沿用上次 seed。
- 2026-06-29 UI 蓝图缓存模拟验收通过：写入 `source=llm` 的 `UiBlueprint` 后可恢复 `renderer=admin`、`screen_count=4`、`design_brief.layout_family=map`，`source=local-template` 或截图数量不足的无效蓝图会被拒绝复用。最新检查：`python -m py_compile backend\generate_materials.py backend\softcopyright\generator.py backend\softcopyright\docgen.py backend\softcopyright\screenshots.py backend\softcopyright\stage_cache.py backend\softcopyright\ui_blueprint.py backend\softcopyright\llm_manual.py backend\softcopyright\llm\provider.py backend\softcopyright\llm\trace.py backend\softcopyright\errors.py` 通过，`node --check desktop\electron\main.cjs` 通过，`npm run build` 通过，`git diff --check` 仅有既有 LF/CRLF warning。
- 2026-06-29 已完成客户版 NSIS 安装包打包：执行 `npm run pack:win:customer` 成功，输出 `release\customer-installer\Soft Copyright Generator Setup 0.1.0.exe`，大小 `573.34 MB`，SHA-256 为 `4D3030E94CBCE8BE8ABAA22E67146996ADFC4C7CC2C43B19F925DB1EEA7BDB81`。安装包解包资源已核对，包含 `backend`、客户预置 `config\production.json`、`config\production.example.json`、`ms-playwright`、`python-runtime`、`libreoffice` 和 `requirements.txt`；预置配置为 GPT 模式、模型 `gpt-5.5`、`SOFT_ACCOUNT_PROVIDER=newapi`。打包日志仅出现 `package.json` 缺少 description/author、默认 Electron 图标、Node `DEP0190` 弃用提示，未影响安装器生成。
- 2026-06-29 已整理版本修改说明，新增 `docs\version-change-summary.md`，按 V0.1.0 至 V0.1.6 的阶段版本说明基础生成、安装包运行时、GPT-only 真实项目、截图真实感、源码质量校验、长流程恢复加速和客户交付安全等更新内容。
- 2026-06-29 针对客户反馈“生成截图排版有重叠”完成顶部布局修复：`top_tabs` 和 `workflow` 导航会自动截断长模块名、限制可视导航项并显示 `+N`，顶部品牌区/导航区/工具区改为独立网格，标题卡片解除固定 52px 高度，工作区标签和状态栏增加溢出保护。使用 `交通运输干线支线路径适配管理软件` 长标题场景完成本地 Playwright smoke，输出 `output-overlap-smoke\software-20260629-OVERLAP`，`warnings: []`；浏览器矩形碰撞检测 `dashboard.html`、`route_adaptation.html` 均为 `issues=[]`。
- 2026-06-30 对照参考压缩包完成说明书疏密优化：参考 `多旋翼无人机航线规划管理系统.docx` 约 45 段、1598 字、23 图，当前生成说明书不再按长报告堆叠正文，而是压缩为手册式短段落，并保留每张关键截图后的“操作说明 / 字段说明 / 处理结果”。`scripts\run_manual_density_review.py` 验证通过：`manual_paragraph_count: 87`，`manual_character_count: 3236`，`manual_average_chars_per_paragraph: 37.2`，`manual_operation_density_ready: true`。
- 2026-06-30 完成源码鉴别材料版式修复：源码材料优先筛选业务逻辑、流程、校验、统计、权限等高信息量代码行，低信息量括号行会补充上下文注释；当源码量足够时稳定输出 60 页、每页 50 行，并使用 Word 原生页码域 `第 PAGE 页`。本地 smoke 输出 `output-layout-smoke-source\LayoutSourceSmokeSystem_代码-(JavaScript_Java_SQL).docx`，`source_total_lines: 7150`，`source_total_pages: 143`，`source_selected_pages: 60`，最后一页非空行数 `50`，源码鉴别材料非空段落 `3000`。
- 2026-06-30 针对 LibreOffice 弹窗/中文路径误判补强 PDF 转换：后端转换时改为独立临时用户配置、隐藏窗口启动、清理会污染 LibreOffice 的环境变量，并先复制为 ASCII 临时 DOCX 转换，再复制回中文正式 PDF 名，避免 LibreOffice 对中文路径回显乱码导致误判失败。验证 `convert_to_pdf()` 对源码材料返回 `err: None`，PDF 大小 `674743` 字节；截图里的 `bootstrap.ini 已经损坏` 弹窗更像外部 LibreOffice 启动/预览配置问题，正式后端转换链路已规避该误判。
- 2026-06-30 完成软著格式规范首轮对齐：说明书和源码鉴别材料统一设置为 A4 纵向页面，并在页眉右上角使用 Word 原生 `PAGE` 域输出 `第 PAGE 页`；源码材料不再使用居中页脚页码。新增 `analyze_docx_layout()` 检查 A4、纵向、页眉页码和页脚页码状态，`generation_report.json` / `validation_report.json` 会记录 `manual_docx_is_a4`、`source_docx_is_a4`、`manual_docx_header_page_number_right`、`source_docx_header_page_number_right`。
- 2026-06-30 正式交付判定已区分 LibreOffice PDF 和简版 fallback PDF：`checks.pdf_official_conversion_ready` 只有两个 PDF 均由 LibreOffice 成功转换且无错误时才为 true；`fallback-reportlab` 仅作为开发预览，不再计入正式可交付。规范性校验新增 `pdf_official_conversion_not_ready`、`docx_page_size_not_a4`、`docx_page_number_not_top_right` 发现项，并写入 `materials_manifest.json` 的 `layout` 证据块。
- 2026-06-30 本地格式 smoke 验证通过：`output-layout-format-smoke` 生成的 `software.docx` 与 `software_代码-(Java).docx` 均为 `21.0 x 29.7cm` A4 纵向，页码域位于页眉右侧，页脚无页码；源码材料 `source_selected_pages: 60`、`lines_per_page: 50`。validator smoke 确认 fallback PDF 会触发 `pdf_official_conversion_not_ready`，LibreOffice 模拟正式转换时规范性 ready 可通过。
- 2026-06-30 已将源码鉴别材料抽取改为严格连续模式：`generate_source_docx()` 现在按真实源码读取顺序先分 50 行/页，超过 60 页时直接输出原始前 30 页和后 30 页，不再在抽取阶段筛行、重排、追加上下文注释或补 filler 行；不足 60 页时按真实顺序全量输出。`selection_mode` 更新为 `first_30_last_30_continuous` / `all_continuous`，并新增 `source_continuous_selection`、`source_material_filler_line_count` 等报告字段。
- 2026-06-30 源码连续性 smoke 验证通过：构造 3100 行源码时总页数 `62`、选中页数 `60`，第 1 页源行 `1-50`，第 30 页 `1451-1500`，第 31 页直接跳到后 30 页首段 `1601-1650`，最后一页 `3051-3100`；`source_presentation_filter_enabled: false`、`source_material_filler_line_count: 0`。validator smoke 确认 `source_continuous_selection=false` 会触发 `source_selection_not_continuous` 且规范性不 ready，true 时规范性 ready 可通过。
- 2026-06-30 新增 PDF 渲染页尺寸校验：`analyze_pdf_layout()` 会优先调用 `pdfinfo` 检查 PDF 页数和页面尺寸；若本机/打包环境的 `pdfinfo.cmd` 不可用，会退回到 PDF `/MediaBox` 轻量解析，不额外引入 Python PDF 依赖。`generation_report.json` / `validation_report.json` 新增 `manual_pdf_is_a4`、`source_pdf_is_a4`、`manual_pdf_page_count`、`source_pdf_page_count` 等字段，正式交付 ready 现在要求说明书 PDF 和源码 PDF 都是 A4 页面。
- 2026-06-30 PDF A4 smoke 验证通过：使用 ReportLab 生成 A4 与 Letter 两个 PDF，MediaBox 兜底可识别 A4 为 `21.0 x 29.7cm`、Letter 为 `21.59 x 27.94cm`；validator smoke 确认 `source_pdf_is_a4=false` 会触发 `pdf_page_size_not_a4` 且规范性不 ready，两个 PDF 均为 A4 时规范性 ready 可通过。按用户要求，不做黑白打印版。
- 2026-06-30 新增说明书 PDF 逐页文本行数校验：依赖 `pypdf` 进行页面文本抽取，`analyze_manual_pdf_text_density()` 会跳过封面页和纯图注页，对正文文本页按不少于 30 行检查，并输出 `manual_pdf_text_density_ready`、`manual_pdf_text_density_page_count`、`manual_pdf_low_text_density_pages`、`manual_pdf_min_text_page_line_count` 等字段。正式交付 ready 现在要求说明书 PDF 正文页文本密度通过；不做黑白打印版。
- 2026-06-30 说明书 PDF 行数 smoke 验证通过：构造封面页、35 行正文页和 10 行正文页时，封面页被排除，正文页计数为 2，低密度页识别为第 3 页 `line_count: 10`；validator smoke 确认 `manual_pdf_text_density_ready=false` 会触发 `manual_pdf_text_density_not_ready` 且规范性不 ready，true 时规范性 ready 可通过。
- 2026-06-30 已将源码材料质量优化前移到源码工程生成阶段：`generated_source` 会写入内部 `.source-material-order.json`，源码鉴别材料读取时优先按该清单连续读取真实文件，清单外文件再按启发式补充；清单采用 `front-core-middle-support-tail-core` 策略，把 Service/Controller/Repository/Mapper/Workflow 等核心业务文件分布到前段和尾段，配置、模型、静态入口等支撑文件放中间。该清单不进入客户 ZIP，`generation_report.json` / `materials_manifest.json` 会记录 `source_material_order_manifest_used`、`source_material_order_strategy` 和文件数量。
- 2026-06-30 源码顺序 smoke 验证通过：本地 Java/Spring Boot 样例 `output-source-order-smoke` 生成 `source_total_lines: 6900`、`source_total_pages: 138`、`source_selected_pages: 60`、`selection_mode: first_30_last_30_continuous`；第 1 页来自 `BusinessOps01AuditService.java` / `BusinessOps01ExportService.java`，第 30 页来自 `WorkflowTransitionSupport.java`，第 31 页进入 `web-console/src/services/businessWorkflowService.js`，最后一页来自 `BusinessOps05Mapper.xml` / `BusinessOps06Mapper.xml`，`source_material_order_manifest_used: true`，补齐文件保持完整代码类，不再使用黑白打印版。
- 2026-06-30 对照手写源码材料样例完成页眉与正文版式对齐：源码鉴别材料页眉改为左侧软件名版本、右侧 Word 原生 `第 PAGE 页` 页码，并在页眉下方添加细横线；正文改为宋体 10.5pt、14pt 固定行距、窄页边距，视觉上接近人工整理样例。`analyze_docx_layout()` 已支持识别页眉表格中的页码域和底边框，避免结构检查漏判。Unicode 安全 smoke 输出 `output-source-style-smoke\供应商资质信息审核归档管理平台_代码-(Java).docx` / `.pdf`，结构检查为 A4、页眉右侧页码、页眉横线均通过，首页 PDF 渲染已人工确认；按用户要求未增加黑白打印版。
- 2026-06-30 对照参考说明书和 TXT 信息表完成操作手册风格对齐：说明书新增独立封面，标题为软件名、下方居中显示“操作手册”；页眉改为左侧软件名版本、右侧裸页码并带横线，避免 LibreOffice 渲染时页码停在中间；正文第四章从“功能模块说明”调整为“功能操作说明”，每个模块补充查询、追加、修改、查看、失效、导出等按钮级操作段落，并在截图后保留“操作说明 / 字段说明 / 处理结果”。TXT 信息表恢复为 16 个软著字段，新增“软件的技术特点分类”，`源程序量` 改为纯数字，编程语言统一为 `JAVASCRIPT/JAVA/SQL` 等规范大小写。智慧城市软件新增 `transport_route` 子类型和交通运输关键词匹配，`交通运输干线支线路径适配管理软件` 稳定命中“交通干支线路径适配系统”，不再随机落到景区票务。Unicode 安全 smoke 输出 `output-manual-info-style-smoke\交通运输干线支线路径适配管理软件.docx` / `.pdf` / `.txt`，PDF 27 页、A4 竖版、页眉右侧裸页码和横线通过结构检查，24 张截图与操作说明密度通过，整份 PDF 已用 Poppler 渲染为 PNG 总览并人工确认无明显空白页、裁切或页眉漂移。

- 2026-06-30 完成客户版 NSIS 安装包重新打包：执行 `npm run pack:win:customer` 成功，输出 `release\customer-installer\Soft Copyright Generator Setup 0.1.0.exe`，大小 `601,264,158` 字节（约 `573.41 MB`），SHA-256 为 `DCAC15DDB43208F111D9D3FD291FC0622E8DCE48AB61DD63EA87BFCE20200E1F`。安装包解包资源已复核，包含 `backend`、客户预置 `config\production.json`、`config\production.example.json`、`ms-playwright`、`python-runtime\python.exe`、`libreoffice\program\soffice.exe` 和 `requirements.txt`；客户配置字段仅做存在性校验，未输出真实 API Key 或网关地址，确认 GPT 模式、模型 `gpt-5.5`、`SOFT_ACCOUNT_PROVIDER=newapi`、`SOFT_CUSTOMER_PRESET_CONFIG=true`。打包日志仅出现 `package.json` 缺少 description/author、默认 Electron 图标、重复 dependency 引用和 Node `DEP0190` 提示，均未阻断安装器生成。

- 2026-07-01 针对客户反馈“手册标题名称不一致”完成截图标题链路修复：前端产品类型推断不再把普通“平台”误判为云计算/Kubernetes，医疗识别补充手术、麻醉、科室、排班等关键词；后端新增“手术排班协同系统”医疗子类型，稳定命中“手术安排与协调平台”场景。截图生成层现在以软件名称和业务蓝图为准，登录页显示“软件名登录”，手册图题固定为“登录界面 / 系统首页 / 模块名 / 统计报表界面”，顶部副标题、面包屑、状态栏、表头、状态值和指标卡会清洗旧缓存或错配设计蓝图中的 `Kubernetes`、`k8s_ops`、`云资源`、`资源水位` 等异域词。针对性 smoke 使用旧 K8S UI 蓝图缓存复现污染场景，验证生成 HTML 中禁用词命中为空，登录标题包含“手术安排与协调平台登录”，业务上下文为“医疗手术排班与科室协同”。

- 2026-07-01 针对客户反馈“气道管理演练结果页生成了消除游戏截图”完成原因定位和修复：截图不是由手册/PDF/源码反向生成，而是截图阶段根据软件类型、业务关键词和 UI 蓝图生成 HTML 原型后截图；原先 `is_game_like()` 只要命中“得分、步数、关卡、道具、玩家”等词就可能进入 `game` 渲染器，医学技能演练/考核系统中的“得分、剩余步骤”因此被误判为游戏。现已收紧游戏判定：只有显式游戏/手游/三消/玩家/道具背包/关卡地图/对局等强游戏语义才走 game；遇到医疗、气道、急救、培训、实训、演练、考核、技能、仿真、管理平台等业务上下文会强制走桌面业务系统截图。前端自动产品类型推断同步去除“得分”类泛化游戏触发，并优先识别医疗/气道/VR/仿真/培训。阶段缓存也新增 UI 蓝图类型二次校验，旧的 game UI 蓝图若与当前软件不匹配会被忽略并重新生成。回归验证：气道管理演练系统为 `admin`，即使误标为“游戏软件”也会纠偏为 `admin`；真实“星糖岛消除冒险”仍为 `game`；旧 game UI 缓存对气道系统 `ui_matches_software_type=false`。

- 2026-07-01 针对客户反馈“需要更真实的基于源码生成的软件截图”完成截图源码证据链升级：截图生成阶段现在会扫描本次 `generated_source` 中的 Controller/Router、Service、Model、Repository/Mapper 等真实生成文件，按模块提取源码文件、接口/路由、服务类方法、字段和类名，写入 `generated_source\ui-prototype\source-ui-evidence.json`、`prototype-manifest.json` 和 `ui_blueprint.design_brief.source_ui_evidence`。后台系统首页新增“源码接口覆盖”卡片，模块页底部新增“源码接口映射”卡片，展示如 `AirwayTrainingController.list`、`AirwayTrainingService.query`、`演练编号/参训人员/技能得分` 等真实源码与业务字段；模块表格也优先使用模块 `data_fields` 作为表头和样例值。`generation_report.json` 新增 `ui_source_evidence_ready`、`ui_source_evidence_module_count`、`ui_source_evidence_file_hits`、`ui_source_evidence_route_hits`、`ui_source_evidence_service_hits` 等检查项。阶段缓存保存 UI 蓝图时会移除输出目录相关源码证据，避免复用旧路径。Unicode 安全 smoke 输出 `output-source-backed-screenshot-review\气道管理演练系统-REVIEW`，`renderer: admin`、`screenshot_count: 9`、`evidence_ready: true`、`evidence_module_count: 2`、`evidence_file_hit_count: 24`、`evidence_route_hit_count: 16`，模块截图包含 `AirwayTrainingController.list`、`AirwayTrainingService.query` 和“演练编号”，且未出现“消除棋盘 / 剩余步数 / 道具背包”等游戏词。

- 2026-07-01 继续完成“真实项目运行截图”硬门禁：正式 `generate_materials()` 现在要求截图必须先启动本次生成的源码项目服务，再从 `http://127.0.0.1:{port}/ui-prototype/*.html` 截图；如果 Playwright 不可用、项目服务启动失败、`/health` 不通、模块接口探针不通、截图模式不是 `project-server`，或缺少源码文件/接口/服务证据，都会直接失败，不再回退为本地 HTML 或 Pillow 静态预览。运行证据会回写 `source-ui-evidence.json` / `prototype-manifest.json` / `ui_blueprint.json`，包括 `render_mode: project-server`、`base_url`、`runtime_probe_ready`、`runtime_probe_count` 和每个探针 URL。Python/FastAPI、JavaScript/Express + Java API 架构均完成 smoke：`output-runtime-backed-smoke` 为 `render_mode=project-server`、`runtime_probe_count=4`、12 张 1280×820 截图；`output-runtime-backed-js-smoke` 模拟交通运输 JavaScript/Java/SQL 架构，Express 服务真实启动，`/health` 和 `trunk_route`/`branch_route`/`route_match` 模块接口均返回 200，源码证据映射到 `TrunkRouteController.list`、`TrunkRouteService.query`、`src/routes/trunk_routeRoute.js` 等真实生成文件。说明书图注同步新增“截图来源”和“源码依据”，写明项目服务 URL、探针数量和模块对应接口/服务/源码文件。

- 2026-07-01 继续收紧“截图必须基于真实项目运行数据”的门禁：`ui-prototype` 页面不再只作为静态 HTML 被项目服务托管，而是在浏览器打开截图页时实际 `fetch` 本次生成项目的 `/health`、`/<module>/`、`/<module>/summary` 以及兼容的 `/api/<module>` 路由，并用接口返回数据刷新表格、指标和当前记录区域；Playwright 截图阶段会等待 `window.__runtimeApiReady`，若页面没有命中生成项目业务接口则直接失败。`source-ui-evidence.json`、`generation_report.json`、`validation_report.json` 和 `materials_manifest.json` 新增 `runtime_api_ready` / `ui_runtime_api_ready`、页面数、接口请求数、每页命中 URL 和记录数证据；正式生成现在要求 `ui_runtime_api_ready=true`，不是只看 `/health` 或外部探针。JavaScript/Java/SQL 交通运输 smoke 输出 `tmp\runtime-api-screenshot-smoke\RuntimeApiScreenshotSmokeSystem-20260701-RUNTIME-API`，27 张截图全部为 `project-server`，`runtime_api_page_count: 27`、`runtime_api_ok_fetch_count: 65`、`source_total_lines: 7150`、`node_modules_exists: false`；干净小样本 `tmp\runtime-api-clean-smoke\RuntimeApiCleanSmoke-20260701-CLEAN` 验证 6 张截图、11 次有效接口返回。生成服务种子数据同步改为交通运输业务台账样例，例如 `TR-HX-1001`、`沪杭干线北向联络线`、`浦东东区`，减少接口返回仍像模板占位数据的问题。说明书运行截图说明也改为读取同一份运行 API 证据，写明截图由源码项目服务运行后加载业务接口数据生成。

- 2026-07-01 继续推进“真实项目截图”质量：Playwright 截图不再只要求接口请求成功，还会校验接口返回的业务编号、名称、范围、节点序列等值已经写入页面可见区域；`source-ui-evidence.json` 的每页 `runtime_api_pages` 新增 `visible_match`，正式页面若接口数据未出现在可见业务区域会直接失败。JavaScript 生成源码的种子记录已按模块 `data_fields` 写入同名业务字段和 `fieldValues`，例如干线路径编号、干线路径名称、途经节点序列、通行方向、服务范围等，截图运行脚本按表头字段绑定真实接口返回值，不再只展示通用 `记录001`。交通运输干支线路径模块页改为台账优先布局，保留筛选、查询、同步、导出、业务表格、线路衔接概览和处理轨迹；导出、统计、复核、详情、表单等操作弹窗新增当前运行记录卡片，显示接口返回的具体记录。截图质量门禁新增 `ui_visible_text_clean`，可见 HTML 若出现 `????`、占位模块名或泛化记录名会停止正式生成；说明书截图说明同步记录“接口返回业务记录出现在页面可见区域”的核验证据。UTF-8 交通运输真实服务 smoke 输出 `tmp\runtime-api-transport-real-smoke\交通运输干线支线路径适配管理软件-TRANSPORT-REAL-UI`，27 张截图全部为 `project-server`，`runtime_api_ready: true`、`runtime_api_page_count: 27`、`runtime_api_fetch_count: 65`、`runtime_api_ok_fetch_count: 65`、`visible_match_pages: 27`、`source_total_lines: 7100`；已抽查 `trunk_route_catalog.png` 显示 `TR-HX-1001`、`沪杭干线北向联络线` 等接口数据，`trunk_route_catalog_operation_2_2.png` 导出弹窗保留真实业务编码前缀。

- 2026-07-01 继续补强“真实项目截图”人工观感门禁：后台模块截图不再只显示接口表格，还必须包含操作弹窗的执行结果、日志/耗时/处理人、统计刷新等可见证据；统计图表必须带最近日期、单位和业务上下文；交通运输类截图必须展示干线/支线拓扑关系、图例、节点编码和服务时间窗。`generation_report.json` / `validation_report.json` 新增 `ui_operation_result_evidence_ready`、`ui_chart_context_ready`、`ui_route_topology_ready` 和 `ui_realism_missing_evidence`，正式生成若缺少这些证据会失败。最终真实服务 smoke 输出 `tmp\runtime-realism-smoke\交通运输干线支线路径适配管理软件-TRANSPORT-REALISM-SMOKE-FINAL-20260701`，`render_mode: project-server`、`runtime_probe_ready: true`、`runtime_api_ready: true`、`runtime_api_page_count: 27`、`runtime_api_ok_fetch_count: 65`、`visible_match_pages: 27`、`screenshot_count: 27`、`ui_visible_text_clean: true`，新增三项真实感门禁均为 true。已抽查 `trunk_route_catalog.png` 包含 `TR-HX-1001`、线路拓扑、干线/支线图例和服务时间窗；`trunk_route_catalog_operation_2_2.png` 包含当前运行记录与导出结果；`statistics.png` 已减少小地图遮挡并补充日期/单位上下文。

- 2026-07-01 完成交通运输正式材料 RERUN13 终版抽检与打包：输出目录为 `output-runtime-backed-formal-real\交通运输干线支线路径适配管理软件-TRANSPORT-FORMAL-REAL-20260701-RERUN13`，材料包为 `output-runtime-backed-formal-real\交通运输干线支线路径适配管理软件-TRANSPORT-FORMAL-REAL-20260701-RERUN13--材料包.zip`。终版包仅包含 5 个客户交付文件：操作手册 DOCX/PDF、申请信息 TXT、源码鉴别材料 DOCX/PDF；`validation.ready_for_delivery=true`、`findings=[]`。截图为 27 张 `project-server` 真实服务截图，`ui_runtime_api_ready=true`、`ui_runtime_api_fetch_count=65`、`ui_runtime_api_ok_fetch_count=65`，未出现消除游戏、泛化 `记录001` 或旧占位数据。说明书 PDF 为 32 页 A4，页眉右上页码和横线视觉抽检通过，`manual_pdf_text_density_ready=true`、低密度正文页为 0；源码 PDF 为 60 页 A4，源码有效行数统一为 7100。针对抽检时发现的尾页观感风险，已从源码鉴别材料候选中排除纯 `web-console/index.html -> /ui-prototype/index.html` 运行入口壳，保留其在生成源码工程中用于真实运行截图，但不再进入源码 PDF 正文；刷新后第 60 页为业务 Query 代码页，不再显示 `ui-prototype` 入口片段。

完整生成样例：

```text
output-runtime-backed-formal-real\交通运输干线支线路径适配管理软件-TRANSPORT-FORMAL-REAL-20260701-RERUN13--材料包.zip
```

生成检查摘要：

```text
blueprint_source: llm
manual_source: llm
ui_screenshot_render_mode: project-server
ui_runtime_api_ready: true
ui_runtime_api_fetch_count: 65
ui_runtime_api_ok_fetch_count: 65
ui_operation_result_evidence_ready: true
ui_chart_context_ready: true
ui_route_topology_ready: true
source_total_lines: 7100
source_total_pages: 142
source_selected_pages: 60
source_line_target_met: true
manual_pdf_text_density_ready: true
validation_ready_for_delivery: true
validation_finding_count: 0
```

说明：名称理解、产品蓝图、技术架构、说明书正文和 UI 蓝图均已在真实 GPT / NewAPI 配置下跑通过。当前产品生成路径已收敛为 GPT-only：先生成可复用的真实产品方案和技术架构，再由说明书、源码、截图共同消费这份方案；默认模板不再作为正式生成兜底。

- 2026-07-05 针对客户反馈“手册截图仍像模板、二级界面重复、还把 AI/接口生成说明写进正文”完成下一阶段链路改造第一版：新增 `backend/softcopyright/ai_frontend_codegen.py`，正式 GPT/OpenAI-compatible 流程现在会在 UI 蓝图之后继续让模型为每张截图生成完整 HTML/CSS 页面代码，再发布到本次 `generated_source/ui-prototype` 并从生成项目服务 URL 截图；`local-template` 仍保留为显式无 token 开发模式。`generate_materials()` 新增硬门禁 `ui_ai_frontend_ready`，正式 GPT 模式下 AI 页面代码未完整生成会直接失败，不再复用共享 renderer 作为客户截图兜底。截图页面会自动注入运行数据脚本并追加可见业务记录条，继续要求页面实际请求生成项目业务接口、把业务编号/名称/范围/状态写入可见区域。
- 2026-07-05 同步修复当前坏图根因：后台页面不再继承 `login-*` 登录形态 class，避免 `login-left_product_panel` 等登录页 CSS 把桌面后台压成左侧窄条；Playwright 截图后新增 PNG 有效内容几何检查，后台截图有效内容宽度不足、右侧大面积空白或高度未铺满时会直接失败。操作页渲染新增独立整页结构，查询、导入、导出、统计、复核/发布等页面不再全部是同一背景加弹窗，并按模块轮换二级页面角色。
- 2026-07-05 说明书客户可见文本新增内部生成说明过滤与校验：`docgen.py` 将“接口返回、运行服务、生成项目、浏览器页面、source-ui-evidence、generated_source、ui-prototype、AI/GPT 生成说明”等内部证据话术转换为业务语言；`validator.py` 新增 `manual_internal_generation_leak` 检查，若说明书或申请信息仍出现内部生成说明则正式校验失败。运行接口证据仍保留在 `generation_report.json`、`validation_report.json`、`source-ui-evidence.json` 等内部报告中，不进入客户交付正文。
- 2026-07-05 新增包内页面重复度检查：`ui_similarity.py` 除历史 UI 指纹相似度外，会计算当前材料包模块页/操作页结构相似度并写入 `ui_package_page_max_similarity`；正式 GPT/AI 页面代码链路中若页面结构过于相似会触发 `ui_package_pages_too_similar`，阻止同一本手册内大量重复截图。`local-template` 开发模式只记录该分数，不作为硬失败项，避免显式无 token 模式被正式质量门禁误伤。
- 2026-07-05 工程验证：`python -m py_compile backend\generate_materials.py backend\softcopyright\generator.py backend\softcopyright\docgen.py backend\softcopyright\screenshots.py backend\softcopyright\llm_manual.py backend\softcopyright\ui_blueprint.py backend\softcopyright\ui_similarity.py backend\softcopyright\ai_frontend_codegen.py backend\softcopyright\validator.py` 通过；`node --check desktop\electron\main.cjs` 通过；`npm run build` 通过；`git diff --check` 仅有既有 LF/CRLF warning。本地 `local-template` smoke 使用绝对 `PLAYWRIGHT_BROWSERS_PATH` 跑到最终校验阶段，24 张截图均从 `project-server` 截取，`ui_similarity_gate_ready=true`、`manual_internal_generation_leak_hits=[]`；最终因显式模板样本中既有 `????` 占位检查失败而停止，未发现本次新增的内部说明泄露。
- 2026-07-06 image2 视觉参考稿接入工程验证通过：`python -m py_compile backend\generate_materials.py backend\softcopyright\generator.py backend\softcopyright\docgen.py backend\softcopyright\screenshots.py backend\softcopyright\llm_manual.py backend\softcopyright\ui_blueprint.py backend\softcopyright\ui_similarity.py backend\softcopyright\ai_frontend_codegen.py backend\softcopyright\validator.py backend\softcopyright\llm\provider.py` 通过；`node --check desktop\electron\main.cjs` 通过；`npm run build` 通过；本地 mock provider 验证“视觉提示词 -> mock image2 PNG -> 多模态按图生成 HTML”链路通过，报告返回 `source=gpt-visual-reference-image2-to-html`、`visual_ready=true`、`reference_count=1`、`multimodal_seen=true`；内部词过滤和禁止直接嵌入参考图检查均触发预期错误。`git diff --check` 未发现空白错误，仅输出当前工作区既有 LF/CRLF 换行提示。
- 2026-07-07 image2 503 诊断链路本地 mock 验证通过：模拟图片模型连续返回 503 时，`visual-reference-manifest.json` 会保留已生成视觉提示词、`failed_page_key`、`image_model=image2`、`image_retry_count` 和脱敏错误；CLI 失败结果的 `checks` 会带回 `ui_visual_prompt_ready=true`、`ui_visual_reference_ready=false`、`ui_visual_reference_failed_page`、`ui_visual_reference_retry_count`，桌面端失败报告可展示这些字段。
- 2026-07-08 客户补正案例对齐验证通过：`python -m py_compile backend\generate_materials.py backend\softcopyright\generator.py backend\softcopyright\docgen.py backend\softcopyright\screenshots.py backend\softcopyright\llm_manual.py backend\softcopyright\validator.py backend\softcopyright\sourcegen.py backend\softcopyright\module_keys.py backend\softcopyright\industry_subtypes.py` 通过；`node --check desktop\electron\main.cjs`、`node --check desktop\electron\preload.cjs`、`npm run build` 均通过；`git diff --check -- backend/softcopyright/docgen.py backend/softcopyright/llm_manual.py backend/softcopyright/module_keys.py backend/softcopyright/validator.py backend/softcopyright/generator.py backend/softcopyright/industry_subtypes.py` 仅有 LF/CRLF warning。本地完整 smoke 输出 `output-style-smoke-3\工业设备智能监控软件样式验收三-20260708-174436-9665`，`manual_natural_style_ready=true`、`manual_mechanical_label_count=0`、`manual_repeated_phrase_count=0`、`manual_pdf_text_density_ready=true`、`manual_pdf_low_text_density_pages=[]`、`source_selected_pages=60`、`lines_per_page=50`、`source_continuous_selection=true`、`source_docx_header_page_number_right=true`、`manual_docx_header_page_number_right=true`、`validation_placeholder_hit_count=0`、`validation_ready_for_delivery=true`、`ui_placeholder_module_keys=""`、`warnings=[]`。抽样 DOCX 未发现 `Fast业务接口`、`线路节点`、`24类界面`、`视觉参考`、`image2`、`GPT`、`generated_source`、`ui-prototype` 等客户可见残留；源码工程已生成 `device_profile`、`gateway_channel`、`telemetry_data`、`remote_command`、`device_alarm`、`maintenance_ticket`、`health_score` 等语义文件；最终 ZIP 根目录仍为说明书 Word/PDF、申请信息 TXT、源码材料 Word/PDF 5 个交付文件。
- 2026-07-08 已基于上述修正重新打包客户版 NSIS 安装器：执行 `npm run pack:win:customer` 成功，输出 `release\customer-installer\Soft Copyright Generator Setup 0.1.0.exe`，大小 `630,992,309` 字节（约 `601.76 MB`），SHA-256 为 `D8A66307D559B3DCBDF8B925F89E20704D6669F1F25AC2C9A99BDCF6986B322B`。安装器解包资源核对通过，包含 `backend\generate_materials.py`、客户预置 `config\production.json`、`config\production.example.json`、`ms-playwright`、`python-runtime\python.exe`、`libreoffice\program\soffice.exe` 和 `requirements.txt`；预置配置检查为 `SOFT_MODEL_MODE=gpt`、`SOFT_ACCOUNT_PROVIDER=newapi`、文本模型 `gpt-5.5`、图片模型 `gpt-image-2`、`SOFT_CUSTOMER_PRESET_CONFIG=true`，仅确认 API Key/Base URL 字段存在，未输出真实密钥或请求地址。打包日志仅出现 `package.json` 缺少 description/author、默认 Electron 图标、重复 dependency 引用和 Node `DEP0190` 提示，均未影响安装器生成。
- 2026-07-09 修复在院病人监测 APP 样本截图阶段误失败：质量门禁原先把任何 `待完善` 都视为占位文案，导致真实医疗业务状态 `入院评估待完善` 被误判为 `泛化记录名`。现已将截图可见文本门禁和最终材料占位校验同步收窄为只拦 `内容待完善`、`说明待完善`、`文案待完善`、`描述待完善`、`信息待完善`、`资料待完善` 等真实占位句；失败目录 `output\禾马兔在院病人监测系统-20260709-143725-7853` 复测 `ui_visible_text_placeholder_hits=[]`，同时 `内容待完善/说明待完善` 仍会被拦截。本次验证：`python -m py_compile backend\generate_materials.py backend\softcopyright\generator.py backend\softcopyright\docgen.py backend\softcopyright\screenshots.py backend\softcopyright\llm_manual.py backend\softcopyright\ui_blueprint.py backend\softcopyright\industry_subtypes.py backend\softcopyright\product_experience.py backend\softcopyright\ai_frontend_codegen.py backend\softcopyright\validator.py` 通过；`node --check desktop\electron\main.cjs`、`node --check desktop\electron\preload.cjs`、`npm run build` 通过。
- 2026-07-09 继续修复同一在院病人监测 APP 样本最终校验误失败：材料真实性、运行截图、源码和 ZIP 白名单均已通过，实际仅停在 `manual_pdf_text_density_not_ready`；人工渲染第 4 页和第 19 页确认两页均为移动端竖屏截图图文说明页，分别有 601/629 字业务说明，只因截图占页高导致 `pypdf` 抽取行数为 21/22。`analyze_manual_pdf_text_density()` 已新增 `figure_text_page` 软通过：含 `图：` 图注、正文不少于 16 行、字符数不少于 500、且包含足够业务操作词的图文页可通过，同时纯文字低行数页仍失败、稀疏截图页不计入正文密度页。失败 PDF 复测 `manual_pdf_text_density_ready=true`、`manual_pdf_low_text_density_pages=[]`、`manual_pdf_text_density_figure_pass_pages=[4,19]`。
- 2026-07-09 针对客户反馈“手册内容和截图对不上、找不到详情和查询按钮、源码页底部留空”继续修正文档生成：说明书模块章节现在会读取对应截图 HTML 的可见入口，移动端 APP/小程序页面若没有真实 `查询` 按钮，将生成“搜索与筛选、查看详情、查看预警、收藏患者、入院摘要”等与截图一致的小节，不再套用后台台账的“查询、添加、编辑、删除、导入导出、操作列”话术；若 GPT 模块正文与移动端截图入口冲突，会自动改用截图对齐段落。源码鉴别材料严格保持每页 50 行、总页数 60 页、超过 60 页时前 30 页 + 后 30 页连续抽取；为减少页底留白，源码正文行距最终调整为 15.2pt、字号保持 10pt，并继续过滤源码空行和注释行。校验评分恢复为 `source_lines_per_page == 50`。用当前失败目录源码工程 smoke 通过：`lines_per_page=50`、`source_selected_pages=60`、`selection_mode=first_30_last_30_continuous`、`source_material_filler_line_count=0`。
- 2026-07-09 优化桌面端生成过程展示：过程详情列表不再在每条日志中重复显示阶段名、百分比和“已运行”时间，这些信息保留在顶部阶段条和当前状态区；单条日志现在只显示执行角色、动作内容和时间戳，辅助文字字重降低，当前行高亮也更轻，减少“生成风格参考图 / 44% / 已运行”在相邻区域重复造成的杂乱感。
- 2026-07-10 针对客户连续反馈“HTML 生成耗时过长、页面风格不统一、文字超出重叠、代码页未铺满、40 分钟仍在生成”完成正式 GPT 后台截图链路架构转向：`backend/softcopyright/ai_frontend_codegen.py` 新增 `stable-component-shell` 默认模式，仍保留 GPT UI 蓝图和 gpt-image-2 全局风格参考，但后台 `admin` 页面不再逐页调用 GPT 生成自由 HTML/CSS，而是由本地稳定组件壳生成统一侧栏、顶部栏、指标卡、业务表格、地图/趋势、操作结果和运行记录区域。报告来源更新为 `gpt-visual-reference-stable-component-shell`，架构策略记录为 `reference-driven-stable-component-shell`；如需回到旧链路，可显式设置 `SOFT_AI_FRONTEND_MODE=llm-html`、`freeform-html` 或 `legacy`。这会显著减少截图阶段 page-level LLM 调用，降低 503/超时/自由 CSS 溢出风险。
- 2026-07-10 同步补强稳定壳门禁：新增 `tests/test_stable_component_shell.py`，断言后台稳定壳在 `require_llm=True` 时不会调用 page-level LLM，并生成 `stable-app` 与 `runtime-record-panel`。本地 Playwright smoke 输出 `output\stable-component-shell-smoke-20260710`，登录页、首页、模块页、操作页、统计页均为 1280x720，`_assert_page_text_layout_quality()` 和 `_assert_screenshot_content_geometry()` 通过；修复 smoke 中发现的稳定壳表格 `height:100%` 导致底部行越界问题，表格改为紧凑固定行高并限制底部区域行数。工程验证通过：`python -m py_compile backend\softcopyright\ai_frontend_codegen.py backend\softcopyright\screenshots.py backend\generate_materials.py backend\softcopyright\generator.py`，`python -m unittest discover -s tests -p "test_stable_component_shell.py" -v`，`python -m unittest discover -s tests -p "test_dashboard_runtime_api.py" -v`，`node --check desktop\electron\main.cjs`，`node --check desktop\electron\preload.cjs`，`npm.cmd run build`。
- 2026-07-11 根据“有重叠应自动处理，而不是增加模板”的反馈调整方向：截图阶段新增浏览器内自动布局修复器 `_auto_repair_page_text_layout()`，Playwright 截图前会先检测文字溢出、视口越界和非父子元素重叠；发现问题时自动压缩按钮/标签/表格行高和字号、约束容器溢出、对绝对定位/固定定位重叠控件沿 Y 方向挪开，并在必要时轻微缩放页面，随后重新执行原有硬门禁。新增回归 `test_layout_repair_moves_overlapping_absolute_controls`，构造两个绝对定位重叠按钮，确认修复前可检测到 `overlap`，修复后无布局问题。稳定壳 smoke 输出 `output\stable-layout-repair-smoke-20260711`，5 个页面均通过“自动修复 -> 布局门禁 -> 截图几何检查”。本阶段明确不通过继续增加模板数量来解决重叠问题。
- 2026-07-12 根据客户对操作手册的三项反馈完成修复：目录改为点引导线加右侧真实页码，生成链路先转换一次 PDF 获取正文标题页，再回填 DOCX 并二次转换，新增 `manual_toc_page_numbers_ready` 硬门禁；操作页中的确认抽屉、详情抽屉、确认面板、modal/dialog 统一限制在视口中央，GPT/React 提示词同步禁止贴底弹窗；Playwright 截图阶段新增可见操作控件裁图，说明书中的 `【查看详情】`、`【添加】` 等按钮文字会以内嵌控件图片替代，并优先使用当前二级界面的实际主操作。小艾听歌软件恢复样本最终为 26 页、19 张界面截图、15 项目录真实页码，`validation.ready_for_delivery=true`、`findings=[]`；逐页 PDF 栅格检查未发现裁切、重叠或目录错页。
- 2026-07-13 完成桌面端 GPT 配置脱敏改造：Electron 的 `get-model-config` 与 `save-model-config` 不再向渲染进程返回完整 API Base URL 或 API Key，只返回配置状态和“已配置（地址已隐藏）”提示；高级设置新增请求地址状态、写入式“更换请求地址”和“更换 API Key”密码框，留空时保留本地已有配置，保存成功后立即清空输入值。新增 `tests/test_desktop_model_config_secrets.py`，防止后续改动重新引入 IPC 密钥或请求地址回显。
- 2026-07-12 上述修复完成后重新生成客户 NSIS 安装器：`release\customer-installer\Soft Copyright Generator Setup 0.1.0.exe`，大小 `578,711,252` 字节（约 `551.90 MB`），SHA-256 为 `99522A1C35FAC4FC19612537BD74786F570BD330BCE0523E04402A40AE118C93`。打包成功；日志中的 package description/author、默认 Electron 图标、重复依赖与 Node `DEP0190` 仍为非阻断提示。文档 QA 遗留的独立 LibreOffice 进程导致运行时准备脚本清理旧目录时出现一次文件占用提示，但安装器已正常生成，随后已终止该 QA 进程。
- 2026-07-12 修复说明书内嵌按钮图片被正文固定行高裁切：按钮裁图本身完整，但原 13.5pt 行高小于 0.22 英寸图片高度，LibreOffice 导出 PDF 时会裁掉按钮上下边缘。现在仅对包含按钮图片的段落使用 19pt 行高与 1pt 上下间距，普通正文排版不变；新增回归断言按钮段落行高。小艾听歌软件恢复生成后，`4.7.2 添加 / 4.7.3 搜索与筛选` 所在第 22 页已按 100% 栅格检查，两个“确认登记”按钮的圆角、边缘和文字均完整，最终 27 页材料再次通过 `validation.ready_for_delivery=true`、`findings=[]`。
- 2026-07-12 按钮完整性修复后重新生成客户安装器：`release\customer-installer\Soft Copyright Generator Setup 0.1.0.exe`，大小 `602,703,500` 字节（约 `574.78 MB`），SHA-256 为 `C8C17E90962AC6C717CEA3384C66AFAC0F2C2D88752323CC1612197F305B4AE5`。打包成功，仅保留既有 package description/author、默认图标、重复依赖和 Node `DEP0190` 非阻断提示。
- 2026-07-12 同步修复材料 ZIP 被占用时的交付路径传递：`make_zip_files()` 原本已生成带时间戳的回退 ZIP，但生成器没有接收其返回路径，报告仍可能指向被占用的旧包；现在 `generation_report.json`、校验和最终结果统一引用真实新包。当前按钮修复材料包为 `output\小艾听歌软件-20260711-215258-5900--材料包-20260712-114254-293049.zip`，SHA-256 为 `912775189ABE424BCBAA76429A0CE664AFC85965BAF6807E2F5BDA007EDE83E0`，`validation.ready_for_delivery=true`、`findings=[]`。
- 2026-07-12 根据客户反馈“移动音乐页面全部是登记、低风险操作也要求确认、部分弹窗过窄、操作文案不自然”完成交互语义重构：新增 `interaction_semantics.py`，移动端二级页按模块标题与业务语义选择“查看搜索结果、播放歌曲、查看歌词、收藏歌单、查看歌手详情、查看专辑详情、调整播放顺序、下载歌曲”，并携带 `interaction_mode`、`interaction_surface`、`requires_confirmation`；播放、浏览、歌词、收藏、队列排序和下载启动全部为即时操作，不再生成登记表单、确认弹窗或办理话术。只有删除、清空、支付、注销、覆盖、重置、取消下载、正式发布等高影响动作允许确认。移动端确需确认的弹窗宽度调整为 `calc(100vw - 32px)`、最大 688px，操作页根节点和手机壳强制铺满 720px。新增浏览器硬门禁：即时操作页出现“登记/确认播放/确认下载/等待用户确认”或可见 dialog 会直接失败。小艾听歌软件 8 张二级截图和操作手册已重新生成，PDF 中“登记/确认登记”命中均为 0，8 个动作均为 `instant`，最终 25 页、19 张截图，`validation.ready_for_delivery=true`、`findings=[]`。
- 2026-07-12 交互语义重构后重新生成客户安装器：`release\customer-installer\Soft Copyright Generator Setup 0.1.0.exe`，大小 `602,712,781` 字节（约 `574.79 MB`），SHA-256 为 `E5878004CD7B1BA96F939367218674A571934EA3220C241A9B89043236CB6759`。最新材料包为 `output\小艾听歌软件-20260711-215258-5900--材料包-20260712-125923-013390.zip`，SHA-256 为 `F9E0A94F27458939AEA50596F832A250A851F527AB0A14ABCE4419FC920F9942`。打包成功，仍只有 package description/author、默认 Electron 图标、重复依赖和 Node `DEP0190` 非阻断提示。
- 2026-07-13 根据客户反馈调整操作手册目录排版：目录条目固定行距由 15pt 增至 20pt、段后距由 2pt 增至 4pt，目录标题下间距由 14pt 增至 20pt；一级章节使用 11pt 加粗，二级功能项保持 10.5pt 并增加 0.25 英寸缩进。15 项典型目录仍保持单页，但不再集中挤在页面上半部，章节层级也更容易扫读。
- 2026-07-13 目录排版调整后复用缓存重建小艾听歌软件样本：操作手册保持 25 页、目录 15 项真实页码、界面截图 19 张，`validation.ready_for_delivery=true`、`findings=[]`；最新材料包为 `output\小艾听歌软件-20260711-215258-5900--材料包-20260713-003240-723013.zip`，SHA-256 为 `59B5CE2A94E5EF6F58B443A46BE0DFD75ACC36935DEEAEB93D39272AA72D6D2F`。目录第 2 页已用 Poppler 栅格化复核，无换页、裁切、重叠或点引导线错位。
- 2026-07-13 已重新生成客户版 NSIS 安装器：`release\customer-installer\Soft Copyright Generator Setup 0.1.0.exe`，大小 `602,713,129` 字节（约 `574.79 MB`），SHA-256 为 `9B0021D8CFC9635E5CC78E7F6BFB7CFBFC769C03E3B6C4911794DFC04ED77A39`。打包成功，日志仅有 package description/author、默认 Electron 图标、重复依赖和 Node `DEP0190` 非阻断提示。
- 2026-07-13 继续优化操作手册正文分页：标题启用 `keep_with_next/keep_together`，截图段落与图注保持同页，图注再与第一条操作说明保持同页；当前页空间不足时由 Word/LibreOffice 将“标题或截图组合”整体移至下一页，避免截图留在页尾、图注掉到下一页。截图后的操作说明统一改为带悬挂缩进的编号步骤，普通正文固定行距由 13.5pt 放宽为 14.5pt、段后距由 0 增至 2pt，改善上半页文字过密的观感。
- 2026-07-13 上述分页优化经真实恢复样本迭代验证：正文样式参数限定在操作手册，避免影响源码材料每页 50 行；统计分析概述调整到截图前，用于填充功能章节结束后的剩余页面。小艾听歌软件最终为 27 页，原截图与图注跨页问题已消除，截图后说明统一为编号步骤，`manual_pdf_low_text_density_pages=[]`，源码 PDF 仍为 60 页，目录 15 项真实页码、截图 19 张，`validation.ready_for_delivery=true`、`findings=[]`。最新材料包为 `output\小艾听歌软件-20260711-215258-5900--材料包-20260713-030634-248749.zip`，SHA-256 为 `AC147FBFC13439865E0AF33E6E81E454417A9AD6071F21BFBE06AAAC1202E739`。
- 2026-07-13 已重新生成包含分页优化的客户版 NSIS 安装器：`release\customer-installer\Soft Copyright Generator Setup 0.1.0.exe`，大小 `602,713,608` 字节（约 `574.79 MB`），SHA-256 为 `C2D7C4D297928D3192C925FE8C72CD3E968E2D94847702F8107520144FA6EB43`。安装包内 `docgen.py` 已核对包含手册专用 14.5pt 行距、标题/截图分页约束、编号步骤和统计概述前置逻辑；打包日志仅有既有非阻断提示。
- 2026-07-13 将手册排版优化从单一样本验收提升为全局生成策略：所有软件类型统一使用 `global-adaptive-v1` 排版配置；DOCX 分析新增截图段、图注、标题分页保护数量和编号步骤数量，生成阶段新增 `manual_pagination_constraints_ready`、`manual_numbered_steps_ready` 硬门禁，最终规范性校验和报告同步这些字段。任何行业或截图方向的手册只要未完整应用全局分页约束，或截图后没有编号步骤，都会停止交付，而不是依赖人工发现。
- 2026-07-13 全局排版策略新增竖屏 720×1280 与横屏 1280×720 双方向组件回归，两种截图均通过同一 `global-adaptive-v1` 分页门禁。正式缓存样本重新生成后报告记录截图段 `19/19`、图注 `19/19`、标题 `50/50` 全部受分页保护，编号步骤 95 条，`manual_pagination_constraints_ready=true`、`manual_numbered_steps_ready=true`、`validation.ready_for_delivery=true`、`findings=[]`。最新材料包为 `output\小艾听歌软件-20260711-215258-5900--材料包-20260713-042615-155025.zip`，SHA-256 为 `5ED39EB2DAA04F5E1D80489190D3D6E3877A5EA4DC484777FED68E2D2BDCFE4B`。两次 Default Template 完整跨类型任务被既有上游界面类型匹配门禁提前拦截，未进入手册阶段；临时输出已清理，排版跨方向验证改由不调用模型的独立组件回归完成。
- 2026-07-13 已重新生成包含全局排版门禁的客户版 NSIS 安装器：`release\customer-installer\Soft Copyright Generator Setup 0.1.0.exe`，大小 `602,973,720` 字节（约 `575.04 MB`），SHA-256 为 `DDFC92CFB83BAD65EB98DB3AE3EC0DE981F7DE95682D484EF163D9890292F067`。安装包内 `docgen.py`、`generator.py`、`validator.py` 已核对包含 `global-adaptive-v1` 和两个硬门禁字段。
- 2026-07-13 定位并修复同一本手机手册内界面视觉大小不一致：原始 PNG 均为 720×1280，差异来自部分 GPT React 页面把主要手机壳限制为 `max-width:430px`，另一些页面使用完整 `width:720px`。React/HTML 提示词现明确禁止 375/390/430px 窄手机模拟框；Playwright 截图前新增手机内容壳几何硬门禁，主要 `.phone/.phone-shell/.mobile-shell/.app-shell/.mobile-screen/.game-frame` 必须至少覆盖 680px 且左右贴近 720px 画布边缘，否则停止截图并要求重新生成页面。该规则对所有 APP、小程序和手机游戏生效，不依赖具体软件名称。
- 2026-07-13 手机画布统一修复后重新生成客户版 NSIS 安装器：`release\customer-installer\Soft Copyright Generator Setup 0.1.0.exe`，大小 `602,975,520` 字节（约 `575.04 MB`），SHA-256 为 `A100D431C7A9D2EEF384D7C592D3D6EA65DC6265B3A0E138228D346D0E069393`。安装包内已核对包含手机内容壳宽度检测和窄手机模拟框拒绝提示；14 项相关回归、Python 编译、Electron 语法检查和前端构建通过。
- 2026-07-13 GPT 配置脱敏改造验证与打包完成：`python -m unittest tests.test_desktop_model_config_secrets -v` 2 项通过，`node --check desktop\electron\main.cjs`、`node --check desktop\electron\preload.cjs`、`npm.cmd run build` 通过。重新执行 `npm.cmd run pack:win:customer` 成功，新安装器为 `release\customer-installer\Soft Copyright Generator Setup 0.1.0.exe`，大小 `602,717,943` 字节（约 `574.80 MB`），SHA-256 为 `16032B4EB18F2FE561BB54E9596A81F1F51D6AC66F299CE4E2E45313361FB216`。已直接读取 `win-unpacked\resources\app.asar` 核对：前端包含地址隐藏状态和两个写入式更换输入，主进程 IPC 返回值中的 Base URL 与 API Key 均为空。打包日志仅有既有 package description/author、默认 Electron 图标、重复依赖与 Node `DEP0190` 非阻断提示。
- 2026-07-13 桌面端模型选择改为请求地址驱动：新增主进程 `list-available-models`，使用本地保存的请求地址和 API Key 尝试 `/models` 与 `/v1/models`，兼容 OpenAI-compatible Bearer 认证和 Anthropic `x-api-key` 认证，且拒绝把认证信息跟随到跨站重定向。高级设置打开时、保存新地址后会自动刷新模型目录，并提供“刷新模型”按钮；正式模型和蓝图模型改为动态建议输入，优先展示网关返回模型，同时允许在供应商未提供模型目录接口时手动填写。请求地址和 API Key 仍只停留在 Electron 主进程，渲染进程仅接收模型 ID。
- 2026-07-13 动态模型目录验证与打包完成：当前用户新配置网关的模型目录请求返回 HTTP 200，共 7 个模型，包含 `gpt-5.6-luna`、`gpt-5.6-sol`、`gpt-5.6-terra`；`python -m unittest tests.test_desktop_model_config_secrets -v` 3 项通过，Electron 主进程/预加载脚本语法检查和 Vite 构建通过。新客户安装器 `release\customer-installer\Soft Copyright Generator Setup 0.1.0.exe` 大小 `602,719,264` 字节（约 `574.80 MB`），SHA-256 为 `206CBD3BF2CE79D5440F9D98786A6BF4CE5EB260F75ED3BC5BD8289EF04F8C90`。直接读取安装包 `app.asar` 已确认包含模型目录 IPC、Bearer/Anthropic 两种认证、预加载桥接、自动目录状态和“刷新模型”界面。打包日志仅有既有非阻断提示。
- 2026-07-13 精简顶部设置入口并增加抽屉动效：删除模型按钮右侧重复的独立设置图标，只保留显示当前模型与推理强度的按钮作为高级设置入口，并将顶部操作区保持右对齐。设置抽屉改为常驻 DOM，通过遮罩 220ms 淡入/淡出和面板 280ms 右侧滑入/滑出完成展开收起动画，关闭期间禁用指针事件，并支持系统“减少动态效果”偏好。
- 2026-07-13 修复动态模型已拉取但下拉框不直观的问题：原实现使用 Chromium `datalist`，模型只在输入框聚焦或输入文字时作为建议弹出，容易被误认为列表为空。正式生成模型与蓝图模型现改为标准 `select`，直接显示网关返回的全部模型；另外保留“自定义模型 ID”输入，兼容没有模型目录接口或需要手动指定模型的供应商。
- 2026-07-13 顶部入口、设置动画和标准模型下拉框完成真实浏览器验收：Playwright 1280×1280 渲染确认顶部仅保留模型设置按钮且位于最右侧，设置面板能从右侧展开并在关闭后完全移出、不遮挡页面，正式模型和蓝图模型均被浏览器识别为 `combobox`。`tests.test_desktop_model_config_secrets` 4 项、Electron 语法检查与 Vite 构建通过。重新生成客户安装器 `release\customer-installer\Soft Copyright Generator Setup 0.1.0.exe`，大小 `602,719,315` 字节（约 `574.80 MB`），SHA-256 为 `1CC38D949A3F538FBE6510F99C4720132D70A704F96E8325BC9D1AC28E9458E0`；直接读取包内 `app.asar` 已确认包含标准模型选择、自定义模型输入、刷新模型按钮及抽屉位移/淡入淡出 CSS。
- 2026-07-13 新增软件品牌图标：设计采用深海军蓝到青绿色圆角底座、白色文档、认证勾选徽章和金色 AI 星芒，保持与桌面端现有蓝绿界面一致，并针对 16px/32px 小尺寸使用粗轮廓和低细节结构。矢量源文件为 `build/icon.svg`，将同步生成透明 `build/icon.png` 和多尺寸 `build/icon.ico`；Electron 窗口、Windows 可执行文件、桌面快捷方式与 NSIS 安装器统一使用该图标。
- 2026-07-13 图标接入验证与打包完成：透明 PNG 为 512×512 RGBA，四角 alpha 为 0；ICO 包含 16、24、32、48、64、128、256px 七档尺寸，缩略图检查中 16px 仍可辨认文档和认证徽章。Electron 语法、`package.json`、4 项桌面配置回归和 Vite 构建通过。新客户安装器 `release\customer-installer\Soft Copyright Generator Setup 0.1.0.exe` 大小 `603,004,556` 字节（约 `575.07 MB`），SHA-256 为 `55A1D2866A9E20593200E4B3021922994650374D312D66E66E37A0E79A9759BA`；包内 `resources\icon.png` 已核对为透明 512×512 图标，electron-builder 使用 `build/icon.ico`，打包日志已不再出现“default Electron icon is used”。
- 2026-07-13 针对资源管理器仍显示旧安装器图标完成原因核验：从 `Soft Copyright Generator Setup 0.1.0.exe` 的 PE 资源直接提取图标，与 `build/icon.png` 缩放到 32×32 后像素平均差为 0，证明新图标已经嵌入，旧显示来自 Windows 对同路径同文件名 EXE 的图标缓存。为避免客户继续命中缓存，版本提升为 `0.1.1` 生成新安装器文件名，并在 NSIS 配置中显式设置 `installerIcon`、`uninstallerIcon`、`installerHeaderIcon` 为 `build/icon.ico`。
- 2026-07-13 图标缓存规避版安装器生成并验证完成：新文件为 `release\customer-installer\Soft Copyright Generator Setup 0.1.1.exe`，大小 `603,090,836` 字节（约 `575.15 MB`），SHA-256 为 `2E0CB4EC0A0222AE27B5C4F0C7DF8234F55571F0CF59298B4809B711B41ED746`。从新 EXE 的 PE 资源提取图标保存到 `output\installer-embedded-icon-0.1.1.png`，与源图标缩放到 32×32 后像素平均差为 0；新文件名避开旧 `0.1.0` Explorer 缓存，同时安装器、卸载器和安装头图标均已显式绑定。
- 2026-07-13 启动与新图标一致的前端品牌化第一阶段：顶部加入图标品牌锁定区，统一深海军蓝、青绿、亮青和金色设计变量；新增“输入需求、生成蓝图、确认模块、生成材料、检查交付”五阶段导航并由现有状态自动推进；空白蓝图区使用图标、AI 星芒和能力标签；底部输入区升级为带任务说明的浮动创建栏；成功结果新增品牌渐变“软著材料包已准备完成”主卡片。生成、队列、设置和文件打开逻辑保持不变。
- 2026-07-13 品牌化第一阶段完成验证与打包：`tests.test_desktop_model_config_secrets` 5 项、Electron 语法检查和 Vite 构建通过；Playwright 分别以 1280×860 和最小窗口 1080×720 验收，顶部流程完整、空白状态无裁切、底部创建栏不遮挡主内容，截图保存为 `output\playwright\brand-refresh-1280x860.png` 与 `brand-refresh-1080x720.png`。新客户安装器 `release\customer-installer\Soft Copyright Generator Setup 0.1.1.exe` 大小 `603,227,357` 字节（约 `575.28 MB`），SHA-256 为 `E60C4BC40758ADE64B2B116EBB43B72DEC6CAF8DC9D210FF106AA2B3E9EE7E32`；包内 `app.asar` 已核对包含品牌图标资源、五阶段导航、任务创建栏、结果主卡和品牌 CSS。
- 2026-07-13 前端品牌化第二阶段完成实现：任务队列增加品牌标识、状态胶囊、进度渐变和当前任务高亮；蓝图模块保留高密度表格编辑方式，但每行升级为带阴影、品牌序号、聚焦反馈和胶囊元数据的独立卡片；生成过程强化当前阶段卡、运行呼吸反馈和折叠详情展开动画；设置抽屉改为固定品牌头、独立滚动内容和固定保存区，生成参数、GPT 配置、模型配置分别使用图标化卡片标题和渐进进入动画。所有配置字段与业务行为保持不变。
- 2026-07-13 品牌化第二阶段完成验证与打包：`tests.test_desktop_model_config_secrets` 6 项、Electron 语法检查和 Vite 构建通过；Playwright 实际检查设置抽屉固定头/滚动内容/固定保存区，并通过注入一次性浏览器 QA 队列验证等待、完成、失败三种任务卡，截图保存为 `output\playwright\brand-phase2-settings.png` 和 `brand-phase2-queue.png`。新客户安装器 `release\customer-installer\Soft Copyright Generator Setup 0.1.1.exe` 大小 `603,228,388` 字节（约 `575.28 MB`），SHA-256 为 `949D988FD65E5694909FF98720840D7F45805BF3174793F4819150ED143FA302`；包内 `app.asar` 已核对包含固定设置结构、队列品牌标识、模块悬停卡片、过程展开动画与运行呼吸动效。
- 2026-07-13 根据界面截图反馈完成图标语义和重复度修正：品牌图标只保留在顶部主品牌区，空白状态改为“文档校验”功能图标，设置标题改为“调节器”，队列改为“有序列表”，任务输入根据状态使用“文档”或“加号”；生成过程图标会按蓝图、视觉、源码、文档、打包阶段动态切换。修复过程卡图标 34px 但网格首列仅 24px 导致的文字重叠，首列调整为 40px；同时移除主按钮所有 SVG 无条件旋转的旧规则，仅加载状态图标旋转，避免中止方框显示为旋转菱形。
- 2026-07-13 图标语义修正完成真实浏览器验收与重新打包：Playwright 测得生成过程图标与文字间距为 `14px`，中止方框的 `animation` 和 `transform` 均为 `none`；空白页与生成过程验收图保存为 `output\playwright\semantic-icons-overview.png`、`semantic-icons-process.png`。`tests.test_desktop_model_config_secrets` 7 项、Electron 主进程/预加载脚本语法检查和 Vite 构建通过。新客户安装器 `release\customer-installer\Soft Copyright Generator Setup 0.1.1.exe` 大小 `603,246,871` 字节（约 `575.30 MB`），SHA-256 为 `0C1379A0A69B8217AA4EA7E1BCBBD73C678B70FA02DE969412B73880758FB242`；直接读取包内 `app.asar` 已确认品牌图片资源只引用一次、过程网格为 40px 图标列、仅显式 loading 状态旋转且不存在主按钮 SVG 无条件旋转规则。
- 2026-07-14 定位并修复客户安装版在 55% 稳定失败的问题：electron-builder 自动把原生 `esbuild.exe` 解包到 `resources\app.asar.unpacked`，旧版却让 Vite 从 `app.asar` 虚拟路径启动，导致 `spawn ... esbuild.exe ENOENT`。Electron 主进程现会解析并向 Python/Node 子进程显式传入 `ESBUILD_BINARY_PATH`。同时针对 `gpt-5.6-sol` 网关大量 524（本机最新追踪中 353 次请求、327 次失败、325 次 524、平均失败等待 126.9 秒）增加前端专用快速止损：默认超时 90 秒、自动重试 0 次，首批页面请求失败后打开熔断并取消尚未开始的页面；蓝图、说明书等其他阶段的重试策略保持不变。
- 2026-07-14 增加独立“界面生成模型”配置，模型目录中的任意模型可分别用于正式内容、蓝图和 React 页面生成；配置保存为 `SOFT_MODEL_GPT_FRONTEND_NAME`，旧配置未提供时继续跟随正式生成模型。修复版提升为 `0.1.2`，44 项完整回归、Python 编译、Electron 语法检查、Vite 构建和 1280×860 设置抽屉浏览器验收均通过；包内 Electron + Vite + JSX 实际构建成功（330ms），确认 `app.asar.unpacked` 中的 esbuild 可执行。新客户安装器 `release\customer-installer\Soft Copyright Generator Setup 0.1.2.exe` 大小 `603,248,407` 字节（约 `575.30 MB`），SHA-256 为 `DB64BD308883956D3D966C2C9B80BC20128B8774D79EFDCD91D52548DE17FE95`；设置验收图为 `output\playwright\frontend-model-settings-0.1.2.png`。
- 2026-07-14 过程详情左侧节点收敛为两种明确状态：历史事件统一显示绿色勾选“已完成”，当前运行事件显示青色旋转环“进行中”，连接线使用完成态青绿色；去除原先按业务角色着色但难以理解的多色小圆点，并把节点移入正常网格列，避免左侧负边距导致裁切。浏览器 fixture 验收记录 4 个完成节点、1 个进行中节点且 `clipped=false`，截图为 `output\playwright\process-node-states-0.1.3.png`；9 项桌面回归、Electron 语法检查和 Vite 构建通过。版本提升为 `0.1.3`，新客户安装器 `release\customer-installer\Soft Copyright Generator Setup 0.1.3.exe` 大小 `603,249,634` 字节（约 `575.30 MB`），SHA-256 为 `B0DA8255C56D6946B33998A660A0A1B11A2DA7687B3D36D0867ACCCE455B3BEB`，包内 `app.asar` 已确认包含 `completed`/`in-progress` 双状态和对应 CSS，旧多色角色圆点规则已移除。
- 2026-07-14 修复 `gpt-5.6-sol` 在 React 页面生成阶段反复超时的问题：旧流程会为每个页面重复上传约 1.67 MB、1672×941 的 image2 参考图，使兼容网关关闭文本流式输出；同时两个 3800-token 大请求并行，均在 90 秒被熔断。新版从实际参考图提取尺寸、主色和提示摘要形成可复用文本风格契约，页面请求不再重复传图；前端默认单路生成，单页输出上限降为 3000 token、目标 6000–9500 字符，总时限调整为 120 秒，并只对超时/524 等临时错误重试当前页一次，成功组件继续缓存。真实 `maitokens + gpt-5.6-sol` 验收中，`login` 在 91 秒生成并落盘，修正后的 `dashboard` 在约 106 秒完成且 React + Vite 构建通过，随后两张业务页面双路测试也全部成功；说明原 50% 失败点已从不可恢复整批熔断改为可完成、可续跑的逐页生成。46 项完整回归、Python 编译、Electron 语法检查和 Vite 构建通过。版本提升为 `0.1.4`，客户安装器 `release\customer-installer\Soft Copyright Generator Setup 0.1.4.exe` 大小 `603,252,031` 字节（约 `575.31 MB`），SHA-256 为 `40CCB40EA6560C328D3EEDC7CD4B13213093E25E3724468F942D1812FCBB378C`；包内核验确认 Electron 配置和外置后端均包含本次修复。
- 2026-07-14 修复 0.1.4 仍把流式响应累计时长误判为网络超时的问题：`SOFT_LLM_AI_FRONTEND_TIMEOUT_SECONDS=120` 现在只负责连接/连续无数据的读超时，持续返回内容的 SSE 流改用独立 `SOFT_LLM_STREAM_HARD_TIMEOUT_SECONDS=600` 安全上限，避免模型仍在输出时于第 120 秒被客户端主动中止。失败任务已缓存 6 个页面，针对截图中实际失败的 `domain_02_42251` 使用相同 `maitokens + gpt-5.6-sol`、相同蓝图和参考图复测，在 135.7 秒成功返回、落盘并通过 React + Vite 构建；该页面此前分别在 121 秒和 147 秒被旧累计计时器误杀。47 项完整回归、Python 编译、Electron 语法检查和 Vite 构建通过。版本提升为 `0.1.5`，客户安装器 `release\customer-installer\Soft Copyright Generator Setup 0.1.5.exe` 大小 `603,253,950` 字节（约 `575.31 MB`），SHA-256 为 `8F6AC8055BA8BEF847F450E061276FEA40E89D4ADA6069F401AE96D7DC51C7A7`；包内核验确认 Electron 和 Python 后端均包含 600 秒流式硬保护配置。
- 2026-07-14 删除过程详情中的“原始运行日志”折叠区及对应深色日志样式，只保留整理后的阶段条、完成/进行中节点和失败报告。重试链路升级为失败阶段断点续跑：从 `generation-failure.json` 读取失败阶段，失败阶段之前不再发送过程事件；产品蓝图直接读取 `generated_source/product-blueprint.json`，技术架构从蓝图恢复，源码阶段直接扫描已有工程并恢复 source info，不再重写源码或逐文件重复刷日志。React 页面会预扫描 JSX/CSS/meta 缓存，已完成页面不再发送“生成组件”事件或调用模型，只显示“从未完成页面继续 X/N”。当前道路工程任务只读验收识别为 `screenshots` 阶段，源码 7650 行直接加载，27 页中已缓存 10 页，下一次从第 11 页 `config_operation_3_3` 继续。49 项完整回归、Python 编译、Electron 语法检查和 Vite 构建通过。版本提升为 `0.1.6`，客户安装器 `release\customer-installer\Soft Copyright Generator Setup 0.1.6.exe` 大小 `603,258,781` 字节（约 `575.31 MB`），SHA-256 为 `94448E4B65CBF43A2DE6C078C63252214AE1965F183E5F23C4D381B055AEDAE3`；包内核验确认断点恢复、源码直接加载、仅缓存缺失时发送生成事件，并确认前端包内已不存在“原始运行日志”文本。
- 2026-07-14 修复复杂运行结果面板导致道路工程任务在截图阶段反复失败的问题：运行时 API v7 不再用长句替换带标题、图表、指标和按钮的 `.operation-result`，而是保留原布局并追加 18px 紧凑操作日志证据；布局修复器只压缩纯文本结果，不再把复杂面板强制收成 42px。另修复固定 1280×720 画布越界缩放时“缩小后又反向扩宽”的问题，6px 右侧越界可正确收敛。道路工程任务已从失败节点续跑完成，27/27 张真实项目运行截图、65 次成功业务接口请求、7650 行源码、33 页操作手册 PDF、60 页源码 PDF 和最终材料 ZIP 全部生成，警告数为 0。
- 2026-07-14 截图阶段增加逐页持久化检查点：每张页面通过运行接口、交互语义、文字几何和截图内容校验后，立即保存 HTML 指纹、截图尺寸、接口请求证据和按钮裁剪信息；再次重试时只恢复连续有效前缀，并从首个未完成页面继续，不再从 1/27 重跑。续跑入口也会从 `generated_source/product-blueprint.json` 恢复已完成业务蓝图，直接建立 `confirmed-outline` 语义契约，跳过原先每次重复的约 80–90 秒名称理解模型调用。新增复杂结果布局、固定画布缩放、截图连续前缀恢复和产品蓝图恢复回归用例，53 项完整测试、Python 编译、Electron 主进程/预加载脚本检查和 Vite 构建全部通过。当前开发版本为 `0.1.8`。
- 2026-07-14 `0.1.8` 客户安装器构建并核验完成：`release\customer-installer\Soft Copyright Generator Setup 0.1.8.exe` 大小 `603,262,919` 字节（约 `575.32 MB`），SHA-256 为 `E0DC995EF21425C7484D028A911480BC9C9C504450CE30A96EC35F7C7120FD8E`。直接检查 `win-unpacked\resources\backend`，确认包内包含 `soft-runtime-api-script:v7`、`screenshot-checkpoint.json`、复杂结果面板选择器、产品蓝图续跑恢复，并已移除会反向扩宽画布的旧缩放逻辑。打包仅有缺少 package description/author、重复依赖与 Node `DEP0190` 非阻断提示。
- 2026-07-15 修复 Word/WPS 手册封面、目录和页眉出现字形或页码裁切的问题：根因是正文固定 14.5pt 行距被 24pt 封面标题和 22pt 目录标题继承，以及页眉表格正好占满页面全部可用宽度。封面主标题/副标题现分别使用 34pt/30pt 行高，目录标题使用 30pt，一级/二级标题使用 18pt；页眉、目录和运行环境表格统一缩入 0.35cm 安全区，页码单元格增加右内边距，目录页码制表位从 6.05in 收至 5.85in，并让页眉配置支持重复调用时清理旧表格。道路工程 33 页手册已重新生成并全页渲染，自动边界扫描最小左/右留白为 133px/149px，无页面触边；PDF 文本密度检查 13 个正文页全部通过、低密度页为 0。原 ZIP 被占用无法覆盖，修复包为 `output\道路工程施工进度智能管控系统-20260714-123558-5168--材料包-排版修复.zip`，SHA-256 为 `300E6887AFF6353DB34E4FCA08571BDD5D15970911BCB6FABF2009E8E1D7E8B0`。54 项完整回归、Python 编译、Electron 检查和 Vite 构建通过。
- 2026-07-15 修复“轨道交通施工质量分析检验大数据系统”在最终校验阶段因说明书末页稀疏而失败的问题：全局常见问题章节由 7 段扩展为 10 段业务化排障说明，覆盖附件预览、统计口径和重复业务记录处理，不放宽 PDF 文本密度门禁。任务从 `manual` 节点断点续跑，复用已完成的视觉参考、125 个源码文件、27 个 React 页面和 27 张截图；最终 33 页说明书末页由 14 行/497 字提升为 20 行/727 字，`manual_pdf_text_density_ready=true`、`ready_for_delivery=true`。材料包为 `output\轨道交通施工质量分析检验大数据系统-20260715-121646-5899--材料包.zip`，大小 `13,255,688` 字节，SHA-256 为 `A574C131BA8E4CC11E809F44A74903E1709BBC1E0A63AE2378218A6D8E83EE2A`；61 项完整回归、Python 编译、Electron 主进程/预加载脚本检查和 Vite 构建全部通过。
- 2026-07-15 全局统一操作手册截图的组件外壳并简化功能说明：React 运行工程新增确定性的 `SharedAppShell`，登录页之外统一使用同一套品牌栏、`工作首页 / 功能办理 / 任务跟踪 / 统计分析 / 系统设置` 主导航和当前功能标题；模型只生成内容区，禁止重复设计全局顶栏。页面差异化限定在业务内容区，并限制为一个主要工作区、最多两个辅助区域、4 个指标卡、6 个主要按钮和 5 行示例表格，避免不同页面像不同软件，也避免所有页面套同一主体模板。说明书每个模块收敛为 1-2 段简介、最多 4 条截图说明、每个功能最多 3 条界面说明和 1 段补充操作，不再重复堆叠相同流程文案。轨道交通样本复用已有 27 个 React 页面，从截图节点重新生成 27 张配图和手册，首页与项目质量策划页已确认顶部组件完全一致、主体内容保持差异；手册由 33 页收敛为 28 页，PDF 密度检查和交付校验通过。最新材料包大小 `13,546,177` 字节，SHA-256 为 `CF28EFEE5B6A0D243CF6BA8853E20481DD8A64261BD922AEC330C84BE515966B`。61 项完整回归、Python 编译、Electron 主进程/预加载脚本检查和 Vite 构建全部通过。
- 2026-07-16 完成“功能说明与图片仍无法对应”诊断：抽查轨道交通样本 PDF 第 5、6、7、9、15、22 页并与对应 React 截图对照，确认当前 `manual_ui_consistency_ready=true` 只代表截图数量/顺序、图注标题和按钮标签来源一致，不代表正文与截图可见内容语义一致。当前 `_actual_screenshot_operation_notes()` 的字段说明仍取自模块级 `module.data_fields[:5]`，二级页图注仍可能使用“窗口展示业务字段、处理状态和操作按钮”泛化模板；校验器没有检查正文提到的字段、指标、面板、状态或操作步骤是否真实出现在该张截图中。典型问题包括统计页说明要求选择“业务模块、状态条件并点击查询”，但截图只有周期、线路、标段和单位工程筛选且没有查询按钮；施工测量预警页截图突出最大偏差、关联测点、复测时限、成果版本、偏差热区和超限测点队列，正文却只罗列模块蓝图字段。该问题已明确为“元数据一致性通过、可见内容语义一致性缺失”，本次仅诊断，尚未修改生成逻辑。
- 2026-07-16 完成全局截图级图文语义一致性改造：Playwright 每页截图前从真实浏览器 DOM 提取 `visible_content_summary`，结构化保存页面标题/业务区标题、指标名、字段标签、状态词、筛选项、筛选按钮、真实操作按钮和完整可见文本；摘要写入 `UiScreenshot`、`screenshot-checkpoint.json` 和 `generation_report.json`，检查点版本提升为 v3，旧截图会自动失效并重采。正式生成新增 `ui_visible_content_summary_ready` 硬门禁，27 张截图只要有一页缺少摘要就停止生成。说明书图注、模块简介和截图后编号步骤优先消费当前页摘要，不再直接使用模块级 `data_fields` 或泛化图注；统计周期等筛选按钮会与业务操作分离，避免把“本周/本月”写成办理动作。`analyze_manual_ui_consistency()` 新增语义覆盖和虚构引用校验：正文若引用截图中不存在的字段、指标、状态、筛选项、查询/打印/归档动作，或没有解释截图主要内容，会返回 `manual_ui_semantic_ready=false` 并阻止交付。轨道交通 27 页真实 React 页面全量 smoke 已通过：`summary_count=27`、`semantic_checked=27`、`semantic_mismatch=0`、`semantic_coverage_missing=0`、标题/按钮错误均为 0；重建手册 DOCX/PDF 位于 `tmp\semantic-manual-smoke`，PDF 文本密度通过，并已栅格抽查项目质量策划、查询、施工测量和统计页，无裁切、重叠或按钮缺失。73 项完整回归通过。
- 2026-07-16 完成人工补正版手册对比评审：解压 `智能生产效率提升平台4补正.zip`，抽查工业机器人路径规划平台、工业设备智能监控软件、智能化生产数据分析系统、智能生产效率提升平台四套人工手册，并重点对比同名智能生产效率提升平台。四套人工手册为 37-54 页、101-172 个 PDF 图片对象、平均每页约 9-11 行文字，核心写法是把每个模块固定拆为查询、添加、导出、导入、编辑、删除，每个动作配按钮裁图、列表/表单/弹窗截图和 1-3 段结果说明。人工版优点是操作覆盖完整、截图与动作位置直接对应、页面阅读压力低；缺点是 CRUD 文案高度重复、语法和标点较粗糙，且软件概况中存在等保/ISO、准确率、行业落地数量和效果百分比等难以从材料验证的宣传性表述。同名旧生成版为 32 页、46 个图片对象、26263 个正文字符、平均 27.1 行/页，明显过密且“展示业务字段、处理状态和操作按钮”泛化图注出现 16 次。使用当前语义链路重建的同名 smoke 为 29 页、121 个图片对象、13583 个正文字符、平均 17 行/页，`semantic_checked=27`、错误与覆盖缺失均为 0，已消除泛化图注并使字段、状态和按钮与截图对应；但当前每个模块仍只有主界面和 2 个二级页，缺少人工版那种查询/新增/导入导出/编辑/删除的完整操作覆盖，且少量筛选说明会把当前值、日期、人员或产线编码串联得过细。结论是后续应保留现有 DOM 语义门禁，同时引入“模块操作覆盖矩阵”和操作结果截图，不应回退人工版的重复模板文案。
- 2026-07-16 完成全局模块操作覆盖矩阵：新增 `operation_coverage.py`，后台模块默认生成 3 个互补操作页、移动端默认 2 个，并按查询、表单维护、导入、导出、分析、流程处理、详情结果、即时操作和破坏性操作分类；只对删除/失效/覆盖等高风险操作要求确认，播放、歌词、查询等即时操作不再套确认框。后台与移动端的本地模板和 GPT 页面规格均写入 `interaction_action/mode/surface/requires_confirmation`，截图检查点提升为 v4 并把交互元数据纳入指纹。正式生成新增 `ui_operation_coverage_ready` 门禁，要求每个模块达到数量和操作类型覆盖，避免再次退回“主界面 + 两张泛化二级页”。页面相似度门禁同步允许同一种查询/表单组件跨模块复用，但仍会拦截多个主模块页面完全同构，兼顾统一组件 UI 与业务内容差异。
- 2026-07-16 修复新增操作页导致全局风格图被无意义重画的问题：视觉参考缓存键升级为 `style-identity-v2`，不再包含页面数量；同一软件、同一视觉身份从 27 页扩展到 35 页时直接复用原 `style_reference.png`。若失败重试覆盖了 manifest，但原风格图和旧 prompt 仍有效，可按旧版页数缓存键恢复并迁移，无需再次请求图片模型。智能生产样本验证中，风格图已从旧 27 页缓存恢复并应用到 35 页；当前外部模型网关随后在新增 React 操作页返回 502，正式 GPT 页面未强制使用模板兜底。
- 2026-07-16 增加整本手册的终端类型一致性门禁：说明书会根据截图横竖方向补全 `expected_renderer`，桌面截图若正文任意位置仍出现“移动端、手机 App、小程序、底部导航”等描述，`manual_ui_renderer_mismatch_count` 会阻止交付。智能生产烟测最初发现概述仍写“移动端生产效率工作入口”，现已改为桌面业务入口并从技术架构、部署说明和运行环境中清理移动端冲突。操作覆盖烟测输出位于 `tmp\operation-coverage-manual-smoke`：35 张截图、24 张操作页、29 页 A4 PDF、113 个图片对象，标题/按钮错误为 0、可见内容语义错误和覆盖缺失为 0、终端类型冲突为 0。已渲染抽查概述页、生产计划协同查询/校验/归档页和末页，未见裁切、图片重叠或按钮缺失。末页为 14 个抽取行、517 字的完整故障处理收尾页；考虑到软著并无每页必须 30 行的硬性要求，新增 `closing_content_page` 软通过：保留少于 30 行的风险提示，但内容达到 12 行/450 字且包含充分操作语义时不再错误阻断。

## 已知问题

1. Windows PowerShell inline / pipeline 传中文参数时可能把中文变成 `????`，长验证命令应使用 UTF-8 文件、JSON 配置、Node/Python 内部构造 Unicode 字符串，或使用 `\u...` 转义。
2. 客户登录、充值、激活码绑定还没有产品化，目前通过 NewAPI token 配置实现。
3. 客户预制安装包已在客户环境验证通过；后续重点从安装可用性转为材料真实性、规范性和业务差异化。
4. 内置 LibreOffice 后安装包体积从约 366 MB 增至约 573 MB，安装解压时间明显变长；客户已验证可用，但仍需在后续版本中关注包体体积和安装体验。
5. GPT-only 完整端到端已跑通；当前策略明确以生成内容质量、真实性和材料一致性为第一优先，耗时不作为降级理由，但需要让长耗时阶段更可视化、可诊断、可恢复。
6. 当前队列已支持桌面端本地持久化和最近失败输出恢复，但仍是顺序队列，不是并发调度器；本阶段不做并发生成，避免多个 GPT/image2/Playwright 任务同时争用本地服务端口和 NewAPI 网关。后续如果要做并发，需要先把每个任务的输出目录、端口池、事件 taskId 和取消语义下沉到主进程调度器。
7. 正式截图已改为强制启动生成项目服务、从真实服务 URL 截图，并要求截图页在浏览器中实际请求生成项目业务接口、把业务数据写入可见区域，同时检查操作结果证据、图表日期/单位上下文、交通运输拓扑细节、页面几何有效区域和包内页面重复度；本地文件/Pillow 渲染仅保留给非正式开发脚本或无硬门禁调用。后续需要继续扩大到更多架构样本的编译/启动覆盖，而不是恢复静态截图兜底。
8. 真实 GPT 游戏单独抽样和金融 GPT-only 端到端验收均已跑通；后续优化必须以不降低材料真实性、一致性和可申请性为前提。
9. 当前 NewAPI 网关仍可能出现 503、524 或读超时；React 页面生成使用 120 秒连接/连续无数据超时和 600 秒流式硬上限，临时错误只重试当前页一次，成功页面持续缓存，截图阶段也已支持逐页检查点恢复。后续应增加生成前模型健康检查和分阶段响应时长展示，而不是静默切换模型或模板兜底。
10. 说明书 PDF 正文页已接入逐页文本行数校验，但 `pypdf` 对复杂版式、图片内文字和部分字体编码的抽取能力仍可能有限；后续真实样本验收时需要复核 `manual_pdf_low_text_density_pages` 是否符合人工观感。
11. 源码材料已按严格连续模式抽取，并已通过内部顺序清单把核心业务文件前移/尾置；页眉右侧页码、页眉横线、字号和行距已对齐手写样例。交通运输正式样本已额外排除纯运行入口壳进入源码 PDF 正文，后续仍需在多架构、移动端和嵌入式样本中复核前 30 页和后 30 页的人工观感。
12. 截图级 `visible_content_summary` 和图文语义门禁已经接入正式链路；当前剩余风险是不同前端命名习惯可能影响 DOM 分类质量，例如自定义组件没有 `metric`、`field-label`、`filter-block` 等语义类名。后续需要继续用手机 APP、小程序、游戏和自由 React 页面抽样，确保标题、指标、字段、筛选项和即时操作均能稳定分类。
13. 模块级操作覆盖矩阵和结构化蓝图契约已接入正式链路，后台默认 3 个操作页、移动端默认 2 个，并按真实业务语义选择动作；后续风险转为更多软件类型的契约质量与动作分类抽样，尤其是只读看板、媒体播放、移动端即时操作和少见行业流程。
14. 智能生产 35 页正式任务已经通过，但 AI 组件当前仍共享普通 CSS 类作用域；运行时稳定尺寸规则已拦截本次 `.metric-strip` 跨页面污染，后续仍应在 React 构建阶段引入组件级选择器前缀或 CSS Modules，从源头消除新类名碰撞。

## 下一步建议

优先级从高到低：

1. 将本轮正式验收修复提升到 `0.1.9` 或下一发布版本，重新构建客户安装器并检查包内 `screenshots.py`、结构化操作分类和图文一致性逻辑，避免继续交付缺少 2026-07-15 至 2026-07-16 升级的 `0.1.8`。
2. 为 AI React 组件增加构建期 CSS 作用域隔离，重点覆盖 `.metric-strip / .workspace / .table-panel / .operation-result / .dialog` 等高频类名，并用现有 35 页正式缓存验证视觉指纹和截图门禁不回退。
3. 用只读监控看板、手机 APP 和媒体播放三类正式样本验证结构化操作分类与终端归一化，确保不会虚构新增/删除、不会给播放增加确认框，也不会把桌面端说明写成移动端。
