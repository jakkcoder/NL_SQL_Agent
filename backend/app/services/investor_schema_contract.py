"""Investor warehouse schema contract: build from PostgreSQL or load packaged JSON.

Used by:
- ``app/data/export_investor_schema_contract.py`` (refresh local JSON)
- ``schema_contract_for_sql_generator`` (catalog SQL generation)
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

logger = logging.getLogger(__name__)

# Tables aligned with planning/complete_function.sql (filter_dp_investor_menu).
INVESTOR_CONTRACT_TABLES: list[tuple[str, str]] = [
    ("public", "distributor_investor_mapping"),
    ("public", "investor"),
    ("public", "tax_status"),
    ("public", "scheme_master"),
    ("public", "payout_mechanism"),
    ("sphmf", "customer_master"),
    ("sphmf", "multiple_bank"),
    ("sphmf", "customer_schemes"),
    ("sphmf", "scheme_setup"),
    ("sphmf", "processed_trxns"),
    ("sphmf", "sipstp"),
    ("sphmf", "dtp_regn"),
    ("sphmf", "trigger_trxn"),
    ("sphmf", "transaction_types"),
]

_COL_SQL = """
SELECT
    c.table_schema,
    c.table_name,
    c.column_name,
    c.ordinal_position,
    c.column_default,
    c.is_nullable,
    c.data_type,
    c.udt_catalog,
    c.udt_schema,
    c.udt_name,
    c.character_maximum_length,
    c.character_octet_length,
    c.numeric_precision,
    c.numeric_precision_radix,
    c.numeric_scale,
    c.datetime_precision,
    c.domain_catalog,
    c.domain_schema,
    c.domain_name,
    c.collation_catalog,
    c.collation_schema,
    c.collation_name,
    c.dtd_identifier,
    c.identity_generation,
    c.identity_start,
    c.identity_increment,
    c.identity_maximum,
    c.identity_minimum,
    c.identity_cycle,
    c.is_generated,
    c.generation_expression,
    c.is_updatable
FROM information_schema.columns c
WHERE c.table_schema = %s AND c.table_name = %s
ORDER BY c.ordinal_position
"""

_PG_COUNT_SQL = """
SELECT COUNT(*) AS n
FROM pg_attribute a
JOIN pg_class cl ON cl.oid = a.attrelid
JOIN pg_namespace n ON n.oid = cl.relnamespace
WHERE n.nspname = %s AND cl.relname = %s
  AND a.attnum > 0 AND NOT a.attisdropped
"""

_COMMENT_SQL = """
SELECT a.attname AS column_name, pg_catalog.col_description(a.attrelid, a.attnum) AS description
FROM pg_attribute a
JOIN pg_class c ON c.oid = a.attrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = %s AND c.relname = %s
  AND a.attnum > 0 AND NOT a.attisdropped
"""

_TABLE_COMMENT_SQL = """
SELECT pg_catalog.obj_description(c.oid) AS table_description
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = %s AND c.relname = %s AND c.relkind IN ('r', 'p', 'v')
"""

_PART_SQL = """
SELECT pt.partstrat, pg_get_partkeydef(c.oid) AS partition_key_def
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_partitioned_table pt ON pt.partrelid = c.oid
WHERE n.nspname = %s AND c.relname = %s
"""

_PK_SQL = """
SELECT kcu.column_name
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
  ON tc.constraint_name = kcu.constraint_name
 AND tc.table_schema = kcu.table_schema
WHERE tc.table_schema = %s AND tc.table_name = %s AND tc.constraint_type = 'PRIMARY KEY'
ORDER BY kcu.ordinal_position
"""

_FK_SQL = """
SELECT
    tc.constraint_name,
    kcu.column_name,
    ccu.table_schema AS foreign_table_schema,
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name
FROM information_schema.table_constraints AS tc
JOIN information_schema.key_column_usage AS kcu
  ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
JOIN information_schema.constraint_column_usage AS ccu
  ON ccu.constraint_name = tc.constraint_name AND ccu.table_schema = tc.table_schema
WHERE tc.constraint_type = 'FOREIGN KEY'
  AND tc.table_schema = %s AND tc.table_name = %s
