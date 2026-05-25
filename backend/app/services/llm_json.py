"""Shared helpers for strict JSON responses from LiteLLM."""

from __future__ import annotations

import json
import re
from typing import Any


def _strip_markdown_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _escape_control_chars_in_json_strings(text: str) -> str:
    """Escape raw newlines/tabs inside JSON string literals (Bedrock sql field often breaks this)."""

    out: list[str] = []
    in_string = False
    escape = False
    for ch in text:
        if in_string:
            if escape:
                out.append(ch)
                escape = False
                continue
            if ch == "\\":
                out.append(ch)
                escape = True
                continue
            if ch == '"':
                out.append(ch)
                in_string = False
                continue
            if ch == "\n":
                out.append("\\n")
                continue
            if ch == "\r":
                out.append("\\r")
                continue
            if ch == "\t":
                out.append("\\t")
                continue
            out.append(ch)
        else:
            if ch == '"':
                in_string = True
            out.append(ch)
    return "".join(out)


def _loads_json_object(text: str) -> Any | None:
    """``json.loads`` with one repair pass for multiline string values."""

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    repaired = _escape_control_chars_in_json_strings(text)
    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        return None


def _unwrap_to_object(parsed: Any, *, depth: int = 0) -> dict[str, Any] | None:
    """Accept dict, single-element list, or nested JSON string (Bedrock double-encoding)."""

    if depth > 6:
        return None
    if isinstance(parsed, dict):
        return parsed
    if isinstance(parsed, list) and len(parsed) == 1:
        return _unwrap_to_object(parsed[0], depth=depth + 1)
    if isinstance(parsed, str):
        inner = parsed.strip()
        if not inner:
            return None
        nested = _loads_json_object(inner)
        if nested is not None:
            return _unwrap_to_object(nested, depth=depth + 1)
        try:
            obj, _end = json.JSONDecoder().raw_decode(_escape_control_chars_in_json_strings(inner))
        except json.JSONDecodeError:
            return None
        return _unwrap_to_object(obj, depth=depth + 1)
    return None


def _json_object_candidates(text: str) -> list[str]:
    """Try full body first, then substring starting at each ``{`` (model preamble text)."""

    text = _strip_markdown_fence(text)
    if not text:
        return []
    candidates = [text]
    for match in re.finditer(r"\{", text):
        start = match.start()
        if start > 0 and text[start - 1] in ("'", '"'):
            continue
        fragment = text[start:]
        if fragment not in candidates:
            candidates.append(fragment)
    return candidates


def parse_json_content(content: str) -> dict[str, Any]:
    """Parse model output into one JSON object (tolerates fences, wrappers, string encoding)."""

    if not content or not str(content).strip():
        raise ValueError("LLM response is empty")

    last_error: Exception | None = None
    for candidate in _json_object_candidates(str(content)):
        parsed = _loads_json_object(candidate)
        if parsed is None:
            last_error = json.JSONDecodeError("invalid JSON", candidate, 0)
            continue
        obj = _unwrap_to_object(parsed)
        if obj is not None:
            return obj

    detail = str(last_error) if last_error else "no JSON object found"
    raise ValueError(f"LLM JSON must be one object: {detail}")
