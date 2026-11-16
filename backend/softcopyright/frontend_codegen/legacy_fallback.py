from __future__ import annotations

import os
from hashlib import sha256
from typing import Any


LEGACY_FALLBACK_VERSION = "legacy-react-v1"


def legacy_cache_key(creative_key: str) -> str:
    return sha256(f"{creative_key}|{LEGACY_FALLBACK_VERSION}".encode("utf-8")).hexdigest()


def requires_legacy_fallback(renderer: str, screenshot: Any) -> bool:
    if os.getenv("SOFT_PAGE_SPEC_FORCE_LEGACY", "").strip().lower() in {"1", "true", "yes", "on"}:
        return True
    if str(renderer or "").strip().lower() == "game":
        return True
    text = " ".join(
        str(value or "")
        for value in (
            getattr(screenshot, "title", ""),
            getattr(screenshot, "caption", ""),
            getattr(screenshot, "interaction_action", ""),
        )
    ).lower()
    return any(term in text for term in ("3d", "三维", "虚拟仿真", "游戏画布", "实时渲染", "webgl"))
