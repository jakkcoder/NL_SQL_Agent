from app.models.search_plan import (
    BinaryFilter,
    IndividualOtmFilter,
    InvestorTab,
    InvestorTypeFilter,
    NonIndividualOtmFilter,
)
from app.services.intent_parser import parse_investor_search_intent
from app.services.plan_validator import PlanValidator


def test_generic_investor_query_needs_clarification():
    plan = parse_investor_search_intent("Show me my investors")
    result = PlanValidator().validate(plan)

    assert plan.investor_tab == InvestorTab.UNKNOWN
    assert result.status == "clarification"


def test_individual_active_otm_name_query():
    plan = parse_investor_search_intent("Show active individual investors with OTM named Rahul")
    result = PlanValidator().validate(plan)

    assert result.can_execute
    assert plan.investor_tab == InvestorTab.INDIVIDUAL
    assert plan.investor_type == InvestorTypeFilter.ACTIVE
    assert plan.individual_otm == IndividualOtmFilter.YES
    assert plan.name_search == "rahul"


def test_non_individual_dormant_without_otm_query():
    plan = parse_investor_search_intent("Show dormant non-individual investors without OTM")
    result = PlanValidator().validate(plan)

    assert result.can_execute
    assert plan.investor_tab == InvestorTab.NON_INDIVIDUAL
    assert plan.investor_type == InvestorTypeFilter.DORMANT
    assert plan.non_individual_otm == NonIndividualOtmFilter.NO


def test_pending_is_out_of_scope():
    plan = parse_investor_search_intent("Show pending investors")
    result = PlanValidator().validate(plan)

    assert result.status == "out_of_scope"


def test_non_individual_rejects_individual_only_filters():
    plan = parse_investor_search_intent("Show non-individual investors with SIP")
    result = PlanValidator().validate(plan)

    assert plan.systematic.mode == BinaryFilter.WITH
    assert result.status == "out_of_scope"
