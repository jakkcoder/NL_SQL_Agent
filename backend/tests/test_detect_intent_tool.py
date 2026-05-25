"""Compatibility shim for models that still call detect_intent_tool first."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.agents.tools import detect_intent_tool


def _ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.state = {}
    return ctx


def test_detect_intent_greeting_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[str] = []

    def _greet(message: str, tool_context: MagicMock) -> dict:
        called.append(message)
        return {"status": "greeting", "reply": "Hi"}

    monkeypatch.setattr("app.agents.tools.greeting_tool", _greet)
    out = detect_intent_tool("hello", _ctx())
    assert called == ["hello"]
    assert out["reply"] == "Hi"


def test_detect_intent_investor_runs_sql(monkeypatch: pytest.MonkeyPatch) -> None:
    def _sql(question: str, tool_context: MagicMock) -> dict:
        return {"status": "ok", "reply": "Found 1 investor record(s).", "rows": [{"id": 1}]}

    monkeypatch.setattr("app.agents.tools.generate_catalog_sql_query_tool", _sql)
    out = detect_intent_tool("Show my investors in Mumbai", _ctx())
    assert out["status"] == "ok"
    assert out["rows"]


def test_detect_intent_banking_out_of_scope() -> None:
    out = detect_intent_tool("What is my account balance?", _ctx())
    assert out["status"] == "out_of_scope"
