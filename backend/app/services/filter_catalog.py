"""Centralized allowed values for investor-search filters."""

from __future__ import annotations

import json
import logging
import os
from copy import deepcopy
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.db.postgres import DatabaseNotConfiguredError, PostgresClient
from app.services.catalog_sqlite import (
    SQLITE_CATALOG_FILTER_QUERIES,
    fetch_all_sqlite,
    is_sqlite_catalog_url,
)
from app.models.agent_state import (
    STATE_KEY_FILTER_CATALOG_SESSION_FETCHED,
    STATE_KEY_FILTER_CATALOG_SNAPSHOT,
)
from app.models.search_plan import (
    ActivityType,
    ALLOWED_DURATIONS,
    BinaryFilter,
    DEFAULT_ACTIVITY_TYPES,
    DEFAULT_OPTIONS,
    DEFAULT_SYSTEMATIC_PLANS,
    EligibilityFilter,
    IndividualOtmFilter,
    InvestorSubtype,
    InvestorTab,
    InvestorTypeFilter,
    NonIndividualOtmFilter,
    SystematicPlanType,
)

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG_PATH = BACKEND_DIR / "app" / "data" / "filter_catalog.default.json"
GENERATED_CATALOG_PATH = BACKEND_DIR / "app" / "data" / "filter_catalog.json"

