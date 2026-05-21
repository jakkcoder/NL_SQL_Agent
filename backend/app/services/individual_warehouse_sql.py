"""Catalog-driven Individual investor SQL.

Filter semantics mirror ``planning/complete_function.sql`` (historical distributor-menu function)
for parity; allowed values are read from ``filter_catalog.json`` before SQL is built.
"""

from __future__ import annotations

import logging
from typing import Any

from app.models.search_plan import (
    DEFAULT_OPTIONS,
    BinaryFilter,
    EligibilityFilter,
    IndividualOtmFilter,
    InvestorSubtype,
    InvestorTypeFilter,
    SearchPlan,
    SystematicPlanType,
)
from app.services.filter_catalog import get_filter_catalog_for_session

logger = logging.getLogger(__name__)

ALLOW_BROKER = "Y"

_NAME_EXPR = """trim(concat(
    ltrim(concat(nullif(i.first_name, NULL), ' ')),
    ltrim(concat(nullif(i.middle_name, NULL), ' ')),
    ltrim(concat(nullif(i.last_name, NULL), ' '))
))"""


def _all_schemes(schemes: list[str]) -> bool:
    return not schemes or schemes == ["ALL"] or set(schemes) == {"ALL"}


def _inv_options_is_full_catalog(inv_options: list[str]) -> bool:
    raw = {str(x).strip() for x in inv_options if str(x).strip() and str(x).strip() != "ALL"}
    return not raw or raw == set(DEFAULT_OPTIONS)


def _validate_plan_values(plan: SearchPlan, session_state: dict[str, Any] | None) -> None:
    catalog = get_filter_catalog_for_session(session_state)
    checks: list[tuple[str, str]] = [
        ("eligibility", plan.eligibility.value),
        ("individual_otm", plan.individual_otm.value),
        ("investor_type", plan.investor_type.value),
        ("holding_mode", plan.holding.mode.value),
        ("systematic_mode", plan.systematic.mode.value),
        ("activity_mode", plan.activity.mode.value),
        ("activity_duration", plan.activity.duration),
        ("sort_key", plan.sort_key),
        ("sort_order", plan.sort_order),
    ]
    for key, value in checks:
        if not catalog.allows(key, value):
            logger.warning("SearchPlan value %s=%s not in filter catalog; continuing.", key, value)
    for subtype in plan.investor_subtypes:
        if not catalog.allows("investor_subtypes", subtype.value):
            logger.warning("investor_subtypes value %s not in catalog", subtype.value)
    for plan_name in plan.systematic.plans:
        if not catalog.allows("systematic_plans", plan_name):
            logger.warning("systematic_plans value %s not in catalog", plan_name)
    for act in plan.activity.activity_types:
        if not catalog.allows("activity_types", act):
            logger.warning("activity_types value %s not in catalog", act)
    for bucket in (plan.holding.schemes, plan.systematic.schemes, plan.activity.schemes):
        for sch in bucket:
            if sch == "ALL":
                continue
            if not catalog.allows("scheme_codes", sch):
                raise ValueError(f"Scheme code {sch!r} is not allowed by filter catalog.")


def _sip_atrxn_or_sql(plans: list[str]) -> str:
    """OR of SIPSTP atrxn_type / switch predicates (matches legacy function)."""

    parts: list[str] = []
    if "SIP" in plans:
        parts.append("(s.atrxn_type = 'P')")
    if "STP" in plans:
        parts.append("(s.atrxn_type = 'SO' AND (s.switch_flag IS NULL OR s.switch_flag NOT IN ('T','Q')))")
    if "SWP" in plans:
        parts.append("(s.atrxn_type = 'R' AND (s.sub_trxn_type IS NULL OR s.sub_trxn_type != 'MB'))")
    if "FLEXSTP" in plans:
        parts.append("(s.atrxn_type = 'SO')")
    if "SWINGSTP" in plans:
        parts.append("(s.atrxn_type = 'SO' AND s.switch_flag = 'Q')")
    if "SMARTSWAP" in plans:
        parts.append("(s.atrxn_type = 'R' AND s.sub_trxn_type = 'MB')")
    if "FLEXSIP" in plans:
        parts.append("(s.atrxn_type = 'P' AND s.sub_trxn_type = 'FS')")
    if not parts:
        return "FALSE"
    return "(" + " OR ".join(parts) + ")"


