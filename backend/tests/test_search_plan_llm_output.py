from app.models.search_plan import SearchPlanLLMOutput


def test_activity_duration_null_defaults_to_one_month():
    output = SearchPlanLLMOutput.model_validate(
        {
            "investor_tab": "individual",
            "normalized_query": "Show individual investors",
            "activity_duration": None,
        }
    )
    assert output.activity_duration == "1 month"
