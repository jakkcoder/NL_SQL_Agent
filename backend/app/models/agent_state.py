"""Strict schemas for root-agent routing state and tool responses."""

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.search_plan import InvestorTab

# ADK session.state keys (flat keys for instruction injection).
STATE_KEY_ROUTING_STATE = "routing_state"
STATE_KEY_CURRENT_INTENT = "current_intent"
STATE_KEY_ROUTE = "route"
STATE_KEY_STEP = "step"
STATE_KEY_INVESTOR_TAB = "investor_tab"
STATE_KEY_LAST_MESSAGE = "last_user_message"
STATE_KEY_NEEDS_CLARIFICATION = "needs_clarification"
STATE_KEY_CLARIFICATION_QUESTION = "clarification_question"
STATE_KEY_FINAL_QUERY = "final_query"
# Top-level copies of final_query.sql / parameters for ADK session UI visibility
STATE_KEY_LAST_SQL = "last_sql"
STATE_KEY_LAST_SQL_PARAMETERS = "last_sql_parameters"
# Catalog SQL generator — append-only trace + last payload
STATE_KEY_QUERY_FLOW_TRACE = "query_flow_trace"
STATE_KEY_QUERY_GENERATOR_LAST = "catalog_query_generator_last"
STATE_KEY_QUERY_FLOW_LAST_ROUTE = "query_flow_last_route"

# Invocation-scoped keys (ADK temp: prefix; not persisted across turns).
STATE_KEY_TEMP_DETECTED_INTENT = "temp:detected_intent"
STATE_KEY_TEMP_SHOULD_CALL_TOOL = "temp:should_call_tool"
STATE_KEY_HAS_SEARCH_FILTERS = "has_search_filters"

def _default_greeting_message() -> str:
    from app.services.investor_capability import build_capability_greeting

    return build_capability_greeting()


HDFC_GREETING_MESSAGE = _default_greeting_message()

NON_INDIVIDUAL_NOT_SUPPORTED = (
    "Non-Individual investor search is not available in this MVP. "
    "I can help with Individual investor search only."
)


class StrictSchemaModel(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class RoutingIntent(str, Enum):
    GREETING = "greeting"
    INVESTOR_SEARCH = "investor_search"
    INVESTOR_TYPE_CLARIFICATION = "investor_type_clarification"
    UNSUPPORTED_BANKING_REQUEST = "unsupported_banking_request"


class RoutingRoute(str, Enum):
    GREETING_TOOL = "greeting_tool"
    ASK_INVESTOR_TYPE_TOOL = "ask_investor_type_tool"
    ANALYZE_SEARCH_ARGUMENTS_TOOL = "analyze_search_arguments_tool"
    SEARCH_INVESTORS_TOOL = "search_investors_tool"
    UNSUPPORTED_BANKING_TOOL = "unsupported_banking_tool"


class RoutingStep(str, Enum):
    NEW = "new"
    AWAITING_INVESTOR_TYPE = "awaiting_investor_type"
    READY_TO_SEARCH = "ready_to_search"
    EXECUTING_SEARCH = "executing_search"
    COMPLETED = "completed"
    BLOCKED = "blocked"


class RoutingState(StrictSchemaModel):
    current_intent: RoutingIntent
    route: RoutingRoute
    step: RoutingStep
    investor_tab: InvestorTab = InvestorTab.INDIVIDUAL
    last_user_message: str = ""
    needs_clarification: bool = False
    clarification_question: str | None = None


class PageMeta(StrictSchemaModel):
    limit: int
    offset: int


ToolStatus = Literal["ok", "greeting", "clarification", "out_of_scope", "error"]


class AgentToolOutput(StrictSchemaModel):
    reply: str
    needs_clarification: bool = False
    rows: list[dict[str, Any]] = Field(default_factory=list)
    count: int = 0
    page: PageMeta | None = None
    status: ToolStatus = "ok"
    routing_state: RoutingState
    warnings: list[str] = Field(default_factory=list)


class IntentDetectionOutput(StrictSchemaModel):
    status: Literal["ok"] = "ok"
    routing_state: RoutingState
    should_call_tool: RoutingRoute
    has_search_filters: bool = False
    detected_filters: list[str] = Field(default_factory=list)
    detection_source: Literal["llm", "fallback", "individual_only"] = "llm"


class GenerateCatalogSqlToolOutput(StrictSchemaModel):
    """Result of ``generate_catalog_sql_query_tool`` (generate, optional execute, optional one retry)."""

    status: Literal["ok", "error", "blocked", "out_of_scope"] = "ok"
    reply: str
    thought: str | None = None
    sql: str | None = None
    parameters: list[Any] = Field(default_factory=list)
    row_count: int = 0
    count: int = 0
    rows: list[dict[str, Any]] = Field(default_factory=list)
    executed: bool = False
    sql_retry_used: bool = False
    generator_model: str = ""
    validation_error: str | None = None
    execute_error: str | None = None
