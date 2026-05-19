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
}


def parse_investor_search_intent(
    query: str,
    messages: list[ChatMessage] | None = None,
    page_limit: int = 25,
    page_offset: int = 0,
) -> SearchPlan:
    """Map user text to a constrained SearchPlan.

    This deterministic parser is intentionally conservative. The ADK agent can
    call this as a tool, and the validator remains the final authority.
    """

    normalized = _normalize(query)
    plan = SearchPlan(page_limit=page_limit, page_offset=page_offset)
    plan.investor_tab = _parse_investor_tab(normalized, messages or [])

    if "pending" in normalized:
        plan.investor_tab = InvestorTab.PENDING

    plan.name_search = _parse_name_search(query, normalized)
    _parse_eligibility(normalized, plan)
    _parse_otm(normalized, plan)
    _parse_investor_type(normalized, plan)
    _parse_subtypes(normalized, plan)
    _parse_holding(normalized, plan)
    _parse_systematic(normalized, plan)
    _parse_activity(normalized, plan)
    _parse_unsupported_search(normalized, plan)
    return plan


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
    return InvestorTab.UNKNOWN


def _parse_name_search(original: str, normalized: str) -> str | None:
    patterns = [
        r"(?:named|called|name is)\s+([a-zA-Z]+)",
        r"(?:search for|find investor|look up investor|lookup investor)\s+([a-zA-Z]+)",
        r"(?:find|search|look up|lookup)\s+([a-zA-Z]+)$",
    ]
    for pattern in patterns:
        match = re.search(pattern, original, flags=re.IGNORECASE)
        if match:
            return match.group(1).lower()
    if normalized.startswith("find investor named "):
        return normalized.rsplit(" ", 1)[-1]
    return None


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
    elif "active" in normalized or "transacted recently" in normalized or "recently transacted" in normalized:
        plan.investor_type = InvestorTypeFilter.ACTIVE


def _parse_subtypes(normalized: str, plan: SearchPlan) -> None:
    subtypes: list[InvestorSubtype] = []
    if "cgf" in normalized:
        subtypes.append(InvestorSubtype.CGF)
    if "minor" in normalized:
        subtypes.append(InvestorSubtype.MINOR)
    if "others" in normalized or "other investors" in normalized or "non cgf non minor" in normalized:
        subtypes.append(InvestorSubtype.OTHERS)
    plan.investor_subtypes = subtypes


def _parse_holding(normalized: str, plan: SearchPlan) -> None:
    if "no holding" in normalized or "without holding" in normalized or "zero balance" in normalized:
        plan.holding.mode = BinaryFilter.WITHOUT
    elif "current holding" in normalized or "have holding" in normalized or "with holding" in normalized:
        plan.holding.mode = BinaryFilter.WITH


def _parse_systematic(normalized: str, plan: SearchPlan) -> None:
    systematic_terms = ["systematic", "sip", "stp", "swp", "dtp", "flex", "swing", "smart swap"]
    if not any(term in normalized for term in systematic_terms):
        return

    without = (
        "without systematic" in normalized
        or "no systematic" in normalized
        or "without sip" in normalized
        or "no sip" in normalized
        or "have no active" in normalized
    )
    plan.systematic.mode = BinaryFilter.WITHOUT if without else BinaryFilter.WITH
    plans = [value for term, value in SYSTEMATIC_SYNONYMS.items() if term in normalized]
    plan.systematic.plans = sorted(set(plans)) if plans else plan.systematic.plans


def _parse_activity(normalized: str, plan: SearchPlan) -> None:
    activity_terms = ["activity", "transaction", "purchase", "switch", "redemption", "redeem", "bought"]
    if not any(term in normalized for term in activity_terms):
        return

    without = "without activity" in normalized or "have not" in normalized or "no recent activity" in normalized
    plan.activity.mode = BinaryFilter.WITHOUT if without else BinaryFilter.WITH
    activities = [value for term, value in ACTIVITY_SYNONYMS.items() if term in normalized]
    plan.activity.activity_types = sorted(set(activities)) if activities else plan.activity.activity_types
    for term, duration in DURATION_SYNONYMS.items():
        if term in normalized:
            plan.activity.duration = duration
            break


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
