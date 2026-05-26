import json
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

try:
    from google.adk.tools import ToolContext
except ModuleNotFoundError:
    ToolContext = Any

from app.core.config import AppConfig, get_config
from app.models.agent_state import (
    AgentToolOutput,
    GenerateCatalogSqlToolOutput,
    HDFC_GREETING_MESSAGE,
    IntentDetectionOutput,
    NON_INDIVIDUAL_NOT_SUPPORTED,
    RoutingIntent,
    RoutingRoute,
    STATE_KEY_FINAL_QUERY,
    STATE_KEY_LAST_SQL,
    STATE_KEY_LAST_SQL_PARAMETERS,
    STATE_KEY_QUERY_FLOW_TRACE,
    STATE_KEY_QUERY_GENERATOR_LAST,
)
from app.services.arn_scope_guard import arn_scope_block_reason
from app.services.final_query import publish_final_query_to_session
from app.services.catalog_sql_executor import CatalogSqlExecuteError, is_execute_timeout_error
from app.services.dp_investor_menu import (
    build_filter_dp_investor_menu_sql,
    execute_filter_dp_investor_menu,
    validate_filter_dp_investor_menu_sql,
)
from app.services.dp_investor_menu_llm import run_dp_investor_menu_param_llm
from app.services.investor_capability import (
    build_unsupported_capability_reply,
    detect_unsupported_question,
)
from app.services.sql_guard import SqlGuardError
from app.services.filter_detection import message_has_search_filters
from app.services.routing import (
    classify_message,
    is_greeting,
    is_unsupported_banking_request,
    normalize_message,
    read_prior_step,
    requests_non_individual_scope,
    write_detect_temp_state,
    write_session_state,
)


def _append_query_flow_trace(session_state: dict[str, Any], entry: dict[str, Any]) -> None:
    from datetime import datetime, timezone

    trace = session_state.get(STATE_KEY_QUERY_FLOW_TRACE)
    if not isinstance(trace, list):
        trace = []
        session_state[STATE_KEY_QUERY_FLOW_TRACE] = trace
    row = {"ts": datetime.now(timezone.utc).isoformat(), **entry}
    trace.append(row)


def _format_sql_tool_reply(
    sql: str,
    parameters: list[Any],
    thought: str | None,
    *,
    sql_postgresql: str | None = None,
    rows: list[dict[str, Any]] | None = None,
    executed: bool = False,
    execute_error: str | None = None,
    sql_retry_used: bool = False,
    max_display_rows: int = 50,
) -> str:
    """User-facing chat text. On success, rows render in the UI table; SQL stays in session state."""

    from app.services.final_query import build_postgresql_executable_sql

    if executed and rows is not None:
        n = len(rows)
        parts = [f"Found {n} investor record(s). See the results table below."]
        if n > max_display_rows:
            parts.append(f"(Table shows the first {max_display_rows} rows.)")
        parts.append("Generated SQL is saved in session state (last_sql).")
        return "\n".join(parts)

    resolved = sql_postgresql or build_postgresql_executable_sql(sql, parameters)
    parts = [
        "Generated read-only PostgreSQL SQL (saved to session state).",
        "",
        "PostgreSQL (parameters inlined):",
        resolved.strip(),
    ]
    if execute_error:
        parts.extend(["", f"Execution failed: {execute_error}"])
        if sql_retry_used:
            parts.append("(One automatic SQL repair was attempted.)")
    else:
        parts.append("")
        parts.append("(SQL was not executed — database not configured or execution disabled.)")

    if thought:
        parts.extend(["", "Model reasoning (thought):", thought.strip()])
    return "\n".join(parts)


