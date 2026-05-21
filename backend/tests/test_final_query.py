from app.core.config import AppConfig
from app.models.search_plan import BinaryFilter, InvestorTab, SearchPlan
from app.models.agent_state import STATE_KEY_FINAL_QUERY, STATE_KEY_LAST_SQL, STATE_KEY_LAST_SQL_PARAMETERS
from app.services.final_query import build_final_query, publish_final_query_to_session


def _config() -> AppConfig:
    return AppConfig(dev_database_url=None, prod_database_url=None)


def test_build_final_query_individual_stp_includes_sql():
    plan = SearchPlan(investor_tab=InvestorTab.INDIVIDUAL)
    plan.systematic.mode = BinaryFilter.WITH
    plan.systematic.plans = ["STP"]

    final_query = build_final_query(plan, "ARN-0411", _config())

    assert final_query["engine"] == "filter_dp_investor_menu"
    assert "filter_dp_investor_menu" in final_query["sql"]
    assert "::systematic_plan" in final_query["sql"]
    assert final_query["parameters"][0] == "ARN-0411"
    assert "STP" in str(final_query["parameters"])
    assert "systematic=WITH (STP)" in final_query["normalized_summary"]


def test_build_final_query_default_individual_uses_null_composites():
    plan = SearchPlan(investor_tab=InvestorTab.INDIVIDUAL)

    final_query = build_final_query(plan, "ARN-TEST", _config())

    assert "NULL" in final_query["sql"]
    assert final_query["combination_strategy"] == "single_function"


def test_publish_final_query_to_session_sets_top_level_sql_keys():
    plan = SearchPlan(investor_tab=InvestorTab.INDIVIDUAL)
    fq = build_final_query(plan, "ARN-TEST", _config())
    session: dict = {}
    publish_final_query_to_session(session, fq)

    assert session[STATE_KEY_FINAL_QUERY] == fq
    assert session[STATE_KEY_LAST_SQL] == fq["sql"]
    assert session[STATE_KEY_LAST_SQL_PARAMETERS] == fq["parameters"]
