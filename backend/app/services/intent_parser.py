"""Legacy deterministic NL → ``SearchPlan`` mapper.

**Not used by the two-tool ADK root agent** (greeting + catalog SQL generator). This module
remains for offline tests and dev scripts that need stable ``SearchPlan`` fixtures without
calling a model.
"""

import re

from app.models.chat import ChatMessage
from app.models.search_plan import (
    ActivityType,
    BinaryFilter,
    EligibilityFilter,
    IndividualOtmFilter,
    InvestorSubtype,
    InvestorTab,
    InvestorTypeFilter,
    NonIndividualOtmFilter,
    SearchPlan,
    SystematicPlanType,
)


SYSTEMATIC_SYNONYMS = {
    "sip": SystematicPlanType.SIP.value,
    "stp": SystematicPlanType.STP.value,
    "swp": SystematicPlanType.SWP.value,
    "dtp": SystematicPlanType.DTP.value,
    "flex sip": SystematicPlanType.FLEXSIP.value,
    "flexsip": SystematicPlanType.FLEXSIP.value,
    "flex stp": SystematicPlanType.FLEXSTP.value,
    "flexstp": SystematicPlanType.FLEXSTP.value,
    "flex index": SystematicPlanType.FLEXINDEX.value,
    "flexindex": SystematicPlanType.FLEXINDEX.value,
    "swing stp": SystematicPlanType.SWINGSTP.value,
    "swingstp": SystematicPlanType.SWINGSTP.value,
    "smart swap": SystematicPlanType.SMARTSWAP.value,
    "smartswap": SystematicPlanType.SMARTSWAP.value,
    "swingstp": SystematicPlanType.SWINGSTP.value,
    "swing stp": SystematicPlanType.SWINGSTP.value,
}

ACTIVITY_SYNONYMS = {
    "purchase": ActivityType.PURCHASE.value,
    "bought": ActivityType.PURCHASE.value,
    "buy": ActivityType.PURCHASE.value,
    "switch": ActivityType.SWITCH.value,
    "redemption": ActivityType.REDEMPTION.value,
    "redeemed": ActivityType.REDEMPTION.value,
    "redeem": ActivityType.REDEMPTION.value,
    "sip": ActivityType.SIP.value,
    "dtp": ActivityType.DTP.value,
    "stp": ActivityType.STP.value,
    "swp": ActivityType.SWP.value,
    "flex sip": ActivityType.FLEXSIP.value,
    "flexsip": ActivityType.FLEXSIP.value,
}

DURATION_SYNONYMS = {
    "1 month": "1 month",
    "one month": "1 month",
    "2 month": "2 month",
    "2 months": "2 month",
    "two months": "2 month",
    "3 month": "3 month",
    "3 months": "3 month",
    "three months": "3 month",
    "6 month": "6 month",
    "6 months": "6 month",
    "six months": "6 month",
    "1 year": "1 year",
    "one year": "1 year",
    "2 year": "2 year",
    "2 years": "2 year",
    "two years": "2 year",
    "3 year": "3 year",
    "3 years": "3 year",
    "three years": "3 year",
    "this financial year": "this financial year",
    "current financial year": "this financial year",
    "last quarter": "3 month",
    "previous quarter": "3 month",
    "fy25": "this financial year",
}


def parse_investor_search_intent(
    query: str,
    messages: list[ChatMessage] | None = None,
    page_limit: int = 25,
    page_offset: int = 0,
) -> SearchPlan:
    """Map user text to a constrained SearchPlan (tests / scripts only).

    The ADK root agent does not use this path; it uses ``generate_catalog_sql_query_tool``.
    First-name ``name_search`` is not set here.
    """

    normalized = _normalize(query)
    plan = SearchPlan(page_limit=page_limit, page_offset=page_offset)
    plan.investor_tab = _parse_investor_tab(normalized, messages or [])

    if "pending" in normalized:
        plan.investor_tab = InvestorTab.PENDING

    _parse_eligibility(normalized, plan)
    _parse_otm(normalized, plan)
    _parse_investor_type(normalized, plan)
    _parse_subtypes(normalized, plan)
    _parse_holding(normalized, plan)
    _parse_systematic(normalized, plan)
    _parse_activity(normalized, plan)
    _parse_unsupported_search(normalized, plan)
    _parse_page_limit_hint(query, plan)
    return plan


