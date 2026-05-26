"""Execute path for ``filter_dp_investor_menu_tool`` (filter_dp_investor_menu)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.agents.tools import filter_dp_investor_menu_tool
from app.core.config import get_config
from app.services.investor_capability import QUERY_GENERATION_FAILED_REPLY
from tests.menu_llm_fixtures import menu_query_llm_json


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


def test_execute_success_returns_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    import litellm

    get_config.cache_clear()
    monkeypatch.setenv("CATALOG_SQL_EXECUTE_ENABLED", "true")
    monkeypatch.setattr(litellm, "completion", lambda **kwargs: _choice(menu_query_llm_json()))
    monkeypatch.setattr(
        "app.services.investor_menu_query.execute_filter_dp_investor_menu",
        lambda *a, **k: [{"uuid": "x", "name": "Test"}],
    )

    out = filter_dp_investor_menu_tool("show investors", _ToolCtx())
    assert out["status"] == "ok"
    assert out["executed"] is True
    assert out["row_count"] == 1
    assert "results table" in out["reply"].lower()


def test_execute_failure_returns_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import litellm

    from app.services.catalog_sql_executor import CatalogSqlExecuteError

    get_config.cache_clear()
    monkeypatch.setenv("CATALOG_SQL_EXECUTE_ENABLED", "true")
    monkeypatch.setattr(litellm, "completion", lambda **kwargs: _choice(menu_query_llm_json()))

    def _fail(*a, **k):
        raise CatalogSqlExecuteError("function filter_dp_investor_menu failed")

    monkeypatch.setattr("app.services.investor_menu_query.execute_filter_dp_investor_menu", _fail)

    out = filter_dp_investor_menu_tool("show investors", _ToolCtx())
    assert out["status"] == "error"
    assert out["executed"] is False
    assert out["sql_retry_used"] is True
    assert QUERY_GENERATION_FAILED_REPLY in out["reply"]
