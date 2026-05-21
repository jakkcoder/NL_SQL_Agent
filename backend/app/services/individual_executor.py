from typing import Any

from app.db.postgres import PostgresClient
from app.models.search_plan import SearchPlan
from app.services.individual_warehouse_sql import build_warehouse_individual_sql


class IndividualInvestorExecutor:
    """Executes Individual investor searches via catalog-driven warehouse SQL."""

    def __init__(self, db: PostgresClient) -> None:
        self._db = db

    def execute(
        self,
        plan: SearchPlan,
        arn_code: str,
        session_state: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        sql, params = self.build_query(plan, arn_code, session_state=session_state)
        return self._db.fetch_all(sql, params)

    @staticmethod
    def build_query(
        plan: SearchPlan,
        arn_code: str,
        session_state: dict[str, Any] | None = None,
    ) -> tuple[str, list[Any]]:
        """Return SQL and parameters without executing (for session-state debugging)."""

        return build_warehouse_individual_sql(plan, arn_code, session_state=session_state)
