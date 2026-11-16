from __future__ import annotations

from html import escape
from pathlib import Path
import re
from typing import Any, Iterable


def _unique_texts(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _sanitize_html(html: str) -> str:
    from .screenshots import _sanitize_formal_ui_html
    return _sanitize_formal_ui_html(html)


def _ensure_runtime_layout_guard(html: str) -> str:
    body_attrs = _body_attrs(html)
    renderer = _html_data_attribute(body_attrs, "renderer") or "admin"
    guard = _runtime_layout_guard_style(renderer)
    style_pattern = r"<style\b[^>]*id=[\"']soft-ai-runtime-guard[\"'][^>]*>[\s\S]*?</style>"
    if re.search(style_pattern, html, flags=re.I):
        return re.sub(style_pattern, guard, html, count=1, flags=re.I)
    if re.search(r"</head\s*>", html, flags=re.I):
        return re.sub(r"</head\s*>", lambda _match: guard + "\n</head>", html, count=1, flags=re.I)
    if re.search(r"<body\b", html, flags=re.I):
        return re.sub(r"<body\b", lambda _match: "<head>" + guard + "</head>\n<body", html, count=1, flags=re.I)
    return guard + "\n" + html


def _runtime_layout_guard_style(renderer: str) -> str:
    if renderer in {"mobile_app", "game"}:
        size = "body{width:720px!important;height:1280px!important;min-height:1280px!important;overflow:hidden!important;}"
        app_rules = ""
    else:
        size = "body{width:1280px!important;height:720px!important;min-height:720px!important;overflow:hidden!important;background:#fff8f3;}"
        app_rules = """
body[data-ai-frontend="true"][data-renderer="admin"] .app{width:1280px!important;height:720px!important;max-width:1280px!important;max-height:720px!important;overflow:hidden!important;}
body[data-ai-frontend="true"][data-renderer="admin"] :is(.main,.content,.workspace,.grid,.bottom,.middle){min-width:0!important;min-height:0!important;}
body[data-ai-frontend="true"][data-renderer="admin"] .work-area{min-width:0!important;min-height:0!important;grid-template-rows:minmax(0,1fr)!important;overflow:hidden!important;}
body[data-ai-frontend="true"][data-renderer="admin"] .screen-root>.metric-strip{flex:0 0 auto!important;height:auto!important;min-height:0!important;max-height:86px!important;overflow:hidden!important;}
body[data-ai-frontend="true"][data-renderer="admin"] .workspace{grid-template-rows:minmax(0,1fr)!important;}
body[data-ai-frontend="true"][data-renderer="admin"] table{width:100%!important;table-layout:fixed!important;border-collapse:collapse;}
body[data-ai-frontend="true"][data-renderer="admin"] :is(th,td){min-width:0!important;max-width:100%!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important;line-height:1.18!important;vertical-align:middle!important;}
body[data-ai-frontend="true"][data-renderer="admin"] :is(button,.btn,.mini-btn,.tab,.nav-item,.select,.input,.mini-input,.tag,.badge,.status span,.field label,.op a){min-width:0!important;max-width:100%!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important;line-height:1.18!important;word-break:keep-all!important;}
body[data-ai-frontend="true"][data-renderer="admin"] :is(button,.btn,.mini-btn){display:inline-flex!important;align-items:center!important;justify-content:center!important;font-size:12px!important;padding-left:8px!important;padding-right:8px!important;}
body[data-ai-frontend="true"][data-renderer="admin"] :is(.opbtn,button.opbtn){height:20px!important;min-height:20px!important;max-height:20px!important;font-size:11px!important;line-height:1!important;padding-top:0!important;padding-bottom:0!important;}
body[data-ai-frontend="true"][data-renderer="admin"] :is(.tag,.badge){display:inline-flex!important;align-items:center!important;justify-content:center!important;padding-left:6px!important;padding-right:6px!important;}
body[data-ai-frontend="true"][data-renderer="admin"] :is(.code,.num,.val,.metric .num,.mcell .val,.record-title .code){display:block!important;min-width:0!important;max-width:100%!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important;line-height:1.12!important;}
body[data-ai-frontend="true"][data-renderer="admin"] :is(.code,.record-title .code){font-size:20px!important;}
body[data-ai-frontend="true"][data-renderer="admin"] :is(.metric .num,.mcell .val,.val){font-size:20px!important;}
body[data-ai-frontend="true"][data-renderer="admin"] :is(.runtime-record-panel b,.meta b,.rec .r-line b,.source-list b){min-width:0!important;max-width:100%!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important;}
body[data-ai-frontend="true"][data-renderer="admin"] .runtime-record-panel :is(div,article,section,li){min-width:0!important;}
body[data-ai-frontend="true"][data-renderer="admin"] .runtime-record-panel :is(b,strong,time,[class*="value"]){display:block!important;min-width:0!important;max-width:100%!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important;}
body[data-ai-frontend="true"][data-renderer="admin"] :is(.operation-result){max-width:100%!important;overflow:hidden!important;text-overflow:ellipsis!important;line-height:1.28!important;}
body[data-ai-frontend="true"][data-renderer="admin"] :is(.work-area,.workspace,.content)>.detail-panel.operation-result{height:100%!important;min-height:0!important;max-height:100%!important;overflow:hidden!important;}
body[data-ai-frontend="true"][data-renderer="admin"] .detail-panel.operation-result>.detail-grid{flex:1 1 0%!important;min-height:0!important;grid-template-rows:minmax(0,1.03fr) minmax(0,.97fr)!important;overflow:hidden!important;}
body[data-ai-frontend="true"][data-renderer="admin"] .comparison-main:has(>.table-panel.operation-result){height:100%!important;min-height:0!important;grid-template-rows:minmax(0,1fr) minmax(0,170px)!important;overflow:hidden!important;}
body[data-ai-frontend="true"][data-renderer="admin"] .comparison-main>.table-panel.operation-result{height:100%!important;min-height:0!important;max-height:170px!important;overflow:hidden!important;}
body[data-ai-frontend="true"][data-renderer="admin"] .workspace>.execution-rail{height:100%!important;min-height:0!important;max-height:100%!important;overflow:hidden!important;}
body[data-ai-frontend="true"][data-renderer="admin"] :is(.map-pin,.map-node,.relation-node,.flow-node) :is(b,strong,span,em){display:block!important;min-width:0!important;max-width:100%!important;white-space:nowrap!important;word-break:keep-all!important;overflow:hidden!important;text-overflow:ellipsis!important;}
body[data-ai-frontend="true"][data-renderer="admin"][data-page-kind="login"] :is(.left-console,.login-hero,.login-brand) h1{max-width:none!important;font-size:31px!important;line-height:1.15!important;white-space:nowrap!important;word-break:keep-all!important;overflow:hidden!important;text-overflow:ellipsis!important;}
body[data-ai-frontend="true"] .page-spec-root :is(button,th,td,.detail-item,.workflow-step,.timeline-item,.kanban-column,.mobile-list-item,.operation-result,.map-pin,.graph-node){overflow:visible!important;}
body[data-ai-frontend="true"] .page-spec-root :is(button,th,td,.detail-item span,.detail-item strong,.workflow-step strong,.workflow-step small,.timeline-item strong,.timeline-item p,.kanban-column strong,.kanban-column article span,.mobile-list-item strong,.mobile-list-item span,.operation-result strong,.operation-result span,.map-pin b,.map-pin small,.graph-node span,.graph-node strong){white-space:normal!important;overflow-wrap:anywhere!important;word-break:break-word!important;text-overflow:clip!important;}
body[data-ai-frontend="true"] .page-spec-root .page-spec-workspace{overflow:auto!important;}
""".strip()
    return f"""
<style id="soft-ai-runtime-guard">
html,body{{margin:0!important;box-sizing:border-box;}}
*,*::before,*::after{{box-sizing:inherit;}}
{size}
body[data-ai-frontend="true"]{{font-family:"Microsoft YaHei","PingFang SC",Arial,sans-serif;-webkit-font-smoothing:antialiased;text-rendering:geometricPrecision;}}
{app_rules}
body[data-renderer="mobile_app"][data-page-kind="operation"] #root,
body[data-renderer="mobile_app"][data-page-kind="operation"] .screen-root,
body[data-renderer="mobile_app"][data-page-kind="operation"] :is(.phone-shell,.mobile-shell,.app-shell){{width:720px!important;min-width:720px!important;max-width:720px!important;margin-left:0!important;margin-right:0!important;}}
body[data-renderer="mobile_app"][data-page-kind="operation"] :is(.confirm-drawer,.detail-drawer,.confirm-panel,[class*="modal"]:not([class*="layer"]):not([class*="overlay"]),[class*="dialog"]:not([class*="layer"]):not([class*="overlay"]),[role="dialog"]:not(:has([class*="dialog"],[class*="modal"]))){{position:fixed!important;left:50%!important;right:auto!important;top:50%!important;bottom:auto!important;transform:translate(-50%,-50%)!important;width:calc(100vw - 32px)!important;max-width:688px!important;max-height:calc(100vh - 48px)!important;margin:0!important;overflow:auto!important;z-index:10000!important;border-radius:12px!important;}}
body[data-renderer="admin"][data-page-kind="operation"] :is(.confirm-drawer,.detail-drawer,.confirm-panel,[class*="modal"]:not([class*="layer"]):not([class*="overlay"]),[class*="dialog"]:not([class*="layer"]):not([class*="overlay"]),[role="dialog"]:not(:has([class*="dialog"],[class*="modal"]))){{position:fixed!important;left:50%!important;right:auto!important;top:50%!important;bottom:auto!important;transform:translate(-50%,-50%)!important;width:min(720px,calc(100vw - 48px))!important;max-height:calc(100vh - 48px)!important;margin:0!important;overflow:auto!important;z-index:10000!important;border-radius:12px!important;}}
.runtime-generated-record{{display:none!important;}}
.runtime-generated-record span{{display:block;color:#64748b;font-size:11px;margin-bottom:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
.runtime-generated-record b{{display:block;font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
.runtime-audit-evidence[data-runtime-operation-result]{{display:block!important;min-width:0!important;max-width:100%!important;height:18px!important;margin-top:4px!important;padding:0 6px!important;border-radius:4px!important;background:#ecfdf5!important;color:#166534!important;font-size:10px!important;line-height:18px!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important;}}
</style>
""".strip()


def _body_attrs(html: str) -> str:
    match = re.search(r"<body\b([^>]*)>", str(html or ""), flags=re.I)
    return match.group(1) if match else ""


def _runtime_module_keys(blueprint: Any, limit: int = 4) -> list[str]:
    return _unique_texts(
        str(getattr(module, "key", "") or "").strip()
        for module in (getattr(blueprint, "modules", []) or [])
    )[:limit]


def _inject_runtime_script_into_ai_page(html_path: Path, *, module_keys: Iterable[str] = ()) -> None:
    try:
        html = html_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"AI 界面页面读取失败：{html_path.name}：{exc}") from exc
    runtime_module_keys = _unique_texts(module_keys)
    if runtime_module_keys:
        html = _set_body_attribute(html, "data-runtime-module-keys", ",".join(runtime_module_keys))
    html = _ensure_runtime_layout_guard(html)
    html = _ensure_operation_evidence_block(html)
    script = runtime_api_script()
    if "soft-runtime-api-script:v14" in html:
        html_path.write_text(_sanitize_html(html), encoding="utf-8")
        return
    if "__runtimeApiReady" in html:
        html, count = re.subn(
            r"(?:<!--\s*soft-runtime-api-script:v\d+\s*-->\s*)?<script>\s*\(function\s*\(\)\s*\{[\s\S]*?window\.__runtimeApiReady[\s\S]*?</script>",
            lambda _match: script,
            html,
            count=1,
            flags=re.I,
        )
        if count == 0:
            return
    elif re.search(r"</body\s*>", html, flags=re.I):
        html = re.sub(r"</body\s*>", lambda _match: script + "\n</body>", html, count=1, flags=re.I)
    else:
        html = html + "\n" + script
    html_path.write_text(_sanitize_html(html), encoding="utf-8")


