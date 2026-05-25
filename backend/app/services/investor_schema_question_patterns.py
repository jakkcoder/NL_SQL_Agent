"""Curated NL→SQL patterns for ``investor_db_schema_guide.json`` (merged at load/build time)."""

from __future__ import annotations

from typing import Any

# sphmf.processed_trxns posting date (not l_trxn_date; that column is on customer_schemes).
PROCESSED_TRXN_DATE = "trxn_date"

# One chat row per investor when dim has multiple folios (PostgreSQL DISTINCT ON).
INVESTOR_DEDUP_ORDER = "ORDER BY i.uuid"
INVESTOR_DEDUP_HINT = (
    "Return one row per investor: SELECT DISTINCT ON (i.uuid) i.uuid, … then ORDER BY i.uuid "
    "(required). Do not emit one row per folio unless the user asks for folio detail."
)

# Flexible name match: concat first+last, trim, strip all spaces, lowercase, ILIKE %pattern%.
INVESTOR_FULL_NAME_NORM_SQL = (
    "lower(replace(trim(concat_ws(' ', coalesce(i.first_name, ''), coalesce(i.last_name, ''))), "
    "' ', ''))"
)
NAME_SEARCH_HINT = (
    "Name filters: match only on normalized full name — "
    f"{INVESTOR_FULL_NAME_NORM_SQL} ILIKE %s. "
    "Never filter with separate first_name = … AND last_name = … or first_name-only ILIKE. "
    "Bind one parameter: lowercase, remove all spaces from the user's name, wrap as %%token%% "
    "(e.g. 'Aparna Jha' → '%%aparnajha%%'; 'Bhavin' → '%%bhavin%%')."
)


def _investor_list_select(*extra_columns: str) -> str:
    """DISTINCT ON (i.uuid) list prefix for outer investor SELECTs."""

    cols = "i.uuid, i.first_name, i.last_name, i.email"
    if extra_columns:
        cols = f"{cols}, {', '.join(extra_columns)}"
    return f"SELECT DISTINCT ON (i.uuid) {cols}"

EQUITY_SCHEME_PREDICATE = (
    "(lower(sm.scheme_type) LIKE '%%equity%%' "
    "OR EXISTS (SELECT 1 FROM sphmf.scheme_setup ss "
    "WHERE ss.schcode = pt.sch_code AND lower(ss.asset_class) = 'equity'))"
)

LIQUID_SCHEME_PREDICATE = (
    "(lower(sm.scheme_type) LIKE '%%liquid%%' "
    "OR lower(sm.scheme_name) LIKE '%%liquid%%' "
    "OR EXISTS (SELECT 1 FROM sphmf.scheme_setup ss "
    "WHERE ss.schcode = pt.sch_code AND lower(ss.schname) LIKE '%%liquid%%'))"
)

