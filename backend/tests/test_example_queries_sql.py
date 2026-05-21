"""Example NL queries → SearchPlan + SQL shape (legacy test fixture + executor).

``parse_investor_search_intent`` is **not** used in production; these tests use it
only as a stable offline stand-in for ``SearchPlan`` to assert warehouse SQL shape.
"""

from __future__ import annotations

import pytest

from app.models.search_plan import ActivityType, BinaryFilter, InvestorTypeFilter, SearchPlan
from app.services.individual_executor import IndividualInvestorExecutor
from app.services.intent_parser import parse_investor_search_intent
from app.services.plan_validator import PlanValidator
from app.services.query_arguments import plan_to_query_arguments

ARN = "ARN-EXAMPLE"


def _warehouse_filter_shape(sql: str) -> tuple[bool, bool, bool]:
    """Holding, systematic, activity dimensions present in catalog-driven warehouse SQL."""

    s = sql.lower()
    holding = "having sum" in s
    systematic = "sipstp" in s or "dtp_regn" in s or "trigger_trxn" in s
    activity = "transaction_types" in s or "trxntypcod" in s
    return holding, systematic, activity


def test_mumbai_city_is_not_a_sql_dimension_default_list():
    """City names are ignored by the deterministic parser; SQL is default menu load."""

    plan = parse_investor_search_intent("Show my investors in Mumbai")
    assert plan.activity.mode == BinaryFilter.ALL
    assert plan.systematic.mode == BinaryFilter.ALL
    v = PlanValidator().validate(plan)
    assert v.can_execute, v.message
    sql, _ = IndividualInvestorExecutor.build_query(plan, ARN)
    assert _warehouse_filter_shape(sql) == (False, False, False)
    assert plan_to_query_arguments(plan)["parameters"]["activity"] is None


def test_age_range_parser_does_not_infer_age_fields():
    """Legacy parser does not infer age; production uses SearchPlan LLM + age_min/age_max."""

    plan = parse_investor_search_intent("Investor with Age between 30 and 40")
    assert plan.activity.mode == BinaryFilter.ALL
    assert plan.name_search is None
    assert plan.age_min is None and plan.age_max is None
    sql, _ = IndividualInvestorExecutor.build_query(plan, ARN)
    assert _warehouse_filter_shape(sql) == (False, False, False)


def test_age_range_on_plan_adds_dob_predicate():
    plan = SearchPlan(age_min=30, age_max=40)
    sql, params = IndividualInvestorExecutor.build_query(plan, ARN)
    assert "extract(year from age(current_date, i.dob))" in sql.lower()
    assert 30 in params and 40 in params


def test_city_on_plan_adds_predicate_and_order_by_uses_select_alias():
    """Postgres requires ORDER BY output columns when the query uses SELECT DISTINCT."""

    plan = SearchPlan(city="Mumbai")
    sql, params = IndividualInvestorExecutor.build_query(plan, ARN)
    low = sql.lower()
    assert "cm_city.city" in low and "customer_master" in low
    assert ARN in params
    assert any("mumbai" in str(p).lower() for p in params)
    assert "order by orderby" in low


def test_redemption_last_quarter_equity_funds_activity_window():
    """Redemption + last quarter → activity composite; equity scheme not parsed (MVP gap)."""

    plan = parse_investor_search_intent("Investors who did redemption in last quarter for equity funds.")
    assert plan.activity.mode == BinaryFilter.WITH
    assert ActivityType.REDEMPTION.value in plan.activity.activity_types
    assert plan.activity.duration == "3 month"
    assert plan.activity.schemes == ["ALL"]
    sql, params = IndividualInvestorExecutor.build_query(plan, ARN)
    assert _warehouse_filter_shape(sql) == (False, False, True)
    assert "trxndbcr" in sql.lower() and "'r'" in sql.lower()
    assert "3 month" in params


