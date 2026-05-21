"""Compress investor schema contract JSON into a prompt-friendly digest."""

from __future__ import annotations

import json
from typing import Any

_MAX_CHARS = 95_000
_MAX_COLS_PER_TABLE = 60
_MAX_FK_PER_TABLE = 20


def summarize_contract_for_sql_prompt(schema_compact: dict[str, Any]) -> str:
    """Human-readable digest: PK, FK, partition defs, column name:type samples."""

    tables = schema_compact.get("tables") or []
    chunks: list[str] = []
    for t in tables:
        fq = t.get("fully_qualified") or f"{t.get('schema')}.{t.get('table')}"
        part = t.get("partition_key_def") or "none"
        pks = ", ".join(t.get("primary_key_columns") or []) or "—"
        fks = t.get("foreign_keys") or []
        fk_bits = []
        for fk in fks[:_MAX_FK_PER_TABLE]:
            fk_bits.append(
                f"{fk.get('column_name')} → {fk.get('foreign_table_schema')}."
                f"{fk.get('foreign_table_name')}.{fk.get('foreign_column_name')}"
            )
        fk_s = "; ".join(fk_bits) or "—"
        cols = t.get("columns") or []
        col_bits = [f"{c.get('name')}:{c.get('data_type')}" for c in cols[:_MAX_COLS_PER_TABLE]]
        col_s = ", ".join(col_bits)
        if len(cols) > _MAX_COLS_PER_TABLE:
            col_s += f", …(+{len(cols) - _MAX_COLS_PER_TABLE} more)"
        chunks.append(
            f"### {fq}\n"
            f"- partition: {part}\n"
            f"- PK: {pks}\n"
            f"- FK: {fk_s}\n"
            f"- columns: {col_s}"
        )
    text = "\n\n".join(chunks)
    if len(text) <= _MAX_CHARS:
        return text
    return text[: _MAX_CHARS - 80] + "\n\n…(digest truncated; prefer narrower questions)\n"


def schema_compact_json_excerpt(schema_compact: dict[str, Any], max_chars: int = 24_000) -> str:
    """Optional JSON fallback slice for the model (bounded size)."""

    raw = json.dumps(schema_compact, default=str)
    if len(raw) <= max_chars:
        return raw
    return raw[: max_chars - 60] + "…(json excerpt truncated)"
