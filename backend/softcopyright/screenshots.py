from __future__ import annotations

from dataclasses import dataclass
from html import escape
import json
from pathlib import Path
import re
import shutil
import socket
import subprocess
import time
from typing import Any, Iterable
import urllib.request

from .blueprint import FeatureModule, ProductBlueprint
from .llm.provider import LLMProvider
from .models import GenerationTask
from .packager import write_json
from .ui_blueprint import UiBlueprint, UiScreenBlueprint, build_ui_blueprint, is_game_like

ADMIN_VIEWPORT = {"width": 1280, "height": 820}
GAME_VIEWPORT = {"width": 720, "height": 1280}


@dataclass
class UiScreenshot:
    key: str
    title: str
    caption: str
    html_path: str
    image_path: str | None = None
    width: int = 0
    height: int = 0


def generate_ui_screenshots(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    output_dir: Path,
    llm_provider: LLMProvider | None = None,
    source_info: dict | None = None,
    emit=None,
    use_project_server: bool = False,
) -> tuple[dict[str, UiScreenshot], list[str], UiBlueprint]:
    ui_dir = output_dir / "ui_screenshots"
    ui_dir.mkdir(parents=True, exist_ok=True)
    prototype_dir = _prototype_dir(output_dir, source_info)
    prototype_dir.mkdir(parents=True, exist_ok=True)
    ui_blueprint = build_ui_blueprint(task, blueprint, llm_provider, emit=emit)
    write_json(ui_dir / "ui_blueprint.json", ui_blueprint.to_dict())
    write_json(prototype_dir / "ui_blueprint.json", ui_blueprint.to_dict())
    _emit(emit, 45, "生成截图页面")
    screenshots = _build_pages(task, blueprint, prototype_dir, ui_blueprint)
    _write_prototype_manifest(task, blueprint, prototype_dir, ui_blueprint, screenshots)
    _write_prototype_index(task, blueprint, prototype_dir, ui_blueprint, screenshots)
    _write_prototype_readme(task, prototype_dir, ui_blueprint, screenshots)
    _publish_project_prototype(task, prototype_dir, ui_blueprint, screenshots, source_info)
    warnings: list[str] = list(ui_blueprint.warnings)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        _render_fallback_images(task, blueprint, screenshots, ui_dir)
        return _to_map(screenshots), warnings + [f"Playwright 未安装，已使用本地图像渲染生成界面截图：{exc}"], ui_blueprint

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            viewport = GAME_VIEWPORT if ui_blueprint.renderer == "game" else ADMIN_VIEWPORT
            page = browser.new_page(viewport=viewport, device_scale_factor=1, is_mobile=ui_blueprint.renderer == "game")
            project_server = None
            render_base_url = ""
            render_mode = "file"
            try:
                if use_project_server:
                    try:
                        project_server = _start_project_server(source_info)
                        render_base_url = project_server["base_url"]
                        render_mode = "project-server"
                    except Exception as exc:
                        warnings.append(f"生成项目服务截图不可用，已回退本地文件截图：{exc}")
                if isinstance(source_info, dict):
                    source_info["ui_screenshot_render_mode"] = render_mode
                    source_info["ui_screenshot_base_url"] = render_base_url
                    source_info["ui_project_server_started"] = render_mode == "project-server"
                for index, item in enumerate(screenshots, start=1):
                    _emit(emit, 45 + min(index, 8), f"渲染界面截图 {index}/{len(screenshots)}")
                    image_path = ui_dir / f"{item.key}.png"
                    page.goto(_render_url(item, render_base_url), wait_until="networkidle")
                    page.screenshot(path=str(image_path), full_page=True)
                    item.image_path = str(image_path)
                    item.width = viewport["width"]
                    item.height = viewport["height"]
            finally:
                _stop_project_server(project_server)
            browser.close()
    except Exception as exc:
        _render_fallback_images(task, blueprint, screenshots, ui_dir)
        warnings.append(f"Playwright 截图不可用，已使用本地图像渲染生成界面截图：{exc}")
    return _to_map(screenshots), warnings, ui_blueprint


def _render_url(item: UiScreenshot, base_url: str) -> str:
    if base_url:
        return f"{base_url.rstrip('/')}/{Path(item.html_path).name}"
    return Path(item.html_path).resolve().as_uri()