ORDER BY tc.constraint_name, kcu.ordinal_position
"""


def _sanitize_catalog_fields(columns: list[dict[str, Any]]) -> None:
    for col in columns:
        for key in ("udt_catalog", "domain_catalog", "collation_catalog"):
            val = col.get(key)
            if val is not None and val != "postgres":
                col[key] = None


def build_full_schema_contract(database_url: str) -> dict[str, Any]:
    """Introspect all columns for INVESTOR_CONTRACT_TABLES; verify counts vs pg_attribute."""

    from datetime import datetime, timezone

    out_tables: list[dict[str, Any]] = []
    missing: list[str] = []

    with psycopg.connect(database_url, connect_timeout=30, row_factory=dict_row) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout = 120000")

            for schema, table in INVESTOR_CONTRACT_TABLES:
                exists = cur.execute(
                    """
                    SELECT 1 FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = %s AND c.relname = %s AND c.relkind IN ('r', 'p')
                    """,
                    (schema, table),
                ).fetchone()
                if not exists:
                    missing.append(f"{schema}.{table}")
                    continue

                cur.execute(_COL_SQL, (schema, table))
                cols = cur.fetchall()
                cur.execute(_PG_COUNT_SQL, (schema, table))
                pg_n = cur.fetchone()["n"]

                cur.execute(_COMMENT_SQL, (schema, table))
                col_comments = {r["column_name"]: r["description"] for r in cur.fetchall()}

                cur.execute(_TABLE_COMMENT_SQL, (schema, table))
                tbl_desc = cur.fetchone()

                cur.execute(_PART_SQL, (schema, table))
                part = cur.fetchone()

                cur.execute(_PK_SQL, (schema, table))
                pks = [r["column_name"] for r in cur.fetchall()]

                cur.execute(_FK_SQL, (schema, table))
                fks = cur.fetchall()

                info_cols = len(cols)
                if info_cols != pg_n:
                    missing.append(
                        f"COUNT_MISMATCH {schema}.{table} "
                        f"information_schema={info_cols} pg_attribute={pg_n}"
                    )

                enriched: list[dict[str, Any]] = []
                for c in cols:
                    d = dict(c)
                    d["pg_comment"] = col_comments.get(d["column_name"])
                    enriched.append(d)

                _sanitize_catalog_fields(enriched)

                out_tables.append(
                    {
                        "schema": schema,
                        "table": table,
                        "fully_qualified": f"{schema}.{table}",
                        "table_description": tbl_desc["table_description"] if tbl_desc else None,
                        "is_partitioned_parent": bool(part and part.get("partition_key_def")),
                        "partition_strategy": part.get("partstrat") if part else None,
                        "partition_key_def": part.get("partition_key_def") if part else None,
                        "primary_key_columns": pks,
                        "foreign_keys": [dict(fk) for fk in fks],
                        "column_count_information_schema": info_cols,
                        "column_count_pg_attribute_non_dropped": pg_n,
                        "columns": enriched,
                    }
                )

    return {
        "contract_kind": "postgresql_schema_dump",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "database_url_configured": True,
        "note": (
            "udt_catalog/domain_catalog/collation_catalog cleared when not 'postgres' "
            "to avoid embedding instance catalog names."
        ),
        "tables_requested": [f"{s}.{t}" for s, t in INVESTOR_CONTRACT_TABLES],
        "tables_found": len(out_tables),
        "tables_missing_in_database": missing,
        "tables": out_tables,
    }


def compact_schema_contract(full: dict[str, Any]) -> dict[str, Any]:
    """Shrink full introspection contract for LLM / session storage (names + types + keys)."""

    slim_tables: list[dict[str, Any]] = []
    for t in full.get("tables", []):
        slim_tables.append(
            {
                "schema": t.get("schema"),
                "table": t.get("table"),
                "fully_qualified": t.get("fully_qualified"),
                "is_partitioned_parent": t.get("is_partitioned_parent"),
                "partition_key_def": t.get("partition_key_def"),
                "primary_key_columns": t.get("primary_key_columns"),
                "foreign_keys": t.get("foreign_keys"),
                "columns": [
                    {
                        "name": c.get("column_name"),
                        "ordinal": c.get("ordinal_position"),
                        "data_type": c.get("data_type"),
                        "udt_name": c.get("udt_name"),
                        "nullable": c.get("is_nullable"),
                        "default": c.get("column_default"),
                        "pg_comment": c.get("pg_comment"),
                    }
                    for c in t.get("columns", [])
                ],
            }
        )
    total_cols = sum(len(x["columns"]) for x in slim_tables)
    return {
        "contract_kind": "investor_schema_compact",
        "source_generated_at": full.get("generated_at"),
        "tables": slim_tables,
        "table_count": len(slim_tables),
        "column_count": total_cols,
    }


def packaged_schema_contract_path() -> Path:
    """Path to committed JSON (may be stale vs production)."""

    return Path(__file__).resolve().parents[1] / "data" / "investor_db_schema_contract.json"


def load_packaged_schema_contract() -> dict[str, Any] | None:
    """Load ``investor_db_schema_contract.json`` from ``app/data`` if present."""

    path = packaged_schema_contract_path()
    if not path.is_file():
        logger.warning("Packaged schema contract missing: %s", path)
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not load packaged schema contract: %s", exc)
        return None


def schema_contract_for_sql_generator(
    filter_catalog: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Compact schema guide for catalog SQL generation (not the 700KB+ raw contract)."""

    from app.services.schema_contract_guide import schema_guide_for_sql_generator

    return schema_guide_for_sql_generator(filter_catalog)


def serialize_schema_contract_for_prompt(contract: dict[str, Any], max_chars: int) -> str:
    """JSON string for LLM user payload; truncate only when over ``max_chars``."""

    from app.services.schema_contract_guide import serialize_schema_guide_for_prompt

    if contract.get("contract_kind") == "investor_schema_guide":
        return serialize_schema_guide_for_prompt(contract, max_chars)
    raw = json.dumps(contract, ensure_ascii=True, default=str)
    if len(raw) <= max_chars:
        return raw
    return raw[: max_chars - 80] + "\n...(investor_schema_contract_json truncated for prompt size)\n"


def write_full_schema_contract_atomic(full: dict[str, Any], path: Path | None = None) -> Path:
    """Atomically write full introspection JSON (default: packaged app/data path)."""

    target = path or packaged_schema_contract_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(full, indent=2, default=str)
    fd, tmp = tempfile.mkstemp(
        prefix="investor_db_schema_contract.",
        suffix=".tmp",
        dir=str(target.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
        os.replace(tmp, target)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return target