def _activity_type_or_sql(types: list[str]) -> str:
    parts: list[str] = []
    if "DTP" in types:
        parts.append("(tt.trxndbcr = 'DR' AND pt.trxn_type_code = 'DRDTP')")
    if "PURCHASE" in types:
        parts.append("(pt.trxn_subtype_code = 'N' AND tt.trxndbcr = 'P')")
    if "SWITCH" in types:
        parts.append("(pt.trxn_subtype_code = 'N' AND tt.trxndbcr IN ('SI','SO'))")
    if "REDEMPTION" in types:
        parts.append("(pt.trxn_subtype_code = 'N' AND tt.trxndbcr = 'R')")
    if "SIP" in types:
        parts.append("(pt.trxn_subtype_code = 'S' AND tt.trxndbcr = 'P')")
    if "STP" in types:
        parts.append("(pt.trxn_subtype_code = 'S' AND tt.trxndbcr IN ('SI','SO'))")
    if "SWP" in types:
        parts.append("(pt.trxn_subtype_code = 'S' AND tt.trxndbcr = 'R')")
    if "FLEXSIP" in types:
        parts.append("(pt.trxn_subtype_code = 'FS' AND tt.trxndbcr = 'P')")
    if not parts:
        return "FALSE"
    return "(" + " OR ".join(parts) + ")"


def _investor_age_sql_clause(plan: SearchPlan) -> tuple[str, list[Any]]:
    """Filter integer age in full years from ``public.investor.dob`` (outer alias ``i``)."""

    lo, hi = plan.age_min, plan.age_max
    if lo is None and hi is None:
        return "TRUE", []
    parts: list[str] = ["i.dob IS NOT NULL"]
    params: list[Any] = []
    if lo is not None and hi is not None:
        parts.append("EXTRACT(YEAR FROM AGE(CURRENT_DATE, i.dob))::int BETWEEN %s AND %s")
        params.extend([lo, hi])
    elif lo is not None:
        parts.append("EXTRACT(YEAR FROM AGE(CURRENT_DATE, i.dob))::int >= %s")
        params.append(lo)
    else:
        parts.append("EXTRACT(YEAR FROM AGE(CURRENT_DATE, i.dob))::int <= %s")
        params.append(hi)
    return "(" + " AND ".join(parts) + ")", params


