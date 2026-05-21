"""PostgreSQL parameter binding for session-stored executable SQL."""

from __future__ import annotations

from app.services.final_query import (
    bind_postgresql_parameters,
    build_postgresql_executable_sql,
    publish_final_query_to_session,
)


def test_bind_postgresql_parameters_inlines_arn() -> None:
    sql = "SELECT 1 FROM public.distributor_investor_mapping WHERE arn_code = %s LIMIT 1"
    out = bind_postgresql_parameters(sql, ["ARN-0411"])
    assert out == "SELECT 1 FROM public.distributor_investor_mapping WHERE arn_code = 'ARN-0411' LIMIT 1"
    assert "%s" not in out


def test_bind_escapes_percent_in_literals() -> None:
    sql = "SELECT %s AS city WHERE name ILIKE %s"
    out = bind_postgresql_parameters(sql, ["Mumbai", "%mum%"])
    assert "'Mumbai'" in out
    assert "'%mum%'" in out


def test_publish_final_query_stores_sql_postgresql_in_last_sql() -> None:
    session: dict = {}
    publish_final_query_to_session(
        session,
        {
            "engine": "catalog_sql_generator",
            "sql": "SELECT uuid FROM public.investor i WHERE i.uuid IN (SELECT investor_uuid FROM public.distributor_investor_mapping WHERE arn_code = %s) AND AGE(i.dob) BETWEEN %s AND %s LIMIT 500",
            "parameters": ["ARN-0411", 30, 40],
        },
    )
    fq = session["final_query"]
    assert "sql_postgresql" in fq
    assert fq["sql_postgresql"].count("%s") == 0
    assert "'ARN-0411'" in fq["sql_postgresql"]
    assert "BETWEEN 30 AND 40" in fq["sql_postgresql"]
    assert session["last_sql"] == fq["sql_postgresql"]
    assert build_postgresql_executable_sql(fq["sql"], fq["parameters"]) == fq["sql_postgresql"]
