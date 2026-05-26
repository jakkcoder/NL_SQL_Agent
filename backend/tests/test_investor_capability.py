"""Capability boundaries and standard unsupported replies."""

from __future__ import annotations

import json

import pytest

from app.core.config import get_config
from app.models.agent_state import STATE_KEY_FINAL_QUERY, STATE_KEY_LAST_SQL
from app.services.investor_capability import build_unsupported_capability_reply
from app.services.investor_menu_query import run_filter_dp_investor_menu_query


def test_unsupported_reply_mentions_future_version() -> None:
    text = build_unsupported_capability_reply("age filters")
    assert "future version" in text.lower()
    assert "filter_dp_investor_menu" in text
    assert "age filters" in text


def test_llm_out_of_scope_does_not_publish_sql(monkeypatch: pytest.MonkeyPatch) -> None:
    import litellm
    from unittest.mock import MagicMock

    get_config.cache_clear()
    monkeypatch.setenv("CATALOG_SQL_EXECUTE_ENABLED", "false")
    payload = json.dumps(
        {
            "thought": "city filter not supported",
            "sql": None,
            "parameters": [],
            "unsupported_reason": "city or geography filters",
        }
    )
    msg = MagicMock()
    msg.content = payload
    ch = MagicMock()
    ch.message = msg
    resp = MagicMock()
    resp.choices = [ch]
    monkeypatch.setattr(litellm, "completion", lambda **kwargs: resp)

    state: dict = {}
    out = run_filter_dp_investor_menu_query("Investors in Mumbai only", state).model_dump(
        mode="json"
    )
    assert out["status"] == "out_of_scope"
    assert out.get("sql") is None
    assert STATE_KEY_FINAL_QUERY not in state
    assert STATE_KEY_LAST_SQL not in state
    assert "not available" in (out.get("reply") or "").lower()
    assert "future version" in (out.get("reply") or "").lower()
