from typing import Any

try:
    from google.adk.tools import ToolContext
except ModuleNotFoundError:
    ToolContext = Any

from app.core.config import AppConfig, get_config
from app.db.postgres import (
    DatabaseNotConfiguredError,
    DatabaseUnavailableError,
    PostgresClient,
)
from app.models.agent_state import (
    AgentToolOutput,
    HDFC_GREETING_MESSAGE,
    NON_INDIVIDUAL_NOT_SUPPORTED,
    IntentDetectionOutput,
    InvestorSchemaFetchToolOutput,
    PageMeta,
    RoutingIntent,
    RoutingRoute,
    RoutingState,
    RoutingStep,
    SearchArgumentsAnalysisOutput,
    STATE_KEY_INVESTOR_SCHEMA_CONTRACT_COMPACT,
    STATE_KEY_INVESTOR_SCHEMA_CONTRACT_META,
    STATE_KEY_INVESTOR_SCHEMA_SESSION_FETCHED,
    STATE_KEY_LAST_NORMALIZED_QUERY,
    STATE_KEY_LAST_SEARCH_PLAN,
    STATE_KEY_PLAN_QUERY,
    STATE_KEY_PLAN_SOURCE,
    STATE_KEY_PLAN_VALIDATION_STATUS,
    STATE_KEY_HAS_SEARCH_FILTERS,
    STATE_KEY_QUERY_ARGUMENTS,
    STATE_KEY_ROUTING_STATE,
)
from app.models.chat import ChatMessage
from app.models.search_plan import InvestorTab, SearchPlan
from app.services.audit import AuditLogger
from app.services.arn_scope_guard import arn_scope_block_reason
from app.services.individual_executor import IndividualInvestorExecutor
from app.services.non_individual_executor import NonIndividualInvestorExecutor
from app.services.plan_validator import PlanValidator
from app.services.react_dynamic_sql_engine import run_react_dynamic_sql
from app.services.result_formatter import format_rows_for_chat
from app.services.final_query import build_final_query, publish_final_query_to_session
from app.services.investor_schema_contract import (
    ensure_investor_schema_for_search_session,
    schema_for_search_plan_llm,
)
from app.services.query_arguments import list_filters_applied, plan_to_query_arguments
from app.services.search_plan_builder import build_search_plan, describe_search_plan
from app.services.intent_detection import detect_routing_intent
from app.services.routing import (
    DEFAULT_INVESTOR_TAB,
    classify_message,
    write_detect_temp_state,
    write_session_state,
)

UNSUPPORTED_REPLY = (
    "I can help only with Individual investor search in this MVP. "
    "Try a search like show my investors or investors with SIP."
)


def fetch_investor_schema_contract_tool(
    tool_context: ToolContext,
    force: bool = False,
) -> dict[str, Any]:
    """Manually refresh PostgreSQL column metadata (optional; auto-fetch runs once per session).

    By default, the first ``build_search_plan`` / search flow in a session already loads
    schema into session and updates ``investor_db_schema_contract.json``. Call this tool
    with ``force=true`` only when you need to re-pull after DB migrations.
    """

    if tool_context.state.get(STATE_KEY_INVESTOR_SCHEMA_SESSION_FETCHED) and not force:
        compact = tool_context.state.get(STATE_KEY_INVESTOR_SCHEMA_CONTRACT_COMPACT) or {}
        return _dump_model(
            InvestorSchemaFetchToolOutput(
                status="ok",
                message=(
                    "Schema already fetched this session; skipped live pull. "
                    "Pass force=true to refresh from the database and rewrite the JSON file."
                ),
                table_count=int(compact.get("table_count") or 0),
                column_count=int(compact.get("column_count") or 0),
                session_state_keys_written=[],
            )
        )

    if force:
        tool_context.state.pop(STATE_KEY_INVESTOR_SCHEMA_SESSION_FETCHED, None)
        tool_context.state.pop(STATE_KEY_INVESTOR_SCHEMA_CONTRACT_COMPACT, None)
        tool_context.state.pop(STATE_KEY_INVESTOR_SCHEMA_CONTRACT_META, None)

    config = get_config()
    ensure_investor_schema_for_search_session(tool_context.state, config.database_url_value)

    compact = tool_context.state.get(STATE_KEY_INVESTOR_SCHEMA_CONTRACT_COMPACT) or {}
    meta = tool_context.state.get(STATE_KEY_INVESTOR_SCHEMA_CONTRACT_META) or {}
    msg = (
        "Schema refreshed for this session (manual). "
        f"Tables: {compact.get('table_count', 0)}, columns: {compact.get('column_count', 0)}."
    )
    if meta.get("tables_missing_in_database"):
        msg += f" Warnings: {meta['tables_missing_in_database']}"

    return _dump_model(
        InvestorSchemaFetchToolOutput(
            status="ok",
            source=meta.get("source"),
            message=msg,
            table_count=int(compact.get("table_count") or 0),
            column_count=int(compact.get("column_count") or 0),
            session_state_keys_written=[
                STATE_KEY_INVESTOR_SCHEMA_CONTRACT_COMPACT,
                STATE_KEY_INVESTOR_SCHEMA_CONTRACT_META,
                STATE_KEY_INVESTOR_SCHEMA_SESSION_FETCHED,
            ],
        )
    )


