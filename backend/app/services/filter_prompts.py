"""Build LLM system prompts from the filter catalog (single source of truth)."""

from __future__ import annotations

from app.agents.instructions import (
    BUILD_SEARCH_PLAN_BASE_PROMPT,
    DETECT_INTENT_BASE_PROMPT,
    ROOT_AGENT_BASE_INSTRUCTION,
)
from app.core.config import get_config
from app.services.filter_catalog import get_filter_catalog

SOURCE_OF_TRUTH_NOTICE = """
FILTER CATALOG (source of truth):
All allowed filter parameter values below come from the centralized filter catalog
(backend/app/data/filter_catalog.json, refreshed from DB + contract). Use ONLY these
values when mapping user text to filters or JSON fields. If a value is not listed,
treat it as out of scope or map to ALL/null as appropriate. When new filters or values
are added to the catalog, they apply automatically — do not invent values.
""".strip()


def build_root_agent_instruction() -> str:
    catalog = get_filter_catalog()
    durations = catalog.format_values_list("activity_duration")
    dynamic_block = ""
    if get_config().dynamic_investor_sql_enabled:
        dynamic_block = """
## Dynamic read-only SQL (enabled on this deployment)
The tool ``run_dynamic_investor_sql_tool`` runs a **guarded** LLM + ReAct loop that generates
read-only ``SELECT``/``WITH`` SQL from the live **investor schema contract** (joins, partition hints, ARN scope).
You must still call ``detect_intent_tool`` first on every turn.
Use ``run_dynamic_investor_sql_tool`` only when ``current_intent`` is ``investor_search`` and the user needs
**ad-hoc analytics** (counts, sums, joins across contract tables) that the standard filter search cannot express.
For normal list or catalog-filter searches, use ``analyze_search_arguments_tool`` + ``search_investors_tool``,
or ``search_investors_tool`` alone when ``has_search_filters`` is false.
Never show generated SQL or raw parameters in the final reply to the user.
""".strip()
    parts = [
        ROOT_AGENT_BASE_INSTRUCTION.strip(),
        dynamic_block,
        SOURCE_OF_TRUTH_NOTICE,
        f"Supported activity duration values (from catalog): {durations}.",
    ]
    return "\n\n".join(p for p in parts if p)


def build_detect_intent_system_prompt() -> str:
    catalog = get_filter_catalog()
    return (
        f"{DETECT_INTENT_BASE_PROMPT.strip()}\n\n"
        f"{SOURCE_OF_TRUTH_NOTICE}\n\n"
        f"{catalog.prompt_intent_filter_reference()}"
    )


def build_search_plan_system_prompt() -> str:
    catalog = get_filter_catalog()
    schema_notice = """
Optional SCHEMA CONTEXT in the user JSON:
If the payload includes "investor_db_schema_compact", it lists real PostgreSQL tables and
columns (names and types) for the distributor investor warehouse. The backend refreshes
this snapshot **once per ADK session** the first time a search plan is built (and skips
later introspection for that session).

Use the snapshot only to ground unsupported_reasons or filter choices when the user asks
for something tied to real columns that are not in the MVP filter catalog.

You must still return ONLY the SearchPlan JSON object defined in the schema appendix below.
Never return SQL, DDL, or multi-statement scripts.
""".strip()
    return (
        f"{BUILD_SEARCH_PLAN_BASE_PROMPT.strip()}\n\n"
        f"{SOURCE_OF_TRUTH_NOTICE}\n\n"
        f"{schema_notice}\n\n"
        f"{catalog.prompt_search_plan_filter_values()}\n\n"
        f"{catalog.prompt_search_plan_json_schema()}"
    )
