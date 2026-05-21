"""Human-readable summaries of SearchPlan (no LLM; used by final_query / query_arguments)."""

from __future__ import annotations

from app.models.search_plan import (
    BinaryFilter,
    EligibilityFilter,
    IndividualOtmFilter,
    InvestorTab,
    InvestorTypeFilter,
    NonIndividualOtmFilter,
    SearchPlan,
)


def describe_search_plan(plan: SearchPlan) -> str:
    """Human-readable summary of selected filters."""

    parts = [f"{plan.investor_tab.value} investors"]
    if plan.name_search:
        parts.append(f"named {plan.name_search}")
    if plan.investor_type != InvestorTypeFilter.ALL:
        parts.append(plan.investor_type.value.lower())
    if plan.investor_tab == InvestorTab.INDIVIDUAL:
        if plan.city and str(plan.city).strip():
            parts.append(f"city={plan.city.strip()}")
        if plan.age_min is not None or plan.age_max is not None:
            lo = plan.age_min if plan.age_min is not None else "?"
            hi = plan.age_max if plan.age_max is not None else "?"
            parts.append(f"age_years={lo}-{hi}")
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
