"""Unit tests for ``generate_catalog_sql_query_tool`` (mocked LLM)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from app.agents.tools import generate_catalog_sql_query_tool
from app.core.config import get_config
from app.models.agent_state import (
    STATE_KEY_QUERY_FLOW_TRACE,
    STATE_KEY_QUERY_GENERATOR_LAST,
    STATE_KEY_FINAL_QUERY,
)


class _ToolCtx:
    __slots__ = ("state",)

    def __init__(self) -> None:
        self.state: dict = {}


def _choice(content: str) -> MagicMock:
    msg = MagicMock()
    msg.content = content
    ch = MagicMock()
    ch.message = msg
    resp = MagicMock()
    resp.choices = [ch]
    return resp


def test_generate_catalog_sql_query_tool_returns_sql_only(monkeypatch: pytest.MonkeyPatch) -> None:
    import litellm

    trusted = get_config().search.default_dev_arn
    safe_sql = (
        "SELECT 1 AS one FROM public.investor i WHERE i.arn_code = %s LIMIT 1"
    )
    payload = json.dumps({"thought": "unit", "sql": safe_sql, "parameters": [trusted]})

    monkeypatch.setattr(litellm, "completion", lambda **kwargs: _choice(payload))

    ctx = _ToolCtx()
    out = generate_catalog_sql_query_tool("count investors", ctx)
    assert out["status"] == "ok"
    assert out["sql"] == safe_sql
    assert "not executed" in (out.get("reply") or "").lower()
    assert safe_sql in (out.get("reply") or "")
    assert ctx.state[STATE_KEY_QUERY_GENERATOR_LAST].get("parsed_sql") == safe_sql
    fq = ctx.state[STATE_KEY_FINAL_QUERY]
    assert fq.get("engine") == "catalog_sql_generator"
    assert fq.get("sql") == safe_sql
    trace = ctx.state[STATE_KEY_QUERY_FLOW_TRACE]
    assert isinstance(trace, list) and trace[-1].get("phase") == "catalog_sql_generator"
