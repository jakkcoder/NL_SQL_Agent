"""Build debug-friendly final SQL snapshots for ADK session state."""

from typing import Any

from app.core.config import AppConfig
from app.models.agent_state import (
    STATE_KEY_FINAL_QUERY,
    STATE_KEY_LAST_SQL,
    STATE_KEY_LAST_SQL_PARAMETERS,
)
from app.models.search_plan import InvestorTab, SearchPlan
from app.services.individual_executor import IndividualInvestorExecutor
from app.services.non_individual_executor import NonIndividualInvestorExecutor
from app.services.search_plan_builder import describe_search_plan


def publish_final_query_to_session(session: dict[str, Any], final_query: dict[str, Any]) -> None:
    """Store final_query plus top-level last_sql / last_sql_parameters for ADK state viewers."""

    session[STATE_KEY_FINAL_QUERY] = final_query
    sql = final_query.get("sql")
    if isinstance(sql, str) and sql.strip():
        session[STATE_KEY_LAST_SQL] = sql
        session[STATE_KEY_LAST_SQL_PARAMETERS] = final_query.get("parameters")
        return

    statements = final_query.get("statements") or []
    if statements:
        chunks: list[str] = []
        for item in statements:
            chunk = item.get("sql") or item.get("template")
            if isinstance(chunk, str) and chunk.strip():
                chunks.append(chunk.strip())
        session[STATE_KEY_LAST_SQL] = "\n---\n".join(chunks) if chunks else None
        session[STATE_KEY_LAST_SQL_PARAMETERS] = [s.get("parameters") for s in statements]
        return

    session.pop(STATE_KEY_LAST_SQL, None)
    session.pop(STATE_KEY_LAST_SQL_PARAMETERS, None)


def build_final_query(plan: SearchPlan, arn_code: str, config: AppConfig) -> dict[str, Any]:
    """Return the SQL the executor would run (for ADK State / local debugging)."""

    summary = describe_search_plan(plan)
    if plan.investor_tab == InvestorTab.INDIVIDUAL:
        sql, params = IndividualInvestorExecutor.build_query(plan, arn_code)
        return {
            "engine": "filter_dp_investor_menu",
            "investor_tab": InvestorTab.INDIVIDUAL.value,
            "combination_strategy": "single_function",
            "sql": _normalize_sql(sql),
            "parameters": _json_safe_params(params),
            "normalized_summary": summary,
        }

    if plan.investor_tab == InvestorTab.NON_INDIVIDUAL:
        raw_statements = NonIndividualInvestorExecutor.build_query_statements(
            plan,
            arn_code,
            max_intersection_rows=config.search.max_intersection_rows,
        )
        statements = [
            {
                "template": item["template"],
                "combination_strategy": item["combination_strategy"],
                "sql": item["sql"],
                "parameters": _json_safe_params(item["parameters"]),
            }
            for item in raw_statements
        ]
        strategy = statements[0]["combination_strategy"] if statements else "default"
        return {
            "engine": "non_individual_sql_templates",
            "investor_tab": InvestorTab.NON_INDIVIDUAL.value,
            "combination_strategy": strategy,
            "statements": statements,
            "normalized_summary": summary,
        }

    return {
        "engine": "unknown",
        "investor_tab": plan.investor_tab.value,
        "normalized_summary": summary,
    }


def _normalize_sql(sql: str) -> str:
    return " ".join(sql.split())


def _json_safe_params(params: list[Any]) -> list[Any]:
    safe: list[Any] = []
    for value in params:
        if isinstance(value, list):
            safe.append([_json_safe_scalar(item) for item in value])
        else:
            safe.append(_json_safe_scalar(value))
    return safe


def _json_safe_scalar(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)
