import json

import pytest

from app.models.agent_state import IntentDetectionLLMOutput
from app.services.intent_detection import _llm_output_to_routing_state, detect_routing_intent
from app.services.llm_json import parse_json_content


def test_parse_json_content_strips_markdown_fence():
    raw = '```json\n{"current_intent": "greeting"}\n```'
    parsed = parse_json_content(raw)
    assert parsed["current_intent"] == "greeting"


def test_llm_output_to_routing_state_normalizes_greeting():
    llm_output = IntentDetectionLLMOutput.model_validate(
        {
            "current_intent": "greeting",
            "route": "greeting_tool",
            "step": "new",
            "investor_tab": "individual",
            "needs_clarification": False,
            "clarification_question": None,
            "has_search_filters": False,
            "detected_filters": [],
        }
    )
    routing_state = _llm_output_to_routing_state(llm_output, "helo")

    assert routing_state.current_intent == "greeting"
    assert routing_state.route == "greeting_tool"
    assert routing_state.investor_tab == "individual"
    assert routing_state.needs_clarification is False


def test_detect_routing_intent_uses_llm_response(monkeypatch):
    llm_json = {
        "current_intent": "investor_search",
        "route": "search_investors_tool",
        "step": "ready_to_search",
        "investor_tab": "individual",
        "needs_clarification": False,
        "clarification_question": None,
        "has_search_filters": False,
        "detected_filters": [],
    }

    class FakeMessage:
        content = json.dumps(llm_json)

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        choices = [FakeChoice()]

    monkeypatch.setattr(
        "app.services.intent_detection.litellm.completion",
        lambda **kwargs: FakeResponse(),
    )

    routing_state, source, has_filters, _ = detect_routing_intent("show individul investors", {})

    assert source == "llm"
    assert routing_state.current_intent == "investor_search"
    assert routing_state.route == "search_investors_tool"
    assert routing_state.investor_tab == "individual"
    assert has_filters is False


def test_detect_routing_intent_accepts_llm_json_without_step(monkeypatch):
    """Some models omit ``step``; Pydantic must not fail and routing must still work."""

    llm_json = {
        "current_intent": "investor_search",
        "route": "search_investors_tool",
        "investor_tab": "individual",
        "needs_clarification": False,
        "clarification_question": None,
        "has_search_filters": False,
        "detected_filters": [],
    }

    class FakeMessage:
        content = json.dumps(llm_json)

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        choices = [FakeChoice()]

    monkeypatch.setattr(
        "app.services.intent_detection.litellm.completion",
        lambda **kwargs: FakeResponse(),
    )

    routing_state, source, _, _ = detect_routing_intent("show my investors", {})

    assert source == "llm"
    assert routing_state.current_intent == "investor_search"
    assert routing_state.step == "ready_to_search"


def test_detect_routing_intent_routes_filtered_search_to_analyze_tool(monkeypatch):
    llm_json = {
        "current_intent": "investor_search",
        "route": "analyze_search_arguments_tool",
        "step": "ready_to_search",
        "investor_tab": "individual",
        "needs_clarification": False,
        "clarification_question": None,
        "has_search_filters": True,
        "detected_filters": ["OTM=Y", "Investor Type=ACTIVE"],
    }

    class FakeMessage:
        content = json.dumps(llm_json)

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        choices = [FakeChoice()]

    monkeypatch.setattr(
        "app.services.intent_detection.litellm.completion",
        lambda **kwargs: FakeResponse(),
    )

    routing_state, _, has_filters, detected = detect_routing_intent(
        "show active individul invstors with otm",
        {},
    )

    assert has_filters is True
    assert routing_state.route == "analyze_search_arguments_tool"
    assert detected == ["OTM=Y", "Investor Type=ACTIVE"]


def test_detect_routing_intent_overrides_llm_clarification_for_show_investors(monkeypatch):
    llm_json = {
        "current_intent": "investor_type_clarification",
        "route": "ask_investor_type_tool",
        "step": "awaiting_investor_type",
        "investor_tab": "unknown",
        "needs_clarification": True,
        "clarification_question": "Are you looking for Individual investors or Non-Individual investors?",
        "has_search_filters": False,
        "detected_filters": [],
    }

    class FakeMessage:
        content = json.dumps(llm_json)

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        choices = [FakeChoice()]

    monkeypatch.setattr(
        "app.services.intent_detection.litellm.completion",
        lambda **kwargs: FakeResponse(),
    )

    routing_state, source, has_filters, _ = detect_routing_intent("show investors", {})

    assert routing_state.current_intent == "investor_search"
    assert routing_state.route == "search_investors_tool"
    assert routing_state.investor_tab == "individual"
    assert has_filters is False


def test_detect_routing_intent_falls_back_when_llm_fails(monkeypatch):
    def _raise(**kwargs):
        raise RuntimeError("LLM unavailable")

    monkeypatch.setattr("app.services.intent_detection.litellm.completion", _raise)

    routing_state, source, has_filters, _ = detect_routing_intent("hi", {})

    assert source == "fallback"
    assert routing_state.current_intent == "greeting"
    assert routing_state.route == "greeting_tool"
    assert has_filters is False
