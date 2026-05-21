"""ARN scope guardrails (session ARN vs user text / tool override)."""

import pytest

from app.agents.tools import analyze_search_arguments_tool, search_investors_tool
from app.services.arn_scope_guard import (
    ARN_SCOPE_REPLY,
    arn_scope_block_reason,
    extract_arn_codes_from_text,
    normalize_arn,
)
from tests.test_agent_tools import FakeToolContext


def test_normalize_arn():
    assert normalize_arn("  arn-0411 ") == "ARN-0411"


def test_extract_arn_codes():
    assert extract_arn_codes_from_text("Show ARN-0411 and ARN-9999") == ["ARN-0411", "ARN-9999"]
    assert extract_arn_codes_from_text("named arnold") == []


def test_arn_scope_block_reason_tool_arg_mismatch():
    assert (
        arn_scope_block_reason(
            user_query="show investors",
            tool_arn_arg="ARN-9999",
            trusted_arn="ARN-0411",
        )
        == ARN_SCOPE_REPLY
    )


def test_arn_scope_block_reason_other_arn_in_text():
    assert (
        arn_scope_block_reason(
            user_query="list investors for ARN-7777",
            tool_arn_arg=None,
            trusted_arn="ARN-0411",
        )
        == ARN_SCOPE_REPLY
    )


def test_arn_scope_block_reason_same_arn_in_text_ok():
    assert (
        arn_scope_block_reason(
            user_query="show all for ARN-0411 please",
            tool_arn_arg=None,
            trusted_arn="ARN-0411",
        )
        is None
    )


def test_arn_scope_block_reason_matching_tool_arg_ok():
    assert (
        arn_scope_block_reason(
            user_query="show investors",
            tool_arn_arg="ARN-0411",
            trusted_arn="ARN-0411",
        )
        is None
    )


class _FakeSearch:
    default_dev_arn = "ARN-0411"
    default_page_limit = 25
    max_intersection_rows = 5000


class _FakeDBCfg:
    statement_timeout_ms = 1000
    pool_min_size = 1
    pool_max_size = 1
    connect_timeout_seconds = 1
    pool_timeout_seconds = 1


class _FakeConfig:
    search = _FakeSearch()
    database_url_value = None
    database = _FakeDBCfg()


def test_search_investors_tool_blocks_cross_arn_query(monkeypatch):
    monkeypatch.setattr("app.agents.tools.get_config", lambda: _FakeConfig())
    out = search_investors_tool("show investors under ARN-8888", FakeToolContext())
    assert out["status"] == "out_of_scope"
    assert "only show investors" in out["reply"].lower()
    assert out["routing_state"]["step"] == "blocked"


def test_analyze_search_arguments_tool_blocks_cross_arn_before_llm(monkeypatch):
    monkeypatch.setattr("app.agents.tools.get_config", lambda: _FakeConfig())

    def boom(*args, **kwargs):
        raise AssertionError("LLM should not run when ARN scope blocks")

    monkeypatch.setattr("app.agents.tools.build_search_plan", boom)

    out = analyze_search_arguments_tool("filter by ARN-8888", FakeToolContext())
    assert out["can_execute"] is False
    assert out["validation_status"] == "out_of_scope"
    assert out["message"] == ARN_SCOPE_REPLY
