"""Development-only Individual search execution against ``DEV_LOCAL_SQLITE_MIRROR``.

The warehouse SQL builder targets PostgreSQL. When ``DEV_INVESTOR_SEARCH_USE_SQLITE`` is
true (development only), the default **unfiltered** Individual list runs as a small
SQLite query against tables produced by ``scripts/sync_filter_catalog_sqlite.py``
(``public_*`` / ``sphmf_*`` physical names).
"""

from __future__ import annotations

import sqlite3
from typing import Any

from app.core.config import AppConfig
from app.models.search_plan import (
    ActivityFilter,
    BinaryFilter,
    EligibilityFilter,
    HoldingFilter,
    IndividualOtmFilter,
    InvestorTab,
    InvestorTypeFilter,
    SearchPlan,
    SystematicFilter,
)
from app.services.catalog_sqlite import sqlite_connect_path


def plan_supported_on_sqlite_dev_mirror(plan: SearchPlan) -> bool:
    """True only for the default Individual menu (no extra dimensions)."""

    if plan.investor_tab != InvestorTab.INDIVIDUAL:
        return False
    if plan.unsupported_reasons:
        return False
    if plan.name_search and str(plan.name_search).strip():
        return False
    if plan.city and str(plan.city).strip():
        return False
    if plan.age_min is not None or plan.age_max is not None:
        return False
    if plan.eligibility != EligibilityFilter.ALL:
        return False
    if plan.individual_otm != IndividualOtmFilter.ALL:
        return False
    if plan.investor_type != InvestorTypeFilter.ALL:
        return False
    if plan.investor_subtypes:
        return False
    if not _is_default_holding(plan.holding):
        return False
    if not _is_default_systematic(plan.systematic):
        return False
    if not _is_default_activity(plan.activity):
        return False
    return True


def _is_default_holding(h: HoldingFilter) -> bool:
    return h.mode == BinaryFilter.ALL and (not h.schemes or h.schemes == ["ALL"])


def _is_default_systematic(s: SystematicFilter) -> bool:
    return s.mode == BinaryFilter.ALL


def _is_default_activity(a: ActivityFilter) -> bool:
    return a.mode == BinaryFilter.ALL


def build_sqlite_dev_list_sql(plan: SearchPlan, arn_code: str) -> tuple[str, list[Any]]:
    """SQLite shape for default list (matches row keys ``format_rows_for_chat`` reads)."""

    sql = """
WITH uuids AS (
    SELECT DISTINCT dim.investor_uuid
    FROM public_distributor_investor_mapping dim
    WHERE dim.arn_code = ?
)
SELECT DISTINCT
    CAST(i.uuid AS TEXT) AS uuid,
    TRIM(
        COALESCE(i.first_name, '') || ' ' ||
        COALESCE(i.middle_name, '') || ' ' ||
        COALESCE(i.last_name, '')
    ) AS first_name,
    i.pan_number,
    i.dob,
    i.email,
    i.mobile_number
FROM public_investor i
WHERE CAST(i.uuid AS TEXT) IN (SELECT investor_uuid FROM uuids)
ORDER BY first_name ASC
LIMIT ? OFFSET ?
"""
    params: list[Any] = [arn_code, plan.page_limit, plan.page_offset]
    return " ".join(sql.split()), params


def execute_individual_search_sqlite_dev(config: AppConfig, plan: SearchPlan, arn_code: str) -> list[dict[str, Any]]:
    """Run the default-list query on the local mirror file."""

    if not plan_supported_on_sqlite_dev_mirror(plan):
        raise ValueError("Search plan is not supported on the SQLite dev mirror.")
    url = config.dev_local_sqlite_mirror_file_url
    if not url:
        raise RuntimeError("DEV_LOCAL_SQLITE_MIRROR must point at an existing SQLite file.")
    path = sqlite_connect_path(url)
    sql, params = build_sqlite_dev_list_sql(plan, arn_code)
    conn = sqlite3.connect(str(path))
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()
