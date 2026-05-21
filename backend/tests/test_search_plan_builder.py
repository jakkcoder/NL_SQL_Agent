import json

import pytest

from app.models.search_plan import (
    BinaryFilter,
    EligibilityFilter,
    IndividualOtmFilter,
    InvestorTab,
    InvestorTypeFilter,
    SearchPlanLLMOutput,
)
from app.services.search_plan_builder import (
    _llm_output_to_search_plan,
    build_search_plan,
    describe_search_plan,
)


def test_llm_output_maps_individual_filters():
    llm_output = SearchPlanLLMOutput.model_validate(
        {
            "investor_tab": "individual",
            "normalized_query": "Show active individual investors with OTM named Rahul with SIP in the last 3 months",
            "name_search": "rahul",
            "eligibility": "ALL",
            "individual_otm": "Y",
            "non_individual_otm": "ALL",
            "investor_type": "ACTIVE",
            "investor_subtypes": [],
            "holding_mode": "ALL",
            "systematic_mode": "WITH",
            "systematic_plans": ["SIP"],
            "activity_mode": "WITH",
            "activity_types": ["SIP"],
            "activity_duration": "3 month",
            "unsupported_reasons": [],
        }
    )
    plan = _llm_output_to_search_plan(llm_output, page_limit=25, page_offset=0)

    assert plan.investor_tab == InvestorTab.INDIVIDUAL
    assert plan.name_search == "rahul"
    assert plan.individual_otm == IndividualOtmFilter.YES
    assert plan.investor_type == InvestorTypeFilter.ACTIVE
    assert plan.systematic.mode == BinaryFilter.WITH
    assert plan.systematic.plans == ["SIP"]
    assert plan.activity.mode == BinaryFilter.WITH
    assert plan.activity.duration == "3 month"


def test_build_search_plan_uses_llm(monkeypatch):
    llm_json = {
        "investor_tab": "individual",
        "normalized_query": "Show dormant individual investors without OTM",
        "name_search": None,
        "eligibility": "ALL",
        "individual_otm": "NOT_AVAILABLE",
        "non_individual_otm": "ALL",
        "investor_type": "DORMANT",
        "investor_subtypes": [],
        "holding_mode": "ALL",
        "systematic_mode": "ALL",
        "systematic_plans": [],
        "activity_mode": "ALL",
        "activity_types": [],
        "activity_duration": "1 month",
        "unsupported_reasons": [],
    }

    class FakeMessage:
        content = json.dumps(llm_json)

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        choices = [FakeChoice()]

    monkeypatch.setattr(
        "app.services.search_plan_builder.litellm.completion",
        lambda **kwargs: FakeResponse(),
    )

    plan, source, normalized = build_search_plan("show dormnt individul invstors w/o otm", {})

    assert source == "llm"
    assert "dormant" in normalized.lower()
    assert plan.investor_tab == InvestorTab.INDIVIDUAL
    assert plan.individual_otm == IndividualOtmFilter.NO
    assert plan.investor_type == InvestorTypeFilter.DORMANT


def test_build_search_plan_applies_session_investor_tab(monkeypatch):
    llm_json = {
        "investor_tab": "unknown",
        "normalized_query": "Show investors with CGF",
        "name_search": None,
        "eligibility": "ALL",
        "individual_otm": "ALL",
        "non_individual_otm": "ALL",
        "investor_type": "ALL",
        "investor_subtypes": ["CGF"],
        "holding_mode": "ALL",
        "systematic_mode": "ALL",
        "systematic_plans": [],
        "activity_mode": "ALL",
        "activity_types": [],
        "activity_duration": "1 month",
        "unsupported_reasons": [],
    }

    class FakeMessage:
        content = json.dumps(llm_json)

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        choices = [FakeChoice()]

    monkeypatch.setattr(
        "app.services.search_plan_builder.litellm.completion",
        lambda **kwargs: FakeResponse(),
    )

    plan, _, _ = build_search_plan("with cgf", {"investor_tab": "individual"})

    assert plan.investor_tab == InvestorTab.INDIVIDUAL


def test_build_search_plan_falls_back_when_llm_fails(monkeypatch):
    monkeypatch.setattr(
        "app.services.search_plan_builder.litellm.completion",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("down")),
    )

    plan, source, _ = build_search_plan(
        "Show active individual investors with OTM named Rahul",
        {},
    )

    assert source == "fallback"
    assert plan.investor_tab == InvestorTab.INDIVIDUAL
    assert plan.individual_otm == IndividualOtmFilter.YES
    assert plan.name_search is None


def test_describe_search_plan_includes_filters():
    llm_output = SearchPlanLLMOutput.model_validate(
        {
            "investor_tab": "individual",
            "normalized_query": "Show active individual investors with OTM named Rahul",
            "name_search": "rahul",
            "individual_otm": "Y",
            "investor_type": "ACTIVE",
            "eligibility": "YES",
            "non_individual_otm": "ALL",
            "investor_subtypes": [],
            "holding_mode": "ALL",
            "systematic_mode": "ALL",
            "systematic_plans": [],
            "activity_mode": "ALL",
            "activity_types": [],
            "activity_duration": "1 month",
            "unsupported_reasons": [],
        }
    )
    plan = _llm_output_to_search_plan(llm_output, 25, 0)
    summary = describe_search_plan(plan)

    assert "individual" in summary
    assert "rahul" in summary
    assert "otm" in summary


@pytest.mark.parametrize(
    "user_query",
    [
        "Investors named 'Bhavin' in Mumbai or Ahmedabad.",
        "Need investor Bhavin from Mumbai please",
        "Looking for Bhavin Ahmedabad clients",
    ],
)
def test_build_search_plan_llm_name_search_varied_phrasing(monkeypatch, user_query):
    """name_search comes from the search-plan LLM; varied user wording still maps when the model returns it (mocked)."""

    llm_json = {
        "investor_tab": "individual",
        "normalized_query": "Show individual investors named Bhavin",
        "name_search": "bhavin",
        "eligibility": "ALL",
        "individual_otm": "ALL",
        "non_individual_otm": "ALL",
        "investor_type": "ALL",
        "investor_subtypes": [],
        "holding_mode": "ALL",
        "systematic_mode": "ALL",
        "systematic_plans": [],
        "activity_mode": "ALL",
        "activity_types": [],
        "activity_duration": "1 month",
        "unsupported_reasons": [],
    }

    class FakeMessage:
        content = json.dumps(llm_json)

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        choices = [FakeChoice()]

    monkeypatch.setattr(
        "app.services.search_plan_builder.litellm.completion",
        lambda **kwargs: FakeResponse(),
    )

    plan, source, _ = build_search_plan(user_query, {})
    assert source == "llm"
    assert plan.name_search == "bhavin"
