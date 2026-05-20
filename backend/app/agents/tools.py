from typing import Any

try:
    from google.adk.tools import ToolContext
except ModuleNotFoundError:
    ToolContext = Any

from app.core.config import AppConfig, get_config
from app.db.postgres import DatabaseNotConfiguredError, PostgresClient
from app.models.agent_state import (
    AgentToolOutput,
    IntentDetectionOutput,
    PageMeta,
    RoutingIntent,
    RoutingRoute,
    RoutingState,
    RoutingStep,
)
from app.models.chat import ChatMessage
from app.models.search_plan import InvestorTab
from app.services.audit import AuditLogger
from app.services.individual_executor import IndividualInvestorExecutor
from app.services.intent_parser import parse_investor_search_intent
from app.services.non_individual_executor import NonIndividualInvestorExecutor
from app.services.plan_validator import PlanValidator
from app.services.result_formatter import format_rows_for_chat

GREETING_TERMS = {
    "hi",
    "hello",
    "hey",
    "good morning",
    "good afternoon",
    "good evening",
    "namaste",
}

UNSUPPORTED_BANKING_TERMS = {
    "account balance",
    "balance",
    "statement",
    "transaction",
    "transfer",
    "payment",
    "loan",
    "card",
    "credit card",
    "debit card",
    "kyc update",
    "service request",
}

INVESTOR_SEARCH_TERMS = {
    "investor",
    "investors",
    "individual",
    "non individual",
    "non-individual",
    "corporate",
    "otm",
    "mandate",
    "active",
    "dormant",
    "cgf",
    "minor",
    "holding",
    "sip",
    "stp",
    "swp",
}

INVESTOR_TYPE_CLARIFICATION = "Are you looking for Individual investors or Non-Individual investors?"


def detect_intent_tool(message: str, tool_context: ToolContext) -> dict[str, Any]:
    """Classify the user message and persist the routing decision in session state."""

    normalized_message = _normalize_message(message)
    if normalized_message in GREETING_TERMS:
        routing_state = RoutingState(
            current_intent=RoutingIntent.GREETING,
            route=RoutingRoute.GREETING_TOOL,
            step=RoutingStep.AWAITING_INVESTOR_TYPE,
            investor_tab=InvestorTab.UNKNOWN,
            last_user_message=message,
            needs_clarification=True,
            clarification_question=INVESTOR_TYPE_CLARIFICATION,
        )
    elif _is_unsupported_banking_request(normalized_message):
        routing_state = RoutingState(
            current_intent=RoutingIntent.UNSUPPORTED_BANKING_REQUEST,
            route=RoutingRoute.UNSUPPORTED_BANKING_TOOL,
            step=RoutingStep.BLOCKED,
            investor_tab=InvestorTab.UNKNOWN,
            last_user_message=message,
        )
    elif _needs_investor_type_clarification(normalized_message):
        routing_state = RoutingState(
            current_intent=RoutingIntent.INVESTOR_TYPE_CLARIFICATION,
            route=RoutingRoute.ASK_INVESTOR_TYPE_TOOL,
            step=RoutingStep.AWAITING_INVESTOR_TYPE,
            investor_tab=InvestorTab.UNKNOWN,
            last_user_message=message,
            needs_clarification=True,
            clarification_question=INVESTOR_TYPE_CLARIFICATION,
        )
    elif _is_investor_search_request(normalized_message):
        investor_tab = _infer_investor_tab(normalized_message)
        routing_state = RoutingState(
            current_intent=RoutingIntent.INVESTOR_SEARCH,
            route=RoutingRoute.SEARCH_INVESTORS_TOOL,
            step=RoutingStep.READY_TO_SEARCH,
            investor_tab=investor_tab,
            last_user_message=message,
        )
    else:
        routing_state = RoutingState(
            current_intent=RoutingIntent.UNSUPPORTED_BANKING_REQUEST,
            route=RoutingRoute.UNSUPPORTED_BANKING_TOOL,
            step=RoutingStep.BLOCKED,
            investor_tab=InvestorTab.UNKNOWN,
            last_user_message=message,
        )

    _write_routing_state(tool_context, routing_state)
    return _dump_model(
        IntentDetectionOutput(
            routing_state=routing_state,
            should_call_tool=routing_state.route,
        )
    )


