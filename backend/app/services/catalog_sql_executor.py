"""Execute validated catalog SQL and format rows for chat."""

from __future__ import annotations

import concurrent.futures
import json
from typing import Any

from app.core.config import AppConfig
from app.db.postgres import DatabaseNotConfiguredError, DatabaseUnavailableError, PostgresClient
from app.services.sql_guard import SqlGuardError, validate_arn_first_parameter, validate_dynamic_sql


class CatalogSqlExecuteError(Exception):
    """Read-only execution failed (message safe to send back to the SQL generator LLM)."""


def dedupe_investor_result_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse multiple folio-level rows to one row per investor when uuid is present."""

    if len(rows) <= 1:
        return rows

    seen: set[Any] = set()
    deduped: list[dict[str, Any]] = []
    for row in rows:
        key = row.get("uuid") or row.get("investor_uuid")
        if key is None:
            deduped.append(row)
            continue
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def is_execute_timeout_error(message: str) -> bool:
    """True when Postgres or the client wall-clock limit stopped a long-running query."""

    low = (message or "").lower()
    return any(
        token in low
        for token in (
            "statement timeout",
            "query canceled",
            "canceling statement",
            "execution limit",
            "timed out",
            "timeout expired",
        )
    )


def execute_wall_timeout_seconds(config: AppConfig) -> float:
    """Client-side cap slightly above ``statement_timeout`` so the tool does not hang."""

    ms = int(config.database.statement_timeout_ms)
    grace = int(config.catalog_sql_execute_grace_seconds)
    return (ms / 1000.0) + max(1, grace)


def _json_safe_cell(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _fetch_rows(
    sql: str,
    parameters: list[Any],
    *,
    trusted_arn: str,
    config: AppConfig,
) -> list[dict[str, Any]]:
    validate_dynamic_sql(sql)
    validate_arn_first_parameter(sql, parameters, trusted_arn)

    db_url = config.database_url_value
    if not db_url:
        raise CatalogSqlExecuteError(
            "Database is not configured (set DEV_DATABASE_URL or PROD_DATABASE_URL)."
        )

    db_cfg = config.database
    db = PostgresClient(
        db_url,
        db_cfg.statement_timeout_ms,
        min_size=1,
        max_size=1,
        connect_timeout_seconds=db_cfg.connect_timeout_seconds,
        pool_timeout_seconds=db_cfg.pool_timeout_seconds,
    )
    try:
        db.open()
        rows = db.fetch_all(sql, parameters)
        return [{k: _json_safe_cell(v) for k, v in dict(row).items()} for row in rows]
    except (DatabaseNotConfiguredError, DatabaseUnavailableError) as exc:
        raise CatalogSqlExecuteError(str(exc)) from exc
    except SqlGuardError as exc:
        raise CatalogSqlExecuteError(f"SQL guard: {exc}") from exc
    except Exception as exc:
        raise CatalogSqlExecuteError(f"{type(exc).__name__}: {exc}") from exc
    finally:
        db.close()


def execute_catalog_sql_readonly(
    sql: str,
    parameters: list[Any],
    *,
    trusted_arn: str,
    config: AppConfig | None = None,
) -> list[dict[str, Any]]:
    """Run parameterized read-only SQL with statement + wall-clock timeouts."""

    from app.core.config import get_config

    config = config or get_config()
    wall_seconds = execute_wall_timeout_seconds(config)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            _fetch_rows,
            sql,
            parameters,
            trusted_arn=trusted_arn,
            config=config,
        )
        try:
            return future.result(timeout=wall_seconds)
        except concurrent.futures.TimeoutError as exc:
            raise CatalogSqlExecuteError(
                f"Query exceeded {wall_seconds:.0f}s execution limit (warehouse may be slow "
                "for SIP/holdings joins). Try narrowing filters or ask your DBA to tune indexes."
            ) from exc


def format_result_rows_for_reply(rows: list[dict[str, Any]], *, max_rows: int) -> str:
    """Compact JSON preview for ADK chat (capped row count)."""

    if not rows:
        return "Query returned 0 rows."
    shown = rows[: max(1, max_rows)]
    payload = {
        "row_count": len(rows),
        "rows_shown": len(shown),
        "rows": shown,
    }
    if len(rows) > len(shown):
        payload["truncated"] = True
    return json.dumps(payload, ensure_ascii=True, default=str, indent=2)
