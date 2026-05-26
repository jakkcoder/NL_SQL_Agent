"""Build and validate SQL for ``public.filter_dp_investor_menu`` (Individual portal)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.config import AppConfig
from app.db.postgres import DatabaseNotConfiguredError, DatabaseUnavailableError, PostgresClient
from app.services.catalog_sql_executor import (
    CatalogSqlExecuteError,
    dedupe_investor_result_rows,
    is_execute_timeout_error,
)
from app.services.sql_guard import SqlGuardError

BACKEND_DIR = Path(__file__).resolve().parents[2]
MENU_CATALOG_PATH = BACKEND_DIR / "app" / "data" / "filter_dp_investor_menu_catalog.json"

ALL_SYSTEMATIC_PLANS = (
    "SIP",
    "STP",
    "SWP",
    "FLEXSTP",
    "FLEXINDEX",
    "DTP",
    "SWINGSTP",
    "SMARTSWAP",
    "FLEXSIP",
)
ALL_ACTIVITY_TYPES = ("PURCHASE", "SWITCH", "REDEMPTION", "SIP", "DTP", "STP", "SWP", "FLEXSIP")
DEFAULT_INV_OPTIONS = ("Z", "N", "Y")

_FUNCTION_CALL = re.compile(
    r"^\s*SELECT\b.+?\bFROM\s+public\.filter_dp_investor_menu\s*\(",
    re.IGNORECASE | re.DOTALL,
)


class MenuCompositeFilter(BaseModel):
    """Holding composite (portal current-holdings panel)."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["ALL", "WITH", "WITHOUT"] = "ALL"
    schemes: list[str] = Field(default_factory=lambda: ["ALL"])
    inv_options: list[str] = Field(default_factory=lambda: list(DEFAULT_INV_OPTIONS))


class MenuSystematicFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["ALL", "WITH", "WITHOUT"] = "ALL"
    plan: list[str] = Field(default_factory=lambda: list(ALL_SYSTEMATIC_PLANS))
    schemes: list[str] = Field(default_factory=lambda: ["ALL"])
    inv_options: list[str] = Field(default_factory=lambda: list(DEFAULT_INV_OPTIONS))


class MenuActivityFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["ALL", "WITH", "WITHOUT"] = "ALL"
    activity_type: list[str] = Field(default_factory=lambda: list(ALL_ACTIVITY_TYPES))
    schemes: list[str] = Field(default_factory=lambda: ["ALL"])
    inv_options: list[str] = Field(default_factory=lambda: list(DEFAULT_INV_OPTIONS))
    duration: str = "1 month"


class DpInvestorMenuParams(BaseModel):
    """Strict JSON from the menu-parameter LLM (no raw SQL)."""

    model_config = ConfigDict(extra="forbid")

    thought: str = ""
    eligibility: Literal["ALL", "YES", "NO"] = "ALL"
    otm: Literal["ALL", "Y", "NOT_AVAILABLE"] = "ALL"
    investor_type: Literal["ALL", "ACTIVE", "DORMANT"] = "ALL"
    investor_subtypes: list[str] = Field(default_factory=list)
    holding: MenuCompositeFilter | None = None
    systematic: MenuSystematicFilter | None = None
    activity: MenuActivityFilter | None = None
    searchtext: str | None = None
    sortkey: Literal["first_name", "pan_number", "dob"] = "first_name"
    sortvalue: Literal["ASC", "DESC"] = "ASC"
    page_limit: int = Field(default=25, ge=1, le=500)
    page_index: int = Field(default=0, ge=0)
    allowbroker: Literal["Y"] = "Y"
    unsupported_reason: str | None = None

    @field_validator("investor_subtypes")
    @classmethod
    def _validate_subtypes(cls, values: list[str]) -> list[str]:
        allowed = {"CGF", "MINOR", "OTHERS"}
        out: list[str] = []
        for v in values:
            key = str(v).strip().upper()
            if key not in allowed:
                raise ValueError(f"Invalid investor_subtypes value: {v}")
            if key not in out:
                out.append(key)
        return out


def load_menu_catalog() -> dict[str, Any]:
    return json.loads(MENU_CATALOG_PATH.read_text(encoding="utf-8"))


def _sql_literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _sql_text_array(values: list[str]) -> str:
    if not values:
        return "ARRAY[]::TEXT[]"
    return f"ARRAY[{', '.join(_sql_literal(v) for v in values)}]::TEXT[]"


def _mode_to_flag(mode: str) -> str | None:
    if mode == "ALL":
        return None
    return "false" if mode == "WITHOUT" else "true"