def greeting_tool(message: str, tool_context: ToolContext) -> dict[str, Any]:
    """Greet the user and persist the next expected routing step."""

    routing_state = RoutingState(
        current_intent=RoutingIntent.GREETING,
        route=RoutingRoute.GREETING_TOOL,
        step=RoutingStep.AWAITING_INVESTOR_TYPE,
        investor_tab=InvestorTab.UNKNOWN,
        last_user_message=message,
        needs_clarification=True,
        clarification_question=INVESTOR_TYPE_CLARIFICATION,
    )
    _write_routing_state(tool_context, routing_state)
    return _dump_model(
        AgentToolOutput(
            reply=(
                "Hello. I can help you search distributor investors. "
                f"{INVESTOR_TYPE_CLARIFICATION}"
            ),
            needs_clarification=True,
            status="greeting",
            routing_state=routing_state,
        )
    )


def ask_investor_type_tool(message: str, tool_context: ToolContext) -> dict[str, Any]:
    """Ask the required investor-type clarification and persist that state."""

    routing_state = RoutingState(
        current_intent=RoutingIntent.INVESTOR_TYPE_CLARIFICATION,
        route=RoutingRoute.ASK_INVESTOR_TYPE_TOOL,
        step=RoutingStep.AWAITING_INVESTOR_TYPE,
        investor_tab=InvestorTab.UNKNOWN,
        last_user_message=message,
        needs_clarification=True,
        clarification_question=INVESTOR_TYPE_CLARIFICATION,
    )
    _write_routing_state(tool_context, routing_state)
    return _dump_model(
        AgentToolOutput(
            reply=INVESTOR_TYPE_CLARIFICATION,
            needs_clarification=True,
            status="clarification",
            routing_state=routing_state,
        )
    )


def unsupported_banking_tool(message: str, tool_context: ToolContext) -> dict[str, Any]:
    """Return a scoped unsupported response for banking requests outside MVP."""

    routing_state = RoutingState(
        current_intent=RoutingIntent.UNSUPPORTED_BANKING_REQUEST,
        route=RoutingRoute.UNSUPPORTED_BANKING_TOOL,
        step=RoutingStep.BLOCKED,
        investor_tab=InvestorTab.UNKNOWN,
        last_user_message=message,
    )
    _write_routing_state(tool_context, routing_state)
    return _dump_model(
        AgentToolOutput(
            reply=(
                "I can help only with distributor investor search in this MVP. "
                "Please ask for Individual or Non-Individual investor search."
            ),
            status="out_of_scope",
            routing_state=routing_state,
        )
    )


def update_routing_state_tool(
    intent: RoutingIntent,
    tool_context: ToolContext,
    message: str = "",
    investor_tab: str = "unknown",
    awaiting: str = "",
) -> dict[str, Any]:
    """Persist an explicit routing-state snapshot for root-agent handoffs."""

    routing_intent = RoutingIntent(intent)
    route_by_intent = {
        RoutingIntent.GREETING: RoutingRoute.GREETING_TOOL,
        RoutingIntent.INVESTOR_SEARCH: RoutingRoute.SEARCH_INVESTORS_TOOL,
        RoutingIntent.INVESTOR_TYPE_CLARIFICATION: RoutingRoute.ASK_INVESTOR_TYPE_TOOL,
        RoutingIntent.UNSUPPORTED_BANKING_REQUEST: RoutingRoute.UNSUPPORTED_BANKING_TOOL,
    }
    step_by_intent = {
        RoutingIntent.GREETING: RoutingStep.AWAITING_INVESTOR_TYPE,
        RoutingIntent.INVESTOR_SEARCH: RoutingStep.READY_TO_SEARCH,
        RoutingIntent.INVESTOR_TYPE_CLARIFICATION: RoutingStep.AWAITING_INVESTOR_TYPE,
        RoutingIntent.UNSUPPORTED_BANKING_REQUEST: RoutingStep.BLOCKED,
    }
    routing_state = RoutingState(
        current_intent=routing_intent,
        route=route_by_intent[routing_intent],
        step=awaiting or step_by_intent[routing_intent],
        investor_tab=InvestorTab(investor_tab),
        last_user_message=message,
        needs_clarification=routing_intent
        in {RoutingIntent.GREETING, RoutingIntent.INVESTOR_TYPE_CLARIFICATION},
        clarification_question=(
            INVESTOR_TYPE_CLARIFICATION
            if routing_intent in {RoutingIntent.GREETING, RoutingIntent.INVESTOR_TYPE_CLARIFICATION}
            else None
        ),
    )
    _write_routing_state(tool_context, routing_state)
    return _dump_model(IntentDetectionOutput(routing_state=routing_state, should_call_tool=routing_state.route))


