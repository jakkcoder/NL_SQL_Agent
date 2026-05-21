"""Unit tests for ``app.services.sql_guard``."""

import pytest

from app.services.sql_guard import SqlGuardError, validate_arn_first_parameter, validate_dynamic_sql


def test_validate_accepts_simple_select_with_arn_and_limit():
    validate_dynamic_sql(
        "SELECT 1 FROM public.distributor_investor_mapping dim WHERE dim.arn_code = %s LIMIT 25",
    )


def test_validate_accepts_with_clause():
    validate_dynamic_sql(
        "WITH x AS (SELECT 1 AS a) SELECT a FROM x WHERE arn_code = %s LIMIT 10",
    )


def test_validate_rejects_missing_limit():
    with pytest.raises(SqlGuardError, match="LIMIT"):
        validate_dynamic_sql("SELECT 1 WHERE arn_code = %s")


def test_validate_rejects_limit_over_500():
    with pytest.raises(SqlGuardError, match="500"):
        validate_dynamic_sql("SELECT 1 WHERE arn_code = %s LIMIT 501")


def test_validate_rejects_forbidden_keyword():
    with pytest.raises(SqlGuardError, match="Forbidden"):
        validate_dynamic_sql("SELECT 1 WHERE arn_code = %s AND pg_sleep(1) LIMIT 1")


def test_validate_rejects_multiple_statements():
    with pytest.raises(SqlGuardError, match="Multiple"):
        validate_dynamic_sql("SELECT 1 WHERE arn_code = %s LIMIT 1; SELECT 2 LIMIT 1")


def test_validate_rejects_non_select():
    with pytest.raises(SqlGuardError, match="SELECT"):
        validate_dynamic_sql("UPDATE t SET a = 1 WHERE arn_code = %s LIMIT 1")


def test_validate_arn_first_parameter_ok():
    validate_arn_first_parameter(
        "SELECT 1 FROM dim WHERE broker_code = %s LIMIT 5",
        ["ARN-0411"],
        "ARN-0411",
    )


def test_validate_arn_wrong_first_param():
    with pytest.raises(SqlGuardError, match="trusted session ARN"):
        validate_arn_first_parameter(
            "SELECT 1 WHERE arn_code = %s LIMIT 5",
            ["OTHER"],
            "ARN-0411",
        )


def test_validate_arn_placeholder_mismatch():
    with pytest.raises(SqlGuardError, match="Count of"):
        validate_arn_first_parameter(
            "SELECT 1 WHERE arn_code = %s AND x = %s LIMIT 5",
            ["ARN-0411"],
            "ARN-0411",
        )


def test_validate_arn_missing_scope_column():
    with pytest.raises(SqlGuardError, match="arn_code"):
        validate_arn_first_parameter(
            "SELECT 1 WHERE id = %s LIMIT 5",
            ["ARN-0411"],
            "ARN-0411",
        )
