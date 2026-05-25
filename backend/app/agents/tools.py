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
    STATE_KEY_QUERY_FLOW_TRACE,
    STATE_KEY_QUERY_GENERATOR_LAST,
)
from app.services.arn_scope_guard import arn_scope_block_reason
from app.services.catalog_sql_executor import (
    CatalogSqlExecuteError,
    dedupe_investor_result_rows,
    execute_catalog_sql_readonly,
    is_execute_timeout_error,
)
from app.services.final_query import publish_final_query_to_session
from app.services.schema_contract_guide import load_schema_guide
from app.services.catalog_sql_validation_repair import run_catalog_sql_validation_repair_llm
from app.services.query_flow_router import CatalogSqlGeneratorTurn, run_catalog_sql_generator_llm
from app.services.sql_guard import (
    SqlGuardError,
    normalize_catalog_sql_parameters,
    sanitize_catalog_sql,
    validate_arn_first_parameter,
    validate_dynamic_sql,
)
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
        "engine": "catalog_sql_generator",
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


def _generate_sql_turn(
    *,
    question: str,
    trusted_arn: str,
    schema_contract: dict[str, Any],
    config: AppConfig,
    repair_context: dict[str, Any] | None,
) -> tuple[CatalogSqlGeneratorTurn, dict[str, Any]]:
    return run_catalog_sql_generator_llm(
        question=question,
        trusted_arn=trusted_arn,
        schema_contract=schema_contract,
        schema_contract_max_chars=config.query_generator_schema_contract_max_chars,
        guide_only=True,
        repair_context=repair_context,
    )


def _validate_turn(sql: str, params: list[Any], trusted_arn: str) -> str | None:
    try:
        validate_dynamic_sql(sql)
        validate_arn_first_parameter(sql, params, trusted_arn)
        return None
    except SqlGuardError as exc:
        return str(exc)


def _hygiene_catalog_sql_turn(
    turn: CatalogSqlGeneratorTurn, trusted_arn: str
) -> CatalogSqlGeneratorTurn:
    sql = sanitize_catalog_sql(turn.sql)
    return turn.model_copy(
        update={
            "sql": sql,
            "parameters": normalize_catalog_sql_parameters(
                sql, list(turn.parameters), trusted_arn
            ),
        }
    )


def _try_validation_repair_turn(
    *,
    turn: CatalogSqlGeneratorTurn,
    question: str,
    trusted_arn: str,
    validation_error: str,
    config: AppConfig,
    tool_context: ToolContext,
    timing_ms: dict[str, int],
) -> tuple[CatalogSqlGeneratorTurn, str | None, bool]:
    """Run small LLM repair when static validation fails; return (turn, error, repair_used)."""

    if not config.catalog_sql_validation_repair_enabled:
        return turn, validation_error, False

    try:
        t0 = time.perf_counter()
        repaired, repair_log = run_catalog_sql_validation_repair_llm(
            question=question,
            trusted_arn=trusted_arn,
            failed_sql=turn.sql,
            failed_parameters=_json_safe(list(turn.parameters)),
            validation_error=validation_error,
        )
        timing_ms["validation_repair"] = int((time.perf_counter() - t0) * 1000)
        repair_log["timing_ms"] = dict(timing_ms)
        tool_context.state[STATE_KEY_QUERY_GENERATOR_LAST] = repair_log
        _append_query_flow_trace(tool_context.state, dict(repair_log))
        repaired = _hygiene_catalog_sql_turn(repaired, trusted_arn)
        err = _validate_turn(repaired.sql, list(repaired.parameters), trusted_arn)
        return repaired, err, True
    except Exception as exc:
        logger.warning("catalog SQL validation repair failed: %s", exc)
        return turn, validation_error, True


