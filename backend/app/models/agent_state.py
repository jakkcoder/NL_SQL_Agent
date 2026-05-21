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
STATE_KEY_LAST_SEARCH_PLAN = "last_search_plan"
STATE_KEY_LAST_NORMALIZED_QUERY = "last_normalized_query"
STATE_KEY_PLAN_SOURCE = "plan_source"
STATE_KEY_QUERY_ARGUMENTS = "query_arguments"
STATE_KEY_FINAL_QUERY = "final_query"
# Top-level copies of final_query.sql / parameters for ADK session UI visibility
STATE_KEY_LAST_SQL = "last_sql"
STATE_KEY_LAST_SQL_PARAMETERS = "last_sql_parameters"
STATE_KEY_PLAN_QUERY = "plan_query"
STATE_KEY_PLAN_VALIDATION_STATUS = "plan_validation_status"
# Compact investor DB schema (live fetch via tool, or derived from packaged JSON)
STATE_KEY_INVESTOR_SCHEMA_CONTRACT_COMPACT = "investor_schema_contract_compact"
STATE_KEY_INVESTOR_SCHEMA_CONTRACT_META = "investor_schema_contract_meta"
STATE_KEY_INVESTOR_SCHEMA_SESSION_FETCHED = "investor_schema_session_fetched"

# Invocation-scoped keys (ADK temp: prefix; not persisted across turns).
STATE_KEY_TEMP_DETECTED_INTENT = "temp:detected_intent"
STATE_KEY_TEMP_SHOULD_CALL_TOOL = "temp:should_call_tool"
STATE_KEY_HAS_SEARCH_FILTERS = "has_search_filters"

HDFC_GREETING_MESSAGE = (
    "Hi, I am a chatbot from HDFC Mutual Fund. "
    "I can help you search Individual investors. "
    "Tell me what you are looking for—for example, show my investors, "
    "investors with SIP, or active investors with OTM."
)

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


class IntentDetectionLLMOutput(StrictSchemaModel):
    """Strict JSON contract returned by the detect-intent LLM classifier."""

    current_intent: RoutingIntent
    route: RoutingRoute
    step: RoutingStep | None = Field(
        default=None,
        description=(
            "Conversation step from the LLM. Some models omit this key; the backend "
            "then derives step from ``current_intent`` before building ``RoutingState``."
        ),
    )
    investor_tab: InvestorTab = InvestorTab.INDIVIDUAL
    needs_clarification: bool = False
    clarification_question: str | None = None
    has_search_filters: bool = False
    detected_filters: list[str] = Field(default_factory=list)


class IntentDetectionOutput(StrictSchemaModel):
    status: Literal["ok"] = "ok"
    routing_state: RoutingState
    should_call_tool: RoutingRoute
    has_search_filters: bool = False
    detected_filters: list[str] = Field(default_factory=list)
    detection_source: Literal["llm", "fallback", "individual_only"] = "llm"


PlanValidationStatus = Literal["valid", "clarification", "out_of_scope"]


class SearchArgumentsAnalysisOutput(StrictSchemaModel):
    """Strict JSON from analyze_search_arguments_tool for the query engine."""

    status: Literal["ok"] = "ok"
    validation_status: PlanValidationStatus
    can_execute: bool
    normalized_query: str
    plan_source: Literal["llm", "fallback"]
    search_plan: dict[str, Any]
    query_arguments: dict[str, Any]
    filters_applied: list[str] = Field(default_factory=list)
    message: str | None = None


class InvestorSchemaFetchToolOutput(StrictSchemaModel):
    """Result of fetch_investor_schema_contract_tool (live schema snapshot for session)."""

    status: Literal["ok", "error"] = "ok"
    source: str | None = None
    message: str | None = None
    table_count: int = 0
    column_count: int = 0
    session_state_keys_written: list[str] = Field(default_factory=list)
