"""Example NL strings: ``generate_catalog_sql_query_tool`` → ``filter_dp_investor_menu``."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from app.agents.tools import generate_catalog_sql_query_tool
from app.core.config import get_config
from app.models.agent_state import (
    STATE_KEY_FINAL_QUERY,
    STATE_KEY_LAST_SQL,
    STATE_KEY_LAST_SQL_PARAMETERS,
)


class _FakeToolContext:
    """Minimal ADK-like tool context for tool unit tests."""

    def __init__(self, state: dict | None = None):
        self.state = state or {}


# Portal-supported examples (see planning/Investor_Filter_Query_Mapping - Individual Investors.csv)
EXAMPLE_QUERIES: list[str] = [
    "Show my investors",
    "Show eligible investors",
    "Show investors with OTM",
    "Show active investors",
    "Show dormant investors",
    "Show minor investors",
    "Show investors with active SIP",
    "Who redeemed recently",
    "Find investor named Bhavin",
]


def _choice(content: str) -> MagicMock:
    msg = MagicMock()
    msg.content = content
    ch = MagicMock()
    ch.message = msg
    resp = MagicMock()
    resp.choices = [ch]
    return resp


def _default_menu_params_json() -> str:
    return json.dumps(
        {
            "thought": "stub",
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


@pytest.fixture
def stub_menu_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    import litellm

    get_config.cache_clear()
    monkeypatch.setenv("CATALOG_SQL_EXECUTE_ENABLED", "false")
    monkeypatch.setattr(
        litellm,
        "completion",
        lambda **kwargs: _choice(_default_menu_params_json()),
    )


@pytest.mark.parametrize("query", EXAMPLE_QUERIES)
def test_generate_catalog_sql_tool_stores_final_query_in_state(
    stub_menu_llm: None,
    query: str,
) -> None:
    tool_context = _FakeToolContext()
    out = generate_catalog_sql_query_tool(query, tool_context)

    assert out["status"] == "ok", out
    assert STATE_KEY_FINAL_QUERY in tool_context.state
    fq = tool_context.state[STATE_KEY_FINAL_QUERY]
    assert fq.get("engine") == "filter_dp_investor_menu"
    sql = fq.get("sql")
    assert isinstance(sql, str) and "filter_dp_investor_menu" in sql
    params = fq.get("parameters")
    assert isinstance(params, list)

    sql_pg = fq.get("sql_postgresql")
    assert isinstance(sql_pg, str) and "filter_dp_investor_menu" in sql_pg
    assert tool_context.state.get(STATE_KEY_LAST_SQL) == sql_pg
    assert tool_context.state.get(STATE_KEY_LAST_SQL_PARAMETERS) == params
