"""Build debug-friendly final SQL snapshots for ADK session state."""

from __future__ import annotations

from typing import Any, Sequence

from app.models.agent_state import (
    STATE_KEY_FINAL_QUERY,
    STATE_KEY_LAST_SQL,
    STATE_KEY_LAST_SQL_PARAMETERS,
)


def _postgresql_literal(value: Any) -> str:
    """Render one value as a PostgreSQL SQL literal (for display / session state only)."""

    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "ARRAY[" + ", ".join(_postgresql_literal(item) for item in value) + "]"
    text = str(value).replace("'", "''")
    return f"'{text}'"


def bind_postgresql_parameters(sql: str, parameters: Sequence[Any]) -> str:
    """Inline ``%s`` placeholders left-to-right with PostgreSQL literals (``%%`` escaped)."""

    if not parameters:
        return sql
    out: list[str] = []
    idx = 0
    pidx = 0
    n = len(sql)
    while idx < n:
        if idx < n - 1 and sql[idx] == "%" and sql[idx + 1] == "s":
            if pidx >= len(parameters):
                raise ValueError("More %s placeholders than parameters")
            out.append(_postgresql_literal(parameters[pidx]))
            pidx += 1
            idx += 2
            continue
        if idx < n - 1 and sql[idx] == "%" and sql[idx + 1] == "%":
            out.append("%")
            idx += 2
            continue
        out.append(sql[idx])
        idx += 1
    if pidx != len(parameters):
        raise ValueError("Fewer %s placeholders than parameters")
    return "".join(out)


def build_postgresql_executable_sql(sql: str, parameters: Sequence[Any]) -> str:
    """Normalize whitespace and return a single PostgreSQL statement with literals inlined."""

    normalized = _normalize_sql(sql)
    if not parameters:
        return normalized
    try:
        return bind_postgresql_parameters(normalized, parameters)
    except ValueError:
        return normalized


def publish_final_query_to_session(session: dict[str, Any], final_query: dict[str, Any]) -> None:
    """Store final_query plus top-level last_sql / last_sql_parameters for ADK state viewers.

    ``last_sql`` is the full PostgreSQL query with parameter values inlined (not ``%s``).
    ``final_query["sql"]`` keeps the parameterized form; ``sql_postgresql`` is the inlined form.
    """

    session[STATE_KEY_FINAL_QUERY] = final_query
    sql = final_query.get("sql")
    params = final_query.get("parameters")
    if isinstance(sql, str) and sql.strip():
        param_list = list(params) if isinstance(params, list) else []
        if "sql_postgresql" not in final_query:
            final_query["sql_postgresql"] = build_postgresql_executable_sql(sql, param_list)
        session[STATE_KEY_LAST_SQL] = final_query["sql_postgresql"]
        session[STATE_KEY_LAST_SQL_PARAMETERS] = param_list
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


def _normalize_sql(sql: str) -> str:
    return " ".join(sql.split())