def generate_catalog_sql_query_tool(question: str, tool_context: ToolContext) -> dict[str, Any]:
    """Generate PostgreSQL from schema guide, execute once, retry LLM once on execution failure."""

    config = get_config()
    trusted_arn = config.search.default_dev_arn
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
                generator_model=config.query_generator_llm_model_resolved,
            )
        )

    schema_contract = load_schema_guide()
    if not schema_contract:
        return _dump_model(
            GenerateCatalogSqlToolOutput(
                status="error",
                reply=(
                    "Investor schema contract is not available. "
                    "Ensure backend/app/data/investor_db_schema_guide.json exists "
                    "(run: python app/data/build_investor_schema_guide.py)."
                ),
                generator_model=config.query_generator_llm_model_resolved,
            )
        )

    gen_model = config.query_generator_llm_model_resolved
    sql_retry_used = False
    execute_error: str | None = None
    rows: list[dict[str, Any]] | None = None
    executed = False
    timing_ms: dict[str, int] = {}

    t0 = time.perf_counter()
    try:
        turn, gen_log = _generate_sql_turn(
            question=question,
            trusted_arn=trusted_arn,
            schema_contract=schema_contract,
            config=config,
            repair_context=None,
        )
    except Exception as exc:
        timing_ms["generate"] = int((time.perf_counter() - t0) * 1000)
        gen_log = {
            "phase": "catalog_sql_generator",
            "error": str(exc),
            "question": question,
            "timing_ms": timing_ms,
        }
        tool_context.state[STATE_KEY_QUERY_GENERATOR_LAST] = gen_log
        _append_query_flow_trace(tool_context.state, dict(gen_log))
        return _dump_model(
            GenerateCatalogSqlToolOutput(
                status="error",
                reply=f"Catalog SQL generator failed: {exc}",
                generator_model=gen_model,
            )
        )

    timing_ms["generate"] = int((time.perf_counter() - t0) * 1000)
    gen_log["timing_ms"] = dict(timing_ms)
    tool_context.state[STATE_KEY_QUERY_GENERATOR_LAST] = gen_log
    _append_query_flow_trace(tool_context.state, dict(gen_log))
    gen_model = str(gen_log.get("model") or gen_model)

    turn = _hygiene_catalog_sql_turn(turn, trusted_arn)
    params = list(turn.parameters)
    validation_error = _validate_turn(turn.sql, params, trusted_arn)
    validation_repair_used = False
    if validation_error:
        turn, validation_error, validation_repair_used = _try_validation_repair_turn(
            turn=turn,
            question=question,
            trusted_arn=trusted_arn,
            validation_error=validation_error,
            config=config,
            tool_context=tool_context,
            timing_ms=timing_ms,
        )
        params = list(turn.parameters)
    if validation_error:
        _publish_sql_to_session(tool_context.state, question=question, sql=turn.sql, parameters=params)
        repair_note = (
            " (A small validation-repair model was tried but could not fix the SQL.)"
            if validation_repair_used
            else ""
        )
        return _dump_model(
            GenerateCatalogSqlToolOutput(
                status="error",
                reply=(
                    f"Generated SQL failed validation: {validation_error}{repair_note}\n\n"
                    f"SQL:\n{turn.sql.strip()}"
                ),
                thought=turn.thought,
                sql=turn.sql,
                parameters=params,
                generator_model=gen_model,
                validation_error=validation_error,
            )
        )

    max_retries = max(0, int(config.catalog_sql_max_retries_on_execute_error))
    attempt = 0
    while True:
        if config.catalog_sql_execute_enabled and config.database_url_value:
            t_exec = time.perf_counter()
            try:
                rows = dedupe_investor_result_rows(
                    execute_catalog_sql_readonly(
                        turn.sql, params, trusted_arn=trusted_arn, config=config
                    )
                )
                timing_ms["execute"] = int((time.perf_counter() - t_exec) * 1000)
                executed = True
                execute_error = None
                break
            except CatalogSqlExecuteError as exc:
                timing_ms["execute"] = int((time.perf_counter() - t_exec) * 1000)
                execute_error = str(exc)
                skip_repair = config.catalog_sql_skip_repair_on_timeout and is_execute_timeout_error(
                    execute_error
                )
                if attempt >= max_retries or skip_repair:
                    break
                sql_retry_used = True
                failed_sql = turn.sql.strip()
                if len(failed_sql) > 8000:
                    failed_sql = failed_sql[:8000] + "\n-- …(truncated for repair prompt)\n"
                repair = {
                    "failed_sql": failed_sql,
                    "failed_parameters": _json_safe(params),
                    "database_error": execute_error,
                    "attempt": attempt + 1,
                }
                try:
                    t_repair = time.perf_counter()
                    turn, repair_log = _generate_sql_turn(
                        question=question,
                        trusted_arn=trusted_arn,
                        schema_contract=schema_contract,
                        config=config,
                        repair_context=repair,
                    )
                    timing_ms["repair_generate"] = int((time.perf_counter() - t_repair) * 1000)
                    repair_log["timing_ms"] = dict(timing_ms)
                    tool_context.state[STATE_KEY_QUERY_GENERATOR_LAST] = repair_log
                    _append_query_flow_trace(tool_context.state, dict(repair_log))
                    params = list(turn.parameters)
                    validation_error = _validate_turn(turn.sql, params, trusted_arn)
                    if validation_error:
                        execute_error = f"Repair SQL failed validation: {validation_error}"
                        break
                except Exception as exc:
                    execute_error = f"SQL repair LLM failed: {exc}"
                    break
                attempt += 1
        else:
            break

    fq = _publish_sql_to_session(
        tool_context.state,
        question=question,
        sql=turn.sql,
        parameters=params,
        rows=rows,
    )
    display_rows = (rows or [])[: config.catalog_sql_max_display_rows]
    row_count = len(rows) if rows else 0
    reply = _format_sql_tool_reply(
        turn.sql,
        params,
        turn.thought,
        sql_postgresql=fq.get("sql_postgresql"),
        rows=rows,
        executed=executed,
        execute_error=execute_error if not executed else None,
        sql_retry_used=sql_retry_used,
        max_display_rows=config.catalog_sql_max_display_rows,
    )

    status = "ok" if executed or not config.catalog_sql_execute_enabled else "error"
    if validation_error:
        status = "error"
    elif execute_error and not executed:
        status = "error"

    return _dump_model(
        GenerateCatalogSqlToolOutput(
            status=status,
            reply=reply,
            thought=turn.thought,
            sql=turn.sql,
            parameters=params,
            row_count=row_count,
            count=row_count,
            rows=display_rows,
            executed=executed,
            sql_retry_used=sql_retry_used,
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
