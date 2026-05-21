from app.models.search_plan import (
    ActivityFilter,
    BinaryFilter,
    EligibilityFilter,
    HoldingFilter,
    IndividualOtmFilter,
    InvestorSubtype,
    InvestorTab,
    InvestorTypeFilter,
    NonIndividualOtmFilter,
    SearchPlan,
    SystematicFilter,
)
from app.services.query_arguments import list_filters_applied, plan_to_query_arguments


def test_individual_no_filter_defaults():
    plan = SearchPlan(investor_tab=InvestorTab.INDIVIDUAL)
    args = plan_to_query_arguments(plan)

    assert args["engine"] == "filter_dp_investor_menu"
    assert args["parameters"]["eligibility"] == "ALL"
    assert args["parameters"]["otm"] == "ALL"
    assert args["parameters"]["holding"] is None
    assert args["parameters"]["systematic"] is None
    assert args["parameters"]["activity"] is None
    assert "No filter" in args["filters_applied"][0]


def test_individual_active_otm_name_mapping():
    plan = SearchPlan(
        investor_tab=InvestorTab.INDIVIDUAL,
        name_search="rahul",
        individual_otm=IndividualOtmFilter.YES,
        investor_type=InvestorTypeFilter.ACTIVE,
    )
    args = plan_to_query_arguments(plan)

    assert args["parameters"]["otm"] == "Y"
    assert args["parameters"]["investor_type"] == "ACTIVE"
    assert args["parameters"]["search_text"] == "rahul"
    labels = list_filters_applied(plan)
    assert any("OTM" in label for label in labels)
    assert any("ACTIVE" in label for label in labels)


def test_individual_sip_holding_activity_rows():
    plan = SearchPlan(
        investor_tab=InvestorTab.INDIVIDUAL,
        holding=HoldingFilter(mode=BinaryFilter.WITH),
        systematic=SystematicFilter(mode=BinaryFilter.WITH, plans=["SIP"]),
        activity=ActivityFilter(
            mode=BinaryFilter.WITH,
            activity_types=["PURCHASE"],
            duration="3 month",
        ),
    )
    args = plan_to_query_arguments(plan)

    assert args["parameters"]["holding"]["mode"] == "WITH"
    assert args["parameters"]["systematic"]["plans"] == ["SIP"]
    assert args["parameters"]["activity"]["activity_types"] == ["PURCHASE"]
    assert args["parameters"]["activity"]["duration"] == "3 month"


def test_non_individual_combination_intersect():
    plan = SearchPlan(
        investor_tab=InvestorTab.NON_INDIVIDUAL,
        non_individual_otm=NonIndividualOtmFilter.YES,
        investor_type=InvestorTypeFilter.ACTIVE,
        investor_subtypes=[InvestorSubtype.CGF],
    )
    args = plan_to_query_arguments(plan)

    assert args["engine"] == "non_individual_sql_templates"
    assert args["combination_strategy"] == "intersect_templates"
    assert set(args["templates"]) == {"otm_yes", "active", "cgf"}


def test_non_individual_single_template():
    plan = SearchPlan(
        investor_tab=InvestorTab.NON_INDIVIDUAL,
        investor_type=InvestorTypeFilter.DORMANT,
    )
    args = plan_to_query_arguments(plan)

    assert args["combination_strategy"] == "single_template"
    assert args["templates"] == ["dormant"]