def parse_with_context(
    query: str,
    messages: list[ChatMessage],
    page_limit: int,
    page_offset: int,
) -> dict[str, Any]:
    """Backend helper that mirrors the ADK tool's deterministic parsing contract."""

    plan = parse_investor_search_intent(
        query=query,
        messages=messages,
        page_limit=page_limit,
        page_offset=page_offset,
    )
    validation = PlanValidator().validate(plan)
    return {
        "plan": plan,
        "validation": validation,
    }


def search_investors_tool(
    query: str,
    tool_context: ToolContext,
    arn_code: str = "",
    page_limit: int = 0,
    page_offset: int = 0,
) -> dict[str, Any]:
    """Parse, validate, execute, and format an investor search request.

    Args:
        query: Distributor's natural-language investor search request.
        arn_code: Distributor ARN. Leave empty to use the configured local default.
        page_limit: Optional page size. Use 0 to apply the configured default.
        page_offset: Optional result offset. Use 0 for the first page.
    """

    config = get_config()
    limit = page_limit or config.search.default_page_limit
    offset = page_offset or 0
    parsed = parse_with_context(
        query=query,
        messages=[],
        page_limit=limit,
        page_offset=offset,
    )
    plan = parsed["plan"]
    validation = parsed["validation"]
    effective_arn = arn_code or config.search.default_dev_arn
    routing_state = RoutingState(
        current_intent=RoutingIntent.INVESTOR_SEARCH,
        route=RoutingRoute.SEARCH_INVESTORS_TOOL,
        step=RoutingStep.EXECUTING_SEARCH,
        investor_tab=plan.investor_tab,
        last_user_message=query,
    )
    _write_routing_state(tool_context, routing_state)

    AuditLogger().log_event(
        "search_plan",
        {
            "investor_tab": plan.investor_tab.value,
            "validation_status": validation.status,
            "arn_code": effective_arn,
        },
    )

    if not validation.can_execute:
        clarification_needed = validation.status == "clarification"
        blocked_state = RoutingState(
            current_intent=(
                RoutingIntent.INVESTOR_TYPE_CLARIFICATION
                if clarification_needed
                else RoutingIntent.UNSUPPORTED_BANKING_REQUEST
            ),
            route=(
                RoutingRoute.ASK_INVESTOR_TYPE_TOOL
                if clarification_needed
                else RoutingRoute.UNSUPPORTED_BANKING_TOOL
            ),
            step=RoutingStep.AWAITING_INVESTOR_TYPE if clarification_needed else RoutingStep.BLOCKED,
            investor_tab=plan.investor_tab,
            last_user_message=query,
            needs_clarification=clarification_needed,
            clarification_question=validation.message if clarification_needed else None,
        )
        _write_routing_state(tool_context, blocked_state)
        return _dump_model(
            AgentToolOutput(
                reply=validation.message or "I need more information before searching.",
                needs_clarification=clarification_needed,
                status=validation.status,
                routing_state=blocked_state,
            )
        )

    db_config = config.database
    db = PostgresClient(
        config.database_url_value,
        db_config.statement_timeout_ms,
        min_size=db_config.pool_min_size,
        max_size=db_config.pool_max_size,
    )
    try:
        db.open()
        rows = _execute_search(db, config, plan, effective_arn)
    except DatabaseNotConfiguredError as exc:
        error_state = RoutingState(
            current_intent=RoutingIntent.INVESTOR_SEARCH,
            route=RoutingRoute.SEARCH_INVESTORS_TOOL,
            step=RoutingStep.BLOCKED,
            investor_tab=plan.investor_tab,
            last_user_message=query,
        )
        _write_routing_state(tool_context, error_state)
        return _dump_model(
            AgentToolOutput(
                reply=str(exc),
                status="error",
                routing_state=error_state,
            )
        )
    finally:
        db.close()

    completed_state = RoutingState(
        current_intent=RoutingIntent.INVESTOR_SEARCH,
        route=RoutingRoute.SEARCH_INVESTORS_TOOL,
        step=RoutingStep.COMPLETED,
        investor_tab=plan.investor_tab,
        last_user_message=query,
    )
    _write_routing_state(tool_context, completed_state)
    return _dump_model(
        AgentToolOutput(
            reply=format_rows_for_chat(rows, plan.page_limit, plan.page_offset),
            rows=_json_safe(rows),
            count=len(rows),
            page=PageMeta(limit=plan.page_limit, offset=plan.page_offset),
            status="ok",
            routing_state=completed_state,
        )
    )


