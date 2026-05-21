import json
from typing import Any

try:
    from google.adk.tools import ToolContext
except ModuleNotFoundError:
    ToolContext = Any

from app.core.config import get_config
from app.models.agent_state import (
    AgentToolOutput,
    GenerateCatalogSqlToolOutput,
    HDFC_GREETING_MESSAGE,
    STATE_KEY_FINAL_QUERY,
    STATE_KEY_QUERY_FLOW_TRACE,
    STATE_KEY_QUERY_GENERATOR_LAST,
)
from app.services.arn_scope_guard import arn_scope_block_reason
from app.services.final_query import publish_final_query_to_session
from app.services.schema_contract_guide import load_schema_guide
from app.services.query_flow_router import run_catalog_sql_generator_llm
from app.services.sql_guard import SqlGuardError, validate_arn_first_parameter, validate_dynamic_sql
from app.services.routing import classify_message, write_session_state


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
) -> str:
    """User-facing text: generated query only (no execution)."""

    from app.services.final_query import build_postgresql_executable_sql

    resolved = sql_postgresql or build_postgresql_executable_sql(sql, parameters)
    parts = [
        "Generated read-only PostgreSQL SQL (not executed against the database).",
        "",
        "PostgreSQL (parameters inlined):",
        resolved.strip(),
        "",
        "Parameterized form (for execution):",
        sql.strip(),
        "",
        f"Parameters ({len(parameters)}):",
        json.dumps(parameters, ensure_ascii=True, default=str),
    ]
    if thought:
        parts.extend(["", "Model reasoning (thought):", thought.strip()])
    return "\n".join(parts)


def generate_catalog_sql_query_tool(
    question: str,
    tool_context: ToolContext,
    arn_code: str = "",
) -> dict[str, Any]:
    """LLM SQL generation from investor_db_schema_guide.json + user question (not executed)."""

    config = get_config()
    trusted_arn = config.search.default_dev_arn
    scope_msg = arn_scope_block_reason(
        user_query=question,
        tool_arn_arg=arn_code.strip() if arn_code and arn_code.strip() else None,
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

    try:
        turn, gen_log = run_catalog_sql_generator_llm(
            question=question,
            trusted_arn=trusted_arn,
            schema_contract=schema_contract,
            schema_contract_max_chars=config.query_generator_schema_contract_max_chars,
            guide_only=True,
        )
    except Exception as exc:
        gen_log = {"phase": "catalog_sql_generator", "error": str(exc), "question": question}
        tool_context.state[STATE_KEY_QUERY_GENERATOR_LAST] = gen_log
        _append_query_flow_trace(tool_context.state, dict(gen_log))
        return _dump_model(
            GenerateCatalogSqlToolOutput(
                status="error",
                reply=f"Catalog SQL generator failed: {exc}",
                generator_model=config.query_generator_llm_model_resolved,
            )
        )

    tool_context.state[STATE_KEY_QUERY_GENERATOR_LAST] = gen_log
    _append_query_flow_trace(tool_context.state, dict(gen_log))

    gen_model = str(gen_log.get("model") or config.query_generator_llm_model_resolved)
    params = list(turn.parameters)

    def _publish_sql(sql: str, parameters: list[Any]) -> None:
        from app.services.final_query import build_postgresql_executable_sql

        safe_params = _json_safe(list(parameters))
        publish_final_query_to_session(
            tool_context.state,
            {
                "engine": "catalog_sql_generator",
                "sql": sql.strip(),
                "sql_postgresql": build_postgresql_executable_sql(sql, safe_params),
                "parameters": safe_params,
                "normalized_summary": (question or "")[:2000],
            },
        )

    try:
        validate_dynamic_sql(turn.sql)
        validate_arn_first_parameter(turn.sql, params, trusted_arn)
    except SqlGuardError as exc:
        _publish_sql(turn.sql, params)
        return _dump_model(
            GenerateCatalogSqlToolOutput(
                status="error",
                reply=f"Generated SQL failed validation: {exc}\n\nSQL:\n{turn.sql.strip()}",
                thought=turn.thought,
                sql=turn.sql,
                parameters=params,
                row_count=0,
                generator_model=gen_model,
                validation_error=str(exc),
            )
        )

    _publish_sql(turn.sql, params)
    fq = tool_context.state.get(STATE_KEY_FINAL_QUERY) or {}
    reply = _format_sql_tool_reply(
        turn.sql,
        params,
        turn.thought,
        sql_postgresql=fq.get("sql_postgresql"),
    )
    return _dump_model(
        GenerateCatalogSqlToolOutput(
            status="ok",
            reply=reply,
            thought=turn.thought,
            sql=turn.sql,
            parameters=params,
            row_count=0,
            generator_model=gen_model,
        )
    )


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
