"""Validation repair LLM invoked when static sql_guard fails."""

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


def test_validation_repair_fixes_cte_semicolon(monkeypatch: pytest.MonkeyPatch) -> None:
    import litellm

    get_config.cache_clear()
    monkeypatch.setenv("CATALOG_SQL_EXECUTE_ENABLED", "false")
    trusted = get_config().search.default_dev_arn

    bad_sql = (
        "SELECT 1 AS n FROM public.distributor_investor_mapping "
        f"WHERE arn_code = '{trusted}' LIMIT 1000"
    )
    good_sql = (
        "SELECT 1 AS n FROM public.distributor_investor_mapping WHERE arn_code = %s LIMIT 20"
    )

    calls: list[str] = []

    def completion(**kwargs):
        user = json.loads(kwargs["messages"][1]["content"])
        if "validation_error" in user:
            payload = json.dumps(
                {"thought": "fix", "sql": good_sql, "parameters": [trusted]}
            )
            calls.append("repair")
        else:
            payload = json.dumps(
                {"thought": "t", "sql": bad_sql, "parameters": [trusted]}
            )
            calls.append("generate")
        return _choice(payload)

    monkeypatch.setattr(litellm, "completion", completion)
    monkeypatch.setattr(
        "app.agents.tools.load_schema_guide",
        lambda: {"contract_kind": "investor_schema_guide", "tables": []},
    )
    monkeypatch.setattr(
        "app.services.schema_guide_module_router.modular_guide_available",
        lambda: False,
    )

    out = generate_catalog_sql_query_tool("Top 20 investors by purchases in FY25", _ToolCtx())
    assert "repair" in calls
    assert out["status"] == "ok"
    assert out["sql"] == good_sql