def _unsupported_capability_output(
    *,
    question: str,
    detail: str | None,
    gen_model: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """No SQL, no session query — capability boundary only."""

    reply = build_unsupported_capability_reply(detail)
    log = {
        "phase": "filter_dp_investor_menu_unsupported",
        "question": question,
        "unsupported_reason": detail,
    }
    tool_context.state[STATE_KEY_QUERY_GENERATOR_LAST] = log
    _append_query_flow_trace(tool_context.state, dict(log))
    tool_context.state.pop(STATE_KEY_FINAL_QUERY, None)
    tool_context.state.pop(STATE_KEY_LAST_SQL, None)
    tool_context.state.pop(STATE_KEY_LAST_SQL_PARAMETERS, None)
    return _dump_model(
        GenerateCatalogSqlToolOutput(
            status="out_of_scope",
            reply=reply,
            generator_model=gen_model,
        )
    )


def _publish_sql_to_session(
    session_state: dict[str, Any],
    *,
    question: str,
    sql: str,
    parameters: list[Any],
    rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    from app.services.final_query import build_postgresql_executable_sql

    safe_params = _json_safe(list(parameters))
    payload = {
        "engine": "filter_dp_investor_menu",
        "sql": sql.strip(),
        "sql_postgresql": build_postgresql_executable_sql(sql, safe_params),
        "parameters": safe_params,
        "normalized_summary": (question or "")[:2000],
        "executed": bool(rows is not None),
        "row_count": len(rows) if rows is not None else 0,
    }
    if rows is not None:
        payload["rows"] = _json_safe(rows)
    publish_final_query_to_session(session_state, payload)
    return payload


def generate_catalog_sql_query_tool(question: str, tool_context: ToolContext) -> dict[str, Any]:
    """Map NL to ``public.filter_dp_investor_menu`` only; never query base tables directly."""

    config = get_config()
    trusted_arn = config.search.default_dev_arn
    gen_model = config.query_generator_llm_model_resolved

    scope_msg = arn_scope_block_reason(
        user_query=question,
        tool_arn_arg=None,
        trusted_arn=trusted_arn,
    )
    if scope_msg:
        return _dump_model(
            GenerateCatalogSqlToolOutput(
                status="blocked",
                reply=scope_msg,
                generator_model=gen_model,
            )
        )

    heuristic_reason = detect_unsupported_question(question)
    if heuristic_reason:
        return _unsupported_capability_output(
            question=question,
            detail=heuristic_reason,
            gen_model=gen_model,
            tool_context=tool_context,
        )

    timing_ms: dict[str, int] = {}
    validation_error: str | None = None
    execute_error: str | None = None
    rows: list[dict[str, Any]] | None = None
    executed = False
    thought = ""

    t0 = time.perf_counter()
    try:
        menu_params, gen_log = run_dp_investor_menu_param_llm(
            question=question,
            trusted_arn=trusted_arn,
        )
    except Exception as exc:
        timing_ms["generate"] = int((time.perf_counter() - t0) * 1000)
        gen_log = {
            "phase": "filter_dp_investor_menu_params",
            "error": str(exc),
            "question": question,
            "timing_ms": timing_ms,
        }
        tool_context.state[STATE_KEY_QUERY_GENERATOR_LAST] = gen_log
        _append_query_flow_trace(tool_context.state, dict(gen_log))
        return _unsupported_capability_output(
            question=question,
            detail=str(exc),
            gen_model=gen_model,
            tool_context=tool_context,
        )

    timing_ms["generate"] = int((time.perf_counter() - t0) * 1000)
    gen_log["timing_ms"] = dict(timing_ms)
    tool_context.state[STATE_KEY_QUERY_GENERATOR_LAST] = gen_log
    _append_query_flow_trace(tool_context.state, dict(gen_log))
    gen_model = str(gen_log.get("model") or gen_model)

    if menu_params.unsupported_reason:
        return _unsupported_capability_output(
            question=question,
            detail=menu_params.unsupported_reason,
            gen_model=gen_model,
            tool_context=tool_context,
        )

    thought = menu_params.thought

    try:
        sql, params = build_filter_dp_investor_menu_sql(menu_params, trusted_arn=trusted_arn)
        validate_filter_dp_investor_menu_sql(sql, params, trusted_arn)
    except (SqlGuardError, ValueError) as exc:
        validation_error = str(exc)
        return _unsupported_capability_output(
            question=question,
            detail=validation_error,
            gen_model=gen_model,
            tool_context=tool_context,
        )

    if config.catalog_sql_execute_enabled and config.database_url_value:
        t_exec = time.perf_counter()
        try:
            rows = execute_filter_dp_investor_menu(
                sql, params, trusted_arn=trusted_arn, config=config
            )
            timing_ms["execute"] = int((time.perf_counter() - t_exec) * 1000)
            executed = True
        except CatalogSqlExecuteError as exc:
            timing_ms["execute"] = int((time.perf_counter() - t_exec) * 1000)
            execute_error = str(exc)
            gen_log["execute_error"] = execute_error
            tool_context.state[STATE_KEY_QUERY_GENERATOR_LAST] = gen_log

    fq = _publish_sql_to_session(
        tool_context.state,
        question=question,
        sql=sql,
        parameters=params,
        rows=rows,
    )
    display_rows = (rows or [])[: config.catalog_sql_max_display_rows]
    row_count = len(rows) if rows else 0
    reply = _format_sql_tool_reply(
        sql,
        params,
        thought,
        sql_postgresql=fq.get("sql_postgresql"),
        rows=rows,
        executed=executed,
        execute_error=execute_error if not executed else None,
        sql_retry_used=False,
        max_display_rows=config.catalog_sql_max_display_rows,
    )

    status = "ok" if executed or not config.catalog_sql_execute_enabled else "error"
    if execute_error and not executed:
        status = "error"
        reply = (
            "I used only the approved ``filter_dp_investor_menu`` function, but execution failed.\n\n"
            f"Details: {execute_error}\n\n"
            "Please verify database connectivity and try again."
        )

    return _dump_model(
        GenerateCatalogSqlToolOutput(
            status=status,
            reply=reply,
            thought=thought,
            sql=sql,
            parameters=params,
            row_count=row_count,
            count=row_count,
            rows=display_rows,
            executed=executed,
            sql_retry_used=False,
            generator_model=gen_model,
            validation_error=validation_error,
            execute_error=execute_error if not executed else None,
        )
    )


def detect_intent_tool(message: str, tool_context: ToolContext) -> dict[str, Any]:
    """Classify the user message and run the right path (compat for models that call this first).

    Pure greetings → ``greeting_tool``. Banking / non-individual scope → out-of-scope reply.
    All other messages → ``generate_catalog_sql_query_tool`` (investor SQL pipeline).
    """

    prior_step = read_prior_step(tool_context.state)
    routing_state = classify_message(message, prior_step)
    has_filters = message_has_search_filters(message, prior_step)
    write_session_state(tool_context.state, routing_state)
    write_detect_temp_state(tool_context.state, routing_state, has_filters)

    normalized = normalize_message(message)
    if is_greeting(normalized):
        return greeting_tool(message, tool_context)
    if is_unsupported_banking_request(normalized):
        return _dump_model(
            AgentToolOutput(
                reply=(
                    "I can only help with distributor Individual investor search "
                    "(lists, filters, counts). I cannot help with banking balances, transfers, or loans."
                ),
                status="out_of_scope",
                routing_state=routing_state,
            )
        )
    if requests_non_individual_scope(normalized):
        return _dump_model(
            AgentToolOutput(
                reply=NON_INDIVIDUAL_NOT_SUPPORTED,
                status="out_of_scope",
                routing_state=routing_state,
            )
        )

    sql_result = generate_catalog_sql_query_tool(message, tool_context)
    if routing_state.current_intent == RoutingIntent.INVESTOR_SEARCH:
        return sql_result

    intent_meta = _dump_model(
        IntentDetectionOutput(
            routing_state=routing_state,
            should_call_tool=RoutingRoute.SEARCH_INVESTORS_TOOL,
            has_search_filters=has_filters,
            detection_source="individual_only",
        )
    )
    if isinstance(sql_result, dict):
        sql_result["intent_detection"] = intent_meta
    return sql_result


def greeting_tool(message: str, tool_context: ToolContext) -> dict[str, Any]:
    """Greet the user and persist routing state for the Individual MVP."""

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


def _dump_model(model: Any) -> dict[str, Any]:
    return model.model_dump(mode="json")


def _json_safe(value: Any) -> Any:
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
