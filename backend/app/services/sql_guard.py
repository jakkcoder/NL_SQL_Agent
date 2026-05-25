"""Lightweight validation for LLM-generated dynamic SQL (read-only MVP guard)."""

from __future__ import annotations

import html
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

# psycopg3 pyformat: only %s, %b, %t are placeholders; literal % must be %%
_PYFORMAT_PLACEHOLDER = re.compile(r"%(?:s|b|t)\b")

_ARN_BIND_MARKERS = ("arn_code", "brok_code", "broker_code", "brokcode")

_ARN_SCOPE_PLACEHOLDER = re.compile(
    r"(?:arn_code|brok_code|broker_code|brokcode)\s*=\s*%[sbt]\b",
    re.IGNORECASE,
)

# LLMs often emit ``);`` then a newline before the main SELECT — treat as one statement.
_SEMICOLON_BETWEEN_CTE_AND_QUERY = re.compile(
    r"\)\s*;\s*(?=(?:WITH|SELECT)\b)",
    re.IGNORECASE | re.DOTALL,
)


class SqlGuardError(ValueError):
    """Raised when generated SQL fails static validation."""


def sanitize_catalog_sql(sql: str) -> str:
    """Normalize common LLM SQL quirks before validation or execution."""

    text = html.unescape(sql.strip())
    text = _SEMICOLON_BETWEEN_CTE_AND_QUERY.sub(") ", text)
    return text.rstrip().rstrip(";").strip()


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


def count_pyformat_placeholders(sql: str) -> int:
    """Count psycopg ``%s`` / ``%b`` / ``%t`` placeholders (not ``%`` inside LIKE literals)."""

    return len(_PYFORMAT_PLACEHOLDER.findall(sql))


def escape_literal_percent_for_pyformat(sql: str) -> str:
    """Escape ``%`` in SQL literals (e.g. ``LIKE '%%equity%%'``) before psycopg ``execute``."""

    parts: list[str] = []
    last = 0
    for match in _PYFORMAT_PLACEHOLDER.finditer(sql):
        chunk = sql[last : match.start()]
        parts.append(chunk.replace("%", "%%"))
        parts.append(match.group(0))
        last = match.end()
    parts.append(sql[last:].replace("%", "%%"))
    return "".join(parts)


def count_arn_scope_placeholders(sql: str) -> int:
    """How many ``%s`` placeholders bind ``arn_code`` / ``brok_code`` (``col = %s`` only)."""

    return len(_ARN_SCOPE_PLACEHOLDER.findall(sql))


def _coerce_non_arn_parameter(value: object) -> object:
    if isinstance(value, str):
        digits = value.replace(",", "").strip()
        if digits.isdigit():
            return int(digits)
    return value


def normalize_catalog_sql_parameters(
    sql: str,
    parameters: list[object],
    trusted_arn: str,
) -> list[object]:
    """Ensure session_arn is first, preserve repeated ARN binds, pad missing ARN slots."""

    n_placeholders = count_pyformat_placeholders(sql)
    params = list(parameters)

    if params and params[0] != trusted_arn:
        if trusted_arn in params:
            arn_vals = [p for p in params if p == trusted_arn]
            other_vals = [p for p in params if p != trusted_arn]
            params = arn_vals + other_vals
        elif n_placeholders > 0:
            params = [trusted_arn, *params]

    if not params:
        params = [trusted_arn]

    arn_slots = count_arn_scope_placeholders(sql)
    arn_vals = [p for p in params if p == trusted_arn]
    other_vals = [_coerce_non_arn_parameter(p) for p in params if p != trusted_arn]
    if arn_slots > len(arn_vals):
        arn_vals = [trusted_arn] * arn_slots
    result = arn_vals + other_vals
    if result and result[0] != trusted_arn:
        result[0] = trusted_arn
    return result


def validate_first_placeholder_arn_scope(sql: str) -> None:
    """Left-to-right first ``%s`` must bind session_arn on a distributor scope column."""

    match = _PYFORMAT_PLACEHOLDER.search(sql)
    if not match:
        raise SqlGuardError("SQL must include at least one %s placeholder for session_arn")
    prefix = sql[: match.end()]
    tail = prefix[-80:] if len(prefix) > 80 else prefix
    if not _ARN_SCOPE_PLACEHOLDER.search(tail):
        raise SqlGuardError(
            "First %s placeholder must follow arn_code, brok_code, or broker_code "
            "(session_arn). Avoid WITH/CTEs that place amount or date %s before distributor scope."
        )


def validate_arn_first_parameter(sql: str, parameters: list[object], trusted_arn: str) -> None:
    """Bind first parameter to trusted ARN and ensure SQL references ARN scope."""

    if not parameters:
        raise SqlGuardError("parameters must be non-empty; first must be session ARN")
    if parameters[0] != trusted_arn:
        raise SqlGuardError("First parameter must be the trusted session ARN")
    n_placeholders = count_pyformat_placeholders(sql)
    if n_placeholders == 0:
        raise SqlGuardError(
            "SQL must use %s placeholders (do not inline session_arn or numeric thresholds)"
        )
    if n_placeholders != len(parameters):
        raise SqlGuardError("Count of %s placeholders must match len(parameters)")
    validate_first_placeholder_arn_scope(sql)
    if not sql_requires_arn_placeholder(sql):
        raise SqlGuardError("SQL must reference arn_code, broker_code, brok_code, or brokcode")
