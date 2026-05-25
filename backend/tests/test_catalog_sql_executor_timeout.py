"""Execute timeout detection and wall-clock guard."""

from __future__ import annotations

from app.services.catalog_sql_executor import is_execute_timeout_error


def test_is_execute_timeout_error() -> None:
    assert is_execute_timeout_error("canceling statement due to statement timeout")
    assert is_execute_timeout_error("Query exceeded 23s execution limit")
    assert not is_execute_timeout_error('relation "foo" does not exist')
