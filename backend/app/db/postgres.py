from collections.abc import Sequence
from typing import Any

from psycopg import OperationalError
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool, PoolTimeout

from app.services.sql_guard import escape_literal_percent_for_pyformat


class DatabaseNotConfiguredError(RuntimeError):
    pass


class DatabaseUnavailableError(RuntimeError):
    """Database URL is set but the server is unreachable or the pool timed out."""


_DB_UNAVAILABLE_MESSAGE = (
    "Could not connect to the investor database. Start PostgreSQL (or fix DEV_DATABASE_URL) "
    "and retry your search."
)


class PostgresClient:
    """Thin PostgreSQL wrapper that enforces read-only, parameterized execution."""

    def __init__(
        self,
        database_url: str | None,
        statement_timeout_ms: int = 15000,
        min_size: int = 1,
        max_size: int = 4,
        connect_timeout_seconds: int = 5,
        pool_timeout_seconds: int = 10,
    ) -> None:
        self._database_url = database_url
        self._statement_timeout_ms = statement_timeout_ms
        self._min_size = min_size
        self._max_size = max_size
        self._connect_timeout_seconds = connect_timeout_seconds
        self._pool_timeout_seconds = pool_timeout_seconds
        self._pool: ConnectionPool | None = None

    def open(self) -> None:
        if not self._database_url:
            return
        self._pool = ConnectionPool(
            self._database_url,
            kwargs={
                "row_factory": dict_row,
                "connect_timeout": self._connect_timeout_seconds,
            },
            min_size=self._min_size,
            max_size=self._max_size,
            timeout=self._pool_timeout_seconds,
            open=True,
        )

    def close(self) -> None:
        if self._pool:
            self._pool.close()
            self._pool = None

    def fetch_all(self, query: str, params: Sequence[Any] | None = None) -> list[dict[str, Any]]:
        if not self._pool:
            raise DatabaseNotConfiguredError(
                "Database URL is not configured. Set DEV_DATABASE_URL or PROD_DATABASE_URL "
                "based on APP_ENV."
            )

        timeout_ms = int(self._statement_timeout_ms)
        try:
            with self._pool.connection(timeout=self._pool_timeout_seconds) as conn:
                with conn.cursor() as cur:
                    cur.execute("BEGIN READ ONLY")
                    cur.execute(f"SET LOCAL statement_timeout = {timeout_ms}")
                    exec_sql = (
                        escape_literal_percent_for_pyformat(query)
                        if params
                        else query
                    )
                    cur.execute(exec_sql, params or ())
                    rows = [dict(row) for row in cur.fetchall()]
                conn.commit()
                return rows
        except (PoolTimeout, OperationalError) as exc:
            raise DatabaseUnavailableError(_DB_UNAVAILABLE_MESSAGE) from exc

    def health_check(self) -> bool:
        rows = self.fetch_all("SELECT 1 AS ok")
        return bool(rows and rows[0].get("ok") == 1)
