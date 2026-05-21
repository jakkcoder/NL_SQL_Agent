"""LLM-powered routing intent detection with strict JSON validation."""

import json
import logging
from typing import Any

import litellm

from app.services.filter_prompts import build_detect_intent_system_prompt
from app.core.config import apply_runtime_env, get_config
from app.models.agent_state import (
    HDFC_GREETING_MESSAGE,
    IntentDetectionLLMOutput,
    RoutingIntent,
    RoutingRoute,
    RoutingState,
    RoutingStep,
)
from app.models.search_plan import InvestorTab
from app.services.filter_detection import message_has_search_filters
from app.services.intent_parser import parse_investor_search_intent
from app.services.llm_json import parse_json_content
from app.services.routing import (
    DEFAULT_INVESTOR_TAB,
    classify_message,
    read_prior_step,
    requests_non_individual_scope,
    normalize_message,
)

logger = logging.getLogger(__name__)

ROUTE_BY_INTENT: dict[RoutingIntent, RoutingRoute] = {
    RoutingIntent.GREETING: RoutingRoute.GREETING_TOOL,
    RoutingIntent.UNSUPPORTED_BANKING_REQUEST: RoutingRoute.UNSUPPORTED_BANKING_TOOL,
}

STEP_BY_INTENT: dict[RoutingIntent, RoutingStep] = {
    RoutingIntent.GREETING: RoutingStep.NEW,
    RoutingIntent.INVESTOR_SEARCH: RoutingStep.READY_TO_SEARCH,
    RoutingIntent.UNSUPPORTED_BANKING_REQUEST: RoutingStep.BLOCKED,
}


def detect_routing_intent(
    message: str,
    session_state: dict[str, Any],
) -> tuple[RoutingState, str, bool, list[str]]:
    """Classify routing intent via LLM; fall back to deterministic rules on failure."""

    try:
        llm_output = _call_intent_llm(message, session_state)
        routing_state = _llm_output_to_routing_state(llm_output, message)
        has_filters = llm_output.has_search_filters
        detected = list(llm_output.detected_filters)
        routing_state, has_filters, detected, source = _apply_individual_only_overrides(
            message,
            routing_state,
            has_filters,
            detected,
            "llm",
        )
        return routing_state, source, has_filters, detected
    except Exception as exc:
        logger.warning("LLM intent detection failed, using fallback: %s", exc)
        prior_step = read_prior_step(session_state)
        routing_state = classify_message(message, prior_step=prior_step)
        has_filters, detected = _fallback_filter_detection(message, prior_step)
        if routing_state.current_intent == RoutingIntent.INVESTOR_SEARCH:
            routing_state = _apply_investor_search_route(routing_state, has_filters)
        routing_state, has_filters, detected, source = _apply_individual_only_overrides(
            message,
            routing_state,
            has_filters,
            detected,
            "fallback",
        )
        return routing_state, source, has_filters, detected


def _fallback_filter_detection(
    message: str,
    prior_step: str | None,
) -> tuple[bool, list[str]]:
    has_filters = message_has_search_filters(message, prior_step)
    if not has_filters:
        return False, []
    plan = parse_investor_search_intent(message)
    from app.services.query_arguments import list_filters_applied

    return True, list_filters_applied(plan)


def _call_intent_llm(message: str, session_state: dict[str, Any]) -> IntentDetectionLLMOutput:
    config = get_config()
    apply_runtime_env(config)
    llm = config.llm

    kwargs: dict[str, Any] = {
        "model": llm.model,
        "messages": [
            {"role": "system", "content": build_detect_intent_system_prompt()},
            {"role": "user", "content": _build_user_payload(message, session_state)},
        ],
        "temperature": 0,
        "timeout": llm.request_timeout_seconds,
        "response_format": {"type": "json_object"},
    }
    if llm.max_output_tokens:
        kwargs["max_tokens"] = llm.max_output_tokens

    response = litellm.completion(**kwargs)
    content = response.choices[0].message.content
    if not content:
        raise ValueError("Empty LLM response for intent detection")
    return IntentDetectionLLMOutput.model_validate(parse_json_content(content))


