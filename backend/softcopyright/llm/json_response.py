"""Parse model JSON without dropping nested data or inventing business values."""
from __future__ import annotations

import json
import re
from typing import Any

from .trace import trace_event


def parse_json_object(content: str, *, label: str = "") -> dict[str, Any]:
    cleaned = str(content or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as original:
        # Only a missing OUTER object terminator is eligible. Never close an
        # unfinished string, array, nested object, key or scalar value.
        stack: list[str] = []
        quoted = escaped = mismatch = False
        for char in cleaned:
            if quoted:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    quoted = False
            elif char == '"':
                quoted = True
            elif char in "{[":
                stack.append(char)
            elif char in "}]":
                if not stack or stack.pop() != ("{" if char == "}" else "["):
                    mismatch = True
                    break
        candidate = cleaned.rstrip()
        if candidate.endswith(","):
            candidate = candidate[:-1].rstrip()
        if (cleaned.startswith("{") and stack == ["{"] and not quoted
                and not mismatch and candidate.endswith(("]", "}"))):
            try:
                data = json.loads(candidate + "}")
            except json.JSONDecodeError:
                raise original
            trace_event(
                "model_json_syntax_repaired", label=label,
                repair="outer_object_terminator", content_chars=len(cleaned),
            )
        else:
            raise
    if not isinstance(data, dict):
        raise ValueError("LLM 返回必须是 JSON 对象")
    return data