def _format_dynamic_sql_rows(rows: list[dict[str, Any]]) -> str:
    """Format arbitrary SELECT rows without assuming investor_menu column names."""

    if not rows:
        return "No rows matched your question."
    keys = list(rows[0].keys())
    preview_keys = keys[:10]
    lines = [
        f"Found {len(rows)} row(s). Showing up to 15 rows. Columns: {', '.join(keys)}.",
    ]
    for idx, row in enumerate(rows[:15], start=1):
        chunks: list[str] = []
        for key in preview_keys:
            val = row.get(key)
            text = "null" if val is None else str(val)
            if len(text) > 72:
                text = text[:69] + "..."
            chunks.append(f"{key}={text}")
        lines.append(f"{idx}. " + " | ".join(chunks))
    if len(rows) > 15:
        lines.append(f"... {len(rows) - 15} more row(s) not shown.")
    return "\n".join(lines)


def _routing_state_from_session(tool_context: ToolContext, question: str) -> RoutingState:
    raw = tool_context.state.get(STATE_KEY_ROUTING_STATE)
    if isinstance(raw, dict):
        try:
            parsed = RoutingState.model_validate(raw)
            return parsed.model_copy(update={"last_user_message": question or parsed.last_user_message})
        except Exception:
            pass
    return RoutingState(
        current_intent=RoutingIntent.INVESTOR_SEARCH,
        route=RoutingRoute.SEARCH_INVESTORS_TOOL,
        step=RoutingStep.READY_TO_SEARCH,
        investor_tab=InvestorTab.INDIVIDUAL,
        last_user_message=question,
    )