def _holding_sql(holding: MenuCompositeFilter | None) -> str:
    if holding is None or holding.mode == "ALL":
        return "NULL::current_holdings"
    flag = _mode_to_flag(holding.mode)
    assert flag is not None
    return (
        f"ROW({_sql_literal(flag)}, {_sql_text_array(holding.schemes)}, "
        f"{_sql_text_array(holding.inv_options)})::current_holdings"
    )


def _systematic_sql(systematic: MenuSystematicFilter | None) -> str:
    if systematic is None or systematic.mode == "ALL":
        return "NULL::systematic_plan"
    flag = _mode_to_flag(systematic.mode)
    assert flag is not None
    return (
        f"ROW({_sql_literal(flag)}, {_sql_text_array(systematic.plan)}, "
        f"{_sql_text_array(systematic.schemes)}, {_sql_text_array(systematic.inv_options)})"
        f"::systematic_plan"
    )


def _activity_sql(activity: MenuActivityFilter | None) -> str:
    if activity is None or activity.mode == "ALL":
        return "NULL::investor_activity"
    flag = _mode_to_flag(activity.mode)
    assert flag is not None
    return (
        f"ROW({_sql_literal(flag)}, {_sql_text_array(activity.activity_type)}, "
        f"{_sql_text_array(activity.schemes)}, {_sql_text_array(activity.inv_options)}, "
        f"{_sql_literal(activity.duration)})::investor_activity"
    )


def build_filter_dp_investor_menu_sql(
    params: DpInvestorMenuParams,
    *,
    trusted_arn: str,
) -> tuple[str, list[Any]]:
    """Return parameterized SELECT wrapping ``public.filter_dp_investor_menu``."""

    arn = trusted_arn.strip()
    if not arn:
        raise SqlGuardError("ARN is required")

    search = params.searchtext
    if search is not None:
        text = search.strip()
        if text:
            if "%" not in text:
                text = f"%{text.lower()}%"
            search = text
        else:
            search = None

    subtype_sql = _sql_text_array(params.investor_subtypes)
    sql = f"""
SELECT
  uuid,
  name,
  pan_number,
  dob,
  email,
  mobile_number,
  count
FROM public.filter_dp_investor_menu(
  %s,
  %s,
  %s,
  %s,
  {subtype_sql},
  {_holding_sql(params.holding)},
  {_systematic_sql(params.systematic)},
  {_activity_sql(params.activity)},
  %s,
  %s,
  %s,
  %s,
  %s,
  %s
)
""".strip()

    parameters: list[Any] = [
        arn,
        params.eligibility,
        params.otm,
        params.investor_type,
        search,
        params.sortkey,
        params.sortvalue,
        params.page_limit,
        params.page_index,
        params.allowbroker,
    ]
    return sql, parameters


def validate_filter_dp_investor_menu_sql(sql: str, parameters: list[Any], trusted_arn: str) -> None:
    if not _FUNCTION_CALL.match(sql.strip()):
        raise SqlGuardError("SQL must be a single SELECT from public.filter_dp_investor_menu(...)")
    if not parameters or str(parameters[0]).strip() != trusted_arn.strip():
        raise SqlGuardError("First bound parameter must be the session ARN")
    forbidden = re.compile(
        r"\b(insert|update|delete|drop|alter|create|grant|revoke|copy|do\b)\b",
        re.IGNORECASE,
    )
    if forbidden.search(sql):
        raise SqlGuardError("Forbidden SQL keyword detected")


def execute_filter_dp_investor_menu(
    sql: str,
    parameters: list[Any],
    *,
    trusted_arn: str,
    config: AppConfig,
) -> list[dict[str, Any]]:
    validate_filter_dp_investor_menu_sql(sql, parameters, trusted_arn)

    db_url = config.database_url_value
    if not db_url:
        raise CatalogSqlExecuteError(
            "Database is not configured (set DEV_DATABASE_URL or PROD_DATABASE_URL)."
        )

    db_cfg = config.database
    db = PostgresClient(
        db_url,
        db_cfg.statement_timeout_ms,
        min_size=1,
        max_size=1,
        connect_timeout_seconds=db_cfg.connect_timeout_seconds,
        pool_timeout_seconds=db_cfg.pool_timeout_seconds,
    )
    try:
        db.open()
        rows = db.fetch_all(sql, parameters)
        safe = [
            {
                k: (v.isoformat() if hasattr(v, "isoformat") else v)
                for k, v in dict(row).items()
            }
            for row in rows
        ]
        return dedupe_investor_result_rows(safe)
    except (DatabaseNotConfiguredError, DatabaseUnavailableError) as exc:
        raise CatalogSqlExecuteError(str(exc)) from exc
    finally:
        db.close()
