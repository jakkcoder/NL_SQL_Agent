"""Validate NL -> filters against Individual Investors CSV (rows 2-31)."""

import pytest

from app.models.search_plan import BinaryFilter, InvestorTab
from app.services.individual_executor import IndividualInvestorExecutor
from app.services.intent_parser import parse_investor_search_intent
from app.services.plan_validator import PlanValidator
from app.services.query_arguments import plan_to_query_arguments
from tests.fixtures.individual_csv_mapping import INDIVIDUAL_CSV_CASES, CsvFilterExpectation


class CaptureDb:
    def fetch_all(self, query, params):
        self.query = query
        self.params = list(params)
        return []


def _assert_plan_matches_csv(plan, expected: CsvFilterExpectation) -> None:
    assert plan.investor_tab == InvestorTab.INDIVIDUAL, expected.label
    assert plan.eligibility.value == expected.eligibility, expected.label
    assert plan.individual_otm.value == expected.otm, expected.label
    assert plan.investor_type.value == expected.investor_type, expected.label
    assert [s.value for s in plan.investor_subtypes] == expected.investor_subtypes, expected.label
    assert plan.holding.mode.value == expected.holding_mode, expected.label
    assert plan.systematic.mode.value == expected.systematic_mode, expected.label
    assert plan.activity.mode.value == expected.activity_mode, expected.label

    if expected.systematic_plans is not None:
        assert sorted(plan.systematic.plans) == sorted(expected.systematic_plans), expected.label
    if expected.activity_types is not None:
        assert sorted(plan.activity.activity_types) == sorted(expected.activity_types), expected.label
    if expected.activity_mode == "WITH":
        assert plan.activity.duration == expected.activity_duration, expected.label
    if expected.name_search is not None:
        assert plan.name_search == expected.name_search, expected.label

    validation = PlanValidator().validate(plan)
    assert validation.can_execute, f"{expected.label}: {validation.message}"

    args = plan_to_query_arguments(plan)
    assert args["engine"] == "filter_dp_investor_menu", expected.label
    params = args["parameters"]
    assert params["eligibility"] == expected.eligibility
    assert params["otm"] == expected.otm
    assert params["investor_type"] == expected.investor_type
    assert params["investor_subtypes"] == expected.investor_subtypes

    if expected.holding_mode == "ALL":
        assert params["holding"] is None
    else:
        assert params["holding"]["mode"] == expected.holding_mode

    if expected.systematic_mode == "ALL":
        assert params["systematic"] is None
    elif expected.systematic_plans is not None:
        assert params["systematic"]["mode"] == expected.systematic_mode
        assert sorted(params["systematic"]["plans"]) == sorted(expected.systematic_plans)

    if expected.activity_mode == "ALL":
        assert params["activity"] is None
    elif expected.activity_types is not None:
        assert params["activity"]["mode"] == expected.activity_mode
        assert sorted(params["activity"]["activity_types"]) == sorted(expected.activity_types)

    db = CaptureDb()
    IndividualInvestorExecutor(db).execute(plan, "ARN-CSV-TEST")
    if expected.sql_has_holding:
        assert "::current_holdings" in db.query, expected.label
    else:
        assert "current_holdings" not in db.query or "NULL" in db.query.split("current_holdings")[0]
    if expected.sql_has_systematic:
        assert "::systematic_plan" in db.query, expected.label
    if expected.sql_has_activity:
        assert "::investor_activity" in db.query, expected.label
    if expected.name_search:
        assert expected.name_search in db.params or f"%{expected.name_search}%" in db.params


@pytest.mark.parametrize("case", INDIVIDUAL_CSV_CASES, ids=lambda c: f"row{c.row}_{c.label}")
def test_csv_mapping_generates_expected_filters(case: CsvFilterExpectation):
    plan = parse_investor_search_intent(case.query)
    _assert_plan_matches_csv(plan, case)
