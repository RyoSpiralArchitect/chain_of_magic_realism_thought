from __future__ import annotations

import dataclasses
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def first_env(names: Iterable[str]) -> Optional[str]:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def clip_text(text: str, max_chars: int) -> str:
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    head = max_chars // 2
    tail = max_chars - head
    return text[:head] + "\n\n...[clipped]...\n\n" + text[-tail:]


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(v) for v in value]
    if dataclasses.is_dataclass(value):
        return json_safe(dataclasses.asdict(value))
    if hasattr(value, "model_dump"):
        try:
            return json_safe(value.model_dump())
        except Exception:
            pass
    return repr(value)


def to_plain_dict(obj: Any) -> Dict[str, Any]:
    """Best-effort conversion of SDK usage objects into JSON-safe dictionaries."""
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return json_safe(obj)
    if hasattr(obj, "model_dump"):
        try:
            return json_safe(obj.model_dump())
        except Exception:
            pass
    if dataclasses.is_dataclass(obj):
        try:
            return json_safe(dataclasses.asdict(obj))
        except Exception:
            pass
    if hasattr(obj, "__dict__"):
        try:
            return json_safe({k: v for k, v in vars(obj).items() if not k.startswith("_")})
        except Exception:
            pass
    return {"repr": repr(obj)}


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def safe_div(numerator: float, denominator: float, default: float = 0.0) -> float:
    return numerator / denominator if denominator else default


def extract_content_text(content: Any) -> str:
    """Extract text from common SDK content shapes."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            text = getattr(item, "text", None)
            if text:
                parts.append(str(text))
                continue
            if isinstance(item, dict):
                if item.get("type") in ("text", "output_text") and item.get("text"):
                    parts.append(str(item["text"]))
                elif item.get("content"):
                    parts.append(extract_content_text(item["content"]))
        return "\n".join(p for p in parts if p)
    text = getattr(content, "text", None)
    if text:
        return str(text)
    return str(content)


def extract_json_object(text: str) -> Dict[str, Any]:
    """Parse the first JSON object found in a model response."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        value = json.loads(stripped)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", stripped, flags=re.S)
    if not match:
        raise ValueError("No JSON object found in judge response.")
    value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise ValueError("Judge JSON must be an object.")
