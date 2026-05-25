"""Build a compact natural-language schema guide from ``investor_db_schema_contract.json``.

Output (``app/data/``):
- ``investor_db_schema_guide.json`` — machine-readable for LLM SQL generation
- ``investor_db_schema_guide.md`` — human-readable reference
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
import re
import sqlite3
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from app.services.investor_schema_question_patterns import enrich_investor_schema_guide

logger = logging.getLogger(__name__)

_SAMPLE_VALUE_MAX_LEN = 160

_DATA_DIR = Path(__file__).resolve().parents[1] / "data"
GUIDE_JSON_PATH = _DATA_DIR / "investor_db_schema_guide.json"
GUIDE_MD_PATH = _DATA_DIR / "investor_db_schema_guide.md"

# Curated join paths (aligned with ``individual_warehouse_sql`` / distributor menu).
JOIN_RECIPES: list[dict[str, str]] = [
    {
        "name": "arn_scope_anchor",
        "description": "Every query must scope to the session distributor ARN.",
        "sql_pattern": "public.distributor_investor_mapping dim WHERE dim.arn_code = %s",
    },
    {
        "name": "investor_identity",
        "description": "List investors for an ARN.",
        "sql_pattern": (
            "dim.investor_uuid = public.investor.uuid "
            "AND dim.arn_code = %s"
        ),
    },
    {
        "name": "folio_kyc_city",
        "description": "Geography / email / folio-level attributes (e.g. Mumbai).",
        "sql_pattern": (
            "sphmf.customer_master cm ON cm.folio_no = dim.folio_number "
            "WHERE dim.arn_code = %s AND lower(trim(cm.city::text)) ILIKE %s"
        ),
    },
    {
        "name": "otm_bank",
        "description": "One-time mandate (OTM) via bank registration.",
        "sql_pattern": (
            "sphmf.multiple_bank mb ON mb.folio_no = dim.folio_number "
            "JOIN public.payout_mechanism pm ON mb.paymech = pm.pay_mech "
            "WHERE pm.otm_flag IS TRUE AND mb.om_umrn IS NOT NULL"
        ),
    },
    {
        "name": "holdings_units",
        "description": "Positive unit balance (holdings) by scheme.",
        "sql_pattern": (
            "sphmf.processed_trxns pt "
            "JOIN sphmf.customer_schemes cs ON pt.folio_no = cs.folio_no AND pt.sch_code = cs.sch_code "
            "JOIN public.scheme_master sm ON pt.sch_code = sm.scheme_cd "
            "WHERE pt.broker_code = %s GROUP BY pt.folio_no, pt.sch_code HAVING SUM(signed units) > 0"
        ),
    },
    {
        "name": "active_sipstp",
        "description": "Active systematic plans (SIP/STP/SWP families).",
        "sql_pattern": (
            "sphmf.sipstp s ON dim.folio_number = s.folio_no AND dim.arn_code = s.brok_code "
            "JOIN public.scheme_master sm ON s.sch_code = sm.scheme_cd "
            "WHERE s.cease_dt IS NULL AND s.to_date > NOW()"
        ),
    },
    {
        "name": "investor_activity",
        "description": "Purchases/redemptions/SIP/STP over a time window.",
        "sql_pattern": (
            "sphmf.processed_trxns pt "
            "JOIN sphmf.transaction_types tt ON pt.trxn_type = tt.trxn_type_code "
            "WHERE pt.broker_code = %s AND pt.l_trxn_date >= %s"
        ),
    },
    {
        "name": "minor_tax_status",
        "description": "Minor investor subtype via tax status flags.",
        "sql_pattern": (
            "sphmf.customer_master cm JOIN public.tax_status ts ON cm.inv_type = ts.inv_type_code "
            "WHERE ts.minor_flag = 'Y' AND ts.distributor_flag = 'Y'"
        ),
    },
    {
        "name": "cgf_schemes",
        "description": "Capital gains feeder (CGF) scheme filter.",
        "sql_pattern": (
            "sphmf.scheme_setup WHERE cgf_flag = 'C' AND plan_type <> 'D'"
        ),
    },
]

TABLE_NARRATIVES: dict[str, str] = {
    "public.distributor_investor_mapping": (
        "Bridge table: links distributor ARN (arn_code) to investor UUID and folio_number. "
        "Use as the mandatory ARN scope anchor for every query."
    ),
    "public.investor": (
        "Investor master: legal name, PAN, date of birth, email, mobile. "
        "Join via uuid = distributor_investor_mapping.investor_uuid."
    ),
    "public.tax_status": (
        "Lookup for investor type codes (inv_type_code) with minor/distributor/active flags."
    ),
    "public.scheme_master": (
        "Scheme reference (scheme_cd, scheme_name, allow_broker). Join on sch_code = scheme_cd."
    ),
    "public.payout_mechanism": (
        "Payment mechanism lookup; filter OTM-capable pay_mech rows (otm_flag, active_flag)."
    ),
    "sphmf.customer_master": (
        "Folio-level customer/KYC: city, inv_type, names. Join folio_no = dim.folio_number."
    ),
    "sphmf.multiple_bank": (
        "Bank/mandate rows per folio (folio_no); used for OTM (om_umrn, paymech, cease_dt)."
    ),
    "sphmf.customer_schemes": (
        "Folio + scheme registration (folio_no, sch_code, div_reinv_flag, l_trxn_date)."
    ),
    "sphmf.scheme_setup": (
        "Scheme setup flags (schcode, cgf_flag, plan_type) for CGF and plan filters."
    ),
    "sphmf.processed_trxns": (
        "Posted transactions: units, trxn_sign, sch_code, broker_code, l_trxn_date, trxn_type."
    ),
    "sphmf.sipstp": (
        "Systematic instructions (SIP/STP/SWP): atrxn_type, switch_flag, sch_code, brok_code, dates."
    ),
    "sphmf.dtp_regn": (
        "Dynamic transfer plan (DTP) registrations."
    ),
    "sphmf.trigger_trxn": (
        "Trigger-based transaction rows."
    ),
    "sphmf.transaction_types": (
        "Maps trxn_type_code to trxndbcr / subtype for activity filters (purchase, redemption, SIP, etc.)."
    ),
}

# Always include these column names when present on a table.
ESSENTIAL_COLUMN_NAMES: frozenset[str] = frozenset(
    {
        "uuid",
        "arn_code",
        "folio_number",
        "folio_no",
        "investor_uuid",
        "pan_number",
        "first_name",
        "middle_name",
        "last_name",
        "dob",
        "email",
        "mobile_number",
        "city",
        "inv_type",
        "sch_code",
        "scheme_cd",
        "scheme_name",
        "broker_code",
        "brok_code",
        "l_trxn_date",
        "trxn_type",
        "trxn_type_code",
        "trxndbcr",
        "trxn_subtype_code",
        "units",
        "trxn_sign",
        "atrxn_type",
        "switch_flag",
        "sub_trxn_type",
        "paymech",
        "om_umrn",
        "cease_dt",
        "allow_broker",
        "div_reinv_flag",
        "cgf_flag",
        "plan_type",
        "schcode",
        "otm_flag",
        "active_flag",
        "minor_flag",
        "distributor_flag",
        "cancellation_request_date",
        "to_date",
    }
)

# Per-table extra essentials beyond the global set.
TABLE_EXTRA_ESSENTIALS: dict[str, frozenset[str]] = {
    "public.scheme_master": frozenset(
        {"scheme_cd", "scheme_name", "allow_broker", "scheme_type", "fund_code", "investment_option"}
    ),
}

_MAX_COLUMNS_PER_TABLE = 45
_SCHEME_MASTER_MAX = 22


def _data_dir() -> Path:
    return _DATA_DIR


def guide_json_path() -> Path:
    return GUIDE_JSON_PATH


def guide_md_path() -> Path:
    return GUIDE_MD_PATH


def _column_description(name: str, data_type: str, nullable: str) -> str:
    """Short NL gloss from column name + type."""

    n = name.lower()
    gloss: str | None = None
    if n in ("arn_code", "brok_code", "broker_code"):
        gloss = "distributor ARN / broker code for row scope"
    elif "folio" in n:
        gloss = "folio identifier linking sphmf and public schemas"
    elif n in ("investor_uuid",) or n == "uuid":
        gloss = "investor UUID key"
    elif n == "city":
        gloss = "city name for geography filters (e.g. Mumbai)"
    elif n == "dob":
        gloss = "date of birth; use AGE(dob) for age filters"
    elif n in ("sch_code", "scheme_cd", "schcode"):
        gloss = "mutual fund scheme code (join to scheme_master.scheme_cd)"
    elif n == "l_trxn_date":
        gloss = "last transaction date for activity/dormancy windows"
    elif n == "atrxn_type":
        gloss = "systematic plan transaction type (SIP/STP/SWP logic)"
    elif n == "trxn_sign":
        gloss = "transaction sign (+ purchase / - redemption) for unit balance"
    elif n == "units":
        gloss = "transaction units"
    elif n == "om_umrn":
        gloss = "OTM UMRN registration"
    elif n == "paymech":
        gloss = "payment mechanism code (join payout_mechanism)"
    elif n == "inv_type":
        gloss = "investor type code (join tax_status)"
    elif "email" in n:
        gloss = "email address"
    elif "pan" in n:
        gloss = "PAN tax id"
    elif gloss is None and n.endswith("_flag"):
        gloss = "boolean/char flag"
    elif gloss is None and n.endswith("_date") or n.endswith("_dt"):
        gloss = "date/timestamp"
    elif gloss is None and n.endswith("_code"):
        gloss = "code lookup key"
    if gloss:
        null_note = " nullable" if nullable == "YES" else ""
        return f"{gloss}; {data_type}{null_note}"
    null_note = " nullable" if nullable == "YES" else ""
    return f"{data_type}{null_note}"


def _parse_catalog_column_refs(filter_catalog: dict[str, Any] | None) -> dict[str, set[str]]:
    """Map fully-qualified table -> column names referenced in filter catalog parameters."""

    refs: dict[str, set[str]] = {}
    if not filter_catalog:
        return refs
    filters = filter_catalog.get("filters") or {}
    pat = re.compile(r"([a-z_][\w]*\.[a-z_][\w]*)\.([a-z_][\w]*)", re.I)
    for spec in filters.values():
        if not isinstance(spec, dict):
            continue
        param = str(spec.get("parameter") or "")
        for m in pat.finditer(param):
            table_ref, col = m.group(1).lower(), m.group(2).lower()
            refs.setdefault(table_ref, set()).add(col)
    return refs


def _pick_columns(
    table: dict[str, Any],
    catalog_refs: dict[str, set[str]],
) -> list[dict[str, str]]:
    fq = str(table.get("fully_qualified") or "").lower()
    schema = str(table.get("schema") or "")
    table_name = str(table.get("table") or "")
    short_ref = f"{schema}.{table_name}".lower()
    catalog_cols = catalog_refs.get(short_ref, set()) | catalog_refs.get(fq, set())
    extra = TABLE_EXTRA_ESSENTIALS.get(fq, frozenset())

    selected: list[tuple[int, str, dict[str, Any]]] = []
    overflow: list[tuple[int, str, dict[str, Any]]] = []
    for col in table.get("columns") or []:
        name = str(col.get("column_name") or "")
        if not name:
            continue
        priority = 10
        if name in ESSENTIAL_COLUMN_NAMES or name in extra or name in catalog_cols:
            priority = 0
        elif col.get("pg_comment"):
            priority = 2
        entry = (priority, name, col)
        if priority <= 2:
            selected.append(entry)
        else:
            overflow.append(entry)

    selected.sort(key=lambda x: (x[0], x[1]))
    cap = _SCHEME_MASTER_MAX if table_name == "scheme_master" else _MAX_COLUMNS_PER_TABLE
    picked = selected[:cap]
    if len(picked) < cap:
        overflow.sort(key=lambda x: x[1])
        picked.extend(overflow[: cap - len(picked)])

    out: list[dict[str, str]] = []
    for _, name, col in picked:
        dtype = str(col.get("data_type") or col.get("udt_name") or "unknown")
        nullable = str(col.get("is_nullable") or "YES")
        comment = col.get("pg_comment")
        desc = _column_description(name, dtype, nullable)
        if comment:
            desc = f"{desc}. DB comment: {comment}"
        out.append({"name": name, "type": dtype, "nullable": nullable, "description": desc})
    return out


def _json_safe_sample_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        text = value if not isinstance(value, str) else value
        if isinstance(text, str) and len(text) > _SAMPLE_VALUE_MAX_LEN:
            return text[: _SAMPLE_VALUE_MAX_LEN - 3] + "..."
        return value
    if isinstance(value, datetime):
        try:
            return value.isoformat()
        except (ValueError, OSError, OverflowError):
            return str(value)
    if isinstance(value, date):
        try:
            return value.isoformat()
        except (ValueError, OSError, OverflowError):
            return str(value)
    if isinstance(value, (UUID, Decimal)):
        return str(value)
    if isinstance(value, (bytes, bytearray)):
        return f"<{len(value)} bytes>"
    if isinstance(value, dict):
        return {str(k): _json_safe_sample_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe_sample_value(v) for v in value[:20]]
    text = str(value)
    if len(text) > _SAMPLE_VALUE_MAX_LEN:
        return text[: _SAMPLE_VALUE_MAX_LEN - 3] + "..."
    return text


def _sample_row_from_db_row(
    row: dict[str, Any],
    documented_columns: list[str],
) -> dict[str, Any]:
    """Keep only documented columns; show how values are stored in the warehouse."""

    out: dict[str, Any] = {}
    for name in documented_columns:
        if name in row:
            out[name] = _json_safe_sample_value(row[name])
    return out


def _sqlite_table_candidates(schema: str, table: str) -> list[str]:
    """Physical SQLite names used by the local mirror (``sync_filter_catalog_sqlite``)."""

    names = [f"{schema}_{table}", table]
    if schema == "public":
        names.append(f"public.{table}")
    return names


def _fetch_sqlite_sample(
    database_url: str,
    schema: str,
    table: str,
    documented_columns: list[str],
) -> dict[str, Any] | None:
    from app.services.catalog_sqlite import sqlite_connect_path

    path = sqlite_connect_path(database_url)
    if not path.is_file():
        return None
    col_sql = ", ".join(f'"{c}"' for c in documented_columns) if documented_columns else "*"
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        for candidate in _sqlite_table_candidates(schema, table):
            try:
                cur = conn.execute(f'SELECT {col_sql} FROM "{candidate}" LIMIT 1')
                row = cur.fetchone()
                if row is not None:
                    raw = dict(row)
                    return _sample_row_from_db_row(raw, documented_columns or list(raw.keys()))
            except sqlite3.Error:
                continue
    finally:
        conn.close()
    return None


def _fetch_postgres_sample(
    database_url: str,
    schema: str,
    table: str,
    documented_columns: list[str],
) -> dict[str, Any] | None:
    import psycopg
    from psycopg import sql
    from psycopg.rows import dict_row

    if documented_columns:
        select_list = sql.SQL(", ").join(sql.Identifier(c) for c in documented_columns)
    else:
        select_list = sql.SQL("*")
    # to_jsonb avoids psycopg decode errors on edge-case timestamps (e.g. year 0001).
    query = sql.SQL("SELECT to_jsonb(t) AS row_json FROM (SELECT {} FROM {} LIMIT 1) t").format(
        select_list,
        sql.Identifier(schema, table),
    )
    try:
        with psycopg.connect(database_url, connect_timeout=30, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("SET statement_timeout = 30000")
                cur.execute(query)
                row = cur.fetchone()
                if row is None:
                    return None
                payload = row.get("row_json")
                if not isinstance(payload, dict):
                    return None
                return _sample_row_from_db_row(payload, documented_columns or list(payload.keys()))
    except Exception as exc:
        logger.warning("Sample row fetch failed for %s.%s: %s", schema, table, exc)
        return None


def fetch_sample_rows_for_contract_tables(
    database_url: str | None,
    *,
    documented_columns_by_fq: dict[str, list[str]],
) -> tuple[dict[str, dict[str, Any] | None], str | None]:
    """First row per contract table (documented columns only). Returns (samples, source note)."""

    from app.services.catalog_sqlite import is_sqlite_catalog_url
    from app.services.investor_schema_contract import INVESTOR_CONTRACT_TABLES

    if not database_url:
        return {}, "database_url not configured"

    samples: dict[str, dict[str, Any] | None] = {}
    use_sqlite = is_sqlite_catalog_url(database_url)
    source = "sqlite_mirror" if use_sqlite else "postgresql"

    for schema, table in INVESTOR_CONTRACT_TABLES:
        fq = f"{schema}.{table}"
        doc_cols = documented_columns_by_fq.get(fq, [])
        if use_sqlite:
            samples[fq] = _fetch_sqlite_sample(database_url, schema, table, doc_cols)
        else:
            samples[fq] = _fetch_postgres_sample(database_url, schema, table, doc_cols)

    return samples, source


def build_schema_guide(
    contract: dict[str, Any],
    *,
    filter_catalog: dict[str, Any] | None = None,
    database_url: str | None = None,
) -> dict[str, Any]:
    """Build compact guide dict from full PostgreSQL schema contract."""

    catalog_refs = _parse_catalog_column_refs(filter_catalog)
    tables_out: list[dict[str, Any]] = []
    documented_columns_by_fq: dict[str, list[str]] = {}
    for t in contract.get("tables") or []:
        fq = str(t.get("fully_qualified") or "")
        cols = _pick_columns(t, catalog_refs)
        documented_columns_by_fq[fq] = [c["name"] for c in cols]
        total = len(t.get("columns") or [])
        tables_out.append(
            {
                "fully_qualified": fq,
                "purpose": TABLE_NARRATIVES.get(fq, f"Warehouse table {fq}."),
                "partition_key_def": t.get("partition_key_def"),
                "primary_key_columns": t.get("primary_key_columns") or [],
                "foreign_keys": [
                    {
                        "column": fk.get("column_name"),
                        "references": (
                            f"{fk.get('foreign_table_schema')}.{fk.get('foreign_table_name')}"
                            f".{fk.get('foreign_column_name')}"
                        ),
                    }
                    for fk in (t.get("foreign_keys") or [])
                ],
                "column_count_total": total,
                "columns_documented": len(cols),
                "columns_omitted": max(0, total - len(cols)),
                "columns": cols,
                "sample_row": None,
                "sample_row_note": None,
            }
        )

    sample_rows, sample_source = fetch_sample_rows_for_contract_tables(
        database_url,
        documented_columns_by_fq=documented_columns_by_fq,
    )
    samples_attached = 0
    for entry in tables_out:
        fq = entry["fully_qualified"]
        sample = sample_rows.get(fq)
        if sample:
            entry["sample_row"] = sample
            samples_attached += 1
        elif database_url:
            entry["sample_row_note"] = "No row returned (empty table or fetch failed)."

    guide: dict[str, Any] = {
        "contract_kind": "investor_schema_guide",
        "source_contract_kind": contract.get("contract_kind"),
        "source_generated_at": contract.get("generated_at"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sample_rows_source": sample_source,
        "sample_rows_attached": samples_attached,
        "purpose": (
            "Compact natural-language schema for LLM read-only SQL generation. "
            "Each table includes a sample_row (first DB record, documented columns only) "
            "so you can see value formats. Only documented columns may be referenced in SQL."
        ),
        "sql_rules": {
            "read_only": "Single SELECT or WITH…SELECT; LIMIT <= 500.",
            "parameters": "Use %s placeholders only; first parameter is session_arn.",
            "arn_scope": "Always filter via public.distributor_investor_mapping.arn_code = %s.",
            "identifiers": "Use only tables/columns listed under tables[].columns in this guide.",
            "joins": "Prefer join_recipes; match folio_no/folio_number and sch_code/scheme_cd consistently.",
            "advanced": (
                "Use EXISTS subqueries for holdings/activity/SIP filters; "
                "AGE(dob) for age; ILIKE for city; aggregate HAVING for unit balances."
            ),
            "investor_row_dedup": (
                "One row per investor (i.uuid): SELECT DISTINCT ON (i.uuid) i.uuid, … ORDER BY i.uuid, "
                "or GROUP BY i.uuid for aggregates; mapping table is per-folio."
            ),
            "investor_name_search": (
                "Name ILIKE on lower(replace(trim(concat_ws(' ', coalesce(first_name,''), coalesce(last_name,''))), "
                "' ', '')) with lowercase space-stripped %pattern% parameter; never split first/last equality."
            ),
        },
        "join_recipes": JOIN_RECIPES,
        "tables": tables_out,
        "table_count": len(tables_out),
    }
    return enrich_investor_schema_guide(guide)


def guide_to_markdown(guide: dict[str, Any]) -> str:
    lines = [
        "# Investor warehouse schema guide",
        "",
        f"Generated: {guide.get('generated_at', '')}",
        f"Source contract: {guide.get('source_generated_at', '')}",
        "",
        guide.get("purpose", ""),
        "",
        "## SQL rules",
        "",
    ]
    rules = guide.get("sql_rules") or {}
    for k, v in rules.items():
        lines.append(f"- **{k}**: {v}")
    lines.extend(["", "## Join recipes", ""])
    for jr in guide.get("join_recipes") or []:
        lines.append(f"### {jr.get('name')}")
        lines.append(jr.get("description", ""))
        lines.append(f"```sql\n{jr.get('sql_pattern', '')}\n```")
        lines.append("")
    vocab = guide.get("filter_vocabulary")
    if isinstance(vocab, dict) and vocab:
        lines.extend(["## Filter vocabulary", ""])
        lines.append("```json")
        lines.append(json.dumps(vocab, indent=2, ensure_ascii=False, default=str))
        lines.append("```")
        lines.append("")
    patterns = guide.get("question_patterns")
    if isinstance(patterns, list) and patterns:
        lines.extend(["## Question patterns (NL → SQL)", ""])
        for qp in patterns:
            if not isinstance(qp, dict):
                continue
            lines.append(f"### {qp.get('id', 'pattern')}")
            examples = qp.get("user_examples") or []
            if examples:
                lines.append("**Examples:** " + "; ".join(str(e) for e in examples[:4]))
            for hint in qp.get("sql_hints") or []:
                lines.append(f"- {hint}")
            sk = qp.get("sql_skeleton")
            if sk:
                lines.append("")
                lines.append("```sql")
                lines.append(str(sk).strip())
                lines.append("```")
            lines.append("")
    lines.extend(["## Tables", ""])
    for t in guide.get("tables") or []:
        fq = t.get("fully_qualified")
        lines.append(f"### `{fq}`")
        lines.append(t.get("purpose", ""))
        if t.get("columns_omitted"):
            lines.append(
                f"*(Showing {t.get('columns_documented')} of {t.get('column_count_total')} columns.)*"
            )
        lines.append("")
        lines.append("| Column | Type | Nullable | Description |")
        lines.append("|--------|------|----------|-------------|")
        for c in t.get("columns") or []:
            lines.append(
                f"| `{c.get('name')}` | {c.get('type')} | {c.get('nullable')} | {c.get('description')} |"
            )
        if t.get("sample_row"):
            lines.append("")
            lines.append("**Sample row (first record, documented columns):**")
            lines.append("")
            lines.append("```json")
            lines.append(json.dumps(t["sample_row"], indent=2, ensure_ascii=False, default=str))
            lines.append("```")
        elif t.get("sample_row_note"):
            lines.append("")
            lines.append(f"*{t['sample_row_note']}*")
        lines.append("")
    return "\n".join(lines)


def write_schema_guide_files(
    contract: dict[str, Any],
    *,
    filter_catalog: dict[str, Any] | None = None,
    database_url: str | None = None,
    json_path: Path | None = None,
    md_path: Path | None = None,
) -> tuple[Path, Path]:
    guide = build_schema_guide(
        contract,
        filter_catalog=filter_catalog,
        database_url=database_url,
    )
    jp = json_path or GUIDE_JSON_PATH
    mp = md_path or GUIDE_MD_PATH
    jp.parent.mkdir(parents=True, exist_ok=True)
    jp.write_text(json.dumps(guide, indent=2, ensure_ascii=False), encoding="utf-8")
    mp.write_text(guide_to_markdown(guide), encoding="utf-8")
    return jp, mp


@lru_cache(maxsize=1)
def load_schema_guide() -> dict[str, Any] | None:
    path = GUIDE_JSON_PATH
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return enrich_investor_schema_guide(raw)


def schema_guide_for_sql_generator(
    filter_catalog: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Guide for LLM prompts: load committed JSON or build from packaged contract."""

    guide = load_schema_guide()
    if guide and guide.get("contract_kind") == "investor_schema_guide":
        return guide
    from app.services.investor_schema_contract import load_packaged_schema_contract

    contract = load_packaged_schema_contract()
    if not contract:
        return None
    return build_schema_guide(contract, filter_catalog=filter_catalog)


def slim_schema_guide_for_prompt(guide: dict[str, Any]) -> dict[str, Any]:
    """Drop sample rows and metadata bloat before sending the monolithic guide to the LLM."""

    out = {k: v for k, v in guide.items() if k != "tables"}
    tables = []
    for table in guide.get("tables") or []:
        if not isinstance(table, dict):
            continue
        tables.append(
            {
                "fully_qualified": table.get("fully_qualified"),
                "purpose": table.get("purpose"),
                "columns": [
                    {
                        "name": c.get("name"),
                        "type": c.get("type"),
                        "description": c.get("description"),
                    }
                    for c in table.get("columns") or []
                    if isinstance(c, dict)
                ],
            }
        )
    out["tables"] = tables
    return out


def serialize_schema_guide_for_prompt(guide: dict[str, Any], max_chars: int) -> str:
    if guide.get("payload_kind") == "modular_sections":
        payload = guide
    else:
        payload = slim_schema_guide_for_prompt(guide)
    raw = json.dumps(payload, ensure_ascii=True, default=str)
    if len(raw) <= max_chars:
        return raw
    return raw[: max_chars - 80] + "\n...(investor_schema_guide_json truncated for prompt size)\n"
