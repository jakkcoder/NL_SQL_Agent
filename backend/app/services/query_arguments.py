"""Map SearchPlan to query-engine arguments (Individual function / NI templates)."""

from typing import Any

from app.models.search_plan import (
    BinaryFilter,
    InvestorSubtype,
    InvestorTab,
    InvestorTypeFilter,
    NonIndividualOtmFilter,
    SearchPlan,
)
from app.services.search_plan_builder import describe_search_plan


def plan_to_query_arguments(plan: SearchPlan) -> dict[str, Any]:
    """Build engine-ready JSON from a validated SearchPlan."""

    if plan.investor_tab == InvestorTab.INDIVIDUAL:
        return _individual_arguments(plan)
    if plan.investor_tab == InvestorTab.NON_INDIVIDUAL:
        return _non_individual_arguments(plan)
    return {
        "engine": "unknown",
        "investor_tab": plan.investor_tab.value,
        "parameters": {},
        "filters_applied": [],
        "combination_strategy": None,
    }


def list_filters_applied(plan: SearchPlan) -> list[str]:
    """Human-readable filter labels aligned with planning CSV mappings."""

    labels: list[str] = []
    if plan.name_search:
        labels.append(f"Name search = {plan.name_search}")
    if plan.eligibility.value != "ALL" and plan.investor_tab == InvestorTab.INDIVIDUAL:
        labels.append(f"Eligibility = {plan.eligibility.value}")
    if plan.investor_tab == InvestorTab.INDIVIDUAL:
        if plan.individual_otm.value != "ALL":
            labels.append(f"OTM = {plan.individual_otm.value}")
    elif plan.non_individual_otm.value != "ALL":
        labels.append(f"OTM = {plan.non_individual_otm.value}")
    if plan.investor_type.value != "ALL":
        labels.append(f"Investor Type = {plan.investor_type.value}")
    if plan.investor_subtypes:
        labels.append(
            "Investor Subtype = " + " + ".join(subtype.value for subtype in plan.investor_subtypes)
        )
    if plan.investor_tab == InvestorTab.INDIVIDUAL:
        if plan.holding.mode != BinaryFilter.ALL:
            labels.append(f"Current Holding = {plan.holding.mode.value}")
        if plan.systematic.mode != BinaryFilter.ALL:
            plans = ",".join(plan.systematic.plans) if plan.systematic.plans else "all plan types"
            labels.append(f"Systematic = {plan.systematic.mode.value} ({plans})")
        if plan.activity.mode != BinaryFilter.ALL:
            types = ",".join(plan.activity.activity_types) or "all types"
            labels.append(
                f"Investor Activity = {plan.activity.mode.value} "
                f"({types}, {plan.activity.duration})"
            )
    if not labels:
        labels.append("No filter (default load)")
    return labels


def _individual_arguments(plan: SearchPlan) -> dict[str, Any]:
    """Arguments for filter_dp_investor_menu per Individual Investors CSV."""

    parameters: dict[str, Any] = {
        "eligibility": plan.eligibility.value,
        "otm": plan.individual_otm.value,
        "investor_type": plan.investor_type.value,
        "investor_subtypes": [subtype.value for subtype in plan.investor_subtypes],
        "holding": _holding_argument(plan),
        "systematic": _systematic_argument(plan),
        "activity": _activity_argument(plan),
        "search_text": plan.name_search,
        "sort_key": plan.sort_key,
        "sort_order": plan.sort_order,
        "page_limit": plan.page_limit,
        "page_offset": plan.page_offset,
        "include_count": "Y",
    }
    return {
        "engine": "filter_dp_investor_menu",
        "investor_tab": InvestorTab.INDIVIDUAL.value,
        "function": "filter_dp_investor_menu",
        "parameters": parameters,
        "filters_applied": list_filters_applied(plan),
        "combination_strategy": "single_function",
        "normalized_summary": describe_search_plan(plan),
    }


def _non_individual_template_names(plan: SearchPlan) -> list[str]:
    """Mirror NonIndividualInvestorExecutor template selection."""

    names: list[str] = []
    if plan.non_individual_otm == NonIndividualOtmFilter.YES:
        names.append("otm_yes")
    elif plan.non_individual_otm == NonIndividualOtmFilter.NO:
        names.append("otm_no")
    if plan.investor_type == InvestorTypeFilter.ACTIVE:
        names.append("active")
    elif plan.investor_type == InvestorTypeFilter.DORMANT:
        names.append("dormant")
    subtype_set = set(plan.investor_subtypes)
    if subtype_set == {InvestorSubtype.CGF, InvestorSubtype.MINOR}:
        names.append("cgf_minor")
    else:
        if InvestorSubtype.CGF in subtype_set:
            names.append("cgf")
        if InvestorSubtype.MINOR in subtype_set:
            names.append("minor")
        if InvestorSubtype.OTHERS in subtype_set:
            names.append("others")
    return names


def _non_individual_arguments(plan: SearchPlan) -> dict[str, Any]:
    """Template list for Non-Individual per NI CSV (intersect when multiple)."""

    template_names = _non_individual_template_names(plan)
    strategy = "default" if not template_names else (
        "single_template" if len(template_names) == 1 else "intersect_templates"
    )
    return {
        "engine": "non_individual_sql_templates",
        "investor_tab": InvestorTab.NON_INDIVIDUAL.value,
        "templates": template_names or ["default"],
        "parameters": {
            "otm": plan.non_individual_otm.value,
            "investor_type": plan.investor_type.value,
            "investor_subtypes": [subtype.value for subtype in plan.investor_subtypes],
            "search_text": plan.name_search,
            "page_limit": plan.page_limit,
            "page_offset": plan.page_offset,
        },
        "filters_applied": list_filters_applied(plan),
        "combination_strategy": strategy,
        "normalized_summary": describe_search_plan(plan),
    }


def _holding_argument(plan: SearchPlan) -> dict[str, Any] | None:
    if plan.holding.mode == BinaryFilter.ALL:
        return None
    return {
        "mode": plan.holding.mode.value,
        "schemes": plan.holding.schemes,
        "inv_options": plan.holding.inv_options,
    }


def _systematic_argument(plan: SearchPlan) -> dict[str, Any] | None:
    if plan.systematic.mode == BinaryFilter.ALL:
        return None
    return {
        "mode": plan.systematic.mode.value,
        "plans": plan.systematic.plans,
        "schemes": plan.systematic.schemes,
        "inv_options": plan.systematic.inv_options,
    }


def _activity_argument(plan: SearchPlan) -> dict[str, Any] | None:
    if plan.activity.mode == BinaryFilter.ALL:
        return None
    return {
        "mode": plan.activity.mode.value,
        "activity_types": plan.activity.activity_types,
        "schemes": plan.activity.schemes,
        "inv_options": plan.activity.inv_options,
        "duration": plan.activity.duration,
    }
