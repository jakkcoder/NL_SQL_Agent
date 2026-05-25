"""Catalog SQL parameter normalization and first-placeholder ARN scope."""

from __future__ import annotations

import pytest

from app.services.sql_guard import (
    SqlGuardError,
    normalize_catalog_sql_parameters,
    sanitize_catalog_sql,
    validate_arn_first_parameter,
    validate_dynamic_sql,
    validate_first_placeholder_arn_scope,
)

_TRUSTED = "ARN-0411"

_SIP_EXISTS_SQL = (
    "SELECT DISTINCT i.first_name FROM public.distributor_investor_mapping dim "
    "JOIN public.investor i ON i.uuid = dim.investor_uuid "
    "WHERE dim.arn_code = %s AND EXISTS ("
    "  SELECT 1 FROM sphmf.sipstp s "
    "  JOIN public.scheme_master sm ON s.sch_code = sm.scheme_cd "
    "  WHERE s.folio_no = dim.folio_number AND s.brok_code = dim.arn_code "
    "  AND s.amount >= %s "
    "  AND lower(sm.scheme_type) LIKE '%%hybrid%%') LIMIT 500"
)

_CTE_AMOUNT_FIRST_SQL = (
    "WITH active_sips AS ("
    "  SELECT s.folio_no FROM sphmf.sipstp s WHERE s.amount >= %s"
    ") SELECT 1 FROM public.distributor_investor_mapping dim "
    "WHERE dim.arn_code = %s LIMIT 1"
)


def test_normalize_puts_session_arn_first() -> None:
    params = normalize_catalog_sql_parameters(_SIP_EXISTS_SQL, [5000, _TRUSTED], _TRUSTED)
    assert params == [_TRUSTED, 5000]


def test_normalize_coerces_numeric_string() -> None:
    params = normalize_catalog_sql_parameters(_SIP_EXISTS_SQL, [_TRUSTED, "5,000"], _TRUSTED)
    assert params == [_TRUSTED, 5000]


def test_validate_sip_exists_pattern() -> None:
    params = normalize_catalog_sql_parameters(_SIP_EXISTS_SQL, [_TRUSTED, 5000], _TRUSTED)
    validate_arn_first_parameter(_SIP_EXISTS_SQL, params, _TRUSTED)


def test_reject_cte_with_amount_placeholder_first() -> None:
    with pytest.raises(SqlGuardError, match="First %s placeholder"):
        validate_first_placeholder_arn_scope(_CTE_AMOUNT_FIRST_SQL)


_DORMANT_SQL = (
    "WITH last_trxn AS ("
    "  SELECT dim2.investor_uuid, MAX(DATE(cs.l_trxn_date)) AS last_dt "
    "  FROM sphmf.customer_schemes cs "
    "  JOIN public.distributor_investor_mapping dim2 ON cs.folio_no = dim2.folio_number "
    "  WHERE dim2.arn_code = %s GROUP BY dim2.investor_uuid"
    ") SELECT i.first_name FROM public.distributor_investor_mapping dim "
    "JOIN public.investor i ON i.uuid = dim.investor_uuid "
    "JOIN last_trxn lt ON lt.investor_uuid = dim.investor_uuid "
    "WHERE dim.arn_code = %s AND (lt.last_dt IS NULL OR CURRENT_DATE - lt.last_dt >= %s) "
    "LIMIT 500"
)


def test_normalize_preserves_duplicate_session_arn() -> None:
    params = normalize_catalog_sql_parameters(
        _DORMANT_SQL, [_TRUSTED, _TRUSTED, 180], _TRUSTED
    )
    assert params == [_TRUSTED, _TRUSTED, 180]
    validate_arn_first_parameter(_DORMANT_SQL, params, _TRUSTED)


def test_normalize_reorders_and_keeps_two_arns() -> None:
    params = normalize_catalog_sql_parameters(_DORMANT_SQL, [180, _TRUSTED, _TRUSTED], _TRUSTED)
    assert params == [_TRUSTED, _TRUSTED, 180]


def test_normalize_pads_missing_second_arn() -> None:
    params = normalize_catalog_sql_parameters(_DORMANT_SQL, [_TRUSTED, 180], _TRUSTED)
    assert params == [_TRUSTED, _TRUSTED, 180]


def test_sanitize_removes_semicolon_between_cte_and_select() -> None:
    raw = (
        "WITH purchase_activity AS (SELECT 1 AS n)\n"
        ";\n"
        "SELECT n FROM purchase_activity ORDER BY n DESC LIMIT 20"
    )
    cleaned = sanitize_catalog_sql(raw)
    validate_dynamic_sql(cleaned)
    assert ";\n" not in cleaned


def test_reject_inlined_sql_without_placeholders() -> None:
    inlined = (
        "SELECT 1 FROM public.distributor_investor_mapping dim "
        f"WHERE dim.arn_code = '{_TRUSTED}' LIMIT 1"
    )
    with pytest.raises(SqlGuardError, match="%s placeholders"):
        validate_arn_first_parameter(inlined, [_TRUSTED], _TRUSTED)
