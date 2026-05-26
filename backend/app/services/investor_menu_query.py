"""Decoupled Individual investor search via ``public.filter_dp_investor_menu`` only.

This module is the stable, requirement-based query path (portal filters → function RPC).
It does not depend on ADK ``ToolContext``; agents and scripts call it with a plain session dict.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.core.config import AppConfig, get_config
from app.models.agent_state import (
    FilterDpInvestorMenuToolOutput,
    STATE_KEY_FINAL_QUERY,
    STATE_KEY_LAST_SQL,
    STATE_KEY_LAST_SQL_PARAMETERS,
    STATE_KEY_QUERY_FLOW_TRACE,
    STATE_KEY_QUERY_GENERATOR_LAST,
)
from app.services.arn_scope_guard import arn_scope_block_reason
from app.services.catalog_sql_executor import CatalogSqlExecuteError
from app.services.dp_investor_menu import (
    FilterDpInvestorMenuLlmTurn,
    execute_filter_dp_investor_menu,
    validate_filter_dp_investor_menu_sql,
)
from app.services.dp_investor_menu_llm import run_dp_investor_menu_param_llm
from app.services.final_query import build_postgresql_executable_sql, publish_final_query_to_session
from app.services.investor_capability import (
    build_query_generation_failed_reply,
    build_unsupported_capability_reply,
)
from app.services.sql_guard import SqlGuardError

logger = logging.getLogger(__name__)

_MAX_QUERY_ATTEMPTS = 2


@dataclass
class _PreparedMenuQuery:
    llm_turn: FilterDpInvestorMenuLlmTurn
    sql: str
    params: list[Any]
    gen_logs: list[dict[str, Any]]
    sql_retry_used: bool
    rows: list[dict[str, Any]] | None = None
    executed: bool = False


def append_query_flow_trace(session_state: dict[str, Any], entry: dict[str, Any]) -> None:
    trace = session_state.get(STATE_KEY_QUERY_FLOW_TRACE)
    if not isinstance(trace, list):
        trace = []
        session_state[STATE_KEY_QUERY_FLOW_TRACE] = trace
    trace.append({"ts": datetime.now(timezone.utc).isoformat(), **entry})


def run_filter_dp_investor_menu_query(
    question: str,
    session_state: dict[str, Any],
    *,
    config: AppConfig | None = None,
) -> FilterDpInvestorMenuToolOutput:
    """Contract + question → Sonnet; one repair on failure; standard message if still failing."""

    config = config or get_config()
    trusted_arn = config.search.default_dev_arn
    gen_model = config.query_generator_llm_model_resolved

    scope_msg = arn_scope_block_reason(
        user_query=question,
        tool_arn_arg=None,
        trusted_arn=trusted_arn,
    )
    if scope_msg:
        return FilterDpInvestorMenuToolOutput(
            status="blocked",
            reply=scope_msg,
            generator_model=gen_model,
        )

    try:
        prepared = _generate_and_execute_menu_query(
            question=question,
            trusted_arn=trusted_arn,
            config=config,
        )
    except _MenuQueryGenerationFailed as exc:
        for log in exc.gen_logs:
            append_query_flow_trace(session_state, dict(log))
        session_state[STATE_KEY_QUERY_GENERATOR_LAST] = exc.gen_logs[-1] if exc.gen_logs else {}
        return _query_generation_failed_output(
            gen_model=str(exc.gen_logs[-1].get("model") if exc.gen_logs else gen_model),
            session_state=session_state,
            sql_retry_used=exc.sql_retry_used,
        )

    for log in prepared.gen_logs:
        append_query_flow_trace(session_state, dict(log))
    session_state[STATE_KEY_QUERY_GENERATOR_LAST] = prepared.gen_logs[-1]
    gen_model = str(prepared.gen_logs[-1].get("model") or gen_model)

    if prepared.llm_turn.unsupported_reason:
        return _unsupported_output(
            question=question,
            detail=prepared.llm_turn.unsupported_reason,
            gen_model=gen_model,
            session_state=session_state,
        )

    sql = prepared.sql
    params = prepared.params
    thought = prepared.llm_turn.thought
    rows = prepared.rows
    executed = prepared.executed

    fq = _publish_sql_to_session(
        session_state,
        question=question,
        sql=sql,
        parameters=params,
        rows=rows,
    )
    display_rows = (rows or [])[: config.catalog_sql_max_display_rows]
    row_count = len(rows) if rows else 0
    reply = _format_reply(
        sql,
        params,
        thought,
        sql_postgresql=fq.get("sql_postgresql"),
        rows=rows,
        executed=executed,
        execute_error=None,
        max_display_rows=config.catalog_sql_max_display_rows,
    )

    status: str = "ok" if executed or not config.catalog_sql_execute_enabled else "error"

    return FilterDpInvestorMenuToolOutput(
        status=status,  # type: ignore[arg-type]
        reply=reply,
        thought=thought,
        sql=sql,
        parameters=params,
        row_count=row_count,
        count=row_count,
        rows=display_rows,
        executed=executed,
        sql_retry_used=prepared.sql_retry_used,
        generator_model=gen_model,
    )


class _MenuQueryGenerationFailed(Exception):
    def __init__(self, *, gen_logs: list[dict[str, Any]], sql_retry_used: bool) -> None:
        self.gen_logs = gen_logs
        self.sql_retry_used = sql_retry_used


def _generate_and_execute_menu_query(
    *,
    question: str,
    trusted_arn: str,
    config: AppConfig,
) -> _PreparedMenuQuery:
    """Up to two Sonnet calls; second sends ``repair_context`` after generate/validate/execute failure."""

    gen_logs: list[dict[str, Any]] = []
    repair_context: dict[str, Any] | None = None
    sql_retry_used = False
    run_execute = bool(config.catalog_sql_execute_enabled and config.database_url_value)

    for attempt in range(_MAX_QUERY_ATTEMPTS):
        t0 = time.perf_counter()
        try:
            llm_turn, gen_log = run_dp_investor_menu_param_llm(
                question=question,
                trusted_arn=trusted_arn,
                repair_context=repair_context,
            )
        except Exception as exc:
            gen_log = {
                "phase": "filter_dp_investor_menu_query_repair"
                if repair_context
                else "filter_dp_investor_menu_query",
                "error": str(exc),
                "question": question,
                "attempt": attempt + 1,
            }
            gen_log["timing_ms"] = {"generate": int((time.perf_counter() - t0) * 1000)}
            gen_logs.append(gen_log)
            if attempt + 1 >= _MAX_QUERY_ATTEMPTS:
                raise _MenuQueryGenerationFailed(
                    gen_logs=gen_logs, sql_retry_used=sql_retry_used
                ) from exc
            repair_context = _repair_from_error(str(exc))
            sql_retry_used = True
            continue

        gen_log["timing_ms"] = {
            **dict(gen_log.get("timing_ms") or {}),
            "generate": int((time.perf_counter() - t0) * 1000),
        }
        gen_log["attempt"] = attempt + 1
        gen_logs.append(gen_log)

        if llm_turn.unsupported_reason:
            return _PreparedMenuQuery(
                llm_turn=llm_turn,
                sql="",
                params=[],
                gen_logs=gen_logs,
                sql_retry_used=sql_retry_used,
            )

        try:
            if not llm_turn.sql:
                raise SqlGuardError("Menu query LLM did not return sql")
            sql = llm_turn.sql.strip()
            params = list(llm_turn.parameters)
            validate_filter_dp_investor_menu_sql(sql, params, trusted_arn)

            rows: list[dict[str, Any]] | None = None
            executed = False
            if run_execute:
                t_exec = time.perf_counter()
                try:
                    rows = execute_filter_dp_investor_menu(
                        sql, params, trusted_arn=trusted_arn, config=config
                    )
                    gen_log["timing_ms"] = {
                        **dict(gen_log.get("timing_ms") or {}),
                        "execute": int((time.perf_counter() - t_exec) * 1000),
                    }
                    executed = True
                except CatalogSqlExecuteError as exc:
                    gen_log["timing_ms"] = {
                        **dict(gen_log.get("timing_ms") or {}),
                        "execute": int((time.perf_counter() - t_exec) * 1000),
                    }
                    gen_log["execute_error"] = str(exc)
                    raise

            return _PreparedMenuQuery(
                llm_turn=llm_turn,
                sql=sql,
                params=params,
                gen_logs=gen_logs,
                sql_retry_used=sql_retry_used,
                rows=rows,
                executed=executed,
            )
        except (SqlGuardError, ValueError, CatalogSqlExecuteError) as exc:
            if attempt + 1 >= _MAX_QUERY_ATTEMPTS:
                raise _MenuQueryGenerationFailed(
                    gen_logs=gen_logs, sql_retry_used=sql_retry_used
                ) from exc
            repair_context = {
                "error": str(exc),
                "failed_sql": llm_turn.sql,
                "failed_parameters": list(llm_turn.parameters),
            }
            if isinstance(exc, CatalogSqlExecuteError):
                repair_context["database_error"] = str(exc)
            sql_retry_used = True

    raise _MenuQueryGenerationFailed(gen_logs=gen_logs, sql_retry_used=sql_retry_used)


def _repair_from_error(message: str) -> dict[str, Any]:
    return {
        "error": message,
        "failed_sql": None,
        "failed_parameters": [],
    }


def _unsupported_output(
    *,
    question: str,
    detail: str | None,
    gen_model: str,
    session_state: dict[str, Any],
) -> FilterDpInvestorMenuToolOutput:
    reply = build_unsupported_capability_reply(detail)
    log = {
        "phase": "filter_dp_investor_menu_unsupported",
        "question": question,
        "unsupported_reason": detail,
    }
    session_state[STATE_KEY_QUERY_GENERATOR_LAST] = log
    append_query_flow_trace(session_state, dict(log))
    session_state.pop(STATE_KEY_FINAL_QUERY, None)
    session_state.pop(STATE_KEY_LAST_SQL, None)
    session_state.pop(STATE_KEY_LAST_SQL_PARAMETERS, None)
    return FilterDpInvestorMenuToolOutput(
        status="out_of_scope",
        reply=reply,
        generator_model=gen_model,
    )


def _query_generation_failed_output(
    *,
    gen_model: str,
    session_state: dict[str, Any],
    sql_retry_used: bool,
) -> FilterDpInvestorMenuToolOutput:
    session_state.pop(STATE_KEY_FINAL_QUERY, None)
    session_state.pop(STATE_KEY_LAST_SQL, None)
    session_state.pop(STATE_KEY_LAST_SQL_PARAMETERS, None)
    return FilterDpInvestorMenuToolOutput(
        status="error",
        reply=build_query_generation_failed_reply(),
        generator_model=gen_model,
        sql_retry_used=sql_retry_used,
    )


def _publish_sql_to_session(
    session_state: dict[str, Any],
    *,
    question: str,
    sql: str,
    parameters: list[Any],
    rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
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


def _format_reply(
    sql: str,
    parameters: list[Any],
    thought: str | None,
    *,
    sql_postgresql: str | None = None,
    rows: list[dict[str, Any]] | None = None,
    executed: bool = False,
    execute_error: str | None = None,
    max_display_rows: int = 50,
) -> str:
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
    else:
        parts.append("")
        parts.append("(SQL was not executed — database not configured or execution disabled.)")

    if thought:
        parts.extend(["", "Model reasoning (thought):", thought.strip()])
    return "\n".join(parts)


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
