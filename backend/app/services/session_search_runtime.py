"""Per-ADK-session bootstrap for investor search (schema + filter catalog).

On the first search-related turn in a session the backend:

1. Loads the investor schema contract: **live PostgreSQL introspection** when
   ``DEV_DATABASE_URL`` is set and ``DEV_LOCAL_SQLITE_MIRROR`` is **not** set (development);
   otherwise the packaged ``investor_db_schema_contract.json``. Stores a compact copy in
   session state (and may rewrite the JSON file on live success).
2. Builds a **snapshot** of the filter catalog (merged from PostgreSQL, a local SQLite
   mirror when ``FILTER_CATALOG_SQLITE_PATH`` or ``DEV_LOCAL_SQLITE_MIRROR`` is set, or
   the JSON file on disk) and keeps it in session state.

When ``DEV_LOCAL_SQLITE_MIRROR`` is set to an existing file in a **development** ``APP_ENV``,
live PostgreSQL **schema introspection is skipped** (packaged ``investor_db_schema_contract.json``
only); catalog merge still uses that SQLite file. Warehouse SQL execution continues to use
``DEV_DATABASE_URL`` / ``PROD_DATABASE_URL`` when configured.

Later turns in the same session reuse both snapshots without re-running DB export or
catalog refresh unless session state keys for schema/catalog are cleared.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import get_config
from app.services.filter_catalog import ensure_filter_catalog_snapshot_for_session
from app.services.investor_schema_contract import ensure_investor_schema_for_search_session

logger = logging.getLogger(__name__)


def ensure_session_search_artifacts(
    session_state: dict[str, Any],
    database_url: str | None,
    *,
    filter_catalog_database_url: str | None = None,
) -> None:
    """Load schema contract + filter catalog into ``session_state`` once per session."""

    cfg = get_config()
    catalog_url = filter_catalog_database_url if filter_catalog_database_url is not None else database_url
    schema_url = None if cfg.dev_local_sqlite_mirror_file_url else database_url
    if schema_url is None and cfg.dev_local_sqlite_mirror_file_url:
        logger.info(
            "DEV_LOCAL_SQLITE_MIRROR is set: loading packaged investor schema contract only "
            "(no live PostgreSQL introspection)."
        )
    ensure_investor_schema_for_search_session(session_state, schema_url)
    ensure_filter_catalog_snapshot_for_session(session_state, catalog_url)
