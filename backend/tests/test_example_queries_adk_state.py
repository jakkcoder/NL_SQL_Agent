"""Example NL strings: ``generate_catalog_sql_query_tool`` persists final SQL in session state."""

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


EXAMPLE_QUERIES: list[str] = [
    "Show my investors in Mumbai",
    "Investor with Age between 30 and 40",
    "Investors who did redemption in last quarter for equity funds.",
    "Active SIPs above 5,000 per month in hybrid funds.",
    "Dormant / inactive investors (investors not transacted in certain period / having 0 units across all schemes)",
    "Top 20 investors by purchases in FY25",
    "Investors named 'Bhavin' in Mumbai or Ahmedabad.",
    "NRI investors",
    "Minor Investors not invested in CGF schemes",
    "Investors with no active SIP",
    "Investors with investment only in Liquid / cash funds",
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
def stub_catalog_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Return a minimal valid SQL proposal for every catalog-generator LLM call."""

    import litellm

    trusted = get_config().search.default_dev_arn
    safe_sql = "SELECT 1 AS one FROM public.investor i WHERE i.arn_code = %s LIMIT 1"

    def _completion(**kwargs):
        payload = json.dumps({"thought": "stub", "sql": safe_sql, "parameters": [trusted]})
        return _choice(payload)

    monkeypatch.setattr(litellm, "completion", _completion)


@pytest.mark.parametrize("query", EXAMPLE_QUERIES)
def test_generate_catalog_sql_tool_stores_final_query_in_state(
    stub_catalog_llm: None,
    query: str,
) -> None:
    tool_context = _FakeToolContext()
    out = generate_catalog_sql_query_tool(query, tool_context)

    assert out["status"] == "ok", out
    assert STATE_KEY_FINAL_QUERY in tool_context.state
    fq = tool_context.state[STATE_KEY_FINAL_QUERY]
    assert fq.get("engine") == "catalog_sql_generator"
    sql = fq.get("sql")
    assert isinstance(sql, str) and "SELECT" in sql
    params = fq.get("parameters")
    assert isinstance(params, list)

    sql_pg = fq.get("sql_postgresql")
    assert isinstance(sql_pg, str) and "SELECT" in sql_pg
    assert "%s" not in sql_pg
    assert tool_context.state.get(STATE_KEY_LAST_SQL) == sql_pg
    assert tool_context.state.get(STATE_KEY_LAST_SQL_PARAMETERS) == params
