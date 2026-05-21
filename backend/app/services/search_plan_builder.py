"""LLM-powered SearchPlan builder with deterministic fallback."""

import json
import logging
from typing import Any

import litellm

from app.core.config import apply_runtime_env, get_config
from app.models.agent_state import STATE_KEY_INVESTOR_TAB, STATE_KEY_LAST_MESSAGE
from app.models.chat import ChatMessage
from app.models.search_plan import (
    ALLOWED_DURATIONS,
    ActivityFilter,
    BinaryFilter,
    DEFAULT_ACTIVITY_TYPES,
    DEFAULT_SYSTEMATIC_PLANS,
    EligibilityFilter,
    HoldingFilter,
    IndividualOtmFilter,
    InvestorSubtype,
    InvestorTab,
    InvestorTypeFilter,
    NonIndividualOtmFilter,
    SearchPlan,
    SearchPlanLLMOutput,
    SystematicFilter,
    SystematicPlanType,
)
from app.services.filter_catalog import get_filter_catalog
from app.services.filter_prompts import build_search_plan_system_prompt
from app.services.intent_parser import parse_investor_search_intent
from app.services.investor_schema_contract import (
    ensure_investor_schema_for_search_session,
    schema_for_search_plan_llm,
)
from app.services.llm_json import parse_json_content

logger = logging.getLogger(__name__)


def _allowed_values(filter_key: str, fallback: set[str]) -> set[str]:
    values = get_filter_catalog().get_values(filter_key)
    return set(values) if values else fallback


def build_search_plan(
    query: str,
    session_state: dict[str, Any] | None = None,
    messages: list[ChatMessage] | None = None,
    page_limit: int = 25,
    page_offset: int = 0,
) -> tuple[SearchPlan, str, str]:
    """Build a SearchPlan from user text; returns (plan, source, normalized_query)."""

    session_state = session_state or {}
    ensure_investor_schema_for_search_session(session_state, get_config().database_url_value)
    try:
        llm_output = _call_search_plan_llm(query, session_state, messages or [])
        plan = _llm_output_to_search_plan(llm_output, page_limit, page_offset)
        plan = _apply_session_defaults(plan, session_state)
        return plan, "llm", llm_output.normalized_query
    except Exception as exc:
        logger.warning("LLM search plan build failed, using fallback parser: %s", exc)
        plan = parse_investor_search_intent(
            query=query,
            messages=messages,
            page_limit=page_limit,
            page_offset=page_offset,
        )
        plan = _apply_session_defaults(plan, session_state)
        return plan, "fallback", query


def describe_search_plan(plan: SearchPlan) -> str:
    """Human-readable summary of selected filters."""

    parts = [f"{plan.investor_tab.value} investors"]
    if plan.name_search:
        parts.append(f"named {plan.name_search}")
    if plan.investor_type != InvestorTypeFilter.ALL:
        parts.append(plan.investor_type.value.lower())
    if plan.investor_tab == InvestorTab.INDIVIDUAL:
        if plan.eligibility != EligibilityFilter.ALL:
            parts.append(f"eligibility={plan.eligibility.value}")
        if plan.individual_otm != IndividualOtmFilter.ALL:
            parts.append(f"otm={plan.individual_otm.value}")
        if plan.holding.mode != BinaryFilter.ALL:
            parts.append(f"holdings={plan.holding.mode.value}")
        if plan.systematic.mode != BinaryFilter.ALL:
            plans = ",".join(plan.systematic.plans) if plan.systematic.plans else "all plans"
            parts.append(f"systematic={plan.systematic.mode.value} ({plans})")
        if plan.activity.mode != BinaryFilter.ALL:
            types = ",".join(plan.activity.activity_types) or "all types"
            parts.append(
                f"activity={plan.activity.mode.value} ({types}, {plan.activity.duration})"
            )
    elif plan.non_individual_otm != NonIndividualOtmFilter.ALL:
        parts.append(f"otm={plan.non_individual_otm.value}")
    if plan.investor_subtypes:
        parts.append("subtypes=" + ",".join(s.value for s in plan.investor_subtypes))
    return "Show " + " ".join(parts)


