"""Build the root agent instruction (static prompt + optional catalog hints)."""

from __future__ import annotations

from app.agents.system_prompts import ROOT_AGENT_BASE_INSTRUCTION
from app.services.filter_catalog import get_filter_catalog_for_session

SOURCE_OF_TRUTH_NOTICE = """
FILTER CATALOG (source of truth):
The ``generate_catalog_sql_query_tool`` sends only ``investor_db_schema_guide.json`` plus the
user question (no live DB catalog merge). Age filters use ``public.investor.dob`` with ``AGE(dob)``;
city filters use ``sphmf.customer_master.city`` per guide join recipes — always call the tool for
these asks; do not claim age or location data is unavailable without a tool result.
When reasoning about filters in your replies to the user, treat catalog-backed semantics as
authoritative — do not invent filter values.
""".strip()


def build_root_agent_instruction() -> str:
    catalog = get_filter_catalog_for_session(None)
    durations = catalog.format_values_list("activity_duration")
    parts = [
        ROOT_AGENT_BASE_INSTRUCTION.strip(),
        SOURCE_OF_TRUTH_NOTICE,
        f"Reference: typical activity duration labels from catalog: {durations}.",
    ]
    return "\n\n".join(p for p in parts if p)
