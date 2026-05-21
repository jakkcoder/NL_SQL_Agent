"""Tests for ``app.services.react_dynamic_sql_engine`` (LLM mocked)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.services.react_dynamic_sql_engine import run_react_dynamic_sql


class _FakeDB:
    def fetch_all(self, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        assert "arn_code" in sql.lower() or "broker_code" in sql.lower()
        return [{"answer": 42}]


def _fake_completion_factory(payloads: list[dict[str, Any]]):
    remaining = list(payloads)

    def _completion(**kwargs: Any):
        if not remaining:
            raise RuntimeError("unexpected extra LLM call")
        payload = remaining.pop(0)

        class _Msg:
            content = json.dumps(payload)

        class _Choice:
            message = _Msg()

        class _Resp:
            choices = [_Choice()]

        return _Resp()

    return _completion


def test_react_succeeds_on_second_turn_after_guard_failure(monkeypatch):
    bad = {"thought": "omit limit", "sql": "SELECT 1 WHERE arn_code = %s", "parameters": ["ARN-0411"]}
    good = {
        "thought": "fix",
        "sql": "SELECT 1 AS answer WHERE arn_code = %s LIMIT 10",
        "parameters": ["ARN-0411"],
    }
    monkeypatch.setattr(
        "app.services.react_dynamic_sql_engine.litellm.completion",
        _fake_completion_factory([bad, good]),
    )

    result = run_react_dynamic_sql(
        user_question="count something",
        trusted_arn="ARN-0411",
        schema_compact={"tables": [], "table_count": 0, "column_count": 0, "contract_kind": "investor_schema_compact"},
        db=_FakeDB(),
        llm_model="bedrock/fake-model",
        llm_timeout_seconds=30,
        max_output_tokens=None,
    )

    assert result["ok"] is True
    assert result["attempts"] == 2
    assert result["rows"] == [{"answer": 42}]
    assert result["error"] is None


def test_react_exhausts_three_attempts(monkeypatch):
    bad = {"thought": "bad", "sql": "SELECT 1 WHERE arn_code = %s", "parameters": ["ARN-0411"]}
    monkeypatch.setattr(
        "app.services.react_dynamic_sql_engine.litellm.completion",
        _fake_completion_factory([bad, bad, bad]),
    )

    result = run_react_dynamic_sql(
        user_question="x",
        trusted_arn="ARN-0411",
        schema_compact={"tables": [], "table_count": 0, "column_count": 0, "contract_kind": "investor_schema_compact"},
        db=_FakeDB(),
        llm_model="bedrock/fake-model",
        llm_timeout_seconds=30,
        max_output_tokens=None,
    )

    assert result["ok"] is False
    assert result["attempts"] == 3
