"""Shared Sonnet menu-query LLM stubs (sql + parameters JSON only)."""

from __future__ import annotations

import json

from app.services.dp_investor_menu import DpInvestorMenuParams, build_filter_dp_investor_menu_sql


def menu_query_llm_json(*, trusted_arn: str = "ARN-0411", thought: str = "stub") -> str:
    sql, params = build_filter_dp_investor_menu_sql(
        DpInvestorMenuParams(),
        trusted_arn=trusted_arn,
    )
    return json.dumps(
        {
            "thought": thought,
            "sql": sql,
            "parameters": params,
            "unsupported_reason": None,
        }
    )
