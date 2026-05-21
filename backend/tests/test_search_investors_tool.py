"""search_investors_tool database error handling."""

from app.agents.tools import search_investors_tool
from app.db.postgres import DatabaseUnavailableError
from app.models.agent_state import STATE_KEY_LAST_SEARCH_PLAN, STATE_KEY_PLAN_QUERY
from app.models.search_plan import InvestorTab, SearchPlan
from tests.test_agent_tools import FakeToolContext


def test_search_investors_tool_returns_error_when_db_unreachable(monkeypatch):
    plan = SearchPlan(investor_tab=InvestorTab.INDIVIDUAL)
    tool_context = FakeToolContext(
        {
            STATE_KEY_PLAN_QUERY: "show minor individual investors",
            STATE_KEY_LAST_SEARCH_PLAN: plan.model_dump(mode="json"),
        }
    )

    monkeypatch.setattr(
        "app.agents.tools._execute_search",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            DatabaseUnavailableError(
                "Could not connect to the investor database. Start PostgreSQL "
                "(or fix DEV_DATABASE_URL) and retry your search."
            )
        ),
    )

    class NoopDb:
        def open(self) -> None:
            return None

        def close(self) -> None:
            return None

    monkeypatch.setattr("app.agents.tools.PostgresClient", lambda *a, **k: NoopDb())

    result = search_investors_tool("show minor individual investors", tool_context)

    assert result["status"] == "error"
    assert "database" in result["reply"].lower()
    assert result["routing_state"]["step"] == "blocked"
