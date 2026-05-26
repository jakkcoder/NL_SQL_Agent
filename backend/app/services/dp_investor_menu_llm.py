"""Map natural language to ``filter_dp_investor_menu`` function parameters."""

from __future__ import annotations

import json
from typing import Any

import litellm

from app.agents.system_prompts import FILTER_DP_INVESTOR_MENU_SYSTEM_PROMPT
from app.core.config import apply_runtime_env, get_config
from app.services.dp_investor_menu import DpInvestorMenuParams, load_menu_catalog
from app.services.llm_json import parse_json_content


def run_dp_investor_menu_param_llm(
    *,
    question: str,
    trusted_arn: str,
) -> tuple[DpInvestorMenuParams, dict[str, Any]]:
    """Return validated function parameters for the Individual investor menu."""

    cfg = get_config()
    apply_runtime_env(cfg)
    model = cfg.query_generator_llm_model_resolved
    catalog = load_menu_catalog()

    user_payload = {
        "session_arn": trusted_arn,
        "question": question,
        "filter_dp_investor_menu_catalog_json": json.dumps(catalog, ensure_ascii=True),
    }
    user_str = json.dumps(user_payload, ensure_ascii=True)

    log: dict[str, Any] = {
        "phase": "filter_dp_investor_menu_params",
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
        raise ValueError("Empty filter_dp_investor_menu parameter response")

    raw = parse_json_content(content)
    if not isinstance(raw, dict):
        raise ValueError("Menu parameter LLM must return a JSON object")

    params = DpInvestorMenuParams.model_validate(raw)
    log["parsed"] = params.model_dump(mode="json")
    if params.unsupported_reason:
        log["unsupported_reason"] = params.unsupported_reason
    return params, log
