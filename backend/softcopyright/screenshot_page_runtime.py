from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time
from typing import Any
import urllib.request


def start_project_server(source_info: dict | None) -> dict[str, Any]:
    if not isinstance(source_info, dict):
        raise RuntimeError("缺少源码项目信息")
    source_dir_raw = source_info.get("source_dir")
    project_entry = source_info.get("ui_project_entry")
    if not source_dir_raw or not isinstance(project_entry, dict):
        raise RuntimeError("缺少生成项目入口信息")
    route_mode = str(project_entry.get("route_mode") or "")
    source_dir = Path(str(source_dir_raw))
    default_port = port_from_url(str(project_entry.get("entry_url") or "")) or default_project_port(route_mode)
    port = select_port(default_port)
    base_url = f"http://127.0.0.1:{port}/ui-prototype"
    command = project_server_command(source_dir, route_mode, port)
    runtime_route_mode = str(command.get("route_mode") or route_mode)
    process = subprocess.Popen(
        command["args"],
        cwd=str(source_dir),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="ignore",
        env=command.get("env"),
    )
    try:
        wait_for_http(f"http://127.0.0.1:{port}/health", process, timeout_seconds=75)
    except Exception:
        stop_project_server({"process": process})
        raise
    source_info["ui_project_server_url"] = base_url
    source_info["ui_project_runtime_route_mode"] = runtime_route_mode
    source_info["ui_project_runtime_command"] = command["display"]
    return {
        "process": process,
        "base_url": base_url,
        "port": port,
        "route_mode": runtime_route_mode,
        "command": command["display"],
    }


def default_project_port(route_mode: str) -> int:
    return 5000 if route_mode == "aspnet-static" else 8080


def project_server_command(source_dir: Path, route_mode: str, port: int) -> dict[str, Any]:
    env = dict(os.environ)
    env["PORT"] = str(port)
    if route_mode == "aspnet-static":
        dotnet = shutil.which("dotnet")
        if dotnet:
            return {
                "args": [dotnet, "run", "--urls", f"http://127.0.0.1:{port}"],
                "env": env,
                "display": "dotnet run",
                "route_mode": "aspnet-static",
            }
        fallback = node_fallback_command(source_dir, port, env)
        if fallback:
            fallback["display"] = "node web-console/src/server.js（未安装 .NET 时使用生成项目备用入口）"
            return fallback
        raise RuntimeError("未找到 dotnet，且 C# 生成项目缺少零依赖 web-console 备用入口")
    if route_mode == "spring-static":
        mvn = shutil.which("mvn") or shutil.which("mvn.cmd")
        if mvn:
            return {
                "args": [mvn, "spring-boot:run", f"-Dspring-boot.run.arguments=--server.port={port}"],
                "env": env,
                "display": "mvn spring-boot:run",
                "route_mode": "spring-static",
            }
        fallback = node_fallback_command(source_dir, port, env)
        if fallback:
            fallback["display"] = "node web-console/src/server.js（未安装 Maven 时使用生成项目备用入口）"
            return fallback
        raise RuntimeError("未找到 Maven，且生成项目缺少 web-console/gateway-service 运行入口，无法启动 Java/Spring Boot 生成项目")
    if route_mode == "node-static" and (source_dir / "gateway-service" / "src" / "server.js").exists():
        command = project_server_command(source_dir / "gateway-service", "node-static", port)
        command["display"] = "node gateway-service/src/server.js"
        return command
    if route_mode == "node-static" and (source_dir / "web-console" / "src" / "server.js").exists():
        command = project_server_command(source_dir / "web-console", "node-static", port)
        command["display"] = "node web-console/src/server.js"
        return command
    if route_mode in {"node-static", "express-static"}:
        node, env = resolve_node_runtime(env)
        app_dir = source_dir
        server_path = app_dir / "src" / "server.js"
        if not server_path.exists():
            for folder in ("gateway-service", "web-console"):
                nested_server = source_dir / folder / "src" / "server.js"
                if nested_server.exists():
                    app_dir = source_dir / folder
                    server_path = nested_server
                    break
        ensure_node_dependencies(app_dir, allow_install=route_mode == "express-static")
        if not server_path.exists():
            raise RuntimeError("生成项目缺少 src/server.js")
        return {
            "args": [node, str(server_path.resolve())],
            "env": env,
            "display": "node src/server.js",
            "route_mode": "node-static",
        }
    if route_mode == "fastapi-static":
        python = sys.executable or shutil.which("python") or shutil.which("python.exe")
        if not python:
            raise RuntimeError("未找到 Python，无法启动 FastAPI 生成项目")
        if python_runtime_has_fastapi(python):
            module_name = "app.runtime_routes:app" if (source_dir / "app" / "runtime_routes.py").exists() else "app.main:app"
            return {
                "args": [python, "-m", "uvicorn", module_name, "--host", "127.0.0.1", "--port", str(port)],
                "env": env,
                "display": f"python -m uvicorn {module_name}",
                "route_mode": "fastapi-static",
            }
        fallback = node_fallback_command(source_dir, port, env)
        if fallback:
            fallback["display"] = "node web-console/src/server.js（包内 Python 缺少 FastAPI/Uvicorn 时使用生成项目备用入口）"
            return fallback
        raise RuntimeError("包内 Python 缺少 FastAPI/Uvicorn，且生成项目缺少零依赖 web-console 备用入口")
    raise RuntimeError(f"不支持的生成项目服务路由模式：{route_mode or 'unknown'}")


