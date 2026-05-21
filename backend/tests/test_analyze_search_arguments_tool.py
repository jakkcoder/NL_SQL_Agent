import json

from app.agents.tools import analyze_search_arguments_tool
from app.models.agent_state import (
    STATE_KEY_FINAL_QUERY,
    STATE_KEY_LAST_SQL,
    STATE_KEY_QUERY_ARGUMENTS,
)


class FakeToolContext:
    def __init__(self, state: dict | None = None):
        self.state = state or {}


def test_analyze_search_arguments_tool_returns_engine_json(monkeypatch):
    llm_json = {
        "investor_tab": "individual",
        "normalized_query": "Show active individual investors with OTM named Rahul",
        "name_search": "rahul",
        "eligibility": "ALL",
        "individual_otm": "Y",
        "non_individual_otm": "ALL",
        "investor_type": "ACTIVE",
        "investor_subtypes": [],
        "holding_mode": "ALL",
        "systematic_mode": "ALL",
        "systematic_plans": [],
        "activity_mode": "ALL",
        "activity_types": [],
        "activity_duration": "1 month",
        "unsupported_reasons": [],
    }

    class FakeMessage:
        content = json.dumps(llm_json)

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        choices = [FakeChoice()]

    monkeypatch.setattr(
        "app.services.search_plan_builder.litellm.completion",
        lambda **kwargs: FakeResponse(),
    )

    tool_context = FakeToolContext()
    result = analyze_search_arguments_tool(
        "show active individul invstors with otm named rahul",
        tool_context,
    )

    assert result["can_execute"] is True
    assert result["query_arguments"]["engine"] == "filter_dp_investor_menu"
    assert result["query_arguments"]["parameters"]["otm"] == "Y"
    assert result["query_arguments"]["parameters"]["search_text"] == "rahul"
    assert tool_context.state[STATE_KEY_QUERY_ARGUMENTS]["engine"] == "filter_dp_investor_menu"
    assert tool_context.state[STATE_KEY_FINAL_QUERY]["engine"] == "filter_dp_investor_menu"
    assert "filter_dp_investor_menu" in tool_context.state[STATE_KEY_FINAL_QUERY]["sql"]
    assert tool_context.state[STATE_KEY_LAST_SQL] == tool_context.state[STATE_KEY_FINAL_QUERY]["sql"]