def _parse_page_limit_hint(original: str, plan: SearchPlan) -> None:
    """Best-effort: Top N / first N in the user string sets page_limit when in range."""

    match = re.search(r"\b(?:top|first)\s+(\d{1,3})\b", original, flags=re.IGNORECASE)
    if not match:
        return
    limit = int(match.group(1))
    if 1 <= limit <= 500:
        plan.page_limit = limit


def _wants_cgf_excluded(normalized: str) -> bool:
    return (
        "without cgf" in normalized
        or "not invested in cgf" in normalized
        or "excluding cgf" in normalized
        or "no cgf" in normalized
        or "non cgf" in normalized
        or "not in cgf" in normalized
    )


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _parse_investor_tab(normalized: str, messages: list[ChatMessage]) -> InvestorTab:
    if "non individual" in normalized or "non-individual" in normalized or "corporate" in normalized:
        return InvestorTab.NON_INDIVIDUAL
    if "individual" in normalized:
        return InvestorTab.INDIVIDUAL

    if normalized in {"individual", "individual investors"}:
        return InvestorTab.INDIVIDUAL
    if normalized in {"non individual", "non-individual", "non individual investors"}:
        return InvestorTab.NON_INDIVIDUAL

    # Reuse an already clarified tab from prior user messages.
    for message in reversed(messages):
        if message.role != "user":
            continue
        prior = _normalize(message.content)
        if prior == normalized:
            continue
        if "non individual" in prior or "non-individual" in prior:
            return InvestorTab.NON_INDIVIDUAL
        if "individual" in prior:
            return InvestorTab.INDIVIDUAL
    return InvestorTab.INDIVIDUAL


def _parse_eligibility(normalized: str, plan: SearchPlan) -> None:
    if "without email" in normalized or "missing email" in normalized or "not eligible" in normalized:
        plan.eligibility = EligibilityFilter.NO
    elif "eligible" in normalized or "email registered" in normalized or "with email" in normalized:
        plan.eligibility = EligibilityFilter.YES


def _parse_otm(normalized: str, plan: SearchPlan) -> None:
    no_otm = (
        "without otm" in normalized
        or "no otm" in normalized
        or "without mandate" in normalized
        or "no mandate" in normalized
        or "otm not registered" in normalized
    )
    yes_otm = (
        "with otm" in normalized
        or "otm registered" in normalized
        or "has mandate" in normalized
        or "with mandate" in normalized
        or "auto debit" in normalized
    )
    if no_otm:
        plan.individual_otm = IndividualOtmFilter.NO
        plan.non_individual_otm = NonIndividualOtmFilter.NO
    elif yes_otm:
        plan.individual_otm = IndividualOtmFilter.YES
        plan.non_individual_otm = NonIndividualOtmFilter.YES


def _parse_investor_type(normalized: str, plan: SearchPlan) -> None:
    if "dormant" in normalized or "inactive" in normalized or "no recent activity" in normalized:
        plan.investor_type = InvestorTypeFilter.DORMANT
    elif "no active sip" in normalized or "without active sip" in normalized:
        return
    elif "active" in normalized or "transacted recently" in normalized or "recently transacted" in normalized:
        plan.investor_type = InvestorTypeFilter.ACTIVE


def _parse_subtypes(normalized: str, plan: SearchPlan) -> None:
    subtypes: list[InvestorSubtype] = []
    if "cgf" in normalized and not _wants_cgf_excluded(normalized):
        subtypes.append(InvestorSubtype.CGF)
    if "minor" in normalized:
        subtypes.append(InvestorSubtype.MINOR)
    if "others" in normalized or "other investors" in normalized or "non cgf non minor" in normalized:
        subtypes.append(InvestorSubtype.OTHERS)
    plan.investor_subtypes = subtypes


def _is_investor_type_recency_phrase(normalized: str) -> bool:
    """Phrases that map to investortype ACTIVE/DORMANT only (CSV rows 7-8), not investor_activity."""

    phrases = (
        "transacted recently",
        "recently transacted",
        "active in last",
        "who has been investing",
        "investors active in",
        "no recent activity",
        "hasn't transacted",
        "has not transacted",
    )
    return any(phrase in normalized for phrase in phrases)


def _parse_holding(normalized: str, plan: SearchPlan) -> None:
    without_phrases = (
        "no holding",
        "no holdings",
        "without holding",
        "zero balance",
        "fully exited",
    )
    with_phrases = (
        "current holding",
        "have holding",
        "with holding",
        "with holdings",
        "hold units",
        "currently hold",
        "currently invested",
        "money in a fund",
        "active holdings",
    )
    if any(phrase in normalized for phrase in without_phrases):
        plan.holding.mode = BinaryFilter.WITHOUT
    elif any(phrase in normalized for phrase in with_phrases):
        plan.holding.mode = BinaryFilter.WITH


