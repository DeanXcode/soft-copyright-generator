from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess


def build_react_vite_bundle(react_dir: Path) -> None:
    electron_node = os.getenv("SOFT_ELECTRON_NODE", "").strip()
    node = electron_node or shutil.which("node") or shutil.which("node.exe")
    vite_bin = frontend_node_module_root() / "vite" / "bin" / "vite.js"
    if not node or (not vite_bin.exists() and not os.getenv("SOFT_NODE_MODULE_ROOT", "").strip()):
        raise RuntimeError("缺少随软件提供的 Node/Vite 运行环境，无法构建 React 界面工程")
    env = dict(os.environ)
    if electron_node and str(node).lower() == electron_node.lower():
        env["ELECTRON_RUN_AS_NODE"] = "1"
    result = subprocess.run(
        [node, str(vite_bin), "build", "--config", "vite.runtime.config.js"],
        cwd=str(react_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="ignore",
        timeout=180,
        env=env,
    )
    if result.returncode != 0:
        detail = react_build_error_detail(result.stdout or "")
        raise RuntimeError(f"React + Vite 界面工程构建失败：{detail[:900]}")


def react_build_error_detail(output: str) -> str:
    cleaned = re.sub(r"\x1b\[[0-9;]*m", "", str(output or ""))
    lines = [line.rstrip() for line in cleaned.splitlines() if line.strip()]
    important: list[str] = []
    markers = ("error during build", "ERROR:", "file:", "Expected ", "Unexpected ", "Parse failure")
    for index, line in enumerate(lines):
        if any(marker.lower() in line.lower() for marker in markers):
            start = max(0, index - 1)
            end = min(len(lines), index + 4)
            for item in lines[start:end]:
                if re.match(r"\s*at\s", item):
                    continue
                if item not in important:
                    important.append(item)
    if important:
        return "\n".join(important)
    return "\n".join(lines[-8:])


def frontend_node_module_root() -> Path:
    configured = os.getenv("SOFT_NODE_MODULE_ROOT", "").strip()
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[3] / "node_modules"
