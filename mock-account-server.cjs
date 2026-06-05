const http = require("http");

const port = Number(process.env.MOCK_ACCOUNT_PORT || 8787);
const token = process.env.MOCK_ACCOUNT_TOKEN || "demo-token";
let usedTokens = 0;

function sendJson(response, statusCode, payload) {
  response.writeHead(statusCode, {
    "Content-Type": "application/json; charset=utf-8",
    "Access-Control-Allow-Origin": "*"
  });
  response.end(JSON.stringify(payload));
}

function readJson(request) {
  return new Promise((resolve, reject) => {
    let body = "";
    request.setEncoding("utf8");
    request.on("data", (chunk) => {
      body += chunk;
    });
    request.on("end", () => {
      try {
        resolve(body ? JSON.parse(body) : {});
      } catch (error) {
        reject(error);
      }
    });
  });
}

function authorized(request) {
  return (request.headers.authorization || "") === `Bearer ${token}`;
}

function extractSoftwareName(prompt) {
  const match = prompt.match(/软件全称[:：]\s*([^\n]+)/);
  return match ? match[1].trim() : "演示业务管理系统";
}

function extractVersion(prompt) {
  const match = prompt.match(/版本号[:：]\s*([^\n]+)/);
  return match ? match[1].trim() : "V1.0";
}

function blueprintResponse(prompt) {
  const softwareName = extractSoftwareName(prompt);
  return {
    industry: "数字化业务管理",
    purpose: "用于业务数据集中管理、流程协同、运行监控和统计分析。",
    summary: `${softwareName}围绕业务档案、流程处理、数据查询、统计分析和权限审计等能力建设，支持用户在统一平台内完成基础资料维护、业务申请处理、记录追踪、报表导出和系统配置，提升日常管理效率和数据一致性。`,
    roles: ["系统管理员", "业务操作员", "审核人员", "统计分析员"],
    pages: ["登录页", "系统首页", "业务档案页", "流程处理页", "综合查询页", "统计报表页", "权限管理页", "日志审计页"],
    modules: [
      {
        key: "business_archive",
        title: "业务档案管理",
        description: "维护业务对象、分类字典、区域组织、状态标签和基础资料变更记录。",
        entities: ["BusinessArchive", "ArchiveCategory", "ArchiveChangeLog"]
      },
      {
        key: "workflow_process",
        title: "流程处理管理",
        description: "支持业务申请、受理、审核、流转、退回、办结和全过程状态追踪。",
        entities: ["WorkflowCase", "ProcessNode", "ApprovalRecord"]
      },
      {
        key: "query_center",
        title: "综合查询管理",
        description: "按关键字、状态、时间、角色和业务类型组合检索数据并查看详情。",
        entities: ["QueryCondition", "QueryResult", "SavedFilter"]
      },
      {
        key: "statistics_report",
        title: "统计报表分析",
        description: "按业务类型、处理效率、时间趋势和组织维度生成统计报表。",
        entities: ["ReportDefinition", "MetricResult", "ExportTask"]
      },
      {
        key: "notification_center",
        title: "消息通知管理",
        description: "管理待办提醒、审核通知、异常预警、站内消息和通知发送记录。",
        entities: ["NoticeMessage", "TodoReminder", "NotifyRule"]
      },
      {
        key: "permission_audit",
        title: "权限与审计管理",
        description: "维护用户角色、菜单权限、数据范围、登录日志和关键操作审计。",
        entities: ["UserRole", "PermissionRule", "AuditLog"]
      }
    ]
  };
}

function paragraphs(title, count) {
  return Array.from({ length: count }, (_, index) => `${title}第${index + 1}部分围绕业务使用过程展开说明，描述用户在系统中完成数据维护、流程处理、状态跟踪、结果查询和异常处理的具体操作，并保证各环节记录完整、口径一致。`);
}

function manualResponse(prompt) {
  return {
    overview: paragraphs("软件概述", 6),
    login_main: paragraphs("登录与首页", 6),
    modules: [
      { key: "business_archive", title: "业务档案管理", paragraphs: paragraphs("业务档案管理", 8) },
      { key: "workflow_process", title: "流程处理管理", paragraphs: paragraphs("流程处理管理", 8) },
      { key: "query_center", title: "综合查询管理", paragraphs: paragraphs("综合查询管理", 8) },
      { key: "statistics_report", title: "统计报表分析", paragraphs: paragraphs("统计报表分析", 8) },
      { key: "notification_center", title: "消息通知管理", paragraphs: paragraphs("消息通知管理", 8) },
      { key: "permission_audit", title: "权限与审计管理", paragraphs: paragraphs("权限与审计管理", 8) }
    ],
    statistics: paragraphs("统计分析", 6),
    security: paragraphs("安全权限", 6),
    faq: paragraphs("常见问题", 4)
  };
}

function chatPayload(requestBody) {
  const prompt = (requestBody.messages || []).map((item) => item.content || "").join("\n");
  const content = prompt.includes("返回 JSON 字段：") ? manualResponse(prompt) : blueprintResponse(prompt);
  const text = JSON.stringify(content);
  const promptTokens = Math.ceil(prompt.length / 2);
  const completionTokens = Math.ceil(text.length / 2);
  usedTokens += promptTokens + completionTokens;
  return {
    id: `mock-chat-${Date.now()}`,
    object: "chat.completion",
    created: Math.floor(Date.now() / 1000),
    model: requestBody.model || "mock-gpt",
    choices: [
      {
        index: 0,
        message: { role: "assistant", content: text },
        finish_reason: "stop"
      }
    ],
    usage: {
      prompt_tokens: promptTokens,
      completion_tokens: completionTokens,
      total_tokens: promptTokens + completionTokens
    }
  };
}

const server = http.createServer((request, response) => {
  if (request.method === "GET" && request.url === "/api/v1/account/balance") {
    if (!authorized(request)) {
      sendJson(response, 401, { ok: false, message: "Unauthorized" });
      return;
    }
    sendJson(response, 200, {
      ok: true,
      accountName: "演示客户",
      balanceTokens: Math.max(0, 100000 - usedTokens),
      balanceLabel: `${Math.max(0, 100000 - usedTokens).toLocaleString("zh-CN")} tokens`,
      expiresAt: "2026-12-31"
    });
    return;
  }

  if (request.method === "POST" && request.url === "/v1/chat/completions") {
    if (!authorized(request)) {
      sendJson(response, 401, { error: { message: "Unauthorized" } });
      return;
    }
    readJson(request)
      .then((body) => sendJson(response, 200, chatPayload(body)))
      .catch((error) => sendJson(response, 400, { error: { message: error.message } }));
    return;
  }

  sendJson(response, 404, { ok: false, message: "Not Found" });
});

server.listen(port, "127.0.0.1", () => {
  console.log(`Mock gateway listening on http://127.0.0.1:${port}`);
  console.log(`Use token: ${token}`);
});