def python_runtime_has_fastapi(python: str) -> bool:
    try:
        result = subprocess.run(
            [python, "-c", "import fastapi, uvicorn"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def resolve_node_runtime(env: dict[str, str] | None = None) -> tuple[str, dict[str, str]]:
    child_env = dict(env or os.environ)
    electron_node = os.getenv("SOFT_ELECTRON_NODE", "").strip()
    node = electron_node or shutil.which("node") or shutil.which("node.exe")
    if not node:
        raise RuntimeError("未找到随软件提供的 Node 运行环境，无法启动 JavaScript/Express 生成项目")
    if electron_node and os.path.normcase(str(node)) == os.path.normcase(electron_node):
        child_env["ELECTRON_RUN_AS_NODE"] = "1"
    else:
        child_env.pop("ELECTRON_RUN_AS_NODE", None)
    return node, child_env


def node_fallback_command(source_dir: Path, port: int, env: dict[str, str]) -> dict[str, Any] | None:
    for folder in ("web-console", "gateway-service"):
        node_app = source_dir / folder
        if not (node_app / "src" / "server.js").exists():
            continue
        command = project_server_command(node_app, "node-static", port)
        command["env"].update({key: value for key, value in env.items() if key == "PORT"})
        return command
    return None


def ensure_node_dependencies(source_dir: Path, *, allow_install: bool = False) -> None:
    package_json = source_dir / "package.json"
    if not package_json.exists():
        return
    try:
        package_data = json.loads(package_json.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        package_data = {}
    dependencies = package_data.get("dependencies") if isinstance(package_data, dict) else {}
    if not dependencies:
        return
    if not allow_install:
        names = ", ".join(sorted(str(name) for name in dependencies.keys())[:6])
        raise RuntimeError(f"JavaScript generated project has third-party runtime dependencies; regenerate zero-dependency web-console: {names}")
    if all((source_dir / "node_modules" / str(name)).exists() for name in dependencies.keys()):
        return
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if not npm:
        raise RuntimeError("生成项目需要安装 npm 依赖，但未找到 npm")
    result = subprocess.run(
        [npm, "install", "--no-audit", "--no-fund"],
        cwd=str(source_dir),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="ignore",
        timeout=180,
    )
    if result.returncode != 0:
        detail = (result.stderr or "").strip().splitlines()[-1:] or ["npm install 失败"]
        raise RuntimeError(f"生成项目 npm 依赖安装失败：{detail[0]}")


def stop_project_server(server: dict[str, Any] | None) -> None:
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


def wait_for_http(url: str, process, timeout_seconds: int) -> None:
    deadline = time.time() + timeout_seconds
    last_error = ""
    while time.time() < deadline:
        if process.poll() is not None:
            detail = f"exit code {process.returncode}"
            raise RuntimeError(f"生成项目服务启动后立即退出：{detail}")
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if 200 <= response.status < 500:
                    return
        except Exception as exc:
            last_error = str(exc)
        time.sleep(1)
    raise RuntimeError(f"生成项目服务启动超时：{last_error}")


def verify_project_runtime(source_info: dict | None, source_evidence: dict[str, Any], base_url: str) -> None:
    if not isinstance(source_info, dict):
        raise RuntimeError("缺少源码项目信息，无法验证运行截图来源")
    root_url = base_url.rstrip("/").rsplit("/ui-prototype", 1)[0]
    health_url = f"{root_url}/health"
    health = http_probe_json(health_url)
    probes: list[dict[str, Any]] = [{"kind": "health", "url": health_url, "ok": True, "status": health["status"]}]
    modules = source_evidence.get("modules") if isinstance(source_evidence.get("modules"), dict) else {}
    module_keys = list(modules.keys())[:3] if isinstance(modules, dict) else []
    if not module_keys:
        raise RuntimeError("未找到可验证的源码模块接口证据")
    route_mode = str(
        source_info.get("ui_project_runtime_route_mode")
        or (source_info.get("ui_project_entry") or {}).get("route_mode")
        or ""
    )
    for module_key in module_keys:
        urls = runtime_probe_urls(root_url, route_mode, module_key)
        ok_probe = None
        last_error = ""
        for url in urls:
            try:
                result = http_probe_json(url)
                ok_probe = {"kind": "module_api", "module_key": module_key, "url": url, "ok": True, "status": result["status"]}
                break
            except Exception as exc:
                last_error = str(exc)
        if ok_probe:
            probes.append(ok_probe)
        else:
            raise RuntimeError(f"生成项目模块接口不可访问：{module_key}，{last_error}")
    source_evidence["runtime_probe_ready"] = True
    source_evidence["runtime_probe_count"] = len(probes)
    source_evidence["runtime_probes"] = probes
    source_info["ui_runtime_probe_ready"] = True
    source_info["ui_runtime_probe_count"] = len(probes)
    source_info["ui_runtime_probes"] = probes


def http_probe_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/json,text/plain,*/*"})
    with urllib.request.urlopen(request, timeout=8) as response:
        status = int(response.status)
        body = response.read(32768).decode("utf-8", errors="ignore")
    if status < 200 or status >= 500:
        raise RuntimeError(f"{url} 返回 HTTP {status}")
    try:
        parsed: Any = json.loads(body) if body.strip() else None
    except Exception:
        parsed = None
    return {"url": url, "status": status, "body": parsed if parsed is not None else body[:500]}


def runtime_probe_urls(root_url: str, route_mode: str, module_key: str) -> list[str]:
    snake = source_snake(module_key)
    kebab = snake.replace("_", "-")
    urls = [f"{root_url}/{snake}/", f"{root_url}/{snake}"]
    if route_mode == "aspnet-static":
        route = source_snake(source_pascal(module_key)).replace("_", "-")
        urls = [f"{root_url}/api/{route}", f"{root_url}/api/{kebab}"]
    elif route_mode == "spring-static":
        urls = [f"{root_url}/api/{kebab}", f"{root_url}/{snake}/", f"{root_url}/{snake}"]
    return unique_texts(urls)


def select_port(preferred: int) -> int:
    for port in [preferred, *range(5100, 5200)]:
        if port_available(port):
            return port
    raise RuntimeError("未找到可用端口")


def port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        try:
            sock.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def port_from_url(value: str) -> int | None:
    match = re.search(r":(\d+)(?:/|$)", value)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def source_snake(value: str) -> str:
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(value or ""))
    text = re.sub(r"[^A-Za-z0-9]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_").lower()


def source_pascal(value: str) -> str:
    return "".join(part[:1].upper() + part[1:] for part in source_snake(value).split("_") if part)


def unique_texts(values) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result
