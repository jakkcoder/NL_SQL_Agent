"""One-shot Sonnet repair for filter_dp_investor_menu query generation."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from app.core.config import get_config
from app.services.investor_capability import QUERY_GENERATION_FAILED_REPLY
from app.services.investor_menu_query import run_filter_dp_investor_menu_query
from tests.menu_llm_fixtures import menu_query_llm_json


def _litellm_response(payload: str) -> MagicMock:
    msg = MagicMock()
    msg.content = payload
    ch = MagicMock()
    ch.message = msg
    resp = MagicMock()
    resp.choices = [ch]
    return resp


def test_validation_failure_retries_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    import litellm

    get_config.cache_clear()
    monkeypatch.setenv("CATALOG_SQL_EXECUTE_ENABLED", "false")
    calls: list[dict] = []

    def _completion(**kwargs: object) -> MagicMock:
        calls.append(kwargs)
        if len(calls) == 1:
            bad = json.dumps(
                {
                    "thought": "bad",
                    "sql": "SELECT 1",
                    "parameters": ["ARN-0411"],
                    "unsupported_reason": None,
                }
            )
            return _litellm_response(bad)
        return _litellm_response(
            menu_query_llm_json(trusted_arn="ARN-0411", thought="fixed")
        )

    monkeypatch.setattr(litellm, "completion", _completion)

    state: dict = {}
    out = run_filter_dp_investor_menu_query("show my investors", state).model_dump(mode="json")
    assert out["status"] == "ok"
    assert out["sql_retry_used"] is True
    assert len(calls) == 2
    repair_payload = json.loads(calls[1]["messages"][1]["content"])
    assert "repair_context" in repair_payload


def test_two_failures_return_standard_message(monkeypatch: pytest.MonkeyPatch) -> None:
    import litellm

    get_config.cache_clear()
    monkeypatch.setenv("CATALOG_SQL_EXECUTE_ENABLED", "false")

    def _completion(**kwargs: object) -> MagicMock:
        bad = json.dumps(
            {
                "thought": "bad",
                "sql": "SELECT 1",
                "parameters": ["ARN-0411"],
                "unsupported_reason": None,
            }
        )
        return _litellm_response(bad)

    monkeypatch.setattr(litellm, "completion", _completion)

    state: dict = {}
    out = run_filter_dp_investor_menu_query("show my investors", state).model_dump(mode="json")
    assert out["status"] == "error"
    assert QUERY_GENERATION_FAILED_REPLY in out["reply"]
    assert out["sql_retry_used"] is True
    assert out.get("sql") is None


def test_llm_empty_response_retries_once(monkeypatch: pytest.MonkeyPatch) -> None:
    import litellm

    get_config.cache_clear()
    monkeypatch.setenv("CATALOG_SQL_EXECUTE_ENABLED", "false")
    n = 0

    def _completion(**kwargs: object) -> MagicMock:
        nonlocal n
        n += 1
        if n == 1:
            return _litellm_response("")
        return _litellm_response(menu_query_llm_json())

    monkeypatch.setattr(litellm, "completion", _completion)

    out = run_filter_dp_investor_menu_query("show investors", {}).model_dump(mode="json")
    assert out["status"] == "ok"
    assert n == 2