# Read-only queries; each returns rows: {"value": ...}
DB_FILTER_QUERIES: dict[str, str] = {
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
        FROM sphmf.scheme_setup
        WHERE cgf_flag IS NOT NULL
        ORDER BY cgf_flag ASC
    """,
    "minor_inv_types": """
        SELECT DISTINCT cm.inv_type AS value
        FROM sphmf.customer_master cm
        INNER JOIN tax_status ts ON cm.inv_type = ts.inv_type_code
        WHERE ts.minor_flag = 'Y'
          AND ts.distributor_flag = 'Y'
          AND ts.active_flag = 'Y'
        ORDER BY cm.inv_type ASC
    """,
    "transaction_type_codes": """
        SELECT DISTINCT tt.trxntypcod AS value
        FROM sphmf.transaction_types tt
        WHERE tt.trxntypcod IS NOT NULL
        ORDER BY tt.trxntypcod ASC
        LIMIT 200
    """,
}


def _contract_catalog() -> dict[str, Any]:
    """Build catalog entries from code enums (no DB required)."""

    def entry(values: list[str], parameter: str, source: str = "contract") -> dict[str, Any]:
        return {"values": values, "parameter": parameter, "source": source}

    return {
        "version": 1,
        "source": "contract",
        "loaded_at": None,
        "filters": {
            "investor_tab": entry(
                [tab.value for tab in InvestorTab if tab != InvestorTab.PENDING],
                "investor_tab",
            ),
            "eligibility": entry([e.value for e in EligibilityFilter], "individual_warehouse.eligibility"),
            "individual_otm": entry([e.value for e in IndividualOtmFilter], "individual_warehouse.otm"),
            "non_individual_otm": entry([e.value for e in NonIndividualOtmFilter], "non_individual_sql.otm"),
            "investor_type": entry([e.value for e in InvestorTypeFilter], "individual_warehouse.investor_type"),
            "investor_subtypes": entry([e.value for e in InvestorSubtype], "individual_warehouse.investor_subtypes"),
            "city": entry([], "sphmf.customer_master.city"),
            "investor_age_years": entry([], "public.investor.dob (age in full years via AGE)"),
            "holding_mode": entry([e.value for e in BinaryFilter], "current_holdings.is_holding"),
            "systematic_mode": entry([e.value for e in BinaryFilter], "systematic_plan.is_active"),
            "systematic_plans": entry(
                [plan.value for plan in SystematicPlanType],
                "systematic_plan.plan",
            ),
            "activity_mode": entry([e.value for e in BinaryFilter], "investor_activity.have"),
            "activity_types": entry(list(DEFAULT_ACTIVITY_TYPES), "investor_activity.activity_type"),
            "activity_duration": entry(sorted(ALLOWED_DURATIONS), "investor_activity.duration"),
            "inv_options": entry(["ALL", *DEFAULT_OPTIONS], "row.inv_options"),
            "scheme_codes": entry(["ALL"], "holding|systematic|activity.schemes"),
            "sort_key": entry(["first_name", "pan_number", "dob"], "sortkey"),
            "sort_order": entry(["ASC", "DESC"], "sortvalue"),
        },
    }


def _merge_db_values(catalog: dict[str, Any], db_key: str, filter_key: str, rows: list[dict[str, Any]]) -> None:
    values = sorted({str(row["value"]).strip() for row in rows if row.get("value") is not None})
    if not values:
        return
    filters = catalog.setdefault("filters", {})
    existing = filters.get(filter_key, {})
    merged = ["ALL", *values] if filter_key == "scheme_codes" else values
    filters[filter_key] = {
        **existing,
        "values": merged,
        "source": "db",
        "db_query_key": db_key,
        "db_count": len(values),
    }


# Maps catalog filter_key -> SearchPlanLLMOutput JSON field name.
SEARCH_PLAN_JSON_FIELDS: dict[str, str] = {
    "investor_tab": "investor_tab",
    "eligibility": "eligibility",
    "individual_otm": "individual_otm",
    "non_individual_otm": "non_individual_otm",
    "investor_type": "investor_type",
    "investor_subtypes": "investor_subtypes",
    "city": "city",
    "holding_mode": "holding_mode",
    "systematic_mode": "systematic_mode",
    "systematic_plans": "systematic_plans",
    "activity_mode": "activity_mode",
    "activity_types": "activity_types",
    "activity_duration": "activity_duration",
}

# Filter keys surfaced in intent-detection (routing) prompts.
INTENT_FILTER_KEYS: tuple[str, ...] = (
    "investor_tab",
    "eligibility",
    "individual_otm",
    "non_individual_otm",
    "investor_type",
    "investor_subtypes",
    "city",
    "holding_mode",
    "systematic_mode",
    "systematic_plans",
    "activity_mode",
    "activity_types",
    "activity_duration",
    "scheme_codes",
)

# Default cap for *optional* short previews (e.g. root-agent one-liners). Intent and
# search-plan prompts pass max_items=None so the full catalog lists are not truncated.
_PROMPT_INLINE_LIMIT = 40

# Hard cap for embedding the entire catalog JSON in a single system message (characters).
_FULL_CATALOG_JSON_CHAR_CAP = 250_000


class FilterCatalog:
    """Load and query the centralized filter value store."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    @property
    def loaded_at(self) -> str | None:
        return self._data.get("loaded_at")

    @property
    def source(self) -> str:
        return str(self._data.get("source", "unknown"))

    def get_entry(self, filter_key: str) -> dict[str, Any]:
        return dict(self._data.get("filters", {}).get(filter_key, {}))

    def get_values(self, filter_key: str) -> list[str]:
        return list(self.get_entry(filter_key).get("values", []))

    def allows(self, filter_key: str, value: str | None) -> bool:
        if value is None:
            return True
        allowed = set(self.get_values(filter_key))
        return not allowed or value in allowed

    def allows_many(self, filter_key: str, values: list[str]) -> bool:
        return all(self.allows(filter_key, value) for value in values)

    def to_dict(self) -> dict[str, Any]:
        return deepcopy(self._data)

    def format_value_union(self, filter_key: str) -> str:
        """SQL-style union string for prompts: \"A\" | \"B\"."""

        values = self.get_values(filter_key)
        if not values:
            return "string"
        return " | ".join(f'"{value}"' for value in values)

    def format_values_list(self, filter_key: str, *, max_items: int | None = _PROMPT_INLINE_LIMIT) -> str:
        values = self.get_values(filter_key)
        if not values:
            return "(none configured)"
        if max_items is None or len(values) <= max_items:
            return ", ".join(f'"{v}"' for v in values)
        shown = ", ".join(f'"{v}"' for v in values[:max_items])
        return f"{shown}, ... ({len(values)} total in catalog)"

    def format_json_array_values(self, filter_key: str, *, max_items: int | None = _PROMPT_INLINE_LIMIT) -> str:
        values = self.get_values(filter_key)
        if not values:
            return "[]"
        if max_items is None or len(values) <= max_items:
            return json.dumps(values)
        preview = json.dumps(values[:max_items])
        return f"{preview[:-1]}, ...] ({len(values)} codes in catalog; use ALL or listed codes only)"

    def prompt_summary(self) -> str:
        """Compact list for debugging or short appendices."""

        lines = ["Catalog filter keys and allowed values (preview):"]
        for key in sorted(self._data.get("filters", {})):
            entry = self.get_entry(key)
            values = entry.get("values", [])
            preview = ", ".join(str(v) for v in values[:12])
            suffix = "..." if len(values) > 12 else ""
            source = entry.get("source", "?")
            param = entry.get("parameter", "")
            param_note = f" -> {param}" if param else ""
            lines.append(f"- {key}{param_note} ({source}): {preview}{suffix}")
        return "\n".join(lines)

    def prompt_search_plan_filter_values(self) -> str:
        """Per-filter allowed values for the search-plan LLM (full lists, no truncation)."""

        lines = ["## Allowed parameter values per filter (catalog)"]
        for key, json_field in SEARCH_PLAN_JSON_FIELDS.items():
            entry = self.get_entry(key)
            parameter = entry.get("parameter", "")
            param_note = f" (maps to JSON `{json_field}`" + (f", DB/engine: {parameter})" if parameter else ")")
            if key == "scheme_codes":
                count = len(self.get_values(key))
                lines.append(
                    f"- scheme_codes{param_note}: use \"ALL\" or a scheme code from catalog "
                    f"({count} codes). Do not invent scheme codes."
                )
                continue
            if key in {"systematic_plans", "activity_types", "investor_subtypes"}:
                lines.append(
                    f"- {key}{param_note}: [] or subset of {self.format_json_array_values(key, max_items=None)}"
                )
            else:
                lines.append(f"- {key}{param_note}: {self.format_value_union(key)}")
        extra_keys = sorted(
            k for k in self._data.get("filters", {}) if k not in SEARCH_PLAN_JSON_FIELDS
        )
        if extra_keys:
            lines.append("\n### Additional catalog dimensions (metadata / future JSON fields)")
            for key in extra_keys:
                entry = self.get_entry(key)
                parameter = entry.get("parameter", "")
                param_note = f" ({parameter})" if parameter else ""
                vals = self.get_values(key)
                if len(vals) > 200:
                    lines.append(
                        f"- {key}{param_note}: {len(vals)} values — see **Complete filter catalog (JSON)** below."
                    )
                else:
                    lines.append(f"- {key}{param_note}: {self.format_values_list(key, max_items=None)}")
        return "\n".join(lines)

    def prompt_search_plan_json_schema(self) -> str:
        """Return JSON schema fragment with unions from catalog."""

        lines = ["Return JSON exactly (no extra keys). Allowed types per field:"]
        lines.append("{")
        for key, json_field in SEARCH_PLAN_JSON_FIELDS.items():
            if key in {"systematic_plans", "activity_types", "investor_subtypes"}:
                lines.append(f'  "{json_field}": array of catalog {key} values,')
            elif key == "activity_duration":
                lines.append(f'  "{json_field}": {self.format_value_union(key)},')
            else:
                lines.append(f'  "{json_field}": {self.format_value_union(key)},')
        lines.append('  "normalized_query": string,')
        lines.append('  "name_search": string or null,')
        lines.append('  "age_min": integer (full years from public.investor.dob) or null,')
        lines.append('  "age_max": integer (full years from public.investor.dob) or null,')
        lines.append('  "unsupported_reasons": [string]')
        lines.append("}")
        return "\n".join(lines)

    def prompt_intent_filter_reference(self) -> str:
        """Filter dimensions for intent/routing LLM (full lists for known keys)."""

        lines = ["## Recognized search filter dimensions (catalog keys)"]
        for key in INTENT_FILTER_KEYS:
            entry = self.get_entry(key)
            parameter = entry.get("parameter", "")
            param_note = f" ({parameter})" if parameter else ""
            lines.append(f"- {key}{param_note}: {self.format_values_list(key, max_items=None)}")
        extra = sorted(k for k in self._data.get("filters", {}) if k not in INTENT_FILTER_KEYS)
        if extra:
            lines.append("\n### Other catalog keys (see full JSON appendix for values)")
            lines.append(", ".join(extra))
        lines.append(
            "\nWhen has_search_filters=true, detected_filters labels should reference "
            "these catalog keys (e.g. eligibility=YES, systematic_plans=SIP)."
        )
        return "\n".join(lines)

    def prompt_full_catalog_json(self, max_chars: int | None = None) -> str:
        """Serialize the entire loaded catalog for LLM grounding (bounded size)."""

        cap = max_chars if max_chars is not None else _FULL_CATALOG_JSON_CHAR_CAP
        raw = json.dumps(self._data, ensure_ascii=True, indent=2, default=str)
        if len(raw) <= cap:
            return raw
        head = raw[: cap - 120]
        return head + "\n…(catalog JSON truncated for prompt size; filters above list the critical keys)\n"


def load_catalog_from_file(path: Path | None = None) -> FilterCatalog:
    path = path or _resolve_catalog_path()
    if path.exists():
        with path.open(encoding="utf-8") as handle:
            return FilterCatalog(json.load(handle))
    logger.warning("Filter catalog file missing at %s; using contract defaults.", path)
    return FilterCatalog(_contract_catalog())


def _resolve_catalog_path() -> Path:
    try:
        from app.core.config import get_config

        configured = getattr(get_config(), "filter_catalog_path", None)
        if configured:
            return Path(configured)
    except Exception:
        pass
    if GENERATED_CATALOG_PATH.exists():
        return GENERATED_CATALOG_PATH
    return DEFAULT_CATALOG_PATH


def refresh_catalog_from_db(
    database_url: str | None,
    statement_timeout_ms: int = 30000,
    output_path: Path | None = None,
) -> FilterCatalog:
    """Run DB discovery queries and write the merged catalog JSON."""

    catalog = _contract_catalog()
    catalog["loaded_at"] = datetime.now(timezone.utc).isoformat()

    if not database_url:
        logger.warning("No database URL; saving contract-only catalog.")
        catalog["source"] = "contract"
        _write_catalog(catalog, output_path)
        return FilterCatalog(catalog)

    catalog["source"] = "sqlite+contract" if is_sqlite_catalog_url(database_url) else "db+contract"

    if is_sqlite_catalog_url(database_url):
        for db_key, sql in SQLITE_CATALOG_FILTER_QUERIES.items():
            try:
                rows = fetch_all_sqlite(database_url, sql)
                filter_key = _db_key_to_filter_key(db_key)
                if filter_key:
                    _merge_db_values(catalog, db_key, filter_key, rows)
                else:
                    catalog.setdefault("db_metadata", {})[db_key] = [
                        str(row.get("value")) for row in rows if row.get("value") is not None
                    ]
            except Exception as exc:
                logger.warning("Filter catalog SQLite query %s failed: %s", db_key, exc)
                catalog.setdefault("db_errors", {})[db_key] = str(exc)
    else:
        db = PostgresClient(database_url, statement_timeout_ms, min_size=1, max_size=1)
        try:
            db.open()
            for db_key, sql in DB_FILTER_QUERIES.items():
                try:
                    rows = db.fetch_all(sql)
                    filter_key = _db_key_to_filter_key(db_key)
                    if filter_key:
                        _merge_db_values(catalog, db_key, filter_key, rows)
                    else:
                        catalog.setdefault("db_metadata", {})[db_key] = [
                            str(row.get("value")) for row in rows if row.get("value") is not None
                        ]
                except Exception as exc:
                    logger.warning("Filter catalog query %s failed: %s", db_key, exc)
                    catalog.setdefault("db_errors", {})[db_key] = str(exc)
        except DatabaseNotConfiguredError:
            logger.warning("Database not configured; saving contract-only catalog.")
        finally:
            db.close()

    _write_catalog(catalog, output_path)
    return FilterCatalog(catalog)


def clear_filter_catalog_session_cache(session_state: dict[str, Any]) -> None:
    """Drop session-scoped filter catalog so the next search turn reloads from DB/file."""

    session_state.pop(STATE_KEY_FILTER_CATALOG_SESSION_FETCHED, None)
    session_state.pop(STATE_KEY_FILTER_CATALOG_SNAPSHOT, None)


def ensure_filter_catalog_snapshot_for_session(
    session_state: dict[str, Any],
    database_url: str | None,
) -> None:
    """Once per session: merge filter catalog (DB + contract when URL set) and cache in state."""

    if session_state.get(STATE_KEY_FILTER_CATALOG_SESSION_FETCHED):
        return

    if os.environ.get("PYTEST_CURRENT_TEST"):
        catalog = load_catalog_from_file()
        session_state[STATE_KEY_FILTER_CATALOG_SNAPSHOT] = catalog.to_dict()
        session_state[STATE_KEY_FILTER_CATALOG_SESSION_FETCHED] = True
        return

    if database_url:
        try:
            catalog = refresh_catalog_from_db(database_url)
        except Exception as exc:
            logger.warning("Session filter catalog DB refresh failed; using JSON file: %s", exc)
            catalog = load_catalog_from_file()
    else:
        catalog = load_catalog_from_file()

    session_state[STATE_KEY_FILTER_CATALOG_SNAPSHOT] = catalog.to_dict()
    session_state[STATE_KEY_FILTER_CATALOG_SESSION_FETCHED] = True


def get_filter_catalog_for_session(session_state: dict[str, Any] | None) -> FilterCatalog:
    """Prefer the session snapshot built by ``ensure_filter_catalog_snapshot_for_session``."""

    if session_state and session_state.get(STATE_KEY_FILTER_CATALOG_SESSION_FETCHED):
        snap = session_state.get(STATE_KEY_FILTER_CATALOG_SNAPSHOT)
        if isinstance(snap, dict) and isinstance(snap.get("filters"), dict):
            return FilterCatalog(snap)
    return get_filter_catalog()


def _db_key_to_filter_key(db_key: str) -> str | None:
    mapping = {
        "scheme_codes": "scheme_codes",
    }
    return mapping.get(db_key)


def _write_catalog(catalog: dict[str, Any], output_path: Path | None) -> None:
    path = output_path or GENERATED_CATALOG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(catalog, handle, indent=2, ensure_ascii=True)
        handle.write("\n")


@lru_cache
def get_filter_catalog() -> FilterCatalog:
    return load_catalog_from_file()


def reload_filter_catalog() -> FilterCatalog:
    get_filter_catalog.cache_clear()
    return get_filter_catalog()
