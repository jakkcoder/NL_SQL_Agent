from collections.abc import Sequence
from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


class DatabaseNotConfiguredError(RuntimeError):
    pass


class PostgresClient:
    """Thin PostgreSQL wrapper that enforces read-only, parameterized execution."""

    def __init__(self, database_url: str | None, statement_timeout_ms: int = 15000) -> None:
        self._database_url = database_url
        self._statement_timeout_ms = statement_timeout_ms
        self._pool: ConnectionPool | None = None

    def open(self) -> None:
        if not self._database_url:
            return
        self._pool = ConnectionPool(
            self._database_url,
            kwargs={"row_factory": dict_row},
            min_size=1,
            max_size=4,
            open=True,
        )

    def close(self) -> None:
        if self._pool:
            self._pool.close()
            self._pool = None

    def fetch_all(self, query: str, params: Sequence[Any] | None = None) -> list[dict[str, Any]]:
        if not self._pool:
            raise DatabaseNotConfiguredError("DATABASE_URL is not configured.")

        with self._pool.connection() as conn:
            with conn.transaction(read_only=True):
                with conn.cursor() as cur:
                    cur.execute("SET LOCAL statement_timeout = %s", (self._statement_timeout_ms,))
                    cur.execute(query, params or ())
                    return [dict(row) for row in cur.fetchall()]

    def health_check(self) -> bool:
        rows = self.fetch_all("SELECT 1 AS ok")
        return bool(rows and rows[0].get("ok") == 1)
