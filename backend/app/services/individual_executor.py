from typing import Any

from app.db.postgres import PostgresClient
from app.models.search_plan import (
    BinaryFilter,
    SearchPlan,
)


class IndividualInvestorExecutor:
    """Executes Individual investor searches through filter_dp_investor_menu()."""

    def __init__(self, db: PostgresClient) -> None:
        self._db = db

    def execute(self, plan: SearchPlan, arn_code: str) -> list[dict[str, Any]]:
        function_sql, params = self._build_function_call(plan, arn_code)
        return self._db.fetch_all(function_sql, params)

    def _build_function_call(self, plan: SearchPlan, arn_code: str) -> tuple[str, list[Any]]:
        params: list[Any] = [
            arn_code,
            plan.eligibility.value,
            plan.individual_otm.value,
            plan.investor_type.value,
            [subtype.value for subtype in plan.investor_subtypes],
        ]

        holding_sql = self._holding_sql(plan, params)
        systematic_sql = self._systematic_sql(plan, params)
        activity_sql = self._activity_sql(plan, params)

        params.extend(
            [
                _search_text(plan.name_search),
                plan.sort_key,
                plan.sort_order,
                plan.page_limit,
                plan.page_offset,
                "Y",
            ]
        )

        sql = f"""
            SELECT *
            FROM filter_dp_investor_menu(
                %s,
                %s,
                %s,
                %s,
                %s::TEXT[],
                {holding_sql},
                {systematic_sql},
                {activity_sql},
                %s,
                %s,
                %s,
                %s,
                %s,
                %s
            )
        """
        return sql, params

    def _holding_sql(self, plan: SearchPlan, params: list[Any]) -> str:
        if plan.holding.mode == BinaryFilter.ALL:
            return "NULL"
        params.extend([plan.holding.mode.value, plan.holding.schemes, plan.holding.inv_options])
        return "ROW(%s, %s::TEXT[], %s::TEXT[])::current_holdings"

    def _systematic_sql(self, plan: SearchPlan, params: list[Any]) -> str:
        if plan.systematic.mode == BinaryFilter.ALL:
            return "NULL"
        params.extend(
            [
                plan.systematic.mode.value,
                plan.systematic.plans,
                plan.systematic.schemes,
                plan.systematic.inv_options,
            ]
        )
        return "ROW(%s, %s::TEXT[], %s::TEXT[], %s::TEXT[])::systematic_plan"

    def _activity_sql(self, plan: SearchPlan, params: list[Any]) -> str:
        if plan.activity.mode == BinaryFilter.ALL:
            return "NULL"
        params.extend(
            [
                plan.activity.mode.value,
                plan.activity.activity_types,
                plan.activity.schemes,
                plan.activity.inv_options,
                plan.activity.duration,
            ]
        )
        return "ROW(%s, %s::TEXT[], %s::TEXT[], %s::TEXT[], %s)::investor_activity"


def _search_text(name_search: str | None) -> str | None:
    if not name_search:
        return None
    return f"%{name_search.lower()}%"
