"""Deterministic routing helpers for the investor-search root agent (Individual MVP)."""

from typing import Any

from app.models.agent_state import (
    HDFC_GREETING_MESSAGE,
    NON_INDIVIDUAL_NOT_SUPPORTED,
    RoutingIntent,
    RoutingRoute,
    RoutingState,
    RoutingStep,
    STATE_KEY_CLARIFICATION_QUESTION,
    STATE_KEY_CURRENT_INTENT,
    STATE_KEY_HAS_SEARCH_FILTERS,
    STATE_KEY_INVESTOR_TAB,
    STATE_KEY_LAST_MESSAGE,
    STATE_KEY_NEEDS_CLARIFICATION,
    STATE_KEY_ROUTE,
    STATE_KEY_ROUTING_STATE,
    STATE_KEY_STEP,
    STATE_KEY_TEMP_DETECTED_INTENT,
    STATE_KEY_TEMP_SHOULD_CALL_TOOL,
)
from app.models.search_plan import InvestorTab
from app.services.filter_detection import message_has_search_filters

GREETING_TERMS = frozenset(
    {
        "hi",
        "hello",
        "hey",
        "good morning",
        "good afternoon",
        "good evening",
        "namaste",
    }
)

UNSUPPORTED_BANKING_TERMS = frozenset(
    {
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
)

INVESTOR_SEARCH_TERMS = frozenset(
    {
        "investor",
        "investors",
        "individual",
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
)

DEFAULT_INVESTOR_TAB = InvestorTab.INDIVIDUAL


def normalize_message(message: str) -> str:
    return " ".join(message.strip().lower().rstrip(".,!?").split())


def requests_non_individual_scope(normalized_message: str) -> bool:
    return (
        "non individual" in normalized_message
        or "non-individual" in normalized_message
        or "corporate" in normalized_message
    )


def is_greeting(normalized_message: str) -> bool:
    return normalized_message in GREETING_TERMS


def is_unsupported_banking_request(normalized_message: str) -> bool:
    return any(term in normalized_message for term in UNSUPPORTED_BANKING_TERMS)


def is_investor_search_request(normalized_message: str) -> bool:
    return any(term in normalized_message for term in INVESTOR_SEARCH_TERMS)


def classify_message(message: str, prior_step: str | None = None) -> RoutingState:
    """Map a user message to the next routing state (Individual investors only)."""

    normalized_message = normalize_message(message)
    if is_greeting(normalized_message):
        return _greeting_state(message)
    if is_unsupported_banking_request(normalized_message):
        return _unsupported_state(message)
    if requests_non_individual_scope(normalized_message):
        return _non_individual_scope_state(message)
    if is_investor_search_request(normalized_message):
        has_filters = message_has_search_filters(message, prior_step)
        return _investor_search_state(message, has_filters)
    return _unsupported_state(message)


def read_prior_step(session_state: dict[str, Any]) -> str | None:
    step = session_state.get(STATE_KEY_STEP)
    return str(step) if step is not None else None


def write_session_state(session_state: dict[str, Any], routing_state: RoutingState) -> None:
    """Persist routing fields into ADK session.state."""

    payload = routing_state.model_dump(mode="json")
    session_state[STATE_KEY_ROUTING_STATE] = payload
    session_state[STATE_KEY_CURRENT_INTENT] = payload["current_intent"]
    session_state[STATE_KEY_ROUTE] = payload["route"]
    session_state[STATE_KEY_STEP] = payload["step"]
    session_state[STATE_KEY_INVESTOR_TAB] = payload["investor_tab"]
    session_state[STATE_KEY_LAST_MESSAGE] = payload["last_user_message"]
    session_state[STATE_KEY_NEEDS_CLARIFICATION] = payload["needs_clarification"]
    session_state[STATE_KEY_CLARIFICATION_QUESTION] = payload["clarification_question"]


def write_detect_temp_state(
    session_state: dict[str, Any],
    routing_state: RoutingState,
    has_search_filters: bool = False,
) -> None:
    """Write invocation-scoped detect results (ADK temp: keys)."""

    session_state[STATE_KEY_TEMP_DETECTED_INTENT] = routing_state.current_intent
    session_state[STATE_KEY_TEMP_SHOULD_CALL_TOOL] = routing_state.route
    session_state[STATE_KEY_HAS_SEARCH_FILTERS] = has_search_filters


def _greeting_state(message: str) -> RoutingState:
    return RoutingState(
        current_intent=RoutingIntent.GREETING,
        route=RoutingRoute.GREETING_TOOL,
        step=RoutingStep.NEW,
        investor_tab=DEFAULT_INVESTOR_TAB,
        last_user_message=message,
        needs_clarification=False,
        clarification_question=None,
    )


def _non_individual_scope_state(message: str) -> RoutingState:
    return RoutingState(
        current_intent=RoutingIntent.UNSUPPORTED_BANKING_REQUEST,
        route=RoutingRoute.UNSUPPORTED_BANKING_TOOL,
        step=RoutingStep.BLOCKED,
        investor_tab=DEFAULT_INVESTOR_TAB,
        last_user_message=message,
        needs_clarification=False,
        clarification_question=NON_INDIVIDUAL_NOT_SUPPORTED,
    )


def _unsupported_state(message: str) -> RoutingState:
    return RoutingState(
        current_intent=RoutingIntent.UNSUPPORTED_BANKING_REQUEST,
        route=RoutingRoute.UNSUPPORTED_BANKING_TOOL,
        step=RoutingStep.BLOCKED,
        investor_tab=DEFAULT_INVESTOR_TAB,
        last_user_message=message,
    )


def _investor_search_state(message: str, has_search_filters: bool) -> RoutingState:
    route = (
        RoutingRoute.ANALYZE_SEARCH_ARGUMENTS_TOOL
        if has_search_filters
        else RoutingRoute.SEARCH_INVESTORS_TOOL
    )
    return RoutingState(
        current_intent=RoutingIntent.INVESTOR_SEARCH,
        route=route,
        step=RoutingStep.READY_TO_SEARCH,
        investor_tab=DEFAULT_INVESTOR_TAB,
        last_user_message=message,
    )