def _normalize_message(message: str) -> str:
    return " ".join(message.strip().lower().rstrip(".,!?").split())


def _is_unsupported_banking_request(normalized_message: str) -> bool:
    return any(term in normalized_message for term in UNSUPPORTED_BANKING_TERMS)


def _is_investor_search_request(normalized_message: str) -> bool:
    return any(term in normalized_message for term in INVESTOR_SEARCH_TERMS)


def _needs_investor_type_clarification(normalized_message: str) -> bool:
    mentions_investor_search = "investor" in normalized_message or "investors" in normalized_message
    mentions_investor_tab = _infer_investor_tab(normalized_message) != InvestorTab.UNKNOWN
    return mentions_investor_search and not mentions_investor_tab


def _infer_investor_tab(normalized_message: str) -> InvestorTab:
    if "non individual" in normalized_message or "non-individual" in normalized_message:
        return InvestorTab.NON_INDIVIDUAL
    if "corporate" in normalized_message:
        return InvestorTab.NON_INDIVIDUAL
    if "individual" in normalized_message:
        return InvestorTab.INDIVIDUAL
    return InvestorTab.UNKNOWN


def _write_routing_state(tool_context: ToolContext, routing_state: RoutingState) -> None:
    routing_state_json = _dump_model(routing_state)
    tool_context.state["routing_state"] = routing_state_json
    tool_context.state["current_intent"] = routing_state_json["current_intent"]
    tool_context.state["route"] = routing_state_json["route"]
    tool_context.state["step"] = routing_state_json["step"]
    tool_context.state["investor_tab"] = routing_state_json["investor_tab"]
    tool_context.state["last_user_message"] = routing_state_json["last_user_message"]
    tool_context.state["needs_clarification"] = routing_state_json["needs_clarification"]
    tool_context.state["clarification_question"] = routing_state_json["clarification_question"]


def _dump_model(model) -> dict[str, Any]:
    return model.model_dump(mode="json")


def _execute_search(db: PostgresClient, config: AppConfig, plan, arn_code: str) -> list[dict[str, Any]]:
    if plan.investor_tab == InvestorTab.INDIVIDUAL:
        return IndividualInvestorExecutor(db).execute(plan, arn_code)
    if plan.investor_tab == InvestorTab.NON_INDIVIDUAL:
        return NonIndividualInvestorExecutor(db, config).execute(plan, arn_code)
    return []


def _json_safe(value):
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)