# Extra join recipes beyond JOIN_RECIPES in schema_contract_guide.py
EXTRA_JOIN_RECIPES: list[dict[str, str]] = [
    {
        "name": "nri_tax_status",
        "description": "NRI / NRE investors via folio inv_type and tax_status.nri_nre.",
        "sql_pattern": (
            "sphmf.customer_master cm ON cm.folio_no = dim.folio_number "
            "JOIN public.tax_status ts ON cm.inv_type = ts.inv_type_code "
            "WHERE dim.arn_code = %s AND ts.nri_nre = 'Y'"
        ),
    },
    {
        "name": "redemption_activity",
        "description": "Redemption posted transactions in a date window (join transaction_types).",
        "sql_pattern": (
            "sphmf.processed_trxns pt ON pt.folio_no = dim.folio_number AND pt.broker_code = dim.arn_code "
            "JOIN sphmf.transaction_types tt ON pt.trxn_type_code = tt.trxntypcod "
            f"WHERE pt.trxn_subtype_code = 'N' AND tt.trxndbcr = 'R' "
            f"AND pt.{PROCESSED_TRXN_DATE} >= %s AND pt.{PROCESSED_TRXN_DATE} < %s"
        ),
    },
    {
        "name": "purchase_activity",
        "description": "Purchase posted transactions (for top-N / FY totals).",
        "sql_pattern": (
            "sphmf.processed_trxns pt ON pt.folio_no = dim.folio_number AND pt.broker_code = dim.arn_code "
            "JOIN sphmf.transaction_types tt ON pt.trxn_type_code = tt.trxntypcod "
            f"WHERE pt.trxn_subtype_code = 'N' AND tt.trxndbcr = 'P' "
            f"AND pt.{PROCESSED_TRXN_DATE} >= %s AND pt.{PROCESSED_TRXN_DATE} < %s"
        ),
    },
    {
        "name": "sip_amount_active",
        "description": "Active SIP rows with instalment amount (sipstp.amount) and scheme filter.",
        "sql_pattern": (
            "sphmf.sipstp s ON dim.folio_number = s.folio_no AND dim.arn_code = s.brok_code "
            "JOIN public.scheme_master sm ON s.sch_code = sm.scheme_cd "
            "WHERE s.cease_dt IS NULL AND (s.cancellation_request_date IS NULL) "
            "AND s.to_date > NOW() AND s.atrxn_type = 'P' AND s.amount >= %s"
        ),
    },
    {
        "name": "no_active_sip",
        "description": "Investors with no live SIP/STP row (NOT EXISTS active sipstp).",
        "sql_pattern": (
            "NOT EXISTS (SELECT 1 FROM sphmf.sipstp s "
            "WHERE s.folio_no = dim.folio_number AND s.brok_code = dim.arn_code "
            "AND s.cease_dt IS NULL AND (s.cancellation_request_date IS NULL) AND s.to_date > NOW())"
        ),
    },
]

FILTER_VOCABULARY: dict[str, Any] = {
    "arn_scope": "First parameter is always session_arn; every query uses distributor_investor_mapping.arn_code = %s.",
    "city_match": "lower(trim(cm.city::text)) ILIKE %s with value like '%mumbai%' (no leading % on user city token only).",
    "age_years": "EXTRACT(YEAR FROM AGE(CURRENT_DATE, i.dob))::int BETWEEN min AND max; require i.dob IS NOT NULL.",
    "activity": {
        "purchase": "pt.trxn_subtype_code = 'N' AND tt.trxndbcr = 'P'",
        "redemption": "pt.trxn_subtype_code = 'N' AND tt.trxndbcr = 'R'",
        "sip_posted": "pt.trxn_subtype_code = 'S' AND tt.trxndbcr = 'P'",
    },
    "sipstp_active": {
        "predicates": [
            "s.cease_dt IS NULL",
            "s.cancellation_request_date IS NULL",
            "s.to_date IS NOT NULL AND s.to_date > NOW()",
            "s.atrxn_type = 'P' for vanilla SIP (see systematic_plans in filter catalog)",
        ],
        "amount_column": "sphmf.sipstp.amount (numeric instalment; compare >= threshold for 'above 5000 per month')",
    },
    "processed_trxns_date": (
        f"Date windows on sphmf.processed_trxns use pt.{PROCESSED_TRXN_DATE} "
        "(not l_trxn_date; customer_schemes still uses cs.l_trxn_date)."
    ),
    "scheme_classification": {
        "equity": (
            "lower(sm.scheme_type) LIKE '%equity%' OR EXISTS on sphmf.scheme_setup "
            "(ss.schcode = pt.sch_code AND lower(ss.asset_class) = 'equity'); "
            "public.scheme_master has scheme_type/scheme_name only (no asset_class)."
        ),
        "hybrid": "lower(sm.scheme_type) LIKE '%hybrid%' OR lower(sm.scheme_type) LIKE '%balanced%'",
        "liquid_cash": (
            "lower(sm.scheme_type) LIKE '%liquid%' OR lower(sm.scheme_name) LIKE '%liquid%' "
            "OR lower(ss.schname) LIKE '%liquid%' via scheme_setup ss on pt.sch_code = ss.schcode"
        ),
        "cgf": "sch_code IN (SELECT schcode FROM sphmf.scheme_setup WHERE cgf_flag = 'C' AND plan_type <> 'D')",
    },
    "dormant_heuristics": {
        "no_recent_activity_days": 180,
        "sql": "MAX(DATE(cs.l_trxn_date)) from sphmf.customer_schemes cs for ARN folios; dormant if CURRENT_DATE - max_d >= 180",
        "zero_units": "SUM signed units from sphmf.processed_trxns (+ for trxn_sign '+', - for '-') grouped by folio+sch_code HAVING sum <= 0 or no rows",
    },
    "financial_year_fy25": {
        "india_fy": f"FY25 = 2025-04-01 inclusive to 2026-04-01 exclusive on pt.{PROCESSED_TRXN_DATE}",
        "note": "Adjust bounds if user names a different FY explicitly.",
    },
    "last_calendar_quarter": "date_trunc('quarter', CURRENT_DATE) - interval '3 months' as start, date_trunc('quarter', CURRENT_DATE) as end",
    "nri": "public.tax_status.nri_nre = 'Y' joined via sphmf.customer_master.inv_type = tax_status.inv_type_code",
    "minor": "tax_status.minor_flag = 'Y' AND tax_status.distributor_flag = 'Y' AND tax_status.active_flag = 'Y'",
    "name_search": (
        f"{INVESTOR_FULL_NAME_NORM_SQL} ILIKE %s — one %%pattern%% parameter: lowercase, all spaces "
        "stripped from the user's name (concat first+last in SQL, not separate column filters)."
    ),
    "investor_row_dedup": INVESTOR_DEDUP_HINT,
}