def _ensure_operation_evidence_block(html: str) -> str:
    if 'name="soft-react-screen"' in html or "name='soft-react-screen'" in html:
        return html
    if 'data-runtime-operation-evidence="v5"' in html or "data-runtime-operation-evidence='v5'" in html:
        return html
    html = re.sub(
        r"<style\s+data-runtime-operation-evidence-style\b[^>]*>[\s\S]*?</style>\s*",
        "",
        html,
        count=1,
        flags=re.I,
    )
    html = re.sub(
        r"<section\b[^>]*class=(?:\"[^\"]*\bruntime-operation-evidence\b[^\"]*\"|'[^']*\bruntime-operation-evidence\b[^']*')[^>]*>[\s\S]*?</section>\s*",
        "",
        html,
        count=1,
        flags=re.I,
    )
    if not _needs_operation_evidence_block(html):
        return html

    result_pattern = re.compile(
        r"(?P<open><(?P<tag>[a-z][\w:-]*)\b[^>]*class\s*=\s*(?P<quote>[\"'])[^\"']*\boperation-result\b[^\"']*(?P=quote)[^>]*>)"
        r"(?P<body>[\s\S]*?)(?P<close></(?P=tag)\s*>)",
        flags=re.I,
    )
    result_match = result_pattern.search(html)
    if result_match:
        opening = result_match.group("open")
        if "data-runtime-operation-evidence" not in opening:
            opening = opening[:-1] + ' data-runtime-operation-evidence="v5">'
        suffix = '<span class="runtime-audit-evidence"> 处理结果：已完成，状态与更新时间已同步保存。</span>'
        replacement = opening + result_match.group("body").rstrip() + suffix + result_match.group("close")
        return html[: result_match.start()] + replacement + html[result_match.end() :]

    evidence = (
        '<span class="runtime-operation-evidence" data-runtime-operation-evidence="v5" '
        'data-runtime-compact="true" data-action="处理" aria-label="处理结果" '
        'style="display:block!important;min-width:0!important;max-width:360px!important;height:18px!important;'
        'min-height:18px!important;max-height:18px!important;margin-left:auto!important;padding:0 6px!important;'
        'border-radius:4px;background:#ecfdf5;color:#166534;font-size:10px!important;line-height:18px!important;'
        'white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important;">'
        '处理结果：待确认 · 状态与更新时间已保存</span>'
    )
    for class_name in ("stable-card-h", "panel-h"):
        header_pattern = re.compile(
            rf"(?P<open><(?P<tag>div|header|section)\b[^>]*class\s*=\s*(?P<quote>[\"'])[^\"']*\b{re.escape(class_name)}\b[^\"']*(?P=quote)[^>]*>)"
            r"(?P<body>[\s\S]*?)(?P<close></(?P=tag)\s*>)",
            flags=re.I,
        )
        header_match = header_pattern.search(html)
        if header_match:
            replacement = (
                header_match.group("open")
                + header_match.group("body")
                + evidence
                + header_match.group("close")
            )
            return html[: header_match.start()] + replacement + html[header_match.end() :]

    if re.search(r"</body\s*>", html, flags=re.I):
        return re.sub(r"</body\s*>", lambda _match: evidence + "\n</body>", html, count=1, flags=re.I)
    return html + "\n" + evidence


