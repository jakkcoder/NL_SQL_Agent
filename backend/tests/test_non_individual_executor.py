from app.core.config import AppConfig
from app.models.search_plan import InvestorSubtype, InvestorTypeFilter, NonIndividualOtmFilter, SearchPlan
from app.services.non_individual_executor import NonIndividualInvestorExecutor


class DummyDb:
    def __init__(self):
        self.calls = []

    def fetch_all(self, query, params):
        self.calls.append((query, params))
        if "CURRENT_DATE - last_trxn_date <= 180" in query:
            return [{"uuid": "1", "first_name": "A"}]
        if "EXISTS" in query:
            return [{"uuid": "1", "first_name": "A"}, {"uuid": "2", "first_name": "B"}]
        return []


def test_single_non_individual_filter_runs_one_template():
    db = DummyDb()
    executor = NonIndividualInvestorExecutor(db, AppConfig(dev_database_url=None, prod_database_url=None))
    plan = SearchPlan()
    plan.non_individual_otm = NonIndividualOtmFilter.YES

    executor.execute(plan, "ARN-0411")

    assert len(db.calls) == 1
    assert "multiple_bank" in db.calls[0][0]


def test_combination_runs_separate_queries_and_intersects():
    db = DummyDb()
    executor = NonIndividualInvestorExecutor(db, AppConfig(dev_database_url=None, prod_database_url=None))
    plan = SearchPlan()
    plan.non_individual_otm = NonIndividualOtmFilter.YES
    plan.investor_type = InvestorTypeFilter.ACTIVE

    rows = executor.execute(plan, "ARN-0411")

    assert len(db.calls) == 2
    assert rows == [{"uuid": "1", "first_name": "A"}]


def test_cgf_minor_uses_single_combined_template():
    db = DummyDb()
    executor = NonIndividualInvestorExecutor(db, AppConfig(dev_database_url=None, prod_database_url=None))
    plan = SearchPlan()
    plan.investor_subtypes = [InvestorSubtype.CGF, InvestorSubtype.MINOR]

    executor.execute(plan, "ARN-0411")

    assert len(db.calls) == 1
    assert "OR (cm.inv_type = '02' OR cm.inv_type = '26')" in db.calls[0][0]
