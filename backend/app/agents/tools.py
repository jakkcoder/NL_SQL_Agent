import logging
from typing import Any

logger = logging.getLogger(__name__)

try:
    from google.adk.tools import ToolContext
except ModuleNotFoundError:
    ToolContext = Any

from app.models.agent_state import AgentToolOutput, HDFC_GREETING_MESSAGE
from app.services.investor_menu_query import run_filter_dp_investor_menu_query
from app.services.routing import classify_message, read_prior_step, write_session_state


def filter_dp_investor_menu_tool(question: str, tool_context: ToolContext) -> dict[str, Any]:
    """ADK entry: function contract + user question → Sonnet strict ``filter_dp_investor_menu`` SQL."""

    prior_step = read_prior_step(tool_context.state)
    routing_state = classify_message(question, prior_step)
    write_session_state(tool_context.state, routing_state)

    result = run_filter_dp_investor_menu_query(question, tool_context.state)
    return _dump_model(result)


def generate_catalog_sql_query_tool(question: str, tool_context: ToolContext) -> dict[str, Any]:
    """Deprecated ADK name — delegates to ``filter_dp_investor_menu_tool``. Not registered on root agent."""

    return filter_dp_investor_menu_tool(question, tool_context)


def greeting_tool(message: str, tool_context: ToolContext) -> dict[str, Any]:
    """Greet the user and persist routing state for the Individual MVP."""

    routing_state = classify_message(message)
    write_session_state(tool_context.state, routing_state)
    return _dump_model(
        AgentToolOutput(
            reply=HDFC_GREETING_MESSAGE,
            needs_clarification=False,
            status="greeting",
            routing_state=routing_state,
        )
    )


def _dump_model(model: Any) -> dict[str, Any]:
    return model.model_dump(mode="json")