def _time_window_present(normalized: str) -> bool:
    return any(term in normalized for term in DURATION_SYNONYMS) or "last " in normalized or "recent" in normalized


def _parse_systematic(normalized: str, plan: SearchPlan) -> None:
    # SIP/STP/SWP + time window maps to investor_activity per planning CSV, not systematic_plan.
    if _time_window_present(normalized) and any(
        term in normalized for term in ("sip", "stp", "swp", "dtp")
    ):
        return

    systematic_terms = [
        "systematic",
        "sip",
        "stp",
        "swp",
        "dtp",
        "flex",
        "swing",
        "smart swap",
        "smartswap",
        "flexsip",
        "flexindex",
        "swingstp",
    ]
    if not any(term in normalized for term in systematic_terms):
        return

    without = (
        "without systematic" in normalized
        or "no systematic" in normalized
        or "without sip" in normalized
        or "no sip" in normalized
        or "have no active" in normalized
        or "no active sip" in normalized
    )
    plan.systematic.mode = BinaryFilter.WITHOUT if without else BinaryFilter.WITH
    plans = _matched_systematic_plans(normalized)
    plan.systematic.plans = plans if plans else plan.systematic.plans


def _matched_systematic_plans(normalized: str) -> list[str]:
    """Prefer longest plan synonym so 'flexsip' does not also match 'sip'."""

    plans: list[str] = []
    for term, value in sorted(SYSTEMATIC_SYNONYMS.items(), key=lambda item: -len(item[0])):
        if term not in normalized:
            continue
        if value in plans:
            continue
        if any(
            other != term and len(other) > len(term) and other in normalized and term in other
            for other in SYSTEMATIC_SYNONYMS
        ):
            continue
        plans.append(value)
    return sorted(set(plans))


def _matched_activity_types(normalized: str) -> list[str]:
    activities: list[str] = []
    for term, value in sorted(ACTIVITY_SYNONYMS.items(), key=lambda item: -len(item[0])):
        if term not in normalized:
            continue
        if value in activities:
            continue
        if any(
            other != term and len(other) > len(term) and other in normalized and term in other
            for other in ACTIVITY_SYNONYMS
        ):
            continue
        activities.append(value)
    return sorted(set(activities))


def _parse_activity(normalized: str, plan: SearchPlan) -> None:
    if _is_investor_type_recency_phrase(normalized):
        return

    activity_terms = ["activity", "transaction", "purchase", "switch", "redemption", "redeem", "bought"]
    sip_activity = "sip transaction" in normalized or "sip instalment" in normalized
    sip_with_window = "sip" in normalized and _time_window_present(normalized)
    any_recent = "any recent transaction" in normalized or "been transacting" in normalized

    if not (
        sip_activity
        or sip_with_window
        or any_recent
        or any(term in normalized for term in activity_terms)
        or (_time_window_present(normalized) and "recent" in normalized)
    ):
        return

    without = "without activity" in normalized or "have not transacted" in normalized
    plan.activity.mode = BinaryFilter.WITHOUT if without else BinaryFilter.WITH

    if any_recent:
        from app.models.search_plan import DEFAULT_ACTIVITY_TYPES

        plan.activity.activity_types = sorted(DEFAULT_ACTIVITY_TYPES)
    else:
        activities = _matched_activity_types(normalized)
        if sip_activity or sip_with_window:
            if ActivityType.SIP.value not in activities:
                activities.append(ActivityType.SIP.value)
        plan.activity.activity_types = activities if activities else plan.activity.activity_types

    duration_set = False
    for term, duration in DURATION_SYNONYMS.items():
        if term in normalized:
            plan.activity.duration = duration
            duration_set = True
            break
    if plan.activity.mode == BinaryFilter.WITH and not duration_set:
        plan.activity.duration = "1 month"


def _parse_unsupported_search(normalized: str, plan: SearchPlan) -> None:
    unsupported_fields = {
        "pan": "PAN search is out of scope for MVP.",
        "folio": "Folio search is out of scope for MVP.",
        "mobile": "Mobile search is out of scope for MVP.",
        "phone": "Mobile search is out of scope for MVP.",
        "email": "Email search is out of scope for MVP unless used as eligibility.",
    }
    for token, reason in unsupported_fields.items():
        if token in normalized and plan.eligibility == EligibilityFilter.ALL:
            plan.unsupported_reasons.append(reason)
