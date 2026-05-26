"""Send function contract + user question to Sonnet; return strict function-call SQL only."""

from __future__ import annotations

import json
from typing import Any

import litellm

from app.agents.system_prompts import FILTER_DP_INVESTOR_MENU_SYSTEM_PROMPT
from app.core.config import apply_runtime_env, get_config
from app.services.dp_investor_menu import FilterDpInvestorMenuLlmTurn, load_menu_catalog
from app.services.llm_json import parse_json_content
from app.services.sql_guard import SqlGuardError


def run_dp_investor_menu_param_llm(
    *,
    question: str,
    trusted_arn: str,
    repair_context: dict[str, Any] | None = None,
) -> tuple[FilterDpInvestorMenuLlmTurn, dict[str, Any]]:
    """Contract JSON + question → Sonnet → ``sql`` + ``parameters`` (or ``unsupported_reason``)."""

    cfg = get_config()
    apply_runtime_env(cfg)
    model = cfg.query_generator_llm_model_resolved
    catalog = load_menu_catalog()

    user_payload: dict[str, Any] = {
        "session_arn": trusted_arn,
        "question": question,
        "function_contract": catalog,
    }
    if repair_context:
        user_payload["repair_context"] = repair_context
    user_str = json.dumps(user_payload, ensure_ascii=True)

    log: dict[str, Any] = {
        "phase": "filter_dp_investor_menu_query_repair"
        if repair_context
        else "filter_dp_investor_menu_query",
        "model": model,
        "question": question,
        "user_payload_chars": len(user_str),
        "raw_response": None,
        "error": None,
    }

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": FILTER_DP_INVESTOR_MENU_SYSTEM_PROMPT},
            {"role": "user", "content": user_str},
        ],
        "temperature": 0,
        "timeout": cfg.query_generator_request_timeout_seconds,
        "response_format": {"type": "json_object"},
    }
    max_out = cfg.query_generator_max_output_tokens_resolved
    if max_out:
        kwargs["max_tokens"] = max_out

    response = litellm.completion(**kwargs)
    content = response.choices[0].message.content
    log["raw_response"] = content
    if not content:
        raise ValueError("Empty filter_dp_investor_menu query response")

    raw = parse_json_content(content)
    if not isinstance(raw, dict):
        raise ValueError("Menu query LLM must return a JSON object")

    turn = FilterDpInvestorMenuLlmTurn.model_validate(raw)
    if turn.unsupported_reason:
        log["parsed"] = turn.model_dump(mode="json")
        log["unsupported_reason"] = turn.unsupported_reason
        return turn, log

    if not turn.sql or not turn.sql.strip():
        raise ValueError("Menu query LLM must return sql for supported questions")

    params = list(turn.parameters)
    if not params:
        raise SqlGuardError("parameters array is required with generated sql")

    params[0] = trusted_arn.strip()
    turn = turn.model_copy(update={"parameters": params})
    log["parsed"] = turn.model_dump(mode="json")
    return turn, log
