from __future__ import annotations

import re
from typing import Any


_URL_PATTERN = re.compile(r"https?://[^\s\"'<>，。；;、)）\]}]+", re.IGNORECASE)
_BEARER_PATTERN = re.compile(r"(Bearer\s+)[A-Za-z0-9._~+/=-]+", re.IGNORECASE)
_SECRET_FIELD_PATTERN = re.compile(
    r"(?i)\b(api[_-]?key|token|secret|authorization)(\s*[:=]\s*['\"]?)[^'\"\s,;，；)）\]}]+"
)
_CONNECTION_POOL_PATTERN = re.compile(
    r"(?i)(?:HTTPS?|HTTP)ConnectionPool\(host=['\"][^'\"]+['\"],\s*port=\d+\)"
)
_RELATIVE_REQUEST_PATH_PATTERN = re.compile(
    r"(?i)(\b(?:for|with)\s+url:\s*)/(?:v\d+/)?(?:chat/completions|messages|images/generations)\b[^\s\"'<>，。；;、)）\]}]*"
)


def sanitize_error_message(value: Any, *, limit: int | None = None) -> str:
    """Return a customer-safe error message without gateway URLs or credentials."""
    text = str(value or "").strip()
    if not text:
        return ""
    text = _BEARER_PATTERN.sub(r"\1[已隐藏]", text)
    text = _SECRET_FIELD_PATTERN.sub(r"\1\2[已隐藏]", text)
    text = _CONNECTION_POOL_PATTERN.sub("模型网关连接", text)
    text = _RELATIVE_REQUEST_PATH_PATTERN.sub(r"\1[模型接口]", text)
    text = re.sub(r"(?i)(for url:\s*)https?://[^\s\"'<>，。；;、)）\]}]+", r"\1[模型网关]", text)
    text = _URL_PATTERN.sub("[模型网关]", text)
    text = re.sub(r"\s+", " ", text).strip()
    if limit is not None and limit > 0:
        return text[:limit]
    return text