def run_dynamic_investor_sql_tool(
    question: str,
    tool_context: ToolContext,
    arn_code: str = "",
) -> dict[str, Any]:
    """Run contract-grounded read-only SQL via LLM ReAct (gated by ``DYNAMIC_INVESTOR_SQL_ENABLED``)."""

    config = get_config()
    if not config.dynamic_investor_sql_enabled:
        blocked = _routing_state_from_session(tool_context, question).model_copy(
            update={"step": RoutingStep.BLOCKED},
        )
        write_session_state(tool_context.state, blocked)
        return _dump_model(
            AgentToolOutput(
                reply="Dynamic investor SQL is disabled for this deployment.",
                status="error",
                routing_state=blocked,
            )
        )

    trusted_arn = config.search.default_dev_arn
    scope_msg = arn_scope_block_reason(
        user_query=question,
        tool_arn_arg=arn_code.strip() if arn_code and arn_code.strip() else None,
        trusted_arn=trusted_arn,
    )
    if scope_msg:
        return _dump_model(_arn_scope_blocked_agent_output(question, tool_context, scope_msg))

    ensure_investor_schema_for_search_session(tool_context.state, config.database_url_value)
    schema_compact = schema_for_search_plan_llm(tool_context.state)
    if not schema_compact:
        rs = _routing_state_from_session(tool_context, question).model_copy(
            update={"step": RoutingStep.BLOCKED},
        )
        write_session_state(tool_context.state, rs)
        return _dump_model(
            AgentToolOutput(
                reply=(
                    "Investor schema contract is not available. "
                    "Run a normal search once or call fetch_investor_schema_contract_tool, then retry."
                ),
                status="error",
                routing_state=rs,
            )
        )

    if not config.database_url_value:
        rs = _routing_state_from_session(tool_context, question).model_copy(
            update={"step": RoutingStep.BLOCKED},
        )
        write_session_state(tool_context.state, rs)
        return _dump_model(
            AgentToolOutput(
                reply="Database is not configured; dynamic SQL cannot run.",
                status="error",
                routing_state=rs,
            )
        )

    db_config = config.database
    db = PostgresClient(
        config.database_url_value,
        db_config.statement_timeout_ms,
        min_size=db_config.pool_min_size,
        max_size=db_config.pool_max_size,
        connect_timeout_seconds=db_config.connect_timeout_seconds,
        pool_timeout_seconds=db_config.pool_timeout_seconds,
    )
    result: dict[str, Any] | None = None
    try:
        db.open()
        result = run_react_dynamic_sql(
            user_question=question,
            trusted_arn=trusted_arn,
            schema_compact=schema_compact,
            db=db,
            llm_model=config.dynamic_sql_llm_model_resolved,
            llm_timeout_seconds=config.llm.request_timeout_seconds,
            max_output_tokens=config.llm.max_output_tokens,
        )
    except (DatabaseNotConfiguredError, DatabaseUnavailableError) as exc:
        rs = _routing_state_from_session(tool_context, question).model_copy(
            update={"step": RoutingStep.BLOCKED},
        )
        write_session_state(tool_context.state, rs)
        return _dump_model(
            AgentToolOutput(
                reply=f"Database error: {exc}",
                status="error",
                routing_state=rs,
            )
        )
    finally:
        db.close()

    assert result is not None
    AuditLogger().log_event(
        "dynamic_investor_sql",
        {
            "ok": result["ok"],
            "attempts": result["attempts"],
            "row_count": len(result.get("rows") or []),
        },
    )

    if result["ok"]:
        publish_final_query_to_session(
            tool_context.state,
            {
                "engine": "react_dynamic_sql",
                "sql": result["final_sql"],
                "parameters": result["parameters"],
                "normalized_summary": question[:2000],
            },
        )
        done = _routing_state_from_session(tool_context, question).model_copy(
            update={"step": RoutingStep.COMPLETED, "route": RoutingRoute.SEARCH_INVESTORS_TOOL},
        )
        write_session_state(tool_context.state, done)
        warnings: list[str] = []
        if result.get("attempts", 0) > 1:
            warnings.append(f"dynamic_sql_attempts={result['attempts']}")
        rows_out = result["rows"] or []
        return _dump_model(
            AgentToolOutput(
                reply=_format_dynamic_sql_rows(rows_out),
                rows=_json_safe(rows_out),
                count=len(rows_out),
                page=PageMeta(limit=min(500, len(rows_out)), offset=0),
                status="ok",
                routing_state=done,
                warnings=warnings,
            )
        )

    rs = _routing_state_from_session(tool_context, question).model_copy(
        update={"step": RoutingStep.BLOCKED},
    )
    write_session_state(tool_context.state, rs)
    err = result.get("error") or "Could not produce a valid read-only query."
    return _dump_model(
        AgentToolOutput(
            reply=(
                f"I could not complete that reporting request after {result.get('attempts', 0)} attempt(s). "
                f"{err}"
            ),
            status="error",
            routing_state=rs,
        )
    )


def detect_intent_tool(message: str, tool_context: ToolContext) -> dict[str, Any]:
    """Classify intent and whether the query needs LLM filter analysis."""

    routing_state, detection_source, has_filters, detected_filters = detect_routing_intent(
        message,
        tool_context.state,
    )
    write_session_state(tool_context.state, routing_state)
    write_detect_temp_state(tool_context.state, routing_state, has_search_filters=has_filters)
    tool_context.state[STATE_KEY_HAS_SEARCH_FILTERS] = has_filters

    # Seed SQL snapshot so ADK session.state shows final_query / last_sql even if the
    # model stops before calling search or analyze (overwritten when those tools run).
    if routing_state.current_intent == RoutingIntent.INVESTOR_SEARCH:
        cfg = get_config()
        provisional = SearchPlan(page_limit=cfg.search.default_page_limit)
        publish_final_query_to_session(
            tool_context.state,
            build_final_query(provisional, cfg.search.default_dev_arn, cfg),
        )

    return _dump_model(
        IntentDetectionOutput(
            routing_state=routing_state,
            should_call_tool=routing_state.route,
            has_search_filters=has_filters,
            detected_filters=detected_filters,
            detection_source=detection_source,
        )
    )


