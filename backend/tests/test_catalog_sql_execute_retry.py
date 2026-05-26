"""Execute path for ``generate_catalog_sql_query_tool`` (filter_dp_investor_menu)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from app.agents.tools import generate_catalog_sql_query_tool
from app.core.config import get_config


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


def _menu_params_payload() -> str:
    return json.dumps(
        {
            "thought": "t",
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


def test_execute_success_returns_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    import litellm

    get_config.cache_clear()
    monkeypatch.setenv("CATALOG_SQL_EXECUTE_ENABLED", "true")
    monkeypatch.setattr(litellm, "completion", lambda **kwargs: _choice(_menu_params_payload()))
    monkeypatch.setattr(
        "app.agents.tools.execute_filter_dp_investor_menu",
        lambda *a, **k: [{"uuid": "x", "name": "Test"}],
    )

    out = generate_catalog_sql_query_tool("show investors", _ToolCtx())
    assert out["status"] == "ok"
    assert out["executed"] is True
    assert out["row_count"] == 1
    assert "results table" in out["reply"].lower()


def test_execute_failure_returns_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import litellm

    from app.services.catalog_sql_executor import CatalogSqlExecuteError

    get_config.cache_clear()
    monkeypatch.setenv("CATALOG_SQL_EXECUTE_ENABLED", "true")
    monkeypatch.setattr(litellm, "completion", lambda **kwargs: _choice(_menu_params_payload()))

    def _fail(*a, **k):
        raise CatalogSqlExecuteError("function filter_dp_investor_menu failed")

    monkeypatch.setattr("app.agents.tools.execute_filter_dp_investor_menu", _fail)

    out = generate_catalog_sql_query_tool("show investors", _ToolCtx())
    assert out["status"] == "error"
    assert out["executed"] is False
    assert out["sql_retry_used"] is False