def _call_search_plan_llm(
    query: str,
    session_state: dict[str, Any],
    messages: list[ChatMessage],
) -> SearchPlanLLMOutput:
    config = get_config()
    apply_runtime_env(config)
    llm = config.llm

    kwargs: dict[str, Any] = {
        "model": llm.model,
        "messages": [
            {"role": "system", "content": build_search_plan_system_prompt()},
            {"role": "user", "content": _build_user_payload(query, session_state, messages)},
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
        raise ValueError("Empty LLM response for search plan builder")
    return SearchPlanLLMOutput.model_validate(parse_json_content(content))


def _build_user_payload(
    query: str,
    session_state: dict[str, Any],
    messages: list[ChatMessage],
) -> str:
    session = {
        key: session_state.get(key)
        for key in (STATE_KEY_INVESTOR_TAB, STATE_KEY_LAST_MESSAGE, "step", "current_intent")
        if session_state.get(key) is not None
    }
    history = [
        {"role": message.role, "content": message.content}
        for message in messages[-6:]
        if message.content
    ]
    payload: dict[str, Any] = {
        "user_message": query,
        "session": session,
        "recent_messages": history,
    }
    schema = schema_for_search_plan_llm(session_state)
    if schema is not None:
        payload["investor_db_schema_compact"] = schema
    return json.dumps(payload, ensure_ascii=True)


def _llm_output_to_search_plan(
    llm_output: SearchPlanLLMOutput,
    page_limit: int,
    page_offset: int,
) -> SearchPlan:
    plan = SearchPlan(page_limit=page_limit, page_offset=page_offset)
    tab = InvestorTab(llm_output.investor_tab)
    plan.investor_tab = (
        InvestorTab.NON_INDIVIDUAL if tab == InvestorTab.NON_INDIVIDUAL else InvestorTab.INDIVIDUAL
    )
    plan.name_search = _normalize_name(llm_output.name_search)
    plan.eligibility = EligibilityFilter(llm_output.eligibility)
    plan.individual_otm = IndividualOtmFilter(llm_output.individual_otm)
    plan.non_individual_otm = NonIndividualOtmFilter(llm_output.non_individual_otm)
    plan.investor_type = InvestorTypeFilter(llm_output.investor_type)
    plan.investor_subtypes = [InvestorSubtype(value) for value in llm_output.investor_subtypes]
    plan.unsupported_reasons = list(llm_output.unsupported_reasons)

    if plan.investor_tab != InvestorTab.INDIVIDUAL:
        plan.eligibility = EligibilityFilter.ALL
        plan.holding = HoldingFilter()
        plan.systematic = SystematicFilter()
        plan.activity = ActivityFilter()
    else:
        plan.holding.mode = BinaryFilter(llm_output.holding_mode)
        plan.systematic.mode = BinaryFilter(llm_output.systematic_mode)
        plan.activity.mode = BinaryFilter(llm_output.activity_mode)
        if plan.systematic.mode == BinaryFilter.WITH:
            plans = _filter_allowed(
                llm_output.systematic_plans,
                _allowed_values("systematic_plans", {plan.value for plan in SystematicPlanType}),
            )
            if plans:
                plan.systematic.plans = plans
        if plan.activity.mode == BinaryFilter.WITH:
            activities = _filter_allowed(
                llm_output.activity_types,
                _allowed_values("activity_types", set(DEFAULT_ACTIVITY_TYPES)),
            )
            if activities:
                plan.activity.activity_types = activities
            duration = llm_output.activity_duration.strip().lower()
            allowed_durations = set(_allowed_values("activity_duration", ALLOWED_DURATIONS))
            if duration in allowed_durations:
                plan.activity.duration = duration

    if "pending" in llm_output.normalized_query.lower() and not plan.unsupported_reasons:
        plan.unsupported_reasons.append("Pending investors are not in scope for MVP.")

    return plan


def _apply_session_defaults(plan: SearchPlan, session_state: dict[str, Any]) -> SearchPlan:
    if plan.investor_tab == InvestorTab.NON_INDIVIDUAL:
        return plan
    if plan.investor_tab == InvestorTab.UNKNOWN:
        session_tab = session_state.get(STATE_KEY_INVESTOR_TAB)
        if session_tab == InvestorTab.INDIVIDUAL.value:
            plan.investor_tab = InvestorTab.INDIVIDUAL
        else:
            plan.investor_tab = InvestorTab.INDIVIDUAL
    return plan


def _normalize_name(name: str | None) -> str | None:
    if not name:
        return None
    cleaned = name.strip().lower()
    return cleaned or None


def _filter_allowed(values: list[str], allowed: set[str]) -> list[str]:
    return sorted({value for value in values if value in allowed})