def _start_project_server(source_info: dict | None) -> dict[str, Any]:
    if not isinstance(source_info, dict):
        raise RuntimeError("缺少源码项目信息")
    source_dir_raw = source_info.get("source_dir")
    project_entry = source_info.get("ui_project_entry")
    if not source_dir_raw or not isinstance(project_entry, dict):
        raise RuntimeError("缺少生成项目入口信息")
    route_mode = str(project_entry.get("route_mode") or "")
    if route_mode != "aspnet-static":
        raise RuntimeError(f"当前仅支持 C#/ASP.NET Core 生成项目服务截图，当前路由模式为 {route_mode or 'unknown'}")
    dotnet = shutil.which("dotnet")
    if not dotnet:
        raise RuntimeError("未找到 dotnet，无法启动 C# 生成项目")
    source_dir = Path(str(source_dir_raw))
    port = _select_port(_port_from_url(str(project_entry.get("entry_url") or "")) or 5000)
    base_url = f"http://127.0.0.1:{port}/ui-prototype"
    process = subprocess.Popen(
        [dotnet, "run", "--urls", f"http://127.0.0.1:{port}"],
        cwd=str(source_dir),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        _wait_for_http(f"http://127.0.0.1:{port}/health", process, timeout_seconds=75)
    except Exception:
        _stop_project_server({"process": process})
        raise
    source_info["ui_project_server_url"] = base_url
    return {"process": process, "base_url": base_url, "port": port}


def _stop_project_server(server: dict[str, Any] | None) -> None:
    if not server:
        return
    process = server.get("process")
    if not process:
        return
    try:
        process.terminate()
        process.wait(timeout=5)
    except Exception:
        try:
            process.kill()
        except Exception:
            pass


def _wait_for_http(url: str, process, timeout_seconds: int) -> None:
    deadline = time.time() + timeout_seconds
    last_error = ""
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError("生成项目服务启动后立即退出")
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if 200 <= response.status < 500:
                    return
        except Exception as exc:
            last_error = str(exc)
        time.sleep(1)
    raise RuntimeError(f"生成项目服务启动超时：{last_error}")


def _select_port(preferred: int) -> int:
    candidates = [preferred] + list(range(5100, 5200))
    for port in candidates:
        if _port_available(port):
            return port
    raise RuntimeError("未找到可用端口")


def _port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        try:
            sock.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _port_from_url(value: str) -> int | None:
    match = re.search(r":(\d+)(?:/|$)", value)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _prototype_dir(output_dir: Path, source_info: dict | None) -> Path:
    if isinstance(source_info, dict) and source_info.get("source_dir"):
        source_dir = Path(str(source_info["source_dir"]))
        source_info["ui_prototype_dir"] = str(source_dir / "ui-prototype")
        return source_dir / "ui-prototype"
    return output_dir / "generated_source" / "ui-prototype"


def _write_prototype_manifest(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    prototype_dir: Path,
    ui_blueprint: UiBlueprint,
    screenshots: list[UiScreenshot],
) -> None:
    manifest = {
        "software_name": task.software_name,
        "version": task.version,
        "product_type": task.product_type,
        "renderer": ui_blueprint.renderer,
        "source": ui_blueprint.source,
        "visual_style": ui_blueprint.visual_style,
        "entry": "index.html",
        "viewport": GAME_VIEWPORT if ui_blueprint.renderer == "game" else ADMIN_VIEWPORT,
        "modules": [{"key": module.key, "title": module.title} for module in blueprint.modules],
        "pages": [
            {
                "key": item.key,
                "title": item.title,
                "caption": item.caption,
                "file": Path(item.html_path).name,
                "html_path": item.html_path,
            }
            for item in screenshots
        ],
    }
    write_json(prototype_dir / "prototype-manifest.json", manifest)


def _write_prototype_index(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    prototype_dir: Path,
    ui_blueprint: UiBlueprint,
    screenshots: list[UiScreenshot],
) -> None:
    pages = [
        {
            "key": item.key,
            "title": item.title,
            "caption": item.caption,
            "file": Path(item.html_path).name,
        }
        for item in screenshots
    ]
    viewport = GAME_VIEWPORT if ui_blueprint.renderer == "game" else ADMIN_VIEWPORT
    first_page = pages[0]["file"] if pages else ""
    page_json = json.dumps(pages, ensure_ascii=False)
    module_titles = " / ".join(module.title for module in blueprint.modules[:5])
    index_html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escape(task.software_name)} UI Prototype</title>
  <style>
    :root {{ color: #1f2937; background: #eef2f6; font-family: "Microsoft YaHei", "PingFang SC", "Segoe UI", sans-serif; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; min-height: 100vh; }}
    .shell {{ display: grid; grid-template-columns: 288px 1fr; min-height: 100vh; }}
    aside {{ background: #172033; color: #d9e6f7; padding: 22px 18px; }}
    h1 {{ margin: 0 0 8px; font-size: 18px; line-height: 1.35; }}
    .meta {{ color: #91a5c2; font-size: 12px; line-height: 1.65; margin-bottom: 18px; }}
    nav {{ display: grid; gap: 8px; }}
    button {{ width: 100%; border: 0; border-radius: 7px; padding: 10px 11px; text-align: left; color: #d9e6f7; background: rgba(255,255,255,.07); cursor: pointer; font: inherit; }}
    button strong {{ display: block; font-size: 13px; line-height: 1.35; }}
    button span {{ display: block; margin-top: 4px; color: #9fb1cc; font-size: 11px; line-height: 1.45; }}
    button.active {{ background: #2f6fed; color: #fff; }}
    button.active span {{ color: #dbe8ff; }}
    main {{ min-width: 0; padding: 20px; }}
    .toolbar {{ min-height: 58px; display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 0 16px; background: #fff; border: 1px solid #dce5f1; border-radius: 8px; margin-bottom: 14px; }}
    .toolbar strong {{ font-size: 18px; }}
    .toolbar span {{ color: #64748b; font-size: 12px; }}
    a {{ color: #2563eb; font-weight: 700; text-decoration: none; }}
    .preview {{ height: calc(100vh - 112px); overflow: auto; display: grid; place-items: start center; padding: 18px; background: #dbe4ef; border-radius: 8px; border: 1px solid #ccd7e6; }}
    iframe {{ width: {viewport["width"]}px; height: {viewport["height"]}px; border: 0; background: #fff; box-shadow: 0 18px 46px rgba(31,41,55,.18); }}
  </style>
</head>
<body>
  <div class="shell">
    <aside>
      <h1>{escape(task.software_name)}</h1>
      <div class="meta">
        <div>{escape(task.product_type)} · {escape(task.version)} · {escape(ui_blueprint.renderer)}</div>
        <div>{escape(module_titles)}</div>
      </div>
      <nav id="pageList"></nav>
    </aside>
    <main>
      <div class="toolbar">
        <div>
          <strong id="pageTitle"></strong><br />
          <span id="pageCaption"></span>
        </div>
        <a id="openPage" href="{escape(first_page)}" target="_blank" rel="noreferrer">打开页面</a>
      </div>
      <div class="preview">
        <iframe id="previewFrame" src="{escape(first_page)}"></iframe>
      </div>
    </main>
  </div>
  <script>
    const pages = {page_json};
    const list = document.getElementById("pageList");
    const title = document.getElementById("pageTitle");
    const caption = document.getElementById("pageCaption");
    const frame = document.getElementById("previewFrame");
    const openPage = document.getElementById("openPage");
    function selectPage(index) {{
      const page = pages[index];
      if (!page) return;
      title.textContent = page.title;
      caption.textContent = page.caption || page.key;
      frame.src = page.file;
      openPage.href = page.file;
      Array.from(list.children).forEach((item, itemIndex) => item.classList.toggle("active", itemIndex === index));
    }}
    pages.forEach((page, index) => {{
      const item = document.createElement("button");
      item.type = "button";
      const pageTitle = document.createElement("strong");
      const pageKey = document.createElement("span");
      pageTitle.textContent = page.title;
      pageKey.textContent = page.key;
      item.append(pageTitle, pageKey);
      item.addEventListener("click", () => selectPage(index));
      list.appendChild(item);
    }});
    selectPage(0);
  </script>
</body>
</html>
"""
    (prototype_dir / "index.html").write_text(index_html, encoding="utf-8")


def _write_prototype_readme(
    task: GenerationTask,
    prototype_dir: Path,
    ui_blueprint: UiBlueprint,
    screenshots: list[UiScreenshot],
) -> None:
    viewport = GAME_VIEWPORT if ui_blueprint.renderer == "game" else ADMIN_VIEWPORT
    page_lines = "\n".join(f"- `{Path(item.html_path).name}`：{item.title}" for item in screenshots)
    content = f"""# {task.software_name} UI Prototype

该目录是生成源码项目的一部分，用于保存软著说明书截图所对应的可浏览页面原型。

- 入口文件：`index.html`
- 蓝图文件：`ui_blueprint.json`
- 清单文件：`prototype-manifest.json`
- 渲染器：`{ui_blueprint.renderer}`
- 截图尺寸：`{viewport["width"]}x{viewport["height"]}`

页面列表：

{page_lines}
"""
    (prototype_dir / "README.md").write_text(content, encoding="utf-8")


def _publish_project_prototype(
    task: GenerationTask,
    prototype_dir: Path,
    ui_blueprint: UiBlueprint,
    screenshots: list[UiScreenshot],
    source_info: dict | None,
) -> None:
    if not isinstance(source_info, dict) or not source_info.get("source_dir"):
        return
    source_dir = Path(str(source_info["source_dir"]))
    target = _project_prototype_target(source_dir)
    served_dir = Path(target["served_dir"])
    if served_dir.resolve() != prototype_dir.resolve():
        if served_dir.exists():
            shutil.rmtree(served_dir)
        shutil.copytree(prototype_dir, served_dir)
        _write_static_redirect(served_dir.parent)
    entry = {
        "entry_file": str(prototype_dir / "index.html"),
        "source_prototype_dir": str(prototype_dir),
        "served_dir": str(served_dir),
        "entry_url": target["entry_url"],
        "run_command": target["run_command"],
        "route_mode": target["route_mode"],
        "renderer": ui_blueprint.renderer,
        "screen_count": len(screenshots),
    }
    write_json(prototype_dir / "project-entry.json", entry)
    if served_dir.resolve() != prototype_dir.resolve():
        write_json(served_dir / "project-entry.json", entry)
    entry_doc = _write_project_entry_doc(task, source_dir, entry)
    entry["entry_doc"] = str(entry_doc)
    write_json(prototype_dir / "project-entry.json", entry)
    if served_dir.resolve() != prototype_dir.resolve():
        write_json(served_dir / "project-entry.json", entry)
    source_info["ui_project_entry"] = entry


def _project_prototype_target(source_dir: Path) -> dict[str, str]:
    if (source_dir / "pom.xml").exists():
        return {
            "served_dir": str(source_dir / "src" / "main" / "resources" / "static" / "ui-prototype"),
            "entry_url": "http://127.0.0.1:8080/ui-prototype/index.html",
            "run_command": "mvn spring-boot:run",
            "route_mode": "spring-static",
        }
    if list(source_dir.glob("*.csproj")):
        return {
            "served_dir": str(source_dir / "wwwroot" / "ui-prototype"),
            "entry_url": "http://127.0.0.1:5000/ui-prototype/index.html",
            "run_command": "dotnet run --urls http://127.0.0.1:5000",
            "route_mode": "aspnet-static",
        }
    if (source_dir / "package.json").exists():
        return {
            "served_dir": str(source_dir / "ui-prototype"),
            "entry_url": "http://127.0.0.1:8080/ui-prototype/index.html",
            "run_command": "npm install && npm start",
            "route_mode": "express-static",
        }
    if (source_dir / "app" / "main.py").exists():
        return {
            "served_dir": str(source_dir / "ui-prototype"),
            "entry_url": "http://127.0.0.1:8080/ui-prototype/index.html",
            "run_command": "uvicorn app.main:app --host 127.0.0.1 --port 8080",
            "route_mode": "fastapi-static",
        }
    return {
        "served_dir": str(source_dir / "ui-prototype"),
        "entry_url": "ui-prototype/index.html",
        "run_command": "open ui-prototype/index.html",
        "route_mode": "file",
    }


def _write_static_redirect(static_root: Path) -> None:
    static_root.mkdir(parents=True, exist_ok=True)
    (static_root / "index.html").write_text(
        """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta http-equiv="refresh" content="0; url=/ui-prototype/index.html" />
  <title>UI Prototype</title>
</head>
<body>
  <a href="/ui-prototype/index.html">打开界面原型</a>
</body>
</html>
""",
        encoding="utf-8",
    )


def _write_project_entry_doc(task: GenerationTask, source_dir: Path, entry: dict[str, str]) -> Path:
    content = f"""# UI Prototype Entry

本源码工程已包含软著说明书截图对应的可浏览前端原型。

- 软件名称：{task.software_name}
- 本地原型目录：`ui-prototype/`
- 项目服务目录：`{_relative_display(source_dir, Path(entry["served_dir"]))}`
- 项目访问地址：`{entry["entry_url"]}`
- 启动命令：`{entry["run_command"]}`
- 路由模式：`{entry["route_mode"]}`

也可以不启动项目，直接打开：

```text
ui-prototype/index.html
```
"""
    path = source_dir / "UI_PROTOTYPE_ENTRY.md"
    path.write_text(content, encoding="utf-8")
    return path


def _relative_display(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _emit(emit, progress: int, message: str, **extra) -> None:
    if emit:
        emit(progress, message, **extra)


def _build_pages(task: GenerationTask, blueprint: ProductBlueprint, ui_dir: Path, ui_blueprint: UiBlueprint) -> list[UiScreenshot]:
    if ui_blueprint.renderer == "game":
        return _build_game_pages(task, blueprint, ui_dir, ui_blueprint)

    design_brief = getattr(ui_blueprint, "design_brief", {}) or {}
    screen_by_key = {screen.key: screen for screen in ui_blueprint.screens}
    screen_by_module_key = {screen.module_key: screen for screen in ui_blueprint.screens if screen.module_key}
    login_screen = screen_by_key.get("login")
    dashboard_screen = screen_by_key.get("dashboard")
    statistics_screen = screen_by_key.get("statistics")
    pages = [
        _write_page(
            ui_dir,
            "login",
            login_screen.title if login_screen else "登录界面",
            login_screen.caption if login_screen else "用户输入账号、密码和验证码后进入系统。",
            _login_body(task, blueprint, design_brief),
            renderer="admin",
        ),
        _write_page(
            ui_dir,
            "dashboard",
            dashboard_screen.title if dashboard_screen else "系统首页",
            dashboard_screen.caption if dashboard_screen else "首页集中展示核心指标、待办事项、异常提醒和快捷入口。",
            _dashboard_body(task, blueprint, design_brief),
            renderer="admin",
        ),
    ]
    for module in blueprint.modules:
        screen = screen_by_module_key.get(module.key) or screen_by_key.get(module.key)
        pages.append(
            _write_page(
                ui_dir,
                screen.key if screen else _module_page_key(module.key),
                screen.title if screen else module.title,
                screen.caption if screen else module.description,
                _module_body(task, blueprint, module, design_brief),
                renderer="admin",
            )
        )
        for operation_index, operation in enumerate(_module_operation_items(module, design_brief)[:4], start=2):
            action = _operation_action_label(operation)
            pages.append(
                _write_page(
                    ui_dir,
                    _module_operation_page_key(module.key, action, operation_index),
                    f"{module.title}{action}界面",
                    f"{module.title}{action}窗口展示业务字段、处理状态和操作按钮。",
                    _module_operation_body(task, blueprint, module, action, design_brief),
                    renderer="admin",
                )
            )
    pages.append(
        _write_page(
            ui_dir,
            "statistics",
            statistics_screen.title if statistics_screen else "统计报表界面",
            statistics_screen.caption if statistics_screen else "系统按日期、模块、状态和角色维度生成统计结果。",
            _statistics_body(task, blueprint, design_brief),
            renderer="admin",
        )
    )
    return pages


def _module_page_key(module_key: str) -> str:
    if module_key in {"login", "dashboard", "statistics"}:
        return f"module_{module_key}"
    return module_key


def _module_operation_page_key(module_key: str, action: str, operation_index: int) -> str:
    token = re.sub(r"[^a-zA-Z0-9]+", "_", action).strip("_").lower()
    token = token or f"operation_{operation_index}"
    return f"{_module_page_key(module_key)}_{token}_{operation_index}"


def _module_operation_items(module: FeatureModule, design_brief: dict[str, Any] | None = None) -> list[str]:
    operations = [str(item).strip() for item in module.operations if str(item).strip()]
    if not operations:
        operations = [
            f"{module.title}详情",
            f"{module.title}记录",
            f"{module.title}编辑",
            f"{module.title}新增",
        ]
    secondary_mix = [str(item).strip() for item in (design_brief or {}).get("secondary_mix", []) if str(item).strip()]
    if not secondary_mix:
        return operations
    selected: list[str] = []
    used: set[int] = set()
    for preferred_action in secondary_mix:
        for index, operation in enumerate(operations):
            if index in used:
                continue
            if _operation_action_label(operation) == preferred_action or preferred_action in operation:
                selected.append(operation)
                used.add(index)
                break
    for index, operation in enumerate(operations):
        if index not in used:
            selected.append(operation)
    return selected


def _operation_action_label(operation: str) -> str:
    for suffix in [
        "详情",
        "记录",
        "编辑",
        "新增",
        "删除",
        "登记",
        "查询",
        "审核",
        "发布",
        "归档",
        "导入",
        "导出",
        "预警",
        "复核",
        "统计",
        "追踪",
        "配置",
        "定位",
        "调度",
        "训练",
        "道具",
        "结算",
        "活动",
        "确认",
        "处置",
    ]:
        if suffix in operation:
            return suffix
    return str(operation).strip() or "处理"


def _module_operation_body(task: GenerationTask, blueprint: ProductBlueprint, module: FeatureModule, action: str, design_brief: dict[str, Any] | None = None) -> str:
    profile = _profile_for_blueprint(task, blueprint, design_brief)
    fields = module.data_fields[:6] or ["业务编号", "业务名称", "业务状态", "责任角色", "更新时间", "处理备注"]
    title = f"{module.title}{action}界面"
    dialog = _operation_dialog(module, action, title, fields)
    background = _module_content(profile, blueprint, module)
    content = f"""
<div class="operation-preview">
  <div class="operation-background">{background}</div>
  <div class="modal-backdrop">
{dialog}
  </div>
</div>
"""
    return _layout(task, blueprint, title, content, module.title, design_brief)


def _operation_dialog(module: FeatureModule, action: str, title: str, fields: list[str]) -> str:
    if action == "查询":
        return _query_dialog(module, title, fields)
    if action == "导入":
        return _import_dialog(module, title)
    if action == "导出":
        return _export_dialog(module, title)
    if action == "统计":
        return _statistics_dialog(module, title)
    if action == "预警":
        return _warning_dialog(module, title, fields)
    if action in {"审核", "复核", "发布"}:
        return _review_dialog(module, action, title, fields)
    if action in {"删除", "归档"}:
        return _confirm_dialog(module, action)
    if action in {"详情", "记录", "追踪"}:
        return _detail_dialog(module, action, title, fields)
    return _form_dialog(module, action, title, fields)


def _dialog_head(title: str) -> str:
    return f'<div class="dialog-head"><strong>{escape(title)}</strong><span class="dialog-close">×</span></div>'


def _field_rows(module: FeatureModule, fields: list[str]) -> str:
    return "".join(
        f"<div class='detail-row'><span>{escape(field)}</span><strong>{escape(_operation_sample_value(module, field, index))}</strong></div>"
        for index, field in enumerate(fields)
    )


def _form_items(module: FeatureModule, fields: list[str]) -> str:
    return "".join(
        f"<div class='form-item'><span>{escape(field)}</span><div class='form-value'>{escape(_operation_sample_value(module, field, index))}</div></div>"
        for index, field in enumerate(fields)
    )


def _query_dialog(module: FeatureModule, title: str, fields: list[str]) -> str:
    query_fields = fields[:4] or ["业务编号", "业务名称", "业务状态", "责任角色"]
    filters = "".join(f"<div class='query-filter'><span>{escape(field)}</span><div>请输入{escape(field)}</div></div>" for field in query_fields)
    rows = "".join(
        "<tr>"
        f"<td>{escape(_operation_sample_value(module, query_fields[0], index))}</td>"
        f"<td>{escape(module.title)}记录{index + 1:03d}</td>"
        f"<td><span class='status {'warn' if index % 3 == 1 else ''}'>{'待复核' if index % 3 == 1 else '已处理'}</span></td>"
        f"<td>2026-06-0{index + 3}</td>"
        "</tr>"
        for index in range(4)
    )
    return f"""
    <section class="dialog query-dialog">
      {_dialog_head(title)}
      <div class="dialog-body">
        <div class="query-grid">{filters}</div>
        <div class="query-actions"><span class="button">查询</span><span class="button ghost">重置</span><span class="button ghost">高级筛选</span></div>
        <div class="result-box"><table><thead><tr><th>编号</th><th>名称</th><th>状态</th><th>更新时间</th></tr></thead><tbody>{rows}</tbody></table></div>
      </div>
      <div class="dialog-footer"><span class="muted">共 128 条记录，当前显示前 4 条</span><span class="button">打开详情</span></div>
    </section>
"""


def _import_dialog(module: FeatureModule, title: str) -> str:
    return f"""
    <section class="dialog import-dialog">
      {_dialog_head(title)}
      <div class="dialog-body">
        <div class="upload-zone">
          <strong>选择{escape(module.title)}导入文件</strong>
          <span>支持 xlsx、csv 文件，系统会先完成字段匹配和重复校验。</span>
        </div>
        <div class="file-row"><span>import_{escape(_module_page_key(module.key))}_20260608.xlsx</span><b>已选择</b></div>
        <div class="progress-line"><span style="width:72%"></span></div>
        <div class="validation-list">
          <div><b>字段匹配</b><span>已匹配 12 个字段</span></div>
          <div><b>重复校验</b><span>发现 2 条待确认记录</span></div>
          <div><b>导入方式</b><span>追加写入并保留原状态</span></div>
        </div>
      </div>
      <div class="dialog-footer"><span class="button ghost">取消</span><span class="button">开始导入</span></div>
    </section>
"""


def _export_dialog(module: FeatureModule, title: str) -> str:
    return f"""
    <section class="dialog export-dialog">
      {_dialog_head(title)}
      <div class="dialog-body">
        <div class="export-layout">
          <div>
            <div class="section-label">导出范围</div>
            <div class="option-list">
              <div><span class="check-mark">✓</span>当前查询结果</div>
              <div><span class="check-mark">✓</span>{escape(module.title)}明细字段</div>
              <div><span class="check-mark muted-check"> </span>操作日志与审批记录</div>
            </div>
          </div>
          <div>
            <div class="section-label">文件格式</div>
            <div class="format-tabs"><span class="active">Excel</span><span>PDF</span><span>CSV</span></div>
            <div class="export-preview">预计导出 128 条数据<br>文件名：{escape(_module_page_key(module.key))}_export_20260608.xlsx</div>
          </div>
        </div>
      </div>
      <div class="dialog-footer"><span class="button ghost">取消</span><span class="button">确认导出</span></div>
    </section>
"""


def _statistics_dialog(module: FeatureModule, title: str) -> str:
    bars = "".join(f"<span style='height:{54 + index * 18}px'></span>" for index in range(6))
    return f"""
    <section class="dialog statistics-dialog">
      {_dialog_head(title)}
      <div class="dialog-body">
        <div class="stat-dialog-grid">
          <div><span>本月处理量</span><strong>1,286</strong></div>
          <div><span>完成率</span><strong>86.4%</strong></div>
          <div><span>异常记录</span><strong>72</strong></div>
        </div>
        <div class="dialog-chart">{bars}</div>
        <div class="legend-row"><span>待处理</span><span>处理中</span><span>已完成</span><span>已归档</span></div>
      </div>
      <div class="dialog-footer"><span class="button ghost">导出图表</span><span class="button">查看明细</span></div>
    </section>
"""


def _warning_dialog(module: FeatureModule, title: str, fields: list[str]) -> str:
    rows = "".join(
        f"<div><span>{escape(field)}</span><strong>{80 + index * 6}%</strong></div>"
        for index, field in enumerate((fields[:4] or ["业务状态", "更新时间", "处理备注", "责任角色"]))
    )
    return f"""
    <section class="dialog warning-dialog">
      {_dialog_head(title)}
      <div class="dialog-body">
        <div class="warning-banner"><strong>{escape(module.title)}预警触发</strong><span>请确认阈值、责任人和处理时限。</span></div>
        <div class="threshold-grid">{rows}</div>
        <div class="dialog-note">系统根据阈值规则、状态变化和处理时长生成预警，确认后写入待办任务。</div>
      </div>
      <div class="dialog-footer"><span class="button ghost">暂不处理</span><span class="button">生成待办</span></div>
    </section>
"""


def _review_dialog(module: FeatureModule, action: str, title: str, fields: list[str]) -> str:
    return f"""
    <section class="dialog review-dialog">
      {_dialog_head(title)}
      <div class="dialog-body review-layout">
        <div class="detail-grid">{_field_rows(module, fields[:4])}</div>
        <div class="approval-panel">
          <div class="approval-step done"><b>提交</b><span>系统管理员 10:12</span></div>
          <div class="approval-step active"><b>{escape(action)}</b><span>等待当前用户处理</span></div>
          <div class="approval-step"><b>归档</b><span>处理完成后自动进入</span></div>
        </div>
        <div class="opinion-box">请输入{escape(action)}意见或处理说明</div>
      </div>
      <div class="dialog-footer"><span class="button ghost">退回</span><span class="button">通过{escape(action)}</span></div>
    </section>
"""


def _confirm_dialog(module: FeatureModule, action: str) -> str:
    note = f"窗口要求用户确认{action}原因，系统提交前校验权限范围并记录操作日志。"
    return f"""
    <section class="dialog confirm-dialog">
      {_dialog_head("信息")}
      <div class="confirm-body">
        <div class="confirm-icon">!</div>
        <div>
          <strong>确认{escape(action)}{escape(module.title)}记录？</strong>
          <p>{escape(note)}</p>
        </div>
      </div>
      <div class="dialog-footer"><span class="button">确定</span><span class="button ghost">取消</span></div>
    </section>
"""


def _detail_dialog(module: FeatureModule, action: str, title: str, fields: list[str]) -> str:
    note = f"窗口用于查看{module.title}的基础信息、处理轨迹、状态变化和关联记录，便于用户核对业务结果。"
    return f"""
    <section class="dialog detail-dialog">
      {_dialog_head(title)}
      <div class="dialog-body">
        <div class="detail-grid">{_field_rows(module, fields)}</div>
        <div class="track-list">
          <div><b>{escape(action)}记录</b><span>提交人：系统管理员　时间：2026-06-08 10:30</span></div>
          <div><b>状态变化</b><span>待处理 → 处理中，已写入操作日志</span></div>
          <div><b>关联说明</b><span>{escape(note)}</span></div>
        </div>
      </div>
      <div class="dialog-footer"><span class="button ghost">导出记录</span><span class="button">关闭</span></div>
    </section>
"""


def _form_dialog(module: FeatureModule, action: str, title: str, fields: list[str]) -> str:
    note = f"窗口用于填写或维护{module.title}数据，系统按必填项、状态流转和业务编码规则进行校验。"
    primary = "提交" if action in {"登记", "新增"} else "保存"
    return f"""
    <section class="dialog form-dialog">
      {_dialog_head(title)}
      <div class="dialog-body">
        <div class="form-grid">{_form_items(module, fields)}</div>
        <div class="dialog-note">{escape(note)}</div>
      </div>
      <div class="dialog-footer"><span class="button ghost">取消</span><span class="button">{escape(primary)}</span></div>
    </section>
"""


def _operation_sample_value(module: FeatureModule, field: str, index: int) -> str:
    values = [
        f"{_module_page_key(module.key).upper()}-{index + 1001}",
        f"{module.title}记录{index + 1:03d}",
        "待处理",
        "系统管理员",
        "2026-06-08 10:30",
        "业务数据已完成初步校验",
    ]
    if "状态" in field:
        return "待处理"
    if "时间" in field:
        return "2026-06-08 10:30"
    if "角色" in field or "责任" in field:
        return "系统管理员"
    if "编号" in field or "编码" in field:
        return values[0]
    if "名称" in field:
        return values[1]
    return values[index % len(values)]


def _build_game_pages(task: GenerationTask, blueprint: ProductBlueprint, ui_dir: Path, ui_blueprint: UiBlueprint) -> list[UiScreenshot]:
    module_by_key = {module.key: module for module in blueprint.modules}
    pages: list[UiScreenshot] = []
    for screen in ui_blueprint.screens:
        module = module_by_key.get(screen.module_key or screen.key)
        body = _game_body_from_screen(task, blueprint, screen, module)
        pages.append(_write_page(ui_dir, screen.key, screen.title, screen.caption, body, renderer="game"))
    return pages


def _write_page(ui_dir: Path, key: str, title: str, caption: str, body: str, renderer: str = "admin") -> UiScreenshot:
    html_path = ui_dir / f"{key}.html"
    html_path.write_text(_page_shell(title, body, renderer), encoding="utf-8")
    return UiScreenshot(key=key, title=title, caption=caption, html_path=str(html_path))


def _page_shell(title: str, body: str, renderer: str = "admin") -> str:
    body_class = "game" if renderer == "game" else "admin"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escape(title)}</title>
  <style>
    :root {{ font-family: "Microsoft YaHei", "PingFang SC", "Segoe UI", sans-serif; color: #1f2937; background: #eef2f6; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; min-height: 100vh; background: #edf2f7; }}
    .app {{ min-height: 100vh; display: grid; grid-template-columns: 220px 1fr; }}
    .sidebar {{ background: var(--sidebar, #1f314f); color: #dce7f7; padding: 24px 18px; }}
    .brand {{ font-size: 18px; font-weight: 800; line-height: 1.35; margin-bottom: 22px; }}
    .sidebar-subtitle {{ margin: -12px 0 18px; color: rgba(220,231,247,.76); font-size: 12px; line-height: 1.45; }}
    .nav {{ display: grid; gap: 8px; }}
    .nav span {{ display: block; padding: 10px 12px; border-radius: 6px; background: rgba(255,255,255,.06); font-size: 13px; }}
    .nav span.active {{ background: var(--accent, #2f6fed); color: white; }}
    .topbar {{ min-height: 76px; display: grid; grid-template-columns: 250px 1fr auto; align-items: center; gap: 18px; padding: 12px 24px; background: var(--sidebar, #1f314f); color: #dce7f7; }}
    .topbar .brand {{ margin: 0 0 4px; color: #ffffff; }}
    .topbar .nav {{ display: flex; gap: 8px; overflow: hidden; }}
    .topbar .nav span {{ white-space: nowrap; }}
    .app.nav-top_tabs {{ grid-template-columns: 1fr; grid-template-rows: auto 1fr; }}
    .app.nav-top_tabs .main {{ padding: 20px 24px; }}
    .app.nav-rail {{ grid-template-columns: 92px 1fr; }}
    .app.nav-rail .sidebar {{ padding: 18px 12px; }}
    .app.nav-rail .brand {{ font-size: 13px; writing-mode: vertical-rl; min-height: 120px; margin: 0 auto 16px; }}
    .app.nav-rail .sidebar-subtitle {{ display: none; }}
    .app.nav-rail .nav span {{ min-height: 48px; display: grid; place-items: center; padding: 6px; font-size: 12px; text-align: center; }}
    .main {{ padding: 24px; }}
    .top {{ height: 58px; display: flex; align-items: center; justify-content: space-between; padding: 0 18px; background: white; border: 1px solid #dde5ef; border-radius: 8px; margin-bottom: 18px; }}
    .title {{ font-size: 22px; font-weight: 800; }}
    .muted {{ color: #64748b; font-size: 13px; }}
    .grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin-bottom: 16px; }}
    .card {{ background: white; border: 1px solid #dde5ef; border-radius: 8px; padding: 16px; }}
    .metric strong {{ display: block; margin-top: 8px; font-size: 26px; color: var(--accent, #1f2937); }}
    .panel {{ background: white; border: 1px solid #dde5ef; border-radius: 8px; padding: 16px; margin-bottom: 16px; }}
    .panel h2 {{ margin: 0 0 12px; font-size: 17px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ padding: 11px 10px; border-bottom: 1px solid #edf1f6; text-align: left; }}
    th {{ color: #52637a; background: #f8fafc; }}
    .toolbar {{ display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 12px; }}
    .input {{ height: 36px; min-width: 180px; border: 1px solid #cfd8e5; border-radius: 6px; padding: 0 10px; color: #64748b; display: inline-flex; align-items: center; background: #fbfdff; }}
    .button {{ height: 36px; padding: 0 14px; border-radius: 6px; background: var(--accent, #2f6fed); color: white; display: inline-flex; align-items: center; font-weight: 700; }}
    .status {{ padding: 4px 8px; border-radius: 999px; background: #e8f6ef; color: #157347; font-weight: 700; font-size: 12px; }}
    .warn {{ background: #fff3cd; color: #8a5a00; }}
    .operation-preview {{ position: relative; min-height: 620px; }}
    .operation-background {{ filter: saturate(.82); pointer-events: none; }}
    .modal-backdrop {{ position: fixed; inset: 0; display: grid; place-items: center; padding: 38px; background: rgba(0,0,0,.38); }}
    .dialog {{ width: min(620px, calc(100vw - 96px)); max-height: calc(100vh - 76px); overflow: hidden; border-radius: 4px; background: #ffffff; border: 1px solid #b8c2d0; box-shadow: 0 18px 52px rgba(0,0,0,.24); }}
    .detail-dialog {{ width: min(690px, calc(100vw - 96px)); }}
    .confirm-dialog {{ width: 360px; }}
    .form-dialog {{ width: 450px; }}
    .query-dialog {{ width: min(780px, calc(100vw - 96px)); }}
    .import-dialog {{ width: 500px; }}
    .export-dialog {{ width: 560px; }}
    .statistics-dialog {{ width: 620px; }}
    .warning-dialog {{ width: 520px; }}
    .review-dialog {{ width: min(720px, calc(100vw - 96px)); }}
    .dialog-head {{ height: 48px; padding: 0 16px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #e5e7eb; background: #f8fafc; }}
    .dialog-head strong {{ font-size: 18px; color: #1f2937; }}
    .dialog-close {{ width: 22px; height: 22px; display: grid; place-items: center; color: #64748b; font-size: 20px; line-height: 1; }}
    .dialog-body {{ padding: 16px; display: grid; gap: 14px; }}
    .form-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px 14px; }}
    .form-item {{ display: grid; gap: 7px; }}
    .form-item span {{ font-size: 12px; color: #52637a; font-weight: 700; }}
    .form-value {{ min-height: 38px; display: flex; align-items: center; padding: 0 10px; border: 1px solid #ccd6e3; border-radius: 6px; background: #fbfdff; color: #1f2937; font-size: 13px; }}
    .dialog-note {{ min-height: 64px; padding: 10px; border: 1px solid #ccd6e3; border-radius: 6px; background: #fbfdff; color: #52637a; line-height: 1.6; font-size: 13px; }}
    .detail-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); border: 1px solid #d7dee8; border-bottom: 0; border-right: 0; }}
    .detail-row {{ min-height: 38px; display: grid; grid-template-columns: 104px 1fr; border-right: 1px solid #d7dee8; border-bottom: 1px solid #d7dee8; }}
    .detail-row span {{ padding: 9px 10px; background: #f7f9fc; color: #52637a; font-size: 12px; }}
    .detail-row strong {{ padding: 9px 10px; color: #1f2937; font-size: 13px; font-weight: 600; }}
    .track-list {{ display: grid; gap: 8px; }}
    .track-list div {{ min-height: 42px; padding: 9px 10px; border: 1px solid #e1e7ef; border-radius: 4px; background: #fbfdff; }}
    .track-list b {{ display: block; margin-bottom: 4px; color: #1f2937; font-size: 13px; }}
    .track-list span {{ color: #64748b; font-size: 12px; line-height: 1.45; }}
    .confirm-body {{ min-height: 112px; display: grid; grid-template-columns: 38px 1fr; gap: 14px; align-items: start; padding: 22px 18px 12px; }}
    .confirm-body strong {{ display: block; margin-bottom: 10px; color: #1f2937; font-size: 16px; }}
    .confirm-body p {{ margin: 0; color: #64748b; line-height: 1.55; font-size: 13px; }}
    .confirm-icon {{ width: 32px; height: 32px; border-radius: 50%; display: grid; place-items: center; background: #eaf4ff; color: #1d8cff; font-weight: 900; font-size: 20px; }}
    .dialog-footer {{ height: 54px; padding: 0 16px; display: flex; align-items: center; justify-content: flex-end; gap: 10px; border-top: 1px solid #e5e7eb; background: #ffffff; }}
    .ghost {{ background: #eef2f7; color: #334155; }}
    .query-grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }}
    .query-filter {{ min-height: 58px; display: grid; gap: 6px; }}
    .query-filter span, .section-label {{ color: #52637a; font-size: 12px; font-weight: 800; }}
    .query-filter div {{ height: 32px; display: flex; align-items: center; padding: 0 9px; border: 1px solid #ccd6e3; border-radius: 4px; color: #94a3b8; background: #fbfdff; font-size: 12px; }}
    .query-actions {{ display: flex; gap: 8px; justify-content: flex-end; }}
    .result-box {{ max-height: 210px; overflow: hidden; border: 1px solid #e1e7ef; border-radius: 4px; }}
    .upload-zone {{ min-height: 116px; display: grid; place-items: center; gap: 8px; text-align: center; border: 1px dashed #8ab4f8; background: #f4f8ff; color: #365375; }}
    .upload-zone strong {{ font-size: 16px; color: #1f2937; }}
    .upload-zone span, .file-row span {{ color: #64748b; font-size: 13px; }}
    .file-row {{ height: 42px; display: flex; align-items: center; justify-content: space-between; padding: 0 12px; border: 1px solid #e1e7ef; border-radius: 4px; background: #ffffff; }}
    .file-row b {{ color: #157347; font-size: 13px; }}
    .progress-line {{ height: 8px; overflow: hidden; border-radius: 999px; background: #e5edf6; }}
    .progress-line span {{ display: block; height: 100%; border-radius: 999px; background: var(--accent, #2f6fed); }}
    .validation-list {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }}
    .validation-list div {{ min-height: 70px; padding: 10px; border: 1px solid #e1e7ef; border-radius: 4px; background: #fbfdff; }}
    .validation-list b, .approval-step b {{ display: block; margin-bottom: 5px; color: #1f2937; font-size: 13px; }}
    .validation-list span, .approval-step span {{ color: #64748b; font-size: 12px; line-height: 1.45; }}
    .export-layout {{ display: grid; grid-template-columns: 1fr 1fr; gap: 18px; align-items: start; }}
    .option-list {{ display: grid; gap: 10px; margin-top: 10px; }}
    .option-list div {{ min-height: 36px; display: flex; gap: 9px; align-items: center; padding: 0 10px; border: 1px solid #e1e7ef; border-radius: 4px; background: #fbfdff; color: #334155; font-size: 13px; }}
    .check-mark {{ width: 18px; height: 18px; display: grid; place-items: center; border-radius: 3px; background: var(--accent, #2f6fed); color: white; font-size: 12px; }}
    .muted-check {{ background: #eef2f7; color: #eef2f7; }}
    .format-tabs {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; margin: 10px 0 12px; }}
    .format-tabs span {{ height: 34px; display: grid; place-items: center; border: 1px solid #ccd6e3; border-radius: 4px; color: #52637a; font-weight: 700; font-size: 12px; }}
    .format-tabs .active {{ background: var(--accent, #2f6fed); border-color: var(--accent, #2f6fed); color: #ffffff; }}
    .export-preview {{ min-height: 86px; padding: 12px; border: 1px solid #e1e7ef; border-radius: 4px; background: #fbfdff; color: #52637a; line-height: 1.7; font-size: 13px; }}
    .stat-dialog-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }}
    .stat-dialog-grid div {{ min-height: 82px; padding: 12px; border-radius: 4px; background: #f8fafc; border: 1px solid #e1e7ef; }}
    .stat-dialog-grid span {{ display: block; color: #52637a; font-size: 12px; margin-bottom: 8px; }}
    .stat-dialog-grid strong {{ color: var(--accent, #2f6fed); font-size: 24px; }}
    .dialog-chart {{ height: 180px; display: flex; align-items: end; gap: 14px; padding: 16px; border-radius: 4px; background: linear-gradient(180deg, #fbfdff, #f1f5f9); border: 1px solid #e1e7ef; }}
    .dialog-chart span {{ flex: 1; border-radius: 5px 5px 0 0; background: linear-gradient(180deg, var(--accent, #2f6fed), rgba(47,111,237,.32)); }}
    .legend-row {{ display: flex; gap: 14px; color: #64748b; font-size: 12px; }}
    .warning-banner {{ min-height: 74px; padding: 14px; border-left: 5px solid #f59e0b; background: #fff7ed; }}
    .warning-banner strong {{ display: block; margin-bottom: 7px; color: #92400e; font-size: 15px; }}
    .warning-banner span {{ color: #8a5a00; font-size: 13px; }}
    .threshold-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }}
    .threshold-grid div {{ min-height: 62px; display: flex; align-items: center; justify-content: space-between; padding: 0 12px; border: 1px solid #e1e7ef; border-radius: 4px; background: #fbfdff; }}
    .threshold-grid span {{ color: #52637a; font-size: 12px; }}
    .threshold-grid strong {{ color: #dc2626; font-size: 18px; }}
    .review-layout {{ grid-template-columns: 1.2fr .8fr; }}
    .review-layout .detail-grid {{ grid-column: 1; }}
    .approval-panel {{ grid-column: 2; display: grid; gap: 10px; }}
    .approval-step {{ min-height: 58px; padding: 10px 12px; border-left: 4px solid #cbd5e1; background: #fbfdff; border-radius: 4px; }}
    .approval-step.done {{ border-left-color: #16a34a; }}
    .approval-step.active {{ border-left-color: var(--accent, #2f6fed); background: var(--accent-soft, #eef6ff); }}
    .opinion-box {{ grid-column: 1 / -1; min-height: 70px; padding: 12px; border: 1px solid #ccd6e3; border-radius: 4px; background: #fbfdff; color: #94a3b8; font-size: 13px; }}
    .two-col {{ display: grid; grid-template-columns: 1.4fr .9fr; gap: 16px; align-items: start; }}
    .focus-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }}
    .focus-card {{ min-height: 88px; border: 1px solid #e3ebf5; border-radius: 8px; padding: 12px; background: linear-gradient(180deg, #ffffff, var(--accent-soft, #f7fbff)); }}
    .focus-card span {{ display: block; color: #52637a; font-size: 12px; margin-bottom: 8px; }}
    .focus-card strong {{ display: block; color: var(--accent, #2f6fed); font-size: 22px; }}
    .focus-card small {{ display: block; margin-top: 6px; color: #64748b; line-height: 1.45; }}
    .process {{ display: flex; gap: 10px; flex-wrap: wrap; }}
    .process span {{ display: inline-flex; height: 32px; align-items: center; padding: 0 10px; border-radius: 999px; background: var(--accent-soft, #eef6ff); color: #365375; font-weight: 700; font-size: 12px; }}
    .mini-chart {{ height: 154px; display: flex; align-items: end; gap: 12px; padding: 12px; border-radius: 8px; background: #f8fafc; }}
    .bar {{ flex: 1; min-width: 24px; border-radius: 8px 8px 2px 2px; background: linear-gradient(180deg, var(--accent, #2f6fed), rgba(47,111,237,.35)); }}
    .app.workflow {{ grid-template-columns: 1fr; grid-template-rows: 86px 1fr; }}
    .app.workflow .sidebar {{ display: flex; align-items: center; gap: 20px; padding: 16px 24px; }}
    .app.workflow .brand {{ width: 250px; margin: 0; }}
    .app.workflow .nav {{ display: flex; gap: 8px; overflow: hidden; }}
    .app.workflow .nav span {{ white-space: nowrap; }}
    .app.workflow .main {{ padding: 20px 26px; }}
    .app.risk {{ background: #f8fafc; grid-template-columns: 246px 1fr; }}
    .app.risk .sidebar {{ background: #17212f; }}
    .app.risk .top {{ border-left: 5px solid var(--accent, #0f766e); }}
    .app.map {{ background: #edf7f1; grid-template-columns: 248px 1fr; }}
    .app.map .sidebar {{ background: #14352b; }}
    .app.pipeline {{ background: #f6f7fb; grid-template-columns: 205px 1fr; }}
    .app.pipeline .sidebar {{ background: #251b4d; }}
    .app.nav-top_tabs {{ grid-template-columns: 1fr; grid-template-rows: auto 1fr; }}
    .app.nav-top_tabs .main {{ padding: 20px 24px; }}
    .app.nav-rail {{ grid-template-columns: 92px 1fr; }}
    .app.nav-rail .sidebar {{ padding: 18px 12px; }}
    .dashboard-split {{ display: grid; grid-template-columns: 1.15fr .85fr; gap: 16px; align-items: stretch; margin-bottom: 16px; }}
    .queue-list {{ display: grid; gap: 10px; }}
    .queue-item {{ min-height: 56px; display: grid; grid-template-columns: 1fr auto; gap: 10px; align-items: center; padding: 11px 12px; border: 1px solid #e3ebf5; border-radius: 8px; background: #fbfdff; }}
    .queue-item strong {{ display: block; font-size: 14px; color: #1f2937; }}
    .queue-item small {{ color: #64748b; line-height: 1.45; }}
    .risk-strip {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 16px; }}
    .risk-tile {{ min-height: 92px; padding: 14px; border-radius: 8px; background: #17212f; color: #d8e5f6; border: 1px solid rgba(255,255,255,.08); }}
    .risk-tile span {{ display: block; font-size: 12px; color: #9fb3ca; margin-bottom: 9px; }}
    .risk-tile strong {{ display: block; font-size: 25px; color: #ffffff; }}
    .risk-tile small {{ display: block; margin-top: 6px; color: #8de0d3; }}
    .map-board {{ position: relative; min-height: 378px; overflow: hidden; border-radius: 8px; background:
      linear-gradient(90deg, rgba(255,255,255,.54) 1px, transparent 1px) 0 0 / 48px 48px,
      linear-gradient(0deg, rgba(255,255,255,.46) 1px, transparent 1px) 0 0 / 48px 48px,
      linear-gradient(135deg, #c8f0d1, #d8ecff 58%, #fff7c8); border: 1px solid #d6e4d8; }}
    .map-board::after {{ content: ""; position: absolute; left: 8%; right: 8%; top: 47%; height: 34px; border-radius: 999px; background: rgba(22,101,52,.16); transform: rotate(-8deg); }}
    .map-pin {{ position: absolute; min-width: 86px; padding: 8px 10px; border-radius: 8px; background: white; color: #1f2937; font-size: 12px; font-weight: 800; box-shadow: 0 10px 24px rgba(31,41,55,.16); border-left: 4px solid var(--accent, #16a34a); }}
    .map-pin small {{ display: block; margin-top: 4px; color: #64748b; font-weight: 600; }}
    .pipeline-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 16px; }}
    .pipeline-card {{ min-height: 118px; display: grid; align-content: space-between; padding: 14px; border-radius: 8px; background: white; border: 1px solid #dde5ef; box-shadow: inset 0 4px 0 var(--accent-soft, #eef6ff); }}
    .pipeline-card span {{ color: #52637a; font-size: 12px; }}
    .pipeline-card strong {{ color: var(--accent, #4f46e5); font-size: 22px; }}
    .command-strip {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 16px; }}
    .command-strip .card {{ background: #111827; color: #dbeafe; border-color: rgba(255,255,255,.08); }}
    .command-strip .metric strong {{ color: #ffffff; }}
    .command-grid {{ display: grid; grid-template-columns: 1.4fr .8fr; gap: 16px; align-items: start; }}
    .command-main {{ grid-row: span 2; min-height: 420px; }}
    .app.command .top {{ border-left: 5px solid var(--accent, #334155); }}
    .kanban-board {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }}
    .kanban-col {{ min-height: 318px; padding: 12px; border: 1px solid #e1e7ef; border-radius: 8px; background: #f8fafc; }}
    .kanban-col h3 {{ margin: 0 0 10px; color: #334155; font-size: 14px; }}
    .kanban-card {{ min-height: 86px; display: grid; gap: 6px; padding: 10px; margin-bottom: 10px; border-radius: 6px; background: #ffffff; border-left: 4px solid var(--accent, #ca8a04); box-shadow: 0 6px 14px rgba(15,23,42,.06); }}
    .kanban-card strong {{ color: #1f2937; font-size: 13px; }}
    .kanban-card span, .kanban-card small {{ color: #64748b; font-size: 12px; line-height: 1.45; }}
    .matrix-layout {{ display: grid; grid-template-columns: 1.35fr .9fr; gap: 16px; align-items: start; }}
    .matrix-main {{ grid-row: span 2; }}
    .matrix-board {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }}
    .matrix-cell {{ min-height: 118px; display: grid; align-content: space-between; padding: 12px; border-radius: 8px; background: linear-gradient(180deg, #ffffff, var(--accent-soft, #faf5ff)); border: 1px solid #e1e7ef; }}
    .matrix-cell span {{ color: #52637a; font-size: 12px; }}
    .matrix-cell strong {{ color: var(--accent, #9333ea); font-size: 24px; }}
    .matrix-cell small {{ color: #64748b; line-height: 1.45; }}
    .shape-triage {{ display: grid; grid-template-columns: 280px 1fr 300px; gap: 14px; align-items: stretch; }}
    .shape-triage .panel {{ margin: 0; }}
    .triage-stack {{ display: grid; gap: 10px; }}
    .triage-item {{ min-height: 68px; padding: 12px; border-left: 5px solid var(--accent, #2f6fed); background: #ffffff; box-shadow: 0 6px 16px rgba(15,23,42,.06); }}
    .triage-item strong {{ display: block; color: #172033; font-size: 13px; }}
    .triage-item span {{ display: block; margin-top: 6px; color: #64748b; font-size: 12px; }}
    .shape-ledger {{ display: grid; grid-template-columns: 1.2fr .8fr; grid-template-rows: auto 1fr; gap: 14px; }}
    .shape-ledger .ledger-toolbar {{ grid-column: 1 / -1; display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; }}
    .ledger-box {{ min-height: 54px; display: grid; align-content: center; padding: 8px 12px; border: 1px solid #dbe3ef; background: #fff; color: #52637a; font-size: 12px; }}
    .shape-wall {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; padding: 14px; background: #111827; color: #dbeafe; }}
    .shape-wall .panel {{ margin: 0; background: #172033; border-color: rgba(255,255,255,.10); color: #dbeafe; }}
    .shape-wall .panel h2, .shape-wall strong {{ color: #ffffff; }}
    .shape-wall .wall-wide {{ grid-column: span 2; min-height: 300px; }}
    .shape-wall .wall-full {{ grid-column: 1 / -1; }}
    .shape-lane {{ display: grid; gap: 14px; }}
    .lane-strip {{ display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 10px; }}
    .lane-step {{ min-height: 118px; padding: 12px; background: linear-gradient(180deg, #ffffff, var(--accent-soft, #eef6ff)); border-top: 5px solid var(--accent, #2f6fed); }}
    .lane-step b {{ display: block; color: var(--accent, #2f6fed); font-size: 22px; margin-bottom: 8px; }}
    .lane-step span {{ color: #52637a; font-size: 12px; line-height: 1.5; }}
    .shape-case {{ display: grid; grid-template-columns: 330px 1fr 310px; gap: 14px; align-items: start; }}
    .case-card {{ min-height: 96px; padding: 14px; background: #ffffff; border: 1px solid #e1e7ef; border-radius: 4px; }}
    .case-card span {{ color: #52637a; font-size: 12px; }}
    .case-card strong {{ display: block; margin-top: 8px; color: #172033; font-size: 18px; }}
    .shape-board {{ display: grid; grid-template-columns: 1fr 340px; gap: 14px; align-items: start; }}
    .shape-board .board-side {{ display: grid; gap: 14px; }}
    .freeform-grid {{ display: grid; grid-template-columns: repeat(12, minmax(0, 1fr)); gap: 14px; align-items: start; }}
    .app.shape-freeform_grid {{ height: 100vh; overflow: hidden; }}
    .app.shape-freeform_grid .main {{ min-height: 0; overflow: hidden; }}
    .app.shape-freeform_grid .top {{ height: 52px; margin-bottom: 12px; }}
    .freeform-slot {{ min-height: 128px; max-height: 300px; margin: 0; overflow: hidden; padding: 12px; }}
    .freeform-slot h2 {{ margin-bottom: 8px; font-size: 15px; }}
    .freeform-slot .grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin-bottom: 0; }}
    .freeform-slot .card {{ padding: 10px; }}
    .freeform-slot .metric strong {{ font-size: 20px; }}
    .freeform-slot .mini-chart {{ height: 112px; padding: 8px; }}
    .freeform-slot .queue-list {{ max-height: 230px; overflow: hidden; }}
    .freeform-slot .queue-item {{ min-height: 48px; padding: 8px 10px; }}
    .freeform-slot .map-board {{ min-height: 210px; }}
    .freeform-slot .kanban-col {{ min-height: 210px; }}
    .freeform-slot .timeline-step {{ min-height: 50px; padding-top: 8px; padding-bottom: 8px; }}
    .freeform-slot th, .freeform-slot td {{ padding: 7px 8px; font-size: 12px; }}
    .freeform-slot .ledger-toolbar {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    .freeform-dense_console {{ padding: 14px; background: #111827; }}
    .freeform-dense_console .freeform-slot {{ background: #172033; border-color: rgba(255,255,255,.10); color: #dbeafe; }}
    .freeform-dense_console .freeform-slot h2, .freeform-dense_console .freeform-slot strong {{ color: #ffffff; }}
    .freeform-document_desk .freeform-slot {{ border-radius: 2px; box-shadow: none; border-left: 5px solid var(--accent, #2f6fed); }}
    .freeform-wide_board .freeform-slot:first-child {{ min-height: 360px; }}
    .timeline {{ display: grid; gap: 11px; }}
    .timeline-step {{ position: relative; min-height: 62px; padding: 11px 12px 11px 42px; border: 1px solid #e3ebf5; border-radius: 8px; background: #ffffff; }}
    .timeline-step::before {{ content: attr(data-step); position: absolute; left: 12px; top: 13px; width: 22px; height: 22px; border-radius: 50%; background: var(--accent, #2f6fed); color: white; display: grid; place-items: center; font-size: 12px; font-weight: 800; }}
    .timeline-step strong {{ display: block; margin-bottom: 4px; }}
    .timeline-step small {{ color: #64748b; }}
    .login-wrap {{ min-height: 100vh; color: #172033; background: var(--login-bg, linear-gradient(135deg, #1f314f, #2f6fed)); }}
    .login-wrap .button {{ height: 42px; display: grid; place-items: center; border-radius: 6px; background: var(--accent, #2f6fed); color: white; font-weight: 800; }}
    .login-brand h1, .login-hero h1 {{ font-size: 34px; line-height: 1.18; margin: 0 0 14px; color: inherit; }}
    .login-brand p, .login-hero p {{ margin: 0; line-height: 1.7; color: inherit; opacity: .82; }}
    .login-box {{ background: white; padding: 42px; display: flex; flex-direction: column; justify-content: center; box-shadow: 0 18px 48px rgba(15,23,42,.14); }}
    .login-box h2 {{ margin: 0 0 24px; font-size: 24px; color: #172033; }}
    .login-split_brand {{ display: grid; grid-template-columns: 1fr 430px; --login-bg: linear-gradient(135deg, var(--sidebar, #1f314f), var(--accent, #2f6fed)); }}
    .login-split_brand .login-hero {{ color: white; padding: 80px 70px; display: flex; flex-direction: column; justify-content: center; }}
    .login-center_card {{ display: grid; place-items: center; padding: 64px; --login-bg: linear-gradient(180deg, #f8fafc, var(--accent-soft, #eef6ff)); }}
    .login-center_card .login-box {{ width: 460px; min-height: 490px; border-radius: 8px; }}
    .login-center_card .login-brand {{ width: 720px; max-width: calc(100vw - 620px); position: absolute; left: 70px; top: 86px; color: var(--sidebar, #1f314f); }}
    .login-console_gate {{ display: grid; grid-template-columns: 1.15fr .85fr; padding: 54px; gap: 30px; --login-bg: #0f172a; color: #dbeafe; }}
    .login-console_gate .login-box {{ background: #111827; border: 1px solid rgba(255,255,255,.12); box-shadow: none; color: #e5eefc; }}
    .login-console_gate .login-box h2 {{ color: #ffffff; }}
    .login-console_gate .field label {{ color: #9fb3ca; }}
    .login-console_gate .field div {{ background: #0b1220; border-color: #334155; color: #94a3b8; }}
    .login-console {{ border: 1px solid rgba(255,255,255,.12); background: #111827; padding: 24px; display: grid; align-content: start; gap: 14px; }}
    .login-console div {{ min-height: 44px; padding: 12px; background: #0b1220; color: #9fb3ca; border-left: 4px solid var(--accent, #2f6fed); font-size: 13px; }}
    .login-portal_grid {{ display: grid; grid-template-columns: .9fr 1.1fr; gap: 28px; padding: 56px; --login-bg: #eef2f7; }}
    .login-portal_grid .login-box {{ border-radius: 0; min-height: 520px; }}
    .login-portal {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; align-content: center; }}
    .login-portal div {{ min-height: 132px; padding: 18px; display: grid; align-content: space-between; background: white; border-left: 5px solid var(--accent, #2f6fed); box-shadow: 0 10px 24px rgba(15,23,42,.08); }}
    .login-portal span {{ color: #64748b; font-size: 12px; }}
    .login-portal strong {{ color: #172033; font-size: 20px; }}
    .login-side_preview {{ display: grid; grid-template-columns: 520px 1fr; min-height: 100vh; --login-bg: #f8fafc; }}
    .login-side_preview .login-box {{ box-shadow: none; border-right: 1px solid #d9e2ef; }}
    .login-preview {{ padding: 56px; display: grid; gap: 16px; align-content: center; }}
    .login-preview .panel {{ margin: 0; }}
    .field {{ display: grid; gap: 8px; margin-bottom: 16px; }}
    .field label {{ color: #52637a; font-size: 13px; font-weight: 700; }}
    .field div {{ height: 42px; border: 1px solid #ccd6e3; border-radius: 7px; padding: 0 12px; display: flex; align-items: center; color: #64748b; }}
    .game-screen {{ min-height: 100vh; padding: 28px; background: linear-gradient(160deg, #7dd3fc 0%, #fef3c7 45%, #f9a8d4 100%); color: #243044; }}
    .game-frame {{ width: 1180px; min-height: 744px; margin: 0 auto; border-radius: 24px; background: rgba(255,255,255,.78); box-shadow: 0 24px 70px rgba(43,55,90,.22); overflow: hidden; border: 6px solid rgba(255,255,255,.65); }}
    .game-top {{ height: 86px; display: flex; align-items: center; justify-content: space-between; padding: 0 30px; background: rgba(255,255,255,.82); }}
    .game-title {{ font-size: 28px; font-weight: 900; color: #30436b; }}
    .game-pill {{ display: inline-flex; align-items: center; height: 38px; padding: 0 16px; border-radius: 999px; background: #ffffff; color: #4b5f85; font-weight: 800; margin-left: 8px; box-shadow: inset 0 -2px 0 rgba(0,0,0,.05); }}
    .game-content {{ display: grid; grid-template-columns: 1fr 360px; gap: 22px; padding: 24px 30px 30px; }}
    .game-panel {{ background: rgba(255,255,255,.88); border-radius: 18px; padding: 20px; border: 2px solid rgba(255,255,255,.75); }}
    .game-board {{ display: grid; grid-template-columns: repeat(8, 54px); grid-auto-rows: 54px; gap: 8px; justify-content: center; padding: 18px; border-radius: 20px; background: #4f46e5; box-shadow: inset 0 0 0 6px rgba(255,255,255,.18); }}
    .gem {{ width: 54px; height: 54px; border-radius: 15px; box-shadow: inset 0 -8px 0 rgba(0,0,0,.12), 0 5px 12px rgba(31,41,55,.18); }}
    .gem.a {{ background: #fb7185; }} .gem.b {{ background: #fbbf24; }} .gem.c {{ background: #34d399; }} .gem.d {{ background: #60a5fa; }} .gem.e {{ background: #a78bfa; }} .gem.f {{ background: #f472b6; }}
    .target-row {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-top: 12px; }}
    .target {{ border-radius: 14px; background: #f8fafc; padding: 12px; text-align: center; font-weight: 800; color: #334155; }}
    .target b {{ display: block; font-size: 24px; color: #2563eb; margin-top: 4px; }}
    .level-map {{ position: relative; height: 470px; border-radius: 22px; background: linear-gradient(180deg, #bbf7d0, #bfdbfe); overflow: hidden; }}
    .level-node {{ position: absolute; width: 62px; height: 62px; border-radius: 50%; background: #fff; display: grid; place-items: center; font-weight: 900; color: #2563eb; box-shadow: 0 8px 18px rgba(30,64,175,.18); border: 5px solid #facc15; }}
    .game-list {{ display: grid; gap: 12px; }}
    .game-list div {{ border-radius: 14px; background: #ffffff; padding: 13px 15px; display: flex; align-items: center; justify-content: space-between; font-weight: 800; color: #41516f; }}
    .big-action {{ height: 58px; border-radius: 18px; background: linear-gradient(180deg, #f97316, #ea580c); color: white; display: grid; place-items: center; font-size: 22px; font-weight: 900; margin-top: 16px; box-shadow: inset 0 -5px 0 rgba(0,0,0,.14); }}
    .game-card-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }}
    .game-card {{ min-height: 132px; border-radius: 18px; background: #fff; padding: 18px; display: grid; align-content: space-between; box-shadow: 0 12px 24px rgba(30,41,59,.12); }}
    .game-card strong {{ font-size: 28px; color: #2563eb; }}
    body.game {{ width: 720px; min-height: 1280px; overflow: hidden; background: #67d8ff; }}
    body.game .game-screen {{ width: 720px; height: 1280px; min-height: 1280px; padding: 0; overflow: hidden; position: relative; background:
      radial-gradient(circle at 14% 10%, rgba(255,255,255,.9) 0 42px, transparent 44px),
      radial-gradient(circle at 86% 12%, rgba(255,246,174,.9) 0 58px, transparent 60px),
      radial-gradient(circle at 82% 82%, rgba(255,142,200,.85) 0 92px, transparent 94px),
      linear-gradient(180deg, #60d7ff 0%, #9cf3bd 42%, #ffd66d 72%, #ff91c8 100%); color: #27324f; }}
    body.game .game-screen::before {{ content: ""; position: absolute; inset: 0; background:
      linear-gradient(135deg, rgba(255,255,255,.22) 25%, transparent 25%) 0 0 / 42px 42px,
      linear-gradient(315deg, rgba(255,255,255,.12) 25%, transparent 25%) 0 0 / 42px 42px; pointer-events: none; }}
    body.game .game-frame {{ width: 720px; height: 1280px; min-height: 1280px; margin: 0; border: 0; border-radius: 0; background: transparent; box-shadow: none; position: relative; overflow: hidden; padding: 28px 28px 34px; }}
    body.game .game-frame::before {{ content: ""; position: absolute; left: 230px; top: 12px; width: 260px; height: 24px; border-radius: 999px; background: rgba(20,34,65,.18); }}
    body.game .game-top {{ height: auto; min-height: 150px; padding: 46px 22px 18px; margin: -28px -28px 22px; border-radius: 0 0 34px 34px; background: rgba(255,255,255,.82); backdrop-filter: blur(10px); align-items: flex-start; flex-direction: column; justify-content: flex-start; gap: 12px; box-shadow: 0 16px 34px rgba(65,78,119,.14); }}
    body.game .game-top > div:last-child {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    body.game .game-title {{ max-width: 650px; font-size: 34px; line-height: 1.18; color: #263b72; text-shadow: 0 2px 0 rgba(255,255,255,.8); }}
    body.game .game-pill {{ height: 42px; margin: 0; padding: 0 15px; border-radius: 999px; background: #ffffff; color: #345083; font-size: 16px; box-shadow: inset 0 -4px 0 rgba(37,99,235,.08), 0 8px 18px rgba(30,64,175,.10); }}
    body.game .game-content {{ display: flex; flex-direction: column; gap: 18px; padding: 0; }}
    body.game .game-panel {{ width: 100%; border-radius: 30px; padding: 22px; background: rgba(255,255,255,.86); border: 4px solid rgba(255,255,255,.72); box-shadow: 0 18px 42px rgba(38,55,100,.16); }}
    body.game .game-panel h2 {{ margin: 0 0 18px; color: #223b71; font-size: 28px; }}
    body.game .game-board {{ grid-template-columns: repeat(8, 58px); grid-auto-rows: 58px; gap: 6px; justify-content: center; padding: 18px; border-radius: 28px; background: linear-gradient(180deg, #6654ff, #4934d8); box-shadow: inset 0 0 0 8px rgba(255,255,255,.20), 0 18px 35px rgba(55,48,163,.24); }}
    body.game .gem {{ width: 58px; height: 58px; border-radius: 17px; box-shadow: inset 0 -9px 0 rgba(0,0,0,.13), inset 0 8px 0 rgba(255,255,255,.18), 0 7px 13px rgba(31,41,55,.18); }}
    body.game .target-row {{ grid-template-columns: repeat(3, 1fr); gap: 12px; }}
    body.game .target {{ min-height: 96px; border-radius: 22px; padding: 14px 8px; font-size: 16px; background: linear-gradient(180deg, #ffffff, #f5fbff); box-shadow: inset 0 -4px 0 rgba(37,99,235,.07); }}
    body.game .target b {{ font-size: 30px; color: #315df4; }}
    body.game .level-map {{ height: 560px; border-radius: 32px; background:
      radial-gradient(circle at 25% 20%, rgba(255,255,255,.62) 0 54px, transparent 56px),
      radial-gradient(circle at 72% 70%, rgba(255,255,255,.45) 0 72px, transparent 74px),
      linear-gradient(180deg, #b8ffc8, #8bd7ff); box-shadow: inset 0 0 0 7px rgba(255,255,255,.35); }}
    body.game .level-node {{ width: 76px; height: 76px; border-width: 7px; font-size: 22px; box-shadow: 0 12px 24px rgba(30,64,175,.22), inset 0 -5px 0 rgba(250,204,21,.18); }}
    body.game .game-list {{ gap: 14px; }}
    body.game .game-list div {{ min-height: 58px; border-radius: 20px; padding: 14px 18px; font-size: 18px; box-shadow: inset 0 -4px 0 rgba(37,99,235,.05); }}
    body.game .big-action {{ height: 76px; border-radius: 28px; font-size: 28px; letter-spacing: 0; background: linear-gradient(180deg, #ff9b21, #f35b0b); box-shadow: inset 0 -8px 0 rgba(149,49,0,.22), 0 14px 24px rgba(234,88,12,.24); }}
    body.game .game-card-grid {{ grid-template-columns: repeat(2, 1fr); gap: 16px; }}
    body.game .game-card {{ min-height: 148px; border-radius: 26px; padding: 20px; background: linear-gradient(180deg, #ffffff, #fff9ed); box-shadow: 0 14px 28px rgba(31,41,55,.12), inset 0 -5px 0 rgba(37,99,235,.05); font-size: 18px; }}
    body.game .game-card strong {{ font-size: 34px; color: #2d63f5; }}
  </style>
</head>
<body class="{body_class}">{body}</body>
</html>"""


def _login_body(task: GenerationTask, blueprint: ProductBlueprint, design_brief: dict[str, Any] | None = None) -> str:
    profile = _profile_for_blueprint(task, blueprint, design_brief)
    pattern = str(profile.get("login_pattern") or "split_brand")
    style = f"--accent:{profile['accent']};--accent-soft:{profile['accent_soft']};--sidebar:{profile['sidebar']};"
    form = f"""
  <section class="login-box">
    <h2>{escape(str(profile.get("industry_subtype") or "系统"))}登录</h2>
    <div class="field"><label>账号</label><div>请输入用户名</div></div>
    <div class="field"><label>密码</label><div>请输入密码</div></div>
    <div class="field"><label>验证码</label><div>请输入右侧图形验证码</div></div>
    <div class="button">登录系统</div>
  </section>"""
    brand = f"""
  <section class="login-brand">
    <h1>{escape(task.software_name)}</h1>
    <p>{escape(str(profile.get("visual_mood") or blueprint.summary))}</p>
  </section>"""
    if pattern == "center_card":
        return f"""
<div class="login-wrap login-center_card" style="{style}">
{brand}
{form}
</div>"""
    if pattern == "console_gate":
        console = "".join(
            f"<div>{escape(label)}：{escape(value)} / {escape(desc)}</div>"
            for label, value, desc in profile.get("focus_cards", [])[:5]
        )
        return f"""
<div class="login-wrap login-console_gate" style="{style}">
  <section class="login-console">
    <div><strong>{escape(task.software_name)}</strong></div>
    {console}
  </section>
{form}
</div>"""
    if pattern == "portal_grid":
        cards = "".join(
            f"<div><span>{escape(label)}</span><strong>{escape(value)}</strong><small>{escape(desc)}</small></div>"
            for label, value, desc in profile.get("focus_cards", [])[:4]
        )
        return f"""
<div class="login-wrap login-portal_grid" style="{style}">
{form}
  <section class="login-portal">
    {cards}
  </section>
</div>"""
    if pattern == "side_preview":
        return f"""
<div class="login-wrap login-side_preview" style="{style}">
{form}
  <section class="login-preview">
    <div class="panel"><h2>{escape(task.software_name)}</h2><p class="muted">{escape(blueprint.summary)}</p></div>
    <div class="grid">{_metric_cards(profile["metrics"])}</div>
    <div class="panel"><h2>{escape(profile["todo_title"])}</h2>{_queue_list(profile, blueprint.modules, 4)}</div>
  </section>
</div>"""
    return f"""
<div class="login-wrap login-split_brand" style="{style}">
  <section class="login-hero">
    <h1>{escape(task.software_name)}</h1>
    <p>{escape(blueprint.summary)}</p>
  </section>
{form}
</div>"""


def _game_login_body(task: GenerationTask, blueprint: ProductBlueprint) -> str:
    return f"""
<div class="game-screen">
  <div class="game-frame">
    <div class="game-top">
      <div class="game-title">{escape(task.software_name)}</div>
      <div><span class="game-pill">公告</span><span class="game-pill">账号中心</span></div>
    </div>
    <div class="game-content">
      <section class="game-panel">
        <div class="level-map">
          {_level_nodes()}
        </div>
      </section>
      <section class="game-panel">
        <h2>玩家登录</h2>
        <div class="game-list">
          <div><span>账号</span><span>请输入手机号/账号</span></div>
          <div><span>密码</span><span>请输入密码</span></div>
          <div><span>区服</span><span>轻松点点消一区</span></div>
        </div>
        <div class="big-action">进入游戏</div>
        <div class="target-row">
          <div class="target">游客<b>试玩</b></div>
          <div class="target">微信<b>登录</b></div>
          <div class="target">公告<b>查看</b></div>
        </div>
      </section>
    </div>
  </div>
</div>"""


def _game_home_body(task: GenerationTask, blueprint: ProductBlueprint) -> str:
    return f"""
<div class="game-screen">
  <div class="game-frame">
    <div class="game-top">
      <div class="game-title">{escape(task.software_name)} 主界面</div>
      <div><span class="game-pill">体力 25/30</span><span class="game-pill">金币 12,860</span><span class="game-pill">钻石 380</span></div>
    </div>
    <div class="game-content">
      <section class="game-panel">
        <div class="level-map">{_level_nodes()}</div>
      </section>
      <section class="game-panel">
        <h2>今日目标</h2>
        <div class="game-list">
          <div><span>当前关卡</span><span>第 36 关</span></div>
          <div><span>星级进度</span><span>86 / 120</span></div>
          <div><span>限时活动</span><span>糖果收集赛</span></div>
          <div><span>每日任务</span><span>3 / 5</span></div>
        </div>
        <div class="big-action">开始游戏</div>
      </section>
    </div>
  </div>
</div>"""


def _game_body_from_screen(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    screen: UiScreenBlueprint,
    module: FeatureModule | None,
) -> str:
    if _is_board_like_game_screen(screen, module):
        return _game_board_body(task, module, title=screen.title)
    if screen.view_type == "game_login":
        return _game_login_body(task, blueprint)
    if screen.view_type == "game_home":
        return _game_home_body(task, blueprint)
    if screen.view_type == "game_level":
        return _game_level_body(task, module, title=screen.title)
    if screen.view_type == "game_inventory":
        return _game_inventory_body(task, module, title=screen.title)
    if screen.view_type == "game_statistics":
        return _game_statistics_body(task, blueprint, title=screen.title)
    if screen.view_type == "game_profile":
        return _game_profile_body(task, screen)
    if screen.view_type == "game_shop":
        return _game_shop_body(task, screen)
    return _game_board_body(task, module, title=screen.title)


def _is_board_like_game_screen(screen: UiScreenBlueprint, module: FeatureModule | None = None) -> bool:
    if screen.key in {"login", "dashboard", "statistics"}:
        return False
    text = " ".join(
        [
            screen.key,
            screen.title,
            screen.caption,
            screen.module_key,
            " ".join(screen.components),
            str(screen.sample_data),
            module.title if module else "",
            module.description if module else "",
        ]
    )
    strong_terms = [
        "糖果棋盘",
        "消除棋盘",
        "棋盘绘制",
        "棋盘编辑",
        "棋盘生成",
        "消除对局",
        "对局运行",
        "步数目标",
        "目标核验",
        "目标可达",
        "限定步数",
        "剩余步数",
        "掉落方向",
        "障碍格",
        "特殊糖果",
        "交换相邻",
        "颜色方块",
        "消除方块",
        "棋子",
        "连消",
    ]
    lowered = text.lower()
    english_terms = [
        "candy_board",
        "board",
        "match_board",
        "move_goal",
        "move",
        "moves",
        "obstacle",
        "gem",
        "candy",
        "tile",
        "combo",
    ]
    if any(term in lowered for term in english_terms):
        return True
    if any(term in text for term in strong_terms):
        return True
    return "棋盘" in text and any(term in text for term in ["编辑", "绘制", "生成", "掉落", "障碍", "步数", "目标", "糖果"])


def _game_board_body(task: GenerationTask, module: FeatureModule | None, title: str | None = None) -> str:
    title = title or "消除对局界面"
    return f"""
<div class="game-screen">
  <div class="game-frame">
    <div class="game-top">
      <div class="game-title">{escape(title)}</div>
      <div><span class="game-pill">第 36 关</span><span class="game-pill">剩余步数 18</span><span class="game-pill">得分 8,420</span></div>
    </div>
    <div class="game-content">
      <section class="game-panel">
        <div class="game-board">{_gems(64)}</div>
      </section>
      <section class="game-panel">
        <h2>通关目标</h2>
        <div class="target-row">
          <div class="target">红色方块<b>18</b></div>
          <div class="target">黄色星星<b>12</b></div>
          <div class="target">冰块障碍<b>6</b></div>
        </div>
        <div class="game-list" style="margin-top:16px">
          <div><span>道具锤子</span><span>x3</span></div>
          <div><span>刷新棋盘</span><span>x2</span></div>
          <div><span>横向火箭</span><span>x1</span></div>
        </div>
        <div class="big-action">交换相邻棋子</div>
      </section>
    </div>
  </div>
</div>"""


def _game_level_body(task: GenerationTask, module: FeatureModule | None, title: str | None = None) -> str:
    title = title or "关卡选择界面"
    return f"""
<div class="game-screen">
  <div class="game-frame">
    <div class="game-top">
      <div class="game-title">{escape(title)}</div>
      <div><span class="game-pill">章节 3</span><span class="game-pill">已解锁 36 关</span><span class="game-pill">最高星级 86</span></div>
    </div>
    <div class="game-content">
      <section class="game-panel"><div class="level-map">{_level_nodes()}</div></section>
      <section class="game-panel">
        <h2>关卡配置</h2>
        <div class="game-list">
          <div><span>棋盘尺寸</span><span>8 x 8</span></div>
          <div><span>目标分数</span><span>12,000</span></div>
          <div><span>限定步数</span><span>24</span></div>
          <div><span>障碍规则</span><span>冰块 / 木箱</span></div>
        </div>
        <div class="big-action">选择关卡</div>
      </section>
    </div>
  </div>
</div>"""


def _game_inventory_body(task: GenerationTask, module: FeatureModule | None, title: str | None = None) -> str:
    title = title or "道具背包界面"
    cards = [
        ("彩虹球", "x6", "#f472b6"),
        ("小木锤", "x12", "#f97316"),
        ("横向火箭", "x4", "#60a5fa"),
        ("金币礼包", "12,860", "#fbbf24"),
        ("体力瓶", "x5", "#34d399"),
        ("限时门票", "x3", "#a78bfa"),
    ]
    html = "".join(f"<div class='game-card'><span>{escape(name)}</span><strong style='color:{color}'>{escape(value)}</strong></div>" for name, value, color in cards)
    return f"""
<div class="game-screen">
  <div class="game-frame">
    <div class="game-top"><div class="game-title">{escape(title)}</div><div><span class="game-pill">背包容量 42/80</span><span class="game-pill">活动奖励待领取</span></div></div>
    <div class="game-content">
      <section class="game-panel"><div class="game-card-grid">{html}</div></section>
      <section class="game-panel">
        <h2>资产流水</h2>
        <div class="game-list">
          <div><span>通关奖励</span><span>+120 金币</span></div>
          <div><span>道具使用</span><span>-1 小木锤</span></div>
          <div><span>活动领取</span><span>+1 彩虹球</span></div>
        </div>
        <div class="big-action">领取奖励</div>
      </section>
    </div>
  </div>
</div>"""


def _game_profile_body(task: GenerationTask, screen: UiScreenBlueprint) -> str:
    return f"""
<div class="game-screen">
  <div class="game-frame">
    <div class="game-top"><div class="game-title">{escape(screen.title)}</div><div><span class="game-pill">账号正常</span><span class="game-pill">已实名认证</span></div></div>
    <div class="game-content">
      <section class="game-panel">
        <div class="game-card-grid">
          <div class="game-card"><span>玩家编号</span><strong>A1024</strong></div>
          <div class="game-card"><span>当前关卡</span><strong>36</strong></div>
          <div class="game-card"><span>累计星级</span><strong>86</strong></div>
          <div class="game-card"><span>金币余额</span><strong>12,860</strong></div>
          <div class="game-card"><span>连续登录</span><strong>7天</strong></div>
          <div class="game-card"><span>账号状态</span><strong>正常</strong></div>
        </div>
      </section>
      <section class="game-panel">
        <h2>通关记录</h2>
        <div class="game-list">
          <div><span>第 36 关</span><span>三星通关</span></div>
          <div><span>第 35 关</span><span>剩余 4 步</span></div>
          <div><span>第 34 关</span><span>最高分 16,420</span></div>
          <div><span>今日任务</span><span>3 / 5</span></div>
        </div>
        <div class="big-action">继续闯关</div>
      </section>
    </div>
  </div>
</div>"""


def _game_shop_body(task: GenerationTask, screen: UiScreenBlueprint) -> str:
    goods = [
        ("金币礼包", "￥6", "12,000 金币"),
        ("体力补给", "￥12", "60 点体力"),
        ("彩虹球礼包", "￥18", "彩虹球 x 6"),
        ("闯关助力包", "￥30", "火箭+锤子+刷新"),
        ("月卡奖励", "￥25", "每日钻石 x 30"),
        ("新手特惠", "￥3", "限购一次"),
    ]
    cards = "".join(
        f"<div class='game-card'><span>{escape(name)}</span><strong>{escape(price)}</strong><span>{escape(desc)}</span></div>"
        for name, price, desc in goods
    )
    return f"""
<div class="game-screen">
  <div class="game-frame">
    <div class="game-top"><div class="game-title">{escape(screen.title)}</div><div><span class="game-pill">金币 12,860</span><span class="game-pill">订单已发货</span></div></div>
    <div class="game-content">
      <section class="game-panel"><div class="game-card-grid">{cards}</div></section>
      <section class="game-panel">
        <h2>订单状态</h2>
        <div class="game-list">
          <div><span>金币礼包订单</span><span>已发货</span></div>
          <div><span>体力补给订单</span><span>支付成功</span></div>
          <div><span>退款申请</span><span>待审核</span></div>
          <div><span>对账批次</span><span>今日已同步</span></div>
        </div>
        <div class="big-action">购买礼包</div>
      </section>
    </div>
  </div>
</div>"""


def _game_statistics_body(task: GenerationTask, blueprint: ProductBlueprint, title: str = "游戏结算统计界面") -> str:
    return f"""
<div class="game-screen">
  <div class="game-frame">
    <div class="game-top"><div class="game-title">{escape(title)}</div><div><span class="game-pill">本局结算</span><span class="game-pill">三星通关</span></div></div>
    <div class="game-content">
      <section class="game-panel">
        <div class="game-card-grid">
          <div class="game-card"><span>最终得分</span><strong>18,640</strong></div>
          <div class="game-card"><span>剩余步数</span><strong>6</strong></div>
          <div class="game-card"><span>连消次数</span><strong>14</strong></div>
          <div class="game-card"><span>最高连击</span><strong>7</strong></div>
          <div class="game-card"><span>获得金币</span><strong>320</strong></div>
          <div class="game-card"><span>星级评价</span><strong>★★★</strong></div>
        </div>
      </section>
      <section class="game-panel">
        <h2>结算明细</h2>
        <div class="game-list">
          <div><span>基础分</span><span>12,000</span></div>
          <div><span>步数奖励</span><span>+3,600</span></div>
          <div><span>连消奖励</span><span>+2,140</span></div>
          <div><span>道具加成</span><span>+900</span></div>
        </div>
        <div class="big-action">下一关</div>
      </section>
    </div>
  </div>
</div>"""


def _admin_profile(task: GenerationTask) -> dict[str, Any]:
    default: dict[str, Any] = {
        "accent": "#2f6fed",
        "accent_soft": "#eef6ff",
        "sidebar": "#1f314f",
        "layout_variant": "classic",
        "nav_model": "side_menu",
        "workspace_shape": "",
        "login_pattern": "split_brand",
        "industry_subtype": "",
        "visual_mood": "桌面业务系统界面",
        "dashboard_pattern": "指标总览+待办队列",
        "module_pattern": "列表详情",
        "user_label": "当前用户：系统管理员",
        "metrics": [("今日新增", "128"), ("待办审核", "36"), ("异常预警", "7"), ("本月处理", "2,406")],
        "filters": ["关键字", "状态", "时间范围"],
        "table_headers": ["业务名称", "所属模块", "状态", "操作"],
        "subjects": ["业务流程", "基础档案", "审核任务", "统计记录", "配置项", "处理单"],
        "objects": ["业务对象", "组织节点", "责任人员", "数据记录", "流程实例", "报表项"],
        "states": ["正常", "待处理", "已归档"],
        "actions": ["查看 / 编辑 / 审核", "详情 / 流转 / 归档"],
        "todo_title": "待办事项",
        "focus_title": "运行专题看板",
        "module_focus_title": "业务处理流程",
        "stat_title": "模块统计",
        "stat_headers": ["模块", "记录数", "完成率", "归档状态"],
        "stat_status": "已归档",
        "focus_cards": [("流程完成率", "96.3%", "本日核心流程闭环"), ("异常处理", "7", "已生成预警提醒"), ("平均时效", "18m", "较昨日提升 6%"), ("数据质量", "98.1%", "校验规则通过率")],
        "process": ["提交", "校验", "审核", "归档"],
        "chart_values": [62, 76, 48, 86, 70, 92],
    }
    profiles: dict[str, dict[str, Any]] = {
        "教育软件": {
            "accent": "#2563eb",
            "accent_soft": "#eff6ff",
            "sidebar": "#17356f",
            "layout_variant": "workflow",
            "user_label": "当前用户：教务管理员",
            "metrics": [("在学学员", "1,286"), ("待批作业", "72"), ("课程完成率", "86.4%"), ("今日课时", "148")],
            "filters": ["课程名称", "班级", "学习状态", "授课教师"],
            "table_headers": ["课程/任务", "班级或学员", "学习状态", "教学操作"],
            "subjects": ["同步课程", "课后作业", "章节测验", "直播课堂", "错题练习", "学习计划"],
            "objects": ["初二 3 班", "高一数学班", "英语提升组", "学生 A1024", "周末培优班", "在线学习组"],
            "states": ["进行中", "待批改", "已完成", "待跟进"],
            "actions": ["查看 / 批改 / 讲评", "进度 / 提醒 / 分析"],
            "todo_title": "教学待办",
            "focus_title": "学习过程看板",
            "module_focus_title": "教学闭环",
            "stat_headers": ["课程模块", "学习人次", "完成率", "教学状态"],
            "stat_status": "已完成",
            "focus_cards": [("课程完成率", "86.4%", "按班级和课程聚合"), ("平均得分", "82.6", "最近一次测评"), ("待批作业", "72", "需教师处理"), ("活跃学员", "1,026", "今日产生学习轨迹")],
            "process": ["备课", "授课", "作业", "测评", "讲评"],
            "chart_values": [66, 74, 82, 58, 88, 92],
        },
        "金融软件": {
            "accent": "#0f766e",
            "accent_soft": "#ecfdf5",
            "sidebar": "#123c40",
            "layout_variant": "risk",
            "user_label": "当前用户：风控管理员",
            "metrics": [("交易笔数", "8,426"), ("待复核", "58"), ("风险命中", "23"), ("清算金额", "1.82亿")],
            "filters": ["客户编号", "风险等级", "交易时间", "复核状态"],
            "table_headers": ["交易/客户", "金融产品", "风险状态", "处理动作"],
            "subjects": ["授信申请", "交易流水", "清算批次", "风控命中", "客户资料", "产品费率"],
            "objects": ["稳健理财", "企业授信", "支付清算", "客户 KYC", "额度策略", "监管报送"],
            "states": ["正常", "待复核", "高风险", "已结算"],
            "actions": ["详情 / 复核 / 冻结", "风控 / 审批 / 导出"],
            "todo_title": "金融复核待办",
            "focus_title": "风险与清算看板",
            "module_focus_title": "审批风控流程",
            "stat_headers": ["业务模块", "业务规模", "通过率", "监管状态"],
            "stat_status": "已报送",
            "focus_cards": [("风险命中率", "0.27%", "规则引擎实时拦截"), ("待复核金额", "326万", "需双人审批"), ("清算成功率", "99.2%", "T+0 批次统计"), ("监管报表", "12", "今日已生成")],
            "process": ["申请", "风控", "复核", "清算", "报送"],
            "chart_values": [72, 68, 92, 54, 80, 88],
        },
        "医疗软件": {
            "accent": "#0891b2",
            "accent_soft": "#ecfeff",
            "sidebar": "#164e63",
            "layout_variant": "workflow",
            "user_label": "当前用户：医务管理员",
            "metrics": [("今日就诊", "436"), ("待分诊", "29"), ("处方审核", "64"), ("库存预警", "11")],
            "filters": ["患者姓名", "科室", "就诊状态", "医生"],
            "table_headers": ["患者/诊疗", "科室或药品", "诊疗状态", "医疗操作"],
            "subjects": ["患者档案", "预约号源", "门诊病历", "处方审核", "药品批次", "随访任务"],
            "objects": ["内科门诊", "儿科门诊", "影像检查", "药房库存", "慢病随访", "护理记录"],
            "states": ["待分诊", "诊疗中", "待审核", "已归档"],
            "actions": ["查看 / 接诊 / 开方", "审核 / 随访 / 归档"],
            "todo_title": "诊疗待办",
            "focus_title": "门诊运行看板",
            "module_focus_title": "诊疗质控流程",
            "stat_headers": ["医疗模块", "业务量", "完成率", "质控状态"],
            "stat_status": "已质控",
            "focus_cards": [("平均候诊", "16m", "较昨日下降 4 分钟"), ("处方通过率", "97.8%", "药师审核统计"), ("药品预警", "11", "近效期和低库存"), ("随访完成", "84.2%", "慢病患者跟踪")],
            "process": ["挂号", "分诊", "接诊", "处方", "随访"],
            "chart_values": [70, 82, 76, 64, 58, 88],
        },
        "地理信息软件": {
            "accent": "#16a34a",
            "accent_soft": "#f0fdf4",
            "sidebar": "#14532d",
            "layout_variant": "map",
            "user_label": "当前用户：GIS管理员",
            "metrics": [("图层数量", "186"), ("空间要素", "42.8万"), ("外业任务", "34"), ("服务调用", "12.6万")],
            "filters": ["图层名称", "行政区划", "数据类型", "发布状态"],
            "table_headers": ["空间任务", "图层/区域", "数据状态", "地图操作"],
            "subjects": ["图层更新", "外业采集", "地址解析", "专题制图", "服务发布", "空间分析"],
            "objects": ["基础底图", "道路网格", "设施点位", "行政区划", "热力网格", "瓦片服务"],
            "states": ["已发布", "待审核", "采集中", "已同步"],
            "actions": ["定位 / 预览 / 发布", "审核 / 入库 / 导出"],
            "todo_title": "空间数据待办",
            "focus_title": "地图服务看板",
            "module_focus_title": "空间数据流程",
            "stat_headers": ["空间模块", "要素量", "入库率", "服务状态"],
            "stat_status": "已发布",
            "focus_cards": [("图层覆盖率", "92.6%", "业务图层可用范围"), ("外业轨迹", "34", "今日上传任务"), ("服务可用性", "99.9%", "瓦片和接口监控"), ("地址匹配率", "96.1%", "标准地址解析")],
            "process": ["采集", "质检", "入库", "制图", "发布"],
            "chart_values": [62, 78, 88, 66, 94, 74],
        },
        "物联网软件": {
            "accent": "#7c3aed",
            "accent_soft": "#f5f3ff",
            "sidebar": "#312e81",
            "layout_variant": "map",
            "user_label": "当前用户：设备管理员",
            "metrics": [("在线设备", "8,642"), ("告警设备", "37"), ("上报数据", "126万"), ("指令成功率", "98.7%")],
            "filters": ["设备编号", "区域", "在线状态", "告警等级"],
            "table_headers": ["设备/任务", "位置或网关", "运行状态", "设备操作"],
            "subjects": ["设备档案", "遥测上报", "远程指令", "离线告警", "巡检任务", "网关通道"],
            "objects": ["东区网关", "冷链仓库", "泵站节点", "楼宇传感器", "充电桩", "工业采集器"],
            "states": ["在线", "告警中", "待巡检", "已接入"],
            "actions": ["详情 / 控制 / 派单", "定位 / 诊断 / 记录"],
            "todo_title": "设备运维待办",
            "focus_title": "设备运行看板",
            "module_focus_title": "设备运维流程",
            "stat_headers": ["设备模块", "设备量", "在线率", "健康状态"],
            "stat_status": "稳定",
            "focus_cards": [("设备在线率", "98.7%", "网关连接正常"), ("告警闭环", "91.4%", "今日处置效率"), ("平均电量", "76%", "低电量设备 18 台"), ("数据延迟", "1.8s", "实时采集链路")],
            "process": ["接入", "采集", "告警", "派单", "维护"],
            "chart_values": [88, 82, 64, 76, 92, 70],
        },
        "信息安全软件": {
            "accent": "#dc2626",
            "accent_soft": "#fef2f2",
            "sidebar": "#451a1a",
            "layout_variant": "risk",
            "user_label": "当前用户：安全管理员",
            "metrics": [("安全事件", "126"), ("高危漏洞", "18"), ("处置中", "32"), ("合规通过", "94.8%")],
            "filters": ["资产名称", "风险等级", "事件类型", "处置状态"],
            "table_headers": ["安全事件", "资产或策略", "风险状态", "处置动作"],
            "subjects": ["入侵告警", "漏洞修复", "基线检查", "日志审计", "合规整改", "策略例外"],
            "objects": ["核心主机", "数据库资产", "公网应用", "访问策略", "等保条款", "敏感数据"],
            "states": ["高风险", "待处置", "已修复", "已审计"],
            "actions": ["研判 / 派单 / 封禁", "复测 / 审计 / 导出"],
            "todo_title": "安全处置待办",
            "focus_title": "风险态势看板",
            "module_focus_title": "安全闭环流程",
            "stat_headers": ["安全模块", "事件量", "闭环率", "风险状态"],
            "stat_status": "已闭环",
            "focus_cards": [("风险评分", "73", "较昨日下降 5 分"), ("漏洞闭环率", "89.6%", "高危优先处置"), ("异常登录", "14", "已触发二次验证"), ("合规通过", "94.8%", "检查项完成情况")],
            "process": ["发现", "研判", "派单", "复测", "审计"],
            "chart_values": [76, 48, 82, 54, 70, 92],
        },
        "大数据软件": {
            "accent": "#9333ea",
            "accent_soft": "#faf5ff",
            "sidebar": "#3b0764",
            "layout_variant": "pipeline",
            "user_label": "当前用户：数据管理员",
            "metrics": [("数据源", "72"), ("采集任务", "148"), ("质量评分", "96.5"), ("今日入仓", "8.6亿")],
            "filters": ["数据源", "主题域", "调度状态", "质量等级"],
            "table_headers": ["数据任务", "主题域/表", "治理状态", "数据操作"],
            "subjects": ["采集任务", "质量规则", "数据表", "血缘关系", "指标定义", "敏感标签"],
            "objects": ["用户主题域", "交易事实表", "日志明细", "指标宽表", "数据目录", "实时队列"],
            "states": ["运行中", "待校验", "已入仓", "质量预警"],
            "actions": ["查看 / 调度 / 血缘", "校验 / 发布 / 导出"],
            "todo_title": "数据治理待办",
            "focus_title": "数据链路看板",
            "module_focus_title": "数据处理流程",
            "stat_headers": ["数据模块", "数据量", "质量率", "入仓状态"],
            "stat_status": "已入仓",
            "focus_cards": [("采集成功率", "98.9%", "近 24 小时任务"), ("质量评分", "96.5", "规则校验汇总"), ("敏感数据", "312", "已纳入权限审批"), ("平均延迟", "46s", "实时链路统计")],
            "process": ["接入", "采集", "清洗", "建模", "发布"],
            "chart_values": [58, 74, 86, 92, 66, 80],
        },
        "人工智能软件": {
            "accent": "#4f46e5",
            "accent_soft": "#eef2ff",
            "sidebar": "#1e1b4b",
            "layout_variant": "pipeline",
            "user_label": "当前用户：算法管理员",
            "metrics": [("数据集", "46"), ("训练任务", "18"), ("模型准确率", "92.7%"), ("推理调用", "32.4万")],
            "filters": ["模型名称", "数据集", "训练状态", "发布版本"],
            "table_headers": ["模型/任务", "数据集或服务", "训练状态", "算法操作"],
            "subjects": ["样本标注", "训练任务", "模型版本", "推理服务", "人工复核", "漂移监控"],
            "objects": ["图像数据集", "文本分类", "预测服务", "模型 v2.4", "GPU 队列", "评估集"],
            "states": ["训练中", "待审核", "已发布", "漂移预警"],
            "actions": ["评估 / 发布 / 回滚", "训练 / 复核 / 监控"],
            "todo_title": "模型任务待办",
            "focus_title": "模型运行看板",
            "module_focus_title": "模型生命周期",
            "stat_headers": ["算法模块", "样本量", "准确率", "发布状态"],
            "stat_status": "已发布",
            "focus_cards": [("准确率", "92.7%", "最近评估集结果"), ("召回率", "89.4%", "业务阈值达标"), ("推理延迟", "86ms", "线上服务 P95"), ("漂移信号", "3", "需人工复核")],
            "process": ["采样", "标注", "训练", "评估", "发布"],
            "chart_values": [64, 70, 88, 92, 76, 84],
        },
        "APP": {
            "accent": "#be185d",
            "accent_soft": "#fdf2f8",
            "sidebar": "#4a1230",
            "layout_variant": "workflow",
            "user_label": "当前用户：运营管理员",
            "metrics": [("活跃用户", "12.8万"), ("待处理订单", "426"), ("推送到达率", "96.8%"), ("今日留存", "42.6%")],
            "filters": ["用户昵称", "渠道来源", "订单状态", "设备类型"],
            "table_headers": ["移动业务", "用户或渠道", "运营状态", "APP操作"],
            "subjects": ["用户登录", "首页推荐", "服务订单", "消息推送", "个人资料", "留存分析"],
            "objects": ["iOS 渠道", "Android 渠道", "会员用户", "服务订单", "推送任务", "活动入口"],
            "states": ["正常", "待支付", "已上线", "已退款"],
            "actions": ["查看 / 推送 / 回访", "配置 / 上线 / 导出"],
            "todo_title": "移动运营待办",
            "focus_title": "APP 运营看板",
            "module_focus_title": "移动端业务流程",
            "stat_headers": ["移动模块", "访问量", "转化率", "运营状态"],
            "stat_status": "已上线",
            "focus_cards": [("日活用户", "12.8万", "按设备和渠道统计"), ("订单转化", "18.6%", "首页入口转化率"), ("推送到达", "96.8%", "近 24 小时任务"), ("崩溃率", "0.08%", "移动端稳定性")],
            "process": ["注册", "浏览", "下单", "支付", "通知"],
            "chart_values": [72, 86, 64, 78, 92, 70],
        },
        "云计算软件": {
            "accent": "#0284c7",
            "accent_soft": "#f0f9ff",
            "sidebar": "#0c4a6e",
            "layout_variant": "pipeline",
            "user_label": "当前用户：云平台管理员",
            "metrics": [("活跃租户", "268"), ("云主机", "3,642"), ("资源告警", "19"), ("账单金额", "86.4万")],
            "filters": ["租户名称", "资源类型", "运行状态", "告警等级"],
            "table_headers": ["云资源", "租户或项目", "资源状态", "云平台操作"],
            "subjects": ["租户配额", "云主机实例", "对象存储", "安全组", "监控告警", "计量账单"],
            "objects": ["生产项目", "测试项目", "虚拟网络", "云硬盘", "边缘节点", "资源池"],
            "states": ["运行中", "资源告警", "待审核", "已归档"],
            "actions": ["详情 / 扩容 / 回收", "监控 / 审批 / 导出"],
            "todo_title": "云资源待办",
            "focus_title": "云资源运行看板",
            "module_focus_title": "云资源生命周期",
            "stat_headers": ["云模块", "资源量", "利用率", "运行状态"],
            "stat_status": "运行中",
            "focus_cards": [("CPU 利用率", "68.2%", "多租户资源池均值"), ("存储容量", "742TB", "对象存储和云硬盘"), ("告警闭环", "93.5%", "运维工单处理"), ("成本优化", "12.4%", "闲置资源回收")],
            "process": ["申请", "审批", "开通", "监控", "回收"],
            "chart_values": [80, 62, 88, 74, 68, 92],
        },
        "VR软件": {
            "accent": "#7e22ce",
            "accent_soft": "#faf5ff",
            "sidebar": "#3b0764",
            "layout_variant": "pipeline",
            "user_label": "当前用户：内容管理员",
            "metrics": [("虚拟场景", "126"), ("在线设备", "384"), ("体验记录", "8,426"), ("素材待审", "37")],
            "filters": ["场景名称", "设备编号", "体验状态", "素材类型"],
            "table_headers": ["VR业务", "场景或设备", "体验状态", "VR操作"],
            "subjects": ["场景版本", "头显设备", "交互脚本", "沉浸培训", "体验记录", "素材审核"],
            "objects": ["应急演练场景", "培训教室", "VR 头显", "手柄定位器", "三维模型", "体验用户"],
            "states": ["体验中", "待校准", "待审核", "已完成"],
            "actions": ["预览 / 校准 / 发布", "审核 / 回放 / 导出"],
            "todo_title": "VR内容待办",
            "focus_title": "沉浸体验看板",
            "module_focus_title": "VR内容发布流程",
            "stat_headers": ["VR模块", "体验次数", "完成率", "发布状态"],
            "stat_status": "已发布",
            "focus_cards": [("设备在线率", "97.4%", "头显与定位器状态"), ("平均沉浸时长", "18m", "单次体验均值"), ("场景完成率", "91.2%", "培训任务统计"), ("素材待审", "37", "模型贴图音视频")],
            "process": ["建模", "审核", "发布", "体验", "复盘"],
            "chart_values": [60, 76, 88, 70, 92, 66],
        },
        "5G软件": {
            "accent": "#0d9488",
            "accent_soft": "#f0fdfa",
            "sidebar": "#134e4a",
            "layout_variant": "map",
            "user_label": "当前用户：网络管理员",
            "metrics": [("基站站点", "1,284"), ("切片实例", "72"), ("边缘节点", "46"), ("网络告警", "23")],
            "filters": ["站点名称", "网络切片", "业务等级", "告警状态"],
            "table_headers": ["网络业务", "站点或切片", "网络状态", "5G操作"],
            "subjects": ["基站巡检", "切片开通", "边缘应用", "终端接入", "QoS 监控", "流量分析"],
            "objects": ["核心城区", "工业园区", "低时延切片", "边缘节点 A", "物联终端", "专网业务"],
            "states": ["正常", "边缘告警", "已激活", "待维护"],
            "actions": ["拓扑 / 诊断 / 派单", "开通 / 调优 / 导出"],
            "todo_title": "网络运维待办",
            "focus_title": "5G 网络运行看板",
            "module_focus_title": "网络业务保障流程",
            "stat_headers": ["网络模块", "连接数", "达标率", "保障状态"],
            "stat_status": "已保障",
            "focus_cards": [("平均时延", "12ms", "核心业务 P95"), ("切片达标", "98.1%", "带宽和隔离指标"), ("边缘负载", "64%", "节点资源均值"), ("告警闭环", "90.6%", "站点故障处理")],
            "process": ["开通", "接入", "监控", "告警", "优化"],
            "chart_values": [74, 82, 60, 88, 70, 94],
        },
        "小程序": {
            "accent": "#16a34a",
            "accent_soft": "#f0fdf4",
            "sidebar": "#14532d",
            "layout_variant": "workflow",
            "user_label": "当前用户：小程序运营",
            "metrics": [("授权用户", "6.4万"), ("预约订单", "312"), ("优惠券核销", "1,826"), ("订阅触达", "95.3%")],
            "filters": ["微信昵称", "服务分类", "订单状态", "活动渠道"],
            "table_headers": ["小程序业务", "用户或服务", "服务状态", "运营操作"],
            "subjects": ["微信授权", "首页轮播", "服务预约", "订单支付", "优惠券", "订阅消息"],
            "objects": ["微信用户", "服务门店", "预约时段", "支付订单", "营销活动", "订阅模板"],
            "states": ["已预约", "待支付", "已核销", "已上线"],
            "actions": ["查看 / 核销 / 退款", "配置 / 推送 / 导出"],
            "todo_title": "小程序待办",
            "focus_title": "轻应用运营看板",
            "module_focus_title": "小程序服务流程",
            "stat_headers": ["小程序模块", "访问量", "核销率", "运营状态"],
            "stat_status": "已上线",
            "focus_cards": [("访问转化率", "21.8%", "首页到预约链路"), ("核销订单", "1,826", "门店服务完成量"), ("订阅触达", "95.3%", "模板消息发送"), ("活动领券", "4,208", "优惠券领取记录")],
            "process": ["授权", "浏览", "预约", "支付", "核销"],
            "chart_values": [68, 84, 76, 58, 92, 80],
        },
        "智慧城市软件": {
            "accent": "#1d4ed8",
            "accent_soft": "#eff6ff",
            "sidebar": "#172554",
            "layout_variant": "map",
            "user_label": "当前用户：城市运营员",
            "metrics": [("公共资源", "2,846"), ("预警事件", "43"), ("核验通行", "18.6万"), ("服务网点", "326")],
            "filters": ["区域名称", "事件类型", "资源状态", "处置部门"],
            "table_headers": ["城市业务", "区域或资源", "处置状态", "城市操作"],
            "subjects": ["态势预警", "资源档案", "票务订单", "门禁通行", "游客会员", "统计报表"],
            "objects": ["核心景区", "服务网点", "闸机设备", "公共停车场", "应急事件", "运营报表"],
            "states": ["正常", "待处置", "已核验", "已归档"],
            "actions": ["定位 / 派单 / 核验", "统计 / 审核 / 导出"],
            "todo_title": "城市治理待办",
            "focus_title": "城市运行看板",
            "module_focus_title": "城市事件闭环",
            "stat_headers": ["城市模块", "业务量", "办结率", "运行状态"],
            "stat_status": "已归档",
            "focus_cards": [("事件办结率", "94.7%", "跨部门协同处置"), ("资源在线率", "98.3%", "设备和服务网点"), ("客流峰值", "3.8万", "区域热度监测"), ("核验成功率", "99.1%", "闸机通行记录")],
            "process": ["发现", "派单", "处置", "核验", "归档"],
            "chart_values": [82, 70, 88, 64, 76, 92],
        },
    }
    profile = dict(default)
    for key, value in profiles.get(task.product_type, {}).items():
        profile[key] = value
    return profile


def _dashboard_body(task: GenerationTask, blueprint: ProductBlueprint, design_brief: dict[str, Any] | None = None) -> str:
    profile = _profile_for_blueprint(task, blueprint, design_brief)
    return _layout(task, blueprint, "系统首页", _dashboard_content(profile, blueprint), active="系统首页", design_brief=design_brief)


def _module_body(task: GenerationTask, blueprint: ProductBlueprint, module: FeatureModule, design_brief: dict[str, Any] | None = None) -> str:
    profile = _profile_for_blueprint(task, blueprint, design_brief)
    return _layout(task, blueprint, module.title, _module_content(profile, blueprint, module), active=module.title, design_brief=design_brief)


def _statistics_body(task: GenerationTask, blueprint: ProductBlueprint, design_brief: dict[str, Any] | None = None) -> str:
    profile = _profile_for_blueprint(task, blueprint, design_brief)
    return _layout(task, blueprint, "统计报表界面", _statistics_content(profile, blueprint), active="统计报表页", design_brief=design_brief)


def _dashboard_content(profile: dict[str, Any], blueprint: ProductBlueprint) -> str:
    variant = str(profile.get("layout_variant") or "classic")
    shaped = _dashboard_shape_content(profile, blueprint)
    if shaped:
        return shaped
    if variant == "risk":
        return f"""
{_risk_tiles(profile)}
<div class="dashboard-split">
  <div class="panel"><h2>{escape(profile["todo_title"])}</h2>{_table(profile["table_headers"], _domain_rows(blueprint.modules, profile, 7))}</div>
  <div class="panel"><h2>{escape(profile["focus_title"])}</h2>{_focus_panel(profile)}{_mini_chart(profile)}</div>
</div>
<div class="panel"><h2>复核队列</h2>{_queue_list(profile, blueprint.modules, 4)}</div>
"""
    if variant == "map":
        return f"""
<div class="grid">{_metric_cards(profile["metrics"])}</div>
<div class="dashboard-split">
  <div class="panel"><h2>{escape(profile["focus_title"])}</h2>{_map_board(profile, blueprint.modules)}</div>
  <div class="panel"><h2>{escape(profile["todo_title"])}</h2>{_queue_list(profile, blueprint.modules, 5)}</div>
</div>
<div class="panel"><h2>业务入口</h2><div class="toolbar">{_quick_buttons(blueprint.modules)}</div></div>
"""
    if variant == "pipeline":
        return f"""
{_pipeline_cards(profile)}
<div class="two-col">
  <div class="panel"><h2>{escape(profile["todo_title"])}</h2>{_queue_list(profile, blueprint.modules, 6)}</div>
  <div class="panel"><h2>{escape(profile["module_focus_title"])}</h2>{_timeline(profile)}</div>
</div>
<div class="panel"><h2>{escape(profile["focus_title"])}</h2>{_mini_chart(profile)}<div class="process">{_process(profile)}</div></div>
"""
    if variant == "workflow":
        return f"""
<div class="grid">{_metric_cards(profile["metrics"])}</div>
<div class="dashboard-split">
  <div class="panel"><h2>{escape(profile["module_focus_title"])}</h2>{_timeline(profile)}</div>
  <div class="panel"><h2>{escape(profile["focus_title"])}</h2>{_focus_panel(profile)}</div>
</div>
<div class="panel"><h2>{escape(profile["todo_title"])}</h2>{_queue_list(profile, blueprint.modules, 5)}</div>
"""
    if variant == "command":
        return f"""
<div class="command-strip">{_metric_cards(profile["metrics"])}</div>
<div class="command-grid">
  <div class="panel command-main"><h2>{escape(profile["dashboard_pattern"])}</h2>{_mini_chart(profile)}<div class="process">{_process(profile)}</div></div>
  <div class="panel"><h2>{escape(profile["todo_title"])}</h2>{_queue_list(profile, blueprint.modules, 5)}</div>
  <div class="panel"><h2>{escape(profile["focus_title"])}</h2>{_focus_panel(profile, compact=True)}</div>
</div>
"""
    if variant == "kanban":
        return f"""
<div class="grid">{_metric_cards(profile["metrics"])}</div>
<div class="panel"><h2>{escape(profile["dashboard_pattern"])}</h2>{_kanban_board(profile, blueprint.modules)}</div>
<div class="dashboard-split">
  <div class="panel"><h2>{escape(profile["focus_title"])}</h2>{_focus_panel(profile, compact=True)}</div>
  <div class="panel"><h2>近期趋势</h2>{_mini_chart(profile)}</div>
</div>
"""
    if variant == "matrix":
        return f"""
<div class="matrix-layout">
  <div class="panel matrix-main"><h2>{escape(profile["dashboard_pattern"])}</h2>{_matrix_board(profile, blueprint.modules)}</div>
  <div class="panel"><h2>{escape(profile["todo_title"])}</h2>{_queue_list(profile, blueprint.modules, 4)}</div>
  <div class="panel"><h2>指标趋势</h2>{_mini_chart(profile)}</div>
</div>
"""
    return f"""
<div class="grid">{_metric_cards(profile["metrics"])}</div>
<div class="two-col">
  <div class="panel"><h2>{escape(profile["todo_title"])}</h2>{_table(profile["table_headers"], _domain_rows(blueprint.modules, profile, 6))}</div>
  <div class="panel"><h2>{escape(profile["focus_title"])}</h2>{_focus_panel(profile)}</div>
</div>
<div class="panel"><h2>快捷入口</h2><div class="toolbar">{_quick_buttons(blueprint.modules)}</div></div>
"""


def _module_content(profile: dict[str, Any], blueprint: ProductBlueprint, module: FeatureModule) -> str:
    variant = str(profile.get("layout_variant") or "classic")
    filters = _filter_toolbar(profile)
    shaped = _module_shape_content(profile, blueprint, module, filters)
    if shaped:
        return shaped
    if variant == "risk":
        return f"""
{_risk_tiles(profile)}
<div class="panel">
  <div class="toolbar">{filters}<span class="button">风险复核</span><span class="button">导出</span></div>
  {_table(profile["table_headers"], _module_rows(module, profile))}
</div>
<div class="two-col">
  <div class="panel"><h2>研判规则</h2>{_focus_panel(profile, compact=True)}</div>
  <div class="panel"><h2>{escape(profile["module_focus_title"])}</h2>{_timeline(profile)}</div>
</div>
"""
    if variant == "map":
        return f"""
<div class="toolbar">{filters}<span class="button">定位</span><span class="button">同步</span></div>
<div class="dashboard-split">
  <div class="panel"><h2>{escape(module.title)}</h2>{_map_board(profile, [module] + blueprint.modules[:5])}</div>
  <div class="panel"><h2>空间任务</h2>{_queue_list(profile, [module] + blueprint.modules[:5], 5)}</div>
</div>
<div class="panel"><h2>业务明细</h2>{_table(profile["table_headers"], _module_rows(module, profile))}</div>
"""
    if variant == "pipeline":
        return f"""
{_pipeline_cards(profile, module)}
<div class="two-col">
  <div class="panel"><div class="toolbar">{filters}<span class="button">调度</span><span class="button">发布</span></div>{_table(profile["table_headers"], _module_rows(module, profile))}</div>
  <div class="panel"><h2>{escape(module.title)}流程</h2>{_timeline(profile)}</div>
</div>
<div class="panel"><h2>模块说明</h2><p class="muted">{escape(module.description)}</p><div class="process">{_process(profile)}</div></div>
"""
    if variant == "workflow":
        return f"""
<div class="dashboard-split">
  <div class="panel"><h2>{escape(module.title)}处理流</h2>{_timeline(profile)}</div>
  <div class="panel"><h2>{escape(profile["module_focus_title"])}</h2>{_focus_panel(profile, compact=True)}</div>
</div>
<div class="panel">
  <div class="toolbar">{filters}<span class="button">查询</span><span class="button">新增</span></div>
  {_table(profile["table_headers"], _module_rows(module, profile))}
</div>
<div class="panel"><h2>模块说明</h2><p class="muted">{escape(module.description)}</p></div>
"""
    if variant == "command":
        return f"""
<div class="command-strip">{_metric_cards(profile["metrics"])}</div>
<div class="command-grid">
  <div class="panel command-main"><h2>{escape(module.title)}指挥区</h2><div class="toolbar">{filters}<span class="button">处置</span><span class="button">联动</span></div>{_table(profile["table_headers"], _module_rows(module, profile))}</div>
  <div class="panel"><h2>处置步骤</h2>{_timeline(profile)}</div>
  <div class="panel"><h2>专题规则</h2>{_focus_panel(profile, compact=True)}</div>
</div>
"""
    if variant == "kanban":
        return f"""
<div class="panel"><h2>{escape(module.title)}任务看板</h2>{_kanban_board(profile, [module] + blueprint.modules[:5])}</div>
<div class="dashboard-split">
  <div class="panel"><div class="toolbar">{filters}<span class="button">新增任务</span><span class="button">批量处理</span></div>{_table(profile["table_headers"], _module_rows(module, profile))}</div>
  <div class="panel"><h2>模块说明</h2><p class="muted">{escape(module.description)}</p>{_focus_panel(profile, compact=True)}</div>
</div>
"""
    if variant == "matrix":
        return f"""
<div class="matrix-layout">
  <div class="panel matrix-main"><h2>{escape(module.title)}矩阵</h2>{_matrix_board(profile, [module] + blueprint.modules[:5])}</div>
  <div class="panel"><h2>处理列表</h2>{_table(profile["table_headers"], _module_rows(module, profile))}</div>
  <div class="panel"><h2>{escape(profile["module_focus_title"])}</h2>{_timeline(profile)}</div>
</div>
"""
    return f"""
<div class="panel">
  <div class="toolbar">{filters}<span class="button">查询</span><span class="button">新增</span></div>
  {_table(profile["table_headers"], _module_rows(module, profile))}
</div>
<div class="two-col">
  <div class="panel"><h2>模块说明</h2><p class="muted">{escape(module.description)}</p><div class="process">{_process(profile)}</div></div>
  <div class="panel"><h2>{escape(profile["module_focus_title"])}</h2>{_focus_panel(profile, compact=True)}</div>
</div>
"""


def _statistics_content(profile: dict[str, Any], blueprint: ProductBlueprint) -> str:
    variant = str(profile.get("layout_variant") or "classic")
    rows = _stat_rows(profile)
    shaped = _statistics_shape_content(profile, blueprint, rows)
    if shaped:
        return shaped
    if variant == "risk":
        return f"""
{_risk_tiles(profile)}
<div class="two-col">
  <div class="panel"><h2>{escape(profile["stat_title"])}</h2>{_table(profile["stat_headers"], rows)}</div>
  <div class="panel"><h2>风险趋势</h2>{_mini_chart(profile)}{_focus_panel(profile, compact=True)}</div>
</div>
"""
    if variant == "map":
        return f"""
<div class="dashboard-split">
  <div class="panel"><h2>区域态势</h2>{_map_board(profile, blueprint.modules)}</div>
  <div class="panel"><h2>{escape(profile["stat_title"])}</h2>{_table(profile["stat_headers"], rows)}</div>
</div>
<div class="panel"><h2>区域趋势</h2>{_mini_chart(profile)}<div class="process">{_process(profile)}</div></div>
"""
    if variant == "pipeline":
        return f"""
{_pipeline_cards(profile)}
<div class="two-col">
  <div class="panel"><h2>{escape(profile["stat_title"])}</h2>{_table(profile["stat_headers"], rows)}</div>
  <div class="panel"><h2>链路趋势</h2>{_mini_chart(profile)}<div class="process">{_process(profile)}</div></div>
</div>
"""
    if variant == "workflow":
        return f"""
<div class="grid">{_metric_cards(profile["metrics"])}</div>
<div class="two-col">
  <div class="panel"><h2>{escape(profile["stat_title"])}</h2>{_table(profile["stat_headers"], rows)}</div>
  <div class="panel"><h2>流程完成趋势</h2>{_timeline(profile)}</div>
</div>
"""
    if variant == "command":
        return f"""
<div class="command-strip">{_metric_cards(profile["metrics"])}</div>
<div class="command-grid">
  <div class="panel command-main"><h2>{escape(profile["stat_title"])}</h2>{_mini_chart(profile)}<div class="process">{_process(profile)}</div></div>
  <div class="panel"><h2>统计明细</h2>{_table(profile["stat_headers"], rows)}</div>
  <div class="panel"><h2>重点指标</h2>{_focus_panel(profile, compact=True)}</div>
</div>
"""
    if variant == "kanban":
        return f"""
<div class="panel"><h2>{escape(profile["stat_title"])}看板</h2>{_kanban_board(profile, blueprint.modules)}</div>
<div class="dashboard-split">
  <div class="panel"><h2>统计明细</h2>{_table(profile["stat_headers"], rows)}</div>
  <div class="panel"><h2>趋势分析</h2>{_mini_chart(profile)}</div>
</div>
"""
    if variant == "matrix":
        return f"""
<div class="matrix-layout">
  <div class="panel matrix-main"><h2>{escape(profile["stat_title"])}</h2>{_matrix_board(profile, blueprint.modules)}</div>
  <div class="panel"><h2>统计明细</h2>{_table(profile["stat_headers"], rows)}</div>
  <div class="panel"><h2>趋势分析</h2>{_mini_chart(profile)}</div>
</div>
"""
    return f"""
<div class="grid">{_metric_cards(profile["metrics"])}</div>
<div class="two-col">
  <div class="panel"><h2>{escape(profile["stat_title"])}</h2>{_table(profile["stat_headers"], rows)}</div>
  <div class="panel"><h2>趋势分析</h2>{_mini_chart(profile)}<div class="process">{_process(profile)}</div></div>
</div>
"""


def _dashboard_shape_content(profile: dict[str, Any], blueprint: ProductBlueprint) -> str:
    shape = str(profile.get("workspace_shape") or "")
    if shape == "freeform_grid":
        return _freeform_structure_content(profile, blueprint, "dashboard")
    if shape == "triage_console":
        return f"""
<div class="shape-triage">
  <section class="panel"><h2>{escape(profile["todo_title"])}</h2>{_triage_stack(profile, blueprint.modules)}</section>
  <section class="panel"><h2>{escape(profile["dashboard_pattern"])}</h2>{_table(profile["table_headers"], _domain_rows(blueprint.modules, profile, 8))}</section>
  <section class="panel"><h2>{escape(profile["focus_title"])}</h2>{_focus_panel(profile, compact=True)}{_mini_chart(profile)}</section>
</div>
"""
    if shape == "ledger_split":
        return f"""
<div class="shape-ledger">
  <div class="ledger-toolbar">{_ledger_boxes(profile)}</div>
  <section class="panel"><h2>{escape(profile["dashboard_pattern"])}</h2>{_table(profile["table_headers"], _domain_rows(blueprint.modules, profile, 9))}</section>
  <section class="panel"><h2>{escape(profile["focus_title"])}</h2>{_focus_panel(profile)}<div class="process">{_process(profile)}</div></section>
</div>
"""
    if shape == "monitor_wall":
        return f"""
<div class="shape-wall">
  <section class="panel wall-wide"><h2>{escape(profile["dashboard_pattern"])}</h2>{_mini_chart(profile)}</section>
  <section class="panel wall-wide"><h2>{escape(profile["todo_title"])}</h2>{_queue_list(profile, blueprint.modules, 5)}</section>
  <section class="panel">{_focus_panel(profile, compact=True)}</section>
  <section class="panel wall-full"><h2>{escape(profile["module_focus_title"])}</h2>{_timeline(profile)}</section>
</div>
"""
    if shape == "process_lane":
        return f"""
<div class="shape-lane">
  <div class="lane-strip">{_lane_steps(profile)}</div>
  <section class="panel"><h2>{escape(profile["todo_title"])}</h2>{_queue_list(profile, blueprint.modules, 6)}</section>
  <section class="panel"><h2>{escape(profile["focus_title"])}</h2>{_mini_chart(profile)}</section>
</div>
"""
    if shape == "case_desk":
        return f"""
<div class="shape-case">
  <section class="panel"><h2>业务档案</h2>{_case_cards(profile)}</section>
  <section class="panel"><h2>{escape(profile["dashboard_pattern"])}</h2>{_table(profile["table_headers"], _domain_rows(blueprint.modules, profile, 8))}</section>
  <section class="panel"><h2>{escape(profile["module_focus_title"])}</h2>{_timeline(profile)}</section>
</div>
"""
    if shape == "board_columns":
        return f"""
<div class="shape-board">
  <section class="panel"><h2>{escape(profile["dashboard_pattern"])}</h2>{_kanban_board(profile, blueprint.modules)}</section>
  <aside class="board-side">
    <section class="panel"><h2>{escape(profile["focus_title"])}</h2>{_focus_panel(profile, compact=True)}</section>
    <section class="panel"><h2>趋势</h2>{_mini_chart(profile)}</section>
  </aside>
</div>
"""
    return ""


def _module_shape_content(profile: dict[str, Any], blueprint: ProductBlueprint, module: FeatureModule, filters: str) -> str:
    shape = str(profile.get("workspace_shape") or "")
    if shape == "freeform_grid":
        return _freeform_structure_content(profile, blueprint, "module", module=module, filters=filters)
    if shape == "triage_console":
        return f"""
<div class="shape-triage">
  <section class="panel"><h2>{escape(module.title)}待处理</h2>{_triage_stack(profile, [module] + blueprint.modules[:5])}</section>
  <section class="panel"><div class="toolbar">{filters}<span class="button">复核</span><span class="button">分派</span></div>{_table(profile["table_headers"], _module_rows(module, profile))}</section>
  <section class="panel"><h2>处置依据</h2>{_focus_panel(profile, compact=True)}{_timeline(profile)}</section>
</div>
"""
    if shape == "ledger_split":
        return f"""
<div class="shape-ledger">
  <div class="ledger-toolbar">{_ledger_boxes(profile)}</div>
  <section class="panel"><div class="toolbar">{filters}<span class="button">查询</span><span class="button">导出</span></div>{_table(profile["table_headers"], _module_rows(module, profile))}</section>
  <section class="panel"><h2>{escape(module.title)}详情</h2>{_case_cards(profile)}<p class="muted">{escape(module.description)}</p></section>
</div>
"""
    if shape == "monitor_wall":
        return f"""
<div class="shape-wall">
  <section class="panel wall-wide"><h2>{escape(module.title)}监控</h2>{_mini_chart(profile)}</section>
  <section class="panel wall-wide"><h2>实时队列</h2>{_queue_list(profile, [module] + blueprint.modules[:5], 5)}</section>
  <section class="panel wall-full"><div class="toolbar">{filters}<span class="button">处置</span><span class="button">联动</span></div>{_table(profile["table_headers"], _module_rows(module, profile))}</section>
</div>
"""
    if shape == "process_lane":
        return f"""
<div class="shape-lane">
  <div class="lane-strip">{_lane_steps(profile)}</div>
  <section class="panel"><div class="toolbar">{filters}<span class="button">提交</span><span class="button">审核</span></div>{_table(profile["table_headers"], _module_rows(module, profile))}</section>
  <section class="panel"><h2>{escape(module.title)}说明</h2><p class="muted">{escape(module.description)}</p></section>
</div>
"""
    if shape == "case_desk":
        return f"""
<div class="shape-case">
  <section class="panel"><h2>{escape(module.title)}档案</h2>{_case_cards(profile)}</section>
  <section class="panel"><div class="toolbar">{filters}<span class="button">保存</span><span class="button">流转</span></div>{_table(profile["table_headers"], _module_rows(module, profile))}</section>
  <section class="panel"><h2>规则与流转</h2>{_timeline(profile)}{_focus_panel(profile, compact=True)}</section>
</div>
"""
    if shape == "board_columns":
        return f"""
<div class="shape-board">
  <section class="panel"><h2>{escape(module.title)}看板</h2>{_kanban_board(profile, [module] + blueprint.modules[:5])}</section>
  <aside class="board-side">
    <section class="panel"><div class="toolbar">{filters}<span class="button">新增</span></div>{_queue_list(profile, [module] + blueprint.modules[:5], 4)}</section>
    <section class="panel"><h2>模块指标</h2>{_focus_panel(profile, compact=True)}</section>
  </aside>
</div>
"""
    return ""


def _statistics_shape_content(profile: dict[str, Any], blueprint: ProductBlueprint, rows: list[list[str]]) -> str:
    shape = str(profile.get("workspace_shape") or "")
    if shape == "freeform_grid":
        return _freeform_structure_content(profile, blueprint, "statistics", rows=rows)
    if shape == "monitor_wall":
        return f"""
<div class="shape-wall">
  <section class="panel wall-wide"><h2>{escape(profile["stat_title"])}</h2>{_mini_chart(profile)}</section>
  <section class="panel wall-wide"><h2>统计明细</h2>{_table(profile["stat_headers"], rows)}</section>
  <section class="panel wall-full"><h2>流程状态</h2>{_timeline(profile)}</section>
</div>
"""
    if shape in {"triage_console", "case_desk"}:
        return f"""
<div class="shape-case">
  <section class="panel"><h2>统计对象</h2>{_case_cards(profile)}</section>
  <section class="panel"><h2>{escape(profile["stat_title"])}</h2>{_table(profile["stat_headers"], rows)}</section>
  <section class="panel"><h2>趋势分析</h2>{_mini_chart(profile)}{_focus_panel(profile, compact=True)}</section>
</div>
"""
    if shape == "process_lane":
        return f"""
<div class="shape-lane">
  <div class="lane-strip">{_lane_steps(profile)}</div>
  <section class="panel"><h2>{escape(profile["stat_title"])}</h2>{_table(profile["stat_headers"], rows)}</section>
</div>
"""
    if shape == "board_columns":
        return f"""
<div class="shape-board">
  <section class="panel"><h2>{escape(profile["stat_title"])}</h2>{_kanban_board(profile, blueprint.modules)}</section>
  <aside class="board-side"><section class="panel">{_table(profile["stat_headers"], rows)}</section><section class="panel">{_mini_chart(profile)}</section></aside>
</div>
"""
    if shape == "ledger_split":
        return f"""
<div class="shape-ledger">
  <div class="ledger-toolbar">{_ledger_boxes(profile)}</div>
  <section class="panel"><h2>{escape(profile["stat_title"])}</h2>{_table(profile["stat_headers"], rows)}</section>
  <section class="panel"><h2>趋势分析</h2>{_mini_chart(profile)}<div class="process">{_process(profile)}</div></section>
</div>
"""
    return ""


def _freeform_structure_content(
    profile: dict[str, Any],
    blueprint: ProductBlueprint,
    page_kind: str,
    module: FeatureModule | None = None,
    rows: list[list[str]] | None = None,
    filters: str = "",
) -> str:
    structure = dict(profile.get("structure_blueprint") or {})
    page = dict(structure.get(page_kind) or {})
    slots = list(page.get("slots") or [])
    if not slots:
        return ""
    layout = str(page.get("layout") or "asymmetric_grid")
    rendered = []
    for index, slot in enumerate(slots):
        rendered.append(_render_structure_slot(profile, blueprint, page_kind, slot, index, module=module, rows=rows, filters=filters))
    return f"<div class='freeform-grid freeform-{escape(layout)}'>{''.join(rendered)}</div>"


def _render_structure_slot(
    profile: dict[str, Any],
    blueprint: ProductBlueprint,
    page_kind: str,
    slot: dict[str, Any],
    index: int,
    module: FeatureModule | None = None,
    rows: list[list[str]] | None = None,
    filters: str = "",
) -> str:
    kind = str(slot.get("kind") or "focus")
    title = str(slot.get("title") or "业务区域")
    span = _slot_span(slot.get("span"), index)
    modules = ([module] + blueprint.modules[:5]) if module else blueprint.modules
    table_rows = rows or (_module_rows(module, profile) if module else _domain_rows(blueprint.modules, profile, 7))
    if kind == "metrics":
        body = f"<div class='grid'>{_metric_cards(profile['metrics'])}</div>"
    elif kind == "queue":
        body = _queue_list(profile, modules, 6)
    elif kind == "table":
        headers = profile["stat_headers"] if page_kind == "statistics" else profile["table_headers"]
        toolbar = f"<div class='toolbar'>{filters}<span class='button'>处理</span></div>" if filters else ""
        body = f"{toolbar}{_table(headers, table_rows)}"
    elif kind == "chart":
        body = f"{_mini_chart(profile)}<div class='process'>{_process(profile)}</div>"
    elif kind == "timeline":
        body = _timeline(profile)
    elif kind == "map":
        body = _map_board(profile, modules)
    elif kind == "matrix":
        body = _matrix_board(profile, modules)
    elif kind == "ledger":
        body = f"<div class='ledger-toolbar'>{_ledger_boxes(profile)}</div>{_table(profile['table_headers'], table_rows[:5])}"
    elif kind == "kanban":
        body = _kanban_board(profile, modules)
    elif kind == "case":
        body = _case_cards(profile)
    else:
        body = _focus_panel(profile, compact=span <= 4)
    return f"<section class='panel freeform-slot freeform-slot-{escape(kind)}' style='grid-column: span {span};'><h2>{escape(title)}</h2>{body}</section>"


def _slot_span(value: Any, index: int) -> int:
    try:
        span = int(value)
    except Exception:
        span = [8, 4, 6, 6, 4, 4][index % 6]
    return max(3, min(12, span))


def _layout(task: GenerationTask, blueprint: ProductBlueprint, title: str, content: str, active: str, design_brief: dict[str, Any] | None = None) -> str:
    profile = _profile_for_blueprint(task, blueprint, design_brief)
    nav = ["系统首页"] + [module.title for module in blueprint.modules[:8]] + ["统计报表页", "系统设置页"]
    nav_html = "".join(f"<span class='{'active' if item == active else ''}'>{escape(item)}</span>" for item in nav)
    variant = str(profile.get("layout_variant") or "classic")
    nav_model = str(profile.get("nav_model") or "side_menu")
    workspace_shape = str(profile.get("workspace_shape") or "")
    app_class = f"{variant} nav-{nav_model}"
    if workspace_shape:
        app_class = f"{app_class} shape-{workspace_shape}"
    if nav_model == "top_tabs":
        return f"""
<div class="app {escape(app_class)}" style="--accent:{profile['accent']};--accent-soft:{profile['accent_soft']};--sidebar:{profile['sidebar']};">
  <header class="topbar">
    <div><div class="brand">{escape(task.software_name)}</div><div class="muted">{escape(task.version)} / {escape(task.product_type)} / {escape(str(profile.get("industry_subtype") or ""))}</div></div>
    <nav class="nav">{nav_html}</nav>
    <div class="muted">{escape(profile["user_label"])}</div>
  </header>
  <main class="main">
    <div class="top"><div><div class="title">{escape(title)}</div><div class="muted">{escape(str(profile.get("dashboard_pattern") or profile.get("visual_mood") or ""))}</div></div><div class="muted">{escape(profile["user_label"])}</div></div>
    {content}
  </main>
</div>"""
    return f"""
<div class="app {escape(app_class)}" style="--accent:{profile['accent']};--accent-soft:{profile['accent_soft']};--sidebar:{profile['sidebar']};">
  <aside class="sidebar">
    <div class="brand">{escape(task.software_name)}</div>
    <div class="sidebar-subtitle">{escape(str(profile.get("industry_subtype") or task.product_type))}</div>
    <nav class="nav">{nav_html}</nav>
  </aside>
  <main class="main">
    <div class="top"><div><div class="title">{escape(title)}</div><div class="muted">{escape(task.version)} / {escape(task.product_type)} / {escape(str(profile.get("visual_mood") or ""))}</div></div><div class="muted">{escape(profile["user_label"])}</div></div>
    {content}
  </main>
</div>"""


def _profile_for_blueprint(task: GenerationTask, blueprint: ProductBlueprint, design_brief: dict[str, Any] | None = None) -> dict[str, Any]:
    profile = _admin_profile(task)
    brief = design_brief or {}
    if brief:
        for key in ["accent", "accent_soft", "sidebar"]:
            if brief.get(key):
                profile[key] = str(brief[key])
        if brief.get("layout_family"):
            profile["layout_variant"] = str(brief["layout_family"])
        if brief.get("nav_model"):
            profile["nav_model"] = str(brief["nav_model"])
        if brief.get("workspace_shape"):
            profile["workspace_shape"] = str(brief["workspace_shape"])
        if brief.get("login_pattern"):
            profile["login_pattern"] = str(brief["login_pattern"])
        if brief.get("structure_blueprint"):
            profile["structure_blueprint"] = dict(brief.get("structure_blueprint") or {})
        if brief.get("semantic_terms"):
            profile["semantic_terms"] = [str(item) for item in list(brief.get("semantic_terms") or []) if str(item).strip()]
        if brief.get("optimized_prompt"):
            profile["optimized_prompt"] = str(brief.get("optimized_prompt") or "")
        profile["industry_subtype"] = str(brief.get("industry_subtype") or getattr(blueprint, "industry_subtype", ""))
        profile["visual_mood"] = str(brief.get("visual_mood") or "")
        profile["dashboard_pattern"] = str(brief.get("dashboard_pattern") or "")
        profile["module_pattern"] = str(brief.get("module_pattern") or "")
        if brief.get("domain_terms"):
            terms = [str(item) for item in list(brief.get("domain_terms") or []) if str(item).strip()]
            if terms:
                profile["subjects"] = terms[:6]
                profile["objects"] = (terms[3:9] or terms)[:6]
        if brief.get("metrics"):
            metrics = [str(item) for item in list(brief.get("metrics") or []) if str(item).strip()]
            if metrics:
                profile["metrics"] = [(metric, _metric_value(index)) for index, metric in enumerate(metrics[:4])]
                profile["stat_subjects"] = metrics[:6]
                profile["stat_title"] = str(brief.get("dashboard_pattern") or "产品指标统计")
    if blueprint.target_users:
        profile["user_label"] = f"当前用户：{blueprint.target_users[0]}"
    if blueprint.business_objects:
        profile["subjects"] = blueprint.business_objects[:6]
        profile["objects"] = (blueprint.business_objects[3:9] or blueprint.business_objects)[:6]
    if blueprint.report_metrics:
        profile["metrics"] = [(metric, _metric_value(index)) for index, metric in enumerate(blueprint.report_metrics[:4])]
        profile["stat_subjects"] = blueprint.report_metrics[:6]
        profile["stat_title"] = "产品指标统计"
    else:
        profile["stat_subjects"] = [module.title for module in blueprint.modules[:6]]
    if blueprint.workflows:
        workflow = blueprint.workflows[0]
        if isinstance(workflow, dict):
            steps = workflow.get("steps")
            if isinstance(steps, list) and steps:
                profile["process"] = [str(step) for step in steps[:6]]
            name = str(workflow.get("name") or "")
            if name:
                profile["module_focus_title"] = name
    if blueprint.quality_rules:
        focus_cards = []
        for index, rule in enumerate(blueprint.quality_rules[:4]):
            label = f"规则{index + 1}"
            value = "已启用"
            focus_cards.append((label, value, str(rule)))
        if focus_cards:
            profile["focus_cards"] = focus_cards
            profile["focus_title"] = "方案规则看板"
    actions = _business_actions_from_modules(blueprint.modules)
    if actions:
        profile["actions"] = actions
    return profile


def _business_actions_from_modules(modules: list[FeatureModule]) -> list[str]:
    actions: list[str] = []
    for module in modules:
        operations = [_operation_label(operation) for operation in module.operations if operation]
        operations = [operation for operation in operations if operation]
        if not operations:
            continue
        parts = operations[:2]
        if not any("导出" in operation for operation in parts):
            parts.append("导出")
        actions.append(" / ".join(parts[:3]))
    return actions[:6]


def _operation_label(value: str) -> str:
    text = str(value).strip()
    match = re.search(r"['\"](?:name|title|operation|label|value)['\"]\s*:\s*['\"]([^'\"]+)['\"]", text)
    if match:
        return match.group(1).strip()
    if text.startswith("{") and text.endswith("}"):
        return ""
    return text


def _triage_stack(profile: dict[str, Any], modules: list[FeatureModule]) -> str:
    items = []
    states = list(profile.get("states") or ["待处理", "处理中", "已完成"])
    for index, module in enumerate((modules or [])[:6]):
        state = states[index % len(states)]
        items.append(
            f"<div class='triage-item'><strong>{escape(module.title)}</strong><span>{escape(state)} / {escape(_metric_value(index))}</span></div>"
        )
    if not items:
        items.append("<div class='triage-item'><strong>暂无待处理事项</strong><span>0</span></div>")
    return f"<div class='triage-stack'>{''.join(items)}</div>"


def _ledger_boxes(profile: dict[str, Any]) -> str:
    metrics = list(profile.get("metrics") or [])[:5]
    return "".join(
        f"<div class='ledger-box'><span>{escape(label)}</span><strong>{escape(value)}</strong></div>"
        for label, value in metrics
    )


def _lane_steps(profile: dict[str, Any]) -> str:
    steps = list(profile.get("process") or ["提交", "校验", "审核", "归档"])[:5]
    return "".join(
        f"<div class='lane-step'><b>{index + 1:02d}</b><strong>{escape(str(step))}</strong><span>{escape(_pipeline_detail(profile, None, index))}</span></div>"
        for index, step in enumerate(steps)
    )


def _case_cards(profile: dict[str, Any]) -> str:
    subjects = list(profile.get("subjects") or [])[:4]
    states = list(profile.get("states") or ["正常", "待处理", "已归档"])
    cards = []
    for index, subject in enumerate(subjects):
        cards.append(
            f"<div class='case-card'><span>{escape(str(subject))}</span><strong>{escape(_metric_value(index))}</strong><small>{escape(states[index % len(states)])}</small></div>"
        )
    return "".join(cards)


def _kanban_board(profile: dict[str, Any], modules: list[FeatureModule]) -> str:
    stages = list(profile.get("process") or ["待处理", "处理中", "待审核", "已完成"])[:4]
    cards: list[str] = []
    source_modules = modules or []
    for stage_index, stage in enumerate(stages):
        items = []
        for item_index, module in enumerate(source_modules[stage_index:: max(1, len(stages))][:3]):
            status = profile["states"][(stage_index + item_index) % len(profile["states"])]
            items.append(
                f"<div class='kanban-card'><strong>{escape(module.title)}</strong><span>{escape(module.description)}</span><small>{escape(status)} · {escape(_metric_value(stage_index + item_index))}</small></div>"
            )
        if not items:
            items.append(f"<div class='kanban-card'><strong>{escape(stage)}任务</strong><span>暂无新的处理事项</span><small>0</small></div>")
        cards.append(f"<div class='kanban-col'><h3>{escape(str(stage))}</h3>{''.join(items)}</div>")
    return f"<div class='kanban-board'>{''.join(cards)}</div>"


def _matrix_board(profile: dict[str, Any], modules: list[FeatureModule]) -> str:
    subjects = list(profile.get("subjects") or [])
    modules = modules or []
    cells = []
    for index in range(9):
        module = modules[index % len(modules)] if modules else None
        label = subjects[index % len(subjects)] if subjects else (module.title if module else f"业务项{index + 1}")
        value = _metric_value(index)
        state = profile["states"][index % len(profile["states"])]
        cells.append(
            f"<div class='matrix-cell'><span>{escape(label)}</span><strong>{escape(value)}</strong><small>{escape(module.title if module else state)} · {escape(state)}</small></div>"
        )
    return f"<div class='matrix-board'>{''.join(cells)}</div>"


def _metric_value(index: int) -> str:
    values = ["1,286", "86.4%", "72", "98.7%", "3.2万", "12.6万"]
    return values[index % len(values)]


def _table(headers: Iterable[str], rows: Iterable[Iterable[str]]) -> str:
    head = "".join(f"<th>{escape(str(item))}</th>" for item in headers)
    body = "".join("<tr>" + "".join(_cell(value) for value in row) + "</tr>" for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _cell(value: str) -> str:
    text = escape(str(value))
    warn_values = {"高风险", "待处置", "质量预警", "漂移预警", "告警中", "库存预警", "资源告警", "边缘告警"}
    status_values = {"正常", "已归档", "待处理", "进行中", "待批改", "已完成", "待跟进", "待复核", "已结算", "待分诊", "诊疗中", "待审核", "已发布", "采集中", "已同步", "在线", "待巡检", "已接入", "已修复", "已审计", "运行中", "待校验", "已入仓", "训练中", "已上线", "待支付", "已退款", "体验中", "待校准", "已激活", "待维护", "已预约", "已核销", "已核验"}
    if text in warn_values:
        return f"<td><span class='status warn'>{text}</span></td>"
    if text in status_values:
        return f"<td><span class='status'>{text}</span></td>"
    return f"<td>{text}</td>"


def _metric_cards(metrics: list[tuple[str, str]]) -> str:
    return "".join(f"<div class='card metric'><span>{escape(label)}</span><strong>{escape(value)}</strong></div>" for label, value in metrics[:4])


def _risk_tiles(profile: dict[str, Any]) -> str:
    cards = list(profile["metrics"][:2]) + [(label, value) for label, value, _desc in profile["focus_cards"][:2]]
    html = "".join(
        f"<div class='risk-tile'><span>{escape(label)}</span><strong>{escape(value)}</strong><small>{escape(_risk_hint(index, profile))}</small></div>"
        for index, (label, value) in enumerate(cards[:4])
    )
    return f"<div class='risk-strip'>{html}</div>"


def _risk_hint(index: int, profile: dict[str, Any]) -> str:
    hints = ["实时监测", "待复核队列", "规则命中", str(profile.get("stat_status", "已归档"))]
    return hints[index % len(hints)]


def _filter_toolbar(profile: dict[str, Any]) -> str:
    return "".join(f"<span class='input'>{escape(label)}</span>" for label in profile["filters"])


def _quick_buttons(modules: list[FeatureModule]) -> str:
    return "".join(f"<span class='button'>{escape(module.title)}</span>" for module in modules[:4])


def _queue_list(profile: dict[str, Any], modules: list[FeatureModule], count: int) -> str:
    rows = _domain_rows(modules, profile, count)
    items = []
    for index, row in enumerate(rows, start=1):
        title = row[0]
        detail = f"{row[1]} / {row[3]}"
        state = row[2]
        badge_class = "status warn" if state in {"高风险", "待处置", "质量预警", "漂移预警", "告警中", "库存预警", "资源告警", "边缘告警"} else "status"
        items.append(
            f"<div class='queue-item'><div><strong>{escape(title)}</strong><small>{escape(detail)}</small></div>"
            f"<span class='{badge_class}'>{escape(state)}</span></div>"
        )
    return f"<div class='queue-list'>{''.join(items)}</div>"


def _map_board(profile: dict[str, Any], modules: list[FeatureModule]) -> str:
    labels = [module.title for module in modules[:5]] or list(profile["subjects"][:5])
    positions = [(10, 18), (56, 12), (72, 42), (28, 58), (48, 73)]
    pins = []
    for index, label in enumerate(labels[:5]):
        x, y = positions[index % len(positions)]
        state = profile["states"][index % len(profile["states"])]
        pins.append(
            f"<div class='map-pin' style='left:{x}%;top:{y}%'>{escape(label)}<small>{escape(state)}</small></div>"
        )
    return f"<div class='map-board'>{''.join(pins)}</div>"


def _pipeline_cards(profile: dict[str, Any], module: FeatureModule | None = None) -> str:
    process = list(profile["process"][:4])
    while len(process) < 4:
        process.append(f"阶段{len(process) + 1}")
    values = [value for _label, value in profile["metrics"][:4]]
    html = "".join(
        f"<div class='pipeline-card'><span>{escape(step)}</span><strong>{escape(values[index % len(values)])}</strong><small>{escape(_pipeline_detail(profile, module, index))}</small></div>"
        for index, step in enumerate(process[:4])
    )
    return f"<div class='pipeline-grid'>{html}</div>"


def _pipeline_detail(profile: dict[str, Any], module: FeatureModule | None, index: int) -> str:
    if module and index == 0:
        return module.title
    subjects = profile["subjects"]
    return subjects[index % len(subjects)]


def _timeline(profile: dict[str, Any]) -> str:
    steps = list(profile["process"][:5])
    cards = list(profile["focus_cards"])
    items = []
    for index, step in enumerate(steps, start=1):
        label, value, desc = cards[(index - 1) % len(cards)]
        items.append(
            f"<div class='timeline-step' data-step='{index}'><strong>{escape(step)} / {escape(label)}：{escape(value)}</strong>"
            f"<small>{escape(desc)}</small></div>"
        )
    return f"<div class='timeline'>{''.join(items)}</div>"


def _stat_rows(profile: dict[str, Any]) -> list[list[str]]:
    return [
        [metric, f"{index * 238}", f"{88 + index % 9}%", profile["stat_status"]]
        for index, metric in enumerate(profile["stat_subjects"][:6], start=1)
    ]


def _domain_rows(modules: list[FeatureModule], profile: dict[str, Any], count: int) -> list[list[str]]:
    rows: list[list[str]] = []
    modules = modules or [FeatureModule("business", "业务模块", "业务处理", ["BusinessRecord"])]
    for index in range(count):
        module = modules[index % len(modules)]
        rows.append(
            [
                f"{profile['subjects'][index % len(profile['subjects'])]}{index + 1:03d}",
                profile["objects"][index % len(profile["objects"])],
                profile["states"][index % len(profile["states"])],
                profile["actions"][index % len(profile["actions"])],
            ]
        )
        if module.title and index % 2 == 1:
            rows[-1][1] = module.title
    return rows


def _module_rows(module: FeatureModule, profile: dict[str, Any]) -> list[list[str]]:
    rows: list[list[str]] = []
    entities = module.entities or ["BusinessRecord", "BusinessQuery"]
    for index in range(6):
        entity = entities[index % len(entities)]
        rows.append(
            [
                f"{module.title}{index + 1:03d}",
                _business_object_label(entity, profile, index),
                profile["states"][(index + 1) % len(profile["states"])],
                profile["actions"][index % len(profile["actions"])],
            ]
        )
    return rows


def _business_object_label(entity: str, profile: dict[str, Any], index: int) -> str:
    if entity and any("\u4e00" <= char <= "\u9fff" for char in entity):
        return entity
    return profile["objects"][index % len(profile["objects"])]


def _focus_panel(profile: dict[str, Any], compact: bool = False) -> str:
    cards = profile["focus_cards"][:2 if compact else 4]
    return "<div class='focus-grid'>" + "".join(
        f"<div class='focus-card'><span>{escape(label)}</span><strong>{escape(value)}</strong><small>{escape(desc)}</small></div>"
        for label, value, desc in cards
    ) + "</div>"


def _process(profile: dict[str, Any]) -> str:
    return "".join(f"<span>{escape(item)}</span>" for item in profile["process"])


def _mini_chart(profile: dict[str, Any]) -> str:
    return "<div class='mini-chart'>" + "".join(f"<span class='bar' style='height:{int(value)}%'></span>" for value in profile["chart_values"]) + "</div>"


def _gems(count: int) -> str:
    classes = ["a", "b", "c", "d", "e", "f"]
    return "".join(f"<span class='gem {classes[index % len(classes)]}'></span>" for index in range(count))


def _level_nodes() -> str:
    points = [(54, 420), (142, 355), (245, 405), (345, 305), (448, 350), (532, 245), (470, 135), (340, 190)]
    return "".join(
        f"<div class='level-node' style='left:{x}px;top:{y}px'>{index}</div>"
        for index, (x, y) in enumerate(points, start=29)
    )


def _to_map(items: list[UiScreenshot]) -> dict[str, UiScreenshot]:
    return {item.key: item for item in items}


def _render_fallback_images(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    screenshots: list[UiScreenshot],
    ui_dir: Path,
) -> None:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return

    font_regular = _font(ImageFont, 18)
    font_small = _font(ImageFont, 14)
    font_title = _font(ImageFont, 28)
    font_metric = _font(ImageFont, 32)

    for item in screenshots:
        path = ui_dir / f"{item.key}.png"
        game = is_game_like(task, blueprint)
        image_size = (GAME_VIEWPORT["width"], GAME_VIEWPORT["height"]) if game else (ADMIN_VIEWPORT["width"], ADMIN_VIEWPORT["height"])
        image = Image.new("RGB", image_size, "#eef2f6")
        draw = ImageDraw.Draw(image)
        if game:
            _draw_game_phone_page(draw, task, blueprint, item, font_title, font_regular, font_small, font_metric)
        elif item.key == "login":
            _draw_login(draw, task, blueprint, font_title, font_regular, font_small)
        else:
            _draw_app_page(draw, task, blueprint, item, font_title, font_regular, font_small, font_metric)
        image.save(path)
        item.image_path = str(path)
        item.width, item.height = image_size


def _font(ImageFont, size: int):
    candidates = [
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simsun.ttc",
        "C:/Windows/Fonts/simhei.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _draw_login(draw, task: GenerationTask, blueprint: ProductBlueprint, title_font, regular_font, small_font) -> None:
    draw.rectangle((0, 0, 790, 820), fill="#1f314f")
    draw.rectangle((790, 0, 1280, 820), fill="#ffffff")
    draw.text((72, 190), task.software_name, fill="#ffffff", font=title_font)
    draw.text((72, 245), _clip(blueprint.summary, 42), fill="#dbe8ff", font=regular_font)
    draw.text((72, 288), _clip(blueprint.industry, 36), fill="#9fc2ff", font=small_font)
    draw.text((850, 180), "系统登录", fill="#1f2937", font=title_font)
    fields = [("账号", "请输入用户名"), ("密码", "请输入密码"), ("验证码", "请输入图形验证码")]
    y = 250
    for label, placeholder in fields:
        draw.text((850, y), label, fill="#52637a", font=small_font)
        draw.rounded_rectangle((850, y + 28, 1190, y + 76), radius=8, outline="#ccd6e3", fill="#fbfdff")
        draw.text((866, y + 42), placeholder, fill="#64748b", font=regular_font)
        y += 96
    draw.rounded_rectangle((850, y + 12, 1190, y + 62), radius=8, fill="#2f6fed")
    draw.text((990, y + 27), "登录系统", fill="#ffffff", font=regular_font)


def _draw_app_page(draw, task: GenerationTask, blueprint: ProductBlueprint, item: UiScreenshot, title_font, regular_font, small_font, metric_font) -> None:
    draw.rectangle((0, 0, 220, 820), fill="#1f314f")
    draw.text((24, 30), _clip(task.software_name, 12), fill="#ffffff", font=regular_font)
    nav = ["系统首页"] + [module.title for module in blueprint.modules[:6]] + ["统计报表页", "系统设置页"]
    y = 90
    for nav_item in nav:
        active = nav_item in {item.title, "系统首页" if item.key == "dashboard" else "", "统计报表页" if item.key == "statistics" else ""}
        draw.rounded_rectangle((18, y, 202, y + 40), radius=7, fill="#2f6fed" if active else "#294260")
        draw.text((32, y + 10), _clip(nav_item, 12), fill="#ffffff", font=small_font)
        y += 48

    draw.rounded_rectangle((244, 24, 1254, 86), radius=8, outline="#dde5ef", fill="#ffffff")
    draw.text((266, 42), item.title, fill="#1f2937", font=title_font)
    draw.text((1030, 48), "当前用户：系统管理员", fill="#64748b", font=small_font)

    metrics = [("今日新增", "128"), ("待办审核", "36"), ("异常预警", "7"), ("本月处理", "2406")]
    for index, (label, value) in enumerate(metrics):
        x = 244 + index * 252
        draw.rounded_rectangle((x, 112, x + 230, 210), radius=8, outline="#dde5ef", fill="#ffffff")
        draw.text((x + 18, 132), label, fill="#64748b", font=small_font)
        draw.text((x + 18, 160), value, fill="#1f2937", font=metric_font)

    draw.rounded_rectangle((244, 236, 1254, 760), radius=8, outline="#dde5ef", fill="#ffffff")
    draw.text((266, 260), item.caption, fill="#52637a", font=regular_font)
    draw.rectangle((266, 310, 1232, 352), fill="#f8fafc")
    headers = ["业务名称", "所属模块", "状态", "操作"]
    for index, header in enumerate(headers):
        draw.text((286 + index * 230, 322), header, fill="#52637a", font=small_font)
    rows = blueprint.modules[:6] or []
    for row_index, module in enumerate(rows, start=1):
        y = 352 + row_index * 54
        draw.line((266, y - 10, 1232, y - 10), fill="#edf1f6")
        values = [f"{module.title}记录{row_index:03d}", module.title, "正常", "查看 / 编辑"]
        for col_index, value in enumerate(values):
            draw.text((286 + col_index * 230, y + 6), _clip(value, 16), fill="#1f2937", font=small_font)


def _draw_game_phone_page(draw, task: GenerationTask, blueprint: ProductBlueprint, item: UiScreenshot, title_font, regular_font, small_font, metric_font) -> None:
    draw.rectangle((0, 0, 720, 1280), fill="#69d8ff")
    draw.ellipse((-120, -80, 170, 210), fill="#b7fbce")
    draw.ellipse((480, 40, 820, 380), fill="#ffe27a")
    draw.ellipse((430, 900, 850, 1330), fill="#ff91c8")
    draw.rounded_rectangle((230, 12, 490, 36), radius=12, fill="#6c7ca3")
    draw.rounded_rectangle((28, 54, 692, 190), radius=32, fill="#ffffff")
    draw.text((56, 86), _clip(item.title, 15), fill="#263b72", font=title_font)
    for index, label in enumerate(["体力25/30", "金币12860", "第36关"]):
        x = 56 + index * 196
        draw.rounded_rectangle((x, 138, x + 168, 178), radius=18, fill="#eef6ff")
        draw.text((x + 16, 149), label, fill="#345083", font=small_font)

    title_text = item.title + item.caption
    if item.key in {"login", "dashboard"} or any(word in title_text for word in ["关卡", "地图"]):
        draw.rounded_rectangle((42, 224, 678, 800), radius=34, fill="#e8fff0")
        points = [(86, 666), (176, 592), (284, 640), (388, 520), (508, 574), (570, 424), (482, 312), (350, 374)]
        for index, (x, y) in enumerate(points, start=29):
            draw.ellipse((x, y, x + 78, y + 78), fill="#ffffff", outline="#facc15", width=7)
            draw.text((x + 24, y + 24), str(index), fill="#2563eb", font=regular_font)
        draw.rounded_rectangle((42, 830, 678, 1128), radius=34, fill="#ffffff")
        for index, (label, value) in enumerate([("当前关卡", "36"), ("星级进度", "86/120"), ("每日任务", "3/5")]):
            y = 866 + index * 72
            draw.text((80, y), label, fill="#41516f", font=regular_font)
            draw.text((535, y), value, fill="#2563eb", font=regular_font)
        draw.rounded_rectangle((72, 1060, 648, 1142), radius=30, fill="#f97316")
        draw.text((292, 1086), "开始游戏", fill="#ffffff", font=regular_font)
    elif any(word in title_text for word in ["道具", "背包", "资产"]):
        cards = [("彩虹球", "x6"), ("小木锤", "x12"), ("横向火箭", "x4"), ("金币礼包", "12860"), ("体力瓶", "x5"), ("限时门票", "x3")]
        for index, (label, value) in enumerate(cards):
            x = 42 + (index % 2) * 324
            y = 232 + (index // 2) * 176
            draw.rounded_rectangle((x, y, x + 288, y + 140), radius=28, fill="#ffffff")
            draw.text((x + 28, y + 28), label, fill="#27324f", font=regular_font)
            draw.text((x + 28, y + 80), value, fill="#f97316" if index == 1 else "#2563eb", font=metric_font)
        draw.rounded_rectangle((42, 820, 678, 1126), radius=34, fill="#ffffff")
        for index, line in enumerate(["通关奖励 +120 金币", "道具使用 -1 小木锤", "活动领取 +1 彩虹球"]):
            draw.text((78, 868 + index * 72), line, fill="#41516f", font=regular_font)
    elif any(word in title_text for word in ["统计", "结算", "星级"]):
        cards = [("最终得分", "18,640"), ("剩余步数", "6"), ("连消次数", "14"), ("最高连击", "7"), ("获得金币", "320"), ("星级评价", "★★★")]
        for index, (label, value) in enumerate(cards):
            x = 42 + (index % 2) * 324
            y = 232 + (index // 2) * 176
            draw.rounded_rectangle((x, y, x + 288, y + 140), radius=28, fill="#ffffff")
            draw.text((x + 28, y + 28), label, fill="#27324f", font=regular_font)
            draw.text((x + 28, y + 80), value, fill="#2563eb", font=metric_font)
        draw.rounded_rectangle((72, 1060, 648, 1142), radius=30, fill="#f97316")
        draw.text((318, 1086), "下一关", fill="#ffffff", font=regular_font)
    else:
        draw.rounded_rectangle((42, 224, 678, 876), radius=34, fill="#5749ec")
        colors = ["#fb7185", "#fbbf24", "#34d399", "#60a5fa", "#a78bfa", "#f472b6"]
        for row in range(8):
            for col in range(8):
                x = 88 + col * 70
                y = 270 + row * 70
                draw.rounded_rectangle((x, y, x + 58, y + 58), radius=18, fill=colors[(row * 3 + col * 2) % len(colors)])
        draw.rounded_rectangle((42, 906, 678, 1158), radius=34, fill="#ffffff")
        for index, (label, value) in enumerate([("红色方块", "18"), ("黄色星星", "12"), ("冰块障碍", "6")]):
            x = 72 + index * 204
            draw.rounded_rectangle((x, 942, x + 174, 1038), radius=24, fill="#f5fbff")
            draw.text((x + 26, 956), label, fill="#27324f", font=small_font)
            draw.text((x + 68, 988), value, fill="#315df4", font=regular_font)
        draw.rounded_rectangle((72, 1060, 648, 1142), radius=30, fill="#f97316")
        draw.text((260, 1086), "交换相邻棋子", fill="#ffffff", font=regular_font)


def _draw_game_page(draw, task: GenerationTask, blueprint: ProductBlueprint, item: UiScreenshot, title_font, regular_font, small_font, metric_font) -> None:
    draw.rectangle((0, 0, 1280, 820), fill="#8dd8ff")
    draw.rectangle((0, 360, 1280, 820), fill="#ffd6e8")
    draw.rounded_rectangle((50, 36, 1230, 784), radius=28, fill="#fff7df", outline="#ffffff", width=6)
    draw.rounded_rectangle((76, 62, 1204, 140), radius=18, fill="#ffffff")
    draw.text((106, 86), item.title, fill="#30436b", font=title_font)
    for index, label in enumerate(["体力 25/30", "金币 12,860", "第36关"]):
        x = 780 + index * 130
        draw.rounded_rectangle((x, 82, x + 116, 122), radius=18, fill="#eef6ff")
        draw.text((x + 14, 93), label, fill="#41516f", font=small_font)

    if item.key in {"login", "dashboard"} or any(word in item.title for word in ["关卡", "任务"]):
        _draw_level_map(draw, regular_font, small_font)
        draw.rounded_rectangle((850, 182, 1168, 642), radius=22, fill="#ffffff")
        labels = [("当前关卡", "36"), ("星级进度", "86/120"), ("目标分数", "12000"), ("限定步数", "24")]
        y = 220
        for label, value in labels:
            draw.rounded_rectangle((884, y, 1134, y + 58), radius=14, fill="#f8fafc")
            draw.text((904, y + 18), label, fill="#41516f", font=small_font)
            draw.text((1064, y + 13), value, fill="#2563eb", font=regular_font)
            y += 78
        draw.rounded_rectangle((884, 560, 1134, 620), radius=18, fill="#f97316")
        draw.text((968, 580), "开始游戏", fill="#ffffff", font=regular_font)
    elif any(word in item.title for word in ["统计", "结算", "匹配", "对战"]):
        cards = [("最终得分", "18,640"), ("剩余步数", "6"), ("最高连击", "7"), ("星级评价", "★★★"), ("获得金币", "320"), ("连消奖励", "+2140")]
        for index, (label, value) in enumerate(cards):
            x = 110 + (index % 3) * 250
            y = 190 + (index // 3) * 170
            draw.rounded_rectangle((x, y, x + 210, y + 130), radius=18, fill="#ffffff")
            draw.text((x + 22, y + 26), label, fill="#41516f", font=regular_font)
            draw.text((x + 22, y + 70), value, fill="#2563eb", font=metric_font)
        draw.rounded_rectangle((890, 190, 1138, 560), radius=20, fill="#ffffff")
        for index, line in enumerate(["基础分 12000", "步数奖励 +3600", "连消奖励 +2140", "道具加成 +900"]):
            draw.text((920, 230 + index * 70), line, fill="#41516f", font=regular_font)
    else:
        _draw_match_board(draw)
        draw.rounded_rectangle((850, 182, 1168, 642), radius=22, fill="#ffffff")
        for index, (label, value) in enumerate([("红色方块", "18"), ("黄色星星", "12"), ("冰块障碍", "6"), ("剩余步数", "18"), ("当前得分", "8420")]):
            y = 212 + index * 72
            draw.rounded_rectangle((884, y, 1134, y + 52), radius=14, fill="#f8fafc")
            draw.text((904, y + 15), label, fill="#41516f", font=small_font)
            draw.text((1068, y + 10), value, fill="#2563eb", font=regular_font)


def _draw_match_board(draw) -> None:
    colors = ["#fb7185", "#fbbf24", "#34d399", "#60a5fa", "#a78bfa", "#f472b6"]
    draw.rounded_rectangle((120, 182, 740, 720), radius=24, fill="#4f46e5")
    for row in range(8):
        for col in range(8):
            x = 166 + col * 66
            y = 216 + row * 60
            draw.rounded_rectangle((x, y, x + 48, y + 48), radius=14, fill=colors[(row * 3 + col * 2) % len(colors)])


def _draw_level_map(draw, regular_font, small_font) -> None:
    draw.rounded_rectangle((120, 182, 790, 642), radius=24, fill="#c7f9d4")
    points = [(170, 520), (260, 455), (360, 500), (465, 405), (570, 450), (650, 345), (720, 380)]
    for index, (x, y) in enumerate(points, start=30):
        draw.ellipse((x, y, x + 62, y + 62), fill="#ffffff", outline="#facc15", width=5)
        draw.text((x + 20, y + 19), str(index), fill="#2563eb", font=regular_font)


def _clip(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 1] + "…"