def greeting_tool(message: str, tool_context: ToolContext) -> dict[str, Any]:
    """Greet the user and persist Individual-only MVP routing state."""

    routing_state = classify_message(message)
    write_session_state(tool_context.state, routing_state)
    return _dump_model(
        AgentToolOutput(
            reply=HDFC_GREETING_MESSAGE,
            needs_clarification=False,
            status="greeting",
            routing_state=routing_state,
        )
    )


def unsupported_banking_tool(message: str, tool_context: ToolContext) -> dict[str, Any]:
    """Return a scoped unsupported response for out-of-scope requests."""

    routing_state = classify_message(message)
    if routing_state.current_intent != RoutingIntent.UNSUPPORTED_BANKING_REQUEST:
        routing_state = RoutingState(
            current_intent=RoutingIntent.UNSUPPORTED_BANKING_REQUEST,
            route=RoutingRoute.UNSUPPORTED_BANKING_TOOL,
            step=RoutingStep.BLOCKED,
            investor_tab=DEFAULT_INVESTOR_TAB,
            last_user_message=message,
        )
    reply = routing_state.clarification_question or UNSUPPORTED_REPLY
    write_session_state(tool_context.state, routing_state)
    return _dump_model(
        AgentToolOutput(
            reply=reply,
            status="out_of_scope",
            routing_state=routing_state,
        )
    )


def analyze_search_arguments_tool(
    query: str,
    tool_context: ToolContext,
    page_limit: int = 0,
    page_offset: int = 0,
) -> dict[str, Any]:
    """LLM-powered filter extraction: natural language -> strict query_arguments JSON.

    Call only when detect_intent_tool returns has_search_filters=true.

    Args:
        query: Natural-language investor search request.
        page_limit: Optional page size. Use 0 for configured default.
        page_offset: Optional offset. Use 0 for first page.
    """

    config = get_config()
    trusted_arn = config.search.default_dev_arn
    scope_msg = arn_scope_block_reason(
        user_query=query,
        tool_arn_arg=None,
        trusted_arn=trusted_arn,
    )
    if scope_msg:
        empty_plan = SearchPlan()
        blocked_state = RoutingState(
            current_intent=RoutingIntent.INVESTOR_SEARCH,
            route=RoutingRoute.ANALYZE_SEARCH_ARGUMENTS_TOOL,
            step=RoutingStep.BLOCKED,
            investor_tab=empty_plan.investor_tab,
            last_user_message=query,
            needs_clarification=False,
            clarification_question=None,
        )
        write_session_state(tool_context.state, blocked_state)
        qa = plan_to_query_arguments(empty_plan)
        return _dump_model(
            SearchArgumentsAnalysisOutput(
                validation_status="out_of_scope",
                can_execute=False,
                normalized_query=query,
                plan_source="fallback",
                search_plan=empty_plan.model_dump(mode="json"),
                query_arguments=qa,
                filters_applied=[],
                message=scope_msg,
            )
        )

    limit = page_limit or config.search.default_page_limit
    offset = page_offset or 0
    parsed = parse_with_context(
        query=query,
        messages=[],
        page_limit=limit,
        page_offset=offset,
        session_state=tool_context.state,
    )
    plan = parsed["plan"]
    validation = parsed["validation"]
    plan_source = parsed["plan_source"]
    normalized_query = parsed["normalized_query"]
    query_arguments = plan_to_query_arguments(plan)
    filters_applied = list_filters_applied(plan)

    tool_context.state[STATE_KEY_PLAN_QUERY] = query
    tool_context.state[STATE_KEY_LAST_NORMALIZED_QUERY] = normalized_query
    tool_context.state[STATE_KEY_PLAN_SOURCE] = plan_source
    tool_context.state[STATE_KEY_PLAN_VALIDATION_STATUS] = validation.status
    tool_context.state[STATE_KEY_LAST_SEARCH_PLAN] = plan.model_dump(mode="json")
    tool_context.state[STATE_KEY_QUERY_ARGUMENTS] = query_arguments
    publish_final_query_to_session(
        tool_context.state,
        build_final_query(plan, config.search.default_dev_arn, config),
    )

    executing_state = RoutingState(
        current_intent=RoutingIntent.INVESTOR_SEARCH,
        route=RoutingRoute.SEARCH_INVESTORS_TOOL,
        step=RoutingStep.READY_TO_SEARCH,
        investor_tab=plan.investor_tab,
        last_user_message=query,
    )
    write_session_state(tool_context.state, executing_state)

    return _dump_model(
        SearchArgumentsAnalysisOutput(
            validation_status=validation.status,
            can_execute=validation.can_execute,
            normalized_query=normalized_query,
            plan_source=plan_source,
            search_plan=plan.model_dump(mode="json"),
            query_arguments=query_arguments,
            filters_applied=filters_applied,
            message=validation.message,
        )
    )


