import json

from app.agents.tools import (
    detect_intent_tool,
    fetch_investor_schema_contract_tool,
    greeting_tool,
    run_dynamic_investor_sql_tool,
    unsupported_banking_tool,
)
from app.core.config import get_config
from app.models.agent_state import (
    STATE_KEY_CURRENT_INTENT,
    STATE_KEY_FINAL_QUERY,
    STATE_KEY_INVESTOR_SCHEMA_CONTRACT_COMPACT,
    STATE_KEY_INVESTOR_SCHEMA_CONTRACT_META,
    STATE_KEY_INVESTOR_SCHEMA_SESSION_FETCHED,
    STATE_KEY_INVESTOR_TAB,
    STATE_KEY_LAST_SQL,
    STATE_KEY_ROUTE,
    STATE_KEY_ROUTING_STATE,
    STATE_KEY_STEP,
    STATE_KEY_TEMP_DETECTED_INTENT,
    STATE_KEY_TEMP_SHOULD_CALL_TOOL,
)
from app.services.routing import classify_message, write_session_state


class FakeToolContext:
    def __init__(self, state: dict | None = None):
        self.state = state or {}


def _mock_llm_intent(monkeypatch, payload: dict):
    class FakeMessage:
        content = json.dumps(payload)

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        choices = [FakeChoice()]

    monkeypatch.setattr(
        "app.services.intent_detection.litellm.completion",
        lambda **kwargs: FakeResponse(),
    )


def test_greeting_tool_sets_individual_ready_state():
    tool_context = FakeToolContext()
    result = greeting_tool("hello", tool_context)

    assert result["status"] == "greeting"
    assert result["needs_clarification"] is False
    assert "Individual investors" in result["reply"]
    assert tool_context.state[STATE_KEY_CURRENT_INTENT] == "greeting"
    assert tool_context.state[STATE_KEY_ROUTE] == "greeting_tool"
    assert tool_context.state[STATE_KEY_STEP] == "new"
    assert tool_context.state[STATE_KEY_INVESTOR_TAB] == "individual"


def test_detect_intent_tool_routes_greeting_and_sets_temp_keys(monkeypatch):
    _mock_llm_intent(
        monkeypatch,
        {
            "current_intent": "greeting",
            "route": "greeting_tool",
            "step": "new",
            "investor_tab": "individual",
            "needs_clarification": False,
            "clarification_question": None,
            "has_search_filters": False,
            "detected_filters": [],
        },
    )
    tool_context = FakeToolContext()
    result = detect_intent_tool("helo", tool_context)

    assert result["should_call_tool"] == "greeting_tool"
    assert result["detection_source"] == "llm"
    assert result["routing_state"]["current_intent"] == "greeting"
    assert tool_context.state[STATE_KEY_CURRENT_INTENT] == "greeting"
    assert tool_context.state[STATE_KEY_TEMP_DETECTED_INTENT] == "greeting"
    assert tool_context.state[STATE_KEY_TEMP_SHOULD_CALL_TOOL] == "greeting_tool"


def test_detect_intent_tool_routes_generic_investor_query_to_search(monkeypatch):
    _mock_llm_intent(
        monkeypatch,
        {
            "current_intent": "investor_type_clarification",
            "route": "ask_investor_type_tool",
            "step": "awaiting_investor_type",
            "investor_tab": "unknown",
            "needs_clarification": True,
            "clarification_question": "Are you looking for Individual investors or Non-Individual investors?",
            "has_search_filters": False,
            "detected_filters": [],
        },
    )
    tool_context = FakeToolContext()
    result = detect_intent_tool("show invstors", tool_context)

    assert result["should_call_tool"] == "search_investors_tool"
    assert result["routing_state"]["step"] == "ready_to_search"
    assert tool_context.state[STATE_KEY_INVESTOR_TAB] == "individual"
    assert "filter_dp_investor_menu" in tool_context.state[STATE_KEY_LAST_SQL]
    assert tool_context.state[STATE_KEY_FINAL_QUERY]["engine"] == "filter_dp_investor_menu"


def test_detect_intent_tool_does_not_seed_sql_for_greeting(monkeypatch):
    _mock_llm_intent(
        monkeypatch,
        {
            "current_intent": "greeting",
            "route": "greeting_tool",
            "step": "new",
            "investor_tab": "individual",
            "needs_clarification": False,
            "clarification_question": None,
            "has_search_filters": False,
            "detected_filters": [],
        },
    )
    tool_context = FakeToolContext()
    detect_intent_tool("hello", tool_context)

    assert STATE_KEY_LAST_SQL not in tool_context.state
    assert STATE_KEY_FINAL_QUERY not in tool_context.state


def test_detect_intent_tool_routes_unsupported_banking_request(monkeypatch):
    _mock_llm_intent(
        monkeypatch,
        {
            "current_intent": "unsupported_banking_request",
            "route": "unsupported_banking_tool",
            "step": "blocked",
            "investor_tab": "individual",
            "needs_clarification": False,
            "clarification_question": None,
            "has_search_filters": False,
            "detected_filters": [],
        },
    )
    tool_context = FakeToolContext()
    result = detect_intent_tool("show my account balnce", tool_context)

    assert result["should_call_tool"] == "unsupported_banking_tool"
    assert result["routing_state"]["step"] == "blocked"


