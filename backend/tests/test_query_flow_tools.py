"""Unit tests for ``generate_catalog_sql_query_tool`` (mocked menu-param LLM)."""

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

    from app.core.config import get_config as _get_config

    get_config.cache_clear()
    monkeypatch.setenv("CATALOG_SQL_EXECUTE_ENABLED", "false")
    trusted = _get_config().search.default_dev_arn
    llm_payload = json.dumps(
        {
            "thought": "default list",
            "eligibility": "ALL",
            "otm": "ALL",
            "investor_type": "ALL",
            "investor_subtypes": [],
            "holding": None,
            "systematic": None,
            "activity": None,
            "searchtext": None,
            "sortkey": "first_name",
            "sortvalue": "ASC",
            "page_limit": 25,
            "page_index": 0,
            "allowbroker": "Y",
            "unsupported_reason": None,
        }
    )

    monkeypatch.setattr(litellm, "completion", lambda **kwargs: _choice(llm_payload))

    ctx = _ToolCtx()
    out = generate_catalog_sql_query_tool("show my investors", ctx)
    assert out["status"] == "ok"
    assert "filter_dp_investor_menu" in (out.get("sql") or "")
    assert out["executed"] is False
    reply = out.get("reply") or ""
    assert "not executed" in reply.lower() or "execution disabled" in reply.lower()
    fq = ctx.state[STATE_KEY_FINAL_QUERY]
    assert fq.get("engine") == "filter_dp_investor_menu"
    trace = ctx.state[STATE_KEY_QUERY_FLOW_TRACE]
    assert isinstance(trace, list) and trace[-1].get("phase") == "filter_dp_investor_menu_params"
