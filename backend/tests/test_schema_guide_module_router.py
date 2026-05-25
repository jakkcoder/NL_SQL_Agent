"""LLM-driven schema guide module selection."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from app.services.schema_guide_module_router import (
    run_schema_guide_module_router_llm,
    select_module_ids_for_question,
)
from app.services.schema_guide_modules import select_module_ids_keyword


def _choice(content: str) -> MagicMock:
    msg = MagicMock()
    msg.content = content
    ch = MagicMock()
    ch.message = msg
    resp = MagicMock()
    resp.choices = [ch]
    return resp


def test_router_llm_parses_json(monkeypatch: pytest.MonkeyPatch) -> None:
    import litellm

    payload = json.dumps(
        {
            "thought": "Mumbai needs city module",
            "selected_module_ids": ["geography_city"],
        }
    )
    monkeypatch.setattr(litellm, "completion", lambda **kwargs: _choice(payload))

    turn, log = run_schema_guide_module_router_llm(
        question="Show my investors in Mumbai",
        max_modules=5,
    )
    assert "core_arn_investor" in turn.selected_module_ids
    assert "geography_city" in turn.selected_module_ids
    assert log["phase"] == "schema_guide_module_router"


def test_select_module_ids_uses_llm_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    import litellm

    from app.core.config import get_config

    get_config.cache_clear()
    monkeypatch.setenv("QUERY_GENERATOR_MODULE_ROUTER_LLM", "true")
    payload = json.dumps(
        {
            "thought": "SIP question",
            "selected_module_ids": ["sip_systematic", "holdings_schemes"],
        }
    )
    monkeypatch.setattr(litellm, "completion", lambda **kwargs: _choice(payload))

    ids, meta = select_module_ids_for_question(
        "Active SIPs above 5,000 per month in hybrid funds."
    )
    assert meta["selection_method"] == "llm"
    assert "sip_systematic" in ids
    assert "core_arn_investor" in ids


def test_select_module_ids_keyword_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import get_config

    get_config.cache_clear()
    monkeypatch.setenv("QUERY_GENERATOR_MODULE_ROUTER_LLM", "false")

    ids, meta = select_module_ids_for_question("NRI investors")
    assert meta["selection_method"] == "keyword_fallback"
    assert "tax_profile" in ids


def test_router_llm_ignores_echoed_question_key(monkeypatch: pytest.MonkeyPatch) -> None:
    import litellm

    payload = json.dumps(
        {
            "thought": "Redemption + equity",
            "selected_module_ids": ["activity_transactions", "holdings_schemes"],
            "question": "Investors who did redemption in last quarter for equity funds",
        }
    )
    monkeypatch.setattr(litellm, "completion", lambda **kwargs: _choice(payload))

    turn, _ = run_schema_guide_module_router_llm(
        question="Investors who did redemption in last quarter for equity funds",
        max_modules=5,
    )
    assert "activity_transactions" in turn.selected_module_ids
    assert "core_arn_investor" in turn.selected_module_ids


def test_keyword_router_mumbai() -> None:
    ids = select_module_ids_keyword("Show my investors in Mumbai")
    assert "geography_city" in ids
    assert "sip_systematic" not in ids