def test_active_sips_hybrid_systematic_and_active_type():
    """'Active' + SIP picks systematic WITH SIP and ACTIVE type; amount and hybrid are MVP gaps."""

    plan = parse_investor_search_intent("Active SIPs above 5,000 per month in hybrid funds.")
    assert plan.investor_type == InvestorTypeFilter.ACTIVE
    assert plan.systematic.mode == BinaryFilter.WITH
    assert "SIP" in plan.systematic.plans
    assert plan.systematic.schemes == ["ALL"]
    sql, _ = IndividualInvestorExecutor.build_query(plan, ARN)
    assert _warehouse_filter_shape(sql) == (False, True, False)


def test_dormant_inactive_investor_type():
    plan = parse_investor_search_intent(
        "Dormant / inactive investors (investors not transacted in certain period / "
        "having 0 units across all schemes)"
    )
    assert plan.investor_type == InvestorTypeFilter.DORMANT
    sql, params = IndividualInvestorExecutor.build_query(plan, ARN)
    assert "CURRENT_DATE - m.d >= 180" in sql.replace("\n", " ")


def test_top_20_purchases_fy25_activity_and_page_limit():
    plan = parse_investor_search_intent("Top 20 investors by purchases in FY25")
    assert plan.page_limit == 20
    assert plan.activity.mode == BinaryFilter.WITH
    assert ActivityType.PURCHASE.value in plan.activity.activity_types
    assert plan.activity.duration == "this financial year"
    args = plan_to_query_arguments(plan)
    assert args["parameters"]["page_limit"] == 20
    sql, params = IndividualInvestorExecutor.build_query(plan, ARN)
    assert _warehouse_filter_shape(sql) == (False, False, True)
    assert 20 in params


def test_named_bhavin_not_in_deterministic_parser():
    """Local parser does not guess names; search-plan LLM supplies name_search."""

    plan = parse_investor_search_intent("Investors named 'Bhavin' in Mumbai or Ahmedabad.")
    assert plan.name_search is None


def test_nri_not_distinct_subtype_default_list():
    """NRI is not mapped to a catalog subtype yet; treat as plain list."""

    plan = parse_investor_search_intent("NRI investors")
    assert plan.investor_subtypes == []
    sql, _ = IndividualInvestorExecutor.build_query(plan, ARN)
    assert _warehouse_filter_shape(sql) == (False, False, False)


def test_minor_excluding_cgf_subtype_minor_only():
    plan = parse_investor_search_intent("Minor Investors not invested in CGF schemes")
    assert [s.value for s in plan.investor_subtypes] == ["MINOR"]
    args = plan_to_query_arguments(plan)
    assert args["parameters"]["investor_subtypes"] == ["MINOR"]


def test_no_active_sip_systematic_without_sip():
    plan = parse_investor_search_intent("Investors with no active SIP")
    assert plan.systematic.mode == BinaryFilter.WITHOUT
    assert "SIP" in plan.systematic.plans
    assert plan.investor_type == InvestorTypeFilter.ALL
    sql, params = IndividualInvestorExecutor.build_query(plan, ARN)
    assert _warehouse_filter_shape(sql) == (False, True, False)
    assert "sipstp" in sql.lower() and "not (" in sql.lower()


def test_liquid_cash_funds_not_scheme_filtered_yet():
    """Liquid/cash wording does not set scheme codes in the deterministic parser."""

    plan = parse_investor_search_intent("Investors with investment only in Liquid / cash funds")
    assert plan.holding.mode == BinaryFilter.ALL
    assert plan.holding.schemes == ["ALL"]
    sql, _ = IndividualInvestorExecutor.build_query(plan, ARN)
    assert _warehouse_filter_shape(sql) == (False, False, False)


@pytest.mark.parametrize(
    "query",
    [
        "Show my investors in Mumbai",
        "Investors who did redemption in last quarter for equity funds.",
        "Investors with no active SIP",
    ],
)
def test_example_queries_remain_validator_clean(query: str):
    plan = parse_investor_search_intent(query)
    assert PlanValidator().validate(plan).can_execute
