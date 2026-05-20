from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.search_plan import InvestorTab


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
    investor_tab: InvestorTab = InvestorTab.UNKNOWN
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
