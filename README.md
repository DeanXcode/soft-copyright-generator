# 软著材料一键生成桌面工具原型

当前仓库已完成 M1 命令行生成闭环原型：输入软件名称、版本号、编程语言、产品类型和业务提示后，生成源码工程、软件说明书、源码鉴别材料、信息表、材料清单和 zip 材料包。

当前工作进度、真实 NewAPI 接入状态、交付配置方式和下一步建议见：

- [当前进度与交付说明](docs/current-progress-and-delivery.md)

## 安装依赖

```powershell
python -m pip install -r requirements.txt
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

桌面端客户界面只显示 GPT 套餐和余额，API 中转站由服务端或交付环境配置。NewAPI 这类 OpenAI-compatible 中转站可直接作为 GPT 网关使用：

推荐使用隐藏配置文件，不要让客户在界面里填写 API。复制模板：

```powershell
Copy-Item config\production.example.json config\production.json
```

然后编辑 `config\production.json`：

```json
{
  "SOFT_ACCOUNT_PROVIDER": "newapi",
  "SOFT_MODEL_GPT_BASE_URL": "https://smoke2.learn-flow.cn/v1",
  "SOFT_MODEL_GPT_API_KEY": "sk-你的NewAPI调用Token",
  "SOFT_MODEL_GPT_NAME": "gpt-5.4"
}
```

`config\production.json` 已加入 `.gitignore`，不要提交真实 token。

也可以临时使用环境变量：

```powershell
$env:SOFT_MODEL_GPT_BASE_URL="https://your-newapi.example.com/v1"
$env:SOFT_MODEL_GPT_API_KEY="你的NEWAPI_KEY"
$env:SOFT_MODEL_GPT_NAME="gpt-4o-mini"
$env:SOFT_MODEL_BALANCE_LABEL="100000 tokens"
$env:SOFT_MODEL_ACCOUNT_NAME="客户账户"
npm run build
npm run electron
```

也可以使用通用网关变量：

```powershell
$env:SOFT_MODEL_GATEWAY_BASE_URL="https://your-newapi.example.com/v1"
$env:SOFT_MODEL_GATEWAY_API_KEY="你的NEWAPI_KEY"
$env:SOFT_MODEL_GATEWAY_MODEL="gpt-4o-mini"
```

当前模型会优先参与“产品蓝图”和“说明书正文”生成。网关未配置、余额不足或模型请求失败时，会自动回退本地模板，不中断材料生成。

## 业务后台余额接口

如果 `SOFT_ACCOUNT_PROVIDER` 设置为 `newapi`，桌面端会根据 `SOFT_MODEL_GPT_BASE_URL` 自动读取 NewAPI 额度接口：

```http
GET /api/usage/token
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

桌面端会优先读取业务后台余额接口：

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
- 自动提取源码生成源码鉴别材料。
- 超过 60 页时采用前 30 页 + 后 30 页。
- 生成软件说明书、源码文档、信息表、材料清单和生成报告。
- 桌面端仅展示 GPT 套餐；底层可通过 NewAPI / OpenAI-compatible 中转站接入真实模型。
- 已支持 LibreOffice 高保真 PDF 转换；未检测到 LibreOffice 时会自动生成简版 PDF 占位文件。

## LibreOffice

Windows 可通过 winget 安装：

```powershell
winget install --id TheDocumentFoundation.LibreOffice -e --accept-package-agreements --accept-source-agreements
```

程序会自动探测 `soffice` 或常见安装路径：

```text
C:\Program Files\LibreOffice\program\soffice.exe
```

## 后续开发

下一阶段建议接入真实 LLM Provider，并启动 Electron 首页，让用户在首页选择语言、产品类型、模型和随机度后一键生成。