def test_detect_intent_tool_treats_individual_reply_as_search(monkeypatch):
    _mock_llm_intent(
        monkeypatch,
        {
            "current_intent": "investor_search",
            "route": "search_investors_tool",
            "step": "ready_to_search",
            "investor_tab": "individual",
            "needs_clarification": False,
            "clarification_question": None,
            "has_search_filters": False,
            "detected_filters": [],
        },
    )
    result = detect_intent_tool("individual", FakeToolContext())

    assert result["has_search_filters"] is False
    assert result["should_call_tool"] == "search_investors_tool"
    assert result["routing_state"]["investor_tab"] == "individual"


def test_detect_intent_tool_routes_filtered_query_to_analyze(monkeypatch):
    _mock_llm_intent(
        monkeypatch,
        {
            "current_intent": "investor_search",
            "route": "analyze_search_arguments_tool",
            "step": "ready_to_search",
            "investor_tab": "individual",
            "needs_clarification": False,
            "clarification_question": None,
            "has_search_filters": True,
            "detected_filters": ["OTM=Y"],
        },
    )
    tool_context = FakeToolContext()
    result = detect_intent_tool("show active individual with otm", tool_context)

    assert result["has_search_filters"] is True
    assert result["should_call_tool"] == "analyze_search_arguments_tool"
    assert "filter_dp_investor_menu" in tool_context.state[STATE_KEY_LAST_SQL]


def test_detect_intent_tool_falls_back_when_llm_unavailable(monkeypatch):
    monkeypatch.setattr(
        "app.services.intent_detection.litellm.completion",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("down")),
    )
    tool_context = FakeToolContext()
    result = detect_intent_tool("hi", tool_context)

    assert result["detection_source"] == "fallback"
    assert result["should_call_tool"] == "greeting_tool"


def test_unsupported_banking_tool_returns_scoped_out_of_scope_output():
    tool_context = FakeToolContext()
    result = unsupported_banking_tool("transfer money", tool_context)

    assert result["status"] == "out_of_scope"
    assert result["routing_state"]["route"] == "unsupported_banking_tool"


def test_write_session_state_persists_flat_adk_keys():
    session_state: dict = {}
    routing_state = classify_message("show individual investors with otm")

    write_session_state(session_state, routing_state)

    assert session_state[STATE_KEY_CURRENT_INTENT] == "investor_search"
    assert session_state[STATE_KEY_ROUTE] == "analyze_search_arguments_tool"
    assert session_state[STATE_KEY_ROUTING_STATE]["current_intent"] == "investor_search"


def test_fetch_investor_schema_contract_tool_writes_compact_schema(monkeypatch):
    tool_context = FakeToolContext()
    result = fetch_investor_schema_contract_tool(tool_context)

    assert result["status"] == "ok"
    assert tool_context.state[STATE_KEY_INVESTOR_SCHEMA_SESSION_FETCHED] is True
    assert STATE_KEY_INVESTOR_SCHEMA_CONTRACT_COMPACT in tool_context.state
    assert tool_context.state[STATE_KEY_INVESTOR_SCHEMA_CONTRACT_META]["source"] in (
        "packaged_file",
        "live_auto",
    )


def test_fetch_investor_schema_contract_tool_skips_when_already_fetched():
    tool_context = FakeToolContext()
    tool_context.state[STATE_KEY_INVESTOR_SCHEMA_SESSION_FETCHED] = True
    tool_context.state[STATE_KEY_INVESTOR_SCHEMA_CONTRACT_COMPACT] = {
        "contract_kind": "investor_schema_compact",
        "table_count": 3,
        "column_count": 10,
        "tables": [],
    }
    result = fetch_investor_schema_contract_tool(tool_context, force=False)
    assert result["status"] == "ok"
    assert "skipped" in result["message"].lower()
    assert result["session_state_keys_written"] == []


def test_run_dynamic_investor_sql_tool_disabled(monkeypatch):
    monkeypatch.setenv("DYNAMIC_INVESTOR_SQL_ENABLED", "false")
    get_config.cache_clear()
    tool_context = FakeToolContext()
    result = run_dynamic_investor_sql_tool("count investors by city", tool_context)
    get_config.cache_clear()

    assert result["status"] == "error"
    assert "disabled" in result["reply"].lower()


def test_run_dynamic_investor_sql_tool_success_path(monkeypatch):
    monkeypatch.setenv("DYNAMIC_INVESTOR_SQL_ENABLED", "true")
    monkeypatch.setenv("DEV_DATABASE_URL", "postgresql://u:p@127.0.0.1:5432/db")
    get_config.cache_clear()

    class FakePg:
        def __init__(self, *args, **kwargs):
            pass

        def open(self):
            return None

        def close(self):
            return None

    monkeypatch.setattr("app.agents.tools.PostgresClient", FakePg)

    def fake_run(**kwargs):
        return {
            "ok": True,
            "attempts": 1,
            "final_sql": "SELECT 1 WHERE arn_code = %s LIMIT 5",
            "parameters": [kwargs["trusted_arn"]],
            "rows": [{"broker_code": kwargs["trusted_arn"], "cnt": 3}],
            "trace": [],
            "error": None,
        }

    monkeypatch.setattr("app.agents.tools.run_react_dynamic_sql", fake_run)

    tool_context = FakeToolContext()
    result = run_dynamic_investor_sql_tool("how many investors", tool_context)
    get_config.cache_clear()

    assert result["status"] == "ok"
    assert result["count"] == 1
    assert "cnt=3" in result["reply"] or "3" in result["reply"]