def build_warehouse_individual_sql(
    plan: SearchPlan,
    arn_code: str,
    session_state: dict[str, Any] | None = None,
) -> tuple[str, list[Any]]:
    """Build SELECT/WITH SQL from ``filter_catalog.json`` + SearchPlan (no RPC)."""

    _validate_plan_values(plan, session_state)
    params: list[Any] = []
    where_parts: list[str] = ["dim.arn_code = %s"]
    params.append(arn_code)

    if plan.eligibility == EligibilityFilter.YES:
        params.append(arn_code)
        where_parts.append(
            """EXISTS (
            SELECT 1
            FROM public.distributor_investor_mapping dim_e
            INNER JOIN sphmf.customer_master cm ON cm.folio_no = dim_e.folio_number
            WHERE dim_e.investor_uuid = dim.investor_uuid
              AND dim_e.arn_code = %s
              AND cm.email IS NOT NULL
        )"""
        )
    elif plan.eligibility == EligibilityFilter.NO:
        params.append(arn_code)
        where_parts.append(
            """NOT EXISTS (
            SELECT 1
            FROM public.distributor_investor_mapping dim_e
            INNER JOIN sphmf.customer_master cm ON cm.folio_no = dim_e.folio_number
            WHERE dim_e.investor_uuid = dim.investor_uuid
              AND dim_e.arn_code = %s
              AND cm.email IS NOT NULL
        )"""
        )

    if plan.individual_otm == IndividualOtmFilter.YES:
        params.append(arn_code)
        where_parts.append(
            """EXISTS (
            SELECT 1
            FROM public.distributor_investor_mapping dim_o
            INNER JOIN sphmf.customer_master cm ON cm.folio_no = dim_o.folio_number
            WHERE dim_o.arn_code = %s
              AND dim_o.investor_uuid = dim.investor_uuid
              AND EXISTS (
                SELECT 1 FROM sphmf.multiple_bank mb
                WHERE dim_o.folio_number = mb.folio_no
                  AND mb.om_umrn IS NOT NULL
                  AND (mb.cease_dt IS NULL OR mb.cease_dt < CURRENT_DATE)
                  AND mb.paymech IN (
                    SELECT DISTINCT pay_mech FROM payout_mechanism
                    WHERE otm_flag IS TRUE AND active_flag IS TRUE
                  )
              )
        )"""
        )
    elif plan.individual_otm == IndividualOtmFilter.NO:
        params.append(arn_code)
        where_parts.append(
            """NOT EXISTS (
            SELECT 1
            FROM public.distributor_investor_mapping dim_o
            INNER JOIN sphmf.customer_master cm ON cm.folio_no = dim_o.folio_number
            WHERE dim_o.arn_code = %s
              AND dim_o.investor_uuid = dim.investor_uuid
              AND EXISTS (
                SELECT 1 FROM sphmf.multiple_bank mb
                WHERE dim_o.folio_number = mb.folio_no
                  AND mb.om_umrn IS NOT NULL
                  AND (mb.cease_dt IS NULL OR mb.cease_dt < CURRENT_DATE)
                  AND mb.paymech IN (
                    SELECT DISTINCT pay_mech FROM payout_mechanism
                    WHERE otm_flag IS TRUE AND active_flag IS TRUE
                  )
              )
        )"""
        )

    if plan.investor_type == InvestorTypeFilter.ACTIVE:
        params.append(arn_code)
        where_parts.append(
            """EXISTS (
            SELECT 1
            FROM (
                SELECT MAX(DATE(pd.l_trxn_date)) AS d, dim_act.investor_uuid
                FROM sphmf.customer_schemes pd
                INNER JOIN public.distributor_investor_mapping dim_act
                  ON pd.folio_no = dim_act.folio_number
                WHERE dim_act.arn_code = %s AND dim_act.investor_uuid = dim.investor_uuid
                GROUP BY dim_act.investor_uuid
            ) m
            WHERE CURRENT_DATE - m.d <= 180
        )"""
        )
    elif plan.investor_type == InvestorTypeFilter.DORMANT:
        params.append(arn_code)
        where_parts.append(
            """EXISTS (
            SELECT 1
            FROM (
                SELECT MAX(DATE(pd.l_trxn_date)) AS d, dim_act.investor_uuid
                FROM sphmf.customer_schemes pd
                INNER JOIN public.distributor_investor_mapping dim_act
                  ON pd.folio_no = dim_act.folio_number
                WHERE dim_act.arn_code = %s AND dim_act.investor_uuid = dim.investor_uuid
                GROUP BY dim_act.investor_uuid
            ) m
            WHERE CURRENT_DATE - m.d >= 180
        )"""
        )

    subtype_clauses: list[str] = []
    if plan.investor_subtypes:
        st_set = {s for s in plan.investor_subtypes}
        if InvestorSubtype.CGF in st_set:
            params.append(arn_code)
            subtype_clauses.append(
                """EXISTS (
                SELECT 1 FROM sphmf.customer_schemes pd
                INNER JOIN public.distributor_investor_mapping dim_c
                  ON dim_c.folio_number = pd.folio_no
                WHERE dim_c.arn_code = %s
                  AND dim_c.investor_uuid = dim.investor_uuid
                  AND pd.sch_code IN (
                    SELECT schcode FROM sphmf.scheme_setup
                    WHERE cgf_flag = 'C' AND plan_type <> 'D'
                  )
            )"""
            )
        if InvestorSubtype.MINOR in st_set:
            params.append(arn_code)
            subtype_clauses.append(
                """EXISTS (
                SELECT 1
                FROM public.distributor_investor_mapping dim_m
                INNER JOIN sphmf.customer_master cm ON cm.folio_no = dim_m.folio_number
                INNER JOIN tax_status ts ON cm.inv_type = ts.inv_type_code
                WHERE dim_m.arn_code = %s
                  AND dim_m.investor_uuid = dim.investor_uuid
                  AND ts.distributor_flag = 'Y' AND ts.minor_flag = 'Y' AND ts.active_flag = 'Y'
            )"""
            )
        if InvestorSubtype.OTHERS in st_set:
            params.append(arn_code)
            params.append(arn_code)
            subtype_clauses.append(
                """(
                EXISTS (
                    SELECT 1
                    FROM sphmf.customer_schemes pd
                    INNER JOIN public.distributor_investor_mapping dim_o
                      ON dim_o.folio_number = pd.folio_no
                    WHERE dim_o.arn_code = %s
                      AND dim_o.investor_uuid = dim.investor_uuid
                      AND pd.sch_code NOT IN (
                        SELECT schcode FROM sphmf.scheme_setup
                        WHERE cgf_flag = 'C' AND plan_type <> 'D'
                      )
                )
                AND EXISTS (
                    SELECT 1
                    FROM public.distributor_investor_mapping dim_o
                    INNER JOIN sphmf.customer_master cm ON cm.folio_no = dim_o.folio_number
                    INNER JOIN tax_status ts ON cm.inv_type = ts.inv_type_code
                    WHERE dim_o.investor_uuid = dim.investor_uuid
                      AND dim_o.arn_code = %s
                      AND NOT (ts.distributor_flag = 'Y' AND ts.minor_flag = 'Y' AND ts.active_flag = 'Y')
                )
            )"""
            )
        if subtype_clauses:
            where_parts.append("(" + " OR ".join(subtype_clauses) + ")")

    if plan.holding.mode != BinaryFilter.ALL:
        all_schemes = _all_schemes(plan.holding.schemes)
        all_inv = _inv_options_is_full_catalog(plan.holding.inv_options)
        scheme_pred = "TRUE" if all_schemes else "pt.sch_code = ANY(%s::TEXT[])"
        inv_pred = "TRUE" if all_inv else "cs.div_reinv_flag = ANY(%s::TEXT[])"
        holding_exists = f"""
            EXISTS (
                SELECT 1
                FROM public.distributor_investor_mapping dim_h
                INNER JOIN (
                    SELECT pt.folio_no, pt.broker_code, pt.sch_code
                    FROM sphmf.processed_trxns pt
                    INNER JOIN sphmf.customer_schemes cs
                      ON pt.folio_no = cs.folio_no AND pt.sch_code = cs.sch_code
                    INNER JOIN scheme_master sm ON pt.sch_code = sm.scheme_cd AND sm.allow_broker = %s
                    WHERE pt.broker_code = %s
                      AND ({scheme_pred})
                      AND ({inv_pred})
                    GROUP BY pt.folio_no, pt.broker_code, pt.sch_code
                    HAVING SUM(
                        CASE WHEN trxn_sign = '-' THEN units * -1
                             WHEN trxn_sign = '+' THEN units
                             ELSE 0 END
                    ) > 0
                ) holdings ON dim_h.folio_number = holdings.folio_no AND dim_h.arn_code = holdings.broker_code
                WHERE dim_h.arn_code = %s AND dim_h.investor_uuid = dim.investor_uuid
            )
        """
        params_h: list[Any] = [ALLOW_BROKER, arn_code]
        if not all_schemes:
            params_h.append(plan.holding.schemes)
        if not all_inv:
            params_h.append(plan.holding.inv_options)
        params_h.append(arn_code)
        params.extend(params_h)
        if plan.holding.mode == BinaryFilter.WITH:
            where_parts.append(holding_exists)
        else:
            where_parts.append(f"NOT ({holding_exists})")

    if plan.systematic.mode != BinaryFilter.ALL:
        sys_fragments: list[tuple[str, list[Any]]] = []
        plans = plan.systematic.plans or [p.value for p in SystematicPlanType]
        sip_or = _sip_atrxn_or_sql(plans)
        if any(p in plans for p in ("SIP", "STP", "SWP", "FLEXSTP", "SWINGSTP", "SMARTSWAP", "FLEXSIP")):
            sch_sip = "TRUE" if _all_schemes(plan.systematic.schemes) else "s.sch_code = ANY(%s::TEXT[])"
            inv_sip = "TRUE" if _inv_options_is_full_catalog(plan.systematic.inv_options) else "cs.div_reinv_flag = ANY(%s::TEXT[])"
            sip_sql = f"""
                EXISTS (
                    SELECT 1 FROM public.distributor_investor_mapping dim_s
                    INNER JOIN sphmf.sipstp s ON dim_s.folio_number = s.folio_no AND dim_s.arn_code = s.brok_code
                    INNER JOIN scheme_master sm ON s.sch_code = sm.scheme_cd AND sm.allow_broker = %s
                    {"INNER JOIN sphmf.customer_schemes cs ON cs.sch_code = s.sch_code AND cs.folio_no = s.folio_no" if not _inv_options_is_full_catalog(plan.systematic.inv_options) else ""}
                    WHERE dim_s.arn_code = %s AND dim_s.investor_uuid = dim.investor_uuid
                      AND ({sip_or})
                      AND ({sch_sip})
                      AND ({inv_sip})
                      AND s.cease_dt IS NULL AND s.cancellation_request_date IS NULL
                      AND s.to_date IS NOT NULL AND s.to_date > NOW()
                )
            """
            sparams: list[Any] = [ALLOW_BROKER, arn_code]
            if not _all_schemes(plan.systematic.schemes):
                sparams.append(plan.systematic.schemes)
            if not _inv_options_is_full_catalog(plan.systematic.inv_options):
                sparams.append(plan.systematic.inv_options)
            sys_fragments.append((sip_sql, sparams))

        if "DTP" in plans:
            sch_dtp = "TRUE" if _all_schemes(plan.systematic.schemes) else "dr.source_sch = ANY(%s::TEXT[])"
            inv_dtp = "TRUE" if _inv_options_is_full_catalog(plan.systematic.inv_options) else "cs.div_reinv_flag = ANY(%s::TEXT[])"
            dtp_sql = f"""
                EXISTS (
                    SELECT 1 FROM public.distributor_investor_mapping dim_d
                    INNER JOIN sphmf.dtp_regn dr ON dim_d.folio_number = dr.folio_no AND dim_d.arn_code = dr.brok_code
                    INNER JOIN scheme_master sm ON dr.source_sch = sm.scheme_cd AND sm.allow_broker = %s
                    {"INNER JOIN sphmf.customer_schemes cs ON cs.sch_code = dr.source_sch AND cs.folio_no = dr.folio_no" if not _inv_options_is_full_catalog(plan.systematic.inv_options) else ""}
                    WHERE dim_d.arn_code = %s AND dim_d.investor_uuid = dim.investor_uuid
                      AND ({sch_dtp})
                      AND ({inv_dtp})
                      AND dr.cease_date IS NULL
                )
            """
            dparams: list[Any] = [ALLOW_BROKER, arn_code]
            if not _all_schemes(plan.systematic.schemes):
                dparams.append(plan.systematic.schemes)
            if not _inv_options_is_full_catalog(plan.systematic.inv_options):
                dparams.append(plan.systematic.inv_options)
            sys_fragments.append((dtp_sql, dparams))

        if "FLEXINDEX" in plans:
            sch_fx = "TRUE" if _all_schemes(plan.systematic.schemes) else "tx.schcode = ANY(%s::TEXT[])"
            inv_fx = "TRUE" if _inv_options_is_full_catalog(plan.systematic.inv_options) else "cs.div_reinv_flag = ANY(%s::TEXT[])"
            fx_sql = f"""
                EXISTS (
                    SELECT 1 FROM public.distributor_investor_mapping dim_f
                    INNER JOIN sphmf.trigger_trxn tx ON dim_f.folio_number = tx.folio_no AND dim_f.arn_code = tx.brokcode
                    INNER JOIN scheme_master sm ON tx.schcode = sm.scheme_cd AND sm.allow_broker = %s
                    {"INNER JOIN sphmf.customer_schemes cs ON cs.sch_code = tx.schcode AND cs.folio_no = tx.folio_no" if not _inv_options_is_full_catalog(plan.systematic.inv_options) else ""}
                    WHERE dim_f.arn_code = %s AND dim_f.investor_uuid = dim.investor_uuid
                      AND ({sch_fx})
                      AND ({inv_fx})
                      AND tx.percent_of IS NOT NULL
                      AND tx.cease_date IS NULL AND tx.date_of_exec IS NULL
                )
            """
            fparams: list[Any] = [ALLOW_BROKER, arn_code]
            if not _all_schemes(plan.systematic.schemes):
                fparams.append(plan.systematic.schemes)
            if not _inv_options_is_full_catalog(plan.systematic.inv_options):
                fparams.append(plan.systematic.inv_options)
            sys_fragments.append((fx_sql, fparams))

        if sys_fragments:
            combined_sql_parts: list[str] = []
            for frag, extra in sys_fragments:
                combined_sql_parts.append(frag)
                params.extend(extra)
            or_chain = " OR ".join(f"({s.strip()})" for s in combined_sql_parts)
            if plan.systematic.mode == BinaryFilter.WITH:
                where_parts.append(f"({or_chain})")
            else:
                where_parts.append(f"NOT ({or_chain})")
        elif plan.systematic.mode == BinaryFilter.WITH:
            where_parts.append("FALSE")

    if plan.activity.mode != BinaryFilter.ALL:
        act_or = _activity_type_or_sql(plan.activity.activity_types)
        sch_act = "TRUE" if _all_schemes(plan.activity.schemes) else "pt.sch_code = ANY(%s::TEXT[])"
        inv_act = "TRUE" if _inv_options_is_full_catalog(plan.activity.inv_options) else "cs.div_reinv_flag = ANY(%s::TEXT[])"
        aparams: list[Any] = [ALLOW_BROKER, arn_code]
        if not _all_schemes(plan.activity.schemes):
            aparams.append(plan.activity.schemes)
        if not _inv_options_is_full_catalog(plan.activity.inv_options):
            aparams.append(plan.activity.inv_options)
        aparams.append(plan.activity.duration)
        act_sql = f"""
            EXISTS (
                SELECT 1
                FROM public.distributor_investor_mapping dim_a
                INNER JOIN sphmf.processed_trxns pt
                  ON dim_a.folio_number = pt.folio_no AND dim_a.arn_code = pt.broker_code
                INNER JOIN sphmf.customer_schemes cs
                  ON pt.folio_no = cs.folio_no AND pt.sch_code = cs.sch_code
                INNER JOIN scheme_master sm ON pt.sch_code = sm.scheme_cd AND sm.allow_broker = %s
                INNER JOIN sphmf.transaction_types tt ON tt.trxntypcod = pt.trxn_type_code
                WHERE dim_a.arn_code = %s AND dim_a.investor_uuid = dim.investor_uuid
                  AND ({act_or})
                  AND ({sch_act})
                  AND ({inv_act})
                  AND pt.entry_date >= NOW() - (%s)::INTERVAL
            )
        """
        params.extend(aparams)
        if plan.activity.mode == BinaryFilter.WITH:
            where_parts.append(act_sql)
        else:
            where_parts.append(f"NOT ({act_sql})")

    inner_where = " AND ".join(where_parts)
    sort_key = plan.sort_key if plan.sort_key in ("first_name", "pan_number", "dob") else "first_name"
    sort_order = plan.sort_order.upper() if plan.sort_order.upper() in ("ASC", "DESC") else "ASC"

    order_expr = (
        "CASE WHEN %s = 'pan_number' THEN i.pan_number::text "
        "WHEN %s = 'dob' THEN i.dob::text "
        f"ELSE {_NAME_EXPR} END"
    )

    name_params: list[Any] = []
    if plan.name_search:
        name_clause = f"lower(i.first_name) ILIKE %s"
        name_params.append(f"%{plan.name_search.lower()}%")
    else:
        name_clause = "TRUE"

    age_clause, age_params = _investor_age_sql_clause(plan)

    city_clause = "TRUE"
    city_params: list[Any] = []
    if plan.city and str(plan.city).strip():
        # City is on ``sphmf.customer_master`` (folio), not ``public.investor``.
        city_clause = (
            "EXISTS ("
            " SELECT 1 FROM public.distributor_investor_mapping dim_city"
            " INNER JOIN sphmf.customer_master cm_city ON cm_city.folio_no = dim_city.folio_number"
            " WHERE dim_city.investor_uuid = i.uuid"
            " AND dim_city.arn_code = %s"
            " AND lower(trim(coalesce(cm_city.city::text, ''))) ILIKE %s"
            ")"
        )
        city_params = [arn_code, f"%{plan.city.strip().lower()}%"]

    params_for_order = [sort_key, sort_key]
    params.extend(name_params)
    params.extend(age_params)
    params.extend(city_params)
    params.extend(params_for_order)
    params.append(plan.page_limit)
    params.append(plan.page_offset)

    sql = f"""
WITH uuids AS (
    SELECT DISTINCT dim.investor_uuid
    FROM public.distributor_investor_mapping dim
    WHERE {inner_where}
)
SELECT DISTINCT
    i.uuid::varchar AS uuid,
    {_NAME_EXPR} AS first_name,
    i.pan_number,
    i.dob,
    i.email,
    i.mobile_number,
    (SELECT COUNT(*)::int FROM uuids) AS count,
    {order_expr} AS orderby
FROM public.investor i
WHERE i.uuid IN (SELECT investor_uuid FROM uuids)
  AND ({name_clause})
  AND ({age_clause})
  AND ({city_clause})
ORDER BY orderby {sort_order}
LIMIT %s OFFSET %s
"""
    return " ".join(sql.split()), params