def _build_user_payload(message: str, session_state: dict[str, Any]) -> str:
    context = {
        key: session_state.get(key)
        for key in (
            "current_intent",
            "route",
            "step",
            "investor_tab",
            "last_user_message",
            "needs_clarification",
            "clarification_question",
            "has_search_filters",
        )
        if session_state.get(key) is not None
    }
    payload = {"user_message": message, "session": context}
    return json.dumps(payload, ensure_ascii=True)


def _llm_output_to_routing_state(
    llm_output: IntentDetectionLLMOutput,
    message: str,
) -> RoutingState:
    intent = RoutingIntent(llm_output.current_intent)
    if intent == RoutingIntent.INVESTOR_TYPE_CLARIFICATION:
        intent = RoutingIntent.INVESTOR_SEARCH

    route = _resolve_route(intent, llm_output.has_search_filters, llm_output.route)
    step = STEP_BY_INTENT.get(intent)
    if step is None:
        step = (
            RoutingStep(llm_output.step)
            if llm_output.step is not None
            else RoutingStep.READY_TO_SEARCH
        )

    needs_clarification = llm_output.needs_clarification
    clarification_question = llm_output.clarification_question
    if intent == RoutingIntent.GREETING:
        needs_clarification = False
        clarification_question = None
        step = RoutingStep.NEW
    elif intent == RoutingIntent.UNSUPPORTED_BANKING_REQUEST:
        needs_clarification = False
        clarification_question = None
    elif intent == RoutingIntent.INVESTOR_SEARCH:
        needs_clarification = False
        clarification_question = None
        step = RoutingStep.READY_TO_SEARCH

    return RoutingState(
        current_intent=intent,
        route=route,
        step=step,
        investor_tab=DEFAULT_INVESTOR_TAB,
        last_user_message=message,
        needs_clarification=needs_clarification,
        clarification_question=clarification_question,
    )


def _resolve_route(
    intent: RoutingIntent,
    has_search_filters: bool,
    llm_route: RoutingRoute,
) -> RoutingRoute:
    if intent != RoutingIntent.INVESTOR_SEARCH:
        return ROUTE_BY_INTENT.get(intent, RoutingRoute(llm_route))
    if has_search_filters:
        return RoutingRoute.ANALYZE_SEARCH_ARGUMENTS_TOOL
    return RoutingRoute.SEARCH_INVESTORS_TOOL


def _apply_investor_search_route(
    routing_state: RoutingState,
    has_search_filters: bool,
) -> RoutingState:
    routing_state.route = (
        RoutingRoute.ANALYZE_SEARCH_ARGUMENTS_TOOL
        if has_search_filters
        else RoutingRoute.SEARCH_INVESTORS_TOOL
    )
    routing_state.investor_tab = DEFAULT_INVESTOR_TAB
    routing_state.step = RoutingStep.READY_TO_SEARCH
    return routing_state


def _apply_individual_only_overrides(
    message: str,
    routing_state: RoutingState,
    has_search_filters: bool,
    detected_filters: list[str],
    source: str,
) -> tuple[RoutingState, bool, list[str], str]:
    """Reconcile LLM output with Individual-only MVP routing rules."""

    normalized = normalize_message(message)
    if requests_non_individual_scope(normalized):
        return classify_message(message), False, [], "individual_only"

    if routing_state.current_intent == RoutingIntent.INVESTOR_TYPE_CLARIFICATION:
        prior_step = None
        has_filters = message_has_search_filters(message, prior_step)
        routing_state = classify_message(message, prior_step=prior_step)
        if routing_state.current_intent == RoutingIntent.INVESTOR_SEARCH:
            routing_state = _apply_investor_search_route(routing_state, has_filters)
        return routing_state, has_filters, detected_filters, "individual_only"

    if routing_state.current_intent == RoutingIntent.INVESTOR_SEARCH:
        routing_state.investor_tab = DEFAULT_INVESTOR_TAB
        routing_state.step = RoutingStep.READY_TO_SEARCH
        routing_state.needs_clarification = False
        routing_state.clarification_question = None
        routing_state = _apply_investor_search_route(routing_state, has_search_filters)

    if routing_state.current_intent == RoutingIntent.GREETING:
        routing_state.investor_tab = DEFAULT_INVESTOR_TAB
        routing_state.step = RoutingStep.NEW
        routing_state.needs_clarification = False
        routing_state.clarification_question = None

    return routing_state, has_search_filters, detected_filters, source
