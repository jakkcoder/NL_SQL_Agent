from typing import Any

from app.core.config import AppConfig, get_config
from app.db.postgres import DatabaseNotConfiguredError, PostgresClient
from app.models.chat import ChatMessage
from app.models.search_plan import InvestorTab
from app.services.audit import AuditLogger
from app.services.individual_executor import IndividualInvestorExecutor
from app.services.intent_parser import parse_investor_search_intent
from app.services.non_individual_executor import NonIndividualInvestorExecutor
from app.services.plan_validator import PlanValidator
from app.services.result_formatter import format_rows_for_chat


def parse_with_context(
    query: str,
    messages: list[ChatMessage],
    page_limit: int,
    page_offset: int,
) -> dict[str, Any]:
    """Backend helper that mirrors the ADK tool's deterministic parsing contract."""

    plan = parse_investor_search_intent(
        query=query,
        messages=messages,
        page_limit=page_limit,
        page_offset=page_offset,
    )
    validation = PlanValidator().validate(plan)
    return {
        "plan": plan,
        "validation": validation,
    }


def search_investors_tool(
    query: str,
    arn_code: str = "",
    page_limit: int = 0,
    page_offset: int = 0,
) -> dict[str, Any]:
    """Parse, validate, execute, and format an investor search request.

    Args:
        query: Distributor's natural-language investor search request.
        arn_code: Distributor ARN. Leave empty to use the configured local default.
        page_limit: Optional page size. Use 0 to apply the configured default.
        page_offset: Optional result offset. Use 0 for the first page.
    """

    config = get_config()
    limit = page_limit or config.search.default_page_limit
    offset = page_offset or 0
    parsed = parse_with_context(
        query=query,
        messages=[],
        page_limit=limit,
        page_offset=offset,
    )
    plan = parsed["plan"]
    validation = parsed["validation"]
    effective_arn = arn_code or config.search.default_dev_arn

    AuditLogger().log_event(
        "search_plan",
        {
            "investor_tab": plan.investor_tab.value,
            "validation_status": validation.status,
            "arn_code": effective_arn,
        },
    )

    if not validation.can_execute:
        return {
            "reply": validation.message or "I need more information before searching.",
            "needs_clarification": validation.status == "clarification",
            "rows": [],
            "count": 0,
            "page": None,
            "status": validation.status,
        }

    db_config = config.database
    db = PostgresClient(
        config.database_url_value,
        db_config.statement_timeout_ms,
        min_size=db_config.pool_min_size,
        max_size=db_config.pool_max_size,
    )
    try:
        db.open()
        rows = _execute_search(db, config, plan, effective_arn)
    except DatabaseNotConfiguredError as exc:
        return {
            "reply": str(exc),
            "needs_clarification": False,
            "rows": [],
            "count": 0,
            "page": None,
            "status": "error",
        }
    finally:
        db.close()

    return {
        "reply": format_rows_for_chat(rows, plan.page_limit, plan.page_offset),
        "needs_clarification": False,
        "rows": _json_safe(rows),
        "count": len(rows),
        "page": {"limit": plan.page_limit, "offset": plan.page_offset},
        "status": "ok",
    }


def _execute_search(db: PostgresClient, config: AppConfig, plan, arn_code: str) -> list[dict[str, Any]]:
    if plan.investor_tab == InvestorTab.INDIVIDUAL:
        return IndividualInvestorExecutor(db).execute(plan, arn_code)
    if plan.investor_tab == InvestorTab.NON_INDIVIDUAL:
        return NonIndividualInvestorExecutor(db, config).execute(plan, arn_code)
    return []


def _json_safe(value):
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)