QUESTION_PATTERNS: list[dict[str, Any]] = [
    {
        "id": "city_mumbai",
        "user_examples": [
            "Show my investors in Mumbai",
            "investors from Mumbai location",
            "Mumbai investors",
        ],
        "tables": ["public.distributor_investor_mapping", "public.investor", "sphmf.customer_master"],
        "join_recipes": ["arn_scope_anchor", "investor_identity", "folio_kyc_city"],
        "sql_hints": [
            INVESTOR_DEDUP_HINT,
            "City filter: lower(trim(cm.city)) ILIKE '%mumbai%'; parameters after ARN: city pattern as %s.",
        ],
        "sql_skeleton": (
            "WITH arn_scope AS (SELECT dim.investor_uuid, dim.folio_number FROM "
            "public.distributor_investor_mapping dim WHERE dim.arn_code = %s) "
            f"{_investor_list_select('cm.city')} FROM arn_scope "
            "JOIN public.investor i ON i.uuid = arn_scope.investor_uuid "
            "JOIN sphmf.customer_master cm ON cm.folio_no = arn_scope.folio_number "
            f"WHERE lower(trim(cm.city::text)) ILIKE %s {INVESTOR_DEDUP_ORDER} LIMIT 500"
        ),
        "parameters_order": ["session_arn", "city_pattern e.g. %mumbai%"],
    },
    {
        "id": "age_range",
        "user_examples": ["Investor with Age between 30 and 40", "investors aged 30-40"],
        "tables": ["public.distributor_investor_mapping", "public.investor"],
        "join_recipes": ["arn_scope_anchor", "investor_identity"],
        "sql_hints": [
            INVESTOR_DEDUP_HINT,
            "Filter on public.investor.dob; use EXTRACT(YEAR FROM AGE(CURRENT_DATE, i.dob))::int BETWEEN %s AND %s.",
            "Age bounds are integers in parameters after session_arn (not inlined).",
        ],
        "sql_skeleton": (
            f"{_investor_list_select('i.dob', 'EXTRACT(YEAR FROM AGE(CURRENT_DATE, i.dob))::int AS age_years')} "
            "FROM public.distributor_investor_mapping dim "
            "JOIN public.investor i ON i.uuid = dim.investor_uuid "
            "WHERE dim.arn_code = %s AND i.dob IS NOT NULL "
            "AND EXTRACT(YEAR FROM AGE(CURRENT_DATE, i.dob))::int BETWEEN %s AND %s "
            f"{INVESTOR_DEDUP_ORDER} LIMIT 500"
        ),
        "parameters_order": ["session_arn", "age_min", "age_max"],
    },
    {
        "id": "redemption_equity_last_quarter",
        "user_examples": [
            "Investors who did redemption in last quarter for equity funds",
            "redemption last quarter equity",
        ],
        "tables": [
            "public.distributor_investor_mapping",
            "public.investor",
            "sphmf.processed_trxns",
            "sphmf.transaction_types",
            "public.scheme_master",
        ],
        "join_recipes": ["arn_scope_anchor", "redemption_activity"],
        "sql_hints": [
            "Use EXISTS on processed_trxns + transaction_types for redemption (trxndbcr='R', trxn_subtype_code='N').",
            "Date window: last completed calendar quarter (see filter_vocabulary.last_calendar_quarter).",
            "Equity: JOIN scheme_master sm ON pt.sch_code = sm.scheme_cd; use filter_vocabulary.scheme_classification.equity "
            "(scheme_type + optional scheme_setup.asset_class; do not use sm.asset_class).",
            "Scope pt.broker_code = session_arn.",
        ],
        "sql_skeleton": (
            f"{_investor_list_select()} FROM public.distributor_investor_mapping dim "
            "JOIN public.investor i ON i.uuid = dim.investor_uuid "
            "WHERE dim.arn_code = %s AND EXISTS ("
            "  SELECT 1 FROM sphmf.processed_trxns pt "
            "  JOIN sphmf.transaction_types tt ON pt.trxn_type_code = tt.trxntypcod "
            "  JOIN public.scheme_master sm ON pt.sch_code = sm.scheme_cd "
            "  WHERE pt.folio_no = dim.folio_number AND pt.broker_code = dim.arn_code "
            "  AND pt.trxn_subtype_code = 'N' AND tt.trxndbcr = 'R' "
            f"  AND pt.{PROCESSED_TRXN_DATE} >= %s AND pt.{PROCESSED_TRXN_DATE} < %s "
            f"  AND {EQUITY_SCHEME_PREDICATE}"
            f") {INVESTOR_DEDUP_ORDER} LIMIT 500"
        ),
        "parameters_order": ["session_arn", "quarter_start", "quarter_end"],
    },
    {
        "id": "investor_last_redemption_date",
        "user_examples": [
            "When was the last redemption for Aparna Jha",
            "last redemption date for investor named Bhavin",
            "show when investor last redeemed",
        ],
        "tables": [
            "public.distributor_investor_mapping",
            "public.investor",
            "sphmf.processed_trxns",
            "sphmf.transaction_types",
        ],
        "join_recipes": ["arn_scope_anchor", "redemption_activity"],
        "sql_hints": [
            NAME_SEARCH_HINT,
            "Return the investor row with last_redemption_date = MAX(pt.trxn_date) across all ARN folios.",
            "Use LEFT JOIN on aggregated redemptions so the investor still appears when no redemption exists (NULL date).",
            "Redemption: pt.trxn_subtype_code = 'N' AND tt.trxndbcr = 'R'; date column pt.trxn_date only.",
            "Do not use EXISTS-only filters without returning last_redemption_date for 'when was last' questions.",
        ],
        "sql_skeleton": (
            f"{_investor_list_select('lr.last_redemption_date')} "
            "FROM public.distributor_investor_mapping dim "
            "JOIN public.investor i ON i.uuid = dim.investor_uuid "
            "LEFT JOIN ("
            "  SELECT dim2.investor_uuid, MAX(pt.trxn_date) AS last_redemption_date "
            "  FROM public.distributor_investor_mapping dim2 "
            "  JOIN sphmf.processed_trxns pt ON pt.folio_no = dim2.folio_number "
            "    AND pt.broker_code = dim2.arn_code "
            "  JOIN sphmf.transaction_types tt ON pt.trxn_type_code = tt.trxntypcod "
            "  WHERE dim2.arn_code = %s AND pt.trxn_subtype_code = 'N' AND tt.trxndbcr = 'R' "
            "  GROUP BY dim2.investor_uuid"
            ") lr ON lr.investor_uuid = i.uuid "
            f"WHERE dim.arn_code = %s AND {INVESTOR_FULL_NAME_NORM_SQL} ILIKE %s "
            f"{INVESTOR_DEDUP_ORDER} LIMIT 500"
        ),
        "parameters_order": [
            "session_arn (redemption aggregate subquery)",
            "session_arn (outer dim)",
            "name_pattern e.g. %aparnajha%",
        ],
    },
    {
        "id": "active_sip_hybrid_min_amount",
        "user_examples": [
            "Active SIPs above 5,000 per month in hybrid funds",
            "SIP more than 5000 hybrid",
        ],
        "tables": [
            "public.distributor_investor_mapping",
            "public.investor",
            "sphmf.sipstp",
            "public.scheme_master",
        ],
        "join_recipes": ["arn_scope_anchor", "sip_amount_active"],
        "sql_hints": [
            "Use EXISTS (not wide JOIN) on sipstp + scheme_master; avoid WITH/CTEs that put amount %s before dim.arn_code = %s.",
            "Active SIP: cease_dt NULL, cancellation_request_date NULL, to_date > NOW(), atrxn_type = 'P'.",
            "Amount: s.amount >= %s as second parameter (integer, e.g. 5000 for 'above 5,000 per month').",
            "Hybrid schemes: scheme_type ILIKE '%hybrid%' OR '%balanced%' per filter_vocabulary.scheme_classification.hybrid.",
        ],
        "sql_skeleton": (
            f"{_investor_list_select()} FROM public.distributor_investor_mapping dim "
            "JOIN public.investor i ON i.uuid = dim.investor_uuid "
            "WHERE dim.arn_code = %s AND EXISTS ("
            "  SELECT 1 FROM sphmf.sipstp s "
            "  JOIN public.scheme_master sm ON s.sch_code = sm.scheme_cd "
            "  WHERE s.folio_no = dim.folio_number AND s.brok_code = dim.arn_code "
            "  AND s.cease_dt IS NULL AND s.cancellation_request_date IS NULL AND s.to_date > NOW() "
            "  AND s.atrxn_type = 'P' AND s.amount >= %s "
            "  AND (lower(sm.scheme_type) LIKE '%%hybrid%%' OR lower(sm.scheme_type) LIKE '%%balanced%%')"
            f") {INVESTOR_DEDUP_ORDER} LIMIT 500"
        ),
        "parameters_order": ["session_arn", "min_sip_amount"],
    },
    {
        "id": "dormant_inactive",
        "user_examples": [
            "Dormant / inactive investors",
            "investors not transacted in certain period",
            "having 0 units across all schemes",
        ],
        "tables": [
            "public.distributor_investor_mapping",
            "public.investor",
            "sphmf.customer_schemes",
            "sphmf.processed_trxns",
        ],
        "join_recipes": ["arn_scope_anchor", "investor_identity"],
        "sql_hints": [
            "Dormant (180d): MAX(DATE(cs.l_trxn_date)) per investor_uuid for ARN folios; filter CURRENT_DATE - max_d >= 180.",
            "Zero units: NOT EXISTS positive holding from processed_trxns SUM(case trxn_sign +/- units) > 0.",
            "User may specify months — parameterize interval as %s days or use date literals in thought only via %s.",
        ],
        "sql_skeleton": (
            f"{_investor_list_select()} FROM public.distributor_investor_mapping dim "
            "JOIN public.investor i ON i.uuid = dim.investor_uuid "
            "WHERE dim.arn_code = %s AND EXISTS ("
            "  SELECT 1 FROM (SELECT MAX(DATE(cs.l_trxn_date)) AS last_dt, dim2.investor_uuid "
            "    FROM sphmf.customer_schemes cs "
            "    JOIN public.distributor_investor_mapping dim2 ON cs.folio_no = dim2.folio_number "
            "    WHERE dim2.arn_code = %s AND dim2.investor_uuid = dim.investor_uuid "
            "    GROUP BY dim2.investor_uuid) x WHERE CURRENT_DATE - x.last_dt >= %s"
            f") {INVESTOR_DEDUP_ORDER} LIMIT 500"
        ),
        "parameters_order": ["session_arn", "session_arn", "inactive_days e.g. 180"],
    },
    {
        "id": "top_purchases_fy25",
        "user_examples": [
            "Top 20 investors by purchases in FY25",
            "top investors by purchase amount FY25",
        ],
        "tables": [
            "public.distributor_investor_mapping",
            "public.investor",
            "sphmf.processed_trxns",
            "sphmf.transaction_types",
        ],
        "join_recipes": ["arn_scope_anchor", "purchase_activity"],
        "sql_hints": [
            "Aggregate SUM(pt.amount) or COUNT(*) for purchases (trxndbcr='P', trxn_subtype_code='N').",
            f"FY25 window: 2025-04-01 to 2026-04-01 on pt.{PROCESSED_TRXN_DATE} (see filter_vocabulary.financial_year_fy25).",
            "ORDER BY total DESC LIMIT 20 (user top N).",
        ],
        "sql_skeleton": (
            "SELECT i.first_name, i.last_name, i.email, SUM(pt.amount) AS purchase_total "
            "FROM public.distributor_investor_mapping dim "
            "JOIN public.investor i ON i.uuid = dim.investor_uuid "
            "JOIN sphmf.processed_trxns pt ON pt.folio_no = dim.folio_number AND pt.broker_code = dim.arn_code "
            "JOIN sphmf.transaction_types tt ON pt.trxn_type_code = tt.trxntypcod "
            "WHERE dim.arn_code = %s AND pt.trxn_subtype_code = 'N' AND tt.trxndbcr = 'P' "
            f"AND pt.{PROCESSED_TRXN_DATE} >= %s AND pt.{PROCESSED_TRXN_DATE} < %s "
            "GROUP BY i.uuid, i.first_name, i.last_name, i.email "
            "ORDER BY purchase_total DESC LIMIT 20"
        ),
        "parameters_order": ["session_arn", "fy_start", "fy_end"],
    },
    {
        "id": "name_multi_city",
        "user_examples": [
            "Investors named 'Bhavin' in Mumbai or Ahmedabad",
            "name Bhavin Mumbai Ahmedabad",
        ],
        "tables": ["public.distributor_investor_mapping", "public.investor", "sphmf.customer_master"],
        "join_recipes": ["arn_scope_anchor", "investor_identity", "folio_kyc_city"],
        "sql_hints": [
            NAME_SEARCH_HINT,
            "Cities: (cm.city ILIKE '%mumbai%' OR cm.city ILIKE '%ahmedabad%') — can inline OR use two %s params.",
        ],
        "sql_skeleton": (
            f"{_investor_list_select('cm.city')} FROM public.distributor_investor_mapping dim "
            "JOIN public.investor i ON i.uuid = dim.investor_uuid "
            "JOIN sphmf.customer_master cm ON cm.folio_no = dim.folio_number "
            f"WHERE dim.arn_code = %s AND {INVESTOR_FULL_NAME_NORM_SQL} ILIKE %s "
            "AND (lower(trim(cm.city::text)) ILIKE '%mumbai%' OR lower(trim(cm.city::text)) ILIKE '%ahmedabad%') "
            f"{INVESTOR_DEDUP_ORDER} LIMIT 500"
        ),
        "parameters_order": ["session_arn", "name_pattern e.g. %bhavin% (lowercase, spaces stripped)"],
    },
    {
        "id": "nri_investors",
        "user_examples": ["NRI investors", "show NRI clients"],
        "tables": ["public.distributor_investor_mapping", "public.investor", "sphmf.customer_master", "public.tax_status"],
        "join_recipes": ["arn_scope_anchor", "nri_tax_status"],
        "sql_hints": ["Filter tax_status.nri_nre = 'Y' joined via customer_master.inv_type."],
        "sql_skeleton": (
            f"{_investor_list_select('ts.inv_type_desc')} FROM public.distributor_investor_mapping dim "
            "JOIN public.investor i ON i.uuid = dim.investor_uuid "
            "JOIN sphmf.customer_master cm ON cm.folio_no = dim.folio_number "
            "JOIN public.tax_status ts ON cm.inv_type = ts.inv_type_code "
            f"WHERE dim.arn_code = %s AND ts.nri_nre = 'Y' {INVESTOR_DEDUP_ORDER} LIMIT 500"
        ),
        "parameters_order": ["session_arn"],
    },
    {
        "id": "minor_not_in_cgf",
        "user_examples": [
            "Minor Investors not invested in CGF schemes",
            "minors without CGF",
        ],
        "tables": [
            "public.distributor_investor_mapping",
            "public.investor",
            "sphmf.customer_master",
            "public.tax_status",
            "sphmf.scheme_setup",
            "sphmf.customer_schemes",
        ],
        "join_recipes": ["arn_scope_anchor", "minor_tax_status", "cgf_schemes"],
        "sql_hints": [
            "Minor: tax_status.minor_flag='Y' AND distributor_flag='Y' AND active_flag='Y'.",
            "NOT invested in CGF: NOT EXISTS customer_schemes row with sch_code in scheme_setup CGF list (cgf_flag='C', plan_type<>'D').",
        ],
        "sql_skeleton": (
            f"{_investor_list_select()} FROM public.distributor_investor_mapping dim "
            "JOIN public.investor i ON i.uuid = dim.investor_uuid "
            "JOIN sphmf.customer_master cm ON cm.folio_no = dim.folio_number "
            "JOIN public.tax_status ts ON cm.inv_type = ts.inv_type_code "
            "WHERE dim.arn_code = %s AND ts.minor_flag = 'Y' AND ts.distributor_flag = 'Y' AND ts.active_flag = 'Y' "
            "AND NOT EXISTS ("
            "  SELECT 1 FROM sphmf.customer_schemes cs "
            "  WHERE cs.folio_no = dim.folio_number AND cs.sch_code IN ("
            "    SELECT schcode FROM sphmf.scheme_setup WHERE cgf_flag = 'C' AND plan_type <> 'D')"
            f") {INVESTOR_DEDUP_ORDER} LIMIT 500"
        ),
        "parameters_order": ["session_arn"],
    },
    {
        "id": "no_active_sip",
        "user_examples": ["Investors with no active SIP", "no live SIP"],
        "tables": ["public.distributor_investor_mapping", "public.investor", "sphmf.sipstp"],
        "join_recipes": ["arn_scope_anchor", "no_active_sip"],
        "sql_hints": ["NOT EXISTS active sipstp row for folio+brok_code; see join_recipe no_active_sip."],
        "sql_skeleton": (
            f"{_investor_list_select()} FROM public.distributor_investor_mapping dim "
            "JOIN public.investor i ON i.uuid = dim.investor_uuid "
            "WHERE dim.arn_code = %s AND NOT EXISTS ("
            "  SELECT 1 FROM sphmf.sipstp s WHERE s.folio_no = dim.folio_number AND s.brok_code = dim.arn_code "
            "  AND s.cease_dt IS NULL AND s.cancellation_request_date IS NULL AND s.to_date > NOW()"
            f") {INVESTOR_DEDUP_ORDER} LIMIT 500"
        ),
        "parameters_order": ["session_arn"],
    },
    {
        "id": "liquid_only_funds",
        "user_examples": [
            "Investors with investment only in Liquid / cash funds",
            "only liquid fund holders",
        ],
        "tables": [
            "public.distributor_investor_mapping",
            "public.investor",
            "sphmf.processed_trxns",
            "public.scheme_master",
        ],
        "join_recipes": ["arn_scope_anchor", "holdings_units"],
        "sql_hints": [
            "Investors who HAVE positive units only in liquid schemes AND have NO positive units in non-liquid schemes.",
            "Use two EXISTS / NOT EXISTS on aggregated processed_trxns by folio with scheme_master classification.",
            "Liquid predicate from filter_vocabulary.scheme_classification.liquid_cash.",
        ],
        "sql_skeleton": (
            f"{_investor_list_select()} FROM public.distributor_investor_mapping dim "
            "JOIN public.investor i ON i.uuid = dim.investor_uuid "
            "WHERE dim.arn_code = %s AND EXISTS ("
            "  SELECT 1 FROM sphmf.processed_trxns pt "
            "  JOIN public.scheme_master sm ON pt.sch_code = sm.scheme_cd "
            "  WHERE pt.folio_no = dim.folio_number AND pt.broker_code = dim.arn_code "
            f"  AND {LIQUID_SCHEME_PREDICATE} "
            "  GROUP BY pt.folio_no, pt.sch_code HAVING SUM(CASE WHEN pt.trxn_sign = '+' THEN pt.units "
            "    WHEN pt.trxn_sign = '-' THEN -pt.units ELSE 0 END) > 0"
            ") AND NOT EXISTS ("
            "  SELECT 1 FROM sphmf.processed_trxns pt "
            "  JOIN public.scheme_master sm ON pt.sch_code = sm.scheme_cd "
            "  WHERE pt.folio_no = dim.folio_number AND pt.broker_code = dim.arn_code "
            f"  AND NOT {LIQUID_SCHEME_PREDICATE} "
            "  GROUP BY pt.folio_no, pt.sch_code HAVING SUM(CASE WHEN pt.trxn_sign = '+' THEN pt.units "
            "    WHEN pt.trxn_sign = '-' THEN -pt.units ELSE 0 END) > 0"
            f") {INVESTOR_DEDUP_ORDER} LIMIT 500"
        ),
        "parameters_order": ["session_arn"],
    },
]


