"""Heuristics for whether a user message includes investor search filters."""

from app.models.search_plan import InvestorTypeFilter
from app.services.intent_parser import parse_investor_search_intent
from app.services.plan_validator import PlanValidator


def message_has_search_filters(message: str, prior_step: str | None = None) -> bool:
    """True when the message includes filters beyond a plain investor list."""

    del prior_step  # Individual-only MVP: no investor-type clarification step.
    plan = parse_investor_search_intent(message)
    if not (PlanValidator().has_any_filter(plan) or _plan_has_type_filters(plan)):
        return False
    return True


def _plan_has_type_filters(plan) -> bool:
    return plan.investor_type != InvestorTypeFilter.ALL or bool(plan.investor_subtypes)
