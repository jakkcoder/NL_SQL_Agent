from app.agents.tools import (
    ask_investor_type_tool,
    detect_intent_tool,
    greeting_tool,
    unsupported_banking_tool,
    update_routing_state_tool,
)


class FakeToolContext:
    def __init__(self):
        self.state = {}


def test_greeting_tool_sets_awaiting_investor_type_state():
    tool_context = FakeToolContext()
    result = greeting_tool("hello", tool_context)

    assert result["status"] == "greeting"
    assert result["needs_clarification"] is True
    assert "Individual investors" in result["reply"]
    expected_state = {
        "current_intent": "greeting",
        "route": "greeting_tool",
        "step": "awaiting_investor_type",
        "investor_tab": "unknown",
        "last_user_message": "hello",
        "needs_clarification": True,
        "clarification_question": "Are you looking for Individual investors or Non-Individual investors?",
    }
    assert result["routing_state"] == expected_state
    assert tool_context.state["routing_state"] == expected_state


def test_update_routing_state_tool_maps_search_intent_to_search_route():
    tool_context = FakeToolContext()
    result = update_routing_state_tool(
        intent="investor_search",
        tool_context=tool_context,
        message="show individual investors",
        investor_tab="individual",
    )

    expected_state = {
        "current_intent": "investor_search",
        "route": "search_investors_tool",
        "step": "ready_to_search",
        "investor_tab": "individual",
        "last_user_message": "show individual investors",
        "needs_clarification": False,
        "clarification_question": None,
    }
    assert result["routing_state"] == expected_state
    assert result["should_call_tool"] == "search_investors_tool"
    assert tool_context.state["routing_state"] == expected_state


def test_update_routing_state_tool_supports_clarification_state():
    tool_context = FakeToolContext()
    result = update_routing_state_tool(
        intent="investor_type_clarification",
        tool_context=tool_context,
        message="show investors",
    )

    assert result["routing_state"]["route"] == "ask_investor_type_tool"
    assert result["routing_state"]["step"] == "awaiting_investor_type"
    assert tool_context.state["needs_clarification"] is True


def test_detect_intent_tool_routes_greeting_to_greeting_tool():
    tool_context = FakeToolContext()
    result = detect_intent_tool("hi", tool_context)

    assert result["should_call_tool"] == "greeting_tool"
    assert result["routing_state"]["current_intent"] == "greeting"
    assert tool_context.state["current_intent"] == "greeting"


def test_detect_intent_tool_routes_generic_investor_query_to_clarification():
    tool_context = FakeToolContext()
    result = detect_intent_tool("show investors", tool_context)

    assert result["should_call_tool"] == "ask_investor_type_tool"
    assert result["routing_state"]["step"] == "awaiting_investor_type"
    assert tool_context.state["clarification_question"]


def test_detect_intent_tool_routes_unsupported_banking_request():
    tool_context = FakeToolContext()
    result = detect_intent_tool("show my account balance", tool_context)

    assert result["should_call_tool"] == "unsupported_banking_tool"
    assert result["routing_state"]["step"] == "blocked"


def test_ask_investor_type_tool_returns_strict_clarification_output():
    tool_context = FakeToolContext()
    result = ask_investor_type_tool("show investors", tool_context)

    assert result["status"] == "clarification"
    assert result["needs_clarification"] is True
    assert result["routing_state"]["route"] == "ask_investor_type_tool"


def test_unsupported_banking_tool_returns_scoped_out_of_scope_output():
    tool_context = FakeToolContext()
    result = unsupported_banking_tool("transfer money", tool_context)

    assert result["status"] == "out_of_scope"
    assert result["routing_state"]["route"] == "unsupported_banking_tool"
