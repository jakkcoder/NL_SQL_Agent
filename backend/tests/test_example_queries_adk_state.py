"""Example NL strings: ``filter_dp_investor_menu_tool`` → ``filter_dp_investor_menu``."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.agents.tools import filter_dp_investor_menu_tool
from app.core.config import get_config
from tests.menu_llm_fixtures import menu_query_llm_json
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


@pytest.fixture
def stub_menu_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    import litellm

    get_config.cache_clear()
    monkeypatch.setenv("CATALOG_SQL_EXECUTE_ENABLED", "false")
    monkeypatch.setattr(
        litellm,
        "completion",
        lambda **kwargs: _choice(menu_query_llm_json()),
    )


@pytest.mark.parametrize("query", EXAMPLE_QUERIES)
def test_generate_catalog_sql_tool_stores_final_query_in_state(
    stub_menu_llm: None,
    query: str,
) -> None:
    tool_context = _FakeToolContext()
    out = filter_dp_investor_menu_tool(query, tool_context)

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
