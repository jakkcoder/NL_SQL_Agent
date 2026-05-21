"""Local SQLite mirror for filter-catalog discovery queries.

PostgreSQL uses ``public`` / ``sphmf`` schemas. The mirror flattens tables into a
single SQLite database with **unqualified** names matching
``SQLITE_CATALOG_FILTER_QUERIES`` (see ``scripts/sync_filter_catalog_sqlite.py``).

Set ``FILTER_CATALOG_SQLITE_PATH`` to a file produced by the sync script so
``refresh_catalog_from_db`` can merge catalog values without contacting the
remote warehouse.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

# Same semantics as ``filter_catalog.DB_FILTER_QUERIES`` but SQLite table names
# (no schema). Populated by ``scripts/sync_filter_catalog_sqlite.py``.
SQLITE_CATALOG_FILTER_QUERIES: dict[str, str] = {
    "scheme_codes": """
        SELECT DISTINCT sm.scheme_cd AS value
        FROM scheme_master sm
        WHERE sm.scheme_cd IS NOT NULL
          AND sm.allow_broker = 'Y'
        ORDER BY sm.scheme_cd ASC
        LIMIT 500
    """,
    "payout_mechanisms": """
        SELECT DISTINCT pay_mech AS value
        FROM payout_mechanism
        WHERE active_flag IS TRUE
          AND pay_mech IS NOT NULL
        ORDER BY pay_mech ASC
    """,
    "cgf_flags": """
        SELECT DISTINCT cgf_flag AS value
        FROM scheme_setup
        WHERE cgf_flag IS NOT NULL
        ORDER BY cgf_flag ASC
    """,
    "minor_inv_types": """
        SELECT DISTINCT cm.inv_type AS value
        FROM customer_master cm
        INNER JOIN tax_status ts ON cm.inv_type = ts.inv_type_code
        WHERE ts.minor_flag = 'Y'
          AND ts.distributor_flag = 'Y'
          AND ts.active_flag = 'Y'
        ORDER BY cm.inv_type ASC
    """,
    "transaction_type_codes": """
        SELECT DISTINCT tt.trxntypcod AS value
        FROM transaction_types tt
        WHERE tt.trxntypcod IS NOT NULL
        ORDER BY tt.trxntypcod ASC
        LIMIT 200
    """,
}


def is_sqlite_catalog_url(database_url: str) -> bool:
    return database_url.strip().lower().startswith("sqlite:")


def sqlite_connect_path(database_url: str) -> Path:
    """Resolve ``sqlite:///path`` (including ``sqlite:////absolute``) to a filesystem path."""

    raw = database_url.strip()
    prefix = "sqlite:///"
    if not raw.lower().startswith(prefix):
        raise ValueError(f"Expected sqlite:/// URL, got {database_url!r}")
    return Path(raw[len(prefix) :]).expanduser()


def fetch_all_sqlite(database_url: str, sql: str) -> list[dict[str, Any]]:
    path = sqlite_connect_path(database_url)
    if not path.is_file():
        raise FileNotFoundError(f"SQLite catalog file missing: {path}")

    conn = sqlite3.connect(str(path))
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(sql)
        rows = [dict(row) for row in cur.fetchall()]
        return rows
    finally:
        conn.close()
