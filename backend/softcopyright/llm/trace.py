from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import threading
from typing import Any

from ..errors import sanitize_error_message

_LOCK = threading.Lock()


def trace_enabled() -> bool:
    return bool(os.getenv("SOFT_LLM_TRACE_PATH", "").strip())


def trace_event(event: str, **payload: Any) -> None:
    path_text = os.getenv("SOFT_LLM_TRACE_PATH", "").strip()
    if not path_text:
        return
    record = {
        "ts": datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds"),
        "event": event,
    }
    record.update({key: _safe_value(value) for key, value in payload.items()})
    path = Path(path_text)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False, sort_keys=True)
        with _LOCK:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
    except OSError:
        return


def _safe_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        if isinstance(value, str):
            return sanitize_error_message(value, limit=500)
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_safe_value(item) for item in value[:20]]
    if isinstance(value, dict):
        return {str(key): _safe_value(item) for key, item in list(value.items())[:30]}
    return str(value)[:500]
