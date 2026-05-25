"""Execute + single repair retry in generate_catalog_sql_query_tool."""

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


def test_execute_success_returns_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    import litellm

    get_config.cache_clear()
    monkeypatch.setenv("CATALOG_SQL_EXECUTE_ENABLED", "true")
    trusted = get_config().search.default_dev_arn
    sql = "SELECT 1 AS n FROM public.distributor_investor_mapping WHERE arn_code = %s LIMIT 1"
    payload = json.dumps({"thought": "t", "sql": sql, "parameters": [trusted]})
    monkeypatch.setattr(litellm, "completion", lambda **kwargs: _choice(payload))
    monkeypatch.setattr(
        "app.agents.tools.execute_catalog_sql_readonly",
        lambda *a, **k: [{"n": 1}],
    )

    out = generate_catalog_sql_query_tool("count", _ToolCtx())
    assert out["status"] == "ok"
    assert out["executed"] is True
    assert out["row_count"] == 1
    assert out["count"] == 1
    assert len(out["rows"]) == 1
    assert "results table" in out["reply"].lower()
    assert "SELECT" not in out["reply"] or "session state" in out["reply"]


def test_execute_failure_retries_once(monkeypatch: pytest.MonkeyPatch) -> None:
    import litellm

    get_config.cache_clear()
    monkeypatch.setenv("CATALOG_SQL_EXECUTE_ENABLED", "true")
    trusted = get_config().search.default_dev_arn
    bad_sql = "SELECT bad FROM nowhere WHERE arn_code = %s LIMIT 1"
    good_sql = "SELECT 2 AS n FROM public.distributor_investor_mapping WHERE arn_code = %s LIMIT 1"
    calls = {"n": 0}

    def completion(**kwargs):
        user = json.loads(kwargs["messages"][1]["content"])
        if "repair_context" in user:
            payload = json.dumps({"thought": "fix", "sql": good_sql, "parameters": [trusted]})
        else:
            payload = json.dumps({"thought": "t", "sql": bad_sql, "parameters": [trusted]})
        return _choice(payload)

    def execute(sql, parameters, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            from app.services.catalog_sql_executor import CatalogSqlExecuteError

            raise CatalogSqlExecuteError("relation \"nowhere\" does not exist")
        return [{"n": 2}]

    monkeypatch.setattr(litellm, "completion", completion)
    monkeypatch.setattr("app.agents.tools.execute_catalog_sql_readonly", execute)

    out = generate_catalog_sql_query_tool("count", _ToolCtx())
    assert out["sql_retry_used"] is True
    assert out["executed"] is True
    assert calls["n"] == 2