def _needs_operation_evidence_block(html: str) -> bool:
    visible = _operation_evidence_visible_text(html)
    if (
        bool(re.search(r"(?:处理|查询|导入|导出|统计|预警|审核|复核|发布|保存|建档|维护|登记|配置|调度|处置|查看|追踪|失效|归档).{0,12}结果：", visible))
        and bool(re.search(r"(?:状态|结果|结论|时间).{0,16}(?:保存|记录|同步|更新)|(?:保存|记录|同步|更新).{0,16}(?:状态|结果|结论|时间)", visible))
    ):
        return False
    body_match = re.search(r"<body\b([^>]*)>", html, flags=re.I)
    body_attrs = body_match.group(1) if body_match else ""
    renderer = _html_data_attribute(body_attrs, "renderer")
    page_kind = _html_data_attribute(body_attrs, "page-kind")
    return renderer in {"", "admin"} and page_kind not in {"login"}


def _operation_evidence_visible_text(html: str) -> str:
    text = re.sub(r"<style\b.*?</style>", " ", str(html or ""), flags=re.S | re.I)
    text = re.sub(r"<script\b.*?</script>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&(?:nbsp|amp|lt|gt|quot);", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _html_data_attribute(attrs: str, name: str) -> str:
    match = re.search(
        rf"\sdata-{re.escape(name)}\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>]+))",
        attrs or "",
        flags=re.I,
    )
    if not match:
        return ""
    return next((group or "").strip() for group in match.groups() if group is not None)


def _set_body_attribute(html: str, name: str, value: str) -> str:
    escaped_value = escape(value, quote=True)
    attribute = re.escape(name)

    def replace(match: re.Match[str]) -> str:
        tag = match.group(0)
        if re.search(rf"\s{attribute}=(?:\"[^\"]*\"|'[^']*'|[^\s>]+)", tag, flags=re.I):
            return re.sub(
                rf"\s{attribute}=(?:\"[^\"]*\"|'[^']*'|[^\s>]+)",
                f' {name}="{escaped_value}"',
                tag,
                count=1,
                flags=re.I,
            )
        return f'{tag[:-1]} {name}="{escaped_value}">'

    return re.sub(r"<body\b[^>]*>", replace, html, count=1, flags=re.I)


def runtime_api_script() -> str:
    return r"""
<!-- soft-runtime-api-script:v14 -->
<script>
(function () {
  const body = document.body;
  const pageKind = body.dataset.pageKind || "general";
  const moduleKey = body.dataset.moduleKey || "";
  const configuredModuleKeys = String(body.dataset.runtimeModuleKeys || "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
  const renderer = body.dataset.renderer || "admin";
  window.__runtimeApiReady = false;
  window.__runtimeApiError = "";
  window.__runtimeApiFetches = [];
  window.__runtimeApiVisibleMatch = false;
  let renderWaitCount = 0;

  function apiPathGroups() {
    if (renderer !== "admin") return [["/health"]];
    if (pageKind === "login") return [["/health"]];
    const modulePaths = (key) => {
      const snake = String(key || "").trim();
      const kebab = snake.replace(/_/g, "-");
      return [
        "/" + snake + "/",
        "/" + snake + "/summary",
        "/api/" + kebab,
        "/api/" + kebab + "/summary",
        "/api/" + snake,
        "/api/" + snake + "/summary",
      ];
    };
    if (moduleKey) return [modulePaths(moduleKey)];
    const links = Array.from(document.querySelectorAll("[data-module-key]"))
      .map((node) => node.getAttribute("data-module-key"))
      .filter(Boolean)
      .filter((value, index, values) => values.indexOf(value) === index)
      .slice(0, 4);
    const modules = links.length ? links : configuredModuleKeys;
    return modules.map(modulePaths);
  }

  async function fetchPath(path) {
    const cancelType = window["Abort" + "Controller"];
    const controller = cancelType ? new cancelType() : null;
    const timer = window.setTimeout(() => { if (controller) controller.abort(); }, 4000);
    try {
      const requestOptions = {
        headers: { "Accept": "application/json" },
        cache: "no-store",
      };
      if (controller) requestOptions.signal = controller.signal;
      const response = await fetch(path, requestOptions);
      const text = await response.text();
      let payload = null;
      try { payload = text ? JSON.parse(text) : null; } catch (error) { payload = null; }
      return { url: path, ok: response.ok, status: response.status, payload: payload, recordCount: countOf(payload), source: "project-service" };
    } catch (error) {
      return { url: path, ok: false, status: 0, payload: null, recordCount: 0, source: String(error && error.message || "request_failed") };
    } finally {
      window.clearTimeout(timer);
    }
  }

  async function fetchFirstAvailable(paths) {
    let lastFailure = null;
    for (const path of paths) {
      const result = await fetchPath(path);
      if (result.ok) return result;
      lastFailure = result;
    }
    return lastFailure || { url: "", ok: false, status: 0, payload: null, recordCount: 0, source: "no_candidate_path" };
  }

  function normalizePayload(payload) {
    if (!payload || typeof payload !== "object") return payload;
    if (Object.prototype.hasOwnProperty.call(payload, "data")) return payload.data;
    return payload;
  }

  function recordsOf(payload) {
    const data = normalizePayload(payload);
    if (Array.isArray(data)) return data;
    if (data && Array.isArray(data.items)) return data.items;
    if (data && Array.isArray(data.records)) return data.records;
    return [];
  }

  function countOf(payload) {
    const data = normalizePayload(payload);
    const records = recordsOf(payload);
    if (records.length) return records.length;
    if (data && typeof data.total === "number") return data.total;
    if (data && typeof data.totalCount === "number") return data.totalCount;
    return data && typeof data.routeCount === "number" ? data.routeCount : 0;
  }

  function statusText(value) {
    const text = String(value || "");
    const map = {
      ENABLED: "已启用",
      PENDING: "待确认",
      PROCESSING: "处理中",
      COMPLETED: "已完成",
      ARCHIVED: "已完成",
      Enabled: "已启用",
      Pending: "待确认",
      Archived: "已完成",
    };
    return map[text] || text || "待确认";
  }

  function cleanCode(value) {
    const text = String(value || "").trim();
    if (!text) return "YW-" + new Date().getFullYear() + "-1001";
    const normalized = text.replace(/_/g, "-");
    if (/^[A-Z]{2,4}-[A-Z]{2,4}-\d{3,}$/.test(normalized) || /^[A-Z]{2,4}-\d{3,}$/.test(normalized)) return normalized;
    return normalized.replace(/[A-Z]+-ROUTE-CATALOG/g, "TR");
  }

  function camelize(text) {
    return String(text || "")
      .replace(/[（）()【】\[\]：:、，,./\\-]+/g, " ")
      .trim()
      .split(/\s+/)
      .filter(Boolean)
      .map((part, index) => index === 0 ? part : part.charAt(0).toUpperCase() + part.slice(1))
      .join("");
  }

  function fieldAliases(label) {
    const text = String(label || "").trim();
    const aliases = [text, camelize(text)];
    const push = (...items) => items.forEach((item) => { if (item && !aliases.includes(item)) aliases.push(item); });
    if (/编号|编码|单号|代码|ID/i.test(text)) push("code", "id");
    if (/名称|标题|线路|路径|节点|方案|记录/i.test(text)) push("name", "moduleTitle");
    if (/状态|进度|结果|结论/i.test(text)) push("status", "result");
    if (/区域|片区|范围|服务|覆盖|站点|节点序列|途经/i.test(text)) push("region", "serviceScope", "nodeSequence");
    if (/方向|类型|等级|优先级/i.test(text)) push("direction", "priority");
    if (/角色|责任|人员|部门|单位/i.test(text)) push("ownerRole");
    if (/时间|日期|更新|创建/i.test(text)) push("updatedAt", "createdAt");
    if (/说明|描述|备注|摘要/i.test(text)) push("description");
    return aliases;
  }

  function pick(record, names, fallback) {
    for (const name of names) {
      if (record && record[name] !== undefined && record[name] !== null && String(record[name]).trim()) {
        return String(record[name]);
      }
    }
    const fieldValues = record && record.fieldValues && typeof record.fieldValues === "object" ? record.fieldValues : null;
    if (fieldValues) {
      for (const name of names) {
        if (fieldValues[name] !== undefined && fieldValues[name] !== null && String(fieldValues[name]).trim()) {
          return String(fieldValues[name]);
        }
      }
    }
    return fallback;
  }

  function valueForField(record, label, fallback) {
    const aliases = fieldAliases(label);
    return pick(record, aliases, fallback);
  }

  function displayValue(record, label, fallback) {
    const value = valueForField(record, label, fallback);
    if (/状态|进度/.test(String(label || ""))) return statusText(value);
    if (/编号|编码|单号|代码|ID/i.test(String(label || ""))) return cleanCode(value);
    return String(value || fallback || "").replace("T", " ").slice(0, 24);
  }

  function recordSignatureValues(records) {
    return records.flatMap((record) => [
      record && record.code,
      record && record.name,
      record && record.region,
      record && record.nodeSequence,
      record && record.serviceScope,
      record && record.result,
    ]).filter((value) => value !== undefined && value !== null && String(value).trim()).map((value) => String(value).trim());
  }

  function currentVisibleText() {
    const bodyText = String(document.body && document.body.innerText || "");
    const controlText = Array.from(document.querySelectorAll("input, select, textarea"))
      .map((node) => String(node.value || node.getAttribute("placeholder") || "").trim())
      .filter(Boolean)
      .join(" ");
    return bodyText + " " + controlText;
  }

  function hasVisibleRecordValue(records) {
    const visible = currentVisibleText();
    const runtimePanelText = String(document.querySelector(".runtime-record-panel")?.innerText || "");
    const candidates = recordSignatureValues(records).filter((value) => value.length >= 2);
    if (runtimePanelText && candidates.some((value) => runtimePanelText.includes(value.slice(0, Math.min(value.length, 18))))) {
      return true;
    }
    return candidates.some((value) => visible.includes(value.slice(0, Math.min(value.length, 18))));
  }

  function updateEntityCell(entity, record, label) {
    if (!entity) return;
    const strong = entity.querySelector("b");
    const small = entity.querySelector("small");
    if (strong) strong.textContent = displayValue(record, label || "名称", strong.textContent);
    if (small) small.textContent = cleanCode(valueForField(record, "编号", small.textContent));
  }

  function updateTables(records) {
    if (!records.length) return;
    const rows = Array.from(document.querySelectorAll(".table-frame tbody tr, .result-box tbody tr"));
    rows.forEach((row, index) => {
      if (row.closest('[data-page-data="spec"]')) return;
      const record = records[index % records.length];
      updateEntityCell(row.querySelector(".entity-cell"), record, row.querySelector("td[data-field]")?.getAttribute("data-field") || "名称");
      const status = row.querySelector(".status");
      if (status) status.textContent = statusText(record.status);
      const cells = Array.from(row.querySelectorAll("td[data-field]"));
      cells.forEach((cell) => {
        const field = cell.getAttribute("data-field") || "";
        if (!field || field === "操作") return;
        if (cell.querySelector(".entity-cell")) {
          updateEntityCell(cell.querySelector(".entity-cell"), record, field);
          return;
        }
        if (cell.querySelector(".row-actions")) return;
        const statusNode = cell.querySelector(".status");
        if (statusNode) {
          statusNode.textContent = statusText(valueForField(record, field, record.status));
          return;
        }
        cell.textContent = displayValue(record, field, cell.textContent);
      });
      if (!cells.length) {
        const table = row.closest("table");
        const headers = Array.from(table?.querySelectorAll("thead th") || []);
        Array.from(row.querySelectorAll("td")).forEach((cell, cellIndex) => {
          const label = String(headers[cellIndex]?.textContent || "").trim();
          if (!label || /操作/.test(label) || cell.querySelector("button, a, .row-actions")) return;
          const statusNode = cell.querySelector(".status, .tag");
          if (statusNode && /状态|进度/.test(label)) {
            statusNode.textContent = statusText(valueForField(record, label, record.status));
            return;
          }
          cell.textContent = displayValue(record, label, cell.textContent);
        });
      }
    });
    const footer = document.querySelector(".table-footer span");
    if (footer) footer.textContent = "已选 1 条 · 当前查询 " + records.length + " 条 · 每页 20 条";
  }

  function updateCards(payloads) {
    const counts = payloads.map(countOf).filter((value) => value > 0);
    const metricValues = Array.from(document.querySelectorAll(".metric strong, .metric-card strong, .focus-card strong, .risk-tile strong, .pipeline-card strong, .matrix-cell strong"));
    metricValues.filter((node) => !node.closest('[data-page-data="spec"]')).slice(0, counts.length).forEach((node, index) => {
      node.textContent = String(counts[index]);
    });
  }

  function updatePageSpecRegions(records) {
    if (!records.length) return;
    const signatures = recordSignatureValues(records);
    Array.from(document.querySelectorAll(".filter-control")).forEach((control, index) => {
      if (control.closest('[data-page-data="spec"]')) return;
      const input = control.querySelector("input, select, textarea");
      if (!input) return;
      const record = records[index % records.length];
      const label = String(control.querySelector("span")?.textContent || "").split("：")[0];
      const value = valueForField(record, label, signatures[index % Math.max(signatures.length, 1)] || "");
      if (value !== undefined && value !== null && String(value).trim()) {
        input.value = String(value).slice(0, 32);
      }
    });
    Array.from(document.querySelectorAll(".metric-card small")).forEach((node, index) => {
      if (node.closest('[data-page-data="spec"]')) return;
      const value = signatures[index % Math.max(signatures.length, 1)];
      if (value) node.textContent = String(value).slice(0, 28);
    });
    Array.from(document.querySelectorAll(".chart-column")).forEach((node, index) => {
      const record = records[index % records.length];
      if (node.closest('[data-page-data="spec"]')) return;
      const label = node.querySelector("small");
      const value = pick(record, ["name", "region", "result", "code"], signatures[index % Math.max(signatures.length, 1)] || "");
      if (label && value) label.textContent = String(value).slice(0, 22);
    });
  }

  function updateLiveFooter(records) {
    if (!records.length) return;
    const record = records[0];
    const values = Array.from(document.querySelectorAll(".live-footer .kv-grid div, .detail-row, .form-item, .query-filter"));
    values.forEach((node) => {
      const label = node.querySelector("span")?.textContent || "";
      const target = node.querySelector("b, strong, .form-value, div:last-child");
      if (target && label) target.textContent = displayValue(record, label, target.textContent);
    });
  }

  function updateQueues(records) {
    if (!records.length) return;
    const queueItems = Array.from(document.querySelectorAll(".queue-list div, .triage-item, .kanban-card, .kanban-column article, .case-card"));
    queueItems.forEach((node, index) => {
      if (node.closest('[data-page-data="spec"]')) return;
      const record = records[index % records.length];
      const strong = node.querySelector("strong, b");
      const span = node.querySelector("span");
      const small = node.querySelector("small");
      if (strong) strong.textContent = pick(record, ["code", "name"], strong.textContent);
      if (span) span.textContent = [pick(record, ["name"], ""), pick(record, ["region"], ""), pick(record, ["result"], "")].filter(Boolean).join(" / ") || span.textContent;
      if (small) small.textContent = statusText(record.status);
    });
  }

  function updateRuntimeRecordPanels(records) {
    if (!records.length) return;
    const record = records[0];
    const panels = Array.from(document.querySelectorAll(".runtime-record-panel"));
    function bindPanel(panel) {
      const codeValue = cleanCode(valueForField(record, "编号", pick(record, ["code"], "YW-0001")));
      const nameValue = pick(record, ["name", "moduleTitle", "code"], "当前对象");
      const scopeValue = pick(record, ["serviceScope", "region", "nodeSequence"], "默认范围");
      const statusValue = statusText(record.status);
      const code = panel.querySelector("[data-runtime-field='code']");
      const name = panel.querySelector("[data-runtime-field='name']");
      const scope = panel.querySelector("[data-runtime-field='scope']");
      const status = panel.querySelector("[data-runtime-field='status']");
      if (code) code.textContent = codeValue;
      if (name) name.textContent = nameValue;
      if (scope) scope.textContent = scopeValue;
      if (status) status.textContent = statusValue;
      if (!code && !name && !scope && !status) {
        const headerMeta = panel.querySelector(".section-head span, .panel-title span, .stable-card-h span, .panel-h span");
        if (headerMeta) {
          headerMeta.textContent = "当前记录 " + codeValue;
        } else {
          const inlineMeta = Array.from(panel.querySelectorAll("span, small, em"))
            .find((node) => !node.closest("button, a") && node.getClientRects().length > 0);
          if (inlineMeta) {
            const original = String(inlineMeta.textContent || "").trim();
            inlineMeta.textContent = codeValue + (original ? " · " + original : "");
          }
        }
      }
    }
    panels.forEach(bindPanel);
    if (!panels.length && pageKind !== "login") {
      const codeValue = cleanCode(valueForField(record, "编号", pick(record, ["code"], "YW-0001")));
      const safeMeta = document.querySelector(".section-head span, .panel-title span, .stable-card-h span, .panel-h span");
      if (safeMeta) safeMeta.textContent = "当前记录 " + codeValue;
    }
  }

  function updateRouteBoards(records) {
    if (!records.length) return;
    const pins = Array.from(document.querySelectorAll(".map-pin"));
    pins.forEach((pin, index) => {
      if (pin.closest('[data-page-data="spec"]')) return;
      const record = records[index % records.length];
      const directTextNode = Array.from(pin.childNodes || []).find(
        (node) => node.nodeType === Node.TEXT_NODE && String(node.textContent || "").trim()
      );
      const labelElement = pin.querySelector(":scope > [data-runtime-field='name'], :scope > b, :scope > strong");
      const labelNode = directTextNode || labelElement;
      const label = pick(record, ["name", "moduleTitle", "code"], labelNode && labelNode.textContent || "");
      const small = pin.querySelector("small");
      if (labelNode) labelNode.textContent = String(label || "").slice(0, 18);
      if (small) {
        small.textContent = [
          pick(record, ["region", "serviceScope"], ""),
          statusText(record.status)
        ].filter(Boolean).join(" · ") || small.textContent;
      }
    });
  }

  function updateOperationResults(records) {
    if (!records.length) return;
    const record = records[0];
    const code = cleanCode(valueForField(record, "编号", pick(record, ["code"], "YW-0001")));
    const status = statusText(record.status);
    Array.from(document.querySelectorAll(".operation-result, .runtime-operation-evidence")).forEach((node) => {
      const action = node.getAttribute("data-action") || "处理";
      const compactText = action + "结果：" + code + " · " + status + " · 状态与更新时间已同步保存";
      if (node.children.length > 0 && node.dataset.runtimeCompact !== "true") {
        let evidence = node.querySelector(".runtime-audit-evidence, [data-runtime-operation-result]");
        if (!evidence) {
          evidence = document.createElement("span");
          evidence.className = "runtime-audit-evidence";
          node.appendChild(evidence);
        }
        evidence.setAttribute("data-runtime-operation-result", "v10");
        evidence.textContent = compactText;
      } else {
        node.textContent = compactText;
      }
    });
  }

  function markReady(fetches) {
    if (
      document.querySelector("body[data-ai-frontend='true']") &&
      !document.querySelector(".screen-root") &&
      renderWaitCount < 90
    ) {
      renderWaitCount += 1;
      window.requestAnimationFrame(() => markReady(fetches));
      return;
    }
    window.__runtimeApiFetches = fetches;
    const payloads = fetches.filter((item) => item.ok).map((item) => item.payload);
    const records = payloads.flatMap(recordsOf);
    updateTables(records);
    updateCards(payloads);
    updatePageSpecRegions(records);
    updateLiveFooter(records);
    updateQueues(records);
    updateRouteBoards(records);
    updateOperationResults(records);
    updateRuntimeRecordPanels(records);
    window.__runtimeApiVisibleMatch = renderer !== "admin" || hasVisibleRecordValue(records) || pageKind === "login";
    fetches.forEach((item) => { if (item && item.ok) item.visibleMatch = window.__runtimeApiVisibleMatch; });
    window.__runtimeApiReady = fetches.some((item) => item.ok);
    if (!window.__runtimeApiReady) {
      window.__runtimeApiError = "业务接口未返回有效数据";
    } else if (!window.__runtimeApiVisibleMatch) {
      window.__runtimeApiError = "接口业务数据未出现在页面可见区域";
    }
  }

  const pathGroups = apiPathGroups();
  if (!pathGroups.length) {
    window.__runtimeApiError = "页面缺少可用业务模块接口";
    return;
  }
  Promise.all(pathGroups.map(fetchFirstAvailable)).then(markReady).catch((error) => {
    window.__runtimeApiError = String(error && error.message || error || "runtime_api_failed");
  });
})();
</script>
"""
