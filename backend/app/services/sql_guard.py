"""Lightweight validation for LLM-generated dynamic SQL (read-only MVP guard)."""

from __future__ import annotations

import re

_MAX_SQL_CHARS = 50_000

_FORBIDDEN = re.compile(
    r"\b("
    r"insert|update|delete|merge|truncate|drop|alter|create|grant|revoke|"
    r"call|execute|do\b|copy|into\s+outfile|pg_sleep|dblink|lo_import|lo_export"
    r")\b",
    re.IGNORECASE,
)

_LEADING_STATEMENT = re.compile(r"^\s*(with|select)\b", re.IGNORECASE | re.DOTALL)


class SqlGuardError(ValueError):
    """Raised when generated SQL fails static validation."""


def validate_dynamic_sql(sql: str) -> None:
    """Ensure a single read-only SELECT/WITH and basic safety."""

    if not sql or not isinstance(sql, str):
        raise SqlGuardError("SQL must be a non-empty string")
    stripped = sql.strip()
    if len(stripped) > _MAX_SQL_CHARS:
        raise SqlGuardError("SQL exceeds maximum length")
    if ";" in stripped.rstrip().rstrip(";"):
        raise SqlGuardError("Multiple SQL statements are not allowed")
    if not _LEADING_STATEMENT.match(stripped):
        raise SqlGuardError("SQL must start with SELECT or WITH")
    if _FORBIDDEN.search(stripped):
        raise SqlGuardError("Forbidden SQL keyword detected")
    limits = [int(m.group(1)) for m in re.finditer(r"\blimit\s+(\d+)\b", stripped, re.IGNORECASE)]
    if not limits:
        raise SqlGuardError("SQL must include an explicit LIMIT")
    if max(limits) > 500:
        raise SqlGuardError("LIMIT must be at most 500")


def sql_requires_arn_placeholder(sql: str) -> bool:
    """Heuristic: distributor-scoped SQL should reference ARN-like columns."""

    low = sql.lower()
    return any(
        token in low
        for token in ("arn_code", "broker_code", "brok_code", "brokcode")
    )


def validate_arn_first_parameter(sql: str, parameters: list[object], trusted_arn: str) -> None:
    """Bind first parameter to trusted ARN and ensure SQL references ARN scope."""

    if not parameters:
        raise SqlGuardError("parameters must be non-empty; first must be session ARN")
    if parameters[0] != trusted_arn:
        raise SqlGuardError("First parameter must be the trusted session ARN")
    if sql.count("%s") != len(parameters):
        raise SqlGuardError("Count of %s placeholders must match len(parameters)")
    if not sql_requires_arn_placeholder(sql):
        raise SqlGuardError("SQL must reference arn_code, broker_code, brok_code, or brokcode")
