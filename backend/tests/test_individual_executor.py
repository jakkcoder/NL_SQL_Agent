from app.models.search_plan import BinaryFilter, SearchPlan
from app.services.individual_executor import IndividualInvestorExecutor


class DummyDb:
    def fetch_all(self, query, params):
        self.query = query
        self.params = params
        return []


def test_default_function_call_uses_null_composites():
    db = DummyDb()
    executor = IndividualInvestorExecutor(db)

    executor.execute(SearchPlan(), "ARN-0411")

    assert "filter_dp_investor_menu" in db.query
    assert "NULL" in db.query
    assert db.params[:5] == ["ARN-0411", "ALL", "ALL", "ALL", []]


def test_holding_filter_uses_current_holdings_composite():
    db = DummyDb()
    executor = IndividualInvestorExecutor(db)
    plan = SearchPlan()
    plan.holding.mode = BinaryFilter.WITH

    executor.execute(plan, "ARN-0411")

    assert "::current_holdings" in db.query
    assert "WITH" in db.params