def parse_with_context(
    query: str,
    messages: list[ChatMessage],
    page_limit: int,
    page_offset: int,
    session_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build SearchPlan via LLM filter extraction with deterministic fallback."""

    plan, plan_source, normalized_query = build_search_plan(
        query=query,
        session_state=session_state,
        messages=messages,
        page_limit=page_limit,
        page_offset=page_offset,
    )
    validation = PlanValidator().validate(plan)
    return {
        "plan": plan,
        "validation": validation,
        "plan_source": plan_source,
        "normalized_query": normalized_query,
    }


def _load_cached_plan(
    query: str,
    session_state: dict[str, Any],
    page_limit: int,
    page_offset: int,
) -> SearchPlan | None:
    if session_state.get(STATE_KEY_PLAN_QUERY) != query:
        return None
    cached = session_state.get(STATE_KEY_LAST_SEARCH_PLAN)
    if not isinstance(cached, dict):
        return None
    plan = SearchPlan.model_validate(cached)
    plan.page_limit = page_limit
    plan.page_offset = page_offset
    return plan


def search_investors_tool(
    query: str,
    tool_context: ToolContext,
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
    trusted_arn = config.search.default_dev_arn
    scope_msg = arn_scope_block_reason(
        user_query=query,
        tool_arn_arg=arn_code.strip() if arn_code and arn_code.strip() else None,
        trusted_arn=trusted_arn,
    )
    if scope_msg:
        return _dump_model(_arn_scope_blocked_agent_output(query, tool_context, scope_msg))

    ensure_investor_schema_for_search_session(tool_context.state, config.database_url_value)

    limit = page_limit or config.search.default_page_limit
    offset = page_offset or 0
    effective_arn = trusted_arn

    cached_plan = _load_cached_plan(query, tool_context.state, limit, offset)
    if cached_plan is not None:
        plan = cached_plan
        validation = PlanValidator().validate(plan)
        plan_source = tool_context.state.get(STATE_KEY_PLAN_SOURCE, "cached")
        normalized_query = tool_context.state.get(STATE_KEY_LAST_NORMALIZED_QUERY, query)
    else:
        parsed = parse_with_context(
            query=query,
            messages=[],
            page_limit=limit,
            page_offset=offset,
            session_state=tool_context.state,
        )
        plan = parsed["plan"]
        validation = parsed["validation"]
        plan_source = parsed["plan_source"]
        normalized_query = parsed["normalized_query"]
        tool_context.state[STATE_KEY_LAST_NORMALIZED_QUERY] = normalized_query
        tool_context.state[STATE_KEY_PLAN_SOURCE] = plan_source
        tool_context.state[STATE_KEY_LAST_SEARCH_PLAN] = plan.model_dump(mode="json")
        tool_context.state[STATE_KEY_QUERY_ARGUMENTS] = plan_to_query_arguments(plan)

    publish_final_query_to_session(
        tool_context.state,
        build_final_query(plan, effective_arn, config),
    )

    executing_state = RoutingState(
        current_intent=RoutingIntent.INVESTOR_SEARCH,
        route=RoutingRoute.SEARCH_INVESTORS_TOOL,
        step=RoutingStep.EXECUTING_SEARCH,
        investor_tab=plan.investor_tab,
        last_user_message=query,
    )
    write_session_state(tool_context.state, executing_state)

    AuditLogger().log_event(
        "search_plan",
        {
            "investor_tab": plan.investor_tab.value,
            "validation_status": validation.status,
            "arn_code": effective_arn,
            "plan_source": plan_source,
            "normalized_query": normalized_query,
            "filter_summary": describe_search_plan(plan),
        },
    )

    if not validation.can_execute:
        return _dump_model(_blocked_search_output(query, plan, validation, tool_context))

    db_config = config.database
    db = PostgresClient(
        config.database_url_value,
        db_config.statement_timeout_ms,
        min_size=db_config.pool_min_size,
        max_size=db_config.pool_max_size,
        connect_timeout_seconds=db_config.connect_timeout_seconds,
        pool_timeout_seconds=db_config.pool_timeout_seconds,
    )
    try:
        db.open()
        rows = _execute_search(db, config, plan, effective_arn)
    except (DatabaseNotConfiguredError, DatabaseUnavailableError) as exc:
        return _dump_model(_database_error_output(query, plan, tool_context, str(exc)))
    finally:
        db.close()

    completed_state = RoutingState(
        current_intent=RoutingIntent.INVESTOR_SEARCH,
        route=RoutingRoute.SEARCH_INVESTORS_TOOL,
        step=RoutingStep.COMPLETED,
        investor_tab=plan.investor_tab,
        last_user_message=query,
    )
    write_session_state(tool_context.state, completed_state)
    tool_context.state[STATE_KEY_LAST_SEARCH_PLAN] = plan.model_dump(mode="json")
    publish_final_query_to_session(
        tool_context.state,
        build_final_query(plan, effective_arn, config),
    )
    return _dump_model(
        AgentToolOutput(
            reply=format_rows_for_chat(rows, plan.page_limit, plan.page_offset),
            rows=_json_safe(rows),
            count=len(rows),
            page=PageMeta(limit=plan.page_limit, offset=plan.page_offset),
            status="ok",
            routing_state=completed_state,
        )
    )


def _arn_scope_blocked_agent_output(
    query: str,
    tool_context: ToolContext,
    message: str,
) -> AgentToolOutput:
    blocked = RoutingState(
        current_intent=RoutingIntent.INVESTOR_SEARCH,
        route=RoutingRoute.SEARCH_INVESTORS_TOOL,
        step=RoutingStep.BLOCKED,
        investor_tab=DEFAULT_INVESTOR_TAB,
        last_user_message=query,
        needs_clarification=False,
        clarification_question=None,
    )
    write_session_state(tool_context.state, blocked)
    return AgentToolOutput(
        reply=message,
        needs_clarification=False,
        status="out_of_scope",
        routing_state=blocked,
    )


def _database_error_output(
    query: str,
    plan: SearchPlan,
    tool_context: ToolContext,
    message: str,
) -> AgentToolOutput:
    error_state = RoutingState(
        current_intent=RoutingIntent.INVESTOR_SEARCH,
        route=RoutingRoute.SEARCH_INVESTORS_TOOL,
        step=RoutingStep.BLOCKED,
        investor_tab=plan.investor_tab,
        last_user_message=query,
    )
    write_session_state(tool_context.state, error_state)
    return AgentToolOutput(
        reply=message,
        status="error",
        routing_state=error_state,
    )


def _blocked_search_output(
    query: str,
    plan: SearchPlan,
    validation,
    tool_context: ToolContext,
) -> AgentToolOutput:
    blocked_state = RoutingState(
        current_intent=RoutingIntent.UNSUPPORTED_BANKING_REQUEST,
        route=RoutingRoute.UNSUPPORTED_BANKING_TOOL,
        step=RoutingStep.BLOCKED,
        investor_tab=DEFAULT_INVESTOR_TAB,
        last_user_message=query,
        needs_clarification=False,
        clarification_question=validation.message,
    )
    write_session_state(tool_context.state, blocked_state)
    reply = validation.message or NON_INDIVIDUAL_NOT_SUPPORTED
    return AgentToolOutput(
        reply=reply,
        needs_clarification=False,
        status=validation.status,
        routing_state=blocked_state,
    )


def _dump_model(model) -> dict[str, Any]:
    return model.model_dump(mode="json")


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