def enrich_investor_schema_guide(guide: dict[str, Any]) -> dict[str, Any]:
    """Attach curated question patterns (does not mutate tables/sample rows)."""

    out = dict(guide)
    recipes = list(out.get("join_recipes") or [])
    seen = {r.get("name") for r in recipes if isinstance(r, dict)}
    for extra in EXTRA_JOIN_RECIPES:
        if extra.get("name") not in seen:
            recipes.append(extra)
            seen.add(extra.get("name"))
    out["join_recipes"] = recipes
    out["filter_vocabulary"] = FILTER_VOCABULARY
    out["question_patterns"] = QUESTION_PATTERNS
    rules = dict(out.get("sql_rules") or {})
    rules["question_patterns"] = (
        "Before writing SQL, match the user question to question_patterns[].user_examples; "
        "follow that pattern's sql_hints and sql_skeleton (parameterize with %s)."
    )
    rules["performance"] = (
        "Prefer EXISTS subqueries scoped to arn_scope; avoid joining sipstp/processed_trxns to investor "
        "without folio+broker predicates; always LIMIT <= 500."
    )
    rules["investor_row_dedup"] = INVESTOR_DEDUP_HINT
    rules["investor_name_search"] = NAME_SEARCH_HINT
    out["sql_rules"] = rules
    return out
