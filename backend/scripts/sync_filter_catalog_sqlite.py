#!/usr/bin/env python3
"""Copy PostgreSQL investor-contract tables into a local SQLite mirror.

**What gets copied**

- **Default (``--mode contract``):** all **14** tables listed in
  ``app.services.investor_schema_contract.INVESTOR_CONTRACT_TABLES`` (the same
  set used for schema contract + warehouse SQL in this repo). Each table is
  stored as ``{schema}_{table}`` (e.g. ``public_investor``, ``sphmf_sipstp``).
- **Six compatibility views** (``scheme_master``, ``customer_master``, …) so
  ``app.services.catalog_sqlite`` discovery queries keep working without
  schema prefixes.

This is a **subset of the warehouse** the NL SQL Agent is built around—not
every table in the entire PostgreSQL instance. For a byte-for-byte clone of the
whole server (all schemas, functions, types), use **local PostgreSQL** +
``pg_dump`` / ``pg_restore`` (or Docker) instead of SQLite.

**Catalog-only mode (``--mode catalog``):** copies only the **6** tables needed
for filter-catalog JSON merge (smaller file, faster).

Usage (from ``backend/`` with network access to Postgres)::

    export SOURCE_DATABASE_URL="$DEV_DATABASE_URL"
    PYTHONPATH=. python scripts/sync_filter_catalog_sqlite.py

Then in ``.env``::

    FILTER_CATALOG_SQLITE_PATH=app/data/filter_catalog_local.sqlite

Schema introspection and **live investor SQL** still use ``DEV_DATABASE_URL``
when set; this file is used for **filter catalog refresh** when the path exists.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

from app.services.catalog_sqlite import SQLITE_CATALOG_FILTER_QUERIES  # noqa: E402
from app.services.investor_schema_contract import INVESTOR_CONTRACT_TABLES  # noqa: E402

# Short names expected by ``SQLITE_CATALOG_FILTER_QUERIES`` -> physical SQLite table.
CATALOG_COMPAT_VIEWS: list[tuple[str, str]] = [
    ("scheme_master", "public_scheme_master"),
    ("payout_mechanism", "public_payout_mechanism"),
    ("scheme_setup", "sphmf_scheme_setup"),
    ("customer_master", "sphmf_customer_master"),
    ("tax_status", "public_tax_status"),
    ("transaction_types", "sphmf_transaction_types"),
]

# (sqlite_short_name, fully_qualified_pg) — ``--mode catalog`` only.
CATALOG_TABLES_ONLY: list[tuple[str, str]] = [
    ("scheme_master", "public.scheme_master"),
    ("payout_mechanism", "public.payout_mechanism"),
    ("scheme_setup", "sphmf.scheme_setup"),
    ("customer_master", "sphmf.customer_master"),
    ("tax_status", "public.tax_status"),
    ("transaction_types", "sphmf.transaction_types"),
]


def _quote_ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _sqlite_physical_name(schema: str, table: str) -> str:
    return f"{schema}_{table}"


def _copy_table_streaming(
    pg_cur,
    sl_cur,
    local_name: str,
    pg_qualified: str,
    *,
    fetch_size: int,
) -> int:
    """Copy ``SELECT *`` from PG into SQLite using ``fetchmany`` (bounded memory)."""

    pg_cur.execute(f"SELECT * FROM {pg_qualified} WHERE false")
    cols = [d.name for d in pg_cur.description]
    sl_cur.execute(f"DROP TABLE IF EXISTS {_quote_ident(local_name)}")
    if not cols:
        sl_cur.execute(f"CREATE TABLE {_quote_ident(local_name)} (_placeholder TEXT)")
        return 0
    col_sql = ", ".join(f"{_quote_ident(c)} TEXT" for c in cols)
    sl_cur.execute(f"CREATE TABLE {_quote_ident(local_name)} ({col_sql})")
    placeholders = ", ".join(["?"] * len(cols))
    col_list = ", ".join(_quote_ident(c) for c in cols)
    insert_sql = f"INSERT INTO {_quote_ident(local_name)} ({col_list}) VALUES ({placeholders})"

    pg_cur.execute(f"SELECT * FROM {pg_qualified}")
    total = 0
    while True:
        rows = pg_cur.fetchmany(fetch_size)
        if not rows:
            break
        batch: list[tuple] = []
        for row in rows:
            if isinstance(row, dict):
                batch.append(tuple(row.get(c) for c in cols))
            else:
                batch.append(tuple(row))
        sl_cur.executemany(insert_sql, batch)
        total += len(rows)
    return total


def _drop_catalog_views(sl_cur: sqlite3.Cursor) -> None:
    for short, _ in CATALOG_COMPAT_VIEWS:
        sl_cur.execute(f"DROP VIEW IF EXISTS {_quote_ident(short)}")


def _create_catalog_views(sl_cur: sqlite3.Cursor) -> None:
    _drop_catalog_views(sl_cur)
    for short, physical in CATALOG_COMPAT_VIEWS:
        sl_cur.execute(
            f"CREATE VIEW {_quote_ident(short)} AS SELECT * FROM {_quote_ident(physical)}"
        )


def _smoke_sqlite(sqlite_path: Path) -> None:
    url = f"sqlite:///{sqlite_path.resolve()}"
    conn = sqlite3.connect(str(sqlite_path))
    try:
        for _key, sql in SQLITE_CATALOG_FILTER_QUERIES.items():
            conn.execute(sql)
    finally:
        conn.close()
    print(f"Smoke OK: ran {len(SQLITE_CATALOG_FILTER_QUERIES)} catalog queries on {url}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pg-url",
        default=os.environ.get("SOURCE_DATABASE_URL") or os.environ.get("DEV_DATABASE_URL"),
        help="PostgreSQL URL (default: SOURCE_DATABASE_URL or DEV_DATABASE_URL)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=BACKEND_DIR / "app" / "data" / "filter_catalog_local.sqlite",
        help="Output SQLite path (default: app/data/filter_catalog_local.sqlite under backend/)",
    )
    parser.add_argument(
        "--fetch-size",
        type=int,
        default=5000,
        metavar="N",
        help="Rows per PG fetchmany batch (default: 5000).",
    )
    parser.add_argument(
        "--mode",
        choices=("contract", "catalog"),
        default="contract",
        help="'contract' = all 14 INVESTOR_CONTRACT_TABLES + catalog views (default). "
        "'catalog' = 6 catalog tables only, short names, no views.",
    )
    parser.add_argument(
        "--smoke-only",
        action="store_true",
        help="Only run catalog discovery SQL against an existing SQLite file (no PG copy).",
    )
    args = parser.parse_args()

    out_path = args.output
    if not args.smoke_only:
        if not args.pg_url:
            print("Missing PostgreSQL URL. Set --pg-url or SOURCE_DATABASE_URL / DEV_DATABASE_URL.", file=sys.stderr)
            return 1
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if out_path.exists():
            out_path.unlink()

        conn_str = args.pg_url.strip()
        mode_label = "14 investor-contract tables + 6 catalog views" if args.mode == "contract" else "6 catalog tables"
        print(f"Copying from PostgreSQL into {out_path} ({mode_label}) ...")
        with psycopg.connect(conn_str, autocommit=True) as pg_conn, sqlite3.connect(str(out_path)) as sl_conn:
            sl_cur = sl_conn.cursor()
            with pg_conn.cursor(row_factory=dict_row) as pg_cur:
                total = 0
                table_count = 0
                if args.mode == "catalog":
                    for local, qualified in CATALOG_TABLES_ONLY:
                        n = _copy_table_streaming(
                            pg_cur, sl_cur, local, qualified, fetch_size=args.fetch_size
                        )
                        print(f"  {local} <- {qualified}: {n} row(s)")
                        total += n
                        table_count += 1
                else:
                    for schema, table in INVESTOR_CONTRACT_TABLES:
                        physical = _sqlite_physical_name(schema, table)
                        qualified = f"{schema}.{table}"
                        n = _copy_table_streaming(
                            pg_cur, sl_cur, physical, qualified, fetch_size=args.fetch_size
                        )
                        print(f"  {physical} <- {qualified}: {n} row(s)")
                        total += n
                        table_count += 1
                    _create_catalog_views(sl_cur)
                    print("  (created 6 catalog compatibility views on top of physical tables)")
            sl_conn.commit()
        print(f"Done. {table_count} table(s), {total} row(s) copied.")

    if not out_path.is_file():
        print(f"SQLite file not found: {out_path}", file=sys.stderr)
        return 1
    _smoke_sqlite(out_path)
    print("\nNext: set FILTER_CATALOG_SQLITE_PATH in .env, e.g.")
    rel = out_path.relative_to(BACKEND_DIR) if out_path.is_relative_to(BACKEND_DIR) else out_path
    print(f"  FILTER_CATALOG_SQLITE_PATH={rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
