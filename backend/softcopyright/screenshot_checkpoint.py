from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .packager import write_json
from .screenshot_capture import _normalize_visible_content_summary


SCREENSHOT_CHECKPOINT_VERSION = 13


def screenshot_checkpoint_path(ui_dir: Path) -> Path:
    return ui_dir / "screenshot-checkpoint.json"


def screenshot_input_fingerprint(item: Any, renderer: str, viewport: dict[str, int]) -> str:
    digest = hashlib.sha256()
    digest.update(
        (
            f"v{SCREENSHOT_CHECKPOINT_VERSION}|{renderer}|"
            f"{viewport.get('width')}x{viewport.get('height')}|{item.key}|"
            f"{item.interaction_action}|{item.interaction_mode}|"
            f"{item.interaction_surface}|{int(bool(item.requires_confirmation))}|"
            f"{item.interaction_action_key}|{item.interaction_role}|{item.interaction_trigger}|"
            f"{'/'.join(item.interaction_input_fields or [])}|{item.interaction_pre_state}|"
            f"{item.interaction_post_state}|{item.interaction_result_evidence}"
        ).encode("utf-8")
    )
    try:
        html_path = Path(item.html_path)
        digest.update(html_path.read_bytes())
        for asset_name in ("app.js", "index.css"):
            asset_path = html_path.parent / "assets" / asset_name
            if asset_path.is_file():
                digest.update(asset_name.encode("utf-8"))
                digest.update(asset_path.read_bytes())
    except OSError:
        return ""
    return digest.hexdigest()


def load_screenshot_checkpoint(ui_dir: Path) -> dict[str, Any]:
    path = screenshot_checkpoint_path(ui_dir)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {"version": SCREENSHOT_CHECKPOINT_VERSION, "pages": {}}
    if not isinstance(payload, dict) or payload.get("version") != SCREENSHOT_CHECKPOINT_VERSION:
        return {"version": SCREENSHOT_CHECKPOINT_VERSION, "pages": {}}
    pages = payload.get("pages")
    payload["pages"] = pages if isinstance(pages, dict) else {}
    return payload


def restore_screenshot_checkpoint_prefix(
    ui_dir: Path,
    screenshots: list[Any],
    renderer: str,
    viewport: dict[str, int],
) -> tuple[dict[str, Any], int]:
    checkpoint = load_screenshot_checkpoint(ui_dir)
    pages = checkpoint.get("pages", {})
    valid_pages: dict[str, Any] = {}
    restored = 0
    for item in screenshots:
        entry = pages.get(item.key)
        image_path = ui_dir / f"{item.key}.png"
        if (
            not isinstance(entry, dict)
            or entry.get("fingerprint") != screenshot_input_fingerprint(item, renderer, viewport)
            or not image_path.is_file()
            or image_path.stat().st_size <= 0
        ):
            break
        item.image_path = str(image_path)
        item.width = int(entry.get("width") or viewport["width"])
        item.height = int(entry.get("height") or viewport["height"])
        item.runtime_fetches = list(entry.get("runtime_fetches") or [])
        item.action_crops = dict(entry.get("action_crops") or {})
        item.visible_content_summary = _normalize_visible_content_summary(
            dict(entry.get("visible_content_summary") or {}),
            item,
        )
        valid_pages[item.key] = {
            **entry,
            "visible_content_summary": dict(item.visible_content_summary or {}),
        }
        restored += 1
    restored_checkpoint = {"version": SCREENSHOT_CHECKPOINT_VERSION, "pages": valid_pages}
    if valid_pages:
        write_json(screenshot_checkpoint_path(ui_dir), restored_checkpoint)
    return restored_checkpoint, restored


def save_screenshot_checkpoint_page(
    ui_dir: Path,
    checkpoint: dict[str, Any],
    item: Any,
    renderer: str,
    viewport: dict[str, int],
) -> None:
    pages = checkpoint.setdefault("pages", {})
    pages[item.key] = {
        "fingerprint": screenshot_input_fingerprint(item, renderer, viewport),
        "width": item.width,
        "height": item.height,
        "runtime_fetches": list(item.runtime_fetches or []),
        "action_crops": dict(item.action_crops or {}),
        "visible_content_summary": dict(item.visible_content_summary or {}),
    }
    write_json(screenshot_checkpoint_path(ui_dir), checkpoint)
