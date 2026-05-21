"""End-to-end plan -> query_arguments -> SQL shape -> optional DB execution."""

import pytest

from app.core.config import get_config
from app.db.postgres import (
    DatabaseNotConfiguredError,
    DatabaseUnavailableError,
    PostgresClient,
)
from app.models.search_plan import (
    ActivityFilter,
    BinaryFilter,
    InvestorTab,
    SearchPlan,
    SystematicFilter,
)
from app.services.individual_executor import IndividualInvestorExecutor
from app.services.intent_parser import parse_investor_search_intent
from app.services.non_individual_executor import NonIndividualInvestorExecutor
from app.services.plan_validator import PlanValidator
from app.services.query_arguments import plan_to_query_arguments


class CaptureDb:
    def __init__(self):
        self.query = ""
        self.params: list = []
        self.calls = 0

    def fetch_all(self, query, params):
        self.query = query
        self.params = list(params)
        self.calls += 1
        return []


def test_sip_with_time_window_maps_to_activity_not_systematic():
    plan = parse_investor_search_intent("individual investors with SIP in last 3 months")

    assert plan.investor_tab == InvestorTab.INDIVIDUAL
    assert plan.systematic.mode == BinaryFilter.ALL
    assert plan.activity.mode == BinaryFilter.WITH
    assert plan.activity.activity_types == ["SIP"]
    assert plan.activity.duration == "3 month"

    args = plan_to_query_arguments(plan)
    assert args["parameters"]["systematic"] is None
    assert args["parameters"]["activity"]["activity_types"] == ["SIP"]
    assert args["parameters"]["activity"]["duration"] == "3 month"


def test_sip_without_time_window_maps_to_systematic():
    plan = parse_investor_search_intent("individual investors with SIP")

    assert plan.systematic.mode == BinaryFilter.WITH
    assert "SIP" in plan.systematic.plans
    assert plan.activity.mode == BinaryFilter.ALL


def test_individual_executor_sql_shape_default():
    db = CaptureDb()
    plan = SearchPlan(investor_tab=InvestorTab.INDIVIDUAL)
    IndividualInvestorExecutor(db).execute(plan, "ARN-TEST")

    assert "filter_dp_investor_menu" in db.query
    assert db.params[:5] == ["ARN-TEST", "ALL", "ALL", "ALL", []]
    assert "NULL" in db.query


def test_individual_executor_sql_includes_activity_composite():
    db = CaptureDb()
    plan = SearchPlan(
        investor_tab=InvestorTab.INDIVIDUAL,
        activity=ActivityFilter(
            mode=BinaryFilter.WITH,
            activity_types=["PURCHASE"],
            duration="3 month",
        ),
    )
    IndividualInvestorExecutor(db).execute(plan, "ARN-TEST")

    assert "::investor_activity" in db.query
    assert "WITH" in db.params
    assert ["PURCHASE"] in db.params
    assert "3 month" in db.params


def test_individual_executor_sql_includes_systematic_composite():
    db = CaptureDb()
    plan = SearchPlan(
        investor_tab=InvestorTab.INDIVIDUAL,
        systematic=SystematicFilter(mode=BinaryFilter.WITH, plans=["SIP"]),
    )
    IndividualInvestorExecutor(db).execute(plan, "ARN-TEST")

    assert "::systematic_plan" in db.query
    assert ["SIP"] in db.params


def test_non_individual_intersect_sql_calls():
    db = CaptureDb()
    plan = parse_investor_search_intent("active non-individual investors with OTM")
    config = get_config()
    NonIndividualInvestorExecutor(db, config).execute(plan, "ARN-TEST")

    assert db.calls == 2


@pytest.mark.integration
def test_live_db_default_individual_list():
    config = get_config()
    if not config.database_url_value:
        pytest.skip("DEV_DATABASE_URL not configured")

    plan = parse_investor_search_intent("show individual investors")
    assert PlanValidator().validate(plan).can_execute

    db_config = config.database
    db = PostgresClient(
        config.database_url_value,
        db_config.statement_timeout_ms,
        min_size=1,
        max_size=1,
        connect_timeout_seconds=db_config.connect_timeout_seconds,
        pool_timeout_seconds=db_config.pool_timeout_seconds,
    )
    try:
        db.open()
        rows = IndividualInvestorExecutor(db).execute(plan, config.search.default_dev_arn)
    except DatabaseNotConfiguredError:
        pytest.skip("database not configured")
    except DatabaseUnavailableError:
        pytest.skip("database unreachable")
    finally:
        db.close()

    assert isinstance(rows, list)
