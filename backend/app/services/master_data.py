from typing import Any

from app.db.postgres import PostgresClient


class MasterDataService:
    """Reads DB-backed filter values for UI/agent validation."""

    def __init__(self, db: PostgresClient) -> None:
        self._db = db

    def get_scheme_options(self) -> list[dict[str, Any]]:
        return self._db.fetch_all(
            """
            SELECT scheme_cd AS value, scheme_name AS label
            FROM scheme_master
            ORDER BY scheme_name ASC
            """
        )

    def get_category_options(self) -> list[dict[str, Any]]:
        return self._db.fetch_all(
            """
            SELECT DISTINCT category AS value, category AS label
            FROM scheme_master
            WHERE category IS NOT NULL
            ORDER BY category ASC
            """
        )
