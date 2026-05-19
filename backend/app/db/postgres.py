from collections.abc import Sequence
from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


class DatabaseNotConfiguredError(RuntimeError):
    pass


class PostgresClient:
    """Thin PostgreSQL wrapper that enforces read-only, parameterized execution."""

    def __init__(
        self,
        database_url: str | None,
        statement_timeout_ms: int = 15000,
        min_size: int = 1,
        max_size: int = 4,
    ) -> None:
        self._database_url = database_url
        self._statement_timeout_ms = statement_timeout_ms
        self._min_size = min_size
        self._max_size = max_size
        self._pool: ConnectionPool | None = None

    def open(self) -> None:
        if not self._database_url:
            return
        self._pool = ConnectionPool(
            self._database_url,
            kwargs={"row_factory": dict_row},
            min_size=self._min_size,
            max_size=self._max_size,
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
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("BEGIN READ ONLY")
                cur.execute(f"SET LOCAL statement_timeout = {timeout_ms}")
                cur.execute(query, params or ())
                rows = [dict(row) for row in cur.fetchall()]
            conn.commit()
            return rows

    def health_check(self) -> bool:
        rows = self.fetch_all("SELECT 1 AS ok")
        return bool(rows and rows[0].get("ok") == 1)
