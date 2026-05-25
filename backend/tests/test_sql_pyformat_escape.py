"""psycopg pyformat: escape literal % in LIKE patterns."""

from __future__ import annotations

from app.services.sql_guard import (
    count_pyformat_placeholders,
    escape_literal_percent_for_pyformat,
    validate_arn_first_parameter,
)


def test_escape_like_percent_literals() -> None:
    sql = (
        "SELECT 1 FROM public.distributor_investor_mapping dim "
        "WHERE dim.arn_code = %s AND lower(sm.scheme_type) LIKE '%equity%' LIMIT 1"
    )
    escaped = escape_literal_percent_for_pyformat(sql)
    assert "LIKE '%%equity%%'" in escaped
    assert escaped.count("%s") == 1
    assert "%equity%" not in escaped.replace("%%equity%%", "")


def test_count_placeholders_ignores_like_literals() -> None:
    sql = "WHERE dim.arn_code = %s AND sm.scheme_type LIKE '%equity%' LIMIT 500"
    assert count_pyformat_placeholders(sql) == 1


def test_validate_arn_with_like_literal() -> None:
    sql = (
        "SELECT i.uuid FROM public.distributor_investor_mapping dim "
        "JOIN public.investor i ON i.uuid = dim.investor_uuid "
        "WHERE dim.arn_code = %s AND EXISTS ("
        "SELECT 1 FROM public.scheme_master sm "
        "WHERE lower(sm.scheme_type) LIKE '%equity%') LIMIT 500"
    )
    validate_arn_first_parameter(sql, ["ARN-0411"], "ARN-0411")
