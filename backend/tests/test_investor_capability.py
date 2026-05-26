"""Capability boundaries and standard unsupported replies."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.agents.tools import generate_catalog_sql_query_tool
from app.core.config import get_config
from app.models.agent_state import STATE_KEY_FINAL_QUERY, STATE_KEY_LAST_SQL
from app.services.investor_capability import (
    build_unsupported_capability_reply,
    detect_unsupported_question,
)


def test_detect_age_question_unsupported() -> None:
    assert detect_unsupported_question("Investor with Age between 30 and 40") is not None


def test_detect_sip_question_supported() -> None:
    assert detect_unsupported_question("Show investors with active SIP") is None


def test_unsupported_reply_mentions_future_version() -> None:
    text = build_unsupported_capability_reply("age filters")
    assert "future version" in text.lower()
    assert "filter_dp_investor_menu" in text
    assert "age filters" in text


class _Ctx:
    def __init__(self) -> None:
        self.state: dict = {}


def test_tool_out_of_scope_does_not_publish_sql(monkeypatch: pytest.MonkeyPatch) -> None:
    get_config.cache_clear()
    monkeypatch.setenv("CATALOG_SQL_EXECUTE_ENABLED", "false")
    ctx = _Ctx()
    out = generate_catalog_sql_query_tool("Investors in Mumbai only", ctx)
    assert out["status"] == "out_of_scope"
    assert out.get("sql") is None
    assert STATE_KEY_FINAL_QUERY not in ctx.state
    assert STATE_KEY_LAST_SQL not in ctx.state
    assert "not available" in (out.get("reply") or "").lower()
    assert "future version" in (out.get("reply") or "").lower()
